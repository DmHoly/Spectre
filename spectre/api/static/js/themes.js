/* Racine de la navigation : les grands thèmes (couche Management), bien mis en avant, puis un lien
   discret « Mes µprojets » en bas pour l'accès direct. Entrer dans un thème -> /management/{slug}. */

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

function stat(n, label) {
  return `<span><strong>${n}</strong> ${label}</span>`;
}

function themeCard(area) {
  const s = area.stats;
  return `
    <a href="/management/${encodeURIComponent(area.slug)}" class="theme-card">
      <div class="theme-card__name">${escapeHtml(area.name)}</div>
      <div style="font-size:13px;color:var(--text-soft);line-height:1.55;min-height:20px;">${escapeHtml(area.description || area.strategy || "")}</div>
      <div class="theme-card__stats">
        ${stat(s.microprojets, "µprojets")}
        ${stat(s.experiences, "expériences")}
        ${stat(s.wafers, "wafers")}
        ${stat(s.concluded, "concluantes")}
      </div>
    </a>`;
}

function microprojectCard(microproject) {
  const area = microproject.management_area;
  return `
    <a href="/microprojets/${encodeURIComponent(microproject.slug)}" class="card card-pad" style="display:flex;flex-direction:column;gap:6px;color:inherit;">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <div style="font-size:14px;font-weight:700;">${escapeHtml(microproject.name)}</div>
        <span class="badge badge-role">${escapeHtml(roleLabel(microproject.role))}</span>
      </div>
      ${area ? `<div style="font-size:11px;color:var(--text-faint);text-transform:uppercase;letter-spacing:.02em;">${escapeHtml(area.name)}</div>` : ""}
      <div style="font-size:12px;color:var(--text-faint);padding-top:6px;border-top:1px solid var(--border-soft);">
        ${microproject.running_count} en cours &middot; ${microproject.concluded_count} terminées
      </div>
    </a>`;
}

async function load() {
  try {
    const [mgmt, mine] = await Promise.all([api.get("/api/management"), api.get("/api/microprojets")]);

    // "Non classé" ne s'affiche que s'il contient vraiment quelque chose - sinon il encombre.
    const themes = mgmt.areas.filter((a) => a.slug !== "non-classe" || a.stats.microprojets > 0);
    document.getElementById("themes").innerHTML = themes.map(themeCard).join("");
    if (mgmt.is_admin) document.getElementById("new-theme-btn").style.display = "";

    document.getElementById("my-microprojects-count").textContent = `(${mine.length})`;
    document.getElementById("my-microprojects").innerHTML = mine.length
      ? mine.map(microprojectCard).join("")
      : `<div style="grid-column:1/-1;font-size:13px;color:var(--text-faint);">Vous n'êtes membre d'aucun µprojet. Ouvrez un thème pour en créer un.</div>`;
    if (mine.length) document.getElementById("my-microprojects-details").open = false;
  } catch (err) {
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

load();
