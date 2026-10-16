/* Cotes : dans l'inspecteur d'une étape, la section « Coter sur le dessin » - mesurer sur l'image
   de l'étape l'épaisseur ou la largeur de ce qui est sous un point qu'on clique (le substrat après
   une planarisation, le diamètre apparent d'un fil après une croissance facettée). La cote ne paraît
   que sur l'image de son étape : une information d'un moment, qui ne charge pas la structure finale.
   Elle vit sur l'étiquette de l'étape (step.layerLabel.measures, une étiquette « seulement cotée »
   quand elle n'est pas affichée : shown faux) et voyage avec elle ; c'est le serveur qui mesure et
   dessine (spectre.plugins.structures.rendering.measure_line). Le point est en nm, dans la géométrie
   de l'image : il suit la couche quand une épaisseur change, tant qu'il reste dedans. */

const MEASURE_DIRECTIONS = {
  thickness: { label: "Épaisseur", action: "Mesurer une épaisseur", hint: "la traversée verticale" },
  width: { label: "Largeur", action: "Mesurer une largeur", hint: "la traversée horizontale" },
};
const MAX_MEASURES = 6; // simulation.MAX_MEASURES côté serveur

// {direction, scope, step} pendant qu'on attend le clic sur le dessin, sinon null
let measuring = null;

function stepMeasures(step) {
  return (step && step.layerLabel && step.layerLabel.measures) || [];
}

function measuresSectionHtml(kind) {
  if (!LABELLED_STEP_KINDS.has(kind)) return "";
  const measures = (state.formLayerLabel && state.formLayerLabel.measures) || [];
  return `
    <details class="sb-declared" id="measures-section" ${measures.length ? "open" : ""}>
      <summary class="sb-declared__summary">Coter sur le dessin <span class="sb-declared__count" id="measures-count">${measures.length ? measures.length : "optionnel"}</span></summary>
      <div class="sb-declared__body">
        <div id="measures-list" class="sb-measures"></div>
        <div class="sb-measures__actions">
          ${Object.entries(MEASURE_DIRECTIONS)
            .map(([direction, d]) => `<button type="button" class="btn btn-line js-measure-start" data-direction="${direction}">${d.action}</button>`)
            .join("")}
        </div>
        <label class="sb-check"><input type="checkbox" id="measure-layer-only"> Couche cliquée seule (sinon : la matière d'un seul tenant)</label>
        <div class="sb-measures__pending" id="measure-pending" hidden>
          <span id="measure-pending-text"></span>
          <button type="button" class="btn btn-line" id="measure-cancel-btn">Annuler</button>
        </div>
        <div class="help" style="margin:8px 0 0;">Cliquez ensuite sur le dessin de cette étape : la cote mesure ce qui est sous le point - l'épaisseur du substrat après une planarisation, la largeur d'un fil après sa croissance. Elle ne paraît que sur l'image de cette étape (et dans son rapport), pas sur la suite. Enregistrée avec la version, sans compter comme un changement de structure.</div>
      </div>
    </details>`;
}

// La longueur mesurée d'une cote, lue sur l'image de son étape (data-length, posé par le serveur).
function measuredLength(stepIndex, k) {
  const frame = state.frames && state.frames[stepIndex + 1];
  const match = frame && frame.svg.match(new RegExp(`<g class="sp-measure"[^>]*data-step="${stepIndex}" data-measure="${k}" data-length="([^"]+)" data-material="([^"]*)"`));
  return match ? { length: Number(match[1]), material: match[2] } : null;
}

function measureLengthText(nm) {
  return Math.abs(nm) >= 1000 ? `${Number((nm / 1000).toFixed(4))} µm` : `${Number(nm.toFixed(1))} nm`;
}

// La liste des cotes de l'étape ouverte, avec leurs longueurs : redessinée après chaque simulation.
function refreshMeasuresList() {
  const box = document.getElementById("measures-list");
  if (!box) return;
  const index = state.selectedIndex;
  const measures = (state.formLayerLabel && state.formLayerLabel.measures) || [];
  document.getElementById("measures-count").textContent = measures.length ? String(measures.length) : "optionnel";
  box.innerHTML = measures
    .map((measure, k) => {
      const measured = measuredLength(index, k);
      const what = measured ? `${escapeHtml(measured.material)} · <strong>${escapeHtml(measureLengthText(measured.length))}</strong>` : "<em>hors de la structure</em>";
      const scope = measure.scope === "layer" ? "couche seule" : "matière";
      return `<div class="sb-measures__row">
          <span>${escapeHtml(MEASURE_DIRECTIONS[measure.direction].label)} · ${what} <span class="sb-measures__scope">(${scope})</span></span>
          <button type="button" class="btn btn-line js-measure-remove" data-measure="${k}" aria-label="Retirer cette cote" title="Retirer cette cote">✕</button>
        </div>`;
    })
    .join("");
  document.querySelectorAll(".js-measure-start").forEach((button) => (button.disabled = measures.length >= MAX_MEASURES));
}

// Pose les cotes de l'étape stepIndex : sur son étiquette (créée « seulement cotée » s'il n'y en a pas,
// retirée si elle n'avait que ses cotes), et dans le formulaire ouvert.
function setStepMeasures(stepIndex, measures) {
  const step = state.steps[stepIndex];
  if (!step) return;
  const withMeasures = (label) => {
    const next = { ...(label || { text: "", values: [], shown: false }) };
    if (measures.length) next.measures = measures;
    else delete next.measures;
    return next.shown === false && !measures.length ? null : next;
  };
  const label = withMeasures(step.layerLabel);
  if (label) step.layerLabel = label;
  else delete step.layerLabel;
  if (stepIndex === state.selectedIndex) state.formLayerLabel = label ? JSON.parse(JSON.stringify(label)) : null;
  refreshMeasuresList();
  renderRail(); // la puce de l'étape dit qu'elle est cotée
  captureHistory();
  scheduleSimulate(0);
}

function startMeasuring(direction) {
  const index = state.selectedIndex;
  if (index == null || index < 0) return;
  measuring = { direction, scope: document.getElementById("measure-layer-only").checked ? "layer" : "material", step: index };
  // la cote se pose sur l'image de l'étape : on la montre
  state.previewMode = "step";
  state.frameLock = null;
  renderFrame();
  document.getElementById("svg-viewport").classList.add("is-measuring");
  document.getElementById("measure-pending").hidden = false;
  document.getElementById("measure-pending-text").textContent = `Cliquez sur le dessin : ${MEASURE_DIRECTIONS[direction].hint} du point. Échap pour annuler.`;
}

function stopMeasuring() {
  measuring = null;
  document.getElementById("svg-viewport").classList.remove("is-measuring");
  const pending = document.getElementById("measure-pending");
  if (pending) pending.hidden = true;
}

// Le point cliqué, en nm dans la géométrie de l'image : le dessin de StructureForge (le <svg> imbriqué
// quand l'image porte des étiquettes) a la géométrie pour viewBox, y retourné.
function geometryPointOf(event) {
  const container = document.getElementById("svg-container");
  const svg = container.querySelector("svg.sp-labelled-structure > svg") || container.querySelector("svg");
  if (!svg) return null;
  const p = svgPointOf(svg, event); // layer-label.js
  return [Math.round(p.x * 10) / 10, Math.round(-p.y * 10) / 10];
}

// Pendant qu'on cote, le clic sur le dessin pose la cote - avant qu'il ne sélectionne une couche, ne
// déplace une étiquette ou la vue (phase de capture).
const measureCanvas = document.getElementById("svg-container");
measureCanvas.addEventListener(
  "mousedown",
  (event) => {
    if (measuring) event.stopPropagation();
  },
  true
);
measureCanvas.addEventListener(
  "click",
  (event) => {
    if (!measuring) return;
    event.stopPropagation();
    event.preventDefault();
    const point = geometryPointOf(event);
    const { direction, scope, step } = measuring;
    stopMeasuring();
    if (!point || !state.steps[step]) return;
    setStepMeasures(step, [...stepMeasures(state.steps[step]), { direction, point, scope }]);
  },
  true
);

document.addEventListener("keydown", (event) => {
  if (measuring && event.key === "Escape") stopMeasuring();
});

document.getElementById("step-form-section").addEventListener("click", (event) => {
  const start = event.target.closest(".js-measure-start");
  if (start) {
    startMeasuring(start.dataset.direction);
    return;
  }
  if (event.target.closest("#measure-cancel-btn")) {
    stopMeasuring();
    return;
  }
  const remove = event.target.closest(".js-measure-remove");
  if (remove) {
    const measures = stepMeasures(state.steps[state.selectedIndex]).filter((_m, k) => k !== Number(remove.dataset.measure));
    setStepMeasures(state.selectedIndex, measures);
  }
});
