"""Armar la cuadrilla del día, y la trazabilidad que eso hace posible.

La regla que sostiene todo lo demás: **el pasado no se edita**. Una cuadrilla
de la semana pasada es lo que atribuye la producción de esos días a personas
concretas. Si se pudiera corregir, ningún número histórico sería comprobable.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from catalogos.models import (
    Colaborador,
    Cuadrilla,
    CuadrillaIntegrante,
    EquipoTrabajo,
    Maquina,
    SeguimientoDespacho,
)
from catalogos import trazabilidad
from core.servicios import trabajo

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

BASE = "mes"
Usuario = get_user_model()


@pytest.fixture
def jefa():
    persona = Usuario.objects.create_user(
        "rosa", password="x", is_staff=True, is_superuser=True
    )
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


@pytest.fixture
def gente():
    equipo = EquipoTrabajo.objects.using(BASE).create(
        nombre="Corte A", area="Corte", integrantes=3, activo=True
    )
    return [
        Colaborador.objects.using(BASE).create(
            nombre=nombre, rol="Cortador", equipo=equipo, activo=True
        )
        for nombre in ("Ana", "Beto", "Ceci")
    ]


@pytest.fixture
def cortadora():
    return Maquina.objects.using(BASE).create(
        nombre="Cortadora 3", tipo="Corte", activo=True, es_robot=False,
    )


def datos(gente, **extra):
    base = {
        "fecha": timezone.localdate().isoformat(),
        "turno": Cuadrilla.Turno.COMPLETO,
        "centro": "Corte",
        "integrante": [str(p.id) for p in gente],
    }
    base.update(extra)
    return base


class TestArmarLaDelDia:
    def test_se_arma_con_la_gente_marcada(self, jefa, gente):
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente))

        cuadrilla = Cuadrilla.objects.using(BASE).get()
        assert cuadrilla.integrantes.count() == 3
        assert cuadrilla.armada_por == "rosa"

    def test_la_jornada_en_blanco_es_el_turno_entero(self, jefa, gente):
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente))

        integrante = CuadrillaIntegrante.objects.using(BASE).first()
        assert integrante.fraccion == Decimal("1.00")

    def test_media_jornada_se_guarda(self, jefa, gente):
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(
            gente, **{f"fraccion_{gente[0].id}": "0.5"}
        ))

        integrante = CuadrillaIntegrante.objects.using(BASE).get(
            colaborador=gente[0]
        )
        assert integrante.fraccion == Decimal("0.50")

    def test_una_jornada_imposible_no_guarda_nada(self, jefa, gente):
        """Se valida antes de escribir. Descubrirlo a mitad de la transacción
        obligaría a deshacerla y el usuario vería un error de sistema."""
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(
            gente, **{f"fraccion_{gente[0].id}": "3"}
        ))

        assert not Cuadrilla.objects.using(BASE).exists()

    def test_una_cuadrilla_vacia_no_se_admite(self, jefa, gente):
        """Peor que ninguna: aparece armada y no atribuye el trabajo a nadie."""
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente, integrante=[]))

        assert not Cuadrilla.objects.using(BASE).exists()

    def test_armar_dos_veces_el_mismo_turno_corrige_en_vez_de_duplicar(
        self, jefa, gente
    ):
        """La base lo impide con una restricción. Sin esto el usuario vería
        «el sistema falló» cuando lo que quiso fue corregir."""
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente))
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente[:1]))

        assert Cuadrilla.objects.using(BASE).count() == 1
        assert Cuadrilla.objects.using(BASE).get().integrantes.count() == 1

    def test_se_puede_armar_la_de_manana(self, jefa, gente):
        manana = (timezone.localdate() + timedelta(days=1)).isoformat()

        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente, fecha=manana))

        assert Cuadrilla.objects.using(BASE).filter(fecha=manana).exists()

    def test_una_persona_dada_de_baja_no_entra(self, jefa, gente):
        Colaborador.objects.using(BASE).filter(pk=gente[0].pk).update(activo=False)

        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente))

        cuadrilla = Cuadrilla.objects.using(BASE).get()
        assert gente[0].id not in [
            i.colaborador_id for i in cuadrilla.integrantes.all()
        ]

    def test_un_centro_inventado_no_se_guarda(self, jefa, gente):
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente, centro="marte"))

        assert not Cuadrilla.objects.using(BASE).exists()


class TestElPasadoNoSeEdita:
    def _de_ayer(self, gente):
        cuadrilla = Cuadrilla.objects.using(BASE).create(
            fecha=timezone.localdate(), turno=Cuadrilla.Turno.COMPLETO, centro="Corte",
        )
        CuadrillaIntegrante.objects.using(BASE).create(
            cuadrilla=cuadrilla, colaborador=gente[0], fraccion=Decimal("1.00")
        )
        Cuadrilla.objects.using(BASE).filter(pk=cuadrilla.pk).update(
            fecha=timezone.localdate() - timedelta(days=3)
        )
        cuadrilla.refresh_from_db()
        return cuadrilla

    def test_no_se_abre_para_cambiar(self, jefa, gente):
        vieja = self._de_ayer(gente)

        respuesta = jefa.get(
            reverse("catalogos:cuadrilla_editar", args=[vieja.pk]), follow=True
        )

        assert reverse("catalogos:cuadrillas") in respuesta.redirect_chain[-1][0]

    def test_no_se_borra(self, jefa, gente):
        vieja = self._de_ayer(gente)

        jefa.post(reverse("catalogos:cuadrilla_deshacer", args=[vieja.pk]))

        assert Cuadrilla.objects.using(BASE).filter(pk=vieja.pk).exists()

    def test_no_se_arma_una_para_un_dia_que_ya_paso(self, jefa, gente):
        ayer = (timezone.localdate() - timedelta(days=1)).isoformat()

        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente, fecha=ayer))

        assert not Cuadrilla.objects.using(BASE).exists()

    def test_la_de_hoy_si_se_borra(self, jefa, gente):
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente))
        cuadrilla = Cuadrilla.objects.using(BASE).get()

        jefa.post(reverse("catalogos:cuadrilla_deshacer", args=[cuadrilla.pk]))

        assert not Cuadrilla.objects.using(BASE).exists()


class TestLaListaAvisaDeLoQueFalta:
    def test_dice_qué_areas_se_quedaron_sin_cuadrilla(self, jefa, gente):
        """Sin el aviso, olvidarse no se nota hasta que los indicadores salen
        vacíos a fin de mes."""
        jefa.post(reverse("catalogos:cuadrilla_armar"), datos(gente))

        respuesta = jefa.get(reverse("catalogos:cuadrillas"))

        sin_armar = respuesta.context["sin_armar"]
        assert "Corte" not in sin_armar
        assert "Soldadura" in sin_armar


class TestLaTrazabilidad:
    def _apuntar(self, maquina, cuantos=1, etapa="Corte"):
        for numero in range(cuantos):
            trabajo.anotar(
                linea=SeguimientoDespacho.Linea.VIGAS,
                referencia=numero + 1,
                codigo=f"V-{numero:03d}",
                etapa=etapa,
                maquina=maquina,
                actor="luis",
            )

    def test_cuenta_los_avances_de_cada_equipo(self, cortadora):
        self._apuntar(cortadora, cuantos=3)
        hoy = timezone.localdate()

        filas = {f["maquina"].id: f["avances"] for f in trazabilidad.por_maquina(hoy, hoy)}

        assert filas[cortadora.id] == 3

    def test_un_equipo_sin_actividad_sigue_en_la_lista(self, cortadora):
        """Un equipo que no aparece se confunde con uno que no existe. Un cero
        dice que está parado, que es la información que se busca."""
        hoy = timezone.localdate()

        filas = trazabilidad.por_maquina(hoy, hoy)

        assert cortadora.id in [f["maquina"].id for f in filas]

    def test_cuenta_por_persona_desde_lo_copiado(self, cortadora, gente):
        cuadrilla = Cuadrilla.objects.using(BASE).create(
            fecha=timezone.localdate(), turno=Cuadrilla.Turno.COMPLETO, centro="Corte",
        )
        for persona in gente:
            CuadrillaIntegrante.objects.using(BASE).create(
                cuadrilla=cuadrilla, colaborador=persona, fraccion=Decimal("1.00")
            )
        self._apuntar(cortadora, cuantos=2)
        hoy = timezone.localdate()

        filas = {f["colaborador"].id: f["avances"] for f in trazabilidad.por_persona(hoy, hoy)}

        assert filas[gente[0].id] == 2

    def test_corregir_la_cuadrilla_no_cambia_el_conteo_pasado(
        self, cortadora, gente
    ):
        cuadrilla = Cuadrilla.objects.using(BASE).create(
            fecha=timezone.localdate(), turno=Cuadrilla.Turno.COMPLETO, centro="Corte",
        )
        for persona in gente:
            CuadrillaIntegrante.objects.using(BASE).create(
                cuadrilla=cuadrilla, colaborador=persona, fraccion=Decimal("1.00")
            )
        self._apuntar(cortadora)

        CuadrillaIntegrante.objects.using(BASE).filter(
            colaborador=gente[0]
        ).delete()

        hoy = timezone.localdate()
        filas = {f["colaborador"].id: f["avances"] for f in trazabilidad.por_persona(hoy, hoy)}
        assert filas[gente[0].id] == 1

    def test_avisa_de_los_avances_de_corte_sin_equipo(self):
        """Debería ser cero. Si no lo es, hay un camino que registra sin decir
        en qué equipo y el indicador por máquina cuenta de menos."""
        self._apuntar(None, cuantos=2)
        hoy = timezone.localdate()

        assert trazabilidad.sin_equipo(hoy, hoy) == 2

    def test_sigue_una_pieza_por_su_codigo(self, jefa, cortadora):
        """En el piso la pieza se llama por lo que lleva pintado, no por su
        número de fila."""
        self._apuntar(cortadora, cuantos=2)

        respuesta = jefa.get(reverse("catalogos:trazabilidad"), {"codigo": "V-001"})

        assert len(respuesta.context["seguimiento"]) == 1

    def test_la_pantalla_abre_sin_datos(self, jefa):
        assert jefa.get(reverse("catalogos:trazabilidad")).status_code == 200

    def test_sin_sesion_no(self):
        cliente = Client(SERVER_NAME="127.0.0.1")
        assert cliente.get(reverse("catalogos:trazabilidad")).status_code == 302
