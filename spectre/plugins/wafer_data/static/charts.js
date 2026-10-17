/* Les dessins de la fiche data d'une plaque (spectre.plugins.wafer_data), en SVG fait main, fonctions pures qui
   rendent une chaîne : un histogramme (dispositifs de la plaque), une cartographie (la colonne par position,
   échelle séquentielle --viz-seq-* bornée aux moustaches pour qu'un point aberrant n'écrase pas la carte), une
   courbe médiane et son enveloppe 10-90 %, et la bande « où elle se place » d'une valeur parmi les plaques du
   projet. Jamais la couleur seule : la carte a son échelle chiffrée et chaque case son infobulle (<title>), la
   courbe sa légende, la bande sa phrase. */

const WaferDataCharts = (() => {
  // 4 chiffres significatifs ; un courant de 1e-6 A ou un compte de 2e7 s'écrit en puissance de dix
  const fmt = (v) => {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const a = Math.abs(v);
    if (a && (a < 1e-3 || a >= 1e7)) return Number(v).toExponential(a < 1e-3 ? 1 : 2).replace(".", ",");
    return Number(v).toLocaleString("fr-FR", { maximumSignificantDigits: 4 });
  };

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

  function ticks(min, max, count = 4) {
    if (!(max > min)) return [min];
    const step = (max - min) / count;
    return Array.from({ length: count + 1 }, (_, i) => min + i * step);
  }

  function histogram(d, unit) {
    const W = 420, H = 190, L = 40, R = 12, T = 14, B = 36;
    const peak = Math.max(...d.counts, 1);
    const bw = (W - L - R) / d.counts.length;
    const x = (v) => L + ((v - d.minimum) / ((d.maximum - d.minimum) || 1)) * (W - L - R);
    const y = (n) => H - B - (n / peak) * (H - T - B);
    const bars = d.counts
      .map((n, i) => {
        const lo = d.minimum + (i * (d.maximum - d.minimum)) / d.counts.length;
        const hi = d.minimum + ((i + 1) * (d.maximum - d.minimum)) / d.counts.length;
        return n
          ? `<rect class="wd-bar" x="${(L + i * bw + 0.5).toFixed(1)}" y="${y(n).toFixed(1)}" width="${Math.max(bw - 1, 1).toFixed(1)}" height="${(H - B - y(n)).toFixed(1)}" rx="1"><title>${fmt(lo)} – ${fmt(hi)} : ${n} dispositif${n > 1 ? "s" : ""}</title></rect>`
          : "";
      })
      .join("");
    const xt = ticks(d.minimum, d.maximum)
      .map((v) => `<text class="wd-tick" x="${x(v).toFixed(1)}" y="${H - B + 16}" text-anchor="middle">${fmt(v)}</text>`)
      .join("");
    const median = d.maximum > d.minimum ? `<line class="wd-median" x1="${x(d.median)}" x2="${x(d.median)}" y1="${T - 4}" y2="${H - B}"><title>médiane ${fmt(d.median)}</title></line>` : "";
    return `<svg class="wd-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Histogramme de ${d.n} valeurs, médiane ${fmt(d.median)}${unit ? " " + unit : ""}">
      <line class="wd-axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"></line>
      <text class="wd-tick" x="${L - 6}" y="${y(peak) + 4}" text-anchor="end">${peak}</text>
      <text class="wd-tick" x="${L - 6}" y="${H - B}" text-anchor="end">0</text>
      ${bars}${median}${xt}
      ${unit ? `<text class="wd-tick" x="${W - R}" y="${H - 4}" text-anchor="end">${escapeHtml(unit)}</text>` : ""}
    </svg>`;
  }

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
        cells += `<rect x="${i * cell}" y="${(ny - 1 - j) * cell}" width="${cell}" height="${cell}" fill="${seqColor(t(v))}"><title>X ${fmt(d.xs[i])}, Y ${fmt(d.ys[j])} : ${fmt(v)}${unit ? " " + unit : ""}</title></rect>`;
      }
    }
    const gid = `wdg${Math.random().toString(36).slice(2, 8)}`;
    const stopsHtml = [0, 0.25, 0.5, 0.75, 1].map((s) => `<stop offset="${s * 100}%" stop-color="${seqColor(s)}"></stop>`).join("");
    const legendH = Math.max(h, 120);
    return `<div class="wd-map">
      <svg class="wd-map__grid" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Cartographie de ${d.n} points, de ${fmt(d.minimum)} à ${fmt(d.maximum)}${unit ? " " + unit : ""}, médiane ${fmt(d.median)}" shape-rendering="crispEdges">${cells}</svg>
      <svg class="wd-map__legend" viewBox="0 0 64 ${legendH}" width="64" height="${legendH}" aria-hidden="true">
        <defs><linearGradient id="${gid}" x1="0" x2="0" y1="1" y2="0">${stopsHtml}</linearGradient></defs>
        <rect x="4" y="6" width="12" height="${legendH - 12}" rx="2" fill="url(#${gid})"></rect>
        <text class="wd-tick" x="22" y="14">${fmt(hi)}</text>
        <text class="wd-tick" x="22" y="${legendH / 2 + 4}">${fmt((lo + hi) / 2)}</text>
        <text class="wd-tick" x="22" y="${legendH - 6}">${fmt(lo)}</text>
      </svg>
    </div>`;
  }

  function curve(d, unit) {
    const W = 420, H = 210, L = 48, R = 12, T = 12, B = 34;
    const lx = d.log_x, ly = d.log_y && Math.min(...d.low) > 0;
    const tx = (v) => (lx ? Math.log10(v) : v);
    const ty = (v) => (ly ? Math.log10(Math.max(v, 1e-30)) : v);
    const x0 = tx(d.x[0]), x1 = tx(d.x[d.x.length - 1]);
    const y0 = Math.min(...d.low.map(ty)), y1 = Math.max(...d.high.map(ty));
    const X = (v) => L + ((tx(v) - x0) / ((x1 - x0) || 1)) * (W - L - R);
    const Y = (v) => H - B - ((ty(v) - y0) / ((y1 - y0) || 1)) * (H - T - B);
    const line = (ys) => d.x.map((x, i) => `${i ? "L" : "M"}${X(x).toFixed(1)},${Y(ys[i]).toFixed(1)}`).join("");
    const band = `${line(d.high)}${d.x.slice().reverse().map((x, i) => `L${X(x).toFixed(1)},${Y(d.low[d.x.length - 1 - i]).toFixed(1)}`).join("")}Z`;
    const xticks = (lx ? ticks(x0, x1).map((v) => 10 ** v) : ticks(d.x[0], d.x[d.x.length - 1]))
      .map((v) => `<text class="wd-tick" x="${X(v).toFixed(1)}" y="${H - B + 16}" text-anchor="middle">${fmt(v)}</text>`)
      .join("");
    const yticks = ticks(y0, y1, 3)
      .map((v) => {
        const real = ly ? 10 ** v : v;
        return `<text class="wd-tick" x="${L - 6}" y="${(Y(real) + 4).toFixed(1)}" text-anchor="end">${fmt(real)}</text><line class="wd-grid" x1="${L}" x2="${W - R}" y1="${Y(real).toFixed(1)}" y2="${Y(real).toFixed(1)}"></line>`;
      })
      .join("");
    return `<svg class="wd-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Courbe médiane de ${d.n} courbes, avec l'enveloppe 10-90 %">
      ${yticks}
      <line class="wd-axis" x1="${L}" x2="${W - R}" y1="${H - B}" y2="${H - B}"></line>
      <path class="wd-band" d="${band}"></path>
      <path class="wd-line" d="${line(d.median)}"></path>
      ${xticks}
      ${unit ? `<text class="wd-tick" x="${L}" y="${T - 2 < 10 ? 10 : T - 2}">${escapeHtml(unit)}</text>` : ""}
    </svg>`;
  }

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

  return { fmt, histogram, wafermap, mapScale, curve, strip, rankText };
})();
