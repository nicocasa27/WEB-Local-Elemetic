"""La migración al núcleo: sembrado, volcado, escritura doble y reconciliación.

Estos tests no comprueban que el núcleo funcione —de eso se ocupa
test_nucleo_servicio— sino que **se pueda llegar hasta él sin perder nada y
sin apagar el taller**. Es la parte que hace defendible el plan: cada paso es
idempotente, verificable y reversible, y hay una red que avisa cuando algo se
sale.
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from catalogos.models import HerrOrdenProduccion, HerrPiezaCatalogo
from core import banderas
from core.servicios import espejo
from nucleo.models import (
    Etapa,
    EtapaAlias,
    EventoProduccion,
    LineaNegocio,
    OrdenProduccion,
    PiezaCatalogo,
    TransicionPermitida,
)

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def sembrar():
    call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())


def orden_heredada(codigo="H-70100", etapa="Soldadura", **campos):
    valores = {
        "codigo": codigo,
        "total_piezas": 4,
        "cantidad_objetivo": 4,
        "estado_etapa": etapa,
        "estado": "Abierta",
        "peso_kg": 40.0,
        "prioridad": 3,
        "ultimo_cambio": timezone.now(),
    }
    valores.update(campos)
    return HerrOrdenProduccion.objects.create(**valores)


class TestSembrado:
    def test_deja_las_cuatro_lineas_con_sus_etapas(self):
        sembrar()
        assert LineaNegocio.objects.using("mes").count() == 4
        for codigo in ("vigas", "herreria", "corta", "robotica"):
            linea = LineaNegocio.objects.using("mes").get(codigo=codigo)
            assert linea.etapas.count() > 0
            assert linea.transiciones.filter(desde__isnull=True).count() == 1, (
                "cada línea necesita exactamente una etapa de entrada"
            )

    def test_repetirlo_no_duplica_nada(self):
        sembrar()
        antes = (
            LineaNegocio.objects.using("mes").count(),
            Etapa.objects.using("mes").count(),
            TransicionPermitida.objects.using("mes").count(),
        )
        sembrar()
        despues = (
            LineaNegocio.objects.using("mes").count(),
            Etapa.objects.using("mes").count(),
            TransicionPermitida.objects.using("mes").count(),
        )
        assert antes == despues

    def test_las_variantes_ortograficas_apuntan_a_la_misma_etapa(self):
        """«Espera Armado» y «Espera de armado» eran dos estados distintos.

        Una orden guardada con la variante equivocada desaparecía de los
        filtros, porque la comparación era de cadenas y nadie normalizaba.
        """
        sembrar()
        herreria = LineaNegocio.objects.using("mes").get(codigo="herreria")
        alias = EtapaAlias.objects.using("mes").filter(
            etapa__linea=herreria, valor_normalizado__in=["espera armado", "espera de armado"]
        )
        assert alias.count() == 2
        assert len({a.etapa_id for a in alias}) == 1

    def test_se_niega_a_seguir_si_hay_un_estado_que_no_conoce(self):
        """El control que decide si la migración puede continuar.

        Un valor sin etapa significa que hay datos cuya forma no conocíamos.
        Seguir en ese momento es perder esas órdenes al volcarlas.
        """
        orden_heredada(etapa="Granallado")
        with pytest.raises(CommandError, match="sin etapa"):
            sembrar()

    def test_la_simulacion_no_escribe(self):
        call_command("sembrar_nucleo", "--simular", verbosity=0, stdout=StringIO())
        assert LineaNegocio.objects.using("mes").count() == 0


class TestVolcado:
    def test_trae_la_orden_con_su_etapa_y_su_peso(self):
        heredada = orden_heredada()
        sembrar()
        call_command("backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO())

        orden = OrdenProduccion.objects.using("mes").get(
            legacy_modelo="HerrOrdenProduccion", legacy_id=heredada.pk
        )
        assert orden.etapa_actual.nombre == "Soldadura"
        assert orden.peso_kg_total == pytest.approx(40.0)
        assert orden.linea.codigo == "herreria"

    def test_repetirlo_no_duplica_nada(self):
        orden_heredada()
        sembrar()
        for _ in range(2):
            call_command("backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO())

        assert OrdenProduccion.objects.using("mes").count() == 1
        assert (
            EventoProduccion.objects.using("mes")
            .filter(tipo=EventoProduccion.Tipo.CREACION)
            .count()
            == 1
        )

    def test_adopta_una_pieza_de_catalogo_que_ya_estaba_puesta(self):
        """El volcado se caía con «clave duplicada» sobre una base normal.

        En el núcleo puede haber piezas de catálogo que nadie volcó: las que
        siembra la configuración inicial, o las que alguien dio de alta a mano
        en la pantalla. No llevan enlace al legado, así que el volcado no las
        encontraba, intentaba insertar una segunda con el mismo nombre y moría
        contra `pieza_unica_por_linea` con un mensaje que no explicaba nada.

        Adoptar es ponerle el enlace a la que ya existe. Crear otra sería
        peor que fallar: las órdenes quedarían repartidas entre dos piezas que
        son la misma.
        """
        heredada = HerrPiezaCatalogo.objects.create(
            nombre="Barandal tipo A", nombre_normalizado="BARANDAL TIPO A", peso_kg=45.2
        )
        sembrar()
        linea = LineaNegocio.objects.using("mes").get(codigo="herreria")
        suelta = PiezaCatalogo.objects.using("mes").create(
            linea=linea, nombre="Barandal tipo A", nombre_normalizado="BARANDAL TIPO A"
        )

        call_command("backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO())

        piezas = PiezaCatalogo.objects.using("mes").filter(
            linea=linea, nombre_normalizado="BARANDAL TIPO A"
        )
        assert piezas.count() == 1, "duplicó el catálogo en vez de adoptarlo"
        adoptada = piezas.get()
        assert adoptada.pk == suelta.pk
        assert adoptada.legacy_modelo == "HerrPiezaCatalogo"
        assert adoptada.legacy_id == heredada.pk

    def test_y_le_pone_los_datos_del_legado(self):
        """Adoptar no es sólo enlazar: el peso viene del catálogo heredado,
        que es el que la gente mantiene."""
        HerrPiezaCatalogo.objects.create(
            nombre="Ancla J de 3/4", nombre_normalizado="ANCLA J DE 3/4", peso_kg=2.4
        )
        sembrar()
        linea = LineaNegocio.objects.using("mes").get(codigo="herreria")
        PiezaCatalogo.objects.using("mes").create(
            linea=linea, nombre="Ancla J de 3/4", nombre_normalizado="ANCLA J DE 3/4"
        )

        call_command("backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO())

        pieza = PiezaCatalogo.objects.using("mes").get(nombre_normalizado="ANCLA J DE 3/4")
        assert float(pieza.peso_kg) == pytest.approx(2.4)

    def test_no_toca_las_tablas_heredadas(self):
        heredada = orden_heredada()
        antes = HerrOrdenProduccion.objects.values().get(pk=heredada.pk)
        sembrar()
        call_command("backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO())
        assert HerrOrdenProduccion.objects.values().get(pk=heredada.pk) == antes

    def test_lo_que_no_se_pudo_reconstruir_queda_marcado(self):
        """Corte láser movía los contadores sin dejar bitácora.

        Ese hueco se declara con un evento de ajuste marcado, en vez de
        rellenarse con fechas y autores inventados que parecerían historial
        de verdad.
        """
        orden_heredada(cantidad_producida=3, cantidad_pintada=2, cantidad_terminada=1)
        sembrar()
        call_command("backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO())

        ajustes = EventoProduccion.objects.using("mes").filter(sin_historico=True).exclude(
            tipo=EventoProduccion.Tipo.CREACION
        )
        assert ajustes.count() == 3
        assert all(a.motivo.codigo == "sin_historico" for a in ajustes)

    def test_los_contadores_cuadran_con_el_historial(self):
        orden_heredada(cantidad_producida=3, cantidad_pintada=2, cantidad_terminada=1)
        sembrar()
        call_command("backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO())

        orden = OrdenProduccion.objects.using("mes").get()
        suma = {"producida": 0, "pintada": 0, "terminada": 0}
        for evento in EventoProduccion.objects.using("mes").filter(orden=orden).exclude(contador=""):
            suma[evento.contador] += evento.delta_cantidad
        assert suma == {"producida": 3, "pintada": 2, "terminada": 1}


class TestVerificacion:
    def test_pasa_despues_de_un_volcado_correcto(self):
        orden_heredada()
        sembrar()
        call_command("backfill_nucleo", verbosity=0, stdout=StringIO())
        call_command("verificar_backfill", verbosity=0, stdout=StringIO())

    def test_falla_si_una_orden_no_llego_al_nucleo(self):
        """Sin esto, «parece que fue bien» sería todo lo que se puede decir."""
        orden_heredada()
        sembrar()
        call_command("backfill_nucleo", verbosity=0, stdout=StringIO())
        # Una orden nueva que el volcado no vio: es exactamente lo que pasaría
        # si el reflejo se cayera sin que nadie mirase el registro.
        orden_heredada(codigo="H-70999")

        with pytest.raises(SystemExit):
            call_command("verificar_backfill", verbosity=0, stdout=StringIO(), stderr=StringIO())

    def test_el_historial_protege_a_la_orden_de_ser_borrada(self):
        """El registro es de sólo añadir, y eso incluye no poder borrar la orden.

        Es la propiedad que sostiene todo lo demás: si una orden con historial
        se pudiera borrar en cascada, el historial no sería una fuente de
        verdad sino una decoración.
        """
        from django.db.models import ProtectedError

        orden_heredada()
        sembrar()
        call_command("backfill_nucleo", verbosity=0, stdout=StringIO())

        with pytest.raises(ProtectedError):
            OrdenProduccion.objects.using("mes").all().delete()


class TestEscrituraDoble:
    def test_apagada_no_escribe_nada(self, monkeypatch):
        """Es el estado por omisión, y el que hay hoy en el taller."""
        monkeypatch.delenv("MES_NUCLEO_HERRERIA", raising=False)
        heredada = orden_heredada()
        sembrar()

        assert espejo.reflejar("HerrOrdenProduccion", heredada.pk) is None
        assert OrdenProduccion.objects.using("mes").count() == 0

    def test_en_doble_refleja_la_orden(self, monkeypatch):
        monkeypatch.setenv("MES_NUCLEO_HERRERIA", banderas.DOBLE)
        heredada = orden_heredada()
        sembrar()

        orden = espejo.reflejar("HerrOrdenProduccion", heredada.pk)

        assert orden is not None
        assert orden.codigo == heredada.codigo
        assert orden.etapa_actual.nombre == heredada.estado_etapa

    def test_refleja_tambien_los_cambios_posteriores(self, monkeypatch):
        monkeypatch.setenv("MES_NUCLEO_HERRERIA", banderas.DOBLE)
        heredada = orden_heredada(etapa="Corte")
        sembrar()
        espejo.reflejar("HerrOrdenProduccion", heredada.pk)

        heredada.estado_etapa = "Pintura"
        heredada.save()
        espejo.reflejar("HerrOrdenProduccion", heredada.pk)

        orden = OrdenProduccion.objects.using("mes").get()
        assert orden.etapa_actual.nombre == "Pintura"

    def test_un_fallo_del_reflejo_no_tumba_la_operacion(self, monkeypatch):
        """Durante el rodaje, el núcleo todavía no manda nada.

        Dejar al taller sin poder apuntar una pieza por culpa de una tabla que
        aún no se usa sería absurdo. El fallo se registra y se sigue.
        """
        monkeypatch.setenv("MES_NUCLEO_HERRERIA", banderas.DOBLE)
        monkeypatch.delenv("MES_NUCLEO_ESTRICTO", raising=False)
        heredada = orden_heredada()
        # Sin sembrar: el reflejo no puede funcionar.
        assert espejo.reflejar("HerrOrdenProduccion", heredada.pk) is None

    def test_en_estricto_el_fallo_sí_se_propaga(self, monkeypatch):
        monkeypatch.setenv("MES_NUCLEO_HERRERIA", banderas.DOBLE)
        monkeypatch.setenv("MES_NUCLEO_ESTRICTO", "1")
        heredada = orden_heredada()
        with pytest.raises(Exception):
            espejo.reflejar("HerrOrdenProduccion", heredada.pk)

    def test_una_bandera_mal_escrita_se_trata_como_apagada(self, monkeypatch):
        """Una errata en una variable de entorno no debe encender nada."""
        monkeypatch.setenv("MES_NUCLEO_HERRERIA", "dobel")
        assert banderas.modo("herreria") == banderas.APAGADA
        assert not banderas.escribe_en_nucleo("herreria")


class TestReconciliacion:
    def test_sin_diferencias_no_anota_nada(self):
        orden_heredada()
        sembrar()
        call_command("backfill_nucleo", verbosity=0, stdout=StringIO())

        salida = StringIO()
        call_command("reconciliar_nucleo", verbosity=0, stdout=salida)

        from nucleo.models import DivergenciaReconciliacion

        assert DivergenciaReconciliacion.objects.using("mes").count() == 0
        assert "Sin divergencias" in salida.getvalue()

    def test_detecta_una_escritura_en_bloque_que_las_señales_no_ven(self):
        """La razón de que esta comprobación exista.

        `.filter(...).update(...)` no dispara `post_save`, así que no se
        refleja sola. En este código hay nueve de ésas. La reconciliación es
        la red que las caza, y por eso el corte de una línea exige siete días
        limpios y no la palabra de nadie.
        """
        heredada = orden_heredada(etapa="Corte")
        sembrar()
        call_command("backfill_nucleo", verbosity=0, stdout=StringIO())

        HerrOrdenProduccion.objects.filter(pk=heredada.pk).update(estado_etapa="Pintura")

        salida = StringIO()
        call_command("reconciliar_nucleo", verbosity=0, stdout=salida)

        from nucleo.models import DivergenciaReconciliacion

        divergencia = DivergenciaReconciliacion.objects.using("mes").get()
        assert divergencia.campo == "etapa"
        assert divergencia.valor_heredado == "Pintura"
        assert divergencia.valor_nucleo == "Corte"

    def test_corregir_vuelve_a_reflejar_lo_que_diverge(self):
        heredada = orden_heredada(etapa="Corte")
        sembrar()
        call_command("backfill_nucleo", verbosity=0, stdout=StringIO())
        HerrOrdenProduccion.objects.filter(pk=heredada.pk).update(estado_etapa="Pintura")

        call_command("reconciliar_nucleo", "--corregir", verbosity=0, stdout=StringIO())

        orden = OrdenProduccion.objects.using("mes").get()
        assert orden.etapa_actual.nombre == "Pintura"

    def test_avisa_de_una_orden_que_esta_solo_en_el_nucleo(self):
        heredada = orden_heredada()
        sembrar()
        call_command("backfill_nucleo", verbosity=0, stdout=StringIO())
        HerrOrdenProduccion.objects.filter(pk=heredada.pk).delete()

        call_command("reconciliar_nucleo", verbosity=0, stdout=StringIO())

        from nucleo.models import DivergenciaReconciliacion

        divergencia = DivergenciaReconciliacion.objects.using("mes").get()
        assert divergencia.campo == "existencia"


class TestPiezas:
    def test_los_tres_catalogos_se_unen_en_uno(self):
        HerrPiezaCatalogo.objects.create(nombre="Marco A", peso_kg=5.0)
        sembrar()
        call_command("backfill_nucleo", verbosity=0, stdout=StringIO())

        from nucleo.models import PiezaCatalogo

        pieza = PiezaCatalogo.objects.using("mes").get(legacy_modelo="HerrPiezaCatalogo")
        assert pieza.linea.codigo == "herreria"
        assert pieza.peso_kg == pytest.approx(5.0)
