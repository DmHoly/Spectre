/* Axe du temps partagé par les vues chronologiques (frise d'une thématique - thematique.js, Gantt des
   lots - lots-common.js) : graduations en français qui ne se chevauchent pas, et le motif hachuré
   de la zone « à venir ». Fonctions pures (aucun accès au DOM) ; l'échelle `x` est une échelle
   temporelle d3 (vendor/d3, chargé avant). */

function timelineAddMonths(date, months) {
  const d = new Date(date);
  d.setMonth(d.getMonth() + months);
  return d;
}

// « 12 mars » (graduations journalières) ou « mars » / « janv. 2027 » (mensuelles : l'année au
// premier repère et à chaque changement d'année).
function timelineTickLabel(date, previous, monthly) {
  if (!monthly) return date.toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
  const showYear = !previous || previous.getFullYear() !== date.getFullYear() || date.getMonth() === 0;
  return date.toLocaleDateString("fr-FR", showYear ? { month: "short", year: "numeric" } : { month: "short" });
}

// Parmi les dates candidates, celles qu'on gradue : au moins `minGap` px d'écart, jamais dans une
// zone `avoid` ([[x0, x1], ...] - là où s'écrit « Aujourd'hui »). `monthly` : booléen, ou fonction
// (date) -> booléen ; par défaut, mensuel si toutes les dates tombent un 1er du mois.
function timelineTicks(x, dates, { minGap = 62, avoid = [], monthly } = {}) {
  const allMonthly = dates.every((d) => d.getDate() === 1);
  const isMonthly = typeof monthly === "function" ? monthly : () => (monthly == null ? allMonthly : monthly);
  const ticks = [];
  let lastX = -Infinity;
  for (const date of dates) {
    const px = x(date);
    if (px - lastX < minGap || avoid.some(([a, b]) => px > a && px < b)) continue;
    ticks.push({ date, px, label: timelineTickLabel(date, ticks.length ? ticks[ticks.length - 1].date : null, isMonthly(date)) });
    lastX = px;
  }
  return ticks;
}

// Le motif de la zone « à venir » (fond or pâle, hachures) - à poser une fois par page, puis
// fill="url(#<id>)".
function timelineHatchDefs(id) {
  return `<svg width="0" height="0" style="position:absolute;" aria-hidden="true"><defs>
      <pattern id="${id}" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="8" height="8" fill="var(--gold-tint)" fill-opacity="0.55"></rect>
        <line x1="0" y1="0" x2="0" y2="8" stroke="var(--gold)" stroke-opacity="0.22" stroke-width="2"></line>
      </pattern>
    </defs></svg>`;
}
