/* Le rapport pas à pas, fabriqué : un diaporama HTML d'un seul fichier, sans rien à charger (ni
   police, ni script, ni image distante - il s'ouvre hors ligne, se transmet tel quel et s'imprime
   en PDF, une diapositive par page).

   StepReportHtml.build(report) -> le document HTML (une chaîne). Pur : il ne lit ni la page ni le
   serveur, tout vient de `report`, que step-report.js compose à partir de l'état du constructeur :

     {
       title, subtitle, date,                      // textes simples ; logoSvg : le logo Aledia (un <svg>, facultatif)
       cover: {svg, materials: [{name, color}], stats: [{label, value}]},
       start: {svg, materials, params},            // le substrat : la structure avant la première étape (sans commentaire : pas une étape)
       steps: [{index, kind, kindLabel, color, tint, name, summary, tags: [texte], svg, materials,
                params: [{label, value, declared, detail}], comment}]
     }

   Chaque diapositive porte le dessin de la structure *après* l'étape, les paramètres sur le côté
   (ceux du formulaire de l'étape, et les paramètres déclarés, marqués), le commentaire et un rappel
   du code couleur (les matériaux du dessin) ; un stepper, en bas, saute d'une étape à l'autre
   (clic, flèches du clavier, #numéro dans l'adresse). */

const StepReportHtml = (() => {
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  // Une couleur n'entre dans un attribut style que si c'est une couleur : jamais du CSS libre.
  function safeColor(color, fallback) {
    return /^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%]+\)|[a-z]{3,20})$/i.test(String(color || "")) ? color : fallback;
  }

  const CSS = `
:root{--navy:#0d1b3e;--navy-700:#122052;--navy-500:#23408e;--gold:#c9a84c;--gold-dark:#8a6d1f;--gold-tint:#f7f1e1;--bg:#f5f6fa;--surface:#fff;--surface-2:#f9fafc;--border:#dde2ec;--border-soft:#e8ebf2;--text:#1b2440;--text-soft:#4a5470;--text-faint:#646e8c;--font-ui:"DM Sans","Helvetica Neue",Arial,system-ui,sans-serif;--font-mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{font-family:var(--font-ui);color:var(--text);background:var(--bg);display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}
.top{flex:none;display:flex;align-items:center;gap:16px;padding:10px 24px;background:linear-gradient(100deg,#060e22 0%,var(--navy) 40%,var(--navy-500) 100%);color:#fff;border-bottom:3px solid var(--gold)}
.top__brand{flex:none;display:flex;align-items:center;gap:12px;padding-right:16px;border-right:1px solid rgba(255,255,255,.22)}
.top__logo{display:block;height:26px;width:auto}
.top__name{font-weight:600;font-size:14px;letter-spacing:.32em;text-transform:uppercase;color:#fff}
.top__title{font-weight:600;font-size:15px;letter-spacing:.01em;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.top__sub{color:#b9c3e0;font-size:13px;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.top__count{margin-left:auto;flex:none;font-family:var(--font-mono);font-size:12px;color:var(--gold-light,#e8c97a)}
.deck{flex:1;min-height:0;position:relative}
.slide{position:absolute;inset:0;display:none;padding:20px 24px 12px;gap:20px;flex-direction:column}
.slide.is-current{display:flex}
.slide__body{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,1.7fr) minmax(280px,1fr);grid-template-rows:minmax(0,1fr);gap:20px}
.draw{display:flex;flex-direction:column;min-height:0;background:var(--surface);border:1px solid var(--border-soft);border-radius:10px;box-shadow:0 1px 2px rgba(13,27,62,.05),0 2px 8px rgba(13,27,62,.05)}
.draw__svg{flex:1;min-height:0;overflow:hidden;padding:16px}
.draw__svg svg{display:block;width:100%;height:100%}
.draw__svg [data-layer-index].sbr-new{stroke:var(--gold);stroke-width:2.5px;vector-effect:non-scaling-stroke}
.legend{flex:none;display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;padding:10px 16px;border-top:1px solid var(--border-soft);font-size:13px;color:var(--text-soft)}
.legend__title{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text-faint)}
.legend__item{display:inline-flex;align-items:center;gap:6px}
.legend__swatch{width:14px;height:14px;border-radius:3px;border:1px solid rgba(13,27,62,.25);flex:none}
.legend__hint{margin-left:auto;display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--text-faint)}
.legend__hint i{width:14px;height:14px;border-radius:3px;border:2.5px solid var(--gold);flex:none}
.side{min-height:0;overflow:auto;display:flex;flex-direction:column;gap:14px;padding-right:2px}
.head{display:flex;flex-direction:column;gap:6px}
.kind{align-self:flex-start;display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
.head h1{margin:0;font-size:26px;line-height:1.15;color:var(--navy)}
.head__summary{font-family:var(--font-mono);font-size:12.5px;color:var(--text-soft)}
.tags{display:flex;flex-wrap:wrap;gap:6px}
.tag{padding:1px 8px;border-radius:999px;background:var(--surface);border:1px solid var(--border);font-size:11.5px;color:var(--text-soft)}
.card{background:var(--surface);border:1px solid var(--border-soft);border-radius:10px;padding:12px 14px}
.card__title{margin:0 0 8px;font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text-faint)}
.params{width:100%;border-collapse:collapse;font-size:14px}
.params th,.params td{padding:5px 0;border-bottom:1px solid var(--border-soft);vertical-align:top;text-align:left}
.params tr:last-child th,.params tr:last-child td{border-bottom:0}
.params th{font-weight:500;color:var(--text-soft);padding-right:12px;width:42%}
.params td{font-family:var(--font-mono);font-size:13px;color:var(--text)}
.params small{display:block;margin-top:2px;font-family:var(--font-ui);font-size:11.5px;color:var(--text-faint)}
.badge{display:inline-block;margin-left:6px;padding:0 6px;border-radius:999px;background:var(--gold-tint);color:var(--gold-dark);border:1px solid var(--gold);font-family:var(--font-ui);font-size:10.5px;font-weight:600;vertical-align:1px}
.empty{margin:0;font-size:13px;color:var(--text-faint)}
.comment{border-left:4px solid var(--gold);background:var(--gold-tint);border-radius:0 10px 10px 0;padding:12px 14px}
.comment p{margin:0;white-space:pre-wrap;font-size:14.5px;line-height:1.5;color:var(--text)}
.comment--none{border-left-color:var(--border);background:var(--surface-2)}
.cover{justify-content:center}
.cover h1{margin:0 0 4px;font-size:40px;color:var(--navy)}
.cover__sub{margin:0 0 16px;font-size:17px;color:var(--text-soft)}
.stats{display:flex;flex-wrap:wrap;gap:12px;margin-top:6px}
.stat{padding:8px 14px;background:var(--surface);border:1px solid var(--border-soft);border-radius:10px}
.stat b{display:block;font-size:20px;color:var(--navy)}
.stat span{font-size:12px;color:var(--text-faint)}
.stepper{flex:none;display:flex;align-items:center;gap:10px;padding:10px 24px 14px;background:var(--surface);border-top:1px solid var(--border)}
.stepper__nav{flex:none;width:34px;height:34px;border-radius:8px;border:1px solid var(--border);background:var(--surface-2);color:var(--navy);font-size:18px;line-height:1;cursor:pointer}
.stepper__nav:hover:not(:disabled){border-color:var(--navy-500);background:#e9edf7}
.stepper__nav:disabled{opacity:.35;cursor:default}
.stepper__track{flex:1;min-width:0;display:flex;gap:6px;overflow-x:auto;padding:4px 2px}
.chip{flex:none;min-width:38px;height:34px;padding:0 10px;display:inline-flex;align-items:center;justify-content:center;gap:6px;border-radius:8px;border:1px solid var(--border);border-top:4px solid var(--chip,#8a93ad);background:var(--surface-2);color:var(--text-soft);font:600 12.5px var(--font-mono);cursor:pointer}
.chip:hover{border-color:var(--navy-500)}
.chip.is-current{background:var(--navy);border-color:var(--navy);border-top-color:var(--gold);color:#fff}
.chip.has-comment::after{content:"";width:6px;height:6px;border-radius:50%;background:var(--gold)}
.chip:focus-visible,.stepper__nav:focus-visible{outline:3px solid rgba(35,64,142,.35);outline-offset:1px}
@media (max-width:860px){.slide__body{grid-template-columns:1fr;overflow:auto}.draw{min-height:260px}}
@page{size:A4 landscape;margin:10mm}
@media print{
  html,body{height:auto;background:#fff;display:block}
  .top{position:static;padding:6px 12px;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .deck{position:static}
  .slide,.slide.is-current{position:static;display:flex;height:182mm;padding:8px 4px;break-after:page;page-break-after:always}
  .slide:last-child{break-after:auto;page-break-after:auto}
  .stepper{display:none}
  .side{overflow:visible}
  *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}`;

  // Le comportement du stepper, tel quel dans le fichier : aucune donnée n'y passe.
  const SCRIPT = `
(function(){
  var slides=[].slice.call(document.querySelectorAll(".slide"));
  var chips=[].slice.call(document.querySelectorAll(".chip"));
  var prev=document.getElementById("prev"),next=document.getElementById("next"),count=document.getElementById("count");
  var cur=0;
  function show(i,fromHash){
    cur=Math.max(0,Math.min(slides.length-1,i));
    slides.forEach(function(s,k){s.classList.toggle("is-current",k===cur)});
    chips.forEach(function(c,k){c.classList.toggle("is-current",k===cur);if(k===cur){c.setAttribute("aria-current","step");c.scrollIntoView({block:"nearest",inline:"nearest"})}else c.removeAttribute("aria-current")});
    prev.disabled=cur===0;next.disabled=cur===slides.length-1;
    count.textContent=slides[cur].getAttribute("data-count")||"";
    if(!fromHash){try{history.replaceState(null,"","#"+cur)}catch(e){}}
  }
  prev.addEventListener("click",function(){show(cur-1)});
  next.addEventListener("click",function(){show(cur+1)});
  chips.forEach(function(c,k){c.addEventListener("click",function(){show(k)})});
  document.addEventListener("keydown",function(e){
    if(e.altKey||e.ctrlKey||e.metaKey)return;
    if(e.key==="ArrowRight"||e.key==="PageDown"||e.key===" "){e.preventDefault();show(cur+1)}
    else if(e.key==="ArrowLeft"||e.key==="PageUp"){e.preventDefault();show(cur-1)}
    else if(e.key==="Home"){e.preventDefault();show(0)}
    else if(e.key==="End"){e.preventDefault();show(slides.length-1)}
  });
  window.addEventListener("hashchange",function(){var n=parseInt(location.hash.slice(1),10);if(!isNaN(n))show(n,true)});
  var start=parseInt(location.hash.slice(1),10);show(isNaN(start)?0:start,true);
})();`;

  function legendHtml(materials, hint) {
    const items = (materials || [])
      .map((m) => `<span class="legend__item"><span class="legend__swatch" style="background:${esc(safeColor(m.color, "#c3c8d4"))}"></span>${esc(m.name)}</span>`)
      .join("");
    return `<div class="legend" aria-label="Code couleur"><span class="legend__title">Code couleur</span>${items}${hint ? `<span class="legend__hint"><i></i>couches de cette étape</span>` : ""}</div>`;
  }

  function drawHtml(svg, materials, hint) {
    return `<div class="draw"><div class="draw__svg">${svg || ""}</div>${legendHtml(materials, hint)}</div>`;
  }

  function paramsHtml(params) {
    if (!params || !params.length) return `<div class="card"><h2 class="card__title">Paramètres</h2><p class="empty">Aucun paramètre.</p></div>`;
    const rows = params
      .map((p) => {
        const badge = p.declared ? `<span class="badge">déclaré</span>` : "";
        const detail = p.detail ? `<small>${esc(p.detail)}</small>` : "";
        return `<tr><th scope="row">${esc(p.label)}</th><td>${esc(p.value)}${badge}${detail}</td></tr>`;
      })
      .join("");
    return `<div class="card"><h2 class="card__title">Paramètres</h2><table class="params">${rows}</table></div>`;
  }

  function commentHtml(comment) {
    const text = (comment || "").trim();
    if (!text) return `<div class="comment comment--none"><p class="empty">Pas de commentaire sur cette étape.</p></div>`;
    return `<div class="comment"><h2 class="card__title" style="color:var(--gold-dark)">Commentaire</h2><p>${esc(text)}</p></div>`;
  }

  function slideHtml(count, inner, extraClass) {
    return `<section class="slide${extraClass ? " " + extraClass : ""}" data-count="${esc(count)}">${inner}</section>`;
  }

  function chipHtml(label, title, color, hasComment) {
    return `<button type="button" class="chip${hasComment ? " has-comment" : ""}" style="--chip:${esc(safeColor(color, "#8a93ad"))}" title="${esc(title)}">${esc(label)}</button>`;
  }

  function build(report) {
    const steps = report.steps || [];
    const total = steps.length;
    const title = report.title || "Structure";
    const cover = report.cover || {};
    const start = report.start || {};
    // le logo Aledia, inline (le rapport n'a rien à charger) : un <svg> fourni par la page, rien d'autre
    const logo = /^\s*<svg[\s>]/.test(report.logoSvg || "") ? report.logoSvg.replace(/^\s*<svg/, '<svg class="top__logo"') : "";

    const stats = (cover.stats || []).map((s) => `<div class="stat"><b>${esc(s.value)}</b><span>${esc(s.label)}</span></div>`).join("");
    const slides = [
      slideHtml(
        "Titre",
        `<div class="slide__body cover" style="grid-template-columns:minmax(0,1fr) minmax(0,1.3fr)">
          <div style="align-self:center"><h1>${esc(title)}</h1>${report.subtitle ? `<p class="cover__sub">${esc(report.subtitle)}</p>` : ""}<div class="stats">${stats}</div></div>
          ${drawHtml(cover.svg, cover.materials, false)}
        </div>`
      ),
      slideHtml(
        `Point de départ · 0 / ${total}`,
        `<div class="slide__body">
          ${drawHtml(start.svg, start.materials, false)}
          <div class="side">
            <div class="head"><span class="kind" style="background:#e9edf7;color:var(--navy)">Point de départ</span><h1>Substrat</h1></div>
            ${paramsHtml(start.params)}
          </div>
        </div>`
      ),
      ...steps.map((step) => {
        const tags = (step.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
        return slideHtml(
          `Étape ${step.index} / ${total}`,
          `<div class="slide__body">
            ${drawHtml(step.svg, step.materials, true)}
            <div class="side">
              <div class="head">
                <span class="kind" style="background:${esc(safeColor(step.tint, "#eceef2"))};color:${esc(safeColor(step.color, "#1b2440"))}">${esc(step.kindLabel)}</span>
                <h1>${esc(step.name)}</h1>
                ${step.summary ? `<div class="head__summary">${esc(step.summary)}</div>` : ""}
                ${tags ? `<div class="tags">${tags}</div>` : ""}
              </div>
              ${paramsHtml(step.params)}
              ${commentHtml(step.comment)}
            </div>
          </div>`
        );
      }),
    ];

    const chips = [
      chipHtml("★", "Titre", "#c9a84c", false),
      chipHtml("0", "Substrat", "#5b5f66", false),
      ...steps.map((s) => chipHtml(String(s.index), `${s.index}. ${s.name}`, s.color, Boolean((s.comment || "").trim()))),
    ].join("");

    return `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)} — rapport étape par étape</title>
<style>${CSS}</style>
</head>
<body>
<header class="top"><div class="top__brand">${logo}<span class="top__name">Spectre</span></div><span class="top__title">${esc(title)}</span>${report.date ? `<span class="top__sub">${esc(report.date)}</span>` : ""}<span class="top__count" id="count"></span></header>
<main class="deck">${slides.join("\n")}</main>
<nav class="stepper" aria-label="Étapes du procédé"><button type="button" class="stepper__nav" id="prev" aria-label="Étape précédente">&#8249;</button><div class="stepper__track">${chips}</div><button type="button" class="stepper__nav" id="next" aria-label="Étape suivante">&#8250;</button></nav>
<script>${SCRIPT}</script>
</body>
</html>`;
  }

  return { build, esc };
})();
