/* Suivi de lots - ce que la liste (/lots, lots.js) et la fiche d'un lot (/lots/{code}, lot.js)
   partagent : statuts, priorité (P10, P20... - la plus petite passe d'abord) et le Gantt. Une
   ligne par lot, de son début à sa fin : la partie écoulée pleine (bleu, ambre si le lot est en
   pause), le reste jusqu'à la fin prévisionnelle en pointillé (une prévision) ; une fois sorti, la
   barre pleine jusqu'à la fin déclarée, l'éventuel dépassement de la prévision en rouge. Dépliée,
   une sous-ligne par expérience liée (au code du graphe de filiation, lineage-graph.js). Saisie
   déclarative pour l'instant : voir spectre.plugins.lots. Dépend de experiments/static/status.js, lineage-graph.js,
   timeline.js et d3. */

const LOT_STATUS = {
  planned: { label: "En préparation", cls: "badge-draft" },
  wip: { label: "En cours", cls: "badge-running" },
  hold: { label: "En pause", cls: "badge-hold" },
  done: { label: "Sorti", cls: "badge-concluded" },
  cancelled: { label: "Annulé", cls: "badge-abandoned" },
};

const LOT_DAY = 86400000;

function lotStatusBadgeHtml(status) {
  const info = LOT_STATUS[status] || LOT_STATUS.planned;
  return `<span class="badge ${info.cls}"><span class="dot"></span>${info.label}</span>`;
}

function lotPriorityHtml(priority) {
  return priority ? `<span class="lot-prio" title="Priorité du lot">${escapeHtml(priority)}</span>` : "";
}

function lotUrl(code) {
  return `/lots/${encodeURIComponent(code)}`;
}

// « 2026-10-02 » -> une date locale (pas minuit UTC, qui recule d'un jour à l'ouest de Greenwich).
function lotDay(iso) {
  if (!iso) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

function lotDateLabel(iso) {
  const day = lotDay(iso);
  return day ? day.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "";
}

function lotTodayStart() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

// aujourd'hui en AAAA-MM-JJ, à l'heure locale (toISOString donnerait la date UTC)
function lotTodayIso() {
  const d = lotTodayStart();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// « +3 j de retard » / « 2 j d'avance » / « à l'heure » - l'écart d'une fin déclarée sur la prévision.
function lotDeltaLabel(days) {
  if (days == null) return "";
  if (days > 0) return `+${days} j de retard`;
  if (days < 0) return `${-days} j d'avance`;
  return "à l'heure";
}

// Où en est le lot, en une ligne : « depuis 43 j · fin prévue le 24 oct. 2026 », « sorti le … ».
function lotTimingLabel(lot) {
  const forecast = lot.forecast_exit_on ? `fin prévue le ${lotDateLabel(lot.forecast_exit_on)}` : "fin prévue à définir";
  if (lot.status === "done") {
    return `Sorti le ${lotDateLabel(lot.exited_on)}${lot.exit_delta_days != null ? ` · ${lotDeltaLabel(lot.exit_delta_days)}` : ""}`;
  }
  if (lot.status === "cancelled") return "Annulé";
  const start = lotDay(lot.started_on);
  if (!start) return `Début à définir · ${forecast}`;
  if (start > lotTodayStart()) return `Début le ${lotDateLabel(lot.started_on)} · ${forecast}`;
  return `Depuis ${lot.elapsed_days} j · ${forecast}${lot.late_days ? ` · +${lot.late_days} j de retard` : ""}`;
}

// --- Gantt ------------------------------------------------------------------------------------

const GANTT_ROW_H = 40;
const GANTT_SUB_H = 26;
const GANTT_AXIS_H = 34;
const GANTT_BAR_H = 14;

// l'axe suit les lots seulement : une expérience commencée bien avant le lot est rognée à gauche
// (flèche « ◂ »), sinon un vieil essai écraserait tous les lots sur quelques pixels
function ganttGeometry(lots, width, labelW) {
  const today = lotTodayStart();
  let min = +today - 14 * LOT_DAY;
  let max = +today + 30 * LOT_DAY;
  for (const lot of lots) {
    for (const iso of [lot.started_on, lot.forecast_exit_on, lot.exited_on]) {
      const day = lotDay(iso);
      if (day) {
        min = Math.min(min, +day);
        max = Math.max(max, +day);
      }
    }
  }
  const pad = (max - min) * 0.04;
  const plotW = Math.max(560, width - labelW);
  const x = d3.scaleTime().domain([new Date(min - pad), new Date(max + pad)]).range([0, plotW]);
  const candidates = x.ticks(Math.max(3, Math.floor(plotW / 90)));
  const todayX = x(today);
  const ticks = timelineTicks(x, candidates, { avoid: [[todayX - 28, todayX + 100]] }); // « Aujourd'hui » s'écrit à droite du trait
  return { x, plotW, labelW, today, todayX, ticks };
}

// Infobulle : chaque élément porte `data-tip` (lignes séparées par \n) - voir mountGanttTooltip.
function tipAttr(lines) {
  return ` data-tip="${escapeHtml(lines.filter(Boolean).join("\n"))}"`;
}

function ganttAxisSvg(geo) {
  return `<svg class="gantt__track" width="${geo.plotW}" height="${GANTT_AXIS_H}" viewBox="0 0 ${geo.plotW} ${GANTT_AXIS_H}" aria-hidden="true">
      ${geo.ticks.map((t) => `<line class="gantt__grid" x1="${t.px}" x2="${t.px}" y1="${GANTT_AXIS_H - 8}" y2="${GANTT_AXIS_H}"></line><text class="gantt__tick" x="${t.px}" y="${GANTT_AXIS_H - 12}" text-anchor="middle">${escapeHtml(t.label)}</text>`).join("")}
      <line class="gantt__today" x1="${geo.todayX}" x2="${geo.todayX}" y1="${GANTT_AXIS_H - 20}" y2="${GANTT_AXIS_H}"></line>
      <text class="gantt__today-label" x="${geo.todayX + 4}" y="${GANTT_AXIS_H - 12}">Aujourd'hui</text>
    </svg>`;
}

function ganttBackground(geo, height) {
  return `${geo.ticks.map((t) => `<line class="gantt__grid" x1="${t.px}" x2="${t.px}" y1="0" y2="${height}"></line>`).join("")}
    <rect x="${geo.todayX}" y="0" width="${Math.max(0, geo.plotW - geo.todayX)}" height="${height}" fill="url(#gantt-hatch)" opacity="0.6"></rect>
    <line class="gantt__today" x1="${geo.todayX}" x2="${geo.todayX}" y1="0" y2="${height}"></line>`;
}

function ganttBar(cls, x0, x1, y, tip, href) {
  return `<rect class="gantt__bar ${cls}" x="${x0}" y="${y}" width="${Math.max(4, x1 - x0)}" height="${GANTT_BAR_H}" rx="3"${tipAttr(tip)}${href ? ` data-href="${escapeHtml(href)}"` : ""}></rect>`;
}

function ganttLotTrack(lot, geo, { href } = {}) {
  const x = geo.x;
  const y = (GANTT_ROW_H - GANTT_BAR_H) / 2;
  const mid = y + GANTT_BAR_H / 2;
  const today = geo.today;
  const start = lotDay(lot.started_on);
  const forecast = lotDay(lot.forecast_exit_on);
  const exited = lotDay(lot.exited_on);
  const head = `${lot.code}${lot.priority ? ` · ${lot.priority}` : ""}`;
  let bars = "";
  let marks = "";

  if (lot.status === "done" || lot.status === "cancelled") {
    const end = exited || forecast || today;
    const from = start || end;
    const done = lot.status === "done";
    bars += ganttBar(done ? "is-done" : "is-cancelled", x(from), x(end), y, [head, `${done ? "Sorti" : "Annulé"} : ${lotDateLabel(lot.started_on) || "?"} → ${lotDateLabel(lot.exited_on) || "?"}`], href);
    if (done && forecast && exited && exited > forecast) {
      bars += ganttBar("is-overrun", x(forecast), x(exited), y, [head, `Fin déclarée : ${lotDeltaLabel(lot.exit_delta_days)} sur la prévision`], href);
    }
    if (done && exited) {
      const ex = x(exited);
      marks += `<g class="gantt__exit"${tipAttr([head, `Fin déclarée le ${lotDateLabel(lot.exited_on)}${lot.exit_delta_days != null ? ` (${lotDeltaLabel(lot.exit_delta_days)})` : ""}`])}><circle cx="${ex}" cy="${mid}" r="7"></circle><path d="M${ex - 3.2},${mid} l2.2,2.4 l4.2,-4.6" fill="none"></path></g>`;
    }
  } else {
    // pas encore sorti : l'écoulé (plein) puis le restant jusqu'à la fin prévisionnelle (pointillé)
    const hold = lot.status === "hold";
    const started = start && start <= today;
    if (started) {
      bars += ganttBar(hold ? "is-elapsed is-hold" : "is-elapsed", x(start), x(today), y, [head, `${hold ? "En pause" : "En cours"} depuis le ${lotDateLabel(lot.started_on)} (${lot.elapsed_days} j)`, lot.hold_reason], href);
    }
    const from = started ? today : start || today;
    if (forecast && forecast > from) {
      bars += ganttBar("is-remaining", x(from), x(forecast), y, [head, start ? `Prévu jusqu'au ${lotDateLabel(lot.forecast_exit_on)}` : `Début à définir · fin prévue le ${lotDateLabel(lot.forecast_exit_on)}`], href);
    }
    if (lot.late_days && forecast) {
      marks += `<g class="gantt__late"${tipAttr([head, `En retard de ${lot.late_days} j sur la fin prévisionnelle`])}>
          <line x1="${x(forecast)}" x2="${geo.todayX}" y1="${y + GANTT_BAR_H + 4}" y2="${y + GANTT_BAR_H + 4}"></line>
          <text x="${geo.todayX + 4}" y="${y + GANTT_BAR_H + 8}">+${lot.late_days} j</text></g>`;
    }
  }
  if (forecast && lot.status !== "cancelled") {
    const fx = x(forecast);
    marks += `<g class="gantt__flag"${tipAttr([head, `Fin prévisionnelle : ${lotDateLabel(lot.forecast_exit_on)}`])}>
        <line x1="${fx}" x2="${fx}" y1="${y - 7}" y2="${y + GANTT_BAR_H + 3}"></line><path d="M${fx},${y - 7} l9,3.5 l-9,3.5 Z"></path></g>`;
  }
  return `<svg class="gantt__track" width="${geo.plotW}" height="${GANTT_ROW_H}" viewBox="0 0 ${geo.plotW} ${GANTT_ROW_H}">
      ${ganttBackground(geo, GANTT_ROW_H)}${bars}${marks}
    </svg>`;
}

function ganttExperienceTrack(exp, geo) {
  const span = lineageSpan(exp);
  const y = GANTT_SUB_H / 2;
  const rawX0 = geo.x(new Date(span.start));
  const clipped = rawX0 < 0;
  const x0 = Math.max(0, rawX0);
  const x1 = Math.max(geo.x(span.end ? new Date(span.end) : geo.today), x0 + 4);
  const before = clipped ? `<path class="gantt__clipped" d="M7,${y - 4} L2,${y} L7,${y + 4}"></path>` : "";
  const style = lineageOutcomeStyle(exp);
  const bar = style.filled
    ? `<rect x="${x0}" y="${y - 3.5}" width="${x1 - x0}" height="7" rx="3.5" fill="${style.color}"></rect>`
    : `<rect x="${x0}" y="${y - 3.5}" width="${x1 - x0}" height="7" rx="3.5" fill="${style.color}" fill-opacity="0.16" style="stroke:${style.color};stroke-width:1.2px"></rect>`;
  const title = exp.title || "Expérience (µprojet dont vous n'êtes pas membre)";
  return `<svg class="gantt__track" width="${geo.plotW}" height="${GANTT_SUB_H}" viewBox="0 0 ${geo.plotW} ${GANTT_SUB_H}">
      ${ganttBackground(geo, GANTT_SUB_H)}
      ${before}<g class="gantt__exp"${tipAttr([`${exp.microproject.code || exp.microproject.name} · ${title}`, `${style.label} · ${lineageElapsedLabel(exp)}`, lineageDatesLabel(exp), exp.wafers.length ? `Wafers : ${exp.wafers.join(", ")}` : ""])}>
        ${bar}<g transform="translate(${x1},${y})">${lineageNodeShapeHtml(exp, { radius: 6, tipRing: false })}</g>
      </g>
    </svg>`;
}

function ganttLotLabel(lot, { expanded, expandable, link = true }) {
  const toggle = expandable
    ? `<button type="button" class="gantt__toggle" data-toggle="${escapeHtml(lot.code)}" aria-expanded="${expanded}" aria-label="${expanded ? "Replier" : "Déplier"} les expériences du lot ${escapeHtml(lot.code)}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 6 6 6-6 6"/></svg></button>`
    : `<span class="gantt__toggle-spacer"></span>`;
  const code = link ? `<a class="gantt__code" href="${lotUrl(lot.code)}">${escapeHtml(lot.code)}</a>` : `<span class="gantt__code">${escapeHtml(lot.code)}</span>`;
  const thematics = (lot.thematics || []).slice(0, 2).map((t) => `<span class="lot-chip">${escapeHtml(t.name)}</span>`).join("");
  const more = (lot.thematics || []).length > 2 ? `<span class="lot-chip lot-chip--more">+${lot.thematics.length - 2}</span>` : "";
  return `<div class="gantt__label">
      ${toggle}
      <div class="gantt__label-body">
        <div class="gantt__label-top">${lotPriorityHtml(lot.priority)}${code}${lotStatusBadgeHtml(lot.status)}</div>
        <div class="gantt__where" title="${escapeHtml(lotTimingLabel(lot))}">${escapeHtml(lotTimingLabel(lot))} · ${lot.wafers.length} wafer${lot.wafers.length > 1 ? "s" : ""}</div>
        ${thematics || more ? `<div class="gantt__chips">${thematics}${more}</div>` : ""}
      </div>
    </div>`;
}

function ganttExperienceLabel(exp) {
  const mp = exp.microproject;
  const title = exp.id
    ? `<a href="/microprojets/${encodeURIComponent(mp.slug)}/experiences/${encodeURIComponent(exp.id)}" title="${escapeHtml(exp.title)}">${escapeHtml(exp.title)}</a>`
    : `<span class="gantt__muted" title="Vous n'êtes pas membre de ce µprojet">Expérience</span>`;
  return `<div class="gantt__label gantt__label--sub">
      <span class="gantt__toggle-spacer"></span>
      <div class="gantt__sub">${mp.code ? `<span class="mp-code">${escapeHtml(mp.code)}</span>` : `<span class="gantt__muted">${escapeHtml(mp.name)}</span>`}${title}</div>
    </div>`;
}

// Le Gantt complet : `expanded` = codes des lots dépliés (toujours tous si `alwaysExpanded`).
function ganttHtml(lots, width, { expanded = new Set(), alwaysExpanded = false, link = true } = {}) {
  const labelW = width < 640 ? 170 : 300;
  const geo = ganttGeometry(lots, width, labelW);
  const rows = lots
    .map((lot) => {
      const open = alwaysExpanded || expanded.has(lot.code);
      const expandable = !alwaysExpanded && lot.experiments.length > 0;
      const lotRow = `<div class="gantt__row">${ganttLotLabel(lot, { expanded: open, expandable, link })}${ganttLotTrack(lot, geo, { href: link ? lotUrl(lot.code) : "" })}</div>`;
      const subs = open
        ? lot.experiments.map((exp) => `<div class="gantt__row gantt__row--sub">${ganttExperienceLabel(exp)}${ganttExperienceTrack(exp, geo)}</div>`).join("")
        : "";
      return lotRow + subs;
    })
    .join("");
  return `<div class="gantt" style="width:${labelW + geo.plotW}px;--gantt-label-w:${labelW}px;">
      ${timelineHatchDefs("gantt-hatch")}
      <div class="gantt__row gantt__row--axis"><div class="gantt__label"></div>${ganttAxisSvg(geo)}</div>
      ${rows}
    </div>`;
}

function ganttLegendHtml() {
  const swatch = (cls) => `<svg width="22" height="12" viewBox="0 0 22 12" aria-hidden="true"><rect class="gantt__bar ${cls}" x="1" y="1" width="20" height="10" rx="3"></rect></svg>`;
  return `<ul class="status-legend" aria-label="Légende du suivi des lots">
      <li>${swatch("is-elapsed")}Écoulé</li>
      <li>${swatch("is-elapsed is-hold")}En pause</li>
      <li>${swatch("is-remaining")}Restant (prévisionnel)</li>
      <li>${swatch("is-done")}Sorti</li>
      <li>${swatch("is-overrun")}Dépassement</li>
      <li><svg width="14" height="16" viewBox="0 0 14 16" aria-hidden="true"><g class="gantt__flag"><line x1="3" x2="3" y1="1" y2="15"></line><path d="M3,1 l9,3.5 l-9,3.5 Z"></path></g></svg>Fin prévisionnelle</li>
      <li><svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><g class="gantt__exit"><circle cx="8" cy="8" r="7"></circle><path d="M4.8,8 l2.2,2.4 l4.2,-4.6" fill="none"></path></g></svg>Fin déclarée</li>
      <li><svg width="22" height="12" viewBox="0 0 22 12" aria-hidden="true"><g class="gantt__late"><line x1="1" x2="21" y1="6" y2="6"></line></g></svg>Retard</li>
      <li class="status-legend__sep" aria-hidden="true"></li>
      <li style="white-space:normal;">Expériences dépliées : même code que le graphe d'un µprojet</li>
    </ul>`;
}

// Infobulle fixe (jamais rognée par le défilement) sur tout ce qui porte data-tip dans `container`.
function mountGanttTooltip(container) {
  let tip = document.getElementById("gantt-tooltip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "gantt-tooltip";
    tip.className = "gantt-tooltip";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.appendChild(tip);
  }
  const show = (target) => {
    const lines = target.dataset.tip.split("\n");
    tip.innerHTML = `<strong>${escapeHtml(lines[0])}</strong>${lines.slice(1).map((l) => `<div>${escapeHtml(l)}</div>`).join("")}`;
    tip.hidden = false;
    const box = target.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const left = Math.max(8, Math.min(box.left + box.width / 2 - t.width / 2, window.innerWidth - t.width - 8));
    const top = box.top - t.height - 8 < 8 ? box.bottom + 8 : box.top - t.height - 8;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  };
  const hide = () => (tip.hidden = true);
  container.addEventListener("mouseover", (event) => {
    const target = event.target.closest("[data-tip]");
    if (target) show(target);
  });
  container.addEventListener("mouseout", (event) => {
    const target = event.target.closest("[data-tip]");
    if (target && !target.contains(event.relatedTarget)) hide();
  });
  container.addEventListener("scroll", hide, true);
  window.addEventListener("scroll", hide, { passive: true });
  container.addEventListener("click", (event) => {
    const target = event.target.closest("[data-href]");
    if (target) window.location.href = target.dataset.href;
  });
}
