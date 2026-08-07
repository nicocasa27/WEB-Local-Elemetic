"""Stock comprometido: apartar material sin sacarlo del estante.

El taller pidió dos cosas que parecen una sola y no lo son:

- Al generar una orden, el material queda **apartado**. Deja de poder
  prometerse a otra orden.
- El inventario **no baja** hasta que el almacenista, con el material en la
  mano, confirma que lo entregó.

Hacerlo con un solo número no funciona, y las dos formas de intentarlo fallan
en direcciones opuestas:

- Si se descuenta al generar la orden, el sistema dice que no hay material que
  sí está en el estante. El almacenista cuenta, ve más de lo que dice la
  pantalla, y deja de creerle. A partir de ahí el inventario es decorativo.
- Si se descuenta sólo al entregar, dos órdenes se prometen la misma lámina y
  nadie se entera hasta el día de la entrega, cuando ya no da tiempo de
  comprar.

Por eso hay dos números y una resta: lo **físico** es lo que hay para contar,
lo **comprometido** es lo que ya tiene dueño, y lo **disponible** —la
diferencia— es lo único que se le puede prometer a una orden nueva.
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.excepciones import CantidadInvalida, StockInsuficiente
from core.servicios import inventario as servicio
from inventario.models import Existencia, LoteMaterial, Material, MovimientoMaterial
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])



@pytest.fixture
def almacen():
    call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
    call_command("sembrar_inventario", verbosity=0, stdout=StringIO())
    return servicio.almacen_principal()


@pytest.fixture
def material(almacen):
    return Material.objects.using(BASE).create(
        codigo="PL-RES", nombre="Lámina de prueba", nombre_normalizado="LÁMINA DE PRUEBA",
        unidad=Material.Unidad.PIEZA, peso_kg=Decimal("50"), stock_minimo=Decimal("4"),
    )


def con_existencia(material, almacen, cantidad, dias=1, costo="100", codigo="L-1"):
    """Un lote recibido y dado de alta, listo para apartar."""
    lote = LoteMaterial.objects.using(BASE).create(
        material=material, codigo=codigo, colada=f"COL-{codigo}",
        costo_unitario=Decimal(costo),
        recibido_en=timezone.localdate() - timezone.timedelta(days=dias),
    )
    servicio.registrar_entrada(
        lote=lote, cantidad=Decimal(cantidad), actor=None, almacen=almacen
    )
    return lote


class TestApartarNoEsSacar:
    def test_reservar_no_baja_el_fisico(self, material, almacen):
        """Lo que el almacenista cuenta en el estante no cambia."""
        con_existencia(material, almacen, 10)

        servicio.reservar(material=material, cantidad=3, actor=None)

        assert servicio.existencia(material, almacen=almacen) == Decimal("10")
        assert servicio.comprometido(material, almacen) == Decimal("3")

    def test_lo_que_baja_es_lo_disponible(self, material, almacen):
        con_existencia(material, almacen, 10)
        assert servicio.disponible(material, almacen=almacen) == Decimal("10")

        servicio.reservar(material=material, cantidad=3, actor=None)

        assert servicio.disponible(material, almacen=almacen) == Decimal("7")

    def test_entregar_es_lo_que_baja_el_inventario(self, material, almacen):
        con_existencia(material, almacen, 10)
        servicio.reservar(material=material, cantidad=3, actor=None)

        servicio.entregar(material=material, cantidad=3, actor=None)

        assert servicio.existencia(material, almacen=almacen) == Decimal("7")
        # Y la reserva no se queda colgada.
        assert servicio.comprometido(material, almacen) == Decimal("0")
        assert servicio.disponible(material, almacen=almacen) == Decimal("7")


class TestNoSePrometeDosVecesLaMismaLamina:
    """El fallo que justifica todo esto."""

    def test_dos_ordenes_no_pueden_apartar_lo_mismo(self, material, almacen):
        con_existencia(material, almacen, 10)
        servicio.reservar(material=material, cantidad=8, actor=None)

        with pytest.raises(StockInsuficiente):
            servicio.reservar(material=material, cantidad=5, actor=None)

        # Y la primera reserva sigue intacta: el intento fallido no la tocó.
        assert servicio.comprometido(material, almacen) == Decimal("8")

    def test_se_puede_apartar_justo_lo_que_queda(self, material, almacen):
        con_existencia(material, almacen, 10)
        servicio.reservar(material=material, cantidad=8, actor=None)
        servicio.reservar(material=material, cantidad=2, actor=None)

        assert servicio.disponible(material, almacen=almacen) == Decimal("0")

    def test_la_base_lo_impide_aunque_se_escriba_a_mano(self, material, almacen):
        """La restricción no está sólo en el servicio.

        Un `update` en bloque o una consulta a mano no pasan por aquí, y el
        día que alguien lo haga el almacén no puede quedar prometiendo
        material que no existe.
        """
        con_existencia(material, almacen, 10)
        fila = Existencia.objects.using(BASE).get(material=material)

        with pytest.raises(IntegrityError):
            with transaction.atomic(using=BASE):
                Existencia.objects.using(BASE).filter(pk=fila.pk).update(
                    comprometido=Decimal("11")
                )

    def test_tampoco_se_compromete_en_negativo(self, material, almacen):
        con_existencia(material, almacen, 10)
        fila = Existencia.objects.using(BASE).get(material=material)

        with pytest.raises(IntegrityError):
            with transaction.atomic(using=BASE):
                Existencia.objects.using(BASE).filter(pk=fila.pk).update(
                    comprometido=Decimal("-1")
                )


class TestLiberar:
    def test_soltar_una_reserva_devuelve_lo_disponible(self, material, almacen):
        con_existencia(material, almacen, 10)
        servicio.reservar(material=material, cantidad=6, actor=None)

        servicio.liberar(material=material, cantidad=6, actor=None)

        assert servicio.comprometido(material, almacen) == Decimal("0")
        assert servicio.disponible(material, almacen=almacen) == Decimal("10")
        # Y no movió nada del estante: liberar no es devolver.
        assert servicio.existencia(material, almacen=almacen) == Decimal("10")

    def test_no_se_libera_mas_de_lo_apartado(self, material, almacen):
        con_existencia(material, almacen, 10)
        servicio.reservar(material=material, cantidad=2, actor=None)

        with pytest.raises(CantidadInvalida):
            servicio.liberar(material=material, cantidad=5, actor=None)


class TestPorLoteYPorAntiguedad:
    def test_se_aparta_del_lote_mas_antiguo(self, material, almacen):
        """Lo que se aparta hoy es lo que se entrega mañana, así que la colada
        queda decidida desde la reserva y no depende de quién tome la lámina
        del estante."""
        viejo = con_existencia(material, almacen, 5, dias=30, codigo="L-VIEJO")
        con_existencia(material, almacen, 5, dias=1, codigo="L-NUEVO")

        servicio.reservar(material=material, cantidad=4, actor=None)

        fila = Existencia.objects.using(BASE).get(material=material, lote=viejo)
        assert fila.comprometido == Decimal("4")

    def test_una_reserva_grande_se_reparte_entre_lotes(self, material, almacen):
        viejo = con_existencia(material, almacen, 5, dias=30, codigo="L-VIEJO")
        nuevo = con_existencia(material, almacen, 5, dias=1, codigo="L-NUEVO")

        movimientos = servicio.reservar(material=material, cantidad=8, actor=None)

        assert len(movimientos) == 2
        assert Existencia.objects.using(BASE).get(
            material=material, lote=viejo).comprometido == Decimal("5")
        assert Existencia.objects.using(BASE).get(
            material=material, lote=nuevo).comprometido == Decimal("3")

    def test_no_se_aparta_de_un_lote_ya_comprometido(self, material, almacen):
        viejo = con_existencia(material, almacen, 5, dias=30, codigo="L-VIEJO")
        nuevo = con_existencia(material, almacen, 5, dias=1, codigo="L-NUEVO")
        servicio.reservar(material=material, cantidad=5, actor=None)

        servicio.reservar(material=material, cantidad=3, actor=None)

        assert Existencia.objects.using(BASE).get(
            material=material, lote=viejo).comprometido == Decimal("5")
        assert Existencia.objects.using(BASE).get(
            material=material, lote=nuevo).comprometido == Decimal("3")


class TestAlertaDeReorden:
    def test_avisa_cuando_la_entrega_deja_el_estante_bajo_minimo(self, material, almacen):
        """El taller lo pidió con «≤»: quedarse justo en el mínimo ya es
        motivo de compra, porque el mínimo es lo que cubre lo que tarda en
        llegar el pedido."""
        con_existencia(material, almacen, 10)  # mínimo del material: 4

        _, faltantes = servicio.entregar(material=material, cantidad=6, actor=None)

        assert len(faltantes) == 1
        material_faltante, queda, comprar = faltantes[0]
        assert material_faltante == material
        assert queda == Decimal("4")
        assert comprar == Decimal("0")

    def test_no_avisa_si_todavia_sobra(self, material, almacen):
        con_existencia(material, almacen, 10)

        _, faltantes = servicio.entregar(material=material, cantidad=2, actor=None)

        assert faltantes == []

    def test_dice_cuanto_falta_para_llegar_al_minimo(self, material, almacen):
        con_existencia(material, almacen, 10)

        _, faltantes = servicio.entregar(material=material, cantidad=9, actor=None)

        _, queda, comprar = faltantes[0]
        assert queda == Decimal("1")
        assert comprar == Decimal("3")

    def test_un_material_sin_minimo_no_avisa_nunca(self, almacen):
        """Cero significa que no se vigila, no que el mínimo sea cero."""
        suelto = Material.objects.using(BASE).create(
            codigo="SIN-MIN", nombre="Sin mínimo", nombre_normalizado="SIN MÍNIMO",
            unidad=Material.Unidad.PIEZA, stock_minimo=Decimal("0"),
        )
        con_existencia(suelto, almacen, 5)

        _, faltantes = servicio.entregar(material=suelto, cantidad=5, actor=None)

        assert faltantes == []


class TestLoQueNoSeGuardaEnUnEstante:
    def test_un_flete_no_se_reserva(self, almacen):
        """OPUS trae en la explosión renglones que no son material: los
        indirectos por porcentaje, la luz, el agua de pozo. Sin esta marca, el
        almacenista tendría que decir cuántos fletes hay en el estante."""
        flete = Material.objects.using(BASE).create(
            codigo="FLETECOMPRA", nombre="Flete de compra", nombre_normalizado="FLETE DE COMPRA",
            unidad=Material.Unidad.PIEZA, inventariable=False,
        )

        movimientos = servicio.reservar(material=flete, cantidad=1, actor=None)

        # No es un error: es que ese renglón no vive en ningún almacén.
        assert movimientos == []
        assert servicio.comprometido(flete, almacen) == Decimal("0")

    def test_por_defecto_todo_es_inventariable(self, material):
        assert material.inventariable is True


class TestLaVerdadSiguenSiendoLosMovimientos:
    def test_la_reserva_queda_escrita_con_quien_y_para_que(self, material, almacen):
        con_existencia(material, almacen, 10)

        servicio.reservar(material=material, cantidad=3, actor=None, comentario="OP-77")

        apunte = MovimientoMaterial.objects.using(BASE).get(
            tipo=MovimientoMaterial.Tipo.RESERVA
        )
        assert apunte.cantidad == Decimal("3")
        assert apunte.comentario == "OP-77"

    def test_recalcular_no_confunde_la_promesa_con_el_estante(self, material, almacen):
        """El fallo que habría metido este cambio si nadie lo mira.

        Las existencias se reconstruyen sumando los movimientos, y así se
        comprueba que la caché no miente. Si la reserva contara en esa suma,
        el físico saldría de más por cada apartado y de menos por cada
        liberación: parecería un descuadre del almacén siendo del recálculo.
        """
        con_existencia(material, almacen, 10)
        servicio.reservar(material=material, cantidad=4, actor=None)

        servicio.recalcular_existencias(material=material)

        fila = Existencia.objects.using(BASE).get(material=material)
        assert fila.cantidad == Decimal("10")
        assert fila.comprometido == Decimal("4")
        assert servicio.descuadres() == []

    def test_el_recalculo_reconstruye_tambien_lo_comprometido(self, material, almacen):
        con_existencia(material, almacen, 10)
        servicio.reservar(material=material, cantidad=4, actor=None)
        # Alguien escribe por un camino que no pasa por el servicio.
        Existencia.objects.using(BASE).filter(material=material).update(
            comprometido=Decimal("1")
        )

        assert servicio.recalcular_existencias(material=material) == 1
        assert Existencia.objects.using(BASE).get(
            material=material).comprometido == Decimal("4")


class TestReintentos:
    def test_reservar_dos_veces_con_la_misma_clave_aparta_una_vez(self, material, almacen):
        """El celular reenvía cuando la red del taller falla."""
        con_existencia(material, almacen, 10)

        servicio.reservar(material=material, cantidad=3, actor=None, clave_idempotencia="k1")
        servicio.reservar(material=material, cantidad=3, actor=None, clave_idempotencia="k1")

        assert servicio.comprometido(material, almacen) == Decimal("3")

    def test_entregar_dos_veces_con_la_misma_clave_descuenta_una_vez(self, material, almacen):
        con_existencia(material, almacen, 10)
        servicio.reservar(material=material, cantidad=3, actor=None)

        servicio.entregar(material=material, cantidad=3, actor=None, clave_idempotencia="e1")
        servicio.entregar(material=material, cantidad=3, actor=None, clave_idempotencia="e1")

        assert servicio.existencia(material, almacen=almacen) == Decimal("7")


class TestCantidades:
    @pytest.mark.parametrize("cantidad", [0, -1])
    def test_no_se_aparta_cero_ni_negativo(self, material, almacen, cantidad):
        con_existencia(material, almacen, 10)
        with pytest.raises(CantidadInvalida):
            servicio.reservar(material=material, cantidad=cantidad, actor=None)

    def test_no_se_aparta_lo_que_no_hay(self, material, almacen):
        con_existencia(material, almacen, 2)
        with pytest.raises(StockInsuficiente):
            servicio.reservar(material=material, cantidad=3, actor=None)
