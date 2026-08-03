"""Inventario de materia prima: existencias, lotes, trazabilidad y costo.

El módulo se sostiene sobre una idea: **el lote**. Sin él no se puede
responder de qué colada salió una pieza ni cuánto costó de verdad una orden, y
esas dos preguntas son la razón de que el inventario exista. Buena parte de
estos tests comprueban justamente eso.
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.excepciones import CantidadInvalida, MotivoRequerido, StockInsuficiente
from core.servicios import inventario as servicio
from core.servicios import produccion
from inventario.models import (
    Almacen,
    Existencia,
    ListaMateriales,
    LoteMaterial,
    Material,
    MovimientoMaterial,
    Proveedor,
    RenglonListaMateriales,
)
from nucleo.models import LineaNegocio, MotivoEvento, PiezaCatalogo

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


@pytest.fixture
def almacen():
    call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
    call_command("sembrar_inventario", verbosity=0, stdout=StringIO())
    return servicio.almacen_principal()


@pytest.fixture
def material(almacen):
    return Material.objects.using("mes").create(
        codigo="PL-TEST", nombre="Lámina negra 3.4mm", nombre_normalizado="LÁMINA NEGRA 3.4MM",
        unidad=Material.Unidad.PIEZA, peso_kg=Decimal("75.820"), stock_minimo=Decimal("5"),
    )


def crear_lote(material, codigo, colada, costo, dia, proveedor=None):
    return LoteMaterial.objects.using("mes").create(
        material=material,
        codigo=codigo,
        colada=colada,
        costo_unitario=Decimal(costo),
        proveedor=proveedor,
        recibido_en=timezone.localdate() - timezone.timedelta(days=dia),
    )


def motivo(codigo, ambito=MotivoEvento.Ambito.AJUSTE):
    return MotivoEvento.objects.using("mes").get(ambito=ambito, codigo=codigo)


class TestSembrado:
    def test_trae_el_catalogo_de_placas_que_ya_existia(self):
        """Ciento trece placas capturadas a lo largo de años.

        Volverlas a capturar a mano sería tirar ese trabajo y además meter
        erratas.
        """
        from catalogos.models import LaserMaterialPlaca

        LaserMaterialPlaca.objects.create(
            nombre="LÁMINA NEGRA", categoria_material="ACERO",
            tipo_material="LÁMINA NEGRA: acero al carbón", calibre="10",
            espesor_mm=3.42, largo_mm=3048, ancho_mm=914, peso_kg=75.82,
        )
        call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
        call_command("sembrar_inventario", verbosity=0, stdout=StringIO())

        material = Material.objects.using("mes").get(legacy_modelo="LaserMaterialPlaca")
        assert material.peso_kg == Decimal("75.820")
        assert "3048×914" in material.nombre, "el nombre tiene que distinguir la medida"

    def test_calcula_el_peso_de_las_placas_que_no_lo_traian(self):
        from catalogos.models import LaserMaterialPlaca

        LaserMaterialPlaca.objects.create(
            nombre="LÁMINA SIN PESO", categoria_material="ACERO",
            espesor_mm=3.0, largo_mm=2000, ancho_mm=1000, peso_kg=0.0,
        )
        call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
        call_command("sembrar_inventario", verbosity=0, stdout=StringIO())

        material = Material.objects.using("mes").get(legacy_modelo="LaserMaterialPlaca")
        # 2000 × 1000 × 3 mm de acero a 7.85 kg/dm³ son 47.1 kg.
        assert material.peso_kg == Decimal("47.100")

    def test_todo_empieza_en_cero(self, almacen):
        """El inventario arranca contando, no suponiendo.

        Un almacén que empieza con cifras inventadas no vuelve a cuadrar
        nunca, y encima se cree.
        """
        assert Existencia.objects.using("mes").exclude(cantidad=0).count() == 0


class TestEntradasYSalidas:
    def test_la_entrada_sube_la_existencia(self, material, almacen):
        lote = crear_lote(material, "L-1", "H-1001", "1200", dia=10)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")
        assert servicio.existencia(material) == Decimal("10")

    def test_el_mismo_envio_repetido_no_cuenta_dos_veces(self, material, almacen):
        lote = crear_lote(material, "L-1", "H-1001", "1200", dia=10)
        for _ in range(2):
            servicio.registrar_entrada(
                lote=lote, cantidad=10, actor="ana", clave_idempotencia="entrada-77"
            )
        assert servicio.existencia(material) == Decimal("10")

    def test_no_se_puede_sacar_lo_que_no_hay(self, material, almacen):
        lote = crear_lote(material, "L-1", "H-1001", "1200", dia=10)
        servicio.registrar_entrada(lote=lote, cantidad=3, actor="ana")

        with pytest.raises(StockInsuficiente):
            servicio.consumir(material=material, cantidad=5, actor="ana")

    def test_la_base_tampoco_deja_dejarlo_en_negativo(self, material, almacen):
        """Ni el servicio, ni un update en bloque, ni una consulta a mano."""
        from django.db.utils import IntegrityError

        lote = crear_lote(material, "L-1", "H-1001", "1200", dia=10)
        servicio.registrar_entrada(lote=lote, cantidad=3, actor="ana")

        with pytest.raises(IntegrityError):
            Existencia.objects.using("mes").filter(material=material).update(
                cantidad=Decimal("-1")
            )

    def test_una_entrada_de_cero_o_negativa_se_rechaza(self, material, almacen):
        lote = crear_lote(material, "L-1", "H-1001", "1200", dia=10)
        with pytest.raises(CantidadInvalida):
            servicio.registrar_entrada(lote=lote, cantidad=0, actor="ana")


class TestConsumoPorAntiguedad:
    """De dónde sale el material decide cuánto cuesta la orden."""

    @pytest.fixture
    def con_tres_lotes(self, material, almacen):
        viejo = crear_lote(material, "L-VIEJO", "H-1001", "1000", dia=30)
        medio = crear_lote(material, "L-MEDIO", "H-1002", "1200", dia=20)
        nuevo = crear_lote(material, "L-NUEVO", "H-1003", "1500", dia=1)
        for lote in (nuevo, medio, viejo):  # a propósito en desorden
            servicio.registrar_entrada(lote=lote, cantidad=5, actor="ana")
        return viejo, medio, nuevo

    def test_sale_primero_lo_que_entro_antes(self, material, con_tres_lotes):
        viejo, medio, nuevo = con_tres_lotes

        servicio.consumir(material=material, cantidad=5, actor="beto")

        assert servicio.existencia(material, lote=viejo) == Decimal("0")
        assert servicio.existencia(material, lote=medio) == Decimal("5")
        assert servicio.existencia(material, lote=nuevo) == Decimal("5")

    def test_un_consumo_que_cruza_lotes_deja_un_apunte_por_cada_uno(
        self, material, con_tres_lotes
    ):
        """Un solo apunte no diría de qué coladas está hecha la orden."""
        viejo, medio, _ = con_tres_lotes

        movimientos = servicio.consumir(material=material, cantidad=8, actor="beto")

        assert len(movimientos) == 2
        assert {m.lote_id for m in movimientos} == {viejo.pk, medio.pk}
        assert abs(movimientos[0].cantidad) == Decimal("5")
        assert abs(movimientos[1].cantidad) == Decimal("3")

    def test_cada_apunte_guarda_el_costo_de_su_lote(self, material, con_tres_lotes):
        """Si mañana se corrige el precio de un lote, lo ya consumido no cambia."""
        movimientos = servicio.consumir(material=material, cantidad=8, actor="beto")
        assert [m.costo_unitario for m in movimientos] == [
            Decimal("1000.000000"), Decimal("1200.000000")
        ]

    def test_se_puede_forzar_un_lote_concreto(self, material, con_tres_lotes):
        _, _, nuevo = con_tres_lotes
        servicio.consumir(material=material, cantidad=2, actor="beto", lote=nuevo)
        assert servicio.existencia(material, lote=nuevo) == Decimal("3")

    def test_forzar_un_lote_sin_material_suficiente_se_rechaza(
        self, material, con_tres_lotes
    ):
        _, _, nuevo = con_tres_lotes
        with pytest.raises(servicio.LoteAgotado):
            servicio.consumir(material=material, cantidad=99, actor="beto", lote=nuevo)


class TestTrazabilidad:
    """Las dos preguntas que hoy se responden buscando en el correo."""

    @pytest.fixture
    def orden_con_material(self, material, almacen):
        linea = LineaNegocio.objects.using("mes").get(codigo="corta")
        orden = produccion.crear_orden(
            linea=linea, actor="ana", codigo="CORTE-1", total_piezas=4
        )
        proveedor = Proveedor.objects.using("mes").create(nombre="Aceros del Sureste")
        lote = crear_lote(material, "L-A", "COLADA-48213", "1200", dia=5, proveedor=proveedor)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")
        servicio.consumir(material=material, cantidad=4, actor="beto", orden=orden)
        return orden, lote

    def test_de_una_colada_a_las_ordenes(self, orden_con_material):
        """Lo que se pregunta cuando la acería avisa de un lote defectuoso."""
        orden, _ = orden_con_material
        movimientos = servicio.ordenes_de_la_colada("COLADA-48213")
        assert [m.orden_id for m in movimientos] == [orden.pk]

    def test_la_colada_se_busca_sin_distinguir_mayusculas(self, orden_con_material):
        assert servicio.ordenes_de_la_colada("colada-48213").count() == 1

    def test_de_una_orden_a_sus_coladas(self, orden_con_material):
        """La pregunta inversa: de qué está hecho lo que entregamos."""
        orden, lote = orden_con_material
        movimientos = servicio.coladas_de_la_orden(orden)
        assert [m.lote_id for m in movimientos] == [lote.pk]
        assert movimientos[0].lote.proveedor.nombre == "Aceros del Sureste"

    def test_el_costo_de_material_de_la_orden(self, orden_con_material):
        orden, _ = orden_con_material
        assert servicio.costo_material_de(orden) == Decimal("4800.0000")

    def test_devolver_material_baja_el_costo_de_la_orden(self, orden_con_material):
        orden, _ = orden_con_material
        consumo = MovimientoMaterial.objects.using("mes").get(
            tipo=MovimientoMaterial.Tipo.CONSUMO
        )

        servicio.devolver(movimiento=consumo, actor="ana", cantidad=1)

        assert servicio.costo_material_de(orden) == Decimal("3600.0000")
        assert servicio.existencia(consumo.material) == Decimal("7")

    def test_devolver_no_borra_el_consumo(self, orden_con_material):
        """Corregir es añadir el apunte contrario, no editar el anterior."""
        consumo = MovimientoMaterial.objects.using("mes").get(
            tipo=MovimientoMaterial.Tipo.CONSUMO
        )
        servicio.devolver(movimiento=consumo, actor="ana", cantidad=1)

        consumo.refresh_from_db(using="mes")
        assert consumo.cantidad == Decimal("-4")
        assert consumo.anulado_por.count() == 1

    def test_no_se_puede_devolver_mas_de_lo_consumido(self, orden_con_material):
        consumo = MovimientoMaterial.objects.using("mes").get(
            tipo=MovimientoMaterial.Tipo.CONSUMO
        )
        with pytest.raises(CantidadInvalida):
            servicio.devolver(movimiento=consumo, actor="ana", cantidad=99)


class TestAjustesYMermas:
    def test_un_ajuste_sin_motivo_se_rechaza(self, material, almacen):
        """Un inventario que se ajusta sin explicar por qué es una opinión."""
        with pytest.raises(MotivoRequerido):
            servicio.ajustar(material=material, cantidad=5, actor="ana", motivo=None)

    def test_el_ajuste_mueve_la_existencia_y_queda_registrado(self, material, almacen):
        lote = crear_lote(material, "L-1", "", "0", dia=1)
        servicio.ajustar(
            material=material, cantidad=7, actor="ana",
            motivo=motivo("inventario_inicial"), lote=lote,
        )
        assert servicio.existencia(material) == Decimal("7")
        movimiento = MovimientoMaterial.objects.using("mes").get()
        assert movimiento.motivo.codigo == "inventario_inicial"

    def test_la_merma_es_un_tipo_propio_y_no_un_ajuste(self, material, almacen):
        """Mezclarlas impide saber cuánto se está tirando.

        La merma es una pérdida que se puede medir y reducir; el ajuste es que
        la cuenta estaba mal. Son cosas distintas.
        """
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")

        servicio.registrar_merma(
            material=material, lote=lote, cantidad=2, actor="ana",
            motivo=motivo("merma_de_corte"),
        )

        assert servicio.existencia(material) == Decimal("8")
        assert MovimientoMaterial.objects.using("mes").filter(
            tipo=MovimientoMaterial.Tipo.MERMA
        ).count() == 1


class TestTraslados:
    def test_mueve_material_entre_almacenes_con_dos_apuntes(self, material, almacen):
        """Dos apuntes para que cada almacén tenga su historial completo."""
        otro = Almacen.objects.using("mes").create(codigo="obra", nombre="Bodega de obra")
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")

        salida, entrada = servicio.trasladar(
            material=material, lote=lote, origen=almacen, destino=otro,
            cantidad=4, actor="ana",
        )

        assert servicio.existencia(material, almacen=almacen) == Decimal("6")
        assert servicio.existencia(material, almacen=otro) == Decimal("4")
        assert salida.traslado == entrada.traslado, "los dos apuntes van emparejados"

    def test_no_se_traslada_lo_que_no_hay(self, material, almacen):
        otro = Almacen.objects.using("mes").create(codigo="obra", nombre="Bodega de obra")
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=2, actor="ana")

        with pytest.raises(StockInsuficiente):
            servicio.trasladar(
                material=material, lote=lote, origen=almacen, destino=otro,
                cantidad=5, actor="ana",
            )


class TestListaDeMateriales:
    """Propone. No descuenta. Y ésa es la decisión de diseño del módulo."""

    @pytest.fixture
    def con_lista(self, material, almacen):
        linea = LineaNegocio.objects.using("mes").get(codigo="corta")
        pieza = PiezaCatalogo.objects.using("mes").create(
            linea=linea, nombre="Tapa D04", nombre_normalizado="TAPA D04"
        )
        lista = ListaMateriales.objects.using("mes").create(pieza=pieza, version=1)
        RenglonListaMateriales.objects.using("mes").create(
            lista=lista, material=material,
            cantidad_por_pieza=Decimal("0.5"), merma_porcentaje=Decimal("10"),
        )
        return pieza, lista

    def test_propone_la_cantidad_con_su_merma(self, material, con_lista):
        pieza, _ = con_lista
        propuesta = servicio.consumo_sugerido(pieza, 10)
        # 0.5 por pieza más un 10% de merma, por diez piezas.
        assert propuesta[0]["cantidad"] == Decimal("5.500000")

    def test_proponer_no_mueve_nada_del_almacen(self, material, con_lista):
        pieza, _ = con_lista
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")

        servicio.consumo_sugerido(pieza, 10)

        assert servicio.existencia(material) == Decimal("10"), (
            "una lista incorrecta que descuenta sola vacía el almacén en una semana"
        )

    def test_compara_lo_previsto_con_lo_gastado(self, material, con_lista):
        """El informe que decide si se puede automatizar el descuento."""
        pieza, _ = con_lista
        linea = LineaNegocio.objects.using("mes").get(codigo="corta")
        orden = produccion.crear_orden(
            linea=linea, actor="ana", codigo="C-1", total_piezas=10,
            cantidad_objetivo=10, pieza=pieza,
        )
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")
        servicio.consumir(material=material, cantidad=7, actor="beto", orden=orden)

        comparacion = servicio.comparar_consumo(orden)

        assert comparacion[0]["previsto"] == Decimal("5.500000")
        assert comparacion[0]["real"] == Decimal("7.000000")
        assert comparacion[0]["diferencia"] == Decimal("1.500000")


class TestCacheYVerificacion:
    def test_las_existencias_se_reconstruyen_desde_los_movimientos(self, material, almacen):
        """La verdad es el historial; la existencia es una caché."""
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")
        Existencia.objects.using("mes").filter(material=material).update(
            cantidad=Decimal("99")
        )

        assert servicio.descuadres(), "el descuadre tiene que detectarse"
        servicio.recalcular_existencias()

        assert servicio.existencia(material) == Decimal("10")
        assert not servicio.descuadres()

    def test_el_comando_falla_cuando_no_cuadran(self, material, almacen):
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")
        Existencia.objects.using("mes").filter(material=material).update(
            cantidad=Decimal("99")
        )

        with pytest.raises(SystemExit):
            call_command("verificar_inventario", verbosity=0, stdout=StringIO())

    def test_el_comando_pasa_cuando_cuadran(self, material, almacen):
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=10, actor="ana")
        call_command("verificar_inventario", verbosity=0, stdout=StringIO())

    def test_avisa_de_lo_que_esta_bajo_minimo(self, material, almacen):
        lote = crear_lote(material, "L-1", "H-1", "1000", dia=5)
        servicio.registrar_entrada(lote=lote, cantidad=2, actor="ana")

        faltantes = servicio.bajo_minimo()

        assert len(faltantes) == 1
        assert faltantes[0][2] == Decimal("3"), "faltan 3 para llegar al mínimo de 5"

    def test_el_valor_del_almacen_se_calcula_lote_a_lote(self, material, almacen):
        """No por promedio: así el número cuadra con lo que se pagó."""
        barato = crear_lote(material, "L-1", "H-1", "1000", dia=10)
        caro = crear_lote(material, "L-2", "H-2", "2000", dia=1)
        servicio.registrar_entrada(lote=barato, cantidad=3, actor="ana")
        servicio.registrar_entrada(lote=caro, cantidad=2, actor="ana")

        assert servicio.valor_de_existencias() == Decimal("7000.0000")
