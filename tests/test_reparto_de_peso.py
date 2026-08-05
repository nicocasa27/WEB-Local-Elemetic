"""A quién se le apunta el peso de una pieza.

El tablero tiene tres tablas de «Detalle por persona», una por etapa, y hasta
ahora no eran comparables entre sí: Robótica y Herrería repartían el peso de
una orden entre quienes la hicieron, y Estructuras se lo daba **entero a cada
uno**. Tres personas que armaron una viga de cien kilos salían con cien kilos
cada una y el tablero decía que el taller había producido trescientos.

Se reparte a partes iguales. Es lo único defendible sin medir el tiempo de
cada quien, y es lo que ya hacían las otras dos líneas.
"""

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse
from django.utils import timezone

pytestmark = pytest.mark.django_db(databases=["default", "mes"])


def equipo(nombre="Cuadrilla Soldadura A", area="Soldadura"):
    from catalogos.models import EquipoTrabajo

    return EquipoTrabajo.objects.get_or_create(
        nombre=nombre, defaults={"area": area, "integrantes": 3}
    )[0]


def persona(nombre, rol="Soldador"):
    from catalogos.models import Colaborador

    return Colaborador.objects.create(
        nombre=nombre, rol=rol, equipo=equipo(), activo=True
    )


def viga(peso, estado="Armado", codigo="V-1"):
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
        peso_kg=peso,
        fecha_creacion=timezone.now(),
        ultimo_cambio=timezone.now(),
    )


def asignar(la_viga, quien, etapa="Soldadura"):
    from catalogos.models import VigaAsignacion

    return VigaAsignacion.objects.create(
        viga_internal_id=la_viga.internal_id,
        etapa=etapa,
        rol=quien.rol,
        colaborador=quien,
        vigente=True,
    )


def tablero(django_user_model):
    jefa = django_user_model.objects.create_user("jefa", password="x")
    jefa.groups.add(Group.objects.get_or_create(name="admin_general")[0])
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(jefa)
    return cliente.get(reverse("produccion:dashboard")).context["quien_hace_que"]


class TestElPesoSeReparte:
    def test_entre_tres_le_toca_un_tercio_a_cada_uno(self, django_user_model):
        la_viga = viga(peso=100)
        gente = [persona(f"Persona {i}") for i in range(3)]
        for quien in gente:
            asignar(la_viga, quien)

        filas = tablero(django_user_model)["Soldadura"]

        assert len(filas) == 3
        for fila in filas:
            assert fila["ton"] == pytest.approx(0.033, abs=0.001)

    def test_la_suma_es_el_peso_de_la_pieza_no_su_multiplo(self, django_user_model):
        """La comprobación que importa: el taller no produce el triple por
        poner a tres personas en la misma viga."""
        la_viga = viga(peso=900)
        for i in range(3):
            asignar(la_viga, persona(f"Persona {i}"))

        filas = tablero(django_user_model)["Soldadura"]

        assert sum(f["ton"] for f in filas) == pytest.approx(0.9, abs=0.002)

    def test_una_sola_persona_se_lleva_la_pieza_entera(self, django_user_model):
        la_viga = viga(peso=250)
        asignar(la_viga, persona("Única"))

        filas = tablero(django_user_model)["Soldadura"]

        assert filas[0]["ton"] == pytest.approx(0.25, abs=0.001)

    def test_cada_etapa_reparte_por_su_cuenta(self, django_user_model):
        """Dos en soldadura y uno en corte: al de corte le toca la viga
        entera, a los de soldadura la mitad a cada uno."""
        la_viga = viga(peso=100)
        asignar(la_viga, persona("Cortador", rol="Operador"), etapa="Corte")
        asignar(la_viga, persona("Soldador A"))
        asignar(la_viga, persona("Soldador B"))

        quien = tablero(django_user_model)

        assert quien["Corte"][0]["ton"] == pytest.approx(0.1, abs=0.001)
        assert [f["ton"] for f in quien["Soldadura"]] == [
            pytest.approx(0.05, abs=0.001),
            pytest.approx(0.05, abs=0.001),
        ]

    def test_las_piezas_se_siguen_contando_enteras(self, django_user_model):
        """Se reparte el peso, no el conteo: los tres trabajaron en una pieza,
        y ninguno trabajó en un tercio de pieza."""
        la_viga = viga(peso=100)
        for i in range(3):
            asignar(la_viga, persona(f"Persona {i}"))

        filas = tablero(django_user_model)["Soldadura"]

        assert all(f["piezas"] == 1 for f in filas)

    def test_una_asignacion_retirada_no_diluye_a_los_demas(self, django_user_model):
        la_viga = viga(peso=100)
        asignar(la_viga, persona("Se queda"))
        retirada = asignar(la_viga, persona("Se fue"))
        retirada.vigente = False
        retirada.save()

        filas = tablero(django_user_model)["Soldadura"]

        assert len(filas) == 1
        assert filas[0]["ton"] == pytest.approx(0.1, abs=0.001)


class TestUnaPiezaSeCuentaUnaVez:
    def test_terminarla_cuenta_el_dia_que_se_termina_y_no_mas(self):
        """El otro doble conteo, el de las toneladas del taller: una pieza que
        pasó por corte, soldadura y pintura no son tres piezas."""
        from core import metricas
        from produccion.models import ProductionLog

        la_viga = viga(peso=1000, estado="Terminado")
        hoy = timezone.localdate()
        for etapa in ("Corte", "Soldadura", "Pintura", "Terminado"):
            ProductionLog.objects.create(
                viga_internal=la_viga,
                fecha_operacion=hoy,
                estado_anterior="",
                estado_nuevo=etapa,
                comentario="",
                timestamp=timezone.now(),
            )

        toneladas = metricas.toneladas_terminadas(hoy, hoy + __import__("datetime").timedelta(days=1))

        assert toneladas == pytest.approx(1.0)

    def test_dos_apuntes_del_mismo_dia_tampoco_la_duplican(self):
        """Pasa cuando alguien corrige un movimiento."""
        from core import metricas
        from produccion.models import ProductionLog

        la_viga = viga(peso=1000, estado="Terminado")
        hoy = timezone.localdate()
        for _ in range(2):
            ProductionLog.objects.create(
                viga_internal=la_viga,
                fecha_operacion=hoy,
                estado_anterior="Pintura",
                estado_nuevo="Terminado",
                comentario="",
                timestamp=timezone.now(),
            )

        toneladas = metricas.toneladas_terminadas(hoy, hoy + __import__("datetime").timedelta(days=1))

        assert toneladas == pytest.approx(1.0)
