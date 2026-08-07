"""Cómo se hace la pieza, en la mano de quien la hace.

La tarjeta del celular decía «V-118 · 3/50 · Obra Norte»: cuál es la pieza,
no cómo es. El detalle —«vigas de 70 cm con un corte a los 30 cm a noventa
grados»— viajaba en un plano impreso o de boca en boca, y por eso se rehacían
piezas.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.servicios import especificaciones
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

VIGAS = "Viga"
TEXTO = "Vigas de 70 cm con un corte a los 30 cm a noventa grados."


def viga(codigo="V-1", pieza_no=1, total=1, proyecto="OBRA", estado="Soldadura"):
    from produccion.models import Viga

    fila = Viga.objects.create(
        codigo_viga=codigo,
        pieza_no=pieza_no,
        total_piezas=total,
        proyecto=proyecto,
        descripcion="pieza",
        fecha_compromiso=timezone.localdate(),
        estado=estado,
        prioridad=3,
        peso_kg=100,
        fecha_creacion=timezone.now(),
        ultimo_cambio=timezone.now(),
    )
    return fila


def lote(cuantas=3, codigo="V-LOTE"):
    return [viga(codigo=codigo, pieza_no=n, total=cuantas) for n in range(1, cuantas + 1)]


class TestGuardarYLeer:
    def test_se_guarda_y_se_lee(self):
        pieza = viga()

        especificaciones.guardar(VIGAS, pieza.internal_id, TEXTO, quien="ana")

        assert especificaciones.de(VIGAS, pieza.internal_id) == TEXTO

    def test_no_necesita_el_motor_unificado(self):
        """Es contenido que alguien escribió, no configuración.

        La ruta puede esperar a que se encienda la escritura doble: sin ella,
        la orden recorre las etapas de siempre y no se pierde nada. Un texto
        que el ingeniero acaba de teclear, no.
        """
        from nucleo.models import OrdenProduccion

        pieza = viga()  # sin volcar al núcleo

        especificaciones.guardar(VIGAS, pieza.internal_id, TEXTO)

        assert not OrdenProduccion.objects.using(BASE).exists()
        assert especificaciones.de(VIGAS, pieza.internal_id) == TEXTO

    def test_vaciarlo_lo_borra(self):
        """Quien vació el campo dice que no hay instrucciones. Dejar una fila
        vacía haría que la tarjeta del piso reservara un hueco para nada."""
        from nucleo.models import EspecificacionOrden

        pieza = viga()
        especificaciones.guardar(VIGAS, pieza.internal_id, TEXTO)

        especificaciones.guardar(VIGAS, pieza.internal_id, "   ")

        assert especificaciones.de(VIGAS, pieza.internal_id) == ""
        assert not EspecificacionOrden.objects.using(BASE).exists()

    def test_sin_nada_escrito_responde_vacio(self):
        assert especificaciones.de(VIGAS, 999999) == ""
        assert especificaciones.de("", None) == ""

    def test_se_recorta_a_lo_que_cabe_en_una_tarjeta(self):
        """Lo que no cabe en la pantalla del piso no son instrucciones: es un
        plano, y para eso está el PDF."""
        pieza = viga()

        especificaciones.guardar(VIGAS, pieza.internal_id, "x" * 5000)

        assert len(especificaciones.de(VIGAS, pieza.internal_id)) == (
            especificaciones.LARGO_MAXIMO
        )

    def test_guardar_dos_veces_no_duplica(self):
        from nucleo.models import EspecificacionOrden

        pieza = viga()
        especificaciones.guardar(VIGAS, pieza.internal_id, TEXTO)
        especificaciones.guardar(VIGAS, pieza.internal_id, "Otra cosa.")

        assert EspecificacionOrden.objects.using(BASE).count() == 1
        assert especificaciones.de(VIGAS, pieza.internal_id) == "Otra cosa."


class TestEsDelLote:
    """Cincuenta vigas iguales se hacen todas igual.

    Escribirlo en una y no en las otras cuarenta y nueve sería escribirlo
    donde nadie lo va a leer.
    """

    def test_escribir_en_una_lo_escribe_en_todas(self):
        piezas = lote()

        especificaciones.guardar(VIGAS, piezas[0].internal_id, TEXTO)

        for pieza in piezas:
            assert especificaciones.de(VIGAS, pieza.internal_id) == TEXTO

    def test_no_se_desborda_a_otro_pedido(self):
        piezas = lote()
        ajena = viga(codigo="V-OTRA")

        especificaciones.guardar(VIGAS, piezas[0].internal_id, TEXTO)

        assert especificaciones.de(VIGAS, ajena.internal_id) == ""

    def test_de_muchas_las_trae_en_una_consulta(self):
        piezas = lote()
        especificaciones.guardar(VIGAS, piezas[0].internal_id, TEXTO)

        traidas = especificaciones.de_muchas(
            VIGAS, [p.internal_id for p in piezas]
        )

        assert traidas == {p.internal_id: TEXTO for p in piezas}

    def test_de_muchas_sin_nada_no_consulta_de_mas(self):
        assert especificaciones.de_muchas(VIGAS, []) == {}
        assert especificaciones.de_muchas("", [1, 2]) == {}


class TestLoQueSeHaceSiempre:
    def _pieza_de_catalogo(self, nombre="Andamio tipo A"):
        from nucleo.models import LineaNegocio, PiezaCatalogo

        call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
        return PiezaCatalogo.objects.create(
            linea=LineaNegocio.objects.get(codigo="herreria"), nombre=nombre
        )

    def test_una_orden_nueva_hereda_lo_que_dice_su_pieza(self):
        from catalogos.models import HerrOrdenProduccion

        pieza = self._pieza_de_catalogo()
        especificaciones.recordar_en_la_pieza(pieza, TEXTO)

        orden = HerrOrdenProduccion.objects.create(
            codigo="H-ANDAMIO",
            nombre="Andamio tipo A",
            total_piezas=1,
            fecha_compromiso=timezone.localdate(),
            peso_kg=10.0,
        )
        call_command(
            "backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO()
        )

        assert especificaciones.de("HerrOrdenProduccion", orden.pk) == TEXTO

    def test_cambiar_la_pieza_no_reescribe_lo_que_ya_esta_en_produccion(self):
        """Corregir cómo se hace algo de aquí en adelante no puede cambiar lo
        que el taller ya tiene en la mano."""
        from catalogos.models import HerrOrdenProduccion

        pieza = self._pieza_de_catalogo()
        especificaciones.recordar_en_la_pieza(pieza, TEXTO)
        orden = HerrOrdenProduccion.objects.create(
            codigo="H-ANDAMIO",
            nombre="Andamio tipo A",
            total_piezas=1,
            fecha_compromiso=timezone.localdate(),
            peso_kg=10.0,
        )
        call_command(
            "backfill_nucleo", "--linea", "herreria", verbosity=0, stdout=StringIO()
        )

        especificaciones.recordar_en_la_pieza(pieza, "Ahora se hace de otra forma.")

        assert especificaciones.de("HerrOrdenProduccion", orden.pk) == TEXTO
