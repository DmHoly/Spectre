/* Page « Planning » (/planning, /planning/{team_slug}) : les plaques d'une équipe par thématique ▸
   µprojet ▸ épi, leurs lots (en cours, sortis, prévus) en colonnes et sur une frise par semaine, les
   expériences prévues en lignes fantômes. Cocher des plaques les met dans un lot prévu (un lot du
   plugin lots au statut « planned » : lotsApi.create / addWafers) ; cliquer une épi ouvre son panneau
   (fiche : experimentsApi.get, cahier : notebookApi.entries). */

const DAY = 86400000;
const WEEK = 7 * DAY;
const WEEKS_BEFORE = 10;
const WEEKS_SHOWN = 26;
const ENDED = new Set(["concluded", "abandoned", "continued"]);

const errorBox = document.getElementById("error");
const grid = document.getElementById("plan-grid");
const selection = new Map(); // clé de plaque -> {lasermark, thematicId}
const collapsed = new Set();
let board = null;
let lotsById = new Map();
let lotsByWafer = new Map();
let offsetWeeks = 0;
let filter = "all";
let query = "";
let areaFilter = "";

function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

// --- dates -------------------------------------------------------------------------------------

function day(iso) {
  if (!iso) return null;
  const d = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(d.getTime()) ? null : new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function mondayOf(d) {
  const m = new Date(d);
  m.setDate(m.getDate() - ((m.getDay() + 6) % 7));
  return m;
}

// numéro de semaine ISO 8601
function isoWeek(d) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
  const yearStart = new Date(Date.UTC(t.getUTCFullYear(), 0, 1));
  return Math.ceil(((t - yearStart) / DAY + 1) / 7);
}

function shortDate(d) {
  return d ? d.toLocaleDateString("fr-FR", { day: "numeric", month: "short" }) : "";
}

function today() {
  return day(board.today) || day(new Date().toISOString());
}

function windowRange() {
  const start = new Date(mondayOf(today()).getTime() - (WEEKS_BEFORE - offsetWeeks) * WEEK);
  return { start, end: new Date(start.getTime() + WEEKS_SHOWN * WEEK) };
}

// --- lots --------------------------------------------------------------------------------------

function indexLots() {
  lotsById = new Map(board.lots.map((lot) => [lot.id, lot]));
  lotsByWafer = new Map();
  for (const lot of board.lots) {
    for (const key of lot.wafers) {
      if (!lotsByWafer.has(key)) lotsByWafer.set(key, []);
      lotsByWafer.get(key).push(lot);
    }
  }
}

// ce que la frise dessine d'un lot : [début, fin], et si la fin n'est qu'une prévision
function lotSpan(lot) {
  const start = day(lot.started_on) || (lot.status === "planned" ? today() : null);
  if (!start) return null;
  const end = day(lot.exited_on) || day(lot.forecast_exit_on) || new Date(Math.max(start.getTime(), today().getTime()) + 2 * WEEK);
  return { start, end: end < start ? start : end, forecast: !lot.exited_on };
}

const LOT_STATUS = {
  planned: { label: "prévu", cls: "planned" },
  wip: { label: "en cours", cls: "wip" },
  hold: { label: "en pause", cls: "hold" },
  done: { label: "sorti", cls: "done" },
  cancelled: { label: "annulé", cls: "cancelled" },
};

function lotChip(lot, { removable, waferKey } = {}) {
  const status = LOT_STATUS[lot.status] || LOT_STATUS.planned;
  const prio = lot.priority ? `<span class="plan-prio">${escapeHtml(lot.priority)}</span>` : "";
  const remove = removable
    ? `<button type="button" class="plan-chip__x" data-remove-lot="${lot.id}" data-wafer="${escapeHtml(waferKey)}" aria-label="Retirer la plaque du lot ${escapeHtml(lot.code)}">&times;</button>`
    : "";
  return `<span class="plan-chip plan-chip--${status.cls}" title="${escapeHtml(`${lot.code} - ${status.label}${lot.title ? ` - ${lot.title}` : ""}`)}">${prio}<a href="${escapeHtml(lot.url)}">${escapeHtml(lot.code)}</a>${remove}</span>`;
}

// --- filtres -----------------------------------------------------------------------------------

function studyVisible(study, mp) {
  if (filter === "running" && ENDED.has(study.status)) return false;
  if (filter === "ended" && !ENDED.has(study.status)) return false;
  if (!query) return true;
  const lots = study.wafers.flatMap((w) => (w.key ? lotsByWafer.get(w.key) || [] : []));
  const haystack = [study.title, mp.code, mp.name, ...study.wafers.map((w) => w.lasermark), ...lots.map((l) => l.code)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

// --- rendu -------------------------------------------------------------------------------------

function pct(d, range) {
  return ((d - range.start) / (range.end - range.start)) * 100;
}

function barHtml(start, end, range, cls, title, label = "") {
  if (!start || end < range.start || start > range.end) return "";
  const left = Math.max(0, pct(start, range));
  const right = Math.min(100, pct(new Date(end.getTime() + DAY), range));
  const width = Math.max(0.6, right - left);
  return `<span class="plan-bar ${cls}" style="left:${left}%;width:${width}%;" title="${escapeHtml(title)}">${label ? `<span>${escapeHtml(label)}</span>` : ""}</span>`;
}

function timeCell(inner, range) {
  const t = pct(today(), range);
  const now = t >= 0 && t <= 100 ? `<span class="plan-now" style="left:${t}%;"></span>` : "";
  return `<div class="plan-time">${now}${inner}</div>`;
}

function headerHtml(range) {
  const weeks = [];
  for (let d = new Date(range.start); d < range.end; d = new Date(d.getTime() + WEEK)) {
    const current = d <= today() && today() < new Date(d.getTime() + WEEK);
    const month = d.getDate() <= 7 ? d.toLocaleDateString("fr-FR", { month: "short" }) : "";
    weeks.push(
      `<span class="plan-week${current ? " is-now" : ""}" title="Semaine du ${shortDate(d)}"><b>S${isoWeek(d)}</b>${month ? `<i>${month}</i>` : ""}</span>`
    );
  }
  return `<div class="plan-row plan-row--head">
      <div class="plan-cols"><span class="plan-c-check"></span><span>Plaque</span><span>Variante</span><span>Lot en cours</span><span>Lot prévu</span></div>
      <div class="plan-weeks" style="--weeks:${WEEKS_SHOWN};">${weeks.join("")}</div>
    </div>`;
}

function waferRow(wafer, study, thematicId, range) {
  const lots = wafer.key ? lotsByWafer.get(wafer.key) || [] : [];
  const planned = lots.filter((l) => l.status === "planned");
  const current = lots.filter((l) => l.status === "wip" || l.status === "hold");
  const past = lots.filter((l) => l.status === "done");
  const shown = current.length ? current : past.slice(-1);
  const checked = wafer.key && selection.has(wafer.key);
  const check = wafer.key
    ? `<input type="checkbox" data-select="${escapeHtml(wafer.key)}" data-lasermark="${escapeHtml(wafer.lasermark)}" data-thematic="${thematicId ?? ""}" ${checked ? "checked" : ""} aria-label="Sélectionner ${escapeHtml(wafer.lasermark)}">`
    : `<input type="checkbox" disabled title="Place encore à associer à une plaque" aria-label="Place à associer">`;
  const name = wafer.key
    ? `<a class="plan-lm" href="/plaques/${encodeURIComponent(wafer.lasermark)}">${escapeHtml(wafer.lasermark)}</a>`
    : `<span class="plan-lm plan-lm--empty">à associer</span>`;
  // des lots qui se chevauchent dans le temps (un lot en cours, le lot prévu après lui) : une voie chacun
  const spans = lots
    .filter((l) => l.status !== "cancelled")
    .map((lot) => ({ lot, span: lotSpan(lot) }))
    .filter((x) => x.span)
    .sort((a, b) => a.span.start - b.span.start);
  const laneEnds = [];
  for (const x of spans) {
    x.lane = laneEnds.findIndex((end) => end < x.span.start);
    if (x.lane < 0) x.lane = laneEnds.length;
    laneEnds[x.lane] = x.span.end;
  }
  const lanes = laneEnds.length;
  const bars = spans
    .map(({ lot, span, lane }) => {
      const status = LOT_STATUS[lot.status] || LOT_STATUS.planned;
      const title = `${lot.code} (${status.label}) : ${shortDate(span.start)} → ${shortDate(span.end)}${span.forecast ? " (prévision)" : ""}`;
      const html = barHtml(span.start, span.end, range, `plan-bar--${status.cls}`, title, `${lot.priority ? `${lot.priority} ` : ""}${lot.code}`);
      return lanes > 1 ? html.replace('style="', `style="top:${((lane + 0.5) / lanes) * 100}%;height:${Math.floor(26 / lanes)}px;`) : html;
    })
    .join("");
  return `<div class="plan-row plan-row--wafer${checked ? " is-selected" : ""}">
      <div class="plan-cols">
        <span class="plan-c-check">${check}</span>
        <span>${name}</span>
        <span class="plan-variant">${escapeHtml(wafer.variant || "")}</span>
        <span>${shown.map((l) => lotChip(l)).join("") || '<span class="plan-none">-</span>'}</span>
        <span>${planned.map((l) => lotChip(l, { removable: true, waferKey: wafer.key })).join("") || '<span class="plan-none">-</span>'}</span>
      </div>
      ${timeCell(bars, range)}
    </div>`;
}

function studyRow(study, mp, range) {
  const start = day(study.started_at);
  const end = day(study.ended_at) || today();
  const cls = ENDED.has(study.status) ? "plan-bar--study-ended" : "plan-bar--study";
  const title = `${study.title} : ${shortDate(start)} → ${study.ended_at ? shortDate(end) : "en cours"}`;
  const mapped = study.wafers.filter((w) => w.key).length;
  return `<div class="plan-row plan-row--study">
      <div class="plan-cols plan-cols--wide">
        <button type="button" class="plan-study" data-study="${escapeHtml(study.id)}" data-mp="${escapeHtml(mp.slug)}">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 8v4l2.5 2.5"/></svg>
          <span class="plan-study__title">${escapeHtml(study.title)}</span>
        </button>
        ${statusBadgeHtml(study.status, study.decision)}
        <span class="plan-count">${mapped}/${study.wafers.length} pl.</span>
      </div>
      ${timeCell(barHtml(start, end, range, cls, title), range)}
    </div>`;
}

function planRow(plan, mp, range) {
  const t = today();
  return `<div class="plan-row plan-row--ghost">
      <div class="plan-cols plan-cols--wide">
        <a class="plan-ghost" href="${escapeHtml(plan.url)}" title="${escapeHtml(plan.intent || "")}">Prévision : ${escapeHtml(plan.title)}</a>
        <span class="plan-count">${plan.wafer_count} plaque${plan.wafer_count > 1 ? "s" : ""} prévue${plan.wafer_count > 1 ? "s" : ""}</span>
      </div>
      ${timeCell(barHtml(t, new Date(t.getTime() + 2 * WEEK), range, "plan-bar--ghost", `Expérience prévue : ${plan.title}`), range)}
    </div>`;
}

function toggleRow(key, cls, label, meta, link) {
  const open = !collapsed.has(key);
  return `<div class="plan-row ${cls}">
      <div class="plan-cols plan-cols--wide">
        <button type="button" class="plan-toggle" data-toggle="${escapeHtml(key)}" aria-expanded="${open}">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>
          <span>${label}</span>
        </button>
        ${link || ""}<span class="plan-meta">${meta}</span>
      </div>
      <div class="plan-time plan-time--blank"></div>
    </div>`;
}

function render() {
  const range = windowRange();
  const rows = [headerHtml(range)];
  let shown = 0;
  for (const group of board.groups) {
    if (areaFilter && group.area.slug !== areaFilter) continue;
    const thematicId = group.thematic ? group.thematic.id : null;
    const mps = group.microprojects
      .map((mp) => ({ mp, studies: mp.studies.filter((s) => studyVisible(s, mp)), plans: query || filter === "ended" ? [] : mp.plans }))
      .filter((x) => x.studies.length || x.plans.length);
    if (!mps.length) continue;
    const gKey = `t:${group.area.slug}:${thematicId ?? "-"}`;
    const wafers = mps.reduce((n, x) => n + x.studies.reduce((m, s) => m + s.wafers.length, 0), 0);
    const tLabel = group.thematic ? escapeHtml(group.thematic.name) : "Sans thématique";
    const areaLabel = board.areas.length > 1 ? ` <span class="plan-area-tag">${escapeHtml(group.area.name)}</span>` : "";
    rows.push(toggleRow(gKey, "plan-row--thematic", tLabel + areaLabel, `${mps.length} µprojet${mps.length > 1 ? "s" : ""} · ${wafers} plaque${wafers > 1 ? "s" : ""}`));
    if (collapsed.has(gKey)) continue;
    for (const { mp, studies, plans } of mps) {
      const mKey = `m:${mp.slug}`;
      const label = `${mp.code ? `<span class="plan-code">${escapeHtml(mp.code)}</span> ` : ""}${escapeHtml(mp.name)}`;
      const link = `<a class="plan-open" href="${escapeHtml(mp.url)}" aria-label="Ouvrir le µprojet ${escapeHtml(mp.name)}">ouvrir</a>`;
      rows.push(toggleRow(mKey, "plan-row--mp", label, `${studies.length} épi${studies.length > 1 ? "s" : ""}`, link));
      if (collapsed.has(mKey)) continue;
      for (const study of studies) {
        shown += 1;
        rows.push(studyRow(study, mp, range));
        for (const wafer of study.wafers) rows.push(waferRow(wafer, study, thematicId, range));
      }
      for (const plan of plans) rows.push(planRow(plan, mp, range));
    }
  }
  if (rows.length === 1) {
    grid.innerHTML = `<div class="empty-state"><div style="font-weight:600;color:var(--text-soft);">Rien à montrer</div>
      <div style="font-size:13px;">${board.groups.length ? "Aucune épi ne correspond à ces filtres." : "Les µprojets des projets de l'équipe n'ont pas encore d'étude."}</div></div>`;
    return;
  }
  grid.innerHTML = rows.join("");
  grid.dataset.studies = shown;
}

function renderKpis() {
  const studies = board.groups.flatMap((g) => g.microprojects.flatMap((mp) => mp.studies));
  const wafers = studies.flatMap((s) => s.wafers.filter((w) => w.key));
  const running = studies.filter((s) => !ENDED.has(s.status)).length;
  const active = board.lots.filter((l) => l.status === "wip" || l.status === "hold").length;
  const planned = board.lots.filter((l) => l.status === "planned").length;
  const inPlan = new Set(board.lots.filter((l) => l.status === "planned").flatMap((l) => l.wafers));
  const runningWafers = studies.filter((s) => !ENDED.has(s.status)).flatMap((s) => s.wafers.filter((w) => w.key));
  const unplanned = runningWafers.filter((w) => !inPlan.has(w.key) && !(lotsByWafer.get(w.key) || []).some((l) => l.status === "wip" || l.status === "hold")).length;
  const kpi = (value, label) => `<div class="kpi"><div class="kpi__value">${value}</div><div class="kpi__label">${label}</div></div>`;
  const box = document.getElementById("plan-kpis");
  box.innerHTML = [
    kpi(wafers.length, "plaques suivies"),
    kpi(running, "épis en cours"),
    kpi(active, "lots en cours"),
    kpi(planned, "lots prévus"),
    kpi(unplanned, "plaques d'épis en cours sans lot"),
  ].join("");
  box.removeAttribute("aria-busy");
}

function renderLegend() {
  document.getElementById("plan-legend").innerHTML = `
    <span><i class="plan-key plan-bar--study"></i>épi en cours</span>
    <span><i class="plan-key plan-bar--study-ended"></i>épi terminée</span>
    <span><i class="plan-key plan-bar--wip"></i>lot en cours</span>
    <span><i class="plan-key plan-bar--hold"></i>lot en pause</span>
    <span><i class="plan-key plan-bar--done"></i>lot sorti</span>
    <span><i class="plan-key plan-bar--planned"></i>lot prévu</span>
    <span><i class="plan-key plan-bar--ghost"></i>expérience prévue</span>
    <span><i class="plan-key plan-key--now"></i>aujourd'hui</span>`;
}

function renderSelection() {
  const bar = document.getElementById("plan-selbar");
  bar.hidden = selection.size === 0;
  document.getElementById("plan-selcount").textContent = `${selection.size} plaque${selection.size > 1 ? "s" : ""} sélectionnée${selection.size > 1 ? "s" : ""}`;
}

// --- panneau d'une épi -------------------------------------------------------------------------

function findStudy(slug, id) {
  for (const group of board.groups) {
    for (const mp of group.microprojects) {
      if (mp.slug !== slug) continue;
      const study = mp.studies.find((s) => s.id === id);
      if (study) return { mp, study, group };
    }
  }
  return null;
}

const drawer = document.getElementById("plan-drawer");
let drawerToken = 0;

function closeDrawer() {
  drawer.hidden = true;
  drawerToken += 1;
}

async function openDrawer(slug, id) {
  const found = findStudy(slug, id);
  if (!found) return;
  const { mp, study, group } = found;
  const token = ++drawerToken;
  drawer.hidden = false;
  document.getElementById("plan-drawer-eyebrow").textContent = `${group.thematic ? group.thematic.name : "Sans thématique"} ▸ ${mp.code || mp.name}`;
  document.getElementById("plan-drawer-title").textContent = study.title;
  const body = document.getElementById("plan-drawer-body");
  const dates = `${shortDate(day(study.started_at))} → ${study.ended_at ? shortDate(day(study.ended_at)) : "en cours"}`;
  const waferList = study.wafers
    .map((w) => {
      const lots = w.key ? lotsByWafer.get(w.key) || [] : [];
      return `<li><span class="plan-lm${w.key ? "" : " plan-lm--empty"}">${escapeHtml(w.lasermark || "à associer")}</span>${w.variant ? ` <span class="plan-variant">${escapeHtml(w.variant)}</span>` : ""} ${lots.map((l) => lotChip(l)).join("")}</li>`;
    })
    .join("");
  body.innerHTML = `
    <div class="plan-drawer__status">${statusBadgeHtml(study.status, study.decision)}<span class="plan-meta">${dates}</span></div>
    <div id="plan-drawer-detail"><div class="skeleton" style="height:120px;"></div></div>
    <h3 class="section-title">Plaques (${study.wafers.length})</h3>
    <ul class="plan-drawer__wafers">${waferList || "<li>Aucune plaque</li>"}</ul>
    <h3 class="section-title">Derniers ajouts au cahier</h3>
    <div id="plan-drawer-notebook"><div class="skeleton" style="height:60px;"></div></div>
    <a class="btn btn-primary btn-block" href="${escapeHtml(study.url)}">Ouvrir la fiche de l'épi</a>`;
  document.getElementById("plan-drawer-close").focus();

  try {
    const detail = await experimentsApi.get(slug, id);
    if (token !== drawerToken) return;
    const image = (detail.structure_images || [])[0];
    const structure = detail.structure_svg
      ? `<div class="plan-drawer__svg">${detail.structure_svg}</div>`
      : image
        ? `<img class="plan-drawer__img" src="${escapeHtml(image.url)}" alt="${escapeHtml(image.caption || "Structure")}">`
        : "";
    const conclusion = detail.conclusion && detail.conclusion.summary ? `<h3 class="section-title">Conclusion</h3><p>${escapeHtml(detail.conclusion.summary)}</p>` : "";
    const hold = detail.hold && detail.hold.reason ? `<p class="plan-hold">En pause : ${escapeHtml(detail.hold.reason)}</p>` : "";
    document.getElementById("plan-drawer-detail").innerHTML = `
      ${hold}
      ${detail.intent ? `<h3 class="section-title">Intention</h3><p>${escapeHtml(detail.intent)}</p>` : ""}
      ${detail.hypothesis ? `<h3 class="section-title">Hypothèse</h3><p>${escapeHtml(detail.hypothesis)}</p>` : ""}
      ${structure ? `<h3 class="section-title">Structure</h3>${structure}` : ""}
      ${conclusion}`;
  } catch (err) {
    if (token === drawerToken) document.getElementById("plan-drawer-detail").innerHTML = `<p class="plan-none">${escapeHtml(err.message)}</p>`;
  }

  const notebookBox = document.getElementById("plan-drawer-notebook");
  if (!pluginEnabled("notebook")) {
    notebookBox.innerHTML = `<p class="plan-none">Cahier désactivé.</p>`;
    return;
  }
  try {
    const entries = await notebookApi.entries(slug, id);
    if (token !== drawerToken) return;
    const latest = [...entries].sort((a, b) => String(b.updated_at || b.created_at).localeCompare(String(a.updated_at || a.created_at))).slice(0, 5);
    notebookBox.innerHTML = latest.length
      ? `<ul class="plan-drawer__notes">${latest
          .map(
            (e) =>
              `<li><span class="plan-note__title">${escapeHtml(e.title || "(sans titre)")}</span><span class="plan-meta">${escapeHtml(timeAgo(e.updated_at || e.created_at))}${e.wafers && e.wafers.length ? ` · ${escapeHtml(e.wafers.join(", "))}` : ""}</span></li>`
          )
          .join("")}</ul>`
      : `<p class="plan-none">Rien dans le cahier pour l'instant.</p>`;
  } catch (err) {
    if (token === drawerToken) notebookBox.innerHTML = `<p class="plan-none">${escapeHtml(err.message)}</p>`;
  }
}

// --- lot prévu ---------------------------------------------------------------------------------

const dialog = document.getElementById("plan-dialog");
let mode = "new";

function setMode(next) {
  mode = next;
  document.querySelectorAll("#plan-mode [data-mode]").forEach((btn) => {
    const active = btn.dataset.mode === mode;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", String(active));
  });
  document.getElementById("plan-new").hidden = mode !== "new";
  document.getElementById("plan-existing").hidden = mode !== "existing";
}

async function openPlanDialog() {
  const marks = [...selection.values()].map((s) => s.lasermark);
  document.getElementById("plan-dialog-wafers").textContent = `${marks.length} plaque${marks.length > 1 ? "s" : ""} : ${marks.join(", ")}`;
  document.getElementById("plan-form").reset();
  const select = document.getElementById("plan-lot");
  select.innerHTML = `<option value="">Chargement…</option>`;
  setMode("new");
  // un début d'aujourd'hui ou d'avant ferait démarrer le lot : le début prévu est à venir
  const tomorrow = new Date(today().getTime() + DAY);
  const iso = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, "0")}-${String(tomorrow.getDate()).padStart(2, "0")}`;
  document.getElementById("plan-start").min = iso;
  document.getElementById("plan-end").min = iso;
  dialog.showModal();
  try {
    const [planned, priorities] = await Promise.all([lotsApi.list({ status: "planned" }), lotsApi.priorities()]);
    document.getElementById("plan-priorities").innerHTML = priorities.map((p) => `<option value="${escapeHtml(p)}"></option>`).join("");
    const editable = planned.filter((l) => l.source !== "prism");
    select.innerHTML = editable.length
      ? editable
          .map((l) => `<option value="${l.id}">${escapeHtml(`${l.priority ? `${l.priority} · ` : ""}${l.code}${l.title ? ` - ${l.title}` : ""}`)}</option>`)
          .join("")
      : `<option value="">Aucun lot prévu</option>`;
    document.querySelector('#plan-mode [data-mode="existing"]').disabled = !editable.length;
  } catch (err) {
    showError(err);
  }
}

async function submitPlan(event) {
  event.preventDefault();
  const lasermarks = [...selection.values()].map((s) => s.lasermark);
  const submit = document.getElementById("plan-submit");
  submit.disabled = true;
  try {
    if (mode === "new") {
      const thematicIds = [...new Set([...selection.values()].map((s) => s.thematicId).filter((id) => id != null))];
      const value = (id) => document.getElementById(id).value.trim();
      await lotsApi.create({
        code: value("plan-code") || null,
        title: value("plan-lot-title"),
        priority: value("plan-priority"),
        started_on: value("plan-start") || null, // dans le futur : le lot reste « prévu »
        forecast_exit_on: value("plan-end") || null,
        wafers: lasermarks,
        thematic_ids: thematicIds,
      });
    } else {
      const lotId = document.getElementById("plan-lot").value;
      if (!lotId) return;
      await lotsApi.addWafers(lotId, { lasermarks });
    }
    dialog.close();
    selection.clear();
    await load();
  } catch (err) {
    dialog.close();
    showError(err);
  } finally {
    submit.disabled = false;
  }
}

async function removeFromLot(lotId, waferKey) {
  const lot = lotsById.get(Number(lotId));
  if (!lot || !confirm(`Retirer la plaque du lot prévu ${lot.code} ?`)) return;
  try {
    await lotsApi.removeWafer(lot.id, waferKey);
    await load();
  } catch (err) {
    showError(err);
  }
}

// --- chargement et événements ------------------------------------------------------------------

function teamSlugFromUrl() {
  const params = routeParams(["/planning/{team_slug}"]);
  return params ? params.team_slug : null;
}

async function load() {
  board = await planningApi.board(teamSlugFromUrl());
  indexLots();
  const teamWrap = document.getElementById("plan-team-wrap");
  if (!board.team) {
    document.getElementById("plan-kpis").hidden = true;
    document.querySelector(".plan-toolbar").hidden = true;
    grid.innerHTML = `<div class="empty-state"><div style="font-weight:600;color:var(--text-soft);">Aucune équipe à planifier</div>
      <div style="font-size:13px;">Le planning d'une équipe est réservé à ses managers. Voyez la page <a href="/equipes">Équipes</a>.</div></div>`;
    return;
  }
  document.getElementById("plan-title").textContent = `Planning - ${board.team.name}`;
  document.title = `Planning ${board.team.name} — Spectre`;
  teamWrap.hidden = board.teams.length < 2;
  document.getElementById("plan-team").innerHTML = board.teams
    .map((t) => `<option value="${escapeHtml(t.slug)}" ${t.slug === board.team.slug ? "selected" : ""}>${escapeHtml(t.name)}</option>`)
    .join("");
  const areaSelect = document.getElementById("plan-area");
  areaSelect.hidden = board.areas.length < 2;
  areaSelect.innerHTML = `<option value="">Tous les projets</option>${board.areas
    .map((a) => `<option value="${escapeHtml(a.slug)}" ${a.slug === areaFilter ? "selected" : ""}>${escapeHtml(a.name)}</option>`)
    .join("")}`;
  renderKpis();
  render();
  renderSelection();
}

grid.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-toggle]");
  if (toggle) {
    const key = toggle.dataset.toggle;
    if (collapsed.has(key)) collapsed.delete(key);
    else collapsed.add(key);
    render();
    return;
  }
  const study = event.target.closest("[data-study]");
  if (study) {
    openDrawer(study.dataset.mp, study.dataset.study);
    return;
  }
  const remove = event.target.closest("[data-remove-lot]");
  if (remove) removeFromLot(remove.dataset.removeLot, remove.dataset.wafer);
});

grid.addEventListener("change", (event) => {
  const box = event.target.closest("[data-select]");
  if (!box) return;
  const key = box.dataset.select;
  if (box.checked) selection.set(key, { lasermark: box.dataset.lasermark, thematicId: box.dataset.thematic ? Number(box.dataset.thematic) : null });
  else selection.delete(key);
  box.closest(".plan-row").classList.toggle("is-selected", box.checked);
  renderSelection();
});

document.getElementById("plan-filter").addEventListener("click", (event) => {
  const btn = event.target.closest("[data-filter]");
  if (!btn) return;
  filter = btn.dataset.filter;
  document.querySelectorAll("#plan-filter [data-filter]").forEach((b) => {
    b.classList.toggle("active", b === btn);
    b.setAttribute("aria-pressed", String(b === btn));
  });
  render();
});

let searchTimer = null;
document.getElementById("plan-search").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    query = event.target.value.trim().toLowerCase();
    render();
  }, 150);
});
document.getElementById("plan-area").addEventListener("change", (event) => {
  areaFilter = event.target.value;
  render();
});
document.getElementById("plan-team").addEventListener("change", (event) => {
  window.location.href = `/planning/${encodeURIComponent(event.target.value)}`;
});
document.getElementById("plan-prev").addEventListener("click", () => {
  offsetWeeks -= 6;
  render();
});
document.getElementById("plan-next").addEventListener("click", () => {
  offsetWeeks += 6;
  render();
});
document.getElementById("plan-today").addEventListener("click", () => {
  offsetWeeks = 0;
  render();
});

document.getElementById("plan-selclear").addEventListener("click", () => {
  selection.clear();
  render();
  renderSelection();
});
document.getElementById("plan-selplan").addEventListener("click", openPlanDialog);
document.getElementById("plan-mode").addEventListener("click", (event) => {
  const btn = event.target.closest("[data-mode]");
  if (btn && !btn.disabled) setMode(btn.dataset.mode);
});
document.getElementById("plan-form").addEventListener("submit", submitPlan);
document.getElementById("plan-cancel").addEventListener("click", () => dialog.close());
document.getElementById("plan-drawer-close").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !drawer.hidden && !dialog.open) closeDrawer();
});

renderLegend();
load().catch(showError);
