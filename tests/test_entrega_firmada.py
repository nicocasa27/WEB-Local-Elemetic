"""Entregar y recibir una pieza entre áreas, firmado por los dos.

Si llegan a pintura dos vigas que debían medir un metro y miden noventa
centímetros, el sistema sabía que la pieza había pasado por corte y por
soldadura, pero no sabía **quién dijo que estaba bien**. Y en un taller esa es
la pregunta: no dónde se rompió, sino quién lo revisó y lo dio por bueno.

Lo que estas pruebas fijan es lo que hace que el mecanismo no se apague solo:

- Que el acta se levante cuando la pieza cambia de área, y **sólo** entonces.
  Pedirle firma a un soldador para pasar de armado a soldadura sería pedirle
  que se firme a sí mismo, y en dos días nadie firmaría nada.
- Que devolver una pieza mala **cuente a favor** de quien la devuelve. Si
  contara en contra, nadie devolvería nada y todas las actas serían
  aceptaciones automáticas, que es lo mismo que no tenerlas.
- Que se pueda contestar quién la aceptó firmando que estaba correcta, que es
  el «que la cobren entre los dos».
"""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from core import estados
from core.servicios import entrega as servicio
from nucleo.models import ActaDeEntrega
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

FIRMA = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="


def cuenta(django_user_model, nombre, grupos=()):
    usuario = django_user_model.objects.create_user(username=nombre, password="prueba")
    for grupo in grupos:
        usuario.groups.add(Group.objects.get_or_create(name=grupo)[0])
    return usuario


def pieza(estado=estados.CORTE, codigo="ZZ-1", proyecto="OBRA PRUEBA"):
    from produccion.models import Viga

    return Viga.objects.create(
        codigo_viga=codigo,
        pieza_no=1,
        total_piezas=1,
        proyecto=proyecto,
        descripcion="Viga de prueba",
        fecha_compromiso=timezone.localdate(),
        estado=estado,
        observaciones="",
        prioridad=1,
        peso_kg=100,
        fecha_creacion=timezone.now(),
        ultimo_cambio=timezone.now(),
    )


def avanzar(client, la_pieza, a, **extra):
    datos = {
        "estado_nuevo": a,
        "comentario": "",
        "fecha_operacion": timezone.localdate().isoformat(),
    }
    datos.update(extra)
    return client.post(
        reverse("produccion:viga_change_status_json", args=[la_pieza.internal_id]),
        datos,
    )


# ------------------------------------------------- cuándo hay que firmar y cuándo no


class TestSoloSeFirmaAlCambiarDeArea:
    def test_de_corte_a_soldadura_sí(self):
        origen, destino = servicio.es_traspaso(estados.CORTE, estados.ESPERA_ARMADO)

        assert origen == "Corte"
        assert destino == "Soldadura"

    def test_de_armado_a_soldadura_no(self):
        """Es la misma área. Sería pedirle a alguien que se firme a sí mismo."""
        origen, _ = servicio.es_traspaso(estados.ARMADO, estados.ESPERA_SOLDADURA)

        assert origen is None

    def test_de_espera_de_corte_a_corte_no(self):
        """Empezar a trabajar no es entregar nada."""
        origen, _ = servicio.es_traspaso(estados.ESPERA_CORTE, estados.CORTE)

        assert origen is None

    def test_salir_de_produccion_sí(self):
        """Alguien dio la pieza por terminada. Eso también responde alguien."""
        origen, destino = servicio.es_traspaso(estados.PINTURA, estados.TERMINADO)

        assert origen == "Pintura"
        assert destino == servicio.FUERA_DE_PRODUCCION


class TestElActaSeLevantaAlAvanzar:
    def test_terminar_corte_deja_el_acta_esperando(self, client, django_user_model):
        cortador = cuenta(django_user_model, "zz_cortador", ["corte"])
        client.force_login(cortador)
        la_pieza = pieza(estados.CORTE)

        avanzar(client, la_pieza, estados.ESPERA_ARMADO, firma_entrega=FIRMA)

        acta = servicio.pendiente("Viga", la_pieza.internal_id)
        assert acta is not None
        assert acta.entrega_por == "zz_cortador"
        assert acta.area_origen == "Corte"
        assert acta.area_destino == "Soldadura"
        assert acta.entrega_firma == FIRMA

    def test_empezar_armado_cierra_el_acta_con_quien_la_recibió(
        self, client, django_user_model
    ):
        cortador = cuenta(django_user_model, "zz_cortador", ["corte"])
        soldador = cuenta(django_user_model, "zz_soldador", ["soldadura"])
        la_pieza = pieza(estados.CORTE)

        client.force_login(cortador)
        avanzar(client, la_pieza, estados.ESPERA_ARMADO, firma_entrega=FIRMA)

        client.force_login(soldador)
        avanzar(client, la_pieza, estados.ARMADO, firma_recibo=FIRMA)

        acta = ActaDeEntrega.objects.using(BASE).get(legacy_id=la_pieza.internal_id)
        assert acta.estado == ActaDeEntrega.Estado.ACEPTADA
        assert acta.recibe_por == "zz_soldador"
        assert acta.recibe_firma == FIRMA

    def test_avanzar_dentro_del_área_no_levanta_nada(self, client, django_user_model):
        soldador = cuenta(django_user_model, "zz_soldador", ["soldadura"])
        client.force_login(soldador)
        la_pieza = pieza(estados.ARMADO)

        avanzar(client, la_pieza, estados.ESPERA_SOLDADURA)

        assert ActaDeEntrega.objects.using(BASE).count() == 0

    def test_sin_firma_el_acta_se_levanta_igual(self, client, django_user_model):
        """La firma la exige la pantalla del celular; el servidor no.

        Un avance desde la lista de la PC —o desde el lote— tiene que quedar
        registrado con quién lo hizo. Si el servidor lo rechazara por falta de
        trazo, los movimientos de oficina serían justo los huecos del rastro de
        responsabilidad.
        """
        cortador = cuenta(django_user_model, "zz_cortador", ["corte"])
        client.force_login(cortador)
        la_pieza = pieza(estados.CORTE)

        avanzar(client, la_pieza, estados.ESPERA_ARMADO)

        acta = servicio.pendiente("Viga", la_pieza.internal_id)
        assert acta is not None
        assert acta.entrega_por == "zz_cortador"
        assert acta.entrega_firma == ""

    def test_una_firma_inventada_no_se_guarda(self, client, django_user_model):
        cortador = cuenta(django_user_model, "zz_cortador", ["corte"])
        client.force_login(cortador)
        la_pieza = pieza(estados.CORTE)

        avanzar(client, la_pieza, estados.ESPERA_ARMADO, firma_entrega="<script>x</script>")

        assert servicio.pendiente("Viga", la_pieza.internal_id).entrega_firma == ""


# ---------------------------------------------------------------- devolver


class TestDevolverUnaPiezaMal:
    def preparar(self, client, django_user_model):
        cortador = cuenta(django_user_model, "zz_cortador", ["corte"])
        soldador = cuenta(django_user_model, "zz_soldador", ["soldadura"])
        la_pieza = pieza(estados.CORTE)
        client.force_login(cortador)
        avanzar(client, la_pieza, estados.ESPERA_ARMADO, firma_entrega=FIRMA)
        client.force_login(soldador)
        return la_pieza, cortador, soldador

    def test_vuelve_a_la_cola_del_área_que_la_entregó(self, client, django_user_model):
        from produccion.models import Viga

        la_pieza, _, _ = self.preparar(client, django_user_model)

        client.post(reverse("produccion:movil_devolver"), {
            "pieza": la_pieza.internal_id,
            "motivo": "Miden 90 cm y debían ser de un metro",
        })

        assert Viga.objects.using(BASE).get(pk=la_pieza.pk).estado == estados.ESPERA_CORTE

    def test_queda_registrado_quién_la_entregó_así(self, client, django_user_model):
        la_pieza, _, _ = self.preparar(client, django_user_model)

        client.post(reverse("produccion:movil_devolver"), {
            "pieza": la_pieza.internal_id,
            "motivo": "Miden 90 cm",
        })

        acta = ActaDeEntrega.objects.using(BASE).get(legacy_id=la_pieza.internal_id)
        assert acta.estado == ActaDeEntrega.Estado.RECHAZADA
        assert acta.entrega_por == "zz_cortador"
        assert acta.recibe_por == "zz_soldador"
        assert "90 cm" in acta.motivo

    def test_se_cierran_las_actas_de_todo_el_lote(self, client, django_user_model):
        """Encontrado probándolo: se devolvían las doce y se cerraba un acta.

        El acta es de cada pieza. Si sólo se cerrara la del botón que se pulsó,
        las otras once se quedarían esperando a que alguien recibiera una pieza
        que ya no está ahí, y el indicador contaría una devolución donde hubo
        doce.
        """
        cortador = cuenta(django_user_model, "zz_cortador", ["corte"])
        soldador = cuenta(django_user_model, "zz_soldador", ["soldadura"])
        primera = pieza(estados.CORTE)
        segunda = pieza(estados.CORTE)

        client.force_login(cortador)
        avanzar(client, primera, estados.ESPERA_ARMADO, firma_entrega=FIRMA)
        avanzar(client, segunda, estados.ESPERA_ARMADO, firma_entrega=FIRMA)

        client.force_login(soldador)
        client.post(reverse("produccion:movil_devolver"), {
            "pieza": primera.internal_id,
            "motivo": "Las dos miden 90 cm",
        })

        rechazadas = ActaDeEntrega.objects.using(BASE).filter(
            estado=ActaDeEntrega.Estado.RECHAZADA
        )
        assert rechazadas.count() == 2
        assert not ActaDeEntrega.objects.using(BASE).filter(
            estado=ActaDeEntrega.Estado.PENDIENTE
        ).exists()

    def test_sin_motivo_no_se_devuelve(self, client, django_user_model):
        from produccion.models import Viga

        la_pieza, _, _ = self.preparar(client, django_user_model)

        client.post(reverse("produccion:movil_devolver"), {
            "pieza": la_pieza.internal_id,
            "motivo": "   ",
        })

        # Ni se devuelve la pieza ni se cierra el acta: una devolución sin
        # motivo obliga a quien la recibe a llamar por teléfono, que es lo que
        # esto venía a ahorrar.
        assert Viga.objects.using(BASE).get(pk=la_pieza.pk).estado == estados.ESPERA_ARMADO
        assert servicio.pendiente("Viga", la_pieza.internal_id) is not None

    def test_quien_la_entregó_no_puede_devolverse_su_propia_entrega(
        self, client, django_user_model
    ):
        """Si pudiera, borraría el rastro de que la entregó mal."""
        from produccion.models import Viga

        la_pieza, cortador, _ = self.preparar(client, django_user_model)
        client.force_login(cortador)

        client.post(reverse("produccion:movil_devolver"), {
            "pieza": la_pieza.internal_id,
            "motivo": "nada",
        })

        assert Viga.objects.using(BASE).get(pk=la_pieza.pk).estado == estados.ESPERA_ARMADO


# --------------------------------------------- quién la dio por buena


class TestQuiénLaDioPorBuena:
    def test_se_puede_saber_quién_firmó_que_estaba_correcta(
        self, client, django_user_model
    ):
        """El caso que pidió el taller, entero.

        Corte entrega. Soldadura acepta y firma que está bien. Soldadura
        entrega a pintura. Pintura la devuelve. Responden dos: el soldador que
        la entregó así, y él mismo por haberla aceptado de corte diciendo que
        estaba correcta.
        """
        cuenta(django_user_model, "zz_cortador", ["corte"])
        cuenta(django_user_model, "zz_soldador", ["soldadura"])
        cuenta(django_user_model, "zz_pintor", ["pintura"])
        la_pieza = pieza(estados.CORTE)

        client.login(username="zz_cortador", password="prueba")
        avanzar(client, la_pieza, estados.ESPERA_ARMADO, firma_entrega=FIRMA)

        client.login(username="zz_soldador", password="prueba")
        avanzar(client, la_pieza, estados.ARMADO, firma_recibo=FIRMA)
        avanzar(client, la_pieza, estados.ESPERA_SOLDADURA)
        avanzar(client, la_pieza, estados.SOLDADURA)
        avanzar(client, la_pieza, estados.ESPERA_PINTURA, firma_entrega=FIRMA)

        segunda = servicio.pendiente("Viga", la_pieza.internal_id)
        assert segunda.area_origen == "Soldadura"
        assert segunda.entrega_por == "zz_soldador"
        # Y quién la había aceptado de corte firmando que estaba bien.
        assert servicio.quien_la_dio_por_buena(segunda) == "zz_soldador"

    def test_en_la_primera_entrega_no_hay_nadie_antes(self, client, django_user_model):
        cortador = cuenta(django_user_model, "zz_cortador", ["corte"])
        client.force_login(cortador)
        la_pieza = pieza(estados.CORTE)
        avanzar(client, la_pieza, estados.ESPERA_ARMADO)

        acta = servicio.pendiente("Viga", la_pieza.internal_id)

        assert servicio.quien_la_dio_por_buena(acta) == ""
