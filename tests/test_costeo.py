"""Costeo: de eventos a horas, y de horas a dinero.

Lo delicado no es multiplicar tarifas: es deducir las horas. Todo el módulo se
apoya en que el historial del núcleo diga cuándo entró una orden a una etapa y
cuándo salió, y en descontar de ahí lo que no fue trabajo: la noche, el fin de
semana y los paros de máquina. Esa es la parte que estos tests vigilan.
"""

from datetime import datetime
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from core.servicios import costeo as servicio
from core.servicios import produccion
from costeo.models import CentroCosto, CostoOrden, Tarifa, TarifaManoObra, TiempoEstandar
from nucleo.models import (
    Asignacion,
    Etapa,
    EventoMaquina,
    EventoProduccion,
    LineaNegocio,
    PiezaCatalogo,
)

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

ZONA = timezone.get_default_timezone()


def momento(dia, hora, minuto=0):
    """Un instante del taller. Los días son de marzo de 2026, lunes el 2."""
    return timezone.make_aware(datetime(2026, 3, dia, hora, minuto), ZONA)


@pytest.fixture
def linea():
    call_command("sembrar_nucleo", verbosity=0, stdout=StringIO())
    call_command("sembrar_inventario", verbosity=0, stdout=StringIO())
    call_command("sembrar_costeo", verbosity=0, stdout=StringIO())
    return LineaNegocio.objects.using("mes").get(codigo="herreria")


@pytest.fixture
def tarifa(linea):
    centro = CentroCosto.objects.using("mes").get(codigo="herreria")
    return Tarifa.objects.using("mes").create(
        centro=centro,
        vigente_desde=momento(1, 0).date(),
        costo_hora_maquina=Decimal("200"),
        costo_hora_mano_obra=Decimal("100"),
        overhead_hora=Decimal("50"),
    )


@pytest.fixture
def orden(linea):
    return produccion.crear_orden(
        linea=linea, actor="ana", codigo="H-COSTO-1", total_piezas=10, cantidad_objetivo=10
    )


def etapa(linea, codigo):
    return Etapa.objects.using("mes").get(linea=linea, codigo=codigo)


def poner_en_etapa(orden, etapa_destino, cuando, anterior=None):
    """Escribe a mano un evento de tránsito con la fecha que se quiera.

    Los servicios usan la hora actual, y aquí hace falta controlar el reloj
    para poder comprobar el cálculo de jornada.
    """
    return EventoProduccion.objects.using("mes").create(
        orden=orden,
        tipo=EventoProduccion.Tipo.CAMBIO_ETAPA,
        etapa=etapa_destino,
        etapa_anterior=anterior,
        ocurrido_en=cuando,
        actor_username="ana",
    )


def crear_colaborador(nombre, rol="Soldador"):
    """Un colaborador con su equipo: `Colaborador.equipo` es obligatorio."""
    from catalogos.models import Colaborador, EquipoTrabajo

    equipo, _ = EquipoTrabajo.objects.using("mes").get_or_create(
        nombre="Equipo de pruebas",
        defaults={"area": "Herrería", "integrantes": 4},
    )
    return Colaborador.objects.using("mes").create(
        nombre=nombre, rol=rol, equipo=equipo, activo=True
    )


def asignar(orden, etapa_destino, nombre="Juan", maquina=None):
    colaborador = crear_colaborador(nombre)
    return Asignacion.objects.using("mes").create(
        orden=orden, etapa=etapa_destino, colaborador=colaborador,
        maquina=maquina, vigente=True, asignado_en=momento(2, 8),
    )


class TestHorasDeducidasDelHistorial:
    """La idea que sostiene el módulo: las horas no se fichan, se deducen."""

    def test_los_tramos_salen_de_los_eventos(self, orden, linea):
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 12), anterior=corte)

        tramos = servicio.tramos_por_etapa(orden, hasta=momento(2, 16))

        # El alta crea su propio evento, así que el primer tramo es el de la
        # etapa inicial.
        assert [t[0].codigo for t in tramos][-2:] == ["corte", "soldadura"]

    def test_la_noche_no_cuenta_como_trabajo(self, orden, linea, tarifa):
        """Una pieza que entra a las 16:00 y sale a las 8:00 del día siguiente
        tardó dos horas, no dieciséis."""
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 16))
        poner_en_etapa(orden, soldadura, momento(3, 8), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden)

        fila = costo.etapas.get(etapa=corte)
        # 16:00-17:00 del lunes más 7:30-8:00 del martes: hora y media.
        assert fila.horas == Decimal("1.5000")

    def test_el_fin_de_semana_tampoco(self, orden, linea, tarifa):
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        # Viernes 6 a las 16:00 → lunes 9 a las 8:00.
        poner_en_etapa(orden, corte, momento(6, 16))
        poner_en_etapa(orden, soldadura, momento(9, 8), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden)

        assert costo.etapas.get(etapa=corte).horas == Decimal("1.5000")

    def test_un_paro_de_maquina_se_descuenta(self, orden, linea, tarifa):
        """Si no se descontara, el costo castigaría a la orden que tuvo mala
        suerte y la varianza dejaría de significar nada."""
        from catalogos.models import Maquina

        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        maquina = Maquina.objects.using("mes").create(nombre="Sierra 1", activo=True)
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 12), anterior=corte)
        asignar(orden, corte, maquina=maquina)
        EventoMaquina.objects.using("mes").create(
            maquina=maquina, clase=EventoMaquina.Clase.PARO,
            inicio=momento(2, 9), fin=momento(2, 10),
        )

        costo = servicio.calcular(orden)

        fila = costo.etapas.get(etapa=corte)
        assert fila.horas_descontadas_por_paro == Decimal("1.0000")
        assert fila.horas == Decimal("3.0000"), "cuatro horas menos una de paro"

    def test_el_paro_nocturno_solo_descuenta_su_parte_laboral(self, orden, linea, tarifa):
        """Un paro de las 16:50 a las 8:00 son cuarenta minutos, no quince horas."""
        from catalogos.models import Maquina

        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        maquina = Maquina.objects.using("mes").create(nombre="Sierra 1", activo=True)
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(3, 12), anterior=corte)
        asignar(orden, corte, maquina=maquina)
        EventoMaquina.objects.using("mes").create(
            maquina=maquina, clase=EventoMaquina.Clase.PARO,
            inicio=momento(2, 16, 50), fin=momento(3, 8),
        )

        costo = servicio.calcular(orden)

        # 16:50-17:00 del lunes y 7:30-8:00 del martes: cuarenta minutos.
        assert costo.etapas.get(etapa=corte).horas_descontadas_por_paro == Decimal(
            "0.6667"
        )

    def test_una_orden_que_va_y_vuelve_acumula_en_una_sola_fila(self, orden, linea, tarifa):
        """Un retroceso no debe crear dos filas de la misma etapa."""
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 10), anterior=corte)
        poner_en_etapa(orden, corte, momento(2, 11), anterior=soldadura)
        poner_en_etapa(orden, soldadura, momento(2, 12), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden, )

        assert costo.etapas.filter(etapa=corte).count() == 1
        # 8:00-10:00 más 11:00-12:00.
        assert costo.etapas.get(etapa=corte).horas == Decimal("3.0000")


class TestTiempoTranscurridoNoEsTiempoTrabajado:
    """El fallo que apareció al probarlo con los datos del taller.

    El historial dice cuándo entró una orden a una etapa y cuándo salió, no
    cuánto se trabajó en ella. Una orden real de herrería llevaba desde abril
    parada en pintura: la primera versión de este módulo le cobró 671 horas y
    191.274 pesos. Con el tope del centro son 7.101, marcados como cota.
    """

    def test_una_orden_parada_semanas_se_cobra_al_tope(self, orden, linea, tarifa):
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        # Tres semanas en corte: unas 135 horas laborables.
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(23, 8), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden)

        fila = costo.etapas.get(etapa=corte)
        assert fila.horas_transcurridas > Decimal("100"), "el tiempo real se guarda"
        assert fila.horas == Decimal("9.0000"), "pero se cobra el tope de una jornada"
        assert fila.topada is True

    def test_una_etapa_topada_no_cuenta_como_cobertura(self, orden, linea, tarifa):
        """Está estimada, no medida.

        Aparentar que se midió lo que se acotó es exactamente lo que produce
        un costo que nadie puede defender.
        """
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(23, 8), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden)

        assert costo.cobertura == Decimal("0.0000")
        # Dos: corte, que duró tres semanas, y soldadura, que es la etapa
        # donde la orden sigue hoy y por tanto lleva acumulando desde marzo.
        # Una orden abierta también acumula tiempo, y eso es correcto.
        assert costo.detalle["etapas_topadas"] == 2
        assert any("tope" in a for a in costo.detalle["avisos"])

    def test_por_debajo_del_tope_no_se_toca_nada(self, orden, linea, tarifa):
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 12), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden)

        fila = costo.etapas.get(etapa=corte)
        assert fila.horas == fila.horas_transcurridas == Decimal("4.0000")
        assert fila.topada is False

    def test_el_tope_se_puede_ajustar_por_centro(self, orden, linea, tarifa):
        """Cada línea trabaja distinto: el tope es un ajuste, no una constante."""
        centro = CentroCosto.objects.using("mes").get(codigo="herreria")
        centro.horas_max_por_visita = Decimal("27")  # tres jornadas
        centro.save(using="mes")

        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(23, 8), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden)

        assert costo.etapas.get(etapa=corte).horas == Decimal("27.0000")

    def test_el_tiempo_transcurrido_se_conserva_como_medida_de_flujo(
        self, orden, linea, tarifa
    ):
        """No se cobra, pero es la medida real de cuánto tarda el taller."""
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(23, 8), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden)

        assert costo.horas_transcurridas > costo.horas_persona


class TestTarifas:
    def test_manda_la_que_regia_el_dia_del_trabajo(self, orden, linea):
        """Subir los sueldos hoy no puede cambiar lo que costó una orden vieja."""
        centro = CentroCosto.objects.using("mes").get(codigo="herreria")
        Tarifa.objects.using("mes").create(
            centro=centro, vigente_desde=momento(1, 0).date(),
            costo_hora_mano_obra=Decimal("100"),
        )
        Tarifa.objects.using("mes").create(
            centro=centro, vigente_desde=momento(20, 0).date(),
            costo_hora_mano_obra=Decimal("500"),
        )

        vieja = servicio.tarifa_vigente(centro, momento(5, 0).date())
        nueva = servicio.tarifa_vigente(centro, momento(25, 0).date())

        assert vieja.costo_hora_mano_obra == Decimal("100.0000")
        assert nueva.costo_hora_mano_obra == Decimal("500.0000")

    def test_la_tarifa_de_la_persona_gana_a_la_del_centro(self, orden, linea, tarifa):
        colaborador = crear_colaborador("Especialista")
        TarifaManoObra.objects.using("mes").create(
            colaborador=colaborador, vigente_desde=momento(1, 0).date(),
            costo_hora=Decimal("250"),
        )

        valor, origen = servicio.tarifa_de_persona(
            colaborador, "soldador", momento(5, 0).date(), tarifa
        )

        assert valor == Decimal("250.0000")
        assert origen == "persona"

    def test_sin_tarifa_de_persona_se_usa_la_del_rol(self, orden, linea, tarifa):
        colaborador = crear_colaborador("Ayudante", rol="Auxiliar")
        TarifaManoObra.objects.using("mes").create(
            colaborador=None, rol="soldador", vigente_desde=momento(1, 0).date(),
            costo_hora=Decimal("140"),
        )

        valor, origen = servicio.tarifa_de_persona(
            colaborador, "soldador", momento(5, 0).date(), tarifa
        )

        assert (valor, origen) == (Decimal("140.0000"), "rol")

    def test_sin_ninguna_de_las_dos_se_usa_la_del_centro(self, orden, linea, tarifa):
        valor, origen = servicio.tarifa_de_persona(None, "", momento(5, 0).date(), tarifa)
        assert (valor, origen) == (Decimal("100.0000"), "centro")


class TestCoberturaYHonestidad:
    """El módulo declara cuánto pudo medir en vez de aparentar que lo midió todo."""

    def test_una_etapa_sin_asignacion_no_inventa_un_operador(self, orden, linea, tarifa):
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 12), anterior=corte)

        costo = servicio.calcular(orden)

        assert costo.mano_obra == Decimal("0.0000")
        assert costo.cobertura == Decimal("0.0000")
        fila = costo.etapas.get(etapa=corte)
        assert any("sin colaborador" in aviso for aviso in fila.avisos)

    def test_la_cobertura_es_la_fraccion_de_etapas_medidas(self, orden, linea, tarifa):
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        pintura = etapa(linea, "pintura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 10), anterior=corte)
        poner_en_etapa(orden, pintura, momento(2, 12), anterior=soldadura)
        asignar(orden, corte, nombre="Juan")
        asignar(orden, soldadura, nombre="Pedro")

        costo = servicio.calcular(orden)

        # Tres tramos, dos con gente.
        assert costo.cobertura == Decimal("0.6667")

    def test_avisa_cuando_no_hay_material_registrado(self, orden, linea, tarifa):
        costo = servicio.calcular(orden)
        assert any("material" in a for a in costo.detalle["avisos"])

    def test_avisa_cuando_no_hay_tiempo_estandar(self, orden, linea, tarifa):
        costo = servicio.calcular(orden)
        assert any("estándar" in a for a in costo.detalle["avisos"])


class TestElDinero:
    @pytest.fixture
    def calculada(self, orden, linea, tarifa):
        from catalogos.models import Maquina

        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        maquina = Maquina.objects.using("mes").create(nombre="Sierra 1", activo=True)
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 12), anterior=corte)
        asignar(orden, corte, maquina=maquina)
        return servicio.calcular(orden), orden

    def test_suma_obra_maquina_e_indirectos(self, calculada):
        costo, _ = calculada
        # Cuatro horas: obra 4×100, máquina 4×200, indirectos 4×50.
        assert costo.mano_obra == Decimal("400.0000")
        assert costo.maquina == Decimal("800.0000")
        assert costo.overhead == Decimal("200.0000")
        assert costo.total == Decimal("1400.0000")

    def test_el_metodo_directo_no_reparte_indirectos(self, calculada):
        _, orden = calculada
        costo = servicio.calcular(orden, CostoOrden.Metodo.DIRECTO)
        assert costo.overhead == Decimal("0.0000")
        assert costo.total == Decimal("1200.0000")

    def test_el_costo_por_pieza(self, calculada):
        costo, _ = calculada
        assert costo.costo_unitario == Decimal("140.0000")

    def test_recalcular_no_duplica_las_filas_de_etapa(self, calculada):
        costo, orden = calculada
        antes = costo.etapas.count()
        de_nuevo = servicio.calcular(orden)
        assert de_nuevo.etapas.count() == antes

    def test_el_material_consumido_entra_en_el_costo(self, calculada, linea):
        from decimal import Decimal as D

        from core.servicios import inventario
        from inventario.models import LoteMaterial, Material

        _, orden = calculada
        material = Material.objects.using("mes").create(
            codigo="M-1", nombre="Placa", nombre_normalizado="PLACA"
        )
        lote = LoteMaterial.objects.using("mes").create(
            material=material, codigo="L-1", costo_unitario=D("300"),
            recibido_en=momento(1, 0).date(),
        )
        inventario.registrar_entrada(lote=lote, cantidad=5, actor="ana")
        inventario.consumir(material=material, cantidad=2, actor="ana", orden=orden)

        costo = servicio.calcular(orden)

        assert costo.material == Decimal("600.0000")
        assert costo.total == Decimal("2000.0000")


class TestVarianza:
    """El informe que dice dónde se pierde dinero, no sólo cuánto cuesta."""

    @pytest.fixture
    def con_estandar(self, orden, linea, tarifa):
        pieza = PiezaCatalogo.objects.using("mes").create(
            linea=linea, nombre="Marco", nombre_normalizado="MARCO"
        )
        orden.pieza = pieza
        orden.save(using="mes")
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        TiempoEstandar.objects.using("mes").create(
            pieza=pieza, etapa=corte, horas_por_pieza=Decimal("0.2"),
            operadores=1, vigente_desde=momento(1, 0).date(),
        )
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 12), anterior=corte)
        asignar(orden, corte)
        return orden, corte

    def test_compara_lo_real_con_lo_estandar(self, con_estandar):
        orden, corte = con_estandar
        servicio.calcular(orden)

        informe = servicio.varianza(orden)

        fila = informe["etapas"][0]
        # Estándar: 0.2 h por pieza × 10 piezas = 2 h. Real: 4 h.
        assert fila["horas_estandar"] == Decimal("2.0000")
        assert fila["horas_reales"] == Decimal("4.0000")
        assert fila["diferencia"] == Decimal("2.0000")
        assert fila["porcentaje"] == Decimal("100.00")

    def test_el_estandar_no_se_multiplica_por_los_retrocesos(self, con_estandar):
        """Una orden que vuelve a corte no duplica su tiempo estándar."""
        orden, corte = con_estandar
        soldadura = etapa(orden.linea, "soldadura")
        poner_en_etapa(orden, corte, momento(3, 8), anterior=soldadura)
        poner_en_etapa(orden, soldadura, momento(3, 9), anterior=corte)

        costo = servicio.calcular(orden)

        assert costo.etapas.get(etapa=corte).horas_estandar == Decimal("2.0000")


class TestMargen:
    def test_sin_precio_de_venta_no_hay_margen(self, orden, linea, tarifa):
        costo = servicio.calcular(orden)
        assert costo.margen is None

    def test_con_precio_de_venta_se_calcula(self, orden, linea, tarifa):
        """El número que justifica todo el proyecto: margen real por orden."""
        corte = etapa(linea, "corte")
        soldadura = etapa(linea, "soldadura")
        EventoProduccion.objects.using("mes").all().delete()
        poner_en_etapa(orden, corte, momento(2, 8))
        poner_en_etapa(orden, soldadura, momento(2, 12), anterior=corte)
        asignar(orden, corte)

        costo = servicio.calcular(orden)
        costo.precio_venta = Decimal("2000")
        costo.save(using="mes")

        # Sin máquina asignada no hay costo de máquina ni indirectos: sólo las
        # cuatro horas de mano de obra a cien. Que salga así y no «lo de
        # siempre» es la comprobación de que el costo se calcula de verdad y
        # no se rellena con supuestos.
        assert costo.total == Decimal("400.0000")
        assert costo.margen == Decimal("1600.0000")
        assert costo.margen_porcentaje == Decimal("80.00")


class TestComando:
    def test_calcula_y_avisa_de_lo_que_falta(self, orden, linea):
        salida = StringIO()
        call_command("calcular_costos", "--orden", orden.folio, stdout=salida)
        texto = salida.getvalue()
        assert orden.folio in texto
        assert "no tienen tarifa" in texto, "debe avisar de que el costo saldrá en cero"

    def test_el_metodo_directo_desde_la_consola(self, orden, linea, tarifa):
        call_command("calcular_costos", "--orden", orden.folio, "--directo", stdout=StringIO())
        costo = CostoOrden.objects.using("mes").get(orden=orden)
        assert costo.metodo == CostoOrden.Metodo.DIRECTO

    def test_se_puede_filtrar_por_linea(self, orden, linea, tarifa):
        salida = StringIO()
        call_command("calcular_costos", "--linea", "herreria", stdout=salida)
        assert orden.folio in salida.getvalue()

    def test_las_tarifas_no_se_pisan(self, linea, tarifa):
        """Una tarifa guardada es inmutable: corregirla es capturar otra."""
        salida = StringIO()
        call_command(
            "sembrar_costeo", "--tarifa", "herreria:999:999:999",
            "--desde", str(tarifa.vigente_desde), stdout=salida,
        )
        tarifa.refresh_from_db(using="mes")
        assert tarifa.costo_hora_maquina == Decimal("200.0000")
        assert "no se toca" in salida.getvalue()
