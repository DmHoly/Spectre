/* « Comment on le démontre » : les objectifs de l'étude (métrique, sens, cible, vérification prévue,
   pourquoi), chacun avec son résultat une fois conclue ; puis les réponses au formulaire d'intention
   du µprojet. */

(() => {
  const OBJECTIVE_DIRECTION_TEXT = { observe: "observer", maximize: "maximiser", minimize: "minimiser", target: "cible" };
  const ICONS = {
    met: '<path d="M5 13l4 4L19 7"/>',
    not_met: '<path d="M6 6l12 12M18 6L6 18"/>',
    partially_met: '<path d="M5 12h14"/>',
    inconclusive: '<path d="M12 17h.01"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/>',
    pending: '<circle cx="12" cy="12" r="3" fill="currentColor"/>',
  };

  function renderObjectives(ctx) {
    const { detail } = ctx;
    const list = document.getElementById("objectives-list");
    if (detail.objectives.length === 0) {
      list.innerHTML = `<li class="hero-objectives__empty">Aucun objectif défini${
        ctx.canEdit ? ` - <button type="button" class="fiche-hero__add js-add-objectives" data-report-hide>ajouter les objectifs</button>` : ""
      }.</li>`;
      const add = list.querySelector(".js-add-objectives");
      if (add) add.addEventListener("click", () => (window.location.href = ExperiencePage.evolveUrl({ stage: "intention" })));
      return;
    }
    const results = detail.conclusion.objective_results || [];
    const verification = detail.objective_verification || {};
    list.innerHTML = detail.objectives
      .map((o) => {
        const result = results.find((r) => r.objective === o.name);
        const status = result ? result.status : "pending";
        const statusText = result ? ExperimentVocabulary.objectiveStatuses[result.status] || result.status : "À vérifier";
        const how = [o.metric, OBJECTIVE_DIRECTION_TEXT[o.direction] || o.direction, o.target != null ? `cible ${o.target}` : ""].filter(Boolean).join(" · ");
        const observed = result && result.observed ? `observé ${result.observed.value}${result.observed.unit ? " " + result.observed.unit : ""}` : "";
        return `
          <li class="hero-objective hero-objective--${status}">
            <span class="hero-objective__icon" aria-hidden="true"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">${ICONS[status] || ICONS.pending}</svg></span>
            <div class="hero-objective__body">
              <div class="hero-objective__head">
                <span class="hero-objective__name">${escapeHtml(o.name)}</span>
                <span class="hero-objective__status">${escapeHtml(statusText)}</span>
              </div>
              ${how || observed ? `<div class="hero-objective__how mono">${escapeHtml([how, observed].filter(Boolean).join(" — "))}</div>` : ""}
              ${verification[o.name] ? `<div class="hero-objective__verif">Vérification&nbsp;: ${escapeHtml(verification[o.name])}</div>` : ""}
              ${o.rationale ? `<div class="hero-objective__why">Pourquoi&nbsp;: ${escapeHtml(o.rationale)}</div>` : ""}
            </div>
          </li>`;
      })
      .join("");
  }

  // Les réponses au formulaire d'intention du µprojet, avec les libellés du formulaire actif quand on
  // les retrouve - une étude plus ancienne a pu être répondue à un formulaire modifié depuis : le nom
  // brut du champ sert alors de repli plutôt que de cacher la réponse.
  async function renderIntentFormAnswers(ctx) {
    const box = document.getElementById("intent-form-info-box");
    const answers = ctx.detail.form_answers || {};
    if (Object.keys(answers).length === 0) {
      box.style.display = "none";
      return;
    }
    let activeForm = null;
    try {
      const active = await intentFormsApi.getActive(ctx.microprojectSlug);
      activeForm = active ? active.form : null; // aucun formulaire actif : les noms de champs bruts
    } catch (err) {
      // formulaire actif indisponible : les noms de champs bruts
    }
    const fieldByName = new Map((activeForm ? activeForm.fields : []).map((f) => [f.name, f]));
    const rows = Object.entries(answers)
      .map(([name, value]) => {
        const field = fieldByName.get(name);
        const text = field && field.type === "boolean" ? (value ? "Oui" : "Non") : String(value);
        return `<div class="fiche-hero__answer"><dt>${escapeHtml(field ? field.label : name)}</dt><dd>${escapeHtml(text)}</dd></div>`;
      })
      .join("");
    box.innerHTML = `<div class="fiche-hero__label">${escapeHtml(activeForm ? activeForm.title : "Formulaire d'intention")}</div><dl class="fiche-hero__answers-list">${rows}</dl>`;
    box.style.display = "block";
  }

  ExperiencePage.registerPanel({
    key: "objectives",
    mount(el, ctx) {
      renderObjectives(ctx);
      return renderIntentFormAnswers(ctx);
    },
  });
})();
