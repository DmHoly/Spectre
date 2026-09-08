/* Page d'un grand thème (/management/{slug}) : son objectif stratégique, ses KPI agrégés, et la
   liste des µprojets qui l'adressent. Un admin peut y créer un µprojet, en rattacher un existant,
   éditer ou supprimer le thème. Voir spectre.api.management. */

const slug = window.location.pathname.split("/").filter(Boolean)[1];

const errorBox = document.getElementById("error");
const flashBox = document.getElementById("flash");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function flash(msg) {
  flashBox.textContent = msg;
  flashBox.style.display = "block";
  setTimeout(() => (flashBox.style.display = "none"), 3000);
}

let current = null;

function kpi(n, label) {
  return `<div><div style="font-size:20px;font-weight:700;">${n}</div><div style="font-size:11.5px;color:var(--text-faint);text-transform:uppercase;letter-spacing:.03em;">${label}</div></div>`;
}

function microprojetCard(p) {
  const roleBadge = p.role ? `<span class="badge badge-role">${escapeHtml(roleLabel(p.role))}</span>` : "";
  const openable = Boolean(p.role);
  const inner = `
    <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
      <div style="font-size:15px;font-weight:700;">${escapeHtml(p.name)}</div>
      ${roleBadge || `<span style="font-size:11px;color:var(--text-faint);">non membre</span>`}
    </div>
    <div style="font-size:13px;color:var(--text-soft);min-height:16px;">${escapeHtml(p.description || "")}</div>
    <div style="display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--text-faint);padding-top:8px;border-top:1px solid var(--border-soft);">
      <span>${p.experiences} expériences</span><span>${p.running} en cours</span><span>${p.concluded} concluantes</span><span>${p.wafers} wafers</span>
    </div>`;
  return openable
    ? `<a href="/microprojets/${encodeURIComponent(p.slug)}" class="card card-pad" style="display:flex;flex-direction:column;gap:8px;color:inherit;">${inner}</a>`
    : `<div class="card card-pad" style="display:flex;flex-direction:column;gap:8px;opacity:.75;">${inner}</div>`;
}

function render(area) {
  current = area;
  document.getElementById("crumb").textContent = "/ " + area.name;
  document.getElementById("area-name-crumb").textContent = area.name;
  document.getElementById("area-name").textContent = area.name;
  document.getElementById("area-description").textContent = area.description || "";
  const strategyEl = document.getElementById("area-strategy");
  if (area.strategy) {
    strategyEl.textContent = "Objectif stratégique : " + area.strategy;
    strategyEl.style.display = "";
  } else {
    strategyEl.style.display = "none";
  }
  const s = area.stats;
  document.getElementById("area-kpi").innerHTML = [
    kpi(s.microprojets, "µprojets"),
    kpi(s.experiences, "expériences"),
    kpi(s.running, "en cours"),
    kpi(s.concluded, "concluantes"),
    kpi(s.wafers, "wafers"),
  ].join("");
  document.getElementById("microprojets").innerHTML = area.microprojets.length
    ? area.microprojets.map(microprojetCard).join("")
    : `<div class="empty-state card" style="grid-column:1/-1;"><div style="font-weight:600;color:var(--text-soft);">Aucun µprojet dans ce thème</div></div>`;

  const admin = area.is_admin;
  document.getElementById("edit-area-btn").style.display = admin ? "" : "none";
  document.getElementById("attach-microprojet-btn").style.display = admin ? "" : "none";
  document.getElementById("ea-delete").style.display = admin && area.slug !== "non-classe" ? "" : "none";
}

async function load() {
  try {
    render(await api.get(`/api/management/${encodeURIComponent(slug)}`));
  } catch (err) {
    showError(err);
  }
}

// --- nouveau µprojet ---
const mpDialog = document.getElementById("microprojet-dialog");
document.getElementById("new-microprojet-btn").addEventListener("click", () => mpDialog.showModal());
document.getElementById("mp-cancel").addEventListener("click", () => mpDialog.close());
document.getElementById("microprojet-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const p = await api.post("/api/microprojets", {
      name: document.getElementById("mp-name").value,
      description: document.getElementById("mp-description").value,
      management_area_slug: slug,
    });
    window.location.href = `/microprojets/${encodeURIComponent(p.slug)}`;
  } catch (err) {
    mpDialog.close();
    showError(err);
  }
});

// --- éditer / supprimer le thème ---
const eaDialog = document.getElementById("edit-area-dialog");
document.getElementById("edit-area-btn").addEventListener("click", () => {
  document.getElementById("ea-name").value = current.name;
  document.getElementById("ea-description").value = current.description || "";
  document.getElementById("ea-strategy").value = current.strategy || "";
  eaDialog.showModal();
});
document.getElementById("ea-cancel").addEventListener("click", () => eaDialog.close());
document.getElementById("edit-area-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    render(
      await api.put(`/api/management/${encodeURIComponent(slug)}`, {
        name: document.getElementById("ea-name").value,
        description: document.getElementById("ea-description").value,
        strategy: document.getElementById("ea-strategy").value,
      })
    );
    eaDialog.close();
    flash("Thème mis à jour.");
  } catch (err) {
    eaDialog.close();
    showError(err);
  }
});
document.getElementById("ea-delete").addEventListener("click", async () => {
  if (!window.confirm(`Supprimer le thème « ${current.name} » ? Ses µprojets repassent en « Non classé ».`)) return;
  try {
    await api.del(`/api/management/${encodeURIComponent(slug)}`);
    window.location.href = "/";
  } catch (err) {
    eaDialog.close();
    showError(err);
  }
});

// --- rattacher un µprojet existant ---
const attachDialog = document.getElementById("attach-dialog");
document.getElementById("attach-microprojet-btn").addEventListener("click", async () => {
  try {
    const all = await api.get("/api/microprojets/tous");
    const others = all.filter((p) => !p.management_area || p.management_area.slug !== slug);
    const select = document.getElementById("attach-select");
    select.innerHTML = others.length
      ? others
          .map(
            (p) =>
              `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}${p.management_area ? ` — ${escapeHtml(p.management_area.name)}` : ""}</option>`
          )
          .join("")
      : `<option value="">Aucun autre µprojet</option>`;
    attachDialog.showModal();
  } catch (err) {
    showError(err);
  }
});
document.getElementById("attach-cancel").addEventListener("click", () => attachDialog.close());
document.getElementById("attach-confirm").addEventListener("click", async () => {
  const projectSlug = document.getElementById("attach-select").value;
  if (!projectSlug) return attachDialog.close();
  try {
    render(await api.post(`/api/management/${encodeURIComponent(slug)}/microprojets`, { project_slug: projectSlug }));
    attachDialog.close();
    flash("µprojet rattaché.");
  } catch (err) {
    attachDialog.close();
    showError(err);
  }
});

load();
