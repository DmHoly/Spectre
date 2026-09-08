/* Formulaire d'intention : rend dynamiquement les questions du formulaire de commit actif du
   projet (spectre.core.intent_forms / follow.storage.commit_form.CommitForm) sous les champs
   titre/intention/hypothèse, et les recueille dans le payload de lancement/évolution - la même
   relation "schéma -> champs -> collecte" qu'objectives.js, mais pilotée par un formulaire
   configurable (YAML) plutôt qu'un schéma fixe. Aucun µprojet n'en a par défaut : la boîte reste
   masquée tant qu'aucun formulaire n'est actif (voir /projets/{slug}/formulaire-intention). */

let activeIntentForm = null; // {name, scope, form: {title, description, fields}} | null

function intentFieldInputHtml(field) {
  const attrs = `id="intent-field-${field.name}" data-field="${field.name}"`;
  if (field.type === "text") return `<textarea ${attrs} rows="2" class="field"></textarea>`;
  if (field.type === "number") return `<input type="number" ${attrs} class="field" step="any">`;
  if (field.type === "boolean") return `<input type="checkbox" ${attrs} style="width:auto;">`;
  if (field.type === "choice") {
    const options = (field.choices || []).map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
    return `<select ${attrs} class="field"><option value="">—</option>${options}</select>`;
  }
  return `<input type="text" ${attrs} class="field">`;
}

function renderIntentForm() {
  const box = document.getElementById("intent-form-box");
  if (!activeIntentForm) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }
  const form = activeIntentForm.form;
  box.style.display = "";
  box.innerHTML = `
    <div class="section-title" style="margin-bottom:6px;">${escapeHtml(form.title)}</div>
    ${form.description ? `<div class="help" style="margin-bottom:12px;">${escapeHtml(form.description)}</div>` : ""}
    <div style="display:flex;flex-direction:column;gap:10px;">
      ${form.fields
        .map(
          (field) => `
        <div>
          <label>${escapeHtml(field.label)}${field.required ? " *" : ""}</label>
          ${intentFieldInputHtml(field)}
          ${field.help ? `<div class="help">${escapeHtml(field.help)}</div>` : ""}
        </div>`
        )
        .join("")}
    </div>`;
}

// Appelé une fois le détail de l'expérience parente chargé (mode évolution) - voir
// loadExistingProcess dans experience-launch.js, qui appelle ceci après avoir rendu les champs.
function fillIntentFormAnswers(answers) {
  if (!activeIntentForm || !answers) return;
  for (const field of activeIntentForm.form.fields) {
    const el = document.getElementById(`intent-field-${field.name}`);
    const value = answers[field.name];
    if (!el || value === undefined || value === null) continue;
    if (field.type === "boolean") el.checked = Boolean(value);
    else el.value = value;
  }
}

function collectIntentFormAnswers() {
  if (!activeIntentForm) return {};
  const answers = {};
  for (const field of activeIntentForm.form.fields) {
    const el = document.getElementById(`intent-field-${field.name}`);
    if (!el) continue;
    if (field.type === "boolean") {
      answers[field.name] = el.checked;
    } else if (field.type === "number") {
      if (el.value !== "") answers[field.name] = parseFloat(el.value);
    } else if (el.value !== "") {
      answers[field.name] = el.value;
    }
  }
  return answers;
}

// Un rejet de formulaire (spectre.api.structures._form_validation_error) renvoie 422 avec
// detail = {message, errors: [...]} plutôt qu'une simple chaîne - affiché en entier plutôt que
// la seule première ligne qu'showError(err) montrerait sinon.
function intentFormErrorMessage(err) {
  const detail = err && err.data && err.data.detail;
  if (detail && typeof detail === "object" && Array.isArray(detail.errors)) {
    return `${detail.message}\n- ${detail.errors.join("\n- ")}`;
  }
  return null;
}

async function loadIntentForm() {
  try {
    activeIntentForm = await api.get(`/api/microprojets/${slug}/formulaire-actif`);
  } catch (err) {
    activeIntentForm = null;
  }
  renderIntentForm();
}
