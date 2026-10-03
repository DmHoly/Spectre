/* Cahier de données de la fiche (onglet « Données ») : des vues sur les mesures des plaques de
   l'expérience (PRISM), chacune avec ses observations et sa conclusion - le cahier de labo de
   l'étude, repris tel quel dans le rapport téléchargé.

   Une vue = un instantané des données (spectre.core.datasets, chargé une fois puis relu) + un
   composant de visualisation du registre DataViz (notebook/static/dataviz/) + ses réglages + une note.
   Ajouter : choisir le type de données, les plaques (celles de l'expérience, cochées, plus
   d'autres pour comparer), charger, puis choisir une vue - d'abord les préréglages du type
   (notebook/static/dataviz/presets.js), puis toute vue qui convient à ces données - et l'ajuster en direct.
   Chaque changement (ajout, réglage, note, ordre, retrait) enregistre une nouvelle version de la
   fiche, comme le reste (voir notebook/api.py), avec la version affichée en If-Match.

   Un panneau de la fiche (ExperiencePage.registerPanel) : il reçoit son contexte (`notebookCtx`) à
   chaque montage. */

let notebookCtx = null;
const notebookSnapshots = new Map(); // snapshot_id -> Promise<jeu de données>
let notebookSources = null;

function loadSnapshot(snapshotId) {
  if (!notebookSnapshots.has(snapshotId)) {
    notebookSnapshots.set(
      snapshotId,
      notebookApi.snapshot(notebookCtx.microprojectSlug, snapshotId).catch((err) => {
        notebookSnapshots.delete(snapshotId);
        throw err;
      })
    );
  }
  return notebookSnapshots.get(snapshotId);
}

async function getNotebookSources() {
  if (!notebookSources) notebookSources = notebookApi.sources(notebookCtx.microprojectSlug).catch(() => ({ sources: [], demo: false }));
  return notebookSources;
}

// `write` : l'appel de notebookApi qui enregistre le changement (une nouvelle version de la piste) ;
// la fiche se recharge ensuite sur place, onglet gardé (ctx.write).
function notebookChange(write) {
  return notebookCtx.write(write);
}

function experienceLasermarks() {
  return [...new Set((notebookCtx.detail.physical_tracking || []).map((e) => e.sample_id).filter(Boolean))];
}

const NB_ICONS = {
  settings: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/></svg>`,
  refresh: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/></svg>`,
  up: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>`,
  down: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`,
  remove: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>`,
};

function notebookEntryHtml(entry, index, total) {
  const canEdit = notebookCtx.canEdit;
  const wafers = (entry.wafers || []).map((w) => `<a class="mono" href="${plateUrl(w)}">${escapeHtml(w)}</a>`).join(", ");
  const note = entry.note || "";
  const actions = canEdit
    ? `<div class="nb-entry__actions" data-report-hide>
        <button type="button" class="nb-btn" data-act="settings" aria-expanded="false">${NB_ICONS.settings}Réglages</button>
        <button type="button" class="nb-btn" data-act="refresh" title="Recharger les données de ces plaques depuis la base">${NB_ICONS.refresh}Actualiser</button>
        <button type="button" class="nb-btn nb-btn--icon" data-act="up" aria-label="Monter cette vue" title="Monter"${index === 0 ? " disabled" : ""}>${NB_ICONS.up}</button>
        <button type="button" class="nb-btn nb-btn--icon" data-act="down" aria-label="Descendre cette vue" title="Descendre"${index === total - 1 ? " disabled" : ""}>${NB_ICONS.down}</button>
        <button type="button" class="nb-btn nb-btn--icon nb-btn--danger" data-act="remove" aria-label="Retirer cette vue du cahier" title="Retirer">${NB_ICONS.remove}</button>
      </div>`
    : "";
  return `
    <article class="nb-entry${entry.in_report === false ? " nb-entry--private" : ""}" data-entry="${entry.id}"${entry.in_report === false ? " data-report-hide" : ""}>
      <header class="nb-entry__head">
        <div class="nb-entry__heading">
          <h3 class="nb-entry__title">${escapeHtml(entry.title)}</h3>
          <div class="nb-entry__meta">
            <span class="nb-chip">${escapeHtml(entry.hook_title || entry.hook)}</span>
            ${wafers ? `<span>${wafers}</span>` : ""}
            <span>données du ${formatDate(entry.fetched_at)}</span>
            ${entry.source === "demo" ? `<span class="nb-chip nb-chip--demo" title="Données de démonstration, pas des mesures réelles">démo</span>` : ""}
            ${entry.objective ? `<span class="nb-chip nb-chip--objective">Objectif : ${escapeHtml(entry.objective)}</span>` : ""}
            ${entry.in_report === false ? `<span class="nb-chip">hors rapport</span>` : ""}
          </div>
        </div>
        ${actions}
      </header>
      <div class="nb-entry__settings" data-report-hide hidden></div>
      <div class="nb-entry__body">
        <div class="nb-entry__viz"><p class="help">Chargement des données…</p></div>
        <aside class="nb-entry__note" aria-label="Observations et conclusion">
          <div class="nb-entry__note-label">Observations &amp; conclusion</div>
          ${
            canEdit
              ? `<textarea class="field nb-note-input" rows="7" data-report-hide placeholder="Ce qu'on voit, ce qu'on en conclut, ce qu'il reste à vérifier…">${escapeHtml(note)}</textarea>
                 <div class="nb-note-actions" data-report-hide hidden>
                   <button type="button" class="btn btn-primary nb-note-save">Enregistrer la note</button>
                   <button type="button" class="btn btn-line nb-note-cancel">Annuler</button>
                 </div>
                 <div class="report-only nb-note-text">${escapeHtml(note)}</div>`
              : `<div class="nb-note-text">${note ? escapeHtml(note) : `<span class="help" style="margin:0;">Pas encore d'observation.</span>`}</div>`
          }
          <div class="nb-entry__by">${escapeHtml(entry.updated_by || entry.created_by || "")} · ${formatDate(entry.updated_at || entry.created_at)}</div>
        </aside>
      </div>
    </article>`;
}

async function renderNotebook(detail) {
  const host = document.getElementById("notebook-entries");
  const entries = detail.data_notebook || [];
  const canEdit = notebookCtx.canEdit;
  document.getElementById("notebook-add-btn").hidden = !canEdit;
  document.getElementById("notebook-demo-note").hidden = !entries.some((e) => e.source === "demo");
  if (!entries.length) {
    const marks = experienceLasermarks();
    host.innerHTML = `
      <div class="nb-empty">
        <p><strong>Pas encore de vue dans ce cahier.</strong></p>
        <p class="help" style="margin:0;">${
          canEdit
            ? `« Ajouter une vue » charge les mesures ${marks.length ? `des plaques ${marks.map(escapeHtml).join(", ")}` : "des plaques"} (EQE, PL, NCEL…) et les montre comme vous avez l'habitude de les regarder ; notez ce que vous y voyez - tout finit dans le rapport.`
            : "Les vues sur les mesures des plaques et les observations apparaîtront ici."
        }</p>
      </div>`;
    return;
  }
  host.innerHTML = entries.map((e, i) => notebookEntryHtml(e, i, entries.length)).join("");
  entries.forEach((entry) => {
    const article = host.querySelector(`[data-entry="${entry.id}"]`);
    const viz = article.querySelector(".nb-entry__viz");
    loadSnapshot(entry.snapshot_id)
      .then((ds) => DataViz.render(viz, ds, entry.component, entry.options || {}))
      .catch((err) => {
        viz.innerHTML = `<div class="viz-empty">Données indisponibles : ${escapeHtml(err.message || String(err))}</div>`;
      });
    if (canEdit) wireNotebookEntry(article, entry, entries);
  });
}

function wireNotebookEntry(article, entry, entries) {
  const note = article.querySelector(".nb-note-input");
  const noteActions = article.querySelector(".nb-note-actions");
  note.addEventListener("input", () => {
    noteActions.hidden = note.value === (entry.note || "");
  });
  article.querySelector(".nb-note-save").addEventListener("click", () => notebookChange(() => notebookApi.updateEntry(notebookCtx.microprojectSlug, notebookCtx.experimentId, notebookCtx.versionId, entry.id, { note: note.value })));
  article.querySelector(".nb-note-cancel").addEventListener("click", () => {
    note.value = entry.note || "";
    noteActions.hidden = true;
  });
  article.querySelector(".nb-entry__actions").addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "up" || act === "down") return notebookChange(() => notebookApi.updateEntry(notebookCtx.microprojectSlug, notebookCtx.experimentId, notebookCtx.versionId, entry.id, { move: act === "up" ? -1 : 1 }));
    if (act === "remove") {
      if (window.confirm(`Retirer « ${entry.title} » du cahier ? (Elle reste dans l'historique de la fiche.)`)) notebookChange(() => notebookApi.removeEntry(notebookCtx.microprojectSlug, notebookCtx.experimentId, notebookCtx.versionId, entry.id));
      return;
    }
    if (act === "refresh") {
      btn.disabled = true;
      try {
        const snap = await notebookApi.takeSnapshot(notebookCtx.microprojectSlug, { hook: entry.hook, wafers: entry.wafers || [], refresh: true });
        notebookChange(() => notebookApi.updateEntry(notebookCtx.microprojectSlug, notebookCtx.experimentId, notebookCtx.versionId, entry.id, { snapshot_id: snap.snapshot_id }));
      } catch (err) {
        notebookCtx.showError(err);
        btn.disabled = false;
      }
      return;
    }
    if (act === "settings") toggleEntrySettings(article, entry, btn);
  });
}

function objectiveOptionsHtml(selected) {
  return `<option value="">— aucun —</option>${(notebookCtx.detail.objectives || [])
    .map((o) => `<option value="${escapeHtml(o.name)}"${o.name === selected ? " selected" : ""}>${escapeHtml(o.name)}</option>`)
    .join("")}`;
}

// Réglages d'une vue existante, ajustés en direct sur son graphique ; « Appliquer » enregistre.
async function toggleEntrySettings(article, entry, btn) {
  const panel = article.querySelector(".nb-entry__settings");
  const viz = article.querySelector(".nb-entry__viz");
  const open = panel.hidden;
  btn.setAttribute("aria-expanded", String(open));
  if (!open) {
    panel.hidden = true;
    const ds = await loadSnapshot(entry.snapshot_id);
    DataViz.render(viz, ds, entry.component, entry.options || {});
    return;
  }
  const ds = await loadSnapshot(entry.snapshot_id);
  const components = DataViz.componentsFor(ds);
  let component = entry.component;
  const paintOptions = (values) => {
    const def = DataViz.get(component);
    panel.querySelector(".nb-settings__options").innerHTML = def ? DataViz.optionsFormHtml(ds, def.options(ds), values, `nbs-${entry.id}`) : "";
  };
  panel.innerHTML = `
    <div class="nb-settings">
      <div class="nb-settings__row">
        <div class="viz-opt"><label for="nbs-${entry.id}-title">Titre</label><input class="field" id="nbs-${entry.id}-title" value="${escapeHtml(entry.title)}" maxlength="200"></div>
        <div class="viz-opt"><label for="nbs-${entry.id}-component">Vue</label><select class="field" id="nbs-${entry.id}-component">${components
          .map((c) => `<option value="${c.key}"${c.key === component ? " selected" : ""}>${escapeHtml(c.label)}</option>`)
          .join("")}</select></div>
        <div class="viz-opt"><label for="nbs-${entry.id}-objective">Objectif servi</label><select class="field" id="nbs-${entry.id}-objective">${objectiveOptionsHtml(entry.objective)}</select></div>
        <label class="viz-check viz-opt viz-opt--check"><input type="checkbox" id="nbs-${entry.id}-report"${entry.in_report === false ? "" : " checked"}> Dans le rapport</label>
      </div>
      <div class="nb-settings__options viz-options"></div>
      <div class="nb-settings__actions">
        <button type="button" class="btn btn-primary nb-settings-apply">Appliquer</button>
        <button type="button" class="btn btn-line nb-settings-cancel">Annuler</button>
      </div>
    </div>`;
  panel.hidden = false;
  paintOptions({ ...(DataViz.get(component) ? DataViz.get(component).defaults(ds) : {}), ...(entry.options || {}) });
  const preview = () => DataViz.render(viz, ds, component, DataViz.readOptions(panel.querySelector(".nb-settings__options")));
  panel.querySelector(`#nbs-${entry.id}-component`).addEventListener("change", (event) => {
    component = event.target.value;
    paintOptions(DataViz.get(component).defaults(ds));
    preview();
  });
  panel.querySelector(".nb-settings__options").addEventListener("change", preview);
  panel.querySelector(".nb-settings-cancel").addEventListener("click", () => btn.click());
  panel.querySelector(".nb-settings-apply").addEventListener("click", () =>
    notebookChange(() =>
      notebookApi.updateEntry(notebookCtx.microprojectSlug, notebookCtx.experimentId, notebookCtx.versionId, entry.id, {
        title: panel.querySelector(`#nbs-${entry.id}-title`).value,
        component,
        options: DataViz.readOptions(panel.querySelector(".nb-settings__options")),
        objective: panel.querySelector(`#nbs-${entry.id}-objective`).value,
        in_report: panel.querySelector(`#nbs-${entry.id}-report`).checked,
      })
    )
  );
}

// --- ajouter une vue -----------------------------------------------------------------------------

const nbAdd = { source: null, dataset: null, component: null, presetTitle: "" };

async function openNotebookDialog() {
  const dialog = document.getElementById("notebook-dialog");
  const { sources, demo } = await getNotebookSources();
  Object.assign(nbAdd, { source: null, dataset: null, component: null, presetTitle: "" });
  document.getElementById("nb-dialog-demo").hidden = !demo;
  document.getElementById("nb-sources").innerHTML = sources.length
    ? sources
        .map(
          (s) => `
        <label class="nb-source">
          <input type="radio" name="nb-source" value="${escapeHtml(s.key)}">
          <span class="nb-source__title">${escapeHtml(s.title)}</span>
          <span class="nb-source__cat">${escapeHtml(s.category || "")}</span>
        </label>`
        )
        .join("")
    : `<p class="help">Aucune source de données disponible (PRISM n'est pas installé sur ce serveur).</p>`;
  const marks = experienceLasermarks();
  document.getElementById("nb-plates").innerHTML = marks.length
    ? marks.map((m) => `<label class="viz-check"><input type="checkbox" value="${escapeHtml(m)}" checked> <span class="mono">${escapeHtml(m)}</span></label>`).join("")
    : `<span class="help" style="margin:0;">Aucun lasermark sur cette expérience - indiquez les plaques ci-dessous.</span>`;
  document.getElementById("nb-extra-plates").value = "";
  document.getElementById("nb-load-status").textContent = "";
  document.getElementById("nb-step-view").hidden = true;
  document.getElementById("nb-add-submit").disabled = true;
  document.getElementById("nb-title").value = "";
  document.getElementById("nb-note").value = "";
  document.getElementById("nb-objective").innerHTML = objectiveOptionsHtml(null);
  const first = document.querySelector('#nb-sources input[name="nb-source"]');
  if (first) {
    first.checked = true;
    nbAdd.source = sources.find((s) => s.key === first.value);
  }
  updateNotebookPlatesState();
  dialog.showModal();
}

function updateNotebookPlatesState() {
  const byWafer = !nbAdd.source || nbAdd.source.by_wafer;
  document.getElementById("nb-plates-step").classList.toggle("is-off", !byWafer);
  document.getElementById("nb-plates-off").hidden = byWafer;
}

function chosenPlates() {
  const checked = [...document.querySelectorAll("#nb-plates input:checked")].map((i) => i.value);
  const extra = document
    .getElementById("nb-extra-plates")
    .value.split(/[,;\s]+/)
    .map((w) => w.trim())
    .filter(Boolean);
  return [...new Set([...checked, ...extra])];
}

async function loadNotebookData() {
  const status = document.getElementById("nb-load-status");
  const btn = document.getElementById("nb-load-btn");
  if (!nbAdd.source) return;
  const wafers = chosenPlates();
  if (nbAdd.source.by_wafer && !wafers.length) {
    status.textContent = "Choisissez au moins une plaque.";
    return;
  }
  btn.disabled = true;
  status.textContent = "Chargement depuis la base…";
  try {
    const ds = await notebookApi.takeSnapshot(notebookCtx.microprojectSlug, { hook: nbAdd.source.key, wafers });
    nbAdd.dataset = ds;
    notebookSnapshots.set(ds.snapshot_id, Promise.resolve(ds));
    const nWafers = DataViz.byWafer(ds).size;
    status.textContent = `${ds.rows.length} ligne${ds.rows.length > 1 ? "s" : ""}${nbAdd.source.by_wafer ? ` · ${nWafers} plaque${nWafers > 1 ? "s" : ""}` : ""}${ds.source === "demo" ? " · données de démonstration" : ""}${ds.truncated ? " · tronqué" : ""}`;
    paintNotebookViews(ds);
  } catch (err) {
    status.textContent = err.message || String(err);
  } finally {
    btn.disabled = false;
  }
}

function paintNotebookViews(ds) {
  const presets = DataViz.presetsFor(ds);
  const components = DataViz.componentsFor(ds);
  const card = (attrs, title, sub) =>
    `<button type="button" class="nb-view" ${attrs}><span class="nb-view__title">${escapeHtml(title)}</span><span class="nb-view__sub">${escapeHtml(sub)}</span></button>`;
  const others = `<div class="nb-views__grid">${components.map((c) => card(`data-component="${c.key}"`, c.label, c.description)).join("")}</div>`;
  document.getElementById("nb-views").innerHTML = presets.length
    ? `<div class="nb-views__label">Pour ce type de données</div><div class="nb-views__grid">${presets.map((p, i) => card(`data-preset="${i}"`, p.title, DataViz.get(p.component).label)).join("")}</div>
       <details class="nb-views__more"><summary>Toutes les vues possibles (${components.length})</summary>${others}</details>`
    : `<div class="nb-views__label">Vues possibles</div>${others}`;
  document.getElementById("nb-step-view").hidden = false;
  const choose = (btn, component, options, title) => {
    document.querySelectorAll("#nb-views .nb-view").forEach((b) => b.classList.toggle("is-selected", b === btn));
    nbAdd.component = component;
    const def = DataViz.get(component);
    const values = { ...def.defaults(ds), ...options };
    document.getElementById("nb-preview-options").innerHTML = DataViz.optionsFormHtml(ds, def.options(ds), values, "nbp");
    const titleInput = document.getElementById("nb-title");
    if (!titleInput.value || titleInput.value === nbAdd.presetTitle) titleInput.value = title;
    nbAdd.presetTitle = title;
    DataViz.render(document.getElementById("nb-preview-viz"), ds, component, values);
    document.getElementById("nb-add-submit").disabled = false;
  };
  document.querySelectorAll("#nb-views [data-preset]").forEach((btn) => {
    const p = presets[Number(btn.dataset.preset)];
    btn.addEventListener("click", () => choose(btn, p.component, p.options || {}, p.title));
  });
  document.querySelectorAll("#nb-views [data-component]").forEach((btn) => {
    const c = DataViz.get(btn.dataset.component);
    btn.addEventListener("click", () => choose(btn, c.key, {}, `${c.label} · ${ds.hook_title || ds.hook}`));
  });
  const firstPreset = document.querySelector("#nb-views [data-preset], #nb-views [data-component]");
  if (firstPreset) firstPreset.click();
}

function wireNotebookDialog() {
  const dialog = document.getElementById("notebook-dialog");
  document.getElementById("notebook-add-btn").addEventListener("click", openNotebookDialog);
  document.getElementById("nb-dialog-close").addEventListener("click", () => dialog.close());
  document.getElementById("nb-add-cancel").addEventListener("click", () => dialog.close());
  document.getElementById("nb-sources").addEventListener("change", async (event) => {
    const { sources } = await getNotebookSources();
    nbAdd.source = sources.find((s) => s.key === event.target.value) || null;
    updateNotebookPlatesState();
    document.getElementById("nb-step-view").hidden = true;
    document.getElementById("nb-add-submit").disabled = true;
  });
  document.getElementById("nb-load-btn").addEventListener("click", loadNotebookData);
  document.getElementById("nb-preview-options").addEventListener("change", () => {
    if (!nbAdd.dataset || !nbAdd.component) return;
    DataViz.render(document.getElementById("nb-preview-viz"), nbAdd.dataset, nbAdd.component, DataViz.readOptions(document.getElementById("nb-preview-options")));
  });
  document.getElementById("nb-add-submit").addEventListener("click", async () => {
    if (!nbAdd.dataset || !nbAdd.component) return;
    const title = document.getElementById("nb-title").value.trim();
    if (!title) {
      document.getElementById("nb-title").focus();
      return;
    }
    dialog.close();
    notebookChange(() =>
      notebookApi.addEntry(notebookCtx.microprojectSlug, notebookCtx.experimentId, notebookCtx.versionId, {
        title,
        snapshot_id: nbAdd.dataset.snapshot_id,
        component: nbAdd.component,
        options: DataViz.readOptions(document.getElementById("nb-preview-options")),
        note: document.getElementById("nb-note").value,
        objective: document.getElementById("nb-objective").value || null,
      })
    );
  });
}

wireNotebookDialog();

ExperiencePage.registerPanel({
  key: "notebook",
  mount(el, ctx) {
    notebookCtx = ctx;
    return renderNotebook(ctx.detail);
  },
});
