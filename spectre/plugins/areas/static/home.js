/* Racine de la navigation : les projets corporate (couche Management : Native, VLC, Nova), bien
   mis en avant, puis un lien discret « Mes µprojets » en bas pour l'accès direct. Entrer dans un
   projet -> /management/{slug} (objectifs, thématiques, µprojets). */

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

function stat(n, label) {
  return `<div class="kpi"><div class="kpi__value">${n}</div><div class="kpi__label">${label}</div></div>`;
}

function themeCard(area, thematicCount, totals) {
  return `
    <a href="/management/${encodeURIComponent(area.slug)}" class="theme-card">
      <div class="theme-card__art">${techArtSvg(area.slug, area.name)}</div>
      <div class="theme-card__head">
        <div class="theme-card__name">${escapeHtml(area.name)}</div>
        <svg class="theme-card__go" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>
      </div>
      <div class="theme-card__desc">${escapeHtml(area.description || area.strategy || "")}</div>
      <div class="theme-card__stats">
        ${stat(thematicCount, "thématiques")}
        ${stat(totals.microprojects, "µprojets")}
        ${stat(totals.experiments, "expériences")}
        ${stat(totals.wafers, "wafers")}
      </div>
    </a>`;
}

// Un de mes µprojets, avec ses compteurs (sa ligne d'experimentsApi.stats).
function microprojectCard(microproject, counts) {
  const area = microproject.area;
  const where = [area && area.name, microproject.thematic && microproject.thematic.name].filter(Boolean).join(" › ");
  return `
    <a href="/microprojets/${encodeURIComponent(microproject.slug)}" class="card card-pad" style="display:flex;flex-direction:column;gap:6px;color:inherit;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:22px;">
        ${microproject.code ? `<span class="mp-code" title="Numéro du µprojet">${escapeHtml(microproject.code)}</span>` : "<span></span>"}
        <span class="badge badge-role">${escapeHtml(roleLabel(microproject.role, microproject.role_source))}</span>
      </div>
      <div style="font-size:14px;font-weight:700;line-height:1.3;overflow-wrap:anywhere;">${escapeHtml(microproject.name)}</div>
      ${where ? `<div style="font-size:11.5px;color:var(--text-faint);font-family:var(--font-mono);">${escapeHtml(where)}</div>` : ""}
      ${ownerChipHtml(microproject.owners)}
      <div style="font-size:12px;color:var(--text-faint);padding-top:6px;border-top:1px solid var(--border-soft);">
        ${counts.running} en cours &middot; ${counts.concluded + counts.abandoned} terminées
      </div>
    </a>`;
}

// Un µprojet du projet système (« Non classé ») : ses compteurs (experimentsApi.stats).
function unclassifiedCard(row) {
  const p = row.microproject;
  const inner = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
      <div style="font-size:14px;font-weight:700;">${escapeHtml(p.name)}</div>
      ${p.role ? `<span class="badge badge-role">${escapeHtml(roleLabel(p.role, p.role_source))}</span>` : `<span style="font-size:11px;color:var(--text-faint);">non membre</span>`}
    </div>
    <div style="font-size:12px;color:var(--text-faint);padding-top:6px;border-top:1px solid var(--border-soft);">
      ${row.running} en cours &middot; ${row.concluded + row.abandoned} terminées
    </div>`;
  return p.role
    ? `<a href="/microprojets/${encodeURIComponent(p.slug)}" class="card card-pad" style="display:flex;flex-direction:column;gap:6px;color:inherit;">${inner}</a>`
    : `<div class="card card-pad" style="display:flex;flex-direction:column;gap:6px;opacity:.75;">${inner}</div>`;
}

async function load() {
  try {
    const [areas, thematics, stats, mine, me, teams] = await Promise.all([
      areasApi.list(),
      areasApi.listThematics(),
      experimentsApi.stats(),
      microprojectsApi.list(),
      accountsApi.me(),
      teamsApi.list(),
    ]);
    const rowsOf = (area) => stats.filter((row) => row.microproject.area && row.microproject.area.slug === area.slug);
    const thematicsOf = (area) => thematics.filter((t) => t.area.slug === area.slug).length;

    // Le projet système (« Non classé ») n'est pas un projet : il sort de la grille, replié en bas
    // comme « Mes µprojets », et n'apparaît que s'il contient quelque chose.
    const unclassified = areas.find((a) => a.is_system);
    const waiting = unclassified ? rowsOf(unclassified) : [];
    if (waiting.length) {
      document.getElementById("unclassified-name").textContent = unclassified.name;
      document.getElementById("unclassified-count").textContent = `(${waiting.length})`;
      document.getElementById("unclassified-link").href = `/management/${encodeURIComponent(unclassified.slug)}`;
      document.getElementById("unclassified").innerHTML = waiting.map(unclassifiedCard).join("");
      document.getElementById("unclassified-details").style.display = "";
    }
    const grid = document.getElementById("themes");
    grid.innerHTML = areas
      .filter((a) => !a.is_system)
      .map((area) => themeCard(area, thematicsOf(area), experimentTotals(rowsOf(area))))
      .join("");
    grid.removeAttribute("aria-busy");
    // Créer un projet : un admin (rattaché ou non à une équipe), ou un manager, à l'une de ses équipes.
    const teamChoices = teams.filter((team) => team.can_manage);
    if (me.is_admin || teamChoices.length) {
      document.getElementById("theme-team").innerHTML = (me.is_admin ? [`<option value="">— Aucune équipe —</option>`] : [])
        .concat(teamChoices.map((team) => `<option value="${escapeHtml(team.slug)}">${escapeHtml(team.name)}</option>`))
        .join("");
      document.getElementById("new-theme-btn").style.display = "";
    }

    // Nouvelle expérience : d'abord une référence, puis le µprojet où la lancer (éditeur)
    if (mine.some((p) => p.can_edit)) document.getElementById("new-experience-btn").style.display = "";

    document.getElementById("my-microprojects-count").textContent = `(${mine.length})`;
    document.getElementById("my-microprojects").innerHTML = mine.length
      ? mine.map((p) => microprojectCard(p, stats.find((row) => row.microproject.slug === p.slug))).join("")
      : `<div style="grid-column:1/-1;font-size:13px;color:var(--text-faint);">Vous n'êtes membre d'aucun µprojet. Ouvrez un projet pour en créer un.</div>`;
    if (mine.length) document.getElementById("my-microprojects-details").open = false;
  } catch (err) {
    document.getElementById("themes").innerHTML = "";
    showError(err);
  }
}

document.getElementById("new-experience-btn").addEventListener("click", () => ReferenceStartPicker.open());

const dialog = document.getElementById("new-theme-dialog");
document.getElementById("new-theme-btn").addEventListener("click", () => dialog.showModal());
document.getElementById("cancel-theme").addEventListener("click", () => dialog.close());
document.getElementById("new-theme-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const area = await areasApi.create({
      name: document.getElementById("theme-name").value,
      description: document.getElementById("theme-description").value,
      strategy: document.getElementById("theme-strategy").value,
      team: document.getElementById("theme-team").value || null,
    });
    window.location.href = `/management/${encodeURIComponent(area.slug)}`;
  } catch (err) {
    dialog.close();
    showError(err);
  }
});

// /p/{code} (lien court vers un µprojet) renvoie ici avec ?introuvable= quand le numéro n'existe pas.
const notFoundCode = new URLSearchParams(window.location.search).get("introuvable");
if (notFoundCode) showError(new Error(`Aucun µprojet numéroté « ${notFoundCode} ».`));

load();
