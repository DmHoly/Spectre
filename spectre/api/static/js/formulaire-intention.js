/* Bibliothèque de formulaires d'intention d'un µprojet (spectre.core.intent_forms) : lesquels sont
   disponibles (partagés entre projets, propres à ce µprojet), lequel est actif, et l'ajout d'un
   nouveau depuis un fichier YAML. */

const slug = window.location.pathname.split("/").filter(Boolean)[1];
document.getElementById("crumb").textContent = "/ " + slug;
document.getElementById("microproject-link").href = `/microprojets/${slug}`;

let currentRole = null;
let activeForm = null; // {name, scope, form} | null

function fieldTypeLabel(type) {
  return { string: "texte court", text: "texte long", number: "nombre", boolean: "oui/non", choice: "choix" }[type] || type;
}

function renderActiveForm() {
  const box = document.getElementById("active-form-box");
  if (!activeForm) {
    box.innerHTML = "Aucun formulaire actif - le titre et l'intention libres suffisent.";
    return;
  }
  const canEdit = currentRole === "editor" || currentRole === "owner";
  const rows = activeForm.form.fields
    .map(
      (f) => `<tr>
        <td>${escapeHtml(f.label)}</td>
        <td class="mono" style="font-size:11.5px;color:var(--text-faint);">${escapeHtml(fieldTypeLabel(f.type))}</td>
        <td>${f.required ? "obligatoire" : "optionnel"}</td>
      </tr>`
    )
    .join("");
  box.innerHTML = `
    <div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px;">
      <div><strong>${escapeHtml(activeForm.form.title)}</strong> <span style="color:var(--text-faint);font-size:12px;">(${escapeHtml(activeForm.name)}${activeForm.scope === "partagee" ? " · partagé" : ""})</span></div>
      ${canEdit ? `<button class="btn btn-line" id="deactivate-btn" style="padding:5px 10px;font-size:12px;">Désactiver</button>` : ""}
    </div>
    ${activeForm.form.description ? `<p class="help" style="margin-bottom:8px;">${escapeHtml(activeForm.form.description)}</p>` : ""}
    <table style="width:100%;font-size:12.5px;border-collapse:collapse;">
      <thead><tr style="color:var(--text-faint);text-align:left;"><th>Question</th><th>Type</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  const deactivateBtn = document.getElementById("deactivate-btn");
  if (deactivateBtn) {
    deactivateBtn.addEventListener("click", async () => {
      try {
        await api.post(`/api/microprojets/${slug}/formulaire-actif`, { name: null });
        await loadAll();
      } catch (err) {
        showError(err);
      }
    });
  }
}

function libraryEntryRow(entry) {
  const canEdit = currentRole === "editor" || currentRole === "owner";
  const isActive = activeForm && activeForm.name === entry.name && (activeForm.scope === "partagee") === (entry.scope === "partagee");
  return `
    <div class="step-row" style="align-items:flex-start;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(entry.name)} ${isActive ? '<span class="badge badge-role">actif</span>' : ""}</div>
        <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(entry.form.title)} · ${entry.form.fields.length} question${entry.form.fields.length > 1 ? "s" : ""}${entry.scope === "partagee" ? " · partagé" : ""}</div>
      </div>
      ${
        canEdit
          ? `<div style="display:flex;gap:6px;">
              ${!isActive ? `<button class="btn btn-line js-activate" data-name="${escapeHtml(entry.name)}" data-partagee="${entry.scope === "partagee"}" style="padding:5px 10px;font-size:12px;">Activer</button>` : ""}
              <button class="btn btn-line js-delete-form" data-name="${escapeHtml(entry.name)}" data-partagee="${entry.scope === "partagee"}" style="padding:5px 10px;font-size:12px;">Supprimer</button>
            </div>`
          : ""
      }
    </div>`;
}

function renderLibrary(library) {
  const entries = [...library.partagees, ...library.microprojet];
  const box = document.getElementById("library-list");
  if (!entries.length) {
    box.innerHTML = `<div class="card card-pad" style="color:var(--text-faint);font-size:13.5px;">Aucun formulaire dans la bibliothèque pour l'instant.</div>`;
    return;
  }
  box.innerHTML = `<div class="card card-pad" style="display:flex;flex-direction:column;gap:4px;">${entries.map(libraryEntryRow).join('<div style="border-top:1px solid var(--border-soft);"></div>')}</div>`;

  box.querySelectorAll(".js-activate").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api.post(`/api/microprojets/${slug}/formulaire-actif`, { name: btn.dataset.name, partagee: btn.dataset.partagee === "true" });
        await loadAll();
      } catch (err) {
        showError(err);
      }
    });
  });
  box.querySelectorAll(".js-delete-form").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api.del(`/api/microprojets/${slug}/formulaires-intention/${encodeURIComponent(btn.dataset.name)}?partagee=${btn.dataset.partagee}`);
        await loadAll();
      } catch (err) {
        showError(err);
      }
    });
  });
}

async function loadAll() {
  clearError();
  try {
    const [library, active] = await Promise.all([
      api.get(`/api/microprojets/${slug}/formulaires-intention`),
      api.get(`/api/microprojets/${slug}/formulaire-actif`),
    ]);
    activeForm = active;
    renderActiveForm();
    renderLibrary(library);
  } catch (err) {
    showError(err);
  }
}

function clearError() {
  document.getElementById("error").style.display = "none";
}
function showError(err) {
  const box = document.getElementById("error");
  const detail = err && err.data && err.data.detail;
  box.textContent = detail && typeof detail === "object" ? JSON.stringify(detail) : err.message || String(err);
  box.style.display = "block";
}

document.getElementById("upload-form-btn").addEventListener("click", () => {
  clearError();
  const name = document.getElementById("new-form-name").value.trim();
  const fileInput = document.getElementById("new-form-file");
  const partagee = document.getElementById("new-form-shared").checked;
  if (!name || !fileInput.files[0]) {
    showError(new Error("Choisissez un nom et un fichier .yml."));
    return;
  }
  const reader = new FileReader();
  reader.onload = async () => {
    try {
      await api.post(`/api/microprojets/${slug}/formulaires-intention`, { name, yaml: reader.result, partagee });
      document.getElementById("new-form-name").value = "";
      fileInput.value = "";
      document.getElementById("new-form-shared").checked = false;
      await loadAll();
    } catch (err) {
      showError(err);
    }
  };
  reader.readAsText(fileInput.files[0]);
});

async function init() {
  try {
    const microproject = await api.get(`/api/microprojets/${slug}`);
    currentRole = microproject.role;
  } catch (err) {
    showError(err);
  }
  await loadAll();
}

init();
