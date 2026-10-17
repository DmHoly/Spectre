/* Les dessins de la fiche data d'une plaque (spectre.plugins.wafer_data), en SVG fait main, fonctions pures qui
   rendent une chaîne : un histogramme (empilé par groupe s'il est coloré), une boîte à moustaches par groupe, un
   nuage de points, une cartographie (la colonne par position, échelle séquentielle --viz-seq-* bornée aux
   moustaches pour qu'un point aberrant n'écrase pas la carte), des courbes (médiane et enveloppe 10-90 %, par
   groupe, ou chacune), et la bande « où elle se place » d'une valeur parmi les plaques du projet.

   Couleurs : la palette catégorielle de la charte (--viz-1 à --viz-8) - une couleur choisie pour une série seule
   (options.color, 1 à 8), une par groupe sinon (« Autres » en gris). Jamais la couleur seule : chaque groupe a sa
   légende (legend), chaque marque son infobulle (<title>), la carte son échelle chiffrée, la bande sa phrase. */

const WaferDataCharts = (() => {
  // 4 chiffres significatifs ; un courant de 1e-6 A ou un compte de 2e7 s'écrit en puissance de dix
  const fmt = (v) => {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const a = Math.abs(v);
    if (a && (a < 1e-3 || a >= 1e7)) return Number(v).toExponential(a < 1e-3 ? 1 : 2).replace(".", ",");
    return Number(v).toLocaleString("fr-FR", { maximumSignificantDigits: 4 });
  };
  const esc = (t) => escapeHtml(String(t ?? ""));

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function hexToRgb(hex) {
    const h = hex.replace("#", "");
    const n = parseInt(h.length === 3 ? h.replace(/(.)/g, "$1$1") : h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  // L'échelle séquentielle de la charte (--viz-seq-1 sombre -> --viz-seq-5 clair), interpolée.
  let stops = null;
  function seqColor(t) {
    if (!stops) stops = [1, 2, 3, 4, 5].map((i) => hexToRgb(cssVar(`--viz-seq-${i}`) || "#888888"));
    const x = Math.min(1, Math.max(0, t)) * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(x));
    const f = x - i;
    const c = stops[i].map((a, k) => Math.round(a + (stops[i + 1][k] - a) * f));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  // --- couleurs et légendes -------------------------------------------------------------------------

  const COLOR_NAMES = ["Bleu", "Ocre", "Vert", "Rouge", "Violet", "Sarcelle", "Brun", "Gris"];
  const single = (color) => `var(--viz-${Math.min(Math.max(Number(color) || 1, 1), 8)})`;
  // une couleur par groupe, dans l'ordre ; « Autres » (le reste des petits groupes) toujours en gris
  const groupColors = (groups) => (groups || []).map((g, i) => (g === "Autres" ? "var(--viz-8)" : `var(--viz-${(i % 7) + 1})`));

  function legend(groups, colors, title = "") {
    if (!groups || groups.length < 2) return "";
    return `<div class="wd-keys" role="list" aria-label="Légende${title ? " : " + esc(title) : ""}">${title ? `<span class="wd-keys__title">${esc(title)}</span>` : ""}${groups
      .map((g, i) => `<span class="wd-keys__item" role="listitem"><span class="wd-keys__swatch" style="background:${colors[i]}"></span>${esc(g)}</span>`)
      .join("")}</div>`;
  }

  // --- axes ---------------------------------------------------------------------------------------

  function ticks(min, max, count = 4) {
    if (!(max > min)) return [min];
    const step = (max - min) / count;
    return Array.from({ length: count + 1 }, (_, i) => min + i * step);
  }

  // Des graduations rondes (1, 2, 5 × 10ⁿ) dans [min ; max].
  function niceTicks(min, max, count = 4) {
    if (!(max > min)) return [min];
    const rough = (max - min) / count;
    const power = 10 ** Math.floor(Math.log10(rough));
    const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough);
    const out = [];
    for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
    return out;
  }

  // Un axe : la transformation (log10 si log) et ses graduations - les décades en log.
  function axis(values, log, count = 4) {
    const finite = values.filter((v) => Number.isFinite(v) && (!log || v > 0));
    let lo = Math.min(...finite), hi = Math.max(...finite);
    if (!finite.length) (lo = 0), (hi = 1);
    const t = (v) => (log ? Math.log10(Math.max(v, 1e-300)) : v);
    let a = t(lo), b = t(hi);
    if (a === b) (a -= log ? 0.5 : Math.abs(a) * 0.1 || 1), (b += log ? 0.5 : Math.abs(b) * 0.1 || 1);
    let list;
    if (log) {
      const decades = [];
      for (let k = Math.ceil(a); k <= Math.floor(b); k++) decades.push(10 ** k);
      const every = Math.ceil(decades.length / 6) || 1;
      list = decades.length >= 2 ? decades.filter((_, i) => i % every === 0) : ticks(a, b, count).map((v) => 10 ** v);
    } else list = niceTicks(a, b, count);
    return { t, a, b, ticks: list };
  }

  // Le cadre commun (grilles, axes, graduations, titres d'axes) d'un graphique en x/y.
  function frame({ W, H, L, R, T, B, X, Y, xAxis, yAxis, xLabel, yLabel }) {
    const yt = yAxis.ticks
      .map((v) => `<line class="wd-grid" x1="${L}" x2="${W - R}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}"></line><text class="wd-tick" x="${L - 6}" y="${(Y(v) + 3.5).toFixed(1)}" text-anchor="end">${fmt(v)}</text>`)
      .join("");
    const xt = xAxis
      ? xAxis.ticks.map((v) => `<text class="wd-tick" x="${X(v).toFixed(1)}" y="${H - B + 15}" text-anchor="middle">${fmt(v)}</text>`).join("")
      : "";
    return `${yt}<line class="wd-axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"></line>${xt}
      ${xLabel ? `<text class="wd-axis-title" x="${W - R}" y="${H - 4}" text-anchor="end">${esc(xLabel)}</text>` : ""}
      ${yLabel ? `<text class="wd-axis-title" x="${L - 6}" y="${T - 6}" text-anchor="start">${esc(yLabel)}</text>` : ""}`;
  }

  const label = (name, unit) => (name ? `${name}${unit ? ` (${unit})` : ""}` : unit || "");

  // --- histogramme ----------------------------------------------------------------------------------

  // options : color (1-8, une seule série), xLabel ; d.series + d.groups : empilé par groupe.
  function histogram(d, unit, options = {}) {
    const W = 420, H = 196, L = 40, R = 12, T = 16, B = 38;
    const peak = Math.max(...d.counts, 1);
    const nb = d.counts.length;
    const bw = (W - L - R) / nb;
    const x = (v) => L + ((v - d.minimum) / ((d.maximum - d.minimum) || 1)) * (W - L - R);
    const y = (n) => H - B - (n / peak) * (H - T - B);
    const series = d.series && d.groups ? d.series : [d.counts];
    const colors = d.series && d.groups ? groupColors(d.groups) : [single(options.color)];
    let bars = "";
    for (let i = 0; i < nb; i++) {
      const lo = d.minimum + (i * (d.maximum - d.minimum)) / nb;
      const hi = d.minimum + ((i + 1) * (d.maximum - d.minimum)) / nb;
      let base = 0;
      series.forEach((counts, g) => {
        const n = counts[i];
        if (!n) return;
        const top = y(base + n), bottom = y(base);
        bars += `<rect class="wd-bar" x="${(L + i * bw + 0.5).toFixed(1)}" y="${top.toFixed(1)}" width="${Math.max(bw - 1, 1).toFixed(1)}" height="${Math.max(bottom - top - (base ? 1 : 0), 0.5).toFixed(1)}" style="fill:${colors[g]}"><title>${fmt(lo)} – ${fmt(hi)} : ${n} dispositif${n > 1 ? "s" : ""}${d.groups ? ` (${esc(d.groups[g])})` : ""}</title></rect>`;
        base += n;
      });
    }
    const xt = ticks(d.minimum, d.maximum)
      .map((v) => `<text class="wd-tick" x="${x(v).toFixed(1)}" y="${H - B + 15}" text-anchor="middle">${fmt(v)}</text>`)
      .join("");
    const median = d.maximum > d.minimum ? `<line class="wd-median" x1="${x(d.median)}" x2="${x(d.median)}" y1="${T - 4}" y2="${H - B}"><title>médiane ${fmt(d.median)}</title></line>` : "";
    return `<svg class="wd-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Histogramme de ${d.n} valeurs, médiane ${fmt(d.median)}${unit ? " " + esc(unit) : ""}">
      <line class="wd-axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"></line>
      <text class="wd-tick" x="${L - 6}" y="${y(peak) + 4}" text-anchor="end">${peak}</text>
      <text class="wd-tick" x="${L - 6}" y="${H - B}" text-anchor="end">0</text>
      ${bars}${median}${xt}
      <text class="wd-axis-title" x="${W - R}" y="${H - 4}" text-anchor="end">${esc(options.xLabel || unit || "")}</text>
    </svg>`;
  }

  // --- boîtes à moustaches ----------------------------------------------------------------------------

  // d.boxes : [{label, n, whisker_low, q1, median, q3, whisker_high, mean, outliers}] ; options : color, yLabel.
  function boxplot(d, unit, options = {}) {
    const boxes = d.boxes || [];
    const W = 420, H = 224, L = 50, R = 12, T = 18, B = boxes.length > 1 ? 40 : 22;
    const all = boxes.flatMap((b) => [b.whisker_low, b.whisker_high, ...b.outliers]);
    const yAxis = axis(all, d.log_y);
    const Y = (v) => H - B - ((yAxis.t(v) - yAxis.a) / (yAxis.b - yAxis.a || 1)) * (H - T - B);
    const grouped = boxes.length > 1 || (boxes[0] && boxes[0].label);
    const colors = grouped ? groupColors(boxes.map((b) => b.label)) : [single(options.color)];
    const band = (W - L - R) / Math.max(boxes.length, 1);
    const width = Math.min(48, band * 0.62);
    const marks = boxes
      .map((b, i) => {
        const cx = L + band * (i + 0.5), c = colors[i % colors.length];
        const tip = `${b.label ? b.label + " - " : ""}${b.n} valeur${b.n > 1 ? "s" : ""} · médiane ${fmt(b.median)} · Q1 ${fmt(b.q1)} · Q3 ${fmt(b.q3)} · moustaches ${fmt(b.whisker_low)} à ${fmt(b.whisker_high)}`;
        const outliers = b.outliers.map((v) => `<circle class="wd-outlier" cx="${cx.toFixed(1)}" cy="${Y(v).toFixed(1)}" r="2.4" style="stroke:${c}"><title>${fmt(v)}</title></circle>`).join("");
        const name = b.label && boxes.length > 1 ? `<text class="wd-tick" x="${cx.toFixed(1)}" y="${H - B + 15}" text-anchor="middle">${esc(b.label.length > 12 ? b.label.slice(0, 11) + "…" : b.label)}<title>${esc(b.label)}</title></text>` : "";
        return `<g class="wd-box"><title>${esc(tip)}</title>
          <line class="wd-whisker" x1="${cx}" x2="${cx}" y1="${Y(b.whisker_high).toFixed(1)}" y2="${Y(b.q3).toFixed(1)}" style="stroke:${c}"></line>
          <line class="wd-whisker" x1="${cx}" x2="${cx}" y1="${Y(b.q1).toFixed(1)}" y2="${Y(b.whisker_low).toFixed(1)}" style="stroke:${c}"></line>
          <line class="wd-whisker" x1="${cx - width / 4}" x2="${cx + width / 4}" y1="${Y(b.whisker_high).toFixed(1)}" y2="${Y(b.whisker_high).toFixed(1)}" style="stroke:${c}"></line>
          <line class="wd-whisker" x1="${cx - width / 4}" x2="${cx + width / 4}" y1="${Y(b.whisker_low).toFixed(1)}" y2="${Y(b.whisker_low).toFixed(1)}" style="stroke:${c}"></line>
          <rect class="wd-box__body" x="${(cx - width / 2).toFixed(1)}" y="${Y(b.q3).toFixed(1)}" width="${width.toFixed(1)}" height="${Math.max(Y(b.q1) - Y(b.q3), 1).toFixed(1)}" rx="2" style="stroke:${c};fill:${c}"></rect>
          <line class="wd-box__median" x1="${(cx - width / 2).toFixed(1)}" x2="${(cx + width / 2).toFixed(1)}" y1="${Y(b.median).toFixed(1)}" y2="${Y(b.median).toFixed(1)}"></line>
          ${outliers}${name}</g>`;
      })
      .join("");
    return `<svg class="wd-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Boîte${boxes.length > 1 ? "s" : ""} à moustaches de ${d.n} valeurs${boxes.length > 1 ? `, ${boxes.length} groupes` : ""}">
      ${frame({ W, H, L, R, T, B, Y, yAxis, yLabel: options.yLabel || unit })}${marks}</svg>`;
  }

  // --- nuage de points --------------------------------------------------------------------------------

  // d.points : [[x, y, groupe]] ; options : color, xLabel, yLabel.
  function scatter(d, options = {}) {
    const W = 420, H = 224, L = 50, R = 12, T = 18, B = 38;
    const xAxis = axis(d.points.map((p) => p[0]), d.log_x);
    const yAxis = axis(d.points.map((p) => p[1]), d.log_y);
    const X = (v) => L + ((xAxis.t(v) - xAxis.a) / (xAxis.b - xAxis.a || 1)) * (W - L - R);
    const Y = (v) => H - B - ((yAxis.t(v) - yAxis.a) / (yAxis.b - yAxis.a || 1)) * (H - T - B);
    const colors = d.groups && d.groups.length ? groupColors(d.groups) : [single(options.color)];
    const titled = d.points.length <= 400;
    const dots = d.points
      .map(([x, y, g]) => `<circle class="wd-dot" cx="${X(x).toFixed(1)}" cy="${Y(y).toFixed(1)}" r="2.6" style="fill:${colors[g] || colors[0]}">${titled ? `<title>${fmt(x)} ; ${fmt(y)}${d.groups && d.groups.length ? ` (${esc(d.groups[g])})` : ""}</title>` : ""}</circle>`)
      .join("");
    return `<svg class="wd-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Nuage de ${d.shown} points${d.shown < d.n ? ` sur ${d.n}` : ""}">
      ${frame({ W, H, L, R, T, B, X, Y, xAxis, yAxis, xLabel: options.xLabel, yLabel: options.yLabel })}${dots}</svg>`;
  }

  // --- cartographie -----------------------------------------------------------------------------------

  // Les bornes de l'échelle d'une cartographie : ses moustaches (Q1 - 1,5 IQR, Q3 + 1,5 IQR), dans [min ; max].
  function mapScale(d) {
    const spread = 1.5 * (d.q3 - d.q1);
    return { lo: Math.max(d.minimum, d.q1 - spread), hi: Math.min(d.maximum, d.q3 + spread) };
  }

  // La cartographie : une case par position mesurée ; l'échelle va des moustaches basses aux hautes - une case
  // au-delà prend la couleur du bout, son infobulle dit sa vraie valeur. options : {lo, hi} une échelle imposée
  // (plusieurs cartes comparées sur la même), size le côté du dessin (300 px).
  function wafermap(d, unit, options = {}) {
    const nx = d.xs.length, ny = d.ys.length;
    const size = options.size || 300;
    const cell = Math.max(2, Math.floor(size / Math.max(nx, ny)));
    const w = cell * nx, h = cell * ny;
    const own = mapScale(d);
    const lo = options.lo ?? own.lo;
    const hi = options.hi ?? own.hi;
    const t = (v) => (hi > lo ? (v - lo) / (hi - lo) : 0.5);
    let cells = "";
    for (let j = 0; j < ny; j++) {
      for (let i = 0; i < nx; i++) {
        const v = d.values[j][i];
        if (v === null) continue;
        // y croît vers le haut sur une plaque : la première ligne de la grille se dessine en bas
        cells += `<rect x="${i * cell}" y="${(ny - 1 - j) * cell}" width="${cell}" height="${cell}" fill="${seqColor(t(v))}"><title>X ${fmt(d.xs[i])}, Y ${fmt(d.ys[j])} : ${fmt(v)}${unit ? " " + esc(unit) : ""}</title></rect>`;
      }
    }
    const gid = `wdg${Math.random().toString(36).slice(2, 8)}`;
    const stopsHtml = [0, 0.25, 0.5, 0.75, 1].map((s) => `<stop offset="${s * 100}%" stop-color="${seqColor(s)}"></stop>`).join("");
    const legendH = Math.max(h, 120);
    return `<div class="wd-map">
      <svg class="wd-map__grid" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Cartographie de ${d.n} points, de ${fmt(d.minimum)} à ${fmt(d.maximum)}${unit ? " " + esc(unit) : ""}, médiane ${fmt(d.median)}" shape-rendering="crispEdges">${cells}</svg>
      <svg class="wd-map__legend" viewBox="0 0 64 ${legendH}" width="64" height="${legendH}" aria-hidden="true">
        <defs><linearGradient id="${gid}" x1="0" x2="0" y1="1" y2="0">${stopsHtml}</linearGradient></defs>
        <rect x="4" y="6" width="12" height="${legendH - 12}" rx="2" fill="url(#${gid})"></rect>
        <text class="wd-tick" x="22" y="14">${fmt(hi)}</text>
        <text class="wd-tick" x="22" y="${legendH / 2 + 4}">${fmt((lo + hi) / 2)}</text>
        <text class="wd-tick" x="22" y="${legendH - 6}">${fmt(lo)}</text>
      </svg>
    </div>`;
  }

  // --- courbes ----------------------------------------------------------------------------------------

  // d : {x, median, low, high} (toutes les courbes) + series [{label, x, median, low, high}] (par groupe) ou
  // curves [{g, x, y}] (chacune, mode « curves ») et groups. options : color (série seule), xLabel, yLabel.
  function curve(d, unit, options = {}) {
    const W = 420, H = 224, L = 50, R = 12, T = 18, B = 38;
    const each = d.curves && d.curves.length ? d.curves : null;
    const series = !each && d.series && d.series.length ? d.series : null;
    const colors = d.groups && d.groups.length ? groupColors(d.groups) : [single(options.color)];
    const layers = each ? each.map((c) => ({ x: c.x, ys: [c.y] })) : (series || [d]).map((s) => ({ x: s.x, ys: [s.low, s.high, s.median] }));
    const xAxis = axis(layers.flatMap((l) => l.x), d.log_x);
    const yAxis = axis(layers.flatMap((l) => l.ys.flat()), d.log_y);
    const X = (v) => L + ((xAxis.t(v) - xAxis.a) / (xAxis.b - xAxis.a || 1)) * (W - L - R);
    const Y = (v) => H - B - ((yAxis.t(v) - yAxis.a) / (yAxis.b - yAxis.a || 1)) * (H - T - B);
    const line = (xs, ys) => xs.map((x, i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join("");
    const band = (s) => `${line(s.x, s.high)}${s.x.slice().reverse().map((x, i) => `L${X(x).toFixed(1)},${Y(s.low[s.x.length - 1 - i]).toFixed(1)}`).join("")}Z`;
    let marks;
    if (each) {
      marks = each
        .map((c) => `<path class="wd-trace" d="${line(c.x, c.y)}" style="stroke:${colors[c.g] || colors[0]}"><title>${d.groups && d.groups.length ? esc(d.groups[c.g]) : "une courbe"}</title></path>`)
        .join("");
      marks += `<path class="wd-line wd-line--overall" d="${line(d.x, d.median)}"><title>médiane de toutes les courbes</title></path>`;
    } else if (series) {
      const bands = series.map((s) => `<path class="wd-band" d="${band(s)}" style="fill:${colors[d.groups.indexOf(s.label)]};fill-opacity:.14"></path>`).join("");
      const medians = series
        .map((s) => `<path class="wd-line" d="${line(s.x, s.median)}" style="stroke:${colors[d.groups.indexOf(s.label)]}"><title>${esc(s.label)} : médiane de ${s.n} courbe${s.n > 1 ? "s" : ""}</title></path>`)
        .join("");
      marks = bands + medians;
    } else {
      marks = `<path class="wd-band" d="${band(d)}" style="fill:${colors[0]};fill-opacity:.18"></path><path class="wd-line" d="${line(d.x, d.median)}" style="stroke:${colors[0]}"><title>médiane de ${d.n} courbe${d.n > 1 ? "s" : ""}</title></path>`;
    }
    const aria = each ? `${each.length} courbes${each.length < d.n ? ` sur ${d.n}` : ""} et leur médiane` : `Courbe médiane de ${d.n} courbes avec l'enveloppe 10-90 %${series ? `, par groupe (${series.length})` : ""}`;
    return `<svg class="wd-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${aria}">
      ${frame({ W, H, L, R, T, B, X, Y, xAxis, yAxis, xLabel: options.xLabel, yLabel: options.yLabel || unit })}
      <g class="wd-plot">${marks}</g></svg>`;
  }

  // --- la place d'une valeur ----------------------------------------------------------------------------

  // Où la valeur de la plaque se place parmi les plaques du projet déjà calculées : leur distribution en barres,
  // la classe de la plaque en navy, les autres en gris ; la phrase (rankText) dit le rang.
  function strip(population, value) {
    const W = 220, H = 34;
    const peak = Math.max(...population.bins, 1);
    const n = population.bins.length;
    const span = population.maximum - population.minimum;
    const mine = span > 0 ? Math.min(n - 1, Math.floor(((value - population.minimum) / span) * n)) : 0;
    const bw = W / n;
    const bars = population.bins
      .map((c, i) => (c ? `<rect class="${i === mine ? "wd-strip__mine" : "wd-strip__bar"}" x="${(i * bw + 0.5).toFixed(1)}" y="${(H - 4 - (c / peak) * (H - 6)).toFixed(1)}" width="${Math.max(bw - 1, 1).toFixed(1)}" height="${((c / peak) * (H - 6)).toFixed(1)}" rx="1"></rect>` : ""))
      .join("");
    return `<svg class="wd-strip" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">${bars}<line class="wd-axis" x1="0" x2="${W}" y1="${H - 3.5}" y2="${H - 3.5}"></line></svg>
      <div class="wd-strip__ends"><span>${fmt(population.minimum)}</span><span>${fmt(population.maximum)}</span></div>`;
  }

  // Face aux autres plaques du projet déjà calculées (elle-même n'en est pas) : `equal` la compte.
  function rankText(population, better) {
    const { count, below, equal } = population;
    const others = count - 1;
    const above = count - below - equal;
    const of = `des ${others} autre${others > 1 ? "s" : ""} plaque${others > 1 ? "s" : ""} calculée${others > 1 ? "s" : ""} du projet`;
    if (better === "high") return `Meilleure que ${Math.round((below / others) * 100)} % ${of}`;
    if (better === "low") return `Meilleure que ${Math.round((above / others) * 100)} % ${of}`;
    return `Au-dessus de ${Math.round((below / others) * 100)} % ${of}`;
  }

  return { fmt, histogram, boxplot, scatter, wafermap, mapScale, curve, strip, rankText, legend, groupColors, single, label, COLOR_NAMES };
})();
