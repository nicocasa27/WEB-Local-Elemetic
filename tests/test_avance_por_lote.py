"""«De estas cincuenta, hice treinta y dos.»

En Estructuras una orden de cincuenta piezas son **cincuenta renglones**, uno
por pieza, porque el avance se lleva por etapas y no por contadores. Para un
soldador que hizo cuarenta, eso eran cuarenta toques con guantes en un
teléfono: en la práctica se apuntaba en papel y alguien lo capturaba por la
tarde, que es exactamente por lo que el sistema iba siempre por detrás del
taller.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def lote(cuantas=50, estado="Soldadura", codigo="V-LOTE", proyecto="TORRE NORTE"):
    from produccion.models import Viga

    return [
        Viga.objects.create(
            codigo_viga=codigo,
            pieza_no=i + 1,
            total_piezas=cuantas,
            proyecto=proyecto,
            descripcion="viga de 60 cm",
            fecha_compromiso=timezone.localdate(),
            estado=estado,
            prioridad=3,
            peso_kg=20,
            fecha_creacion=timezone.now(),
            ultimo_cambio=timezone.now(),
        )
        for i in range(cuantas)
    ]


def navegador(django_user_model, nombre="juan", grupo="soldadura"):
    persona = django_user_model.objects.create_user(nombre, password="x")
    if grupo:
        persona.groups.add(Group.objects.get_or_create(name=grupo)[0])
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


def avanzar(cliente, codigo, desde, hacia, cuantas):
    return cliente.post(
        reverse("produccion:viga_avanzar_grupo"),
        {
            "codigo": codigo,
            "estado_actual": desde,
            "estado_nuevo": hacia,
            "cantidad": cuantas,
            "fecha_operacion": timezone.localdate().isoformat(),
            "comentario": "",
        },
    )


def cuantas_en(estado, codigo="V-LOTE"):
    from produccion.models import Viga

    return Viga.objects.filter(codigo_viga=codigo, estado=estado).count()


class TestAvanzarUnaParteDelLote:
    def test_treinta_y_dos_de_cincuenta(self, django_user_model):
        lote(50)
        cliente = navegador(django_user_model)

        respuesta = avanzar(cliente, "V-LOTE", "Soldadura", "Espera de pintura", 32)

        assert respuesta.status_code == 200, respuesta.content
        assert respuesta.json()["hechas"] == 32
        assert cuantas_en("Espera de pintura") == 32
        assert cuantas_en("Soldadura") == 18

    def test_dice_cuántas_quedan(self, django_user_model):
        """Para que el soldador sepa lo que le falta sin recargar."""
        lote(50)
        cliente = navegador(django_user_model)

        datos = avanzar(cliente, "V-LOTE", "Soldadura", "Espera de pintura", 32).json()

        assert datos["quedan"] == 18

    def test_el_lote_entero(self, django_user_model):
        lote(50)
        cliente = navegador(django_user_model)

        avanzar(cliente, "V-LOTE", "Soldadura", "Espera de pintura", 50)

        assert cuantas_en("Soldadura") == 0
        assert cuantas_en("Espera de pintura") == 50

    def test_pedir_mas_de_las_que_hay_avanza_las_que_hay(self, django_user_model):
        """No es un error: es alguien que se pasó de largo con el número."""
        lote(5)
        cliente = navegador(django_user_model)

        datos = avanzar(cliente, "V-LOTE", "Soldadura", "Espera de pintura", 999).json()

        assert datos["hechas"] == 5

    def test_deja_bitacora_de_cada_pieza(self, django_user_model):
        """Es lo que hace que el lote no sea un atajo que pierde el rastro."""
        from produccion.models import ProductionLog

        lote(10)
        cliente = navegador(django_user_model)

        avanzar(cliente, "V-LOTE", "Soldadura", "Espera de pintura", 7)

        assert (
            ProductionLog.objects.filter(estado_nuevo="Espera de pintura").count() == 7
        )


class TestLasMismasComprobacionesQueUnaPieza:
    def test_sin_permiso_de_esa_etapa_no_avanza_ninguna(self, django_user_model):
        """Se llama al endpoint de una pieza, así que sus guardas se aplican
        igual. Copiarlas para el lote habría sido la primera copia en
        separarse."""
        lote(10, estado="Pintura")
        cliente = navegador(django_user_model, grupo="corte")

        respuesta = avanzar(cliente, "V-LOTE", "Pintura", "Terminado", 10)

        assert respuesta.status_code == 400
        assert cuantas_en("Pintura") == 10

    def test_corte_exige_equipo_y_no_avanza_a_medias(self, django_user_model):
        """Si falta el equipo va a fallar en las cincuenta: se para en la
        primera en vez de dejar el lote a medio camino."""
        from catalogos.models import Maquina

        Maquina.objects.create(nombre="Plasma CNC 1", tipo="Corte", activo=True)
        lote(10, estado="Espera de corte")
        cliente = navegador(django_user_model, grupo="corte")

        respuesta = avanzar(cliente, "V-LOTE", "Espera de corte", "Corte", 10)

        assert respuesta.status_code == 400
        assert "equipo de corte" in respuesta.json()["error"]
        assert cuantas_en("Espera de corte") == 10

    def test_con_el_equipo_puesto_sí_avanza(self, django_user_model):
        from catalogos.models import Maquina

        maquina = Maquina.objects.create(nombre="Plasma CNC 1", tipo="Corte", activo=True)
        lote(10, estado="Espera de corte")
        cliente = navegador(django_user_model, grupo="corte")

        respuesta = cliente.post(
            reverse("produccion:viga_avanzar_grupo"),
            {
                "codigo": "V-LOTE",
                "estado_actual": "Espera de corte",
                "estado_nuevo": "Corte",
                "cantidad": 6,
                "maquina_id": maquina.id,
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
            },
        )

        assert respuesta.status_code == 200, respuesta.content
        assert cuantas_en("Corte") == 6

    def test_solo_toca_las_de_ese_codigo_y_esa_etapa(self, django_user_model):
        lote(5, codigo="V-A")
        lote(5, codigo="V-B")
        lote(5, codigo="V-A", estado="Corte")
        cliente = navegador(django_user_model)

        avanzar(cliente, "V-A", "Soldadura", "Espera de pintura", 5)

        assert cuantas_en("Soldadura", "V-A") == 0
        assert cuantas_en("Soldadura", "V-B") == 5
        assert cuantas_en("Corte", "V-A") == 5


class TestLoQueNoSePuedePedir:
    def test_pide_sesion(self):
        respuesta = Client(SERVER_NAME="127.0.0.1").post(
            reverse("produccion:viga_avanzar_grupo"), {}
        )
        assert respuesta.status_code == 302

    def test_solo_por_post(self, django_user_model):
        respuesta = navegador(django_user_model).get(
            reverse("produccion:viga_avanzar_grupo")
        )
        assert respuesta.status_code == 405

    @pytest.mark.parametrize(
        "datos",
        [
            {"codigo": "", "estado_actual": "Soldadura", "cantidad": 5},
            {"codigo": "V-LOTE", "estado_actual": "", "cantidad": 5},
            {"codigo": "V-LOTE", "estado_actual": "Soldadura", "cantidad": 0},
            {"codigo": "V-LOTE", "estado_actual": "Soldadura", "cantidad": "muchas"},
        ],
    )
    def test_datos_incompletos(self, django_user_model, datos):
        respuesta = navegador(django_user_model).post(
            reverse("produccion:viga_avanzar_grupo"),
            {**datos, "estado_nuevo": "Espera de pintura",
             "fecha_operacion": timezone.localdate().isoformat()},
        )

        assert respuesta.status_code == 400

    def test_cuando_ya_no_queda_ninguna_lo_dice(self, django_user_model):
        """Pasa cuando dos personas capturan el mismo lote a la vez."""
        lote(3)
        cliente = navegador(django_user_model)
        avanzar(cliente, "V-LOTE", "Soldadura", "Espera de pintura", 3)

        respuesta = avanzar(cliente, "V-LOTE", "Soldadura", "Espera de pintura", 3)

        assert respuesta.status_code == 409
        assert "Ya no hay piezas" in respuesta.json()["error"]


class TestLaPantallaLasAgrupa:
    def test_cincuenta_piezas_iguales_son_una_tarjeta(self, django_user_model):
        lote(50)

        trabajos = navegador(django_user_model).get(
            reverse("produccion:movil")
        ).context["trabajos"]

        assert len(trabajos) == 1
        assert trabajos[0]["cuantas"] == 50

    def test_y_pide_el_número(self, django_user_model):
        lote(50)

        pagina = navegador(django_user_model).get(
            reverse("produccion:movil")
        ).content.decode()

        assert "¿Cuántas?" in pagina
        assert 'name="cantidad"' in pagina
        assert 'max="50"' in pagina

    def test_una_sola_pieza_no_pregunta_nada(self, django_user_model):
        """Preguntar «¿cuántas?» sobre una pieza añade un gesto a la acción
        que más se repite en el día."""
        lote(1)

        respuesta = navegador(django_user_model).get(reverse("produccion:movil"))

        assert respuesta.context["trabajos"][0]["cuantas"] == 1
        assert "¿Cuántas?" not in respuesta.content.decode()

    def test_distintas_etapas_son_tarjetas_distintas(self, django_user_model):
        """Dos piezas del mismo código en distinta etapa son dos trabajos y no
        se pueden sumar."""
        lote(3, estado="Soldadura")
        lote(2, estado="Armado")

        trabajos = navegador(django_user_model).get(
            reverse("produccion:movil")
        ).context["trabajos"]

        assert sorted(t["cuantas"] for t in trabajos) == [2, 3]

    def test_el_aviso_de_recorte_cuenta_piezas_no_tarjetas(self, django_user_model):
        """Decir «hay 3 piezas más» cuando hay ciento cincuenta sería peor que
        no decir nada."""
        from produccion.movil import TOPE

        for i in range(TOPE + 2):
            lote(3, codigo=f"V-{i:03d}")

        respuesta = navegador(django_user_model).get(reverse("produccion:movil"))

        # Caben TOPE tarjetas de tres piezas; sobran dos lotes enteros.
        assert len(respuesta.context["trabajos"]) == TOPE
        assert respuesta.context["de_mas"] == 6

    def test_ningún_grupo_sale_partido(self, django_user_model):
        """Con un recorte de piezas, el último grupo se partía: la tarjeta
        decía «2 de 3» habiendo tres, y la tercera no se podía avanzar desde
        ahí."""
        from produccion.movil import TOPE

        for i in range(TOPE + 5):
            lote(3, codigo=f"V-{i:03d}")

        trabajos = navegador(django_user_model).get(
            reverse("produccion:movil")
        ).context["trabajos"]

        assert all(t["cuantas"] == 3 for t in trabajos)


class TestNoSeMezclanDosObras:
    """Dos pedidos distintos pueden usar el mismo código de pieza.

    Sin la obra, «las 12 de la obra Norte» avanzaba las primeras doce de las
    dos obras juntas, y la mitad del avance quedaba apuntado en el pedido
    equivocado.
    """

    def test_la_obra_acota_el_lote(self, django_user_model):
        lote(10, proyecto="TORRE NORTE")
        lote(10, proyecto="NAVE SUR")
        cliente = navegador(django_user_model)

        respuesta = cliente.post(
            reverse("produccion:viga_avanzar_grupo"),
            {
                "codigo": "V-LOTE",
                "proyecto": "NAVE SUR",
                "estado_actual": "Soldadura",
                "estado_nuevo": "Espera de pintura",
                "cantidad": 10,
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
            },
        )

        from produccion.models import Viga

        assert respuesta.json()["hechas"] == 10
        assert (
            Viga.objects.filter(proyecto="TORRE NORTE", estado="Soldadura").count() == 10
        )
        assert Viga.objects.filter(proyecto="NAVE SUR", estado="Soldadura").count() == 0


class TestTambienDesdeLaPC:
    """El avance por cantidades existía sólo en el celular.

    En la PC, un pedido de cincuenta vigas eran cincuenta clics. No era
    urgente —quien captura desde la oficina suele ser supervisión— pero era
    una diferencia entre pantallas de las que acaban en «depende de dónde lo
    abras».
    """

    def _con_next(self, cliente, cuantas, destino="/vigas/"):
        return cliente.post(
            reverse("produccion:viga_avanzar_grupo"),
            {
                "codigo": "V-LOTE",
                "proyecto": "TORRE NORTE",
                "estado_actual": "Soldadura",
                "estado_nuevo": "Espera de pintura",
                "cantidad": cuantas,
                "fecha_operacion": timezone.localdate().isoformat(),
                "comentario": "",
                "next": destino,
            },
        )

    def test_un_formulario_normal_redirige_en_vez_de_devolver_json(
        self, django_user_model
    ):
        """Así funciona aunque el JavaScript falle, que en el taller pasa."""
        lote(10)
        cliente = navegador(django_user_model)

        respuesta = self._con_next(cliente, 4)

        assert respuesta.status_code == 302
        assert respuesta["Location"] == "/vigas/"
        assert cuantas_en("Espera de pintura") == 4

    def test_el_mensaje_dice_cuantas_y_cuantas_quedan(self, django_user_model):
        lote(10)
        cliente = navegador(django_user_model)

        respuesta = self._con_next(cliente, 4)
        texto = " ".join(str(m) for m in respuesta.wsgi_request._messages)

        assert "4 piezas" in texto
        assert "Quedan 6" in texto

    def test_un_error_tambien_se_dice_en_la_pantalla(self, django_user_model):
        """Un formulario que no responde nada es peor que uno que falla."""
        lote(10, estado="Terminado")
        cliente = navegador(django_user_model)

        respuesta = self._con_next(cliente, 4)

        assert respuesta.status_code == 302
        assert "Ya no hay piezas" in " ".join(
            str(m) for m in respuesta.wsgi_request._messages
        )

    def test_la_lista_de_escritorio_ofrece_el_lote(self, django_user_model):
        """El botón sólo aparece cuando de verdad hay más de una igual."""
        lote(10)
        lote(1, codigo="V-SOLA")
        cliente = navegador(django_user_model, nombre="jefa", grupo="admin_general")

        cuerpo = cliente.get(reverse("produccion:viga_list")).content.decode()

        assert "de 10 iguales" in cuerpo
        # Una pieza sola no tiene lote: ofrecerle «de 1 iguales» sería un
        # segundo botón que hace lo mismo que el de al lado.
        assert "de 1 iguales" not in cuerpo
