"""Pintura como área propia.

El grupo «soldadura» cubría armado, soldadura, pintura y terminado, porque
nadie había preguntado si en el taller eran la misma gente. No lo son. Con el
reparto viejo, un soldador podía dar una pieza por terminada sin que hubiera
pasado por pintura, y el sistema lo daba por bueno.

Lo delicado del cambio no es partir el grupo: es que **el día del despliegue
nadie está todavía en el grupo nuevo**. Si soldadura pierde pintura de golpe,
las piezas en pintura dejan de poder avanzar y el síntoma —«el sistema ya no
me deja»— aparece tres días después, sin que nadie lo relacione con el
cambio. Por eso hay una red: mientras no exista ninguna cuenta de pintura,
soldadura sigue cubriéndola.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from produccion.views import _etapas_permitidas

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def cuenta(django_user_model, nombre, *grupos):
    persona = django_user_model.objects.create_user(nombre, password="x")
    for grupo in grupos:
        persona.groups.add(Group.objects.get_or_create(name=grupo)[0])
    return persona


def navegador(persona):
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


def pieza(estado):
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


def avanzar(cliente, la_pieza, destino):
    return cliente.post(
        reverse("produccion:viga_change_status_json", args=[la_pieza.internal_id]),
        {
            "estado_nuevo": destino,
            "fecha_operacion": timezone.localdate().isoformat(),
            "comentario": "",
        },
    )


class TestElRepartoSeparado:
    def test_el_pintor_puede_pintar(self, django_user_model):
        cliente = navegador(cuenta(django_user_model, "diana", "pintura"))
        la_pieza = pieza("Espera de pintura")

        assert avanzar(cliente, la_pieza, "Pintura").status_code == 200

    def test_y_dar_por_terminada(self, django_user_model):
        cliente = navegador(cuenta(django_user_model, "diana", "pintura"))
        la_pieza = pieza("Pintura")

        assert avanzar(cliente, la_pieza, "Terminado").status_code == 200

    def test_el_pintor_no_suelda(self, django_user_model):
        cliente = navegador(cuenta(django_user_model, "diana", "pintura"))
        la_pieza = pieza("Espera de soldadura")

        assert avanzar(cliente, la_pieza, "Soldadura").status_code == 403

    def test_el_soldador_deja_la_pieza_en_espera_de_pintura(self, django_user_model):
        """El solape en la etapa de espera es a propósito: es el punto de
        entrega entre las dos áreas y las dos tienen que poder tocarlo."""
        cuenta(django_user_model, "diana", "pintura")
        cliente = navegador(cuenta(django_user_model, "juan", "soldadura"))
        la_pieza = pieza("Soldadura")

        assert avanzar(cliente, la_pieza, "Espera de pintura").status_code == 200

    def test_pero_ya_no_la_pinta(self, django_user_model):
        cuenta(django_user_model, "diana", "pintura")
        cliente = navegador(cuenta(django_user_model, "juan", "soldadura"))
        la_pieza = pieza("Espera de pintura")

        assert avanzar(cliente, la_pieza, "Pintura").status_code == 403

    def test_ni_la_da_por_terminada_sin_pintar(self, django_user_model):
        """Éste es el agujero que se cierra."""
        cuenta(django_user_model, "diana", "pintura")
        cliente = navegador(cuenta(django_user_model, "juan", "soldadura"))
        la_pieza = pieza("Pintura")

        assert avanzar(cliente, la_pieza, "Terminado").status_code == 403


class TestLaRedDeSeguridad:
    """Sin nadie en el grupo de pintura, nada cambia."""

    def test_sin_pintores_el_soldador_sigue_pintando(self, django_user_model):
        cliente = navegador(cuenta(django_user_model, "juan", "soldadura"))
        la_pieza = pieza("Espera de pintura")

        assert avanzar(cliente, la_pieza, "Pintura").status_code == 200

    def test_en_cuanto_hay_un_pintor_se_separa(self, django_user_model):
        soldador = cuenta(django_user_model, "juan", "soldadura")

        antes = _etapas_permitidas(soldador)
        cuenta(django_user_model, "diana", "pintura")
        despues = _etapas_permitidas(soldador)

        assert "Pintura" in antes
        assert "Pintura" not in despues
        assert "Soldadura" in despues

    def test_un_grupo_vacio_no_cuenta(self, django_user_model):
        """Crear el grupo no basta: tiene que haber alguien dentro. Si contara
        el grupo vacío, `asegurar_grupos` dispararía el corte solo."""
        Group.objects.get_or_create(name="pintura")
        soldador = cuenta(django_user_model, "juan", "soldadura")

        assert "Pintura" in _etapas_permitidas(soldador)


class TestLaColaDelCelularSigueAlServidor:
    def test_el_pintor_solo_ve_pintura(self, django_user_model):
        cliente = navegador(cuenta(django_user_model, "diana", "pintura"))
        pieza("Espera de pintura")
        pieza("Soldadura")
        pieza("Corte")

        trabajos = cliente.get(reverse("produccion:movil")).context["trabajos"]

        assert [t["etapa"] for t in trabajos] == ["Espera de pintura"]

    def test_el_soldador_ya_no_ve_pintura(self, django_user_model):
        cuenta(django_user_model, "diana", "pintura")
        cliente = navegador(cuenta(django_user_model, "juan", "soldadura"))
        pieza("Pintura")
        pieza("Soldadura")

        trabajos = cliente.get(reverse("produccion:movil")).context["trabajos"]

        assert [t["etapa"] for t in trabajos] == ["Soldadura"]

    def test_terminado_no_ocupa_sitio_en_la_cola(self, django_user_model):
        """El grupo de pintura puede poner una pieza en «Terminado», pero una
        pieza terminada ya no es trabajo de nadie."""
        cliente = navegador(cuenta(django_user_model, "diana", "pintura"))
        pieza("Terminado")

        assert cliente.get(reverse("produccion:movil")).context["trabajos"] == []


class TestElComandoQueRepartLasCuentasQueYaExisten:
    def _ficha(self, nombre, usuario, rol, area="Pintura"):
        from catalogos.models import Colaborador, EquipoTrabajo

        equipo, _ = EquipoTrabajo.objects.get_or_create(
            nombre=f"Cuadrilla {area}", defaults={"area": area, "integrantes": 3}
        )
        return Colaborador.objects.create(
            nombre=nombre, rol=rol, equipo=equipo, usuario=usuario, activo=True
        )

    def test_mueve_a_los_pintores(self, django_user_model):
        from io import StringIO

        from django.core.management import call_command

        persona = cuenta(django_user_model, "diana", "soldadura")
        self._ficha("Diana Sosa", "diana", "Pintor")

        call_command("separar_pintura", stdout=StringIO())

        grupos = set(persona.groups.values_list("name", flat=True))
        assert grupos == {"pintura"}

    def test_tambien_por_el_area_del_equipo(self, django_user_model):
        """Un auxiliar de la cuadrilla de pintura es de pintura, aunque su rol
        en la ficha no diga «Pintor»."""
        from io import StringIO

        from django.core.management import call_command

        persona = cuenta(django_user_model, "omar", "soldadura")
        self._ficha("Omar Cimé", "omar", "Auxiliar", area="Pintura")

        call_command("separar_pintura", stdout=StringIO())

        assert "pintura" in set(persona.groups.values_list("name", flat=True))

    def test_no_toca_a_los_soldadores(self, django_user_model):
        from io import StringIO

        from django.core.management import call_command

        persona = cuenta(django_user_model, "juan", "soldadura")
        self._ficha("Juan Pérez", "juan", "Soldador", area="Soldadura")

        call_command("separar_pintura", stdout=StringIO())

        assert set(persona.groups.values_list("name", flat=True)) == {"soldadura"}

    def test_el_ensayo_no_escribe_nada(self, django_user_model):
        from io import StringIO

        from django.core.management import call_command

        persona = cuenta(django_user_model, "diana", "soldadura")
        self._ficha("Diana Sosa", "diana", "Pintor")

        salida = StringIO()
        call_command("separar_pintura", "--ensayo", stdout=salida)

        assert "Ensayo" in salida.getvalue()
        assert set(persona.groups.values_list("name", flat=True)) == {"soldadura"}

    def test_quien_pinta_y_suelda_se_queda_en_los_dos(self, django_user_model):
        from io import StringIO

        from django.core.management import call_command

        persona = cuenta(django_user_model, "diana", "soldadura")
        self._ficha("Diana Sosa", "diana", "Pintor")

        call_command("separar_pintura", "--dejar-en-soldadura", stdout=StringIO())

        assert set(persona.groups.values_list("name", flat=True)) == {
            "soldadura",
            "pintura",
        }

    def test_sin_pintores_lo_dice_y_no_rompe_nada(self, django_user_model):
        from io import StringIO

        from django.core.management import call_command

        salida = StringIO()
        call_command("separar_pintura", stdout=salida)

        assert "Ninguna ficha activa" in salida.getvalue()

    def test_una_ficha_que_apunta_a_una_cuenta_que_no_existe_se_avisa(self, django_user_model):
        from io import StringIO

        from django.core.management import call_command

        self._ficha("Fantasma", "nadie", "Pintor")

        salida = StringIO()
        call_command("separar_pintura", stdout=salida)

        assert "no es ninguna cuenta" in salida.getvalue()
