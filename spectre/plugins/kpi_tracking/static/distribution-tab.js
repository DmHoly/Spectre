/* L'onglet d'un KPI suivi dans le bloc « Évolution des KPI » de la page d'un projet (kpis/static/kpi-trend.js :
   un KPI à `render`) : une boîte à moustaches par plaque des µprojets du projet, colorées par µprojet.
   Les distributions de tous les KPI suivis viennent d'un seul appel, fait à la première ouverture d'un
   onglet puis gardé (un type PRISM lent ne se requête qu'une fois). */

const KpiDistributionTabs = (function () {
  const SOURCE_LABELS = { prism: "Données PRISM", demo: "Données de démonstration", mixed: "Sources mêlées" };

  // Les KPI suivis d'un projet, prêts pour KpiTrendBlock : [{key, label, render}].
  async function kpisFor(areaSlug) {
    const tracked = await kpiTrackingApi.list(areaSlug);
    let loading = null;
    const load = (refresh) => {
      if (refresh || !loading) {
        loading = kpiTrackingApi.distributions(areaSlug, { refresh }).catch((err) => {
          loading = null;
          throw err;
        });
      }
      return loading;
    };
    return tracked.map((k) => ({
      key: `tracked:${k.id}`,
      label: k.title,
      async render(panel) {
        const result = await load(false);
        const kpi = result.kpis.find((d) => d.id === k.id);
        panel.innerHTML = kpi ? cardHtml(kpi, result) : `<div class="error">Ce KPI n'est plus suivi.</div>`;
      },
    }));
  }

  function colorsOf(result) {
    // une couleur par µprojet (le premier qui suit la plaque) - la même pour tous les KPI
    const colors = new Map();
    for (const wafer of result.wafers) {
      const first = wafer.microprojects[0];
      if (first && !colors.has(first.slug)) colors.set(first.slug, { name: first.name, color: kpiBoxplotColor(colors.size) });
    }
    return colors;
  }

  function legendHtml(colors) {
    if (colors.size < 2) return "";
    return `<div class="kt-legend" aria-label="Couleur par µprojet">${[...colors.values()]
      .map((c) => `<span class="kt-legend__item" style="color:${c.color}"><span class="kt-legend__swatch"></span><span style="color:var(--text-soft)">${escapeHtml(c.name)}</span></span>`)
      .join("")}</div>`;
  }

  function cardHtml(kpi, result) {
    const colors = colorsOf(result);
    const wafers = result.wafers.length;
    const meta = `${escapeHtml(kpi.hook_title)} · ${escapeHtml(kpi.column)}`;
    const head = `<div class="kt-box__head">
        <div>${kpi.unit ? `<span class="kt-box__unit" style="margin-left:0;">${escapeHtml(kpi.unit)}</span>` : ""}</div>
        <span class="kt-box__meta">${meta}${result.source ? ` · ${escapeHtml(SOURCE_LABELS[result.source] || "")}` : ""}</span>
      </div>${kpi.description ? `<p class="kt-box__desc">${escapeHtml(kpi.description)}</p>` : ""}`;
    if (kpi.status !== "ok") return `${head}<div class="kt-box__error">${escapeHtml(kpi.message || "Calcul impossible.")}</div>`;
    const svg = kpiBoxplotSvg(kpi.groups, {
      label: `${kpi.title} : une boîte à moustaches par plaque`,
      colorOf: (group) => (colors.get(group.microprojects[0] && group.microprojects[0].slug) || { color: kpiBoxplotColor(0) }).color,
    });
    const body = svg
      ? `<div class="kt-box__plot">${svg}</div>`
      : `<p class="help">${wafers ? "Aucune mesure de ce KPI sur les plaques suivies pour l'instant." : "Aucune plaque suivie par les µprojets de ce projet."}</p>`;
    const count = `<p class="kt-box__meta" style="margin:8px 0 0;">${wafers} plaque${wafers > 1 ? "s" : ""} suivie${wafers > 1 ? "s" : ""} · une boîte par plaque, sur toutes ses mesures</p>`;
    return `${head}${legendHtml(colors)}${body}${count}`;
  }

  return { kpisFor };
})();
