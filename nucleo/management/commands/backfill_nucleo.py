"""Copia las órdenes heredadas al núcleo y les reconstruye el historial.

Es el paso 3 de la migración. **No modifica ni una fila de las tablas
heredadas**: sólo lee. Se puede volver a ejecutar tantas veces como haga
falta, porque cada fila del núcleo recuerda de cuál salió
(`legacy_modelo`, `legacy_id`) y se localiza por ahí.

    python manage.py backfill_nucleo --linea corta --simular
    python manage.py backfill_nucleo --linea corta
    python manage.py backfill_nucleo            # las cuatro

Qué hace, en orden:

1. **Clientes y obras.** Hoy hay tres conceptos sin relación entre sí
   (`Proyecto`, `HerrCliente`, `CortaClienteProyecto`) más un campo de texto
   libre en vigas. Aquí se copian tal cual, cada uno a su sitio. Las que sean
   la misma empresa escrita de dos formas **no se fusionan aquí**: eso lo
   propone `fusionar_clientes` en un CSV y lo aprueba una persona, porque dos
   nombres parecidos pueden ser dos empresas distintas y unirlas mal
   contamina la facturación.

2. **Piezas de catálogo**, de los tres catálogos que hay a uno.

3. **Órdenes.** Con el folio heredado conservado: durante la convivencia una
   orden migrada mantiene el número que ya está impreso. Los folios nuevos
   salen de la secuencia, muy por encima.

4. **Historial.** Se reconstruye desde las bitácoras que sí existen:
   `HerrEstadoCambio`, `HerrAvanceCambio`, `LaserEstadoCambio` y
   `production_log`. Donde no hay bitácora —el avance por contadores de corte
   láser no dejó ninguna— se emite un evento de ajuste marcado
   `sin_historico`. **No se inventan fechas ni autores.** Rellenar los huecos
   con datos plausibles destruiría justamente la trazabilidad que motiva todo
   esto; un hueco declarado es información, un hueco disimulado es mentira.

5. **Asignaciones**, de las seis tablas que hay a una.

Al final, para cada orden, los contadores del núcleo cuadran con la suma de su
historial. Si algo no cuadra es porque se emitió el ajuste correspondiente, y
`verificar_backfill` lo cuenta.
"""

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalogos.models import (
    CortaClienteProyecto,
    CortaPiezaCatalogo,
    HerrAsignacion,
    HerrAvanceCambio,
    HerrCliente,
    HerrEstadoCambio,
    HerrOrdenAsignacion,
    HerrOrdenProduccion,
    HerrPiezaCatalogo,
    LaserAsignacion,
    LaserEstadoCambio,
    LaserOrdenAsignacion,
    LaserOrdenProduccion,
    RobotOrdenAsignacion,
    RobotOrdenProduccion,
    RobotPiezaCatalogo,
    VigaAsignacion,
)
from core.servicios import especificaciones as servicio_especificaciones
from core.servicios import ruta as servicio_ruta
from nucleo.management.commands.sembrar_nucleo import clave, codigo_de
from nucleo.models import (
    Asignacion,
    Cliente,
    Etapa,
    EtapaAlias,
    EventoProduccion,
    LineaNegocio,
    MotivoEvento,
    Obra,
    OrdenProduccion,
    PiezaCatalogo,
)
from produccion.models import ProductionLog, Viga
from core.bases import BASE  # noqa: F401


#: Cuando una orden heredada tiene proyecto pero no cliente —que es la
#: mayoría—, la obra tiene que colgar de algo. Este cliente marcador existe
#: para no inventarse empresas, y para que `fusionar_clientes` sepa
#: exactamente dónde mirar después.
CLIENTE_SIN_ASIGNAR = "(sin cliente asignado)"

#: Comentario con el que el sistema heredado marca los cierres automáticos.
MARCA_CIERRE_AUTOMATICO = "auto_bloqueo"


def con_zona(valor):
    """Interpreta en la zona del taller las fechas que vienen sin zona.

    La tabla heredada `vigas` es anterior a que el proyecto activara el
    soporte de zonas horarias, así que sus marcas de tiempo no la llevan.
    Guardarlas tal cual haría que Django las tratara como UTC y todo el
    historial de vigas se desplazaría seis horas: los avances de primera hora
    aparecerían el día anterior. Siempre significaron hora local, y así se
    leen.
    """
    if valor is None or timezone.is_aware(valor):
        return valor
    return timezone.make_aware(valor, timezone.get_default_timezone())


def a_decimal(valor, decimales=3):
    plantilla = Decimal(1).scaleb(-decimales)
    try:
        return Decimal(str(valor or 0)).quantize(plantilla)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(0).quantize(plantilla)


def peso_unitario(total_kg, piezas):
    """Reparte el peso de la orden entre sus piezas sin perder gramos.

    Se hace con `Decimal` desde el principio y a seis decimales. Con tres, una
    orden de cuatro piezas y 6.518 kg volvía a salir como 6.520 al
    multiplicar: dos gramos por orden que, sumados sobre un año de producción,
    descuadran las toneladas del tablero.
    """
    piezas = max(int(piezas or 1), 1)
    return (a_decimal(total_kg, 6) / piezas).quantize(Decimal("0.000001"))


class Command(BaseCommand):
    help = "Copia las órdenes heredadas al núcleo y reconstruye su historial."

    def add_arguments(self, parser):
        parser.add_argument(
            "--linea",
            choices=["vigas", "herreria", "corta", "robotica"],
            help="Sólo una línea. Por omisión, las cuatro.",
        )
        parser.add_argument("--simular", action="store_true", help="No escribe nada.")
        parser.add_argument("--lote", type=int, default=500, help="Filas por transacción.")
        parser.add_argument(
            "--limite", type=int, default=0, help="Tope de órdenes, para una prueba rápida."
        )

    def handle(self, *args, **opciones):
        self.simular = opciones["simular"]
        self.lote = max(int(opciones["lote"] or 500), 1)
        self.limite = max(int(opciones["limite"] or 0), 0)
        self.ahora = timezone.now()
        self.contadas = {}

        if not LineaNegocio.objects.using(BASE).exists():
            raise CommandError(
                "No hay configuración del núcleo. Ejecutar antes `sembrar_nucleo`."
            )

        if self.simular:
            self.stdout.write(self.style.WARNING("Simulación: nada de esto se guarda.\n"))

        lineas = [opciones["linea"]] if opciones.get("linea") else [
            "robotica", "corta", "herreria", "vigas"
        ]

        for nombre in lineas:
            with transaction.atomic(using=BASE):
                self._volcar(nombre)
                if self.simular:
                    transaction.set_rollback(True, using=BASE)

        self._resumen()

    # --------------------------------------------------- una sola fila
    #
    # La escritura doble usa exactamente este mismo código, fila a fila. Es
    # deliberado: si el volcado inicial y la escritura doble tuvieran cada uno
    # su propio mapeo, acabarían diciendo cosas distintas, que es literalmente
    # la enfermedad que esta fase viene a curar. Un solo mapeo, dos formas de
    # invocarlo.

    @classmethod
    def para_espejo(cls):
        """El comando preparado para usarse desde una vista, no desde la consola."""
        comando = cls()
        comando.simular = False
        comando.lote = 500
        comando.limite = 0
        comando.ahora = timezone.now()
        comando.contadas = {}
        return comando

    def volcar_una(self, etiqueta, pk):
        """Refleja en el núcleo una sola fila heredada. Devuelve la orden."""
        despacho = {
            "HerrOrdenProduccion": ("herreria", HerrOrdenProduccion, self._fila_herreria),
            "LaserOrdenProduccion": ("corta", LaserOrdenProduccion, self._fila_corta),
            "RobotOrdenProduccion": ("robotica", RobotOrdenProduccion, self._fila_robotica),
            "Viga": ("vigas", Viga, self._fila_vigas),
        }
        if etiqueta not in despacho:
            raise ValueError(f"no sé reflejar {etiqueta!r}")

        codigo, modelo, metodo = despacho[etiqueta]
        fila = modelo.objects.using(BASE).filter(pk=pk).first()
        if fila is None:
            return None

        linea = self._linea(codigo)
        if etiqueta == "RobotOrdenProduccion":
            contexto = Etapa.objects.using(BASE).filter(linea=linea).order_by("orden").first()
        else:
            contexto = self._mapa_etapas(linea)
        return metodo(fila, linea, contexto)

    # -------------------------------------------------------------- común

    def _linea(self, codigo):
        return LineaNegocio.objects.using(BASE).get(codigo=codigo)

    def _mapa_etapas(self, linea):
        """De cualquier escritura histórica a la etapa que le corresponde."""
        mapa = {}
        for alias in EtapaAlias.objects.using(BASE).filter(etapa__linea=linea).select_related("etapa"):
            mapa[alias.valor_normalizado] = alias.etapa
        return mapa

    def _cliente_marcador(self):
        cliente, _ = Cliente.objects.using(BASE).get_or_create(
            nombre_normalizado=CLIENTE_SIN_ASIGNAR.upper(),
            defaults={"nombre": CLIENTE_SIN_ASIGNAR, "origen": "migracion"},
        )
        return cliente

    def _cliente(self, nombre, origen):
        nombre = (nombre or "").strip()
        if not nombre:
            return self._cliente_marcador()
        cliente, creado = Cliente.objects.using(BASE).get_or_create(
            nombre_normalizado=nombre.upper(),
            defaults={"nombre": nombre, "origen": origen},
        )
        self._contar("clientes", int(creado))
        return cliente

    def _obra(self, cliente, nombre, legacy_modelo="", legacy_id=None):
        nombre = (nombre or "").strip()
        if not nombre:
            return None
        obra, creada = Obra.objects.using(BASE).get_or_create(
            cliente=cliente,
            nombre_normalizado=nombre.upper(),
            defaults={
                "nombre": nombre,
                "legacy_modelo": legacy_modelo,
                "legacy_id": legacy_id,
            },
        )
        self._contar("obras", int(creada))
        return obra

    def _contar(self, etiqueta, cuantos=1):
        self.contadas[etiqueta] = self.contadas.get(etiqueta, 0) + cuantos

    def _evento(self, orden, legacy_modelo, legacy_id, **campos):
        """Inserta un evento si no está ya. Devuelve (evento, es_nuevo)."""
        campos.setdefault("metadata", {})
        campos["ocurrido_en"] = con_zona(campos.get("ocurrido_en")) or self.ahora
        if legacy_id is not None:
            evento, creado = EventoProduccion.objects.using(BASE).get_or_create(
                legacy_modelo=legacy_modelo,
                legacy_id=legacy_id,
                defaults={"orden": orden, **campos},
            )
        else:
            evento = EventoProduccion.objects.using(BASE).create(
                orden=orden, legacy_modelo=legacy_modelo, **campos
            )
            creado = True
        self._contar("eventos", int(creado))
        return evento, creado

    # ------------------------------------------------------------ catálogo

    def _volcar_piezas(self, linea, modelo, etiqueta, con_archivos=False):
        """Vuelca un catálogo de piezas, adoptando lo que ya esté puesto.

        La búsqueda es por el enlace al legado, y si no lo encuentra, **por el
        nombre dentro de la línea**. Esa segunda pasada es lo que faltaba: en
        el núcleo puede haber piezas que nadie volcó —las que sembró la
        configuración, o las que alguien dio de alta a mano en la pantalla— y
        que no llevan enlace. Sin adoptarlas, el volcado intentaba insertar
        una segunda pieza con el mismo nombre y moría contra
        `pieza_unica_por_linea`, con un mensaje que no explicaba nada.

        Adoptar significa ponerle el enlace a la que ya existe, no crear otra.
        Duplicar el catálogo sería peor que fallar: las órdenes quedarían
        repartidas entre dos piezas que son la misma.
        """
        for fila in modelo.objects.using(BASE).all():
            nombre_normalizado = (fila.nombre or "").upper()
            defaults = {
                "linea": linea,
                "nombre": fila.nombre,
                "nombre_normalizado": nombre_normalizado,
                "activo": fila.activo,
            }
            if con_archivos:
                defaults["pdf"] = fila.pdf
                defaults["dxf"] = fila.dxf
            else:
                defaults["peso_kg"] = a_decimal(getattr(fila, "peso_kg", 0))

            pieza = (
                PiezaCatalogo.objects.using(BASE)
                .filter(legacy_modelo=etiqueta, legacy_id=fila.pk)
                .first()
            )
            if pieza is None:
                pieza = (
                    PiezaCatalogo.objects.using(BASE)
                    .filter(linea=linea, nombre_normalizado=nombre_normalizado)
                    .first()
                )
                if pieza is not None:
                    pieza.legacy_modelo = etiqueta
                    pieza.legacy_id = fila.pk

            if pieza is None:
                PiezaCatalogo.objects.using(BASE).create(
                    legacy_modelo=etiqueta, legacy_id=fila.pk, **defaults
                )
                self._contar("piezas", 1)
                continue

            for campo, valor in defaults.items():
                setattr(pieza, campo, valor)
            pieza.save(using=BASE)
            self._contar("piezas", 0)

    def _pieza_de(self, etiqueta, legacy_id):
        if not legacy_id:
            return None
        return (
            PiezaCatalogo.objects.using(BASE)
            .filter(legacy_modelo=etiqueta, legacy_id=legacy_id)
            .first()
        )

    def _pieza_por_nombre(self, linea, nombre):
        """La pieza de catálogo de esa línea que se llama así, o `None`.

        Herrería no guarda a qué pieza del catálogo corresponde una orden:
        copia el nombre y ahí se acaba el vínculo. Así que se busca por el
        nombre normalizado, que es la misma clave con la que el catálogo se
        declara único. No es una relación de verdad —dos piezas distintas con
        el mismo nombre serían la misma para esto— pero el catálogo ya prohíbe
        justamente eso.
        """
        nombre = (nombre or "").strip().upper()
        if not nombre:
            return None
        return (
            PiezaCatalogo.objects.using(BASE)
            .filter(linea=linea, nombre_normalizado=nombre)
            .first()
        )

    def _heredar_del_lote(self, orden):
        """Una orden recién creada nace sabiendo por dónde pasa y cómo se hace.

        Un andamio que no se pinta lo dice su pieza de catálogo; una viga más
        de un pedido de cincuenta lo dicen sus hermanas. Sin esto, la ruta y
        las instrucciones había que escribirlas a mano en cada pedido y en
        cada pieza, y el día que se olvidara, la pieza se formaba en una cola
        por la que no iba a pasar, o llegaba al soldador sin decirle dónde va
        el corte.

        Sólo actúa al dar de alta. Cambiar lo recordado de una pieza no
        reescribe lo que ya va por medio taller.
        """
        heredada = servicio_ruta.heredada(orden)
        if heredada and list(orden.ruta or []) != list(heredada):
            orden.ruta = list(heredada)
            orden.save(using=BASE, update_fields=["ruta", "actualizado_en"])

        texto = servicio_especificaciones.heredadas(orden)
        if texto:
            servicio_especificaciones.guardar_en_una(
                orden.legacy_modelo, orden.legacy_id, texto, quien="alta"
            )

    # ------------------------------------------------------------ despacho

    def _volcar(self, nombre):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{nombre}"))
        getattr(self, f"_volcar_{nombre}")()

    # ------------------------------------------------------------ herrería

    def _volcar_herreria(self):
        linea = self._linea("herreria")
        etapas = self._mapa_etapas(linea)
        self._volcar_piezas(linea, HerrPiezaCatalogo, "HerrPiezaCatalogo")

        for fila in HerrCliente.objects.using(BASE).all():
            self._cliente(fila.nombre, "HerrCliente")

        consulta = HerrOrdenProduccion.objects.using(BASE).order_by("pk")
        if self.limite:
            consulta = consulta[: self.limite]

        for fila in consulta.iterator(chunk_size=self.lote):
            self._fila_herreria(fila, linea, etapas)

        self._volcar_asignaciones(
            linea, HerrAsignacion, "HerrAsignacion", "HerrOrdenProduccion", etapas, con_rol=True
        )
        self._volcar_asignaciones(
            linea, HerrOrdenAsignacion, "HerrOrdenAsignacion", "HerrOrdenProduccion", etapas
        )

    def _fila_herreria(self, fila, linea, etapas):
        cliente = (
            self._cliente(fila.cliente_herreria.nombre, "HerrCliente")
            if fila.cliente_herreria_id
            else self._cliente_marcador()
        )
        obra = (
            self._obra(cliente, fila.proyecto.nombre, "Proyecto", fila.proyecto_id)
            if fila.proyecto_id
            else None
        )
        total = max(int(fila.total_piezas or 1), 1)
        orden = self._guardar_orden(
            linea=linea,
            etiqueta="HerrOrdenProduccion",
            fila=fila,
            cliente=cliente,
            obra=obra,
            etapa=etapas.get(clave(fila.estado_etapa)),
            # `peso_kg` es el peso total de la orden: se fija como
            # `kg_pieza * total` al darla de alta.
            peso_unitario=peso_unitario(fila.peso_kg, total),
            # Herrería no guarda de qué pieza del catálogo salió la orden:
            # copia el nombre y ahí acaba el vínculo. Se reconstruye por el
            # nombre, que es lo que hace que una orden nueva pueda heredar la
            # ruta y las instrucciones de lo que se fabrica todas las semanas.
            pieza=self._pieza_por_nombre(linea, fila.nombre),
            atributos={
                "pieza_no": int(fila.pieza_no or 1),
                "es_op": bool(fila.es_op),
                "plano_pdf": fila.plano_pdf.name if fila.plano_pdf else "",
            },
        )
        self._historial_herreria(orden, fila, etapas)
        self._cuadrar(orden, fila.cantidad_producida, fila.cantidad_pintada, fila.cantidad_terminada)
        return orden

    def _historial_herreria(self, orden, fila, etapas):
        for cambio in HerrEstadoCambio.objects.using(BASE).filter(orden_id=fila.pk).order_by("pk"):
            self._evento_cambio_etapa(orden, cambio, etapas, "HerrEstadoCambio")
        for avance in HerrAvanceCambio.objects.using(BASE).filter(orden_id=fila.pk).order_by("pk"):
            self._eventos_avance(orden, avance, "HerrAvanceCambio")

    # ---------------------------------------------------------- corte láser

    def _volcar_corta(self):
        linea = self._linea("corta")
        etapas = self._mapa_etapas(linea)
        self._volcar_piezas(linea, CortaPiezaCatalogo, "CortaPiezaCatalogo", con_archivos=True)

        consulta = LaserOrdenProduccion.objects.using(BASE).order_by("pk")
        if self.limite:
            consulta = consulta[: self.limite]

        for fila in consulta.iterator(chunk_size=self.lote):
            self._fila_corta(fila, linea, etapas)

        self._volcar_asignaciones(
            linea, LaserAsignacion, "LaserAsignacion", "LaserOrdenProduccion", etapas, con_rol=True
        )
        self._volcar_asignaciones(
            linea, LaserOrdenAsignacion, "LaserOrdenAsignacion", "LaserOrdenProduccion", etapas
        )

    def _fila_corta(self, fila, linea, etapas):
        cliente, obra = self._cliente_de_corta(fila)
        total = max(int(fila.total_piezas or 1), 1)
        orden = self._guardar_orden(
            linea=linea,
            etiqueta="LaserOrdenProduccion",
            fila=fila,
            cliente=cliente,
            obra=obra,
            etapa=etapas.get(clave(fila.estado_etapa)),
            peso_unitario=peso_unitario(fila.peso_kg, total),
            pieza=self._pieza_de("CortaPiezaCatalogo", fila.corta_pieza_id),
            atributos={
                "pieza_no": int(fila.pieza_no or 1),
                "es_op": bool(fila.es_op),
                "folio_externo": fila.folio_externo,
                "correo": fila.correo,
                "telefono": fila.telefono,
                "material_id": fila.material_id,
                "pieza_ancho_mm": int(fila.pieza_ancho_mm or 0),
                "pieza_alto_mm": int(fila.pieza_alto_mm or 0),
                "logo_ancho_mm": int(fila.logo_ancho_mm or 0),
                "logo_alto_mm": int(fila.logo_alto_mm or 0),
                "apartado": int(fila.apartado or 0),
                "enviado": int(fila.enviado or 0),
                "archivo": fila.archivo.name if fila.archivo else "",
                "archivo_dxf": fila.archivo_dxf.name if fila.archivo_dxf else "",
            },
        )
        for cambio in (
            LaserEstadoCambio.objects.using(BASE).filter(orden_id=fila.pk).order_by("pk")
        ):
            self._evento_cambio_etapa(orden, cambio, etapas, "LaserEstadoCambio")
        # Corte láser no tiene bitácora de avance: los contadores se
        # movían sin dejar rastro. Todo lo que no cuadre sale como ajuste
        # declarado, que es la única forma honesta de cerrarlo.
        self._cuadrar(
            orden, fila.cantidad_producida, fila.cantidad_pintada, fila.cantidad_terminada
        )
        return orden

    def _cliente_de_corta(self, fila):
        """En corta, cliente y proyecto son el mismo campo con una etiqueta.

        `CortaClienteProyecto.tipo` dice si esa fila es una empresa, una obra
        o las dos cosas a la vez. Se respeta tal cual: donde el dato heredado
        no distingue, aquí tampoco se inventa la distinción.
        """
        if not fila.corta_cliente_proyecto_id:
            base = self._cliente_marcador()
            obra = (
                self._obra(base, fila.proyecto.nombre, "Proyecto", fila.proyecto_id)
                if fila.proyecto_id
                else None
            )
            return base, obra

        origen = fila.corta_cliente_proyecto
        if origen.tipo == CortaClienteProyecto.TIPO_CHOICES[1][0]:  # "proyecto"
            cliente = self._cliente_marcador()
            obra = self._obra(cliente, origen.nombre, "CortaClienteProyecto", origen.pk)
            return cliente, obra

        cliente = self._cliente(origen.nombre, "CortaClienteProyecto")
        obra = (
            self._obra(cliente, fila.proyecto.nombre, "Proyecto", fila.proyecto_id)
            if fila.proyecto_id
            else None
        )
        return cliente, obra

    # ------------------------------------------------------------ robótica

    def _volcar_robotica(self):
        linea = self._linea("robotica")
        etapas = self._mapa_etapas(linea)
        self._volcar_piezas(linea, RobotPiezaCatalogo, "RobotPiezaCatalogo")

        consulta = RobotOrdenProduccion.objects.using(BASE).order_by("pk")
        if self.limite:
            consulta = consulta[: self.limite]

        primera = Etapa.objects.using(BASE).filter(linea=linea).order_by("orden").first()

        for fila in consulta.iterator(chunk_size=self.lote):
            self._fila_robotica(fila, linea, primera)

        self._volcar_asignaciones(
            linea, RobotOrdenAsignacion, "RobotOrdenAsignacion", "RobotOrdenProduccion", etapas
        )

    def _fila_robotica(self, fila, linea, primera):
        cliente = self._cliente_marcador()
        obra = (
            self._obra(cliente, fila.proyecto.nombre, "Proyecto", fila.proyecto_id)
            if fila.proyecto_id
            else None
        )
        # Robótica no guarda peso en la orden: está en las partidas.
        peso = sum(
            a_decimal(item.pieza_peso_kg) * int(item.cantidad_requerida or 1)
            for item in fila.items.all()
        )
        objetivo = max(int(fila.cantidad_objetivo or 1), 1)
        orden = self._guardar_orden(
            linea=linea,
            etiqueta="RobotOrdenProduccion",
            fila=fila,
            cliente=cliente,
            obra=obra,
            etapa=primera,
            peso_unitario=peso_unitario(peso, objetivo),
            atributos={"producto": fila.producto},
            codigo=fila.nombre or fila.producto,
            total_piezas=objetivo,
        )
        self._cuadrar(orden, 0, 0, 0)
        return orden

    # -------------------------------------------------------------- vigas

    def _volcar_vigas(self):
        linea = self._linea("vigas")
        etapas = self._mapa_etapas(linea)

        consulta = Viga.objects.using(BASE).order_by("internal_id")
        if self.limite:
            consulta = consulta[: self.limite]

        for fila in consulta.iterator(chunk_size=self.lote):
            self._fila_vigas(fila, linea, etapas)

        self._volcar_asignaciones(
            linea, VigaAsignacion, "VigaAsignacion", "Viga", etapas, con_rol=True
        )

    def _fila_vigas(self, fila, linea, etapas):
        terminadas = {clave("Terminado"), clave("Enviado")}
        cliente = self._cliente_marcador()
        obra = self._obra(cliente, fila.proyecto, "Viga.proyecto")
        etapa = etapas.get(clave(fila.estado))

        # Cada fila de `vigas` es **una** pieza: `total_piezas` dice de
        # cuántas consta el conjunto, no cuántas hay en esta fila. Por eso
        # el peso de la fila es el peso unitario y el objetivo es uno.
        orden = self._guardar_orden(
            linea=linea,
            etiqueta="Viga",
            fila=fila,
            cliente=cliente,
            obra=obra,
            etapa=etapa,
            peso_unitario=peso_unitario(fila.peso_kg, 1),
            codigo=fila.codigo_viga,
            total_piezas=1,
            pk=fila.internal_id,
            creado_en=fila.fecha_creacion,
            atributos={
                "pieza_no": int(fila.pieza_no or 1),
                "piezas_del_conjunto": int(fila.total_piezas or 1),
            },
        )

        momento_terminado = None
        for registro in (
            ProductionLog.objects.using(BASE)
            .filter(viga_internal_id=fila.internal_id)
            .order_by("pk")
        ):
            self._evento(
                orden,
                "ProductionLog",
                registro.pk,
                tipo=EventoProduccion.Tipo.CAMBIO_ETAPA,
                etapa_anterior=etapas.get(clave(registro.estado_anterior)),
                etapa=etapas.get(clave(registro.estado_nuevo)),
                comentario=(registro.comentario or "")[:255],
                fecha_operacion=registro.fecha_operacion,
                ocurrido_en=registro.timestamp,
            )
            if clave(registro.estado_nuevo) in terminadas and momento_terminado is None:
                momento_terminado = (registro.timestamp, registro.fecha_operacion)

        # La viga terminada cuenta como una pieza hecha, y se apunta con
        # la fecha real del cambio de estado, no con la de hoy.
        if clave(fila.estado) in terminadas and momento_terminado:
            self._evento(
                orden,
                "Viga.terminada",
                fila.internal_id,
                tipo=EventoProduccion.Tipo.AVANCE,
                etapa=etapa,
                contador=EventoProduccion.Contador.TERMINADA,
                delta_cantidad=1,
                cantidad_resultante=1,
                ocurrido_en=momento_terminado[0],
                fecha_operacion=momento_terminado[1],
                comentario="derivado del cambio de estado",
            )

        objetivo = 1 if clave(fila.estado) in terminadas else 0
        self._cuadrar(orden, objetivo, objetivo, objetivo)
        return orden

    # ------------------------------------------------------- órdenes común

    def _guardar_orden(
        self,
        *,
        linea,
        etiqueta,
        fila,
        cliente,
        obra,
        etapa,
        peso_unitario,
        atributos,
        pieza=None,
        codigo=None,
        total_piezas=None,
        pk=None,
        creado_en=None,
    ):
        legacy_id = pk or fila.pk
        total = total_piezas if total_piezas is not None else max(int(getattr(fila, "total_piezas", 1) or 1), 1)
        objetivo = max(int(getattr(fila, "cantidad_objetivo", total) or total), 1)
        estado_heredado = (getattr(fila, "estado", "") or "").strip().lower()
        estado = {
            "abierta": OrdenProduccion.Estado.ABIERTA,
            "cerrada": OrdenProduccion.Estado.CERRADA,
            "cancelada": OrdenProduccion.Estado.CANCELADA,
        }.get(estado_heredado, OrdenProduccion.Estado.ABIERTA)
        # Vigas no tiene estado general: el ciclo lo marca la etapa.
        if etiqueta == "Viga":
            estado = OrdenProduccion.Estado.ABIERTA

        orden, creada = OrdenProduccion.objects.using(BASE).update_or_create(
            legacy_modelo=etiqueta,
            legacy_id=legacy_id,
            defaults={
                "linea": linea,
                # Durante la convivencia se conserva el folio impreso. Los
                # folios nuevos salen de la secuencia, mil por encima.
                "folio": f"{linea.prefijo_folio}-{int(legacy_id):05d}",
                "codigo": (codigo if codigo is not None else getattr(fila, "codigo", "")) or "",
                "cliente": cliente,
                "obra": obra,
                "pieza": pieza,
                "nombre": (getattr(fila, "nombre", "") or "")[:180],
                "descripcion": (getattr(fila, "descripcion", "") or "")[:255],
                "observaciones": (getattr(fila, "observaciones", "") or "")[:255],
                "total_piezas": total,
                "cantidad_objetivo": objetivo,
                "peso_kg_unitario": peso_unitario,
                "fecha_compromiso": getattr(fila, "fecha_compromiso", None),
                "prioridad": int(getattr(fila, "prioridad", 3) or 3),
                "etapa_actual": etapa,
                "estado": estado,
                "cierre_pendiente_en": con_zona(getattr(fila, "cierre_pendiente_en", None)),
                "cierre_pendiente_hasta": con_zona(getattr(fila, "cierre_pendiente_hasta", None)),
                "cierre_pendiente_por": getattr(fila, "cierre_pendiente_por", "") or "",
                "cierre_bloqueado_en": con_zona(getattr(fila, "cierre_bloqueado_en", None)),
                "cierre_revertido_en": con_zona(getattr(fila, "cierre_revertido_en", None)),
                "cierre_revertido_por": getattr(fila, "cierre_revertido_por", "") or "",
                "ultimo_cambio": con_zona(getattr(fila, "ultimo_cambio", None)),
                # Si la fila heredada reaparece, la orden revive. Pasa cuando
                # se restaura un respaldo o cuando alguien vuelve a dar de
                # alta lo que había borrado por error.
                "retirada_en": None,
                "creado_en": con_zona(
                    creado_en or getattr(fila, "creado_en", None) or self.ahora
                ),
                "atributos": atributos,
            },
        )
        self._contar("ordenes", int(creada))

        if creada:
            self._heredar_del_lote(orden)
            self._evento(
                orden,
                f"{etiqueta}.alta",
                legacy_id,
                tipo=EventoProduccion.Tipo.CREACION,
                etapa=etapa,
                ocurrido_en=orden.creado_en,
                comentario="alta reconstruida desde el sistema heredado",
                sin_historico=True,
                metadata={"legacy_modelo": etiqueta, "legacy_id": legacy_id},
            )
        return orden

    def _evento_cambio_etapa(self, orden, cambio, etapas, etiqueta):
        """Un renglón de bitácora se convierte en un evento.

        El sistema heredado marca los cierres automáticos escribiendo
        `auto_bloqueo` en el comentario. Aquí eso pasa a ser un tipo de evento
        propio, que es lo que permite contarlos sin buscar una palabra dentro
        de un texto libre —exactamente el problema que hoy tiene el tablero
        con «retrabajo», que se mide de dos formas incompatibles en la misma
        pantalla.
        """
        automatico = (cambio.comentario or "").strip() == MARCA_CIERRE_AUTOMATICO
        motivo = None
        texto_motivo = (getattr(cambio, "motivo_retroceso", "") or "").strip()
        if texto_motivo:
            motivo = (
                MotivoEvento.objects.using(BASE)
                .filter(
                    ambito=MotivoEvento.Ambito.RETROCESO,
                    codigo=codigo_de(texto_motivo) or "correccion",
                )
                .first()
            )

        self._evento(
            orden,
            etiqueta,
            cambio.pk,
            tipo=(
                EventoProduccion.Tipo.CIERRE_FIRME
                if automatico
                else EventoProduccion.Tipo.CAMBIO_ETAPA
            ),
            etapa_anterior=etapas.get(clave(cambio.estado_anterior)),
            etapa=etapas.get(clave(cambio.estado_nuevo)),
            motivo=motivo,
            comentario=(cambio.comentario or "")[:255] or texto_motivo[:255],
            actor_username=cambio.actor_username or "",
            fecha_operacion=cambio.fecha_operacion,
            ocurrido_en=cambio.creado_en,
            metadata={"motivo_retroceso": texto_motivo} if texto_motivo else {},
        )

    def _eventos_avance(self, orden, avance, etiqueta):
        """Un renglón de avance son hasta tres eventos, uno por contador.

        La bitácora heredada guarda «antes» y «después» de los tres a la vez.
        Aquí se separan y se guarda **la diferencia**, que es lo que mata la
        duplicación de stock: dos pestañas mandando el mismo total producían
        el doble; dos incrementos de cinco producen diez.

        El identificador heredado se reutiliza con sufijo porque una fila da
        varios eventos y cada uno necesita su propia marca para que volver a
        correr el volcado no los duplique.
        """
        for contador, antes, despues in (
            (EventoProduccion.Contador.PRODUCIDA, avance.soldadas_prev, avance.soldadas_new),
            (EventoProduccion.Contador.PINTADA, avance.pintadas_prev, avance.pintadas_new),
            (EventoProduccion.Contador.TERMINADA, avance.terminadas_prev, avance.terminadas_new),
        ):
            delta = int(despues or 0) - int(antes or 0)
            if delta == 0:
                continue
            self._evento(
                orden,
                f"{etiqueta}:{contador}",
                avance.pk,
                tipo=EventoProduccion.Tipo.AVANCE,
                etapa=orden.etapa_actual,
                contador=contador,
                delta_cantidad=delta,
                cantidad_resultante=int(despues or 0),
                actor_username=avance.actor_username or "",
                fecha_operacion=avance.fecha_operacion,
                ocurrido_en=avance.creado_en,
            )

    def _cuadrar(self, orden, producida, pintada, terminada):
        """Deja los contadores del núcleo iguales a los heredados.

        Y, si el historial reconstruido no llega a esa cifra, emite el ajuste
        que falta **marcado como sin historial**. Esa marca es el punto: dice
        cuánto de lo que hay no se pudo reconstruir, en vez de esconderlo.
        """
        suma = {"producida": 0, "pintada": 0, "terminada": 0}
        for evento in EventoProduccion.objects.using(BASE).filter(
            orden=orden, tipo=EventoProduccion.Tipo.AVANCE
        ):
            if evento.contador:
                suma[evento.contador] += evento.delta_cantidad

        objetivo = {
            "producida": int(producida or 0),
            "pintada": int(pintada or 0),
            "terminada": int(terminada or 0),
        }
        motivo = (
            MotivoEvento.objects.using(BASE)
            .filter(ambito=MotivoEvento.Ambito.AJUSTE, codigo="sin_historico")
            .first()
        )

        for contador, esperado in objetivo.items():
            diferencia = esperado - suma[contador]
            if diferencia == 0:
                continue
            _, nuevo = self._evento(
                orden,
                f"{orden.legacy_modelo}:cuadre:{contador}",
                orden.legacy_id,
                tipo=EventoProduccion.Tipo.AJUSTE,
                etapa=orden.etapa_actual,
                contador=contador,
                delta_cantidad=diferencia,
                cantidad_resultante=esperado,
                motivo=motivo,
                ocurrido_en=orden.ultimo_cambio or orden.creado_en,
                comentario="cuadre de migración: el sistema heredado no guardó este movimiento",
                sin_historico=True,
            )
            self._contar("ajustes_sin_historico", int(nuevo))

        OrdenProduccion.objects.using(BASE).filter(pk=orden.pk).update(
            cantidad_producida=objetivo["producida"],
            cantidad_pintada=objetivo["pintada"],
            cantidad_terminada=objetivo["terminada"],
        )

    # ------------------------------------------------------- asignaciones

    def _volcar_asignaciones(
        self, linea, modelo, etiqueta, etiqueta_orden, etapas, con_rol=False
    ):
        """Las seis tablas de asignación pasan a una.

        `fraccion_peso` se deja en uno y se reparte después, cuando el módulo
        de costeo lo necesite: cambiarlo aquí alteraría en silencio las cifras
        del tablero durante la convivencia, y la reconciliación lo marcaría
        como divergencia sin serlo.
        """
        campo_orden = "viga_internal_id" if etiqueta_orden == "Viga" else "orden_id"
        indice = {
            o.legacy_id: o
            for o in OrdenProduccion.objects.using(BASE).filter(legacy_modelo=etiqueta_orden)
        }
        creadas = 0

        for fila in modelo.objects.using(BASE).all().iterator(chunk_size=self.lote):
            orden = indice.get(getattr(fila, campo_orden, None))
            if orden is None:
                continue
            etapa_texto = getattr(fila, "etapa", "") or ""
            _, nueva = Asignacion.objects.using(BASE).update_or_create(
                legacy_modelo=etiqueta,
                legacy_id=fila.pk,
                defaults={
                    "orden": orden,
                    "etapa": etapas.get(clave(etapa_texto)),
                    "rol": (getattr(fila, "rol", "") or "") if con_rol else "",
                    "colaborador": getattr(fila, "colaborador", None),
                    "maquina": getattr(fila, "maquina", None),
                    "vigente": bool(getattr(fila, "vigente", True)),
                    "asignado_por": getattr(fila, "asignado_por", "") or "",
                    "asignado_en": con_zona(getattr(fila, "asignado_en", None)) or self.ahora,
                },
            )
            creadas += int(nueva)

        if creadas:
            self._contar("asignaciones", creadas)

    # ------------------------------------------------------------ informe

    def _resumen(self):
        self.stdout.write(self.style.MIGRATE_HEADING("\nResumen"))
        if not self.contadas:
            self.stdout.write("  nada que volcar")
            return
        for etiqueta in sorted(self.contadas):
            self.stdout.write(f"  {etiqueta:24} {self.contadas[etiqueta]:>7}")
        sin_historico = self.contadas.get("ajustes_sin_historico", 0)
        if sin_historico:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  {sin_historico} movimiento(s) no se pudieron reconstruir y quedan\n"
                    "  como ajuste declarado. No es un error: es lo que el sistema\n"
                    "  heredado no guardó. `verificar_backfill` los detalla."
                )
            )
        if self.simular:
            self.stdout.write(self.style.WARNING("\n  Simulación: nada de esto se guardó."))
