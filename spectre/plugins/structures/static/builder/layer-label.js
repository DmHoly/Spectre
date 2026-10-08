/* Étiquettes de couches : dans l'inspecteur d'une étape qui crée une couche, la section « Afficher
   sur la structure » - une case, le texte (prérempli du matériau), les valeurs écrites dessous
   (épaisseur, composition d'un nitrure, paramètres déclarés de l'étape). L'étiquette vit sur
   l'étape (step.layerLabel) et voyage à part dans l'API, par position d'étape, comme les paramètres
   déclarés ; c'est le serveur qui la dessine - l'aperçu compris -, reliée à la couche que l'étape a
   créée (spectre/plugins/structures/rendering.py). Seules les étapes choisies en portent une.
   Une étape qui ne crée pas de couche (nettoyage, gravure, etch back...) porte une marque
   d'interface : la même étiquette, reliée en pointillé à la surface telle qu'elle était quand
   l'étape a eu lieu, entre les couches d'avant et celles d'après. */

// Les types d'étape qui créent une couche ; un nitrure à composition se reconnaît à son nom
// (GRADED_NITRIDE_RE, form-widgets.js).
const LAYER_STEP_KINDS = new Set(["deposition", "epitaxial_growth", "faceted_growth", "facet_envelope", "lithography"]);
// Ceux qui n'en créent pas : une marque d'interface (simulation.INTERFACE_STEP_KINDS côté serveur).
const INTERFACE_STEP_KINDS = new Set(["etch", "planarization", "chemical", "resist_strip"]);
const LABELLED_STEP_KINDS = new Set([...LAYER_STEP_KINDS, ...INTERFACE_STEP_KINDS]);
// Ce qui, d'une étiquette, n'est que sa place sur le dessin : son texte déplacé (offset) et son point
// d'accroche posé à la main (anchor) - simulation.LABEL_PLACE_KEYS côté serveur.
const LABEL_PLACES = [
  { key: "offset", text: "Texte déplacé à la main sur le dessin" },
  { key: "anchor", text: "Point d'accroche posé à la main" },
];

// {index d'étape: {text, values}} à l'envoi ; rattachées à chaque étape (step.layerLabel) au
// chargement d'un procédé, d'une structure ou d'une brique enregistrés.
function layerLabelsPayload(steps) {
  const out = {};
  steps.forEach((step, i) => {
    if (step.layerLabel) out[i] = step.layerLabel;
  });
  return out;
}

function attachLayerLabels(steps, labels) {
  if (!labels) return steps;
  return steps.map((step, i) => {
    const label = labels[i] || labels[String(i)];
    if (!label) return step;
    const layerLabel = { text: label.text || "", values: [...(label.values || [])] };
    LABEL_PLACES.forEach(({ key }) => {
      if (Array.isArray(label[key])) layerLabel[key] = [...label[key]];
    });
    return { ...step, layerLabel };
  });
}

// Le texte proposé quand on coche la case : le matériau d'une couche, le nom d'une étape sans couche.
function layerLabelDefaultText(step) {
  if (!step) return "";
  if (INTERFACE_STEP_KINDS.has(step.kind)) return step.name || "";
  return step.material || step.resist_material || "";
}

// Les valeurs qu'une étape peut écrire sous son étiquette.
function layerLabelOptions(step) {
  const options = [];
  if (step.thickness) options.push({ key: "thickness", label: "Épaisseur" });
  if (step.depth) options.push({ key: "depth", label: "Profondeur" });
  if (GRADED_NITRIDE_RE.test(step.material || "")) options.push({ key: "composition", label: "Composition (taux d'In / d'Al)" });
  (step.declaredParams || []).forEach((param) => {
    if (param.name) options.push({ key: `declared:${param.name}`, label: `${param.name} (paramètre déclaré)` });
  });
  return options;
}

function layerLabelSectionHtml(kind) {
  if (!LABELLED_STEP_KINDS.has(kind)) return "";
  const label = state.formLayerLabel;
  const mark = INTERFACE_STEP_KINDS.has(kind);
  const help = mark
    ? "Cette étape ne laisse pas de couche : sa marque pointe, en pointillé, la surface où elle a eu lieu - entre les couches d'avant et celles d'après. Enregistrée avec la version, sans compter comme un changement de structure."
    : "Pour qu'une capture d'écran porte l'essentiel : le texte et ses valeurs à droite du dessin, reliés à la couche. Enregistrée avec la version, sans compter comme un changement de structure.";
  return `
    <details class="sb-declared" id="layer-label-section" ${label ? "open" : ""}>
      <summary class="sb-declared__summary">Afficher sur la structure <span class="sb-declared__count" id="layer-label-state">${label ? (mark ? "marquée" : "étiquetée") : "optionnel"}</span></summary>
      <div class="sb-declared__body">
        <label class="sb-check"><input type="checkbox" id="layer-label-on" ${label ? "checked" : ""}> ${mark ? "Marquer cette étape à l'interface où elle a lieu" : "Étiqueter cette couche à côté de la structure"}</label>
        <div id="layer-label-fields" class="sb-layer-label" ${label ? "" : "hidden"}>
          <div>
            <label for="layer-label-text">Texte</label>
            <input class="field" id="layer-label-text" maxlength="40" value="${escapeHtml(label ? label.text : "")}" placeholder="${mark ? "ex : clean HF" : "ex : p-GaN"}" autocomplete="off">
          </div>
          <fieldset class="sb-layer-label__values">
            <legend>Valeurs écrites dessous</legend>
            <div id="layer-label-values"></div>
          </fieldset>
        </div>
        ${LABEL_PLACES.map(
          ({ key, text }) => `
        <div class="sb-layer-label__place" data-place="${key}" ${label && label[key] ? "" : "hidden"}>
          <span>${text}</span>
          <button type="button" class="btn btn-line js-layer-label-reset-place" data-place="${key}">Remettre à sa place</button>
        </div>`
        ).join("")}
        <div class="help" style="margin:8px 0 0;">${help} Sur le dessin, glissez le texte de l'étiquette pour le placer ailleurs, ou son point d'accroche (${mark ? "le losange, sur la surface" : "le rond, sur la couche"}) pour qu'il pointe un autre endroit ; un double-clic les remet à leur place automatique.</div>
      </div>
    </details>`;
}

// Les cases des valeurs, redessinées seulement quand les valeurs possibles changent (un paramètre
// déclaré ajouté, un matériau à composition choisi) - pas à chaque frappe.
function refreshLayerLabelValues(step) {
  const box = document.getElementById("layer-label-values");
  if (!box || !step) return;
  const options = layerLabelOptions(step);
  const key = options.map((o) => o.key).join("|");
  if (box.dataset.options === key) return;
  box.dataset.options = key;
  const chosen = new Set((state.formLayerLabel && state.formLayerLabel.values) || []);
  box.innerHTML = options.length
    ? options
        .map(
          (o) => `<label class="sb-check"><input type="checkbox" class="js-layer-label-value" value="${escapeHtml(o.key)}" ${chosen.has(o.key) ? "checked" : ""}> ${escapeHtml(o.label)}</label>`
        )
        .join("")
    : `<div class="help" style="margin:0;">Aucune valeur pour ce type d'étape - ajoutez un paramètre déclaré (un dopage, par exemple).</div>`;
}

// L'étiquette telle que le formulaire la décrit (null : pas d'étiquette), gardée dans
// state.formLayerLabel pour les rendus suivants - appelée par buildStepFromForm (step-kinds.js).
function readLayerLabelFromForm(step) {
  const on = document.getElementById("layer-label-on");
  if (!on || !LABELLED_STEP_KINDS.has(step.kind)) return null;
  if (!on.checked) {
    state.formLayerLabel = null;
    return null;
  }
  const available = new Set(layerLabelOptions(step).map((o) => o.key));
  const values = [...document.querySelectorAll("#layer-label-values .js-layer-label-value:checked")].map((box) => box.value).filter((v) => available.has(v));
  // la place choisie sur le dessin (glisser le texte ou le point, plus bas) n'est pas dans le
  // formulaire : gardée
  const place = {};
  LABEL_PLACES.forEach(({ key }) => {
    if (state.formLayerLabel && state.formLayerLabel[key]) place[key] = state.formLayerLabel[key];
  });
  state.formLayerLabel = { text: document.getElementById("layer-label-text").value.trim(), values, ...place };
  return state.formLayerLabel;
}

// Cocher la case : le texte prend le nom du matériau (d'une étape sans couche : son nom) et
// l'épaisseur (ou la profondeur) est cochée, s'il n'y avait rien. Branché avant l'inspecteur (inspector.js), dont l'écouteur relit ensuite le formulaire.
document.getElementById("step-form-section").addEventListener("change", (event) => {
  if (event.target.id !== "layer-label-on") return;
  const on = event.target.checked;
  document.getElementById("layer-label-fields").hidden = !on;
  const step = state.steps[state.selectedIndex];
  const mark = Boolean(step) && INTERFACE_STEP_KINDS.has(step.kind);
  document.getElementById("layer-label-state").textContent = on ? (mark ? "marquée" : "étiquetée") : "optionnel";
  if (!on) {
    // décochée, l'étiquette perd aussi sa place sur le dessin (readLayerLabelFromForm)
    document.querySelectorAll("#layer-label-section .sb-layer-label__place").forEach((row) => (row.hidden = true));
    return;
  }
  const text = document.getElementById("layer-label-text");
  if (!text.value.trim()) text.value = layerLabelDefaultText(step);
  const boxes = [...document.querySelectorAll("#layer-label-values .js-layer-label-value")];
  if (!boxes.some((box) => box.checked)) {
    const size = boxes.find((box) => box.value === "thickness" || box.value === "depth");
    if (size) size.checked = true;
  }
});

// ---------------------------------------------------------------------------------------------
// Placer une étiquette à la main : glisser son texte sur le dessin, ou son point d'accroche (le rond
// sur la couche, le losange d'une marque d'interface). Le déplacement du texte depuis sa place
// automatique est gardé sur l'étiquette (layerLabel.offset, [dx, dy] en unités du dessin) ; le point,
// en fractions du cadre de ce qu'il désigne (layerLabel.anchor, [fx, fy], le cadre étant
// data-anchor-box) : il suit la couche quand elle change. Le serveur ramène sur la couche (sur la
// surface, pour une marque d'interface) un point posé à côté, et redessine le trait
// (rendering.labelled_svg). Poser le point ne déplace aucun texte, et l'inverse.
// Double-clic sur le texte ou sur le point, ou « Remettre à sa place » dans l'inspecteur : retour à
// la place automatique. L'étiquette d'une brique est gardée sur sa première étape étiquetée
// (data-step) ; son accolade n'a pas de point à déplacer.
// ---------------------------------------------------------------------------------------------

// {kind: "text"|"anchor", onMarker, g, step, svg, start, moving, points, base, box, leader, ax, ay, elbow, width, tx, ty, d}
let labelDrag = null;

// Le trait d'une étiquette vers son texte - le même que rendering._leader_points côté serveur.
function labelLeaderPoints(ax, ay, elbow, tx, ty, width) {
  if (tx - 6 >= elbow) return `${ax},${ay} ${elbow},${ay} ${tx - 6},${ty}`;
  const end = tx + width + 6 < ax ? tx + width + 6 : tx - 6;
  return `${ax},${ay} ${end},${ty}`;
}

function svgPointOf(svg, event) {
  const point = svg.createSVGPoint();
  point.x = event.clientX;
  point.y = event.clientY;
  return point.matrixTransform(svg.getScreenCTM().inverse());
}

// Le point posé en (x, y) (unités du dessin), en fractions du cadre [x0, y0, x1, y1] de ce qu'il
// désigne, bornées à [0, 1] (LayerLabel.anchor) - posé hors de la couche, le serveur l'y ramène.
function labelAnchorFractions(box, x, y) {
  const [x0, y0, x1, y1] = box;
  const fraction = (v, a, b) => (b > a ? Math.min(1, Math.max(0, (v - a) / (b - a))) : 0.5);
  const round = (v) => Math.round(v * 1000) / 1000;
  return [round(fraction(x, x0, x1)), round(fraction(y, y0, y1))];
}

// La section de l'inspecteur dit si le texte ou le point de l'étiquette affichée ont été déplacés.
function refreshLayerLabelPlace() {
  document.querySelectorAll("#layer-label-section .sb-layer-label__place[data-place]").forEach((row) => {
    row.hidden = !(state.formLayerLabel && state.formLayerLabel[row.dataset.place]);
  });
}

// Pose (value : [dx, dy] ou [fx, fy]) ou efface (null) la place du texte (key "offset") ou du point
// (key "anchor") de l'étiquette de l'étape stepIndex.
function setLayerLabelPlace(stepIndex, key, value) {
  const step = state.steps[stepIndex];
  if (!step || !step.layerLabel) return;
  const placed = Array.isArray(value) && (key === "anchor" || value[0] !== 0 || value[1] !== 0);
  const withPlace = (label) => {
    const next = { ...label };
    if (placed) next[key] = value;
    else delete next[key];
    return next;
  };
  step.layerLabel = withPlace(step.layerLabel);
  if (stepIndex === state.selectedIndex && state.formLayerLabel) {
    state.formLayerLabel = withPlace(state.formLayerLabel);
    refreshLayerLabelPlace();
  }
  captureHistory();
  scheduleSimulate(0);
}

// Le point d'accroche sous le pointeur. Un point visible l'emporte sur une zone où attraper (celle
// d'une étiquette plus bas, peinte par-dessus, couvre les points d'au-dessus dans un empilement de
// couches fines) ; sur des zones seules, celle du point le plus proche. {anchor, onMarker} ou null.
function labelAnchorAt(event) {
  const container = document.getElementById("svg-container");
  const under = document.elementsFromPoint(event.clientX, event.clientY).filter((el) => container.contains(el));
  const marker = under.find((el) => !el.classList.contains("sp-layer-anchor__hit") && el.closest(".sp-layer-anchor"));
  if (marker) return { anchor: marker.closest(".sp-layer-anchor"), onMarker: true };
  const hits = under.filter((el) => el.classList.contains("sp-layer-anchor__hit"));
  if (!hits.length) return null;
  const p = svgPointOf(hits[0].ownerSVGElement, event);
  const distance = (hit) => {
    const [x, y] = (hit.closest(".sp-layer-label").dataset.anchor || "0 0").split(" ").map(Number);
    return Math.hypot(x - p.x, y - p.y);
  };
  const nearest = hits.reduce((best, hit) => (distance(hit) < distance(best) ? hit : best));
  return { anchor: nearest.closest(".sp-layer-anchor"), onMarker: false };
}

// Ce que le pointeur attrape : le texte d'une étiquette, ou son point d'accroche (pas l'accolade
// d'une brique, ni le point d'une image d'avant un retournement : sans data-anchor-box).
function labelDragTarget(event) {
  let handle = event.target.closest && event.target.closest(".sp-layer-label__text, .sp-layer-anchor");
  if (!handle) return null;
  const kind = handle.classList.contains("sp-layer-anchor") ? "anchor" : "text";
  let onMarker = false;
  if (kind === "anchor") {
    const found = labelAnchorAt(event);
    if (!found) return null;
    ({ anchor: handle, onMarker } = found);
  }
  const g = handle.closest(".sp-layer-label[data-step]");
  if (!g) return null;
  const step = state.steps[parseInt(g.dataset.step, 10)];
  if (!step || !step.layerLabel) return null;
  if (kind === "anchor" && !g.dataset.anchorBox) return null;
  return { g, handle, kind, onMarker };
}

document.getElementById("svg-container").addEventListener("mousedown", (event) => {
  if (event.button !== 0) return;
  const target = labelDragTarget(event);
  if (!target) return;
  event.preventDefault();
  event.stopPropagation(); // pas de déplacement de la vue zoomée (simulation.js)
  const { g, handle, kind, onMarker } = target;
  const svg = g.ownerSVGElement;
  const [ax, ay] = (g.dataset.anchor || "0 0").split(" ").map(Number);
  const firstText = g.querySelector(".sp-layer-label__text text");
  const leader = g.querySelector(".sp-layer-leader");
  const step = parseInt(g.dataset.step, 10);
  labelDrag = {
    kind,
    onMarker,
    g,
    step,
    svg,
    start: svgPointOf(svg, event),
    moving: handle,
    points: leader ? leader.getAttribute("points") : null,
    base: (g.dataset.offset || "0 0").split(" ").map(Number),
    box: kind === "anchor" ? g.dataset.anchorBox.split(" ").map(Number) : null,
    leader,
    ax,
    ay,
    elbow: Number(g.dataset.elbow || 0),
    width: Number(g.dataset.width || 0),
    tx: Number(firstText ? firstText.getAttribute("x") : 0),
    ty: Number(g.dataset.top || 0) + 16 * 1.3 / 2, // TITLE_SIZE * LINE_HEIGHT / 2 (rendering.py)
    d: [0, 0],
  };
  g.classList.add(kind === "anchor" ? "is-dragging-anchor" : "is-dragging");
  // le point se pose sur la couche de l'étape : on la voit, soulignée, pendant qu'on le déplace
  if (kind === "anchor" && !g.dataset.interface) hoverStepLayers(step); // simulation.js
});

function dragLabelTo(event) {
  const p = svgPointOf(labelDrag.svg, event);
  const dx = p.x - labelDrag.start.x;
  const dy = p.y - labelDrag.start.y;
  labelDrag.d = [dx, dy];
  labelDrag.moving.setAttribute("transform", `translate(${dx} ${dy})`);
  if (labelDrag.leader) {
    const { ax, ay, elbow, tx, ty, width } = labelDrag;
    const points = labelDrag.kind === "anchor" ? labelLeaderPoints(ax + dx, ay + dy, elbow, tx, ty, width) : labelLeaderPoints(ax, ay, elbow, tx + dx, ty + dy, width);
    labelDrag.leader.setAttribute("points", points);
  }
}

// Un clic (sans déplacement) sur le point d'une étiquette sélectionne son étape (sur l'écran des
// variations : fait varier sa couche) ; à côté du point, dans la zone où l'attraper, c'est un clic
// sur la couche dessous (simulation.js), comme sans la zone.
function clickLabelAnchor(drag, event) {
  if (!drag.onMarker) {
    const container = document.getElementById("svg-container");
    clickLayer(document.elementsFromPoint(event.clientX, event.clientY).find((el) => container.contains(el) && el.matches("[data-layer-index]")));
    return;
  }
  if (state.wizardScreen === "variations") {
    if (!drag.g.dataset.interface) startVaryingLayer(drag.step); // variations.js
    return;
  }
  selectStep(drag.step, { fromCanvas: true });
}

window.addEventListener("mousemove", (event) => {
  if (labelDrag) dragLabelTo(event);
});

window.addEventListener("mouseup", (event) => {
  if (!labelDrag) return;
  dragLabelTo(event); // là où le bouton est relâché
  const drag = labelDrag;
  labelDrag = null;
  drag.g.classList.remove("is-dragging", "is-dragging-anchor");
  if (drag.kind === "anchor" && !drag.g.dataset.interface) hoverStepLayers(null);
  if (Math.hypot(drag.d[0], drag.d[1]) < 2) {
    drag.moving.removeAttribute("transform");
    if (drag.leader && drag.points != null) drag.leader.setAttribute("points", drag.points);
    if (drag.kind === "anchor") clickLabelAnchor(drag, event);
    return;
  }
  suppressNextClick = true; // le clic qui suit n'est pas un clic sur une couche (simulation.js)
  if (drag.kind === "anchor") {
    setLayerLabelPlace(drag.step, "anchor", labelAnchorFractions(drag.box, drag.ax + drag.d[0], drag.ay + drag.d[1]));
    return;
  }
  const round = (v) => Math.round(v * 10) / 10;
  setLayerLabelPlace(drag.step, "offset", [round(drag.base[0] + drag.d[0]), round(drag.base[1] + drag.d[1])]);
});

document.getElementById("svg-container").addEventListener("dblclick", (event) => {
  const target = labelDragTarget(event);
  if (!target || (target.kind === "anchor" && !target.onMarker)) return; // à côté du point : la couche
  const key = target.kind === "anchor" ? "anchor" : "offset";
  if (!target.g.hasAttribute(key === "anchor" ? "data-anchor-placed" : "data-offset")) return;
  event.preventDefault();
  setLayerLabelPlace(parseInt(target.g.dataset.step, 10), key, null);
});

document.getElementById("step-form-section").addEventListener("click", (event) => {
  const button = event.target.closest(".js-layer-label-reset-place");
  if (!button) return;
  setLayerLabelPlace(state.selectedIndex, button.dataset.place, null);
});
