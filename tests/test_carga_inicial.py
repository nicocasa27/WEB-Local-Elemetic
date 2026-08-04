"""El inventario del día uno.

El importador de OPUS da de alta el catálogo y lo deja en cero, a propósito: un
presupuesto dice lo que se va a necesitar, no lo que hay. Esto sube lo otro, el
conteo físico, que es lo único con lo que se puede arrancar.

Dos reglas que se prueban aquí:

- **Cada renglón entra como un lote**, aunque sea «INICIAL-2026». Sin lote, el
  día que un cliente reclame no habrá forma de decir de qué colada salió su
  pieza, y la trazabilidad empieza rota desde el primer día.
- **Nada entra a medias en silencio.** Los renglones con problema se quedan
  fuera y se dicen. Un almacén con la mitad de los renglones se ve igual de
  completo que uno entero.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from core import roles
from core.servicios import inventario as servicio
from inventario import carga_inicial
from inventario.models import Almacen, LoteMaterial, Material

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

BASE = "mes"
Usuario = get_user_model()


@pytest.fixture
def almacen():
    return Almacen.objects.using(BASE).create(
        nombre="Principal", es_principal=True, activo=True
    )


@pytest.fixture
def catalogo(almacen):
    for codigo in ("HSS4X3/16", "PL-3/8"):
        Material.objects.using(BASE).create(
            codigo=codigo, nombre=f"Perfil {codigo}",
            nombre_normalizado=f"PERFIL {codigo}",
            unidad=Material.Unidad.KILOGRAMO,
        )


@pytest.fixture
def almacenista(almacen):
    roles.asegurar_grupos()
    persona = Usuario.objects.create_user("mateo", password="x")
    persona.groups.set(Group.objects.filter(name=roles.ALMACEN))
    cliente = Client(SERVER_NAME="127.0.0.1")
    cliente.force_login(persona)
    return cliente


BUENO = (
    "Clave,Cantidad,Lote,Colada,Costo,Almacen,Proveedor,Fecha\n"
    "HSS4X3/16,320.5,INICIAL-2026,C-99871,182.40,Principal,,2026-08-01\n"
    "PL-3/8,88,INICIAL-2026,C-99880,210.00,Principal,,2026-08-01\n"
)


class TestLeerElArchivo:
    def test_entiende_el_archivo_bien_formado(self, catalogo):
        renglones, problema = carga_inicial.leer(BUENO)

        assert not problema
        assert len(renglones) == 2
        assert all(r["listo"] for r in renglones)

    def test_los_encabezados_no_dependen_de_acentos_ni_mayusculas(self, catalogo):
        """El archivo casi siempre sale de un Excel escrito a mano."""
        renglones, problema = carga_inicial.leer(
            "CLAVE,CANTIDAD,Almacén\nHSS4X3/16,10,Principal\n"
        )

        assert not problema
        assert renglones[0]["listo"]

    def test_sin_las_dos_columnas_obligatorias_no_sigue(self, catalogo):
        renglones, problema = carga_inicial.leer("Nombre,Color\nAlgo,rojo\n")

        assert "Clave" in problema
        assert not renglones

    def test_una_clave_que_no_esta_en_el_catalogo_se_avisa(self, catalogo):
        """No se dan de alta materiales aquí: esto es el conteo, no el
        catálogo. Crearlos al vuelo llenaría el catálogo de erratas."""
        renglones, _ = carga_inicial.leer("Clave,Cantidad\nINVENTADO,10\n")

        assert not renglones[0]["listo"]
        assert "catálogo" in renglones[0]["avisos"][0]

    def test_una_cantidad_que_no_es_numero_se_avisa(self, catalogo):
        renglones, _ = carga_inicial.leer("Clave,Cantidad\nHSS4X3/16,muchos\n")

        assert not renglones[0]["listo"]

    def test_una_cantidad_de_cero_no_sirve(self, catalogo):
        renglones, _ = carga_inicial.leer("Clave,Cantidad\nHSS4X3/16,0\n")

        assert not renglones[0]["listo"]

    def test_sin_lote_se_pone_uno_con_el_ano(self, catalogo):
        renglones, _ = carga_inicial.leer("Clave,Cantidad\nHSS4X3/16,10\n")

        assert renglones[0]["lote"] == f"INICIAL-{timezone.localdate():%Y}"

    def test_acepta_varios_formatos_de_fecha(self, catalogo):
        renglones, _ = carga_inicial.leer(
            "Clave,Cantidad,Fecha\nHSS4X3/16,10,01/08/2026\n"
        )

        assert renglones[0]["listo"]
        assert renglones[0]["fecha"].month == 8

    def test_se_avisan_todos_los_problemas_de_una_vez(self, catalogo):
        """Para poder corregir el archivo entero, en vez de descubrir el
        siguiente error después de arreglar el primero."""
        renglones, _ = carga_inicial.leer(
            "Clave,Cantidad\nINVENTADO,10\nHSS4X3/16,nada\nPL-3/8,5\n"
        )

        assert [r["listo"] for r in renglones] == [False, False, True]


class TestAplicarlo:
    def test_el_material_entra_al_almacen(self, catalogo, almacen):
        renglones, _ = carga_inicial.leer(BUENO)

        carga_inicial.aplicar(renglones, actor=None)

        item = Material.objects.using(BASE).get(codigo="HSS4X3/16")
        assert servicio.existencia(item) == Decimal("320.500000")

    def test_cada_renglon_deja_su_lote_con_colada(self, catalogo, almacen):
        """Sin lote no se puede responder de qué colada salió una pieza, que
        es la razón de tener lotes."""
        renglones, _ = carga_inicial.leer(BUENO)

        carga_inicial.aplicar(renglones, actor=None)

        lote = LoteMaterial.objects.using(BASE).get(codigo="INICIAL-2026", material__codigo="HSS4X3/16")
        assert lote.colada == "C-99871"
        assert lote.costo_unitario == Decimal("182.400000")

    def test_los_renglones_con_problema_no_entran(self, catalogo, almacen):
        renglones, _ = carga_inicial.leer(
            "Clave,Cantidad\nINVENTADO,10\nPL-3/8,5\n"
        )

        hechos = carga_inicial.aplicar(renglones, actor=None)

        assert len(hechos) == 1

    def test_subir_el_mismo_archivo_dos_veces_no_duplica(self, catalogo, almacen):
        """Con la red del taller, el segundo envío llega. Cada renglón lleva
        clave de idempotencia."""
        renglones, _ = carga_inicial.leer(BUENO)
        carga_inicial.aplicar(renglones, actor=None)

        renglones, _ = carga_inicial.leer(BUENO)
        carga_inicial.aplicar(renglones, actor=None)

        item = Material.objects.using(BASE).get(codigo="HSS4X3/16")
        assert servicio.existencia(item) == Decimal("320.500000")


class TestLaPantalla:
    def _subir(self, cliente, contenido, **extra):
        return cliente.post(reverse("inventario:carga_inicial"), {
            "archivo": SimpleUploadedFile(
                "inventario.csv", contenido.encode("utf-8"), content_type="text/csv"
            ),
            **extra,
        })

    def test_revisar_no_toca_nada(self, almacenista, catalogo, almacen):
        """Se ve lo que va a pasar antes de que pase. Es la misma salvaguarda
        que en el importador de OPUS."""
        respuesta = self._subir(almacenista, BUENO)

        assert respuesta.context["paso"] == "revisar"
        item = Material.objects.using(BASE).get(codigo="HSS4X3/16")
        assert servicio.existencia(item) == Decimal("0")

    def test_confirmar_lo_aplica(self, almacenista, catalogo, almacen):
        almacenista.post(reverse("inventario:carga_inicial"), {
            "crudo": BUENO, "confirmar": "sí",
        })

        item = Material.objects.using(BASE).get(codigo="HSS4X3/16")
        assert servicio.existencia(item) == Decimal("320.500000")

    def test_quien_no_es_de_almacen_no_entra(self, catalogo, almacen):
        persona = Usuario.objects.create_user("ana", password="x")
        cliente = Client(SERVER_NAME="127.0.0.1")
        cliente.force_login(persona)

        respuesta = cliente.get(reverse("inventario:carga_inicial"))

        assert respuesta.status_code == 302

    def test_sin_archivo_lo_dice(self, almacenista, catalogo):
        respuesta = almacenista.post(reverse("inventario:carga_inicial"), {})

        assert respuesta.context["paso"] == "subir"
