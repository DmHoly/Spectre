/* Page d'un projet corporate (/management/{slug}) - trois niveaux : le projet (Native, VLC, Nova),
   ses thématiques (dopage PGaN, double EBL...), et sous chacune les µprojets (chaînes
   d'expériences). En tête, mis en avant, les objectifs corporate de la période, classés par
   importance. Un admin édite tout (objectifs, thématiques, rattachements) ; chacun peut créer un
   µprojet. Voir spectre.api.management. */

const slug = window.location.pathname.split("/").filter(Boolean)[1];
const areaUrl = `/api/management/${encodeURIComponent(slug)}`;
document.getElementById("atlas-link").href = `/management/${encodeURIComponent(slug)}/atlas`;

// Tendances, juste sous les objectifs : bloc KPI à onglets réutilisable (js/kpi-trend.js), un
// onglet par KPI déclaré côté serveur (spectre/core/trends.py).
KpiTrendBlock.mount(document.getElementById("trends"), {
  eyebrow: "Tendances",
  title: "Évolution des KPI",
  kpisUrl: `${areaUrl}/tendances`,
  seriesUrl: (key, months) => `${areaUrl}/tendances/${encodeURIComponent(key)}?mois=${months}`,
  storageKey: `spectre:tendances:${slug}`,
});

const errorBox = document.getElementById("error");
const flashBox = document.getElementById("flash");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function flash(msg) {
  errorBox.style.display = "none";
  flashBox.textContent = msg;
  flashBox.style.display = "block";
  setTimeout(() => (flashBox.style.display = "none"), 3000);
}

let current = null;

const ICON_UP = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>`;
const ICON_DOWN = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;
const ICON_EDIT = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>`;
const ICON_FLAG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 22V4"/><path d="M4 4h12l-2 4 2 4H4"/></svg>`;

function kpi(n, label) {
  return `<div class="kpi"><div class="kpi__value">${n}</div><div class="kpi__label">${label}</div></div>`;
}

function plural(n, one, many) {
  return `${n} ${n > 1 ? many : one}`;
}

// --- objectifs --------------------------------------------------------------------------------

function objectiveBlock(o, index, total, admin) {
  const tools = admin
    ? `<div class="obj__tools">
        <button type="button" class="obj__tool" data-move="${o.id}" data-dir="-1" ${index === 0 ? "disabled" : ""} aria-label="Monter l'objectif « ${escapeHtml(o.title)} »" title="Plus important">${ICON_UP}</button>
        <button type="button" class="obj__tool" data-move="${o.id}" data-dir="1" ${index === total - 1 ? "disabled" : ""} aria-label="Descendre l'objectif « ${escapeHtml(o.title)} »" title="Moins important">${ICON_DOWN}</button>
        <button type="button" class="obj__tool" data-edit-objective="${o.id}" aria-label="Modifier l'objectif « ${escapeHtml(o.title)} »" title="Modifier">${ICON_EDIT}</button>
      </div>`
    : "";
  return `
    <li class="obj${index === 0 ? " obj--first" : ""}">
      <div class="obj__top">
        <div class="obj__rank" aria-label="Priorité ${index + 1}">${String(index + 1).padStart(2, "0")}</div>
        <div class="obj__body">
          <div class="obj__title">${escapeHtml(o.title)}</div>
          ${o.detail ? `<div class="obj__detail">${escapeHtml(o.detail)}</div>` : ""}
          ${o.target ? `<div class="obj__target">${ICON_FLAG}${escapeHtml(o.target)}</div>` : ""}
        </div>
        ${tools}
      </div>
    </li>`;
}

function renderObjectives(area) {
  const list = document.getElementById("objectives");
  const admin = area.is_admin;
  document.getElementById("objectives-period").textContent = area.objectives_period || "6 prochains mois";
  const objs = area.objectifs || [];
  list.innerHTML = objs.length
    ? objs.map((o, i) => objectiveBlock(o, i, objs.length, admin)).join("")
    : `<li class="obj-empty" style="grid-column:1/-1;">${
        admin
          ? "Aucun objectif défini pour cette période. Ajoutez-les par ordre d'importance avec « + Objectif »."
          : "Aucun objectif corporate n'a encore été défini pour cette période."
      }</li>`;
  list.removeAttribute("aria-busy");
}

// --- thématiques & µprojets -------------------------------------------------------------------

function microprojetCard(p) {
  const roleBadge = p.role ? `<span class="badge badge-role">${escapeHtml(roleLabel(p.role))}</span>` : "";
  const inner = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
      <div style="font-size:15px;font-weight:700;">${escapeHtml(p.name)}</div>
      ${roleBadge || `<span style="font-size:11px;color:var(--text-faint);">non membre</span>`}
    </div>
    <div style="font-size:13px;color:var(--text-soft);min-height:16px;">${escapeHtml(p.description || "")}</div>
    <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--text-faint);padding-top:8px;border-top:1px solid var(--border-soft);">
      <span>${p.experiences} expériences</span><span>${p.running} en cours</span><span>${p.concluded} concluantes</span><span>${p.wafers} wafers</span>
    </div>`;
  return p.role
    ? `<a href="/microprojets/${encodeURIComponent(p.slug)}" class="card card-pad" style="display:flex;flex-direction:column;gap:8px;color:inherit;">${inner}</a>`
    : `<div class="card card-pad" style="display:flex;flex-direction:column;gap:8px;opacity:.75;">${inner}</div>`;
}

function thematicSection(t, items, admin) {
  const none = t === null;
  const name = none ? "Sans thématique" : t.name;
  const s = none ? null : t.stats;
  const meta = none
    ? plural(items.length, "µprojet", "µprojets")
    : `${plural(s.microprojets, "µprojet", "µprojets")} · ${plural(s.experiences, "expérience", "expériences")} · ${s.running} en cours · ${s.wafers} wafers`;
  const actions = none
    ? ""
    : `<div class="thematic__actions">
        <button type="button" class="btn btn-line btn-sm" data-new-mp="${escapeHtml(t.slug)}">+ µprojet</button>
        ${admin ? `<button type="button" class="btn btn-line btn-sm" data-edit-thematic="${escapeHtml(t.slug)}" aria-label="Modifier la thématique ${escapeHtml(t.name)}">${ICON_EDIT} Modifier</button>` : ""}
      </div>`;
  const grid = items.length
    ? `<div class="mp-grid">${items.map(microprojetCard).join("")}</div>`
    : `<div style="font-size:13px;color:var(--text-faint);padding:6px 0;">Aucun µprojet dans cette thématique pour l'instant.</div>`;
  return `
    <section class="thematic${none ? " thematic--none" : ""}">
      <div class="thematic__head">
        <div>
          <h3 class="thematic__name">${escapeHtml(name)}</h3>
          ${!none && t.description ? `<div class="thematic__desc">${escapeHtml(t.description)}</div>` : ""}
          <div class="thematic__meta">${meta}</div>
        </div>
        ${actions}
      </div>
      ${grid}
    </section>`;
}

function renderThematics(area) {
  const admin = area.is_admin;
  const byThematic = new Map(area.thematiques.map((t) => [t.slug, []]));
  const orphans = [];
  for (const p of area.microprojets) {
    (byThematic.get(p.thematique_slug) || orphans).push(p);
  }
  const sections = area.thematiques.map((t) => thematicSection(t, byThematic.get(t.slug), admin));
  if (orphans.length) sections.push(thematicSection(null, orphans, admin));
  document.getElementById("thematics").innerHTML = sections.length
    ? sections.join("")
    : `<div class="empty-state card" style="margin-top:14px;"><div style="font-weight:600;color:var(--text-soft);">Aucune thématique ni µprojet dans ce projet</div>${
        admin ? `<div style="font-size:13px;color:var(--text-faint);margin-top:4px;">Commencez par créer une thématique (ex : dopage PGaN, double EBL).</div>` : ""
      }</div>`;
}

function thematicOptions(selected) {
  return [`<option value="">— Sans thématique —</option>`]
    .concat(
      current.thematiques.map(
        (t) => `<option value="${escapeHtml(t.slug)}"${t.slug === selected ? " selected" : ""}>${escapeHtml(t.name)}</option>`
      )
    )
    .join("");
}

function render(area) {
  current = area;
  document.title = `${area.name} — Spectre`;
  document.getElementById("crumb").textContent = "/ " + area.name;
  document.getElementById("area-name-crumb").textContent = area.name;
  document.getElementById("area-name").textContent = area.name;
  document.getElementById("area-art").innerHTML = techArtSvg(area.slug, area.name);
  document.getElementById("area-description").textContent = area.description || "";
  const strategyEl = document.getElementById("area-strategy");
  if (area.strategy) {
    strategyEl.textContent = "Note stratégique : " + area.strategy;
    strategyEl.style.display = "";
  } else {
    strategyEl.style.display = "none";
  }
  renderObjectives(area);

  const s = area.stats;
  document.getElementById("area-kpi").innerHTML = [
    kpi(s.thematiques, "thématiques"),
    kpi(s.microprojets, "µprojets"),
    kpi(s.experiences, "expériences"),
    kpi(s.running, "en cours"),
    kpi(s.concluded, "concluantes"),
    kpi(s.wafers, "wafers"),
  ].join("");
  renderThematics(area);

  const admin = area.is_admin;
  for (const id of ["edit-area-btn", "attach-microprojet-btn", "new-thematic-btn", "new-objective-btn"]) {
    document.getElementById(id).style.display = admin ? "" : "none";
  }
  document.getElementById("ea-delete").style.display = admin && area.slug !== "non-classe" ? "" : "none";
}

async function load() {
  try {
    render(await api.get(areaUrl));
  } catch (err) {
    showError(err);
  }
}

/** Run a write that returns the refreshed project, re-render, close ``dialog``, flash ``msg``. */
async function save(dialog, request, msg) {
  try {
    render(await request());
    if (dialog) dialog.close();
    if (msg) flash(msg);
  } catch (err) {
    if (dialog) dialog.close();
    showError(err);
  }
}

// --- objectifs : ajouter / modifier / supprimer / réordonner ----------------------------------

const objDialog = document.getElementById("objective-dialog");
let editingObjective = null;
function openObjectiveDialog(objective) {
  editingObjective = objective || null;
  document.getElementById("obj-dialog-title").textContent = objective ? "Modifier l'objectif" : "Nouvel objectif";
  document.getElementById("obj-title").value = objective ? objective.title : "";
  document.getElementById("obj-detail").value = objective ? objective.detail : "";
  document.getElementById("obj-target").value = objective ? objective.target : "";
  document.getElementById("obj-rank-help").style.display = objective ? "none" : "";
  document.getElementById("obj-delete").style.display = objective ? "" : "none";
  objDialog.showModal();
}
document.getElementById("new-objective-btn").addEventListener("click", () => openObjectiveDialog(null));
document.getElementById("obj-cancel").addEventListener("click", () => objDialog.close());
document.getElementById("objective-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const body = {
    title: document.getElementById("obj-title").value,
    detail: document.getElementById("obj-detail").value,
    target: document.getElementById("obj-target").value,
  };
  const o = editingObjective;
  save(
    objDialog,
    () => (o ? api.put(`${areaUrl}/objectifs/${o.id}`, body) : api.post(`${areaUrl}/objectifs`, body)),
    o ? "Objectif mis à jour." : "Objectif ajouté."
  );
});
document.getElementById("obj-delete").addEventListener("click", () => {
  const o = editingObjective;
  if (!o || !window.confirm(`Supprimer l'objectif « ${o.title} » ?`)) return;
  save(objDialog, () => api.del(`${areaUrl}/objectifs/${o.id}`), "Objectif supprimé.");
});

document.getElementById("objectives").addEventListener("click", (event) => {
  const move = event.target.closest("[data-move]");
  if (move && !move.disabled) {
    const ids = current.objectifs.map((o) => o.id);
    const from = ids.indexOf(Number(move.dataset.move));
    const to = from + Number(move.dataset.dir);
    if (from < 0 || to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    save(null, () => api.put(`${areaUrl}/objectifs`, { ids }));
    return;
  }
  const edit = event.target.closest("[data-edit-objective]");
  if (edit) openObjectiveDialog(current.objectifs.find((o) => o.id === Number(edit.dataset.editObjective)));
});

// --- thématiques ------------------------------------------------------------------------------

const thDialog = document.getElementById("thematic-dialog");
let editingThematic = null;
function openThematicDialog(thematic) {
  editingThematic = thematic || null;
  document.getElementById("th-dialog-title").textContent = thematic ? "Modifier la thématique" : "Nouvelle thématique";
  document.getElementById("th-name").value = thematic ? thematic.name : "";
  document.getElementById("th-description").value = thematic ? thematic.description : "";
  document.getElementById("th-delete").style.display = thematic ? "" : "none";
  thDialog.showModal();
}
document.getElementById("new-thematic-btn").addEventListener("click", () => openThematicDialog(null));
document.getElementById("th-cancel").addEventListener("click", () => thDialog.close());
document.getElementById("thematic-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const body = { name: document.getElementById("th-name").value, description: document.getElementById("th-description").value };
  const t = editingThematic;
  save(
    thDialog,
    () => (t ? api.put(`${areaUrl}/thematiques/${encodeURIComponent(t.slug)}`, body) : api.post(`${areaUrl}/thematiques`, body)),
    t ? "Thématique mise à jour." : "Thématique créée."
  );
});
document.getElementById("th-delete").addEventListener("click", () => {
  const t = editingThematic;
  if (!t || !window.confirm(`Supprimer la thématique « ${t.name} » ? Ses µprojets restent dans le projet, sans thématique.`)) return;
  save(thDialog, () => api.del(`${areaUrl}/thematiques/${encodeURIComponent(t.slug)}`), "Thématique supprimée.");
});

document.getElementById("thematics").addEventListener("click", (event) => {
  const newMp = event.target.closest("[data-new-mp]");
  if (newMp) return openMicroprojetDialog(newMp.dataset.newMp);
  const edit = event.target.closest("[data-edit-thematic]");
  if (edit) openThematicDialog(current.thematiques.find((t) => t.slug === edit.dataset.editThematic));
});

// --- nouveau µprojet --------------------------------------------------------------------------

const mpDialog = document.getElementById("microprojet-dialog");
function openMicroprojetDialog(thematicSlug) {
  document.getElementById("mp-thematic").innerHTML = thematicOptions(thematicSlug || "");
  mpDialog.showModal();
}
document.getElementById("new-microprojet-btn").addEventListener("click", () => openMicroprojetDialog(""));
document.getElementById("mp-cancel").addEventListener("click", () => mpDialog.close());
document.getElementById("microprojet-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const p = await api.post("/api/microprojets", {
      name: document.getElementById("mp-name").value,
      description: document.getElementById("mp-description").value,
      management_area_slug: slug,
      thematique_slug: document.getElementById("mp-thematic").value || null,
    });
    window.location.href = `/microprojets/${encodeURIComponent(p.slug)}`;
  } catch (err) {
    mpDialog.close();
    showError(err);
  }
});

// --- modifier / supprimer le projet -----------------------------------------------------------

const eaDialog = document.getElementById("edit-area-dialog");
document.getElementById("edit-area-btn").addEventListener("click", () => {
  document.getElementById("ea-name").value = current.name;
  document.getElementById("ea-description").value = current.description || "";
  document.getElementById("ea-period").value = current.objectives_period || "";
  document.getElementById("ea-strategy").value = current.strategy || "";
  eaDialog.showModal();
});
document.getElementById("ea-cancel").addEventListener("click", () => eaDialog.close());
document.getElementById("edit-area-form").addEventListener("submit", (event) => {
  event.preventDefault();
  save(
    eaDialog,
    () =>
      api.put(areaUrl, {
        name: document.getElementById("ea-name").value,
        description: document.getElementById("ea-description").value,
        strategy: document.getElementById("ea-strategy").value,
        objectives_period: document.getElementById("ea-period").value,
      }),
    "Projet mis à jour."
  );
});
document.getElementById("ea-delete").addEventListener("click", async () => {
  if (!window.confirm(`Supprimer le projet « ${current.name} » ? Ses thématiques et objectifs sont supprimés, ses µprojets repassent en « Non classé ».`)) return;
  try {
    await api.del(areaUrl);
    window.location.href = "/";
  } catch (err) {
    eaDialog.close();
    showError(err);
  }
});

// --- rattacher un µprojet existant (ou le changer de thématique) ------------------------------

const attachDialog = document.getElementById("attach-dialog");
document.getElementById("attach-microprojet-btn").addEventListener("click", async () => {
  try {
    const all = await api.get("/api/microprojets/tous");
    const select = document.getElementById("attach-select");
    select.innerHTML = all.length
      ? all
          .map((p) => {
            const where = [p.management_area && p.management_area.name, p.thematique && p.thematique.name].filter(Boolean).join(" › ");
            return `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}${where ? ` — ${escapeHtml(where)}` : ""}</option>`;
          })
          .join("")
      : `<option value="">Aucun µprojet</option>`;
    document.getElementById("attach-thematic").innerHTML = thematicOptions("");
    attachDialog.showModal();
  } catch (err) {
    showError(err);
  }
});
document.getElementById("attach-cancel").addEventListener("click", () => attachDialog.close());
document.getElementById("attach-confirm").addEventListener("click", () => {
  const microprojectSlug = document.getElementById("attach-select").value;
  if (!microprojectSlug) return attachDialog.close();
  save(
    attachDialog,
    () =>
      api.post(`${areaUrl}/microprojets`, {
        microproject_slug: microprojectSlug,
        thematique_slug: document.getElementById("attach-thematic").value || null,
      }),
    "µprojet rattaché."
  );
});

load();
