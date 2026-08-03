"""Tests de core.estados y core.jornada.

Son funciones puras: no necesitan base de datos y corren en milisegundos.
Varios comparan el comportamiento nuevo con el que tenía el código original,
para dejar constancia de qué cambia y por qué.
"""

from datetime import date, datetime, time, timedelta

import pytest
from django.utils import timezone

from core import estados, jornada


class TestNormalizar:
    def test_deja_igual_los_estados_bien_escritos(self):
        for estado in estados.SECUENCIA:
            assert estados.normalizar(estado) == estado

    @pytest.mark.parametrize(
        "variante,esperado",
        [
            ("Espera Armado", estados.ESPERA_ARMADO),
            ("ESPERA ARMADO", estados.ESPERA_ARMADO),
            ("espera armado", estados.ESPERA_ARMADO),
            ("  Espera   Armado  ", estados.ESPERA_ARMADO),
            ("Espera Soldadura", estados.ESPERA_SOLDADURA),
            ("Espera Pintura", estados.ESPERA_PINTURA),
        ],
    )
    def test_resuelve_las_variantes_historicas(self, variante, esperado):
        assert estados.normalizar(variante) == esperado

    def test_mejora_sobre_el_comportamiento_anterior(self):
        """El parche original sólo reconocía la variante en mayúsculas.

        `_norm_estado` comparaba contra un diccionario cuyas claves estaban en
        mayúsculas, así que "espera armado" en minúsculas no se reconocía y la
        orden se quedaba fuera de los filtros.
        """
        assert estados.normalizar("espera armado") == estados.ESPERA_ARMADO
        assert estados.normalizar("Espera armado") == estados.ESPERA_ARMADO

    def test_un_estado_desconocido_se_conserva(self):
        """Preferible mostrar algo raro a perder la orden."""
        assert estados.normalizar("Granallado") == "Granallado"

    def test_vacio_devuelve_vacio(self):
        assert estados.normalizar("") == ""
        assert estados.normalizar(None) == ""


class TestPosicionYRetroceso:
    def test_el_estado_de_cierre_esta_dentro_de_la_secuencia(self):
        """Es el defecto de control de acceso que corrige este módulo.

        `"Terminado (bloqueo pend.)"` no aparecía en ninguna de las listas de
        estados que usaban las vistas. Al buscar su posición se obtenía -1, la
        comprobación `destino < actual` daba falso, y desde una orden cerrada
        se podía saltar a cualquier estado sin indicar motivo de retroceso.
        """
        assert estados.posicion(estados.CIERRE_PENDIENTE) is not None
        assert estados.CIERRE_PENDIENTE in estados.SECUENCIA_COMPLETA

    def test_desde_el_cierre_pendiente_volver_atras_es_retroceso(self):
        assert estados.es_retroceso(estados.CIERRE_PENDIENTE, estados.SOLDADURA) is True

    def test_avanzar_no_es_retroceso(self):
        assert estados.es_retroceso(estados.CORTE, estados.SOLDADURA) is False

    def test_retroceder_lo_es(self):
        assert estados.es_retroceso(estados.SOLDADURA, estados.CORTE) is True

    def test_un_estado_desconocido_devuelve_none_y_no_falso(self):
        """Devolver None obliga a decidir; devolver -1 desactivaba la regla.

        Con la implementación anterior, un estado fuera de la lista daba
        índice -1 y la comparación resultaba falsa, así que el sistema
        concluía «no es retroceso» y dejaba pasar el cambio sin motivo.
        """
        assert estados.es_retroceso("Granallado", estados.CORTE) is None
        assert estados.posicion("Granallado") is None

    def test_las_variantes_encuentran_su_posicion(self):
        assert estados.posicion("Espera Armado") == estados.posicion(estados.ESPERA_ARMADO)


class TestColores:
    def test_las_variantes_dan_el_mismo_color(self):
        """Antes había dos diccionarios distintos, uno por módulo de vistas.

        El de catalogos usaba la clave "Espera Armado" y el de produccion
        "Espera de armado", así que el mismo estado se pintaba de un color o
        de otro según la pantalla.
        """
        assert estados.color("Espera Armado") == estados.color(estados.ESPERA_ARMADO)

    def test_un_estado_desconocido_tiene_color_por_defecto(self):
        assert estados.color("Granallado") == estados.COLOR_POR_DEFECTO

    def test_todos_los_estados_de_la_secuencia_tienen_color(self):
        for estado in estados.SECUENCIA_COMPLETA:
            assert estados.color(estado) != estados.COLOR_POR_DEFECTO, estado


class TestJornada:
    def _momento(self, dia, hora, minuto=0):
        return timezone.make_aware(
            datetime.combine(dia, time(hora, minuto)), timezone.get_default_timezone()
        )

    def test_un_lunes_completo_son_nueve_horas(self):
        lunes = date(2026, 8, 3)
        assert lunes.weekday() == 0
        segundos = jornada.segundos_laborales(
            self._momento(lunes, 0), self._momento(lunes, 23, 59)
        )
        assert segundos == jornada.SEGUNDOS_POR_DIA_LABORAL
        # 7:30-13:00 son 5,5 h y 13:30-17:00 son 3,5 h.
        assert jornada.HORAS_POR_DIA_LABORAL == 9.0

    def test_la_comida_no_cuenta(self):
        lunes = date(2026, 8, 3)
        segundos = jornada.segundos_laborales(
            self._momento(lunes, 12), self._momento(lunes, 14)
        )
        # 12:00-13:00 y 13:30-14:00 = hora y media
        assert segundos == 90 * 60

    def test_la_noche_no_cuenta(self):
        lunes = date(2026, 8, 3)
        martes = date(2026, 8, 4)
        segundos = jornada.segundos_laborales(
            self._momento(lunes, 16, 30), self._momento(martes, 8, 0)
        )
        # 16:30-17:00 del lunes y 7:30-8:00 del martes = una hora
        assert segundos == 60 * 60

    def test_el_fin_de_semana_no_cuenta(self):
        sabado = date(2026, 8, 8)
        domingo = date(2026, 8, 9)
        assert sabado.weekday() == 5
        segundos = jornada.segundos_laborales(
            self._momento(sabado, 0), self._momento(domingo, 23, 59)
        )
        assert segundos == 0

    def test_un_intervalo_invertido_o_vacio_da_cero(self):
        lunes = date(2026, 8, 3)
        assert jornada.segundos_laborales(self._momento(lunes, 12), self._momento(lunes, 10)) == 0
        assert jornada.segundos_laborales(None, self._momento(lunes, 10)) == 0

    def test_la_semana_laboral_son_cuarenta_y_cinco_horas(self):
        """Es el tiempo disponible por máquina con el que el tablero calcula
        la disponibilidad: nueve horas por cinco días."""
        assert jornada.HORAS_POR_SEMANA_LABORAL == 45.0

    def test_coincide_con_el_calculo_original(self):
        """El módulo recoge el horario tal cual, sin cambiar los números.

        Se comprueba contra el helper que sigue vivo en produccion/views.py
        para tener la certeza de que la mudanza no altera ningún informe.
        """
        from produccion.views import _labor_seconds_between

        lunes = date(2026, 8, 3)
        casos = [
            (self._momento(lunes, 8), self._momento(lunes, 12)),
            (self._momento(lunes, 12), self._momento(lunes, 14)),
            (self._momento(lunes, 16, 30), self._momento(lunes + timedelta(days=1), 8)),
            (self._momento(lunes, 7), self._momento(lunes + timedelta(days=6), 18)),
        ]
        for desde, hasta in casos:
            assert jornada.segundos_laborales(desde, hasta) == _labor_seconds_between(desde, hasta)
