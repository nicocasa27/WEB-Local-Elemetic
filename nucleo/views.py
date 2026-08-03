"""La pantalla de puesta en marcha.

Este software estuvo abandonado. Quien lo hizo no está, y lo que se añada
ahora tiene que poder configurarlo el taller sin llamar a nadie. Los módulos
nuevos —núcleo, inventario, costeo— son configurables por datos precisamente
por eso, pero eso no sirve de nada si la única forma de llegar a esos datos es
un comando de consola o adivinar una dirección del administrador.

Esta pantalla es la puerta. No captura nada: **dice qué hay, qué falta, qué
pasa si falta y dónde se arregla.** Cada renglón lleva a la pantalla del
administrador donde se captura, que es donde ya está toda la edición.

La distinción entre «falta» y «opcional» es deliberada y es la información más
útil de la página: sin tarifas, el costeo da cero y no sirve; sin proveedores,
funciona igual y sólo se pierde detalle. Una lista de pendientes que no
distingue lo que bloquea de lo que no acaba ignorándose entera.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse

from core import banderas

BASE = "mes"

LISTO = "listo"
FALTA = "falta"
OPCIONAL = "opcional"


def _admin(modelo):
    """Dirección de la lista del administrador para un modelo."""
    return reverse(f"admin:{modelo._meta.app_label}_{modelo._meta.model_name}_changelist")


def _renglon(titulo, cantidad, estado, explicacion, modelo=None, unidad="", accion="Configurar"):
    return {
        "titulo": titulo,
        "cantidad": cantidad,
        "unidad": unidad,
        "estado": estado,
        "explicacion": explicacion,
        "enlace": _admin(modelo) if modelo else "",
        "accion": accion,
    }


def _seccion_nucleo():
    from nucleo.models import Etapa, LineaNegocio, MotivoEvento, TransicionPermitida

    lineas = LineaNegocio.objects.using(BASE).count()
    etapas = Etapa.objects.using(BASE).count()
    transiciones = TransicionPermitida.objects.using(BASE).count()
    motivos = MotivoEvento.objects.using(BASE).filter(activo=True).count()

    return {
        "titulo": "Proceso de producción",
        "descripcion": (
            "Las etapas por las que pasa una orden y qué movimientos están "
            "permitidos. Antes esto estaba escrito dentro del código: añadir un "
            "granallado o exigir un motivo para retroceder era trabajo de "
            "programación. Ahora es editar una fila."
        ),
        "renglones": [
            _renglon(
                "Líneas de producción", lineas,
                LISTO if lineas else FALTA,
                "Vigas, herrería, corte láser y robótica. Aquí se ajusta si una línea "
                "usa almacén, si emite acuse y cuántos minutos dura la ventana para "
                "deshacer un cierre.",
                LineaNegocio, "líneas",
            ),
            _renglon(
                "Etapas", etapas,
                LISTO if etapas else FALTA,
                "Los pasos de cada línea, en orden. Añadir uno nuevo no requiere tocar "
                "nada más.",
                Etapa, "etapas",
            ),
            _renglon(
                "Movimientos permitidos", transiciones,
                LISTO if transiciones else FALTA,
                "De qué etapa se puede pasar a cuál, cuáles exigen motivo, cuáles exigen "
                "un grupo concreto y cuáles se bloquean si la máquina está parada. Esta "
                "última regla antes sólo existía en el navegador: cualquiera con la "
                "dirección se la saltaba.",
                TransicionPermitida, "reglas",
            ),
            _renglon(
                "Motivos", motivos,
                LISTO if motivos else FALTA,
                "Por qué se para una máquina, por qué se retrocede una etapa, por qué se "
                "ajusta el inventario. Antes eran cuatro catálogos distintos y texto "
                "libre; por eso el tablero medía «retrabajo» de dos formas que no "
                "coincidían.",
                MotivoEvento, "motivos",
            ),
        ],
    }


def _seccion_inventario():
    from inventario.models import (
        Almacen,
        Existencia,
        ListaMateriales,
        LoteMaterial,
        Material,
        Proveedor,
    )

    almacenes = Almacen.objects.using(BASE).filter(activo=True).count()
    materiales = Material.objects.using(BASE).filter(activo=True).count()
    con_existencia = Existencia.objects.using(BASE).filter(cantidad__gt=0).count()
    proveedores = Proveedor.objects.using(BASE).filter(activo=True).count()
    lotes = LoteMaterial.objects.using(BASE).count()
    listas = ListaMateriales.objects.using(BASE).filter(vigente=True).count()

    return {
        "titulo": "Inventario de materia prima",
        "descripcion": (
            "Qué material hay, de qué colada salió y cuánto costó. Es lo que "
            "permite responder a un cliente que reclama, y la mitad del costeo."
        ),
        "renglones": [
            _renglon(
                "Almacenes", almacenes,
                LISTO if almacenes else FALTA,
                "Dónde está el material. Con uno basta para empezar.",
                Almacen, "almacenes",
            ),
            _renglon(
                "Catálogo de material", materiales,
                LISTO if materiales else FALTA,
                "Traído de las placas que ya estaban capturadas en corte láser, con su "
                "peso y su densidad. Aquí se dan de alta las que falten y se pone el "
                "mínimo por debajo del cual hay que comprar.",
                Material, "materiales",
            ),
            _renglon(
                "Conteo inicial", con_existencia,
                LISTO if con_existencia else FALTA,
                "El inventario arranca contando, no suponiendo. Se saca la hoja con "
                "«inventario_fisico --plantilla», se cuenta en el almacén y se carga. "
                "Mientras esto esté en cero, el módulo no dice nada útil.",
                Existencia, "con existencia", accion="Ver existencias",
            ),
            _renglon(
                "Lotes", lotes,
                LISTO if lotes else FALTA,
                "Cada entrada de material con su colada, su certificado y su costo. Sin "
                "lote no hay trazabilidad ni hay costeo: son la misma información.",
                LoteMaterial, "lotes",
            ),
            _renglon(
                "Proveedores", proveedores,
                LISTO if proveedores else OPCIONAL,
                "Sirve para saber a quién comprarle y de quién viene cada colada. El "
                "inventario funciona sin ellos, con menos detalle.",
                Proveedor, "proveedores",
            ),
            _renglon(
                "Listas de materiales", listas,
                LISTO if listas else OPCIONAL,
                "Qué material lleva cada pieza. Por ahora sólo propone el consumo: una "
                "persona confirma. Se automatizará cuando lo propuesto y lo realmente "
                "gastado coincidan.",
                ListaMateriales, "listas",
            ),
        ],
    }


def _seccion_costeo():
    from django.utils import timezone

    from core.servicios import costeo as servicio
    from costeo.models import CentroCosto, TarifaManoObra, TiempoEstandar

    centros = CentroCosto.objects.using(BASE).filter(activo=True).count()
    sin_tarifa = servicio.sin_tarifa()
    con_tarifa = centros - len(sin_tarifa)
    tarifas_persona = TarifaManoObra.objects.using(BASE).count()
    estandares = (
        TiempoEstandar.objects.using(BASE)
        .filter(vigente_desde__lte=timezone.localdate())
        .count()
    )

    return {
        "titulo": "Costeo",
        "descripcion": (
            "Cuánto cuesta de verdad cada orden. No hay que apuntar horas: se "
            "deducen del historial de producción. Lo único que hay que capturar "
            "es cuánto cuesta una hora."
        ),
        "renglones": [
            _renglon(
                "Centros de costo", centros,
                LISTO if centros else FALTA,
                "Uno por línea. Aquí también se ajusta el tope de horas que se cobran "
                "por cada paso de una orden por una etapa.",
                CentroCosto, "centros",
            ),
            _renglon(
                "Centros con tarifa", con_tarifa,
                # Sin ningún centro tampoco hay tarifas: da igual que la lista
                # de centros sin tarifa esté vacía porque no hay centros que
                # mirar. Contarlo como listo sería el peor error de esta
                # pantalla, porque diría que está resuelto lo único que
                # bloquea el costeo entero.
                LISTO if centros and not sin_tarifa else FALTA,
                "Costo por hora de máquina, de mano de obra y de indirectos. Sin esto "
                "todas las órdenes salen en cero, y un costo en cero no es un costo "
                "barato: es un costo que no se calculó. Las tarifas no se editan: para "
                "corregir una se captura otra con fecha nueva.",
                CentroCosto, f"de {centros}",
            ),
            _renglon(
                "Tarifas por persona o rol", tarifas_persona,
                LISTO if tarifas_persona else OPCIONAL,
                "Afina el costo de mano de obra. Sin ellas se usa la tarifa del centro.",
                TarifaManoObra, "tarifas",
            ),
            _renglon(
                "Tiempos estándar", estandares,
                LISTO if estandares else FALTA,
                "Cuánto debería tardar una pieza en cada etapa. Es lo que enciende el "
                "informe de varianza, que dice en qué etapa se pierde dinero en vez de sólo "
                "cuánto. También es lo que permite quitar el tope de horas.",
                TiempoEstandar, "tiempos",
            ),
        ],
    }


def _seccion_migracion():
    from nucleo.models import DivergenciaReconciliacion, LineaNegocio, OrdenProduccion

    lineas = []
    for linea in LineaNegocio.objects.using(BASE).all():
        modo = banderas.modo(linea.codigo)
        divergencias = (
            DivergenciaReconciliacion.objects.using(BASE)
            .filter(linea=linea, resuelta_en__isnull=True)
            .count()
        )
        lineas.append(
            {
                "linea": linea,
                "modo": modo,
                "ordenes": OrdenProduccion.objects.using(BASE)
                .filter(linea=linea)
                .count(),
                "divergencias": divergencias,
            }
        )
    return lineas


@login_required
def configuracion(request):
    """Qué está configurado, qué falta y dónde se arregla."""
    secciones = [_seccion_nucleo(), _seccion_inventario(), _seccion_costeo()]

    pendientes = sum(
        1
        for seccion in secciones
        for renglon in seccion["renglones"]
        if renglon["estado"] == FALTA
    )

    return render(
        request,
        "nucleo/configuracion.html",
        {
            "secciones": secciones,
            "migracion": _seccion_migracion(),
            "pendientes": pendientes,
            "puede_entrar_al_admin": request.user.is_staff,
        },
    )
