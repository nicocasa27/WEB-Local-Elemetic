"""Calendario laboral del taller.

El horario estaba escrito directamente en dos sitios de produccion/views.py:
en el cálculo de duración entre estados y en el de disponibilidad de máquina.
Dos copias del mismo dato que había que acordarse de cambiar a la vez.

Es lunes a viernes, de 7:30 a 13:00 y de 13:30 a 17:00: cinco horas y media
por la mañana y tres y media por la tarde, o sea **nueve horas al día y
cuarenta y cinco a la semana**. Ese es el tiempo disponible por máquina con
el que el tablero calcula la disponibilidad.

No contempla sábados, ni segundo turno, ni horas extra, ni los días festivos
de México, así que toda hora trabajada fuera de esa franja es invisible para
los informes: una pieza soldada un sábado no suma tiempo, y una máquina
parada en festivo cuenta como disponible.

Se recoge aquí tal cual está, sin cambiar el comportamiento, pero con la
estructura preparada para que los turnos y los festivos pasen a ser datos.
Hace falta antes de poder calcular disponibilidad de verdad y antes de
cualquier costeo de mano de obra.
"""

from datetime import date, datetime, time, timedelta

from django.utils import timezone

#: Tramos de trabajo de un día laborable, como (inicio, fin).
TRAMOS = [
    (time(7, 30), time(13, 0)),
    (time(13, 30), time(17, 0)),
]

#: Días de la semana laborables. 0 es lunes, 6 domingo.
DIAS_LABORABLES = {0, 1, 2, 3, 4}

#: Días festivos. Vacío por ahora: hoy el sistema no los contempla y añadirlos
#: cambiaría los informes históricos. Cuando se rellene, conviene hacerlo con
#: una fecha de corte para no reescribir el pasado.
FESTIVOS: set[date] = set()

SEGUNDOS_POR_DIA_LABORAL = sum(
    (datetime.combine(date.min, fin) - datetime.combine(date.min, inicio)).seconds
    for inicio, fin in TRAMOS
)

HORAS_POR_DIA_LABORAL = SEGUNDOS_POR_DIA_LABORAL / 3600
HORAS_POR_SEMANA_LABORAL = HORAS_POR_DIA_LABORAL * len(DIAS_LABORABLES)


def es_laborable(dia):
    """¿Se trabaja ese día?"""
    return dia.weekday() in DIAS_LABORABLES and dia not in FESTIVOS


def tramos_del_dia(dia, zona=None):
    """Tramos de trabajo de un día concreto, ya con zona horaria.

    Devuelve una lista vacía si el día no es laborable.
    """
    if not es_laborable(dia):
        return []
    zona = zona or timezone.get_default_timezone()
    salida = []
    for inicio, fin in TRAMOS:
        salida.append(
            (
                timezone.make_aware(datetime.combine(dia, inicio), zona),
                timezone.make_aware(datetime.combine(dia, fin), zona),
            )
        )
    return salida


def segundos_laborales(desde, hasta, zona=None):
    """Segundos de jornada entre dos instantes.

    Es lo que permite decir que una pieza tardó tres horas en soldadura en vez
    de diecinueve, cuando entre medias hubo una noche.

    Recorre día a día, igual que la versión original, pero cortando pronto: sin
    ese corte, una pieza parada dos meses obligaba a recorrer sesenta días
    creando objetos con zona horaria en cada vuelta, y eso se hacía una vez por
    fila del informe.
    """
    if not desde or not hasta or hasta <= desde:
        return 0

    zona = zona or timezone.get_default_timezone()
    inicio = timezone.localtime(desde, zona)
    fin = timezone.localtime(hasta, zona)

    total = 0
    dia = inicio.date()
    ultimo = fin.date()
    while dia <= ultimo:
        for tramo_inicio, tramo_fin in tramos_del_dia(dia, zona):
            solape_inicio = max(inicio, tramo_inicio)
            solape_fin = min(fin, tramo_fin)
            if solape_fin > solape_inicio:
                total += int((solape_fin - solape_inicio).total_seconds())
        dia += timedelta(days=1)
    return total


def horas_laborales(desde, hasta, zona=None):
    """Lo mismo que `segundos_laborales`, en horas."""
    return segundos_laborales(desde, hasta, zona) / 3600


def solape_laboral(desde, hasta, zona=None):
    """Segundos de jornada que cubre un intervalo.

    Se usa para el tiempo muerto: un paro que empieza a las 16:50 y termina a
    las 8:00 del día siguiente son cuarenta minutos de parada, no quince
    horas.
    """
    return segundos_laborales(desde, hasta, zona)
