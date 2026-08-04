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
