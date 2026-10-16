/* L'onglet d'un KPI suivi dans le bloc « Évolution des KPI » de la page d'un projet (kpis/static/kpi-trend.js :
   un KPI à `render`) : une boîte à moustaches par plaque des µprojets du projet (et par date de mesure),
   colorées par µprojet, dans l'ordre du temps, sous une fenêtre de temps (time-window.js) qui ne garde que les
   boîtes de la période choisie - par défaut le dernier mois des données, « Tout » pour tout l'historique. La
   fenêtre est la même pour tous les onglets du projet.

   Les distributions de tous les KPI suivis viennent d'un seul appel, fait à la première ouverture d'un
   onglet puis gardé (un type PRISM lent ne se requête qu'une fois). */

const KpiDistributionTabs = (function () {
  const SOURCE_LABELS = { prism: "Données PRISM", demo: "Données de démonstration", mixed: "Sources mêlées" };

  // Les KPI suivis d'un projet, prêts pour KpiTrendBlock : [{key, label, render}].
  async function kpisFor(areaSlug) {
    const tracked = await kpiTrackingApi.list(areaSlug);
    let loading = null;
    let timeline = null; // {min, max, from, to} : l'étendue des boîtes de tous les KPI et la fenêtre choisie
    const load = (refresh) => {
      if (refresh || !loading) {
        loading = kpiTrackingApi
          .distributions(areaSlug, { refresh })
          .then((result) => {
            timeline = timelineOf(result, timeline);
            return result;
          })
          .catch((err) => {
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
        if (!kpi) {
          panel.innerHTML = `<div class="error">Ce KPI n'est plus suivi.</div>`;
          return;
        }
        draw(panel, kpi, result, timeline);
        // un clic (ou Entrée) sur une boîte ouvre le récapitulatif de sa plaque
        const openGroup = (event) => {
          const best = event.target.closest("[data-open-best]");
          const target = best || event.target.closest("[data-group]");
          const group = kpi.groups[best ? kpi.best : target && target.dataset.group];
          if (group) KpiWaferModal.open({ group, kpi });
        };
        panel.onclick = openGroup;
        panel.onkeydown = (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openGroup(event);
          }
        };
      },
    }));
  }

  // L'axe du temps du projet : de la première à la dernière boîte, tous KPI confondus. La fenêtre choisie est
  // gardée d'un onglet à l'autre ; la première fois, c'est le dernier mois des données.
  function timelineOf(result, previous) {
    const days = result.kpis.flatMap((d) => d.groups.map((g) => g.sort_date)).filter(Boolean).map(KpiTimeWindow.dayMs);
    if (!days.length) return null;
    const min = Math.min(...days);
    const max = Math.max(...days);
    if (min === max) return null;
    if (previous && previous.min === min && previous.max === max) return previous;
    return { min, max, ...KpiTimeWindow.defaultWindow(min, max, days) };
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

  function inWindow(group, timeline) {
    if (!timeline || !group.sort_date) return true;
    const t = KpiTimeWindow.dayMs(group.sort_date);
    return t >= timeline.from && t <= timeline.to;
  }

  // La carte d'un KPI : l'en-tête, la fenêtre de temps, puis le dessin (`.kt-plot-slot`) qui se refait seul quand
  // la fenêtre bouge - la fenêtre, elle, n'est pas redessinée pendant qu'on la glisse.
  function draw(panel, kpi, result, timeline) {
    const colors = colorsOf(result);
    const head = `<div class="kt-box__head">
        <div>${kpi.unit ? `<span class="kt-box__unit" style="margin-left:0;">${escapeHtml(kpi.unit)}</span>` : ""}</div>
        <span class="kt-box__meta">${escapeHtml(kpi.hook_title)} · ${escapeHtml(kpi.column)}${result.source ? ` · ${escapeHtml(SOURCE_LABELS[result.source] || "")}` : ""}</span>
      </div>${kpi.description ? `<p class="kt-box__desc">${escapeHtml(kpi.description)}</p>` : ""}`;
    const filters = kpi.summary ? `<p class="kt-filters-line">Filtres : ${escapeHtml(kpi.summary)}</p>` : "";
    if (kpi.status !== "ok") {
      panel.innerHTML = `${head}${filters}<div class="kt-box__error">${escapeHtml(kpi.message || "Calcul impossible.")}</div>`;
      return;
    }
    const best = kpi.best === null || kpi.best === undefined ? null : kpi.groups[kpi.best];
    panel.innerHTML = `${head}${filters}${legendHtml(colors)}
      <div class="kt-box__layout${best ? "" : " kt-box__layout--solo"}">
        <div class="kt-box__main"><div class="kt-window-slot"></div><div class="kt-plot-slot"></div></div>
        ${best ? `<aside class="kt-best" aria-label="Meilleure plaque"></aside>` : ""}
      </div>`;
    const slot = panel.querySelector(".kt-plot-slot");
    if (best) drawBest(panel.querySelector(".kt-best"), kpi, best, colors, timeline);
    const drawPlot = () => {
      const shown = kpi.groups.map((g, index) => ({ ...g, index })).filter((g) => inWindow(g, timeline));
      const svg = kpiBoxplotSvg(shown, {
        label: `${kpi.title} : une boîte à moustaches par plaque, dans l'ordre du temps`,
        best: kpi.best,
        goal: kpi.goal,
        colorOf: (group) => (colors.get(group.microprojects[0] && group.microprojects[0].slug) || { color: kpiBoxplotColor(0) }).color,
      });
      const wafers = result.wafers.length;
      let body;
      if (svg) body = `<div class="kt-box__plot">${svg}</div>`;
      else if (!wafers) body = `<p class="help">Aucune plaque suivie par les µprojets de ce projet.</p>`;
      else if (shown.length < kpi.groups.length) body = `<p class="help">Aucune boîte dans cette fenêtre : élargissez-la, ou « Tout ».</p>`;
      else body = `<p class="help">Aucune mesure de ce KPI sur les plaques suivies pour l'instant.</p>`;
      const undated = shown.filter((g) => g.stats && !g.dated).length;
      slot.innerHTML = `${body}<p class="kt-box__meta" style="margin:8px 0 0;">${shown.length} boîte${shown.length > 1 ? "s" : ""}${
        shown.length < kpi.groups.length ? ` sur ${kpi.groups.length}` : ""
      } · une par plaque (et par date de mesure), dans l'ordre du temps${undated ? ` · ${undated} placée${undated > 1 ? "s" : ""} à la date où une étude a commencé à suivre la plaque (pas de date de mesure)` : ""}</p>`;
    };
    if (timeline) {
      const days = kpi.groups.map((g) => g.sort_date).filter(Boolean).map(KpiTimeWindow.dayMs);
      KpiTimeWindow.mount(panel.querySelector(".kt-window-slot"), {
        min: timeline.min,
        max: timeline.max,
        from: timeline.from,
        to: timeline.to,
        days,
        onChange(from, to) {
          timeline.from = from;
          timeline.to = to;
          drawPlot();
          if (best) drawBest(panel.querySelector(".kt-best"), kpi, best, colors, timeline);
        },
      });
    }
    drawPlot();
  }

  // La meilleure plaque d'après l'objectif du KPI, épinglée à côté du graphique : toujours visible, hors de la fenêtre
  // de temps comprise (« meilleure de tous les temps »).
  function drawBest(aside, kpi, group, colors, timeline) {
    const s = group.stats;
    const color = (colors.get(group.microprojects[0] && group.microprojects[0].slug) || { color: kpiBoxplotColor(0) }).color;
    const svg = kpiBoxplotSvg([{ ...group, index: kpi.best }], { label: `Meilleure plaque : ${group.wafer}`, colorOf: () => color, goal: kpi.goal, best: kpi.best });
    const outside = timeline && !inWindow(group, timeline);
    aside.innerHTML = `<div class="kt-best__eyebrow">★ Meilleure plaque</div>
      <p class="kt-best__wafer">${escapeHtml(group.wafer)}</p>
      <p class="kt-best__date">${group.sort_date ? `${group.dated ? "mesurée le" : "suivie depuis le"} ${escapeHtml(KpiTimeWindow.fmt(KpiTimeWindow.dayMs(group.sort_date)))}` : ""}</p>
      <p class="kt-best__value">${escapeHtml(kpiFormatNumber(s.median))}<span class="kt-best__unit">${escapeHtml(kpi.unit || "")} (médiane)</span></p>
      <div class="kt-best__plot">${svg}</div>
      <p class="kt-best__quart">Q1 ${escapeHtml(kpiFormatNumber(s.q1))} · Q3 ${escapeHtml(kpiFormatNumber(s.q3))} · n ${s.n}</p>
      <p class="kt-best__goal">Objectif : ${escapeHtml(kpi.goal_summary)}</p>
      ${outside ? '<p class="kt-best__outside">Hors de la fenêtre de temps actuelle</p>' : ""}
      <p style="margin:10px 0 0;"><button type="button" class="btn btn-line" data-open-best>Voir sa fiche</button></p>`;
  }

  return { kpisFor };
})();
