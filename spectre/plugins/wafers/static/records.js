/* Les fiches de plaque, côté pages (globaux `WaferRecords`) : ce qu'une fiche dit d'une plaque en
   une ligne (sa source, ce que la base en disait le jour de la fiche : lot, produit, dernière
   étape), le découpage d'un texte collé en lasermarks, et le libellé d'une source. Partagé par
   l'index (wafer-index.js) et la page d'une plaque (wafer.js). Dépend d'escapeHtml et formatDate
   (kernel/ui.js). */

const WaferRecords = (() => {
  const SOURCE_LABELS = { prism: "la base de la ligne (PRISM)", demo: "la base de démonstration", manual: "saisie à la main, hors base" };

  function sourceLabel(source) {
    return SOURCE_LABELS[source] || source;
  }

  // « W12-A3, W12-A4 » / un par ligne / séparés par des espaces : les lasermarks, sans doublon
  // (comparés sans casse ni séparateurs, comme le serveur)
  function parseLasermarks(text) {
    const seen = new Set();
    const out = [];
    for (const raw of String(text || "").split(/[\s,;]+/)) {
      const value = raw.trim();
      const key = waferKey(value);
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(value);
    }
    return out;
  }

  // ce que la base dit d'une plaque, en une ligne : lot, produit, dernière étape (et quand)
  function summaryHtml(summary) {
    if (!summary) return "";
    const parts = [];
    if (summary.lot) parts.push(`lot <strong class="mono">${escapeHtml(summary.lot)}</strong>`);
    if (summary.product) parts.push(escapeHtml(summary.product));
    if (summary.last_step) parts.push(`dernière étape ${escapeHtml(summary.last_step)}${summary.last_movement ? ` (${escapeHtml(summary.last_movement.slice(0, 10))})` : ""}`);
    if (!parts.length && summary.wafer_name) parts.push(`fiche Gozer ${escapeHtml(summary.wafer_name)}`);
    if (summary.substrate) parts.push(escapeHtml(summary.substrate));
    return parts.join(" · ");
  }

  // la pastille « Fiche » d'une plaque enregistrée pour elle-même
  function chipHtml(record, { title = true } = {}) {
    const tip = title ? ` title="Fiche créée le ${escapeHtml(formatDate(record.created_at))} par ${escapeHtml(record.created_by)}, depuis ${escapeHtml(sourceLabel(record.source))}"` : "";
    return `<span class="wafer-record-chip"${tip}>Fiche</span>`;
  }

  return { sourceLabel, parseLasermarks, summaryHtml, chipHtml };
})();
