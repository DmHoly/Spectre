/* Page « Lots » (/lots) : le Gantt des lots par priorité (en cours par défaut ; sortis, annulés,
   tous), leurs indicateurs, et la création d'un lot (priorité, début, fin prévisionnelle, wafers).
   Une ligne se déplie sur les expériences du lot (celles qui suivent un de ses wafers). Rendu
   partagé avec la fiche d'un lot : lots-gantt.js. */

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

const FILTER_KEY = "spectre:lots:filtre";
let filter = "actifs";
try {
  filter = localStorage.getItem(FILTER_KEY) || "actifs";
} catch (err) {
  filter = "actifs";
}
let lots = [];
const expanded = new Set();
const scroll = document.getElementById("gantt-scroll");

function kpi(value, label, alert) {
  return `<div class="kpi${alert ? " kpi--alert" : ""}"><div class="kpi__value">${value}</div><div class="kpi__label">${label}</div></div>`;
}

function renderKpis() {
  const active = lots.filter((l) => ["planned", "wip", "hold"].includes(l.status));
  const wafers = active.filter((l) => l.status !== "planned").reduce((n, l) => n + l.wafers.length, 0);
  const late = active.filter((l) => l.late_days).length;
  const soon = active.filter((l) => {
    const d = lotDay(l.forecast_exit_on);
    return d && d >= lotTodayStart() && d - lotTodayStart() <= 30 * LOT_DAY;
  }).length;
  const box = document.getElementById("lots-kpis");
  box.innerHTML = [
    kpi(lots.length, filter === "actifs" ? "lots suivis" : "lots affichés"),
    kpi(active.filter((l) => l.status === "wip").length, "en cours"),
    kpi(active.filter((l) => l.status === "hold").length, "en pause"),
    kpi(wafers, "wafers dans le WIP"),
    kpi(late, "en retard", late > 0),
    kpi(soon, "sorties prévues sous 30 j"),
  ].join("");
  box.removeAttribute("aria-busy");
}

function renderGantt() {
  if (!lots.length) {
    scroll.innerHTML = `<div class="empty-state">
        <div style="font-weight:600;color:var(--text-soft);">${filter === "actifs" ? "Aucun lot en cours" : "Aucun lot ici"}</div>
        <div style="font-size:13px;">« + Nouveau lot » pour déclarer un lot : ses wafers, son parcours, sa sortie prévue.</div>
      </div>`;
    return;
  }
  scroll.innerHTML = ganttHtml(lots, scroll.clientWidth || 1100, { expanded });
}

function renderTable() {
  document.getElementById("lots-table-body").innerHTML = lots.length
    ? `<div style="overflow-x:auto;"><table><thead><tr><th>Lot</th><th>Priorité</th><th>Statut</th><th>Début</th><th>Fin prévisionnelle</th><th>Fin déclarée</th><th>Wafers</th><th>Expériences</th><th>Thématiques</th></tr></thead><tbody>${lots
        .map(
          (l) => `<tr>
            <td><a href="${lotUrl(l.code)}" style="font-family:var(--font-mono);font-weight:600;">${escapeHtml(l.code)}</a>${l.title ? ` · ${escapeHtml(l.title)}` : ""}</td>
            <td>${lotPriorityHtml(l.priority) || "—"}</td>
            <td>${lotStatusBadgeHtml(l.status)}</td>
            <td class="num">${escapeHtml(lotDateLabel(l.started_on) || "—")}</td>
            <td class="num">${escapeHtml(lotDateLabel(l.forecast_exit_on) || "—")}${l.late_days ? ` <span style="color:var(--danger);font-weight:600;">+${l.late_days} j</span>` : ""}</td>
            <td class="num">${escapeHtml(lotDateLabel(l.exited_on) || "—")}${l.exit_delta_days ? ` <span style="color:${l.exit_delta_days > 0 ? "var(--danger)" : "var(--done)"};">(${l.exit_delta_days > 0 ? "+" : ""}${l.exit_delta_days} j)</span>` : ""}</td>
            <td class="num">${l.wafers.length}</td>
            <td class="num">${l.experiences.length}</td>
            <td>${escapeHtml(l.thematiques.map((t) => t.name).join(", ") || "—")}</td>
          </tr>`
        )
        .join("")}</tbody></table></div>`
    : `<p class="help" style="margin-top:8px;">Aucun lot.</p>`;
}

async function load() {
  document.querySelectorAll("#lots-filter [data-filter]").forEach((b) => {
    const on = b.dataset.filter === filter;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
  try {
    lots = (await api.get(`/api/lots?statut=${encodeURIComponent(filter)}`)).lots;
  } catch (err) {
    showError(err);
    scroll.innerHTML = "";
    return;
  }
  renderKpis();
  renderGantt();
  renderTable();
}

document.getElementById("gantt-legend").innerHTML = ganttLegendHtml();
mountGanttTooltip(scroll);

document.getElementById("lots-filter").addEventListener("click", (event) => {
  const button = event.target.closest("[data-filter]");
  if (!button || button.dataset.filter === filter) return;
  filter = button.dataset.filter;
  try {
    localStorage.setItem(FILTER_KEY, filter);
  } catch (err) {
    /* confort seulement */
  }
  load();
});

scroll.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-toggle]");
  if (!toggle) return;
  event.stopPropagation();
  const code = toggle.dataset.toggle;
  if (expanded.has(code)) expanded.delete(code);
  else expanded.add(code);
  renderGantt();
  const again = scroll.querySelector(`[data-toggle="${CSS.escape(code)}"]`);
  if (again) again.focus();
});

let resizeTimer = null;
new ResizeObserver(() => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => lots.length && renderGantt(), 120);
}).observe(scroll);

// --- nouveau lot ------------------------------------------------------------------------------

const lotDialog = document.getElementById("lot-dialog");
document.getElementById("new-lot-btn").addEventListener("click", () => {
  document.getElementById("lot-form").reset();
  lotDialog.showModal();
  document.getElementById("lot-code").focus();
});
document.getElementById("lot-cancel").addEventListener("click", () => lotDialog.close());
document.getElementById("lot-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const lot = await api.post("/api/lots", {
      code: document.getElementById("lot-code").value.trim() || null,
      title: document.getElementById("lot-title").value,
      priority: document.getElementById("lot-priority").value,
      description: document.getElementById("lot-description").value,
      started_on: document.getElementById("lot-started").value || null,
      forecast_exit_on: document.getElementById("lot-forecast").value || null,
      wafers: document.getElementById("lot-wafers").value.split(/[\s,;]+/).filter(Boolean),
    });
    window.location.href = lotUrl(lot.code);
  } catch (err) {
    lotDialog.close();
    showError(err);
  }
});

load();
