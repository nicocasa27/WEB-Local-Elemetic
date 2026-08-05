"""«Control de producción»: las cuatro líneas en una sola lista.

La pregunta «¿qué está haciendo el taller?» no tenía pantalla. Había cuatro,
una por línea, porque el sistema es el mismo motor copiado cuatro veces, y
para contestar había que abrir las cuatro y sumar de cabeza.

Lo delicado de juntarlas es que **hay dos formas de trabajar que no se miden
igual**: una pieza a medida avanza por etapas y una orden en serie avanza por
cantidades. Enseñarlas en la misma tabla obliga a decidir qué es «avance»
para las dos, y a no mentir con la que no encaje.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core.servicios import panorama

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def proyecto(nombre="OBRA DE PRUEBA"):
    from catalogos.models import Proyecto

    return Proyecto.objects.get_or_create(nombre=nombre)[0]


def viga(estado="Soldadura", codigo="V-1", peso=100, piezas=1):
    from produccion.models import Viga

    return Viga.objects.create(
        codigo_viga=codigo,
        pieza_no=1,
        total_piezas=piezas,
        proyecto="TORRE NORTE",
        descripcion="viga de prueba",
        fecha_compromiso=timezone.localdate(),
        estado=estado,
        prioridad=3,
        peso_kg=peso,
        fecha_creacion=timezone.now(),
        ultimo_cambio=timezone.now(),
    )


def orden_herreria(codigo="H-1", etapa="Soldadura", piezas=30, terminadas=0, estado="Abierta"):
    from catalogos.models import HerrOrdenProduccion

    return HerrOrdenProduccion.objects.create(
        proyecto=proyecto(),
        codigo=codigo,
        pieza_no=1,
        total_piezas=piezas,
        nombre="Andamio",
        descripcion="Andamio estándar",
        fecha_compromiso=timezone.localdate(),
        prioridad=3,
        peso_kg=900,
        estado_etapa=etapa,
        estado=estado,
        cantidad_objetivo=piezas,
        cantidad_terminada=terminadas,
    )


def navegador(django_user_model, nombre="jefa"):
    persona = django_user_model.objects.create_user(nombre, password="x")
    persona.groups.add(Group.objects.get_or_create(name="admin_general")[0])
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestLasDosFormasDeTrabajarSalenJuntas:
    def test_los_andamios_y_las_vigas_en_la_misma_lista(self):
        """Es lo que pidió el taller: «mando a hacer treinta andamios y quiero
        verlo junto con lo demás»."""
        viga(codigo="V-42")
        orden_herreria(codigo="H-42")

        renglones = panorama.lo_que_se_esta_haciendo()

        assert {r["codigo"] for r in renglones} == {"V-42", "H-42"}
        assert {r["linea"] for r in renglones} == {"estructuras", "herreria"}

    def test_una_orden_en_serie_avanza_por_cantidades(self):
        orden_herreria(codigo="H-42", piezas=30, terminadas=12)

        renglon = panorama.lo_que_se_esta_haciendo(linea="herreria")[0]

        assert renglon["en_serie"] is True
        assert (renglon["hechas"], renglon["piezas"]) == (12, 30)
        assert renglon["avance"] == 40

    def test_una_pieza_a_medida_avanza_por_etapas(self):
        """No tiene cantidades: lo que se mide es cuánto lleva recorrido."""
        viga(estado="Espera de pintura", codigo="V-42")

        renglon = panorama.lo_que_se_esta_haciendo(linea="estructuras")[0]

        assert renglon["en_serie"] is False
        assert renglon["etapa"] == "Espera de pintura"
        assert renglon["avance"] == 75

    @pytest.mark.parametrize(
        "etapa,esperado",
        [("Espera de corte", 0), ("Corte", 12), ("Soldadura", 62), ("Terminado", 100)],
    )
    def test_el_recorrido_de_cada_etapa(self, etapa, esperado):
        """«Terminado» es el cien por cien de producción aunque la pieza no
        haya salido del taller: enviarla es de logística."""
        assert panorama._avance_de_etapa(etapa) == esperado

    def test_una_orden_de_una_pieza_no_se_marca_como_serie(self):
        """La misma regla que aplica el servidor para aceptar un avance."""
        orden_herreria(codigo="H-42", piezas=1)

        assert panorama.lo_que_se_esta_haciendo(linea="herreria")[0]["en_serie"] is False


class TestQueSaleYQueNo:
    def test_lo_terminado_no_es_produccion(self):
        """Terminado y enviado tienen sus propias pantallas: almacén y
        logística. Aquí llenarían la lista de cosas que ya no se hacen."""
        viga(estado="Terminado", codigo="V-LISTA")
        viga(estado="Enviado", codigo="V-FUERA")
        viga(estado="Corte", codigo="V-ACTIVA")

        renglones = panorama.lo_que_se_esta_haciendo()

        assert [r["codigo"] for r in renglones] == ["V-ACTIVA"]

    def test_una_orden_cerrada_no_sale(self):
        orden_herreria(codigo="H-42", estado="Cerrada")

        assert panorama.lo_que_se_esta_haciendo() == []

    def test_lo_mas_urgente_va_primero(self):
        import datetime

        hoy = timezone.localdate()
        tarde = viga(codigo="V-TARDE")
        tarde.fecha_compromiso = hoy + datetime.timedelta(days=30)
        tarde.save()
        viga(codigo="V-HOY")

        renglones = panorama.lo_que_se_esta_haciendo()

        assert [r["codigo"] for r in renglones] == ["V-HOY", "V-TARDE"]

    def test_lo_que_no_tiene_fecha_va_al_final(self):
        """No es que no corra prisa: es que nadie ha dicho para cuándo, y
        colarlo entre lo urgente sería inventarse un dato."""
        from catalogos.models import RobotOrdenProduccion

        viga(codigo="V-CON-FECHA")
        RobotOrdenProduccion.objects.create(
            proyecto=proyecto(), nombre="R-SIN-FECHA", producto="pieza",
            cantidad_objetivo=5, estado="Abierta",
        )

        renglones = panorama.lo_que_se_esta_haciendo()

        assert [r["codigo"] for r in renglones] == ["V-CON-FECHA", "R-SIN-FECHA"]


class TestRoboticaNoTieneEtapas:
    def test_se_dice_en_vez_de_inventarle_una(self):
        from catalogos.models import RobotOrdenProduccion

        RobotOrdenProduccion.objects.create(
            proyecto=proyecto(), nombre="R-1", producto="placa",
            cantidad_objetivo=8, estado="Abierta",
        )

        renglon = panorama.lo_que_se_esta_haciendo(linea="robotica")[0]

        assert renglon["etapa"] == ""
        assert renglon["piezas"] == 8

    def test_y_la_pantalla_lo_escribe(self, django_user_model):
        from catalogos.models import RobotOrdenProduccion

        RobotOrdenProduccion.objects.create(
            proyecto=proyecto(), nombre="R-1", producto="placa",
            cantidad_objetivo=8, estado="Abierta",
        )

        pagina = navegador(django_user_model).get(reverse("produccion:control")).content.decode()

        assert "sin etapas" in pagina


class TestLosTotalesCuadranConLaLista:
    def test_se_calculan_de_lo_que_se_ensena(self):
        """Un contador que dice diez sobre una lista de ocho es peor que no
        tener contador."""
        viga(codigo="V-1", peso=1000, piezas=2)
        orden_herreria(codigo="H-1", piezas=30)

        renglones = panorama.lo_que_se_esta_haciendo()
        resumen = panorama.resumen(renglones)

        assert resumen["renglones"] == 2
        assert resumen["piezas"] == 32
        assert float(resumen["toneladas"]) == pytest.approx(1.9)

    def test_cuenta_lo_que_va_fuera_de_fecha(self):
        import datetime

        vencida = viga(codigo="V-TARDE")
        vencida.fecha_compromiso = timezone.localdate() - datetime.timedelta(days=3)
        vencida.save()
        viga(codigo="V-HOY")

        resumen = panorama.resumen(panorama.lo_que_se_esta_haciendo())

        assert resumen["vencidas"] == 1


class TestLaPantalla:
    def test_pide_sesion(self):
        respuesta = Client(SERVER_NAME="127.0.0.1").get(reverse("produccion:control"))
        assert respuesta.status_code == 302

    def test_ensena_las_dos_lineas(self, django_user_model):
        viga(codigo="V-42")
        orden_herreria(codigo="H-42")

        pagina = navegador(django_user_model).get(reverse("produccion:control")).content.decode()

        assert "V-42" in pagina and "H-42" in pagina
        assert "12/30 terminadas" not in pagina  # 0 terminadas
        assert "0/30 terminadas" in pagina

    def test_se_puede_filtrar_por_linea(self, django_user_model):
        viga(codigo="V-42")
        orden_herreria(codigo="H-42")

        respuesta = navegador(django_user_model).get(
            reverse("produccion:control") + "?linea=herreria"
        )

        assert [r["codigo"] for r in respuesta.context["renglones"]] == ["H-42"]

    def test_el_conteo_de_las_pestanas_no_se_filtra_a_si_mismo(self, django_user_model):
        """Si se calculara sobre lo filtrado, al entrar en Herrería las otras
        pestañas dirían cero y parecería que no hay nada más en el taller."""
        viga(codigo="V-42")
        orden_herreria(codigo="H-42")

        respuesta = navegador(django_user_model).get(
            reverse("produccion:control") + "?linea=herreria"
        )

        assert respuesta.context["conteo_por_linea"]["estructuras"] == 1
        assert respuesta.context["total_sin_filtrar"] == 2

    def test_una_linea_inventada_se_ignora(self, django_user_model):
        viga(codigo="V-42")

        respuesta = navegador(django_user_model).get(
            reverse("produccion:control") + "?linea=inventada"
        )

        assert respuesta.context["linea"] == ""
        assert len(respuesta.context["renglones"]) == 1

    def test_se_puede_buscar_por_codigo(self, django_user_model):
        viga(codigo="V-42")
        viga(codigo="V-99")

        respuesta = navegador(django_user_model).get(
            reverse("produccion:control") + "?q=V-42"
        )

        assert [r["codigo"] for r in respuesta.context["renglones"]] == ["V-42"]

    def test_vacia_lo_explica(self, django_user_model):
        pagina = navegador(django_user_model).get(reverse("produccion:control")).content.decode()

        assert "no tiene nada en producción" in pagina

    def test_cada_renglon_lleva_a_la_pantalla_de_su_linea(self, django_user_model):
        """El panorama es de lectura: enseña qué hay y manda al sitio donde se
        trabaja."""
        orden_herreria(codigo="H-42")

        pagina = navegador(django_user_model).get(reverse("produccion:control")).content.decode()

        assert reverse("catalogos:herreria_control") in pagina
