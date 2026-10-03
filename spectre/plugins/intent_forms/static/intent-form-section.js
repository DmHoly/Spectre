/* Section « formulaire d'intention » des pages qui lancent ou font évoluer une expérience
   (constructeur, structure en images) : rend les questions du formulaire actif du µprojet
   (follow.storage.commit_form.CommitForm) sous les champs titre/intention/hypothèse, puis les
   recueille dans le payload. Aucun µprojet n'en a par défaut : la boîte reste masquée tant
   qu'aucun formulaire n'est actif (voir /microprojets/{slug}/formulaire-intention).

     const section = await mountIntentFormSection(el, { microprojectSlug, onError });
     section.fill(answers);          // réponses de la version de départ (évolution)
     section.collect();              // -> {nom du champ: réponse}
     section.errorMessage(err);      // le détail d'un refus du formulaire (422), ou null

   Le contexte est passé en paramètre : rien n'est lu dans les globales de la page hôte. */

async function mountIntentFormSection(el, { microprojectSlug, onError }) {
  let form = null; // {title, description, fields} | null

  function inputId(field) {
    return `intent-field-${field.name}`;
  }

  function inputHtml(field) {
    const attrs = `id="${escapeHtml(inputId(field))}" data-field="${escapeHtml(field.name)}"`;
    if (field.type === "text") return `<textarea ${attrs} rows="2" class="field"></textarea>`;
    if (field.type === "number") return `<input type="number" ${attrs} class="field" step="any">`;
    if (field.type === "boolean") return `<input type="checkbox" ${attrs} style="width:auto;">`;
    if (field.type === "choice") {
      const options = (field.choices || []).map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
      return `<select ${attrs} class="field"><option value="">—</option>${options}</select>`;
    }
    return `<input type="text" ${attrs} class="field">`;
  }

  function render() {
    if (!form) {
      el.style.display = "none";
      el.innerHTML = "";
      return;
    }
    el.style.display = "";
    el.innerHTML = `
      <div class="section-title" style="margin-bottom:6px;">${escapeHtml(form.title)}</div>
      ${form.description ? `<div class="help" style="margin-bottom:12px;">${escapeHtml(form.description)}</div>` : ""}
      <div style="display:flex;flex-direction:column;gap:10px;">
        ${form.fields
          .map(
            (field) => `
          <div>
            <label>${escapeHtml(field.label)}${field.required ? " *" : ""}</label>
            ${inputHtml(field)}
            ${field.help ? `<div class="help">${escapeHtml(field.help)}</div>` : ""}
          </div>`
          )
          .join("")}
      </div>`;
  }

  function input(field) {
    return el.querySelector(`[data-field="${CSS.escape(field.name)}"]`);
  }

  try {
    const active = await intentFormsApi.getActive(microprojectSlug);
    form = active ? active.form : null;
  } catch (err) {
    form = null;
    if (onError) onError(err);
  }
  render();

  return {
    fill(answers) {
      if (!form || !answers) return;
      for (const field of form.fields) {
        const target = input(field);
        const value = answers[field.name];
        if (!target || value === undefined || value === null) continue;
        if (field.type === "boolean") target.checked = Boolean(value);
        else target.value = value;
      }
    },

    collect() {
      if (!form) return {};
      const answers = {};
      for (const field of form.fields) {
        const target = input(field);
        if (!target) continue;
        if (field.type === "boolean") {
          answers[field.name] = target.checked;
        } else if (field.type === "number") {
          if (target.value !== "") answers[field.name] = parseFloat(target.value);
        } else if (target.value !== "") {
          answers[field.name] = target.value;
        }
      }
      return answers;
    },

    // Un refus du formulaire par le serveur (422, detail = {message, errors: [...]}) : affiché en
    // entier plutôt que le seul message général.
    errorMessage(err) {
      const detail = err && err.data && err.data.detail;
      if (detail && typeof detail === "object" && Array.isArray(detail.errors)) {
        return `${detail.message}\n- ${detail.errors.join("\n- ")}`;
      }
      return null;
    },
  };
}
