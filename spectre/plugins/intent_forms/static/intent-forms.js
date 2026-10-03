/* Bibliothèque de formulaires d'intention d'un µprojet (spectre.plugins.intent_forms) : lesquels
   sont disponibles (partagés entre µprojets, propres à ce µprojet), lequel est actif - une copie de
   l'entrée activée, qu'il faut réactiver pour y reporter une modification -, l'ajout d'un nouveau
   depuis un fichier YAML, le renommage, le remplacement et la suppression d'une entrée. */

const { slug } = routeParams("/microprojets/{slug}/formulaire-intention");
document.getElementById("crumb").textContent = "/ " + slug;
document.getElementById("microproject-link").href = `/microprojets/${slug}`;

let currentRole = null;
let activeForm = null; // {form, origin: {form_id, name} | null, outdated} | null
let library = []; // [{id, name, scope, microproject, created_by, updated_by, can_edit, form}]

function canActivate() {
  return currentRole === "editor" || currentRole === "owner";
}

function fieldTypeLabel(type) {
  return { string: "texte court", text: "texte long", number: "nombre", boolean: "oui/non", choice: "choix" }[type] || type;
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Lecture du fichier impossible."));
    reader.readAsText(file);
  });
}

async function run(action) {
  clearError();
  try {
    await action();
    await loadAll();
  } catch (err) {
    showError(err);
  }
}

function originLabel() {
  const origin = activeForm.origin;
  if (!origin) return "posé directement dans le dépôt du µprojet";
  const entry = library.find((e) => e.id === origin.form_id);
  if (!entry) return `copie de « ${origin.name} », retiré depuis de la bibliothèque`;
  return `copie de « ${entry.name} »${entry.scope === "shared" ? " · partagé" : ""}`;
}

function renderActiveForm() {
  const box = document.getElementById("active-form-box");
  if (!activeForm) {
    box.innerHTML = "Aucun formulaire actif - le titre et l'intention libres suffisent.";
    return;
  }
  const rows = activeForm.form.fields
    .map(
      (f) => `<tr>
        <td>${escapeHtml(f.label)}</td>
        <td class="mono" style="font-size:11.5px;color:var(--text-faint);">${escapeHtml(fieldTypeLabel(f.type))}</td>
        <td>${f.required ? "obligatoire" : "optionnel"}</td>
      </tr>`
    )
    .join("");
  const canReactivate = canActivate() && activeForm.outdated && activeForm.origin;
  box.innerHTML = `
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-bottom:8px;">
      <div><strong>${escapeHtml(activeForm.form.title)}</strong> <span style="color:var(--text-faint);font-size:12px;">(${escapeHtml(originLabel())})</span></div>
      ${canActivate() ? `<button class="btn btn-line" id="deactivate-btn" type="button" style="padding:5px 10px;font-size:12px;">Désactiver</button>` : ""}
    </div>
    ${
      activeForm.outdated
        ? `<div class="flash" style="margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;gap:12px;">
            <span>L'entrée de bibliothèque a été modifiée depuis son activation : ce µprojet applique encore la version ci-dessous.</span>
            ${canReactivate ? `<button class="btn btn-primary" id="reactivate-btn" type="button" style="padding:5px 10px;font-size:12px;">Réactiver</button>` : ""}
          </div>`
        : ""
    }
    ${activeForm.form.description ? `<p class="help" style="margin-bottom:8px;">${escapeHtml(activeForm.form.description)}</p>` : ""}
    <table style="width:100%;font-size:12.5px;border-collapse:collapse;">
      <thead><tr style="color:var(--text-faint);text-align:left;"><th>Question</th><th>Type</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  const deactivateBtn = document.getElementById("deactivate-btn");
  if (deactivateBtn) deactivateBtn.addEventListener("click", () => run(() => intentFormsApi.deactivate(slug)));
  const reactivateBtn = document.getElementById("reactivate-btn");
  if (reactivateBtn) reactivateBtn.addEventListener("click", () => run(() => intentFormsApi.activate(slug, activeForm.origin.form_id)));
}

function libraryEntryRow(entry) {
  const isOrigin = activeForm && activeForm.origin && activeForm.origin.form_id === entry.id;
  const isActive = isOrigin && !activeForm.outdated;
  const questions = `${entry.form.fields.length} question${entry.form.fields.length > 1 ? "s" : ""}`;
  const author = entry.created_by ? ` · par ${escapeHtml(entry.created_by)}` : "";
  const edited = entry.updated_by && entry.updated_by !== entry.created_by ? `, modifié par ${escapeHtml(entry.updated_by)}` : "";
  const buttons = [];
  if (canActivate() && !isActive) {
    buttons.push(`<button class="btn btn-line js-activate" type="button" data-id="${escapeHtml(entry.id)}" style="padding:5px 10px;font-size:12px;">${isOrigin ? "Réactiver" : "Activer"}</button>`);
  }
  if (entry.can_edit) {
    buttons.push(`<button class="btn btn-line js-delete-form" type="button" data-id="${escapeHtml(entry.id)}" style="padding:5px 10px;font-size:12px;">Supprimer</button>`);
  }
  return `
    <div class="step-row" style="align-items:flex-start;flex-wrap:wrap;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(entry.name)} ${isActive ? '<span class="badge badge-role">actif</span>' : ""}</div>
        <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(entry.form.title)} · ${questions}${entry.scope === "shared" ? " · partagé" : ""}${author}${edited}</div>
      </div>
      ${buttons.length ? `<div style="display:flex;gap:6px;">${buttons.join("")}</div>` : ""}
      ${
        entry.can_edit
          ? `<details style="flex-basis:100%;font-size:12.5px;">
              <summary style="cursor:pointer;color:var(--link);">Modifier</summary>
              <div class="field-group" style="margin-top:8px;">
                <div><label>Nom</label><input class="field js-edit-name" value="${escapeHtml(entry.name)}"></div>
                <div><label>Remplacer par un fichier YAML (optionnel)</label><input class="field js-edit-file" type="file" accept=".yml,.yaml,text/yaml"></div>
                <button class="btn btn-line js-save-form" type="button" data-id="${escapeHtml(entry.id)}">Enregistrer</button>
              </div>
            </details>`
          : ""
      }
    </div>`;
}

function renderLibrary() {
  const box = document.getElementById("library-list");
  if (!library.length) {
    box.innerHTML = `<div class="card card-pad" style="color:var(--text-faint);font-size:13.5px;">Aucun formulaire dans la bibliothèque pour l'instant.</div>`;
    return;
  }
  box.innerHTML = `<div class="card card-pad" style="display:flex;flex-direction:column;gap:4px;">${library.map(libraryEntryRow).join('<div style="border-top:1px solid var(--border-soft);"></div>')}</div>`;

  box.querySelectorAll(".js-activate").forEach((btn) => {
    btn.addEventListener("click", () => run(() => intentFormsApi.activate(slug, btn.dataset.id)));
  });
  box.querySelectorAll(".js-delete-form").forEach((btn) => {
    btn.addEventListener("click", () => {
      const entry = library.find((e) => e.id === btn.dataset.id);
      const scope = entry.scope === "shared" ? " de la bibliothèque partagée (tous les µprojets la voient)" : "";
      if (!window.confirm(`Supprimer « ${entry.name} »${scope} ? Les µprojets qui l'ont activé gardent leur copie.`)) return;
      run(() => intentFormsApi.remove(entry.id));
    });
  });
  box.querySelectorAll(".js-save-form").forEach((btn) => {
    btn.addEventListener("click", () => {
      const panel = btn.closest("details");
      const name = panel.querySelector(".js-edit-name").value.trim();
      const file = panel.querySelector(".js-edit-file").files[0];
      run(async () => {
        const body = { name };
        if (file) body.yaml = await readFile(file);
        await intentFormsApi.update(btn.dataset.id, body);
      });
    });
  });
}

async function loadAll() {
  try {
    [library, activeForm] = await Promise.all([intentFormsApi.list({ microproject: slug }), intentFormsApi.getActive(slug)]);
    renderActiveForm();
    renderLibrary();
  } catch (err) {
    showError(err);
  }
}

function clearError() {
  document.getElementById("error").style.display = "none";
}
function showError(err) {
  const box = document.getElementById("error");
  box.textContent = err.message || String(err);
  box.style.display = "block";
}

document.getElementById("upload-form-btn").addEventListener("click", () => {
  const name = document.getElementById("new-form-name").value.trim();
  const fileInput = document.getElementById("new-form-file");
  const shared = document.getElementById("new-form-shared").checked;
  if (!name || !fileInput.files[0]) {
    showError(new Error("Choisissez un nom et un fichier .yml."));
    return;
  }
  run(async () => {
    const yaml = await readFile(fileInput.files[0]);
    await intentFormsApi.create({ name, yaml, scope: shared ? "shared" : "microproject", microproject: shared ? null : slug });
    document.getElementById("new-form-name").value = "";
    fileInput.value = "";
    document.getElementById("new-form-shared").checked = false;
  });
});

async function init() {
  try {
    const microproject = await microprojectsApi.get(slug);
    currentRole = microproject.role;
  } catch (err) {
    showError(err);
  }
  await loadAll();
}

init();
