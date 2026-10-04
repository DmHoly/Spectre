/* Page /bibliotheque : hub global (commun à tous les µprojets). Liste les structures, présets et
   briques intégrés et partagés - sans µprojet - et permet à leur auteur (ou à un administrateur) de
   renommer ou supprimer un élément partagé. Composer une structure ou une brique passe par le
   constructeur, qui vit sous un µprojet (simulation) : d'où le sélecteur "µprojet de travail",
   mémorisé en local, qui ne sert qu'à ouvrir ces éditeurs. */

const WORK_MICROPROJECT_KEY = "spectre.libWorkMicroproject";

const SCOPE_LABELS = { builtin: "intégré", shared: "partagé" };

const COLLECTIONS = [
  {
    listId: "shared-structures",
    noun: "la structure",
    list: () => processLibraryApi.savedStructures(),
    update: (id, changes) => processLibraryApi.updateSavedStructure(id, changes),
    remove: (id) => processLibraryApi.deleteSavedStructure(id),
    summary: (item) => `${item.steps.length} étape(s)`,
    editorHref: (s, item) => `/microprojets/${s}/structures/bibliotheque/${encodeURIComponent(item.id)}?retour=bibliotheque`,
  },
  {
    listId: "shared-presets",
    noun: "le préset",
    list: () => processLibraryApi.stepPresets(),
    update: (id, changes) => processLibraryApi.updateStepPreset(id, changes),
    remove: (id) => processLibraryApi.deleteStepPreset(id),
    summary: (item) => `${item.payload.kind === "etch" ? "Gravure" : "Dépôt"} · ${item.payload.recipe}`,
    editorHref: (s) => `/microprojets/${s}/presets-etapes`,
  },
  {
    listId: "shared-bricks",
    noun: "la brique",
    list: () => processLibraryApi.techBricks(),
    update: (id, changes) => processLibraryApi.updateTechBrick(id, changes),
    remove: (id) => processLibraryApi.deleteTechBrick(id),
    summary: (item) => `${item.steps.length} étape(s)`,
    editorHref: (s, item) => `/microprojets/${s}/briques-technologiques/bibliotheque/${encodeURIComponent(item.id)}?retour=bibliotheque`,
  },
];

let workSlug = null;
const loaded = new Map(); // listId -> éléments affichés

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

function rememberedMicroproject() {
  try {
    return localStorage.getItem(WORK_MICROPROJECT_KEY);
  } catch {
    return null;
  }
}

function itemRow(collection, item) {
  const author = item.created_by && item.created_by.name ? ` · par ${escapeHtml(item.created_by.name)}` : "";
  const s = workSlug ? encodeURIComponent(workSlug) : null;
  const actions = [];
  if (s && item.can_edit) {
    actions.push(`<a class="btn btn-line" href="${collection.editorHref(s, item)}" style="padding:5px 10px;font-size:12px;">Modifier</a>`);
  }
  if (item.can_edit) {
    actions.push(`<button class="btn btn-line js-rename" data-id="${escapeHtml(item.id)}" type="button" style="padding:5px 10px;font-size:12px;">Renommer</button>`);
    actions.push(
      `<button class="btn btn-line js-remove" data-id="${escapeHtml(item.id)}" type="button" style="padding:5px 10px;font-size:12px;color:var(--danger);">Supprimer</button>`
    );
  }
  return `
    <div class="step-row" style="align-items:flex-start;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(item.name)}
          <span style="font-weight:400;font-size:11px;color:var(--text-faint);">· ${SCOPE_LABELS[item.scope] || escapeHtml(item.scope)}${author}</span>
        </div>
        <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(collection.summary(item))}</div>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">${actions.join("")}</div>
    </div>`;
}

function renderCollection(collection) {
  const items = loaded.get(collection.listId) || [];
  const host = document.getElementById(collection.listId);
  host.innerHTML = items.length ? items.map((item) => itemRow(collection, item)).join("") : `<div class="help">Rien pour l'instant.</div>`;
  const find = (id) => items.find((item) => item.id === id);
  host.querySelectorAll(".js-rename").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const item = find(btn.dataset.id);
      const name = item && window.prompt(`Nouveau nom pour ${collection.noun} « ${item.name} » :`, item.name);
      if (!name || !name.trim() || name.trim() === item.name) return;
      await changeCollection(collection, () => collection.update(item.id, { name: name.trim() }));
    });
  });
  host.querySelectorAll(".js-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const item = find(btn.dataset.id);
      if (!item) return;
      const warning = item.scope === "shared" ? " Cet élément est partagé : il disparaîtra de tous les µprojets." : "";
      if (!window.confirm(`Supprimer ${collection.noun} « ${item.name} » ?${warning}`)) return;
      await changeCollection(collection, () => collection.remove(item.id));
    });
  });
}

async function loadCollection(collection) {
  loaded.set(collection.listId, await collection.list());
  renderCollection(collection);
}

async function changeCollection(collection, change) {
  clearError();
  try {
    await change();
    await loadCollection(collection);
  } catch (err) {
    showError(err);
  }
}

function applyMicroproject(microproject) {
  // microproject = { slug, role } ou null : seulement pour ouvrir le constructeur et la page des présets
  workSlug = microproject ? microproject.slug : null;
  document.querySelectorAll(".js-needs-microproject").forEach((el) => (el.style.display = microproject ? "" : "none"));
  COLLECTIONS.forEach(renderCollection);
  if (!microproject) return;
  try {
    localStorage.setItem(WORK_MICROPROJECT_KEY, microproject.slug);
  } catch {
    /* mode privé : on continue sans mémoriser */
  }
  const s = encodeURIComponent(microproject.slug);
  const set = (id, href) => {
    const el = document.getElementById(id);
    if (el) el.href = href;
  };
  set("new-structure-link", `/microprojets/${s}/structures/bibliotheque/nouvelle?retour=bibliotheque&partagee=1`);
  set("presets-link", `/microprojets/${s}/presets-etapes?partagee=1`);
  set("new-brick-link", `/microprojets/${s}/briques-technologiques/bibliotheque/nouvelle?retour=bibliotheque&partagee=1`);
}

async function initWorkMicroproject() {
  const microprojects = await microprojectsApi.list();
  if (microprojects.length === 0) {
    document.getElementById("no-microproject-msg").style.display = "";
    applyMicroproject(null);
    return;
  }
  const select = document.getElementById("work-microproject");
  select.innerHTML = microprojects.map((p) => `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}</option>`).join("");
  const remembered = rememberedMicroproject();
  const initial = microprojects.find((p) => p.slug === remembered) || microprojects[0];
  select.value = initial.slug;
  document.getElementById("work-microproject-row").style.display = microprojects.length > 1 ? "" : "none";
  applyMicroproject(initial);
  select.addEventListener("change", () => {
    const chosen = microprojects.find((p) => p.slug === select.value);
    if (chosen) applyMicroproject(chosen);
  });
}

async function init() {
  try {
    await Promise.all(COLLECTIONS.map(loadCollection));
  } catch (err) {
    showError(err);
  }
  try {
    await initWorkMicroproject();
  } catch (err) {
    showError(err);
  }
}

init();
