"""Por qué etapas pasa cada orden.

No todas pasan por todas: hay piezas que se cortan, se sueldan y se entregan
sin pintar. La secuencia estaba configurada **por línea**, así que no había
forma de decirlo. En el taller se pasaba la pieza por pintura igual y se
declaraba sin pintar nada: el sistema registraba una etapa que no ocurrió, y
todo lo que se calcula encima —cuánto falta, cuánto tardó, cuánto costó, quién
lo hizo— quedaba apoyado en un dato falso.
"""

import pytest
from django.core.management import call_command
from django.utils import timezone
from io import StringIO

from core import estados
from core.servicios import ruta

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

VIGAS = "Viga"


def viga(estado="Soldadura", codigo="V-1"):
    from produccion.models import Viga

    return Viga.objects.create(
        codigo_viga=codigo,
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


def volcada(pieza):
    """Deja la pieza con su fila en el núcleo, que es donde vive la ruta."""
    call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
    call_command("backfill_nucleo", "--linea", "vigas", verbosity=0, stdout=StringIO())
    return pieza


class TestArmarLaRuta:
    def test_sin_marcar_nada_es_la_de_siempre(self):
        """Una orden que no pasa por ninguna etapa no es una orden: lo más
        probable es un formulario mandado sin tocar las casillas."""
        assert ruta.armar([]) == ruta.secuencia_completa()

    def test_quitar_pintura_quita_tambien_su_espera(self):
        """Dejar la cola de una etapa que no se hace es dejar la pieza
        esperando a nadie."""
        armada = ruta.armar(["Corte", "Armado", "Soldadura"])

        assert estados.PINTURA not in armada
        assert estados.ESPERA_PINTURA not in armada
        assert armada[-1] == estados.TERMINADO

    def test_solo_corte_y_soldadura(self):
        assert ruta.armar(["Corte", "Soldadura"]) == [
            estados.ESPERA_CORTE,
            estados.CORTE,
            estados.ESPERA_SOLDADURA,
            estados.SOLDADURA,
            estados.TERMINADO,
        ]

    def test_terminado_no_se_puede_quitar(self):
        """No es trabajo de taller: es el cierre."""
        assert estados.TERMINADO in ruta.armar(["Corte"])

    def test_enviado_nunca_entra(self):
        """Enviar es de logística, no de producción."""
        assert estados.ENVIADO not in ruta.armar(["Corte", "Pintura"])

    def test_el_orden_se_respeta(self):
        """Marcarlas al revés no invierte el proceso."""
        assert ruta.armar(["Pintura", "Corte"]) == ruta.armar(["Corte", "Pintura"])

    def test_una_etapa_inventada_se_ignora(self):
        assert ruta.armar(["Corte", "Galvanizado"]) == ruta.armar(["Corte"])

    def test_las_casillas_vuelven_como_estaban(self):
        marcadas = ["Corte", "Soldadura"]

        assert ruta.etapas_de_trabajo(ruta.armar(marcadas)) == marcadas

    def test_sin_ruta_las_casillas_salen_todas(self):
        assert ruta.etapas_de_trabajo([]) == ruta.CONFIGURABLES


class TestGuardarYLeer:
    def test_se_guarda_y_se_lee(self):
        pieza = volcada(viga())

        guardada = ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Soldadura"])

        assert guardada == ruta.armar(["Corte", "Soldadura"])
        assert ruta.de(VIGAS, pieza.internal_id) == guardada

    def test_la_ruta_completa_se_guarda_como_vacia(self):
        """Para distinguir lo que alguien decidió de lo que nadie tocó."""
        from nucleo.models import OrdenProduccion

        pieza = volcada(viga())

        ruta.guardar(VIGAS, pieza.internal_id, ruta.CONFIGURABLES)

        orden = OrdenProduccion.objects.using("mes").get(
            legacy_modelo=VIGAS, legacy_id=pieza.internal_id
        )
        assert orden.ruta == []
        assert ruta.de(VIGAS, pieza.internal_id) == ruta.secuencia_completa()

    def test_sin_ruta_responde_la_de_siempre(self):
        pieza = volcada(viga())

        assert ruta.de(VIGAS, pieza.internal_id) == ruta.secuencia_completa()

    def test_una_orden_sin_fila_en_el_nucleo_no_se_rompe(self):
        """Pasa si se creó con la escritura doble apagada. La función nueva
        sólo puede quitar etapas, nunca añadirlas ni fallar."""
        assert ruta.de(VIGAS, 999999) == ruta.secuencia_completa()
        assert ruta.de("", None) == ruta.secuencia_completa()

    def test_y_guardar_lo_dice_en_vez_de_fingir(self):
        """Una configuración que la pantalla acepta y el sistema ignora es
        peor que un error."""
        assert ruta.guardar(VIGAS, 999999, ["Corte"]) is None


class TestLaSiguienteEtapa:
    def test_sin_pintura_de_soldadura_se_va_a_terminado(self):
        """Es lo que hace útil la ruta."""
        pieza = volcada(viga(estado="Soldadura"))
        ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Armado", "Soldadura"])

        assert ruta.siguiente(VIGAS, pieza.internal_id, "Soldadura") == estados.TERMINADO

    def test_con_la_ruta_completa_se_va_a_espera_de_pintura(self):
        pieza = volcada(viga(estado="Soldadura"))

        assert (
            ruta.siguiente(VIGAS, pieza.internal_id, "Soldadura")
            == estados.ESPERA_PINTURA
        )

    def test_desde_la_ultima_no_hay_siguiente(self):
        pieza = volcada(viga(estado="Terminado"))

        assert ruta.siguiente(VIGAS, pieza.internal_id, "Terminado") == ""

    def test_una_pieza_en_una_etapa_que_su_ruta_no_contempla_no_queda_atascada(self):
        """Pasa al recortar la ruta de algo que ya iba por en medio. Sin esto
        la pieza se queda sin ningún botón y hay que arreglarla por la base."""
        pieza = volcada(viga(estado="Pintura"))
        ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Soldadura"])

        assert ruta.siguiente(VIGAS, pieza.internal_id, "Pintura") == estados.TERMINADO

    def test_una_etapa_que_no_existe_no_revienta(self):
        pieza = volcada(viga())

        assert ruta.siguiente(VIGAS, pieza.internal_id, "Galvanizado") == ""


class TestElAvanceSeMideSobreSuRuta:
    def test_sin_pintura_soldadura_es_el_ochenta_por_ciento(self):
        pieza = volcada(viga(estado="Soldadura"))
        ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Armado", "Soldadura"])

        # espera_corte, corte, espera_armado, armado, espera_soldadura,
        # soldadura, terminado -> soldadura es la sexta de siete.
        assert ruta.avance(VIGAS, pieza.internal_id, "Soldadura") == 83

    def test_con_la_ruta_completa_es_menos(self):
        pieza = volcada(viga(estado="Soldadura"))

        assert ruta.avance(VIGAS, pieza.internal_id, "Soldadura") == 62

    def test_terminado_es_el_cien_por_cien_en_cualquier_ruta(self):
        """Una lista de control llena de órdenes que nunca llegan al final
        deja de leerse."""
        pieza = volcada(viga(estado="Terminado"))
        ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Soldadura"])

        assert ruta.avance(VIGAS, pieza.internal_id, "Terminado") == 100


def navegador(django_user_model, nombre="jefa", grupo="admin_general"):
    from django.contrib.auth.models import Group
    from django.test import Client

    persona = django_user_model.objects.create_user(nombre, password="x")
    if grupo:
        persona.groups.add(Group.objects.get_or_create(name=grupo)[0])
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


class TestLaPantallaDeRuta:
    def test_pide_sesion(self):
        from django.test import Client
        from django.urls import reverse

        respuesta = Client(SERVER_NAME="127.0.0.1").get(
            reverse("produccion:ruta", args=["estructuras", 1])
        )
        assert respuesta.status_code == 302

    def test_el_piso_no_decide_la_ruta(self, django_user_model):
        """No es del piso: es de quien recibe el pedido y sabe qué acordó con
        el cliente. Un operador que quitara pintura de una orden estaría
        cambiando lo que se vendió."""
        from django.urls import reverse

        pieza = volcada(viga())
        cliente = navegador(django_user_model, "juan", grupo="soldadura")

        respuesta = cliente.get(
            reverse("produccion:ruta", args=["estructuras", pieza.internal_id])
        )

        assert respuesta.status_code == 302

    def test_ensena_las_casillas_marcadas(self, django_user_model):
        from django.urls import reverse

        pieza = volcada(viga())
        ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Soldadura"])

        respuesta = navegador(django_user_model).get(
            reverse("produccion:ruta", args=["estructuras", pieza.internal_id])
        )

        assert respuesta.context["marcadas"] == ["Corte", "Soldadura"]
        assert respuesta.context["es_la_de_siempre"] is False

    def test_sin_ruta_salen_todas_marcadas(self, django_user_model):
        from django.urls import reverse

        pieza = volcada(viga())

        respuesta = navegador(django_user_model).get(
            reverse("produccion:ruta", args=["estructuras", pieza.internal_id])
        )

        assert respuesta.context["marcadas"] == ruta.CONFIGURABLES
        assert respuesta.context["es_la_de_siempre"] is True

    def test_se_guarda_desde_la_pantalla(self, django_user_model):
        from django.urls import reverse

        pieza = volcada(viga())

        navegador(django_user_model).post(
            reverse("produccion:ruta_guardar", args=["estructuras", pieza.internal_id]),
            {"etapas": ["Corte", "Soldadura"]},
        )

        assert ruta.de(VIGAS, pieza.internal_id) == ruta.armar(["Corte", "Soldadura"])

    def test_lo_dice_cuando_no_hay_donde_guardarla(self, django_user_model):
        """Una configuración que la pantalla acepta y el sistema ignora es
        peor que un error. Pasa con la escritura doble apagada."""
        from django.urls import reverse

        pieza = viga()  # sin volcar: no tiene fila en el núcleo

        respuesta = navegador(django_user_model).post(
            reverse("produccion:ruta_guardar", args=["estructuras", pieza.internal_id]),
            {"etapas": ["Corte"]},
            follow=True,
        )

        assert "no se puede guardar" in respuesta.content.decode()

    def test_una_orden_que_no_existe_no_revienta(self, django_user_model):
        from django.urls import reverse

        respuesta = navegador(django_user_model).get(
            reverse("produccion:ruta", args=["estructuras", 999999])
        )

        assert respuesta.status_code == 302

    def test_una_linea_inventada_tampoco(self, django_user_model):
        respuesta = navegador(django_user_model).get("/control/inventada/1/ruta/")

        assert respuesta.status_code == 302


class TestElCasoCompleto:
    """Lo que pidió el taller, de punta a punta: una pieza que se corta, se
    suelda y se entrega sin pintar."""

    def test_el_soldador_la_cierra_sin_pasarla_por_pintura(self, django_user_model):
        from django.urls import reverse

        from produccion.models import Viga

        pieza = volcada(viga(estado="Soldadura", codigo="V-SIN-PINTURA"))
        # Ventas configura la ruta al recibir el pedido.
        navegador(django_user_model).post(
            reverse("produccion:ruta_guardar", args=["estructuras", pieza.internal_id]),
            {"etapas": ["Corte", "Armado", "Soldadura"]},
        )

        # El soldador abre su pantalla: el botón dice «Terminado», no
        # «Espera de pintura».
        soldador = navegador(django_user_model, "juan", grupo="soldadura")
        trabajos = soldador.get(reverse("produccion:movil")).context["trabajos"]
        trabajo = next(t for t in trabajos if t["codigo"] == "V-SIN-PINTURA")
        assert trabajo["siguiente"] == estados.TERMINADO

        # Y el servidor se lo acepta, aunque «Terminado» sea de pintura.
        respuesta = soldador.post(
            trabajo["url_avance"],
            {
                "estado_nuevo": trabajo["siguiente"],
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
            },
        )

        assert respuesta.status_code == 200, respuesta.content
        assert Viga.objects.get(internal_id=pieza.internal_id).estado == estados.TERMINADO

    def test_sin_ruta_recortada_sigue_yendo_a_pintura(self, django_user_model):
        """La función nueva sólo puede quitar etapas, nunca cambiar lo que ya
        funcionaba."""
        from django.urls import reverse

        volcada(viga(estado="Soldadura", codigo="V-NORMAL"))
        soldador = navegador(django_user_model, "juan", grupo="soldadura")

        trabajos = soldador.get(reverse("produccion:movil")).context["trabajos"]
        trabajo = next(t for t in trabajos if t["codigo"] == "V-NORMAL")

        assert trabajo["siguiente"] == estados.ESPERA_PINTURA

    def test_el_panorama_la_marca(self, django_user_model):
        from django.urls import reverse

        pieza = volcada(viga(estado="Soldadura"))
        ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Armado", "Soldadura"])

        pagina = navegador(django_user_model).get(reverse("produccion:control")).content.decode()

        assert "Ruta propia" in pagina


class TestLaExcepcionDeLaRutaNoAbreLaPuerta:
    """Quien es dueño de una etapa puede completarla, lleve su ruta a donde la
    lleve. Esa excepción es necesaria —si no, una pieza sin pintura deja al
    soldador atascado— pero tiene que ser estrecha.

    La primera versión no lo era: valía para cualquier destino que la ruta
    pusiera después, y como en una ruta normal la siguiente de «Espera de
    pintura» es «Pintura», un soldador podía meterse a pintar. Justo lo
    contrario de separar las áreas.
    """

    def _cliente(self, django_user_model, nombre, grupo):
        return navegador(django_user_model, nombre, grupo=grupo)

    def _avanzar(self, cliente, pieza, destino):
        from django.urls import reverse

        return cliente.post(
            reverse("produccion:viga_change_status_json", args=[pieza.internal_id]),
            {
                "estado_nuevo": destino,
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
            },
        )

    def test_el_soldador_no_entra_a_pintura_por_la_puerta_de_atras(
        self, django_user_model
    ):
        self._cliente(django_user_model, "diana", "pintura")  # hay pintores
        pieza = volcada(viga(estado="Espera de pintura"))
        soldador = self._cliente(django_user_model, "juan", "soldadura")

        assert self._avanzar(soldador, pieza, "Pintura").status_code == 403

    def test_pero_sí_cierra_una_que_no_lleva_pintura(self, django_user_model):
        self._cliente(django_user_model, "diana", "pintura")
        pieza = volcada(viga(estado="Soldadura"))
        ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Armado", "Soldadura"])
        soldador = self._cliente(django_user_model, "juan", "soldadura")

        respuesta = self._avanzar(soldador, pieza, estados.TERMINADO)

        assert respuesta.status_code == 200, respuesta.content

    def test_y_no_le_deja_saltarse_dos_etapas(self, django_user_model):
        """La excepción es para el destino exacto de su ruta, no para
        cualquiera que quede por delante."""
        pieza = volcada(viga(estado="Corte"))
        ruta.guardar(VIGAS, pieza.internal_id, ["Corte", "Armado", "Soldadura"])
        cortador = self._cliente(django_user_model, "luis", "corte")

        assert self._avanzar(cortador, pieza, estados.TERMINADO).status_code == 403
