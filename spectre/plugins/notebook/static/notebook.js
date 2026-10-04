/* Le cahier de données de la fiche (onglet « Données ») : toutes les données de l'étude, le cahier de
   labo repris tel quel dans le rapport téléchargé. Deux types d'entrée (notebook/service.py), une
   seule forme : PRISM (des vues DataViz sur des instantanés des mesures des plaques) et chargée à la
   main (valeur, texte, tableau, images annotées, fichiers, liens - dont les anciennes preuves).

   Chaque entrée montre son titre, son type, ses plaques, son objectif, le stepper du procédé (les
   étapes mesurées en rouge, notebook/static/stepper.js) et ses mesures côte à côte, une par étape,
   pour comparer avant et après ; son interprétation, ses observations (modifiables sur place). Les
   entrées mesurées sur des plaques que la version ne suit pas (`applies: false`) sont rangées,
   repliées, dans « Autres plaques ». Un instantané PRISM est chargé une fois puis gardé en mémoire
   d'un rechargement à l'autre (il ne change jamais).

   Ajouter ou modifier une entrée : la boîte de notebook/static/entry-dialog.js. Chaque changement
   (ajout, modification, note, annotations, ordre, retrait) enregistre une nouvelle version de la
   fiche, avec la version affichée en If-Match (ctx.write).

   Un panneau de la fiche (ExperiencePage.registerPanel) : il lit le cahier de la version affichée
   (notebookApi.entries, et le nombre d'entrées par étape : notebookApi.stepCounts) et le déclare à
   la fiche (ctx.setNotebook) - la vue du procédé en fait ses badges, la conclusion ses citations ;
   un clic sur un badge filtre le cahier sur une étape (ExperiencePage.onNotebookFilter). */

(() => {
  const host = document.getElementById("notebook-entries");
  const filterBar = document.getElementById("notebook-filter");
  let ctx = null;
  let mounts = 0;
  let entries = [];
  let filterStep = null;

  const ICONS = {
    edit: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>`,
    refresh: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/></svg>`,
    up: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>`,
    down: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`,
    remove: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>`,
    file: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M12 12v6M9 15l3 3 3-3"/></svg>`,
    link: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>`,
  };

  // --- instantanés PRISM ---------------------------------------------------------------------------

  const snapshotCache = new Map(); // snapshot_id -> Promise<jeu de données>
  const snapshots = {
    load(snapshotId) {
      if (!snapshotCache.has(snapshotId)) {
        snapshotCache.set(
          snapshotId,
          notebookApi.snapshot(ctx.microprojectSlug, snapshotId).catch((err) => {
            snapshotCache.delete(snapshotId);
            throw err;
          })
        );
      }
      return snapshotCache.get(snapshotId);
    },
    remember(ds) {
      snapshotCache.set(ds.snapshot_id, Promise.resolve(ds));
    },
  };

  // --- étapes, plaques -----------------------------------------------------------------------------

  function processSteps() {
    return (ctx.process && ctx.process.steps) || [];
  }

  function stepperSteps() {
    return processSteps().map((step, i) => ({
      id: step.id,
      label: step.name || ExperimentVocabulary.stepKinds[step.kind] || step.kind,
      title: `${i + 1}. ${ExperimentVocabulary.stepLabel(step)}`,
    }));
  }

  // « Étape 3 · Dépôt — Couche GaN », « Étape retirée », « Non située »
  function measurementTitle(m) {
    if (!m.step_id) return { number: "", text: "Mesure non située" };
    const steps = processSteps();
    const i = steps.findIndex((step) => step.id === m.step_id);
    if (m.step_retired || i < 0) return { number: "–", text: "Étape retirée du procédé" };
    return { number: String(i + 1), text: `Étape ${i + 1} · ${ExperimentVocabulary.stepLabel(steps[i])}` };
  }

  // Les mesures dans l'ordre du procédé (la non située d'abord, les étapes retirées à la fin) : on lit
  // l'avant à gauche, l'après à droite.
  function orderedMeasurements(entry) {
    const order = new Map(processSteps().map((step, i) => [step.id, i]));
    const rank = (m) => (!m.step_id ? -1 : !m.step_retired && order.has(m.step_id) ? order.get(m.step_id) : Number.MAX_SAFE_INTEGER);
    return [...(entry.measurements || [])].sort((a, b) => rank(a) - rank(b));
  }

  function plateLabel(key) {
    const tracked = (ctx.detail.physical_tracking || []).find((e) => e.sample_id && waferKey(e.sample_id) === key);
    return tracked ? tracked.sample_id : key;
  }

  function entryPlates(entry) {
    if ((entry.wafers || []).length) return entry.wafers.map(plateLabel);
    // une entrée qui vaut pour toute la piste : une vue PRISM montre les plaques de son instantané
    return entry.kind === "prism" ? [...new Set(entry.measurements.flatMap((m) => (m.snapshot && m.snapshot.wafers) || []))] : [];
  }

  function formatSize(bytes) {
    if (!bytes && bytes !== 0) return "";
    return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} Mo` : `${Math.max(1, Math.round(bytes / 1024))} ko`;
  }

  // --- écritures -----------------------------------------------------------------------------------

  // Une mesure telle qu'une écriture la renvoie : sans ce que le serveur calcule (étape retirée,
  // résumé de l'instantané, url et description des fichiers) ; une annotation qui ne désigne aucune
  // image de la mesure (une ancienne preuve sans image) n'est pas renvoyée.
  function measurementInput(kind, m) {
    if (kind === "prism") return { step_id: m.step_id, snapshot_id: m.snapshot_id, component: m.component, options: m.options || {} };
    const images = new Set((m.attachments || []).filter((a) => (a.content_type || "").startsWith("image/")).map((a) => a.id));
    return {
      step_id: m.step_id,
      value: m.value || null,
      text: m.text || null,
      table: m.table || null,
      attachments: (m.attachments || []).map((a) => ({ id: a.id, caption: a.caption || null })),
      links: (m.links || []).map((l) => ({ url: l.url, label: l.label || null })),
      annotations: (m.annotations || []).filter((a) => images.has(a.attachment_id) && (a.type === "arrow" || a.type === "box")),
    };
  }

  function writeEntry(entry, changes) {
    return ctx.write(() => notebookApi.updateEntry(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, entry.id, changes));
  }

  // --- une mesure ----------------------------------------------------------------------------------

  // Les annotations d'une image (en % de l'image), dessinées une fois l'image chargée, dans un repère
  // aux proportions de l'image : flèches et cadres gardent leur forme. Pas de <marker> (le rapport
  // retire les id) : la pointe d'une flèche est un triangle.
  function annotationsSvg(annotations, width, height) {
    const ratio = height / width;
    const shapes = annotations
      .map((a) => {
        const x = a.x;
        const y = a.y * ratio;
        const x2 = a.x2 ?? a.x;
        const y2 = (a.y2 ?? a.y) * ratio;
        if (a.type === "arrow") {
          const angle = Math.atan2(y2 - y, x2 - x);
          const head = (side) => `${x2 - 3.2 * Math.cos(angle + side)},${y2 - 3.2 * Math.sin(angle + side)}`;
          return `<g class="nb-annot"><line class="nb-annot__halo" x1="${x}" y1="${y}" x2="${x2}" y2="${y2}"/><line x1="${x}" y1="${y}" x2="${x2}" y2="${y2}"/><polygon points="${x2},${y2} ${head(0.45)} ${head(-0.45)}"/></g>`;
        }
        const rect = `x="${Math.min(x, x2)}" y="${Math.min(y, y2)}" width="${Math.abs(x2 - x)}" height="${Math.abs(y2 - y)}"`;
        return `<g class="nb-annot nb-annot--box"><rect class="nb-annot__halo" ${rect}/><rect ${rect}/></g>`;
      })
      .join("");
    return `<svg class="nb-annots" viewBox="0 0 100 ${100 * ratio}" aria-hidden="true">${shapes}</svg>`;
  }

  function annotationListHtml(annotations, editable) {
    if (!annotations.length) return "";
    return `<ol class="nb-annot-list">${annotations
      .map(
        (a, i) => `<li>${a.type === "arrow" ? "Flèche" : "Cadre"}${a.label ? ` - ${escapeHtml(a.label)}` : ""}${
          editable ? ` <button type="button" class="nb-annot-remove" data-remove-annotation="${i}" data-report-hide aria-label="Retirer l'annotation ${i + 1}">×</button>` : ""
        }</li>`
      )
      .join("")}</ol>`;
  }

  function imageHtml(entry, m, attachment, editable) {
    const mine = (m.annotations || []).filter((a) => a.attachment_id === attachment.id);
    return `
      <figure class="nb-figure" data-attachment="${escapeHtml(attachment.id)}">
        <div class="nb-figure__frame${editable ? " is-editable" : ""}">
          <img src="${escapeHtml(attachment.url)}" alt="${escapeHtml(attachment.caption || attachment.filename || "Image de la mesure")}" draggable="false">
        </div>
        ${attachment.caption ? `<figcaption class="nb-figure__caption">${escapeHtml(attachment.caption)}</figcaption>` : ""}
        <div class="nb-figure__annotations">${annotationListHtml(mine, editable)}</div>
        ${
          editable
            ? `<div class="nb-annot-tools" data-report-hide>
                 <button type="button" class="nb-btn" data-tool="arrow" aria-pressed="false">Flèche</button>
                 <button type="button" class="nb-btn" data-tool="box" aria-pressed="false">Cadre</button>
                 <button type="button" class="btn btn-primary nb-annot-save" hidden>Enregistrer les annotations</button>
                 <span class="nb-annot-hint" role="status"></span>
               </div>`
            : ""
        }
      </figure>`;
  }

  function manualContentHtml(entry, m, editable) {
    const value = m.value
      ? `<div class="nb-value">${m.value.name ? `<span class="nb-value__name">${escapeHtml(m.value.name)}</span>` : ""}<span class="nb-value__number">${escapeHtml(String(m.value.number))}</span>${
          m.value.unit ? `<span class="nb-value__unit">${escapeHtml(m.value.unit)}</span>` : ""
        }</div>`
      : "";
    const text = m.text ? `<div class="nb-note-text">${escapeHtml(m.text)}</div>` : "";
    const table = m.table
      ? `<div class="viz-table-wrap"><table class="viz-table"><thead><tr>${m.table.columns.map((c) => `<th scope="col">${escapeHtml(c)}</th>`).join("")}</tr></thead><tbody>${m.table.rows
          .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell == null ? "" : String(cell))}</td>`).join("")}</tr>`)
          .join("")}</tbody></table></div>`
      : "";
    const attachments = m.attachments || [];
    const images = attachments.filter((a) => (a.content_type || "").startsWith("image/"));
    const documents = attachments.filter((a) => !(a.content_type || "").startsWith("image/"));
    const figures = images.length ? `<div class="nb-figures" data-count="${Math.min(images.length, 2)}">${images.map((a) => imageHtml(entry, m, a, editable)).join("")}</div>` : "";
    const files = documents.length
      ? `<ul class="nb-files">${documents
          .map(
            (a) => `<li class="nb-file">${ICONS.file}<a class="nb-file__name" href="${escapeHtml(a.url)}" download="${escapeHtml(a.filename || "")}">${escapeHtml(a.filename || "fichier")}</a><span class="nb-file__size">${escapeHtml(formatSize(a.size))}</span></li>`
          )
          .join("")}</ul>`
      : "";
    const links = (m.links || []).length
      ? `<ul class="nb-links">${m.links
          .map(
            (l) => `<li class="nb-link">${ICONS.link}<span class="nb-link__text"><a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${escapeHtml(l.label || l.url)}</a>${
              l.label ? `<span class="nb-link__url">${escapeHtml(l.url)}</span>` : ""
            }</span></li>`
          )
          .join("")}</ul>`
      : "";
    const body = value + text + table + figures + files + links;
    return body || `<p class="help" style="margin:0;">Mesure faite à cette étape, sans contenu joint.</p>`;
  }

  function measurementHtml(entry, m, { titled, editable }) {
    const title = measurementTitle(m);
    const snap = m.snapshot || {};
    const head = titled
      ? `<h4 class="nb-measure__step${m.step_retired ? " is-retired" : ""}">${title.number ? `<span class="nb-measure__dot" aria-hidden="true">${escapeHtml(title.number)}</span>` : ""}${escapeHtml(title.text)}</h4>`
      : "";
    const content =
      entry.kind === "prism"
        ? `<div class="nb-measure__viz"><p class="help">Chargement des données…</p></div>${
            snap.fetched_at ? `<div class="nb-measure__src">données du ${escapeHtml(formatDate(snap.fetched_at))}${snap.row_count != null ? ` · ${snap.row_count} ligne${snap.row_count > 1 ? "s" : ""}` : ""}</div>` : ""
          }`
        : manualContentHtml(entry, m, editable);
    return `<section class="nb-measure" data-step="${escapeHtml(m.step_id || "")}">${head}${content}</section>`;
  }

  // --- une entrée ----------------------------------------------------------------------------------

  function entryHtml(entry, { first, last }) {
    const canEdit = ctx.canEdit;
    const prism = entry.kind === "prism";
    const measurements = orderedMeasurements(entry);
    const hook = prism ? (measurements.find((m) => m.snapshot) || {}).snapshot || {} : {};
    const demo = measurements.some((m) => m.snapshot && m.snapshot.source === "demo");
    const plates = entryPlates(entry);
    const situated = measurements.some((m) => m.step_id);
    const showStepper = situated || processSteps().length > 0;
    const actions = canEdit
      ? `<div class="nb-entry__actions" data-report-hide>
          <button type="button" class="nb-btn" data-act="edit">${ICONS.edit}Modifier</button>
          ${prism && measurements.length === 1 ? `<button type="button" class="nb-btn" data-act="refresh" title="Recharger les données de ces plaques depuis la base">${ICONS.refresh}Actualiser</button>` : ""}
          <button type="button" class="nb-btn nb-btn--icon" data-act="up" aria-label="Monter « ${escapeHtml(entry.title)} »" title="Monter"${first ? " disabled" : ""}>${ICONS.up}</button>
          <button type="button" class="nb-btn nb-btn--icon" data-act="down" aria-label="Descendre « ${escapeHtml(entry.title)} »" title="Descendre"${last ? " disabled" : ""}>${ICONS.down}</button>
          <button type="button" class="nb-btn nb-btn--icon nb-btn--danger" data-act="remove" aria-label="Retirer « ${escapeHtml(entry.title)} » du cahier" title="Retirer">${ICONS.remove}</button>
        </div>`
      : "";
    const note = entry.note || "";
    return `
      <article class="nb-entry${entry.in_report === false ? " nb-entry--private" : ""}" data-entry="${escapeHtml(entry.id)}" aria-labelledby="nb-entry-${escapeHtml(entry.id)}"${entry.in_report === false ? " data-report-hide" : ""}>
        <header class="nb-entry__head">
          <div class="nb-entry__heading">
            <h3 class="nb-entry__title" id="nb-entry-${escapeHtml(entry.id)}">${escapeHtml(entry.title)}</h3>
            <div class="nb-entry__meta">
              <span class="nb-chip${prism ? " nb-chip--prism" : ""}">${prism ? `PRISM${hook.hook_title || hook.hook ? ` · ${escapeHtml(hook.hook_title || hook.hook)}` : ""}` : "Donnée manuelle"}</span>
              ${plates.length ? `<span class="nb-entry__plates">${plates.map((w) => `<a class="mono" href="${plateUrl(w)}">${escapeHtml(w)}</a>`).join(", ")}</span>` : ""}
              ${demo ? `<span class="nb-chip nb-chip--demo" title="Données de démonstration, pas des mesures réelles">démo</span>` : ""}
              ${entry.objective ? `<span class="nb-chip nb-chip--objective">Objectif : ${escapeHtml(entry.objective)}</span>` : ""}
              ${entry.in_report === false ? `<span class="nb-chip">hors rapport</span>` : ""}
            </div>
          </div>
          ${actions}
        </header>
        ${showStepper ? `<div class="nb-entry__steps"></div>` : ""}
        <div class="nb-entry__body">
          <div class="nb-entry__viz">
            <div class="nb-measures" data-count="${Math.min(measurements.length, 3)}">${
              measurements.length
                ? measurements.map((m) => measurementHtml(entry, m, { titled: measurements.length > 1 || situated, editable: canEdit && !prism })).join("")
                : `<p class="help" style="margin:0;">Pas encore de mesure.</p>`
            }</div>
            ${entry.interpretation ? `<div class="nb-interpretation"><div class="nb-entry__note-label">Interprétation</div><p class="nb-note-text">${escapeHtml(entry.interpretation)}</p></div>` : ""}
          </div>
          <aside class="nb-entry__note" aria-label="Observations">
            <div class="nb-entry__note-label">Observations</div>
            ${
              canEdit
                ? `<textarea class="field nb-note-input" rows="6" data-report-hide aria-label="Observations sur « ${escapeHtml(entry.title)} »" placeholder="Ce qu'on voit, ce qu'on en conclut, ce qu'il reste à vérifier…">${escapeHtml(note)}</textarea>
                   <div class="nb-note-actions" data-report-hide hidden>
                     <button type="button" class="btn btn-primary nb-note-save">Enregistrer la note</button>
                     <button type="button" class="btn btn-line nb-note-cancel">Annuler</button>
                   </div>
                   <div class="report-only nb-note-text">${escapeHtml(note)}</div>`
                : `<div class="nb-note-text">${note ? escapeHtml(note) : `<span class="help" style="margin:0;">Pas d'observation.</span>`}</div>`
            }
            <div class="nb-entry__by">${escapeHtml(entry.updated_by || entry.created_by || "")} · ${formatDate(entry.updated_at || entry.created_at)}</div>
          </aside>
        </div>
      </article>`;
  }

  function mountEntry(article, entry, position) {
    const steps = article.querySelector(".nb-entry__steps");
    if (steps) {
      const measured = (entry.measurements || []).filter((m) => m.step_id).map((m) => m.step_id);
      mountStepper(steps, {
        steps: stepperSteps(),
        measured,
        retired: (entry.measurements || []).filter((m) => m.step_id && m.step_retired).map((m) => m.step_id),
        label: `Étapes mesurées : ${entry.title}`,
      });
      if (!measured.length) steps.insertAdjacentHTML("beforeend", `<p class="nb-entry__unsituated">Mesure non située dans le procédé.</p>`);
    }
    if (entry.kind === "prism") {
      (entry.measurements || []).forEach((m) => {
        const viz = article.querySelector(`.nb-measure[data-step="${CSS.escape(m.step_id || "")}"] .nb-measure__viz`);
        if (!viz || !m.snapshot_id) return;
        snapshots
          .load(m.snapshot_id)
          .then((ds) => DataViz.render(viz, ds, m.component, m.options || {}))
          .catch((err) => {
            viz.innerHTML = `<div class="viz-empty">Données indisponibles : ${escapeHtml(err.message || String(err))}</div>`;
          });
      });
    }
    article.querySelectorAll(".nb-figure").forEach((figure) => wireFigure(figure, entry));
    if (ctx.canEdit) wireEntry(article, entry, position);
  }

  // Une image : ses annotations dessinées une fois chargée ; pour un éditeur, poser une flèche (clic
  // au départ puis à l'arrivée) ou un cadre (cliquer-glisser), retirer une annotation, puis enregistrer
  // (les annotations de la mesure, par un PATCH de ses mesures).
  function wireFigure(figure, entry) {
    const stepId = figure.closest(".nb-measure").dataset.step || null;
    const measurement = (entry.measurements || []).find((m) => (m.step_id || null) === stepId);
    const attachmentId = figure.dataset.attachment;
    const frame = figure.querySelector(".nb-figure__frame");
    const img = frame.querySelector("img");
    const others = (measurement.annotations || []).filter((a) => a.attachment_id !== attachmentId);
    let local = (measurement.annotations || []).filter((a) => a.attachment_id === attachmentId);
    const editable = frame.classList.contains("is-editable");

    const draw = () => {
      frame.querySelector(".nb-annots")?.remove();
      if (img.naturalWidth && local.length) frame.insertAdjacentHTML("beforeend", annotationsSvg(local, img.naturalWidth, img.naturalHeight));
      figure.querySelector(".nb-figure__annotations").innerHTML = annotationListHtml(local, editable);
    };
    if (img.complete && img.naturalWidth) draw();
    else img.addEventListener("load", draw, { once: true });
    if (!editable) return;

    const tools = figure.querySelector(".nb-annot-tools");
    const hint = tools.querySelector(".nb-annot-hint");
    const save = tools.querySelector(".nb-annot-save");
    let tool = null;
    let start = null;
    const setTool = (next) => {
      tool = next;
      start = null;
      tools.querySelectorAll("[data-tool]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tool === tool)));
      frame.classList.toggle("is-drawing", Boolean(tool));
      hint.textContent = tool === "arrow" ? "Cliquez le départ puis l'arrivée de la flèche." : tool === "box" ? "Cliquez-glissez pour dessiner le cadre." : "";
    };
    const changed = () => {
      save.hidden = false;
      draw();
    };
    const at = (event) => {
      const rect = img.getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100)),
        y: Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100)),
      };
    };
    const finish = (shape) => {
      const label = window.prompt("Libellé de l'annotation (facultatif)");
      local = [...local, { attachment_id: attachmentId, ...shape, label: (label || "").trim() || null }];
      setTool(null);
      changed();
    };
    tools.querySelectorAll("[data-tool]").forEach((btn) => btn.addEventListener("click", () => setTool(tool === btn.dataset.tool ? null : btn.dataset.tool)));
    frame.addEventListener("pointerdown", (event) => {
      if (tool !== "box") return;
      event.preventDefault();
      start = at(event);
    });
    frame.addEventListener("pointerup", (event) => {
      if (tool !== "box" || !start) return;
      const end = at(event);
      if (Math.abs(end.x - start.x) < 1 && Math.abs(end.y - start.y) < 1) return; // un simple clic : pas de cadre
      finish({ type: "box", x: start.x, y: start.y, x2: end.x, y2: end.y });
    });
    frame.addEventListener("click", (event) => {
      if (tool !== "arrow") return;
      const point = at(event);
      if (!start) {
        start = point;
        hint.textContent = "Cliquez l'arrivée de la flèche.";
      } else finish({ type: "arrow", x: start.x, y: start.y, x2: point.x, y2: point.y });
    });
    figure.querySelector(".nb-figure__annotations").addEventListener("click", (event) => {
      const btn = event.target.closest("[data-remove-annotation]");
      if (!btn) return;
      local = local.filter((_, i) => i !== Number(btn.dataset.removeAnnotation));
      changed();
    });
    save.addEventListener("click", () => {
      save.disabled = true;
      writeEntry(entry, {
        measurements: entry.measurements.map((m) => measurementInput(entry.kind, m === measurement ? { ...m, annotations: [...others, ...local] } : m)),
      }).then((done) => {
        if (!done) save.disabled = false;
      });
    });
  }

  function wireEntry(article, entry, position) {
    const note = article.querySelector(".nb-note-input");
    const noteActions = article.querySelector(".nb-note-actions");
    note.addEventListener("input", () => {
      noteActions.hidden = note.value === (entry.note || "");
    });
    article.querySelector(".nb-note-save").addEventListener("click", () => writeEntry(entry, { note: note.value }));
    article.querySelector(".nb-note-cancel").addEventListener("click", () => {
      note.value = entry.note || "";
      noteActions.hidden = true;
    });
    article.querySelector(".nb-entry__actions").addEventListener("click", async (event) => {
      const btn = event.target.closest("[data-act]");
      if (!btn) return;
      const act = btn.dataset.act;
      if (act === "edit") return NotebookEntryDialog.open(ctx, { entry, snapshots });
      if (act === "up" || act === "down") return writeEntry(entry, { position: act === "up" ? position.before : position.after });
      if (act === "remove") {
        if (window.confirm(`Retirer « ${entry.title} » du cahier ? (Elle reste dans l'historique de la fiche.)`)) {
          ctx.write(() => notebookApi.removeEntry(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, entry.id));
        }
        return;
      }
      if (act === "refresh") {
        btn.disabled = true;
        try {
          const [m] = entry.measurements;
          const loaded = m.snapshot || {};
          const ds = await notebookApi.takeSnapshot(ctx.microprojectSlug, { hook: loaded.hook, wafers: loaded.wafers || [], refresh: true });
          snapshots.remember(ds);
          await writeEntry(entry, { measurements: [measurementInput("prism", { ...m, snapshot_id: ds.snapshot_id })] });
        } catch (err) {
          ctx.showError(err);
        }
        btn.disabled = false;
      }
    });
  }

  // --- le cahier -----------------------------------------------------------------------------------

  // Monter ou descendre une entrée parmi celles de son groupe (cette version, autres plaques) : la
  // place, dans le cahier entier, de sa voisine.
  function positions(group) {
    const index = new Map(entries.map((entry, i) => [entry.id, i]));
    return group.map((entry, i) => ({
      first: i === 0,
      last: i === group.length - 1,
      before: i > 0 ? index.get(group[i - 1].id) : null,
      after: i < group.length - 1 ? index.get(group[i + 1].id) : null,
    }));
  }

  function emptyHtml() {
    const marks = [...new Set((ctx.detail.physical_tracking || []).map((e) => e.sample_id).filter(Boolean))];
    return `
      <div class="nb-empty">
        <p><strong>Pas encore de donnée dans ce cahier.</strong></p>
        <p class="help" style="margin:0;">${
          ctx.canEdit
            ? `« Ajouter une donnée » : les mesures ${marks.length ? `des plaques ${marks.map(escapeHtml).join(", ")}` : "des plaques"} en base (EQE, PL, NCEL…), ou ce qu'on a mesuré à la main - une valeur, un tableau, une image, un fichier -, situé dans le procédé. Tout finit dans le rapport.`
            : "Les données mesurées et leurs observations apparaîtront ici."
        }</p>
      </div>`;
  }

  function render() {
    const applying = entries.filter((entry) => entry.applies !== false);
    const others = entries.filter((entry) => entry.applies === false);
    if (!entries.length) {
      host.innerHTML = emptyHtml();
      applyFilter();
      return;
    }
    const applyingPositions = positions(applying);
    const otherPositions = positions(others);
    host.innerHTML = `
      ${applying.length ? applying.map((entry, i) => entryHtml(entry, applyingPositions[i])).join("") : `<p class="help nb-none">Aucune donnée pour les plaques que suit cette version.</p>`}
      ${
        others.length
          ? `<details class="nb-others" data-report-show>
               <summary><span class="nb-others__title">Autres plaques</span> <span class="nb-others__count">${others.length}</span> <span class="nb-others__help">mesurées sur des plaques que cette version ne suit pas</span></summary>
               <div class="nb-entries">${others.map((entry, i) => entryHtml(entry, otherPositions[i])).join("")}</div>
             </details>`
          : ""
      }`;
    applying.forEach((entry, i) => mountEntry(host.querySelector(`[data-entry="${CSS.escape(entry.id)}"]`), entry, applyingPositions[i]));
    others.forEach((entry, i) => mountEntry(host.querySelector(`[data-entry="${CSS.escape(entry.id)}"]`), entry, otherPositions[i]));
    applyFilter();
  }

  // Le filtre sur une étape (un badge de la vue du procédé) : les entrées qui y ont une mesure. Les
  // autres sont masquées à l'écran, pas dans le rapport (data-report-show).
  function applyFilter() {
    const step = filterStep;
    let shown = 0;
    host.querySelectorAll(".nb-entry").forEach((article) => {
      const entry = entries.find((e) => e.id === article.dataset.entry);
      const match = !step || (entry.measurements || []).some((m) => m.step_id === step);
      article.hidden = !match;
      article.toggleAttribute("data-report-show", !match);
      if (match) shown += 1;
    });
    const others = host.querySelector(".nb-others");
    if (others && step) {
      const visible = others.querySelectorAll(".nb-entry:not([hidden])").length;
      others.hidden = !visible;
      if (visible) others.open = true;
    } else if (others) others.hidden = false;
    const none = host.querySelector(".nb-none");
    if (none) none.hidden = Boolean(step);
    filterBar.hidden = !step;
    if (!step) {
      filterBar.innerHTML = "";
      return;
    }
    const i = processSteps().findIndex((s) => s.id === step);
    const name = i < 0 ? "une étape retirée du procédé" : `l'étape ${i + 1} · ${ExperimentVocabulary.stepLabel(processSteps()[i])}`;
    filterBar.innerHTML = `
      <span class="nb-filter__text">${shown ? `<strong>${shown}</strong> donnée${shown > 1 ? "s" : ""} mesurée${shown > 1 ? "s" : ""} à ${escapeHtml(name)}` : `Aucune donnée mesurée à ${escapeHtml(name)}`}</span>
      <button type="button" class="btn btn-line nb-filter__clear">Retirer le filtre</button>`;
  }

  filterBar.addEventListener("click", (event) => {
    if (!event.target.closest(".nb-filter__clear")) return;
    filterStep = null;
    applyFilter();
    document.getElementById("notebook-add-btn").focus({ preventScroll: true });
  });

  ExperiencePage.onNotebookFilter((step) => {
    filterStep = step;
    applyFilter();
    document.getElementById("notebook-card").scrollIntoView({ block: "start" });
    filterBar.querySelector(".nb-filter__clear")?.focus({ preventScroll: true });
  });

  async function load() {
    const seq = (mounts += 1);
    const version = ctx.isTip ? null : ctx.versionId;
    const [list, stepCounts] = await Promise.all([
      notebookApi.entries(ctx.microprojectSlug, ctx.experimentId, version),
      notebookApi.stepCounts(ctx.microprojectSlug, ctx.experimentId, version),
    ]);
    if (seq !== mounts) return; // un rechargement plus récent est en route
    entries = list;
    // le repère de l'onglet « Données » compte les entrées par le détail (notebook_count) ; la vue du
    // procédé et la conclusion lisent ce résumé
    ctx.setNotebook({
      entries: entries.map(({ id, title, kind, objective, applies }) => ({ id, title, kind, objective, applies })),
      stepCounts,
    });
    if (filterStep && !entries.some((entry) => entry.measurements.some((m) => m.step_id === filterStep)) && !processSteps().some((s) => s.id === filterStep)) {
      filterStep = null; // l'étape n'existe plus, et plus rien n'y est mesuré
    }
    document.getElementById("notebook-add-btn").hidden = !ctx.canEdit;
    document.getElementById("notebook-demo-note").hidden = !entries.some((e) => (e.measurements || []).some((m) => m.snapshot && m.snapshot.source === "demo"));
    render();
  }

  document.getElementById("notebook-add-btn").addEventListener("click", () => NotebookEntryDialog.open(ctx, { snapshots }));

  ExperiencePage.registerPanel({
    key: "notebook",
    mount(el, context) {
      ctx = context;
      return load();
    },
  });
})();
