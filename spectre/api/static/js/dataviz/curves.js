/* Courbes : pour les colonnes qui portent un balayage complet par ligne (I et V, EQE... d'un
   device), une courbe par ligne - un vecteur contre un autre -, colorées par plaque, avec la
   médiane de chaque plaque en trait épais. L'axe horizontal peut être divisé par une grandeur
   scalaire de la ligne (le courant par la surface, pour une densité de courant). */
DataViz.register({
  key: "curves",
  label: "Courbes",
  description: "Une courbe par device (un vecteur contre un autre), colorées par plaque.",
  accepts(ds, o = {}) {
    const vectors = DataViz.columnsOfKind(ds, "vector");
    if (o.x || o.y) return [o.x, o.y].every((c) => vectors.includes(c)) && (!o.xDivide || DataViz.kind(ds, o.xDivide) === "number");
    return vectors.length >= 2;
  },
  options: () => [
    { key: "x", label: "Axe horizontal (vecteur)", type: "column", filter: "vector" },
    { key: "y", label: "Axe vertical (vecteur)", type: "column", filter: "vector" },
    { key: "xDivide", label: "Diviser l'horizontal par", type: "column", filter: "number", optional: true },
    { key: "yScale", label: "Multiplier le vertical par", type: "number", step: "any" },
    { key: "logx", label: "Horizontal en log", type: "checkbox" },
    { key: "logy", label: "Vertical en log", type: "checkbox" },
    { key: "maxPerWafer", label: "Courbes par plaque (max.)", type: "number", min: 0, max: 400, step: 1 },
    { key: "median", label: "Médiane par plaque", type: "checkbox" },
  ],
  defaults(ds) {
    const vectors = DataViz.columnsOfKind(ds, "vector");
    return { x: vectors[0], y: vectors[1], xDivide: "", yScale: 1, logx: false, logy: false, maxPerWafer: 40, median: true };
  },
  render(el, ds, o) {
    drawCurves(el, ds, {
      x: o.x,
      y: o.y,
      xDivide: o.xDivide,
      yScale: Number(o.yScale) || 1,
      logx: o.logx,
      logy: o.logy,
      maxPerWafer: o.maxPerWafer ?? 40,
      median: o.median,
      xLabel: o.xDivide ? `${o.x} / ${o.xDivide}` : o.x,
      yLabel: Number(o.yScale) && Number(o.yScale) !== 1 ? `${o.y} × ${o.yScale}` : o.y,
    });
  },
});

// Le tracé, partagé avec les composants propres à un type de données (eqe-curves.js...).
function drawCurves(el, ds, o) {
  const label = DataViz.find(ds, ["Led_Name", "device", "die"]);
  const ok = (v, log) => typeof v === "number" && Number.isFinite(v) && (!log || v > 0);
  const groups = [...DataViz.byWafer(ds).entries()];
  const series = [];
  groups.forEach(([wafer, idxs], gi) => {
    const lines = [];
    idxs.forEach((i) => {
      const xv = DataViz.cell(ds, i, o.x);
      const yv = DataViz.cell(ds, i, o.y);
      if (!Array.isArray(xv) || !Array.isArray(yv)) return;
      const div = o.xDivide ? DataViz.cell(ds, i, o.xDivide) : 1;
      if (o.xDivide && !(typeof div === "number" && div)) return;
      const pts = [];
      for (let k = 0; k < Math.min(xv.length, yv.length); k++) {
        const x = xv[k] / div;
        const y = yv[k] * o.yScale;
        if (ok(x, o.logx) && ok(y, o.logy)) pts.push([x, y]);
      }
      if (pts.length > 1) lines.push({ pts, name: label ? DataViz.cell(ds, i, label) : `ligne ${i + 1}` });
    });
    series.push({ wafer, color: DataViz.categorical(gi), lines });
  });
  const allPts = series.flatMap((s) => s.lines.flatMap((l) => l.pts));
  if (!allPts.length) {
    el.innerHTML = `<div class="viz-empty">Pas de courbe à tracer avec ces colonnes.</div>`;
    return;
  }
  const W = 720;
  const H = 380;
  const frame = { left: 74, top: 14, width: W - 94, height: H - 66 };
  const sx = DataViz.scale(DataViz.extent(allPts.map((p) => p[0])), [frame.left, frame.left + frame.width], { log: o.logx });
  const sy = DataViz.scale(DataViz.padded(DataViz.extent(allPts.map((p) => p[1])), o.logy), [frame.top + frame.height, frame.top], { log: o.logy });
  const path = (pts) => pts.map((p, k) => `${k ? "L" : "M"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join("");
  let marks = "";
  series.forEach((s) => {
    const shown = o.maxPerWafer > 0 ? s.lines.filter((_, k) => k % Math.max(1, Math.ceil(s.lines.length / o.maxPerWafer)) === 0) : [];
    shown.forEach((l) => {
      marks += `<path d="${path(l.pts)}" fill="none" stroke="${s.color}" stroke-opacity="0.28" stroke-width="1" data-tip="${DataViz.esc(`${s.wafer} · ${l.name}`)}"/>`;
    });
  });
  if (o.median) {
    // médiane point à point, sur une grille commune de l'axe horizontal (interpolation)
    const [gx0, gx1] = sx.domain || DataViz.extent(allPts.map((p) => p[0]));
    const grid = Array.from({ length: 48 }, (_, k) =>
      o.logx ? 10 ** (Math.log10(gx0) + (k * (Math.log10(gx1) - Math.log10(gx0))) / 47) : gx0 + (k * (gx1 - gx0)) / 47
    );
    const interp = (pts, x) => {
      for (let k = 1; k < pts.length; k++) {
        const [a, b] = [pts[k - 1], pts[k]];
        if ((a[0] <= x && x <= b[0]) || (b[0] <= x && x <= a[0])) return a[1] + ((b[1] - a[1]) * (x - a[0])) / (b[0] - a[0] || 1);
      }
      return null;
    };
    series.forEach((s) => {
      const med = grid
        .map((x) => {
          const st = DataViz.stats(s.lines.map((l) => interp(l.pts, x)).filter((v) => v !== null));
          return st.n >= Math.max(1, Math.floor(s.lines.length / 3)) ? [x, st.median] : null;
        })
        .filter(Boolean);
      if (med.length > 1) marks += `<path d="${path(med)}" fill="none" stroke="${s.color}" stroke-width="2.8" data-tip="${DataViz.esc(`${s.wafer} · médiane de ${s.lines.length} courbes`)}"/>`;
    });
  }
  el.innerHTML = `${DataViz.svgOpen(W, H, `${o.yLabel} en fonction de ${o.xLabel}`)}
    ${DataViz.axes(frame, sx, sy, { xLabel: o.xLabel + (o.logx ? " (log)" : ""), yLabel: o.yLabel + (o.logy ? " (log)" : "") })}
    ${o.overlay ? o.overlay(frame, sx, sy) : ""}
    ${marks}</svg>${DataViz.legendHtml(series.map((s) => `${s.wafer} (${s.lines.length})`))}`;
}
