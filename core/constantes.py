"""Constantes de negocio que estaban repartidas por el código.

Ninguna cambia de valor: es una mudanza, no un ajuste. Lo que se gana es que
cada una tenga un solo sitio donde mirarse y donde cambiarse.
"""

# ------------------------------------------------------------------- cierre
#
# Al llegar la última pieza a terminada, la orden queda en un estado
# intermedio durante esta ventana, para poder corregir un error de dedo. Si
# nadie la revierte, el cierre pasa a definitivo y la orden se bloquea.
#
# Los diez minutos son de `catalogos/views.py`. Conviene saber que el
# temporizador no corre solo: hasta ahora el cierre sólo se consolidaba cuando
# alguien abría la pantalla de control, así que un viernes por la tarde las
# órdenes se quedaban en el limbo hasta el lunes.
CIERRE_VENTANA_MINUTOS = 10

#: Tope de filas que consolida cada pasada. Estaba puesto para no penalizar la
#: carga de la pantalla; con el trabajo programado deja de tener sentido como
#: límite duro y pasa a ser el tamaño del lote.
CIERRE_LOTE = 200


# -------------------------------------------------------------------- decote
#
# Días que una orden enviada permanece disponible antes de poder purgarse.
DECOTE_DIAS = 5


# ------------------------------------------------------------------ almacén
#
# Movimientos que afectan al stock disponible. `enviar` sale del apartado y
# `revertir_a_apartado` vuelve a él, así que ninguno de los dos lo toca.
TIPOS_MOVIMIENTO_DISPONIBLE = ("stock_in", "apartar", "revertir_a_stock", "ajuste")

#: Tipo histórico que no distinguía si la reversión iba al almacén o al
#: apartado. No debe escribirse: existe para poder leer los registros viejos.
TIPO_MOVIMIENTO_AMBIGUO = "revertir"


# -------------------------------------------------------------------- roles
#
# Grupos de Django que usa el control de acceso. Sólo `herreria`,
# `herreria_supervision`, `corte_laser`, `corte_laser_supervision` y
# `pedidos_ventas` se crean por migración; el resto hay que darlos de alta a
# mano en cada entorno, que es una de las cosas a arreglar.
GRUPO_ADMIN = "admin_general"
GRUPO_INGENIERIA = "ingenieria_civil"
GRUPO_CORTE = "corte"
GRUPO_SOLDADURA = "soldadura"
GRUPO_ROBOTICA = "robotica"
GRUPO_HERRERIA = "herreria"
GRUPO_HERRERIA_SUPERVISION = "herreria_supervision"
GRUPO_CORTE_LASER = "corte_laser"
GRUPO_CORTE_LASER_SUPERVISION = "corte_laser_supervision"
GRUPO_PEDIDOS = "pedidos_ventas"

GRUPOS_ADMINISTRACION = (GRUPO_ADMIN, GRUPO_INGENIERIA)


# ------------------------------------------------------- líneas de negocio
#
# Los cuatro motores de producción que hoy son el mismo código copiado cuatro
# veces. Se nombran aquí para poder referirse a ellos antes de que exista la
# tabla que los represente.
LINEA_VIGAS = "vigas"
LINEA_HERRERIA = "herreria"
LINEA_CORTA = "corta"
LINEA_ROBOTICA = "robotica"

LINEAS = (LINEA_VIGAS, LINEA_HERRERIA, LINEA_CORTA, LINEA_ROBOTICA)

#: A partir de cuántas piezas una orden deja de llevarse por etapas y pasa a
#: llevarse por contadores.
PIEZAS_MINIMAS_ORDEN_GRANDE = 2
