"""Comprueba que la propia infraestructura de tests funciona."""

import pytest


@pytest.mark.django_db(databases=["default", "mes"])
def test_las_tablas_heredadas_existen():
    """Sin esto, cualquier test sobre vigas fallaría por tabla inexistente."""
    from produccion.models import ProductionLog, Viga

    assert Viga.objects.count() == 0
    assert ProductionLog.objects.count() == 0


@pytest.mark.django_db(databases=["default", "mes"])
def test_se_puede_crear_una_viga():
    from django.utils import timezone

    from produccion.models import Viga

    viga = Viga.objects.create(
        codigo_viga="PRUEBA-1",
        pieza_no=1,
        total_piezas=1,
        proyecto="PROYECTO DE PRUEBA",
        descripcion="viga de prueba",
        fecha_compromiso=timezone.localdate(),
        estado="Espera de corte",
        peso_kg=100,
        fecha_creacion=timezone.now(),
        ultimo_cambio=timezone.now(),
    )
    assert viga.internal_id
    assert Viga.objects.count() == 1


@pytest.mark.django_db(databases=["default", "mes"])
def test_los_perfiles_de_usuario_se_crean_con_su_grupo(crear_usuario):
    usuario = crear_usuario("herreria")
    assert usuario.groups.filter(name="herreria").exists()
