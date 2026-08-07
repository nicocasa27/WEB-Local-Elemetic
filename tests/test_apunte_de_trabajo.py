"""Con qué equipo y con qué cuadrilla se hizo cada avance.

La bitácora heredada dice que una pieza pasó de Corte a Espera de armado, y
nada más. No dice en cuál de los seis equipos de corte se hizo ni quién
estaba, así que «cuánto produjo la cortadora 3 esta semana» no tenía respuesta.

Dos decisiones se prueban aquí porque no son obvias:

- **Los integrantes se copian, no se consultan.** Una cuadrilla es un registro
  vivo; si el apunte sólo guardara la llave, corregirla mañana reescribiría
  quién cortó la pieza la semana pasada.
- **Anotar nunca impide avanzar.** Sin cuadrilla armada el apunte se escribe
  igual. Un taller que no puede mover una pieza porque falta un dato de
  medición deja de usar el sistema, y entonces no se mide nada.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from catalogos.models import (
    ApunteDeTrabajo,
    Colaborador,
    Cuadrilla,
    CuadrillaIntegrante,
    EquipoTrabajo,
    Maquina,
    SeguimientoDespacho,
)
from core.servicios import trabajo
from produccion.models import Viga
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

Usuario = get_user_model()


@pytest.fixture
def cortadora():
    return Maquina.objects.using(BASE).create(
        nombre="Cortadora 3", tipo="Corte", activo=True, es_robot=False,
        funcion="Perfil hasta 12 mm",
    )


@pytest.fixture
def pintadora():
    return Maquina.objects.using(BASE).create(
        nombre="Cabina 1", tipo="Pintura", activo=True, es_robot=False,
    )


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


def cuadrilla_de_hoy(centro="Corte", maquina=None, gente=(), turno=None):
    cuadrilla = Cuadrilla.objects.using(BASE).create(
        fecha=timezone.localdate(),
        turno=turno or Cuadrilla.Turno.COMPLETO,
        centro=centro,
        maquina=maquina,
    )
    for persona in gente:
        CuadrillaIntegrante.objects.using(BASE).create(
            cuadrilla=cuadrilla, colaborador=persona,
            papel="Operador", fraccion=Decimal("1.00"),
        )
    return cuadrilla


def pieza(codigo="V-1", estado="Espera de corte"):
    return Viga.objects.using(BASE).create(
        codigo_viga=codigo, pieza_no=1, total_piezas=1, proyecto="TORRE",
        descripcion="HSS", fecha_compromiso=timezone.localdate(),
        estado=estado, prioridad=3, peso_kg=Decimal("50"),
        fecha_creacion=timezone.now(), ultimo_cambio=timezone.now(),
    )


class TestElApunteGuardaLoQueLaBitacoraNoGuarda:
    def test_queda_el_equipo(self, cortadora, gente):
        cuadrilla_de_hoy(gente=gente)

        apunte = trabajo.anotar(
            linea=SeguimientoDespacho.Linea.VIGAS, referencia=7,
            etapa="Corte", maquina=cortadora, actor="ana",
        )

        assert apunte.maquina_id == cortadora.id

    def test_queda_la_cuadrilla_sin_haberla_pedido(self, cortadora, gente):
        """Nadie va a escribir su cuadrilla en cada avance. Si hubiera que
        capturarla, el campo llegaría vacío y el dato no serviría."""
        cuadrilla = cuadrilla_de_hoy(gente=gente)

        apunte = trabajo.anotar(
            linea=SeguimientoDespacho.Linea.VIGAS, referencia=7,
            etapa="Corte", maquina=cortadora,
        )

        assert apunte.cuadrilla_id == cuadrilla.id

    def test_los_integrantes_quedan_copiados(self, cortadora, gente):
        cuadrilla_de_hoy(gente=gente)

        apunte = trabajo.anotar(
            linea=SeguimientoDespacho.Linea.VIGAS, referencia=7,
            etapa="Corte", maquina=cortadora,
        )

        assert apunte.integrantes_ids == sorted(p.id for p in gente)

    def test_corregir_la_cuadrilla_manana_no_reescribe_el_pasado(
        self, cortadora, gente
    ):
        """La razón de copiar en vez de consultar.

        Si el apunte leyera la cuadrilla al mostrarlo, quitar hoy a quien no
        vino cambiaría quién cortó la pieza la semana pasada. El apunte es un
        hecho: dice quién había en ese momento.
        """
        cuadrilla = cuadrilla_de_hoy(gente=gente)
        apunte = trabajo.anotar(
            linea=SeguimientoDespacho.Linea.VIGAS, referencia=7,
            etapa="Corte", maquina=cortadora,
        )

        CuadrillaIntegrante.objects.using(BASE).filter(
            cuadrilla=cuadrilla, colaborador=gente[0]
        ).delete()

        apunte.refresh_from_db()
        assert gente[0].id in apunte.integrantes_ids

    def test_sin_cuadrilla_armada_se_anota_igual(self, cortadora):
        """Anotar nunca impide avanzar. Un apunte sin cuadrilla vale más que
        una pieza que no se puede mover."""
        apunte = trabajo.anotar(
            linea=SeguimientoDespacho.Linea.VIGAS, referencia=7,
            etapa="Corte", maquina=cortadora,
        )

        assert apunte.pk is not None
        assert apunte.cuadrilla_id is None

    def test_una_linea_inventada_se_rechaza(self, cortadora):
        with pytest.raises(ValueError):
            trabajo.anotar(linea="volando", referencia=1, etapa="Corte")


class TestQueCuadrillaEsLaVigente:
    def test_la_del_equipo_gana_sobre_la_del_area(self, cortadora, gente):
        """«La cuadrilla de la cortadora 3» dice más que «la de corte»."""
        cuadrilla_de_hoy(gente=gente)
        pegada = cuadrilla_de_hoy(maquina=cortadora, gente=gente[:1])

        elegida = trabajo.cuadrilla_vigente(centro="Corte", maquina=cortadora)

        assert elegida.id == pegada.id

    def test_la_de_ayer_no_cuenta(self, gente):
        vieja = cuadrilla_de_hoy(gente=gente)
        Cuadrilla.objects.using(BASE).filter(pk=vieja.pk).update(
            fecha=timezone.localdate() - timedelta(days=1)
        )

        assert trabajo.cuadrilla_vigente(centro="Corte") is None

    def test_la_de_otro_centro_tampoco(self, gente):
        cuadrilla_de_hoy(centro="Pintura", gente=gente)

        assert trabajo.cuadrilla_vigente(centro="Corte") is None

    def test_la_jornada_completa_cubre_las_dos_mitades(self):
        manana = timezone.make_aware(
            timezone.datetime.combine(date(2026, 8, 4), timezone.datetime.min.time())
        ).replace(hour=9)
        tarde = manana.replace(hour=16)

        assert Cuadrilla.Turno.COMPLETO in trabajo.turnos_que_cubren(manana)
        assert Cuadrilla.Turno.COMPLETO in trabajo.turnos_que_cubren(tarde)
        assert Cuadrilla.Turno.MATUTINO in trabajo.turnos_que_cubren(manana)
        assert Cuadrilla.Turno.VESPERTINO in trabajo.turnos_que_cubren(tarde)


class TestElEquipoTieneQueSerDelArea:
    def test_una_cabina_de_pintura_no_sirve_para_cortar(self, pintadora):
        """Sin comprobarlo se podría anotar que una viga se cortó en la
        cabina de pintura, y el indicador por máquina sería mentira."""
        maquina, error = trabajo.maquina_valida(pintadora.id, etapa="Corte")

        assert maquina is None
        assert "no es de Corte" in error

    def test_una_dada_de_baja_tampoco(self, cortadora):
        Maquina.objects.using(BASE).filter(pk=cortadora.pk).update(activo=False)

        maquina, error = trabajo.maquina_valida(cortadora.id, etapa="Corte")

        assert maquina is None

    def test_texto_que_no_es_numero_no_revienta(self):
        maquina, error = trabajo.maquina_valida("ninguna", etapa="Corte")

        assert maquina is None
        assert error


class TestAlAvanzarUnaPieza:
    @pytest.fixture
    def cortador(self):
        from django.contrib.auth.models import Group

        from core import roles

        roles.asegurar_grupos()
        persona = Usuario.objects.create_user("luis", password="x")
        grupo, _ = Group.objects.get_or_create(name="corte")
        persona.groups.add(grupo)
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)
        return cliente

    def _avanzar(self, cliente, suelta, **extra):
        return cliente.post(
            reverse("produccion:viga_change_status_json", args=[suelta.pk]),
            {
                "estado_nuevo": "Corte",
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
                **extra,
            },
        )

    def test_sin_equipo_no_deja_entrar_a_corte(self, cortador, cortadora):
        """Sin esto la producción de los seis equipos queda en un solo
        montón: no se puede saber cuál va saturado ni cuál está parado.

        Hace falta que exista al menos un equipo: si no hay ninguno dado de
        alta, no se exige — ver el test de más abajo.
        """
        suelta = pieza("V-SIN-EQUIPO")

        respuesta = self._avanzar(cortador, suelta)

        assert respuesta.status_code == 400
        assert respuesta.json()["falta"] == "maquina"
        suelta.refresh_from_db()
        assert suelta.estado == "Espera de corte"

    def test_con_equipo_avanza_y_deja_apunte(self, cortador, cortadora, gente):
        cuadrilla = cuadrilla_de_hoy(gente=gente)
        suelta = pieza("V-CON-EQUIPO")

        respuesta = self._avanzar(cortador, suelta, maquina_id=cortadora.id)

        assert respuesta.status_code == 200
        apunte = ApunteDeTrabajo.objects.using(BASE).get(
            referencia=suelta.internal_id, etapa="Corte"
        )
        assert apunte.maquina_id == cortadora.id
        assert apunte.cuadrilla_id == cuadrilla.id
        assert apunte.actor == "luis"

    def test_un_equipo_de_otra_area_se_rechaza(self, cortador, pintadora):
        suelta = pieza("V-CABINA")

        respuesta = self._avanzar(cortador, suelta, maquina_id=pintadora.id)

        assert respuesta.status_code == 400
        suelta.refresh_from_db()
        assert suelta.estado == "Espera de corte"

    def test_las_etapas_sin_equipos_no_lo_piden(self, cortador):
        """En soldadura y pintura no hay seis máquinas intercambiables.
        Preguntarlo sería ruido en cada avance."""
        suelta = pieza("V-SIGUE", estado="Corte")

        respuesta = self._avanzar(
            cortador, suelta, estado_nuevo="Espera de armado"
        )

        assert respuesta.status_code == 200

    def test_sin_ningun_equipo_dado_de_alta_no_bloquea(self, cortador):
        """Un taller recién instalado no tiene máquinas capturadas. Si el
        requisito de medición se aplicara igual, no se podría mover una sola
        pieza: la exigencia habría parado la producción.
        """
        suelta = pieza("V-SIN-MAQUINAS")

        respuesta = self._avanzar(cortador, suelta)

        assert respuesta.status_code == 200
        suelta.refresh_from_db()
        assert suelta.estado == "Corte"

    def test_si_falla_el_apunte_no_avanza_la_pieza(self, cortador, cortadora, monkeypatch):
        """Van en la misma transacción. Un apunte sin su cambio de estado
        mediría trabajo que no ocurrió; un cambio sin apunte lo perdería."""
        def revienta(**kwargs):
            raise RuntimeError("sin base")

        monkeypatch.setattr("produccion.views.servicio_trabajo.anotar", revienta)
        suelta = pieza("V-ATOMICA")

        respuesta = self._avanzar(cortador, suelta, maquina_id=cortadora.id)

        assert respuesta.status_code == 500
        suelta.refresh_from_db()
        assert suelta.estado == "Espera de corte"
