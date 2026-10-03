/* Page d'un projet corporate (/management/{slug}) - trois niveaux : le projet (Native, VLC, Nova),
   ses thématiques (dopage PGaN, double EBL...), et sous chacune les µprojets (chaînes
   d'expériences). En tête, dans un bloc repliable, les objectifs corporate de la période : chacun
   porte un pourcentage (un chiffre de 0 à 100 % servant au calcul du bonus, simplement noté - les
   objectifs sont classés par lui), et peut être marqué atteint, avec le µprojet qui l'a validé.
   Un admin édite tout (objectifs, thématiques, rattachements) ; chacun peut créer un µprojet.
   Chaque µprojet porte son numéro (Nat_0004) : la recherche de la topbar y mène directement.
   Voir spectre.api.management. */

const { slug } = routeParams("/management/{slug}");
document.getElementById("atlas-link").href = `/management/${encodeURIComponent(slug)}/atlas`;

// Tendances, juste sous les objectifs : bloc KPI à onglets réutilisable (kpis/static/kpi-trend.js), un
// onglet par KPI déclaré côté serveur (spectre/core/trends.py).
KpiTrendBlock.mount(document.getElementById("trends"), {
  eyebrow: "Tendances",
  title: "Évolution des KPI",
  loadKpis: () => kpisApi.list(slug),
  loadSeries: (key, months, variant) => kpisApi.series(slug, key, months, variant),
  storageKey: `spectre:tendances:${slug}`,
  // un point jalon (étude) d'une tendance -> sa fiche (aujourd'hui : données de démo EQE)
  onPointClick: (point, series) => openStudy(series.key, point.study),
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
function objectiveBlock(o, index, admin) {
  const tools = admin
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
  const admin = area.is_admin;
  document.getElementById("objectives-period").textContent = area.objectives_period || "6 prochains mois";
  const objs = area.objectifs || [];
  const achieved = objs.filter((o) => o.achieved).length;
  document.getElementById("objectives-summary").textContent = objs.length
    ? `${plural(objs.length, "objectif", "objectifs")} · ${achieved} atteint${achieved > 1 ? "s" : ""}`
    : "aucun objectif";
  list.innerHTML = objs.length
    ? objs.map((o, i) => objectiveBlock(o, i, admin)).join("")
    : `<li class="obj-empty" style="grid-column:1/-1;">${
        admin
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

function microprojetCard(p) {
  const roleBadge = p.role ? `<span class="badge badge-role">${escapeHtml(roleLabel(p.role))}</span>` : "";
  const inner = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:22px;">
      ${p.code ? `<span class="mp-code" title="Numéro du µprojet">${escapeHtml(p.code)}</span>` : "<span></span>"}
      ${roleBadge || `<span style="font-size:11px;color:var(--text-faint);">non membre</span>`}
    </div>
    <div style="font-size:15px;font-weight:700;line-height:1.3;overflow-wrap:anywhere;">${escapeHtml(p.name)}</div>
    <div style="font-size:13px;color:var(--text-soft);min-height:16px;">${escapeHtml(p.description || "")}</div>
    ${ownerChipHtml(p.owners)}
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
  const thematicUrl = none ? null : `/management/${encodeURIComponent(slug)}/thematiques/${encodeURIComponent(t.slug)}`;
  const actions = none
    ? ""
    : `<div class="thematic__actions">
        <a class="btn btn-tint btn-sm" href="${thematicUrl}">Explorer la thématique ${ICON_ARROW}</a>
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
    render(await areasApi.get(slug));
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
  document.getElementById("obj-weight").value = objective && objective.weight != null ? objective.weight : "";
  document.getElementById("obj-achieved").checked = Boolean(objective && objective.achieved);
  // le µprojet qui valide : un de ce projet (numéro + nom), ou celui déjà choisi s'il est ailleurs
  const validator = objective && objective.validated_by;
  const choices = current.microprojets.map((p) => ({ slug: p.slug, code: p.code, name: p.name }));
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
    const p = await microprojectsApi.create({
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
  document.getElementById("ea-prefix").value = current.code_prefix || "";
  document.getElementById("ea-prefix-wrap").style.display = current.slug === "non-classe" ? "none" : "";
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
        code_prefix: current.slug === "non-classe" ? null : document.getElementById("ea-prefix").value,
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
    const all = await microprojectsApi.listAll();
    const select = document.getElementById("attach-select");
    select.innerHTML = all.length
      ? all
          .map((p) => {
            const where = [p.management_area && p.management_area.name, p.thematique && p.thematique.name].filter(Boolean).join(" › ");
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
      areasApi.assignMicroproject(slug, {
        microproject_slug: microprojectSlug,
        thematique_slug: document.getElementById("attach-thematic").value || null,
      }),
    "µprojet rattaché."
  );
});

// --- fiche d'étude derrière un point de tendance (démo) -----------------------------------------

const studyDialog = document.getElementById("study-dialog");
const DIRECTION_LABELS = { maximize: "Maximiser", minimize: "Minimiser", target: "Cible précise", observe: "Observer" };

// Vue symbolique de l'arbre d'expériences : la ligne principale des études (en haut), les pistes
// secondaires en dessous ; le chemin jusqu'à l'étude affichée est tracé, la suite estompée.
function studyTreeSvg(tree) {
  const colW = 118;
  const laneH = 58;
  const pad = 52; // place pour les libellés centrés sous les nœuds des bords
  const cols = Math.max(...tree.nodes.map((n) => n.col)) + 1;
  const lanes = Math.max(...tree.nodes.map((n) => n.lane)) + 1;
  const width = pad * 2 + (cols - 1) * colW;
  const height = pad + (lanes - 1) * laneH + 34;
  const pos = new Map(tree.nodes.map((n) => [n.id, { x: pad + n.col * colW, y: pad + n.lane * laneH, node: n }]));
  const edges = tree.edges
    .map(([from, to]) => {
      const a = pos.get(from);
      const b = pos.get(to);
      const onPath = b.node.state !== "future" && a.node.state !== "future";
      const d = a.y === b.y ? `M${a.x},${a.y} L${b.x},${b.y}` : `M${a.x},${a.y} C${a.x + colW * 0.55},${a.y} ${b.x - colW * 0.55},${b.y} ${b.x},${b.y}`;
      return `<path class="tree-edge${onPath ? " is-path" : ""}" d="${d}"/>`;
    })
    .join("");
  const nodes = tree.nodes
    .map((n) => {
      const { x, y } = pos.get(n.id);
      const status = n.status === "abandoned" ? " is-abandoned" : n.status === "inconclusive" ? " is-inconclusive" : "";
      const study = n.lane === 0 ? ` data-study="${escapeHtml(n.id)}" tabindex="0" role="button" aria-label="Ouvrir l'étude ${escapeHtml(n.title)}"` : "";
      return `<g class="tree-node is-${n.state}${status}" transform="translate(${x},${y})"${study}>
          <title>${escapeHtml(n.title)}</title>
          <circle r="${n.state === "current" ? 10 : 8}"></circle>
          <text y="24" text-anchor="middle">${escapeHtml(n.label)}</text>
        </g>`;
    })
    .join("");
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Arbre des expériences de l'étude">${edges}${nodes}</svg>`;
}

function studyHtml(study) {
  const r = study.result;
  const delta = r.previous != null ? `<span class="study__result-delta">${r.value - r.previous >= 0 ? "+" : ""}${(r.value - r.previous).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} pt</span> vs étude précédente · ` : "";
  const o = study.objective;
  const [year, month] = study.period.split("-");
  const when = new Date(Number(year), Number(month) - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
  return `
    <div class="study__head">
      <div>
        <div class="study__badges">
          ${study.demo ? `<span class="study__demo">Démo · fiche fictive</span>` : ""}
          <span class="study__where">${escapeHtml(study.project)} › ${escapeHtml(study.microproject)} · conclue en ${escapeHtml(when)}</span>
        </div>
        <h2 class="study__title" id="study-title">${escapeHtml(study.title)}</h2>
        <p class="study__change">${escapeHtml(study.change)}</p>
      </div>
      <button type="button" class="btn btn-line btn-sm" id="study-close">Fermer</button>
    </div>
    <div class="study__grid">
      <div class="study__panel">
        <div class="study__panel-title">Structure</div>
        <div class="study__svg">${study.structure_svg}</div>
        <div class="study__legend">${study.materials.map((m) => `<span><i style="background:${escapeHtml(study.material_colors[m] || "var(--text-faint)")};"></i>${escapeHtml(m)}</span>`).join("")}</div>
        <details class="study__steps"><summary>Procédé (${study.steps.length} étapes)</summary><ol>${study.steps.map((name) => `<li>${escapeHtml(name)}</li>`).join("")}</ol></details>
      </div>
      <div>
        <div class="study__panel">
          <div class="study__panel-title">Résultat</div>
          <div class="study__result">
            <span class="study__result-value">${escapeHtml(r.metric)} ${r.value.toLocaleString("fr-FR")} ${escapeHtml(r.unit)}</span>
          </div>
          <div class="study__result-meta">${delta}objectif ${r.target.toLocaleString("fr-FR")} ${escapeHtml(r.unit)}</div>
        </div>
        <div class="study__panel">
          <div class="study__panel-title">Objectif</div>
          <div class="study__objective-name">${escapeHtml(o.name)}</div>
          <div class="study__meta">${escapeHtml(DIRECTION_LABELS[o.direction] || o.direction)} · cible ${o.target.toLocaleString("fr-FR")} % · <strong>${escapeHtml(o.status)}</strong></div>
          <div class="study__meta">${escapeHtml(o.rationale)}</div>
        </div>
        <div class="study__panel">
          <div class="study__panel-title">Conclusion</div>
          ${statusBadgeHtml("concluded", study.conclusion.decision)}
          <p class="study__conclusion">${escapeHtml(study.conclusion.summary)}</p>
        </div>
      </div>
    </div>
    <div class="study__panel study__tree">
      <div class="study__panel-title">Arbre d'expériences</div>
      ${studyTreeSvg(study.tree)}
      <div class="tree-legend"><span>● étude de la ligne principale (cliquer pour l'ouvrir)</span><span>◌ piste abandonnée ou non concluante</span></div>
    </div>`;
}

async function openStudy(kpiKey, studyId) {
  if (!kpiKey || !studyId) return;
  const box = document.getElementById("study-content");
  if (!studyDialog.open) {
    box.innerHTML = `<div class="skeleton" style="height:420px;"></div>`;
    studyDialog.showModal();
  }
  try {
    const study = await kpisDemoApi.study(slug, kpiKey, studyId);
    box.innerHTML = studyHtml(study);
    box.dataset.kpi = kpiKey;
    document.getElementById("study-close").focus();
  } catch (err) {
    box.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div><button type="button" class="btn btn-line btn-sm" id="study-close" style="margin-top:12px;">Fermer</button>`;
  }
}

document.getElementById("study-content").addEventListener("click", (event) => {
  if (event.target.closest("#study-close")) return studyDialog.close();
  const node = event.target.closest("[data-study]");
  if (node) openStudy(document.getElementById("study-content").dataset.kpi, node.dataset.study);
});
document.getElementById("study-content").addEventListener("keydown", (event) => {
  const node = event.target.closest && event.target.closest("[data-study]");
  if (node && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    openStudy(document.getElementById("study-content").dataset.kpi, node.dataset.study);
  }
});
studyDialog.addEventListener("click", (event) => {
  if (event.target === studyDialog) studyDialog.close(); // clic sur le fond
});

load();
