/* Page /bibliotheque : hub global (commun à tous les µprojets). Liste les structures, présets et
   briques intégrés et partagés, avec leur propriétaire (et son équipe), et permet de les composer
   dans le constructeur - sans µprojet - et à leur auteur (ou à un administrateur) de les renommer,
   les supprimer ou de donner la main à d'autres comptes et équipes. */


// le type de l'étape d'un préset, comme dans la palette du constructeur
const PRESET_KIND_LABELS = {
  deposition: "Dépôt",
  epitaxial_growth: "Croissance épitaxiale",
  faceted_growth: "Croissance facettée",
  facet_envelope: "Rattrapage des plans",
  lithography: "Lithographie",
  etch: "Gravure",
  resist_strip: "Retrait de résine",
  planarization: "Planarisation",
  chemical: "Étape chimique",
  flip: "Retournement",
};

const SCOPE_LABELS = { builtin: "intégré", shared: "partagé" };

const COLLECTIONS = [
  {
    listId: "shared-structures",
    noun: "la structure",
    list: () => processLibraryApi.savedStructures(),
    setEditors: (id, body) => processLibraryApi.setStructureEditors(id, body),
    update: (id, changes) => processLibraryApi.updateSavedStructure(id, changes),
    remove: (id) => processLibraryApi.deleteSavedStructure(id),
    summary: (item) => `${item.steps.length} étape(s)${usageText(`structure:${item.id}`)}`,
    editorHref: (item) => `/bibliotheque/structures/${encodeURIComponent(item.id)}?retour=bibliotheque`,
  },
  {
    listId: "shared-presets",
    noun: "le préset",
    list: () => processLibraryApi.stepPresets(),
    setEditors: (id, body) => processLibraryApi.setPresetEditors(id, body),
    update: (id, changes) => processLibraryApi.updateStepPreset(id, changes),
    remove: (id) => processLibraryApi.deleteStepPreset(id),
    summary: (item) => `${PRESET_KIND_LABELS[item.step.kind] || item.step.kind} · v${item.version || 1}`,
    editorHref: (item) => `/bibliotheque/presets/${encodeURIComponent(item.id)}?retour=bibliotheque`,
  },
  {
    listId: "shared-bricks",
    noun: "la brique",
    list: () => processLibraryApi.techBricks(),
    setEditors: (id, body) => processLibraryApi.setBrickEditors(id, body),
    update: (id, changes) => processLibraryApi.updateTechBrick(id, changes),
    remove: (id) => processLibraryApi.deleteTechBrick(id),
    summary: (item) => `${item.reference ? "brique de référence · " : ""}${item.substrate ? "brique de départ · " : ""}${item.steps.length} étape(s) · v${item.version || "1.0"}${usageText(item.id)}`,
    editorHref: (item) => `/bibliotheque/briques/${encodeURIComponent(item.id)}?retour=bibliotheque`,
  },
];

const loaded = new Map(); // listId -> éléments affichés
let usages = {}; // id de brique, ou `structure:<id>` -> les études qui en ont une copie (GET /api/tech-brick-usages)

// « · utilisée dans N études » pour une brique ou une structure insérée comme brique
function usageText(key) {
  const uses = usages[key];
  if (!uses || !uses.length) return "";
  return ` · utilisée dans ${uses.length} étude${uses.length > 1 ? "s" : ""}`;
}

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

function itemRow(collection, item) {
  const author = item.created_by && item.created_by.name ? ` · par ${escapeHtml(item.created_by.name)}` : "";
  const actions = [];
  const href = collection.editorHref(item);
  if (item.can_edit) {
    actions.push(`<a class="btn btn-line" href="${href}" style="padding:5px 10px;font-size:12px;">Modifier</a>`);
  } else {
    actions.push(`<a class="btn btn-line" href="${href}&dupliquer=1" style="padding:5px 10px;font-size:12px;">Dupliquer</a>`);
  }
  if (item.can_manage_access) {
    actions.push(`<button class="btn btn-line js-access" data-id="${escapeHtml(item.id)}" type="button" style="padding:5px 10px;font-size:12px;">Accès</button>`);
  }
  if (item.can_edit) {
    actions.push(`<button class="btn btn-line js-rename" data-id="${escapeHtml(item.id)}" type="button" style="padding:5px 10px;font-size:12px;">Renommer</button>`);
  }
  if (item.can_manage_access) {
    actions.push(
      `<button class="btn btn-line js-remove" data-id="${escapeHtml(item.id)}" type="button" style="padding:5px 10px;font-size:12px;color:var(--danger);">Supprimer</button>`
    );
  }
  return `
    <div class="step-row" style="align-items:flex-start;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(item.name)}
          <span style="font-weight:400;font-size:11px;color:var(--text-faint);">· ${SCOPE_LABELS[item.scope] || escapeHtml(item.scope)}${author}</span>
          ${LibraryAccess.badgesHtml(item)}
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
  host.querySelectorAll(".js-access").forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = find(btn.dataset.id);
      if (!item) return;
      LibraryAccess.open(item, {
        save: (body) => collection.setEditors(item.id, body),
        onSaved: () => loadCollection(collection),
      });
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

async function init() {
  try {
    usages = await processLibraryApi.techBrickUsages({}).catch(() => ({})); // un renseignement : la page s'en passe
    await Promise.all(COLLECTIONS.map(loadCollection));
  } catch (err) {
    showError(err);
  }
}

init();
