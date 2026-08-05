"""«Control de producción»: qué está haciendo el taller ahora mismo.

Una sola lista con las cuatro líneas. La pregunta que contesta —«¿qué se está
produciendo?»— no tenía pantalla: había que abrir cuatro y sumar de cabeza.

Es de **lectura**. Desde cada renglón se va a la pantalla de su línea, que es
donde se trabaja. Poner aquí también los botones de avanzar significaría
mantener cuatro comportamientos distintos en una tabla que mezcla cuatro
tipos de orden, y esa es exactamente la clase de pantalla que acaba
haciéndolo todo a medias.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.servicios import panorama as servicio


@login_required
def control(request):
    busqueda = (request.GET.get("q") or "").strip()
    linea = (request.GET.get("linea") or "").strip()
    if linea not in servicio.LINEAS:
        linea = ""

    renglones = servicio.lo_que_se_esta_haciendo(busqueda=busqueda, linea=linea)

    # El conteo por línea se calcula **sin** el filtro de línea puesto: si se
    # calculara sobre lo filtrado, al entrar en «Herrería» las demás pestañas
    # dirían cero y parecería que no hay nada más en el taller.
    todo = (
        renglones
        if not linea
        else servicio.lo_que_se_esta_haciendo(busqueda=busqueda)
    )

    return render(
        request,
        "produccion/panorama.html",
        {
            "renglones": renglones,
            "resumen": servicio.resumen(renglones),
            "conteo_por_linea": servicio.resumen(todo)["por_linea"],
            "total_sin_filtrar": len(todo),
            "lineas": servicio.LINEAS,
            "linea": linea,
            "busqueda": busqueda,
        },
    )
