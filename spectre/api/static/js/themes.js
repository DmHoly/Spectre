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

function themeCard(area) {
  const s = area.stats;
  return `
    <a href="/management/${encodeURIComponent(area.slug)}" class="theme-card">
      <div class="theme-card__art">${techArtSvg(area.slug, area.name)}</div>
      <div class="theme-card__head">
        <div class="theme-card__name">${escapeHtml(area.name)}</div>
        <svg class="theme-card__go" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14"/><path d="m13 6 6 6-6 6"/></svg>
      </div>
      <div class="theme-card__desc">${escapeHtml(area.description || area.strategy || "")}</div>
      <div class="theme-card__stats">
        ${stat(s.thematiques, "thématiques")}
        ${stat(s.microprojets, "µprojets")}
        ${stat(s.experiences, "expériences")}
        ${stat(s.wafers, "wafers")}
      </div>
    </a>`;
}

function microprojectCard(microproject) {
  const area = microproject.management_area;
  const where = [area && area.name, microproject.thematique && microproject.thematique.name].filter(Boolean).join(" › ");
  return `
    <a href="/microprojets/${encodeURIComponent(microproject.slug)}" class="card card-pad" style="display:flex;flex-direction:column;gap:6px;color:inherit;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <div style="font-size:14px;font-weight:700;">${escapeHtml(microproject.name)}</div>
        <span class="badge badge-role">${escapeHtml(roleLabel(microproject.role))}</span>
      </div>
      ${where ? `<div style="font-size:11.5px;color:var(--text-faint);font-family:var(--font-mono);">${escapeHtml(where)}</div>` : ""}
      <div style="font-size:12px;color:var(--text-faint);padding-top:6px;border-top:1px solid var(--border-soft);">
        ${microproject.running_count} en cours &middot; ${microproject.concluded_count} terminées
      </div>
    </a>`;
}

async function load() {
  try {
    const [mgmt, mine] = await Promise.all([api.get("/api/management"), api.get("/api/microprojets")]);

    // "Non classé" ne s'affiche que s'il contient vraiment quelque chose - sinon il encombre.
    // « Non classé » n'est pas un projet : il sort de la grille, replié en bas comme « Mes µprojets »
    // (et n'apparaît que s'il contient quelque chose).
    const themes = mgmt.areas.filter((a) => a.slug !== "non-classe");
    const unclassified = mgmt.areas.find((a) => a.slug === "non-classe");
    if (unclassified && unclassified.stats.microprojets > 0) {
      document.getElementById("unclassified-count").textContent = `(${unclassified.stats.microprojets})`;
      document.getElementById("unclassified-details").style.display = "";
    }
    const grid = document.getElementById("themes");
    grid.innerHTML = themes.map(themeCard).join("");
    grid.removeAttribute("aria-busy");
    if (mgmt.is_admin) document.getElementById("new-theme-btn").style.display = "";

    document.getElementById("my-microprojects-count").textContent = `(${mine.length})`;
    document.getElementById("my-microprojects").innerHTML = mine.length
      ? mine.map(microprojectCard).join("")
      : `<div style="grid-column:1/-1;font-size:13px;color:var(--text-faint);">Vous n'êtes membre d'aucun µprojet. Ouvrez un projet pour en créer un.</div>`;
    if (mine.length) document.getElementById("my-microprojects-details").open = false;
  } catch (err) {
    document.getElementById("themes").innerHTML = "";
    showError(err);
  }
}

const dialog = document.getElementById("new-theme-dialog");
document.getElementById("new-theme-btn").addEventListener("click", () => dialog.showModal());
document.getElementById("cancel-theme").addEventListener("click", () => dialog.close());
document.getElementById("new-theme-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const area = await api.post("/api/management", {
      name: document.getElementById("theme-name").value,
      description: document.getElementById("theme-description").value,
      strategy: document.getElementById("theme-strategy").value,
    });
    window.location.href = `/management/${encodeURIComponent(area.slug)}`;
  } catch (err) {
    dialog.close();
    showError(err);
  }
});

// Contenu de « Non classé » chargé seulement à l'ouverture du bloc (la page d'accueil n'en a pas besoin).
const unclassifiedDetails = document.getElementById("unclassified-details");
unclassifiedDetails.addEventListener("toggle", async () => {
  if (!unclassifiedDetails.open || unclassifiedDetails.dataset.loaded) return;
  const box = document.getElementById("unclassified");
  box.innerHTML = `<div class="skeleton" style="height:84px;"></div>`;
  try {
    const area = await api.get("/api/management/non-classe");
    unclassifiedDetails.dataset.loaded = "1";
    box.innerHTML = area.microprojets
      .map((p) => {
        const inner = `
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
            <div style="font-size:14px;font-weight:700;">${escapeHtml(p.name)}</div>
            ${p.role ? `<span class="badge badge-role">${escapeHtml(roleLabel(p.role))}</span>` : `<span style="font-size:11px;color:var(--text-faint);">non membre</span>`}
          </div>
          <div style="font-size:12px;color:var(--text-faint);padding-top:6px;border-top:1px solid var(--border-soft);">
            ${p.running} en cours &middot; ${p.concluded} terminées
          </div>`;
        return p.role
          ? `<a href="/microprojets/${encodeURIComponent(p.slug)}" class="card card-pad" style="display:flex;flex-direction:column;gap:6px;color:inherit;">${inner}</a>`
          : `<div class="card card-pad" style="display:flex;flex-direction:column;gap:6px;opacity:.75;">${inner}</div>`;
      })
      .join("");
  } catch (err) {
    box.innerHTML = "";
    showError(err);
  }
});

load();
