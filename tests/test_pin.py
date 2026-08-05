"""Entrar con cuatro dígitos desde la tableta del piso.

En el taller hay gente que no teclea un correo y una contraseña de ocho
caracteres de pie, con guantes, delante de una tableta compartida. Eso acababa
de una de dos maneras, y las dos rompen lo mismo:

- No entraban, y el avance se apuntaba en papel para que alguien de oficina lo
  capturara por la tarde. Por eso el sistema iba siempre por detrás del piso.
- O alguien dejaba su sesión abierta y todo el turno quedaba registrado a su
  nombre. El dato de quién hizo qué, que es con el que se mide el rendimiento,
  quedaba mal sin que nada lo indicara.

Lo que estas pruebas fijan, además del caso feliz, son las tres reglas que
hacen que el PIN no se convierta en un agujero: sólo abre cuentas de piso, dos
personas no pueden compartirlo, y la sesión de la tableta se cierra sola.
"""

import time

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from acceso import servicios
from acceso.models import Pin
from acceso.views import CLAVE_SESION, CLAVE_VISTO
from core import roles

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def cuenta(django_user_model, nombre, grupos=(), **extra):
    usuario = django_user_model.objects.create_user(
        username=nombre, password="prueba", **extra
    )
    for grupo in grupos:
        usuario.groups.add(Group.objects.get_or_create(name=grupo)[0])
    return usuario


def soldador(django_user_model, nombre="zz_soldador", pin="1234"):
    usuario = cuenta(django_user_model, nombre, ["soldadura"])
    if pin:
        Pin.objects.create(usuario=usuario, digitos=pin)
    return usuario


# ------------------------------------------------------ el caso de todos los días


class TestElOperadorEntraConCuatroDigitos:
    def test_teclear_el_pin_lo_deja_en_su_trabajo(self, client, django_user_model):
        soldador(django_user_model, pin="1234")

        respuesta = client.post(reverse("acceso:entrar"), {"pin": "1234"})

        assert respuesta.status_code == 302
        assert respuesta.url == reverse("produccion:movil")
        assert client.session["_auth_user_id"]

    def test_el_teclado_se_abre_sin_haber_entrado(self, client):
        """Es la puerta. Pedir sesión para llegar a ella no tendría sentido."""
        respuesta = client.get(reverse("acceso:teclado"))

        assert respuesta.status_code == 200
        assert "PIN" in respuesta.content.decode()

    def test_los_espacios_y_los_guiones_no_estorban(self, client, django_user_model):
        """Se teclea en una pantalla táctil con guantes: se limpia lo que llegue."""
        soldador(django_user_model, pin="4321")

        respuesta = client.post(reverse("acceso:entrar"), {"pin": " 43-21 "})

        assert respuesta.status_code == 302

    def test_un_pin_que_no_es_de_nadie_lo_dice_y_no_abre(self, client, django_user_model):
        soldador(django_user_model, pin="1234")

        respuesta = client.post(reverse("acceso:entrar"), {"pin": "9999"})

        assert respuesta.status_code == 200
        assert "no es de nadie" in respuesta.content.decode()
        assert "_auth_user_id" not in client.session

    def test_el_error_se_queda_escrito_en_la_pantalla(self, client, django_user_model):
        """Y no como aviso flotante, que se va a los dos segundos.

        A un brazo de distancia y con guantes, un aviso que desaparece solo es
        un aviso que no se leyó. Es lo único que esa pantalla tiene que decir.
        """
        respuesta = client.post(reverse("acceso:entrar"), {"pin": "0001"})

        cuerpo = respuesta.content.decode()
        assert "pin-error" in cuerpo


# ------------------------------------------------------ quién puede tener PIN


class TestElPinNoAbreLaAdministracion:
    """Cuatro dígitos son diez mil combinaciones.

    Eso no puede ser lo único que separe a cualquiera de la cuenta que da de
    alta usuarios, borra máquinas o cierra órdenes. Quien administra entra con
    su usuario y su contraseña, desde una PC.
    """

    def test_una_cuenta_de_administracion_no_admite_pin(self, django_user_model):
        jefe = cuenta(django_user_model, "zz_jefe", ["admin_general"])

        pin, error = servicios.asignar(jefe, "1234")

        assert pin is None
        assert "usuario y contraseña" in error

    def test_un_superusuario_tampoco(self, django_user_model):
        raiz = cuenta(django_user_model, "zz_raiz", ["soldadura"], is_superuser=True)

        pin, error = servicios.asignar(raiz, "1234")

        assert pin is None

    def test_una_cuenta_de_oficina_sin_area_tampoco(self, django_user_model):
        ventas = cuenta(django_user_model, "zz_ventas", ["pedidos_ventas"])

        pin, error = servicios.asignar(ventas, "1234")

        assert pin is None
        assert "para el piso" in error.lower()

    def test_pasar_a_alguien_a_administracion_le_apaga_el_pin_solo(
        self, client, django_user_model
    ):
        """Sin que nadie tenga que acordarse de borrárselo.

        Es el caso que convierte una regla en un agujero: se asciende a un
        soldador, se le dan permisos de administración, y su PIN de cuatro
        dígitos sigue abriendo, ahora con todo lo que puede hacer el nuevo rol.
        """
        persona = soldador(django_user_model, pin="1234")
        persona.groups.add(Group.objects.get_or_create(name="admin_general")[0])

        assert servicios.quien_es("1234") is None

        respuesta = client.post(reverse("acceso:entrar"), {"pin": "1234"})
        assert "_auth_user_id" not in client.session
        assert respuesta.status_code == 200

    def test_apagar_la_cuenta_apaga_el_pin(self, django_user_model):
        persona = soldador(django_user_model, pin="1234")
        persona.is_active = False
        persona.save()

        assert servicios.quien_es("1234") is None


# ------------------------------------------------------------ el PIN es único


class TestDosPersonasNoPuedenCompartirPin:
    """Si dos personas tienen el 1234, el trabajo queda a nombre de cualquiera.

    Y el error no da ningún síntoma hasta que alguien revisa el rendimiento del
    mes, cuando ya no se puede separar.
    """

    def test_no_se_deja_poner_uno_ocupado(self, django_user_model):
        soldador(django_user_model, "zz_uno", pin="1234")
        otro = cuenta(django_user_model, "zz_dos", ["corte"])

        pin, error = servicios.asignar(otro, "1234")

        assert pin is None
        assert "ya es de" in error

    def test_se_dice_de_quién_es(self, django_user_model):
        """Para que quien lo pone elija otro sin tener que ir a buscarlo."""
        dueno = soldador(django_user_model, "zz_uno", pin="1234")
        dueno.first_name = "Juan"
        dueno.last_name = "Pérez"
        dueno.save()
        otro = cuenta(django_user_model, "zz_dos", ["corte"])

        _, error = servicios.asignar(otro, "1234")

        assert "Juan Pérez" in error

    def test_cambiarse_el_propio_pin_al_mismo_no_es_un_choque(self, django_user_model):
        persona = soldador(django_user_model, pin="1234")

        pin, error = servicios.asignar(persona, "1234")

        assert error is None
        assert pin.digitos == "1234"

    def test_una_cuenta_apagada_sigue_ocupando_su_pin(self, django_user_model):
        """A propósito.

        Si alguien se va y otro hereda su PIN, el trabajo del mes pasado y el
        de éste quedan bajo el mismo número y ya no se pueden separar. Para
        liberarlo hay que quitárselo, que es una decisión y no un descuido.
        """
        ido = soldador(django_user_model, "zz_ido", pin="1234")
        ido.is_active = False
        ido.save()
        nuevo = cuenta(django_user_model, "zz_nuevo", ["soldadura"])

        pin, error = servicios.asignar(nuevo, "1234")

        assert pin is None

    def test_el_pin_libre_que_propone_no_está_tomado(self, django_user_model):
        soldador(django_user_model, "zz_uno", pin="1234")

        propuesto = servicios.libre()

        assert len(propuesto) == servicios.LARGO
        assert propuesto != "1234"


class TestElFormatoDelPin:
    def test_tienen_que_ser_cuatro(self, django_user_model):
        persona = cuenta(django_user_model, "zz_p", ["soldadura"])

        assert servicios.asignar(persona, "123")[1]
        assert servicios.asignar(persona, "12345")[1]
        assert servicios.asignar(persona, "")[1]

    def test_el_1234_se_admite(self, django_user_model):
        """No es un secreto: es un gafete.

        Obligar a que sea difícil de adivinar no compra nada aquí —cualquier
        compañero lo puede ver— y sí cuesta: un PIN raro se acaba escribiendo
        en un papel pegado a la tableta.
        """
        persona = cuenta(django_user_model, "zz_p", ["soldadura"])

        pin, error = servicios.asignar(persona, "1234")

        assert error is None


# --------------------------------------------------- la tableta es de todos


class TestLaTabletaEsCompartida:
    def test_entrar_cierra_la_sesión_del_anterior(self, client, django_user_model):
        """Lo que impide que el segundo apunte su trabajo a nombre del primero."""
        primero = soldador(django_user_model, "zz_primero", pin="1111")
        segundo = soldador(django_user_model, "zz_segundo", pin="2222")

        client.post(reverse("acceso:entrar"), {"pin": "1111"})
        assert int(client.session["_auth_user_id"]) == primero.pk

        client.post(reverse("acceso:entrar"), {"pin": "2222"})
        assert int(client.session["_auth_user_id"]) == segundo.pk

    def test_el_botón_de_terminar_cierra_y_deja_el_teclado(
        self, client, django_user_model
    ):
        soldador(django_user_model, pin="1234")
        client.post(reverse("acceso:entrar"), {"pin": "1234"})

        respuesta = client.post(reverse("acceso:salir"))

        assert respuesta.url == reverse("acceso:teclado")
        assert "_auth_user_id" not in client.session

    def test_el_botón_de_terminar_sale_en_la_pantalla_del_operador(
        self, client, django_user_model
    ):
        soldador(django_user_model, pin="1234")
        client.post(reverse("acceso:entrar"), {"pin": "1234"})

        cuerpo = client.get(reverse("produccion:movil")).content.decode()

        assert "acceso:salir" not in cuerpo  # que esté resuelta, no cruda
        assert reverse("acceso:salir") in cuerpo
        assert "Terminé" in cuerpo

    def test_en_la_pc_de_oficina_no_sale(self, client, django_user_model):
        """Ahí la sesión es de una persona y de un sitio."""
        persona = soldador(django_user_model, pin="1234")
        client.force_login(persona)

        cuerpo = client.get(reverse("produccion:movil")).content.decode()

        assert reverse("acceso:salir") not in cuerpo


class TestLaSesiónDeLaTabletaSeCierraSola:
    """Nadie va a tocar «salir» cuando le llaman de la nave.

    Y una tableta con la sesión de alguien abierta es peor que ninguna sesión:
    el siguiente apunta su trabajo, de buena fe, a nombre del anterior.
    """

    def test_tras_el_plazo_sin_usarse_pide_el_pin_otra_vez(
        self, client, django_user_model
    ):
        soldador(django_user_model, pin="1234")
        client.post(reverse("acceso:entrar"), {"pin": "1234"})

        sesion = client.session
        sesion[CLAVE_VISTO] = int(time.time()) - (
            servicios.minutos_de_inactividad() * 60 + 60
        )
        sesion.save()

        respuesta = client.get(reverse("produccion:movil"))

        assert respuesta.status_code == 302
        assert respuesta.url == reverse("acceso:teclado")
        assert "_auth_user_id" not in client.session

    def test_se_cuenta_desde_la_última_petición_y_no_desde_que_entró(
        self, client, django_user_model
    ):
        """Quien está trabajando sigue dentro.

        Con un plazo absoluto, a los quince minutos sale todo el mundo esté o
        no en medio de algo, que es la clase de cosa que hace que la gente deje
        de usar la pantalla.
        """
        soldador(django_user_model, pin="1234")
        client.post(reverse("acceso:entrar"), {"pin": "1234"})

        sesion = client.session
        sesion[CLAVE_VISTO] = int(time.time()) - 60
        sesion.save()

        client.get(reverse("produccion:movil"))

        assert client.session[CLAVE_VISTO] >= int(time.time()) - 5

    def test_la_sesión_de_oficina_no_se_cierra_sola(self, client, django_user_model):
        """Quien está en la PC de arriba está en su sitio."""
        jefe = cuenta(django_user_model, "zz_jefe", ["admin_general"])
        client.force_login(jefe)

        sesion = client.session
        sesion[CLAVE_VISTO] = int(time.time()) - 10 * 60 * 60
        sesion.save()

        respuesta = client.get(reverse("produccion:home"))

        assert respuesta.status_code == 200
        assert client.session.get(CLAVE_SESION) is None


class TestElTecladoNoSeDejaAporrear:
    def test_tras_varios_intentos_hace_esperar(self, client, django_user_model):
        soldador(django_user_model, pin="1234")

        for _ in range(servicios.INTENTOS_ANTES_DE_ESPERAR):
            respuesta = client.post(reverse("acceso:entrar"), {"pin": "0000"})

        assert respuesta.status_code == 429
        assert "Espera" in respuesta.content.decode()

    def test_durante_la_espera_ni_el_pin_bueno_abre(self, client, django_user_model):
        soldador(django_user_model, pin="1234")
        for _ in range(servicios.INTENTOS_ANTES_DE_ESPERAR):
            client.post(reverse("acceso:entrar"), {"pin": "0000"})

        respuesta = client.post(reverse("acceso:entrar"), {"pin": "1234"})

        assert respuesta.status_code == 429
        assert "_auth_user_id" not in client.session


# --------------------------------------------------------- la pantalla de altas


class TestSePoneDesdeLaPantallaDeUsuarios:
    def test_al_dar_de_alta_a_alguien_del_piso_se_le_pone_su_pin(
        self, client, django_user_model
    ):
        jefe = cuenta(django_user_model, "zz_jefe", ["admin_general"])
        client.force_login(jefe)

        client.post(reverse("catalogos:usuario_crear"), {
            "username": "zz_nuevo",
            "first_name": "",
            "last_name": "",
            "email": "",
            "is_active": "on",
            "grupos": ["soldadura"],
            "pin": "5678",
            "contrasena": "unaclave123",
            "repetida": "unaclave123",
        })

        creado = django_user_model.objects.get(username="zz_nuevo")
        assert servicios.de(creado) == "5678"

    def test_dejarlo_vacío_le_quita_el_pin(self, client, django_user_model):
        jefe = cuenta(django_user_model, "zz_jefe", ["admin_general"])
        client.force_login(jefe)
        persona = soldador(django_user_model, pin="1234")

        client.post(reverse("catalogos:usuario_editar", args=[persona.pk]), {
            "username": persona.username,
            "first_name": "",
            "last_name": "",
            "email": "",
            "is_active": "on",
            "grupos": ["soldadura"],
            "pin": "",
        })

        assert servicios.de(persona) == ""

    def test_guardar_la_cuenta_no_le_borra_los_permisos(
        self, client, django_user_model
    ):
        """Encontrado al poner un PIN desde la pantalla, y anterior a él.

        Las casillas de «Qué puede hacer» estaban dentro de un segundo `<form>`
        sin botón, así que al guardar no llegaba ninguna al servidor y la
        persona se quedaba sin ningún permiso. Sin error y sin aviso: el
        síntoma salía al día siguiente, cuando esa cuenta entraba y no veía
        nada, y no se parecía a su causa.

        Lo que fija esta prueba es que la pantalla mande los permisos, que es
        justo lo que el navegador no hacía.
        """
        jefe = cuenta(django_user_model, "zz_jefe", ["admin_general"])
        client.force_login(jefe)
        persona = soldador(django_user_model, pin="1234")

        cuerpo = client.get(
            reverse("catalogos:usuario_editar", args=[persona.pk])
        ).content.decode()

        # Una casilla por rol, y todas enganchadas al formulario que lleva el
        # botón de guardar.
        assert 'id="form-cuenta"' in cuerpo
        assert cuerpo.count('form="form-cuenta"') == len(roles.ROLES)

    def test_la_lista_enseña_el_pin(self, client, django_user_model):
        """Porque la pregunta que llega de verdad es «se me olvidó el mío».

        Si estuviera escondido habría que ponerle uno nuevo cada vez, y a mitad
        de turno eso es dejar a alguien fuera. Sólo la ve quien administra.
        """
        jefe = cuenta(django_user_model, "zz_jefe", ["admin_general"])
        client.force_login(jefe)
        soldador(django_user_model, pin="4242")

        cuerpo = client.get(reverse("catalogos:usuarios")).content.decode()

        assert "4242" in cuerpo
