/* Page « KPI suivis » d'un µprojet (spectre.plugins.kpi_tracking) : l'onglet « Distributions » trace, pour
   chaque KPI suivi, une boîte à moustaches par plaque que ses études suivent (colorées par étude) ;
   l'onglet « Configuration » choisit les KPI parmi ceux que PRISM propose. Les distributions se
   calculent à la première ouverture de l'onglet, pas avant - une base PRISM lente ne retarde pas la
   configuration. */

const { slug } = routeParams("/microprojets/{slug}/kpi");
document.getElementById("crumb").textContent = "/ " + slug;
document.getElementById("microproject-link").href = `/microprojets/${slug}`;

const SOURCE_LABELS = { prism: "Données PRISM", demo: "Données de démonstration", mixed: "Sources mêlées" };

let canEdit = false;
let tracked = [];
let distributionsLoaded = false;
let activeTab = "distributions";

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

function setTab(name) {
  activeTab = name;
  for (const tab of document.querySelectorAll(".tab")) {
    const on = tab.dataset.tab === name;
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", String(on));
  }
  document.getElementById("panel-distributions").style.display = name === "distributions" ? "" : "none";
  document.getElementById("panel-configuration").style.display = name === "configuration" ? "" : "none";
  document.getElementById("kt-refresh").style.display = name === "distributions" && canEdit && tracked.length ? "" : "none";
  history.replaceState(null, "", name === "configuration" ? "#configuration" : location.pathname);
  if (name === "distributions" && !distributionsLoaded) loadDistributions();
}

/* -- distributions ------------------------------------------------------------------------ */

function studyColors(wafers) {
  // une couleur par étude (la première qui suit la plaque) - la même pour tous les KPI de la page
  const colors = new Map();
  for (const wafer of wafers) {
    const first = wafer.studies[0];
    if (first && !colors.has(first.experiment_id)) colors.set(first.experiment_id, { title: first.title, color: kpiBoxplotColor(colors.size) });
  }
  return colors;
}

function renderBoxCard(kpi, colors) {
  const head = `<div class="kt-box__head">
      <div><span class="kt-box__title">${escapeHtml(kpi.title)}</span>${kpi.unit ? `<span class="kt-box__unit">${escapeHtml(kpi.unit)}</span>` : ""}</div>
      <span class="kt-box__meta">${escapeHtml(kpi.hook_title)} · ${escapeHtml(kpi.column)}</span>
    </div>${kpi.description ? `<p class="kt-box__desc">${escapeHtml(kpi.description)}</p>` : ""}`;
  if (kpi.status !== "ok") {
    return `<div class="card card-pad kt-box">${head}<div class="kt-box__error">${escapeHtml(kpi.message || "Calcul impossible.")}</div></div>`;
  }
  const svg = kpiBoxplotSvg(kpi.groups, {
    label: `${kpi.title} : une boîte à moustaches par plaque`,
    colorOf: (group) => (colors.get(group.studies[0] && group.studies[0].experiment_id) || { color: kpiBoxplotColor(0) }).color,
  });
  const body = svg
    ? `<div class="kt-box__plot">${svg}</div>`
    : `<p class="help">${kpi.groups.length ? "Aucune mesure de ce KPI sur les plaques suivies pour l'instant." : "Aucune plaque suivie par les études de ce µprojet."}</p>`;
  return `<div class="card card-pad kt-box">${head}${body}</div>`;
}

function renderLegend(colors) {
  if (colors.size < 2) return "";
  return `<div class="kt-legend" aria-label="Couleur par étude">${[...colors.values()]
    .map((c) => `<span class="kt-legend__item" style="color:${c.color}"><span class="kt-legend__swatch"></span><span style="color:var(--text-soft)">${escapeHtml(c.title)}</span></span>`)
    .join("")}</div>`;
}

function renderDistributions(result) {
  const box = document.getElementById("kt-boxes");
  const source = document.getElementById("kt-source");
  source.style.display = result.source ? "" : "none";
  source.textContent = SOURCE_LABELS[result.source] || "";
  if (!result.kpis.length) {
    box.innerHTML = `<div class="card"><div class="empty-state">
        <p>Ce µprojet ne suit aucun KPI. Choisissez-les dans l'onglet « Configuration ».</p>
        <button class="btn btn-primary" type="button" id="kt-go-config">Choisir les KPI</button>
      </div></div>`;
    document.getElementById("kt-go-config").addEventListener("click", () => setTab("configuration"));
    return;
  }
  const colors = studyColors(result.wafers);
  const summary = `<p class="kt-box__meta" style="margin-bottom:12px;">${result.wafers.length} plaque${result.wafers.length > 1 ? "s" : ""} suivie${result.wafers.length > 1 ? "s" : ""} · une boîte par plaque, sur toutes ses mesures</p>`;
  box.innerHTML = summary + renderLegend(colors) + result.kpis.map((k) => renderBoxCard(k, colors)).join("");
}

async function loadDistributions({ refresh = false } = {}) {
  clearError();
  const box = document.getElementById("kt-boxes");
  box.innerHTML = '<div class="skeleton" style="height:260px;width:100%;"></div>';
  try {
    renderDistributions(await kpiTrackingApi.distributions(slug, { refresh }));
    distributionsLoaded = true;
  } catch (err) {
    box.innerHTML = "";
    showError(err);
  }
}

document.getElementById("kt-refresh").addEventListener("click", () => loadDistributions({ refresh: true }));
for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => setTab(tab.dataset.tab));

(async function init() {
  try {
    const [microproject, trackedList, catalogList] = await Promise.all([
      microprojectsApi.get(slug),
      kpiTrackingApi.list(slug),
      kpiTrackingApi.catalog(slug),
    ]);
    canEdit = !!microproject.can_edit;
    tracked = trackedList;
    document.getElementById("crumb").textContent = "/ " + microproject.name;
    mountKpiConfig({
      slug,
      canEdit,
      catalog: catalogList,
      tracked,
      trackedEl: document.getElementById("kt-tracked"),
      catalogEl: document.getElementById("kt-catalog"),
      showError,
      clearError,
      onChange(list) {
        tracked = list;
        distributionsLoaded = false; // le choix a changé : les boîtes sont à refaire
      },
    });
    setTab(location.hash === "#configuration" ? "configuration" : "distributions");
  } catch (err) {
    document.getElementById("kt-boxes").innerHTML = "";
    showError(err);
  }
})();
