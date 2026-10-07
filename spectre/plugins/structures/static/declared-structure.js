/* Page « sans structure » (declared-structure.html) : lancer une expérience au minimum, sans
   structure complète - une description libre, un dessin collé si l'on en a un (facultatif,
   attachments/static/image-drop.js), et le split déclaré dans un tableau : une ligne par plaque, une
   colonne par chose qu'on change, la valeur de chaque plaque écrite telle quelle (kind "declared",
   voir spectre.plugins.structures.kinds.DeclaredStructure). Chaque ligne peut nommer sa plaque
   (lasermark) ; sinon elle s'associe plus tard sur la fiche, depuis la FDL de l'étude. Deux adresses :
   - /microprojets/{slug}/structures/sans-structure : nouvelle expérience (experimentsApi.create) ;
   - /microprojets/{slug}/experiences/{id}/evoluer-sans-structure : éditer une telle expérience
     (experimentsApi.evolve), ou en partir sur une nouvelle piste (create avec from_version),
     préremplie depuis sa dernière version, ou celle de ?version= (une version passée ne se continue
     que sur une nouvelle piste).
   Avec ?prevision=<id> : on lance une expérience prévue depuis l'arbre du µprojet - son titre, son
   intention et autant de lignes que de plaques prévues ; le lancement envoie son `plan_id`.
   objectives.js / intention-copy.js du constructeur sont repris tels quels : ils lisent `slug` et
   `state`, définis ici. */

const evolveRoute = routeParams("/microprojets/{slug}/experiences/{experiment_id}/evoluer-sans-structure");
const { slug } = evolveRoute || routeParams("/microprojets/{slug}/structures/sans-structure");
const evolveExperienceId = evolveRoute ? evolveRoute.experiment_id : null;
const evolveVersionId = evolveExperienceId ? new URLSearchParams(window.location.search).get("version") : null;
const planParam = new URLSearchParams(window.location.search).get("prevision");
const planId = /^\d+$/.test(planParam || "") ? parseInt(planParam, 10) : null;
let launchedPlan = null; // la prévision chargée (loadPlan)
const state = { objectives: [] };
let parentDetail = null; // la version de départ (sa version_id part en If-Match, ou en from_version)

const DS_MAX_ROWS = 200; // kinds.MAX_DECLARED_WAFERS
const DS_MAX_FACTORS = 20; // kinds.MAX_DECLARED_FACTORS

// Le split : ses colonnes (ce qu'on change) et ses lignes, une par plaque - {label, values, sample_id, fdl, location}
const split = { factors: [], rows: [] };

let imageDrop = null;
let studyFdlField = null;
let intentFormSection = null; // intent_forms/static/intent-form-section.js

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}
errorBox.title = "Cliquer pour fermer";
errorBox.addEventListener("click", clearError);

function setPageTitle(text) {
  document.getElementById("page-title").textContent = text;
  document.title = `${text} — Spectre`;
  document.getElementById("crumb").innerHTML = `/ <a href="/microprojets/${encodeURIComponent(slug)}">${escapeHtml(slug)}</a> / ${escapeHtml(text)}`;
}

function blankRow() {
  return { label: "", values: split.factors.map(() => ""), sample_id: "", fdl: [], location: null };
}

// --- le tableau du split ---------------------------------------------------------------------------

const REMOVE_ICON = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>`;

function renderSplitTable() {
  const wrap = document.getElementById("ds-table-wrap");
  const head = `<tr>
      <th scope="col" class="ds-table__idx">#</th>
      <th scope="col" class="ds-table__label">Nom <span class="ds-optional">facultatif</span></th>
      ${split.factors
        .map(
          (factor, j) => `<th scope="col" class="ds-table__factor">
            <span class="ds-factor">
              <input class="field ds-factor__input" data-factor="${j}" value="${escapeHtml(factor)}" placeholder="ce qu'on change" aria-label="Titre de la colonne ${j + 1}" maxlength="80" autocomplete="off">
              <button class="ds-icon-btn" type="button" data-remove-factor="${j}" aria-label="Retirer la colonne ${escapeHtml(factor || String(j + 1))}" title="Retirer la colonne">${REMOVE_ICON}</button>
            </span>
          </th>`
        )
        .join("")}
      <th scope="col" class="ds-table__plate">Plaque <span class="ds-optional">lasermark, facultative</span></th>
      <th scope="col" class="ds-table__actions" aria-label="Actions"></th>
    </tr>`;
  const body = split.rows
    .map(
      (row, i) => `<tr data-row="${i}">
        <td class="mono ds-table__idx">${i + 1}</td>
        <td><input class="field ds-cell" data-row="${i}" data-col="label" value="${escapeHtml(row.label)}" placeholder="${i === 0 ? "ex : réf" : ""}" aria-label="Nom de la plaque ${i + 1}" maxlength="80" autocomplete="off"></td>
        ${split.factors
          .map(
            (factor, j) =>
              `<td><input class="field ds-cell" data-row="${i}" data-col="${j}" value="${escapeHtml(row.values[j] || "")}" aria-label="${escapeHtml(factor || `Colonne ${j + 1}`)} de la plaque ${i + 1}" maxlength="200" autocomplete="off"></td>`
          )
          .join("")}
        <td><input class="field mono ds-cell" data-row="${i}" data-col="sample_id" value="${escapeHtml(row.sample_id)}" placeholder="à associer" aria-label="Lasermark de la plaque ${i + 1}" list="entity-sample-id-history" autocomplete="off">${
          row.fdl && row.fdl.length ? `<div class="ds-row-fdl">${fdlChipsHtml(row.fdl, { label: false })}</div>` : ""
        }</td>
        <td class="ds-table__actions">
          <button class="ds-icon-btn" type="button" data-remove-row="${i}" aria-label="Retirer la plaque ${i + 1}" title="Retirer la plaque"${split.rows.length <= 1 ? " disabled" : ""}>${REMOVE_ICON}</button>
        </td>
      </tr>`
    )
    .join("");
  wrap.innerHTML = `<table class="ds-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
  updateSplitNote();
}

function updateSplitNote() {
  const named = split.rows.filter((row) => row.sample_id.trim()).length;
  const count = split.rows.length;
  document.getElementById("ds-split-note").textContent =
    `${count} plaque${count > 1 ? "s" : ""}` + (named ? ` · ${named} nommée${named > 1 ? "s" : ""}` : "");
  document.getElementById("ds-add-row").disabled = count >= DS_MAX_ROWS;
  document.getElementById("ds-add-factor").disabled = split.factors.length >= DS_MAX_FACTORS;
}

function focusCell(row, col) {
  const cell = document.querySelector(`#ds-table-wrap [data-row="${row}"][data-col="${col}"]`);
  if (cell) cell.focus();
}

function addRow() {
  if (split.rows.length >= DS_MAX_ROWS) return;
  split.rows.push(blankRow());
  renderSplitTable();
  focusCell(split.rows.length - 1, split.factors.length ? 0 : "label");
}

function addFactor() {
  if (split.factors.length >= DS_MAX_FACTORS) return;
  split.factors.push("");
  split.rows.forEach((row) => row.values.push(""));
  renderSplitTable();
  const input = document.querySelector(`#ds-table-wrap [data-factor="${split.factors.length - 1}"]`);
  if (input) input.focus();
}

function mountSplitTable() {
  const wrap = document.getElementById("ds-table-wrap");
  wrap.addEventListener("input", (event) => {
    const target = event.target;
    clearError();
    if (target.dataset.factor !== undefined) {
      split.factors[Number(target.dataset.factor)] = target.value;
      return;
    }
    const row = split.rows[Number(target.dataset.row)];
    if (!row) return;
    const col = target.dataset.col;
    if (col === "label") row.label = target.value;
    else if (col === "sample_id") {
      row.sample_id = target.value;
      updateSplitNote();
    } else row.values[Number(col)] = target.value;
  });
  wrap.addEventListener("click", (event) => {
    const removeRow = event.target.closest("[data-remove-row]");
    if (removeRow && split.rows.length > 1) {
      split.rows.splice(Number(removeRow.dataset.removeRow), 1);
      renderSplitTable();
      return;
    }
    const removeFactor = event.target.closest("[data-remove-factor]");
    if (removeFactor) {
      const j = Number(removeFactor.dataset.removeFactor);
      split.factors.splice(j, 1);
      split.rows.forEach((row) => row.values.splice(j, 1));
      renderSplitTable();
    }
  });
  // Entrée sur la dernière ligne : une plaque de plus ; sinon la case du dessous
  wrap.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const target = event.target;
    if (target.dataset.row === undefined) return;
    event.preventDefault();
    const i = Number(target.dataset.row);
    if (i === split.rows.length - 1) {
      split.rows.push(blankRow());
      renderSplitTable();
    }
    focusCell(i + 1, target.dataset.col);
  });
  // un bloc copié d'Excel (tabulations, retours à la ligne) remplit le tableau à partir de la case
  wrap.addEventListener("paste", (event) => {
    const target = event.target;
    if (target.dataset.row === undefined) return;
    const text = (event.clipboardData || window.clipboardData).getData("text");
    if (!/[\t\n]/.test(text.replace(/\r?\n$/, ""))) return;
    event.preventDefault();
    pasteBlock(Number(target.dataset.row), target.dataset.col, text);
  });
}

// Les colonnes d'une ligne dans l'ordre où on les lit : nom, colonnes du split, plaque.
function columnOrder() {
  return ["label", ...split.factors.map((_, j) => String(j)), "sample_id"];
}

function pasteBlock(startRow, startCol, text) {
  const lines = text.replace(/\r/g, "").replace(/\n$/, "").split("\n").map((line) => line.split("\t"));
  const width = Math.max(...lines.map((cells) => cells.length));
  // un bloc plus large que le tableau : autant de colonnes de split en plus (elles se placent avant
  // la plaque, qui reste la dernière colonne)
  if (startCol !== "sample_id") {
    const missing = columnOrder().indexOf(String(startCol)) + width - columnOrder().length;
    for (let k = 0; k < missing && split.factors.length < DS_MAX_FACTORS; k++) {
      split.factors.push("");
      split.rows.forEach((row) => row.values.push(""));
    }
  }
  const columns = columnOrder();
  const startIndex = columns.indexOf(String(startCol));
  lines.forEach((cells, di) => {
    const i = startRow + di;
    if (i >= DS_MAX_ROWS) return;
    while (split.rows.length <= i) split.rows.push(blankRow());
    const row = split.rows[i];
    cells.forEach((raw, dj) => {
      const key = columns[startIndex + dj];
      const value = raw.trim();
      if (key === undefined) return;
      if (key === "label") row.label = value;
      else if (key === "sample_id") row.sample_id = value;
      else row.values[Number(key)] = value;
    });
  });
  renderSplitTable();
}

// --- envoyer ----------------------------------------------------------------------------------------

function collectPayload() {
  const title = document.getElementById("exp-title").value.trim();
  const intent = document.getElementById("exp-intent").value.trim();
  if (imageDrop.isUploading()) return { error: "Une image est encore en cours d'envoi - un instant.", focus: null };
  if (!title) return { error: "Le titre est obligatoire.", focus: document.getElementById("exp-title") };
  if (!intent) return { error: "L'intention est obligatoire.", focus: document.getElementById("exp-intent") };
  const unnamed = split.factors.findIndex((factor) => !factor.trim());
  if (unnamed >= 0) {
    return { error: "Donnez un titre à chaque colonne du split (ce qu'on change), ou retirez-la.", focus: document.querySelector(`#ds-table-wrap [data-factor="${unnamed}"]`) };
  }
  if (!split.rows.length) return { error: "Le split compte au moins une plaque.", focus: document.getElementById("ds-add-row") };
  const images = imageDrop.get();
  const payload = {
    structure: {
      kind: "declared",
      description: document.getElementById("ds-description").value,
      images: images.map((img) => ({ ...img, caption: (img.caption || "").trim() || null })),
      factors: split.factors.map((factor) => factor.trim()),
      wafers: split.rows.map((row) => ({ label: row.label.trim() || null, values: row.values.map((v) => (v || "").trim()) })),
    },
    title,
    intent,
    hypothesis: document.getElementById("exp-hypothesis").value.trim() || null,
    context: document.getElementById("exp-context").value,
    objectives: state.objectives,
    // une place par ligne, à sa place (une ligne sans lasermark reste à associer)
    entities: split.rows.map((row) => ({ sample_id: row.sample_id.trim() || null, location: row.location || null, fdl: row.fdl || [] })),
    fdl: studyFdlField.get(),
    form_answers: intentFormSection ? intentFormSection.collect() : {},
  };
  if (planId && launchedPlan) payload.plan_id = launchedPlan.id;
  if (evolveExperienceId && planId) {
    payload.from_version = { experiment_id: evolveExperienceId, version_id: parentDetail ? parentDetail.version_id : null };
  } else if (evolveExperienceId && document.getElementById("branch-fork").checked) {
    const branchName = document.getElementById("new-branch-name").value.trim();
    if (!branchName) return { error: "Donnez un nom à la nouvelle piste.", focus: document.getElementById("new-branch-name") };
    payload.branch = branchName;
    payload.from_version = { experiment_id: evolveExperienceId, version_id: parentDetail ? parentDetail.version_id : null };
  }
  return { payload };
}

async function launch() {
  clearError();
  const { payload, error, focus } = collectPayload();
  if (error) {
    showError(new Error(error));
    if (focus) focus.focus();
    return;
  }
  const button = document.getElementById("launch-btn");
  button.disabled = true;
  try {
    const result =
      evolveExperienceId && !payload.from_version
        ? await experimentsApi.evolve(slug, evolveExperienceId, parentDetail && parentDetail.version_id, payload)
        : await experimentsApi.create(slug, payload);
    window.location.href = `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(result.id)}`;
  } catch (err) {
    const formMessage = intentFormSection && intentFormSection.errorMessage(err);
    showError(formMessage ? new Error(formMessage) : err);
    button.disabled = false;
  }
}

// --- préremplir -----------------------------------------------------------------------------------

function setImages(images) {
  imageDrop.set(images || []);
  updateDrawingCount();
  if ((images || []).length) document.getElementById("ds-drawing").open = true;
}

function updateDrawingCount() {
  const count = imageDrop ? imageDrop.get().length : 0;
  document.getElementById("ds-drawing-count").textContent = count ? `${count} image${count > 1 ? "s" : ""}` : "";
}

async function loadParent() {
  const detail = evolveVersionId
    ? await experimentsApi.getVersion(slug, evolveExperienceId, evolveVersionId)
    : await experimentsApi.get(slug, evolveExperienceId);
  parentDetail = detail;
  const declared = detail.declared_structure;
  if (declared) {
    document.getElementById("ds-description").value = declared.description || "";
    setImages(declared.images);
    split.factors = [...declared.factors];
  }
  if (planId) {
    // une expérience prévue : une nouvelle piste, sur de nouvelles plaques - le split de départ, sans ses plaques
    if (declared) split.rows = declared.wafers.map((w) => ({ ...blankRow(), label: w.label || "", values: [...w.values] }));
    return detail;
  }
  if (!detail.is_tip) forceNewBranch();
  document.getElementById("exp-title").value = detail.title;
  document.getElementById("exp-intent").value = detail.intent;
  document.getElementById("exp-hypothesis").value = detail.hypothesis || "";
  document.getElementById("exp-context").value = detail.context || "";
  const verification = detail.objective_verification || {};
  state.objectives = detail.objectives.map((o) => ({ ...o, verification_method: verification[o.name] || null }));
  renderObjectives();
  if (intentFormSection) intentFormSection.fill(detail.form_answers);
  studyFdlField.set(detail.fdl || []);
  const tracking = detail.physical_tracking || [];
  if (declared) {
    split.rows = declared.wafers.map((w, i) => ({
      label: w.label || "",
      values: [...w.values],
      sample_id: (tracking[i] && tracking[i].sample_id) || "",
      fdl: (tracking[i] && tracking[i].fdl) || [],
      location: (tracking[i] && tracking[i].location) || null,
    }));
  } else {
    // une étude dessinée qu'on poursuit sans structure : ses plaques, une ligne chacune
    split.rows = (tracking.length ? tracking : [{}]).map((e) => ({ ...blankRow(), sample_id: e.sample_id || "", fdl: e.fdl || [], location: e.location || null }));
  }
  return detail;
}

// Une expérience prévisionnelle qu'on lance (?prevision=) : son titre, son intention, une ligne par
// plaque prévue. Lancée ou supprimée entre-temps : on lance sans elle.
async function loadPlan() {
  if (!planId) return;
  try {
    launchedPlan = await experimentsApi.getPlan(slug, planId);
  } catch (err) {
    showError(err.status === 404 ? new Error("Cette expérience prévisionnelle n'existe plus (déjà lancée ou supprimée) : l'expérience se lancera sans elle.") : err);
    return;
  }
  document.getElementById("exp-title").value = launchedPlan.title;
  if (launchedPlan.intent) document.getElementById("exp-intent").value = launchedPlan.intent;
  const planned = launchedPlan.mode === "new_wafers" ? Math.min(DS_MAX_ROWS, launchedPlan.wafer_count || 1) : null;
  if (planned && split.rows.length < planned) {
    while (split.rows.length < planned) split.rows.push(blankRow());
  }
}

// Une version passée : on n'écrit jamais que sur la pointe d'une piste, on en part donc sur une nouvelle.
function forceNewBranch() {
  document.getElementById("branch-fork").checked = true;
  document.getElementById("branch-continue").disabled = true;
  document.getElementById("new-branch-name").hidden = false;
}

async function loadEntityHistory() {
  try {
    const history = waferSuggestions(await wafersApi.list({ microproject: slug }));
    document.getElementById("entity-sample-id-history").innerHTML = history.sample_ids.map((v) => `<option value="${escapeHtml(v)}">`).join("");
    document.getElementById("entity-fdl-history").innerHTML = (history.fdls || []).map((v) => `<option value="${escapeHtml(v)}">`).join("");
  } catch (err) {
    // autocomplétion seulement
  }
}

async function initDeclaredStructurePage() {
  const base = `/microprojets/${encodeURIComponent(slug)}`;
  const builderLink = document.getElementById("builder-link");
  const imageLink = document.getElementById("image-link");
  const cancelLink = document.getElementById("cancel-link");
  const query = window.location.search;
  if (evolveExperienceId && planId) {
    setPageTitle("Lancer une expérience prévue · sans structure");
    builderLink.href = `${base}/experiences/${encodeURIComponent(evolveExperienceId)}/evoluer${query}`;
    imageLink.href = `${base}/experiences/${encodeURIComponent(evolveExperienceId)}/evoluer-image${query}`;
    cancelLink.href = base;
  } else if (evolveExperienceId) {
    setPageTitle("Éditer la fiche · sans structure");
    document.getElementById("launch-btn").textContent = "Enregistrer les modifications";
    document.getElementById("branch-choice-wrap").hidden = false;
    builderLink.href = `${base}/experiences/${encodeURIComponent(evolveExperienceId)}/evoluer${query}`;
    imageLink.href = `${base}/experiences/${encodeURIComponent(evolveExperienceId)}/evoluer-image${query}`;
    cancelLink.href = `${base}/experiences/${encodeURIComponent(evolveExperienceId)}${query}`;
  } else {
    setPageTitle("Nouvelle expérience · sans structure");
    builderLink.href = `${base}/structures/nouvelle${planId ? `?prevision=${planId}` : ""}`;
    imageLink.href = `${base}/structures/image${planId ? `?prevision=${planId}` : ""}`;
    cancelLink.href = base;
  }

  studyFdlField = mountFdlField(document.getElementById("exp-study-fdl"), { datalistId: "entity-fdl-history", label: "FDL de l'étude" });
  document.querySelector("#exp-study-fdl .fdl-field__input").id = "exp-study-fdl-input";
  imageDrop = mountImageDrop(document.getElementById("image-drop"), {
    slug,
    compact: true,
    // une image collée n'importe où (le dessin replié) l'ouvre
    onChange: (images) => {
      clearError();
      updateDrawingCount();
      if (images && images.length) document.getElementById("ds-drawing").open = true;
    },
    onError: showError,
    // pas quand une fenêtre est ouverte par-dessus
    isActive: () => !document.querySelector("dialog[open]"),
  });

  split.rows = [blankRow()];
  mountSplitTable();
  document.getElementById("ds-add-row").addEventListener("click", addRow);
  document.getElementById("ds-add-factor").addEventListener("click", addFactor);
  document.getElementById("launch-btn").addEventListener("click", launch);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      launch();
    }
  });
  document.getElementById("branch-continue").addEventListener("change", () => {
    document.getElementById("new-branch-name").hidden = true;
  });
  document.getElementById("branch-fork").addEventListener("change", () => {
    document.getElementById("new-branch-name").hidden = false;
    document.getElementById("new-branch-name").focus();
  });
  document.getElementById("objective-form").addEventListener("submit", () => {
    if (document.getElementById("obj-name").value === "") document.getElementById("objective-add").open = false;
  });

  renderObjectives();
  renderSplitTable();
  loadEntityHistory();
  try {
    const microproject = await microprojectsApi.get(slug);
    if (microproject.role !== "editor" && microproject.role !== "owner") {
      showError(new Error("Vous n'avez qu'un accès en lecture à ce µprojet : impossible d'y lancer une expérience."));
      document.getElementById("launch-btn").disabled = true;
    }
    const label = microproject.code ? `${microproject.code} · ${microproject.name}` : microproject.name;
    document.getElementById("crumb").innerHTML = `/ <a href="${base}">${escapeHtml(label)}</a> / ${escapeHtml(document.getElementById("page-title").textContent)}`;
    if (pluginEnabled("intent_forms")) {
      intentFormSection = await mountIntentFormSection(document.getElementById("intent-form-box"), { microprojectSlug: slug, onError: showError });
    }
    if (evolveExperienceId) await loadParent();
    await loadPlan();
    renderSplitTable();
  } catch (err) {
    showError(err);
  }
  if (!evolveExperienceId) document.getElementById("exp-title").focus({ preventScroll: true });
}

document.addEventListener("DOMContentLoaded", initDeclaredStructurePage);
