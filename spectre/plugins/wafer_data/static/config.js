/* Page « Fiche data » du menu Data (spectre.plugins.wafer_data) : on choisit un projet corporate (gardé dans
   l'adresse, ?projet=) et on règle les blocs que l'onglet « Data » de ses plaques montre - les renommer, les
   déplacer, les retirer, en ajouter (un genre, un type de données PRISM, ses colonnes, des filtres au même
   vocabulaire que les KPI suivis : kpi_tracking/static/kpi-config.js). Puis calculer d'avance les fiches de
   toutes les plaques du projet, paquet par paquet, et voir ce que pèse leur magasin (administrateurs). */

const selectEl = document.getElementById("wd-area");
const panels = document.getElementById("wd-panels");
const manageable = new Map(); // slug -> peut gérer le projet
let loadToken = 0;

const KIND_INFO = {
  value: { desc: "Un chiffre : médiane, moyenne, part des LED allumées… situé parmi les plaques du projet.", glyph: '<path d="M4 19h16"/><path d="M7 15V9"/><path d="M12 15V5"/><path d="M17 15v-3"/>' },
  histogram: { desc: "La distribution d'une colonne sur les dispositifs de la plaque.", glyph: '<path d="M3 20h18"/><rect x="5" y="12" width="3" height="8"/><rect x="10.5" y="6" width="3" height="14"/><rect x="16" y="10" width="3" height="10"/>' },
  wafermap: { desc: "La colonne par position (X, Y) : une carte de la plaque, comme une PL.", glyph: '<circle cx="12" cy="12" r="9"/><path d="M8 8h3v3H8zM13 8h3v3h-3zM8 13h3v3H8z"/>' },
  curve: { desc: "Une courbe par dispositif (EQE en fonction du courant) : la médiane et l'enveloppe 10-90 %.", glyph: '<path d="M3 20h18"/><path d="M4 17c4-1 5-10 8-10s4 6 8 7"/>' },
  images: { desc: "Des fichiers d'images retrouvés d'après un modèle de chemin ({lasermark}, {lot}…).", glyph: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 17-5-5-9 8"/>' },
};
const DATE_LABEL = { latest: "mesure la plus récente", all: "toutes les mesures" };
const BETTER_LABEL = { high: "plus haut = mieux", low: "plus bas = mieux", "": "" };

function clearError() {
  const box = document.getElementById("error");
  box.style.display = "none";
  box.textContent = "";
}

function showError(err) {
  const box = document.getElementById("error");
  box.textContent = err && err.message ? err.message : String(err);
  box.style.display = "block";
  box.scrollIntoView({ block: "nearest" });
}

const svgIcon = (path, size = 16) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;

function mountConfig({ slug, canEdit, catalog, blocks }) {
  let current = blocks;
  const hooks = catalog.hooks;
  const aggregates = Object.fromEntries(catalog.aggregates.map((a) => [a.key, a.label]));
  const form = { kind: "value", hook: hooks[0] ? hooks[0].hook : "", filters: [] };
  const blocksEl = document.getElementById("wd-blocks");
  const addEl = document.getElementById("wd-add");
  document.getElementById("wd-add-card").hidden = !canEdit;
  document.getElementById("wd-compute-card").hidden = !canEdit;

  const hookOf = (key) => hooks.find((h) => h.hook === key);

  function describe(b) {
    const c = b.config;
    const parts = b.kind === "images" ? [`<span class="mono">${escapeHtml(c.pattern)}</span>`, `${c.max} images au plus`] : [escapeHtml(b.hook_title)];
    if (b.kind === "value") parts.push(`${escapeHtml(c.column)} · ${escapeHtml(aggregates[c.aggregate] || c.aggregate)}${c.better ? ` · ${BETTER_LABEL[c.better]}` : ""}`);
    if (b.kind === "histogram") parts.push(escapeHtml(c.column));
    if (b.kind === "wafermap") parts.push(`${escapeHtml(c.column)} par ${escapeHtml(c.x)}, ${escapeHtml(c.y)}`);
    if (b.kind === "curve") parts.push(`${escapeHtml(c.y)} en fonction de ${escapeHtml(c.x)}${c.log_x ? " (x log)" : ""}${c.log_y ? " (y log)" : ""}`);
    if (c.date && hookOf(b.hook) && hookOf(b.hook).dated) parts.push(DATE_LABEL[c.date]);
    (c.filters || []).forEach((f) => parts.push(escapeHtml(kpiFilterText(f))));
    if (!b.available) parts.push('<span class="wd-row__missing">n\'est plus dans PRISM</span>');
    return parts.join(" · ");
  }

  function renderBlocks() {
    if (!current.length) {
      blocksEl.innerHTML = `<p class="help">Aucun bloc pour l'instant${canEdit ? " : ajoutez-en ci-dessous - l'onglet « Data » de chaque plaque du projet les montrera dans cet ordre." : "."}</p>`;
      return;
    }
    blocksEl.innerHTML = current
      .map(
        (b, i) => `<div class="wd-row" data-id="${b.id}">
          <span class="wd-row__kind">${escapeHtml(b.kind_label)}</span>
          <div style="min-width:0;"><div class="wd-row__name">${escapeHtml(b.title)}</div><div class="wd-row__meta">${describe(b)}</div></div>
          <div>${canEdit ? `<input type="text" class="field" data-rename="${b.id}" value="${escapeHtml(b.label)}" maxlength="80" placeholder="Nom affiché (par défaut : ${escapeHtml(b.title)})" aria-label="Nom affiché de ${escapeHtml(b.title)}">` : ""}</div>
          <div class="wd-row__actions">${
            canEdit
              ? `<button type="button" class="btn btn-line wd-icon-btn" data-move="up" data-id="${b.id}" aria-label="Monter ${escapeHtml(b.title)}" ${i === 0 ? "disabled" : ""}>${svgIcon('<path d="m6 15 6-6 6 6"/>')}</button>
                 <button type="button" class="btn btn-line wd-icon-btn" data-move="down" data-id="${b.id}" aria-label="Descendre ${escapeHtml(b.title)}" ${i === current.length - 1 ? "disabled" : ""}>${svgIcon('<path d="m6 9 6 6 6-6"/>')}</button>
                 <button type="button" class="btn btn-line" data-remove="${b.id}">Retirer</button>`
              : ""
          }</div>
        </div>`
      )
      .join("");
  }

  async function reload() {
    current = await waferDataApi.blocks(slug);
    renderBlocks();
  }

  blocksEl.addEventListener("click", async (event) => {
    const move = event.target.closest("[data-move]");
    const remove = event.target.closest("[data-remove]");
    clearError();
    try {
      if (move) {
        await waferDataApi.update(slug, move.dataset.id, { move: move.dataset.move });
        await reload();
        const again = blocksEl.querySelector(`[data-move="${move.dataset.move}"][data-id="${move.dataset.id}"]`);
        if (again && !again.disabled) again.focus();
      } else if (remove) {
        const block = current.find((b) => String(b.id) === remove.dataset.remove);
        if (!window.confirm(`Retirer le bloc « ${block.title} » ? Il disparaîtra de l'onglet Data des plaques du projet, et ce qu'il avait calculé sera oublié.`)) return;
        await waferDataApi.remove(slug, remove.dataset.remove);
        await reload();
      }
    } catch (err) {
      showError(err);
    }
  });
  blocksEl.addEventListener("change", async (event) => {
    const input = event.target.closest("[data-rename]");
    if (!input) return;
    clearError();
    try {
      await waferDataApi.update(slug, input.dataset.rename, { label: input.value });
      await reload();
    } catch (err) {
      showError(err);
    }
  });

  // --- l'ajout d'un bloc -------------------------------------------------------------------------

  const options = (items, selected) => items.map(([value, text]) => `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(text)}</option>`).join("");
  const field = (id, label, control, wide = false) => `<div${wide ? ' class="wd-form__wide"' : ""}><label for="${id}">${label}</label>${control}</div>`;

  function defaultColumn(hook, avoid = []) {
    if (hook.representative && !avoid.includes(hook.representative)) return hook.representative;
    const columns = hook.columns.map((c) => c.name).filter((n) => ![hook.x, hook.y, ...avoid].includes(n) && !/date/i.test(n));
    return columns[0] || hook.columns[0].name;
  }

  function renderAdd() {
    const label = addEl.querySelector("#wd-f-label") ? addEl.querySelector("#wd-f-label").value : "";
    const usable = form.kind === "wafermap" ? hooks.filter((h) => h.x && h.y) : hooks;
    if (form.kind !== "images" && !usable.some((h) => h.hook === form.hook)) form.hook = usable[0] ? usable[0].hook : "";
    const hook = hookOf(form.hook);
    const kinds = catalog.kinds
      .map(
        (k) => `<button type="button" class="wd-kind" data-kind="${k.key}" aria-pressed="${k.key === form.kind}">
          <span class="wd-kind__title">${svgIcon(KIND_INFO[k.key].glyph)}${escapeHtml(k.label)}</span>
          <span class="wd-kind__desc">${escapeHtml(KIND_INFO[k.key].desc)}</span></button>`
      )
      .join("");
    let fields = "";
    if (form.kind === "images") {
      fields += field(
        "wd-f-pattern",
        "Où chercher les images",
        `<input type="text" class="field mono" id="wd-f-pattern" placeholder="\\\\serveur\\mesures\\PL\\{lot}\\{lasermark}_*.png" maxlength="500">
         <p class="help" style="margin-top:6px;">Un chemin de fichier : ${catalog.placeholders.map((p) => `<span class="mono">{${p}}</span>`).join(", ")} prennent les valeurs de la plaque (le lot et le run viennent de sa vie en ligne) ; <span class="mono">*</span> et <span class="mono">?</span> dans le nom du fichier. Le dossier doit être sous un dossier autorisé pour les images externes.</p>`,
        true
      );
      fields += field("wd-f-max", "Images au plus", `<input type="number" class="field" id="wd-f-max" min="1" max="24" value="8">`);
    } else if (!hook) {
      fields = `<p class="help wd-form__wide">${form.kind === "wafermap" ? "Aucun type de données PRISM n'a de colonnes de position (X, Y)." : "PRISM ne propose aucun type de données par plaque pour l'instant."}</p>`;
    } else {
      const columns = hook.columns.map((c) => [c.name, c.unit ? `${c.name} (${c.unit})` : c.name]);
      fields += field("wd-f-hook", "Type de données", `<select class="field" id="wd-f-hook">${options(usable.map((h) => [h.hook, `${h.title} · ${h.category}`]), form.hook)}</select>`);
      if (form.kind === "curve") {
        fields += field("wd-f-x", "Abscisse (une série par ligne)", `<select class="field" id="wd-f-x">${options(columns, hook.columns.some((c) => c.name === "I") ? "I" : defaultColumn(hook))}</select>`);
        fields += field("wd-f-y", "Ordonnée", `<select class="field" id="wd-f-y">${options(columns, hook.columns.some((c) => c.name === "EQE") ? "EQE" : defaultColumn(hook, ["I"]))}</select>`);
        fields += `<div class="wd-form__checks"><label><input type="checkbox" id="wd-f-logx" checked> abscisse en log</label><label><input type="checkbox" id="wd-f-logy"> ordonnée en log</label></div>`;
      } else {
        fields += field("wd-f-column", form.kind === "wafermap" ? "Colonne à cartographier" : "Colonne", `<select class="field" id="wd-f-column">${options(columns, defaultColumn(hook))}</select>`);
      }
      if (form.kind === "value") {
        fields += field("wd-f-aggregate", "Agrégat sur les lignes de la plaque", `<select class="field" id="wd-f-aggregate">${options(catalog.aggregates.map((a) => [a.key, a.label]), "median")}</select>`);
        fields += field("wd-f-better", "Sens", `<select class="field" id="wd-f-better">${options([["", "Neutre (centile)"], ["high", "Plus haut = mieux"], ["low", "Plus bas = mieux"]], "")}</select>`);
      }
      if (hook.dated) fields += field("wd-f-date", "Mesures", `<select class="field" id="wd-f-date">${options([["latest", "La plus récente"], ["all", "Toutes, mêlées"]], "latest")}</select>`);
      const chips = form.filters.map((f, i) => `<span class="wd-chip">${escapeHtml(kpiFilterText(f))}<button type="button" class="wd-chip__x" data-drop-filter="${i}" aria-label="Retirer le filtre ${escapeHtml(kpiFilterText(f))}">×</button></span>`).join("");
      fields += `<div class="wd-form__wide"><label for="wd-f-fcol">Filtres <span class="help" style="display:inline;margin:0;font-weight:400;">(les lignes gardées les passent tous)</span></label>
        ${chips ? `<div class="wd-filters" style="margin-bottom:8px;">${chips}</div>` : ""}
        <div class="wd-filter-row">
          <select class="field" id="wd-f-fcol" aria-label="Colonne à filtrer">${options(columns, columns[0][0])}</select>
          <select class="field" id="wd-f-fop" aria-label="Comparaison">${options(KPI_OPERATORS, "eq")}</select>
          <input type="text" class="field" id="wd-f-fval" placeholder="Valeur (ex : MQW-B3)" aria-label="Valeur du filtre">
          <button type="button" class="btn btn-tint" id="wd-f-fadd">Ajouter le filtre</button>
        </div></div>`;
    }
    fields += field("wd-f-label", "Nom affiché <span class=\"help\" style=\"display:inline;margin:0;font-weight:400;\">(facultatif)</span>", `<input type="text" class="field" id="wd-f-label" maxlength="80" value="${escapeHtml(label)}">`);
    addEl.innerHTML = `<div class="wd-kinds" role="group" aria-label="Genre de bloc">${kinds}</div>
      <div class="wd-form">${fields}</div>
      <div style="margin-top:14px;"><button type="button" class="btn btn-primary" id="wd-f-submit">Ajouter le bloc</button></div>`;
  }

  function value(id) {
    const el = addEl.querySelector(`#${id}`);
    return el ? (el.type === "checkbox" ? el.checked : el.value) : undefined;
  }

  addEl.addEventListener("click", async (event) => {
    const kind = event.target.closest("[data-kind]");
    const drop = event.target.closest("[data-drop-filter]");
    if (kind) {
      form.kind = kind.dataset.kind;
      renderAdd();
      addEl.querySelector(`[data-kind="${form.kind}"]`).focus();
    } else if (drop) {
      form.filters.splice(Number(drop.dataset.dropFilter), 1);
      renderAdd();
    } else if (event.target.closest("#wd-f-fadd")) {
      const raw = value("wd-f-fval").trim();
      if (!raw) return addEl.querySelector("#wd-f-fval").focus();
      form.filters.push({ column: value("wd-f-fcol"), op: value("wd-f-fop"), value: raw });
      renderAdd();
    } else if (event.target.closest("#wd-f-submit")) {
      clearError();
      const config = {};
      if (form.kind === "images") Object.assign(config, { pattern: value("wd-f-pattern"), max: Number(value("wd-f-max")) || 8 });
      else {
        if (form.kind === "curve") Object.assign(config, { x: value("wd-f-x"), y: value("wd-f-y"), log_x: value("wd-f-logx"), log_y: value("wd-f-logy") });
        else config.column = value("wd-f-column");
        if (form.kind === "value") Object.assign(config, { aggregate: value("wd-f-aggregate"), better: value("wd-f-better") });
        if (value("wd-f-date")) config.date = value("wd-f-date");
        config.filters = form.filters;
      }
      try {
        await waferDataApi.add(slug, { kind: form.kind, hook: form.kind === "images" ? "" : form.hook, config, label: value("wd-f-label") || null });
        form.filters = [];
        addEl.querySelector("#wd-f-label").value = "";
        renderAdd();
        await reload();
      } catch (err) {
        showError(err);
      }
    }
  });
  addEl.addEventListener("change", (event) => {
    if (event.target.id === "wd-f-hook") {
      form.hook = event.target.value;
      form.filters = [];
      renderAdd();
    }
  });

  // --- le calcul d'avance ------------------------------------------------------------------------

  const computeEl = document.getElementById("wd-compute");
  computeEl.innerHTML = `<div style="display:flex;gap:8px;flex-wrap:wrap;">
      <button type="button" class="btn btn-primary" data-compute="missing">Calculer les fiches qui manquent</button>
      <button type="button" class="btn btn-line" data-compute="all" title="Relire PRISM pour chaque plaque : plus long">Tout recalculer</button>
    </div>
    <div class="js-compute-status" aria-live="polite"></div>`;
  computeEl.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-compute]");
    if (!button) return;
    const status = computeEl.querySelector(".js-compute-status");
    computeEl.querySelectorAll("[data-compute]").forEach((b) => (b.disabled = true));
    clearError();
    let offset = 0, computed = 0;
    const errors = new Set();
    status.innerHTML = `<div class="wd-progress"><div class="wd-progress__bar"></div></div><p class="help js-progress-text">Recherche des plaques du projet…</p>`;
    try {
      for (;;) {
        const step = await waferDataApi.compute(slug, { offset, refresh: button.dataset.compute === "all" });
        computed += step.computed;
        step.errors.forEach((e) => errors.add(e));
        status.querySelector(".wd-progress__bar").style.width = `${step.total ? (step.done / step.total) * 100 : 100}%`;
        status.querySelector(".js-progress-text").textContent = `${step.done} / ${step.total} plaques · ${computed} bloc${computed > 1 ? "s" : ""} calculé${computed > 1 ? "s" : ""}`;
        if (step.next_offset === null) break;
        offset = step.next_offset;
      }
      if (errors.size) status.insertAdjacentHTML("beforeend", `<p class="wd-state wd-state--error">${[...errors].map(escapeHtml).join("<br>")}</p>`);
      renderStorage();
    } catch (err) {
      showError(err);
    } finally {
      computeEl.querySelectorAll("[data-compute]").forEach((b) => (b.disabled = false));
    }
  });

  renderBlocks();
  if (canEdit) renderAdd();
  renderStorage();
}

function bytes(n) {
  if (n < 1024) return `${n} o`;
  if (n < 1024 ** 2) return `${(n / 1024).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Ko`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo`;
  return `${(n / 1024 ** 3).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} Go`;
}

async function renderStorage() {
  const host = document.getElementById("wd-storage");
  const stats = await waferDataApi.storage().catch(() => null); // administrateurs seulement
  if (!stats) {
    host.innerHTML = "";
    return;
  }
  const tile = (value, label) => `<div class="kpi"><div class="kpi__value">${value}</div><div class="kpi__label">${label}</div></div>`;
  host.innerHTML = `<div class="section-title" style="margin:20px 0 4px;">Magasin des résumés (tous projets)</div>
    <p class="help">Hors de la base de Spectre ; au-delà du budget, les résumés les moins lus sont oubliés et se recalculent à la demande - les valeurs, elles, restent.</p>
    <div class="wd-storage">
      ${tile(stats.wafers.toLocaleString("fr-FR"), "plaques")}
      ${tile(stats.digests.toLocaleString("fr-FR"), "résumés")}
      ${tile(stats.scalars.toLocaleString("fr-FR"), "valeurs")}
      ${tile(bytes(stats.file_bytes), "sur disque")}
      ${tile(bytes(stats.budget_bytes), "budget")}
    </div>`;
}

async function show(slug) {
  const token = ++loadToken;
  clearError();
  panels.style.display = "none";
  history.replaceState(null, "", slug ? `?projet=${encodeURIComponent(slug)}` : location.pathname);
  if (!slug) return;
  try {
    const [blocks, catalog] = await Promise.all([waferDataApi.blocks(slug), waferDataApi.catalog(slug)]);
    if (token !== loadToken) return;
    for (const id of ["wd-blocks", "wd-add", "wd-compute"]) {
      const el = document.getElementById(id);
      el.replaceWith(el.cloneNode(false));
    }
    const canEdit = !!manageable.get(slug);
    mountConfig({ slug, canEdit, catalog, blocks });
    document.getElementById("wd-readonly").style.display = canEdit ? "none" : "";
    panels.style.display = "";
  } catch (err) {
    if (token === loadToken) showError(err);
  }
}

selectEl.addEventListener("change", () => show(selectEl.value));

(async function init() {
  try {
    const areas = (await areasApi.list()).filter((a) => !a.is_system);
    areas.sort((a, b) => a.name.localeCompare(b.name, "fr"));
    areas.forEach((a) => manageable.set(a.slug, a.can_manage));
    if (!areas.length) {
      selectEl.innerHTML = "<option>Aucun projet</option>";
      return;
    }
    selectEl.innerHTML = '<option value="">Choisir un projet…</option>' + areas.map((a) => `<option value="${escapeHtml(a.slug)}">${escapeHtml(a.name)}</option>`).join("");
    selectEl.disabled = false;
    const wanted = new URLSearchParams(location.search).get("projet");
    if (wanted && manageable.has(wanted)) {
      selectEl.value = wanted;
      show(wanted);
    }
  } catch (err) {
    selectEl.innerHTML = "<option>—</option>";
    showError(err);
  }
})();
