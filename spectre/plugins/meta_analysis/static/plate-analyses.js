/* Les analyses où paraît une plaque, sur sa page (global `PlateAnalyses`, plugin meta_analysis) : chacune, son rôle
   (référence ou comparée) et ses autres plaques, et « Nouvelle analyse » qui en part, cette plaque en référence.
   La page de la plaque (plugin wafers) le monte seulement si pluginEnabled("meta_analysis").

     PlateAnalyses.mount(host, plate) - host : la section, cachée tant que rien n'est rendu */

const PlateAnalyses = (() => {
  function itemHtml(analysis, key) {
    const isRef = analysis.reference && analysis.reference.key === key;
    const others = analysis.wafers.filter((w) => w.key !== key);
    return `
      <li class="ma-plate-item">
        <a class="ma-plate-item__title" href="/analyses/${encodeURIComponent(analysis.id)}">${escapeHtml(analysis.title)}</a>
        <span class="ma-plate-item__role${isRef ? " is-ref" : ""}">${isRef ? "Référence" : "Comparée"}</span>
        <span class="help" style="margin:0;">${
          others.length
            ? `avec ${others
                .slice(0, 6)
                .map((w) => `<span class="mono">${escapeHtml(w.lasermark)}</span>`)
                .join(", ")}${others.length > 6 ? ` et ${others.length - 6} autres` : ""}`
            : "seule pour l'instant"
        } · ${escapeHtml(formatDate(analysis.updated_at))}</span>
      </li>`;
  }

  async function mount(host, plate) {
    if (!host) return;
    let analyses = [];
    try {
      analyses = await metaAnalysisApi.list({ wafer: plate.lasermark });
    } catch (err) {
      return; // la page de la plaque se passe de ce bloc
    }
    const fresh = `/analyses?ref=${encodeURIComponent(plate.lasermark)}`;
    host.innerHTML = `
      <div class="plate-life__head">
        <h2 class="section-title" id="plate-analyses-title">Analyses où elle paraît</h2>
        <a class="btn btn-line" href="${fresh}" title="Une analyse qui compare d'autres plaques à celle-ci, prise comme référence">Nouvelle analyse avec elle en référence</a>
      </div>
      ${
        analyses.length
          ? `<ul class="ma-plate-list">${analyses.map((a) => itemHtml(a, plate.key)).join("")}</ul>`
          : `<p class="help" style="margin:0;">Aucune analyse ne la compare encore à d'autres plaques.</p>`
      }`;
    host.setAttribute("aria-labelledby", "plate-analyses-title");
    host.hidden = false;
  }

  return { mount };
})();
