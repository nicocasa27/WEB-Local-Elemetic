"""Que el taller pueda configurar el sistema sin depender de nadie.

Este software estuvo abandonado y quien lo hizo no está. Todo lo que se añada
ahora es configurable por datos, pero eso no vale nada si la única forma de
llegar a esos datos es un comando de consola. Estos tests vigilan las dos
cosas que lo hacían imposible y que se descubrieron al montar los módulos:

- los usuarios que administran no podían entrar al administrador de Django;
- las aplicaciones nuevas no tenían permisos, así que no se le podía dar
  acceso a nadie que no fuera superusuario.
"""

from io import StringIO

import pytest
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

APLICACIONES_NUEVAS = ["nucleo", "inventario", "costeo"]


def usuario(nombre="tzinti", grupo="admin_general", staff=False):
    persona = User.objects.create_user(nombre, password="x", is_staff=staff)
    if grupo:
        persona.groups.add(Group.objects.get_or_create(name=grupo)[0])
    return persona


def navegador(persona):
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestPantallaDePuestaEnMarcha:
    def test_pide_sesion(self):
        respuesta = Client(SERVER_NAME="127.0.0.1").get(reverse("nucleo:configuracion"))
        assert respuesta.status_code == 302

    def test_funciona_con_el_sistema_recien_instalado(self):
        """Sin sembrar nada: la pantalla es lo primero que se abre.

        Si reventara con la base vacía, sería inútil justo cuando más falta
        hace.
        """
        respuesta = navegador(usuario()).get(reverse("nucleo:configuracion"))
        assert respuesta.status_code == 200

    def test_dice_lo_que_falta(self):
        respuesta = navegador(usuario()).get(reverse("nucleo:configuracion"))
        assert respuesta.context["pendientes"] > 0

    def test_lo_sembrado_deja_de_aparecer_como_pendiente(self):
        antes = navegador(usuario("a")).get(reverse("nucleo:configuracion")).context[
            "pendientes"
        ]

        call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
        call_command("sembrar_inventario", verbosity=0, stdout=StringIO())

        despues = navegador(usuario("b")).get(reverse("nucleo:configuracion")).context[
            "pendientes"
        ]
        assert despues < antes

    def test_cada_renglon_lleva_a_donde_se_captura(self):
        """Una lista de pendientes sin el enlace obliga a adivinar la dirección."""
        respuesta = navegador(usuario()).get(reverse("nucleo:configuracion"))
        for seccion in respuesta.context["secciones"]:
            for renglon in seccion["renglones"]:
                assert renglon["enlace"].startswith("/admin/"), renglon["titulo"]

    def test_distingue_lo_que_bloquea_de_lo_que_no(self):
        """Sin tarifas el costeo da cero; sin proveedores funciona igual.

        Una lista que no distingue lo urgente de lo prescindible acaba
        ignorándose entera.
        """
        respuesta = navegador(usuario()).get(reverse("nucleo:configuracion"))
        estados = {
            renglon["titulo"]: renglon["estado"]
            for seccion in respuesta.context["secciones"]
            for renglon in seccion["renglones"]
        }
        assert estados["Centros con tarifa"] == "falta"
        assert estados["Proveedores"] == "opcional"

    def test_avisa_a_quien_todavia_no_puede_capturar(self):
        respuesta = navegador(usuario(staff=False)).get(reverse("nucleo:configuracion"))
        assert respuesta.context["puede_entrar_al_admin"] is False
        assert b"no puede entrar" in respuesta.content

    def test_ensena_el_estado_de_las_cuatro_lineas(self):
        call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
        respuesta = navegador(usuario()).get(reverse("nucleo:configuracion"))
        assert len(respuesta.context["migracion"]) == 4
        assert all(m["modo"] == "apagada" for m in respuesta.context["migracion"])


class TestHabilitarLaConfiguracion:
    def test_recrea_los_permisos_que_falten(self):
        """En la base del taller, los permisos de las aplicaciones nuevas no existían.

        Django los crea al migrar, pero en la base donde vive `auth`. Como el
        enrutador manda las aplicaciones nuevas a PostgreSQL y la
        autenticación sigue en SQLite, ahí no se crearon: la base de
        producción tenía cero. En una base de pruebas recién montada sí
        aparecen, así que para comprobar el arreglo hay que borrarlos primero
        y ver que el comando los repone.
        """
        Permission.objects.filter(
            content_type__app_label__in=APLICACIONES_NUEVAS
        ).delete()

        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())

        assert (
            Permission.objects.filter(
                content_type__app_label__in=APLICACIONES_NUEVAS
            ).count()
            > 0
        )

    def test_da_acceso_al_administrador_a_quien_administra(self):
        persona = usuario("tzinti", staff=False)

        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())

        persona.refresh_from_db()
        assert persona.is_staff, "el menú les enseñaba el enlace y el admin les rechazaba"
        assert persona.groups.filter(name="configuracion").exists()

    def test_no_les_da_acceso_a_usuarios_ni_contrasenas(self):
        """Quien captura una tarifa no tiene por qué poder crear cuentas."""
        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())
        grupo = Group.objects.get(name="configuracion")

        etiquetas = set(
            grupo.permissions.values_list("content_type__app_label", flat=True)
        )

        assert "auth" not in etiquetas
        assert etiquetas <= set(APLICACIONES_NUEVAS) | {"catalogos"}

    def test_no_toca_a_quien_no_administra(self):
        operador = usuario("juan", grupo="soldadura")
        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())
        operador.refresh_from_db()
        assert not operador.is_staff

    def test_se_puede_repetir_sin_efectos(self):
        usuario("tzinti")
        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())
        primera = Permission.objects.count()
        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())
        assert Permission.objects.count() == primera

    def test_se_puede_deshacer(self):
        persona = usuario("tzinti", staff=False)
        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())

        call_command("habilitar_configuracion", "--quitar", verbosity=0, stdout=StringIO())

        persona.refresh_from_db()
        assert not persona.is_staff
        assert not persona.groups.filter(name="configuracion").exists()

    def test_deshacer_no_deja_fuera_a_un_superusuario(self):
        """Quitarle is_staff al superusuario dejaría a todos fuera sin remedio."""
        jefe = User.objects.create_superuser("jefe", password="x")
        jefe.groups.add(Group.objects.get_or_create(name="admin_general")[0])
        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())

        call_command("habilitar_configuracion", "--quitar", verbosity=0, stdout=StringIO())

        jefe.refresh_from_db()
        assert jefe.is_staff

    def test_simular_no_escribe(self):
        persona = usuario("tzinti", staff=False)
        call_command("habilitar_configuracion", "--simular", verbosity=0, stdout=StringIO())
        persona.refresh_from_db()
        assert not persona.is_staff


class TestAccesoRealAlAdministrador:
    """La comprobación que de verdad importa: que las pantallas abran."""

    @pytest.fixture
    def configurador(self):
        persona = usuario("tzinti", staff=False)
        call_command("habilitar_configuracion", verbosity=0, stdout=StringIO())
        persona.refresh_from_db()
        return navegador(persona)

    @pytest.mark.parametrize(
        "ruta",
        [
            "/admin/",
            "/admin/nucleo/etapa/",
            "/admin/nucleo/transicionpermitida/",
            "/admin/nucleo/motivoevento/",
            "/admin/inventario/material/",
            "/admin/inventario/lotematerial/",
            "/admin/costeo/centrocosto/",
            "/admin/costeo/tiempoestandar/",
        ],
    )
    def test_puede_abrir_las_pantallas_de_configuracion(self, configurador, ruta):
        assert configurador.get(ruta).status_code == 200

    @pytest.mark.parametrize("ruta", ["/admin/auth/user/", "/admin/auth/group/"])
    def test_no_puede_tocar_cuentas(self, configurador, ruta):
        assert configurador.get(ruta).status_code == 403

    def test_el_historial_no_se_puede_editar(self, configurador):
        """Un registro que se puede editar deja de ser un registro."""
        assert configurador.get("/admin/nucleo/eventoproduccion/add/").status_code == 403
        assert (
            configurador.get("/admin/inventario/movimientomaterial/add/").status_code == 403
        )
