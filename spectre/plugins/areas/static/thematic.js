/* Page d'une thématique (/management/{projet}/thematiques/{thématique}) : on y « voyage » - d'une
   thématique du projet à l'autre (onglets, précédente/suivante), et dans le temps : une frise avec
   une ligne par µprojet, chaque expérience en barre de son lancement à sa conclusion (ou jusqu'à
   aujourd'hui), au même code que le graphe de filiation (lineage-graph.js : creux = en cours,
   plein = terminée, pictogramme = issue). À droite d'« aujourd'hui », la zone à venir et, plus
   bas, le bloc « Perspectives » - un aperçu (placeholder) de la future feuille de route.
   Voir spectre.api.management::get_thematic. */

const { slug: areaSlug, thematique_slug: thematicSlug } = routeParams("/management/{slug}/thematiques/{thematique_slug}");
const areaPath = `/management/${encodeURIComponent(areaSlug)}`;
document.getElementById("atlas-link").href = `${areaPath}/atlas`;

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

let current = null;

function plural(n, one, many) {
  return `${n} ${n > 1 ? many : one}`;
}

function kpi(value, label) {
  return `<div class="kpi"><div class="kpi__value">${value}</div><div class="kpi__label">${label}</div></div>`;
}

function microprojetUrl(p) {
  return `/microprojets/${encodeURIComponent(p.slug)}`;
}

function median(values) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

// --- en-tête, voyage entre thématiques, indicateurs ------------------------------------------

function renderHead(t) {
  document.title = `${t.name} — ${t.area.name} — Spectre`;
  document.getElementById("crumb").textContent = `/ ${t.area.name} / ${t.name}`;
  const areaCrumb = document.getElementById("area-crumb");
  areaCrumb.textContent = t.area.name;
  areaCrumb.href = areaPath;
  document.getElementById("thematic-crumb").textContent = t.name;
  document.getElementById("th-eyebrow").textContent = `Thématique · ${t.area.name}`;
  document.getElementById("th-name").textContent = t.name;
  document.getElementById("th-description").textContent = t.description || "";
  document.getElementById("mp-dialog-where").textContent = `Dans ${t.area.name} › ${t.name}.`;
}

function thematicHref(slug) {
  return `${areaPath}/thematiques/${encodeURIComponent(slug)}`;
}

function renderTravel(t) {
  const index = t.thematiques.findIndex((x) => x.slug === t.slug);
  document.getElementById("th-travel").innerHTML = t.thematiques
    .map((x) => {
      const active = x.slug === t.slug;
      return `<a class="tab${active ? " active" : ""}" href="${thematicHref(x.slug)}"${active ? ` aria-current="page"` : ""}>${escapeHtml(x.name)}<span class="tab__count" aria-label="${plural(x.microprojets, "µprojet", "µprojets")}">${x.microprojets}</span></a>`;
    })
    .join("");
  const step = (id, target, fallback) => {
    const link = document.getElementById(id);
    link.querySelector("span").textContent = target ? target.name : fallback;
    if (target) {
      link.href = thematicHref(target.slug);
      link.removeAttribute("aria-disabled");
      link.title = `${id === "th-prev" ? "Thématique précédente" : "Thématique suivante"} : ${target.name}`;
    } else {
      link.removeAttribute("href");
      link.setAttribute("aria-disabled", "true");
    }
  };
  step("th-prev", index > 0 ? t.thematiques[index - 1] : null, "Précédente");
  step("th-next", index >= 0 && index < t.thematiques.length - 1 ? t.thematiques[index + 1] : null, "Suivante");
  const active = document.querySelector("#th-travel .tab.active");
  if (active) active.scrollIntoView({ block: "nearest", inline: "center" });
}

function renderKpis(t) {
  const s = t.stats;
  const now = new Date();
  const done = t.microprojets.flatMap((p) => p.frise.filter((n) => n.ended_at)).map((n) => new Date(n.ended_at) - new Date(n.started_at));
  const typical = median(done);
  const starts = t.microprojets.flatMap((p) => [p.created_at, ...p.frise.map((n) => n.started_at)]).filter(Boolean).map((d) => new Date(d));
  const since = starts.length ? new Date(Math.min(...starts)) : null;
  const box = document.getElementById("th-kpis");
  box.innerHTML = [
    kpi(s.microprojets, "µprojets"),
    kpi(s.experiences, "expériences"),
    kpi(s.running, "en cours"),
    kpi(t.microprojets.reduce((n, p) => n + p.frise.filter((x) => x.status === "hold").length, 0), "dont en pause"),
    kpi(s.concluded, "terminées"),
    kpi(s.wafers, "wafers"),
    kpi(typical == null ? "—" : escapeHtml(formatDuration(typical)), "durée médiane jusqu'à conclusion"),
    kpi(since ? escapeHtml(formatDuration(now - since)) : "—", "d'activité"),
  ].join("");
  box.removeAttribute("aria-busy");
}

// --- frise -----------------------------------------------------------------------------------

// Colonne des libellés (µprojet, propriétaire) : plus étroite sur un petit écran, où la frise défile.
const labelWidth = (width) => (width < 600 ? 150 : 230);
const ROW_H = 24; // une sous-ligne d'expériences
const LANE_PAD = 10;
const BAR_H = 8;
const MARK_R = 6.5;
const AXIS_H = 40;
const PAST_SHARE = 0.8; // part de la largeur pour le passé ; le reste = la zone « à venir »
const DAY = 86400000;

// « 6 prochains mois » -> 6 (l'horizon des objectifs du projet donne la largeur de la zone à venir).
function horizonMonths(period) {
  const match = /(\d+)\s*(?:derniers?\s+|prochains?\s+)?mois/i.exec(period || "");
  return match ? Math.min(24, Math.max(1, Number(match[1]))) : 6;
}

function friseGeometry(t, width) {
  const now = new Date();
  const futureEnd = timelineAddMonths(now, horizonMonths(t.area.objectives_period));
  const starts = t.microprojets.flatMap((p) => [p.created_at, ...p.frise.map((n) => n.started_at)]).filter(Boolean).map((d) => +new Date(d));
  let start = starts.length ? Math.min(...starts) : +now - 90 * DAY;
  start = Math.min(start, +now - 30 * DAY); // jamais un passé écrasé sur quelques pixels
  start -= (+now - start) * 0.04;
  const labelW = labelWidth(width);
  const plotW = Math.max(520, width - labelW);
  const pastW = Math.round(plotW * PAST_SHARE);
  const x = d3.scaleTime().domain([new Date(start), now, futureEnd]).range([0, pastW, plotW]);
  return { now, futureEnd, start: new Date(start), labelW, plotW, pastW, x };
}

function friseTicks(geo) {
  const past = d3.scaleTime().domain([geo.start, geo.now]).range([0, geo.pastW]);
  const pastTicks = past.ticks(Math.max(2, Math.floor(geo.pastW / 95)));
  const monthly = pastTicks.every((d) => d.getDate() === 1);
  const future = [];
  for (let d = d3.timeMonth.ceil(new Date(+geo.now + DAY)); d <= geo.futureEnd; d = d3.timeMonth.offset(d, 1)) future.push(d);
  // ni chevauchement, ni sur « Aujourd'hui » (timeline.js)
  return timelineTicks(geo.x, [...pastTicks, ...future], { avoid: [[geo.pastW - 110, geo.pastW + 34]], monthly: (date) => monthly || date > geo.now });
}

function axisSvg(geo, ticks, t) {
  const months = horizonMonths(t.area.objectives_period);
  const futureMid = (geo.pastW + geo.plotW) / 2;
  return `<svg class="frise__track frise-axis" width="${geo.plotW}" height="${AXIS_H}" viewBox="0 0 ${geo.plotW} ${AXIS_H}" aria-hidden="true">
      <rect x="${geo.pastW}" y="0" width="${geo.plotW - geo.pastW}" height="${AXIS_H}" fill="url(#frise-hatch)"></rect>
      <text class="frise-axis__future" x="${futureMid}" y="14" text-anchor="middle">À VENIR · ${months} MOIS</text>
      ${ticks.map((tk) => `<line class="frise-grid" x1="${tk.px}" x2="${tk.px}" y1="${AXIS_H - 8}" y2="${AXIS_H}"></line><text x="${tk.px}" y="${AXIS_H - 12}" text-anchor="middle">${escapeHtml(tk.label)}</text>`).join("")}
      <line class="frise-today" x1="${geo.pastW}" x2="${geo.pastW}" y1="18" y2="${AXIS_H}"></line>
      <text class="frise-axis__today" x="${geo.pastW - 6}" y="${AXIS_H - 12}" text-anchor="end">Aujourd'hui</text>
    </svg>`;
}

// Range les expériences d'un µprojet en sous-lignes pour qu'aucune barre (ni son repère de fin) n'en
// chevauche une autre - en pixels, après mise à l'échelle.
function packLane(items, x) {
  const rowEnds = [];
  for (const item of items) {
    item.x0 = x(item.start);
    item.x1 = Math.max(x(item.end), item.x0 + 4);
    let row = rowEnds.findIndex((end) => end + MARK_R * 2 + 6 <= item.x0);
    if (row < 0) {
      row = rowEnds.length;
      rowEnds.push(item.x1);
    } else {
      rowEnds[row] = item.x1;
    }
    item.row = row;
  }
  return Math.max(1, rowEnds.length);
}

function laneSvg(lane, geo, ticks, laneIndex) {
  const rows = packLane(lane.items, geo.x);
  const height = rows * ROW_H + LANE_PAD * 2;
  const rowY = (row) => LANE_PAD + row * ROW_H + ROW_H / 2;
  const created = lane.p.created_at ? geo.x(new Date(lane.p.created_at)) : lane.items.length ? lane.items[0].x0 : null;
  const life = created == null ? "" : `<line class="frise-life" x1="${created}" x2="${geo.pastW}" y1="${rowY(0)}" y2="${rowY(0)}"></line>`;
  const bars = lane.items
    .map((item, i) => {
      const style = lineageOutcomeStyle(item);
      const y = rowY(item.row);
      const bar = style.filled
        ? `<rect x="${item.x0}" y="${y - BAR_H / 2}" width="${item.x1 - item.x0}" height="${BAR_H}" rx="4" fill="${style.color}"></rect>`
        : `<rect x="${item.x0}" y="${y - BAR_H / 2}" width="${item.x1 - item.x0}" height="${BAR_H}" rx="4" fill="${style.color}" fill-opacity="0.16" style="stroke:${style.color};stroke-width:1.2px"></rect>`;
      const href = item.id ? `/microprojets/${encodeURIComponent(lane.p.slug)}/experiences/${encodeURIComponent(item.id)}` : "";
      const focus = href ? ` tabindex="0" role="link" data-href="${escapeHtml(href)}"` : "";
      return `<g class="frise-bar" data-lane="${laneIndex}" data-item="${i}"${focus} aria-label="${escapeHtml(itemSummary(lane, item))}">
          <rect class="frise-hit" x="${item.x0 - 8}" y="${y - ROW_H / 2 + 1}" width="${item.x1 - item.x0 + 18}" height="${ROW_H - 2}" rx="5"></rect>
          ${bar}
          <g transform="translate(${item.x1},${y})">${lineageNodeShapeHtml(item, { radius: MARK_R, tipRing: false })}</g>
        </g>`;
    })
    .join("");
  const empty = lane.items.length
    ? ""
    : `<text class="frise-empty" x="${Math.min((created ?? 0) + 10, geo.pastW - 160)}" y="${rowY(0) + 4}">Aucune expérience pour l'instant</text>`;
  return `<svg class="frise__track" width="${geo.plotW}" height="${height}" viewBox="0 0 ${geo.plotW} ${height}">
      <rect x="${geo.pastW}" y="0" width="${geo.plotW - geo.pastW}" height="${height}" fill="url(#frise-hatch)"></rect>
      ${ticks.map((tk) => `<line class="frise-grid" x1="${tk.px}" x2="${tk.px}" y1="0" y2="${height}"></line>`).join("")}
      ${life}
      <line class="frise-today" x1="${geo.pastW}" x2="${geo.pastW}" y1="0" y2="${height}"></line>
      ${bars}${empty}
    </svg>`;
}

function itemTitle(item) {
  return item.title || "Expérience";
}

function itemSummary(lane, item) {
  return `${lane.p.code ? `${lane.p.code} · ` : ""}${itemTitle(item)} - ${lineageOutcomeStyle(item).label}, ${lineageElapsedLabel(item)}`;
}

function laneLabel(p) {
  const name = p.role
    ? `<a class="frise__name" href="${microprojetUrl(p)}" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</a>`
    : `<span class="frise__name" title="${escapeHtml(p.name)} - vous n'êtes pas membre de ce µprojet">${escapeHtml(p.name)}</span>`;
  const meta = [plural(p.frise.length, "version", "versions"), p.created_at ? `créé le ${formatDate(p.created_at)}` : ""].filter(Boolean).join(" · ");
  return `<div class="frise__label">
      <div class="frise__title">${p.code ? `<span class="mp-code">${escapeHtml(p.code)}</span>` : ""}${name}</div>
      ${ownerChipHtml(p.owners, { label: false })}
      <div class="frise__meta">${escapeHtml(meta)}</div>
    </div>`;
}

let friseLanes = [];

function renderFrise(t) {
  const scroll = document.getElementById("frise-scroll");
  if (!t.microprojets.length) {
    scroll.innerHTML = `<div class="empty-state"><div style="font-weight:600;color:var(--text-soft);">Aucun µprojet dans cette thématique pour l'instant</div><div style="font-size:13px;">« + Nouveau µprojet » pour démarrer sa chronologie.</div></div>`;
    return;
  }
  const geo = friseGeometry(t, scroll.clientWidth || 1000);
  const ticks = friseTicks(geo);
  friseLanes = t.microprojets.map((p) => ({
    p,
    items: p.frise
      .map((n) => {
        const span = lineageSpan(n);
        return { ...n, start: new Date(span.start), end: span.end ? new Date(span.end) : geo.now };
      })
      .sort((a, b) => a.start - b.start),
  }));
  const months = horizonMonths(t.area.objectives_period);
  scroll.innerHTML = `
    <div class="frise" style="width:${geo.labelW + geo.plotW}px;--label-w:${geo.labelW}px;">
      ${timelineHatchDefs("frise-hatch")}
      <div class="frise__row frise__row--axis"><div></div>${axisSvg(geo, ticks, t)}</div>
      ${friseLanes.map((lane, i) => `<div class="frise__row">${laneLabel(lane.p)}${laneSvg(lane, geo, ticks, i)}</div>`).join("")}
      <div class="frise-future-note" style="left:${geo.labelW + geo.pastW}px;width:${geo.plotW - geo.pastW}px;">
        <span title="Placeholder : jalons et µprojets prévus sur les ${months} prochains mois - voir « Perspectives » plus bas">Feuille de route à venir</span>
      </div>
    </div>`;
  renderTable();
}

// Bulle de détail : au survol comme au focus clavier (jamais au survol seul).
function showTooltip(group) {
  const lane = friseLanes[Number(group.dataset.lane)];
  const item = lane && lane.items[Number(group.dataset.item)];
  const tip = document.getElementById("frise-tooltip");
  if (!item || !tip) return;
  tip.innerHTML = `
    <div class="frise-tooltip__where">${escapeHtml(lane.p.code || lane.p.name)}</div>
    <div class="frise-tooltip__title">${escapeHtml(itemTitle(item))}</div>
    ${statusBadgeHtml(item.status, item.decision)} <strong style="margin-left:6px;font-variant-numeric:tabular-nums;">${escapeHtml(lineageElapsedLabel(item))}</strong>
    <div class="frise-tooltip__dates">${escapeHtml(lineageDatesLabel(item))}</div>
    ${lineageHoldLabel(item) ? `<div class="frise-tooltip__hold">${escapeHtml(lineageHoldLabel(item))}</div>` : ""}
    <div class="frise-tooltip__hint">${item.id ? "Cliquer pour ouvrir la fiche" : "Détail réservé aux membres du µprojet"}</div>`;
  tip.hidden = false;
  // position: fixed (hors du conteneur qui défile, sinon la bulle y serait rognée)
  const box = group.getBoundingClientRect();
  const tipBox = tip.getBoundingClientRect();
  let left = box.left + box.width / 2 - tipBox.width / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - tipBox.width - 8));
  let top = box.top - tipBox.height - 8;
  if (top < 8) top = box.bottom + 8;
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function hideTooltip() {
  const tip = document.getElementById("frise-tooltip");
  if (tip) tip.hidden = true;
}

const friseScroll = document.getElementById("frise-scroll");
friseScroll.addEventListener("mouseover", (event) => {
  const group = event.target.closest(".frise-bar");
  if (group) showTooltip(group);
});
friseScroll.addEventListener("mouseout", (event) => {
  const group = event.target.closest(".frise-bar");
  if (group && !group.contains(event.relatedTarget)) hideTooltip();
});
friseScroll.addEventListener("focusin", (event) => {
  const group = event.target.closest(".frise-bar");
  if (group) showTooltip(group);
});
friseScroll.addEventListener("focusout", hideTooltip);
friseScroll.addEventListener("scroll", hideTooltip);
window.addEventListener("scroll", hideTooltip, { passive: true });
friseScroll.addEventListener("click", (event) => {
  const group = event.target.closest(".frise-bar[data-href]");
  if (group) window.location.href = group.dataset.href;
});
friseScroll.addEventListener("keydown", (event) => {
  const group = event.target.closest && event.target.closest(".frise-bar[data-href]");
  if (group && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    window.location.href = group.dataset.href;
  }
});

let resizeTimer = null;
new ResizeObserver(() => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => current && current.microprojets.length && renderFrise(current), 120);
}).observe(friseScroll);

// Vue tableau de la frise : les mêmes données, lisibles sans la couleur ni la souris.
function renderTable() {
  const rows = friseLanes.flatMap((lane) =>
    lane.items.map(
      (item) => `<tr>
        <td>${lane.p.code ? `<span class="mp-code">${escapeHtml(lane.p.code)}</span> ` : ""}${escapeHtml(lane.p.name)}</td>
        <td>${item.id ? `<a href="/microprojets/${encodeURIComponent(lane.p.slug)}/experiences/${encodeURIComponent(item.id)}">${escapeHtml(itemTitle(item))}</a>` : escapeHtml(itemTitle(item))}</td>
        <td>${statusBadgeHtml(item.status, item.decision)}</td>
        <td class="num">${escapeHtml(formatDate(item.started_at))}</td>
        <td class="num">${lineageSpan(item).end ? `${escapeHtml(formatDate(lineageSpan(item).end))}${lineageSpan(item).state === "continued" ? " (continuée)" : ""}` : "—"}</td>
        <td class="num">${escapeHtml(lineageElapsedLabel(item))}</td>
      </tr>`
    )
  );
  document.getElementById("frise-table-body").innerHTML = rows.length
    ? `<div style="overflow-x:auto;"><table><thead><tr><th>µprojet</th><th>Version d'expérience</th><th>Issue</th><th>Début</th><th>Fin</th><th>Durée</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`
    : `<p class="help" style="margin-top:8px;">Aucune expérience.</p>`;
}

// --- µprojets ---------------------------------------------------------------------------------

function lastActivity(p) {
  const dates = [p.created_at, ...p.frise.flatMap((n) => [n.started_at, n.ended_at])].filter(Boolean).map((d) => +new Date(d));
  return dates.length ? new Date(Math.max(...dates)).toISOString() : null;
}

function microprojetCard(p) {
  const last = lastActivity(p);
  const inner = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:22px;">
      ${p.code ? `<span class="mp-code" title="Numéro du µprojet">${escapeHtml(p.code)}</span>` : "<span></span>"}
      ${p.role ? `<span class="badge badge-role">${escapeHtml(roleLabel(p.role))}</span>` : `<span style="font-size:11px;color:var(--text-faint);">non membre</span>`}
    </div>
    <div style="font-size:15px;font-weight:700;line-height:1.3;overflow-wrap:anywhere;">${escapeHtml(p.name)}</div>
    <div style="font-size:13px;color:var(--text-soft);min-height:16px;">${escapeHtml(p.description || "")}</div>
    ${ownerChipHtml(p.owners)}
    <div class="mp-card__stats">
      <span>${plural(p.experiences, "expérience", "expériences")}</span><span>${p.running} en cours</span><span>${p.concluded} terminées</span><span>${p.wafers} wafers</span>
      ${last ? `<span style="flex-basis:100%;">Dernière activité ${escapeHtml(timeAgo(last))}</span>` : ""}
    </div>`;
  return p.role
    ? `<a href="${microprojetUrl(p)}" class="card card-pad mp-card">${inner}</a>`
    : `<div class="card card-pad mp-card mp-card--locked" title="Vous n'êtes pas membre de ce µprojet">${inner}</div>`;
}

function renderMicroprojets(t) {
  document.getElementById("th-microprojets").innerHTML = t.microprojets.length
    ? t.microprojets.map(microprojetCard).join("")
    : `<div class="card empty-state" style="grid-column:1/-1;">Aucun µprojet dans cette thématique pour l'instant.</div>`;
}

// --- perspectives (placeholder) ---------------------------------------------------------------

function quarterLabel(date) {
  return `T${Math.floor(date.getMonth() / 3) + 1} ${date.getFullYear()}`;
}

function renderFuture(t) {
  const now = new Date();
  const months = horizonMonths(t.area.objectives_period);
  const quarters = [];
  for (let m = 1; m <= months && quarters.length < 3; m += 1) {
    const label = quarterLabel(timelineAddMonths(now, m));
    if (!quarters.includes(label) && label !== quarterLabel(now)) quarters.push(label);
  }
  if (!quarters.length) quarters.push(quarterLabel(timelineAddMonths(now, 3)));
  const ghost = (when) => `<li class="th-future__item"><span class="th-future__when">${escapeHtml(when)}</span><span class="th-future__ghost" aria-hidden="true"></span></li>`;
  document.getElementById("th-future").innerHTML = `
    <div class="th-section__head" style="margin-bottom:8px;">
      <div>
        <div class="page-eyebrow">Perspectives</div>
        <h2 id="future-title">Évolution de la thématique</h2>
        <p class="th-section__sub">Où va « ${escapeHtml(t.name)} » sur les ${escapeHtml(t.area.objectives_period || "6 prochains mois")}.</p>
      </div>
      <span class="badge badge-draft"><span class="dot"></span>Aperçu · à venir</span>
    </div>
    <div class="th-future__grid">
      <div class="th-future__col"><h3>Prochains jalons</h3><ul>${quarters.map(ghost).join("")}</ul></div>
      <div class="th-future__col"><h3>Cibles des KPI</h3><ul>${["cible", "cible"].map(() => ghost("à définir")).join("")}</ul></div>
      <div class="th-future__col"><h3>µprojets envisagés</h3><ul>${ghost("à planifier")}${ghost("à planifier")}</ul></div>
    </div>
    <p class="th-future__note">Emplacement réservé : ce bloc accueillera la feuille de route de la thématique - jalons datés, cibles des indicateurs suivis et µprojets prévus, reliés aux objectifs corporate de ${escapeHtml(t.area.name)}. Ils prolongeront la frise au-delà d'aujourd'hui.</p>`;
}

// --- nouveau µprojet dans cette thématique ----------------------------------------------------

const mpDialog = document.getElementById("microprojet-dialog");
document.getElementById("new-microprojet-btn").addEventListener("click", () => mpDialog.showModal());
document.getElementById("mp-cancel").addEventListener("click", () => mpDialog.close());
document.getElementById("microprojet-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const p = await microprojectsApi.create({
      name: document.getElementById("mp-name").value,
      description: document.getElementById("mp-description").value,
      management_area_slug: areaSlug,
      thematique_slug: thematicSlug,
    });
    window.location.href = microprojetUrl(p);
  } catch (err) {
    mpDialog.close();
    showError(err);
  }
});

// --- chargement -------------------------------------------------------------------------------

async function load() {
  document.getElementById("frise-legend").innerHTML = lineageLegendHtml({ tip: false });
  try {
    current = await areasApi.getThematic(areaSlug, thematicSlug);
  } catch (err) {
    showError(err);
    document.getElementById("th-name").textContent = "Thématique introuvable";
    document.getElementById("frise-scroll").innerHTML = "";
    return;
  }
  renderHead(current);
  renderTravel(current);
  renderKpis(current);
  renderFrise(current);
  renderMicroprojets(current);
  renderFuture(current);
}

load();
