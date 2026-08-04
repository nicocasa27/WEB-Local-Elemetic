"""«Mi trabajo» para Herrería y Corta.mx.

La pantalla del celular sólo cubría Estructuras metálicas. Un herrero entraba
y leía «tu cuenta no tiene un área de producción»: media planta —y la mitad
que más órdenes mueve al día— sin pantalla de piso.

Lo delicado aquí no es enseñar las órdenes, es **no enseñar un botón que el
servidor va a rechazar**. Una orden de varias piezas no avanza por etapas
después de soldadura: se lleva por contadores, y el endpoint la rechaza con
un 409. En el piso, un botón que falla sin explicar por qué hace que la gente
deje de usar la pantalla.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def proyecto():
    from catalogos.models import Proyecto

    return Proyecto.objects.get_or_create(nombre="OBRA DE PRUEBA")[0]


def orden_herreria(estado_etapa="Soldadura", piezas=1, codigo="H-1", estado="Abierta"):
    from catalogos.models import HerrOrdenProduccion

    return HerrOrdenProduccion.objects.create(
        proyecto=proyecto(),
        codigo=codigo,
        pieza_no=1,
        total_piezas=piezas,
        nombre="Barandal",
        descripcion="Barandal tipo A",
        fecha_compromiso=timezone.localdate(),
        prioridad=3,
        peso_kg=50,
        estado_etapa=estado_etapa,
        estado=estado,
        cantidad_objetivo=piezas,
    )


def orden_corta(estado_etapa="Corte", piezas=1, codigo="L-1"):
    from catalogos.models import LaserOrdenProduccion

    return LaserOrdenProduccion.objects.create(
        proyecto=proyecto(),
        codigo=codigo,
        pieza_no=1,
        total_piezas=piezas,
        nombre="Placa",
        descripcion="Placa cortada",
        fecha_compromiso=timezone.localdate(),
        prioridad=3,
        peso_kg=5,
        estado_etapa=estado_etapa,
        estado="Abierta",
        cantidad_objetivo=piezas,
    )


def navegador(django_user_model, nombre, *grupos):
    persona = django_user_model.objects.create_user(nombre, password="x")
    for grupo in grupos:
        persona.groups.add(Group.objects.get_or_create(name=grupo)[0])
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


def trabajos(cliente):
    return cliente.get(reverse("produccion:movil")).context["trabajos"]


class TestHerreriaYaTienePantallaDePiso:
    def test_un_herrero_ve_sus_ordenes(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria(codigo="H-42")

        assert [t["codigo"] for t in trabajos(cliente)] == ["H-42"]

    def test_ya_no_dice_que_no_tiene_area(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria")

        pagina = cliente.get(reverse("produccion:movil")).content.decode()

        assert "no tiene un área de producción" not in pagina

    def test_supervision_tambien(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria_supervision")
        orden_herreria(codigo="H-42")

        assert [t["codigo"] for t in trabajos(cliente)] == ["H-42"]

    def test_el_boton_apunta_al_endpoint_de_herreria(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden = orden_herreria()

        esperado = reverse("catalogos:herreria_change_status_json", args=[orden.pk])

        assert trabajos(cliente)[0]["url_avance"] == esperado

    def test_una_orden_cerrada_no_sale(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria(estado="Cerrada")

        assert trabajos(cliente) == []

    def test_las_etapas_de_espera_tambien_salen(self, django_user_model):
        """Una orden en «Espera de corte» es trabajo disponible del área."""
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria(estado_etapa="Espera de corte", codigo="H-ESPERA")
        orden_herreria(estado_etapa="Corte", codigo="H-ACTIVA")

        assert sorted(t["codigo"] for t in trabajos(cliente)) == ["H-ACTIVA", "H-ESPERA"]

    def test_una_orden_terminada_no_sale(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria(estado_etapa="Terminado")

        assert trabajos(cliente) == []


class TestCortaTambien:
    def test_un_operador_de_corta_ve_sus_ordenes(self, django_user_model):
        cliente = navegador(django_user_model, "carla", "corte_laser")
        orden_corta(codigo="L-42")

        assert [t["codigo"] for t in trabajos(cliente)] == ["L-42"]

    def test_el_boton_apunta_al_endpoint_de_corta(self, django_user_model):
        cliente = navegador(django_user_model, "carla", "corte_laser")
        orden = orden_corta()

        esperado = reverse("catalogos:corte_laser_change_status_json", args=[orden.pk])

        assert trabajos(cliente)[0]["url_avance"] == esperado


class TestCadaQuienLoSuyo:
    def test_el_herrero_no_ve_corta(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_corta(codigo="L-42")

        assert trabajos(cliente) == []

    def test_el_de_corta_no_ve_herreria(self, django_user_model):
        cliente = navegador(django_user_model, "carla", "corte_laser")
        orden_herreria(codigo="H-42")

        assert trabajos(cliente) == []

    def test_el_administrador_ve_las_tres_lineas(self, django_user_model):
        from produccion.models import Viga

        cliente = navegador(django_user_model, "jefa", "admin_general")
        orden_herreria(codigo="H-42")
        orden_corta(codigo="L-42")
        Viga.objects.create(
            codigo_viga="V-42",
            pieza_no=1,
            total_piezas=1,
            proyecto="OBRA",
            descripcion="viga",
            fecha_compromiso=timezone.localdate(),
            estado="Soldadura",
            prioridad=3,
            peso_kg=100,
            fecha_creacion=timezone.now(),
            ultimo_cambio=timezone.now(),
        )

        respuesta = cliente.get(reverse("produccion:movil"))

        assert {t["linea"] for t in respuesta.context["trabajos"]} == {
            "herreria",
            "corta",
            "estructuras",
        }
        assert respuesta.context["varias_lineas"] is True
        assert "Herrería" in respuesta.content.decode()

    def test_con_una_sola_linea_no_se_repite_el_nombre(self, django_user_model):
        """Para un herrero, «Herrería» en las quince tarjetas es ruido."""
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria()

        assert cliente.get(reverse("produccion:movil")).context["varias_lineas"] is False


class TestNoSeEnsenaUnBotonQueElServidorRechaza:
    def test_una_orden_grande_en_soldadura_no_ofrece_avanzar(self, django_user_model):
        """Después de soldadura, una orden de varias piezas se lleva por
        contadores. El endpoint responde 409 a cualquier etapa posterior."""
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria(estado_etapa="Soldadura", piezas=8)

        trabajo = trabajos(cliente)[0]

        assert trabajo["siguiente"] == ""
        assert trabajo["por_cantidades"] is True

    def test_y_manda_a_la_pantalla_donde_si_se_puede(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria(estado_etapa="Soldadura", piezas=8)

        pagina = cliente.get(reverse("produccion:movil")).content.decode()

        assert "Capturar avance por cantidades" in pagina
        assert reverse("catalogos:herreria_control") in pagina

    def test_una_orden_grande_en_corte_si_pasa_a_soldadura(self, django_user_model):
        """De corte a soldadura sí lo acepta, y se salta armado."""
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria(estado_etapa="Corte", piezas=8)

        assert trabajos(cliente)[0]["siguiente"] == "Soldadura"

    def test_una_orden_de_una_pieza_sigue_la_secuencia_completa(self, django_user_model):
        cliente = navegador(django_user_model, "hugo", "herreria")
        orden_herreria(estado_etapa="Corte", piezas=1)

        assert trabajos(cliente)[0]["siguiente"] == "Espera de armado"

    def test_lo_que_se_ofrece_es_lo_que_el_servidor_acepta(self, django_user_model):
        """La comprobación que de verdad importa: se pulsa y avanza.

        Las reglas de qué acepta el endpoint están copiadas en la pantalla.
        Esta prueba es lo que impide que las dos copias se separen.
        """
        from catalogos.models import HerrOrdenProduccion

        cliente = navegador(django_user_model, "hugo", "herreria")
        orden = orden_herreria(estado_etapa="Corte", piezas=8)
        trabajo = trabajos(cliente)[0]

        respuesta = cliente.post(
            trabajo["url_avance"],
            {
                "estado_nuevo": trabajo["siguiente"],
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
            },
        )

        assert respuesta.status_code == 200, respuesta.content
        assert respuesta.json()["ok"] is True
        assert HerrOrdenProduccion.objects.get(pk=orden.pk).estado_etapa == "Soldadura"

    def test_una_orden_de_una_pieza_tambien_llega_al_servidor(self, django_user_model):
        from catalogos.models import HerrOrdenProduccion

        cliente = navegador(django_user_model, "hugo", "herreria")
        orden = orden_herreria(estado_etapa="Corte", piezas=1)
        trabajo = trabajos(cliente)[0]

        respuesta = cliente.post(
            trabajo["url_avance"],
            {
                "estado_nuevo": trabajo["siguiente"],
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
            },
        )

        assert respuesta.status_code == 200, respuesta.content
        assert HerrOrdenProduccion.objects.get(pk=orden.pk).estado_etapa == "Espera de armado"


class TestElRecorteSeDice:
    def test_se_avisa_de_lo_que_no_cupo(self, django_user_model):
        from produccion.movil import TOPE

        cliente = navegador(django_user_model, "hugo", "herreria")
        for i in range(TOPE + 3):
            orden_herreria(codigo=f"H-{i:03d}")

        respuesta = cliente.get(reverse("produccion:movil"))

        assert len(respuesta.context["trabajos"]) == TOPE
        assert respuesta.context["de_mas"] == 3
        assert "3 piezas más pendientes" in respuesta.content.decode()
