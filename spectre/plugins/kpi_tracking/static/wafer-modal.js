/* Le récapitulatif d'une plaque, au clic sur sa boîte à moustaches (global `KpiWaferModal`) : ce que dit sa fiche
   (/plaques/{lasermark}) - son nom de run, son lot, ses FDL, ses µprojets, la structure qu'elle a vue, pourquoi elle
   est là (contexte, intention, hypothèse, objectifs, conclusion : `PlateContext`), et les études qui la suivent -
   avec, en tête, ce que la boîte cliquée dit du KPI (le jour de mesure, les quartiles).

     KpiWaferModal.open({ group, kpi })     // group : {wafer, date, stats, ...} d'une distribution

   Dépend de wafersApi, experimentsApi, PlateContext (wafers/static/plate-context.js), statusBadgeHtml
   (experiments/status.js), kpiFormatNumber (boxplot.js), escapeHtml et formatDate (kernel/ui.js). */

const KpiWaferModal = (function () {
  let dialog = null;
  let token = 0; // une réponse tardive d'une plaque quittée ne remplace pas la courante

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "kt-modal";
    dialog.setAttribute("aria-labelledby", "kt-modal-title");
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close(); // un clic sur le voile
    });
    document.body.appendChild(dialog);
    return dialog;
  }

  function chips(values, mono = true) {
    return values.length
      ? values.map((v) => `<span class="kt-modal__chip${mono ? " mono" : ""}">${escapeHtml(v)}</span>`).join(" ")
      : '<span class="kt-modal__none">—</span>';
  }

  function statsHtml(group, kpi) {
    const s = group.stats;
    if (!s) return `<p class="help">Aucune mesure de ce KPI pour cette plaque${group.date ? ` le ${escapeHtml(group.date)}` : ""}.</p>`;
    const cell = (label, value) => `<div class="kt-modal__stat"><div class="kt-modal__stat-value">${escapeHtml(kpiFormatNumber(value))}</div><div class="kt-modal__stat-label">${escapeHtml(label)}</div></div>`;
    return `<div class="kt-modal__stats">
      <div class="kt-modal__stat"><div class="kt-modal__stat-value">${s.n}</div><div class="kt-modal__stat-label">lignes</div></div>
      ${cell("min", s.minimum)}${cell("Q1", s.q1)}${cell("médiane", s.median)}${cell("Q3", s.q3)}${cell("max", s.maximum)}${cell("moyenne", s.mean)}
    </div>${kpi.unit ? `<p class="kt-modal__unit">en ${escapeHtml(kpi.unit)}</p>` : ""}`;
  }

  async function structureHtml(plate) {
    const latest = plate.occurrences.find((o) => o.experiment.member && o.experiment.version_id);
    if (latest) {
      try {
        const detail = await experimentsApi.getVersion(latest.experiment.microproject.slug, latest.experiment.id, latest.experiment.version_id);
        if (detail.structure_svg) return `<div class="kt-modal__structure">${detail.structure_svg}</div><p class="kt-modal__caption">Vue dans ${escapeHtml(latest.experiment.title)}</p>`;
        if (detail.structure_images && detail.structure_images.length) {
          return `<div class="kt-modal__structure"><img src="${escapeHtml(detail.structure_images[0].url)}" alt="${escapeHtml(detail.structure_images[0].caption || "Structure")}"></div>`;
        }
      } catch (err) {
        /* une étude illisible : on retombe sur la structure attachée à la plaque, s'il y en a une */
      }
    }
    if (plate.structure && plate.structure.svg) return `<div class="kt-modal__structure">${plate.structure.svg}</div><p class="kt-modal__caption">${escapeHtml(plate.structure.label || "")}</p>`;
    return '<p class="help">Pas de structure définie pour cette plaque.</p>';
  }

  function studiesHtml(plate) {
    if (!plate.occurrences.length) return '<p class="help">Aucune étude ne suit cette plaque.</p>';
    return `<ul class="kt-modal__studies">${plate.occurrences
      .map((o) => {
        const exp = o.experiment;
        const mp = exp.microproject;
        const title = exp.member
          ? `<a href="/microprojets/${encodeURIComponent(mp.slug)}/experiences/${encodeURIComponent(exp.id)}">${escapeHtml(exp.title)}</a>`
          : `<span class="help">Étude d'un µprojet dont vous n'êtes pas membre</span>`;
        return `<li>${statusBadgeHtml(exp.status)} ${title}
          <span class="kt-modal__study-meta"><a class="fiche-code" href="/microprojets/${encodeURIComponent(mp.slug)}" title="${escapeHtml(mp.name)}">${escapeHtml(mp.code || mp.name)}</a>${o.variant ? ` · variante <span class="mono">${escapeHtml(o.variant)}</span>` : ""} · mise à jour le ${escapeHtml(formatDate(exp.updated_at))}</span></li>`;
      })
      .join("")}</ul>`;
  }

  async function open({ group, kpi }) {
    const dlg = ensureDialog();
    const mine = ++token;
    const when = group.date ? ` · mesurée le ${group.date}` : "";
    dlg.innerHTML = `<div class="kt-modal__head">
        <div><div class="section-title">Récapitulatif de la plaque</div><h2 id="kt-modal-title" class="kt-modal__title mono">${escapeHtml(group.wafer)}</h2>
        <p class="kt-modal__sub">${escapeHtml(kpi.title)}${escapeHtml(when)}</p></div>
        <button type="button" class="btn btn-line kt-modal__close" aria-label="Fermer">Fermer</button>
      </div>
      <div class="kt-modal__body">${statsHtml(group, kpi)}<div class="skeleton" style="height:140px;margin-top:14px;"></div></div>`;
    dlg.querySelector(".kt-modal__close").addEventListener("click", () => dlg.close());
    if (!dlg.open) dlg.showModal();
    const body = dlg.querySelector(".kt-modal__body");
    try {
      const plate = await wafersApi.get(group.wafer);
      const structure = await structureHtml(plate);
      if (mine !== token) return;
      const line = (label, html) => `<div class="kt-modal__line"><div class="plate-detail__label">${escapeHtml(label)}</div><div>${html}</div></div>`;
      const fdl = [...new Set([...(plate.fdl || []), ...(plate.line_fdl || [])])];
      body.innerHTML = `${statsHtml(group, kpi)}
        <section class="kt-modal__section">
          ${line("Run d'épitaxie", chips(plate.run_names || []))}
          ${line("Lot", chips(plate.lot_name ? [plate.lot_name] : []))}
          ${line("FDL", chips(fdl))}
          ${line("Rattachée à", plate.microprojects.length ? plate.microprojects.map((m) => `<a class="fiche-code" href="/microprojets/${encodeURIComponent(m.slug)}" title="${escapeHtml(m.name)}">${escapeHtml(m.code || m.name)}</a>`).join(" ") : '<span class="kt-modal__none">—</span>')}
          ${plate.last_location ? line("Emplacement", escapeHtml(plate.last_location)) : ""}
        </section>
        <section class="kt-modal__section"><h3 class="section-title">Structure</h3>${structure}</section>
        <section class="kt-modal__section"><h3 class="section-title">Pourquoi elle est là, ce qu'on a compris</h3>
          <div class="plate-context"><div class="plate-context__list js-context-list"></div></div></section>
        <section class="kt-modal__section"><h3 class="section-title">Études qui la suivent</h3>${studiesHtml(plate)}</section>
        <p class="kt-modal__foot"><a class="btn btn-primary" href="/plaques/${encodeURIComponent(plate.lasermark)}">Ouvrir la fiche complète</a></p>`;
      PlateContext.render(body.querySelector(".plate-context"), plate);
    } catch (err) {
      if (mine === token) body.innerHTML = `${statsHtml(group, kpi)}<div class="error" style="margin-top:14px;">${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  return { open };
})();
