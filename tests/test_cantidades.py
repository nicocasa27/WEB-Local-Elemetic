"""Cómo se escribe una cantidad en pantalla.

El almacén guarda seis decimales, y la pantalla los enseñaba tal cual:
«120,000000». Peor todavía, con el idioma puesto en «es» (España) la coma
era el separador decimal, así que un peso de 1.6 kg se leía «1,600» —
mil seiscientos.
"""

from decimal import Decimal

import pytest
from django.template import Context, Template

from produccion.templatetags.produccion_extras import cantidad


def render(valor):
    plantilla = Template("{% load produccion_extras %}{{ x|cantidad }}")
    return plantilla.render(Context({"x": valor}))


class TestLosCerosDeRellenoNoSeEnsenan:
    @pytest.mark.parametrize(
        "guardado,en_pantalla",
        [
            ("120.000000", "120"),
            ("1.600000", "1.6"),
            ("0.000000", "0"),
            ("42", "42"),
        ],
    )
    def test_se_quitan(self, guardado, en_pantalla):
        assert cantidad(Decimal(guardado)) == en_pantalla


class TestLosDecimalesQueSignificanAlgoSeQuedan:
    """No se recorta a dos ni a tres: si alguien capturó una diezmilésima,
    es porque la ocupa."""

    @pytest.mark.parametrize(
        "guardado,en_pantalla",
        [
            ("0.125000", "0.125"),
            ("0.000400", "0.0004"),
            ("12.345678", "12.345678"),
        ],
    )
    def test_no_se_recortan(self, guardado, en_pantalla):
        assert cantidad(Decimal(guardado)) == en_pantalla


class TestLosMilesSeAgrupan:
    def test_una_cifra_larga_se_puede_leer(self):
        assert cantidad(Decimal("100000213.231200")) == "100,000,213.2312"

    def test_el_punto_es_el_decimal(self):
        """México, no España. Con «es» a secas esto salía «1 234,5»."""
        assert cantidad(Decimal("1234.500000")) == "1,234.5"


class TestLoQueNoEsUnNumero:
    @pytest.mark.parametrize("vacio", [None, ""])
    def test_vacio_no_escribe_nada(self, vacio):
        assert cantidad(vacio) == ""

    def test_un_texto_se_devuelve_tal_cual(self):
        """El filtro no es sitio para reventar una pantalla entera."""
        assert cantidad("por definir") == "por definir"


class TestDesdeUnaPlantilla:
    def test_el_filtro_esta_registrado(self):
        assert render(Decimal("1.600000")) == "1.6"

    def test_no_lo_vuelve_a_localizar_django(self):
        """`number_format` ya devuelve una cadena; si Django la tocara otra
        vez, el punto decimal se convertiría en coma."""
        assert render(Decimal("100000213.231200")) == "100,000,213.2312"
