/* EQE vs densité de courant - un composant propre au type « EQE / LIV » : la vue de référence
   d'une LED. Chaque device : son EQE (en %) en fonction de J = I / surface (A/cm², échelle log),
   la médiane de chaque plaque en trait épais, et un repère à 25 A/cm² (le régime où PRISM compare
   des devices de tailles différentes). S'appuie sur le tracé générique de curves.js. */
DataViz.register({
  key: "eqe-curves",
  label: "EQE vs densité de courant",
  description: "EQE (%) en fonction de J (A/cm², log), médiane par plaque, repère à 25 A/cm².",
  accepts: (ds) =>
    DataViz.has(ds, "I") && DataViz.has(ds, "EQE") && DataViz.has(ds, "area_cm2") && DataViz.kind(ds, "I") === "vector" && DataViz.kind(ds, "EQE") === "vector",
  options: () => [
    { key: "maxPerWafer", label: "Courbes par plaque (max.)", type: "number", min: 0, max: 400, step: 1 },
    { key: "median", label: "Médiane par plaque", type: "checkbox" },
    { key: "mark25", label: "Repère à 25 A/cm²", type: "checkbox" },
  ],
  defaults: () => ({ maxPerWafer: 40, median: true, mark25: true }),
  render(el, ds, o) {
    drawCurves(el, ds, {
      x: "I",
      y: "EQE",
      xDivide: "area_cm2",
      yScale: 100,
      logx: true,
      logy: false,
      maxPerWafer: o.maxPerWafer ?? 40,
      median: o.median,
      xLabel: "J (A/cm²)",
      yLabel: "EQE (%)",
      overlay: o.mark25
        ? (frame, sx) => {
            const x = sx(25);
            if (!Number.isFinite(x) || x < frame.left || x > frame.left + frame.width) return "";
            return `<line class="viz-ref" x1="${x}" x2="${x}" y1="${frame.top}" y2="${frame.top + frame.height}"/><text class="viz-tick" x="${x + 4}" y="${frame.top + 11}">25 A/cm²</text>`;
          }
        : null,
    });
  },
});
