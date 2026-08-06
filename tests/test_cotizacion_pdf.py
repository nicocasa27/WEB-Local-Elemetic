"""Leer la cotización de Corta.mx en PDF para no volver a teclearla.

La cotización se genera en la página, se baja en PDF y hasta ahora alguien
volvía a capturar a mano lo que ya estaba escrito ahí: folio, pieza, medidas,
material, espesor y cantidad. Una medida mal tecleada se corta mal, y eso se
paga en material.

`tests/datos/cotizacion_corta.pdf` es una cotización de verdad —la Cort-119—,
y es la única documentación que hay del formato. Si algún día el generador
cambia, estos tests son los que avisan.

El PDF lo produce Tempus Tools colocando cada letra por separado, y de ahí
salen los dos estropicios que hay que deshacer antes de leer nada: letras
sueltas («C o r t - 1 1 9») y espacios metidos dentro de los números
(«1,1 12.00»). Buena parte de lo que se comprueba aquí es eso.
"""

import json

import pytest
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from catalogos.models import LaserMaterialPlaca
from core.servicios import cotizacion as servicio

MUESTRA = "tests/datos/cotizacion_corta.pdf"


@pytest.fixture
def pdf_de_muestra():
    return (settings.BASE_DIR / MUESTRA).read_bytes()


class TestEnderezar:
    def test_junta_las_letras_sueltas(self):
        assert servicio.enderezar("Numero: C o r t - 1 1 9") == "Numero: Cort-119"

    def test_respeta_las_palabras_separadas_por_doble_espacio(self):
        """Con las letras sueltas, el doble espacio es lo que separa palabras."""
        assert servicio.enderezar("N o t a s  a d i c i o n a l e s") == "Notas adicionales"

    def test_no_toca_el_texto_normal(self):
        texto = "Detalles de la pieza"
        assert servicio.enderezar(texto) == texto

    def test_no_pega_una_letra_suelta_a_la_palabra_siguiente(self):
        """Un tramo de menos de tres no es un tramo: «# Parte» no es «#Parte»."""
        assert servicio.enderezar("# Parte Detalles") == "# Parte Detalles"

    def test_quita_el_espacio_metido_dentro_de_un_numero(self):
        assert servicio.enderezar("1,1 12.00 x 272.00 mm") == "1,112.00 x 272.00 mm"

    def test_conserva_el_espacio_entre_la_cantidad_y_el_precio(self):
        """Es el que marca dónde acaba cada pieza. Sin él no hay renglones."""
        assert servicio.enderezar("3 $ 7 8 7 . 0 6 $ 2 , 3 6 1 . 1 8") == "3 $ 787.06 $ 2,361.18"


class TestLeerLaCotizacionDeVerdad:
    def test_saca_el_folio(self, pdf_de_muestra):
        assert servicio.de_pdf(pdf_de_muestra).folio == "Cort-119"

    def test_saca_la_caducidad(self, pdf_de_muestra):
        assert servicio.de_pdf(pdf_de_muestra).caducidad == "10-Aug-2026"

    def test_saca_la_pieza_entera(self, pdf_de_muestra):
        cot = servicio.de_pdf(pdf_de_muestra)

        assert len(cot.renglones) == 1
        r = cot.renglones[0]
        assert r.numero == 1
        assert r.parte == "PLACA316"
        assert r.largo_mm == 1112.0
        assert r.ancho_mm == 272.0
        assert r.material == "Acero A36"
        assert r.espesor_mm == 4.76
        assert r.cantidad == 3
        assert r.procesos == ["Corte", "Material"]

    def test_el_mayor_es_el_largo(self, pdf_de_muestra):
        """La cotización da dos números sin decir cuál es cuál. El formulario
        pide largo y ancho por separado, y se captura el mayor como largo."""
        r = servicio.de_pdf(pdf_de_muestra).renglones[0]
        assert r.largo_mm > r.ancho_mm

    def test_no_se_queja_de_nada(self, pdf_de_muestra):
        assert servicio.de_pdf(pdf_de_muestra).avisos == []

    def test_no_confunde_el_subtotal_con_una_pieza(self, pdf_de_muestra):
        """Las líneas de Subtotal, Iva y Total también llevan importes."""
        assert len(servicio.de_pdf(pdf_de_muestra).renglones) == 1


class TestLoQueNoSePuedeLeer:
    def test_un_pdf_sin_texto_lo_dice(self):
        cot = servicio.de_pdf(b"%PDF-1.4 esto no es un pdf")

        assert cot.vacia
        assert any("no trae texto" in a for a in cot.avisos)

    def test_un_texto_sin_piezas_lo_dice(self):
        cot = servicio.leer("COTIZACIÓN\nNúmero de cotización: Cort-1\n")

        assert cot.folio == "Cort-1"
        assert any("ninguna pieza" in a for a in cot.avisos)

    def test_avisa_de_la_pieza_incompleta(self):
        cot = servicio.leer("1\nPLACA\n2 $10.00 $20.00\n")

        assert cot.renglones[0].cantidad == 2
        assert any("faltan datos" in a for a in cot.avisos)


class TestVariasPiezas:
    """Una cotización puede traer varias, y cada una es un pedido aparte."""

    def test_las_separa(self):
        cot = servicio.leer(
            "1\nBRIDA\n100.00 x 50.00 mm\nAcero A36\nEspesor: 3.00 mm\nCorte\n"
            "2 $10.00 $20.00\n"
            "3\nTAPA\n400.00 x 200.00 mm\nAluminio\nEspesor: 6.35 mm\nCorte\nDoblez\n"
            "5 $30.00 $150.00\n"
        )

        assert [r.numero for r in cot.renglones] == [1, 3]
        assert [r.parte for r in cot.renglones] == ["BRIDA", "TAPA"]
        assert [r.cantidad for r in cot.renglones] == [2, 5]
        assert cot.renglones[1].procesos == ["Corte", "Doblez"]


@pytest.mark.django_db(databases=["default", "mes"])
class TestBuscarLaPlacaEnElCatalogo:
    def placa(self, **cambios):
        datos = dict(
            categoria_material="Acero",
            tipo_material="",
            nombre="A36",
            espesor_mm=4.76,
            largo_mm=2440,
            ancho_mm=1220,
            activo=True,
        )
        datos.update(cambios)
        return LaserMaterialPlaca.objects.create(**datos)

    def renglon(self, **cambios):
        datos = dict(numero=1, material="Acero A36", espesor_mm=4.76)
        datos.update(cambios)
        return servicio.Renglon(**datos)

    def test_encuentra_la_que_coincide(self):
        buena = self.placa()
        assert servicio.placa_parecida(self.renglon()) == buena

    def test_el_espesor_manda(self):
        """Misma placa con otro espesor no sirve, y el error saldría en kilos."""
        self.placa(espesor_mm=6.35)
        assert servicio.placa_parecida(self.renglon()) is None

    def test_no_elige_solo_por_el_espesor(self):
        """Hay muchas placas de 4.76 mm. Dejar el campo vacío es más honesto
        que rellenarlo por la persona que captura: el material es el precio."""
        self.placa(nombre="INOX304", categoria_material="Inoxidable")
        assert servicio.placa_parecida(self.renglon()) is None

    def test_no_mira_las_dadas_de_baja(self):
        self.placa(activo=False)
        assert servicio.placa_parecida(self.renglon()) is None


@pytest.mark.django_db(databases=["default", "mes"])
class TestLaPantalla:
    @pytest.fixture
    def quien_captura(self):
        persona = User.objects.create_user("captura", password="x")
        persona.groups.add(Group.objects.get_or_create(name="corte_laser")[0])
        cliente = Client()
        cliente.force_login(persona)
        return cliente

    def url(self):
        return reverse("catalogos:corte_laser_leer_cotizacion")

    def subir(self, cliente, datos):
        return cliente.post(
            self.url(),
            {"archivo": SimpleUploadedFile("cot.pdf", datos, content_type="application/pdf")},
        )

    def test_devuelve_lo_leido(self, quien_captura, pdf_de_muestra):
        cuerpo = json.loads(self.subir(quien_captura, pdf_de_muestra).content)

        assert cuerpo["ok"]
        assert cuerpo["folio"] == "Cort-119"
        assert len(cuerpo["renglones"]) == 1
        r = cuerpo["renglones"][0]
        assert r["parte"] == "PLACA316"
        assert r["largo_mm"] == 1112
        assert r["ancho_mm"] == 272
        assert r["cantidad"] == 3

    def test_propone_la_placa_del_catalogo(self, quien_captura, pdf_de_muestra):
        placa = LaserMaterialPlaca.objects.create(
            categoria_material="Acero", nombre="A36", espesor_mm=4.76,
            largo_mm=2440, ancho_mm=1220, activo=True,
        )

        cuerpo = json.loads(self.subir(quien_captura, pdf_de_muestra).content)

        assert cuerpo["renglones"][0]["placa_id"] == placa.id
        assert "A36" in cuerpo["renglones"][0]["placa_nombre"]

    def test_sin_placa_en_el_catalogo_lo_deja_vacio(self, quien_captura, pdf_de_muestra):
        cuerpo = json.loads(self.subir(quien_captura, pdf_de_muestra).content)
        assert cuerpo["renglones"][0]["placa_id"] is None

    def test_no_crea_nada(self, quien_captura, pdf_de_muestra):
        """Lo importante de todo esto: leer no guarda. Si la lectura sale mal,
        el daño es un formulario mal llenado que se ve y se corrige."""
        from catalogos.models import CortaPiezaCatalogo, LaserOrdenProduccion

        self.subir(quien_captura, pdf_de_muestra)

        assert not LaserOrdenProduccion.objects.exists()
        assert not CortaPiezaCatalogo.objects.exists()
        assert not LaserMaterialPlaca.objects.exists()

    def test_sin_archivo_avisa(self, quien_captura):
        assert quien_captura.post(self.url(), {}).status_code == 400

    def test_pide_sesion(self, pdf_de_muestra):
        assert self.subir(Client(), pdf_de_muestra).status_code in {302, 403}

    def test_quien_no_es_de_corta_no_puede(self, pdf_de_muestra):
        persona = User.objects.create_user("ajeno", password="x")
        persona.groups.add(Group.objects.get_or_create(name="soldadura")[0])
        cliente = Client()
        cliente.force_login(persona)

        assert self.subir(cliente, pdf_de_muestra).status_code == 403

    def test_el_formulario_trae_el_lector(self, quien_captura):
        html = quien_captura.get(reverse("catalogos:corte_laser_create")).content.decode()

        assert 'id="cotizacionPanel"' in html
        assert reverse("catalogos:corte_laser_leer_cotizacion") in html
