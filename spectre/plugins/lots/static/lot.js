/* Fiche d'un lot (/lots/{code}) : sa priorité (P10, P20...), son début, sa fin prévisionnelle et sa
   fin déclarée, son planning et ses expériences sur le Gantt (lots-gantt.js), ses wafers, ses
   thématiques et ses expériences liées (retrouvées par ses wafers). Tout est saisi à la main pour
   l'instant - voir spectre.plugins.lots. L'adresse porte le code du lot : la page le résout
   (lotsApi.list({code})), puis travaille par son id. Les règles de statut (fin déclarée = sorti...)
   sont celles du serveur : la page envoie ce qui a été saisi et affiche le lot qu'il renvoie. */

const { code } = routeParams("/lots/{code}");
let lot = null;

const errorBox = document.getElementById("error");
const flashBox = document.getElementById("flash");
function showError(err) {
  flashBox.style.display = "none";
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function flash(msg) {
  errorBox.style.display = "none";
  flashBox.textContent = msg;
  flashBox.style.display = "block";
  setTimeout(() => (flashBox.style.display = "none"), 3000);
}

function kpi(value, label, { wide = false, alert = false, note = "" } = {}) {
  return `<div class="kpi${wide ? " kpi--wide" : ""}${alert ? " kpi--alert" : ""}"><div class="kpi__value">${value}</div><div class="kpi__label">${label}</div>${
    note ? `<div class="kpi__note">${escapeHtml(note)}</div>` : ""
  }</div>`;
}

// --- rendu ------------------------------------------------------------------------------------

function renderHead() {
  document.title = `${lot.code} — Lots — Spectre`;
  document.getElementById("crumb").textContent = `/ Lots / ${lot.code}`;
  document.getElementById("lot-crumb").textContent = lot.code;
  document.getElementById("lot-code").innerHTML = `${lotPriorityHtml(lot.priority)}${escapeHtml(lot.code)} ${lotStatusBadgeHtml(lot.status)}`;
  document.getElementById("lot-title").textContent = lot.title || "";
  document.getElementById("lot-description").textContent = lot.description || "";
  document.getElementById("delete-lot-btn").style.display = lot.can_delete ? "" : "none";
  document.getElementById("declare-end-btn").style.display = lot.is_active ? "" : "none";
  const banners = [];
  if (lot.status === "hold") {
    banners.push(`<div class="lot-banner lot-banner--hold">Lot en pause${lot.hold_reason ? ` · <span>${escapeHtml(lot.hold_reason)}</span>` : ""}</div>`);
  }
  if (lot.late_days) {
    banners.push(`<div class="lot-banner lot-banner--late">En retard de ${lot.late_days} j sur la fin prévisionnelle (${escapeHtml(lotDateLabel(lot.forecast_exit_on))})</div>`);
  }
  if (lot.status === "done" && lot.exit_delta_days) {
    const late = lot.exit_delta_days > 0;
    banners.push(`<div class="lot-banner lot-banner--${late ? "late" : "early"}">Sorti avec ${escapeHtml(lotDeltaLabel(lot.exit_delta_days))} sur la prévision (${escapeHtml(lotDateLabel(lot.forecast_exit_on))})</div>`);
  }
  document.getElementById("lot-banners").innerHTML = banners.join("");
}

function renderKpis() {
  const done = lot.status === "done";
  const started = lot.started_on && lotDay(lot.started_on) <= lotTodayStart();
  const duration = lot.elapsed_days != null ? `${lot.elapsed_days} j` : "—";
  const box = document.getElementById("lot-kpis");
  box.innerHTML = [
    kpi(lot.priority ? escapeHtml(lot.priority) : "—", "priorité", { wide: true }),
    kpi(escapeHtml(lotDateLabel(lot.started_on) || "—"), "début", { note: lot.started_on && !started ? "à venir" : "" }),
    kpi(escapeHtml(lotDateLabel(lot.forecast_exit_on) || "—"), "fin prévisionnelle", {
      alert: Boolean(lot.late_days),
      note: lot.late_days ? `+${lot.late_days} j de retard` : lot.planned_days != null ? `${lot.planned_days} j prévus` : "",
    }),
    kpi(escapeHtml(lotDateLabel(lot.exited_on) || "—"), "fin déclarée", {
      alert: done && lot.exit_delta_days > 0,
      note: done && lot.exit_delta_days != null ? lotDeltaLabel(lot.exit_delta_days) : "",
    }),
    kpi(duration, done ? "durée" : "écoulé"),
    kpi(lot.wafers.length, "wafers"),
    kpi(lot.experiments.length, "expériences liées"),
  ].join("");
  box.removeAttribute("aria-busy");
}

const ganttScroll = document.getElementById("gantt-scroll");
function renderGantt() {
  ganttScroll.innerHTML = ganttHtml([lot], ganttScroll.clientWidth || 1100, { alwaysExpanded: true, link: false });
}

function renderWafers() {
  document.getElementById("wafers-count").textContent = lot.wafers.length;
  document.getElementById("wafers").innerHTML = lot.wafers.length
    ? lot.wafers
        .map((w) => {
          const uses = w.experiments.length
            ? w.experiments
                .map((u) => {
                  const mp = u.microproject.code || u.microproject.name;
                  return u.member
                    ? `<a class="lot-chip" href="/microprojets/${encodeURIComponent(u.microproject.slug)}/experiences/${encodeURIComponent(u.id)}" title="${escapeHtml(u.title)}">${escapeHtml(mp)} · ${escapeHtml(u.title)}</a>`
                    : `<span class="lot-chip" title="µprojet dont vous n'êtes pas membre">${escapeHtml(mp)}</span>`;
                })
                .join("")
            : `<span>pas encore suivi par une expérience</span>`;
          return `<li class="wafer">
              <a class="wafer__mark" href="${plateUrl(w.lasermark)}">${escapeHtml(w.lasermark)}</a>
              <span class="wafer__uses">${uses}</span>
              <button type="button" class="wafer__remove" data-remove="${escapeHtml(w.key)}" data-lasermark="${escapeHtml(w.lasermark)}" aria-label="Retirer ${escapeHtml(w.lasermark)} du lot" title="Retirer du lot"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
            </li>`;
        })
        .join("")
    : `<li class="help">Aucun wafer dans ce lot pour l'instant.</li>`;
}

function renderThematics() {
  document.getElementById("thematics").innerHTML = lot.thematics.length
    ? lot.thematics
        .map(
          (t) =>
            `<a class="lot-chip${t.declared && !t.via_experiments ? " lot-chip--declared" : ""}" href="/management/${encodeURIComponent(t.area.slug)}/thematiques/${encodeURIComponent(t.slug)}" title="${escapeHtml(t.area.name)} › ${escapeHtml(t.name)}${t.declared ? " - visée" : ""}${t.via_experiments ? " - via ses expériences" : ""}">${escapeHtml(t.name)}</a>`
        )
        .join("")
    : `<span class="help">Aucune thématique pour l'instant.</span>`;
}

function renderExperiences() {
  const groups = new Map();
  for (const e of lot.experiments) {
    const key = e.microproject.slug;
    if (!groups.has(key)) groups.set(key, { mp: e.microproject, items: [] });
    groups.get(key).items.push(e);
  }
  document.getElementById("experiences").innerHTML = groups.size
    ? [...groups.values()]
        .map(
          ({ mp, items }) => `<div class="mp-group">
            <div class="mp-group__head">${mp.code ? `<span class="mp-code">${escapeHtml(mp.code)}</span>` : ""}<a href="/microprojets/${encodeURIComponent(mp.slug)}">${escapeHtml(mp.name)}</a></div>
            ${items
              .map(
                (e) => `<div class="exp-row">
                  ${statusBadgeHtml(e.status, e.decision)}
                  <span class="exp-row__title">${
                    e.id
                      ? `<a href="/microprojets/${encodeURIComponent(mp.slug)}/experiences/${encodeURIComponent(e.id)}">${escapeHtml(e.title)}</a>`
                      : `<span class="gantt__muted">Expérience d'un µprojet dont vous n'êtes pas membre</span>`
                  }</span>
                  <span class="exp-row__meta">${escapeHtml(lineageElapsedLabel(e))} · ${escapeHtml(e.wafers.join(", "))}</span>
                </div>`
              )
              .join("")}
          </div>`
        )
        .join("")
    : `<p class="help">Aucune expérience ne suit encore un wafer de ce lot. Dès qu'une expérience renseigne un de ses lasermarks (suivi physique), elle apparaît ici - et un badge du lot s'affiche à côté de son nœud dans le graphe du µprojet.</p>`;
}

function render(data) {
  lot = data;
  // le code a changé (modification) : l'adresse suit
  if (lotUrl(lot.code) !== window.location.pathname) history.replaceState(null, "", lotUrl(lot.code));
  renderHead();
  renderKpis();
  renderGantt();
  renderWafers();
  renderThematics();
  renderExperiences();
}

async function load() {
  try {
    const [found] = await lotsApi.list({ code, view: "summary" });
    if (!found) throw new Error(`Lot « ${code} » introuvable.`);
    render(await lotsApi.get(found.id));
  } catch (err) {
    showError(err);
    document.getElementById("lot-code").textContent = code || "Lot introuvable";
  }
}

lotsApi
  .priorities()
  .then((priorities) => {
    document.getElementById("lot-priorities").innerHTML = priorities.map((p) => `<option value="${escapeHtml(p)}">`).join("");
  })
  .catch(() => {}); // suggestions seulement

// Une écriture qui renvoie le lot à jour : re-rendu, fermeture du dialogue, message. -> réussie ?
async function save(request, msg, dialog) {
  try {
    render(await request());
    if (dialog) dialog.close();
    if (msg) flash(msg);
    return true;
  } catch (err) {
    if (dialog) dialog.close();
    showError(err);
    return false;
  }
}

// --- informations du lot (dont la fin déclarée) -------------------------------------------------

const editDialog = document.getElementById("edit-dialog");
const statusField = document.getElementById("ed-status");
const exitedField = document.getElementById("ed-exited");
function syncHoldField() {
  document.getElementById("ed-hold-wrap").style.display = statusField.value === "hold" ? "" : "none";
}
statusField.addEventListener("change", syncHoldField);

// les champs du formulaire -> ceux du lot (une date vide : null)
const EDIT_FIELDS = {
  code: "ed-code",
  priority: "ed-priority",
  status: "ed-status",
  hold_reason: "ed-hold",
  title: "ed-title",
  started_on: "ed-started",
  forecast_exit_on: "ed-forecast",
  exited_on: "ed-exited",
  description: "ed-description",
};
const DATE_FIELDS = ["started_on", "forecast_exit_on", "exited_on"];

// « Déclarer la fin » : la date de fin déclarée, aujourd'hui par défaut (le serveur en fait un lot sorti)
function openEditDialog({ declareEnd = false } = {}) {
  Object.entries(EDIT_FIELDS).forEach(([name, id]) => (document.getElementById(id).value = lot[name] || ""));
  if (declareEnd) exitedField.value = exitedField.value || lotTodayIso();
  syncHoldField();
  editDialog.showModal();
  (declareEnd ? exitedField : document.getElementById("ed-code")).focus();
}
document.getElementById("edit-lot-btn").addEventListener("click", () => openEditDialog());
document.getElementById("declare-end-btn").addEventListener("click", () => openEditDialog({ declareEnd: true }));
document.getElementById("ed-cancel").addEventListener("click", () => editDialog.close());
document.getElementById("edit-form").addEventListener("submit", (event) => {
  event.preventDefault();
  // seulement ce qui a changé, avec la version affichée (If-Match : 412 si le lot a bougé entre-temps)
  const changes = {};
  Object.entries(EDIT_FIELDS).forEach(([name, id]) => {
    const value = document.getElementById(id).value;
    const typed = DATE_FIELDS.includes(name) ? value || null : value;
    if (typed !== (DATE_FIELDS.includes(name) ? lot[name] || null : lot[name] || "")) changes[name] = typed;
  });
  save(() => lotsApi.update(lot.id, changes, lot.updated_at), "Lot mis à jour.", editDialog);
});
document.getElementById("delete-lot-btn").addEventListener("click", async () => {
  if (!window.confirm(`Supprimer le lot ${lot.code} ? Ses wafers et ses expériences ne sont pas touchés - seul le suivi du lot disparaît.`)) return;
  try {
    await lotsApi.remove(lot.id);
    window.location.href = "/lots";
  } catch (err) {
    showError(err);
  }
});

// --- wafers ----------------------------------------------------------------------------------

document.getElementById("wafer-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.getElementById("wafer-input");
  const lasermarks = input.value.split(/[\s,;]+/).filter(Boolean);
  if (!lasermarks.length) return;
  save(() => lotsApi.addWafers(lot.id, { lasermarks }), `${lasermarks.length} wafer${lasermarks.length > 1 ? "s" : ""} ajouté${lasermarks.length > 1 ? "s" : ""}.`).then((ok) => {
    if (ok) input.value = "";
  });
});
document.getElementById("wafers").addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove]");
  if (!button) return;
  const lasermark = button.dataset.lasermark;
  if (!window.confirm(`Retirer ${lasermark} du lot ${lot.code} ?`)) return;
  save(async () => {
    await lotsApi.removeWafer(lot.id, button.dataset.remove);
    return lotsApi.get(lot.id);
  }, `${lasermark} retiré du lot.`);
});

// --- thématiques visées --------------------------------------------------------------------------

const thematicsDialog = document.getElementById("thematics-dialog");
document.getElementById("edit-thematics-btn").addEventListener("click", async () => {
  try {
    // toutes les thématiques, à plat ({id, name, area}) : groupées ici par projet corporate
    const groups = new Map();
    for (const t of await areasApi.listThematics()) {
      if (!groups.has(t.area.slug)) groups.set(t.area.slug, { area: t.area, thematics: [] });
      groups.get(t.area.slug).thematics.push(t);
    }
    const declared = new Set(lot.thematics.filter((t) => t.declared).map((t) => t.id));
    document.getElementById("thematic-picker").innerHTML = groups.size
      ? [...groups.values()]
          .map(
            (g) => `<fieldset><legend>${escapeHtml(g.area.name)}</legend>${g.thematics
              .map((t) => `<label><input type="checkbox" value="${t.id}"${declared.has(t.id) ? " checked" : ""}> ${escapeHtml(t.name)}</label>`)
              .join("")}</fieldset>`
          )
          .join("")
      : `<p class="help">Aucune thématique n'existe encore (elles se créent sur la page d'un projet corporate).</p>`;
    thematicsDialog.showModal();
  } catch (err) {
    showError(err);
  }
});
document.getElementById("thematics-cancel").addEventListener("click", () => thematicsDialog.close());
document.getElementById("thematics-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const ids = [...document.querySelectorAll("#thematic-picker input:checked")].map((i) => Number(i.value));
  save(() => lotsApi.setThematics(lot.id, { thematic_ids: ids }), "Thématiques enregistrées.", thematicsDialog);
});

mountGanttTooltip(ganttScroll);
let resizeTimer = null;
new ResizeObserver(() => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => lot && renderGantt(), 120);
}).observe(ganttScroll);

load();
