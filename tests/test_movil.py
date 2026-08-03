"""«Mi trabajo»: la pantalla del operador en el celular.

Registrar que se terminó una etapa costaba de cinco a siete toques: abrir la
lista completa del taller —trescientas órdenes—, encontrar la propia, poner
una fecha, abrir un diálogo y guardar. En un teléfono, de pie, con guantes. En
la práctica no se hacía en el momento: se apuntaba en papel y alguien lo
capturaba por la tarde, y por eso el sistema iba siempre por detrás de la
realidad del piso.

Lo que hacía imposible arreglarlo es que **no existía ninguna relación entre
la cuenta con la que alguien inicia sesión y la ficha del colaborador al que
se le asigna el trabajo**. El sistema sabía a quién se asignó cada orden, pero
no sabía que esa persona era la que acababa de entrar. Sin eso no se puede
enseñar «lo mío», sólo «todo».
"""

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from produccion.movil import colaborador_de

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def equipo():
    from catalogos.models import EquipoTrabajo

    return EquipoTrabajo.objects.get_or_create(
        nombre="Equipo de pruebas", defaults={"area": "Soldadura", "integrantes": 3}
    )[0]


def colaborador(nombre="Juan Pérez", usuario="", rol="Soldador"):
    from catalogos.models import Colaborador

    return Colaborador.objects.create(
        nombre=nombre, rol=rol, equipo=equipo(), usuario=usuario, activo=True
    )


def pieza(estado="Soldadura", codigo="PRUEBA-1"):
    from produccion.models import Viga

    return Viga.objects.create(
        codigo_viga=codigo,
        pieza_no=1,
        total_piezas=1,
        proyecto="OBRA DE PRUEBA",
        descripcion="pieza",
        fecha_compromiso=timezone.localdate(),
        estado=estado,
        prioridad=3,
        peso_kg=100,
        fecha_creacion=timezone.now(),
        ultimo_cambio=timezone.now(),
    )


def asignar(persona, la_pieza, etapa="Soldadura"):
    from catalogos.models import VigaAsignacion

    return VigaAsignacion.objects.create(
        viga_internal_id=la_pieza.internal_id,
        etapa=etapa,
        rol="Soldador",
        colaborador=persona,
        vigente=True,
    )


def navegador(django_user_model, nombre="juan", grupo="soldadura"):
    """Un operador de piso: su cuenta y el grupo de su área.

    Sin el grupo, el servidor rechaza el cambio de etapa con un 403. Es la
    regla de siempre y está bien; lo que se ha añadido es que la pantalla lo
    diga en vez de enseñar un botón que va a fallar.
    """
    from django.contrib.auth.models import Group

    persona = django_user_model.objects.create_user(nombre, password="x")
    if grupo:
        persona.groups.add(Group.objects.get_or_create(name=grupo)[0])
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestSaberQuienEsQuienEntra:
    def test_encuentra_al_colaborador_por_la_cuenta_enlazada(self, django_user_model):
        persona = django_user_model.objects.create_user("jperez", password="x")
        ficha = colaborador(usuario="jperez")

        assert colaborador_de(persona) == ficha

    def test_no_distingue_mayusculas(self, django_user_model):
        persona = django_user_model.objects.create_user("JPerez", password="x")
        ficha = colaborador(usuario="jperez")

        assert colaborador_de(persona) == ficha

    def test_si_nadie_lo_capturo_lo_intenta_por_el_nombre(self, django_user_model):
        """Acertar el primer día sin configurar nada vale más que la exactitud.

        Aquí sólo decide qué órdenes se enseñan; para nada importante se
        usaría el enlace explícito.
        """
        persona = django_user_model.objects.create_user("Juan Pérez", password="x")
        ficha = colaborador(nombre="Juan Pérez")

        assert colaborador_de(persona) == ficha

    def test_un_colaborador_dado_de_baja_no_cuenta(self, django_user_model):
        persona = django_user_model.objects.create_user("jperez", password="x")
        ficha = colaborador(usuario="jperez")
        ficha.activo = False
        ficha.save()

        assert colaborador_de(persona) is None

    def test_sin_ficha_no_revienta(self, django_user_model):
        persona = django_user_model.objects.create_user("nadie", password="x")
        assert colaborador_de(persona) is None


class TestLaPantalla:
    def test_pide_sesion(self):
        respuesta = Client(SERVER_NAME="127.0.0.1").get(reverse("produccion:movil"))
        assert respuesta.status_code == 302

    def test_sin_ficha_lo_dice_en_vez_de_salir_vacia(self, django_user_model):
        """Una pantalla vacía sin explicación parece que el sistema falla."""
        respuesta = navegador(django_user_model, "sinficha").get(reverse("produccion:movil"))

        assert respuesta.status_code == 200
        assert respuesta.context["colaborador"] is None
        assert "todavía no está enlazada" in respuesta.content.decode()

    def test_solo_ensena_lo_asignado_a_esa_persona(self, django_user_model):
        cliente = navegador(django_user_model, "juan")
        yo = colaborador(usuario="juan")
        otro = colaborador(nombre="Otra persona", usuario="ana")
        mia = pieza(codigo="MIA-1")
        suya = pieza(codigo="SUYA-1")
        asignar(yo, mia)
        asignar(otro, suya)

        trabajos = cliente.get(reverse("produccion:movil")).context["trabajos"]

        assert [t["codigo"] for t in trabajos] == ["MIA-1"]

    def test_no_ensena_las_etapas_de_espera(self, django_user_model):
        """Una orden en espera no es trabajo de nadie todavía.

        Es la orden esperando a que alguien la tome. Enseñarla en «lo mío»
        sólo añade ruido a una pantalla que vive de tener poco.
        """
        cliente = navegador(django_user_model, "juan")
        yo = colaborador(usuario="juan")
        asignar(yo, pieza(estado="Espera de pintura", codigo="ESPERA-1"))
        asignar(yo, pieza(estado="Soldadura", codigo="ACTIVA-1"))

        trabajos = cliente.get(reverse("produccion:movil")).context["trabajos"]

        assert [t["codigo"] for t in trabajos] == ["ACTIVA-1"]

    def test_no_ensena_lo_terminado(self, django_user_model):
        cliente = navegador(django_user_model, "juan")
        yo = colaborador(usuario="juan")
        asignar(yo, pieza(estado="Terminado", codigo="LISTA-1"))

        assert cliente.get(reverse("produccion:movil")).context["trabajos"] == []

    def test_una_asignacion_retirada_no_cuenta(self, django_user_model):
        cliente = navegador(django_user_model, "juan")
        yo = colaborador(usuario="juan")
        asignacion = asignar(yo, pieza())
        asignacion.vigente = False
        asignacion.save()

        assert cliente.get(reverse("produccion:movil")).context["trabajos"] == []

    def test_dice_a_que_etapa_pasa(self, django_user_model):
        """El botón lleva el nombre de lo que la persona acaba de hacer."""
        cliente = navegador(django_user_model, "juan")
        asignar(colaborador(usuario="juan"), pieza(estado="Soldadura"))

        trabajo = cliente.get(reverse("produccion:movil")).context["trabajos"][0]

        assert trabajo["etapa"] == "Soldadura"
        assert trabajo["siguiente"] == "Espera de pintura"


class TestUnSoloToque:
    def test_el_boton_manda_todo_lo_que_hace_falta(self, django_user_model):
        """Sin campos que rellenar: ni fecha, ni etapa destino, ni comentario.

        La fecha de operación era obligatoria y la ponía el operador. Es un
        dato que no tiene por qué pensar —siempre es hoy— y era el origen de
        que la lista se comportara distinto según el ancho de la pantalla.
        """
        cliente = navegador(django_user_model, "juan")
        la_pieza = pieza(estado="Soldadura")
        asignar(colaborador(usuario="juan"), la_pieza)

        pagina = cliente.get(reverse("produccion:movil")).content.decode()

        assert 'name="estado_nuevo" value="Espera de pintura"' in pagina
        assert 'name="fecha_operacion"' in pagina
        # Ningún campo que el operador tenga que rellenar.
        assert "<select" not in pagina
        assert 'type="date"' not in pagina

    def test_el_avance_llega_al_servidor(self, django_user_model):
        """La comprobación que importa: que la pieza avanza de verdad."""
        from produccion.models import ProductionLog, Viga

        cliente = navegador(django_user_model, "juan")
        la_pieza = pieza(estado="Soldadura")
        asignar(colaborador(usuario="juan"), la_pieza)

        respuesta = cliente.post(
            reverse("produccion:viga_change_status_json", args=[la_pieza.internal_id]),
            {
                "estado_nuevo": "Espera de pintura",
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
            },
        )

        assert respuesta.status_code == 200
        assert respuesta.json()["ok"] is True
        la_pieza.refresh_from_db()
        assert la_pieza.estado == "Espera de pintura"
        assert ProductionLog.objects.filter(
            viga_internal_id=la_pieza.internal_id, estado_nuevo="Espera de pintura"
        ).exists()
        assert Viga.objects.count() == 1

    def test_repetir_el_mismo_avance_no_lo_cuenta_dos_veces(self, django_user_model):
        """La red del taller se cae: el celular reintenta.

        La protección de fondo la dará la clave de idempotencia del motor
        unificado. Mientras tanto vale que el cambio de etapa es idempotente
        por naturaleza: pedir dos veces «pasa a Espera de pintura» deja la
        pieza en esa etapa una sola vez.
        """
        cliente = navegador(django_user_model, "juan")
        la_pieza = pieza(estado="Soldadura")
        asignar(colaborador(usuario="juan"), la_pieza)
        datos = {
            "estado_nuevo": "Espera de pintura",
            "fecha_operacion": timezone.localdate().isoformat(),
            "comentario": "",
        }
        ruta = reverse("produccion:viga_change_status_json", args=[la_pieza.internal_id])

        cliente.post(ruta, datos)
        cliente.post(ruta, datos)

        la_pieza.refresh_from_db()
        assert la_pieza.estado == "Espera de pintura"


class TestSinElGrupoDelAreaSeExplica:
    def test_no_se_ensena_un_boton_que_va_a_ser_rechazado(self, django_user_model):
        """Un botón que falla sin decir por qué hace que dejen de usarla."""
        cliente = navegador(django_user_model, "juan", grupo=None)
        asignar(colaborador(usuario="juan"), pieza(estado="Soldadura"))

        respuesta = cliente.get(reverse("produccion:movil"))

        assert respuesta.context["trabajos"][0]["puede_mover"] is False
        assert "no está en el grupo del área" in respuesta.content.decode()

    def test_el_de_corte_no_puede_mover_soldadura(self, django_user_model):
        cliente = navegador(django_user_model, "juan", grupo="corte")
        asignar(colaborador(usuario="juan"), pieza(estado="Soldadura"))

        trabajo = cliente.get(reverse("produccion:movil")).context["trabajos"][0]

        assert trabajo["puede_mover"] is False

    def test_el_de_corte_si_puede_mover_corte(self, django_user_model):
        cliente = navegador(django_user_model, "juan", grupo="corte")
        asignar(colaborador(usuario="juan"), pieza(estado="Corte"), etapa="Corte")

        trabajo = cliente.get(reverse("produccion:movil")).context["trabajos"][0]

        assert trabajo["puede_mover"] is True
        assert trabajo["siguiente"] == "Espera de armado"


class TestElTallerPuedeEnlazarLasCuentasSolo:
    def test_el_formulario_de_colaborador_tiene_el_campo(self, django_user_model):
        from catalogos.views import ColaboradorForm

        assert "usuario" in ColaboradorForm().fields

    def test_la_puesta_en_marcha_avisa_de_lo_que_falta(self, django_user_model):
        from django.contrib.auth.models import Group

        persona = django_user_model.objects.create_user("jefa", password="x")
        persona.groups.add(Group.objects.get_or_create(name="admin_general")[0])
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)
        colaborador(usuario="")

        secciones = cliente.get(reverse("nucleo:configuracion")).context["secciones"]
        piso = next(s for s in secciones if s["titulo"] == "El celular del piso")

        assert piso["renglones"][0]["estado"] == "falta"
