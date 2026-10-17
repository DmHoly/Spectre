/* Le bloc « Données » d'une analyse de plaques (global `AnalysisData`) : les plaques face à la référence.

   - Les KPI comparés (choisis ici, gardés dans l'analyse : PATCH /api/analyses/{id} {kpis}) : n'importe quelle
     colonne scalaire d'un type de données PRISM par plaque - ses colonnes de KPI d'abord, puis les autres. Une boîte
     à moustaches par plaque, dans l'ordre de l'analyse (kpiBoxplotSvg, plugin kpi_tracking), et un tableau - n,
     médiane, écart à la médiane de la référence (absolu et en %), jour de mesure. GET /api/analyses/{id}/kpis.
     Quand on a dit quel sens est un progrès (« plus haut = mieux »), l'écart le dit en mots, pas seulement en couleur.
   - Les blocs libres (gardés dans l'analyse : PATCH {blocks}) : les blocs de la fiche data (valeur, histogramme,
     boîte, nuage, cartographie, courbes, images), choisis ici sur n'importe quel type de données PRISM avec le même
     formulaire (wafer_data/block-form.js) et calculés sur chaque plaque : GET /api/analyses/{id}/blocks. Il faut le
     plugin wafer_data.
   - La fiche data de chaque plaque (plugin wafer_data, s'il est actif : GET /api/wafers/{key}/data), bloc par bloc :
     les blocs que les projets corporate des plaques ont configurés (/fiche-data).

   Un bloc, libre ou de fiche, se rapproche d'une plaque à l'autre : les valeurs en un tableau (une colonne par
   plaque, écart à la référence), les courbes médianes superposées, une boîte par plaque (ou, groupées, les boîtes
   de chaque plaque côte à côte), les cartographies côte à côte sur une même échelle, les histogrammes et les nuages
   côte à côte, les images en une rangée par plaque (la visionneuse en grand).

   Une couleur par plaque, la même partout (AnalysisData.colorOf) : la référence en navy, les autres dans l'ordre de
   la palette des graphiques.

     AnalysisData.mount(host, {analysisId, getAnalysis, onAnalysis}) -> {reload(), snapshot()} */

const AnalysisData = (() => {
  const SERIES = ["var(--viz-1)", "var(--viz-2)", "var(--viz-3)", "var(--viz-4)", "var(--viz-5)", "var(--viz-6)", "var(--viz-7)", "var(--viz-8)"];
  const colorOf = (index) => (index === 0 ? "var(--navy)" : SERIES[(index - 1) % SERIES.length]);
  const BETTER = { high: "plus haut = mieux", low: "plus bas = mieux" };
  const CHARTS = ["curve", "boxplot", "wafermap", "histogram", "scatter", "images"];
  const THUMBS = 6; // les images montrées par plaque ; la visionneuse a les autres
  const fmt = (v) => (typeof kpiFormatNumber === "function" ? kpiFormatNumber(v) : String(v));
  const icon = (path) => `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
  const REFRESH = '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>';
  const PLUS = '<path d="M12 5v14M5 12h14"/>';
  const dot = (index) => `<span class="ma-dot" style="background:${colorOf(index)}" aria-hidden="true"></span>`;
  const waferName = (w, i) => `${dot(i)}<span class="mono">${escapeHtml(w.lasermark)}</span>`;

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

  const gap = (value, ref) => (ref === null || ref === undefined || value === null || value === undefined ? null : { absolute: value - ref, relative: ref ? (value - ref) / Math.abs(ref) : null });

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
    const state = { choices: null, editing: false, kpis: null, catalog: null, free: null, form: null, entries: new Map() };
    const withBlocks = pluginEnabled("wafer_data") && typeof waferDataApi !== "undefined" && typeof WaferBlockForm !== "undefined";
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
      ${
        withBlocks
          ? `<section class="ma-free" aria-labelledby="free-title">
              <div class="ma-free__head">
                <h3 class="ma-subtitle" id="free-title">Blocs libres</h3>
                <button type="button" class="btn btn-line js-free-add" aria-expanded="false">${icon(PLUS)}Ajouter un bloc</button>
              </div>
              <p class="help ma-free__intro">N'importe quelle donnée de PRISM, montrée plaque contre plaque : une valeur, des courbes (EQE en fonction de V…), une cartographie, un nuage, des images… - comme dans la fiche data d'un projet, mais choisie pour cette analyse.</p>
              <div class="ma-free__list js-free-list"></div>
              <div class="card ma-free__form js-free-form-card" hidden>
                <h4 class="section-title js-free-form-title">Ajouter un bloc</h4>
                <div class="js-free-form"></div>
                <div class="error js-free-error" role="alert" hidden></div>
              </div>
              <div class="js-free-figures"></div>
            </section>`
          : ""
      }
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

    // les colonnes du catalogue, par type de données : ses colonnes de KPI, puis les autres
    function catalogOptions(catalog) {
      const byHook = new Map();
      catalog.forEach((k) => {
        if (!byHook.has(k.hook_title)) byHook.set(k.hook_title, { kpi: [], raw: [] });
        byHook.get(k.hook_title)[k.kpi ? "kpi" : "raw"].push(k);
      });
      const option = (k) => `<option value="${escapeHtml(k.key)}">${escapeHtml(k.column)}${k.unit ? ` (${escapeHtml(k.unit)})` : ""}</option>`;
      return [...byHook.entries()]
        .map(
          ([title, g]) =>
            `${g.kpi.length ? `<optgroup label="${escapeHtml(title)} · KPI">${g.kpi.map(option).join("")}</optgroup>` : ""}${
              g.raw.length ? `<optgroup label="${escapeHtml(title)} · autres colonnes">${g.raw.map(option).join("")}</optgroup>` : ""
            }`
        )
        .join("");
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
              : `<p class="help" style="margin:0;">Aucun KPI encore : prenez ceux que suivent les projets de ces plaques, ou n'importe quelle colonne de PRISM.</p>`
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
            <span class="ma-field__label">Ajouter une donnée PRISM <span class="help" style="display:inline;margin:0;font-weight:400;">(une colonne qui donne un nombre par dispositif)</span></span>
            <input type="search" class="field js-kpi-filter" placeholder="Filtrer : EQE, CIE, Lambda, FWHM…" aria-label="Filtrer les colonnes" autocomplete="off">
            <select class="field" name="kpi" required>
              <option value="">Choisir une colonne…</option>
              ${catalogOptions(catalog)}
            </select>
          </label>
          <select class="field" name="better" aria-label="Sens d'un progrès">
            <option value="">sans sens de progrès</option>
            <option value="high">plus haut = mieux</option>
            <option value="low">plus bas = mieux</option>
          </select>
          <button type="submit" class="btn btn-primary">Ajouter</button>
        </form>
        <p class="help" style="margin:0;">Une courbe, une carte, des images ? Un <strong>bloc libre</strong>, plus bas.</p>
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
    // filtrer la liste des colonnes : un type de données sans colonne qui convient se replie
    editor.addEventListener("input", (event) => {
      if (!event.target.classList.contains("js-kpi-filter")) return;
      const words = event.target.value.toLowerCase().split(/\s+/).filter(Boolean);
      const select = editor.querySelector('select[name="kpi"]');
      select.querySelectorAll("optgroup").forEach((group) => {
        let any = false;
        group.querySelectorAll("option").forEach((option) => {
          const text = `${group.label} ${option.textContent}`.toLowerCase();
          option.hidden = !words.every((w) => text.includes(w));
          any = any || !option.hidden;
        });
        group.hidden = !any;
      });
      const first = select.querySelector("optgroup:not([hidden]) option:not([hidden])");
      if (first && (!select.value || select.selectedOptions[0].hidden)) select.value = first.value;
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
        kpisEl.innerHTML = `<div class="ma-empty-data"><p>Aucun KPI comparé. « Choisir les KPI » : ceux que suivent les projets de ces plaques (EQE max, PL…), ou n'importe quelle colonne de PRISM qui donne un nombre par dispositif. Chaque KPI donne une boîte à moustaches par plaque et l'écart de sa médiane à la référence.</p></div>`;
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

    // -- un bloc rapproché d'une plaque à l'autre (libre ou de fiche) --------------------------------
    //    entry : {id, block: {kind, kind_label, title, unit, units, config, hook_title, origin}, perWafer: [bloc
    //    calculé sur la plaque {status, message, data} | null (hors de son projet)]}

    function valuesHtml(entries, wafers, title) {
      if (!entries.length) return "";
      const head = wafers.map((w, i) => `<th scope="col">${waferName(w, i)}${i === 0 ? ` <span class="ma-chip__ref">Réf.</span>` : ""}</th>`).join("");
      const rows = entries
        .map(({ block, perWafer }) => {
          const ref = perWafer[0] && perWafer[0].status === "ok" ? perWafer[0].data.value : null;
          const better = block.config.better === "high" || block.config.better === "low" ? block.config.better : null;
          const cells = perWafer
            .map((b, i) => {
              if (!b) return `<td class="help">hors de son projet</td>`;
              if (b.status !== "ok") return `<td class="help">${b.status === "error" ? "erreur" : "pas de mesure"}</td>`;
              const v = b.data.value;
              return `<td><span class="mono">${WaferDataCharts.fmt(v)}</span>${i > 0 ? `<br>${deltaHtml(gap(v, ref), better)}` : ""}</td>`;
            })
            .join("");
          return `<tr><th scope="row">${escapeHtml(block.title)}${block.unit ? ` <span class="help" style="margin:0;">${escapeHtml(block.unit)}</span>` : ""}</th>${cells}</tr>`;
        })
        .join("");
      return `<section class="card ma-sheet"><div class="wd-chart__head"><span class="wd-chart__title">${escapeHtml(title)}</span><span class="wd-chart__kind">face à la référence</span></div>
        <div class="ma-kpi__table-wrap"><table class="ma-kpi__table ma-values"><thead><tr><th scope="col">Valeur</th>${head}</tr></thead><tbody>${rows}</tbody></table></div></section>`;
    }

    function legendHtml(wafers, present) {
      return `<p class="ma-legend">${wafers
        .map((w, i) => (present[i] ? `<span>${waferName(w, i)}${i === 0 ? " (réf.)" : ""}</span>` : ""))
        .join("")}</p>`;
    }

    const multiple = (i, wafers, body, note = "", wide = true) =>
      `<figure class="ma-multiple${wide ? " ma-multiple--wide" : ""}">${body}<figcaption>${waferName(wafers[i], i)}${note ? ` · ${note}` : ""}</figcaption></figure>`;

    // une boîte par plaque (comme un KPI) quand le bloc ne groupe pas ; sinon les boîtes de chaque plaque côte à côte
    function boxplotFigure(block, perWafer, ok, wafers) {
      const c = block.config;
      const single = !c.group_by;
      if (!single) {
        return `<div class="ma-small-multiples">${perWafer
          .map((b, i) => (ok[i] ? multiple(i, wafers, WaferDataCharts.boxplot(b.data, block.unit, { color: c.color, yLabel: WaferDataCharts.label(c.column, block.unit) }), `${b.data.n} valeurs`) : ""))
          .join("")}</div><p class="wd-chart__caption">Une boîte par ${escapeHtml(c.group_by)}, pour chaque plaque ; chacune a sa propre échelle.</p>`;
      }
      const groups = perWafer.map((b, i) => {
        const box = ok[i] && b.data.boxes && b.data.boxes[0];
        return { wafer: wafers[i].lasermark, key: wafers[i].key, index: i, studies: [], stats: box || null, outliers: box ? box.outliers : [], date: ok[i] ? b.data.date : null };
      });
      const ref = groups[0].stats ? groups[0].stats.median : null;
      const better = c.better || null;
      const rows = groups
        .map(
          (g, i) => `<tr${i === 0 ? ` class="is-ref"` : ""}><th scope="row">${waferName(wafers[i], i)}${i === 0 ? ` <span class="ma-chip__ref">Réf.</span>` : ""}</th>
            <td class="mono">${g.stats ? g.stats.n : "—"}</td><td class="mono">${g.stats ? fmt(g.stats.median) : "aucune mesure"}</td>
            <td>${i === 0 ? `<span class="help" style="margin:0;">référence</span>` : g.stats ? deltaHtml(gap(g.stats.median, ref), better) : "—"}</td></tr>`
        )
        .join("");
      return `<div class="ma-kpi__plot">${kpiBoxplotSvg(groups, { colorOf: (g) => colorOf(g.index), label: `${block.title} : une boîte par plaque, la référence d'abord` })}</div>
        <div class="ma-kpi__table-wrap"><table class="ma-kpi__table"><thead><tr><th scope="col">Plaque</th><th scope="col">n</th><th scope="col">Médiane</th><th scope="col">Écart à la réf.</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    }

    function imagesFigure(entry, perWafer, ok, wafers) {
      return `<div class="ma-image-rows">${perWafer
        .map((b, i) => {
          if (!ok[i]) return "";
          const images = b.data.images || [];
          const thumbs = images
            .slice(0, THUMBS)
            .map((img, n) => {
              const caption = Object.values(img.meta || {}).join(" · ") || img.name;
              return `<button type="button" class="wd-image" data-ma-image="${n}" data-entry="${escapeHtml(entry.id)}" data-wafer="${i}" title="${escapeHtml(img.name)}" aria-label="Agrandir ${escapeHtml(img.name)} (${escapeHtml(wafers[i].lasermark)})">
                <img src="${escapeHtml(img.url)}" alt="" loading="lazy"><span class="wd-image__name">${escapeHtml(caption)}</span></button>`;
            })
            .join("");
          const more = images.length > THUMBS ? `<button type="button" class="btn btn-line ma-image-row__more" data-ma-image="0" data-entry="${escapeHtml(entry.id)}" data-wafer="${i}">Voir les ${images.length}</button>` : "";
          return `<div class="ma-image-row"><div class="ma-image-row__who">${waferName(wafers[i], i)} <span class="help" style="margin:0;">${b.data.total} image${b.data.total > 1 ? "s" : ""}</span>${more}</div><div class="wd-images__grid ma-image-row__thumbs">${thumbs}</div></div>`;
        })
        .join("")}</div>`;
    }

    function chartEntryHtml(entry, wafers) {
      const { block, perWafer } = entry;
      const c = block.config;
      const units = block.units || {};
      const ok = perWafer.map((b) => b && b.status === "ok" && b.data);
      const missing = wafers.filter((w, i) => !ok[i]).map((w) => w.lasermark);
      const errors = [...new Set(perWafer.filter((b) => b && b.status === "error" && b.message).map((b) => b.message))];
      const missingNote = missing.length ? `<p class="help" style="margin:6px 0 0;">${block.origin === "free" ? "Sans mesure" : "Sans ce bloc ou sans mesure"} : ${missing.map((m) => `<span class="mono">${escapeHtml(m)}</span>`).join(", ")}.</p>` : "";
      let figure = "";
      if (!ok.some(Boolean)) figure = errors.length ? `<p class="wd-state wd-state--error">${escapeHtml(errors[0])}</p>` : `<p class="wd-state">Aucune de ces plaques n'a de mesure pour ce bloc.</p>`;
      else if (block.kind === "curve") {
        const series = perWafer.map((b, i) => (ok[i] ? { index: i, wafer: wafers[i].lasermark, data: b.data } : null)).filter(Boolean);
        figure = `${curvesSvg(series, block.unit)}${legendHtml(wafers, ok)}<p class="wd-chart__caption">${escapeHtml(c.y)} en fonction de ${escapeHtml(c.x)} : une médiane par plaque ; derrière, l'enveloppe 10 - 90 % des courbes de la référence.</p>`;
      } else if (block.kind === "wafermap") {
        const scales = perWafer.map((b, i) => (ok[i] ? WaferDataCharts.mapScale(b.data) : null)).filter(Boolean);
        const lo = Math.min(...scales.map((s) => s.lo));
        const hi = Math.max(...scales.map((s) => s.hi));
        figure = `<div class="ma-small-multiples">${perWafer
          .map((b, i) => (ok[i] ? multiple(i, wafers, WaferDataCharts.wafermap(b.data, block.unit, { lo, hi, size: 180 }), `méd. ${WaferDataCharts.fmt(b.data.median)}`, false) : ""))
          .join("")}</div><p class="wd-chart__caption">Une même échelle pour toutes les cartes, de ${WaferDataCharts.fmt(lo)} à ${WaferDataCharts.fmt(hi)}${block.unit ? " " + escapeHtml(block.unit) : ""}.</p>`;
      } else if (block.kind === "histogram") {
        figure = `<div class="ma-small-multiples">${perWafer
          .map((b, i) => (ok[i] ? multiple(i, wafers, WaferDataCharts.histogram(b.data, block.unit, { color: c.color, xLabel: WaferDataCharts.label(c.column, block.unit) }), `méd. ${WaferDataCharts.fmt(b.data.median)}`) : ""))
          .join("")}</div><p class="wd-chart__caption">Chaque histogramme a sa propre échelle.</p>`;
      } else if (block.kind === "scatter") {
        figure = `<div class="ma-small-multiples">${perWafer
          .map((b, i) => (ok[i] ? multiple(i, wafers, WaferDataCharts.scatter(b.data, { color: c.color, xLabel: WaferDataCharts.label(c.x, units.x), yLabel: WaferDataCharts.label(c.y, units.y) }), `${b.data.n} points`) : ""))
          .join("")}</div><p class="wd-chart__caption">${escapeHtml(c.y)} en fonction de ${escapeHtml(c.x)}, un nuage par plaque.</p>`;
      } else if (block.kind === "boxplot") {
        figure = boxplotFigure(block, perWafer, ok, wafers);
      } else if (block.kind === "images") {
        figure = imagesFigure(entry, perWafer, ok, wafers);
      }
      const origin = block.origin === "free" ? "bloc libre de l'analyse" : `projet ${escapeHtml(block.areaName)}`;
      return `<figure class="card ma-sheet ma-sheet--${block.kind} wd-chart--${block.kind}">
        <figcaption class="wd-chart__head"><span class="wd-chart__title">${escapeHtml(block.title)}</span><span class="wd-chart__kind">${escapeHtml(block.kind_label)}</span></figcaption>
        <div class="ma-figure">${figure}</div>${missingNote}
        <p class="wd-source">${escapeHtml(block.hook_title || "Fichiers")} · ${origin}</p>
      </figure>`;
    }

    function entriesHtml(entries, wafers, valuesTitle) {
      entries.forEach((e) => state.entries.set(e.id, e));
      const values = entries.filter((e) => e.block.kind === "value");
      const charts = entries.filter((e) => CHARTS.includes(e.block.kind));
      return `${valuesHtml(values, wafers, valuesTitle)}<div class="ma-sheets">${charts.map((e) => chartEntryHtml(e, wafers)).join("")}</div>`;
    }

    // la visionneuse : les images d'une plaque pour un bloc
    host.addEventListener("click", (event) => {
      const button = event.target.closest("[data-ma-image]");
      if (!button || typeof WaferDataViewer === "undefined") return;
      const entry = state.entries.get(button.dataset.entry);
      const b = entry && entry.perWafer[Number(button.dataset.wafer)];
      if (!b || !b.data) return;
      const wafer = getAnalysis().wafers[Number(button.dataset.wafer)];
      WaferDataViewer.open({ title: `${entry.block.title} · ${wafer ? wafer.lasermark : ""}`, images: b.data.images, groups: b.data.groups || [], index: Number(button.dataset.maImage) });
    });

    // -- les blocs libres de l'analyse ---------------------------------------------------------------

    const free = withBlocks
      ? {
          list: host.querySelector(".js-free-list"),
          card: host.querySelector(".js-free-form-card"),
          formHost: host.querySelector(".js-free-form"),
          title: host.querySelector(".js-free-form-title"),
          error: host.querySelector(".js-free-error"),
          figures: host.querySelector(".js-free-figures"),
          add: host.querySelector(".js-free-add"),
        }
      : null;

    function freeError(err) {
      free.error.textContent = err ? err.message || String(err) : "";
      free.error.hidden = !err;
    }

    async function catalogOnce() {
      if (!state.catalog) state.catalog = await waferDataApi.freeCatalog();
      return state.catalog;
    }

    async function saveBlocks(list) {
      const analysis = await metaAnalysisApi.update(analysisId, { blocks: list.map(({ kind, hook, config, label }) => ({ kind, hook, config, label: label || "" })) });
      onAnalysis(analysis);
      renderFreeList();
      await loadFree();
    }

    const arrow = (d) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`;

    function renderFreeList() {
      const blocks = getAnalysis().blocks || [];
      if (!blocks.length) {
        free.list.innerHTML = "";
        return;
      }
      free.list.innerHTML = blocks
        .map(
          (b, i) => `<div class="wd-row ma-free__row">
            <span class="wd-row__kind">${escapeHtml(b.kind_label)}</span>
            <div style="min-width:0;"><div class="wd-row__name">${escapeHtml(b.title)}</div><div class="wd-row__meta">${state.catalog ? WaferBlockForm.describe(b, state.catalog) : ""}</div></div>
            <div class="wd-row__actions">
              <button type="button" class="btn btn-line wd-icon-btn" data-free-move="-1" data-index="${i}" aria-label="Monter ${escapeHtml(b.title)}" ${i === 0 ? "disabled" : ""}>${arrow("m6 15 6-6 6 6")}</button>
              <button type="button" class="btn btn-line wd-icon-btn" data-free-move="1" data-index="${i}" aria-label="Descendre ${escapeHtml(b.title)}" ${i === blocks.length - 1 ? "disabled" : ""}>${arrow("m6 9 6 6 6-6")}</button>
              <button type="button" class="btn btn-line" data-free-edit="${i}">Modifier</button>
              <button type="button" class="btn btn-line" data-free-remove="${i}">Retirer</button>
            </div>
          </div>`
        )
        .join("");
    }

    async function openForm(block = null) {
      freeError(null);
      free.card.hidden = false;
      free.add.setAttribute("aria-expanded", "true");
      if (!state.form) {
        free.formHost.innerHTML = `<div class="skeleton" style="height:120px;"></div>`;
        try {
          const catalog = await catalogOnce();
          free.formHost.innerHTML = "";
          state.form = WaferBlockForm.mount(free.formHost, {
            catalog,
            titleEl: free.title,
            canEditTypes: false,
            kindNotes: { value: "Un chiffre par plaque : médiane, moyenne, part des LED allumées… et son écart à la référence." },
            // les vraies colonnes se lisent sur la référence de l'analyse
            probe: (hook) => waferDataApi.probeFree(hook, getAnalysis().wafers[0].lasermark),
            titleOf: (index) => ((getAnalysis().blocks || [])[index] || {}).title || "",
            showError: freeError,
            clearError: () => freeError(null),
            onCancel: closeForm,
            async submit(chosen, editing) {
              const list = [...(getAnalysis().blocks || [])];
              if (editing !== null) list[editing] = chosen;
              else list.push(chosen);
              await saveBlocks(list);
              closeForm();
            },
          });
        } catch (err) {
          free.formHost.innerHTML = "";
          freeError(err);
          return;
        }
      }
      if (block) state.form.edit(block);
      else if (state.form.editing() !== null) state.form.reset();
      free.card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function closeForm() {
      free.card.hidden = true;
      free.add.setAttribute("aria-expanded", "false");
      if (state.form && state.form.editing() !== null) state.form.reset();
      free.add.focus();
    }

    if (free) {
      free.add.addEventListener("click", () => (free.card.hidden ? openForm() : closeForm()));
      free.list.addEventListener("click", async (event) => {
        const move = event.target.closest("[data-free-move]");
        const edit = event.target.closest("[data-free-edit]");
        const remove = event.target.closest("[data-free-remove]");
        const list = [...(getAnalysis().blocks || [])];
        try {
          if (move) {
            const at = Number(move.dataset.index);
            const to = at + Number(move.dataset.freeMove);
            [list[at], list[to]] = [list[to], list[at]];
            await saveBlocks(list);
            const again = free.list.querySelector(`[data-free-move="${move.dataset.freeMove}"][data-index="${to}"]`);
            if (again && !again.disabled) again.focus();
          } else if (edit) {
            const index = Number(edit.dataset.freeEdit);
            await openForm({ ...list[index], id: index });
          } else if (remove) {
            const index = Number(remove.dataset.freeRemove);
            if (!window.confirm(`Retirer le bloc « ${list[index].title} » de l'analyse ?`)) return;
            list.splice(index, 1);
            if (state.form && state.form.editing() !== null) closeForm();
            await saveBlocks(list);
          }
        } catch (err) {
          freeError(err);
          free.card.hidden = false;
        }
      });
    }

    async function loadFree({ refresh = false } = {}) {
      if (!free) return;
      const blocks = getAnalysis().blocks || [];
      if (blocks.length && !state.catalog) {
        try {
          await catalogOnce();
        } catch (err) {
          /* sans catalogue, la liste se passe de la ligne qui décrit chaque bloc */
        }
      }
      renderFreeList();
      if (!blocks.length) {
        state.free = null;
        free.figures.innerHTML = "";
        return;
      }
      free.figures.innerHTML = blocks.map(() => `<div class="card skeleton" style="height:220px;margin-top:12px;"></div>`).join("");
      try {
        state.free = await metaAnalysisApi.blocks(analysisId, { refresh });
        const wafers = getAnalysis().wafers;
        const entries = state.free.blocks.map((b) => ({ id: `free-${b.index}`, block: { ...b, origin: "free" }, perWafer: b.wafers }));
        free.figures.innerHTML = entriesHtml(entries, wafers, "Valeurs choisies");
      } catch (err) {
        free.figures.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
      }
    }

    // -- la fiche data de chaque plaque, rapprochée bloc par bloc ------------------------------------

    function gatherBlocks(wafers, sheets) {
      const blocks = new Map();
      sheets.forEach((sheet, i) => {
        (sheet && !sheet.error ? sheet.areas : []).forEach((area) =>
          area.blocks.forEach((block) => {
            if (!blocks.has(block.id)) blocks.set(block.id, { id: `sheet-${block.id}`, block: { ...block, areaName: area.area.name }, perWafer: wafers.map(() => null) });
            blocks.get(block.id).perWafer[i] = block;
          })
        );
      });
      return [...blocks.values()];
    }

    async function loadSheets({ refresh = false } = {}) {
      if (!pluginEnabled("wafer_data") || typeof waferDataApi === "undefined") {
        sheetsEl.innerHTML = "";
        return;
      }
      const wafers = getAnalysis().wafers;
      sheetsEl.innerHTML = `<h3 class="ma-subtitle">Fiche data des plaques</h3><div class="card skeleton" style="height:220px;"></div>`;
      const sheets = await Promise.all(wafers.map((w) => waferDataApi.sheet(w.lasermark, { refresh }).catch((err) => ({ error: err }))));
      const entries = gatherBlocks(wafers, sheets);
      const noSheet = wafers.filter((w, i) => !sheets[i] || sheets[i].error || !sheets[i].areas.length).map((w) => w.lasermark);
      sheetsEl.innerHTML = `<h3 class="ma-subtitle">Fiche data des plaques</h3>
        ${
          entries.length
            ? entriesHtml(entries, wafers, "Valeurs de la fiche data")
            : `<div class="ma-empty-data"><p>Les projets de ces plaques n'ont pas encore choisi les données de leurs fiches (valeurs, courbes, cartographies) : un manager les configure dans « Fiche data » du menu Data. D'ici, les blocs libres montrent n'importe quelle donnée.</p></div>`
        }
        ${noSheet.length ? `<p class="help">Sans fiche data (aucun µprojet rangé dans un projet corporate ne les suit) : ${noSheet.map((m) => `<span class="mono">${escapeHtml(m)}</span>`).join(", ")}.</p>` : ""}`;
    }

    const refreshBtn = host.querySelector(".js-data-refresh");
    async function reload({ refresh = false } = {}) {
      refreshBtn.disabled = true;
      try {
        await Promise.all([loadKpis({ refresh }), loadFree({ refresh }), loadSheets({ refresh })]);
      } finally {
        refreshBtn.disabled = false;
      }
    }
    refreshBtn.addEventListener("click", () => reload({ refresh: true }));

    // -- pour le rapport -------------------------------------------------------------------------------

    // Une image du serveur, réduite et gardée dans le document (le rapport s'ouvre hors ligne) - null si illisible.
    async function inlineImage(url, size = 360) {
      try {
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) return null;
        const bitmap = await createImageBitmap(await response.blob());
        const scale = Math.min(1, size / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(bitmap.width * scale));
        canvas.height = Math.max(1, Math.round(bitmap.height * scale));
        canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.82);
      } catch (err) {
        return null;
      }
    }

    // Les dessins d'une section tels qu'ils sont rendus ; les images y entrent réduites, les boutons en sortent.
    async function figuresOf(root) {
      return Promise.all(
        [...root.querySelectorAll(".ma-sheet")].map(async (el) => {
          const figure = (el.querySelector(".ma-figure") || el.querySelector(".ma-kpi__table-wrap")).cloneNode(true);
          figure.querySelectorAll(".ma-image-row__more").forEach((b) => b.remove());
          await Promise.all(
            [...figure.querySelectorAll("button.wd-image")].map(async (button) => {
              const img = button.querySelector("img");
              const src = img ? await inlineImage(img.getAttribute("src")) : null;
              const tile = document.createElement("span");
              tile.className = "wd-image";
              tile.innerHTML = src ? `<img src="${src}" alt="">${button.querySelector(".wd-image__name")?.outerHTML || ""}` : `<span class="wd-image__name">${escapeHtml(button.title)}</span>`;
              button.replaceWith(tile);
            })
          );
          return {
            title: el.querySelector(".wd-chart__title")?.textContent || "",
            kind: el.querySelector(".wd-chart__kind")?.textContent || "",
            figure: figure.innerHTML,
          };
        })
      );
    }

    // Ce que le bloc montre, pour le rapport (report-html.js) : les KPI (dessin, tableau), ce qui bouge pour chaque
    // plaque (par clé : [{title, text, verdict}]), les blocs libres et ceux de la fiche data tels qu'ils sont rendus.
    async function snapshot() {
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
      const [blocks, sheets] = await Promise.all([free ? figuresOf(free.figures) : [], figuresOf(sheetsEl)]);
      return { kpis, blocks, sheets, moves };
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
