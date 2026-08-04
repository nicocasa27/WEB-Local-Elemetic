"""Indicadores del tablero que daban números equivocados.

Un indicador mal calculado es peor que ninguno: no se nota que falla, se toman
decisiones con él, y el día que alguien lo descubre se pierde la confianza en
todo el tablero.

**Las toneladas de Herrería salían siempre en cero.** Se calculaban desde
`HerrProduccion`, multiplicando la cantidad por el peso de la pieza del renglón
de la orden. En la base del taller sólo hay una fila de esa tabla y tiene el
renglón vacío, así que el peso resolvía a cero y la suma también. Se ve en las
fotos semanales guardadas: hay una con «1 pieza» y «0 toneladas».

**El retrabajo se medía de dos formas en la misma pantalla**: una buscaba la
palabra suelta en el comentario y otra la etiqueta que pone el formulario. La
primera cuenta como retrabajo un comentario que diga «no hubo retrabajo».
"""

from datetime import date, timedelta

import pytest

from core import estados as est
from core import metricas

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

LUNES = date(2026, 3, 2)
SIGUIENTE = LUNES + timedelta(days=7)


def orden(codigo="H-TEST", piezas=10, peso_kg=500.0):
    from catalogos.models import HerrOrdenProduccion

    return HerrOrdenProduccion.objects.create(
        codigo=codigo,
        nombre=codigo,
        descripcion="",
        total_piezas=piezas,
        peso_kg=peso_kg,
        estado_etapa="Soldadura",
    )


def avance(la_orden, dia, terminadas_prev=0, terminadas_new=0, soldadas_new=0):
    from catalogos.models import HerrAvanceCambio

    return HerrAvanceCambio.objects.create(
        orden=la_orden,
        fecha_operacion=dia,
        terminadas_prev=terminadas_prev,
        terminadas_new=terminadas_new,
        soldadas_prev=0,
        soldadas_new=soldadas_new,
    )


class TestLasToneladasDeHerreria:
    def test_una_orden_terminada_pesa(self):
        """Lo que antes daba cero.

        Diez piezas de una orden de 500 kg son 50 kg cada una.
        """
        la_orden = orden(piezas=10, peso_kg=500.0)
        avance(la_orden, LUNES, terminadas_prev=0, terminadas_new=4)

        assert metricas.piezas_de_herreria(LUNES, SIGUIENTE) == 4
        assert metricas.toneladas_de_herreria(LUNES, SIGUIENTE) == pytest.approx(0.2)

    def test_cuenta_la_diferencia_no_el_total(self):
        """Un cambio de 15 a 22 son siete piezas, no veintidós.

        Es el mismo error que llevaba el avance de la lista: mandar el valor
        absoluto en vez del delta.
        """
        la_orden = orden(piezas=100, peso_kg=1000.0)
        avance(la_orden, LUNES, terminadas_prev=15, terminadas_new=22)

        assert metricas.piezas_de_herreria(LUNES, SIGUIENTE) == 7

    def test_una_correccion_a_la_baja_resta(self):
        """Si alguien capturó de más y lo arregla, la producción baja."""
        la_orden = orden(piezas=10, peso_kg=500.0)
        avance(la_orden, LUNES, terminadas_prev=0, terminadas_new=5)
        avance(la_orden, LUNES, terminadas_prev=5, terminadas_new=3)

        assert metricas.piezas_de_herreria(LUNES, SIGUIENTE) == 3

    def test_solo_cuenta_lo_terminado(self):
        """Contar también soldadas y pintadas mediría la pieza tres veces.

        Es el mismo doble conteo que tiene el tablero en Estructuras, donde la
        misma tonelada se suma en Corte, en Soldadura y en Pintura.
        """
        la_orden = orden(piezas=10, peso_kg=500.0)
        avance(la_orden, LUNES, soldadas_new=8)

        assert metricas.piezas_de_herreria(LUNES, SIGUIENTE) == 0

    def test_reparte_por_dia(self):
        la_orden = orden(piezas=10, peso_kg=500.0)
        avance(la_orden, LUNES, terminadas_prev=0, terminadas_new=2)
        avance(la_orden, LUNES + timedelta(days=1), terminadas_prev=2, terminadas_new=5)

        dias = metricas.produccion_de_herreria(LUNES, SIGUIENTE)

        assert dias[LUNES]["piezas"] == 2
        assert dias[LUNES + timedelta(days=1)]["piezas"] == 3

    def test_no_cuenta_lo_de_otra_semana(self):
        la_orden = orden(piezas=10, peso_kg=500.0)
        avance(la_orden, LUNES - timedelta(days=1), terminadas_new=9)

        assert metricas.piezas_de_herreria(LUNES, SIGUIENTE) == 0

    def test_una_orden_sin_peso_no_inventa_toneladas(self):
        """Enseñar cero es lo correcto: hace visible que falta el dato."""
        la_orden = orden(piezas=10, peso_kg=0.0)
        avance(la_orden, LUNES, terminadas_new=4)

        assert metricas.piezas_de_herreria(LUNES, SIGUIENTE) == 4
        assert metricas.toneladas_de_herreria(LUNES, SIGUIENTE) == 0.0

    def test_una_orden_sin_piezas_no_divide_entre_cero(self):
        """No se puede llegar aquí guardando: el modelo fuerza al menos una
        pieza. La protección se comprueba directamente porque el cálculo no
        debe depender de esa coincidencia."""

        class OrdenRota:
            total_piezas = 0
            peso_kg = 500.0

        assert metricas._peso_unitario(OrdenRota()) == 0.0

    def test_sin_movimiento_da_cero_sin_reventar(self):
        assert metricas.toneladas_de_herreria(LUNES, SIGUIENTE) == 0.0


class TestLaProduccionPorPersonaEsFlujo:
    """El indicador estaba mal planteado, no mal calculado, que es peor: el
    número salía siempre y nadie tenía motivo para dudar de él.

    Se hacía `toneladas en estado Terminado / integrantes` y se comparaba
    contra una meta de media tonelada por persona **a la semana**. Arriba un
    inventario, abajo un flujo. Y como el inventario sólo crece mientras no se
    envía, el indicador subía solo y se desplomaba el día que salía un camión:
    exactamente al revés de lo que significa producir.
    """

    def pieza(self, codigo, peso, estado=est.TERMINADO):
        from django.utils import timezone

        from produccion.models import Viga

        return Viga.objects.create(
            codigo_viga=codigo, pieza_no=1, total_piezas=1, proyecto="P",
            descripcion="", fecha_compromiso=timezone.localdate(), estado=estado,
            prioridad=3, peso_kg=peso,
            fecha_creacion=timezone.now(), ultimo_cambio=timezone.now(),
        )

    def termina(self, pieza, dia):
        from django.utils import timezone

        from produccion.models import ProductionLog

        return ProductionLog.objects.create(
            viga_internal_id=pieza.internal_id,
            estado_anterior=est.PINTURA,
            estado_nuevo=est.TERMINADO,
            fecha_operacion=dia,
            timestamp=timezone.now(),
        )

    def test_cuenta_lo_terminado_en_el_rango(self):
        pieza = self.pieza("F-1", 500)
        self.termina(pieza, LUNES)

        assert metricas.toneladas_terminadas(LUNES, SIGUIENTE) == pytest.approx(0.5)

    def test_no_cuenta_lo_de_otra_semana(self):
        """Es lo que hacía el cálculo viejo: una pieza terminada hace tres
        meses seguía sumando hoy, sólo por estar todavía en el almacén."""
        pieza = self.pieza("F-2", 500)
        self.termina(pieza, LUNES - timedelta(days=30))

        assert metricas.toneladas_terminadas(LUNES, SIGUIENTE) == 0.0

    def test_una_pieza_no_cuenta_dos_veces_el_mismo_dia(self):
        """Un movimiento corregido deja dos apuntes. La pieza es una."""
        pieza = self.pieza("F-3", 500)
        self.termina(pieza, LUNES)
        self.termina(pieza, LUNES)

        assert metricas.toneladas_terminadas(LUNES, SIGUIENTE) == pytest.approx(0.5)

    def test_sigue_contando_aunque_ya_se_haya_enviado(self):
        """Enviar no deshace haber producido.

        Con el cálculo viejo, la producción de la semana bajaba en cuanto
        salía el camión, porque la pieza dejaba de estar en «Terminado».
        """
        pieza = self.pieza("F-4", 500, estado=est.ENVIADO)
        self.termina(pieza, LUNES)

        assert metricas.toneladas_terminadas(LUNES, SIGUIENTE) == pytest.approx(0.5)

    def test_se_reparte_entre_las_personas(self):
        pieza = self.pieza("F-5", 1000)
        self.termina(pieza, LUNES)

        assert metricas.toneladas_por_persona(LUNES, SIGUIENTE, 4) == pytest.approx(0.25)

    def test_sin_personas_da_cero_sin_reventar(self):
        """Pasa el primer día, antes de dar de alta a nadie."""
        assert metricas.toneladas_por_persona(LUNES, SIGUIENTE, 0) == 0.0

    def test_una_semana_sin_producir_da_cero(self):
        assert metricas.toneladas_terminadas(LUNES, SIGUIENTE) == 0.0


class TestElRetrabajoSeMideDeUnaSolaForma:
    def test_cuenta_lo_que_alguien_declaro(self):
        from produccion.models import ProductionLog

        assert metricas.ETIQUETA_RETRABAJO in str(metricas.filtro_de_retrabajo())
        # Y se aplica sobre el campo que se le pida, para poder usarlo también
        # a través de una relación.
        assert "logs__comentario" in str(metricas.filtro_de_retrabajo("logs__comentario"))
        assert ProductionLog.objects.filter(metricas.filtro_de_retrabajo()).count() == 0

    def test_no_cuenta_un_comentario_que_solo_menciona_la_palabra(self):
        """«No hubo retrabajo» contaba como retrabajo."""
        from django.utils import timezone

        from produccion.models import ProductionLog, Viga

        pieza = Viga.objects.create(
            codigo_viga="X-1",
            pieza_no=1,
            total_piezas=1,
            proyecto="P",
            descripcion="",
            fecha_compromiso=timezone.localdate(),
            estado="Corte",
            prioridad=3,
            peso_kg=10,
            fecha_creacion=timezone.now(),
            ultimo_cambio=timezone.now(),
        )
        ProductionLog.objects.create(
            viga_internal_id=pieza.internal_id,
            estado_anterior="Espera de corte",
            estado_nuevo="Corte",
            fecha_operacion=LUNES,
            timestamp=timezone.now(),
            comentario="Se revisó y no hubo retrabajo",
        )

        assert ProductionLog.objects.filter(metricas.filtro_de_retrabajo()).count() == 0

    def test_si_cuenta_el_que_marco_el_formulario(self):
        from django.utils import timezone

        from produccion.models import ProductionLog, Viga

        pieza = Viga.objects.create(
            codigo_viga="X-2",
            pieza_no=1,
            total_piezas=1,
            proyecto="P",
            descripcion="",
            fecha_compromiso=timezone.localdate(),
            estado="Corte",
            prioridad=3,
            peso_kg=10,
            fecha_creacion=timezone.now(),
            ultimo_cambio=timezone.now(),
        )
        ProductionLog.objects.create(
            viga_internal_id=pieza.internal_id,
            estado_anterior="Soldadura",
            estado_nuevo="Corte",
            fecha_operacion=LUNES,
            timestamp=timezone.now(),
            comentario=f"Regresada {metricas.ETIQUETA_RETRABAJO}",
        )

        assert ProductionLog.objects.filter(metricas.filtro_de_retrabajo()).count() == 1
