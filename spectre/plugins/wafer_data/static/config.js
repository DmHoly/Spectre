/* Page « Fiche data » du menu Data (spectre.plugins.wafer_data) : on choisit un projet corporate (gardé dans
   l'adresse, ?projet=) et on règle les blocs que l'onglet « Data » de ses plaques montre - les renommer, les
   déplacer, les modifier, les retirer, en ajouter. Un bloc lit des colonnes d'un type de données PRISM, et
   chaque colonne a un **type** (scalaire, vecteur, lien vers une image, booléen, catégorie...) : chaque liste ne
   propose que les colonnes du bon type - deux vecteurs pour des courbes, une colonne de liens pour une galerie.
   Le type est observé sur de vraies lignes (« Lire les vraies colonnes » : quelques plaques du projet), deviné
   sinon d'après la fiche PRISM, et se corrige à la main (« Colonnes et types », pour tous les projets).
   Couleurs : une par valeur d'une catégorie (« Colorer par ») ou une couleur de la palette de la charte.
   Filtres au même vocabulaire que les KPI suivis (kpi_tracking/static/kpi-config.js). Puis calculer d'avance
   les fiches de toutes les plaques du projet, paquet par paquet, et voir ce que pèse leur magasin. */

const selectEl = document.getElementById("wd-area");
const panels = document.getElementById("wd-panels");
const manageable = new Map(); // slug -> peut gérer le projet
let loadToken = 0;

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
  const blocksEl = document.getElementById("wd-blocks");
  const addEl = document.getElementById("wd-add");
  document.getElementById("wd-add-card").hidden = !canEdit;
  document.getElementById("wd-compute-card").hidden = !canEdit;

  // --- la liste des blocs ------------------------------------------------------------------------

  const describe = (b) => WaferBlockForm.describe(b, catalog);

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
                 ${b.available ? `<button type="button" class="btn btn-line" data-edit="${b.id}">Modifier</button>` : ""}
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
    const edit = event.target.closest("[data-edit]");
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
        if (blockForm && blockForm.editing() === block.id) blockForm.reset();
      } else if (edit) {
        blockForm.edit(current.find((b) => String(b.id) === edit.dataset.edit));
        document.getElementById("wd-add-card").scrollIntoView({ behavior: "smooth", block: "start" });
        addEl.querySelector("#wd-f-submit").focus({ preventScroll: true });
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

  // --- le formulaire d'un bloc (block-form.js) -------------------------------------------------------

  const blockForm = canEdit
    ? WaferBlockForm.mount(addEl, {
        catalog,
        titleEl: document.querySelector("#wd-add-card .section-title"),
        canEditTypes: true,
        probe: (hook) => waferDataApi.probe(slug, hook),
        setColumnType: (hook, column, type) => waferDataApi.setColumnType(slug, hook, column, type),
        titleOf: (id) => (current.find((b) => b.id === id) || {}).title || "",
        showError,
        clearError,
        async submit(block, editing) {
          if (editing !== null) await waferDataApi.update(slug, editing, { config: block.config, label: block.label });
          else await waferDataApi.add(slug, { ...block, label: block.label || null });
          await reload();
        },
      })
    : null;

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
