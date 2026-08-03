import os
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mes_vigas_web.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from catalogos.models import (
    CortaClienteProyecto,
    LaserOrdenProduccion,
    LogisticaEnvioCorta,
    LogisticaExpediente,
    LogisticaExpedienteDescarga,
    LogisticaMovimientoCorta,
    LogisticaStockCorta,
)


def _now_tag() -> str:
    return timezone.localtime(timezone.now()).strftime("%Y%m%d-%H%M%S")


def _ensure_admin_user() -> object:
    User = get_user_model()
    user = User.objects.filter(username="sim_admin").first()
    if user:
        if not user.is_superuser:
            user.is_superuser = True
            user.is_staff = True
            user.set_password("sim_admin")
            user.save(update_fields=["is_superuser", "is_staff", "password"])
        return user
    user = User.objects.create_user(
        username="sim_admin",
        password="sim_admin",
        is_superuser=True,
        is_staff=True,
        email="sim_admin@example.com",
    )
    return user


def _pick_pdf_bytes(base_dir: Path) -> bytes:
    cand = base_dir / "media" / "logistica" / "envios_corta" / "2026" / "05" / "08" / "Envio_Corta_Test.pdf"
    if cand.exists():
        return cand.read_bytes()
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >>\nendobj\n4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 10 100 Td (SIM CORTA) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000116 00000 n \n0000000200 00000 n \ntrailer\n<< /Root 1 0 R /Size 5 >>\nstartxref\n290\n%%EOF\n"
    )


def _cleanup_previous_simulations(tag_prefix: str):
    qs = LaserOrdenProduccion.objects.using("mes").filter(folio_externo_normalizado__startswith=tag_prefix.upper())
    ids = list(qs.values_list("id", flat=True)[:200])
    if not ids:
        return 0
    LogisticaMovimientoCorta.objects.using("mes").filter(orden_id__in=ids).delete()
    for e in LogisticaEnvioCorta.objects.using("mes").filter(orden_id__in=ids):
        try:
            if getattr(e, "comprobante_pdf", None):
                e.comprobante_pdf.delete(save=False)
        except Exception:
            pass
    LogisticaEnvioCorta.objects.using("mes").filter(orden_id__in=ids).delete()
    LogisticaExpedienteDescarga.objects.using("mes").filter(orden_corta_id__in=ids).delete()
    LogisticaExpediente.objects.using("mes").filter(orden_corta_id__in=ids).delete()
    deleted, _ = LaserOrdenProduccion.objects.using("mes").filter(id__in=ids).delete()
    return int(deleted or 0)


def main():
    base_dir = BASE_DIR
    user = _ensure_admin_user()
    tag_prefix = "SIM-CORTA-"
    cleaned = _cleanup_previous_simulations(tag_prefix=tag_prefix)

    tag = _now_tag()
    folio_externo = f"{tag_prefix}{tag}"

    cliente, _ = CortaClienteProyecto.objects.using("mes").get_or_create(
        nombre_normalizado="SIM CORTA",
        defaults={"nombre": "SIM CORTA", "tipo": "mixto", "activo": True},
    )

    producto = f"Pieza simulada corta ({tag})"
    orden = LaserOrdenProduccion.objects.using("mes").create(
        corta_cliente_proyecto=cliente,
        folio_externo=folio_externo,
        codigo=f"SIM-{tag}",
        descripcion=producto,
        total_piezas=5,
        cantidad_objetivo=5,
        estado="Abierta",
        estado_etapa="Espera de corte",
        prioridad=3,
    )

    stock = LogisticaStockCorta.objects.using("mes").filter(producto_normalizado=producto.upper()).first()
    if not stock:
        stock = LogisticaStockCorta.objects.using("mes").create(producto=producto, stock=0)
    stock.stock = 10
    stock.save(update_fields=["stock", "actualizado_en"])

    client = Client(HTTP_HOST="localhost")
    client.force_login(user)

    r1 = client.post("/catalogos/pedidos/logistica/corta/", {"action": "apartar", "orden_id": int(orden.id), "cantidad": 5})
    r1_status = int(getattr(r1, "status_code", 0) or 0)

    pdf_bytes = _pick_pdf_bytes(base_dir)
    upload = SimpleUploadedFile("Envio_Corta_SIM.pdf", pdf_bytes, content_type="application/pdf")
    r2 = client.post(
        "/catalogos/pedidos/logistica/corta/",
        {"action": "enviar", "orden_id": int(orden.id), "cantidad": 3, "comprobante_pdf": upload},
    )
    r2_status = int(getattr(r2, "status_code", 0) or 0)

    upload2 = SimpleUploadedFile("Envio_Corta_SIM_2.pdf", pdf_bytes, content_type="application/pdf")
    r3 = client.post(
        "/catalogos/pedidos/logistica/corta/",
        {"action": "enviar", "orden_id": int(orden.id), "cantidad": 2, "comprobante_pdf": upload2},
    )
    r3_status = int(getattr(r3, "status_code", 0) or 0)

    orden.refresh_from_db(using="mes")
    envios = list(LogisticaEnvioCorta.objects.using("mes").filter(orden_id=int(orden.id)).order_by("id"))
    exp = LogisticaExpediente.objects.using("mes").filter(orden_corta_id=int(orden.id)).first()

    zip_resp = client.get(f"/catalogos/pedidos/logistica/corta/{int(orden.id)}/expediente.zip")
    zip_status = int(getattr(zip_resp, "status_code", 0) or 0)
    zip_bytes = bytes(getattr(zip_resp, "content", b"") or b"")

    exp.refresh_from_db(using="mes")
    descargas = list(LogisticaExpedienteDescarga.objects.using("mes").filter(orden_corta_id=int(orden.id)).order_by("-id"))

    decote_before = LaserOrdenProduccion.objects.using("mes").filter(id=int(orden.id)).exists()
    r_del = client.post("/catalogos/pedidos/logistica/corta/", {"action": "decote_delete", "orden_id": int(orden.id)})
    r_del_status = int(getattr(r_del, "status_code", 0) or 0)
    decote_after = LaserOrdenProduccion.objects.using("mes").filter(id=int(orden.id)).exists()

    out_dir = base_dir / "media" / "expedientes_simulados"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_zip = out_dir / f"Expediente_{folio_externo}.zip"
    out_zip.write_bytes(zip_bytes)

    pdf_in_zip = 0
    xlsx_in_zip = 0
    try:
        import zipfile

        with zipfile.ZipFile(out_zip, mode="r") as zf:
            for name in zf.namelist():
                if name.lower().endswith(".pdf"):
                    pdf_in_zip += 1
                if name.lower().endswith(".xlsx"):
                    xlsx_in_zip += 1
    except Exception:
        pdf_in_zip = -1
        xlsx_in_zip = -1

    print("SIM_LOGISTICA_CORTA_RESULT")
    print("cleanup_deleted_rows:", cleaned)
    print("orden_id:", int(orden.id))
    print("folio_externo:", folio_externo)
    print("producto:", producto)
    print("apartado:", int(getattr(orden, "apartado", 0) or 0))
    print("enviado:", int(getattr(orden, "enviado", 0) or 0))
    print("saldo:", max(0, int(getattr(orden, "total_piezas", 0) or 0) - int(getattr(orden, "apartado", 0) or 0) - int(getattr(orden, "enviado", 0) or 0)))
    print("envios_count:", len(envios))
    print("expediente_generado:", bool(exp and getattr(exp, "generado_en", None)))
    print("descargas_count:", int(getattr(exp, "descargas_count", 0) or 0) if exp else 0)
    print("descargas_rows:", len(descargas))
    print("zip_status:", zip_status, "zip_bytes:", len(zip_bytes))
    print("zip_saved_to:", str(out_zip))
    print("zip_xlsx_files:", xlsx_in_zip, "zip_pdf_files:", pdf_in_zip)
    print("apartar_status:", r1_status, "enviar1_status:", r2_status, "enviar2_status:", r3_status)
    print("decote_delete_status:", r_del_status, "order_existed_before:", decote_before, "order_exists_after:", decote_after)


if __name__ == "__main__":
    main()
