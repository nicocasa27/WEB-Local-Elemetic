"""El importador de vigas desde PDF. **Aparcado: no lo llama nadie.**

Quinientas veintisiete líneas —la vista `viga_import` y su analizador de
PDF— que vivían en `produccion/views.py` sin ninguna ruta en `urls.py`. No
se podía abrir desde ninguna parte del sistema, ni por dirección directa: no
existía. Y su plantilla enlazaba a `{% url 'produccion:viga_import' %}`, que
hoy ni siquiera resuelve.

Estorbaba de dos maneras. Quien leía `views.py` buscando cómo se dan de alta
las vigas encontraba esto primero y creía haber dado con el camino bueno. Y
cada búsqueda, cada revisión y cada refactor tenía que pasar por encima.

No se borra. El analizador conoce el formato de los PDF de obra de este
taller, y ese conocimiento no está escrito en ningún otro sitio; en la fase de
inventario puede servir para leer certificados de material.

**El modelo `catalogos.PdfExtractionTemplate` se queda donde está.** Aquí sólo
se aparca código: la tabla tiene datos y las tablas no se tocan.

Para revivirlo: devolver este bloque a `produccion/views.py`, devolver
`viga_import.html` a `produccion/templates/produccion/`, añadir la ruta en
`produccion/urls.py`, y volver a importar `PdfExtractionTemplate`.
"""

def _to_canonical_rows(rows, headers):
    today = timezone.localdate()
    map_ = _guess_mapping(headers)
    out = []
    for r in rows:
        d = _normalize_row(r, map_, today)
        out.append(
            {
                "codigo": d["codigo"],
                "proyecto": d["proyecto"],
                "descripcion": d["descripcion"],
                "peso": d["peso"],
                "cantidad": d["cantidad"],
                "estado": d["estado"],
                "prioridad": d["prioridad"] or "1",
                "observaciones": "",
                "fecha": d["fecha"].isoformat(),
            }
        )
    return out


def _pdf_default_config():
    return {
        "big_mark_regex": r"\b\d{1,2}[A-Z]{1,6}\d{1,4}-\d{1,3}[A-Z]?\b",
        "mark_regex": r"\b[A-Z]{1,6}\d{1,4}-\d{1,3}[A-Z]?\b",
        "profile_regex": r"\b(IPR|IPE|IPN|HEB|HEA|W)\b\s*([0-9A-ZxX.,/]+(?:KG/ML)?)",
        "total_regex": r"\bTOTAL\b.*?(\d+(?:[.,]\d+)?)\b",
        "num_piezas_regex": r"\b(\d{1,4})\b",
        "prefer_total": True,
    }


def _extract_pdf_lines(content: bytes):
    if PdfReader is None:
        return []
    reader = PdfReader(io.BytesIO(content))
    lines = []
    for page in reader.pages[:10]:
        text = page.extract_text() or ""
        text = text.replace("\u00a0", " ")
        for ln in text.splitlines():
            ln = ln.strip()
            if ln:
                lines.append(ln)
    return lines


def _guess_proyecto_from_lines(lines):
    up_all = re.sub(r"\s+", " ", "\n".join(lines)).upper()
    if "ALMAERA" in up_all:
        return "ALMAERA"
    m = re.search(r"\bPROYECTO\b\s*[:\-]\s*([A-Z0-9 \-_/]{3,})", up_all)
    if m:
        return m.group(1).strip().upper()
    return ""


def _extract_rows_from_lines(lines, config):
    cfg = _pdf_default_config()
    cfg.update({k: v for k, v in (config or {}).items() if v is not None})

    up_all = re.sub(r"\s+", " ", "\n".join(lines)).upper()
    proyecto = _guess_proyecto_from_lines(lines) or "SIN PROYECTO"

    big_mark_re = re.compile(cfg["big_mark_regex"])
    mark_re = re.compile(cfg["mark_regex"])
    profile_re = re.compile(cfg["profile_regex"])
    total_re = re.compile(cfg["total_regex"], flags=re.IGNORECASE)
    num_re = re.compile(cfg["num_piezas_regex"])

    current_big = ""
    for ln in lines[:60]:
        m = big_mark_re.search(ln.upper())
        if m:
            current_big = m.group(0).strip()
            break

    total_doc = None
    for ln in lines:
        if "TOTAL" in ln.upper():
            m = total_re.search(ln)
            if m:
                try:
                    total_doc = float(m.group(1).replace(",", "."))
                    break
                except Exception:
                    logger.exception("Error ignorado en _extract_rows_from_lines()")

    num_piezas = None
    for ln in lines:
        up = ln.upper()
        if ("NUMERO DE PIEZAS" in up) or ("NÚMERO DE PIEZAS" in up):
            m = num_re.search(up)
            if m:
                try:
                    num_piezas = int(m.group(1))
                    break
                except Exception:
                    logger.exception("Error ignorado en _extract_rows_from_lines()")

    keywords = ("IPR", "IPE", "IPN", "HEB", "HEA", "W ")
    seen = set()
    out = []
    for ln in lines:
        up = ln.upper()
        if not any(k in up for k in keywords):
            continue
        prof_m = profile_re.search(up)
        if not prof_m:
            continue
        mm = mark_re.search(up)
        if not mm:
            continue

        marca = mm.group(0).strip()
        if marca in seen:
            continue
        seen.add(marca)

        perfil = f"{prof_m.group(1)} {prof_m.group(2)}".strip()
        nums = re.findall(r"\d+(?:[.,]\d+)?", up)
        kg_pza = None
        kg_total = None
        if len(nums) >= 2:
            try:
                kg_pza = float(nums[-2].replace(",", "."))
                kg_total = float(nums[-1].replace(",", "."))
            except Exception:
                kg_pza = None
                kg_total = None

        peso_out = None
        if cfg.get("prefer_total") and total_doc:
            peso_out = total_doc
        elif kg_total:
            peso_out = kg_total
        elif kg_pza:
            peso_out = kg_pza
        else:
            peso_out = 0.0

        out.append(
            {
                "codigo": current_big or marca,
                "proyecto": proyecto,
                "descripcion": perfil,
                "peso": round(float(peso_out or 0.0), 2),
                "cantidad": int(num_piezas or 1),
                "estado": ESTADOS[0],
                "prioridad": "1",
                "observaciones": "",
                "fecha": timezone.localdate().isoformat(),
            }
        )

    return out


def _extract_rows_from_pdf(content: bytes):
    lines = _extract_pdf_lines(content)
    text_all = "\n".join(lines)
    up_all = re.sub(r"\s+", " ", "\n".join(lines)).upper()

    proyecto = ""
    m = re.search(r"\bPROYECTO\b\s*[:\-]\s*([A-Z0-9 \-_/]{3,})", up_all)
    if m:
        proyecto = m.group(1).strip()
    if "ALMAERA" in up_all:
        proyecto = "ALMAERA"
    if not proyecto:
        proyecto = "SIN PROYECTO"

    descripcion = ""
    m = re.search(r"\bTITULO\s+DEL\s+PLANO\b\s*[:\-]\s*(.+)", text_all, flags=re.IGNORECASE)
    if m:
        descripcion = m.group(1).strip()
    if not descripcion:
        m = re.search(r"\bVIGA\s+PRINCIPAL\b", up_all)
        if m:
            descripcion = "VIGA PRINCIPAL"

    keywords = ("IPR", "IPE", "IPN", "HEB", "HEA", "W ")
    big_mark_re = re.compile(r"\b\d{1,2}[A-Z]{1,6}\d{1,4}-\d{1,3}[A-Z]?\b")
    mark_re = re.compile(r"\b[A-Z]{1,6}\d{1,4}-\d{1,3}[A-Z]?\b")
    profile_re = re.compile(r"\b(IPR|IPE|IPN|HEB|HEA|W)\b\s*([0-9A-ZxX.,/]+(?:KG/ML)?)")

    seen = set()
    out_rows = []
    current_big = ""
    current_num_piezas = None
    current_total = None

    for ln in lines:
        up = ln.upper()

        bm = big_mark_re.search(up)
        if bm:
            current_big = bm.group(0).strip()

        if ("NUMERO DE PIEZAS" in up) or ("NÚMERO DE PIEZAS" in up):
            ints = re.findall(r"\b\d{1,4}\b", up)
            if ints:
                try:
                    current_num_piezas = int(ints[-1])
                except Exception:
                    logger.exception("Error ignorado en _extract_rows_from_pdf()")

        sm = mark_re.search(up)
        if sm and current_num_piezas is None and "EMBARQUE" in up_all:
            ints = re.findall(r"\b\d{1,4}\b", up)
            if ints:
                try:
                    current_num_piezas = int(ints[0])
                except Exception:
                    logger.exception("Error ignorado en _extract_rows_from_pdf()")

        if "TOTAL" in up:
            nums = re.findall(r"\d+(?:[.,]\d+)?", up)
            if nums:
                try:
                    current_total = float(nums[-1].replace(",", "."))
                except Exception:
                    logger.exception("Error ignorado en _extract_rows_from_pdf()")

        if "LISTA DE MATERIALES" not in up_all and not any(k in up for k in keywords):
            continue

        prof_m = profile_re.search(up)
        if not prof_m:
            continue

        mm = mark_re.search(up)
        if not mm:
            continue
        marca = mm.group(0).strip()

        nums = re.findall(r"\d+(?:[.,]\d+)?", up)
        kg_pza = None
        kg_total = None
        if len(nums) >= 2:
            try:
                kg_pza = float(nums[-2].replace(",", "."))
                kg_total = float(nums[-1].replace(",", "."))
            except Exception:
                kg_pza = None
                kg_total = None

        if marca in seen:
            continue
        seen.add(marca)

        cantidad = int(current_num_piezas or 1)
        if not current_total and kg_total:
            current_total = kg_total

        perfil = f"{prof_m.group(1)} {prof_m.group(2)}".strip()
        codigo_out = current_big or marca
        peso_out = float(current_total or 0.0)
        if peso_out <= 0 and kg_total:
            peso_out = float(kg_total)
        if peso_out <= 0 and kg_pza:
            peso_out = float(kg_pza)

        out_rows.append(
            {
                "codigo": codigo_out,
                "proyecto": proyecto,
                "descripcion": perfil,
                "peso": round(peso_out, 2),
                "cantidad": cantidad,
                "estado": ESTADOS[0],
                "prioridad": "1",
                "observaciones": "",
                "fecha": timezone.localdate().isoformat(),
            }
        )

    if out_rows:
        return out_rows, []

    codigo = ""
    m = big_mark_re.search(up_all) or mark_re.search(up_all)
    if m:
        codigo = m.group(0).strip()
    peso = ""
    m = re.search(r"\bPESO\b\s*[:\-]?\s*([0-9]+(?:[.,][0-9]+)?)\s*KG", up_all)
    if m:
        peso = m.group(1)
    cantidad = ""
    m = re.search(r"(?:PZAS|PIEZAS|CANTIDAD)\s*[:\-]?\s*([0-9]{1,4})", up_all)
    if m:
        cantidad = m.group(1)
    rows = []
    if codigo or proyecto or descripcion or peso or cantidad:
        rows = [
            {
                "codigo": codigo,
                "proyecto": proyecto,
                "descripcion": descripcion,
                "peso": float(str(peso).replace(",", ".") or 0),
                "cantidad": int(cantidad or "1"),
                "estado": ESTADOS[0],
                "prioridad": "1",
                "observaciones": "",
                "fecha": timezone.localdate().isoformat(),
            }
        ]
    return rows, []


@login_required
def viga_import(request):
    if not _is_admin_user(request.user):
        return redirect("produccion:home")
    pdf_notice = None
    if request.method == "POST":
        stage = request.POST.get("stage", "upload")
        if stage == "upload":
            form = VigaImportUploadForm(request.POST, request.FILES)
            if form.is_valid():
                f = form.cleaned_data["archivo"]
                name = f.name.lower()
                content = f.read()
                rows = []
                headers = []
                pdf_lines = []
                template_cfg = {}
                template_id = ""
                guessed_proyecto = ""
                if name.endswith(".csv"):
                    text = content.decode("utf-8", errors="ignore")
                    reader = csv.DictReader(io.StringIO(text))
                    headers = reader.fieldnames or []
                    for r in reader:
                        rows.append({k: r.get(k, "") for k in headers})
                elif name.endswith(".xlsx"):
                    bio = io.BytesIO(content)
                    wb = load_workbook(bio, read_only=True, data_only=True)
                    ws = wb.active
                    it = ws.iter_rows(values_only=True)
                    headers = [str(x or "").strip() for x in next(it, [])]
                    for row in it:
                        d = {}
                        for i, h in enumerate(headers):
                            d[h] = row[i] if i < len(row) else ""
                        rows.append(d)
                elif name.endswith(".pdf"):
                    try:
                        pdf_lines = _extract_pdf_lines(content)
                        guessed_proyecto = _guess_proyecto_from_lines(pdf_lines)
                        tmpl = (
                            PdfExtractionTemplate.objects.filter(activo=True, proyecto_normalizado=guessed_proyecto)
                            .order_by("-actualizado_en")
                            .first()
                            if guessed_proyecto
                            else PdfExtractionTemplate.objects.filter(activo=True, proyecto_normalizado="")
                            .order_by("-actualizado_en")
                            .first()
                        )
                        if tmpl:
                            template_id = str(tmpl.pk)
                            try:
                                template_cfg = json.loads(tmpl.config_json or "{}") if tmpl.config_json else {}
                            except Exception:
                                template_cfg = {}
                        rows = _extract_rows_from_lines(pdf_lines, template_cfg)
                        if not rows:
                            pdf_notice = "No se detectó una tabla o datos suficientes en el PDF. Usa “Ver texto extraído” y ajusta la plantilla."
                    except Exception:
                        pdf_notice = "No se pudo leer el PDF. Intenta exportar la tabla a Excel/CSV y súbela aquí."
                else:
                    pdf_notice = "Formato no reconocido. Usa PDF, CSV o XLSX."
                if name.endswith(".pdf") and pdf_lines:
                    return render(
                        request,
                        "produccion/viga_import.html",
                        {
                            "form": VigaImportUploadForm(),
                            "rows": rows,
                            "estados": ESTADOS,
                            "pdf_lines_json": json.dumps(pdf_lines) if pdf_lines else "",
                            "pdf_text": "\n".join(pdf_lines) if pdf_lines else "",
                            "template_id": template_id,
                            "template_cfg": {**_pdf_default_config(), **(template_cfg or {})},
                            "template_proyecto": guessed_proyecto,
                            "pdf_notice": pdf_notice,
                        },
                    )
                if rows:
                    headers = [str(h) for h in headers]
                    canon_rows = _to_canonical_rows(rows, headers)
                    return render(
                        request,
                        "produccion/viga_import.html",
                        {
                            "form": VigaImportUploadForm(),
                            "rows": canon_rows,
                            "estados": ESTADOS,
                            "pdf_notice": pdf_notice,
                        },
                    )
            return render(
                request,
                "produccion/viga_import.html",
                {"form": form, "pdf_notice": pdf_notice},
            )
        elif stage in {"reparse", "save_template"}:
            pdf_lines = json.loads(request.POST.get("pdf_lines_json") or "[]")
            template_id = (request.POST.get("template_id") or "").strip()
            template_proyecto = (request.POST.get("template_proyecto") or "").strip().upper()
            template_cfg = {
                "big_mark_regex": request.POST.get("big_mark_regex") or _pdf_default_config()["big_mark_regex"],
                "mark_regex": request.POST.get("mark_regex") or _pdf_default_config()["mark_regex"],
                "profile_regex": request.POST.get("profile_regex") or _pdf_default_config()["profile_regex"],
                "total_regex": request.POST.get("total_regex") or _pdf_default_config()["total_regex"],
                "num_piezas_regex": request.POST.get("num_piezas_regex") or _pdf_default_config()["num_piezas_regex"],
                "prefer_total": request.POST.get("prefer_total") == "1",
            }
            if stage == "save_template":
                nombre = (request.POST.get("template_nombre") or "").strip() or f"Plantilla {template_proyecto or 'PDF'}"
                if template_id:
                    PdfExtractionTemplate.objects.filter(pk=template_id).update(
                        nombre=nombre,
                        proyecto_normalizado=template_proyecto,
                        config_json=json.dumps(template_cfg),
                        activo=True,
                    )
                else:
                    t = PdfExtractionTemplate.objects.create(
                        nombre=nombre,
                        proyecto_normalizado=template_proyecto,
                        config_json=json.dumps(template_cfg),
                        activo=True,
                    )
                    template_id = str(t.pk)
                pdf_notice = "Plantilla guardada."
            rows = _extract_rows_from_lines(pdf_lines, template_cfg)
            return render(
                request,
                "produccion/viga_import.html",
                {
                    "form": VigaImportUploadForm(),
                    "rows": rows,
                    "estados": ESTADOS,
                    "pdf_lines_json": json.dumps(pdf_lines) if pdf_lines else "",
                    "pdf_text": "\n".join(pdf_lines) if pdf_lines else "",
                    "template_id": template_id,
                    "template_cfg": {**_pdf_default_config(), **(template_cfg or {})},
                    "template_proyecto": template_proyecto,
                    "pdf_notice": pdf_notice,
                },
            )
        elif stage == "commit":
            total_rows = int(request.POST.get("total_rows") or "0")
            created = 0
            first_code = ""
            observaciones_global = (request.POST.get("observaciones_global") or "").strip()
            with transaction.atomic(using="mes"):
                now = timezone.now()
                for i in range(total_rows):
                    codigo = (request.POST.get(f"codigo_{i}") or "").strip()
                    if not codigo:
                        continue
                    proyecto = (request.POST.get(f"proyecto_{i}") or "SIN PROYECTO").strip().upper()
                    descripcion = (request.POST.get(f"descripcion_{i}") or "").strip()
                    try:
                        peso = float((request.POST.get(f"peso_{i}") or "0").replace(",", "."))
                    except Exception:
                        peso = 0.0
                    try:
                        cantidad = int(request.POST.get(f"cantidad_{i}") or "1")
                    except Exception:
                        cantidad = 1
                    cantidad = max(cantidad, 1)
                    estado = (request.POST.get(f"estado_{i}") or ESTADOS[0]).strip()
                    if estado not in ESTADOS:
                        estado = ESTADOS[0]
                    try:
                        prioridad = int(request.POST.get(f"prioridad_{i}") or "1")
                    except Exception:
                        prioridad = 1
                    prioridad = max(prioridad, 1)
                    observaciones = (request.POST.get(f"observaciones_{i}") or "").strip() or observaciones_global
                    fecha_txt = (request.POST.get(f"fecha_{i}") or "").strip()
                    fecha = timezone.localdate()
                    if fecha_txt:
                        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                            try:
                                fecha = datetime.strptime(fecha_txt, fmt).date()
                                break
                            except Exception:
                                logger.exception("Error ignorado en viga_import()")

                    if not first_code:
                        first_code = codigo

                    Proyecto.objects.get_or_create(
                        nombre_normalizado=proyecto.upper(),
                        defaults={"nombre": proyecto.upper(), "activo": True},
                    )

                    for n_pieza in range(1, cantidad + 1):
                        Viga.objects.create(
                            codigo_viga=codigo,
                            pieza_no=n_pieza,
                            total_piezas=cantidad,
                            proyecto=proyecto,
                            descripcion=descripcion,
                            fecha_compromiso=fecha,
                            estado=estado,
                            observaciones=observaciones,
                            prioridad=prioridad,
                            peso_kg=peso,
                            fecha_creacion=now,
                            ultimo_cambio=now,
                        )
                        created += 1
            if first_code:
                return redirect(f"{reverse('produccion:viga_list')}?q={first_code}")
            return redirect("produccion:viga_list")
    form = VigaImportUploadForm()
    return render(
        request,
        "produccion/viga_import.html",
        {"form": form, "pdf_notice": pdf_notice},
    )


# ------------------------------------------------ ayudantes del importador
#
# Se quedaron huérfanos en `produccion/views.py` al aparcar el bloque de
# arriba: eran los únicos que los llamaban.

def _guess_mapping(headers):
    keys = [h.strip() for h in headers]
    lo = [h.lower() for h in keys]
    def find(candidates):
        for name in candidates:
            for i, h in enumerate(lo):
                if h == name or name in h:
                    return keys[i]
        return keys[0] if keys else ""
    return {
        "codigo": find(["marca", "codigo_viga", "código", "codigo", "code", "viga"]),
        "proyecto": find(["proyecto", "proy"]),
        "descripcion": find(["descripcion", "descripción", "desc", "perfil", "titulo"]),
        "peso": find(["kg/pza", "kg_pza", "kg por pieza", "peso_kg", "peso", "kg"]),
        "cantidad": find(["cantidad", "numero de piezas", "número de piezas", "piezas", "total"]),
        "estado": "",
        "prioridad": "",
        "fecha": "",
    }


def _normalize_row(row, map_, today):
    def get(name):
        col = map_.get(name) or ""
        val = row.get(col, "")
        if val is None:
            return ""
        return str(val).strip()
    codigo = get("codigo")
    proyecto = get("proyecto").upper()
    descripcion = get("descripcion")
    try:
        peso = float(get("peso").replace(",", "."))
    except Exception:
        peso = 0.0
    try:
        cantidad = int(float(get("cantidad") or "1"))
    except Exception:
        cantidad = 1
    estado = get("estado")
    if estado and estado not in ESTADOS:
        estado = ""
    prioridad = get("prioridad")
    fecha_txt = get("fecha")
    fecha = today
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            fecha = datetime.strptime(fecha_txt, fmt).date()
            break
        except Exception:
            logger.exception("Error ignorado en _normalize_row()")
    if not proyecto:
        proyecto = "SIN PROYECTO"
    return {
        "codigo": codigo,
        "proyecto": proyecto,
        "descripcion": descripcion,
        "peso": peso,
        "cantidad": max(cantidad, 1),
        "estado": estado or ESTADOS[0],
        "prioridad": prioridad or "",
        "fecha": fecha,
    }
