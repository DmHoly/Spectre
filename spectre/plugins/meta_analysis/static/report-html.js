/* Le mini-rapport d'une analyse de plaques : un document HTML d'un seul fichier, sans rien à charger (ni police,
   ni script, ni image distante - il s'ouvre hors ligne, se transmet tel quel et s'imprime en PDF).

   AnalysisReport.build(report) -> le document (une chaîne). Pur : tout vient de `report`, que la page de
   l'analyse compose (analysis.js) à partir de ce qu'elle montre :

     {
       title, question, conclusion, date, byline, logoSvg,       // textes ; logoSvg facultatif (un <svg>)
       wafers: [{lasermark, color, isRef, structure: {svg, caption} | null, facts: [{label, value}],
                 notes: {context, hypothesis, learnings} | null, studies: [{title, status, conclusion, next}]}],
       differences: [{lasermark, color, comparable, items: [{kind, step, parameter, from, to}],
                      kpis: [{title, text, verdict}]}],             // une entrée par plaque comparée (pas la référence)
       kpis: [{title, source, better, status, message, svg, rows: [{lasermark, color, isRef, n, median, delta, verdict, date}]}],
       blocks: [{title, kind, figure}],                             // les blocs libres de l'analyse, comme sheets
       sheets: [{title, kind, figure}],                             // figure : le dessin déjà rendu (SVG / HTML, les
                                                                    // images déjà réduites en data: URL)
     }

   AnalysisReport.differences(result, row) : ce qui distingue une ligne d'un tableau du comparateur de sa base
   (le portage de comparator.table.differences) - {kind, step, parameter, from, to}. */

const AnalysisReport = (() => {
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  // Une couleur n'entre dans un attribut style que si c'est une couleur : jamais du CSS libre.
  function safeColor(color, fallback = "#646e8c") {
    return /^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%]+\)|var\(--[a-z0-9-]+\)|[a-z]{3,20})$/i.test(String(color || "")) ? color : fallback;
  }

  // -- ce qui diffère de la base dans un tableau du comparateur -------------------------------------

  function differences(result, row) {
    const base = result.baseline;
    const rows = result.rows || [];
    if (base === null || base === undefined || row === base || !rows[row] || !rows[base]) return [];
    const cells = rows[row].cells;
    const baseCells = rows[base].cells;
    if (!cells || !baseCells) return [];
    const found = [];
    let start = 0;
    for (const group of result.groups || []) {
      const width = group.columns.length;
      const mine = cells.slice(start, start + width);
      group.columns.forEach((column, i) => {
        const cell = mine[i];
        if (cell.status === "changed" || cell.changed) found.push({ kind: "changed", step: group.label, parameter: column.label, from: baseCells[start + i].text, to: cell.text });
        else if (cell.status === "added_param") found.push({ kind: "added_param", step: group.label, parameter: column.label, from: null, to: cell.text });
      });
      const statuses = new Set(mine.map((cell) => cell.status));
      ["added_layer", "moved", "absent"].forEach((kind) => statuses.has(kind) && found.push({ kind, step: group.label, parameter: null, from: null, to: null }));
      start += width;
    }
    return found;
  }

  const DIFF = {
    changed: { mark: "≠", word: "modifié" },
    added_param: { mark: "+", word: "paramètre ajouté" },
    added_layer: { mark: "+", word: "couche en plus" },
    moved: { mark: "↕", word: "étape déplacée" },
    absent: { mark: "−", word: "couche absente" },
  };

  function diffHtml(item) {
    const d = DIFF[item.kind] || { mark: "•", word: item.kind };
    const what = item.parameter ? `${esc(item.step)} · ${esc(item.parameter)}` : esc(item.step);
    const change = item.kind === "changed" ? ` : <span class="mono">${esc(item.from)}</span> → <span class="mono">${esc(item.to)}</span>` : item.kind === "added_param" ? ` : <span class="mono">${esc(item.to)}</span>` : "";
    return `<li class="diff diff--${esc(item.kind)}"><span class="diff__mark" aria-hidden="true">${d.mark}</span><span>${what}${change} <span class="diff__word">${d.word}</span></span></li>`;
  }

  const dot = (color) => `<span class="dot" style="background:${safeColor(color)}"></span>`;
  const paragraphs = (text) => esc(text).replace(/\n{2,}/g, "</p><p>").replace(/\n/g, "<br>");

  // -- les sections ---------------------------------------------------------------------------------

  function waferCard(w) {
    const facts = (w.facts || []).map((f) => `<tr><th>${esc(f.label)}</th><td>${esc(f.value)}</td></tr>`).join("");
    return `<article class="plate${w.isRef ? " plate--ref" : ""}">
      <header class="plate__head">${dot(w.color)}<span class="mono plate__name">${esc(w.lasermark)}</span>${w.isRef ? `<span class="badge">Référence</span>` : ""}</header>
      <div class="plate__figure">${w.structure && w.structure.svg ? w.structure.svg : `<p class="empty">Pas de structure dessinée</p>`}</div>
      ${w.structure && w.structure.caption ? `<p class="plate__caption">${esc(w.structure.caption)}</p>` : ""}
      ${facts ? `<table class="facts">${facts}</table>` : ""}
    </article>`;
  }

  function verdictWord(verdict) {
    return verdict === "better" ? " · mieux" : verdict === "worse" ? " · moins bien" : "";
  }

  function differenceCard(d) {
    const structural = !d.comparable
      ? `<p class="empty">Pas de structure d'étude à comparer à la référence.</p>`
      : d.items.length
        ? `<ul class="diffs">${d.items.map(diffHtml).join("")}</ul>`
        : `<p class="same">Même structure que la référence.</p>`;
    const kpis = d.kpis.length
      ? `<ul class="moves">${d.kpis.map((k) => `<li><span>${esc(k.title)}</span><span class="delta${k.verdict ? ` delta--${esc(k.verdict)}` : ""}">${esc(k.text)}${verdictWord(k.verdict)}</span></li>`).join("")}</ul>`
      : `<p class="empty">Aucun KPI mesuré à comparer.</p>`;
    return `<article class="card versus">
      <header class="versus__head">${dot(d.color)}<span class="mono plate__name">${esc(d.lasermark)}</span><span class="versus__vs">face à la référence</span></header>
      <div class="versus__body">
        <div><h4>Ce qui diffère</h4>${structural}</div>
        <div><h4>Ce qui bouge</h4>${kpis}</div>
      </div>
    </article>`;
  }

  function kpiCard(k) {
    const head = `<header class="kpi__head"><h3>${esc(k.title)}</h3><span class="kpi__source">${esc(k.source)}</span>${k.better ? `<span class="pill">${k.better === "high" ? "plus haut = mieux" : "plus bas = mieux"}</span>` : ""}</header>`;
    if (k.status !== "ok") return `<article class="card kpi">${head}<p class="empty">${esc(k.message)}</p></article>`;
    const rows = k.rows
      .map(
        (r) => `<tr${r.isRef ? ` class="is-ref"` : ""}><th>${dot(r.color)}<span class="mono">${esc(r.lasermark)}</span>${r.isRef ? ` <span class="badge">Réf.</span>` : ""}</th>
          <td class="mono">${esc(r.n)}</td><td class="mono">${esc(r.median)}</td>
          <td><span class="delta${r.verdict ? ` delta--${esc(r.verdict)}` : ""}">${esc(r.delta)}${verdictWord(r.verdict)}</span></td><td class="mono">${esc(r.date)}</td></tr>`
      )
      .join("");
    return `<article class="card kpi">${head}
      ${k.svg ? `<div class="kpi__plot">${k.svg}</div>` : ""}
      <table class="grid"><thead><tr><th>Plaque</th><th>n</th><th>Médiane</th><th>Écart à la réf.</th><th>Mesure du</th></tr></thead><tbody>${rows}</tbody></table>
    </article>`;
  }

  function contextCard(w) {
    const notes = w.notes || {};
    const fields = [
      ["Pourquoi elle est là", notes.context],
      ["Ce qu'on voulait voir", notes.hypothesis],
      ["Ce qu'on a compris grâce à elle", notes.learnings],
    ].filter(([, text]) => text);
    const studies = (w.studies || [])
      .map(
        (s) => `<li><strong>${esc(s.title)}</strong>${s.status ? ` <span class="pill pill--mute">${esc(s.status)}</span>` : ""}${s.conclusion ? `<p>${paragraphs(s.conclusion)}</p>` : ""}${s.next ? `<p class="next"><strong>Suite :</strong> ${esc(s.next)}</p>` : ""}</li>`
      )
      .join("");
    if (!fields.length && !studies) return "";
    return `<article class="card context">
      <header class="plate__head">${dot(w.color)}<span class="mono plate__name">${esc(w.lasermark)}</span>${w.isRef ? `<span class="badge">Référence</span>` : ""}</header>
      ${fields.map(([label, text]) => `<div class="field"><h4>${esc(label)}</h4><p>${paragraphs(text)}</p></div>`).join("")}
      ${studies ? `<div class="field"><h4>Ses études</h4><ul class="studies">${studies}</ul></div>` : ""}
    </article>`;
  }

  const CSS = `
:root{--navy:#0d1b3e;--navy-500:#23408e;--gold:#c9a84c;--gold-dark:#8a6d1f;--gold-tint:#f7f1e1;--bg:#f5f6fa;--surface:#fff;--surface-2:#f9fafc;--border:#dde2ec;--border-soft:#e8ebf2;--text:#1b2440;--text-soft:#4a5470;--text-faint:#646e8c;--accent-tint-strong:#dbe1f0;--link:#23408e;--done:#37703f;--danger:#b5392f;--continue:#6f4fa3;--hold:#9f5c00;--viz-1:#1d6fae;--viz-2:#c08a1e;--viz-3:#37803f;--viz-4:#b5392f;--viz-5:#6f4fa3;--viz-6:#1f8a8a;--viz-7:#97502f;--viz-8:#5e6573;--font-ui:"DM Sans","Helvetica Neue",Arial,system-ui,sans-serif;--font-mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;font-family:var(--font-ui);color:var(--text);background:var(--bg);-webkit-font-smoothing:antialiased;line-height:1.45}
.mono{font-family:var(--font-mono)}
.top{display:flex;align-items:center;gap:16px;padding:10px 32px;background:linear-gradient(100deg,#060e22 0%,var(--navy) 40%,var(--navy-500) 100%);color:#fff;border-bottom:3px solid var(--gold)}
.top__brand{display:flex;align-items:center;gap:12px;padding-right:16px;border-right:1px solid rgba(255,255,255,.22)}
.top__logo{display:block;height:26px;width:auto}
.top__name{font-weight:600;font-size:14px;letter-spacing:.32em;text-transform:uppercase}
.top__kind{font-size:13px;color:#b9c3e0}
.top__date{margin-left:auto;font-family:var(--font-mono);font-size:12px;color:#e8c97a}
main{max-width:1180px;margin:0 auto;padding:28px 32px 48px}
h1{margin:0 0 8px;font-size:32px;line-height:1.15;color:var(--navy)}
h2{margin:36px 0 14px;font-family:var(--font-mono);font-size:12px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:var(--text-faint);display:flex;align-items:center;gap:10px}
h2::before{content:"";width:24px;height:2px;background:var(--gold)}
h3{margin:0;font-size:16px;color:var(--navy)}
h4{margin:0 0 6px;font-family:var(--font-mono);font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text-faint)}
.question{margin:0 0 10px;padding:12px 16px;border-left:4px solid var(--gold);background:var(--gold-tint);border-radius:0 10px 10px 0;font-size:16px;white-space:pre-line}
.byline{margin:0;color:var(--text-faint);font-size:13px}
.lineup{display:flex;flex-wrap:wrap;gap:6px 14px;margin:14px 0 0;font-size:13.5px}
.lineup>span{display:inline-flex;align-items:center}
.lineup__ref{margin-left:5px;color:var(--text-faint)}
.card{background:var(--surface);border:1px solid var(--border-soft);border-radius:10px;padding:14px 16px;box-shadow:0 1px 2px rgba(13,27,62,.05),0 2px 8px rgba(13,27,62,.05);break-inside:avoid;page-break-inside:avoid}
.dot{display:inline-block;flex:none;width:10px;height:10px;border-radius:50%;margin-right:7px}
.badge{display:inline-block;margin-left:8px;padding:0 7px;border-radius:999px;background:var(--gold-tint);color:var(--gold-dark);border:1px solid var(--gold);font-family:var(--font-mono);font-size:10.5px;font-weight:600;text-transform:uppercase;letter-spacing:.05em}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;background:var(--gold-tint);color:var(--gold-dark);font-family:var(--font-mono);font-size:11px}
.pill--mute{background:var(--surface-2);color:var(--text-soft);border:1px solid var(--border)}
.plates{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:14px}
.plate{background:var(--surface);border:1px solid var(--border-soft);border-radius:10px;padding:12px;display:flex;flex-direction:column;gap:8px;break-inside:avoid;page-break-inside:avoid}
.plate--ref{border-top:3px solid var(--gold)}
.plate__head{display:flex;align-items:center;margin-bottom:6px}
.plate__name{font-weight:600;color:var(--navy)}
.plate__figure{height:200px;display:flex;align-items:center;justify-content:center;background:var(--surface-2);border:1px solid var(--border-soft);border-radius:8px;padding:6px;overflow:hidden}
.plate__figure svg,.plate__figure img{max-width:100%;max-height:100%}
.plate__caption{margin:0;font-size:12.5px;color:var(--text-soft)}
.facts{width:100%;border-collapse:collapse;font-size:12.5px}
.facts th{text-align:left;font-family:var(--font-mono);font-size:10.5px;font-weight:500;color:var(--text-faint);padding:3px 10px 3px 0;vertical-align:top;white-space:nowrap}
.facts td{padding:3px 0;overflow-wrap:anywhere}
.stack{display:flex;flex-direction:column;gap:12px}
.versus__head{display:flex;align-items:center;margin-bottom:10px}
.versus__vs{margin-left:8px;font-size:12.5px;color:var(--text-faint)}
.versus__body{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.diffs,.moves,.studies{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:5px;font-size:13.5px}
.diff{display:flex;gap:8px;align-items:baseline}
.diff__mark{flex:none;display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:4px;font-size:12px;font-weight:700}
.diff--changed .diff__mark{background:#fbeae8;color:var(--danger)}
.diff--added_param .diff__mark{background:#f1ecf8;color:var(--continue)}
.diff--added_layer .diff__mark{background:#e7f3e8;color:var(--done)}
.diff--moved .diff__mark{background:#fdf5e8;color:var(--hold)}
.diff--absent .diff__mark{background:var(--surface-2);color:var(--text-faint);border:1px dashed var(--border)}
.diff__word{color:var(--text-faint);font-size:12px}
.moves li{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid var(--border-soft);padding-bottom:4px}
.same{margin:0;color:var(--done);font-size:13.5px}
.empty{margin:0;color:var(--text-faint);font-size:13px}
.delta{font-family:var(--font-mono);font-size:12.5px;white-space:nowrap;color:var(--text-soft)}
.delta--better{color:var(--done);font-weight:600}
.delta--worse{color:var(--danger);font-weight:600}
.kpi__head{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 12px;margin-bottom:8px}
.kpi__source{font-family:var(--font-mono);font-size:11.5px;color:var(--text-faint)}
.kpi__plot{overflow-x:auto}
.kpi__plot svg{max-width:100% !important;height:auto}
.grid{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
.grid th,.grid td{padding:5px 10px;text-align:left;border-bottom:1px solid var(--border-soft);vertical-align:top}
.grid thead th{font-family:var(--font-mono);font-size:10.5px;font-weight:500;color:var(--text-faint)}
.grid tbody th{font-weight:500;white-space:nowrap}
.grid tr.is-ref{background:var(--gold-tint)}
.sheet__figure{display:flex;flex-direction:column;gap:8px}
.sheet__figure .wd-svg{max-width:720px}
.wd-axis-title{font-family:var(--font-mono);font-size:10px;fill:var(--text-soft)}
.wd-box__body{fill-opacity:.2;stroke-width:1.5}
.wd-box__median{stroke:var(--navy);stroke-width:2.5}
.wd-whisker{stroke-width:1.4}
.wd-outlier{fill:var(--surface);stroke-width:1.3}
.wd-dot{fill-opacity:.72}
.ma-image-rows{display:flex;flex-direction:column;gap:12px}
.ma-image-row__who{display:flex;align-items:center;gap:8px;font-size:12.5px}
.wd-images__grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px;margin-top:4px}
.wd-image{display:flex;flex-direction:column;gap:3px;border:1px solid var(--border-soft);border-radius:6px;padding:4px;background:var(--surface-2)}
.wd-image img{width:100%;aspect-ratio:4/3;object-fit:contain;background:var(--surface)}
.wd-image__name{font-family:var(--font-mono);font-size:10px;color:var(--text-faint);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.field{margin-top:10px}
.field p{margin:0 0 6px;font-size:14px}
.studies li p{margin:4px 0 0;font-size:13.5px}
.next{color:var(--text-soft)}
.conclusion{font-size:15.5px;border-left:4px solid var(--gold)}
.conclusion p{margin:0 0 8px}
footer{margin-top:40px;font-size:12px;color:var(--text-faint);border-top:1px solid var(--border);padding-top:10px}
.kt-plot-axis,.wd-axis{stroke:var(--border);stroke-width:1}
.kt-plot-grid,.wd-grid{stroke:var(--border-soft);stroke-width:1}
.kt-plot-tick,.wd-tick{font-family:var(--font-mono);font-size:10.5px;fill:var(--text-faint)}
.kt-plot-tick--strong{fill:var(--text-soft);font-weight:500}
.kt-plot-empty{font-size:11px;fill:var(--text-faint)}
.wd-svg{width:100%;height:auto;display:block;overflow:visible}
.wd-bar{fill:var(--viz-1)}
.wd-median{stroke:var(--gold-dark);stroke-width:1.5;stroke-dasharray:4 3}
.wd-band{fill:var(--accent-tint-strong);stroke:none}
.wd-map{display:flex;align-items:center;gap:8px;max-width:100%}
.wd-map__grid{max-width:calc(100% - 72px);height:auto;background:var(--surface-2);border-radius:4px}
.ma-curve{fill:none;stroke-width:1.8;stroke-linejoin:round;stroke-opacity:.9}
.ma-curve--ref{stroke-width:3;stroke-opacity:1}
.ma-small-multiples{display:flex;flex-wrap:wrap;gap:16px}
.ma-multiple{margin:0;display:flex;flex-direction:column;gap:6px}
.ma-multiple--wide{flex:1 1 260px;max-width:360px}
.ma-multiple figcaption,.ma-legend{font-size:12.5px;display:flex;align-items:center;flex-wrap:wrap;gap:4px 14px;margin:0}
.ma-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px}
.wd-chart__caption{margin:0;font-size:12.5px;color:var(--text-soft)}
.ma-kpi__table{width:100%;border-collapse:collapse;font-size:13px}
.ma-kpi__table th,.ma-kpi__table td{padding:5px 10px;text-align:left;border-bottom:1px solid var(--border-soft);vertical-align:top}
.ma-kpi__table thead th{font-family:var(--font-mono);font-size:10.5px;font-weight:500;color:var(--text-faint)}
.ma-delta{font-family:var(--font-mono);font-size:12px;white-space:nowrap;color:var(--text-soft)}
.ma-delta--better{color:var(--done);font-weight:600}
.ma-delta--worse{color:var(--danger);font-weight:600}
.ma-chip__ref{font-family:var(--font-mono);font-size:10.5px;font-weight:600;text-transform:uppercase;color:var(--gold-dark)}
.help{color:var(--text-faint);font-size:12.5px}
@media (max-width:760px){main{padding:20px 16px 40px}.versus__body{grid-template-columns:1fr}.top{padding:10px 16px}}
@media print{body{background:#fff}.top{-webkit-print-color-adjust:exact;print-color-adjust:exact}main{max-width:none;padding:16px 0}h2{break-after:avoid}}
`;

  // Une section de dessins déjà rendus (blocs libres, fiche data) ; rien sans dessin. title : un texte de la page.
  function figures(title, list) {
    if (!(list || []).length) return "";
    return `<h2>${title}</h2><div class="stack">${list
      .map((s) => `<article class="card"><header class="kpi__head"><h3>${esc(s.title)}</h3><span class="kpi__source">${esc(s.kind)}</span></header><div class="sheet__figure">${s.figure}</div></article>`)
      .join("")}</div>`;
  }

  function build(report) {
    const wafers = report.wafers || [];
    const ref = wafers.find((w) => w.isRef);
    const lineup = wafers.map((w) => `<span>${dot(w.color)}<span class="mono">${esc(w.lasermark)}</span>${w.isRef ? `<span class="lineup__ref">(réf.)</span>` : ""}</span>`).join("");
    const contexts = wafers.map(contextCard).filter(Boolean);
    const sections = [
      `<h2>Les plaques côte à côte</h2><div class="plates">${wafers.map(waferCard).join("")}</div>`,
      (report.differences || []).length
        ? `<h2>Ce qui diffère de la référence, ce qui bouge</h2><div class="stack">${report.differences.map(differenceCard).join("")}</div>`
        : "",
      (report.kpis || []).length ? `<h2>KPI face à la référence</h2><div class="stack">${report.kpis.map(kpiCard).join("")}</div>` : "",
      figures("Données choisies pour l'analyse", report.blocks),
      figures("Fiche data des plaques", report.sheets),
      contexts.length ? `<h2>Contexte et enseignements de chaque plaque</h2><div class="stack">${contexts.join("")}</div>` : "",
      `<h2>Ce qu'on a compris</h2><div class="card conclusion">${report.conclusion ? `<p>${paragraphs(report.conclusion)}</p>` : `<p class="empty">Pas encore de conclusion.</p>`}</div>`,
    ];
    return `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(report.title)} — analyse de plaques</title>
<style>${CSS}</style>
</head>
<body>
<header class="top">
  <div class="top__brand">${report.logoSvg ? report.logoSvg.replace("<svg", '<svg class="top__logo" aria-hidden="true"') : ""}<span class="top__name">Spectre</span></div>
  <span class="top__kind">Analyse de plaques</span>
  <span class="top__date">${esc(report.date)}</span>
</header>
<main>
  <h1>${esc(report.title)}</h1>
  ${report.question ? `<p class="question">${esc(report.question)}</p>` : ""}
  <p class="byline">${esc(report.byline)}${ref ? ` · référence <span class="mono">${esc(ref.lasermark)}</span>` : ""} · ${wafers.length} plaque${wafers.length > 1 ? "s" : ""}</p>
  <div class="lineup">${lineup}</div>
  ${sections.join("")}
  <footer>Rapport fait par Spectre le ${esc(report.date)} : un instantané de l'analyse - structures, données et notes telles qu'elles étaient ce jour-là.</footer>
</main>
</body>
</html>`;
  }

  return { build, differences, esc };
})();
