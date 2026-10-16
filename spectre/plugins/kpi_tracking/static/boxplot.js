/* Le dessin d'une boîte à moustaches par plaque (SVG, sans bibliothèque) : boîte de Q1 à Q3, trait de la
   médiane, moustaches jusqu'aux dernières valeurs à 1,5 × l'écart interquartile, valeurs aberrantes en
   points. Pur : reçoit les statistiques déjà calculées par le serveur (kpi_tracking.service) et rend
   une chaîne SVG - une plaque sans mesure garde sa place, marquée « aucune mesure ». */

const KPI_BOXPLOT_COLORS = ["var(--viz-1)", "var(--viz-2)", "var(--viz-3)", "var(--viz-4)", "var(--viz-5)", "var(--viz-6)", "var(--viz-7)", "var(--viz-8)"];

function kpiBoxplotColor(index) {
  return KPI_BOXPLOT_COLORS[index % KPI_BOXPLOT_COLORS.length];
}

function kpiFormatNumber(value) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const abs = Math.abs(value);
  if (abs !== 0 && (abs >= 1e5 || abs < 1e-3)) return value.toExponential(2);
  return Number(value.toPrecision(4)).toLocaleString("fr-FR", { maximumFractionDigits: 6 });
}

// Des graduations rondes (1, 2, 5 × 10ⁿ) couvrant [low, high] : [{value}] et les bornes élargies.
function kpiNiceTicks(low, high, count = 5) {
  if (low === high) {
    const pad = Math.abs(low) * 0.1 || 1;
    low -= pad;
    high += pad;
  }
  const rough = (high - low) / count;
  const power = Math.pow(10, Math.floor(Math.log10(rough)));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough);
  const start = Math.floor(low / step) * step;
  const end = Math.ceil(high / step) * step;
  const ticks = [];
  for (let v = start; v <= end + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return { ticks, low: start, high: end };
}

/* groups : [{wafer, studies, stats|null, outliers}] ; options.colorOf(group, index) -> couleur CSS,
   options.label : le titre accessible du dessin. Renvoie une chaîne SVG. */
function kpiBoxplotSvg(groups, options = {}) {
  const esc = escapeHtml;
  const measured = groups.filter((g) => g.stats);
  if (!measured.length) return "";
  const extent = measured.flatMap((g) => [g.stats.whisker_low, g.stats.whisker_high, ...g.outliers]);
  const { ticks, low, high } = kpiNiceTicks(Math.min(...extent), Math.max(...extent));
  const band = Math.max(84, Math.min(150, 720 / groups.length)); // large quand il y a peu de plaques
  const frame = { left: 64, right: 16, top: 14, height: 250 };
  const width = frame.left + frame.right + band * groups.length;
  const height = frame.top + frame.height + 58;
  const y = (v) => frame.top + frame.height * (1 - (v - low) / (high - low));
  const colorOf = options.colorOf || ((g, i) => kpiBoxplotColor(i));
  let marks = "";
  ticks.forEach((t) => {
    marks += `<line class="kt-plot-grid" x1="${frame.left}" x2="${width - frame.right}" y1="${y(t).toFixed(1)}" y2="${y(t).toFixed(1)}"/>
      <text class="kt-plot-tick" x="${frame.left - 8}" y="${(y(t) + 3.5).toFixed(1)}" text-anchor="end">${esc(kpiFormatNumber(t))}</text>`;
  });
  marks += `<line class="kt-plot-axis" x1="${frame.left}" x2="${frame.left}" y1="${frame.top}" y2="${frame.top + frame.height}"/>
    <line class="kt-plot-axis" x1="${frame.left}" x2="${width - frame.right}" y1="${frame.top + frame.height}" y2="${frame.top + frame.height}"/>`;
  groups.forEach((g, i) => {
    const cx = frame.left + band * (i + 0.5);
    const baseline = frame.top + frame.height;
    const studies = g.studies.map((s) => s.title).join(" · ");
    const caption = `<text class="kt-plot-tick kt-plot-tick--strong" x="${cx}" y="${baseline + 16}" text-anchor="middle">${esc(g.wafer)}</text>`;
    if (!g.stats) {
      marks += `${caption}<text class="kt-plot-empty" x="${cx}" y="${baseline - 8}" text-anchor="middle">aucune mesure</text>
        <title>${esc(`${g.wafer} · aucune mesure · ${studies}`)}</title>`;
      return;
    }
    const s = g.stats;
    const color = colorOf(g, i);
    const w = Math.min(46, band * 0.55);
    const tip = `${g.wafer} · ${studies}\nn ${s.n} · médiane ${kpiFormatNumber(s.median)} · moyenne ${kpiFormatNumber(s.mean)}\nQ1 ${kpiFormatNumber(s.q1)} · Q3 ${kpiFormatNumber(s.q3)}\nmin ${kpiFormatNumber(s.minimum)} · max ${kpiFormatNumber(s.maximum)}`;
    const boxTop = y(s.q3);
    marks += `<g style="color:${color}">
        <title>${esc(tip)}</title>
        <line x1="${cx}" x2="${cx}" y1="${y(s.whisker_low).toFixed(1)}" y2="${y(s.q1).toFixed(1)}" stroke="currentColor" stroke-width="1.4"/>
        <line x1="${cx}" x2="${cx}" y1="${y(s.q3).toFixed(1)}" y2="${y(s.whisker_high).toFixed(1)}" stroke="currentColor" stroke-width="1.4"/>
        <line x1="${cx - w / 4}" x2="${cx + w / 4}" y1="${y(s.whisker_low).toFixed(1)}" y2="${y(s.whisker_low).toFixed(1)}" stroke="currentColor" stroke-width="1.4"/>
        <line x1="${cx - w / 4}" x2="${cx + w / 4}" y1="${y(s.whisker_high).toFixed(1)}" y2="${y(s.whisker_high).toFixed(1)}" stroke="currentColor" stroke-width="1.4"/>
        <rect x="${cx - w / 2}" y="${boxTop.toFixed(1)}" width="${w}" height="${Math.max(1, y(s.q1) - boxTop).toFixed(1)}" rx="3" fill="currentColor" fill-opacity="0.16" stroke="currentColor" stroke-width="1.6"/>
        <line x1="${cx - w / 2}" x2="${cx + w / 2}" y1="${y(s.median).toFixed(1)}" y2="${y(s.median).toFixed(1)}" stroke="currentColor" stroke-width="2.6"/>
        ${g.outliers.map((v) => `<circle cx="${cx}" cy="${y(v).toFixed(1)}" r="2.4" fill="none" stroke="currentColor" stroke-width="1.2"><title>${esc(`${g.wafer} · ${kpiFormatNumber(v)}`)}</title></circle>`).join("")}
      </g>
      ${caption}
      <text class="kt-plot-tick" x="${cx}" y="${baseline + 30}" text-anchor="middle">n ${s.n}</text>
      <text class="kt-plot-tick" x="${cx}" y="${baseline + 43}" text-anchor="middle">méd. ${esc(kpiFormatNumber(s.median))}</text>`;
  });
  return `<svg viewBox="0 0 ${width} ${height}" style="width:${width}px;max-width:100%;height:auto" role="img" aria-label="${esc(options.label || "Boîtes à moustaches par plaque")}">${marks}</svg>`;
}
