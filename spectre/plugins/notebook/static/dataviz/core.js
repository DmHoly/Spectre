/* DataViz - le registre des composants de visualisation du cahier de données.

   Un composant = un fichier de ce dossier qui appelle DataViz.register({...}) :
     key          identifiant stable (enregistré dans le cahier : ne pas le renommer)
     label        nom affiché ; description : une phrase ; icon : un <svg> (facultatif)
     accepts(ds, options?)   ce jeu de données (et ces réglages, s'il y en a) lui convient-il ?
     options(ds)  les réglages proposés : [{key, label, type, ...}] - types : "column" (filter :
                  "number" | "vector" | "text" | "any", optional), "columns", "select" (choices),
                  "number" (min, max, step), "checkbox", "text"
     defaults(ds) les réglages de départ
     render(el, ds, options)  dessine dans `el` (HTML/SVG statique : il part tel quel dans le rapport)
   Un jeu de données (ds) = un instantané (spectre.core.datasets) : {hook, hook_title, wafers,
   source, columns, rows, ...} - les colonnes telles que PRISM les renvoie.

   Les préréglages par type de données (DataViz.addPresets("eqe", [...])) proposent, à l'ajout
   d'une vue, les façons habituelles de regarder ce type (voir presets.js).

   Tout le reste ici : lire les colonnes, échelles et axes SVG, couleurs (tokens --viz-* de
   kernel.css), statistiques, infobulles, formulaire de réglages. */

const DataViz = (() => {
  const registry = new Map();
  const presets = {};

  // -- registre ---------------------------------------------------------------------------------
  function register(component) {
    registry.set(component.key, component);
  }
  function get(key) {
    return registry.get(key) || null;
  }
  function safe(fn, fallback = false) {
    try {
      return fn();
    } catch (err) {
      return fallback;
    }
  }
  function componentsFor(ds) {
    return [...registry.values()].filter((c) => safe(() => c.accepts(ds)));
  }
  function addPresets(hook, list) {
    presets[hook] = (presets[hook] || []).concat(list);
  }
  function presetsFor(ds) {
    return (presets[ds.hook] || []).filter((p) => {
      const c = get(p.component);
      return c && safe(() => c.accepts(ds, p.options || {}));
    });
  }

  // -- colonnes ---------------------------------------------------------------------------------
  function colIndex(ds, name) {
    return ds.columns.indexOf(name);
  }
  function has(ds, name) {
    return Boolean(name) && colIndex(ds, name) >= 0;
  }
  function find(ds, candidates) {
    const lower = ds.columns.map((c) => c.toLowerCase());
    for (const name of candidates) {
      const i = lower.indexOf(String(name).toLowerCase());
      if (i >= 0) return ds.columns[i];
    }
    return null;
  }
  function values(ds, name) {
    const i = colIndex(ds, name);
    return i < 0 ? [] : ds.rows.map((r) => r[i]);
  }
  const kindCache = new WeakMap();
  function kind(ds, name) {
    let cache = kindCache.get(ds);
    if (!cache) kindCache.set(ds, (cache = {}));
    if (cache[name]) return cache[name];
    const sample = values(ds, name).filter((v) => v !== null && v !== undefined).slice(0, 60);
    let k = "empty";
    if (sample.length) {
      if (sample.every((v) => Array.isArray(v))) k = "vector";
      else if (sample.every((v) => typeof v === "number")) k = "number";
      else if (sample.every((v) => typeof v === "boolean")) k = "bool";
      else k = "text";
    }
    return (cache[name] = k);
  }
  function columnsOfKind(ds, wanted) {
    return ds.columns.filter((c) => wanted === "any" || kind(ds, c) === wanted);
  }
  function waferColumn(ds) {
    return find(ds, ["wafername", "wafer_name", "Wafer name", "wafer", "lasermark"]);
  }
  function xyColumns(ds) {
    return [find(ds, ["X", "x_position", "x", "die_x"]), find(ds, ["Y", "y_position", "y", "die_y"])];
  }
  // lignes regroupées par plaque, dans l'ordre d'apparition : Map(plaque -> [index de ligne])
  function byWafer(ds) {
    const wc = waferColumn(ds);
    const groups = new Map();
    const w = wc ? colIndex(ds, wc) : -1;
    ds.rows.forEach((row, i) => {
      const key = w >= 0 ? String(row[w] ?? "—") : "Toutes";
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(i);
    });
    return groups;
  }
  function cell(ds, rowIndex, name) {
    const i = colIndex(ds, name);
    return i < 0 ? undefined : ds.rows[rowIndex][i];
  }

  // -- couleurs (tokens de kernel.css) -------------------------------------------------------------
  const tokenCache = {};
  function token(name) {
    if (!(name in tokenCache)) tokenCache[name] = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return tokenCache[name];
  }
  function categorical(i) {
    return token(`--viz-${(i % 8) + 1}`);
  }
  function hexToRgb(hex) {
    const h = hex.replace("#", "");
    const n = parseInt(h.length === 3 ? h.replace(/./g, "$&$&") : h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  // t entre 0 et 1 -> couleur de la rampe séquentielle (--viz-seq-1 .. 5)
  function sequential(t) {
    if (t === null || t === undefined || Number.isNaN(t)) return token("--viz-empty");
    const stops = [1, 2, 3, 4, 5].map((i) => hexToRgb(token(`--viz-seq-${i}`)));
    const x = Math.max(0, Math.min(1, t)) * (stops.length - 1);
    const i = Math.min(Math.floor(x), stops.length - 2);
    const f = x - i;
    const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }
  function gradientCss() {
    return `linear-gradient(90deg, ${[1, 2, 3, 4, 5].map((i) => token(`--viz-seq-${i}`)).join(", ")})`;
  }

  // -- échelles et axes ---------------------------------------------------------------------------
  function extent(list) {
    let min = Infinity;
    let max = -Infinity;
    for (const v of list) {
      if (typeof v !== "number" || !Number.isFinite(v)) continue;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    return min <= max ? [min, max] : [0, 1];
  }
  function niceStep(span, count) {
    const raw = span / Math.max(count, 1);
    const power = 10 ** Math.floor(Math.log10(raw));
    const n = raw / power;
    return (n >= 5 ? 10 : n >= 2 ? 5 : n >= 1 ? 2 : 1) * power;
  }
  function scale([d0, d1], [r0, r1], { log = false } = {}) {
    if (log) {
      const l0 = Math.log10(Math.max(d0, 1e-12));
      const l1 = Math.log10(Math.max(d1, 1e-12));
      const span = l1 - l0 || 1;
      const f = (v) => (v > 0 ? r0 + ((Math.log10(v) - l0) / span) * (r1 - r0) : NaN);
      f.ticks = () => {
        const out = [];
        for (let p = Math.floor(l0); p <= Math.ceil(l1); p++) if (p >= l0 - 1e-9 && p <= l1 + 1e-9) out.push(10 ** p);
        return out.length >= 2 ? out : [d0, d1];
      };
      f.domain = [d0, d1];
      return f;
    }
    let lo = d0;
    let hi = d1;
    if (lo === hi) {
      lo -= Math.abs(lo) * 0.1 || 1;
      hi += Math.abs(hi) * 0.1 || 1;
    }
    const f = (v) => r0 + ((v - lo) / (hi - lo)) * (r1 - r0);
    f.ticks = (count = 5) => {
      const step = niceStep(hi - lo, count);
      const out = [];
      for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Number(v.toPrecision(12)));
      return out;
    };
    f.domain = [lo, hi];
    return f;
  }
  // un domaine un peu élargi, pour que les points ne collent pas aux bords
  function padded([a, b], log = false) {
    if (log) return [a / 1.3, b * 1.3];
    const pad = (b - a) * 0.06 || Math.abs(a) * 0.1 || 1;
    return [a - pad, b + pad];
  }
  const fmt = (v) => (typeof formatParamValue === "function" ? formatParamValue(v) : String(v));
  function esc(v) {
    return typeof escapeHtml === "function" ? escapeHtml(v) : String(v);
  }

  // Axes + grille d'un graphique 2D (chaîne SVG). frame : {left, top, width, height}
  function axes(frame, sx, sy, { xLabel = "", yLabel = "", xTicks = null, yTicks = null } = {}) {
    const { left, top, width, height } = frame;
    const bottom = top + height;
    const xs = xTicks || sx.ticks(6);
    const ys = yTicks || sy.ticks(5);
    let out = `<g class="viz-axes">`;
    ys.forEach((v) => {
      const y = sy(v);
      if (!Number.isFinite(y)) return;
      out += `<line class="viz-grid" x1="${left}" x2="${left + width}" y1="${y}" y2="${y}"/><text class="viz-tick" x="${left - 6}" y="${y + 3.5}" text-anchor="end">${esc(fmt(v))}</text>`;
    });
    xs.forEach((v) => {
      const x = sx(v);
      if (!Number.isFinite(x)) return;
      out += `<line class="viz-grid viz-grid--x" x1="${x}" x2="${x}" y1="${top}" y2="${bottom}"/><text class="viz-tick" x="${x}" y="${bottom + 15}" text-anchor="middle">${esc(fmt(v))}</text>`;
    });
    out += `<line class="viz-axis" x1="${left}" x2="${left + width}" y1="${bottom}" y2="${bottom}"/><line class="viz-axis" x1="${left}" x2="${left}" y1="${top}" y2="${bottom}"/>`;
    if (xLabel) out += `<text class="viz-label" x="${left + width / 2}" y="${bottom + 34}" text-anchor="middle">${esc(xLabel)}</text>`;
    if (yLabel) out += `<text class="viz-label" transform="translate(${left - 46},${top + height / 2}) rotate(-90)" text-anchor="middle">${esc(yLabel)}</text>`;
    return `${out}</g>`;
  }
  function svgOpen(width, height, label) {
    return `<svg class="viz-svg" viewBox="0 0 ${width} ${height}" width="100%" role="img" aria-label="${esc(label || "")}" preserveAspectRatio="xMidYMid meet">`;
  }
  // Légende des plaques (couleur -> nom), HTML
  function legendHtml(names) {
    return `<div class="viz-legend">${names
      .map((n, i) => `<span class="viz-legend__item"><span class="viz-legend__swatch" style="background:${categorical(i)}"></span>${esc(n)}</span>`)
      .join("")}</div>`;
  }

  // -- statistiques -------------------------------------------------------------------------------
  function quantile(sorted, q) {
    if (!sorted.length) return NaN;
    const pos = (sorted.length - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.ceil(pos);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
  }
  function stats(list) {
    const v = list.filter((x) => typeof x === "number" && Number.isFinite(x)).sort((a, b) => a - b);
    if (!v.length) return { n: 0 };
    const mean = v.reduce((a, b) => a + b, 0) / v.length;
    let std = Math.sqrt(v.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(v.length - 1, 1));
    if (std < Math.abs(mean) * 1e-9) std = 0; // une valeur constante, pas du bruit d'arrondi
    return { n: v.length, min: v[0], q1: quantile(v, 0.25), median: quantile(v, 0.5), q3: quantile(v, 0.75), max: v[v.length - 1], mean, std };
  }

  // -- infobulle partagée : tout élément [data-tip] d'un graphique --------------------------------
  let tip = null;
  function wireTooltips(root) {
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "viz-tip";
      tip.hidden = true;
      document.body.appendChild(tip);
    }
    root.addEventListener("mousemove", (event) => {
      const target = event.target.closest("[data-tip]");
      if (!target || !root.contains(target)) {
        tip.hidden = true;
        return;
      }
      tip.textContent = target.getAttribute("data-tip");
      tip.hidden = false;
      const x = Math.min(event.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
      tip.style.left = `${x}px`;
      tip.style.top = `${event.clientY + 14}px`;
    });
    root.addEventListener("mouseleave", () => {
      if (tip) tip.hidden = true;
    });
  }

  // -- formulaire de réglages d'un composant ------------------------------------------------------
  function optionsFormHtml(ds, fields, values, prefix) {
    return fields
      .map((f) => {
        const id = `${prefix}-${f.key}`;
        const value = values[f.key];
        let input = "";
        if (f.type === "column") {
          const cols = columnsOfKind(ds, f.filter || "any");
          input = `<select class="field" id="${id}" data-opt="${f.key}">${f.optional ? `<option value="">${esc(f.noneLabel || "— aucune —")}</option>` : ""}${cols
            .map((c) => `<option value="${esc(c)}"${c === value ? " selected" : ""}>${esc(c)}</option>`)
            .join("")}</select>`;
        } else if (f.type === "columns") {
          const cols = columnsOfKind(ds, f.filter || "any");
          const chosen = new Set(value || []);
          input = `<div class="viz-checks" id="${id}" data-opt="${f.key}" data-type="columns">${cols
            .map((c) => `<label class="viz-check"><input type="checkbox" value="${esc(c)}"${chosen.has(c) ? " checked" : ""}> ${esc(c)}</label>`)
            .join("")}</div>`;
        } else if (f.type === "select") {
          input = `<select class="field" id="${id}" data-opt="${f.key}">${f.choices
            .map((c) => `<option value="${esc(c.value)}"${String(c.value) === String(value) ? " selected" : ""}>${esc(c.label)}</option>`)
            .join("")}</select>`;
        } else if (f.type === "number") {
          input = `<input class="field" type="number" id="${id}" data-opt="${f.key}" data-type="number" value="${esc(value ?? "")}"${f.min != null ? ` min="${f.min}"` : ""}${f.max != null ? ` max="${f.max}"` : ""} step="${f.step || "any"}">`;
        } else if (f.type === "checkbox") {
          return `<label class="viz-check viz-opt viz-opt--check"><input type="checkbox" id="${id}" data-opt="${f.key}" data-type="checkbox"${value ? " checked" : ""}> ${esc(f.label)}</label>`;
        } else {
          input = `<input class="field" id="${id}" data-opt="${f.key}" value="${esc(value ?? "")}">`;
        }
        return `<div class="viz-opt${f.type === "columns" ? " viz-opt--wide" : ""}"><label for="${id}">${esc(f.label)}</label>${input}</div>`;
      })
      .join("");
  }
  function readOptions(root) {
    const out = {};
    root.querySelectorAll("[data-opt]").forEach((el) => {
      const key = el.dataset.opt;
      if (el.dataset.type === "columns") out[key] = [...el.querySelectorAll("input:checked")].map((i) => i.value);
      else if (el.dataset.type === "checkbox") out[key] = el.checked;
      else if (el.dataset.type === "number") out[key] = el.value === "" ? null : Number(el.value);
      else out[key] = el.value;
    });
    return out;
  }

  // -- rendu ------------------------------------------------------------------------------------------
  function render(el, ds, componentKey, options = {}) {
    const component = get(componentKey);
    if (!component) {
      el.innerHTML = `<div class="viz-empty">Composant de visualisation « ${esc(componentKey)} » indisponible sur cette version de Spectre.</div>`;
      return;
    }
    try {
      const merged = { ...safe(() => component.defaults(ds), {}), ...options };
      el.innerHTML = "";
      component.render(el, ds, merged);
      if (!el.dataset.tips) {
        wireTooltips(el);
        el.dataset.tips = "1";
      }
    } catch (err) {
      console.error(err);
      el.innerHTML = `<div class="viz-empty">Impossible d'afficher cette vue : ${esc(err.message || String(err))}</div>`;
    }
  }

  return {
    register,
    get,
    componentsFor,
    addPresets,
    presetsFor,
    colIndex,
    has,
    find,
    values,
    kind,
    columnsOfKind,
    waferColumn,
    xyColumns,
    byWafer,
    cell,
    token,
    categorical,
    sequential,
    gradientCss,
    extent,
    scale,
    padded,
    fmt,
    esc,
    axes,
    svgOpen,
    legendHtml,
    stats,
    optionsFormHtml,
    readOptions,
    render,
  };
})();
