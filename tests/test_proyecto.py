"""Cómo va un proyecto.

La pregunta de la obra es «¿cómo va Matilda?» y la respuesta útil es una
resta: «faltan dieciocho vigas, ayer se terminaron nueve». El sistema no podía
darla porque un proyecto era sólo un nombre: nadie había apuntado nunca cuánto
había que fabricar, así que «faltan dieciocho» no se podía calcular.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.servicios import proyecto as servicio

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

MATILDA = "Matilda"


def proyecto(nombre=MATILDA):
    from catalogos.models import Proyecto

    return Proyecto.objects.create(nombre=nombre)


def vigas(cuantas, codigo="V-118", estado="Soldadura", obra=MATILDA, peso=100):
    from produccion.models import Viga

    return [
        Viga.objects.create(
            codigo_viga=codigo,
            pieza_no=n,
            total_piezas=cuantas,
            proyecto=obra,
            descripcion="Viga IPR 12 x 30",
            fecha_compromiso=timezone.localdate(),
            estado=estado,
            prioridad=3,
            peso_kg=peso,
            fecha_creacion=timezone.now(),
            ultimo_cambio=timezone.now(),
        )
        for n in range(1, cuantas + 1)
    ]


def requerimiento(el_proyecto, descripcion="Viga IPR", codigo="V-118", cantidad=27):
    from nucleo.models import RequerimientoProyecto

    return RequerimientoProyecto.objects.create(
        proyecto=el_proyecto,
        descripcion=descripcion,
        codigo=codigo,
        cantidad=cantidad,
    )


def el(lista, codigo="V-118"):
    return next(c for c in lista if c.codigo.upper() == codigo.upper())


class TestLaPreguntaDeLaObra:
    def test_faltan_dieciocho_y_ayer_se_hicieron_nueve(self):
        """El caso literal: veintisiete vendidas, nueve terminadas."""
        el_proyecto = proyecto()
        requerimiento(el_proyecto, cantidad=27)
        vigas(9, estado="Terminado")
        vigas(18, estado="Soldadura")

        concepto = el(servicio.conceptos(el_proyecto))

        assert concepto.requerido == 27
        assert concepto.hechas == 9
        assert concepto.faltan == 18
        assert concepto.avance == 33

    def test_lo_enviado_cuenta_como_hecho(self):
        """Una pieza en la obra está hecha. No contarla dejaría un proyecto
        entregado viéndose a medias para siempre."""
        el_proyecto = proyecto()
        vigas(5, estado="Enviado")

        assert el(servicio.conceptos(el_proyecto)).hechas == 5

    def test_un_requerimiento_sin_produccion_ya_se_ve(self):
        """Es el caso del día que se da de alta el proyecto, y es justo lo que
        antes no se podía ver: el proyecto existía y no decía nada."""
        el_proyecto = proyecto()
        requerimiento(el_proyecto, cantidad=27)

        concepto = el(servicio.conceptos(el_proyecto))

        assert concepto.requerido == 27
        assert concepto.hechas == 0
        assert concepto.faltan == 27

    def test_lo_planeado_manda_sobre_lo_dado_de_alta(self):
        """Si se vendieron veintisiete y hay veinte en el sistema, faltan
        siete por dar de alta y el proyecto tiene que decirlo."""
        el_proyecto = proyecto()
        requerimiento(el_proyecto, cantidad=27)
        vigas(20, estado="Terminado")

        concepto = el(servicio.conceptos(el_proyecto))

        assert concepto.requerido == 27
        assert concepto.faltan == 7


class TestLoQueSeProduceSinPlanear:
    def test_aparece_igual(self):
        """Es trabajo real: esconderlo sería peor que no cuadrar."""
        el_proyecto = proyecto()
        vigas(5)

        concepto = el(servicio.conceptos(el_proyecto))

        assert concepto.requerido == 5
        assert concepto.planeado is False

    def test_y_se_cuenta_cuanto_hay_sin_planear(self):
        """Un proyecto donde todo apareció solo es un proyecto que nadie
        planeó, y el «faltan» sólo mide contra lo ya dado de alta."""
        el_proyecto = proyecto()
        vigas(5)

        assert servicio.resumen(servicio.conceptos(el_proyecto))["sin_planear"] == 1

    def test_lo_de_otra_obra_no_se_cuela(self):
        el_proyecto = proyecto()
        vigas(5, obra="OTRA OBRA")

        assert servicio.conceptos(el_proyecto) == []


class TestLasCuatroLineas:
    def _orden_de_herreria(self, el_proyecto, objetivo=10, terminadas=4):
        from catalogos.models import HerrOrdenProduccion

        return HerrOrdenProduccion.objects.create(
            proyecto=el_proyecto,
            codigo="H-BARANDAL",
            nombre="Barandal tipo A",
            total_piezas=objetivo,
            cantidad_objetivo=objetivo,
            cantidad_terminada=terminadas,
            fecha_compromiso=timezone.localdate(),
            peso_kg=50.0,
        )

    def test_herreria_entra_en_el_proyecto(self):
        """La pantalla anterior sólo enseñaba Estructuras, así que un proyecto
        con herrería se veía a un tercio."""
        el_proyecto = proyecto()
        self._orden_de_herreria(el_proyecto)

        concepto = el(servicio.conceptos(el_proyecto), "H-BARANDAL")

        assert concepto.linea == "Herrería"
        assert concepto.requerido == 10
        assert concepto.hechas == 4
        assert concepto.en_produccion == 6

    def test_una_orden_cancelada_no_cuenta(self):
        el_proyecto = proyecto()
        orden = self._orden_de_herreria(el_proyecto)
        orden.estado = "Cancelada"
        orden.save()

        assert servicio.conceptos(el_proyecto) == []

    def test_los_totales_suman_las_dos_lineas(self):
        el_proyecto = proyecto()
        self._orden_de_herreria(el_proyecto, objetivo=10, terminadas=4)
        vigas(5, estado="Terminado")

        resumen = servicio.resumen(servicio.conceptos(el_proyecto))

        assert resumen["requerido"] == 15
        assert resumen["hechas"] == 9
        assert resumen["conceptos"] == 2

    def test_robotica_se_lista_pero_sin_avance(self):
        """Esa línea no apunta cuánto se lleva hecho de cada orden, así que
        cualquier porcentaje que se enseñara estaría inventado."""
        from catalogos.models import RobotOrdenProduccion

        el_proyecto = proyecto()
        RobotOrdenProduccion.objects.create(
            proyecto=el_proyecto, nombre="Placa robotizada", cantidad_objetivo=30
        )

        assert len(servicio.ordenes_de_robotica(el_proyecto)) == 1
        assert servicio.conceptos(el_proyecto) == []


class TestElOrden:
    def test_lo_que_falta_va_primero(self):
        """Un proyecto se mira para saber qué queda, no para leer lo ya
        entregado."""
        el_proyecto = proyecto()
        vigas(3, codigo="A-LISTA", estado="Terminado")
        vigas(3, codigo="Z-PENDIENTE", estado="Corte")

        assert servicio.conceptos(el_proyecto)[0].codigo == "Z-PENDIENTE"


def navegador(django_user_model, nombre="jefa", grupo="admin_general"):
    persona = django_user_model.objects.create_user(nombre, password="x")
    if grupo:
        persona.groups.add(Group.objects.get_or_create(name=grupo)[0])
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestLaPantalla:
    def test_pide_sesion(self):
        el_proyecto = proyecto()
        anonimo = Client(SERVER_NAME="127.0.0.1")

        respuesta = anonimo.get(
            reverse("catalogos:proyecto_detalle", args=[el_proyecto.pk])
        )

        assert respuesta.status_code == 302

    def test_ensena_la_resta(self, django_user_model):
        el_proyecto = proyecto()
        requerimiento(el_proyecto, cantidad=27)
        vigas(9, estado="Terminado")

        cuerpo = (
            navegador(django_user_model)
            .get(reverse("catalogos:proyecto_detalle", args=[el_proyecto.pk]))
            .content.decode()
        )

        assert "Faltan" in cuerpo and "V-118" in cuerpo

    def test_apuntar_lo_que_lleva(self, django_user_model):
        el_proyecto = proyecto()

        navegador(django_user_model).post(
            reverse("catalogos:proyecto_requerimiento_crear", args=[el_proyecto.pk]),
            {"descripcion": "Viga IPR", "codigo": "V-118", "cantidad": "27"},
            follow=True,
        )

        assert el(servicio.conceptos(el_proyecto)).requerido == 27

    def test_dos_renglones_con_el_mismo_codigo_se_rechazan(self, django_user_model):
        """Se cruzarían los dos con la misma producción y el avance saldría
        contado por duplicado."""
        el_proyecto = proyecto()
        requerimiento(el_proyecto, cantidad=27)

        respuesta = navegador(django_user_model).post(
            reverse("catalogos:proyecto_requerimiento_crear", args=[el_proyecto.pk]),
            {"descripcion": "Otra viga", "codigo": "V-118", "cantidad": "5"},
            follow=True,
        )

        assert "ya lleva un renglón" in respuesta.content.decode()
        assert el(servicio.conceptos(el_proyecto)).requerido == 27

    def test_sin_cantidad_no_se_apunta(self, django_user_model):
        el_proyecto = proyecto()

        navegador(django_user_model).post(
            reverse("catalogos:proyecto_requerimiento_crear", args=[el_proyecto.pk]),
            {"descripcion": "Viga IPR", "codigo": "V-118", "cantidad": "0"},
            follow=True,
        )

        assert servicio.conceptos(el_proyecto) == []

    def test_quitar_lo_planeado_no_borra_lo_producido(self, django_user_model):
        el_proyecto = proyecto()
        fila = requerimiento(el_proyecto, cantidad=27)
        vigas(9, estado="Terminado")

        navegador(django_user_model).post(
            reverse(
                "catalogos:proyecto_requerimiento_borrar",
                args=[el_proyecto.pk, fila.pk],
            ),
            follow=True,
        )

        concepto = el(servicio.conceptos(el_proyecto))
        assert concepto.hechas == 9
        assert concepto.planeado is False

    def test_el_piso_no_planea(self, django_user_model):
        """Apuntar un requerimiento es decir qué se le prometió al cliente."""
        el_proyecto = proyecto()
        cliente = navegador(django_user_model, nombre="juan", grupo="soldadura")

        respuesta = cliente.post(
            reverse("catalogos:proyecto_requerimiento_crear", args=[el_proyecto.pk]),
            {"descripcion": "Viga IPR", "codigo": "V-118", "cantidad": "27"},
        )

        assert respuesta.status_code == 302
        assert servicio.conceptos(el_proyecto) == []

    def test_pero_si_ve_como_va(self, django_user_model):
        el_proyecto = proyecto()
        cliente = navegador(django_user_model, nombre="juan", grupo="soldadura")

        respuesta = cliente.get(
            reverse("catalogos:proyecto_detalle", args=[el_proyecto.pk])
        )

        assert respuesta.status_code == 200


class TestElCruceAguantaComoSeTeclea:
    """En el taller el mismo perfil se escribe de tres formas.

    `V-118`, `V118` y `v 118` según quién lo teclee. Con la comparación
    literal, un requerimiento de veintisiete vigas `V-118` no encontraba las
    veintisiete piezas `V118` y el proyecto decía que no se había hecho nada.
    """

    def test_el_guion_no_separa_el_requerimiento_de_su_produccion(self):
        el_proyecto = proyecto()
        requerimiento(el_proyecto, codigo="V-118", cantidad=27)
        vigas(9, codigo="V118", estado="Terminado")

        lista = servicio.conceptos(el_proyecto)

        assert len(lista) == 1
        assert lista[0].requerido == 27
        assert lista[0].hechas == 9

    def test_ni_los_espacios_ni_las_minusculas(self):
        el_proyecto = proyecto()
        requerimiento(el_proyecto, codigo="v 118", cantidad=10)
        vigas(4, codigo="V-118", estado="Terminado")

        assert servicio.conceptos(el_proyecto)[0].hechas == 4

    def test_pero_los_acentos_si_distinguen(self):
        """En este catálogo la letra distingue piezas de verdad: juntar
        «Ángulo-D» con «Angulo-D» sería peor que separarlas."""
        el_proyecto = proyecto()
        vigas(2, codigo="Ángulo-D")
        vigas(3, codigo="Angulo-D")

        assert len(servicio.conceptos(el_proyecto)) == 2

    def test_dos_formas_del_mismo_codigo_se_rechazan_al_apuntar(
        self, django_user_model
    ):
        el_proyecto = proyecto()
        requerimiento(el_proyecto, codigo="V-118", cantidad=27)

        respuesta = navegador(django_user_model).post(
            reverse("catalogos:proyecto_requerimiento_crear", args=[el_proyecto.pk]),
            {"descripcion": "La misma", "codigo": "V118", "cantidad": "5"},
            follow=True,
        )

        assert "ya lleva un renglón" in respuesta.content.decode()
