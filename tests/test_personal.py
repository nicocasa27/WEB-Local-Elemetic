"""Recursos humanos: la gente del taller, su organización y su sueldo.

Lo que había: una ficha con nombre, equipo y un rol elegido de cuatro palabras
escritas en el código, que se daba de alta desde la pantalla de Equipos porque
era donde cabía. No se podía contestar cuánta gente hay, en qué departamento
está, ni cuánto suma la nómina; y los datos de la persona —cuándo nació, cuándo
entró, cuánto gana— no existían en ningún sitio.

Dos cosas se vigilan aquí por encima del resto:

- que **inventar un puesto nuevo no rompa el reparto de trabajo**, que sigue
  funcionando con los cuatro papeles de siempre;
- que **el sueldo no lo vea quien no debe**, porque en el taller esta pantalla
  se abre delante de otros.
"""

from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, User
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from acceso import servicios as pines
from catalogos.models import Colaborador, EquipoTrabajo
from personal.models import Departamento, Puesto

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


@pytest.fixture
def quien_administra():
    persona = User.objects.create_user("jefa", password="x")
    persona.groups.add(Group.objects.get_or_create(name="admin_general")[0])
    cliente = Client()
    cliente.force_login(persona)
    return cliente


@pytest.fixture
def equipo():
    return EquipoTrabajo.objects.create(
        nombre="Cuadrilla A", area="Soldadura", integrantes=3, activo=True
    )


@pytest.fixture
def departamento():
    return Departamento.objects.create(nombre="Producción", activo=True)


@pytest.fixture
def puesto(departamento):
    return Puesto.objects.create(
        nombre="Pailero", departamento=departamento, rol_de_produccion="Soldador", activo=True
    )


def alta(equipo, **cambios):
    datos = {
        "nombre": "Juan Pérez",
        "sexo": "M",
        "fecha_nacimiento": "1990-05-14",
        "telefono": "9991234567",
        "departamento": "",
        "puesto": "",
        "equipo": str(equipo.id),
        "fecha_ingreso": "2026-01-15",
        "sueldo_mensual": "12500.50",
        "activo": "on",
        "usuario": "",
        "contrasena": "",
        "pin": "",
    }
    datos.update(cambios)
    # Una casilla sin marcar no manda cadena vacía: no manda nada. Dejar
    # `grupos: ""` haría fallar la validación por un dato que el navegador
    # nunca envía, y el test estaría probando algo que no pasa.
    return {k: v for k, v in datos.items() if v != ""} | {
        k: v for k, v in datos.items() if k != "grupos" and v == ""
    }


class TestDarDeAlta:
    def test_se_guarda_la_persona_entera(self, quien_administra, equipo, puesto):
        respuesta = quien_administra.post(
            reverse("personal:alta"),
            alta(equipo, departamento=str(puesto.departamento_id), puesto=str(puesto.id)),
        )

        assert respuesta.status_code == 302
        ficha = Colaborador.objects.get(nombre="Juan Pérez")
        assert ficha.sexo == "M"
        assert ficha.fecha_nacimiento.isoformat() == "1990-05-14"
        assert ficha.fecha_ingreso.isoformat() == "2026-01-15"
        assert ficha.telefono == "9991234567"
        assert ficha.departamento == puesto.departamento
        assert ficha.puesto == puesto
        assert ficha.sueldo_mensual == Decimal("12500.50")
        assert ficha.activo

    def test_un_puesto_nuevo_no_rompe_el_reparto_de_trabajo(self, quien_administra, equipo, puesto):
        """El sistema reparte por los cuatro papeles de siempre. Un puesto
        inventado dice a cuál se parece, y la asignación sigue funcionando."""
        quien_administra.post(reverse("personal:alta"), alta(equipo, puesto=str(puesto.id)))

        assert Colaborador.objects.get(nombre="Juan Pérez").rol == "Soldador"

    def test_un_puesto_que_no_es_de_produccion_no_deja_el_rol_vacio(
        self, quien_administra, equipo, departamento
    ):
        """`rol` no admite vacío en la base. Alguien de administración tiene
        que poder darse de alta igual."""
        oficina = Puesto.objects.create(
            nombre="Contadora", departamento=departamento, rol_de_produccion="", activo=True
        )

        quien_administra.post(reverse("personal:alta"), alta(equipo, puesto=str(oficina.id)))

        assert Colaborador.objects.get(nombre="Juan Pérez").rol == "Auxiliar"

    def test_el_departamento_sale_del_puesto_si_no_se_dice(
        self, quien_administra, equipo, puesto
    ):
        """Si el puesto ya sabe de qué departamento es, no hay que teclearlo."""
        quien_administra.post(
            reverse("personal:alta"), alta(equipo, puesto=str(puesto.id), departamento="")
        )

        assert Colaborador.objects.get(nombre="Juan Pérez").departamento == puesto.departamento

    def test_se_puede_dar_de_alta_sin_departamento_ni_puesto(self, quien_administra, equipo):
        """El primer día no hay ninguno, y hay que poder empezar por alguien."""
        respuesta = quien_administra.post(reverse("personal:alta"), alta(equipo))

        assert respuesta.status_code == 302
        assert Colaborador.objects.filter(nombre="Juan Pérez").exists()

    def test_avisa_del_nombre_repetido_sin_bloquearlo_a_ciegas(self, quien_administra, equipo):
        """En un taller hay dos Juan Pérez de verdad. Lo que no puede pasar es
        darlo de alta dos veces sin enterarse."""
        quien_administra.post(reverse("personal:alta"), alta(equipo))

        respuesta = quien_administra.post(reverse("personal:alta"), alta(equipo))

        assert respuesta.status_code == 200
        assert "Ya hay alguien llamado" in respuesta.content.decode()
        assert Colaborador.objects.filter(nombre="Juan Pérez").count() == 1


class TestFechasQueNoPuedenSer:
    def test_no_se_puede_nacer_en_el_futuro(self, quien_administra, equipo):
        futuro = (timezone.localdate() + timezone.timedelta(days=30)).isoformat()

        respuesta = quien_administra.post(
            reverse("personal:alta"), alta(equipo, fecha_nacimiento=futuro)
        )

        assert respuesta.status_code == 200
        assert not Colaborador.objects.filter(nombre="Juan Pérez").exists()

    def test_un_ano_mal_tecleado_se_ve_al_momento(self, quien_administra, equipo):
        """Un dedo de más en el año, visto aquí y no dentro de seis meses en un
        informe de edades."""
        respuesta = quien_administra.post(
            reverse("personal:alta"), alta(equipo, fecha_nacimiento="2020-05-14")
        )

        assert respuesta.status_code == 200
        assert "catorce" in respuesta.content.decode()

    def test_no_se_puede_entrar_a_trabajar_antes_de_nacer(self, quien_administra, equipo):
        respuesta = quien_administra.post(
            reverse("personal:alta"),
            alta(equipo, fecha_nacimiento="1990-05-14", fecha_ingreso="1985-01-01"),
        )

        assert respuesta.status_code == 200
        assert "antes de nacer" in respuesta.content.decode()

    def test_el_sueldo_no_puede_ser_negativo(self, quien_administra, equipo):
        respuesta = quien_administra.post(
            reverse("personal:alta"), alta(equipo, sueldo_mensual="-100")
        )

        assert respuesta.status_code == 200
        assert not Colaborador.objects.filter(nombre="Juan Pérez").exists()


class TestLaCuentaSeCreaDesdeLaFicha:
    """Aquí y no en la pantalla de Usuarios porque el enlace entre la cuenta y
    la ficha es justo lo que se olvida cuando son dos pantallas, y sin enlace
    «Mi trabajo» no le enseña sus órdenes a nadie."""

    def test_se_crea_enlazada(self, quien_administra, equipo):
        quien_administra.post(
            reverse("personal:alta"),
            alta(equipo, usuario="jperez", contrasena="clave12345", grupos="soldadura"),
        )

        cuenta = User.objects.get(username="jperez")
        assert list(cuenta.groups.values_list("name", flat=True)) == ["soldadura"]
        assert Colaborador.objects.get(nombre="Juan Pérez").usuario == "jperez"

    def test_con_pin_para_la_tableta(self, quien_administra, equipo):
        quien_administra.post(
            reverse("personal:alta"),
            alta(equipo, usuario="jperez", pin="4821", grupos="soldadura"),
        )

        assert pines.de(User.objects.get(username="jperez")) == "4821"

    def test_sin_usuario_no_se_crea_ninguna(self, quien_administra, equipo):
        """No todo el mundo necesita entrar al sistema."""
        quien_administra.post(reverse("personal:alta"), alta(equipo))

        assert Colaborador.objects.filter(nombre="Juan Pérez").exists()
        assert not User.objects.filter(username="jperez").exists()

    def test_una_contrasena_o_un_pin_sin_usuario_se_rechaza(self, quien_administra, equipo):
        respuesta = quien_administra.post(
            reverse("personal:alta"), alta(equipo, contrasena="clave12345")
        )

        assert respuesta.status_code == 200
        assert not Colaborador.objects.filter(nombre="Juan Pérez").exists()

    def test_una_cuenta_nueva_sin_forma_de_entrar_se_rechaza(self, quien_administra, equipo):
        """Crear una cuenta sin contraseña ni PIN es crear algo con lo que
        nadie puede entrar, y nadie se entera hasta que lo intenta."""
        respuesta = quien_administra.post(
            reverse("personal:alta"), alta(equipo, usuario="jperez")
        )

        assert respuesta.status_code == 200
        assert not User.objects.filter(username="jperez").exists()

    def test_no_se_puede_repetir_un_usuario(self, quien_administra, equipo):
        User.objects.create_user("jperez", password="x")

        respuesta = quien_administra.post(
            reverse("personal:alta"),
            alta(equipo, usuario="jperez", contrasena="clave12345"),
        )

        assert respuesta.status_code == 200
        assert "ya existe" in respuesta.content.decode().lower()


class TestBaja:
    def test_no_se_borra_a_nadie(self, quien_administra, equipo):
        """Sus asignaciones, sus firmas y su rendimiento quedan en el
        historial. Sin la ficha, todo eso se queda sin dueño."""
        quien_administra.post(
            reverse("personal:alta"),
            alta(equipo, usuario="jperez", pin="4821", grupos="soldadura"),
        )
        ficha = Colaborador.objects.get(nombre="Juan Pérez")

        quien_administra.post(reverse("personal:dar_de_baja", args=[ficha.id]))

        ficha.refresh_from_db()
        assert Colaborador.objects.filter(pk=ficha.pk).exists()
        assert not ficha.activo

    def test_su_cuenta_deja_de_entrar(self, quien_administra, equipo):
        """Alguien que ya no trabaja aquí no puede seguir teniendo llave."""
        quien_administra.post(
            reverse("personal:alta"),
            alta(equipo, usuario="jperez", pin="4821", grupos="soldadura"),
        )
        ficha = Colaborador.objects.get(nombre="Juan Pérez")

        quien_administra.post(reverse("personal:dar_de_baja", args=[ficha.id]))

        cuenta = User.objects.get(username="jperez")
        assert not cuenta.is_active
        assert not pines.de(cuenta), "el PIN sigue abriendo la tableta"

    def test_se_puede_reactivar(self, quien_administra, equipo):
        quien_administra.post(reverse("personal:alta"), alta(equipo))
        ficha = Colaborador.objects.get(nombre="Juan Pérez")
        quien_administra.post(reverse("personal:dar_de_baja", args=[ficha.id]))

        quien_administra.post(reverse("personal:dar_de_baja", args=[ficha.id]))

        ficha.refresh_from_db()
        assert ficha.activo

    def test_solo_por_post(self, quien_administra, equipo):
        quien_administra.post(reverse("personal:alta"), alta(equipo))
        ficha = Colaborador.objects.get(nombre="Juan Pérez")

        assert quien_administra.get(reverse("personal:dar_de_baja", args=[ficha.id])).status_code == 405


class TestOrganizacion:
    def test_se_crea_un_departamento(self, quien_administra):
        quien_administra.post(
            reverse("personal:organizacion"),
            {"que": "departamento", "id": "", "nombre": "  Pintura  ", "activo": "on"},
        )

        d = Departamento.objects.get(nombre_normalizado="PINTURA")
        assert d.nombre == "Pintura", "no se limpiaron los espacios"

    def test_no_se_repite_un_departamento(self, quien_administra, departamento):
        quien_administra.post(
            reverse("personal:organizacion"),
            {"que": "departamento", "id": "", "nombre": "producción", "activo": "on"},
        )

        assert Departamento.objects.filter(nombre_normalizado="PRODUCCIÓN").count() == 1

    def test_se_crea_un_puesto(self, quien_administra, departamento):
        quien_administra.post(
            reverse("personal:organizacion"),
            {
                "que": "puesto", "id": "", "nombre": "Pailero",
                "departamento": str(departamento.id),
                "rol_de_produccion": "Soldador", "activo": "on",
            },
        )

        p = Puesto.objects.get(nombre_normalizado="PAILERO")
        assert p.departamento == departamento
        assert p.rol_de_produccion == "Soldador"

    def test_el_mismo_puesto_puede_estar_en_dos_departamentos(self, quien_administra, departamento):
        """«Auxiliar» de pintura y «Auxiliar» de corte son dos puestos."""
        otro = Departamento.objects.create(nombre="Pintura", activo=True)
        Puesto.objects.create(nombre="Auxiliar", departamento=departamento, activo=True)

        quien_administra.post(
            reverse("personal:organizacion"),
            {"que": "puesto", "id": "", "nombre": "Auxiliar",
             "departamento": str(otro.id), "rol_de_produccion": "", "activo": "on"},
        )

        assert Puesto.objects.filter(nombre_normalizado="AUXILIAR").count() == 2

    def test_no_dos_veces_el_mismo_en_el_mismo_departamento(self, quien_administra, departamento):
        Puesto.objects.create(nombre="Pailero", departamento=departamento, activo=True)

        quien_administra.post(
            reverse("personal:organizacion"),
            {"que": "puesto", "id": "", "nombre": "pailero",
             "departamento": str(departamento.id), "rol_de_produccion": "", "activo": "on"},
        )

        assert Puesto.objects.filter(nombre_normalizado="PAILERO").count() == 1


class TestLoQueSeVe:
    def test_la_nomina_se_calcula_de_los_activos(self, quien_administra, equipo):
        """Se calcula, no se guarda: un total guardado se queda viejo en cuanto
        alguien da de alta a alguien por otra pantalla."""
        Colaborador.objects.create(
            nombre="A", rol="Soldador", equipo=equipo, activo=True, sueldo_mensual=Decimal("10000")
        )
        Colaborador.objects.create(
            nombre="B", rol="Pintor", equipo=equipo, activo=True, sueldo_mensual=Decimal("5000")
        )
        Colaborador.objects.create(
            nombre="C", rol="Pintor", equipo=equipo, activo=False, sueldo_mensual=Decimal("9999")
        )

        respuesta = quien_administra.get(reverse("personal:lista"))

        assert respuesta.context["resumen"]["nomina"] == Decimal("15000")
        assert respuesta.context["resumen"]["personas"] == 2
        assert respuesta.context["resumen"]["bajas"] == 1

    def test_filtrar_no_cambia_el_total_del_taller(self, quien_administra, equipo, departamento):
        """Si el resumen se calculara sobre lo filtrado, filtrar por un
        departamento haría creer que esa es la nómina del taller."""
        Colaborador.objects.create(
            nombre="A", rol="Soldador", equipo=equipo, activo=True,
            sueldo_mensual=Decimal("10000"), departamento=departamento,
        )
        Colaborador.objects.create(
            nombre="B", rol="Pintor", equipo=equipo, activo=True, sueldo_mensual=Decimal("5000")
        )

        respuesta = quien_administra.get(
            reverse("personal:lista"), {"departamento": str(departamento.id)}
        )

        assert len(respuesta.context["fichas"]) == 1
        assert respuesta.context["resumen"]["nomina"] == Decimal("15000")


class TestQuienPuedeEntrar:
    """El sueldo no lo puede ver cualquiera: en el taller esta pantalla se abre
    delante de otros."""

    @pytest.mark.parametrize(
        "ruta", ["personal:lista", "personal:alta", "personal:organizacion"]
    )
    def test_pide_sesion(self, ruta):
        respuesta = Client().get(reverse(ruta))
        assert respuesta.status_code == 302
        assert "login" in respuesta["Location"]

    @pytest.mark.parametrize(
        "ruta", ["personal:lista", "personal:alta", "personal:organizacion"]
    )
    def test_un_soldador_no_entra(self, ruta):
        persona = User.objects.create_user("soldador", password="x")
        persona.groups.add(Group.objects.get_or_create(name="soldadura")[0])
        cliente = Client()
        cliente.force_login(persona)

        assert cliente.get(reverse(ruta)).status_code == 302

    def test_un_soldador_no_puede_dar_de_baja_a_nadie(self, equipo):
        ficha = Colaborador.objects.create(
            nombre="A", rol="Soldador", equipo=equipo, activo=True
        )
        persona = User.objects.create_user("soldador", password="x")
        persona.groups.add(Group.objects.get_or_create(name="soldadura")[0])
        cliente = Client()
        cliente.force_login(persona)

        cliente.post(reverse("personal:dar_de_baja", args=[ficha.id]))

        ficha.refresh_from_db()
        assert ficha.activo

    def test_esta_en_el_menu_de_quien_administra(self, quien_administra):
        html = quien_administra.get(reverse("personal:lista")).content.decode()
        assert reverse("personal:lista") in html
        assert "Recursos humanos" in html


class TestSembrarLaOrganizacion:
    """`sembrar_personal` deja el taller organizado sin teclear nada.

    Nada de lo que siembra está inventado: sale de las etapas del proceso, de
    las áreas de las cuadrillas que existen, de las máquinas dadas de alta y de
    los roles del sistema. Es un punto de partida, no una verdad: lo que sobre
    se desactiva desde la pantalla.
    """

    def sembrar(self):
        from io import StringIO

        from django.core.management import call_command

        salida = StringIO()
        call_command("sembrar_personal", stdout=salida)
        return salida.getvalue()

    def test_crea_los_departamentos_por_los_que_pasa_el_trabajo(self, equipo):
        self.sembrar()

        nombres = set(Departamento.objects.values_list("nombre", flat=True))
        assert {"Corte", "Armado", "Soldadura", "Pintura"} <= nombres

    def test_crea_los_departamentos_de_las_otras_lineas(self, equipo):
        self.sembrar()

        nombres = set(Departamento.objects.values_list("nombre", flat=True))
        assert {"Herrería", "Robótica", "Corta.mx", "Almacén"} <= nombres

    def test_los_puestos_de_corte_dicen_que_cortan(self, equipo):
        """Salen de las máquinas que hay dadas de alta: plasma, oxicorte,
        sierra cinta."""
        self.sembrar()

        corte = Departamento.objects.get(nombre="Corte")
        puestos = set(corte.puestos.values_list("nombre", flat=True))
        assert "Operador de plasma" in puestos
        assert "Operador de oxicorte" in puestos
        assert "Ayudante de corte" in puestos

    def test_cada_puesto_dice_a_que_papel_se_parece(self, equipo):
        """Es lo que hace que un puesto nuevo no rompa el reparto de órdenes."""
        self.sembrar()

        assert Puesto.objects.get(nombre="Armador").rol_de_produccion == "Soldador"
        assert Puesto.objects.get(nombre="Soldador MIG").rol_de_produccion == "Soldador"
        assert Puesto.objects.get(nombre="Operador de plasma").rol_de_produccion == "Operador"

    def test_los_de_oficina_no_entran_en_el_reparto(self, equipo):
        """Un almacenista no puede salir propuesto para soldar una viga."""
        self.sembrar()

        assert Puesto.objects.get(nombre="Almacenista").rol_de_produccion == ""
        assert Puesto.objects.get(nombre="Chofer").rol_de_produccion == ""

    def test_auxiliar_se_queda_sin_departamento_a_proposito(self, equipo):
        """Hay auxiliares en corte, en soldadura y en pintura: meterlo en uno
        solo sería mentir sobre los otros dos."""
        self.sembrar()

        assert Puesto.objects.get(nombre="Auxiliar").departamento is None
        assert Puesto.objects.get(nombre="Soldador").departamento.nombre == "Soldadura"

    def test_a_quien_ya_estaba_se_le_pone_su_puesto(self, equipo):
        ficha = Colaborador.objects.create(
            nombre="Antiguo", rol="Pintor", equipo=equipo, activo=True
        )

        self.sembrar()

        ficha.refresh_from_db()
        assert ficha.puesto.rol_de_produccion == "Pintor"

    def test_el_departamento_sale_del_area_de_su_cuadrilla(self, equipo):
        """Otro dato que ya estaba en la base y que nadie había puesto en su
        sitio: la cuadrilla sabe de qué área es."""
        ficha = Colaborador.objects.create(
            nombre="Antiguo", rol="Soldador", equipo=equipo, activo=True
        )

        self.sembrar()

        ficha.refresh_from_db()
        assert ficha.departamento.nombre == "Soldadura"

    def test_no_pisa_el_departamento_que_alguien_ya_puso_a_mano(self, equipo, departamento):
        ficha = Colaborador.objects.create(
            nombre="Antiguo", rol="Soldador", equipo=equipo, activo=True,
            departamento=departamento,
        )

        self.sembrar()

        ficha.refresh_from_db()
        assert ficha.departamento == departamento

    def test_correrlo_dos_veces_no_duplica_nada(self, equipo):
        self.sembrar()
        cuantos = (Departamento.objects.count(), Puesto.objects.count())

        self.sembrar()

        assert (Departamento.objects.count(), Puesto.objects.count()) == cuantos

    def test_avisa_de_quien_se_queda_suelto(self, equipo):
        """Una cuadrilla de un área que no es ninguno de los departamentos."""
        rara = EquipoTrabajo.objects.create(
            nombre="Cuadrilla X", area="Lo que sea", integrantes=1, activo=True
        )
        Colaborador.objects.create(nombre="Suelto", rol="Auxiliar", equipo=rara, activo=True)

        salida = self.sembrar()

        assert "sin departamento" in salida
