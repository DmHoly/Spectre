/* « Promouvoir comme référence », partout (global `PromotionLink`) : le même bouton, qui ouvre le
   formulaire de la promotion (/promotion) déjà rempli - depuis la fiche d'une étude, une variante
   d'un split, la conclusion, la page d'évolution d'un µprojet, la liste et la page d'une référence.
   Aucune condition pour le montrer : ce que la structure permet ou non, le formulaire le dit (ses
   règles). Les pages qui l'utilisent chargent aussi /static/promotion/promotion.css.

     PromotionLink.url({microproject, experimentId, versionId, variant, reference, back})
     PromotionLink.html(target, {label, compact, title})  - un <a class="btn promote-btn"> */

const PromotionLink = (() => {
  const ICON = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4Z"/><path d="m9.5 10 2 2 3.5-3.5"/></svg>';

  function url(target = {}) {
    const params = new URLSearchParams();
    if (target.microproject) params.set("microprojet", target.microproject);
    if (target.experimentId) params.set("etude", target.experimentId);
    if (target.versionId) params.set("version", target.versionId);
    if (target.variant !== undefined && target.variant !== null) params.set("variante", String(target.variant));
    if (target.reference) params.set("reference", target.reference);
    params.set("retour", target.back || window.location.pathname + window.location.search + window.location.hash);
    return `/promotion?${params.toString()}`;
  }

  function html(target, options = {}) {
    const label = options.label || "Promouvoir comme référence";
    const title = options.title || "Choisir cette structure comme référence (nouvelle référence ou nouvelle version) : le formulaire de la promotion";
    return `<a class="btn promote-btn${options.compact ? " promote-btn--compact" : ""}" href="${escapeHtml(url(target))}" title="${escapeHtml(title)}">${ICON}<span>${escapeHtml(label)}</span></a>`;
  }

  return { url, html, ICON };
})();
