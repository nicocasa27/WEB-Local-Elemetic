/* Alta y edición de órdenes de Corta.mx.
 *
 * Estaba escrito dentro de la plantilla. Aquí se puede leer y el navegador lo
 * guarda en caché.
 *
 * Lo que la plantilla sabe y este archivo no llega en los atributos de #mesCfg.
 */

const cfg = document.getElementById("mesCfg").dataset;

(function () {
  try { window.parent.postMessage({type: "corte:close-edit", reload: true}, window.location.origin); } catch (e) {}
})();

  (function () {
    const payloadEl = document.getElementById("laserMaterialesPayload");
    const payload = payloadEl ? JSON.parse(payloadEl.textContent) : [];
    const matSel = document.getElementById(cfg.campoMaterial);
    const catSel = document.getElementById("laserMaterialCategoria");
    const tipoSel = document.getElementById("laserMaterialTipo");
    const anchoInput = document.getElementById(cfg.campoAncho);
    const altoInput = document.getElementById(cfg.campoAlto);
    const qtyInput = document.getElementById(cfg.campoPiezas);
    const outPza = document.getElementById("laserKgPza");
    const outTotal = document.getElementById("laserKgTotal");
    const outEspesor = document.getElementById(cfg.campoEspesor);
    const outCalibre = document.getElementById(cfg.campoCalibre);
    const avisoPlaca = document.getElementById("laserAvisoPlaca");
    const input = document.getElementById("pdfArchivoInput");
    const frame = document.getElementById("pdfArchivoFrame");
    const openTab = document.getElementById("pdfArchivoOpenTab");
    const cpInput = document.getElementById(cfg.campoCliente);
    if (cpInput) cpInput.setAttribute("list", "cortaClienteProyectoList");

    // El alta de placa la rellena y la lectura de la cotización la llama.
    // Compartida aquí y no en `window`, que es de todos y de nadie.
    let proponerPlaca = null;

    const matMap = {};
    (payload || []).forEach((m) => {
      if (!m || !m.id) return;
      matMap[String(m.id)] = m;
    });

    const optTextById = {};
    if (matSel) {
      Array.from(matSel.options || []).forEach((o) => {
        const v = String(o.value || "").trim();
        if (!v) return;
        optTextById[v] = o.textContent || "";
      });
    }

    function uniqSorted(values) {
      const set = new Set();
      (values || []).forEach((v) => {
        const s = String(v || "").trim();
        if (s) set.add(s);
      });
      return Array.from(set).sort((a, b) => a.localeCompare(b, "es"));
    }

    function fillSelect(sel, items, allLabel) {
      if (!sel) return;
      const cur = String(sel.value || "");
      sel.innerHTML = "";
      const allOpt = document.createElement("option");
      allOpt.value = "";
      allOpt.textContent = allLabel;
      sel.appendChild(allOpt);
      (items || []).forEach((v) => {
        const opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v;
        sel.appendChild(opt);
      });
      sel.value = cur;
    }

    function sortMaterials(list) {
      return (list || []).slice().sort((a, b) => {
        const ac = String(a.categoria_material || "");
        const bc = String(b.categoria_material || "");
        if (ac !== bc) return ac.localeCompare(bc, "es");
        const at = String(a.tipo_material || "");
        const bt = String(b.tipo_material || "");
        if (at !== bt) return at.localeCompare(bt, "es");
        const an = String(a.nombre || "");
        const bn = String(b.nombre || "");
        if (an !== bn) return an.localeCompare(bn, "es");
        const ae = parseFloat(a.espesor_mm || "0");
        const be = parseFloat(b.espesor_mm || "0");
        if (ae !== be) return ae - be;
        const al = parseFloat(a.largo_mm || "0");
        const bl = parseFloat(b.largo_mm || "0");
        if (al !== bl) return al - bl;
        const aa = parseFloat(a.ancho_mm || "0");
        const ba = parseFloat(b.ancho_mm || "0");
        if (aa !== ba) return aa - ba;
        return (parseInt(a.id || "0", 10) || 0) - (parseInt(b.id || "0", 10) || 0);
      });
    }

    function tiposForCategoria(cat) {
      const c = String(cat || "").trim();
      const items = (payload || []).filter((m) => {
        const mc = String(m.categoria_material || "").trim();
        return !c || mc === c;
      });
      return uniqSorted(items.map((m) => m.tipo_material));
    }

    function rebuildMaterialOptions() {
      if (!matSel) return;
      const selected = String(matSel.value || "").trim();
      const cat = catSel ? String(catSel.value || "").trim() : "";
      const tipo = tipoSel ? String(tipoSel.value || "").trim() : "";
      const blankText = (matSel.options && matSel.options[0]) ? (matSel.options[0].textContent || "---------") : "---------";
      matSel.innerHTML = "";
      const blankOpt = document.createElement("option");
      blankOpt.value = "";
      blankOpt.textContent = blankText;
      matSel.appendChild(blankOpt);
      const filtered = sortMaterials((payload || []).filter((m) => {
        const mc = String(m.categoria_material || "").trim();
        const mt = String(m.tipo_material || "").trim();
        if (cat && mc !== cat) return false;
        if (tipo && mt !== tipo) return false;
        return true;
      }));
      filtered.forEach((m) => {
        const id = String(m.id || "").trim();
        if (!id) return;
        const opt = document.createElement("option");
        opt.value = id;
        opt.textContent = optTextById[id] || String(m.nombre || id);
        matSel.appendChild(opt);
      });
      if (selected && filtered.some((m) => String(m.id) === selected)) {
        matSel.value = selected;
      } else {
        matSel.value = "";
      }
    }

    function syncCategoryTypeFromSelectedMaterial() {
      if (!matSel || !catSel || !tipoSel) return;
      const mid = String(matSel.value || "").trim();
      const m = matMap[mid];
      if (!m) return;
      catSel.value = String(m.categoria_material || "").trim();
      fillSelect(tipoSel, tiposForCategoria(catSel.value), "Todos");
      tipoSel.value = String(m.tipo_material || "").trim();
      rebuildMaterialOptions();
    }

    if (catSel) {
      fillSelect(catSel, uniqSorted((payload || []).map((m) => m.categoria_material)), "Todas");
    }
    if (tipoSel) {
      fillSelect(tipoSel, tiposForCategoria(catSel ? catSel.value : ""), "Todos");
    }
    if (catSel) {
      catSel.addEventListener("change", () => {
        if (tipoSel) {
          const curTipo = String(tipoSel.value || "").trim();
          fillSelect(tipoSel, tiposForCategoria(catSel.value), "Todos");
          tipoSel.value = curTipo;
        }
        rebuildMaterialOptions();
        calc();
      });
    }
    if (tipoSel) {
      tipoSel.addEventListener("change", () => {
        rebuildMaterialOptions();
        calc();
      });
    }

    /* Espesor y cédula: se copian de la placa, pero se pueden escribir encima.
     *
     * La regla es una sola: **no se pisa lo que alguien escribió**. Mientras el
     * campo esté vacío o siga teniendo lo que puso la placa anterior, se
     * refresca al cambiar de placa. En cuanto se teclea algo distinto, ese
     * valor manda y ya no se toca, porque significa que la placa que había en
     * el taller no era exactamente la del catálogo y eso es justo lo que se
     * quiere anotar.
     *
     * Y cuando no cuadran, se dice. Una divergencia callada entre el pedido y
     * la placa es la clase de dato que aparece meses después sin que nadie
     * sepa cuál de los dos era el bueno.
     */
    function aMano(campo) {
      return campo && campo.dataset.aMano === "1";
    }

    function copiarDeLaPlaca(m) {
      const poner = (campo, valor) => {
        if (!campo || aMano(campo)) return;
        campo.value = m ? String(valor || "") : "";
        campo.dataset.deLaPlaca = campo.value;
      };
      poner(outEspesor, m && m.espesor_mm);
      poner(outCalibre, m && m.calibre);
    }

    function marcarSiLoCambiaron(campo) {
      if (!campo) return;
      const escrito = String(campo.value || "").trim();
      const puesto = String(campo.dataset.deLaPlaca || "").trim();
      // Volver a dejarlo como lo puso la placa -o vaciarlo- lo devuelve al
      // automático: si no, un tecleo y un arrepentimiento lo congelaban.
      campo.dataset.aMano = escrito && escrito !== puesto ? "1" : "0";
    }

    function mismoNumero(a, b) {
      const x = parseFloat(a);
      const y = parseFloat(b);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return false;
      return Math.abs(x - y) < 0.005;
    }

    function avisarSiNoCuadran(m) {
      if (!avisoPlaca) return;
      const quejas = [];
      if (m && outEspesor) {
        const escrito = String(outEspesor.value || "").trim();
        if (escrito && !mismoNumero(escrito, m.espesor_mm)) {
          quejas.push(`el espesor (${escrito} mm) no es el de la placa (${m.espesor_mm} mm)`);
        }
      }
      if (m && outCalibre) {
        const escrito = String(outCalibre.value || "").trim();
        const suyo = String(m.calibre || "").trim();
        if (escrito && suyo && escrito.toUpperCase() !== suyo.toUpperCase()) {
          quejas.push(`la cédula (${escrito}) no es la de la placa (${suyo})`);
        }
      }
      avisoPlaca.classList.toggle("d-none", !quejas.length);
      if (quejas.length) {
        avisoPlaca.textContent =
          "Ojo: " + quejas.join(" y ") + ". Se guarda lo escrito, no lo de la placa. " +
          "Los kilos se siguen calculando con la placa.";
      }
    }

    function filtrarPorEspesorYCalibre() {
      // Escribir 4.76 deja en la lista sólo las placas de ese espesor. Es como
      // se busca de verdad: «necesito la de 4.76», no «necesito una de acero».
      if (!matSel) return;
      const esp = outEspesor ? String(outEspesor.value || "").trim() : "";
      const ced = outCalibre ? String(outCalibre.value || "").trim() : "";
      if (!esp && !ced) return;

      const candidatas = (payload || []).filter((m) => {
        if (esp && !mismoNumero(esp, m.espesor_mm)) return false;
        if (ced && String(m.calibre || "").trim().toUpperCase() !== ced.toUpperCase()) return false;
        return true;
      });
      // Si sólo queda una, se elige sola: no tiene sentido obligar a abrir un
      // desplegable de un solo elemento.
      if (candidatas.length === 1 && String(matSel.value || "") !== String(candidatas[0].id)) {
        if (catSel) catSel.value = "";
        if (tipoSel) {
          fillSelect(tipoSel, tiposForCategoria(""), "Todos");
          tipoSel.value = "";
        }
        rebuildMaterialOptions();
        matSel.value = String(candidatas[0].id);
        syncCategoryTypeFromSelectedMaterial();
      }
    }

    [outEspesor, outCalibre].forEach((campo) => {
      if (!campo) return;
      campo.dataset.deLaPlaca = campo.value || "";
      // Lo que venga puesto al abrir una orden ya guardada es de la orden, no
      // de la placa: se respeta.
      campo.dataset.aMano = String(campo.value || "").trim() ? "1" : "0";
      campo.addEventListener("input", () => {
        marcarSiLoCambiaron(campo);
        filtrarPorEspesorYCalibre();
        calc();
      });
    });

    function round3(x) {
      return Math.round((x + Number.EPSILON) * 1000) / 1000;
    }

    function estPlateKg(m) {
      const direct = parseFloat(m && m.peso_kg ? String(m.peso_kg) : "0");
      if (Number.isFinite(direct) && direct > 0) return direct;
      const esp = parseFloat(m && m.espesor_mm ? String(m.espesor_mm) : "0");
      const l = parseFloat(m && m.largo_mm ? String(m.largo_mm) : "0");
      const a = parseFloat(m && m.ancho_mm ? String(m.ancho_mm) : "0");
      if (!(esp > 0) || !(l > 0) || !(a > 0)) return 0;
      const cat = String((m && m.categoria_material) ? m.categoria_material : "").toUpperCase();
      const tipo = String((m && m.tipo_material) ? m.tipo_material : "").toUpperCase();
      let dens = 7.85;
      if (cat.includes("ALUMIN") || tipo.includes("ALUMIN")) dens = 2.7;
      else if (cat.includes("INOX") || cat.includes("INOXID") || tipo.includes("INOX") || tipo.includes("INOXID")) dens = 8.0;
      const volMm3 = l * a * esp;
      const volCm3 = volMm3 / 1000.0;
      const kg = (volCm3 * dens) / 1000.0;
      return Number.isFinite(kg) && kg > 0 ? kg : 0;
    }

    function calc() {
      const mid = matSel ? String((matSel.value || "").trim()) : "";
      const m = matMap[mid];
      const ancho = anchoInput ? parseFloat(anchoInput.value || "0") : 0;
      const alto = altoInput ? parseFloat(altoInput.value || "0") : 0;
      const qtyRaw = qtyInput ? parseInt(qtyInput.value || "1", 10) : 1;
      const qty = Number.isFinite(qtyRaw) && qtyRaw > 0 ? qtyRaw : 1;
      copiarDeLaPlaca(m);
      avisarSiNoCuadran(m);
      if (!m || !(ancho > 0) || !(alto > 0)) {
        if (outPza) outPza.value = "";
        if (outTotal) outTotal.value = "";
        return;
      }
      const plateArea = (parseFloat(m.largo_mm || "0") * parseFloat(m.ancho_mm || "0"));
      if (!(plateArea > 0)) {
        if (outPza) outPza.value = "";
        if (outTotal) outTotal.value = "";
        return;
      }
      const margin = 30;
      const rectArea = (ancho + (2 * margin)) * (alto + (2 * margin));
      const plateKg = estPlateKg(m);
      if (!(plateKg > 0)) {
        if (outPza) outPza.value = "";
        if (outTotal) outTotal.value = "";
        return;
      }
      const perPiece = (rectArea / plateArea) * plateKg;
      const totalKg = perPiece * qty;
      if (outPza) outPza.value = String(round3(perPiece));
      if (outTotal) outTotal.value = String(round3(totalKg));
    }

    if (matSel) matSel.addEventListener("change", calc);
    if (anchoInput) anchoInput.addEventListener("input", calc);
    if (altoInput) altoInput.addEventListener("input", calc);
    if (qtyInput) qtyInput.addEventListener("input", calc);
    syncCategoryTypeFromSelectedMaterial();
    if (matSel) {
      matSel.addEventListener("change", () => {
        syncCategoryTypeFromSelectedMaterial();
        calc();
      });
    }
    calc();

    /* Alta de una placa sin salir del formulario.
     *
     * Lo que importa aquí no es el envío, que es trivial, sino que al volver la
     * placa quede metida en `payload` y en `optTextById`. Si no, la lista se
     * reconstruye al cambiar categoría o tipo y la recién creada desaparece,
     * y los kilos estimados salen vacíos porque `calc` la busca en `matMap`.
     */
    (function () {
      // Lo que se pueda saber de la placa antes de abrir el recuadro. Lo pone
      // la lectura de la cotización: ver `proponerPlaca` más abajo.
      let propuesta = null;

      const abrir = document.getElementById("nuevaPlacaAbrir");
      const panel = document.getElementById("nuevaPlacaPanel");
      const guardar = document.getElementById("nuevaPlacaGuardar");
      const cancelar = document.getElementById("nuevaPlacaCancelar");
      const aviso = document.getElementById("nuevaPlacaAviso");
      const url = cfg.urlPlacaNueva;
      if (!abrir || !panel || !guardar || !url) return;

      const campos = {
        categoria_material: document.getElementById("nuevaPlacaCategoria"),
        tipo_material: document.getElementById("nuevaPlacaTipo"),
        nombre: document.getElementById("nuevaPlacaNombre"),
        calibre: document.getElementById("nuevaPlacaCalibre"),
        espesor_mm: document.getElementById("nuevaPlacaEspesor"),
        largo_cm: document.getElementById("nuevaPlacaLargo"),
        ancho_cm: document.getElementById("nuevaPlacaAncho"),
        peso_kg: document.getElementById("nuevaPlacaPeso"),
      };

      function sugerencias() {
        // Para que quien da de alta reutilice las categorías y tipos que ya
        // existen en vez de inventar una variante nueva de la misma palabra.
        const lista = (sel, valores) => {
          const dl = document.getElementById(sel);
          if (!dl) return;
          dl.innerHTML = "";
          uniqSorted(valores).forEach((v) => {
            const o = document.createElement("option");
            o.value = v;
            dl.appendChild(o);
          });
        };
        lista("nuevaPlacaCategorias", (payload || []).map((m) => m.categoria_material));
        lista("nuevaPlacaTipos", (payload || []).map((m) => m.tipo_material));
      }

      function decir(texto, clase) {
        if (!aviso) return;
        aviso.textContent = texto || "";
        aviso.className = "small mt-2 " + (clase || "");
      }

      function cerrar() {
        panel.classList.add("d-none");
        decir("", "");
      }

      function mostrar() {
        panel.classList.remove("d-none");
        sugerencias();
        // Arranca con lo que ya esté filtrado arriba: casi siempre es lo que
        // la persona estuvo buscando antes de no encontrarlo.
        if (catSel && catSel.value && campos.categoria_material && !campos.categoria_material.value) {
          campos.categoria_material.value = catSel.value;
        }
        if (tipoSel && tipoSel.value && campos.tipo_material && !campos.tipo_material.value) {
          campos.tipo_material.value = tipoSel.value;
        }
        // Y con lo que dijera la cotización, que es más concreto todavía. Así
        // sólo queda por teclear el tamaño de la placa, que la cotización no
        // dice: da la medida de la pieza, no la de la lámina de donde sale.
        if (propuesta) {
          if (campos.categoria_material && propuesta.categoria && !campos.categoria_material.value) {
            campos.categoria_material.value = propuesta.categoria;
          }
          if (campos.nombre && propuesta.nombre && !campos.nombre.value) {
            campos.nombre.value = propuesta.nombre;
          }
          if (campos.espesor_mm && propuesta.espesor && !campos.espesor_mm.value) {
            campos.espesor_mm.value = propuesta.espesor;
          }
        }
        const primeroVacio = ["nombre", "espesor_mm", "largo_cm", "ancho_cm"]
          .map((k) => campos[k])
          .find((e) => e && !String(e.value || "").trim());
        (primeroVacio || campos.nombre).focus();
      }

      // Lo que la cotización sabe de la placa, para no volver a teclearlo.
      // «Acero A36» se parte en categoría y nombre por la primera palabra, que
      // es como lo escribe Corta.mx.
      proponerPlaca = function (renglon) {
        const texto = String((renglon && renglon.material) || "").trim();
        const trozos = texto.split(/\s+/);
        propuesta = {
          categoria: trozos.length > 1 ? trozos[0] : "",
          nombre: trozos.length > 1 ? trozos.slice(1).join(" ") : texto,
          espesor: renglon && renglon.espesor_mm ? String(renglon.espesor_mm) : "",
        };
        return mostrar;
      };

      abrir.addEventListener("click", () => {
        if (panel.classList.contains("d-none")) mostrar();
        else cerrar();
      });

      if (cancelar) cancelar.addEventListener("click", cerrar);

      function csrf() {
        const el = document.querySelector("input[name=csrfmiddlewaretoken]");
        return el ? el.value : "";
      }

      guardar.addEventListener("click", async () => {
        const datos = new FormData();
        Object.keys(campos).forEach((k) => {
          datos.append(k, campos[k] ? String(campos[k].value || "").trim() : "");
        });
        datos.append("activo", "on");

        guardar.disabled = true;
        decir("Guardando...", "text-muted");
        let res;
        try {
          res = await fetch(url, {
            method: "POST",
            headers: {"X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest"},
            body: datos,
          });
        } catch (e) {
          guardar.disabled = false;
          decir("No se pudo conectar con el servidor. Reintenta.", "text-danger");
          return;
        }
        guardar.disabled = false;

        let cuerpo = null;
        try { cuerpo = await res.json(); } catch (e) { cuerpo = null; }
        if (!res.ok || !cuerpo || !cuerpo.ok) {
          const errores = (cuerpo && cuerpo.errores) || {};
          const partes = Object.keys(errores).map((k) => {
            const msgs = errores[k];
            return (Array.isArray(msgs) ? msgs.join(" ") : String(msgs));
          });
          decir(partes.length ? partes.join(" ") : ((cuerpo && cuerpo.error) || "No se pudo guardar."), "text-danger");
          return;
        }

        const m = cuerpo.material;
        const id = String(m.id);
        // Sustituir y no acumular: si se le da a Guardar dos veces con los
        // mismos datos, el servidor devuelve la misma placa y aquí no debe
        // quedar duplicada en la lista.
        const yaEstaba = payload.findIndex((x) => String(x.id) === id);
        if (yaEstaba >= 0) payload[yaEstaba] = m;
        else payload.push(m);
        matMap[id] = m;
        optTextById[id] = cuerpo.etiqueta;

        if (catSel) {
          const cat = catSel.value;
          fillSelect(catSel, uniqSorted((payload || []).map((x) => x.categoria_material)), "Todas");
          catSel.value = cat;
        }
        if (tipoSel) {
          const tipo = tipoSel.value;
          fillSelect(tipoSel, tiposForCategoria(catSel ? catSel.value : ""), "Todos");
          tipoSel.value = tipo;
        }
        rebuildMaterialOptions();
        if (matSel) {
          matSel.value = id;
          // La placa nueva puede quedar fuera del filtro de arriba, y entonces
          // asignar el valor no surte efecto. Se limpia el filtro y se rehace.
          if (String(matSel.value) !== id) {
            if (catSel) catSel.value = "";
            if (tipoSel) {
              fillSelect(tipoSel, tiposForCategoria(""), "Todos");
              tipoSel.value = "";
            }
            rebuildMaterialOptions();
            matSel.value = id;
          }
        }
        syncCategoryTypeFromSelectedMaterial();
        calc();
        cerrar();
      });
    })();

    if (input && frame) {
      input.addEventListener("change", function () {
        const f = input.files && input.files[0];
        if (!f) return;
        const prev = frame.dataset.objectUrl;
        if (prev) URL.revokeObjectURL(prev);
        const url = URL.createObjectURL(f);
        frame.dataset.objectUrl = url;
        frame.src = url + "#view=FitH";
        if (openTab) {
          openTab.href = url;
          openTab.style.display = "";
        }
      });
    }

    /* Leer la cotización de Corta.mx y llenar el pedido con ella.
     *
     * El PDF ya se adjuntaba: lo único nuevo es que, al elegirlo, se manda a
     * leer. Nada se guarda desde aquí, sólo se escriben los campos de arriba,
     * que es lo que permite que una lectura equivocada no pase de un susto.
     */
    (function () {
      const panel = document.getElementById("cotizacionPanel");
      const resumen = document.getElementById("cotizacionResumen");
      const avisos = document.getElementById("cotizacionAvisos");
      const lista = document.getElementById("cotizacionRenglones");
      const cerrar = document.getElementById("cotizacionCerrar");
      const url = cfg.urlLeerCotizacion;
      if (!panel || !lista || !input || !url) return;

      const folioInput = document.getElementById(cfg.campoFolio);
      const piezaInput = document.getElementById(cfg.campoPieza);
      const descInput = document.getElementById(cfg.campoDescripcion);

      if (cerrar) cerrar.addEventListener("click", () => panel.classList.add("d-none"));

      function csrf() {
        const el = document.querySelector("input[name=csrfmiddlewaretoken]");
        return el ? el.value : "";
      }

      function llenar(folio, r) {
        if (folioInput && folio && !folioInput.value.trim()) folioInput.value = folio;
        if (piezaInput && r.parte) piezaInput.value = r.parte;
        if (anchoInput && r.ancho_mm) anchoInput.value = r.ancho_mm;
        if (altoInput && r.largo_mm) altoInput.value = r.largo_mm;
        if (qtyInput && r.cantidad) qtyInput.value = r.cantidad;
        if (descInput && !descInput.value.trim() && (r.procesos || []).length) {
          descInput.value = r.procesos.join(", ");
        }
        if (matSel && r.placa_id) {
          matSel.value = String(r.placa_id);
          if (String(matSel.value) !== String(r.placa_id)) {
            // La placa puede estar fuera del filtro de categoría o tipo.
            if (catSel) catSel.value = "";
            if (tipoSel) {
              fillSelect(tipoSel, tiposForCategoria(""), "Todos");
              tipoSel.value = "";
            }
            rebuildMaterialOptions();
            matSel.value = String(r.placa_id);
          }
          syncCategoryTypeFromSelectedMaterial();
        }
        calc();
        const arriba = folioInput || piezaInput;
        if (arriba) {
          arriba.scrollIntoView({behavior: "smooth", block: "center"});
          arriba.focus({preventScroll: true});
        }
      }

      function pintar(datos) {
        panel.classList.remove("d-none");
        lista.innerHTML = "";

        const partes = [];
        if (datos.folio) partes.push("Folio " + datos.folio);
        if (datos.caducidad) partes.push("caduca el " + datos.caducidad);
        const n = (datos.renglones || []).length;
        partes.push(n === 1 ? "1 pieza" : n + " piezas");
        if (resumen) resumen.textContent = partes.join(" · ");

        if (avisos) {
          avisos.textContent = (datos.avisos || []).join(" ");
          avisos.classList.toggle("d-none", !(datos.avisos || []).length);
        }

        if (n > 1 && resumen) {
          // Cada pieza de la cotización es un pedido aparte: no se puede
          // llenar el formulario con varias a la vez, y fingir que sí sería
          // perder las demás sin decirlo.
          resumen.textContent += " · una por pedido";
        }

        (datos.renglones || []).forEach((r) => {
          const fila = document.createElement("div");
          fila.className = "d-flex justify-content-between align-items-center gap-2 border rounded p-2 flex-wrap";

          const texto = document.createElement("div");
          const titulo = document.createElement("div");
          titulo.className = "fw-semibold";
          titulo.textContent = r.parte || "(sin nombre)";
          const detalle = document.createElement("div");
          detalle.className = "text-muted small";
          const trozos = [];
          if (r.largo_mm && r.ancho_mm) trozos.push(r.largo_mm + " x " + r.ancho_mm + " mm");
          if (r.material) trozos.push(r.material);
          if (r.espesor_mm) trozos.push(r.espesor_mm + " mm de espesor");
          if (r.cantidad) trozos.push(r.cantidad + " pzas");
          detalle.textContent = trozos.join(" · ");
          texto.appendChild(titulo);
          texto.appendChild(detalle);

          const placa = document.createElement("div");
          placa.className = "small " + (r.placa_id ? "text-success" : "text-warning-emphasis");
          if (r.placa_id) {
            placa.textContent = "Placa: " + r.placa_nombre;
          } else {
            // La cotización no dice el tamaño de la lámina -da la medida de la
            // pieza, no la de donde sale-, así que la placa no se puede crear
            // sola. Lo que sí se puede es dejar escrito todo lo demás.
            placa.append("Esta placa no está en el catálogo. ");
            const alta = document.createElement("button");
            alta.type = "button";
            alta.className = "btn btn-link btn-sm p-0 align-baseline";
            alta.textContent = "Darla de alta con estos datos";
            alta.addEventListener("click", () => {
              if (proponerPlaca) proponerPlaca(r)();
            });
            placa.appendChild(alta);
          }
          texto.appendChild(placa);

          const boton = document.createElement("button");
          boton.type = "button";
          boton.className = "btn btn-argon text-white";
          boton.textContent = "Llenar con esta";
          boton.addEventListener("click", () => llenar(datos.folio, r));

          fila.appendChild(texto);
          fila.appendChild(boton);
          lista.appendChild(fila);
        });

        if (!n) {
          const vacio = document.createElement("div");
          vacio.className = "text-muted small";
          vacio.textContent = "No se pudo leer ninguna pieza de este PDF. Captúralo a mano.";
          lista.appendChild(vacio);
        }
      }

      input.addEventListener("change", async function () {
        const f = input.files && input.files[0];
        if (!f) return;
        const datos = new FormData();
        datos.append("archivo", f);
        panel.classList.remove("d-none");
        if (resumen) resumen.textContent = "Leyendo el PDF...";
        if (lista) lista.innerHTML = "";
        if (avisos) avisos.textContent = "";

        let res;
        try {
          res = await fetch(url, {
            method: "POST",
            headers: {"X-CSRFToken": csrf(), "X-Requested-With": "XMLHttpRequest"},
            body: datos,
          });
        } catch (e) {
          if (resumen) resumen.textContent = "No se pudo leer el PDF. Captúralo a mano.";
          return;
        }
        let cuerpo = null;
        try { cuerpo = await res.json(); } catch (e) { cuerpo = null; }
        if (!cuerpo) {
          if (resumen) resumen.textContent = "No se pudo leer el PDF. Captúralo a mano.";
          return;
        }
        pintar(cuerpo);
      });
    })();
  })();
