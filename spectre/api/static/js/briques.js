/* Page dédiée aux briques technologiques : liste (préréglées / partagées / projet) uniquement -
   la composition elle-même se fait dans le constructeur de structure, en "mode brique" (voir
   structure-builder/brick-mode.js), pas ici. */

const pathParts = window.location.pathname.split("/").filter(Boolean);
const slug = pathParts[1];

const state = {
  bricks: { presets: [], partagees: [], projet: [] },
  currentRole: null,
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
  document.getElementById("flash").style.display = "none";
}
function showFlash(message) {
  const flashBox = document.getElementById("flash");
  flashBox.textContent = message;
  flashBox.style.display = "block";
  errorBox.style.display = "none";
}

function scopeSuffix(scope) {
  if (scope === "preset") return `<span style="font-weight:400;font-size:11px;color:var(--text-faint);">· préset, disponible dans tous les projets</span>`;
  if (scope === "partagee") return `<span style="font-weight:400;font-size:11px;color:var(--text-faint);">· partagée, visible dans tous les projets</span>`;
  return "";
}

function brickRow(brick) {
  const canManage = state.currentRole === "editor" || state.currentRole === "owner";
  const isPreset = brick.scope === "preset";
  const editHref = `/projets/${encodeURIComponent(slug)}/briques-technologiques/bibliotheque/${encodeURIComponent(brick.name)}?scope=${brick.scope}`;
  return `
    <div class="step-row" style="align-items:flex-start;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(brick.name)} ${scopeSuffix(brick.scope)}</div>
        <div style="font-size:12px;color:var(--text-faint);">${brick.steps.length} étape(s)</div>
        ${brick.notes ? `<div style="font-size:12px;color:var(--text-soft);margin-top:3px;max-width:56ch;">${escapeHtml(brick.notes)}</div>` : ""}
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">
        ${canManage ? `<a class="btn btn-line" href="${editHref}&dupliquer=1" style="padding:5px 10px;font-size:12px;">Dupliquer</a>` : ""}
        ${canManage && !isPreset ? `<a class="btn btn-line" href="${editHref}" style="padding:5px 10px;font-size:12px;">Modifier</a>` : ""}
        ${
          canManage && !isPreset
            ? `<button class="btn btn-line js-remove" data-name="${escapeHtml(brick.name)}" data-scope="${brick.scope}" type="button" style="padding:5px 10px;font-size:12px;color:var(--danger);">Supprimer</button>`
            : ""
        }
      </div>
    </div>`;
}

function renderList() {
  const entries = [
    ...state.bricks.presets.map((b) => ({ ...b, scope: "preset" })),
    ...state.bricks.partagees.map((b) => ({ ...b, scope: "partagee" })),
    ...state.bricks.projet.map((b) => ({ ...b, scope: "projet" })),
  ];
  document.getElementById("bricks-list").innerHTML = entries.length
    ? entries.map(brickRow).join("")
    : `<div class="help">Aucune brique pour l'instant.</div>`;

  document.querySelectorAll(".js-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        state.bricks = await api.del(
          `/api/projects/${encodeURIComponent(slug)}/briques-technologiques/${encodeURIComponent(btn.dataset.name)}?partagee=${btn.dataset.scope === "partagee"}`
        );
        renderList();
        showFlash("Brique supprimée.");
      } catch (err) {
        showError(err);
      }
    });
  });
}

async function init() {
  try {
    const project = await api.get(`/api/projects/${encodeURIComponent(slug)}`);
    state.currentRole = project.role;
    document.getElementById("crumb").textContent = "/ " + project.name;
    document.getElementById("back-link").href = `/projets/${encodeURIComponent(slug)}`;
    document.getElementById("new-brick-link").href = `/projets/${encodeURIComponent(slug)}/briques-technologiques/bibliotheque/nouvelle`;
    if (!(state.currentRole === "editor" || state.currentRole === "owner")) {
      document.getElementById("new-brick-link").style.display = "none";
    }
  } catch (err) {
    showError(err);
    return;
  }
  try {
    state.bricks = await api.get(`/api/projects/${encodeURIComponent(slug)}/briques-technologiques`);
    renderList();
  } catch (err) {
    showError(err);
  }
}

init();
