"""Vacía la información del sistema conservando la estructura.

Borra **filas**, no tablas. Al terminar, la base tiene exactamente los mismos
esquemas, índices y restricciones que antes, sin un solo dato de operación.

Está pensado para dejar el sistema listo para llenarlo con datos simulados y
poder enseñarlo o practicar con él. **No es una herramienta de operación** y
no debería existir en el servidor del taller sin candado, así que:

- Pide confirmación escribiendo el nombre de la base. Sin `--si-estoy-seguro`
  no borra nada.
- Se niega a correr con `DEBUG = False`, que es como corre en producción.
  Saltarse eso exige `--aunque-sea-produccion`, que hay que escribir a
  propósito.
- Antes de tocar nada avisa de cuántas filas se va a llevar por delante.

Lo que **no** borra, salvo que se pida:

- **Los usuarios y sus permisos.** Vaciarlos dejaría el sistema sin nadie que
  pueda entrar. Con `--tambien-usuarios` se borran todos menos el
  administrador fijo, que es la entrada de respaldo.
- **Los catálogos de configuración de planta** —proyectos, equipos, máquinas,
  colaboradores— con `--conservar-planta`, por si se quiere volver a llenar
  la operación sin recapturar el taller.

El orden de borrado importa: primero lo que apunta a otras cosas y al final
lo apuntado, porque casi todas las llaves foráneas son `PROTECT` y borrar al
revés falla a la mitad, dejando la base medio vacía.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

BASE = "mes"

#: De lo más dependiente a lo menos. Cada grupo se borra entero antes de pasar
#: al siguiente.
#:
#: Se escriben como (app, Modelo) y se resuelven en tiempo de ejecución para
#: que el comando no cargue medio proyecto al importarse.
OPERACION = [
    # --- costeo, que cuelga de todo lo demás
    ("costeo", "CostoEtapa"),
    ("costeo", "CostoOrden"),
    ("costeo", "TiempoEstandar"),
    ("costeo", "Tarifa"),
    ("costeo", "TarifaManoObra"),

    # --- inventario
    ("inventario", "SeguimientoCompra"),
    ("inventario", "RenglonOrdenCompra"),
    ("inventario", "OrdenCompra"),
    ("inventario", "RenglonListaMateriales"),
    ("inventario", "ListaMateriales"),
    ("inventario", "MovimientoMaterial"),
    ("inventario", "Existencia"),
    ("inventario", "LoteMaterial"),

    # --- núcleo unificado
    ("nucleo", "DivergenciaReconciliacion"),
    ("nucleo", "EventoMaquina"),
    ("nucleo", "Asignacion"),
    ("nucleo", "EventoProduccion"),
    ("nucleo", "OrdenProduccion"),
    ("nucleo", "Obra"),

    # --- logística
    ("catalogos", "LogisticaExpedienteDescarga"),
    ("catalogos", "LogisticaExpediente"),
    ("catalogos", "LogisticaAcuseEntrega"),
    ("catalogos", "LogisticaEnvioItem"),
    ("catalogos", "LogisticaEnvio"),
    ("catalogos", "LogisticaEnvioCorta"),
    ("catalogos", "LogisticaMovimiento"),
    ("catalogos", "LogisticaMovimientoCorta"),
    ("catalogos", "LogisticaStock"),
    ("catalogos", "LogisticaStockCorta"),

    # --- pedidos
    ("catalogos", "PedidoProduccionItem"),
    ("catalogos", "PedidoProduccion"),

    # --- las cuatro líneas de producción
    ("catalogos", "HerrProduccion"),
    ("catalogos", "HerrOrdenAsignacion"),
    ("catalogos", "HerrOrdenItem"),
    ("catalogos", "HerrAvanceCambio"),
    ("catalogos", "HerrEstadoCambio"),
    ("catalogos", "HerrAsignacion"),
    ("catalogos", "HerrSolicitudProduccion"),
    ("catalogos", "HerrOrdenProduccion"),

    ("catalogos", "LaserProduccion"),
    ("catalogos", "LaserOrdenAsignacion"),
    ("catalogos", "LaserOrdenItem"),
    ("catalogos", "LaserEstadoCambio"),
    ("catalogos", "LaserAsignacion"),
    ("catalogos", "LaserOrdenProduccion"),

    ("catalogos", "RobotProduccion"),
    ("catalogos", "RobotOrdenAsignacion"),
    ("catalogos", "RobotOrdenItem"),
    ("catalogos", "RobotOrdenProduccion"),

    ("catalogos", "VigaAsignacion"),
    ("catalogos", "VigaPlano"),
    ("produccion", "ProductionLog"),
    ("produccion", "Viga"),

    # --- planta: paros, fallas y cuadrillas
    #
    # El apunte de trabajo va antes que la cuadrilla y que la máquina:
    # apunta a las dos, y a la máquina con PROTECT.
    ("catalogos", "ApunteDeTrabajo"),
    ("catalogos", "CuadrillaIntegrante"),
    ("catalogos", "Cuadrilla"),
    ("catalogos", "MaquinaFalla"),
    ("catalogos", "MaquinaParo"),
    ("catalogos", "PlantaEvento"),
    ("catalogos", "WeeklyReportSnapshot"),
]

#: La configuración del taller: quién trabaja, con qué y para quién. Se borra
#: al final y sólo si no se pidió conservarla.
PLANTA = [
    # Va primero porque apunta a `LineaNegocio` con PROTECT: al revés, el
    # borrado revienta a la mitad. La transacción lo revierte, pero el error
    # sale a los treinta segundos y no dice nada útil.
    ("costeo", "CentroCosto"),

    ("catalogos", "Colaborador"),
    ("catalogos", "EquipoTrabajo"),
    ("catalogos", "Maquina"),
    ("catalogos", "MaquinaParoMotivo"),
    ("catalogos", "MaquinaFallaTipo"),
    ("catalogos", "HerrPiezaCatalogo"),
    ("catalogos", "CortaPiezaCatalogo"),
    ("catalogos", "RobotPiezaCatalogo"),
    ("catalogos", "HerrCliente"),
    ("catalogos", "CortaClienteProyecto"),
    ("catalogos", "LaserMaterialPlaca"),
    ("catalogos", "Proyecto"),
    ("inventario", "Material"),
    ("inventario", "Proveedor"),
    ("inventario", "Almacen"),
    ("nucleo", "Cliente"),
    ("nucleo", "PiezaCatalogo"),
    ("nucleo", "TransicionPermitida"),
    ("nucleo", "EtapaAlias"),
    ("nucleo", "Etapa"),
    ("nucleo", "MotivoEvento"),
    ("nucleo", "LineaNegocio"),
]


def modelo(app, nombre):
    from django.apps import apps

    return apps.get_model(app, nombre)


class Command(BaseCommand):
    help = "Vacía la información conservando la estructura de la base."

    def add_arguments(self, parser):
        parser.add_argument(
            "--si-estoy-seguro",
            dest="confirmacion",
            default="",
            help="El nombre de la base, para confirmar. Sin esto no borra nada.",
        )
        parser.add_argument(
            "--conservar-planta",
            action="store_true",
            help="No toca proyectos, equipos, máquinas, colaboradores ni catálogos.",
        )
        parser.add_argument(
            "--tambien-usuarios",
            action="store_true",
            help="Borra las cuentas, menos el administrador fijo.",
        )
        parser.add_argument(
            "--aunque-sea-produccion",
            action="store_true",
            help="Permite correrlo con DEBUG=False. Que nadie lo escriba sin querer.",
        )

    def handle(self, *args, **opciones):
        from django.conf import settings

        nombre_base = connections[BASE].settings_dict["NAME"]

        if not settings.DEBUG and not opciones["aunque_sea_produccion"]:
            raise CommandError(
                "DEBUG está en False, o sea que esto parece un servidor de "
                "verdad. Si aun así quieres vaciarlo, añade "
                "--aunque-sea-produccion."
            )

        grupos = list(OPERACION)
        if not opciones["conservar_planta"]:
            grupos += PLANTA

        conteos = self._contar(grupos)
        total = sum(conteos.values())

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"\nSe va a vaciar «{nombre_base}»"
        ))
        for etiqueta, cuantas in sorted(conteos.items(), key=lambda p: -p[1]):
            if cuantas:
                self.stdout.write(f"  {cuantas:>8,}  {etiqueta}")
        self.stdout.write(self.style.WARNING(f"\n  {total:,} filas en total"))
        if opciones["conservar_planta"]:
            self.stdout.write("  Se conservan proyectos, equipos, máquinas y catálogos.")

        if opciones["confirmacion"] != nombre_base:
            raise CommandError(
                f"\nNo se borró nada. Para hacerlo de verdad:\n"
                f"  manage.py limpiar_datos --si-estoy-seguro {nombre_base}\n"
            )

        borradas = self._borrar(grupos)
        if opciones["tambien_usuarios"]:
            borradas += self._borrar_usuarios()

        self.stdout.write(self.style.SUCCESS(
            f"\nListo: {borradas:,} filas borradas. La estructura queda igual.\n"
        ))

    # ------------------------------------------------------------ interior

    def _contar(self, grupos):
        conteos = {}
        for app, nombre in grupos:
            try:
                Modelo = modelo(app, nombre)
            except LookupError:
                continue
            conteos[f"{app}.{nombre}"] = Modelo.objects.using(BASE).count()
        return conteos

    def _borrar(self, grupos):
        total = 0
        with transaction.atomic(using=BASE):
            for app, nombre in grupos:
                try:
                    Modelo = modelo(app, nombre)
                except LookupError:
                    continue
                # `_raw_delete` evitaría las señales, pero también las llaves
                # foráneas en cascada. Se usa el borrado normal: es más lento
                # y es el que respeta las reglas de la base.
                cuantas, _ = Modelo.objects.using(BASE).all().delete()
                if cuantas:
                    self.stdout.write(f"  borradas {cuantas:>8,}  {app}.{nombre}")
                total += cuantas
        return total

    def _borrar_usuarios(self):
        """Todas las cuentas menos el administrador fijo.

        Dejar al menos una es lo que impide quedarse fuera del sistema que
        acabas de vaciar.
        """
        from django.contrib.auth import get_user_model

        from catalogos.management.commands.crear_admin import USUARIO as ADMIN

        Usuario = get_user_model()
        cuantas, _ = Usuario.objects.exclude(username=ADMIN).delete()
        self.stdout.write(f"  borradas {cuantas:>8,}  cuentas (se conserva «{ADMIN}»)")
        return cuantas
