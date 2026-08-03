"""Tests de la consolidación de cierres vencidos."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from catalogos.models import HerrEstadoCambio, HerrOrdenProduccion
from core import estados
from core.servicios import cierres
from tests import escenarios

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def orden_en_cierre_pendiente(vencida_hace_minutos=None, codigo="H-70001"):
    """Orden esperando a que se consolide su cierre.

    Con `vencida_hace_minutos` la ventana ya pasó; sin él, sigue abierta.
    """
    pieza = escenarios.crear_pieza(nombre=f"pieza {codigo}")
    orden = escenarios.crear_orden_de_herreria(pieza, cantidad=4, codigo=codigo)
    ahora = timezone.now()
    if vencida_hace_minutos is None:
        hasta = ahora + timedelta(minutes=5)
    else:
        hasta = ahora - timedelta(minutes=vencida_hace_minutos)
    HerrOrdenProduccion.objects.filter(pk=orden.pk).update(
        estado_etapa=estados.CIERRE_PENDIENTE,
        cierre_pendiente_en=ahora,
        cierre_pendiente_hasta=hasta,
        cantidad_terminada=4,
    )
    orden.refresh_from_db()
    return orden


class TestConsolidacion:
    def test_cierra_las_ordenes_vencidas(self):
        orden = orden_en_cierre_pendiente(vencida_hace_minutos=1)

        assert cierres.consolidar_linea("herreria") == 1

        orden.refresh_from_db()
        assert orden.estado_etapa == estados.TERMINADO
        assert orden.cierre_bloqueado_en is not None
        assert orden.cierre_pendiente_hasta is None

    def test_respeta_las_que_siguen_en_ventana(self):
        """Mientras quede plazo, la orden se puede revertir y no se toca."""
        orden = orden_en_cierre_pendiente(vencida_hace_minutos=None)

        assert cierres.consolidar_linea("herreria") == 0

        orden.refresh_from_db()
        assert orden.estado_etapa == estados.CIERRE_PENDIENTE

    def test_deja_constancia_en_la_bitacora(self):
        """Quién cerró la orden tiene que quedar registrado, aunque sea el sistema."""
        orden = orden_en_cierre_pendiente(vencida_hace_minutos=30)
        cierres.consolidar_linea("herreria")

        registro = HerrEstadoCambio.objects.filter(orden=orden).order_by("-id").first()
        assert registro is not None
        assert registro.estado_nuevo == estados.TERMINADO
        assert registro.actor_username == "system"
        assert registro.comentario == "auto_bloqueo"

    def test_es_idempotente(self):
        """Al correr cada minuto, la segunda pasada no debe hacer nada."""
        orden_en_cierre_pendiente(vencida_hace_minutos=1)

        assert cierres.consolidar_linea("herreria") == 1
        assert cierres.consolidar_linea("herreria") == 0

    def test_procesa_mas_alla_del_tamano_de_lote(self):
        """El tope de doscientas filas por pasada dejaba trabajo sin hacer.

        Con acumulación, la versión anterior nunca alcanzaba: cada llamada
        cerraba doscientas y se detenía. Ahora sigue por lotes hasta agotar.
        """
        from core.constantes import CIERRE_LOTE

        cuantas = CIERRE_LOTE + 5
        for i in range(cuantas):
            orden_en_cierre_pendiente(vencida_hace_minutos=1, codigo=f"H-711{i:03d}")

        assert cierres.consolidar_linea("herreria") == cuantas
        assert not HerrOrdenProduccion.objects.filter(
            estado_etapa=estados.CIERRE_PENDIENTE
        ).exists()

    def test_consolidar_todas_recorre_las_dos_lineas(self):
        orden_en_cierre_pendiente(vencida_hace_minutos=1)
        resultado = cierres.consolidar_todas()
        assert resultado == {"herreria": 1, "corta": 0}


class TestComando:
    def test_el_comando_cierra_sin_que_nadie_abra_la_pantalla(self):
        """Es el punto de todo el cambio.

        Antes, un cierre que vencía un viernes a las 17:05 seguía pendiente el
        lunes, porque sólo se consolidaba al cargar la pantalla de control.
        """
        orden = orden_en_cierre_pendiente(vencida_hace_minutos=90)
        salida = StringIO()

        call_command("consolidar_cierres", stdout=salida)

        orden.refresh_from_db()
        assert orden.estado_etapa == estados.TERMINADO
        assert "1 orden(es) cerradas en firme" in salida.getvalue()

    def test_simular_no_modifica_nada(self):
        orden = orden_en_cierre_pendiente(vencida_hace_minutos=90)
        salida = StringIO()

        call_command("consolidar_cierres", "--simular", stdout=salida)

        orden.refresh_from_db()
        assert orden.estado_etapa == estados.CIERRE_PENDIENTE
        assert orden.codigo in salida.getvalue()

    def test_se_puede_limitar_a_una_linea(self):
        orden = orden_en_cierre_pendiente(vencida_hace_minutos=5)
        call_command("consolidar_cierres", "--linea", "corta", stdout=StringIO())

        orden.refresh_from_db()
        assert orden.estado_etapa == estados.CIERRE_PENDIENTE, "no debía tocar herrería"

    def test_sin_trabajo_pendiente_no_hace_ruido(self):
        """Corriendo cada minuto, lo contrario llenaría el registro."""
        salida = StringIO()
        call_command("consolidar_cierres", stdout=salida)
        assert salida.getvalue().strip() == "Sin cierres vencidos."
