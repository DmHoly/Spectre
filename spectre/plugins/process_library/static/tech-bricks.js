/* Page dédiée aux briques technologiques : liste (intégrées / partagées / µprojet) uniquement -
   la composition elle-même se fait dans le constructeur de structure, en "mode brique" (voir
   structures/static/builder/brick-mode.js), pas ici. */

const { slug } = routeParams("/microprojets/{slug}/briques-technologiques");

const state = {
  bricks: [],
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
  if (scope === "builtin") return `<span style="font-weight:400;font-size:11px;color:var(--text-faint);">· intégrée, disponible dans tous les µprojets</span>`;
  if (scope === "shared") return `<span style="font-weight:400;font-size:11px;color:var(--text-faint);">· partagée, visible dans tous les µprojets</span>`;
  return "";
}

function brickRow(brick) {
  const canCreate = state.currentRole === "editor" || state.currentRole === "owner";
  const editHref = `/microprojets/${encodeURIComponent(slug)}/briques-technologiques/bibliotheque/${encodeURIComponent(brick.id)}`;
  return `
    <div class="step-row" style="align-items:flex-start;">
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${escapeHtml(brick.name)} ${scopeSuffix(brick.scope)}</div>
        <div style="font-size:12px;color:var(--text-faint);">${brick.steps.length} étape(s)</div>
        ${brick.notes ? `<div style="font-size:12px;color:var(--text-soft);margin-top:3px;max-width:56ch;">${escapeHtml(brick.notes)}</div>` : ""}
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;">
        ${canCreate ? `<a class="btn btn-line" href="${editHref}?dupliquer=1" style="padding:5px 10px;font-size:12px;">Dupliquer</a>` : ""}
        ${brick.can_edit ? `<a class="btn btn-line" href="${editHref}" style="padding:5px 10px;font-size:12px;">Modifier</a>` : ""}
        ${
          brick.can_edit
            ? `<button class="btn btn-line js-remove" data-id="${escapeHtml(brick.id)}" type="button" style="padding:5px 10px;font-size:12px;color:var(--danger);">Supprimer</button>`
            : ""
        }
      </div>
    </div>`;
}

function confirmRemoval(brick) {
  const shared = brick.scope === "shared" ? " Elle est partagée : elle disparaîtra de tous les µprojets." : "";
  return window.confirm(`Supprimer la brique « ${brick.name} » ?${shared}`);
}

function renderList() {
  document.getElementById("bricks-list").innerHTML = state.bricks.length
    ? state.bricks.map(brickRow).join("")
    : `<div class="help">Aucune brique pour l'instant.</div>`;

  document.querySelectorAll(".js-remove").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const brick = state.bricks.find((b) => b.id === btn.dataset.id);
      if (!brick || !confirmRemoval(brick)) return;
      try {
        await processLibraryApi.deleteTechBrick(brick.id);
        await loadBricks();
        showFlash("Brique supprimée.");
      } catch (err) {
        showError(err);
      }
    });
  });
}

async function loadBricks() {
  state.bricks = await processLibraryApi.techBricks({ microproject: slug });
  renderList();
}

async function init() {
  try {
    const microproject = await microprojectsApi.get(slug);
    state.currentRole = microproject.role;
    document.getElementById("crumb").textContent = "/ " + microproject.name;
    document.getElementById("back-link").href = "/bibliotheque";
    document.getElementById("new-brick-link").href = `/microprojets/${encodeURIComponent(slug)}/briques-technologiques/bibliotheque/nouvelle`;
    if (!(state.currentRole === "editor" || state.currentRole === "owner")) {
      document.getElementById("new-brick-link").style.display = "none";
    }
  } catch (err) {
    showError(err);
    return;
  }
  try {
    await loadBricks();
  } catch (err) {
    showError(err);
  }
}

init();
