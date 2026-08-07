"""Cuánto tarda cada quien, y dónde se queda parado el material.

El tablero contestaba cuánto se produjo. No contestaba nada de lo que el
taller pregunta a diario: cuánto tarda esta persona en soldar una pieza, cuánto
tiempo pasa entre que algo se termina de cortar y alguien lo empieza a armar, y
quién entrega piezas que hay que rehacer.

No hizo falta un cronómetro: el cronómetro es la diferencia entre dos apuntes
seguidos de la misma pieza, y los apuntes ya se escribían en cada avance.

Dos decisiones que estas pruebas fijan porque son las que hacen que el número
signifique algo:

- **La mediana manda, no el promedio.** Un corte que se empieza un viernes a
  las cuatro y se cierra el lunes a las ocho son 64 horas, y con el promedio le
  hunde el mes a esa persona. Mientras no exista un calendario laboral que
  descuente noches y fines de semana, el promedio no puede decidir nada.
- **El tiempo se le apunta a quien cierra la etapa**, que es quien afirma que
  ese trabajo es suyo y quien firma la entrega.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core import estados
from core.servicios import rendimiento as servicio
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def apunte(referencia, etapa, cuando, actor, etapa_anterior=""):
    from catalogos.models import ApunteDeTrabajo, SeguimientoDespacho

    return ApunteDeTrabajo.objects.using(BASE).create(
        linea=SeguimientoDespacho.Linea.VIGAS,
        referencia=referencia,
        codigo="ZZ-1",
        etapa=etapa,
        etapa_anterior=etapa_anterior,
        actor=actor,
        ocurrido_en=cuando,
    )


def pieza(estado=estados.CORTE, peso=100):
    from produccion.models import Viga

    return Viga.objects.create(
        codigo_viga="ZZ-1",
        pieza_no=1,
        total_piezas=1,
        proyecto="OBRA PRUEBA",
        descripcion="",
        fecha_compromiso=timezone.localdate(),
        estado=estado,
        observaciones="",
        prioridad=1,
        peso_kg=peso,
        fecha_creacion=timezone.now(),
        ultimo_cambio=timezone.now(),
    )


@pytest.fixture
def rango():
    ahora = timezone.now()
    return ahora - timedelta(days=30), ahora + timedelta(days=1)


class TestElTiempoSaleDeLosApuntes:
    def test_lo_que_tarda_una_etapa_es_el_hueco_entre_dos_apuntes(self, rango):
        desde, hasta = rango
        la_pieza = pieza()
        empezó = timezone.now() - timedelta(hours=2)
        apunte(la_pieza.internal_id, estados.CORTE, empezó, "zz_juan")
        apunte(
            la_pieza.internal_id,
            estados.ESPERA_ARMADO,
            empezó + timedelta(minutes=42),
            "zz_juan",
        )

        filas = servicio.por_persona(desde, hasta)

        assert len(filas) == 1
        assert filas[0].usuario == "zz_juan"
        assert filas[0].etapa == estados.CORTE
        assert filas[0].tiempos.mediana == pytest.approx(42 * 60)

    def test_se_le_apunta_a_quien_cierra_la_etapa(self, rango):
        """Es quien pulsa «Terminé corte»: quien afirma que el trabajo es suyo."""
        desde, hasta = rango
        la_pieza = pieza()
        empezó = timezone.now() - timedelta(hours=2)
        apunte(la_pieza.internal_id, estados.CORTE, empezó, "zz_abre")
        apunte(
            la_pieza.internal_id,
            estados.ESPERA_ARMADO,
            empezó + timedelta(minutes=30),
            "zz_cierra",
        )

        filas = servicio.por_persona(desde, hasta)

        assert [f.usuario for f in filas] == ["zz_cierra"]

    def test_una_etapa_sin_cerrar_todavía_no_cuenta(self, rango):
        """Lo que está en curso no es una medición: es trabajo a medias."""
        desde, hasta = rango
        la_pieza = pieza()
        apunte(la_pieza.internal_id, estados.CORTE, timezone.now(), "zz_juan")

        assert servicio.por_persona(desde, hasta) == []

    def test_dos_apuntes_a_la_misma_hora_no_son_un_tramo(self, rango):
        """Un avance en lote escribe una fila por pieza en el mismo instante."""
        desde, hasta = rango
        la_pieza = pieza()
        ahora = timezone.now()
        apunte(la_pieza.internal_id, estados.CORTE, ahora, "zz_juan")
        apunte(la_pieza.internal_id, estados.ESPERA_ARMADO, ahora, "zz_juan")

        assert servicio.por_persona(desde, hasta) == []

    def test_un_tramo_que_empieza_antes_del_rango_cuenta_donde_se_cerró(self):
        """Si no, todo lo que cruza la medianoche desaparecería del informe."""
        ahora = timezone.now()
        la_pieza = pieza()
        apunte(la_pieza.internal_id, estados.CORTE, ahora - timedelta(days=3), "zz_juan")
        apunte(
            la_pieza.internal_id, estados.ESPERA_ARMADO, ahora - timedelta(hours=1), "zz_juan"
        )

        filas = servicio.por_persona(ahora - timedelta(days=1), ahora + timedelta(days=1))

        assert len(filas) == 1


class TestLaMedianaMandaSobreElPromedio:
    def test_un_fin_de_semana_no_le_hunde_el_número_a_nadie(self, rango):
        """Cinco cortes de media hora y uno que se quedó abierto el fin de semana.

        Para el promedio son once horas de corte de media. Para la mediana,
        media hora, que es lo que de verdad tarda esa persona.
        """
        desde, hasta = rango
        base = timezone.now() - timedelta(days=10)
        for i in range(5):
            la_pieza = pieza()
            arranque = base + timedelta(hours=i)
            apunte(la_pieza.internal_id, estados.CORTE, arranque, "zz_juan")
            apunte(
                la_pieza.internal_id,
                estados.ESPERA_ARMADO,
                arranque + timedelta(minutes=30),
                "zz_juan",
            )
        colgada = pieza()
        apunte(colgada.internal_id, estados.CORTE, base, "zz_juan")
        apunte(colgada.internal_id, estados.ESPERA_ARMADO, base + timedelta(hours=64), "zz_juan")

        fila = servicio.por_persona(desde, hasta)[0]

        assert fila.tiempos.mediana == pytest.approx(30 * 60)
        assert fila.tiempos.promedio > 2 * 3600
        assert fila.tiempos.peor == pytest.approx(64 * 3600)


class TestDóndeSeParaElMaterial:
    def test_la_espera_entre_áreas_no_es_de_nadie(self, rango):
        """Es material parado, y es donde se pierden los días de un pedido."""
        desde, hasta = rango
        la_pieza = pieza()
        base = timezone.now() - timedelta(days=2)
        apunte(la_pieza.internal_id, estados.ESPERA_ARMADO, base, "zz_juan")
        apunte(la_pieza.internal_id, estados.ARMADO, base + timedelta(hours=6), "zz_pedro")

        filas = servicio.esperas(desde, hasta)

        assert [f.etapa for f in filas] == [estados.ESPERA_ARMADO]
        assert filas[0].tiempos.mediana == pytest.approx(6 * 3600)

    def test_las_esperas_no_salen_en_el_rendimiento_de_nadie(self, rango):
        desde, hasta = rango
        la_pieza = pieza()
        base = timezone.now() - timedelta(days=2)
        apunte(la_pieza.internal_id, estados.ESPERA_ARMADO, base, "zz_juan")
        apunte(la_pieza.internal_id, estados.ARMADO, base + timedelta(hours=6), "zz_pedro")

        assert servicio.por_persona(desde, hasta) == []

    def test_lo_parado_ahora_se_cuenta_desde_el_último_cambio(self):
        la_pieza = pieza(estados.ESPERA_ARMADO)
        la_pieza.ultimo_cambio = timezone.now() - timedelta(hours=30)
        la_pieza.save()

        filas = servicio.parado_ahora()

        de_armado = [f for f in filas if f["etapa"] == estados.ESPERA_ARMADO]
        assert de_armado
        assert de_armado[0]["la_que_mas"] > 29 * 3600


class TestQuiénEntregaBien:
    def crear_acta(self, **campos):
        from nucleo.models import ActaDeEntrega

        datos = {
            "legacy_modelo": "Viga",
            "legacy_id": 1,
            "codigo": "ZZ-1",
            "area_origen": "Corte",
            "area_destino": "Soldadura",
            "etapa_origen": estados.CORTE,
            "etapa_destino": estados.ESPERA_ARMADO,
            "entrega_por": "zz_juan",
            "entregado_en": timezone.now() - timedelta(days=1),
            "estado": ActaDeEntrega.Estado.ACEPTADA,
            "recibe_por": "zz_pedro",
            "recibido_en": timezone.now(),
        }
        datos.update(campos)
        return ActaDeEntrega.objects.using(BASE).create(**datos)

    def test_una_entrega_aceptada_cuenta_a_favor_de_quien_la_hizo(self, rango):
        desde, hasta = rango
        self.crear_acta()

        filas = {f.usuario: f for f in servicio.calidad(desde, hasta)}

        assert filas["zz_juan"].entregas_buenas == 1
        assert filas["zz_juan"].porcentaje_bueno == 100

    def test_devolver_cuenta_a_favor_de_quien_devuelve(self, rango):
        """Y en contra de quien entregó.

        Es lo que sostiene todo el mecanismo: si devolver contara en contra,
        nadie devolvería nada y en una semana todas las actas serían
        aceptaciones automáticas, que es lo mismo que no tenerlas.
        """
        from nucleo.models import ActaDeEntrega

        desde, hasta = rango
        self.crear_acta(estado=ActaDeEntrega.Estado.RECHAZADA, motivo="miden 90 cm")

        filas = {f.usuario: f for f in servicio.calidad(desde, hasta)}

        assert filas["zz_juan"].devueltas == 1
        assert filas["zz_juan"].detectadas == 0
        assert filas["zz_pedro"].detectadas == 1
        assert filas["zz_pedro"].devueltas == 0

    def test_quien_la_dio_por_buena_también_responde(self, rango):
        """El «que la cobren entre los dos» del taller.

        Corte entrega y el soldador firma que está bien. El soldador la entrega
        a pintura y pintura la devuelve. Responden el soldador por entregarla
        así, y el soldador otra vez por haberla aceptado de corte diciendo que
        estaba correcta.
        """
        from nucleo.models import ActaDeEntrega

        desde, hasta = rango
        base = timezone.now() - timedelta(days=2)
        self.crear_acta(entregado_en=base, entrega_por="zz_cortador", recibe_por="zz_soldador")
        self.crear_acta(
            entregado_en=base + timedelta(hours=4),
            area_origen="Soldadura",
            area_destino="Pintura",
            entrega_por="zz_soldador",
            recibe_por="zz_pintor",
            estado=ActaDeEntrega.Estado.RECHAZADA,
            motivo="mal soldada",
        )

        filas = {f.usuario: f for f in servicio.calidad(desde, hasta)}

        assert filas["zz_soldador"].devueltas == 1
        assert filas["zz_soldador"].dio_por_buenas_y_salieron_mal == 1
        assert filas["zz_pintor"].detectadas == 1
        # El cortador no responde: su entrega la aceptaron y nadie la devolvió.
        assert filas["zz_cortador"].devueltas == 0


class TestLaPantalla:
    def test_no_la_abre_cualquiera(self, client, django_user_model):
        """Enseña el nombre de cada quien con su tiempo al lado."""
        from django.contrib.auth.models import Group
        from django.urls import reverse

        soldador = django_user_model.objects.create_user(
            username="zz_soldador", password="prueba"
        )
        soldador.groups.add(Group.objects.get_or_create(name="soldadura")[0])
        client.force_login(soldador)

        respuesta = client.get(reverse("produccion:rendimiento"))

        assert respuesta.status_code == 302

    def test_la_ve_quien_dirige(self, client, django_user_model):
        from django.contrib.auth.models import Group
        from django.urls import reverse

        jefe = django_user_model.objects.create_user(username="zz_jefe", password="prueba")
        jefe.groups.add(Group.objects.get_or_create(name="admin_general")[0])
        client.force_login(jefe)

        respuesta = client.get(reverse("produccion:rendimiento"))

        assert respuesta.status_code == 200

    def test_sin_datos_lo_dice_en_vez_de_enseñar_una_tabla_vacía(
        self, client, django_user_model
    ):
        """Una pantalla vacía se lee como «nadie trabajó»."""
        from django.contrib.auth.models import Group
        from django.urls import reverse

        jefe = django_user_model.objects.create_user(username="zz_jefe", password="prueba")
        jefe.groups.add(Group.objects.get_or_create(name="admin_general")[0])
        client.force_login(jefe)

        cuerpo = client.get(reverse("produccion:rendimiento")).content.decode()

        assert "Todavía no hay tiempos que medir" in cuerpo
