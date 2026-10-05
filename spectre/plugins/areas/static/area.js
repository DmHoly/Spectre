/* Page d'un projet corporate (/management/{slug}) - trois niveaux : le projet (Native, VLC, Nova),
   ses thématiques (dopage PGaN, double EBL...), et sous chacune les µprojets (chaînes
   d'expériences). En tête, dans un bloc repliable, les objectifs corporate de la période : chacun
   porte un pourcentage (un chiffre de 0 à 100 % servant au calcul du bonus, simplement noté - les
   objectifs sont classés par lui), et peut être marqué atteint, avec le µprojet qui l'a validé.
   Qui gère le projet (un admin, ou un manager de son équipe : can_manage, renvoyé par l'API) en
   édite les objectifs et les thématiques ; seul un admin le rattache à une équipe ou y rattache un
   µprojet existant ; y créer un µprojet est ouvert à tous dans un projet sans équipe (et « Non
   classé »), aux membres de son équipe et à l'admin sinon (can_place_microproject).
   Chaque µprojet porte son numéro (Nat_0004) : la recherche de la topbar y mène directement.
   Le projet vient de areasApi (avec can_manage, can_delete et son équipe), les µprojets et leurs
   compteurs de experimentsApi.stats, le rôle d'admin de accountsApi.me (is_admin). */

const { slug } = routeParams("/management/{slug}");
document.getElementById("atlas-link").href = `/management/${encodeURIComponent(slug)}/atlas`;

// Tendances, juste sous les objectifs : bloc KPI à onglets réutilisable (kpis/static/kpi-trend.js), un
// onglet par KPI déclaré côté serveur (spectre/plugins/kpis/service.py).
KpiTrendBlock.mount(document.getElementById("trends"), {
  eyebrow: "Tendances",
  title: "Évolution des KPI",
  loadKpis: () => kpisApi.list(slug),
  loadSeries: (key, months, variant) => kpisApi.series(slug, key, months, variant),
  storageKey: `spectre:tendances:${slug}`,
  // un point jalon (étude) d'une tendance -> sa fiche (aujourd'hui : données de démo EQE)
  onPointClick: (point, series) => openDemoStudy(series.key, point.study),
});

// La fiche d'une étude derrière un point de tendance : seules les séries de démonstration en ont
// (plugin kpis_demo, actif seulement avec SPECTRE_DEMO_DATA=1) - ses fichiers ne sont donc chargés
// qu'au premier clic sur un tel point.
function loadAsset(url) {
  return new Promise((resolve, reject) => {
    const el = url.endsWith(".css")
      ? Object.assign(document.createElement("link"), { rel: "stylesheet", href: url })
      : Object.assign(document.createElement("script"), { src: url });
    el.onload = resolve;
    el.onerror = () => reject(new Error("La fiche de l'étude n'a pas pu être chargée."));
    document.head.appendChild(el);
  });
}

let demoStudyReady = null;
function openDemoStudy(kpiKey, studyId) {
  if (!kpiKey || !studyId) return;
  demoStudyReady =
    demoStudyReady ||
    Promise.all([loadAsset("/static/kpis_demo/kpis_demo.css"), loadAsset("/static/kpis_demo/client.js")]).then(() =>
      loadAsset("/static/kpis_demo/study.js")
    );
  demoStudyReady.then(
    () => KpisDemo.openStudy(slug, kpiKey, studyId),
    (err) => {
      demoStudyReady = null;
      showError(err);
    }
  );
}

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

let current = null; // le projet (areasApi.get)
let rows = []; // ses µprojets et leurs compteurs (experimentsApi.stats)
let admin = false; // rattacher une équipe ou un µprojet existant (accountsApi.me)
let teams = []; // les équipes proposées au rattachement (admin seulement)

const ICON_EDIT = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>`;
const ICON_CHECK = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>`;
const ICON_ARROW = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>`;
const ICON_FLAG = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 22V4"/><path d="M4 4h12l-2 4 2 4H4"/></svg>`;

function kpi(n, label) {
  return `<div class="kpi"><div class="kpi__value">${n}</div><div class="kpi__label">${label}</div></div>`;
}

function plural(n, one, many) {
  return `${n} ${n > 1 ? many : one}`;
}

// --- objectifs --------------------------------------------------------------------------------

function percent(value) {
  return `${Number(value).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %`;
}

// Toutes les cartes au même format : rang (ordre des pourcentages), pourcentage, intitulé,
// précisions, échéance, et en pied l'état (atteint ou non) avec le µprojet qui l'a validé.
function objectiveBlock(o, index) {
  const tools = current.can_manage
    ? `<div class="obj__tools"><button type="button" class="obj__tool" data-edit-objective="${o.id}" aria-label="Modifier l'objectif « ${escapeHtml(o.title)} »" title="Modifier">${ICON_EDIT}</button></div>`
    : "";
  const weight =
    o.weight !== null && o.weight !== undefined
      ? `<span class="obj__weight" title="Pourcentage servant au calcul du bonus">${percent(o.weight)}<small>bonus</small></span>`
      : `<span class="obj__weight obj__weight--none">% à définir</span>`;
  const validator = o.validated_by
    ? `validé par <a href="/microprojets/${encodeURIComponent(o.validated_by.slug)}">${escapeHtml(o.validated_by.code || o.validated_by.name)}</a>${o.validated_by.code ? ` · ${escapeHtml(o.validated_by.name)}` : ""}`
    : "";
  const status = o.achieved
    ? `<span class="obj__achieved">${ICON_CHECK}Atteint</span>${validator ? ` · ${validator}` : ""}`
    : validator
      ? `<span>En cours · ${validator}</span>`
      : `<span>En cours</span>`;
  return `
    <li class="obj${o.achieved ? " obj--achieved" : ""}">
      <div class="obj__top">
        <span class="obj__rank" aria-label="Rang ${index + 1}">${String(index + 1).padStart(2, "0")}</span>
        ${weight}
        ${tools}
      </div>
      <div class="obj__title">${escapeHtml(o.title)}</div>
      ${o.detail ? `<div class="obj__detail" title="${escapeHtml(o.detail)}">${escapeHtml(o.detail)}</div>` : ""}
      ${o.target ? `<div class="obj__target">${ICON_FLAG}${escapeHtml(o.target)}</div>` : ""}
      <div class="obj__status">${status}</div>
    </li>`;
}

function renderObjectives(area) {
  const list = document.getElementById("objectives");
  document.getElementById("objectives-period").textContent = area.objectives_period || "6 prochains mois";
  const objs = area.objectives;
  const achieved = objs.filter((o) => o.achieved).length;
  document.getElementById("objectives-summary").textContent = objs.length
    ? `${plural(objs.length, "objectif", "objectifs")} · ${achieved} atteint${achieved > 1 ? "s" : ""}`
    : "aucun objectif";
  list.innerHTML = objs.length
    ? objs.map((o, i) => objectiveBlock(o, i)).join("")
    : `<li class="obj-empty" style="grid-column:1/-1;">${
        area.can_manage
          ? "Aucun objectif défini pour cette période. Ajoutez-les avec « + Objectif », chacun avec son pourcentage."
          : "Aucun objectif corporate n'a encore été défini pour cette période."
      }</li>`;
  list.removeAttribute("aria-busy");
}

// Bloc repliable : son état (ouvert/replié) est mémorisé par le navigateur, pour tous les projets.
const OBJECTIVES_COLLAPSED_KEY = "spectre:objectifs-replies";

function setObjectivesCollapsed(collapsed) {
  document.getElementById("objectives-section").classList.toggle("is-collapsed", collapsed);
  document.getElementById("objectives-toggle").setAttribute("aria-expanded", String(!collapsed));
  try {
    localStorage.setItem(OBJECTIVES_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch (err) {
    /* stockage indisponible (navigation privée...) : simple confort perdu */
  }
}

document.getElementById("objectives-toggle").addEventListener("click", () => {
  setObjectivesCollapsed(!document.getElementById("objectives-section").classList.contains("is-collapsed"));
});

(function restoreObjectivesCollapsed() {
  let collapsed = false;
  try {
    collapsed = localStorage.getItem(OBJECTIVES_COLLAPSED_KEY) === "1";
  } catch (err) {
    collapsed = false;
  }
  if (collapsed) setObjectivesCollapsed(true);
})();

// --- thématiques & µprojets -------------------------------------------------------------------

function microprojetCard(row) {
  const p = row.microproject;
  const roleBadge = p.role ? `<span class="badge badge-role">${escapeHtml(roleLabel(p.role, p.role_source))}</span>` : "";
  const inner = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:22px;">
      ${p.code ? `<span class="mp-code" title="Numéro du µprojet">${escapeHtml(p.code)}</span>` : "<span></span>"}
      ${roleBadge || `<span style="font-size:11px;color:var(--text-faint);">non membre</span>`}
    </div>
    <div style="font-size:15px;font-weight:700;line-height:1.3;overflow-wrap:anywhere;">${escapeHtml(p.name)}</div>
    <div style="font-size:13px;color:var(--text-soft);min-height:16px;">${escapeHtml(p.description || "")}</div>
    ${ownerChipHtml(p.owners)}
    <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--text-faint);padding-top:8px;border-top:1px solid var(--border-soft);">
      <span>${row.running + row.concluded + row.abandoned} expériences</span><span>${row.running} en cours</span><span>${row.concluded + row.abandoned} terminées</span><span>${row.wafers} wafers</span>
    </div>`;
  return p.role
    ? `<a href="/microprojets/${encodeURIComponent(p.slug)}" class="card card-pad" style="display:flex;flex-direction:column;gap:8px;color:inherit;">${inner}</a>`
    : `<div class="card card-pad" style="display:flex;flex-direction:column;gap:8px;opacity:.75;">${inner}</div>`;
}

function thematicSection(t, items) {
  const none = t === null;
  const name = none ? "Sans thématique" : t.name;
  const s = experimentTotals(items);
  const meta = none
    ? plural(items.length, "µprojet", "µprojets")
    : `${plural(s.microprojects, "µprojet", "µprojets")} · ${plural(s.experiments, "expérience", "expériences")} · ${s.running} en cours · ${s.wafers} wafers`;
  const thematicUrl = none ? null : `/management/${encodeURIComponent(slug)}/thematiques/${encodeURIComponent(t.slug)}`;
  const actions = none
    ? ""
    : `<div class="thematic__actions">
        <a class="btn btn-tint btn-sm" href="${thematicUrl}">Explorer la thématique ${ICON_ARROW}</a>
        ${current.can_place_microproject ? `<button type="button" class="btn btn-line btn-sm" data-new-mp="${escapeHtml(t.slug)}" aria-label="Nouveau µprojet dans ${escapeHtml(t.name)}">+ µprojet</button>` : ""}
        ${current.can_manage ? `<button type="button" class="btn btn-line btn-sm" data-edit-thematic="${escapeHtml(t.slug)}" aria-label="Modifier la thématique ${escapeHtml(t.name)}">${ICON_EDIT} Modifier</button>` : ""}
      </div>`;
  const grid = items.length
    ? `<div class="mp-grid">${items.map(microprojetCard).join("")}</div>`
    : `<div style="font-size:13px;color:var(--text-faint);padding:6px 0;">Aucun µprojet dans cette thématique pour l'instant.</div>`;
  return `
    <section class="thematic${none ? " thematic--none" : ""}">
      <div class="thematic__head">
        <div>
          <h3 class="thematic__name">${none ? escapeHtml(name) : `<a href="${thematicUrl}">${escapeHtml(name)}</a>`}</h3>
          ${!none && t.description ? `<div class="thematic__desc">${escapeHtml(t.description)}</div>` : ""}
          <div class="thematic__meta">${meta}</div>
        </div>
        ${actions}
      </div>
      ${grid}
    </section>`;
}

function renderThematics(area) {
  const byThematic = new Map(area.thematics.map((t) => [t.slug, []]));
  const orphans = [];
  for (const row of rows) {
    const thematic = row.microproject.thematic;
    (byThematic.get(thematic && thematic.slug) || orphans).push(row);
  }
  const sections = area.thematics.map((t) => thematicSection(t, byThematic.get(t.slug)));
  if (orphans.length) sections.push(thematicSection(null, orphans));
  document.getElementById("thematics").innerHTML = sections.length
    ? sections.join("")
    : `<div class="empty-state card" style="margin-top:14px;"><div style="font-weight:600;color:var(--text-soft);">Aucune thématique ni µprojet dans ce projet</div>${
        area.can_manage && !area.is_system ? `<div style="font-size:13px;color:var(--text-faint);margin-top:4px;">Commencez par créer une thématique (ex : dopage PGaN, double EBL).</div>` : ""
      }</div>`;
}

function thematicOptions(selected) {
  return [`<option value="">— Sans thématique —</option>`]
    .concat(
      current.thematics.map(
        (t) => `<option value="${escapeHtml(t.slug)}"${t.slug === selected ? " selected" : ""}>${escapeHtml(t.name)}</option>`
      )
    )
    .join("");
}

function render() {
  const area = current;
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
  document.getElementById("area-team").innerHTML = area.team
    ? `<a class="team-chip" href="/equipes/${encodeURIComponent(area.team.slug)}">Équipe <strong>${escapeHtml(area.team.name)}</strong></a>`
    : "";
  renderObjectives(area);

  const s = experimentTotals(rows);
  document.getElementById("area-kpi").innerHTML = [
    kpi(area.thematics.length, "thématiques"),
    kpi(s.microprojects, "µprojets"),
    kpi(s.experiments, "expériences"),
    kpi(s.running, "en cours"),
    kpi(s.done, "terminées"),
    kpi(s.wafers, "wafers"),
  ].join("");
  renderThematics(area);

  // le projet système (« Non classé ») ne porte ni thématique ni objectif : ses µprojets attendent d'être rangés
  const shown = {
    "edit-area-btn": area.can_manage,
    // créer ou ranger un µprojet ici : can_place_microproject (tous dans un projet sans équipe, sinon
    // ses membres et l'admin) ; rattacher un µprojet existant reste à l'admin
    "new-microprojet-btn": area.can_place_microproject,
    "attach-microprojet-btn": admin && area.can_place_microproject,
    "new-thematic-btn": area.can_manage && !area.is_system,
    "new-objective-btn": area.can_manage && !area.is_system,
  };
  for (const [id, visible] of Object.entries(shown)) document.getElementById(id).style.display = visible ? "" : "none";
  document.getElementById("ea-delete").style.display = area.can_delete ? "" : "none";
}

async function load() {
  try {
    const [me, area, stats] = await Promise.all([accountsApi.me(), areasApi.get(slug), experimentsApi.stats({ area: slug })]);
    admin = me.is_admin;
    if (admin) teams = await teamsApi.list();
    current = area;
    rows = stats;
    render();
  } catch (err) {
    showError(err);
  }
}

/** Run a write, re-read the project (and its µprojets' counts with ``withStats``, which re-reads
    their repositories), re-render, close ``dialog``, flash ``msg``. */
async function save(dialog, request, msg, { withStats = false } = {}) {
  try {
    await request();
    const [area, stats] = await Promise.all([areasApi.get(slug), withStats ? experimentsApi.stats({ area: slug }) : rows]);
    current = area;
    rows = stats;
    render();
    if (dialog) dialog.close();
    if (msg) flash(msg);
  } catch (err) {
    if (dialog) dialog.close();
    showError(err);
  }
}

// --- objectifs : ajouter / modifier / supprimer -----------------------------------------------

const objDialog = document.getElementById("objective-dialog");
let editingObjective = null;
function openObjectiveDialog(objective) {
  editingObjective = objective || null;
  document.getElementById("obj-dialog-title").textContent = objective ? "Modifier l'objectif" : "Nouvel objectif";
  document.getElementById("obj-title").value = objective ? objective.title : "";
  document.getElementById("obj-detail").value = objective ? objective.detail : "";
  document.getElementById("obj-target").value = objective ? objective.target : "";
  document.getElementById("obj-weight").value = objective && objective.weight != null ? objective.weight : "";
  document.getElementById("obj-achieved").checked = Boolean(objective && objective.achieved);
  // le µprojet qui valide : un de ce projet (numéro + nom), ou celui déjà choisi s'il est ailleurs
  const validator = objective && objective.validated_by;
  const choices = rows.map(({ microproject: p }) => ({ slug: p.slug, code: p.code, name: p.name }));
  if (validator && !choices.some((p) => p.slug === validator.slug)) choices.unshift(validator);
  const select = document.getElementById("obj-validated-by");
  select.innerHTML =
    `<option value="">— aucun —</option>` +
    choices.map((p) => `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.code ? `${p.code} · ${p.name}` : p.name)}</option>`).join("");
  select.value = validator ? validator.slug : "";
  document.getElementById("obj-delete").style.display = objective ? "" : "none";
  objDialog.showModal();
}
document.getElementById("new-objective-btn").addEventListener("click", () => openObjectiveDialog(null));
document.getElementById("obj-cancel").addEventListener("click", () => objDialog.close());
document.getElementById("objective-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const weightRaw = document.getElementById("obj-weight").value;
  const body = {
    title: document.getElementById("obj-title").value,
    detail: document.getElementById("obj-detail").value,
    target: document.getElementById("obj-target").value,
    weight: weightRaw === "" ? null : Number(weightRaw),
    achieved: document.getElementById("obj-achieved").checked,
    validated_by: document.getElementById("obj-validated-by").value || null,
  };
  const o = editingObjective;
  save(
    objDialog,
    () => (o ? areasApi.updateObjective(slug, o.id, body) : areasApi.createObjective(slug, body)),
    o ? "Objectif mis à jour." : "Objectif ajouté."
  );
});
document.getElementById("obj-delete").addEventListener("click", () => {
  const o = editingObjective;
  if (!o || !window.confirm(`Supprimer l'objectif « ${o.title} » ?`)) return;
  save(objDialog, () => areasApi.removeObjective(slug, o.id), "Objectif supprimé.");
});

document.getElementById("objectives").addEventListener("click", (event) => {
  const edit = event.target.closest("[data-edit-objective]");
  if (edit) openObjectiveDialog(current.objectives.find((o) => o.id === Number(edit.dataset.editObjective)));
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
    () => (t ? areasApi.updateThematic(slug, t.slug, body) : areasApi.createThematic(slug, body)),
    t ? "Thématique mise à jour." : "Thématique créée."
  );
});
document.getElementById("th-delete").addEventListener("click", () => {
  const t = editingThematic;
  if (!t || !window.confirm(`Supprimer la thématique « ${t.name} » ? Ses µprojets restent dans le projet, sans thématique.`)) return;
  save(thDialog, () => areasApi.removeThematic(slug, t.slug), "Thématique supprimée.");
});

document.getElementById("thematics").addEventListener("click", (event) => {
  const newMp = event.target.closest("[data-new-mp]");
  if (newMp) return openMicroprojetDialog(newMp.dataset.newMp);
  const edit = event.target.closest("[data-edit-thematic]");
  if (edit) openThematicDialog(current.thematics.find((t) => t.slug === edit.dataset.editThematic));
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
    const p = await microprojectsApi.create({
      name: document.getElementById("mp-name").value,
      description: document.getElementById("mp-description").value,
      area: slug,
      thematic: document.getElementById("mp-thematic").value || null,
    });
    // sa page propose de lancer la première expérience depuis une référence
    window.location.href = `/microprojets/${encodeURIComponent(p.slug)}?premiere-experience=1`;
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
  document.getElementById("ea-prefix").value = current.code_prefix || "";
  document.getElementById("ea-prefix-wrap").style.display = current.is_system ? "none" : ""; // il ne numérote pas ses µprojets
  // l'équipe : un admin seulement, et jamais pour le projet système (ses µprojets n'ont que leurs membres)
  const teamEditable = admin && !current.is_system;
  document.getElementById("ea-team-wrap").style.display = teamEditable ? "" : "none";
  if (teamEditable) {
    const selected = current.team ? current.team.slug : "";
    document.getElementById("ea-team").innerHTML = [`<option value="">— Aucune équipe —</option>`]
      .concat(teams.map((t) => `<option value="${escapeHtml(t.slug)}"${t.slug === selected ? " selected" : ""}>${escapeHtml(t.name)}</option>`))
      .join("");
  }
  eaDialog.showModal();
});
document.getElementById("ea-cancel").addEventListener("click", () => eaDialog.close());
document.getElementById("edit-area-form").addEventListener("submit", (event) => {
  event.preventDefault();
  save(
    eaDialog,
    () =>
      areasApi.update(slug, {
        name: document.getElementById("ea-name").value,
        description: document.getElementById("ea-description").value,
        strategy: document.getElementById("ea-strategy").value,
        objectives_period: document.getElementById("ea-period").value,
        ...(current.is_system ? {} : { code_prefix: document.getElementById("ea-prefix").value }),
        ...(admin && !current.is_system ? { team: document.getElementById("ea-team").value || null } : {}),
      }),
    "Projet mis à jour."
  );
});
document.getElementById("ea-delete").addEventListener("click", async () => {
  if (!window.confirm(`Supprimer le projet « ${current.name} » ? Ses thématiques et objectifs sont supprimés, ses µprojets repassent en « Non classé ».`)) return;
  try {
    await areasApi.remove(slug);
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
    const all = await microprojectsApi.list({ scope: "all" });
    const select = document.getElementById("attach-select");
    select.innerHTML = all.length
      ? all
          .map((p) => {
            const where = [p.area && p.area.name, p.thematic && p.thematic.name].filter(Boolean).join(" › ");
            return `<option value="${escapeHtml(p.slug)}">${p.code ? `${escapeHtml(p.code)} · ` : ""}${escapeHtml(p.name)}${where ? ` — ${escapeHtml(where)}` : ""}</option>`;
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
      microprojectsApi.update(microprojectSlug, {
        area: slug,
        thematic: document.getElementById("attach-thematic").value || null,
      }),
    "µprojet rattaché.",
    { withStats: true }
  );
});

load();
