import os
import sys

import django
from core.bases import BASE  # noqa: F401


def _add(rows, *, categoria, tipo, nombre, calibre, espesor_mm, ancho_cm, largo_cm, peso_kg):
    rows.append(
        {
            "categoria_material": str(categoria),
            "tipo_material": str(tipo),
            "nombre": str(nombre),
            "calibre": str(calibre),
            "espesor_mm": float(espesor_mm),
            "ancho_mm": int(round(float(ancho_cm) * 10.0)),
            "largo_mm": int(round(float(largo_cm) * 10.0)),
            "peso_kg": float(peso_kg or 0.0),
            "activo": True,
        }
    )


def main():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mes_vigas_web.settings")
    django.setup()

    from catalogos.models import LaserMaterialPlaca

    rows = []

    categoria = "ACERO"

    tipo = "LÁMINA NEGRA: acero al carbón"
    for calibre, esp, kg in [
        ("C-16", 1.52, 26.96),
        ("C-14", 1.90, 33.7),
        ("C-12", 2.66, 47.17),
        ("C-11", 3.04, 53.91),
        ("C-10", 3.42, 60.65),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Lam negra R/C comercial (3 X 8')", calibre=calibre, espesor_mm=esp, ancho_cm=91.4, largo_cm=243.8, peso_kg=kg)
    for calibre, esp, kg in [
        ("C-16", 1.52, 33.7),
        ("C-14", 1.90, 42.12),
        ("C-12", 2.66, 58.97),
        ("C-11", 3.04, 67.39),
        ("C-10", 3.42, 75.82),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Lam negra R/C comercial (3 X 10')", calibre=calibre, espesor_mm=esp, ancho_cm=91.4, largo_cm=304.8, peso_kg=kg)
    for calibre, esp, kg in [
        ("C-16", 1.52, 35.94),
        ("C-14", 1.90, 44.93),
        ("C-12", 2.66, 62.90),
        ("C-11", 3.04, 71.88),
        ("C-10", 3.42, 80.87),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Lam negra R/C comercial (4 X 8')", calibre=calibre, espesor_mm=esp, ancho_cm=121.9, largo_cm=243.8, peso_kg=kg)
    for calibre, esp, kg in [
        ("C-16", 1.52, 44.93),
        ("C-14", 1.90, 56.16),
        ("C-12", 2.66, 76.82),
        ("C-11", 3.04, 89.86),
        ("C-10", 3.42, 101.09),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Lam negra R/C comercial (4 X 10')", calibre=calibre, espesor_mm=esp, ancho_cm=121.9, largo_cm=304.8, peso_kg=kg)

    for calibre, esp, kg in [
        ("C-26", 0.45, 7.88),
        ("C-24", 0.61, 10.68),
        ("C-22", 0.76, 13.3),
        ("C-20", 0.91, 15.93),
        ("C-18", 1.21, 21.18),
        ("C-16", 1.52, 26.6),
        ("C-14", 1.90, 33.7),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Lam negra R/F 1008 (3x 8')", calibre=calibre, espesor_mm=esp, ancho_cm=91.4, largo_cm=243.8, peso_kg=kg)
    for calibre, esp, kg in [
        ("C-26", 0.45, 9.85),
        ("C-24", 0.61, 13.35),
        ("C-22", 0.76, 16.63),
        ("C-20", 0.91, 19.91),
        ("C-18", 1.21, 26.47),
        ("C-16", 1.52, 33.26),
        ("C-14", 1.90, 42.12),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Lam negra R/F 1008 (3 x 10')", calibre=calibre, espesor_mm=esp, ancho_cm=91.4, largo_cm=304.8, peso_kg=kg)
    for calibre, esp, kg in [
        ("C-26", 0.45, 10.5),
        ("C-24", 0.61, 14.24),
        ("C-22", 0.76, 17.74),
        ("C-20", 0.91, 21.24),
        ("C-18", 1.21, 28.24),
        ("C-16", 1.52, 35.47),
        ("C-14", 1.90, 44.93),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Lam negra R/F 1008 (4 x 8')", calibre=calibre, espesor_mm=esp, ancho_cm=121.9, largo_cm=243.8, peso_kg=kg)
    for calibre, esp, kg in [
        ("C-26", 0.45, 13.3),
        ("C-24", 0.61, 17.8),
        ("C-22", 0.76, 22.17),
        ("C-20", 0.91, 26.55),
        ("C-18", 1.21, 35.3),
        ("C-16", 1.52, 44.34),
        ("C-14", 1.90, 56.16),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Lam negra R/F 1008 (4 x 10')", calibre=calibre, espesor_mm=esp, ancho_cm=121.9, largo_cm=304.8, peso_kg=kg)

    tipo = "PLACA ASTM A36 Y A572 G50"
    for calibre, esp, kg in [
        ('3/16"', 4.8, 421),
        ('1/4"', 6.4, 562),
        ('5/16"', 7.9, 702),
        ('3/8"', 9.5, 842),
        ('7/16"', 11.1, 983),
        ('1/2"', 12.7, 1123),
        ('5/8"', 15.9, 1404),
        ('3/4"', 19.1, 1685),
        ('7/8"', 22.2, 1966),
        ('1"', 25.4, 2246),
        ('1 1/4"', 31.8, 2808),
        ('1 1/2"', 38.1, 3370),
        ('1 3/4"', 44.5, 3931),
        ('2"', 50.8, 4493),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Placa A-36 (6 x 20')", calibre=calibre, espesor_mm=esp, ancho_cm=182.8, largo_cm=609.6, peso_kg=kg)
    for calibre, esp, kg in [
        ('3/16"', 4.8, 562),
        ('1/4"', 6.4, 749),
        ('5/16"', 7.9, 936),
        ('3/8"', 9.5, 1123),
        ('7/16"', 11.1, 1311),
        ('1/2"', 12.7, 1498),
        ('5/8"', 15.9, 1872),
        ('3/4"', 19.1, 2246),
        ('7/8"', 22.2, 2621),
        ('1"', 25.4, 2995),
        ('1 1/4"', 31.8, 3744),
        ('1 1/2"', 38.1, 4493),
        ('1 3/4"', 44.5, 5242),
        ('2"', 50.8, 5990),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Placa A-36 (8 x 20')", calibre=calibre, espesor_mm=esp, ancho_cm=243.8, largo_cm=609.6, peso_kg=kg)
    for calibre, esp, kg in [
        ('1/8"', 3.17, 0),
        ('3/16"', 4.8, 186),
        ('1/4"', 6.4, 279),
        ('3/8"', 9.5, 764),
        ('1/2"', 12.7, 742),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Placa A-36 (4x10')", calibre=calibre, espesor_mm=esp, ancho_cm=121.9, largo_cm=304.8, peso_kg=kg)

    tipo = "Placa AC COMERCIAL"
    for calibre, esp, kg in [
        ('1/8"', 3.17, 69),
        ('3/16"', 4.8, 104),
        ('1/4"', 6.4, 139),
        ('5/16"', 7.9, 174),
        ('3/8"', 9.5, 208),
        ('1/2"', 12.7, 278),
        ('5/8"', 15.9, 348),
        ('3/4"', 19.1, 417),
        ('1"', 25.4, 556),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Placa AC comercial (3x10')", calibre=calibre, espesor_mm=esp, ancho_cm=91.4, largo_cm=304.8, peso_kg=kg)
    for calibre, esp, kg in [
        ('3/16"', 4.8, 186),
        ('1/4"', 6.4, 279),
        ('5/16"', 7.9, 371),
        ('3/8"', 9.5, 764),
        ('1/2"', 12.7, 742),
        ('5/8"', 15.9, 139),
        ('3/4"', 19.1, 232),
        ('1"', 25.4, 557),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre="Placa AC comercial (4x10')", calibre=calibre, espesor_mm=esp, ancho_cm=121.9, largo_cm=304.8, peso_kg=kg)

    categoria = "ACERO INOXIDABLE"
    tipo = "PLACA DE ACERO INOXIDABLE"
    nombre = "Hoja 304 2B (4x10')"
    for esp, kg in [
        (10.0, 103.25),
        (11.0, 91.81),
        (12.0, 80.37),
        (14.0, 57.19),
        (16.0, 45.75),
        (18.0, 36.72),
        (20.0, 26.85),
        (22.0, 22.27),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre=nombre, calibre="", espesor_mm=esp, ancho_cm=121.9, largo_cm=304.8, peso_kg=kg)
    for calibre, esp, kg in [
        ('1/8"', 3.17, 0),
        ('3/16"', 4.76, 143.28),
        ('1/4"', 6.35, 191.14),
        ('3/8"', 9.53, 286.86),
        ('1/2"', 12.70, 382.28),
        ('1"', 25.40, 764.55),
    ]:
        _add(rows, categoria=categoria, tipo=tipo, nombre=nombre, calibre=calibre, espesor_mm=esp, ancho_cm=121.9, largo_cm=304.8, peso_kg=kg)

    categoria = "ALUMINIO"
    tipo = "LÁMINA DE ALUMINIO"
    _add(
        rows,
        categoria=categoria,
        tipo=tipo,
        nombre="Lámina lisa de aluminio 3003 H14 (4x10)",
        calibre='1/8"',
        espesor_mm=3.17,
        ancho_cm=121.9,
        largo_cm=304.8,
        peso_kg=0,
    )

    created = 0
    updated = 0
    for r in rows:
        nombre_norm = (r["nombre"] or "").strip().upper()
        obj = (
            LaserMaterialPlaca.objects.using(BASE)
            .filter(
                categoria_material=r["categoria_material"],
                tipo_material=r["tipo_material"],
                nombre_normalizado=nombre_norm,
                calibre=r["calibre"],
                espesor_mm=r["espesor_mm"],
                largo_mm=r["largo_mm"],
                ancho_mm=r["ancho_mm"],
            )
            .first()
        )
        if obj:
            changed = False
            for k in ["categoria_material", "tipo_material", "nombre", "peso_kg", "activo"]:
                if getattr(obj, k) != r[k]:
                    setattr(obj, k, r[k])
                    changed = True
            if changed:
                obj.save(using=BASE)
                updated += 1
            continue
        LaserMaterialPlaca.objects.using(BASE).create(**r)
        created += 1

    print(f"rows={len(rows)} created={created} updated={updated}")


if __name__ == "__main__":
    main()
