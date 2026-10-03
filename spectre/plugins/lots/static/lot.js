/* Fiche d'un lot (/lots/{code}) : sa priorité (P10, P20...), son début, sa fin prévisionnelle et sa
   fin déclarée, son planning et ses expériences sur le Gantt (lots-gantt.js), ses wafers, ses
   thématiques et ses expériences liées (retrouvées par ses wafers). Tout est saisi à la main pour
   l'instant - voir spectre.api.lots. */

const { code } = routeParams("/lots/{code}");
let lotCode = code;
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
  document.getElementById("declare-end-btn").style.display = ["planned", "wip", "hold"].includes(lot.status) ? "" : "none";
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
    kpi(lot.experiences.length, "expériences liées"),
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
          const uses = w.experiences.length
            ? w.experiences
                .map((u) =>
                  u.id
                    ? `<a class="lot-chip" href="/microprojets/${encodeURIComponent(u.slug)}/experiences/${encodeURIComponent(u.id)}" title="${escapeHtml(u.title)}">${escapeHtml(u.microproject)} · ${escapeHtml(u.title)}</a>`
                    : `<span class="lot-chip" title="µprojet dont vous n'êtes pas membre">${escapeHtml(u.microproject)}</span>`
                )
                .join("")
            : `<span>pas encore suivi par une expérience</span>`;
          return `<li class="wafer">
              <a class="wafer__mark" href="${plateUrl(w.lasermark)}">${escapeHtml(w.lasermark)}</a>
              <span class="wafer__uses">${uses}</span>
              <button type="button" class="wafer__remove" data-remove="${escapeHtml(w.lasermark)}" aria-label="Retirer ${escapeHtml(w.lasermark)} du lot" title="Retirer du lot"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
            </li>`;
        })
        .join("")
    : `<li class="help">Aucun wafer dans ce lot pour l'instant.</li>`;
}

function renderThematics() {
  document.getElementById("thematics").innerHTML = lot.thematiques.length
    ? lot.thematiques
        .map(
          (t) =>
            `<a class="lot-chip${t.declared && !t.via_experiences ? " lot-chip--declared" : ""}" href="/management/${encodeURIComponent(t.area.slug)}/thematiques/${encodeURIComponent(t.slug)}" title="${escapeHtml(t.area.name)} › ${escapeHtml(t.name)}${t.declared ? " - visée" : ""}${t.via_experiences ? " - via ses expériences" : ""}">${escapeHtml(t.name)}</a>`
        )
        .join("")
    : `<span class="help">Aucune thématique pour l'instant.</span>`;
}

function renderExperiences() {
  const groups = new Map();
  for (const e of lot.experiences) {
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
  if (lot.code !== code) {
    // le code a changé (modification) : l'adresse suit
    history.replaceState(null, "", lotUrl(lot.code));
    lotCode = lot.code;
  }
  renderHead();
  renderKpis();
  renderGantt();
  renderWafers();
  renderThematics();
  renderExperiences();
}

async function load() {
  try {
    render(await lotsApi.get(lotCode));
  } catch (err) {
    showError(err);
    document.getElementById("lot-code").textContent = code || "Lot introuvable";
  }
}

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
// une fin déclarée = lot sorti ; repasser à un statut « pas fini » efface la fin déclarée
exitedField.addEventListener("change", () => {
  if (exitedField.value && statusField.value !== "cancelled") statusField.value = "done";
  syncHoldField();
});
statusField.addEventListener("change", () => {
  if (statusField.value === "done" && !exitedField.value) exitedField.value = lotTodayIso();
  if (!["done", "cancelled"].includes(statusField.value)) exitedField.value = "";
  syncHoldField();
});

function openEditDialog({ declareEnd = false } = {}) {
  document.getElementById("ed-code").value = lot.code;
  document.getElementById("ed-priority").value = lot.priority || "";
  statusField.value = lot.status;
  document.getElementById("ed-hold").value = lot.hold_reason || "";
  document.getElementById("ed-title").value = lot.title || "";
  document.getElementById("ed-started").value = lot.started_on || "";
  document.getElementById("ed-forecast").value = lot.forecast_exit_on || "";
  exitedField.value = lot.exited_on || "";
  document.getElementById("ed-description").value = lot.description || "";
  if (declareEnd) {
    statusField.value = "done";
    exitedField.value = exitedField.value || lotTodayIso();
  }
  syncHoldField();
  editDialog.showModal();
  (declareEnd ? exitedField : document.getElementById("ed-code")).focus();
}
document.getElementById("edit-lot-btn").addEventListener("click", () => openEditDialog());
document.getElementById("declare-end-btn").addEventListener("click", () => openEditDialog({ declareEnd: true }));
document.getElementById("ed-cancel").addEventListener("click", () => editDialog.close());
document.getElementById("edit-form").addEventListener("submit", (event) => {
  event.preventDefault();
  save(
    () =>
      lotsApi.update(lotCode, {
        code: document.getElementById("ed-code").value,
        priority: document.getElementById("ed-priority").value,
        status: statusField.value,
        hold_reason: document.getElementById("ed-hold").value,
        title: document.getElementById("ed-title").value,
        started_on: document.getElementById("ed-started").value || null,
        forecast_exit_on: document.getElementById("ed-forecast").value || null,
        exited_on: exitedField.value || null,
        description: document.getElementById("ed-description").value,
      }),
    "Lot mis à jour.",
    editDialog
  );
});
document.getElementById("delete-lot-btn").addEventListener("click", async () => {
  if (!window.confirm(`Supprimer le lot ${lot.code} ? Ses wafers et ses expériences ne sont pas touchés - seul le suivi du lot disparaît.`)) return;
  try {
    await lotsApi.remove(lotCode);
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
  save(() => lotsApi.addWafers(lotCode, { lasermarks }), `${lasermarks.length} wafer${lasermarks.length > 1 ? "s" : ""} ajouté${lasermarks.length > 1 ? "s" : ""}.`).then((ok) => {
    if (ok) input.value = "";
  });
});
document.getElementById("wafers").addEventListener("click", (event) => {
  const button = event.target.closest("[data-remove]");
  if (!button) return;
  const lasermark = button.dataset.remove;
  if (!window.confirm(`Retirer ${lasermark} du lot ${lot.code} ?`)) return;
  save(() => lotsApi.removeWafer(lotCode, lasermark), `${lasermark} retiré du lot.`);
});

// --- thématiques visées --------------------------------------------------------------------------

const thematicsDialog = document.getElementById("thematics-dialog");
document.getElementById("edit-thematics-btn").addEventListener("click", async () => {
  try {
    const options = await lotsApi.thematicOptions();
    const declared = new Set(lot.thematiques.filter((t) => t.declared).map((t) => t.id));
    document.getElementById("thematic-picker").innerHTML = options.length
      ? options
          .map(
            (g) => `<fieldset><legend>${escapeHtml(g.area.name)}</legend>${g.thematiques
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
  save(() => lotsApi.setThematics(lotCode, { thematic_ids: ids }), "Thématiques enregistrées.", thematicsDialog);
});

mountGanttTooltip(ganttScroll);
let resizeTimer = null;
new ResizeObserver(() => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => lot && renderGantt(), 120);
}).observe(ganttScroll);

load();
