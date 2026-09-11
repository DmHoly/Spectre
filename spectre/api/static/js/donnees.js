/* Page /donnees : sélectionner un hook (spectre/core/datahook), voir sa fiche (titre, description,
   paramètres attendus, post-traitements appliqués), lancer sa requête, afficher le résultat brut
   en tableau. Un paramètre de hook est toujours une liste (wafer_names...) - saisie ici comme du
   texte séparé par des virgules. */

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

let currentHooks = [];

function hookDetailsHtml(hook) {
  const paramsHtml = hook.parameters.length
    ? hook.parameters
        .map(
          (p) => `
      <div style="margin-top:8px;">
        <label style="font-size:11px;">${escapeHtml(p)}</label>
        <input class="field js-hook-param" data-param="${escapeHtml(p)}" placeholder="valeurs séparées par des virgules (ex: W12-A3, W12-A4)">
      </div>`
        )
        .join("")
    : `<div class="help" style="margin-top:8px;">Ce hook ne prend aucun paramètre.</div>`;

  const postHtml = hook.postprocessing.length
    ? `<div class="help" style="margin-top:8px;">Post-traitement : ${hook.postprocessing.map(escapeHtml).join(", ")}</div>`
    : "";

  return `
    <p style="font-size:13px;color:var(--text-soft);line-height:1.55;white-space:pre-line;">${escapeHtml(hook.description)}</p>
    ${postHtml}
    <form id="hook-run-form" style="margin-top:12px;">
      ${paramsHtml}
      <button class="btn btn-primary" type="submit" style="margin-top:12px;">Lancer la requête</button>
    </form>`;
}

function renderHookDetails(key) {
  const hook = currentHooks.find((h) => h.key === key);
  const box = document.getElementById("hook-details");
  document.getElementById("results-card").style.display = "none";
  if (!hook) {
    box.innerHTML = "";
    return;
  }
  box.innerHTML = hookDetailsHtml(hook);
  document.getElementById("hook-run-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const parameters = {};
    box.querySelectorAll(".js-hook-param").forEach((input) => {
      parameters[input.dataset.param] = input.value
        .split(",")
        .map((v) => v.trim())
        .filter((v) => v.length > 0);
    });
    const submitBtn = event.target.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Requête en cours…";
    try {
      const result = await api.post(`/api/donnees/hooks/${encodeURIComponent(key)}/executer`, { parameters });
      renderResults(result);
    } catch (err) {
      showError(err);
      document.getElementById("results-card").style.display = "none";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Lancer la requête";
    }
  });
}

function cellText(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return `[${value.length} valeurs]`;
  return String(value);
}

function renderResults(result) {
  document.getElementById("results-card").style.display = "";
  document.getElementById("results-summary").textContent =
    result.row_count === 0 ? "Aucune ligne renvoyée." : `${result.row_count} ligne${result.row_count > 1 ? "s" : ""}.`;

  const table = document.getElementById("donnees-table");
  if (result.row_count === 0) {
    table.innerHTML = "";
    return;
  }
  const head = `<thead><tr>${result.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  // Un tableau de résultat brut peut être long - on ne montre que les 200 premières lignes pour
  // rester réactif, le total exact étant de toute façon déjà annoncé au-dessus.
  const body = `<tbody>${result.rows
    .slice(0, 200)
    .map((row) => `<tr>${row.map((v) => `<td>${escapeHtml(cellText(v))}</td>`).join("")}</tr>`)
    .join("")}</tbody>`;
  table.innerHTML = head + body;
}

async function init() {
  try {
    const body = await api.get("/api/donnees/hooks");
    currentHooks = body.hooks;
  } catch (err) {
    showError(err);
    return;
  }
  const select = document.getElementById("hook-select");
  select.innerHTML = currentHooks.map((h) => `<option value="${escapeHtml(h.key)}">${escapeHtml(h.title)}</option>`).join("");
  select.addEventListener("change", () => renderHookDetails(select.value));
  if (currentHooks.length) renderHookDetails(select.value);
}

init();
