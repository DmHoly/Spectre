/* Le contexte d'une plaque, sur sa page (global `PlateContext`) : pourquoi elle est là et ce qu'on a
   compris grâce à elle. Deux sources :

   - les études des µprojets qui la suivent (dont on est membre) : leur contexte, ce qu'elles veulent
     démontrer, leur hypothèse, leurs objectifs et leur réponse, leur conclusion - lus dans
     occurrence.experiment.story (GET /api/wafers/{key}) ;
   - les notes de la plaque, écrites ici (PUT /api/wafers/{key}/notes) : pourquoi elle est là, ce
     qu'on voulait voir, ce qu'on a compris - surtout quand aucune étude ne la suit.

     PlateContext.render(host, plate)

   Dépend de wafersApi, statusBadgeHtml (experiments/status.js), escapeHtml, formatDate. */

const PlateContext = (() => {
  const DECISIONS = { promote: "promouvoir", branch: "poursuivre en variante", replicate: "répliquer", abandon: "abandonner", inconclusive: "non concluant" };
  const RESULTS = { met: "atteint", achieved: "atteint", passed: "atteint", partial: "en partie", partially_met: "en partie", not_met: "pas atteint", failed: "pas atteint", inconclusive: "non concluant" };
  const NOTE_FIELDS = [
    { key: "context", label: "Pourquoi elle est là", placeholder: "Le contexte : d'où elle vient, pourquoi on l'a lancée ou gardée…" },
    { key: "hypothesis", label: "Ce qu'on voulait voir", placeholder: "L'hypothèse, la question posée à cette plaque…" },
    { key: "learnings", label: "Ce qu'on a compris grâce à elle", placeholder: "Les résultats, ce qu'elle a appris, la suite…" },
  ];

  function textHtml(label, text) {
    if (!text) return "";
    return `<div class="plate-context__field"><div class="plate-detail__label">${escapeHtml(label)}</div><p>${escapeHtml(text)}</p></div>`;
  }

  function storyHtml(o) {
    const exp = o.experiment;
    const mp = exp.microproject;
    const story = exp.story || {};
    const conclusion = story.conclusion;
    const objectives = (story.objectives || []).filter((x) => x.name);
    const body = [
      textHtml("Contexte", story.context),
      textHtml("Ce qu'on veut démontrer", story.intent),
      textHtml("Hypothèse", story.hypothesis),
      objectives.length
        ? `<div class="plate-context__field"><div class="plate-detail__label">Objectifs</div><ul class="plate-context__objectives">${objectives
            .map(
              (x) => `<li><strong>${escapeHtml(x.name)}</strong>${x.status ? ` <span class="plate-tag plate-tag--mute">${escapeHtml(RESULTS[x.status] || x.status)}</span>` : ""}${
                x.reasoning ? `<span class="plate-context__answer">${escapeHtml(x.reasoning)}</span>` : ""
              }</li>`
            )
            .join("")}</ul></div>`
        : "",
      conclusion && (conclusion.summary || conclusion.decision || conclusion.next_steps)
        ? `<div class="plate-context__field plate-context__conclusion"><div class="plate-detail__label">Ce qu'on a compris - conclusion${conclusion.decision ? ` · ${escapeHtml(DECISIONS[conclusion.decision] || conclusion.decision)}` : ""}</div>${
            conclusion.summary ? `<p>${escapeHtml(conclusion.summary)}</p>` : ""
          }${conclusion.next_steps ? `<p class="plate-context__next"><strong>Suite :</strong> ${escapeHtml(conclusion.next_steps)}</p>` : ""}</div>`
        : "",
    ].join("");
    return `
      <article class="card plate-context__card">
        <header class="plate-context__head">
          ${statusBadgeHtml(exp.status)}
          <a class="fiche-code" href="/microprojets/${encodeURIComponent(mp.slug)}" title="µprojet ${escapeHtml(mp.name)}">${escapeHtml(mp.code || mp.name)}</a>
          <a class="plate-context__title" href="/microprojets/${encodeURIComponent(mp.slug)}/experiences/${encodeURIComponent(exp.id)}">${escapeHtml(exp.title)}</a>
          ${o.variant ? `<span class="help" style="margin:0;">variante <strong class="mono">${escapeHtml(o.variant)}</strong></span>` : ""}
        </header>
        ${body || `<p class="help" style="margin:0;">Cette étude n'a encore ni contexte, ni hypothèse, ni conclusion.</p>`}
      </article>`;
  }

  function notesViewHtml(notes, alone) {
    const filled = notes && NOTE_FIELDS.some((f) => notes[f.key]);
    return `
      <article class="card plate-context__card plate-context__notes${alone ? " is-alone" : ""}">
        <header class="plate-context__head">
          <span class="plate-context__title">Notes de la plaque</span>
          <button type="button" class="btn btn-line js-notes-edit">${filled ? "Modifier" : "Écrire son contexte"}</button>
        </header>
        ${
          filled
            ? NOTE_FIELDS.map((f) => textHtml(f.label, notes[f.key])).join("") +
              `<p class="help plate-context__by">Écrit par ${escapeHtml(notes.updated_by)}, le ${escapeHtml(formatDate(notes.updated_at))}</p>`
            : `<p class="help" style="margin:0;">${
                alone
                  ? "Aucune étude d'un de vos µprojets ne la suit : dites ici pourquoi elle est là, ce qu'on voulait voir avec elle et ce qu'on a compris grâce à elle."
                  : "Ce que la plaque elle-même a appris, au-delà de ses études."
              }</p>`
        }
      </article>`;
  }

  function notesFormHtml(notes) {
    return `
      <form class="card plate-context__card plate-context__notes is-editing js-notes-form">
        <header class="plate-context__head"><span class="plate-context__title">Notes de la plaque</span></header>
        <div class="error js-notes-error" role="alert" hidden></div>
        ${NOTE_FIELDS.map(
          (f) => `<label class="plate-context__edit"><span class="plate-detail__label">${escapeHtml(f.label)}</span>
            <textarea class="field" name="${f.key}" rows="3" maxlength="4000" placeholder="${escapeHtml(f.placeholder)}">${escapeHtml((notes && notes[f.key]) || "")}</textarea></label>`
        ).join("")}
        <div class="wafer-dialog__actions">
          <button type="button" class="btn btn-line js-notes-cancel">Annuler</button>
          <button type="submit" class="btn btn-primary">Enregistrer</button>
        </div>
      </form>`;
  }

  function render(host, plate) {
    const seen = new Set();
    const studies = plate.occurrences.filter((o) => {
      if (!o.experiment.member || seen.has(o.experiment.id)) return false;
      seen.add(o.experiment.id);
      return true;
    });
    const hidden = plate.occurrences.filter((o) => !o.experiment.member).length;
    let notes = plate.notes;
    let editing = false;

    function draw() {
      const list = host.querySelector(".js-context-list");
      list.innerHTML =
        studies.map(storyHtml).join("") +
        (hidden ? `<p class="help plate-context__hidden">${hidden} étude${hidden > 1 ? "s" : ""} d'un µprojet dont vous n'êtes pas membre la sui${hidden > 1 ? "vent" : "t"} aussi.</p>` : "") +
        (editing ? notesFormHtml(notes) : notesViewHtml(notes, !studies.length));
      const edit = list.querySelector(".js-notes-edit");
      if (edit) edit.addEventListener("click", () => ((editing = true), draw(), list.querySelector("textarea").focus()));
      const form = list.querySelector(".js-notes-form");
      if (!form) return;
      form.querySelector(".js-notes-cancel").addEventListener("click", () => ((editing = false), draw()));
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const body = Object.fromEntries(NOTE_FIELDS.map((f) => [f.key, form.elements[f.key].value]));
        const button = form.querySelector("[type=submit]");
        button.disabled = true;
        try {
          notes = await wafersApi.setNotes(plate.key, body);
          editing = false;
          draw();
        } catch (err) {
          const box = form.querySelector(".js-notes-error");
          box.textContent = err.message || String(err);
          box.hidden = false;
          button.disabled = false;
        }
      });
    }

    draw();
  }

  return { render };
})();
