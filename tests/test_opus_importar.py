"""Del archivo de OPUS al catálogo de materiales.

El lector ya está probado aparte (`test_opus.py`): esto es el paso siguiente,
cruzar las claves y dar de alta lo que falte.

Lo que se comprueba aquí son las decisiones que el archivo real obligó a tomar,
porque ninguna es evidente y las tres se pueden equivocar en silencio:

- una clave repetida se acumula en vez de pisarse,
- los indirectos por porcentaje entran marcados como no inventariables,
- lo que ya existe en el catálogo no se toca.

Y sobre todo: **nunca se importa sin ver antes lo que va a pasar**. Un archivo
mal leído mete material equivocado, y de ahí sale material comprado de más o de
menos.
"""

from decimal import Decimal
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from core import opus, roles
from inventario.models import Material
from inventario.opus_import import agrupar, cotejar
from core.bases import BASE  # noqa: F401

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

Usuario = get_user_model()
ARCHIVO = Path(settings.BASE_DIR) / "tests" / "datos" / "opus_explosion.csv"


@pytest.fixture
def base():
    call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
    call_command("sembrar_inventario", verbosity=0, stdout=StringIO())
    roles.asegurar_grupos()


@pytest.fixture
def almacenista(base):
    persona = Usuario.objects.create_user("marco", password="x")
    persona.groups.set(Group.objects.filter(name=roles.ALMACEN))
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


def subir(cliente, texto=None):
    crudo = (texto or ARCHIVO.read_text(encoding="utf-8")).encode("utf-8")
    return cliente.post(reverse("inventario:opus_importar"), {
        "archivo": SimpleUploadedFile("opus.csv", crudo, content_type="text/csv"),
    })


class TestAgrupar:
    @pytest.fixture
    def partidas(self):
        return opus.leer(ARCHIVO.read_text(encoding="utf-8")).partidas

    def test_una_clave_repetida_se_acumula(self, partidas):
        """`INDIRECTO-F` sale dos veces con costos distintos.

        Dar de alta por clave o revienta contra el índice único o se queda con
        el último renglón. Las dos cosas pierden datos sin decirlo.
        """
        juntas = {e["clave"]: e for e in agrupar(partidas)}
        assert juntas["INDIRECTO-F"]["renglones"] == 2
        assert juntas["INDIRECTO-F"]["cantidad"] == Decimal("0.090000")

    def test_el_costo_se_pondera_por_cantidad(self, partidas):
        """El promedio simple descuadraría el presupuesto: lo que tiene que
        respetarse es el importe total."""
        juntas = {e["clave"]: e for e in agrupar(partidas)}
        entrada = juntas["INDIRECTO-F"]
        assert entrada["costo"] == (
            entrada["importe"] / entrada["cantidad"]
        ).quantize(Decimal("0.0001"))

    def test_los_porcentajes_no_son_inventariables(self, partidas):
        """«(%)m» es un indirecto que OPUS calcula sobre el total. Sin la
        marca, alguien tendría que decir cuántos fletes hay en el estante."""
        juntas = {e["clave"]: e for e in agrupar(partidas)}
        assert juntas["INDIRECTO-F"]["inventariable"] is False
        assert juntas["LAMINA-A"]["inventariable"] is True

    def test_se_queda_con_la_descripcion_mas_larga(self, partidas):
        """Cuando una clave se repite, la descripción más completa es la que
        más sirve para reconocerla en el catálogo."""
        juntas = {e["clave"]: e for e in agrupar(partidas)}
        assert juntas["INDIRECTO-F"]["descripcion"]


class TestCotejar:
    def test_marca_lo_que_ya_existe(self, base):
        Material.objects.using(BASE).create(
            codigo="LAMINA-A", nombre="Ya estaba", nombre_normalizado="YA ESTABA"
        )
        partidas = opus.leer(ARCHIVO.read_text(encoding="utf-8")).partidas

        agrupadas = {e["clave"]: e for e in cotejar(agrupar(partidas))}

        assert agrupadas["LAMINA-A"]["nueva"] is False
        assert agrupadas["CADENA-B"]["nueva"] is True


class TestLaPantalla:
    def test_enseña_lo_que_pasaria_sin_dar_de_alta_nada(self, almacenista):
        """Es la salvaguarda entera: se ve primero, se confirma después."""
        antes = Material.objects.using(BASE).count()

        respuesta = subir(almacenista)

        assert respuesta.status_code == 200
        assert respuesta.context["paso"] == "revisar"
        assert Material.objects.using(BASE).count() == antes

    def test_dice_cuantas_son_nuevas(self, almacenista):
        respuesta = subir(almacenista)
        assert len(respuesta.context["nuevas"]) == 6

    def test_confirmar_las_da_de_alta(self, almacenista):
        respuesta = subir(almacenista)

        almacenista.post(reverse("inventario:opus_importar"), {
            "crudo": respuesta.context["crudo"], "confirmar": "sí",
        })

        assert Material.objects.using(BASE).filter(codigo="CADENA-B").exists()

    def test_el_indirecto_entra_marcado(self, almacenista):
        respuesta = subir(almacenista)
        almacenista.post(reverse("inventario:opus_importar"), {
            "crudo": respuesta.context["crudo"], "confirmar": "sí",
        })

        indirecto = Material.objects.using(BASE).get(codigo="INDIRECTO-F")
        assert indirecto.inventariable is False

    def test_no_pisa_lo_que_ya_estaba(self, almacenista):
        """Un material del catálogo puede tener mínimo y proveedor capturados a
        mano. Pisarlos con lo que trae un presupuesto sería perder ese trabajo
        a cambio de nada."""
        Material.objects.using(BASE).create(
            codigo="LAMINA-A", nombre="Nombre del taller",
            nombre_normalizado="NOMBRE DEL TALLER", stock_minimo=Decimal("25"),
        )

        respuesta = subir(almacenista)
        almacenista.post(reverse("inventario:opus_importar"), {
            "crudo": respuesta.context["crudo"], "confirmar": "sí",
        })

        conservado = Material.objects.using(BASE).get(codigo="LAMINA-A")
        assert conservado.nombre == "Nombre del taller"
        assert conservado.stock_minimo == Decimal("25")

    def test_los_nuevos_entran_sin_minimo(self, almacenista):
        """Inventar un mínimo llenaría la pantalla de compras de avisos falsos
        el primer día."""
        respuesta = subir(almacenista)
        almacenista.post(reverse("inventario:opus_importar"), {
            "crudo": respuesta.context["crudo"], "confirmar": "sí",
        })

        assert Material.objects.using(BASE).get(codigo="CADENA-B").stock_minimo == Decimal("0")

    def test_un_archivo_que_no_cuadra_no_se_importa(self, almacenista):
        """Que no cuadre casi siempre significa que un renglón se partió mal,
        y un renglón mal partido es material comprado de más o de menos."""
        roto = ARCHIVO.read_text(encoding="utf-8").replace(
            '"$10,000.00",,50.00%', '"$1,000.00",,50.00%'
        )
        respuesta = subir(almacenista, roto)
        assert respuesta.context["lectura"].cuadra is False

        antes = Material.objects.using(BASE).count()
        almacenista.post(reverse("inventario:opus_importar"), {
            "crudo": respuesta.context["crudo"], "confirmar": "sí",
        })

        assert Material.objects.using(BASE).count() == antes

    def test_un_archivo_que_no_es_de_opus_lo_dice(self, almacenista):
        respuesta = subir(almacenista, "hola,mundo\n1,2\n")
        assert respuesta.context["paso"] == "subir"

    def test_las_unidades_se_traducen(self, almacenista):
        respuesta = subir(almacenista)
        almacenista.post(reverse("inventario:opus_importar"), {
            "crudo": respuesta.context["crudo"], "confirmar": "sí",
        })

        assert Material.objects.using(BASE).get(codigo="SOLERA-D").unidad == "kg"
        assert Material.objects.using(BASE).get(codigo="AGUA-E").unidad == "lt"


class TestQuienPuedeImportar:
    def test_un_soldador_no(self, base):
        persona = Usuario.objects.create_user("soldador", password="x")
        persona.groups.set(Group.objects.filter(name="soldadura"))
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)

        assert cliente.get(reverse("inventario:opus_importar")).status_code == 302

    def test_el_almacenista_si(self, almacenista):
        assert almacenista.get(reverse("inventario:opus_importar")).status_code == 200
