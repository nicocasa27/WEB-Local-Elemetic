"""El inventario del día uno: subir lo que hay hoy en el estante.

El importador de OPUS da de alta el **catálogo** —qué materiales existen— pero
los deja todos en cero, a propósito: un presupuesto dice lo que se va a
necesitar, no lo que hay. Para arrancar hace falta lo otro: el conteo físico.

Esto lo sube de un archivo plano. Es la única forma realista de empezar; a mano
son catorce campos por renglón y varios cientos de renglones, y un almacén
capturado a medias es peor que ninguno porque las reservas empiezan a fallar
sin que se sepa por qué.

**Cada renglón entra como un lote.** No se acepta «hay 300 kg de placa» a
secas: se pide el lote y su colada, aunque sea «INICIAL-2026». Sin eso, el día
que un cliente reclame no habrá forma de decir de qué colada salió su pieza, y
la trazabilidad —que es la razón de tener lotes— empieza rota desde el primer
día.

**Nunca importa solo.** Se sube, se ve renglón por renglón lo que va a pasar y
sólo entonces se confirma. Y se puede volver a subir el mismo archivo sin miedo:
cada renglón lleva clave de idempotencia, así que reintentar no duplica.
"""

import csv
import io
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone

from core import roles
from core.servicios import inventario as servicio
from inventario.models import Almacen, LoteMaterial, Material, Proveedor

logger = logging.getLogger(__name__)

BASE = "mes"
CERO = Decimal("0")

#: Las columnas que se esperan. El nombre se compara sin acentos ni mayúsculas,
#: porque el archivo casi siempre sale de un Excel escrito a mano.
COLUMNAS = {
    "clave": "codigo",
    "codigo": "codigo",
    "material": "codigo",
    "cantidad": "cantidad",
    "existencia": "cantidad",
    "lote": "lote",
    "colada": "colada",
    "costo": "costo",
    "costounitario": "costo",
    "almacen": "almacen",
    "proveedor": "proveedor",
    "fecha": "fecha",
}

solo_almacen = user_passes_test(roles.puede_entregar_material, login_url="login")


def _normalizar(texto):
    """Sin acentos, sin espacios, en minúsculas. Para comparar encabezados."""
    import unicodedata

    limpio = unicodedata.normalize("NFD", (texto or "").strip().lower())
    return "".join(c for c in limpio if c.isalnum())


def _cantidad(texto):
    texto = (texto or "").strip().replace(",", "").replace("$", "")
    if not texto:
        return None
    try:
        return Decimal(texto)
    except InvalidOperation:
        return None


def _fecha(texto):
    texto = (texto or "").strip()
    if not texto:
        return timezone.localdate()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    return None


def leer(contenido):
    """Convierte el archivo en renglones revisados, sin tocar nada.

    Devuelve `(renglones, problema)`. Cada renglón lleva su aviso si algo no
    cuadra: se enseñan todos juntos para poder corregir el archivo de una vez,
    en lugar de descubrir el siguiente error después de arreglar el primero.
    """
    lector = csv.reader(io.StringIO(contenido))
    filas = [f for f in lector if any((c or "").strip() for c in f)]
    if not filas:
        return [], "El archivo está vacío."

    encabezado = [_normalizar(c) for c in filas[0]]
    mapa = {}
    for posicion, nombre in enumerate(encabezado):
        if nombre in COLUMNAS:
            mapa.setdefault(COLUMNAS[nombre], posicion)

    if "codigo" not in mapa or "cantidad" not in mapa:
        return [], (
            "No se encontraron las columnas «Clave» y «Cantidad». "
            "El primer renglón del archivo tiene que ser el encabezado."
        )

    materiales = {
        m.codigo.upper(): m
        for m in Material.objects.using(BASE).filter(activo=True)
    }
    ya_hay = set(
        LoteMaterial.objects.using(BASE).values_list("material__codigo", "codigo")
    )

    renglones = []
    for numero, fila in enumerate(filas[1:], start=2):
        def celda(clave):
            posicion = mapa.get(clave)
            if posicion is None or posicion >= len(fila):
                return ""
            return (fila[posicion] or "").strip()

        codigo = celda("codigo").upper()
        cantidad = _cantidad(celda("cantidad"))
        fecha = _fecha(celda("fecha"))
        material = materiales.get(codigo)

        # El lote por defecto lleva el año: «INICIAL-2026» se distingue de una
        # segunda carga hecha más tarde, y sigue siendo legible.
        lote = celda("lote") or f"INICIAL-{timezone.localdate():%Y}"

        avisos = []
        if not codigo:
            avisos.append("Falta la clave del material.")
        elif material is None:
            avisos.append(
                "Esa clave no está en el catálogo. Impórtala primero desde OPUS "
                "o dala de alta a mano."
            )
        if cantidad is None:
            avisos.append("La cantidad no es un número.")
        elif cantidad <= CERO:
            avisos.append("La cantidad tiene que ser mayor que cero.")
        if fecha is None:
            avisos.append("La fecha no se entiende. Usa AAAA-MM-DD.")
        if material is not None and (material.codigo, lote) in ya_hay:
            avisos.append(
                f"El lote «{lote}» ya existe para este material. "
                "Se dejará como está."
            )

        renglones.append({
            "numero": numero,
            "codigo": codigo,
            "material": material,
            "cantidad": cantidad,
            "lote": lote,
            "colada": celda("colada"),
            "costo": _cantidad(celda("costo")) or CERO,
            "almacen": celda("almacen"),
            "proveedor": celda("proveedor"),
            "fecha": fecha,
            "avisos": avisos,
            "listo": not avisos,
        })

    return renglones, ""


@transaction.atomic(using=BASE)
def aplicar(renglones, *, actor):
    """Da de alta los lotes y registra su entrada.

    Sólo los renglones sin avisos. Los demás se quedan fuera y se informan: no
    se importa «lo que se pueda» en silencio, porque un almacén con la mitad de
    los renglones se ve igual de completo que uno entero.
    """
    almacenes = {
        a.nombre.upper(): a for a in Almacen.objects.using(BASE).all()
    }
    proveedores = {
        p.nombre.upper(): p for p in Proveedor.objects.using(BASE).all()
    }

    hechos = []
    for renglon in renglones:
        if not renglon["listo"]:
            continue

        almacen = almacenes.get((renglon["almacen"] or "").upper())
        lote, _ = LoteMaterial.objects.using(BASE).get_or_create(
            material=renglon["material"],
            codigo=renglon["lote"],
            defaults={
                "colada": renglon["colada"],
                "costo_unitario": renglon["costo"],
                "proveedor": proveedores.get((renglon["proveedor"] or "").upper()),
                "recibido_en": renglon["fecha"],
                "observaciones": "Carga inicial de inventario",
            },
        )
        movimiento = servicio.registrar_entrada(
            lote=lote,
            cantidad=renglon["cantidad"],
            actor=actor,
            almacen=almacen,
            comentario="Carga inicial de inventario",
            # Volver a subir el mismo archivo no vuelve a sumar: el segundo
            # intento devuelve el mismo movimiento.
            clave_idempotencia=(
                f"carga-inicial-{renglon['material'].codigo}-{renglon['lote']}"
            ),
        )
        hechos.append((renglon, movimiento))

    logger.info("carga inicial: %s renglones aplicados", len(hechos))
    return hechos


@solo_almacen
def importar(request):
    contexto = {"paso": "subir"}

    if request.method != "POST":
        return render(request, "inventario/carga_inicial.html", contexto)

    archivo = request.FILES.get("archivo")
    crudo = request.POST.get("crudo") or ""

    if archivo is not None:
        datos = archivo.read()
        try:
            crudo = datos.decode("utf-8-sig")
        except UnicodeDecodeError:
            crudo = datos.decode("cp1252", errors="replace")
    elif not crudo:
        messages.error(request, "No se recibió ningún archivo.")
        return render(request, "inventario/carga_inicial.html", contexto)

    renglones, problema = leer(crudo)
    if problema:
        messages.error(request, problema)
        return render(request, "inventario/carga_inicial.html", contexto)

    listos = [r for r in renglones if r["listo"]]
    con_avisos = [r for r in renglones if not r["listo"]]

    if request.POST.get("confirmar") == "sí":
        if not listos:
            messages.error(
                request, "Ningún renglón está listo. No se importó nada."
            )
        else:
            hechos = aplicar(renglones, actor=request.user)
            messages.success(
                request,
                f"{len(hechos)} renglones cargados al almacén."
                + (f" {len(con_avisos)} se quedaron fuera." if con_avisos else ""),
            )
            return redirect("inventario:existencias")

    contexto.update({
        "paso": "revisar",
        "renglones": renglones,
        "listos": listos,
        "con_avisos": con_avisos,
        "crudo": crudo,
    })
    return render(request, "inventario/carga_inicial.html", contexto)
