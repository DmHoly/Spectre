/* Le bloc « Données » d'une analyse de plaques (global `AnalysisData`) : les plaques face à la référence.

   - Les KPI comparés (choisis ici, gardés dans l'analyse : PATCH /api/analyses/{id} {kpis}) : une boîte à moustaches
     par plaque, dans l'ordre de l'analyse (kpiBoxplotSvg, plugin kpi_tracking), et un tableau - n, médiane, écart à
     la médiane de la référence (absolu et en %), jour de mesure. GET /api/analyses/{id}/kpis. Quand on a dit quel
     sens est un progrès (« plus haut = mieux »), l'écart le dit en mots, pas seulement en couleur.
   - La fiche data de chaque plaque (plugin wafer_data, s'il est actif : GET /api/wafers/{key}/data), bloc par bloc,
     rapprochée d'une plaque à l'autre : les valeurs en un tableau (une colonne par plaque, écart à la référence),
     les courbes médianes superposées, les cartographies côte à côte sur une même échelle, les histogrammes côte à
     côte. Les blocs sont ceux que les projets corporate des plaques ont configurés (/fiche-data).

   Une couleur par plaque, la même partout (AnalysisData.colorOf) : la référence en navy, les autres dans l'ordre de
   la palette des graphiques.

     AnalysisData.mount(host, {analysisId, getAnalysis, onAnalysis}) -> {reload()} */

const AnalysisData = (() => {
  const SERIES = ["var(--viz-1)", "var(--viz-2)", "var(--viz-3)", "var(--viz-4)", "var(--viz-5)", "var(--viz-6)", "var(--viz-7)", "var(--viz-8)"];
  const colorOf = (index) => (index === 0 ? "var(--navy)" : SERIES[(index - 1) % SERIES.length]);
  const BETTER = { high: "plus haut = mieux", low: "plus bas = mieux" };
  const fmt = (v) => (typeof kpiFormatNumber === "function" ? kpiFormatNumber(v) : String(v));
  const icon = (path) => `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
  const REFRESH = '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>';
  const dot = (index) => `<span class="ma-dot" style="background:${colorOf(index)}" aria-hidden="true"></span>`;

  // L'écart à la référence en signe et en chiffres (« ▲ +12,3 (+4,5 %) ») et, quand un sens de progrès est choisi,
  // son verdict (better / worse) - null sans écart calculable.
  function deltaText(delta, better) {
    if (!delta) return null;
    const { absolute, relative } = delta;
    if (!absolute) return { text: "= réf.", verdict: "" };
    const up = absolute > 0;
    const sign = up ? "+" : "−";
    const pct = relative === null || relative === undefined ? "" : ` (${sign}${fmt(Math.abs(relative) * 100)} %)`;
    return { text: `${up ? "▲" : "▼"} ${sign}${fmt(Math.abs(absolute))}${pct}`, verdict: better ? ((better === "high") === up ? "better" : "worse") : "" };
  }

  // Le même écart à l'écran : le verdict dit en mots - la couleur ne fait que doubler le mot.
  function deltaHtml(delta, better) {
    const d = deltaText(delta, better);
    if (!d) return `<span class="help" style="margin:0;">—</span>`;
    const word = d.verdict === "better" ? " · mieux" : d.verdict === "worse" ? " · moins bien" : "";
    return `<span class="ma-delta${d.verdict ? ` ma-delta--${d.verdict}` : ""}">${d.text}${word}</span>`;
  }

  // -- les courbes superposées : une médiane par plaque, l'enveloppe 10-90 % de la référence derrière --------------

  function curvesSvg(series, unit) {
    const W = 560, H = 250, L = 52, R = 14, T = 14, B = 34;
    const first = series[0].data;
    const lx = !!first.log_x;
    const ly = !!first.log_y && series.every((s) => Math.min(...s.data.median) > 0);
    const tx = (v) => (lx ? Math.log10(v) : v);
    const ty = (v) => (ly ? Math.log10(Math.max(v, 1e-30)) : v);
    const xs = series.flatMap((s) => [s.data.x[0], s.data.x[s.data.x.length - 1]]).map(tx);
    const ref = series.find((s) => s.index === 0);
    const ysAll = series.flatMap((s) => s.data.median).concat(ref ? [...ref.data.low, ...ref.data.high] : []).map(ty);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ysAll), y1 = Math.max(...ysAll);
    const X = (v) => L + ((tx(v) - x0) / (x1 - x0 || 1)) * (W - L - R);
    const Y = (v) => H - B - ((ty(v) - y0) / (y1 - y0 || 1)) * (H - T - B);
    const path = (d, ys) => d.x.map((x, i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join("");
    const steps = (lo, hi, n) => Array.from({ length: n + 1 }, (_, i) => lo + ((hi - lo) * i) / n);
    const xticks = steps(x0, x1, 4)
      .map((v) => (lx ? 10 ** v : v))
      .map((v) => `<text class="wd-tick" x="${X(v).toFixed(1)}" y="${H - B + 16}" text-anchor="middle">${WaferDataCharts.fmt(v)}</text>`)
      .join("");
    const yticks = steps(y0, y1, 3)
      .map((v) => {
        const real = ly ? 10 ** v : v;
        return `<line class="wd-grid" x1="${L}" x2="${W - R}" y1="${Y(real).toFixed(1)}" y2="${Y(real).toFixed(1)}"></line><text class="wd-tick" x="${L - 6}" y="${(Y(real) + 4).toFixed(1)}" text-anchor="end">${WaferDataCharts.fmt(real)}</text>`;
      })
      .join("");
    const band = ref
      ? `<path class="wd-band" d="${path(ref.data, ref.data.high)}${ref.data.x
          .slice()
          .reverse()
          .map((x, i) => `L${X(x).toFixed(1)},${Y(ref.data.low[ref.data.x.length - 1 - i]).toFixed(1)}`)
          .join("")}Z"><title>Référence : 10 - 90 % de ses courbes</title></path>`
      : "";
    // la référence en dernier : par-dessus les autres
    const lines = [...series]
      .sort((a, b) => (a.index === 0) - (b.index === 0))
      .map((s) => `<path class="ma-curve${s.index === 0 ? " ma-curve--ref" : ""}" d="${path(s.data, s.data.median)}" style="stroke:${colorOf(s.index)}"><title>${escapeHtml(s.wafer)} : médiane de ${s.data.n} courbe${s.data.n > 1 ? "s" : ""}</title></path>`)
      .join("");
    return `<svg class="wd-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Courbes médianes de ${series.length} plaques superposées, l'enveloppe 10-90 % de la référence derrière">
      ${yticks}<line class="wd-axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"></line>${band}${lines}${xticks}
      ${unit ? `<text class="wd-tick" x="${L}" y="10">${escapeHtml(unit)}</text>` : ""}
    </svg>`;
  }

  function mount(host, { analysisId, getAnalysis, onAnalysis }) {
    const state = { choices: null, editing: false, kpis: null, sheets: null };
    host.innerHTML = `
      <div class="ma-section-head">
        <h2 class="section-title" id="data-title">Données - face à la référence</h2>
        <span class="help js-data-meta" style="margin:0;"></span>
        <span class="ma-data__actions">
          <button type="button" class="btn btn-line js-kpi-edit" aria-expanded="false">Choisir les KPI</button>
          <button type="button" class="btn btn-line js-data-refresh" title="Relire les bases de caractérisation pour ces plaques">${icon(REFRESH)}Rafraîchir</button>
        </span>
      </div>
      <div class="ma-kpi-editor js-kpi-editor" hidden></div>
      <div class="js-kpis"></div>
      <div class="js-sheets"></div>`;
    host.setAttribute("aria-labelledby", "data-title");
    const editor = host.querySelector(".js-kpi-editor");
    const kpisEl = host.querySelector(".js-kpis");
    const sheetsEl = host.querySelector(".js-sheets");
    const editBtn = host.querySelector(".js-kpi-edit");

    // -- choisir les KPI ---------------------------------------------------------------------------

    async function saveKpis(list) {
      const analysis = await metaAnalysisApi.update(analysisId, { kpis: list.map(({ hook, column, label, filters, better }) => ({ hook, column, label: label || "", filters: filters || [], better: better || null })) });
      onAnalysis(analysis);
      state.choices = null;
      await renderEditor();
      loadKpis();
    }

    async function renderEditor() {
      if (!state.editing) {
        editor.hidden = true;
        return;
      }
      editor.hidden = false;
      const analysis = getAnalysis();
      if (!state.choices) {
        editor.innerHTML = `<div class="skeleton" style="height:80px;"></div>`;
        try {
          state.choices = await metaAnalysisApi.kpiChoices(analysisId);
        } catch (err) {
          editor.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
          return;
        }
      }
      const { catalog, suggested } = state.choices;
      const byHook = new Map();
      catalog.forEach((k) => (byHook.get(k.hook_title) || byHook.set(k.hook_title, []).get(k.hook_title)).push(k));
      editor.innerHTML = `
        <div class="ma-kpi-editor__chosen">
          <div class="ma-field__label">KPI comparés</div>
          ${
            analysis.kpis.length
              ? `<ul class="ma-kpi-list">${analysis.kpis
                  .map(
                    (k, i) => `<li class="ma-kpi-list__item">
                      <span class="ma-kpi-list__title">${escapeHtml(k.title)}</span>
                      <label class="visually-hidden" for="kpi-better-${i}">Sens d'un progrès pour ${escapeHtml(k.title)}</label>
                      <select class="field ma-kpi-list__better" id="kpi-better-${i}" data-index="${i}">
                        <option value="">sans sens de progrès</option>
                        <option value="high"${k.better === "high" ? " selected" : ""}>plus haut = mieux</option>
                        <option value="low"${k.better === "low" ? " selected" : ""}>plus bas = mieux</option>
                      </select>
                      <button type="button" class="ma-chip__btn ma-chip__remove js-kpi-remove" data-index="${i}" aria-label="Ne plus comparer ${escapeHtml(k.title)}" title="Ne plus comparer"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>
                    </li>`
                  )
                  .join("")}</ul>`
              : `<p class="help" style="margin:0;">Aucun KPI encore : prenez ceux que suivent les projets de ces plaques, ou choisissez dans le catalogue.</p>`
          }
        </div>
        ${
          suggested.length
            ? `<div class="ma-kpi-editor__suggested"><div class="ma-field__label">Suivis par les projets de ces plaques</div><div class="ma-chips">${suggested
                .map((s, i) => `<button type="button" class="btn btn-line ma-kpi-suggest js-kpi-suggest" data-index="${i}" title="Projet ${escapeHtml(s.area.name)}">+ ${escapeHtml(s.title)}</button>`)
                .join("")}</div></div>`
            : ""
        }
        <form class="ma-kpi-editor__add js-kpi-add">
          <label class="ma-field">
            <span class="ma-field__label">Ajouter du catalogue PRISM</span>
            <select class="field" name="kpi" required>
              <option value="">Choisir une colonne de KPI…</option>
              ${[...byHook.entries()]
                .map(([title, list]) => `<optgroup label="${escapeHtml(title)}">${list.map((k) => `<option value="${escapeHtml(k.key)}">${escapeHtml(k.column)}${k.unit ? ` (${escapeHtml(k.unit)})` : ""}</option>`).join("")}</optgroup>`)
                .join("")}
            </select>
          </label>
          <select class="field" name="better" aria-label="Sens d'un progrès">
            <option value="">sans sens de progrès</option>
            <option value="high">plus haut = mieux</option>
            <option value="low">plus bas = mieux</option>
          </select>
          <button type="submit" class="btn btn-primary">Ajouter</button>
        </form>
        <div class="error js-kpi-error" role="alert" hidden></div>`;
    }

    function editorError(err) {
      const box = editor.querySelector(".js-kpi-error");
      if (!box) return;
      box.textContent = err ? err.message || String(err) : "";
      box.hidden = !err;
    }

    editBtn.addEventListener("click", () => {
      state.editing = !state.editing;
      editBtn.setAttribute("aria-expanded", String(state.editing));
      editBtn.textContent = state.editing ? "Fermer le choix des KPI" : "Choisir les KPI";
      renderEditor();
    });
    editor.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button || button.type === "submit") return;
      const list = [...getAnalysis().kpis];
      if (button.classList.contains("js-kpi-remove")) list.splice(Number(button.dataset.index), 1);
      else if (button.classList.contains("js-kpi-suggest")) list.push(state.choices.suggested[Number(button.dataset.index)]);
      else return;
      saveKpis(list).catch(editorError);
    });
    editor.addEventListener("change", (event) => {
      const select = event.target.closest(".ma-kpi-list__better");
      if (!select) return;
      const list = getAnalysis().kpis.map((k) => ({ ...k }));
      list[Number(select.dataset.index)].better = select.value || null;
      saveKpis(list).catch(editorError);
    });
    editor.addEventListener("submit", (event) => {
      event.preventDefault();
      const form = event.target;
      const entry = state.choices.catalog.find((k) => k.key === form.elements.kpi.value);
      if (!entry) return;
      saveKpis([...getAnalysis().kpis, { hook: entry.hook, column: entry.column, better: form.elements.better.value || null }]).catch(editorError);
    });

    // -- les KPI : boîtes et écarts -----------------------------------------------------------------

    function kpiHtml(kpi) {
      const head = `<header class="ma-kpi__head">
          <h3 class="ma-kpi__title">${escapeHtml(kpi.title)}</h3>
          <span class="ma-kpi__source">${escapeHtml(kpi.hook_title)}${kpi.unit ? ` · ${escapeHtml(kpi.unit)}` : ""}</span>
          ${kpi.better ? `<span class="ma-kpi__better">${BETTER[kpi.better]}</span>` : ""}
        </header>`;
      if (kpi.status !== "ok") return `<article class="card ma-kpi">${head}<p class="wd-state wd-state--error">${escapeHtml(kpi.message)}</p></article>`;
      const groups = kpi.groups.map((g, i) => ({ ...g, studies: [], index: i }));
      const svg = kpiBoxplotSvg(groups, { colorOf: (g) => colorOf(g.index), label: `${kpi.title} : une boîte par plaque, la référence d'abord` });
      const rows = kpi.groups
        .map(
          (g, i) => `<tr${i === 0 ? ` class="is-ref"` : ""}>
            <th scope="row">${dot(i)}<span class="mono">${escapeHtml(g.wafer)}</span>${i === 0 ? ` <span class="ma-chip__ref">Réf.</span>` : ""}</th>
            <td class="mono">${g.stats ? g.stats.n : "—"}</td>
            <td class="mono">${g.stats ? fmt(g.stats.median) : "aucune mesure"}</td>
            <td>${i === 0 ? `<span class="help" style="margin:0;">référence</span>` : deltaHtml(g.delta, kpi.better)}</td>
            <td class="mono">${g.date ? `${escapeHtml(g.date)}${g.dates > 1 ? ` <span class="help" style="margin:0;">(${g.dates} dates)</span>` : ""}` : "—"}</td>
          </tr>`
        )
        .join("");
      return `<article class="card ma-kpi">${head}
        ${svg ? `<div class="ma-kpi__plot">${svg}</div>` : `<p class="wd-state">Aucune de ces plaques n'a de mesure de ce KPI.</p>`}
        <div class="ma-kpi__table-wrap"><table class="ma-kpi__table">
          <thead><tr><th scope="col">Plaque</th><th scope="col">n</th><th scope="col">Médiane</th><th scope="col">Écart à la réf.</th><th scope="col">Mesure du</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </article>`;
    }

    async function loadKpis({ refresh = false } = {}) {
      const analysis = getAnalysis();
      if (!analysis.kpis.length) {
        kpisEl.innerHTML = `<div class="ma-empty-data"><p>Aucun KPI comparé. « Choisir les KPI » : ceux que suivent les projets de ces plaques (EQE max, PL…), ou n'importe quelle colonne de KPI de PRISM. Chaque KPI donne une boîte à moustaches par plaque et l'écart de sa médiane à la référence.</p></div>`;
        return;
      }
      kpisEl.innerHTML = analysis.kpis.map(() => `<div class="card skeleton" style="height:320px;margin-bottom:12px;"></div>`).join("");
      try {
        state.kpis = await metaAnalysisApi.kpis(analysisId, { refresh });
        kpisEl.innerHTML = `<div class="ma-kpis">${state.kpis.kpis.map(kpiHtml).join("")}</div>`;
        host.querySelector(".js-data-meta").textContent = state.kpis.source === "demo" ? "Données de démonstration" : "";
      } catch (err) {
        kpisEl.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
      }
    }

    // -- la fiche data de chaque plaque, rapprochée bloc par bloc ------------------------------------

    function gatherBlocks(wafers, sheets) {
      const blocks = new Map();
      sheets.forEach((sheet, i) => {
        (sheet && !sheet.error ? sheet.areas : []).forEach((area) =>
          area.blocks.forEach((block) => {
            if (!blocks.has(block.id)) blocks.set(block.id, { block, area: area.area, perWafer: wafers.map(() => null) });
            blocks.get(block.id).perWafer[i] = block;
          })
        );
      });
      return [...blocks.values()];
    }

    function valuesHtml(entries, wafers) {
      if (!entries.length) return "";
      const head = wafers.map((w, i) => `<th scope="col">${dot(i)}<span class="mono">${escapeHtml(w.lasermark)}</span>${i === 0 ? ` <span class="ma-chip__ref">Réf.</span>` : ""}</th>`).join("");
      const rows = entries
        .map(({ block, perWafer }) => {
          const ref = perWafer[0] && perWafer[0].status === "ok" ? perWafer[0].data.value : null;
          const better = block.config.better === "high" || block.config.better === "low" ? block.config.better : null;
          const cells = perWafer
            .map((b, i) => {
              if (!b) return `<td class="help">hors de son projet</td>`;
              if (b.status !== "ok") return `<td class="help">${b.status === "error" ? "erreur" : "pas de mesure"}</td>`;
              const v = b.data.value;
              const delta = i > 0 && ref !== null && v !== null ? { absolute: v - ref, relative: ref ? (v - ref) / Math.abs(ref) : null } : null;
              return `<td><span class="mono">${WaferDataCharts.fmt(v)}</span>${i > 0 ? `<br>${deltaHtml(delta, better)}` : ""}</td>`;
            })
            .join("");
          return `<tr><th scope="row">${escapeHtml(block.title)}${block.unit ? ` <span class="help" style="margin:0;">${escapeHtml(block.unit)}</span>` : ""}</th>${cells}</tr>`;
        })
        .join("");
      return `<section class="card ma-sheet"><div class="wd-chart__head"><span class="wd-chart__title">Valeurs de la fiche data</span><span class="wd-chart__kind">face à la référence</span></div>
        <div class="ma-kpi__table-wrap"><table class="ma-kpi__table ma-values"><thead><tr><th scope="col">Valeur</th>${head}</tr></thead><tbody>${rows}</tbody></table></div></section>`;
    }

    function legendHtml(wafers, present) {
      return `<p class="ma-legend">${wafers
        .map((w, i) => (present[i] ? `<span>${dot(i)}<span class="mono">${escapeHtml(w.lasermark)}</span>${i === 0 ? " (réf.)" : ""}</span>` : ""))
        .join("")}</p>`;
    }

    function chartEntryHtml({ block, perWafer }, wafers) {
      const ok = perWafer.map((b) => b && b.status === "ok" && b.data);
      const missing = wafers.filter((w, i) => !ok[i]).map((w) => w.lasermark);
      const missingNote = missing.length ? `<p class="help" style="margin:6px 0 0;">Sans ce bloc ou sans mesure : ${missing.map((m) => `<span class="mono">${escapeHtml(m)}</span>`).join(", ")}.</p>` : "";
      let figure = "";
      if (!ok.some(Boolean)) figure = `<p class="wd-state">Aucune de ces plaques n'a de mesure pour ce bloc.</p>`;
      else if (block.kind === "curve") {
        const series = perWafer.map((b, i) => (ok[i] ? { index: i, wafer: wafers[i].lasermark, data: b.data } : null)).filter(Boolean);
        figure = `${curvesSvg(series, block.unit)}${legendHtml(wafers, ok)}<p class="wd-chart__caption">Une médiane par plaque ; derrière, l'enveloppe 10 - 90 % des courbes de la référence.</p>`;
      } else if (block.kind === "wafermap") {
        const scales = perWafer.map((b, i) => (ok[i] ? WaferDataCharts.mapScale(b.data) : null)).filter(Boolean);
        const lo = Math.min(...scales.map((s) => s.lo));
        const hi = Math.max(...scales.map((s) => s.hi));
        figure = `<div class="ma-small-multiples">${perWafer
          .map((b, i) => (ok[i] ? `<figure class="ma-multiple">${WaferDataCharts.wafermap(b.data, block.unit, { lo, hi, size: 180 })}<figcaption>${dot(i)}<span class="mono">${escapeHtml(wafers[i].lasermark)}</span> · méd. ${WaferDataCharts.fmt(b.data.median)}</figcaption></figure>` : ""))
          .join("")}</div><p class="wd-chart__caption">Une même échelle pour toutes les cartes, de ${WaferDataCharts.fmt(lo)} à ${WaferDataCharts.fmt(hi)}${block.unit ? " " + escapeHtml(block.unit) : ""}.</p>`;
      } else if (block.kind === "histogram") {
        figure = `<div class="ma-small-multiples">${perWafer
          .map((b, i) => (ok[i] ? `<figure class="ma-multiple ma-multiple--wide">${WaferDataCharts.histogram(b.data, block.unit)}<figcaption>${dot(i)}<span class="mono">${escapeHtml(wafers[i].lasermark)}</span> · méd. ${WaferDataCharts.fmt(b.data.median)}</figcaption></figure>` : ""))
          .join("")}</div><p class="wd-chart__caption">Chaque histogramme a sa propre échelle.</p>`;
      }
      return `<figure class="card ma-sheet wd-chart--${block.kind}">
        <figcaption class="wd-chart__head"><span class="wd-chart__title">${escapeHtml(block.title)}</span><span class="wd-chart__kind">${escapeHtml(block.kind_label)}</span></figcaption>
        <div class="ma-figure">${figure}</div>${missingNote}
        <p class="wd-source">${escapeHtml(block.hook_title)} · projet ${escapeHtml(block.areaName)}</p>
      </figure>`;
    }

    async function loadSheets({ refresh = false } = {}) {
      if (!pluginEnabled("wafer_data") || typeof waferDataApi === "undefined") {
        sheetsEl.innerHTML = "";
        return;
      }
      const wafers = getAnalysis().wafers;
      sheetsEl.innerHTML = `<h3 class="ma-subtitle">Fiche data des plaques</h3><div class="card skeleton" style="height:220px;"></div>`;
      const sheets = await Promise.all(wafers.map((w) => waferDataApi.sheet(w.lasermark, { refresh }).catch((err) => ({ error: err }))));
      const entries = gatherBlocks(wafers, sheets).map((e) => ({ ...e, block: { ...e.block, areaName: e.area.name } }));
      const values = entries.filter((e) => e.block.kind === "value");
      const charts = entries.filter((e) => ["curve", "wafermap", "histogram"].includes(e.block.kind));
      const noSheet = wafers.filter((w, i) => !sheets[i] || sheets[i].error || !sheets[i].areas.length).map((w) => w.lasermark);
      sheetsEl.innerHTML = `<h3 class="ma-subtitle">Fiche data des plaques</h3>
        ${
          entries.length
            ? `${valuesHtml(values, wafers)}<div class="ma-sheets">${charts.map((e) => chartEntryHtml(e, wafers)).join("")}</div>`
            : `<div class="ma-empty-data"><p>Les projets de ces plaques n'ont pas encore choisi les données de leurs fiches (valeurs, courbes, cartographies) : un manager les configure dans « Fiche data » du menu Data.</p></div>`
        }
        ${noSheet.length ? `<p class="help">Sans fiche data (aucun µprojet rangé dans un projet corporate ne les suit) : ${noSheet.map((m) => `<span class="mono">${escapeHtml(m)}</span>`).join(", ")}.</p>` : ""}`;
    }

    const refreshBtn = host.querySelector(".js-data-refresh");
    async function reload({ refresh = false } = {}) {
      refreshBtn.disabled = true;
      try {
        await Promise.all([loadKpis({ refresh }), loadSheets({ refresh })]);
      } finally {
        refreshBtn.disabled = false;
      }
    }
    refreshBtn.addEventListener("click", () => reload({ refresh: true }));

    // Ce que le bloc montre, pour le rapport (report-html.js) : les KPI (dessin, tableau), ce qui bouge pour chaque
    // plaque (par clé : [{title, text, verdict}]) et les dessins de la fiche data tels qu'ils sont rendus.
    function snapshot() {
      const wafers = getAnalysis().wafers;
      const moves = Object.fromEntries(wafers.map((w) => [w.key, []]));
      const kpis = (state.kpis ? state.kpis.kpis : []).map((kpi) => {
        const source = `${kpi.hook_title}${kpi.unit ? ` · ${kpi.unit}` : ""}`;
        if (kpi.status !== "ok") return { title: kpi.title, source, better: kpi.better, status: kpi.status, message: kpi.message, svg: "", rows: [] };
        const groups = kpi.groups.map((g, i) => ({ ...g, studies: [], index: i }));
        const rows = kpi.groups.map((g, i) => {
          const d = i === 0 ? null : deltaText(g.delta, kpi.better);
          if (i > 0 && d && moves[g.key]) moves[g.key].push({ title: kpi.title, text: d.text, verdict: d.verdict });
          return {
            lasermark: g.wafer,
            color: colorOf(i),
            isRef: i === 0,
            n: g.stats ? String(g.stats.n) : "—",
            median: g.stats ? fmt(g.stats.median) : "aucune mesure",
            delta: i === 0 ? "référence" : d ? d.text : "—",
            verdict: d ? d.verdict : "",
            date: g.date || "—",
          };
        });
        return { title: kpi.title, source, better: kpi.better, status: "ok", message: "", svg: kpiBoxplotSvg(groups, { colorOf: (g) => colorOf(g.index), label: kpi.title }), rows };
      });
      const sheets = [...sheetsEl.querySelectorAll(".ma-sheet")].map((el) => ({
        title: el.querySelector(".wd-chart__title")?.textContent || "",
        kind: el.querySelector(".wd-chart__kind")?.textContent || "",
        figure: (el.querySelector(".ma-figure") || el.querySelector(".ma-kpi__table-wrap"))?.innerHTML || "",
      }));
      return { kpis, sheets, moves };
    }

    return {
      snapshot,
      reload: () => {
        state.choices = null;
        renderEditor();
        return reload();
      },
    };
  }

  return { mount, colorOf };
})();
