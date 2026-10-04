/* Onglet « Conclusion » : la conclusion d'une étude conclue (résumé, décision, suite, réponse à
   chaque objectif et les données du cahier qui l'appuient), ou le formulaire pour la rédiger -
   prérempli quand on la modifie, ou quand une étude rouverte garde ses réponses.

   Le verdict d'un objectif cite des entrées du cahier (`evidence_ids`, le champ de Follow, qui
   désignait les anciennes preuves : une preuve convertie garde son id). Leurs titres viennent du
   panneau du cahier, qui les déclare à la fiche après coup (ctx.notebook, ExperiencePage.onNotebook) :
   les citations se complètent alors sans toucher à la saisie en cours. */

(() => {
  const { decisions, objectiveStatuses } = ExperimentVocabulary;
  let current = null; // {el, ctx, cited: [Set d'ids par objectif] | null} : ce qui est affiché

  function notebookEntries(ctx) {
    return (ctx.notebook && ctx.notebook.entries) || [];
  }

  // « Données : titre, titre » sous un verdict (vide tant que le cahier n'est pas lu)
  function citesHtml(ctx, ids) {
    if (!ids.length || !ctx.notebook) return "";
    const titles = new Map(notebookEntries(ctx).map((entry) => [entry.id, entry.title]));
    return `<span class="conclusion-cites__label">Données :</span> ${ids
      .map((id) => (titles.has(id) ? `<a href="#donnees">${escapeHtml(titles.get(id))}</a>` : `<span class="conclusion-cites__missing">donnée introuvable</span>`))
      .join(", ")}`;
  }

  // Les entrées du cahier à cocher sous un objectif : celles qui lui sont liées d'abord.
  function citeChoicesHtml(ctx, objective, cited, i) {
    if (!ctx.notebook) return `<span class="help" style="margin:0;">Lecture du cahier…</span>`;
    const entries = notebookEntries(ctx);
    if (!entries.length) return `<span class="help" style="margin:0;">Le cahier n'a pas encore de donnée à citer.</span>`;
    const linked = (entry) => entry.objective === objective.name;
    return [...entries.filter(linked), ...entries.filter((entry) => !linked(entry))]
      .map(
        (entry) => `<label class="conclusion-cite"><input type="checkbox" value="${escapeHtml(entry.id)}" data-cite="${i}"${cited.has(entry.id) ? " checked" : ""}> <span>${escapeHtml(entry.title)}</span>${
          linked(entry) ? ` <span class="conclusion-cite__tag">liée à cet objectif</span>` : ""
        }${entry.applies === false ? ` <span class="conclusion-cite__tag">autre plaque</span>` : ""}</label>`
      )
      .join("");
  }

  function refreshCites() {
    if (!current || !current.el.isConnected) return;
    const { el, ctx, cited } = current;
    el.querySelectorAll("[data-cites]").forEach((box) => {
      const result = ctx.detail.conclusion.objective_results[Number(box.dataset.cites)];
      box.innerHTML = citesHtml(ctx, (result && result.evidence_ids) || []);
    });
    if (cited) {
      el.querySelectorAll("[data-cite-choices]").forEach((box) => {
        const i = Number(box.dataset.citeChoices);
        box.innerHTML = citeChoicesHtml(ctx, ctx.detail.objectives[i], cited[i], i);
      });
    }
  }

  ExperiencePage.onNotebook(refreshCites);
  const isConcluded = (detail) => detail.status === "concluded" || detail.status === "abandoned";
  const optionsHtml = (labels) => Object.entries(labels).map(([value, label]) => `<option value="${value}">${escapeHtml(label)}</option>`).join("");

  function concludedViewHtml(detail) {
    const c = detail.conclusion;
    const answers = c.objective_results
      .map((r, i) => {
        const objective = detail.objectives.find((o) => o.name === r.objective);
        return `
          <div style="padding:8px 0;border-top:1px solid var(--border-soft);">
            <div style="font-size:13px;font-weight:600;">${escapeHtml(r.objective)}</div>
            ${objective && objective.rationale ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:1px;">${escapeHtml(objective.rationale)}</div>` : ""}
            <div style="font-size:12.5px;color:var(--text-soft);margin-top:4px;">${escapeHtml(objectiveStatuses[r.status] || r.status)}${r.reasoning ? " — " + escapeHtml(r.reasoning) : ""}</div>
            <div class="conclusion-cites" data-cites="${i}"></div>
          </div>`;
      })
      .join("");
    return `
      <div class="section-title" style="margin-bottom:14px;">Conclusion</div>
      ${c.summary ? `<p style="font-size:13.5px;line-height:1.6;margin-bottom:10px;">${escapeHtml(c.summary)}</p>` : ""}
      ${c.decision ? `<div style="font-size:12.5px;color:var(--text-soft);">Décision&nbsp;: <strong>${escapeHtml(decisions[c.decision] || c.decision)}</strong></div>` : ""}
      ${c.next_steps ? `<div style="font-size:12.5px;color:var(--text-soft);margin-top:4px;">Suite&nbsp;: ${escapeHtml(c.next_steps)}</div>` : ""}
      ${answers ? `<div style="margin-top:14px;">${answers}</div>` : ""}`;
  }

  function render(el, ctx) {
    const { detail } = ctx;
    current = { el, ctx, cited: null };
    if (isConcluded(detail)) {
      el.innerHTML =
        concludedViewHtml(detail) +
        (ctx.canEdit ? `<button class="btn btn-line" type="button" data-report-hide style="margin-top:16px;padding:5px 12px;font-size:12px;">Modifier la conclusion</button>` : "");
      el.querySelector("button")?.addEventListener("click", () => renderForm(el, ctx, detail.conclusion));
      refreshCites();
      return;
    }
    if (!ctx.canEdit) {
      el.innerHTML = `<div class="section-title" style="margin-bottom:14px;">Conclusion</div><div class="help" style="font-style:italic;">Pas encore conclue — expérience en cours.</div>`;
      return;
    }
    const c = detail.conclusion || {};
    const hasPrior = (c.objective_results || []).length > 0 || c.summary || c.decision || c.next_steps;
    renderForm(el, ctx, hasPrior ? c : null);
  }

  // `prefill` : la conclusion à modifier (ou celle d'une étude rouverte), null pour une première.
  function renderForm(el, ctx, prefill) {
    const { detail } = ctx;
    const editing = Boolean(prefill);
    const canCancel = isConcluded(detail); // revenir à la conclusion affichée
    const verification = detail.objective_verification || {};
    // les entrées citées par objectif : celles de la conclusion modifiée, puis ce qu'on coche
    const cited = detail.objectives.map((o) => new Set(((prefill && prefill.objective_results) || []).find((r) => r.objective === o.name)?.evidence_ids || []));
    current = { el, ctx, cited };
    el.innerHTML = `
      <div class="section-title" style="margin-bottom:14px;">${editing ? "Modifier la conclusion" : "Conclure l'expérience"}</div>
      <span class="report-only help" style="font-style:italic;">Pas encore conclue — expérience en cours.</span>
      <form class="field-group" data-report-hide>
        <div>${detail.objectives
          .map(
            (o, i) => `
          <div style="margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid var(--border-soft);">
            <label for="obj-result-${i}" style="margin-bottom:2px;">${escapeHtml(o.name)}</label>
            ${o.rationale ? `<div style="font-size:11.5px;color:var(--text-faint);margin-bottom:2px;">Pourquoi&nbsp;: ${escapeHtml(o.rationale)}</div>` : ""}
            ${verification[o.name] ? `<div style="font-size:11.5px;color:var(--text-faint);margin-bottom:6px;">Vérification prévue&nbsp;: ${escapeHtml(verification[o.name])}</div>` : ""}
            <select class="field" id="obj-result-${i}" style="margin-bottom:6px;">${optionsHtml(objectiveStatuses)}</select>
            <textarea class="field" id="obj-reasoning-${i}" rows="2" placeholder="Réponse : qu'a-t-on constaté ?" aria-label="Réponse pour ${escapeHtml(o.name)}"></textarea>
            <fieldset class="conclusion-cites-form">
              <legend>Données du cahier qui l'appuient</legend>
              <div class="conclusion-cites-form__list" data-cite-choices="${i}"></div>
            </fieldset>
          </div>`
          )
          .join("")}</div>
        <div><label for="conclude-summary">Résumé</label><textarea class="field" id="conclude-summary" rows="2"></textarea></div>
        <div class="field-row">
          <div><label for="conclude-decision">Décision</label>
            <select class="field" id="conclude-decision"><option value="">—</option>${optionsHtml(decisions)}</select>
          </div>
          <div><label for="conclude-status">Statut final</label>
            <select class="field" id="conclude-status">
              <option value="concluded">Conclue</option>
              <option value="abandoned">Abandonnée</option>
            </select>
          </div>
        </div>
        <div><label for="conclude-next-steps">Prochaine étape (optionnelle)</label><input class="field" id="conclude-next-steps"></div>
        <div style="display:flex;gap:10px;">
          <button class="btn btn-primary" style="flex:1;" type="submit">${editing ? "Enregistrer les modifications" : "Enregistrer la conclusion"}</button>
          ${canCancel ? `<button class="btn btn-line js-cancel" type="button">Annuler</button>` : ""}
        </div>
      </form>`;
    const field = (id) => el.querySelector(`#${id}`);
    el.querySelector(".js-cancel")?.addEventListener("click", () => render(el, ctx));
    el.querySelector("form").addEventListener("change", (event) => {
      const box = event.target.closest("[data-cite]");
      if (!box) return;
      const ids = cited[Number(box.dataset.cite)];
      if (box.checked) ids.add(box.value);
      else ids.delete(box.value);
    });
    refreshCites();

    if (prefill) {
      field("conclude-summary").value = prefill.summary || "";
      field("conclude-decision").value = prefill.decision || "";
      field("conclude-status").value = prefill.status === "abandoned" ? "abandoned" : "concluded";
      field("conclude-next-steps").value = prefill.next_steps || "";
      (prefill.objective_results || []).forEach((r) => {
        const i = detail.objectives.findIndex((o) => o.name === r.objective);
        if (i < 0) return;
        field(`obj-result-${i}`).value = r.status;
        field(`obj-reasoning-${i}`).value = r.reasoning || "";
      });
    }

    el.querySelector("form").addEventListener("submit", (event) => {
      event.preventDefault();
      // une citation qui ne désigne plus aucune entrée du cahier lu serait refusée (422) : elle tombe
      const known = ctx.notebook ? new Set(notebookEntries(ctx).map((entry) => entry.id)) : null;
      const previous = (name) => ((prefill && prefill.objective_results) || []).find((r) => r.objective === name) || {};
      const body = {
        status: field("conclude-status").value,
        decision: field("conclude-decision").value || null,
        summary: field("conclude-summary").value || null,
        next_steps: field("conclude-next-steps").value || null,
        objective_results: detail.objectives.map((o, i) => ({
          objective: o.name,
          status: field(`obj-result-${i}`).value,
          reasoning: field(`obj-reasoning-${i}`).value.trim() || null,
          observed: previous(o.name).observed || null, // pas de champ pour elle ici : gardée telle quelle
          evidence_ids: [...cited[i]].filter((id) => !known || known.has(id)),
        })),
      };
      ctx.write(() => experimentsApi.conclude(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, body));
    });
  }

  ExperiencePage.registerPanel({ key: "conclusion", mount: render });
})();
