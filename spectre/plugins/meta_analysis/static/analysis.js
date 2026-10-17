/* Page /analyses/{id} : une analyse de plaques. La plaque de référence et celles qu'on lui compare, côte à côte -
   une colonne par plaque : la structure qu'elle a vue, ce qu'on sait d'elle (µprojet, statut, lot, FDL, runs) et
   son contexte (PlateContext, plugin wafers : les études qui la suivent et ses notes, qu'on écrit d'ici) -, puis
   le tableau du comparateur (la référence en base), les données face à la référence (analysis-data.js : KPI
   comparés, fiche data de chaque plaque) et la conclusion de l'analyse. Une couleur par plaque, la même partout
   (pastille des plaques, colonnes, graphiques).

   La structure d'une plaque est celle de la page de la plaque : la dernière étude de vos µprojets qui la suit
   (son dessin, ou sa première image), sinon la structure attachée à la plaque. Seules les plaques qu'une étude
   de vos µprojets suit entrent dans le tableau du comparateur (un jeton wafer: se lit dans une étude) ; les
   autres sont nommées au-dessus.

   Les passeports des plaques sont gardés pendant la visite : changer la référence ou l'ordre ne relit rien. */

(() => {
  const { analysis_id: analysisId } = routeParams("/analyses/{analysis_id}");
  const state = { analysis: null, user: null, plates: new Map(), structures: new Map(), comparison: null };
  const errorEl = document.getElementById("error");
  const columnsEl = document.getElementById("columns");
  const chipsEl = document.getElementById("chips");
  const input = document.getElementById("picker-input");
  const listbox = document.getElementById("picker-options");
  const conclusionForm = document.getElementById("conclusion-form");
  const conclusionEl = document.getElementById("conclusion");
  const EMPTY_COMPARISON = { baseline: 0, rows: [], groups: [], summary: {} };
  const MAX_WAFERS = 16; // meta_analysis.service.MAX_WAFERS

  function showError(err) {
    errorEl.textContent = err ? err.message || String(err) : "";
    errorEl.hidden = !err;
  }

  const plural = (n, word) => `${n} ${word}${n > 1 ? "s" : ""}`;
  const plateUrl = (lasermark) => `/plaques/${encodeURIComponent(lasermark)}`;

  // la dernière étude d'un de vos µprojets qui suit la plaque (celle dont elle montre la structure), ou null
  function latestStudy(plate) {
    return (plate && plate.occurrences.find((o) => o.experiment.member && o.experiment.version_id)) || null;
  }

  // -- l'en-tête ---------------------------------------------------------------------------------

  function renderHero() {
    const a = state.analysis;
    document.title = `${a.title} — Spectre`;
    // la barre du haut garde « / Analyses » : un long titre la ferait déborder ; il est dans le fil de la page
    document.getElementById("title-crumb").textContent = a.title;
    document.getElementById("title").textContent = a.title;
    const question = document.getElementById("question");
    question.textContent = a.question || "Aucune question écrite : « Modifier » pour dire ce qu'on cherche à comprendre.";
    question.classList.toggle("is-empty", !a.question);
    const updated = a.updated_at !== a.created_at ? ` · modifiée par ${a.updated_by}, ${formatDate(a.updated_at)}` : "";
    document.getElementById("meta").textContent = `Créée par ${a.created_by}, ${formatDate(a.created_at)}${updated}`;
    document.getElementById("delete").hidden = !(state.user && (state.user.is_admin || state.user.id === a.created_by_id));
  }

  const heroForm = document.querySelector(".js-hero-form");
  const heroView = document.querySelector(".js-hero-view");
  function editHero(open) {
    heroForm.hidden = !open;
    heroView.hidden = open;
    document.getElementById("edit").hidden = open;
    if (!open) return;
    heroForm.elements.title.value = state.analysis.title;
    heroForm.elements.question.value = state.analysis.question;
    heroForm.elements.title.focus();
  }
  document.getElementById("edit").addEventListener("click", () => editHero(true));
  heroForm.querySelector(".js-hero-cancel").addEventListener("click", () => editHero(false));
  heroForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      state.analysis = await metaAnalysisApi.update(analysisId, { title: heroForm.elements.title.value, question: heroForm.elements.question.value });
      editHero(false);
      renderHero();
      showError(null);
    } catch (err) {
      showError(err);
    }
  });

  document.getElementById("delete").addEventListener("click", async () => {
    if (!window.confirm(`Supprimer l'analyse « ${state.analysis.title} » ? Les notes écrites sur ses plaques restent sur leur page.`)) return;
    try {
      await metaAnalysisApi.remove(analysisId);
      location.href = "/analyses";
    } catch (err) {
      showError(err);
    }
  });

  const copyBtn = document.getElementById("copy-link");
  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      copyBtn.textContent = "Lien copié";
    } catch (err) {
      copyBtn.textContent = "Copie impossible";
    }
    setTimeout(() => (copyBtn.textContent = "Copier le lien"), 1600);
  });

  // -- les plaques : la référence d'abord ---------------------------------------------------------

  function renderChips() {
    const wafers = state.analysis.wafers;
    document.getElementById("plates-count").textContent = `${plural(wafers.length, "plaque")} · ${MAX_WAFERS} au plus`;
    chipsEl.innerHTML = wafers
      .map(
        (w, i) => `
        <li class="ma-chip${i === 0 ? " is-ref" : ""}">
          <span class="ma-dot" style="background:${AnalysisData.colorOf(i)}" aria-hidden="true"></span>
          ${i === 0 ? `<span class="ma-chip__ref">Réf.</span>` : ""}
          <a class="mono" href="${plateUrl(w.lasermark)}">${escapeHtml(w.lasermark)}</a>
          ${
            i === 0
              ? ""
              : `<button type="button" class="ma-chip__btn js-make-ref" data-index="${i}" aria-label="Prendre ${escapeHtml(w.lasermark)} comme référence" title="Prendre comme référence"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4v16"/><path d="M20 12H9"/><path d="m13 8-4 4 4 4"/></svg></button>`
          }
          ${
            wafers.length > 1
              ? `<button type="button" class="ma-chip__btn ma-chip__remove js-remove" data-index="${i}" aria-label="Retirer ${escapeHtml(w.lasermark)} de l'analyse" title="Retirer de l'analyse"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button>`
              : ""
          }
        </li>`
      )
      .join("");
    input.disabled = wafers.length >= MAX_WAFERS;
  }

  async function saveWafers(lasermarks, { keepError = false } = {}) {
    try {
      state.analysis = await metaAnalysisApi.update(analysisId, { wafers: lasermarks });
      if (!keepError) showError(null);
      renderHero();
      renderChips();
      await renderPlates();
      data?.reload();
    } catch (err) {
      showError(err);
    }
  }

  chipsEl.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const lasermarks = state.analysis.wafers.map((w) => w.lasermark);
    const index = Number(button.dataset.index);
    if (button.classList.contains("js-make-ref")) {
      const [ref] = lasermarks.splice(index, 1);
      saveWafers([ref, ...lasermarks]);
    } else if (button.classList.contains("js-remove")) {
      lasermarks.splice(index, 1);
      saveWafers(lasermarks);
    }
  });

  // -- ajouter des plaques : par lasermark, run d'épitaxie, lot, µprojet ou FDL (wafer-picker.js) -----------

  WaferPicker.mount({
    input,
    listbox,
    has: (key) => state.analysis.wafers.some((w) => w.key === key),
    onPick: (lasermarks) => {
      const current = state.analysis.wafers.map((w) => w.lasermark);
      const room = MAX_WAFERS - current.length;
      const capped = lasermarks.length > room;
      if (room > 0) saveWafers([...current, ...lasermarks.slice(0, room)], { keepError: capped });
      if (capped) showError(`Une analyse compare ${MAX_WAFERS} plaques au plus : ${room ? `${room} ajoutée${room > 1 ? "s" : ""} sur ${lasermarks.length}` : "retirez-en pour en ajouter"}.`);
    },
  });

  // -- côte à côte ---------------------------------------------------------------------------------

  // la structure d'une plaque, comme sur sa page : {html, caption} - html null : rien à dessiner
  async function structureOf(plate) {
    const latest = latestStudy(plate);
    if (latest) {
      const exp = latest.experiment;
      const detail = await experimentsApi.getVersion(exp.microproject.slug, exp.id, exp.version_id).catch(() => null);
      const studyLink = `<a href="/microprojets/${encodeURIComponent(exp.microproject.slug)}/experiences/${encodeURIComponent(exp.id)}">${escapeHtml(exp.title)}</a>`;
      const variant = latest.variant ? ` · variante <strong class="mono">${escapeHtml(latest.variant)}</strong>` : "";
      if (detail && detail.structure_svg) return { html: detail.structure_svg, caption: `Vue dans ${studyLink}${variant}`, label: `${exp.title}${latest.variant ? ` · ${latest.variant}` : ""}` };
      if (detail && detail.structure_images && detail.structure_images.length) {
        const image = detail.structure_images[0];
        return { html: `<img src="${escapeHtml(image.url)}" alt="${escapeHtml(image.caption || "Structure en images")}">`, caption: `Vue dans ${studyLink}${variant} - en images`, label: exp.title };
      }
    }
    if (plate.structure) {
      const st = plate.structure;
      const origin = st.kind === "reference" ? "version de référence" : "structure de la bibliothèque";
      return { html: st.svg || null, caption: `<strong>${escapeHtml(st.label)}</strong> · ${origin}, attachée à la plaque`, label: st.label };
    }
    return { html: null, caption: latest ? "Sa dernière étude n'a pas de structure dessinée." : "Aucune étude de vos µprojets ne la suit, et aucune structure ne lui est attachée.", label: "" };
  }

  function factsHtml(plate) {
    const latest = latestStudy(plate);
    const fdl = plate.fdl.length ? plate.fdl : plate.line_fdl || [];
    const facts = [
      ["Statut", latest ? statusBadgeHtml(latest.experiment.status) : plate.record ? `<span class="help" style="margin:0;">fiche de plaque, sans étude</span>` : "—"],
      [
        "µprojets",
        plate.microprojects.length
          ? plate.microprojects.map((m) => `<a class="fiche-code" href="/microprojets/${encodeURIComponent(m.slug)}" title="${escapeHtml(m.name)}">${escapeHtml(m.code || m.name)}</a>`).join(" ")
          : "—",
      ],
      ["Lot", plate.lot_name ? `<span class="mono">${escapeHtml(plate.lot_name)}</span>` : "—"],
      ["FDL", fdl.length ? `<span class="mono">${fdl.map(escapeHtml).join(", ")}</span>` : "—"],
      ["Runs d'épi.", (plate.run_names || []).length ? `<span class="mono">${plate.run_names.map(escapeHtml).join(", ")}</span>` : "—"],
      ["Études", plate.occurrences.length ? String(plate.occurrences.length) : "—"],
    ];
    return `<dl class="ma-facts">${facts.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join("")}</dl>`;
  }

  function columnHtml(wafer, index) {
    return `
      <article class="card ma-col${index === 0 ? " is-ref" : ""}" data-key="${escapeHtml(wafer.key)}" aria-label="${index === 0 ? "Référence" : "Plaque"} ${escapeHtml(wafer.lasermark)}">
        <header class="ma-col__head">
          <span class="ma-dot" style="background:${AnalysisData.colorOf(index)}" aria-hidden="true"></span>
          ${index === 0 ? `<span class="ma-col__badge">Référence</span>` : `<span class="ma-col__rank mono">${index}</span>`}
          <a class="ma-col__lasermark mono" href="${plateUrl(wafer.lasermark)}">${escapeHtml(wafer.lasermark)}</a>
        </header>
        <div class="ma-col__figure js-figure"><div class="skeleton" style="height:100%;"></div></div>
        <p class="help ma-col__caption js-caption"></p>
        <div class="js-facts"><div class="skeleton" style="height:120px;"></div></div>
        <div class="ma-col__context js-context"><div class="plate-context__list js-context-list"></div></div>
      </article>`;
  }

  // la plaque (son passeport), lue une fois par visite ; une erreur est gardée pour être dite dans sa colonne
  function plateOf(wafer) {
    if (!state.plates.has(wafer.key)) state.plates.set(wafer.key, wafersApi.get(wafer.lasermark).catch((err) => ({ error: err })));
    return state.plates.get(wafer.key);
  }

  function structureFor(wafer, plate) {
    if (!state.structures.has(wafer.key)) state.structures.set(wafer.key, structureOf(plate));
    return state.structures.get(wafer.key);
  }

  // toutes les structures dessinées, dans l'ordre de la page : ← → passe d'une plaque à l'autre
  function openZoom(key) {
    const items = [];
    let start = 0;
    for (const [i, w] of state.analysis.wafers.entries()) {
      const shown = columnsEl.querySelector(`.ma-col[data-key="${CSS.escape(w.key)}"] .js-zoom`);
      if (!shown) continue;
      if (w.key === key) start = items.length;
      items.push({ html: shown.querySelector(".ma-col__svg").innerHTML, caption: `${w.lasermark}${shown.dataset.label ? ` - ${shown.dataset.label}` : ""}`, badge: i === 0 ? "Réf." : "" });
    }
    openStructureZoom({ title: state.analysis.title, items, index: start });
  }

  async function fillColumn(column, wafer) {
    const plate = await plateOf(wafer);
    if (plate.error) {
      column.querySelector(".js-figure").innerHTML = `<div class="ma-col__empty">Plaque illisible</div>`;
      column.querySelector(".js-caption").textContent = plate.error.message || String(plate.error);
      column.querySelector(".js-facts").innerHTML = "";
      return null;
    }
    column.querySelector(".js-facts").innerHTML = factsHtml(plate);
    PlateContext.render(column.querySelector(".js-context"), plate);
    const structure = await structureFor(wafer, plate);
    const figure = column.querySelector(".js-figure");
    figure.innerHTML = structure.html
      ? `<button type="button" class="builder-canvas-svg structure-zoomable js-zoom" data-label="${escapeHtml(structure.label)}" aria-label="Agrandir la structure de ${escapeHtml(wafer.lasermark)}" title="Agrandir et comparer"><span class="ma-col__svg">${structure.html}</span>${STRUCTURE_ZOOM_BADGE}</button>`
      : `<div class="ma-col__empty">Pas de structure</div>`;
    column.querySelector(".js-caption").innerHTML = structure.caption;
    figure.querySelector(".js-zoom")?.addEventListener("click", () => openZoom(wafer.key));
    return plate;
  }

  async function renderPlates() {
    const wafers = state.analysis.wafers;
    columnsEl.innerHTML = wafers.map(columnHtml).join("");
    const columns = [...columnsEl.querySelectorAll(".ma-col")];
    const plates = await Promise.all(wafers.map((w, i) => fillColumn(columns[i], w)));
    renderComparison(plates);
  }

  // -- le tableau du comparateur ------------------------------------------------------------------

  const table = Comparator.mount(document.getElementById("comparison"), EMPTY_COMPARISON, {
    emptyText: "Aucune de ces plaques n'est suivie par une étude de vos µprojets : rien à comparer paramètre par paramètre.",
  });
  let comparisonTicket = 0;

  async function renderComparison(plates) {
    const wafers = state.analysis.wafers;
    const comparable = wafers.filter((w, i) => plates[i] && latestStudy(plates[i]));
    const left = wafers.filter((w) => !comparable.includes(w));
    const note = document.getElementById("comparison-note");
    const refOut = left.includes(wafers[0]);
    note.innerHTML = [
      refOut && comparable.length ? `La référence <strong class="mono">${escapeHtml(wafers[0].lasermark)}</strong> n'est suivie par aucune étude de vos µprojets : le tableau prend <strong class="mono">${escapeHtml(comparable[0].lasermark)}</strong> comme base.` : "",
      left.length ? `Hors du tableau, faute d'étude de vos µprojets qui les suive : ${left.map((w) => `<span class="mono">${escapeHtml(w.lasermark)}</span>`).join(", ")}.` : "",
    ]
      .filter(Boolean)
      .join(" ");
    note.hidden = !note.innerHTML;
    const items = comparable.map((w) => Comparator.waferItem(w.lasermark));
    state.comparison = { keys: comparable.map((w) => w.key), result: null };
    const link = document.getElementById("open-comparator");
    link.hidden = !items.length;
    if (!items.length) return table.update(EMPTY_COMPARISON);
    link.href = Comparator.pageUrl(items, 0);
    const ticket = ++comparisonTicket;
    try {
      const result = await comparatorApi.compare(items, 0);
      if (ticket === comparisonTicket) {
        table.update(result);
        state.comparison.result = result;
      }
    } catch (err) {
      if (ticket === comparisonTicket) {
        table.update(EMPTY_COMPARISON);
        note.hidden = false;
        note.textContent = `Le comparateur n'a pas pu lire ces plaques : ${err.message || err}`;
      }
    }
  }

  // -- la conclusion ------------------------------------------------------------------------------

  const conclusionButton = conclusionForm.querySelector("[type=submit]");
  const conclusionState = conclusionForm.querySelector(".js-conclusion-state");
  const dirty = () => conclusionEl.value.trim() !== (state.analysis?.conclusion || "");

  function renderConclusion() {
    conclusionEl.value = state.analysis.conclusion;
    conclusionButton.disabled = true;
    conclusionState.textContent = state.analysis.conclusion ? "" : "Pas encore de conclusion.";
  }
  conclusionEl.addEventListener("input", () => {
    conclusionButton.disabled = !dirty();
    conclusionState.textContent = dirty() ? "Modifiée, pas encore enregistrée." : "";
  });
  conclusionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    conclusionButton.disabled = true;
    try {
      state.analysis = await metaAnalysisApi.update(analysisId, { conclusion: conclusionEl.value });
      renderHero();
      renderConclusion();
      conclusionState.textContent = "Enregistrée.";
    } catch (err) {
      showError(err);
      conclusionButton.disabled = false;
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (state.analysis && dirty()) event.preventDefault();
  });

  let data = null; // le bloc « Données » (analysis-data.js), monté au chargement

  // -- le rapport ---------------------------------------------------------------------------------
  // Un instantané de ce que montre la page, en un fichier HTML autonome (report-html.js) : les plaques et leurs
  // structures, ce qui diffère de la référence et ce qui bouge, les KPI, la fiche data, le contexte de chaque
  // plaque (relu : ses notes ont pu changer d'ici) et la conclusion.

  const textOf = (html) => {
    const el = document.createElement("div");
    el.innerHTML = html || "";
    return el.textContent.trim();
  };

  function factsText(plate) {
    const latest = latestStudy(plate);
    const fdl = plate.fdl.length ? plate.fdl : plate.line_fdl || [];
    return [
      { label: "Statut", value: latest ? (STATUS_LABELS[latest.experiment.status] || {}).label || latest.experiment.status : plate.record ? "fiche de plaque, sans étude" : "—" },
      { label: "µprojets", value: plate.microprojects.map((m) => m.code || m.name).join(", ") || "—" },
      { label: "Lot", value: plate.lot_name || "—" },
      { label: "FDL", value: fdl.join(", ") || "—" },
      { label: "Runs d'épi.", value: (plate.run_names || []).join(", ") || "—" },
    ];
  }

  function studiesOf(plate) {
    const seen = new Set();
    return plate.occurrences
      .filter((o) => o.experiment.member && !seen.has(o.experiment.id) && seen.add(o.experiment.id))
      .map((o) => {
        const conclusion = (o.experiment.story || {}).conclusion || {};
        return { title: o.experiment.title, status: (STATUS_LABELS[o.experiment.status] || {}).label || "", conclusion: conclusion.summary || "", next: conclusion.next_steps || "" };
      });
  }

  let logoPromise = null;
  function loadLogo() {
    if (!logoPromise) logoPromise = fetch("/static/kernel/img/aledia-logo.svg").then((r) => (r.ok ? r.text() : "")).catch(() => "");
    return logoPromise;
  }

  async function buildReport() {
    const a = state.analysis;
    const [fresh, logoSvg] = await Promise.all([Promise.all(a.wafers.map((w) => wafersApi.get(w.lasermark).catch(() => null))), loadLogo()]);
    const cached = await Promise.all(a.wafers.map(plateOf));
    const plates = a.wafers.map((w, i) => fresh[i] || (cached[i].error ? null : cached[i]));
    const structures = await Promise.all(a.wafers.map((w, i) => (cached[i].error ? null : structureFor(w, cached[i]))));
    const snap = data ? await data.snapshot() : { kpis: [], blocks: [], sheets: [], moves: {} };
    const comparison = state.comparison || { keys: [], result: null };
    const refRow = comparison.keys.indexOf(a.wafers[0].key);
    const wafers = a.wafers.map((w, i) => ({
      lasermark: w.lasermark,
      color: AnalysisData.colorOf(i),
      isRef: i === 0,
      structure: structures[i] ? { svg: structures[i].html, caption: textOf(structures[i].caption) } : null,
      facts: plates[i] ? factsText(plates[i]) : [],
      notes: plates[i] ? plates[i].notes : null,
      studies: plates[i] ? studiesOf(plates[i]) : [],
    }));
    const differences = a.wafers.slice(1).map((w, j) => {
      const row = comparison.keys.indexOf(w.key);
      const comparable = !!comparison.result && refRow === 0 && row > 0;
      return {
        lasermark: w.lasermark,
        color: AnalysisData.colorOf(j + 1),
        comparable,
        items: comparable ? AnalysisReport.differences(comparison.result, row) : [],
        kpis: snap.moves[w.key] || [],
      };
    });
    const updated = a.updated_at !== a.created_at ? ` · modifiée par ${a.updated_by} le ${formatDate(a.updated_at)}` : "";
    return {
      title: a.title,
      question: a.question,
      conclusion: a.conclusion,
      date: new Date().toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }),
      byline: `Créée par ${a.created_by} le ${formatDate(a.created_at)}${updated}`,
      logoSvg,
      wafers,
      differences,
      kpis: snap.kpis,
      blocks: snap.blocks,
      sheets: snap.sheets,
    };
  }

  function fileName(title) {
    const base = title.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
    return `analyse-${base || analysisId}.html`;
  }

  const reportBtn = document.getElementById("report");
  reportBtn.addEventListener("click", async () => {
    reportBtn.disabled = true;
    reportBtn.textContent = "Rapport en cours…";
    try {
      const html = AnalysisReport.build(await buildReport());
      const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName(state.analysis.title);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
    } catch (err) {
      showError(err);
    } finally {
      reportBtn.disabled = false;
      reportBtn.textContent = "Rapport";
    }
  });

  // -- au chargement ------------------------------------------------------------------------------

  async function init() {
    try {
      const [analysis, user] = await Promise.all([metaAnalysisApi.get(analysisId), accountsApi.me().catch(() => null)]);
      state.analysis = analysis;
      state.user = user;
      renderHero();
      renderChips();
      renderConclusion();
      data = AnalysisData.mount(document.getElementById("data"), {
        analysisId,
        getAnalysis: () => state.analysis,
        onAnalysis: (analysis) => {
          state.analysis = analysis;
          renderHero();
        },
      });
      data.reload();
      await renderPlates();
    } catch (err) {
      showError(err);
      document.getElementById("title").textContent = "Analyse introuvable";
    }
  }

  init();
})();
