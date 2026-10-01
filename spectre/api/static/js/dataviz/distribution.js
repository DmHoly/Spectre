/* Distribution par plaque : une boîte à moustaches par plaque (quartiles, médiane, moustaches à
   1,5 × l'écart interquartile) avec les points de mesure par-dessus - la façon habituelle de
   comparer des plaques (ou les variantes d'un split) sur un KPI. */
DataViz.register({
  key: "distribution",
  label: "Distribution par plaque",
  description: "Boîte à moustaches + points, une par plaque, pour comparer un KPI.",
  accepts(ds, o = {}) {
    if (o.value) return DataViz.has(ds, o.value) && DataViz.kind(ds, o.value) === "number";
    return DataViz.columnsOfKind(ds, "number").length > 0;
  },
  options: () => [
    { key: "value", label: "Valeur", type: "column", filter: "number" },
    { key: "log", label: "Échelle logarithmique", type: "checkbox" },
    { key: "points", label: "Afficher les points", type: "checkbox" },
    { key: "hideZero", label: "Ignorer les zéros (devices éteints)", type: "checkbox" },
  ],
  defaults(ds) {
    const [x, y] = DataViz.xyColumns(ds);
    const numbers = DataViz.columnsOfKind(ds, "number").filter((c) => c !== x && c !== y);
    return { value: numbers[0] || DataViz.columnsOfKind(ds, "number")[0], log: false, points: true, hideZero: false };
  },
  render(el, ds, o) {
    const vs = DataViz.values(ds, o.value);
    const groups = [...DataViz.byWafer(ds).entries()].map(([wafer, idxs]) => {
      const vals = idxs.map((i) => vs[i]).filter((v) => typeof v === "number" && Number.isFinite(v) && (!o.log || v > 0) && !(o.hideZero && v === 0));
      const zeros = o.hideZero ? idxs.filter((i) => vs[i] === 0).length : 0;
      return { wafer, vals, zeros, st: DataViz.stats(vals) };
    });
    const all = groups.flatMap((g) => g.vals);
    if (!all.length) {
      el.innerHTML = `<div class="viz-empty">Aucune valeur numérique dans « ${DataViz.esc(o.value)} ».</div>`;
      return;
    }
    const W = 720;
    const H = 320;
    const frame = { left: 64, top: 14, width: W - 84, height: H - 70 };
    const band = frame.width / groups.length;
    const sy = DataViz.scale(DataViz.padded(DataViz.extent(all), o.log), [frame.top + frame.height, frame.top], { log: o.log });
    const xCenter = (i) => frame.left + band * (i + 0.5);
    let marks = "";
    groups.forEach((g, i) => {
      if (!g.st.n) return;
      const c = DataViz.categorical(i);
      const cx = xCenter(i);
      const bw = Math.min(54, band * 0.5);
      const iqr = g.st.q3 - g.st.q1;
      const lowW = Math.min(...g.vals.filter((v) => v >= g.st.q1 - 1.5 * iqr));
      const highW = Math.max(...g.vals.filter((v) => v <= g.st.q3 + 1.5 * iqr));
      const tipText = `${g.wafer} · n ${g.st.n} · médiane ${DataViz.fmt(g.st.median)} · Q1 ${DataViz.fmt(g.st.q1)} · Q3 ${DataViz.fmt(g.st.q3)}`;
      if (o.points) {
        // points répartis en largeur de façon déterministe (pas d'aléatoire : la vue reste la même)
        g.vals.forEach((v, k) => {
          const jitter = (((k * 9301 + 49297) % 233280) / 233280 - 0.5) * bw * 0.9;
          marks += `<circle cx="${(cx + jitter).toFixed(1)}" cy="${sy(v).toFixed(1)}" r="2.2" fill="${c}" fill-opacity="0.35" data-tip="${DataViz.esc(`${g.wafer} · ${DataViz.fmt(v)}`)}"/>`;
        });
      }
      marks += `
        <line x1="${cx}" x2="${cx}" y1="${sy(lowW)}" y2="${sy(g.st.q1)}" stroke="${c}" stroke-width="1.4"/>
        <line x1="${cx}" x2="${cx}" y1="${sy(g.st.q3)}" y2="${sy(highW)}" stroke="${c}" stroke-width="1.4"/>
        <line x1="${cx - bw / 4}" x2="${cx + bw / 4}" y1="${sy(lowW)}" y2="${sy(lowW)}" stroke="${c}" stroke-width="1.4"/>
        <line x1="${cx - bw / 4}" x2="${cx + bw / 4}" y1="${sy(highW)}" y2="${sy(highW)}" stroke="${c}" stroke-width="1.4"/>
        <rect x="${cx - bw / 2}" y="${sy(g.st.q3)}" width="${bw}" height="${Math.max(1, sy(g.st.q1) - sy(g.st.q3))}" fill="${c}" fill-opacity="0.16" stroke="${c}" stroke-width="1.6" rx="3" data-tip="${DataViz.esc(tipText)}"/>
        <line x1="${cx - bw / 2}" x2="${cx + bw / 2}" y1="${sy(g.st.median)}" y2="${sy(g.st.median)}" stroke="${c}" stroke-width="2.6"/>
        <text class="viz-tick viz-tick--strong" x="${cx}" y="${frame.top + frame.height + 16}" text-anchor="middle">${DataViz.esc(g.wafer)}</text>
        <text class="viz-tick" x="${cx}" y="${frame.top + frame.height + 30}" text-anchor="middle">n ${g.st.n} · méd. ${DataViz.esc(DataViz.fmt(g.st.median))}${g.zeros ? ` · ${g.zeros} éteints` : ""}</text>`;
    });
    el.innerHTML = `${DataViz.svgOpen(W, H, `Distribution de ${o.value} par plaque`)}
      ${DataViz.axes(frame, (v) => v, sy, { xTicks: [], yLabel: o.value + (o.log ? " (log)" : "") })}
      ${marks}</svg>`;
  },
});
