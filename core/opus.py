"""Lectura de una explosión de insumos exportada desde OPUS.

Este módulo **sólo lee**. No toca la base ni da nada de alta: devuelve lo que
encontró y una lista de avisos para que una persona los revise antes de
importar. Esa separación es a propósito: una explosión mal leída es material
comprado de menos o de más, y el momento de detectarlo es antes de escribir.

Sobre el formato, comprobado contra un archivo real del taller
(«Explosión de insumos Remolques», TL del Sur, jul-2026):

**El delimitador es la coma y el archivo está bien entrecomillado.** Era la
duda importante, porque en México OPUS suele escribir la coma como separador
decimal, y aquí las descripciones llevan comas de por sí. No es el caso: los
decimales van con punto (`95.826500`), la coma sólo separa millares y siempre
dentro de comillas (`"$5,368.77"`), y las descripciones con coma o con comilla
doble vienen escapadas según la regla de siempre
(`"CADENA DE ESLABONES DE 1/2"" DE 1 MT"`). El lector de csv de la biblioteca
estándar lo interpreta bien sin configurar nada.

**La rejilla tiene columnas de relleno.** El encabezado real es
`Clave,,Descripción,,,Unidad,Cantidad,,Costo,,Importe,,Porcentaje`: entre cada
dato hay una o dos columnas vacías. Se localizan por el encabezado y no por
posición fija, porque el relleno cambia entre versiones de OPUS.

**Hay renglones que no son insumos** y hay que saltarlos: doce de portada, el
título de la sección (`Tipo: Materiales`) y el total (`Total de Materiales`).
El total se guarda: cuadrar la suma contra él es la mejor prueba de que la
lectura fue correcta.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

# --------------------------------------------------------------- constantes

#: Las columnas del renglón de insumos, tal como las rotula OPUS.
COLUMNAS = ("Clave", "Descripción", "Unidad", "Cantidad", "Costo", "Importe", "Porcentaje")

#: Meses como los abrevia OPUS: `08/jul./2026`.
MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

#: Unidades que no son una cosa que se pueda guardar en un almacén. OPUS las
#: usa para costos indirectos que se calculan como porcentaje del total —
#: consumibles, fletes—. Entran en el costo del proyecto pero no generan
#: demanda de compra ni existencia física.
UNIDADES_NO_INVENTARIABLES = {"(%)m", "(%)mo", "(%)", "%"}

#: Unidades que se cuentan de una en una. Una cantidad con decimales en estas
#: no se puede surtir tal cual: no existen 2,945385 boquillas.
UNIDADES_DISCRETAS = {"pza", "pieza", "piezas", "jgo", "juego"}

#: Cuánto puede separarse `cantidad * costo` de `importe` sin que sea sospecha
#: de renglón mal partido. OPUS redondea el importe a centavos, así que un
#: centavo de diferencia es normal; más de un peso, no.
TOLERANCIA_IMPORTE = Decimal("1.00")


# ------------------------------------------------------------------ tipos


@dataclass(frozen=True)
class Aviso:
    """Algo que una persona tiene que mirar antes de importar.

    No es un error: el archivo se lee entero de todas formas. Es lo que el
    módulo no puede decidir solo.
    """

    clase: str
    detalle: str
    renglon: int = 0

    def __str__(self):
        sitio = f" (renglón {self.renglon})" if self.renglon else ""
        return f"{self.clase}: {self.detalle}{sitio}"


@dataclass(frozen=True)
class Partida:
    """Un insumo de la explosión."""

    clave: str
    descripcion: str
    unidad: str
    cantidad: Decimal
    costo: Decimal
    importe: Decimal
    tipo: str
    renglon: int

    @property
    def inventariable(self):
        return self.unidad.lower() not in UNIDADES_NO_INVENTARIABLES

    @property
    def discreta(self):
        return self.unidad.lower() in UNIDADES_DISCRETAS


@dataclass
class Cabecera:
    """La portada: de qué proyecto y de qué cliente es esta explosión."""

    proyecto: str = ""
    cliente: str = ""
    ubicacion: str = ""
    fecha_propuesta: date = None
    inicio_obra: date = None
    fin_obra: date = None
    duracion_dias: int = None


@dataclass
class Lectura:
    cabecera: Cabecera = field(default_factory=Cabecera)
    partidas: list = field(default_factory=list)
    totales: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)

    @property
    def importe_leido(self):
        return sum((p.importe for p in self.partidas), Decimal("0"))

    @property
    def cuadra(self):
        """Si la suma de los renglones coincide con el total que trae OPUS.

        Es la comprobación que de verdad prueba que el archivo se partió bien:
        un renglón mal separado descuadra la suma.
        """
        declarado = sum(self.totales.values(), Decimal("0"))
        if not declarado:
            return None
        return abs(self.importe_leido - declarado) <= TOLERANCIA_IMPORTE


# --------------------------------------------------------------- conversión


def _limpio(valor):
    return (valor or "").strip()


def a_decimal(valor):
    """`"$5,368.77"` → `Decimal("5368.77")`. Cadena vacía → `None`.

    Quita el signo de peso y los separadores de millar. El punto se respeta
    porque en este formato es el separador decimal.
    """
    texto = _limpio(valor).replace("$", "").replace(",", "").replace("%", "")
    if not texto:
        return None
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def a_fecha(valor):
    """`"08/jul./2026"` → `date(2026, 7, 8)`. Devuelve `None` si no se entiende."""
    texto = _limpio(valor)
    partes = re.split(r"[/\-\s]+", texto.replace(".", ""))
    if len(partes) != 3:
        return None
    dia, mes, anio = partes
    numero = MESES.get(mes[:3].lower())
    if numero is None:
        try:
            numero = int(mes)
        except ValueError:
            return None
    try:
        return date(int(anio), numero, int(dia))
    except ValueError:
        return None


# ------------------------------------------------------------------ lectura


def _celdas(renglon, indice):
    return _limpio(renglon[indice]) if indice < len(renglon) else ""


def _leer_cabecera(renglones, avisos):
    """Saca proyecto, cliente y fechas de la portada.

    Los rótulos aparecen de dos formas: unos con el valor pegado en la misma
    celda («Descripción del proyecto: Mantenimiento y…») y otros con el rótulo
    en una celda y el valor unas columnas más allá. Se busca por texto en vez
    de por posición porque la portada se descuadra entre exportaciones.
    """
    cabecera = Cabecera()

    def valor_tras(rotulo, numero_renglon, columna):
        """El primer valor no vacío a la derecha del rótulo."""
        for celda in renglones[numero_renglon][columna + 1:]:
            if _limpio(celda):
                return _limpio(celda)
        return ""

    for i, renglon in enumerate(renglones):
        for j, celda in enumerate(renglon):
            texto = _limpio(celda)
            if not texto or ":" not in texto:
                continue
            rotulo, _, pegado = texto.partition(":")
            rotulo = rotulo.strip().lower()
            pegado = pegado.strip()
            valor = pegado or valor_tras(rotulo, i, j)

            if rotulo.startswith("descripción del proyecto"):
                cabecera.proyecto = valor
            elif rotulo == "cliente":
                cabecera.cliente = valor
            elif rotulo == "ubicación":
                # Viene como «, Yucatán, »: OPUS deja los separadores de
                # ciudad y estado aunque falte la ciudad.
                cabecera.ubicacion = valor.strip(" ,")
            elif rotulo.startswith("fecha de propuesta"):
                cabecera.fecha_propuesta = a_fecha(valor)
            elif rotulo.startswith("inicio de obra"):
                cabecera.inicio_obra = a_fecha(valor)
            elif rotulo.startswith("fin de obra"):
                cabecera.fin_obra = a_fecha(valor)
                if cabecera.fin_obra is None and i > 0:
                    # En el archivo real el valor de «Fin de obra» aparece en
                    # el renglón de **arriba**, suelto y sin rótulo. Es un
                    # descuadre de la propia exportación, así que se recoge
                    # pero se avisa: no conviene fiarse en silencio.
                    suelto = a_fecha(_celdas(renglones[i - 1], j + 2))
                    if suelto:
                        cabecera.fin_obra = suelto
                        avisos.append(Aviso(
                            "portada descuadrada",
                            "«Fin de obra» venía sin valor y se tomó el del "
                            f"renglón anterior ({suelto.isoformat()})",
                            renglon=i + 1,
                        ))
            elif rotulo.startswith("duración en días"):
                numero = a_decimal(valor)
                cabecera.duracion_dias = int(numero) if numero is not None else None

    return cabecera


def _mapa_de_columnas(renglon):
    """Dónde cae cada columna, buscando sus rótulos.

    No se fija la posición: entre cada dato OPUS deja una o dos columnas de
    relleno y ese relleno cambia entre versiones.
    """
    mapa = {}
    for i, celda in enumerate(renglon):
        texto = _limpio(celda)
        for nombre in COLUMNAS:
            if texto.lower() == nombre.lower():
                mapa[nombre] = i
    return mapa


def leer(contenido):
    """Lee una explosión de insumos. Devuelve una `Lectura`.

    `contenido` es el texto del archivo. Nunca lanza por un renglón malo: lo
    salta y lo deja anotado en `avisos`.
    """
    if isinstance(contenido, bytes):
        # OPUS exporta en la codificación de Windows en español.
        for codificacion in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                contenido = contenido.decode(codificacion)
                break
            except UnicodeDecodeError:
                continue

    renglones = list(csv.reader(io.StringIO(contenido)))
    lectura = Lectura()
    lectura.cabecera = _leer_cabecera(renglones, lectura.avisos)

    mapa = {}
    tipo = ""
    vistas = {}

    for numero, renglon in enumerate(renglones, start=1):
        primera = _celdas(renglon, 0)

        if not mapa:
            posible = _mapa_de_columnas(renglon)
            if "Clave" in posible and "Cantidad" in posible:
                mapa = posible
                faltan = [c for c in COLUMNAS if c not in mapa]
                if faltan:
                    lectura.avisos.append(Aviso(
                        "columna ausente",
                        f"El encabezado no trae {', '.join(faltan)}",
                        renglon=numero,
                    ))
            continue

        if primera.lower().startswith("tipo:"):
            tipo = primera.split(":", 1)[1].strip()
            continue

        if primera.lower().startswith("total"):
            importe = a_decimal(_celdas(renglon, mapa.get("Importe", -1)))
            if importe is not None:
                lectura.totales[tipo or primera] = importe
            continue

        clave = primera
        cantidad = a_decimal(_celdas(renglon, mapa.get("Cantidad", -1)))
        if not clave or cantidad is None:
            continue

        partida = Partida(
            clave=clave,
            descripcion=_celdas(renglon, mapa.get("Descripción", -1)),
            unidad=_celdas(renglon, mapa.get("Unidad", -1)),
            cantidad=cantidad,
            costo=a_decimal(_celdas(renglon, mapa.get("Costo", -1))) or Decimal("0"),
            importe=a_decimal(_celdas(renglon, mapa.get("Importe", -1))) or Decimal("0"),
            tipo=tipo,
            renglon=numero,
        )
        lectura.partidas.append(partida)
        vistas.setdefault(partida.clave, []).append(partida)

    if not mapa:
        lectura.avisos.append(Aviso(
            "sin encabezado",
            "No se encontró el renglón con «Clave» y «Cantidad». "
            "¿Es una explosión de insumos de OPUS?",
        ))
        return lectura

    _revisar(lectura, vistas)
    return lectura


def _revisar(lectura, vistas):
    """Lo que una persona tiene que decidir. Ninguno de estos casos es un
    error del archivo: son cosas que el importador no puede resolver solo."""

    for clave, repetidas in vistas.items():
        if len(repetidas) > 1:
            suma = sum((p.cantidad for p in repetidas), Decimal("0"))
            lectura.avisos.append(Aviso(
                "clave repetida",
                f"«{clave}» aparece {len(repetidas)} veces con costos distintos "
                f"(suma {suma}). Hay que decidir si se acumulan o se importan aparte",
                renglon=repetidas[0].renglon,
            ))

    for partida in lectura.partidas:
        if not partida.inventariable:
            lectura.avisos.append(Aviso(
                "no inventariable",
                f"«{partida.clave}» viene en «{partida.unidad}»: es un costo "
                "indirecto calculado por porcentaje, no material que se guarde",
                renglon=partida.renglon,
            ))
        elif partida.discreta and partida.cantidad != partida.cantidad.to_integral_value():
            lectura.avisos.append(Aviso(
                "fracción de pieza",
                f"«{partida.clave}»: {partida.cantidad} {partida.unidad}. "
                "Del almacén no se puede surtir una fracción de pieza",
                renglon=partida.renglon,
            ))

        esperado = partida.cantidad * partida.costo
        if abs(esperado - partida.importe) > TOLERANCIA_IMPORTE:
            lectura.avisos.append(Aviso(
                "importe descuadrado",
                f"«{partida.clave}»: {partida.cantidad} x {partida.costo} = "
                f"{esperado:.2f}, pero el archivo dice {partida.importe}. "
                "Suele ser señal de un renglón mal separado",
                renglon=partida.renglon,
            ))

    if lectura.cuadra is False:
        declarado = sum(lectura.totales.values(), Decimal("0"))
        lectura.avisos.append(Aviso(
            "total descuadrado",
            f"La suma de los renglones da {lectura.importe_leido:.2f} y el "
            f"archivo declara {declarado:.2f}",
        ))
