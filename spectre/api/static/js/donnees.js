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

  // Le cache disque (voir spectre/core/datahook/cache.py) ne s'applique qu'aux hooks qui
  // déclarent cache_key_column ET prennent wafer_names - offrir la case sinon ("forcer le
  // rafraîchissement") n'aurait aucun effet et laisserait croire que ce hook est mis en cache.
  const cacheHtml = hook.cacheable
    ? `<label style="display:flex;align-items:center;gap:6px;margin-top:10px;font-size:12.5px;font-weight:400;">
         <input type="checkbox" id="hook-refresh-checkbox"> Forcer le rafraîchissement (ignorer le cache)
       </label>`
    : "";

  return `
    <p style="font-size:13px;color:var(--text-soft);line-height:1.55;white-space:pre-line;">${escapeHtml(hook.description)}</p>
    ${postHtml}
    <form id="hook-run-form" style="margin-top:12px;">
      ${paramsHtml}
      ${cacheHtml}
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
    const refreshCheckbox = document.getElementById("hook-refresh-checkbox");
    const refresh = refreshCheckbox ? refreshCheckbox.checked : false;
    const submitBtn = event.target.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Requête en cours…";
    try {
      const result = await api.post(`/api/donnees/hooks/${encodeURIComponent(key)}/executer`, { parameters, refresh });
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
  const countLabel = result.row_count === 0 ? "Aucune ligne renvoyée." : `${result.row_count} ligne${result.row_count > 1 ? "s" : ""}.`;
  // from_cache/fetched n'existent que pour un hook cacheable (voir _hook_summary côté API) - absents
  // pour les autres, où la distinction cache/base n'a pas de sens.
  const cacheLabel =
    result.from_cache !== undefined
      ? ` (${result.from_cache.length} wafer${result.from_cache.length > 1 ? "s" : ""} en cache, ${result.fetched.length} requêté${result.fetched.length > 1 ? "s" : ""})`
      : "";
  document.getElementById("results-summary").textContent = countLabel + cacheLabel;

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
