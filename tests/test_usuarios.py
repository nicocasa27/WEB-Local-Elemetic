"""Alta y modificación de usuarios, y quién puede hacerla.

Dos agujeros que venían de no tener pantalla:

**Nadie del piso tenía cuenta.** Los once usuarios del sistema son de oficina.
Crear una significaba entrar al admin de Django y elegir entre once grupos con
nombre técnico —«corte_laser_supervision»— sin ninguna pista de qué abría cada
uno. El resultado práctico: los movimientos los captura un supervisor, así que
la trazabilidad dice quién *capturó*, no quién *hizo*, y la pantalla «Mi
trabajo» del celular no la puede abrir nadie.

**No había un grupo de almacén.** El taller pidió que quien produce no pueda
confirmar la entrega de material. Sin un grupo aparte, esa regla no se puede
escribir: sería el operador diciendo que recibió lo que él mismo pidió.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from catalogos.management.commands.crear_admin import USUARIO as USUARIO_ADMIN
from catalogos.models import Colaborador, EquipoTrabajo
from core import roles
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

Usuario = get_user_model()


@pytest.fixture
def grupos():
    roles.asegurar_grupos()


@pytest.fixture
def jefa(grupos):
    persona = Usuario.objects.create_user("jefa", password="x")
    persona.groups.add(Group.objects.get(name="admin_general"))
    return persona


@pytest.fixture
def navegador(jefa):
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(jefa)
    return cliente


@pytest.fixture
def colaborador():
    equipo = EquipoTrabajo.objects.using(BASE).create(
        nombre="Cuadrilla A", area="Soldadura", integrantes=0
    )
    return Colaborador.objects.using(BASE).create(
        nombre="Juan Pérez", rol="Soldador", equipo=equipo
    )


class TestSoloAdministraQuienDebe:
    def test_un_operador_no_entra_a_usuarios(self, grupos):
        operador = Usuario.objects.create_user("cortador", password="x")
        operador.groups.add(Group.objects.get(name="corte"))
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(operador)

        assert cliente.get(reverse("catalogos:usuarios")).status_code == 302

    def test_un_administrador_si(self, navegador):
        assert navegador.get(reverse("catalogos:usuarios")).status_code == 200

    def test_sin_sesion_tampoco(self):
        cliente = Client(SERVER_NAME="127.0.0.1")
        assert cliente.get(reverse("catalogos:usuarios")).status_code == 302

    def test_apagar_una_cuenta_exige_post(self, navegador, jefa):
        otra = Usuario.objects.create_user("otra", password="x")
        # Con GET no pasa nada: un enlace no puede apagar a nadie.
        assert navegador.get(
            reverse("catalogos:usuario_apagar", args=[otra.pk])
        ).status_code == 405
        otra.refresh_from_db()
        assert otra.is_active is True


class TestCrearUnaCuenta:
    def _datos(self, **extra):
        datos = {
            "username": "jperez",
            "first_name": "Juan",
            "last_name": "Pérez",
            "email": "",
            "is_active": "on",
            "grupos": ["soldadura"],
            "colaborador": "",
            "contrasena": "taller2026",
            "repetida": "taller2026",
        }
        datos.update(extra)
        return datos

    def test_se_crea_y_puede_entrar(self, navegador):
        navegador.post(reverse("catalogos:usuario_crear"), self._datos())

        persona = Usuario.objects.get(username="jperez")
        assert persona.check_password("taller2026")
        assert persona.is_active is True

    def test_recibe_sus_permisos(self, navegador):
        navegador.post(reverse("catalogos:usuario_crear"), self._datos())

        persona = Usuario.objects.get(username="jperez")
        assert list(persona.groups.values_list("name", flat=True)) == ["soldadura"]

    def test_se_enlaza_con_su_ficha_del_taller(self, navegador, colaborador):
        """Sin el enlace, el sistema sabe que entró «jperez» pero no que
        jperez es Juan Pérez del equipo de soldadura, y «Mi trabajo» no le
        puede enseñar sus órdenes."""
        navegador.post(
            reverse("catalogos:usuario_crear"),
            self._datos(colaborador=str(colaborador.pk)),
        )

        colaborador.refresh_from_db()
        assert colaborador.usuario == "jperez"

    def test_una_ficha_no_queda_enlazada_a_dos_cuentas(self, navegador, colaborador):
        """Si dos fichas apuntaran al mismo usuario, «Mi trabajo» le enseñaría
        las órdenes de otro."""
        otra = Colaborador.objects.using(BASE).create(
            nombre="Homónimo", rol="Auxiliar", equipo=colaborador.equipo, usuario="jperez"
        )

        navegador.post(
            reverse("catalogos:usuario_crear"),
            self._datos(colaborador=str(colaborador.pk)),
        )

        otra.refresh_from_db()
        colaborador.refresh_from_db()
        assert otra.usuario == ""
        assert colaborador.usuario == "jperez"

    def test_las_contrasenas_tienen_que_coincidir(self, navegador):
        navegador.post(
            reverse("catalogos:usuario_crear"),
            self._datos(repetida="otra-cosa"),
        )
        assert not Usuario.objects.filter(username="jperez").exists()

    def test_no_se_admite_una_contrasena_de_tres_letras(self, navegador):
        navegador.post(
            reverse("catalogos:usuario_crear"),
            self._datos(contrasena="abc", repetida="abc"),
        )
        assert not Usuario.objects.filter(username="jperez").exists()

    def test_quien_no_administra_no_abre_el_admin_de_django(self, navegador):
        """`is_staff` da acceso al admin de Django, que enseña las tablas en
        crudo. Un soldador no tiene por qué verlas."""
        navegador.post(reverse("catalogos:usuario_crear"), self._datos())

        assert Usuario.objects.get(username="jperez").is_staff is False

    def test_quien_administra_si(self, navegador):
        navegador.post(
            reverse("catalogos:usuario_crear"),
            self._datos(username="otrajefa", grupos=["admin_general"]),
        )

        assert Usuario.objects.get(username="otrajefa").is_staff is True


class TestModificar:
    def test_se_cambian_los_permisos(self, navegador, colaborador):
        persona = Usuario.objects.create_user("cambiante", password="x")
        persona.groups.add(Group.objects.get(name="corte"))

        navegador.post(reverse("catalogos:usuario_editar", args=[persona.pk]), {
            "username": "cambiante", "first_name": "", "last_name": "", "email": "",
            "is_active": "on", "grupos": ["soldadura", "almacen"], "colaborador": "",
        })

        assert set(persona.groups.values_list("name", flat=True)) == {"soldadura", "almacen"}

    def test_se_cambia_la_contrasena(self, navegador):
        persona = Usuario.objects.create_user("olvidadiza", password="vieja")

        navegador.post(reverse("catalogos:usuario_contrasena", args=[persona.pk]), {
            "contrasena": "nueva-2026", "repetida": "nueva-2026",
        })

        persona.refresh_from_db()
        assert persona.check_password("nueva-2026")

    def test_apagar_no_borra(self, navegador):
        """Borrar la cuenta dejaría sin autor los movimientos que registró, y
        el historial dejaría de poder explicarse."""
        persona = Usuario.objects.create_user("saliente", password="x")

        navegador.post(reverse("catalogos:usuario_apagar", args=[persona.pk]))

        persona.refresh_from_db()
        assert persona.is_active is False
        assert Usuario.objects.filter(username="saliente").exists()

    def test_no_puedo_apagarme_a_mi_misma(self, navegador, jefa):
        navegador.post(reverse("catalogos:usuario_apagar", args=[jefa.pk]))

        jefa.refresh_from_db()
        assert jefa.is_active is True


class TestElAdministradorFijo:
    """Es la entrada de respaldo del taller. No se puede cerrar por descuido."""

    @pytest.fixture
    def admin_creado(self, grupos):
        from django.core.management import call_command
        from io import StringIO

        call_command("crear_admin", verbosity=0, stdout=StringIO())
        return Usuario.objects.get(username=USUARIO_ADMIN)

    def test_se_crea_con_todos_los_permisos(self, admin_creado):
        assert admin_creado.is_superuser is True
        assert admin_creado.is_active is True

    def test_correrlo_dos_veces_no_duplica(self, admin_creado):
        from django.core.management import call_command
        from io import StringIO

        call_command("crear_admin", verbosity=0, stdout=StringIO())
        assert Usuario.objects.filter(username=USUARIO_ADMIN).count() == 1

    def test_no_pisa_una_contrasena_ya_cambiada(self, admin_creado):
        """Sin `--restablecer` no se toca: si el taller la cambió a propósito,
        volver a correr el comando no puede devolverla a la de fábrica."""
        from django.core.management import call_command
        from io import StringIO

        admin_creado.set_password("la-que-puso-el-taller")
        admin_creado.save()

        call_command("crear_admin", verbosity=0, stdout=StringIO())

        admin_creado.refresh_from_db()
        assert admin_creado.check_password("la-que-puso-el-taller")

    def test_restablecer_la_devuelve(self, admin_creado):
        from django.core.management import call_command
        from io import StringIO
        from catalogos.management.commands.crear_admin import CONTRASENA_DE_FABRICA

        admin_creado.set_password("otra")
        admin_creado.is_active = False
        admin_creado.save()

        call_command("crear_admin", restablecer=True, verbosity=0, stdout=StringIO())

        admin_creado.refresh_from_db()
        assert admin_creado.check_password(CONTRASENA_DE_FABRICA)
        assert admin_creado.is_active is True

    def test_no_se_puede_apagar(self, navegador, admin_creado):
        navegador.post(reverse("catalogos:usuario_apagar", args=[admin_creado.pk]))

        admin_creado.refresh_from_db()
        assert admin_creado.is_active is True

    def test_no_se_le_cambia_el_usuario(self, navegador, admin_creado):
        """Si se le cambiara el nombre, `crear_admin` crearía otro la próxima
        vez y habría dos administradores fijos."""
        navegador.post(reverse("catalogos:usuario_editar", args=[admin_creado.pk]), {
            "username": "otro-nombre", "first_name": "", "last_name": "", "email": "",
            "is_active": "on", "grupos": ["admin_general"], "colaborador": "",
        })

        admin_creado.refresh_from_db()
        assert admin_creado.username == USUARIO_ADMIN


class TestLosPapeles:
    def test_existe_el_grupo_de_almacen(self, grupos):
        """El taller pidió que quien produce no confirme entregas. Sin un
        grupo aparte, esa regla no se puede escribir."""
        assert Group.objects.filter(name=roles.ALMACEN).exists()

    def test_un_operador_no_puede_entregar_material(self, grupos):
        operador = Usuario.objects.create_user("op", password="x")
        operador.groups.add(Group.objects.get(name="soldadura"))

        assert roles.puede_entregar_material(operador) is False

    def test_el_almacenista_si(self, grupos):
        almacenista = Usuario.objects.create_user("almacen1", password="x")
        almacenista.groups.add(Group.objects.get(name=roles.ALMACEN))

        assert roles.puede_entregar_material(almacenista) is True

    def test_asegurar_grupos_es_idempotente(self, grupos):
        assert roles.asegurar_grupos() == []

    def test_cada_papel_esta_explicado(self):
        """La lista se enseña en pantalla: un rol sin descripción es un
        casillero que nadie sabe si marcar."""
        sin_explicar = [r["clave"] for r in roles.ROLES if not r.get("descripcion")]
        assert not sin_explicar


class TestUnRolNuevoNoSePierdeEnSilencio:
    """`groups.set()` con un `filter` descarta lo que no existe, sin avisar.

    Un rol nuevo no existe en la base del taller hasta que alguien corre un
    comando. «Pintura» fue el último: un administrador lo marcaba, guardaba
    sin ningún error, y el rol no se aplicaba. El único síntoma habría sido
    que a esa persona el sistema no la deja trabajar, días después y sin
    relación aparente con el formulario que se guardó.
    """

    def test_se_crea_el_grupo_que_falta_al_asignarlo(self, django_user_model):
        from django.contrib.auth.models import Group

        from catalogos.usuarios import _aplicar_grupos

        Group.objects.filter(name="pintura").delete()
        persona = django_user_model.objects.create_user("diana", password="x")

        _aplicar_grupos(persona, ["pintura"])

        assert set(persona.groups.values_list("name", flat=True)) == {"pintura"}

    def test_no_borra_los_grupos_que_ya_estaban(self, django_user_model):
        from django.contrib.auth.models import Group

        from catalogos.usuarios import _aplicar_grupos

        Group.objects.get_or_create(name="corte")
        persona = django_user_model.objects.create_user("juan", password="x")

        _aplicar_grupos(persona, ["corte"])

        assert Group.objects.filter(name="corte").count() == 1

    def test_todos_los_roles_de_la_lista_se_pueden_asignar(self, django_user_model):
        """Si alguien añade un rol y olvida crearlo, esto lo detecta."""
        from catalogos.usuarios import _aplicar_grupos
        from core import roles

        persona = django_user_model.objects.create_user("todos", password="x")
        claves = [r["clave"] for r in roles.ROLES]

        _aplicar_grupos(persona, claves)

        assert set(persona.groups.values_list("name", flat=True)) == set(claves)
