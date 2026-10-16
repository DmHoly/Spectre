/* Page « Configuration des KPI » du menu Data (spectre.plugins.kpi_tracking) : on choisit un µprojet
   (gardé dans l'adresse, ?microprojet=) et on règle les KPI qu'il suit - la même configuration que
   l'onglet du µprojet (kpi-config.js). */

const selectEl = document.getElementById("kt-microproject");
const panels = document.getElementById("kt-panels");
const openLink = document.getElementById("kt-open");
let loadToken = 0; // une réponse tardive d'un µprojet quitté ne remplace pas le courant

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
  history.replaceState(null, "", slug ? `?microprojet=${encodeURIComponent(slug)}` : location.pathname);
  if (!slug) return;
  try {
    const [microproject, tracked, catalog] = await Promise.all([microprojectsApi.get(slug), kpiTrackingApi.list(slug), kpiTrackingApi.catalog(slug)]);
    if (token !== loadToken) return;
    const trackedEl = document.getElementById("kt-tracked");
    const catalogEl = document.getElementById("kt-catalog");
    // les écouteurs se posent sur de nouveaux éléments : le choix précédent ne reste pas branché
    for (const el of [trackedEl, catalogEl]) el.replaceWith(el.cloneNode(false));
    mountKpiConfig({
      slug,
      canEdit: !!microproject.can_edit,
      catalog,
      tracked,
      trackedEl: document.getElementById("kt-tracked"),
      catalogEl: document.getElementById("kt-catalog"),
      showError,
      clearError,
      onChange() {},
    });
    document.getElementById("kt-readonly").style.display = microproject.can_edit ? "none" : "";
    openLink.href = `/microprojets/${encodeURIComponent(slug)}/kpi`;
    openLink.style.display = "";
    panels.style.display = "";
  } catch (err) {
    if (token === loadToken) showError(err);
  }
}

selectEl.addEventListener("change", () => show(selectEl.value));

(async function init() {
  try {
    const microprojects = await microprojectsApi.list({ scope: "readable" });
    microprojects.sort((a, b) => a.name.localeCompare(b.name, "fr"));
    if (!microprojects.length) {
      selectEl.innerHTML = "<option>Aucun µprojet</option>";
      return;
    }
    selectEl.innerHTML = '<option value="">Choisir un µprojet…</option>' + microprojects.map((m) => `<option value="${escapeHtml(m.slug)}">${escapeHtml(m.code ? `${m.code} · ${m.name}` : m.name)}</option>`).join("");
    selectEl.disabled = false;
    const wanted = new URLSearchParams(location.search).get("microprojet");
    if (wanted && microprojects.some((m) => m.slug === wanted)) {
      selectEl.value = wanted;
      show(wanted);
    }
  } catch (err) {
    selectEl.innerHTML = "<option>—</option>";
    showError(err);
  }
})();
