"""El diálogo «Asignaciones por etapa».

Abría con las tres listas en blanco: el aviso decía «marca las casillas para
seleccionar múltiples» y no había ninguna casilla. No se podía asignar a
nadie desde ninguna de las tres pantallas de producción.

La causa: el payload se armaba buscando un `EquipoTrabajo` cuyo campo
`estados` nombrara la etapa. `estados` es una lista que se captura a mano y
**ninguno de los equipos la tiene puesta** —los cuatro están en `[]`—, así
que la búsqueda devolvía `None` siempre y el payload salía vacío. La
información sí estaba: en `area`, que dice «Corte», «Soldadura», «Pintura».
"""

import pytest

from produccion.views import _build_participantes_payload, _equipo_for_etapa

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def equipo(nombre, area, estados_json="[]", sub_area=""):
    from catalogos.models import EquipoTrabajo

    return EquipoTrabajo.objects.create(
        nombre=nombre,
        area=area,
        sub_area=sub_area,
        estados_json=estados_json,
        integrantes=3,
        activo=True,
    )


def persona(nombre, el_equipo, rol="Soldador"):
    from catalogos.models import Colaborador

    return Colaborador.objects.create(
        nombre=nombre, rol=rol, equipo=el_equipo, activo=True
    )


class TestEncontrarElEquipoDeUnaEtapa:
    def test_por_el_area_cuando_nadie_capturo_los_estados(self):
        """El caso real: los cuatro equipos del taller tienen `estados` vacío."""
        corte = equipo("Cuadrilla Corte A", "Corte")

        assert _equipo_for_etapa("Corte") == corte

    def test_los_estados_capturados_mandan_sobre_el_area(self):
        """Si alguien se tomó la molestia de configurarlo, gana. La caída al
        `area` es una red, no una regla nueva."""
        equipo("Cuadrilla Corte A", "Corte")
        especial = equipo("Cuadrilla mixta", "Otra", estados_json='["Corte"]')

        assert _equipo_for_etapa("Corte") == especial

    def test_tambien_mira_la_sub_area(self):
        pintura = equipo("Cuadrilla nave 2", "Acabados", sub_area="Pintura")

        assert _equipo_for_etapa("Pintura") == pintura

    def test_no_distingue_mayusculas(self):
        corte = equipo("Cuadrilla Corte A", "CORTE")

        assert _equipo_for_etapa("Corte") == corte

    def test_un_equipo_dado_de_baja_no_cuenta(self):
        corte = equipo("Cuadrilla Corte A", "Corte")
        corte.activo = False
        corte.save()

        assert _equipo_for_etapa("Corte") is None

    def test_una_etapa_sin_equipo_devuelve_nada(self):
        equipo("Cuadrilla Corte A", "Corte")

        assert _equipo_for_etapa("Pintura") is None

    def test_una_etapa_vacia_no_engancha_con_un_area_vacia(self):
        """`sub_area` en blanco es lo normal. Sin esta guarda, pedir la etapa
        vacía devolvería el primer equipo de la lista."""
        equipo("Cuadrilla Corte A", "Corte")

        assert _equipo_for_etapa("") is None
        assert _equipo_for_etapa(None) is None


class TestElDialogoSeLlena:
    def test_las_tres_etapas_traen_su_gente(self):
        corte = equipo("Cuadrilla Corte A", "Corte")
        soldadura = equipo("Cuadrilla Soldadura A", "Soldadura")
        pintura = equipo("Cuadrilla Pintura", "Pintura")
        persona("Ana", corte, rol="Operador")
        persona("Beto", soldadura)
        persona("Carla", pintura, rol="Pintor")

        payload = _build_participantes_payload()

        assert set(payload) == {"Corte", "Soldadura", "Pintura"}
        assert [i["nombre"] for i in payload["Corte"]["items"]] == ["Ana"]
        assert [i["nombre"] for i in payload["Soldadura"]["items"]] == ["Beto"]
        assert [i["nombre"] for i in payload["Pintura"]["items"]] == ["Carla"]

    def test_corte_trae_operadores_y_maquinas(self):
        from catalogos.models import Maquina

        corte = equipo("Cuadrilla Corte A", "Corte")
        persona("Ana", corte, rol="Operador")
        Maquina.objects.create(nombre="Plasma CNC 1", tipo="Corte", activo=True)

        bloque = _build_participantes_payload()["Corte"]

        assert [o["nombre"] for o in bloque["operadores"]] == ["Ana"]
        assert [m["nombre"] for m in bloque["maquinas"]] == ["Plasma CNC 1"]

    def test_soldadura_cae_a_armado_si_hace_falta(self):
        """La etapa se llama Soldadura o Armado según la pantalla."""
        armado = equipo("Cuadrilla de armado", "Armado")
        persona("Beto", armado)

        assert _build_participantes_payload()["Soldadura"]["equipo"] == "Cuadrilla de armado"

    def test_sin_equipos_no_revienta(self):
        assert _build_participantes_payload() == {}


class TestArmadoSePodiaQuedarBloqueado:
    """El fallo que paraba el taller.

    El equipo de una etapa se busca por el área, y **no hay ningún equipo con
    área «Armado»**: los cuatro del taller son Corte, Soldadura, Soldadura y
    Pintura. Como la comprobación estaba antes de mirar si había alguien a
    quien asignar, cualquier intento de pasar una pieza a Armado moría con un
    400, aunque no se estuviera asignando a nadie.

    Once piezas esperando armado que no se podían mover ni desde la lista ni
    desde el celular, y un mensaje que no decía cómo arreglarlo.
    """

    def _avanzar(self, cliente, la_pieza, destino):
        from django.urls import reverse
        from django.utils import timezone

        return cliente.post(
            reverse("produccion:viga_change_status_json", args=[la_pieza.internal_id]),
            {
                "estado_nuevo": destino,
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
            },
        )

    def _pieza(self, estado):
        from django.utils import timezone

        from produccion.models import Viga

        return Viga.objects.create(
            codigo_viga=f"P-{estado}",
            pieza_no=1,
            total_piezas=1,
            proyecto="OBRA",
            descripcion="pieza",
            fecha_compromiso=timezone.localdate(),
            estado=estado,
            prioridad=3,
            peso_kg=100,
            fecha_creacion=timezone.now(),
            ultimo_cambio=timezone.now(),
        )

    def _cliente(self, django_user_model):
        from django.contrib.auth.models import Group
        from django.test import Client

        persona = django_user_model.objects.create_user("juan", password="x")
        persona.groups.add(Group.objects.get_or_create(name="soldadura")[0])
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)
        return cliente

    def test_sin_equipo_de_armado_la_pieza_avanza_igual(self, django_user_model):
        """Sin nadie a quien asignar no hace falta ningún equipo: no hay nada
        que validar contra él."""
        equipo("Cuadrilla Soldadura A", "Soldadura")
        cliente = self._cliente(django_user_model)
        la_pieza = self._pieza("Espera de armado")

        respuesta = self._avanzar(cliente, la_pieza, "Armado")

        assert respuesta.status_code == 200, respuesta.content
        la_pieza.refresh_from_db()
        assert la_pieza.estado == "Armado"

    def test_lo_mismo_con_pintura(self, django_user_model):
        cliente = self._cliente(django_user_model)
        la_pieza = self._pieza("Espera de pintura")

        respuesta = self._avanzar(cliente, la_pieza, "Pintura")

        assert respuesta.status_code == 200, respuesta.content

    def test_si_se_asigna_a_alguien_y_no_hay_equipo_sí_se_avisa(self, django_user_model):
        """Cuando el equipo hace falta de verdad, el mensaje dice dónde se
        arregla. El de antes no lo decía."""
        cliente = self._cliente(django_user_model)
        la_pieza = self._pieza("Espera de armado")

        from django.urls import reverse
        from django.utils import timezone

        respuesta = cliente.post(
            reverse("produccion:viga_change_status_json", args=[la_pieza.internal_id]),
            {
                "estado_nuevo": "Armado",
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
                "soldador_id": "1",
                "auxiliar_ids": "2",
            },
        )

        assert respuesta.status_code == 400
        assert "Configuración de planta" in respuesta.json()["error"]

    def test_con_equipo_y_gente_se_guarda_la_asignacion(self, django_user_model):
        from catalogos.models import VigaAsignacion

        soldadura = equipo("Cuadrilla Soldadura A", "Soldadura", sub_area="Armado")
        soldador = persona("Beto", soldadura, rol="Soldador")
        auxiliar = persona("Ana", soldadura, rol="Auxiliar")
        cliente = self._cliente(django_user_model)
        la_pieza = self._pieza("Espera de armado")

        from django.urls import reverse
        from django.utils import timezone

        respuesta = cliente.post(
            reverse("produccion:viga_change_status_json", args=[la_pieza.internal_id]),
            {
                "estado_nuevo": "Armado",
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
                "soldador_id": str(soldador.id),
                "auxiliar_ids": str(auxiliar.id),
            },
        )

        assert respuesta.status_code == 200, respuesta.content
        asignados = set(
            VigaAsignacion.objects.filter(
                viga_internal_id=la_pieza.internal_id, etapa="Armado", vigente=True
            ).values_list("colaborador__nombre", flat=True)
        )
        assert asignados == {"Beto", "Ana"}
