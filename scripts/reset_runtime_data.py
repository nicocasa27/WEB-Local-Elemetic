import os
import sys
from pathlib import Path

import django
from django.db import connections, transaction

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mes_vigas_web.settings")
django.setup()

from catalogos.models import (
    HerrAsignacion,
    HerrAvanceCambio,
    HerrEstadoCambio,
    HerrOrdenAsignacion,
    HerrOrdenItem,
    HerrOrdenProduccion,
    HerrProduccion,
    HerrSolicitudProduccion,
    LaserAsignacion,
    LaserEstadoCambio,
    LaserOrdenAsignacion,
    LaserOrdenItem,
    LaserOrdenProduccion,
    LaserProduccion,
    LogisticaAcuseEntrega,
    LogisticaEnvio,
    LogisticaEnvioCorta,
    LogisticaExpediente,
    LogisticaExpedienteDescarga,
    LogisticaMovimiento,
    LogisticaMovimientoCorta,
    LogisticaStock,
    LogisticaStockCorta,
    PedidoProduccion,
    VigaAsignacion,
    VigaPlano,
    WeeklyReportSnapshot,
)

USING = "mes"


def table_count(table_name: str) -> int:
    with connections[USING].cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return int(cur.fetchone()[0])


def c(model, **filters) -> int:
    return model.objects.using(USING).filter(**filters).count()


def show_counts(label: str) -> None:
    print("---", label)
    try:
        print("vigas", table_count("vigas"))
    except Exception as e:
        print("vigas ERR", e)
    try:
        print("production_log", table_count("production_log"))
    except Exception as e:
        print("production_log ERR", e)
    print("VigaPlano", c(VigaPlano))
    print("VigaAsignacion", c(VigaAsignacion))
    print("WeeklyReportSnapshot", c(WeeklyReportSnapshot))
    print("HERR HerrOrdenProduccion", c(HerrOrdenProduccion))
    print("HERR HerrOrdenItem", c(HerrOrdenItem))
    print("HERR HerrProduccion", c(HerrProduccion))
    print("HERR HerrEstadoCambio", c(HerrEstadoCambio))
    print("HERR HerrAvanceCambio", c(HerrAvanceCambio))
    print("HERR HerrAsignacion", c(HerrAsignacion))
    print("HERR HerrOrdenAsignacion", c(HerrOrdenAsignacion))
    print("HERR HerrSolicitudProduccion", c(HerrSolicitudProduccion))
    print("CORTA LaserOrdenProduccion", c(LaserOrdenProduccion))
    print("CORTA LaserOrdenItem", c(LaserOrdenItem))
    print("CORTA LaserProduccion", c(LaserProduccion))
    print("CORTA LaserEstadoCambio", c(LaserEstadoCambio))
    print("CORTA LaserAsignacion", c(LaserAsignacion))
    print("CORTA LaserOrdenAsignacion", c(LaserOrdenAsignacion))
    print("VENTAS PedidoProduccion", c(PedidoProduccion))
    print("LOG OP LogisticaEnvio", c(LogisticaEnvio))
    print("LOG OP LogisticaAcuseEntrega", c(LogisticaAcuseEntrega))
    print("LOG OP LogisticaMovimiento", c(LogisticaMovimiento))
    print("LOG OP LogisticaExpediente(pedido)", c(LogisticaExpediente, pedido__isnull=False))
    print(
        "LOG OP LogisticaExpedienteDescarga(pedido)",
        c(LogisticaExpedienteDescarga, pedido__isnull=False),
    )
    print("LOG OP LogisticaStock", c(LogisticaStock))
    print("LOG Corta LogisticaEnvioCorta", c(LogisticaEnvioCorta))
    print("LOG Corta LogisticaMovimientoCorta", c(LogisticaMovimientoCorta))
    print("LOG Corta LogisticaExpediente(corta)", c(LogisticaExpediente, orden_corta__isnull=False))
    print(
        "LOG Corta LogisticaExpedienteDescarga(corta)",
        c(LogisticaExpedienteDescarga, orden_corta__isnull=False),
    )
    print("LOG Corta LogisticaStockCorta", c(LogisticaStockCorta))


print("DB_VENDOR", connections[USING].vendor)
show_counts("ANTES")

with transaction.atomic(using=USING):
    with connections[USING].cursor() as cur:
        cur.execute("TRUNCATE TABLE production_log, vigas CASCADE")

    VigaPlano.objects.using(USING).all().delete()
    VigaAsignacion.objects.using(USING).all().delete()
    WeeklyReportSnapshot.objects.using(USING).all().delete()

    LogisticaEnvio.objects.using(USING).all().delete()
    LogisticaExpedienteDescarga.objects.using(USING).filter(pedido__isnull=False).delete()
    LogisticaExpediente.objects.using(USING).filter(pedido__isnull=False).delete()
    LogisticaAcuseEntrega.objects.using(USING).all().delete()
    LogisticaMovimiento.objects.using(USING).all().delete()
    PedidoProduccion.objects.using(USING).all().delete()

    HerrProduccion.objects.using(USING).all().delete()
    HerrAsignacion.objects.using(USING).all().delete()
    HerrOrdenAsignacion.objects.using(USING).all().delete()
    HerrEstadoCambio.objects.using(USING).all().delete()
    HerrAvanceCambio.objects.using(USING).all().delete()
    HerrSolicitudProduccion.objects.using(USING).all().delete()
    HerrOrdenItem.objects.using(USING).all().delete()
    HerrOrdenProduccion.objects.using(USING).all().delete()

    LogisticaEnvioCorta.objects.using(USING).all().delete()
    LogisticaMovimientoCorta.objects.using(USING).all().delete()
    LogisticaExpedienteDescarga.objects.using(USING).filter(orden_corta__isnull=False).delete()
    LogisticaExpediente.objects.using(USING).filter(orden_corta__isnull=False).delete()
    LaserProduccion.objects.using(USING).all().delete()
    LaserAsignacion.objects.using(USING).all().delete()
    LaserOrdenAsignacion.objects.using(USING).all().delete()
    LaserEstadoCambio.objects.using(USING).all().delete()
    LaserOrdenItem.objects.using(USING).all().delete()
    LaserOrdenProduccion.objects.using(USING).all().delete()

    LogisticaStock.objects.using(USING).all().delete()
    LogisticaStockCorta.objects.using(USING).all().delete()

show_counts("DESPUÉS")
print("RESET_OK")
