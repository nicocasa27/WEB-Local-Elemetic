"""Dos ayudantes de `produccion/views.py` que ya no llamaba nadie.

No tienen que ver entre sí ni con el importador de PDF: aparecieron al
revisar el archivo entero buscando qué más había dejado de usarse. Los dos
son de una época en la que las asignaciones y el tablero se dibujaban de
otra manera.

- `_build_asignacion_payload` — el diálogo de asignaciones lo sustituyó
  `_build_participantes_payload`, que sí se usa.
- `_find_top_marca` — nada lo nombra en el proyecto.

Se guardan por si el cálculo sirve de referencia. No se importan desde
ningún sitio y no se ejecutan.
"""

def _build_asignacion_payload():
    payload = {}
    armado_equipo = _equipo_for_etapa("Armado")
    if armado_equipo:
        qs = Colaborador.objects.filter(activo=True, equipo=armado_equipo).order_by("rol", "nombre")
        payload["Armado"] = {
            "equipo": armado_equipo.nombre,
            "soldadores": [{"id": c.id, "nombre": c.nombre} for c in qs.filter(rol="Soldador")],
            "auxiliares": [{"id": c.id, "nombre": c.nombre} for c in qs.filter(rol="Auxiliar")],
        }
    pintura_equipo = _equipo_for_etapa("Pintura")
    if pintura_equipo:
        qs = Colaborador.objects.filter(activo=True, equipo=pintura_equipo).order_by("rol", "nombre")
        payload["Pintura"] = {
            "equipo": pintura_equipo.nombre,
            "pintores": [{"id": c.id, "nombre": c.nombre} for c in qs.filter(rol="Pintor")],
        }
    return payload


def _find_top_marca(lines):
    joined = " ".join([ln.strip() for ln in lines[:40] if (ln or "").strip()]).upper()
    joined = re.sub(r"\s+", " ", joined)
    pat = re.compile(r"\b\d{1,2}[A-Z]{1,6}\d{1,4}-[0-9]{1,3}[A-Z]?\b")
    m = pat.search(joined)
    if m:
        return m.group(0).strip()
    pat2 = re.compile(r"\b[A-Z]{1,6}\d{1,4}-[0-9]{1,3}[A-Z]?\b")
    m2 = pat2.search(joined)
    if m2:
        return m2.group(0).strip()
    return ""
