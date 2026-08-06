"""Leer una cotización de Corta.mx en PDF y sacar de ahí el pedido.

Hoy la cotización se genera en la página, se baja en PDF y alguien vuelve a
teclear a mano lo que ya está escrito ahí: el folio, la pieza, las medidas, el
material, el espesor y la cantidad. Se teclea mal de vez en cuando, y una
medida mal tecleada se corta mal.

El PDF lo produce **Tempus Tools**, que es el motor de cotización que hay
detrás de Corta.mx, y trae capa de texto, así que no hace falta reconocer
imágenes: se lee.

Dos trampas de ese PDF, y las dos vienen de que coloca cada letra por separado:

1. Hay texto que sale con las letras sueltas -«C o r t - 1 1 9»-, porque el
   generador escribe glifo a glifo.
2. Hay espacios metidos dentro de los números -«1,1 12.00» por «1,112.00»-,
   que salen de los pares de kerning.

Los dos se arreglan antes de mirar nada, en `enderezar`. Si algún día cambian
el formato, lo que se rompe es la lectura, no el sistema: esto **no crea nada**,
sólo propone, y quien captura ve lo leído y lo corrige antes de guardar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Renglon:
    """Una pieza de la cotización. Cada una es un pedido."""

    numero: int
    parte: str = ""
    largo_mm: float = 0.0
    ancho_mm: float = 0.0
    material: str = ""
    espesor_mm: float = 0.0
    cantidad: int = 0
    procesos: list[str] = field(default_factory=list)

    @property
    def completo(self) -> bool:
        return bool(self.parte and self.largo_mm > 0 and self.ancho_mm > 0 and self.cantidad > 0)


@dataclass
class Cotizacion:
    folio: str = ""
    caducidad: str = ""
    renglones: list[Renglon] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def vacia(self) -> bool:
        return not self.renglones


def _juntar_run(fragmento: str) -> str:
    """«C o r t - 1 1 9» -> «Cort-119», sin pegar palabras que sí van sueltas.

    Se junta cada tramo de tres o más letras seguidas separadas por **un solo**
    espacio. El doble espacio es lo que el generador usa para separar palabras
    cuando ya está separando las letras, así que rompe el tramo: «N o t a s  a
    d i c i o n a l e s» son dos palabras, no una.

    El umbral de tres evita destrozar texto normal: «de la pieza» no se toca.
    """
    trozos = re.split(r"( +)", fragmento)
    # trozos alterna palabra, separador, palabra, ... Se guardan en pares para
    # poder devolver el texto tal cual cuando el tramo no llega a tres.
    pares: list[tuple[str, str]] = []
    for i in range(0, len(trozos), 2):
        pares.append((trozos[i], trozos[i + 1] if i + 1 < len(trozos) else ""))

    salida: list[str] = []
    i = 0
    while i < len(pares):
        if len(pares[i][0]) != 1:
            salida.append(pares[i][0])
            salida.append(pares[i][1])
            i += 1
            continue

        # Hasta dónde llega el tramo de letras sueltas: mientras la palabra sea
        # de un carácter y el separador con la siguiente sea un solo espacio.
        fin = i
        while fin + 1 < len(pares) and pares[fin][1] == " " and len(pares[fin + 1][0]) == 1:
            fin += 1

        largo = fin - i + 1
        if largo >= 3:
            salida.append("".join(p[0] for p in pares[i : fin + 1]))
            salida.append(pares[fin][1])
        else:
            for par in pares[i : fin + 1]:
                salida.append(par[0])
                salida.append(par[1])
        i = fin + 1
    return "".join(salida)


def enderezar(texto: str) -> str:
    """Deshace lo que el generador del PDF le hizo al texto.

    El signo de peso se aparta antes de juntar letras. Si no, «3 $ 7 8 7 . 0 6»
    es un tramo entero de caracteres sueltos y se juntaría en «3$787.06»,
    perdiendo el espacio que separa la cantidad del precio, que es justo el
    que marca dónde acaba cada pieza.

    El espacio entre dos dígitos siempre sobra: en esta cotización no hay
    ningún sitio donde dos números seguidos se separen sólo por un espacio.
    """
    lineas = []
    for linea in (texto or "").splitlines():
        linea = " $".join(_juntar_run(f) for f in linea.split("$"))
        anterior = None
        while anterior != linea:
            anterior = linea
            linea = re.sub(r"(?<=\d) (?=\d)", "", linea)
        lineas.append(re.sub(r"\s{2,}", " ", linea).strip())
    return "\n".join(lineas)


def _numero(bruto: str) -> float:
    try:
        return float((bruto or "").replace(",", "").strip())
    except ValueError:
        return 0.0


_FOLIO = re.compile(r"N[uú]mero de cotizaci[oó]n:\s*(\S+)", re.I)
_CADUCIDAD = re.compile(r"Fecha de caducidad:\s*(\S+)", re.I)
_MEDIDAS = re.compile(r"([\d.,]+)\s*[x×]\s*([\d.,]+)\s*mm", re.I)
_ESPESOR = re.compile(r"(?:Espesor|Thickness)\s*:\s*([\d.,]+)\s*mm", re.I)
_SOLO_NUMERO = re.compile(r"^(\d{1,3})$")
_CANTIDAD_Y_PRECIOS = re.compile(r"^(\d+)\s+\$\s*[\d.,]+")
# Lo que no es dato de la pieza aunque caiga dentro del bloque.
_RUIDO = re.compile(r"^(subtotal|iva|total|precio|unitario|cantidad|#)\b", re.I)


def leer(texto: str) -> Cotizacion:
    """De la capa de texto del PDF a la cotización.

    Se parte de que cada pieza empieza con una línea que es sólo su número de
    renglón y termina con la línea de cantidad y precios («3 $787.06 …»). Es lo
    que hace el generador, y da un principio y un final que no dependen de en
    qué orden imprima el resto.
    """
    cot = Cotizacion()
    plano = enderezar(texto)
    lineas = [ln for ln in plano.splitlines() if ln.strip()]

    for linea in lineas:
        if not cot.folio:
            m = _FOLIO.search(linea)
            if m:
                cot.folio = m.group(1).strip()
        if not cot.caducidad:
            m = _CADUCIDAD.search(linea)
            if m:
                cot.caducidad = m.group(1).strip()

    abierto: Renglon | None = None
    cuerpo: list[str] = []
    for linea in lineas:
        if abierto is None:
            m = _SOLO_NUMERO.match(linea)
            if m:
                abierto = Renglon(numero=int(m.group(1)))
                cuerpo = []
            continue

        fin = _CANTIDAD_Y_PRECIOS.match(linea)
        if fin:
            abierto.cantidad = int(fin.group(1))
            _rellenar(abierto, cuerpo)
            cot.renglones.append(abierto)
            abierto = None
            cuerpo = []
            continue

        if _RUIDO.match(linea):
            # El bloque se cortó sin llegar a la cantidad: lo que se abrió no
            # era una pieza. Pasa con el «#» de la cabecera de la tabla.
            abierto = None
            cuerpo = []
            continue

        cuerpo.append(linea)

    if not cot.folio:
        cot.avisos.append("No se encontró el número de cotización.")
    if cot.vacia:
        cot.avisos.append("No se encontró ninguna pieza en la cotización.")
    for r in cot.renglones:
        if not r.completo:
            cot.avisos.append(f"A la pieza {r.numero} le faltan datos: revísala antes de guardar.")
    return cot


def _rellenar(renglon: Renglon, cuerpo: list[str]) -> None:
    """Reparte las líneas sueltas de una pieza entre sus campos.

    Por contenido y no por posición: el generador cambia el orden según lo que
    tenga que imprimir -no todas las piezas llevan espesor, ni los mismos
    procesos- y una lectura por número de línea se rompería con la primera
    cotización que no se pareciera a esta.
    """
    sobrantes: list[str] = []
    for linea in cuerpo:
        m = _MEDIDAS.search(linea)
        if m and renglon.largo_mm <= 0:
            a = _numero(m.group(1))
            b = _numero(m.group(2))
            # El formulario pide largo y ancho por separado. La cotización sólo
            # da dos números: el mayor es el largo, que es como se captura hoy.
            renglon.largo_mm = max(a, b)
            renglon.ancho_mm = min(a, b)
            continue
        m = _ESPESOR.search(linea)
        if m:
            renglon.espesor_mm = _numero(m.group(1))
            continue
        sobrantes.append(linea)

    if sobrantes:
        # La primera línea suelta es el nombre de la pieza: va pegado al número
        # de renglón. Las demás son el material y los procesos.
        renglon.parte = sobrantes[0]
    if len(sobrantes) > 1:
        renglon.material = sobrantes[1]
    if len(sobrantes) > 2:
        renglon.procesos = sobrantes[2:]


def texto_de_pdf(datos: bytes) -> str:
    """La capa de texto del PDF, o vacío si no la tiene.

    Un PDF escaneado no trae texto y aquí no se reconocen imágenes. Devolver
    vacío hace que `leer` avise de que no encontró nada, que es la verdad.
    """
    from io import BytesIO

    from pypdf import PdfReader

    try:
        lector = PdfReader(BytesIO(datos))
        return "\n".join((pagina.extract_text() or "") for pagina in lector.pages)
    except Exception:
        return ""


def placa_parecida(renglon: Renglon):
    """La placa del catálogo que mejor encaja con lo que dice la cotización.

    La cotización trae «Acero A36» y «Espesor: 4.76 mm»; el catálogo tiene esos
    mismos datos repartidos en categoría, nombre y espesor. No hay una clave
    común, así que se puntúa: el espesor pesa más que el nombre porque una
    placa del mismo material con otro espesor **no sirve**, y confundirlas
    saldría en kilos y en dinero.

    Devuelve `None` si no hay nada razonable. Es preferible dejar el campo
    vacío a elegir por la persona que captura: el material decide el precio.
    """
    from catalogos.models import LaserMaterialPlaca

    texto = (renglon.material or "").strip().upper()
    if not texto and renglon.espesor_mm <= 0:
        return None

    palabras = {p for p in re.split(r"[^\wÁÉÍÓÚÑ]+", texto) if len(p) >= 2}
    mejor = None
    mejor_punto = 0
    for placa in LaserMaterialPlaca.objects.filter(activo=True):
        punto = 0
        if renglon.espesor_mm > 0:
            if abs(float(placa.espesor_mm or 0.0) - renglon.espesor_mm) <= 0.01:
                punto += 10
            else:
                # Espesor distinto: no es esta placa, por mucho que el nombre
                # coincida.
                continue
        nombre = (placa.nombre or "").strip().upper()
        if nombre and nombre in palabras:
            punto += 5
        categoria = (placa.categoria_material or "").strip().upper()
        if categoria and categoria in palabras:
            punto += 2
        tipo = (placa.tipo_material or "").strip().upper()
        if tipo and tipo in texto:
            punto += 1
        if punto > mejor_punto:
            mejor_punto = punto
            mejor = placa

    # Sólo el espesor no basta: hay muchas placas de 4.76 mm.
    return mejor if mejor_punto >= 12 else None


def de_pdf(datos: bytes) -> Cotizacion:
    texto = texto_de_pdf(datos)
    if not texto.strip():
        cot = Cotizacion()
        cot.avisos.append(
            "El PDF no trae texto: puede ser un escaneo o una imagen. "
            "Baja la cotización otra vez desde la página, o captúrala a mano."
        )
        return cot
    return leer(texto)
