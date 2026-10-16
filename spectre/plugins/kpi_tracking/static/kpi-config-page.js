/* Page « Configuration des KPI » du menu Data (spectre.plugins.kpi_tracking) : on choisit un projet corporate
   (gardé dans l'adresse, ?projet=) et on règle les KPI qu'il suit (kpi-config.js). Ses µprojets les
   partagent : leurs plaques se remontent toutes dans le bloc « Évolution des KPI » de la page du projet. */

const selectEl = document.getElementById("kt-area");
const panels = document.getElementById("kt-panels");
const openLink = document.getElementById("kt-open");
let loadToken = 0; // une réponse tardive d'un projet quitté ne remplace pas le courant
const manageable = new Map(); // slug -> peut gérer le projet

function clearError() {
  const box = document.getElementById("error");
  box.style.display = "none";
  box.textContent = "";
}

function showError(err) {
  const box = document.getElementById("error");
  box.textContent = err && err.message ? err.message : String(err);
  box.style.display = "block";
}

async function show(slug) {
  const token = ++loadToken;
  clearError();
  panels.style.display = "none";
  openLink.style.display = "none";
  history.replaceState(null, "", slug ? `?projet=${encodeURIComponent(slug)}` : location.pathname);
  if (!slug) return;
  try {
    const [tracked, catalog] = await Promise.all([kpiTrackingApi.list(slug), kpiTrackingApi.catalog(slug)]);
    if (token !== loadToken) return;
    // les écouteurs se posent sur de nouveaux éléments : le choix précédent ne reste pas branché
    for (const id of ["kt-tracked", "kt-catalog"]) {
      const el = document.getElementById(id);
      el.replaceWith(el.cloneNode(false));
    }
    const canEdit = !!manageable.get(slug);
    mountKpiConfig({
      slug,
      canEdit,
      catalog,
      tracked,
      trackedEl: document.getElementById("kt-tracked"),
      catalogEl: document.getElementById("kt-catalog"),
      showError,
      clearError,
      onChange() {},
    });
    document.getElementById("kt-readonly").style.display = canEdit ? "none" : "";
    openLink.href = `/management/${encodeURIComponent(slug)}`;
    openLink.style.display = "";
    panels.style.display = "";
  } catch (err) {
    if (token === loadToken) showError(err);
  }
}

selectEl.addEventListener("change", () => show(selectEl.value));

(async function init() {
  try {
    const areas = (await areasApi.list()).filter((a) => !a.is_system);
    areas.sort((a, b) => a.name.localeCompare(b.name, "fr"));
    areas.forEach((a) => manageable.set(a.slug, a.can_manage));
    if (!areas.length) {
      selectEl.innerHTML = "<option>Aucun projet</option>";
      return;
    }
    selectEl.innerHTML = '<option value="">Choisir un projet…</option>' + areas.map((a) => `<option value="${escapeHtml(a.slug)}">${escapeHtml(a.name)}</option>`).join("");
    selectEl.disabled = false;
    const wanted = new URLSearchParams(location.search).get("projet");
    if (wanted && manageable.has(wanted)) {
      selectEl.value = wanted;
      show(wanted);
    }
  } catch (err) {
    selectEl.innerHTML = "<option>—</option>";
    showError(err);
  }
})();
