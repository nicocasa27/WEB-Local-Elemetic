"""Lleva a la base la regla de que los contadores no pueden ser imposibles.

La invariante es «terminadas ≤ pintadas ≤ producidas ≤ objetivo». Hoy no la
comprueba nadie: ni el navegador, ni el servidor, ni la base. Por eso se puede
guardar «soldadas 0, pintadas 0, terminadas 50», y esas cincuenta piezas
salen en los informes sin haber pasado por ninguna etapa.

El servicio del núcleo ya no deja crear más. Esto es el último cinturón: la
regla en la base, donde no la puede saltar ningún camino de código, ni un
`update` en bloque, ni una consulta escrita a mano.

**Se añade en dos tiempos, y ese es el punto del comando.** PostgreSQL permite
crear una restricción `NOT VALID`: se aplica a todo lo que se escriba a partir
de ese momento, pero no rechaza las filas que ya estaban. Ponerla en modo
estricto de golpe rompería el sistema con los datos actuales, porque hay
órdenes que vienen así desde hace años.

**Cuidado con un matiz de `NOT VALID` que no es evidente y que se descubrió
probándolo:** tolera que las filas malas *existan*, pero no que se
*modifiquen*. Cualquier actualización de una de esas órdenes —incluido el
reflejo de la escritura doble— se rechaza, y la orden queda congelada. En
la copia del taller eso dejó a L-00014 sin poder actualizarse, y el reflejo
se lo tragó en silencio porque está pensado para no interrumpir al operador.

Por eso el orden correcto es **corregir primero y endurecer después**, y por
eso `--aplicar` se niega si quedan órdenes que la incumplan.

    python manage.py endurecer_invariantes            # informa, no toca nada
    python manage.py endurecer_invariantes --aplicar  # exige que no queden malas
    python manage.py endurecer_invariantes --validar  # la deja definitiva
    python manage.py endurecer_invariantes --quitar   # la retira, si hiciera falta

Entre medias hay trabajo humano: corregir las órdenes que venían mal, con un
evento de ajuste y su motivo, no con un `UPDATE`. `verificar_backfill` las
lista.
"""

from django.core.management.base import BaseCommand
from django.db import connections

from nucleo.models import OrdenProduccion
from core.bases import BASE  # noqa: F401

RESTRICCION = "orden_contadores_en_cascada"

CONDICION = """
    cantidad_terminada <= cantidad_pintada
    AND cantidad_pintada <= cantidad_producida
    AND cantidad_producida <= cantidad_objetivo
"""


class Command(BaseCommand):
    help = "Añade en la base la invariante de contadores, en dos tiempos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar",
            action="store_true",
            help="Crea la restricción como NOT VALID: vale para lo nuevo, tolera lo viejo.",
        )
        parser.add_argument(
            "--validar",
            action="store_true",
            help="Exige que ya no quede ninguna fila incumpliéndola. Falla si queda alguna.",
        )
        parser.add_argument(
            "--quitar",
            action="store_true",
            help="Retira la restricción. La vuelta atrás, si algo se atasca.",
        )
        parser.add_argument(
            "--igualmente",
            action="store_true",
            help=(
                "Aplica aunque queden órdenes incumpliéndola. Esas órdenes quedarán "
                "congeladas: no se podrán actualizar hasta corregirlas."
            ),
        )

    def handle(self, *args, **opciones):
        incumplen = [
            orden for orden in OrdenProduccion.objects.using(BASE).all()
            if not orden.contadores_coherentes
        ]
        estado = self._estado_actual()

        self.stdout.write(self.style.MIGRATE_HEADING("Situación"))
        self.stdout.write(f"  restricción en la base: {estado}")
        self.stdout.write(f"  órdenes que la incumplen: {len(incumplen)}")
        for orden in incumplen[:20]:
            self.stdout.write(
                f"      {orden.folio}: objetivo {orden.cantidad_objetivo}, "
                f"producidas {orden.cantidad_producida}, "
                f"pintadas {orden.cantidad_pintada}, "
                f"terminadas {orden.cantidad_terminada}"
            )
        if len(incumplen) > 20:
            self.stdout.write(f"      … y {len(incumplen) - 20} más")

        if opciones["quitar"]:
            self._quitar(estado)
        elif opciones["aplicar"]:
            self._aplicar(estado, incumplen, opciones["igualmente"])
        elif opciones["validar"]:
            self._validar(estado, incumplen)
        else:
            self.stdout.write(
                "\n  No se ha tocado nada. El orden es: corregir las órdenes de arriba\n"
                "  con un evento de ajuste y su motivo, luego --aplicar, luego --validar."
            )

    def _estado_actual(self):
        with connections[BASE].cursor() as cursor:
            cursor.execute(
                "SELECT convalidated FROM pg_constraint WHERE conname = %s", [RESTRICCION]
            )
            fila = cursor.fetchone()
        if fila is None:
            return "no existe"
        return "validada" if fila[0] else "creada sin validar (NOT VALID)"

    def _quitar(self, estado):
        if estado == "no existe":
            self.stdout.write("\n  No existe: no hay nada que quitar.")
            return
        with connections[BASE].cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE nucleo_ordenproduccion DROP CONSTRAINT {RESTRICCION}"
            )
        self.stdout.write(self.style.SUCCESS("\n  Retirada."))

    def _aplicar(self, estado, incumplen, igualmente):
        if estado != "no existe":
            self.stdout.write(self.style.WARNING("\n  Ya existía: no se hace nada."))
            return

        if incumplen and not igualmente:
            self.stdout.write(
                self.style.ERROR(
                    f"\n  No se aplica: quedan {len(incumplen)} orden(es) que la incumplen.\n"
                    "\n"
                    "  `NOT VALID` tolera que esas filas existan, pero **no que se\n"
                    "  modifiquen**: cualquier actualización suya sería rechazada y la\n"
                    "  orden quedaría congelada. Durante la escritura doble eso además\n"
                    "  pasa desapercibido, porque el reflejo está pensado para no\n"
                    "  interrumpir al operador y se limita a anotar el fallo.\n"
                    "\n"
                    "  Corregirlas primero con `core.servicios.produccion.ajustar`, que\n"
                    "  deja el arreglo en el historial con su motivo.\n"
                    "  Si aun así se quiere aplicar ahora: --aplicar --igualmente."
                )
            )
            raise SystemExit(1)

        with connections[BASE].cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE nucleo_ordenproduccion "
                f"ADD CONSTRAINT {RESTRICCION} CHECK ({CONDICION}) NOT VALID"
            )
        self.stdout.write(
            self.style.SUCCESS(
                "\n  Creada como NOT VALID. A partir de ahora la base rechaza cualquier\n"
                "  escritura que deje los contadores en un estado imposible, venga por\n"
                "  donde venga. Las filas que ya estaban no se han tocado."
            )
        )

    def _validar(self, estado, incumplen):
        if estado == "no existe":
            self.stdout.write(
                self.style.ERROR("\n  No existe todavía. Ejecutar antes con --aplicar.")
            )
            raise SystemExit(1)
        if incumplen:
            self.stdout.write(
                self.style.ERROR(
                    f"\n  Quedan {len(incumplen)} orden(es) incumpliéndola. Corregirlas con\n"
                    "  un evento de ajuste (`core.servicios.produccion.ajustar`) y volver.\n"
                    "  No se validan a base de UPDATE: la corrección tiene que quedar en\n"
                    "  el historial con su motivo, como cualquier otro movimiento."
                )
            )
            raise SystemExit(1)

        with connections[BASE].cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE nucleo_ordenproduccion VALIDATE CONSTRAINT {RESTRICCION}"
            )
        self.stdout.write(
            self.style.SUCCESS("\n  Validada: ninguna fila puede incumplirla, ni vieja ni nueva.")
        )
