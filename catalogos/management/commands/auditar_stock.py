"""Comprueba que el stock guardado cuadre con la suma de sus movimientos.

`LogisticaStock.stock` y `LogisticaStockCorta.stock` son contadores que se
actualizan a mano en cada operación, en paralelo a la fila que se inserta en
la tabla de movimientos. Nada garantiza que las dos cosas coincidan, y hay al
menos dos motivos conocidos para que se separen:

- El avance de producción manda la cantidad **absoluta** de piezas terminadas
  y el servidor calcula la diferencia contra el valor anterior. Dos pestañas
  abiertas a la vez sobre la misma orden producen dos veces el mismo
  incremento.
- Revertir un cierre no deshace el `stock_in` que ese cierre generó.

Este informe es la línea base contra la que se medirá si la reforma del
almacén arregla el problema. Conviene guardarlo antes de tocar nada.

    python manage.py auditar_stock

Sólo lee. No corrige nada: un descuadre puede venir de una operación real mal
registrada, y decidir cuál es el valor bueno no es cosa de un script.
"""
from django.core.management.base import BaseCommand
from django.db.models import Sum
from core.bases import BASE  # noqa: F401

# El material pasa por tres estados: disponible, apartado y enviado. Los
# movimientos registran los saltos entre ellos, así que no todos afectan al
# stock disponible:
#
#   stock_in             +n   producción entrega   -> aumenta el disponible
#   apartar              -n   se reserva           -> baja el disponible
#   revertir_a_stock     +n   vuelve al almacén    -> aumenta el disponible
#   ajuste               ±n   corrección manual    -> afecta al disponible
#   enviar               -n   sale del apartado    -> NO toca el disponible
#   revertir_a_apartado  +n   vuelve a la reserva  -> NO toca el disponible
#
# Sumar `enviar` descuenta dos veces la misma pieza: es el error que tenía la
# primera versión de este informe y producía un descuadre inventado.
TIPOS_QUE_MUEVEN_EL_DISPONIBLE = ["stock_in", "apartar", "revertir_a_stock", "ajuste"]

# `revertir` es el tipo histórico que no distinguía destino. Los registros que
# lo llevan no se pueden clasificar, así que cualquier stock calculado sobre un
# periodo que los contenga es aproximado. Se avisa en lugar de adivinar.
TIPO_AMBIGUO_HISTORICO = "revertir"

from catalogos.models import (
    LogisticaMovimiento,
    LogisticaMovimientoCorta,
    LogisticaStock,
    LogisticaStockCorta,
    PedidoProduccionItem,
)


class Command(BaseCommand):
    help = "Compara los contadores de stock con la suma de los movimientos registrados."

    def handle(self, *args, **opciones):
        descuadres = 0

        # ---------------------------------------------------------- herrería
        self.stdout.write(self.style.MIGRATE_HEADING("\nAlmacén de herrería"))
        movimientos = dict(
            LogisticaMovimiento.objects.using(BASE)
            .filter(tipo__in=TIPOS_QUE_MUEVEN_EL_DISPONIBLE)
            .values_list("producto_id")
            .annotate(total=Sum("cantidad"))
            .values_list("producto_id", "total")
        )
        filas = LogisticaStock.objects.using(BASE).select_related("producto")
        if not filas:
            self.stdout.write("  (sin registros)")
        for fila in filas:
            guardado = int(fila.stock or 0)
            calculado = int(movimientos.get(fila.producto_id, 0) or 0)
            if guardado == calculado:
                self.stdout.write(f"    {str(fila.producto)[:38]:38} {guardado:6}   correcto")
            else:
                descuadres += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"    {str(fila.producto)[:38]:38} guardado={guardado} "
                        f"movimientos={calculado}  diferencia={guardado - calculado}"
                    )
                )

        # -------------------------------------------------------------- corta
        self.stdout.write(self.style.MIGRATE_HEADING("\nAlmacén de Corta"))
        movimientos_corta = dict(
            LogisticaMovimientoCorta.objects.using(BASE)
            .filter(tipo__in=TIPOS_QUE_MUEVEN_EL_DISPONIBLE)
            .values_list("producto")
            .annotate(total=Sum("cantidad"))
            .values_list("producto", "total")
        )
        filas_corta = LogisticaStockCorta.objects.using(BASE)
        if not filas_corta:
            self.stdout.write("  (sin registros)")
        for fila in filas_corta:
            guardado = int(fila.stock or 0)
            calculado = int(movimientos_corta.get(fila.producto, 0) or 0)
            if guardado == calculado:
                self.stdout.write(f"    {str(fila.producto)[:38]:38} {guardado:6}   correcto")
            else:
                descuadres += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"    {str(fila.producto)[:38]:38} guardado={guardado} "
                        f"movimientos={calculado}  diferencia={guardado - calculado}"
                    )
                )

        # ------------------------------------------- coherencia de los pedidos
        #
        # La invariante es apartado + enviado <= cantidad_total. Si se rompe,
        # se ha comprometido más material del que se pidió.
        self.stdout.write(self.style.MIGRATE_HEADING("\nCoherencia de las líneas de pedido"))
        incoherentes = []
        for item in PedidoProduccionItem.objects.using(BASE).select_related("pedido", "producto"):
            total = int(item.cantidad_total or 0)
            apartado = int(item.apartado or 0)
            enviado = int(item.enviado or 0)
            if apartado < 0 or enviado < 0 or apartado + enviado > total:
                incoherentes.append(
                    f"{item.pedido.folio} línea {item.id}: total={total} "
                    f"apartado={apartado} enviado={enviado}"
                )
        if incoherentes:
            descuadres += len(incoherentes)
            for linea in incoherentes:
                self.stdout.write(self.style.WARNING(f"    {linea}"))
        else:
            self.stdout.write("    todas correctas")

        # ------------------------------------ movimientos históricos ambiguos
        self.stdout.write(self.style.MIGRATE_HEADING("\nMovimientos de tipo ambiguo"))
        n_amb = LogisticaMovimiento.objects.using(BASE).filter(tipo=TIPO_AMBIGUO_HISTORICO).count()
        n_amb_corta = (
            LogisticaMovimientoCorta.objects.using(BASE)
            .filter(tipo=TIPO_AMBIGUO_HISTORICO)
            .count()
        )
        if n_amb or n_amb_corta:
            self.stdout.write(
                self.style.WARNING(
                    f"    herrería: {n_amb}   corta: {n_amb_corta}\n"
                    "    Se escribieron antes de distinguir el destino de la reversión, así que\n"
                    "    no se sabe si devolvieron el material al almacén o al apartado. Los\n"
                    "    descuadres de arriba pueden explicarse por completo con esto."
                )
            )
        else:
            self.stdout.write("    ninguno")

        # ------------------------------------------------------------ resumen
        self.stdout.write(self.style.MIGRATE_HEADING("\nResumen"))
        if descuadres:
            self.stdout.write(
                self.style.ERROR(
                    f"  {descuadres} descuadre(s). Guardar este informe: es la referencia "
                    "contra la que se medirá la reforma del almacén."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("  Sin descuadres."))
