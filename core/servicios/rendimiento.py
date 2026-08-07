"""Cuánto tarda cada quien, y dónde se queda parado el material.

El taller quiere contestar tres preguntas, y hasta ahora no tenía con qué:

1. **¿Cuánto tarda esta persona en soldar una pieza?** Para saber quién está
   rindiendo y quién necesita ayuda.
2. **¿Cuánto tiempo pasa entre que algo se termina de cortar y alguien lo
   empieza a armar?** Ese hueco no es trabajo de nadie: es material parado, y
   suele ser la mitad del tiempo que tarda un pedido.
3. **¿Quién entrega mal y quién lo da por bueno?** De eso responde
   `core.servicios.entrega`, y aquí se cuenta.

De dónde salen los tiempos
--------------------------

De `ApunteDeTrabajo`, que ya se escribía en cada avance y guarda la etapa, la
hora y quién la movió. **No hace falta un cronómetro**: el cronómetro es la
diferencia entre dos apuntes seguidos de la misma pieza. Un apunte que dice
«entró en Corte a las 9:10» y el siguiente que dice «entró en Espera de armado
a las 9:52» son cuarenta y dos minutos de corte.

Eso tiene una consecuencia que conviene decir en voz alta: **sólo se puede
medir desde que existen los apuntes**. Lo anterior está en la bitácora
heredada, que guarda la hora pero no quién, así que sirve para las esperas
pero no para el rendimiento de una persona.

Por qué la mediana y no el promedio
-----------------------------------

Un cortador empieza una pieza el viernes a las cuatro y la cierra el lunes a
las ocho. Para el promedio son sesenta y cuatro horas de corte y le hunde el
número del mes entero; para la mediana es un dato más entre veinte. Mientras
no exista un calendario laboral que sepa descontar noches y fines de semana
—está previsto, no está hecho— la mediana es lo único que se puede enseñar sin
mentir. El promedio y el peor caso se dan al lado, porque el peor caso es
justamente donde hay que mirar.

A quién se le apunta el tiempo
------------------------------

A **quien cierra la etapa**, no a quien la abre. Es quien pulsa «Terminé
soldadura», o sea quien afirma que ese trabajo es suyo, y es el mismo que
firma la entrega. Casi siempre son la misma persona; cuando no lo son, que
cuente el que lo dio por hecho es lo coherente con el resto del sistema.
"""

from dataclasses import dataclass, field
from datetime import timedelta, timezone as dt_timezone

from django.utils import timezone

from core import estados
from core.bases import BASE  # noqa: F401


#: Las etapas en las que alguien está trabajando. El tiempo que una pieza pasa
#: aquí es trabajo de una persona.
DE_TRABAJO = {estados.CORTE, estados.ARMADO, estados.SOLDADURA, estados.PINTURA}

#: Las etapas en las que la pieza está parada esperando a que alguien la tome.
#: El tiempo aquí no es de nadie: es el hueco entre dos áreas, y es donde se
#: pierden los días de un pedido sin que aparezca en ningún indicador.
DE_ESPERA = {
    estados.ESPERA_CORTE,
    estados.ESPERA_ARMADO,
    estados.ESPERA_SOLDADURA,
    estados.ESPERA_PINTURA,
}


def _mediana(valores):
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    medio = len(ordenados) // 2
    if len(ordenados) % 2:
        return float(ordenados[medio])
    return (ordenados[medio - 1] + ordenados[medio]) / 2.0


@dataclass
class Medida:
    """Un montón de duraciones con lo que hay que saber de ellas."""

    segundos: list = field(default_factory=list)

    @property
    def muestras(self):
        return len(self.segundos)

    @property
    def mediana(self):
        return _mediana(self.segundos)

    @property
    def promedio(self):
        return sum(self.segundos) / len(self.segundos) if self.segundos else 0.0

    @property
    def peor(self):
        return max(self.segundos) if self.segundos else 0.0

    @property
    def total(self):
        return sum(self.segundos)


@dataclass
class FilaDePersona:
    """Lo que hizo una persona en una etapa."""

    usuario: str
    nombre: str = ""
    etapa: str = ""
    tiempos: Medida = field(default_factory=Medida)
    piezas: int = 0
    kilos: float = 0.0

    @property
    def muestras(self):
        return self.tiempos.muestras

    @property
    def kilos_por_hora(self):
        horas = self.tiempos.total / 3600.0
        return round(self.kilos / horas, 1) if horas > 0.01 else 0.0


@dataclass
class FilaDeEspera:
    """Cuánto se queda parado el material entre dos áreas."""

    etapa: str
    tiempos: Medida = field(default_factory=Medida)

    @property
    def muestras(self):
        return self.tiempos.muestras


@dataclass
class FilaDeCalidad:
    """La hoja de servicios de una persona en los traspasos."""

    usuario: str
    nombre: str = ""
    #: Entregas que hizo y que la siguiente área aceptó.
    entregas_buenas: int = 0
    #: Entregas suyas que le devolvieron. Trabajo que hubo que rehacer.
    devueltas: int = 0
    #: Devoluciones que **él** detectó al recibir. Cuenta a favor: es la
    #: revisión que se le pide, y si contara en contra nadie devolvería nada.
    detectadas: int = 0
    #: Piezas que él aceptó y firmó como buenas, y que más adelante se
    #: devolvieron. Es el «que la cobren entre los dos».
    dio_por_buenas_y_salieron_mal: int = 0

    @property
    def entregas(self):
        return self.entregas_buenas + self.devueltas

    @property
    def porcentaje_bueno(self):
        return round(self.entregas_buenas / self.entregas * 100) if self.entregas else None


# ------------------------------------------------------------------- tramos


def _nombres_de_cuenta():
    """De nombre de usuario al nombre de la persona, para poder leerlo."""
    from catalogos.models import Colaborador

    return {
        c.usuario: c.nombre
        for c in Colaborador.objects.using(BASE).exclude(usuario="").only(
            "usuario", "nombre"
        )
    }


def tramos(desde, hasta, linea="vigas"):
    """Cada rato que una pieza pasó en una etapa, dentro del rango.

    Devuelve tuplas `(referencia, etapa, segundos, quien_la_cerró)`.

    El rango se aplica al **cierre** del tramo: un corte que empezó ayer y se
    cerró hoy cuenta hoy, que es cuando se hizo el trabajo que se está
    midiendo. Se leen apuntes desde antes del rango para poder cerrar los
    tramos que lo cruzan; sin ese margen, todo lo que empieza al final de un
    día y acaba al principio del siguiente desaparecería del informe.
    """
    from catalogos.models import ApunteDeTrabajo

    margen = desde - timedelta(days=14)
    filas = list(
        ApunteDeTrabajo.objects.using(BASE)
        .filter(linea=linea, ocurrido_en__gte=margen, ocurrido_en__lt=hasta)
        .order_by("referencia", "ocurrido_en")
        .values("referencia", "etapa", "ocurrido_en", "actor")
    )

    resultado = []
    for i in range(len(filas) - 1):
        actual, siguiente = filas[i], filas[i + 1]
        if actual["referencia"] != siguiente["referencia"]:
            continue
        if siguiente["ocurrido_en"] < desde:
            continue
        segundos = (siguiente["ocurrido_en"] - actual["ocurrido_en"]).total_seconds()
        if segundos <= 0:
            # Dos apuntes en el mismo instante: un avance en lote, que escribe
            # una fila por pieza. No es un tramo, es la misma marca de tiempo.
            continue
        resultado.append(
            (
                int(actual["referencia"]),
                estados.normalizar(actual["etapa"]),
                segundos,
                # Quien cierra la etapa, no quien la abre. Ver la cabecera.
                siguiente["actor"] or "",
            )
        )
    return resultado


def por_persona(desde, hasta):
    """Cuánto tarda cada quien en cada etapa, y cuánto material movió."""
    from produccion.models import Viga

    lista = tramos(desde, hasta)
    de_trabajo = [t for t in lista if t[1] in DE_TRABAJO and t[3]]
    if not de_trabajo:
        return []

    pesos = dict(
        Viga.objects.using(BASE)
        .filter(internal_id__in={t[0] for t in de_trabajo})
        .values_list("internal_id", "peso_kg")
    )
    nombres = _nombres_de_cuenta()

    filas = {}
    for referencia, etapa, segundos, quien in de_trabajo:
        clave = (quien, etapa)
        fila = filas.get(clave)
        if fila is None:
            filas[clave] = fila = FilaDePersona(
                usuario=quien, nombre=nombres.get(quien, quien), etapa=etapa
            )
        fila.tiempos.segundos.append(segundos)
        fila.piezas += 1
        fila.kilos += float(pesos.get(referencia) or 0)

    # Quien más trabajo cerró, primero. La pregunta de esta pantalla es quién
    # está rindiendo, y para eso hace falta ver antes a quien tiene muestras
    # suficientes para que su número signifique algo.
    return sorted(filas.values(), key=lambda f: (-f.piezas, f.nombre, f.etapa))


def esperas(desde, hasta):
    """Cuánto se queda el material parado entre un área y la siguiente."""
    filas = {}
    for _, etapa, segundos, _ in tramos(desde, hasta):
        if etapa not in DE_ESPERA:
            continue
        fila = filas.get(etapa)
        if fila is None:
            filas[etapa] = fila = FilaDeEspera(etapa=etapa)
        fila.tiempos.segundos.append(segundos)

    # En el orden en que el material las recorre, que es como se lee un
    # cuello de botella: se busca dónde se atasca, no cuál es el mayor.
    return sorted(filas.values(), key=lambda f: estados.posicion(f.etapa) or 0)


def parado_ahora():
    """Lo que está esperando **en este momento**, y desde cuándo.

    El histórico dice dónde se atasca de costumbre; esto dice qué está atascado
    ahora, que es lo único sobre lo que se puede hacer algo hoy.
    """
    from produccion.models import Viga

    ahora = timezone.now()
    filas = []
    for etapa in sorted(DE_ESPERA, key=lambda e: estados.posicion(e) or 0):
        piezas = list(
            Viga.objects.using(BASE)
            .filter(estado__in=estados.variantes(etapa))
            .values("internal_id", "codigo_viga", "proyecto", "ultimo_cambio")
            .order_by("ultimo_cambio")[:200]
        )
        if not piezas:
            continue
        # `ultimo_cambio` viene de la tabla heredada sin zona horaria, y lo que
        # guarda es **UTC**, no la hora local. Interpretarlo como local le
        # restaría seis horas a cada espera de este taller: una pieza parada
        # desde hace treinta horas se leería como veinticuatro. La misma
        # conversión que hace `views._format_utc_naive_dt_as_local`.
        esperas_seg = []
        for pieza in piezas:
            marca = pieza["ultimo_cambio"]
            if marca is None:
                continue
            if timezone.is_naive(marca):
                marca = timezone.make_aware(marca, dt_timezone.utc)
            esperas_seg.append((ahora - marca).total_seconds())
        if not esperas_seg:
            continue
        filas.append({
            "etapa": etapa,
            "piezas": len(piezas),
            "la_que_mas": max(esperas_seg),
            "mediana": _mediana(esperas_seg),
        })
    return filas


def calidad(desde, hasta):
    """Quién entrega bien, quién devuelve, y quién dio por bueno lo que no lo era."""
    from core.servicios import entrega as servicio_entrega
    from nucleo.models import ActaDeEntrega

    actas = list(
        ActaDeEntrega.objects.using(BASE)
        .filter(entregado_en__gte=desde, entregado_en__lt=hasta)
        .order_by("entregado_en")
    )
    nombres = _nombres_de_cuenta()

    filas = {}

    def de(usuario):
        if not usuario:
            return None
        fila = filas.get(usuario)
        if fila is None:
            filas[usuario] = fila = FilaDeCalidad(
                usuario=usuario, nombre=nombres.get(usuario, usuario)
            )
        return fila

    for acta in actas:
        quien_entrega = de(acta.entrega_por)
        if acta.estado == ActaDeEntrega.Estado.ACEPTADA and quien_entrega:
            quien_entrega.entregas_buenas += 1
        elif acta.estado == ActaDeEntrega.Estado.RECHAZADA:
            if quien_entrega:
                quien_entrega.devueltas += 1
            detectó = de(acta.recibe_por)
            if detectó:
                detectó.detectadas += 1
            # Y quien la había dado por buena en el escalón anterior. Es la
            # pregunta del taller: si llegan a pintura dos vigas que no miden
            # lo que debían, responde quien las soldó y también quien las
            # aceptó de corte diciendo que estaban bien.
            firmó_antes = de(servicio_entrega.quien_la_dio_por_buena(acta))
            if firmó_antes:
                firmó_antes.dio_por_buenas_y_salieron_mal += 1

    return sorted(filas.values(), key=lambda f: (-f.devueltas, -f.entregas, f.nombre))
