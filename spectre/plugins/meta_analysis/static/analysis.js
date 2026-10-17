/* Page /analyses/{id} : une analyse de plaques. La plaque de référence et celles qu'on lui compare, côte à côte -
   une colonne par plaque : la structure qu'elle a vue, ce qu'on sait d'elle (µprojet, statut, lot, FDL, runs) et
   son contexte (PlateContext, plugin wafers : les études qui la suivent et ses notes, qu'on écrit d'ici) -, puis
   le tableau du comparateur (la référence en base) et la conclusion de l'analyse.

   La structure d'une plaque est celle de la page de la plaque : la dernière étude de vos µprojets qui la suit
   (son dessin, ou sa première image), sinon la structure attachée à la plaque. Seules les plaques qu'une étude
   de vos µprojets suit entrent dans le tableau du comparateur (un jeton wafer: se lit dans une étude) ; les
   autres sont nommées au-dessus.

   Les passeports des plaques sont gardés pendant la visite : changer la référence ou l'ordre ne relit rien. */

(() => {
  const { analysis_id: analysisId } = routeParams("/analyses/{analysis_id}");
  const state = { analysis: null, user: null, plates: new Map(), structures: new Map(), options: [], active: -1 };
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

  async function saveWafers(lasermarks) {
    try {
      state.analysis = await metaAnalysisApi.update(analysisId, { wafers: lasermarks });
      showError(null);
      renderHero();
      renderChips();
      await renderPlates();
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

  // -- ajouter une plaque (combobox) --------------------------------------------------------------

  function closeOptions() {
    listbox.hidden = true;
    listbox.innerHTML = "";
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    state.options = [];
    state.active = -1;
  }

  function renderOptions() {
    listbox.innerHTML = state.options
      .map((option, index) => {
        const added = state.analysis.wafers.some((w) => w.key === option.key);
        return `
          <li class="cmp-option${added ? " is-added" : ""}" role="option" id="picker-option-${index}" data-index="${index}" aria-selected="${index === state.active}">
            <span class="cmp-option__label mono">${escapeHtml(option.lasermark)}${added ? ` <span class="help" style="margin:0;">· déjà dans l'analyse</span>` : ""}</span>
            ${option.sublabel ? `<span class="cmp-option__sub">${escapeHtml(option.sublabel)}</span>` : ""}
          </li>`;
      })
      .join("");
    listbox.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (state.active >= 0) input.setAttribute("aria-activedescendant", `picker-option-${state.active}`);
  }

  function waferOption(w) {
    const exp = w.latest && w.latest.experiment;
    const sublabel = exp && exp.member ? [exp.title, exp.microproject.name].filter(Boolean).join(" · ") : w.record ? "fiche de plaque, sans étude" : exp ? exp.microproject.name : "";
    return { key: w.key, lasermark: w.lasermark, sublabel };
  }

  function addWafer(option) {
    input.value = "";
    closeOptions();
    if (state.analysis.wafers.some((w) => w.key === option.key)) return;
    saveWafers([...state.analysis.wafers.map((w) => w.lasermark), option.lasermark]);
  }

  let timer = null;
  let searchTicket = 0;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const query = input.value.trim();
    if (!query) return closeOptions();
    timer = setTimeout(async () => {
      const ticket = ++searchTicket;
      try {
        const found = await wafersApi.list({ q: query });
        if (ticket !== searchTicket || input.value.trim() !== query) return;
        state.options = found.slice(0, 8).map(waferOption);
        // une plaque que Spectre ne connaît pas encore s'ajoute quand même, telle qu'écrite
        if (!found.length) {
          state.options.push({ key: query.replace(/[^0-9a-z]/gi, "").toUpperCase(), lasermark: query, sublabel: "Ajouter telle qu'écrite - Spectre ne la connaît pas encore" });
        }
        state.active = 0;
        renderOptions();
      } catch (err) {
        showError(err);
      }
    }, 200);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") return closeOptions();
    if (listbox.hidden || !state.options.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      state.active = (state.active + (event.key === "ArrowDown" ? 1 : -1) + state.options.length) % state.options.length;
      renderOptions();
      document.getElementById(`picker-option-${state.active}`)?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && state.active >= 0) {
      event.preventDefault();
      addWafer(state.options[state.active]);
    }
  });
  listbox.addEventListener("mousedown", (event) => event.preventDefault()); // garder le focus dans le champ
  listbox.addEventListener("click", (event) => {
    const option = event.target.closest(".cmp-option");
    if (option) addWafer(state.options[Number(option.dataset.index)]);
  });
  input.addEventListener("blur", () => setTimeout(closeOptions, 120));

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
    const link = document.getElementById("open-comparator");
    link.hidden = !items.length;
    if (!items.length) return table.update(EMPTY_COMPARISON);
    link.href = Comparator.pageUrl(items, 0);
    const ticket = ++comparisonTicket;
    try {
      const result = await comparatorApi.compare(items, 0);
      if (ticket === comparisonTicket) table.update(result);
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

  // -- au chargement ------------------------------------------------------------------------------

  async function init() {
    try {
      const [analysis, user] = await Promise.all([metaAnalysisApi.get(analysisId), accountsApi.me().catch(() => null)]);
      state.analysis = analysis;
      state.user = user;
      renderHero();
      renderChips();
      renderConclusion();
      await renderPlates();
    } catch (err) {
      showError(err);
      document.getElementById("title").textContent = "Analyse introuvable";
    }
  }

  init();
})();
