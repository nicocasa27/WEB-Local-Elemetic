"""El motor unificado de producción.

Cada clase de aquí corresponde a un fallo concreto del sistema heredado. No
son tests de cobertura: son la prueba de que el fallo ya no se puede repetir.
"""

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.excepciones import (
    CantidadInvalida,
    ConflictoDeConcurrencia,
    MaquinaNoDisponible,
    MotivoRequerido,
    OrdenBloqueada,
    TransicionInvalida,
)
from core.servicios import produccion
from nucleo.models import (
    Asignacion,
    Etapa,
    EventoMaquina,
    EventoProduccion,
    LineaNegocio,
    MotivoEvento,
    OrdenProduccion,
    TransicionPermitida,
)
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

CONTADOR = EventoProduccion.Contador


@pytest.fixture
def nucleo():
    """La configuración sembrada, igual que en el taller."""
    call_command("sembrar_nucleo", verbosity=0)
    return LineaNegocio.objects.using(BASE).get(codigo="herreria")


@pytest.fixture
def orden(nucleo):
    return produccion.crear_orden(
        linea=nucleo,
        actor="ana",
        codigo="H-TEST-1",
        total_piezas=10,
        cantidad_objetivo=10,
        peso_kg_unitario="12.500",
    )


def etapa(linea, codigo):
    return Etapa.objects.using(BASE).get(linea=linea, codigo=codigo)


class TestAltaYFolios:
    def test_el_folio_sale_de_la_secuencia_y_no_se_repite(self, nucleo):
        """El sistema heredado calculaba el folio como «último id + 1».

        Al purgar una orden quedaba un hueco que la siguiente ocupaba, así que
        acababa habiendo dos acuses de entrega firmados con el mismo número.
        """
        folios = {
            produccion.crear_orden(linea=nucleo, actor="ana", codigo=f"C{i}").folio
            for i in range(5)
        }
        assert len(folios) == 5

    def test_el_alta_deja_su_evento(self, orden):
        evento = EventoProduccion.objects.using(BASE).get(
            orden=orden, tipo=EventoProduccion.Tipo.CREACION
        )
        assert evento.actor_username == "ana"
        assert evento.etapa.codigo == "espera_corte"

    def test_nace_en_la_etapa_inicial_configurada(self, orden):
        assert orden.etapa_actual.codigo == "espera_corte"

    def test_repetir_el_alta_con_la_misma_clave_no_crea_dos(self, nucleo):
        primera = produccion.crear_orden(
            linea=nucleo, actor="ana", codigo="X", clave_idempotencia="alta-1"
        )
        segunda = produccion.crear_orden(
            linea=nucleo, actor="ana", codigo="X", clave_idempotencia="alta-1"
        )
        assert primera.pk == segunda.pk
        assert OrdenProduccion.objects.using(BASE).count() == 1


class TestCambioDeEtapa:
    def test_avanza_a_la_etapa_siguiente(self, orden, nucleo):
        produccion.cambiar_etapa(orden, destino="corte", actor="ana")
        orden.refresh_from_db(using=BASE)
        assert orden.etapa_actual.codigo == "corte"

    def test_una_transicion_que_no_esta_en_la_tabla_se_rechaza(self, orden, nucleo):
        """La máquina de estados vive en datos: si la fila no está, no se puede."""
        TransicionPermitida.objects.using(BASE).filter(
            linea=nucleo, desde=orden.etapa_actual, hasta=etapa(nucleo, "corte")
        ).delete()
        with pytest.raises(TransicionInvalida):
            produccion.cambiar_etapa(orden, destino="corte", actor="ana")

    def test_retroceder_sin_motivo_se_rechaza(self, orden, nucleo):
        produccion.cambiar_etapa(orden, destino="soldadura", actor="ana")
        with pytest.raises(MotivoRequerido):
            produccion.cambiar_etapa(orden, destino="corte", actor="ana")

    def test_retroceder_con_motivo_queda_registrado(self, orden, nucleo):
        produccion.cambiar_etapa(orden, destino="soldadura", actor="ana")
        motivo = produccion.motivo(MotivoEvento.Ambito.RETROCESO, "retrabajo")

        evento = produccion.cambiar_etapa(
            orden, destino="corte", actor="ana", motivo=motivo
        )

        # Hoy el retrabajo se mide de dos formas incompatibles en la misma
        # pantalla: una busca la palabra en un comentario libre y otra una
        # etiqueta. Con una clave foránea la definición es una sola.
        assert evento.motivo.codigo == "retrabajo"

    def test_la_version_vieja_no_pisa_el_trabajo_de_otro(self, orden):
        produccion.cambiar_etapa(orden, destino="corte", actor="ana")
        with pytest.raises(ConflictoDeConcurrencia):
            produccion.cambiar_etapa(orden, destino="armado", actor="beto", version=0)

    def test_la_maquina_parada_bloquea_el_avance(self, orden, nucleo):
        """Esta regla sólo existía en el navegador.

        Bastaba con desactivar el JavaScript, o con conocer la dirección, para
        registrar producción en una máquina que estaba parada.
        """
        from catalogos.models import Maquina

        maquina = Maquina.objects.using(BASE).create(nombre="Láser 1", activo=True)
        Asignacion.objects.using(BASE).create(
            orden=orden, maquina=maquina, vigente=True, asignado_en=timezone.now()
        )
        EventoMaquina.objects.using(BASE).create(
            maquina=maquina, clase=EventoMaquina.Clase.PARO, inicio=timezone.now()
        )
        TransicionPermitida.objects.using(BASE).filter(
            linea=nucleo, desde=orden.etapa_actual, hasta=etapa(nucleo, "corte")
        ).update(bloquea_si_maquina_en_paro=True)

        with pytest.raises(MaquinaNoDisponible):
            produccion.cambiar_etapa(orden, destino="corte", actor="ana")


class TestAvance:
    def test_dos_avances_iguales_suman_los_dos(self, orden):
        """El fallo que duplicaba el stock.

        El sistema heredado recibe el total («terminadas = 5») y calcula la
        diferencia contra lo que había. Dos pestañas abiertas mandan las dos
        «5» y el almacén recibe diez piezas que no existen. Recibiendo la
        diferencia, dos «+5» son diez porque de verdad se hicieron diez.
        """
        produccion.registrar_avance(orden, contador=CONTADOR.PRODUCIDA, delta=5, actor="ana")
        produccion.registrar_avance(orden, contador=CONTADOR.PRODUCIDA, delta=5, actor="beto")

        orden.refresh_from_db(using=BASE)
        assert orden.cantidad_producida == 10

    def test_el_mismo_envio_repetido_solo_cuenta_una_vez(self, orden):
        """El celular del taller reenvía cuando la red se cae a media petición."""
        produccion.registrar_avance(
            orden, contador=CONTADOR.PRODUCIDA, delta=3, actor="ana",
            clave_idempotencia="pieza-abc",
        )
        produccion.registrar_avance(
            orden, contador=CONTADOR.PRODUCIDA, delta=3, actor="ana",
            clave_idempotencia="pieza-abc",
        )

        orden.refresh_from_db(using=BASE)
        assert orden.cantidad_producida == 3
        assert EventoProduccion.objects.using(BASE).filter(
            orden=orden, tipo=EventoProduccion.Tipo.AVANCE
        ).count() == 1

    def test_no_se_puede_terminar_lo_que_no_se_pinto(self, orden):
        """La invariante que no existía en ningún sitio.

        Ni en el navegador, ni en el servidor, ni en la base. Se podía guardar
        «soldadas 0, pintadas 0, terminadas 50», y esas cincuenta piezas
        aparecían en los informes sin haber pasado por ninguna etapa.
        """
        with pytest.raises(CantidadInvalida):
            produccion.registrar_avance(
                orden, contador=CONTADOR.TERMINADA, delta=5, actor="ana"
            )

    def test_no_se_puede_pasar_del_objetivo(self, orden):
        with pytest.raises(CantidadInvalida):
            produccion.registrar_avance(
                orden, contador=CONTADOR.PRODUCIDA, delta=11, actor="ana"
            )

    def test_no_se_puede_dejar_un_contador_en_negativo(self, orden):
        with pytest.raises(CantidadInvalida):
            produccion.registrar_avance(
                orden, contador=CONTADOR.PRODUCIDA, delta=-1, actor="ana"
            )

    def test_la_cascada_completa_avanza(self, orden):
        for contador in (CONTADOR.PRODUCIDA, CONTADOR.PINTADA, CONTADOR.TERMINADA):
            produccion.registrar_avance(orden, contador=contador, delta=10, actor="ana")
        orden.refresh_from_db(using=BASE)
        assert (orden.cantidad_producida, orden.cantidad_pintada, orden.cantidad_terminada) == (
            10, 10, 10
        )

    def test_los_contadores_se_reconstruyen_desde_el_historial(self, orden):
        """Los contadores son caché: la verdad está en los eventos."""
        produccion.registrar_avance(orden, contador=CONTADOR.PRODUCIDA, delta=4, actor="ana")
        OrdenProduccion.objects.using(BASE).filter(pk=orden.pk).update(cantidad_producida=99)

        produccion.recalcular_contadores(orden)

        orden.refresh_from_db(using=BASE)
        assert orden.cantidad_producida == 4


class TestCierreYReversion:
    @pytest.fixture
    def terminada(self, orden):
        for contador in (CONTADOR.PRODUCIDA, CONTADOR.PINTADA, CONTADOR.TERMINADA):
            produccion.registrar_avance(orden, contador=contador, delta=10, actor="ana")
        orden.refresh_from_db(using=BASE)
        return orden

    def test_al_llegar_al_objetivo_se_abre_la_ventana(self, terminada):
        assert terminada.etapa_actual.es_cierre_pendiente
        assert terminada.cierre_pendiente_hasta is not None

    def test_pasado_el_plazo_el_cierre_es_firme(self, terminada):
        futuro = terminada.cierre_pendiente_hasta + timezone.timedelta(minutes=1)

        produccion.consolidar_cierre(terminada, ahora=futuro)

        terminada.refresh_from_db(using=BASE)
        assert terminada.estado == OrdenProduccion.Estado.CERRADA
        assert terminada.etapa_actual.codigo == "terminado"

    def test_dentro_del_plazo_todavia_no(self, terminada):
        assert produccion.consolidar_cierre(terminada) is None

    def test_revertir_sin_motivo_se_rechaza(self, terminada):
        with pytest.raises(MotivoRequerido):
            produccion.revertir_cierre(terminada, actor="ana", motivo=None)

    def test_revertir_devuelve_la_orden_y_anula_lo_que_el_cierre_hizo(self, terminada):
        """En el sistema heredado revertir dejaba el ingreso a almacén puesto.

        La orden volvía a producción y las piezas seguían contadas como
        entregadas. Aquí la reversión escribe el evento contrario de todo lo
        que el cierre escribió, y no borra nada.
        """
        motivo = produccion.motivo(MotivoEvento.Ambito.REVERSION, "error_de_captura")
        etapa_previa = terminada.cierre_etapa_previa

        produccion.revertir_cierre(terminada, actor="ana", motivo=motivo)

        terminada.refresh_from_db(using=BASE)
        assert terminada.etapa_actual_id == etapa_previa.pk
        assert terminada.cierre_pendiente_hasta is None
        assert terminada.cierre_revertido_por == "ana"

        anulaciones = EventoProduccion.objects.using(BASE).filter(
            orden=terminada, tipo=EventoProduccion.Tipo.ANULACION
        )
        assert anulaciones.exists()
        assert all(a.anula_a_id is not None for a in anulaciones)

    def test_el_historial_no_se_borra_al_revertir(self, terminada):
        antes = EventoProduccion.objects.using(BASE).filter(orden=terminada).count()
        motivo = produccion.motivo(MotivoEvento.Ambito.REVERSION, "error_de_captura")

        produccion.revertir_cierre(terminada, actor="ana", motivo=motivo)

        despues = EventoProduccion.objects.using(BASE).filter(orden=terminada).count()
        assert despues > antes, "revertir añade eventos, nunca quita"

    def test_un_cierre_firme_ya_no_se_revierte(self, terminada):
        futuro = terminada.cierre_pendiente_hasta + timezone.timedelta(minutes=1)
        produccion.consolidar_cierre(terminada, ahora=futuro)
        terminada.refresh_from_db(using=BASE)
        motivo = produccion.motivo(MotivoEvento.Ambito.REVERSION, "error_de_captura")

        with pytest.raises(OrdenBloqueada):
            produccion.revertir_cierre(terminada, actor="ana", motivo=motivo)

    def test_una_orden_cerrada_no_admite_mas_avances(self, terminada):
        futuro = terminada.cierre_pendiente_hasta + timezone.timedelta(minutes=1)
        produccion.consolidar_cierre(terminada, ahora=futuro)
        terminada.refresh_from_db(using=BASE)

        with pytest.raises(OrdenBloqueada):
            produccion.registrar_avance(
                terminada, contador=CONTADOR.PRODUCIDA, delta=1, actor="ana"
            )


class TestLaMismaLogicaSirveParaLasCuatroLineas:
    """El motivo de toda la fase, en un test.

    Si esto pasa para las cuatro líneas sin una sola comprobación de tipo, es
    que ya no hay cuatro motores: hay uno configurado de cuatro formas.
    """

    @pytest.mark.parametrize("codigo", ["vigas", "herreria", "corta", "robotica"])
    def test_alta_y_avance_de_etapa(self, nucleo, codigo):
        linea = LineaNegocio.objects.using(BASE).get(codigo=codigo)
        orden = produccion.crear_orden(
            linea=linea, actor="ana", codigo=f"{codigo}-1", total_piezas=3
        )

        siguientes = produccion.etapas_disponibles(orden)
        assert siguientes, f"{codigo} no tiene ninguna transición configurada"

        destino = min(
            (t.hasta for t in siguientes if t.hasta.orden > orden.etapa_actual.orden),
            key=lambda e: e.orden,
        )
        produccion.cambiar_etapa(orden, destino=destino, actor="ana")

        orden.refresh_from_db(using=BASE)
        assert orden.etapa_actual_id == destino.pk
