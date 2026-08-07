"""Importar una explosión de insumos de OPUS al catálogo de materiales.

El lector (`core/opus.py`) ya deja el archivo entendido y avisado. Esto es el
paso siguiente: cruzar las claves con el catálogo y dar de alta lo que falte.

**Nunca importa solo.** Se sube el archivo, se ve lo que va a pasar —qué claves
ya existen, cuáles son nuevas, qué avisos hay— y sólo entonces se confirma. Es
la misma salvaguarda que en el resto del sistema: un archivo mal leído mete
material equivocado en el catálogo, y de ahí sale material comprado de más o de
menos.

Las tres decisiones que el archivo real obligó a tomar, y que aquí se aplican:

- **Los renglones en «(%)m» no son material.** Son indirectos que OPUS calcula
  como porcentaje del total —fletes, consumibles—. Se dan de alta marcados como
  no inventariables, para que entren en el costo del proyecto pero nadie tenga
  que decir cuántos fletes hay en el estante.
- **Una clave repetida se acumula.** «CONSUMIBLES» sale dos veces con costos
  distintos: se suman las cantidades y el costo se pondera. Quedarse con la
  última sería perder datos en silencio.
- **Las fracciones de pieza se redondean hacia arriba al reservar.** OPUS
  reparte el desgaste de un consumible entre proyectos y pide 2,945385
  boquillas; del almacén no sale una fracción. Aquí sólo se avisa: el redondeo
  ocurre en la reserva, no en el catálogo, porque el dato del presupuesto es el
  que es.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.shortcuts import redirect, render

from core import opus, roles
from inventario.models import Material
from core.bases import BASE  # noqa: F401

CERO = Decimal("0")

#: Cómo se traduce la unidad de OPUS a la del catálogo. Lo que no esté aquí
#: entra como pieza, que es el valor por defecto del modelo.
UNIDADES = {
    "pza": "pza", "pieza": "pza", "jgo": "pza",
    "kg": "kg", "ton": "kg",
    "m": "m", "ml": "m",
    "m2": "m2", "m²": "m2",
    "m3": "m3", "m³": "m3",
    "lt": "lt", "l": "lt", "litro": "lt",
    "hr": "hr", "h": "hr", "jor": "hr",
}

solo_almacen = user_passes_test(roles.puede_entregar_material, login_url="login")


def _unidad(texto):
    return UNIDADES.get((texto or "").strip().lower(), "pza")


def agrupar(partidas):
    """Junta las claves repetidas sumando cantidad y ponderando el costo.

    «CONSUMIBLES» aparece dos veces en el archivo real con costos distintos. Un
    importador que dé de alta por clave o revienta contra el índice único o se
    queda con el último renglón: las dos cosas pierden datos sin decirlo.

    El costo se pondera por cantidad porque es lo que respeta el importe total:
    quedarse con el promedio simple descuadraría el presupuesto.
    """
    juntas = {}
    for partida in partidas:
        entrada = juntas.setdefault(partida.clave, {
            "clave": partida.clave,
            "descripcion": partida.descripcion,
            "unidad": partida.unidad,
            "cantidad": CERO,
            "importe": CERO,
            "renglones": 0,
        })
        entrada["cantidad"] += partida.cantidad
        entrada["importe"] += partida.importe
        entrada["renglones"] += 1
        if len(partida.descripcion) > len(entrada["descripcion"]):
            entrada["descripcion"] = partida.descripcion

    for entrada in juntas.values():
        entrada["costo"] = (
            (entrada["importe"] / entrada["cantidad"]).quantize(Decimal("0.0001"))
            if entrada["cantidad"] else CERO
        )
        entrada["inventariable"] = (
            entrada["unidad"].lower() not in opus.UNIDADES_NO_INVENTARIABLES
        )
    return sorted(juntas.values(), key=lambda e: e["clave"])


def cotejar(agrupadas):
    """Qué claves ya están en el catálogo y cuáles habría que crear."""
    claves = [e["clave"] for e in agrupadas]
    existentes = {
        m.codigo: m
        for m in Material.objects.using(BASE).filter(codigo__in=claves)
    }
    for entrada in agrupadas:
        entrada["material"] = existentes.get(entrada["clave"])
        entrada["nueva"] = entrada["material"] is None
    return agrupadas


@transaction.atomic(using=BASE)
def aplicar(agrupadas, actor=None):
    """Da de alta lo que falta. **No toca lo que ya existe.**

    Un material del catálogo puede tener mínimo, proveedor y existencia
    capturados a mano; pisarlos con lo que trae un presupuesto sería perder
    trabajo del taller a cambio de nada.
    """
    creados = []
    for entrada in agrupadas:
        if not entrada["nueva"]:
            continue
        material = Material.objects.using(BASE).create(
            codigo=entrada["clave"],
            nombre=entrada["descripcion"] or entrada["clave"],
            nombre_normalizado=(entrada["descripcion"] or entrada["clave"]).upper(),
            unidad=_unidad(entrada["unidad"]),
            inventariable=entrada["inventariable"],
            # Sin mínimo: lo pone el taller cuando sepa cada cuánto se repone.
            # Inventarlo aquí llenaría la pantalla de compras de avisos falsos.
            stock_minimo=CERO,
            activo=True,
        )
        creados.append(material)
    return creados


# ------------------------------------------------------------------ vistas


@login_required
@solo_almacen
def importar(request):
    """Sube el archivo, enseña lo que pasaría, y sólo confirma si se pide."""
    contexto = {"paso": "subir"}

    if request.method != "POST":
        return render(request, "inventario/opus_importar.html", contexto)

    archivo = request.FILES.get("archivo")
    crudo = request.POST.get("crudo") or ""

    if archivo is not None:
        crudo = archivo.read()
        try:
            crudo = crudo.decode("utf-8")
        except UnicodeDecodeError:
            crudo = crudo.decode("cp1252", errors="replace")
    elif not crudo:
        messages.error(request, "No se recibió ningún archivo.")
        return render(request, "inventario/opus_importar.html", contexto)

    lectura = opus.leer(crudo)

    if not lectura.partidas:
        messages.error(
            request,
            "No parece una explosión de insumos de OPUS: no se encontró el "
            "renglón de encabezado con «Clave» y «Cantidad».",
        )
        return render(request, "inventario/opus_importar.html", contexto)

    agrupadas = cotejar(agrupar(lectura.partidas))

    if request.POST.get("confirmar") == "sí":
        if lectura.cuadra is False:
            # No se importa un archivo que no cuadra: casi siempre significa
            # que algún renglón se partió mal, y un renglón mal partido es
            # material comprado de más o de menos.
            messages.error(
                request,
                "El archivo no cuadra con su propio total. No se importó nada.",
            )
        else:
            creados = aplicar(agrupadas, actor=request.user)
            messages.success(
                request,
                f"{len(creados)} material{'es' if len(creados) != 1 else ''} "
                f"dado{'s' if len(creados) != 1 else ''} de alta.",
            )
            return redirect("inventario:existencias")

    contexto.update({
        "paso": "revisar",
        "lectura": lectura,
        "agrupadas": agrupadas,
        "nuevas": [e for e in agrupadas if e["nueva"]],
        "conocidas": [e for e in agrupadas if not e["nueva"]],
        "crudo": crudo,
    })
    return render(request, "inventario/opus_importar.html", contexto)
