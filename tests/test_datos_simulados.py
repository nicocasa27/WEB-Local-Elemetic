"""Vaciar la base y volverla a llenar con un taller simulado.

Dos comandos con riesgos opuestos.

`limpiar_datos` borra. El riesgo es que borre de más —la estructura, o las
cuentas, y entonces nadie puede entrar al sistema que acaba de vaciar— o que
falle a la mitad y deje la base medio llena, que es peor que las dos cosas
anteriores porque parece que funcionó.

`sembrar_demo` inventa. El riesgo es que invente cosas imposibles. Es fácil
generar mil filas al azar; lo difícil es que no salga una pieza terminada con
fecha de mañana, una orden con más piezas pintadas que soldadas, o toneladas
que no cuadran con ninguna bitácora. Con datos así cada pantalla parece rota y
el sistema no se puede enseñar ni practicar.

Estos tests comprueban justo esas dos cosas: que uno no se pase de borrar y que
el otro no invente imposibles.
"""

import datetime
from collections import Counter
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connections
from django.utils import timezone

from catalogos.management.commands.crear_admin import USUARIO as USUARIO_ADMIN
from core import estados as est

pytestmark = pytest.mark.django_db(databases=["default", "mes"])

Usuario = get_user_model()
BASE = "mes"


def sembrar():
    call_command("sembrar_demo", verbosity=0, stdout=StringIO())


def limpiar(**extra):
    """Vacía la base de pruebas.

    Va con `aunque_sea_produccion` porque durante los tests `DEBUG` es False y
    el comando, con razón, se niega a correr: eso es lo que impide vaciar el
    servidor del taller sin escribirlo a propósito. El guardia se comprueba en
    `TestElGuardiaDeProduccion`.
    """
    nombre = connections[BASE].settings_dict["NAME"]
    call_command(
        "limpiar_datos",
        confirmacion=nombre,
        aunque_sea_produccion=True,
        verbosity=0,
        stdout=StringIO(),
        **extra,
    )


class TestElGuardiaDeProduccion:
    def test_con_debug_apagado_se_niega(self):
        """`DEBUG = False` es como corre el servidor del taller.

        Vaciarlo ahí tiene que costar escribir una bandera a mano, no un
        despiste con la flecha arriba de la terminal.
        """
        nombre = connections[BASE].settings_dict["NAME"]
        with pytest.raises(CommandError, match="DEBUG"):
            call_command(
                "limpiar_datos", confirmacion=nombre, verbosity=0, stdout=StringIO()
            )


class TestVaciarNoSePasa:
    def test_sin_confirmacion_no_borra_nada(self):
        from produccion.models import Viga

        sembrar()
        antes = Viga.objects.using(BASE).count()
        assert antes > 0

        with pytest.raises(CommandError):
            call_command(
                "limpiar_datos", aunque_sea_produccion=True,
                verbosity=0, stdout=StringIO(),
            )

        assert Viga.objects.using(BASE).count() == antes

    def test_la_confirmacion_tiene_que_ser_el_nombre_de_la_base(self):
        from produccion.models import Viga

        sembrar()
        antes = Viga.objects.using(BASE).count()

        with pytest.raises(CommandError):
            call_command(
                "limpiar_datos", confirmacion="sí", aunque_sea_produccion=True,
                verbosity=0, stdout=StringIO(),
            )

        assert Viga.objects.using(BASE).count() == antes

    def test_deja_la_estructura_en_pie(self):
        """Borra filas, no tablas. Después del vaciado se tiene que poder
        volver a escribir sin migrar nada."""
        from produccion.models import Viga

        sembrar()
        limpiar()

        assert Viga.objects.using(BASE).count() == 0
        # Y la tabla sigue ahí y admite datos.
        Viga.objects.using(BASE).create(
            codigo_viga="POST-LIMPIEZA", pieza_no=1, total_piezas=1,
            proyecto="P", descripcion="", fecha_compromiso=timezone.localdate(),
            estado=est.ESPERA_CORTE, prioridad=3, peso_kg=1,
            fecha_creacion=timezone.now(), ultimo_cambio=timezone.now(),
        )
        assert Viga.objects.using(BASE).count() == 1

    def test_no_toca_las_cuentas_por_defecto(self):
        """Vaciarlas dejaría el sistema sin nadie que pueda entrar."""
        Usuario.objects.create_user("quedaviva", password="x")

        limpiar()

        assert Usuario.objects.filter(username="quedaviva").exists()

    def test_con_tambien_usuarios_conserva_al_administrador_fijo(self):
        call_command("crear_admin", verbosity=0, stdout=StringIO())
        Usuario.objects.create_user("prescindible", password="x")

        limpiar(tambien_usuarios=True)

        assert not Usuario.objects.filter(username="prescindible").exists()
        assert Usuario.objects.filter(username=USUARIO_ADMIN).exists()

    def test_conservar_planta_deja_el_taller(self):
        from catalogos.models import Maquina
        from produccion.models import Viga

        sembrar()

        limpiar(conservar_planta=True)

        assert Viga.objects.using(BASE).count() == 0
        assert Maquina.objects.using(BASE).count() > 0

    def test_el_orden_de_borrado_no_revienta_a_la_mitad(self):
        """Casi todas las llaves foráneas son PROTECT.

        Con el orden mal, el borrado falla en algún punto. La transacción lo
        revierte, así que el síntoma no es una base a medias sino un error a
        los treinta segundos — pero de todas formas hay que probarlo con la
        base llena, que es cuando aparece.
        """
        from inventario.models import Material
        from nucleo.models import LineaNegocio

        sembrar()
        limpiar()

        assert LineaNegocio.objects.using(BASE).count() == 0
        assert Material.objects.using(BASE).count() == 0


class TestElTallerSimuladoEsCreible:
    @pytest.fixture(scope="class")
    def _sembrado(self, django_db_setup, django_db_blocker):
        """Se siembra una vez para toda la clase: son trece comprobaciones
        sobre el mismo taller y sembrarlo en cada una tarda un minuto y medio.

        Al escribirse fuera de la transacción de cada test, los datos no
        desaparecen solos. Por eso el vaciado del final no es opcional: sin él
        el taller se queda puesto y contamina lo que venga después, que fue
        exactamente lo que pasó la primera vez.
        """
        with django_db_blocker.unblock():
            sembrar()
            try:
                yield
            finally:
                limpiar(tambien_usuarios=True)

    @pytest.fixture
    def taller(self, _sembrado):
        return True

    def test_hay_taller(self, taller):
        from catalogos.models import Cuadrilla, Maquina
        from produccion.models import Viga

        assert Viga.objects.using(BASE).count() > 100
        assert Maquina.objects.using(BASE).count() >= 10
        assert Cuadrilla.objects.using(BASE).count() > 0

    def test_toda_pieza_tiene_la_bitacora_de_su_etapa(self, taller):
        """Una pieza en pintura tiene apuntes de corte, armado y soldadura.

        Generar sólo el estado final deja piezas sin historia: la pantalla de
        detalle sale vacía y los informes por etapa no cuadran con nada.
        """
        from produccion.models import ProductionLog, Viga

        apuntes = Counter(
            ProductionLog.objects.using(BASE).values_list("viga_internal_id", flat=True)
        )
        malas = [
            v.codigo_viga
            for v in Viga.objects.using(BASE).all()
            if apuntes.get(v.internal_id, 0) != est.SECUENCIA.index(est.normalizar(v.estado))
        ]
        assert not malas, f"{len(malas)} piezas sin la bitácora de su etapa"

    def test_no_hay_movimientos_en_el_futuro(self, taller):
        """Los informes semanales contarían semanas que no han pasado."""
        from produccion.models import ProductionLog

        hoy = timezone.localdate()
        futuros = [
            ts for ts in ProductionLog.objects.using(BASE).values_list("timestamp", flat=True)
            if timezone.localtime(ts.replace(tzinfo=datetime.timezone.utc)).date() > hoy
        ]
        assert not futuros, f"{len(futuros)} apuntes con fecha futura"

    def test_los_movimientos_caen_en_jornada(self, taller):
        """No es cosmético: la disponibilidad y los tiempos por etapa se
        calculan descontando lo que queda fuera de la jornada."""
        from produccion.models import ProductionLog

        fuera = 0
        for ts in ProductionLog.objects.using(BASE).values_list("timestamp", flat=True):
            local = timezone.localtime(ts.replace(tzinfo=datetime.timezone.utc))
            if local.weekday() >= 5 or not (7 <= local.hour <= 17):
                fuera += 1
        assert fuera == 0, f"{fuera} apuntes fuera del horario de trabajo"

    def test_las_fechas_de_compromiso_estan_repartidas(self, taller):
        """En la base real las veintiséis piezas están vencidas, que es lo
        mismo que no tener fecha: si todo es urgente, no se puede priorizar."""
        from produccion.models import Viga

        hoy = timezone.localdate()
        vencidas = sum(
            1 for f in Viga.objects.using(BASE).values_list("fecha_compromiso", flat=True)
            if f < hoy
        )
        total = Viga.objects.using(BASE).count()
        assert 0 < vencidas < total * 0.5, (
            f"{vencidas} de {total} vencidas: o ninguna urgencia o todas"
        )

    def test_el_avance_de_herreria_no_se_contradice(self, taller):
        """Terminadas ≤ pintadas ≤ soldadas ≤ total.

        Es la invariante que la base real no tiene, y por eso allí se puede
        declarar material terminado que nunca se soldó.
        """
        from catalogos.models import HerrOrdenProduccion

        rotas = [
            o.codigo
            for o in HerrOrdenProduccion.objects.using(BASE).all()
            if not (
                o.cantidad_terminada <= o.cantidad_pintada
                <= o.cantidad_producida <= o.cantidad_objetivo
            )
        ]
        assert not rotas, f"Órdenes con avance imposible: {rotas}"

    def test_el_almacen_cuadra_con_sus_movimientos(self, taller):
        """Cada existencia viene de una entrada con lote y costo.

        Poner el número a mano en `Existencia` sería más rápido y dejaría el
        almacén sin historia: no se podría decir de qué colada salió una pieza.
        """
        from core.servicios import inventario as servicio

        assert servicio.descuadres() == []

    def test_hay_material_bajo_minimo_para_ver_la_alerta(self, taller):
        from core.servicios import inventario as servicio

        assert len(servicio.bajo_minimo()) > 0

    def test_todo_el_piso_tiene_cuenta_y_esta_enlazado(self, taller):
        """Es lo que no pasa en la base real, y por lo que «Mi trabajo» del
        celular no la puede abrir nadie."""
        from catalogos.models import Colaborador

        sueltos = Colaborador.objects.using(BASE).filter(activo=True, usuario="").count()
        assert sueltos == 0

    def test_las_maquinas_dicen_lo_que_saben_hacer(self, taller):
        """Sin la función, elegir equipo de corte al lanzar una orden es una
        lista de seis nombres sin criterio."""
        from catalogos.models import Maquina

        corte = Maquina.objects.using(BASE).filter(tipo="Corte", activo=True)
        assert corte.count() == 6
        assert not corte.filter(funcion="").exists()

    def test_pintura_es_un_centro_de_trabajo(self, taller):
        from catalogos.models import Maquina

        assert Maquina.objects.using(BASE).filter(tipo="Pintura").exists()

    def test_las_cuadrillas_no_repiten_a_nadie(self, taller):
        """Alguien dos veces en la misma cuadrilla contaría sus horas dobles."""
        from catalogos.models import Cuadrilla

        for cuadrilla in Cuadrilla.objects.using(BASE).prefetch_related("integrantes"):
            ids = [i.colaborador_id for i in cuadrilla.integrantes.all()]
            assert len(ids) == len(set(ids))

    def test_hay_material_no_inventariable(self, taller):
        """Los indirectos por porcentaje de OPUS —fletes, consumibles— no
        ocupan sitio en ningún estante."""
        from inventario.models import Material

        assert Material.objects.using(BASE).filter(inventariable=False).exists()

    def test_hay_listas_de_materiales(self, taller):
        """Sin ellas la Rama A no puede reservar material al lanzar una orden:
        no hay forma de saber qué lleva un andamio."""
        from inventario.models import ListaMateriales, RenglonListaMateriales

        assert ListaMateriales.objects.using(BASE).count() > 0
        assert RenglonListaMateriales.objects.using(BASE).count() > 0


class TestEsReproducible:
    def test_la_misma_semilla_da_el_mismo_taller(self):
        """Sin esto, un fallo que sólo aparece con ciertos datos no se puede
        reproducir: se vuelve a sembrar y ya son otros."""
        from produccion.models import Viga

        call_command("sembrar_demo", semilla=7, verbosity=0, stdout=StringIO())
        primera = list(
            Viga.objects.using(BASE).order_by("internal_id").values_list(
                "codigo_viga", "peso_kg", "estado"
            )
        )

        limpiar()
        call_command("sembrar_demo", semilla=7, verbosity=0, stdout=StringIO())
        segunda = list(
            Viga.objects.using(BASE).order_by("internal_id").values_list(
                "codigo_viga", "peso_kg", "estado"
            )
        )

        assert primera == segunda
