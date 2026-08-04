"""Lectura de la explosión de insumos de OPUS.

El riesgo de este módulo no es que reviente: es que **lea mal en silencio**.
Un renglón mal separado en una explosión de insumos es material comprado de
menos o de más, y no se nota hasta que falta en el piso.

La duda de partida era el delimitador. En México OPUS suele escribir la coma
como separador decimal, y las descripciones de insumos llevan comas de por sí
(«PLACA DE 1/2", A-36»), así que una coma estricta sin reglas de comillas
partiría los renglones mal.

Comprobado contra un archivo real del taller, **no es el caso**: los decimales
van con punto, la coma sólo separa millares y siempre dentro de comillas, y
las descripciones vienen entrecomilladas según la regla de siempre. Estos
tests fijan eso, para que si mañana llega una exportación distinta se sepa por
qué dejó de funcionar.

El archivo de prueba es una copia anonimizada del real: mismos entrecomillados,
misma portada descuadrada, misma clave repetida, misma unidad de porcentaje y
mismas fracciones de pieza, con nombres y precios inventados. El original
lleva costos de proveedor y el nombre del cliente, y eso no tiene por qué
quedar guardado en el repositorio.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings

from core import opus

ARCHIVO = Path(settings.BASE_DIR) / "tests" / "datos" / "opus_explosion.csv"


@pytest.fixture(scope="module")
def lectura():
    return opus.leer(ARCHIVO.read_text(encoding="utf-8"))


class TestLaComaSepara:
    """Lo que se dudaba antes de ver un archivo real."""

    def test_lee_todos_los_insumos(self, lectura):
        assert len(lectura.partidas) == 7

    def test_la_suma_cuadra_con_el_total_del_archivo(self, lectura):
        """La prueba de verdad de que el archivo se partió bien.

        Un renglón mal separado cambia una cantidad o un importe y la suma
        deja de cuadrar. Que coincida al centavo con lo que declara OPUS dice
        que las 7 filas y sus 13 columnas se leyeron enteras.
        """
        assert lectura.importe_leido == Decimal("20000.00")
        assert lectura.cuadra is True

    def test_una_descripcion_con_coma_no_se_parte(self, lectura):
        """`"CADENA DE ESLABONES DE 1/2"" DE 1 MT"` es **un** campo."""
        cadena = next(p for p in lectura.partidas if p.clave == "CADENA-B")
        assert cadena.descripcion == 'CADENA DE ESLABONES DE 1/2" DE 1 MT'
        assert cadena.cantidad == Decimal("20")

    def test_una_clave_con_comilla_doble_sobrevive(self, lectura):
        # La clave del archivo es ANULAR-C seguido de una comilla doble —la
        # marca de pulgada—, que OPUS escapa duplicándola y envuelve el campo
        # entre comillas. Va como comentario y no como docstring justamente
        # porque escribirlo aquí cerraría el docstring antes de tiempo.
        assert any(p.clave == 'ANULAR-C"' for p in lectura.partidas)

    def test_el_millar_entrecomillado_no_se_lee_como_dos_columnas(self, lectura):
        """`"$10,000.00"` son diez mil, no diez."""
        lamina = next(p for p in lectura.partidas if p.clave == "LAMINA-A")
        assert lamina.costo == Decimal("1000.00")
        assert lamina.importe == Decimal("10000.00")

    def test_los_decimales_van_con_punto(self, lectura):
        anular = next(p for p in lectura.partidas if p.clave.startswith("ANULAR"))
        assert anular.cantidad == Decimal("0.500000")


class TestLasColumnasSeBuscanPorSuRotulo:
    def test_no_se_usa_una_posicion_fija(self, lectura):
        """Entre cada dato OPUS deja una o dos columnas vacías, y ese relleno
        cambia entre versiones. Si se leyera por posición, bastaría una
        columna de más para desplazarlo todo."""
        solera = next(p for p in lectura.partidas if p.clave == "SOLERA-D")
        assert solera.unidad == "kg"
        assert solera.cantidad == Decimal("25")
        assert solera.costo == Decimal("100.00")

    def test_se_recortan_los_espacios_sobrantes(self, lectura):
        solera = next(p for p in lectura.partidas if p.clave == "SOLERA-D")
        assert solera.descripcion.endswith("FINAL")

    def test_el_renglon_de_total_no_es_un_insumo(self, lectura):
        assert not any(p.clave.lower().startswith("total") for p in lectura.partidas)
        assert lectura.totales == {"Materiales": Decimal("20000.00")}

    def test_el_titulo_de_seccion_marca_el_tipo(self, lectura):
        assert {p.tipo for p in lectura.partidas} == {"Materiales"}


class TestLaPortada:
    def test_saca_proyecto_y_cliente(self, lectura):
        assert "bastidores" in lectura.cabecera.proyecto
        assert lectura.cabecera.cliente == "Cliente De Prueba SA de CV"

    def test_limpia_la_ubicacion(self, lectura):
        """Viene como «, Yucatán, »: OPUS deja los separadores aunque falte
        la ciudad."""
        assert lectura.cabecera.ubicacion == "Yucatán"

    def test_entiende_el_mes_abreviado_en_español(self, lectura):
        assert lectura.cabecera.fecha_propuesta == date(2026, 7, 8)
        assert lectura.cabecera.inicio_obra == date(2026, 7, 21)

    def test_recoge_el_fin_de_obra_descuadrado_y_avisa(self, lectura):
        """En el archivo real —y en esta copia— el valor de «Fin de obra»
        aparece en el renglón de arriba, suelto y sin rótulo. Se recoge, pero
        no en silencio: fiarse de un descuadre sin decirlo es cómo se cuelan
        los errores de fecha."""
        assert lectura.cabecera.fin_obra == date(2026, 7, 23)
        assert any(a.clase == "portada descuadrada" for a in lectura.avisos)

    def test_la_duracion_es_un_numero(self, lectura):
        assert lectura.cabecera.duracion_dias == 3


class TestLoQueTieneQueDecidirUnaPersona:
    """Avisos, no errores. El archivo se lee entero de todas formas."""

    def _de(self, lectura, clase):
        return [a for a in lectura.avisos if a.clase == clase]

    def test_una_clave_repetida_no_se_pisa_sola(self, lectura):
        """`INDIRECTO-F` sale dos veces con costos distintos. Un importador
        que dé de alta por clave o revienta o se queda con la última: las dos
        cosas son datos perdidos sin avisar."""
        avisos = self._de(lectura, "clave repetida")
        assert len(avisos) == 1
        assert "INDIRECTO-F" in avisos[0].detalle
        # Y las dos siguen en la lectura, sin fusionar.
        assert len([p for p in lectura.partidas if p.clave == "INDIRECTO-F"]) == 2

    def test_los_costos_por_porcentaje_no_son_material(self, lectura):
        """«(%)m» es un indirecto calculado sobre el total —consumibles,
        fletes—. Entra en el costo del proyecto pero no se guarda en un
        almacén ni genera una compra."""
        avisos = self._de(lectura, "no inventariable")
        assert len(avisos) == 2
        assert all(not p.inventariable for p in lectura.partidas if p.unidad == "(%)m")

    def test_no_se_puede_surtir_media_pieza(self, lectura):
        """OPUS reparte el desgaste de consumibles entre proyectos, así que
        salen cantidades como 0,5 pza. Del almacén no sale media boquilla."""
        avisos = self._de(lectura, "fracción de pieza")
        assert len(avisos) == 1
        assert "ANULAR" in avisos[0].detalle

    def test_un_kilo_fraccionario_no_avisa(self, lectura):
        """25,5 kg es perfectamente surtible: el aviso es sólo para las
        unidades que se cuentan de una en una."""
        assert not any("SOLERA-D" in a.detalle for a in lectura.avisos)


class TestUnRenglonMalLeidoSeNota:
    """La red de seguridad contra el fallo que de verdad da miedo: que una
    exportación distinta parta mal una fila y nadie se entere.

    Hay dos comprobaciones y **cazan cosas distintas**, así que hacen falta
    las dos:

    - `cantidad x costo` contra el importe del propio renglón, que delata una
      cantidad o un costo corrompidos.
    - la suma de importes contra el total del archivo, que delata un importe
      corrompido o un renglón que se perdió entero.

    Cada una es ciega al fallo de la otra.
    """

    def _con(self, viejo, nuevo):
        return opus.leer(ARCHIVO.read_text(encoding="utf-8").replace(viejo, nuevo))

    def test_una_cantidad_corrompida_la_caza_el_renglon(self):
        """Y el total sigue cuadrando, porque los importes no se tocaron: por
        eso la suma sola no basta."""
        lectura = self._con(
            "LAMINA-A,,LAMINA LISA DE PRUEBA,,,pza,10.000000",
            "LAMINA-A,,LAMINA LISA DE PRUEBA,,,pza,1.000000",
        )
        descuadres = [a for a in lectura.avisos if a.clase == "importe descuadrado"]
        assert len(descuadres) == 1
        assert "LAMINA-A" in descuadres[0].detalle
        assert lectura.cuadra is True

    def test_un_importe_corrompido_lo_caza_el_total(self):
        lectura = self._con('"$10,000.00",,50.00%', '"$1,000.00",,50.00%')
        assert lectura.cuadra is False
        assert any(a.clase == "total descuadrado" for a in lectura.avisos)

    def test_un_renglon_perdido_lo_caza_el_total(self):
        """Si una fila se cae —por una comilla sin cerrar, por ejemplo—, el
        importe leído baja y la suma deja de coincidir."""
        sin_cadena = "\n".join(
            r for r in ARCHIVO.read_text(encoding="utf-8").splitlines()
            if not r.startswith("CADENA-B")
        )
        lectura = opus.leer(sin_cadena)
        assert len(lectura.partidas) == 6
        assert lectura.cuadra is False


class TestNoRevienta:
    def test_un_archivo_que_no_es_de_opus_avisa_en_vez_de_fallar(self):
        lectura = opus.leer("hola,mundo\n1,2\n")
        assert lectura.partidas == []
        assert any(a.clase == "sin encabezado" for a in lectura.avisos)

    def test_un_archivo_vacio_no_falla(self):
        assert opus.leer("").partidas == []

    def test_lee_la_codificación_de_windows(self):
        """OPUS exporta desde Windows en español, no en UTF-8."""
        crudo = ARCHIVO.read_text(encoding="utf-8").encode("cp1252")
        assert opus.leer(crudo).cabecera.ubicacion == "Yucatán"


class TestConversiones:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ('"$5,368.77"'.strip('"'), Decimal("5368.77")),
            ("$4.85", Decimal("4.85")),
            ("$0.20", Decimal("0.20")),
            ("95.826500", Decimal("95.826500")),
            ("0.53%", Decimal("0.53")),
            ("", None),
            ("no es un número", None),
        ],
    )
    def test_dinero_y_cantidades(self, texto, esperado):
        assert opus.a_decimal(texto) == esperado

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("08/jul./2026", date(2026, 7, 8)),
            ("21/jul./2026", date(2026, 7, 21)),
            ("01/dic./2025", date(2025, 12, 1)),
            ("15/03/2026", date(2026, 3, 15)),
            ("", None),
            ("mañana", None),
            ("32/ene./2026", None),
        ],
    )
    def test_fechas(self, texto, esperado):
        assert opus.a_fecha(texto) == esperado
