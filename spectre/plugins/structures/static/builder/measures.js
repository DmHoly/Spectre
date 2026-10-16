/* Cotes : dans l'inspecteur d'une étape, la section « Coter sur le dessin » - mesurer sur l'image
   de l'étape l'épaisseur ou la largeur de ce qui est sous un point qu'on clique (le substrat après
   une planarisation, le diamètre apparent d'un fil après une croissance facettée). La cote ne paraît
   que sur l'image de son étape : une information d'un moment, qui ne charge pas la structure finale.
   Elle vit sur l'étiquette de l'étape (step.layerLabel.measures, une étiquette « seulement cotée »
   quand elle n'est pas affichée : shown faux) et voyage avec elle ; c'est le serveur qui mesure et
   dessine (spectre.plugins.structures.rendering.measure_line). Le point est en nm, dans la géométrie
   de l'image : il suit la couche quand une épaisseur change, tant qu'il reste dedans.
   Une cote peut être suivie à des étapes d'après (« Suivre aux étapes », measure.also : leurs ids) :
   la même couche y est mesurée au même endroit, avec l'écart à sa valeur d'origine - le dépôt de
   400 nm que la planarisation suivante amincit. L'inspecteur de ces étapes dit les cotes qu'elles
   reprennent. */

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
  // ouverte aussi sur une étape qui reprend la cote d'une étape d'avant
  const current = state.steps[state.selectedIndex];
  const followedHere = Boolean(current && current.id) && state.steps.some((source, i) => i < state.selectedIndex && stepMeasures(source).some((m) => (m.also || []).includes(current.id)));
  return `
    <details class="sb-declared" id="measures-section" ${measures.length || followedHere ? "open" : ""}>
      <summary class="sb-declared__summary">Coter sur le dessin <span class="sb-declared__count" id="measures-count">${measures.length ? measures.length : "optionnel"}</span></summary>
      <div class="sb-declared__body">
        <div id="measures-list" class="sb-measures"></div>
        <div id="measures-followed-here" class="sb-measures"></div>
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
        <div class="help" style="margin:8px 0 0;">Cliquez ensuite sur le dessin de cette étape : la cote mesure ce qui est sous le point - l'épaisseur du substrat après une planarisation, la largeur d'un fil après sa croissance. Elle paraît sur l'image de cette étape (et dans son rapport) ; « Suivre aux étapes » la reprend sur celles d'après que vous cochez, avec l'écart à sa valeur d'ici (une planarisation qui amincit le dépôt). Enregistrée avec la version, sans compter comme un changement de structure.</div>
      </div>
    </details>`;
}

// La longueur mesurée d'une cote, lue sur l'image de son étape (data-length, posé par le serveur).
function measuredLength(stepIndex, k) {
  const frame = state.frames && state.frames[stepIndex + 1];
  const match = frame && frame.svg.match(new RegExp(`<g class="sp-measure"[^>]*data-step="${stepIndex}" data-measure="${k}" data-length="([^"]+)" data-material="([^"]*)"`));
  return match ? { length: Number(match[1]), material: match[2] } : null;
}

// Sa longueur sur l'image d'une étape d'après où elle est suivie (data-at), et sa longueur d'origine.
function followedLength(stepIndex, k, at) {
  const frame = state.frames && state.frames[at + 1];
  const match = frame && frame.svg.match(new RegExp(`<g class="sp-measure"[^>]*data-step="${stepIndex}" data-measure="${k}" data-at="${at}" data-length="([^"]+)"[^>]*data-reference="([^"]+)"`));
  return match ? { length: Number(match[1]), reference: Number(match[2]) } : null;
}

function measureChangeText(followed) {
  const change = Math.round((followed.length - followed.reference) * 10) / 10;
  if (Math.abs(change) < 0.05) return `${measureLengthText(followed.length)} (=)`;
  return `${measureLengthText(followed.length)} (${change > 0 ? "+" : "−"}${measureLengthText(Math.abs(change))})`;
}

// Les « Suivre aux étapes » ouverts (par numéro de cote), gardés ouverts quand la liste se redessine.
const openFollowLists = new Set();

function stepTitle(index) {
  const step = state.steps[index];
  return `Étape ${index + 1} · ${step ? step.name : ""}`;
}

// Les étapes d'après où la cote k de l'étape index peut être suivie : une case chacune (une étape
// neuve reçoit son id à la simulation suivante - d'ici là, pas de case).
function followListHtml(index, k, measure) {
  const also = new Set(measure.also || []);
  const later = state.steps.map((step, j) => ({ step, j })).filter(({ j }) => j > index);
  if (!later.length) return "";
  const rows = later
    .map(({ step, j }) => {
      const followed = step.id && also.has(step.id) ? followedLength(index, k, j) : null;
      const value = followed ? ` - <strong>${escapeHtml(measureChangeText(followed))}</strong>` : "";
      return `<label class="sb-check"><input type="checkbox" class="js-measure-follow" data-measure="${k}" value="${escapeHtml(step.id || "")}" ${step.id ? "" : "disabled"} ${step.id && also.has(step.id) ? "checked" : ""}> ${escapeHtml(stepTitle(j))}${value}</label>`;
    })
    .join("");
  const count = later.filter(({ step }) => step.id && also.has(step.id)).length;
  return `<details class="sb-measures__follow" data-measure="${k}" ${openFollowLists.has(k) ? "open" : ""}>
      <summary>Suivre aux étapes${count ? ` (${count})` : ""}</summary>
      <div class="sb-measures__follow-list">${rows}</div>
    </details>`;
}

// Les cotes d'étapes d'avant que l'étape ouverte reprend, avec leur longueur ici et leur écart.
function followedHereHtml(index) {
  const step = state.steps[index];
  if (!step || !step.id) return "";
  const rows = [];
  state.steps.forEach((source, i) => {
    if (i >= index) return;
    stepMeasures(source).forEach((measure, k) => {
      if (!(measure.also || []).includes(step.id)) return;
      const followed = followedLength(i, k, index);
      const what = followed ? `<strong>${escapeHtml(measureChangeText(followed))}</strong>` : "<em>couche absente ici</em>";
      rows.push(`<div class="sb-measures__row">
          <span>${escapeHtml(MEASURE_DIRECTIONS[measure.direction].label)} de l'étape ${i + 1} (${escapeHtml(source.name)}) · ${what}</span>
          <button type="button" class="btn btn-line js-measure-unfollow" data-step="${i}" data-measure="${k}" aria-label="Ne plus la suivre ici" title="Ne plus la suivre ici">✕</button>
        </div>`);
    });
  });
  return rows.length ? `<div class="sb-measures__here">Reprises ici</div>${rows.join("")}` : "";
}

// Suit (on) ou ne suit plus la cote k de l'étape index à l'étape d'id stepId.
function setMeasureFollowed(index, k, stepId, on) {
  const measures = stepMeasures(state.steps[index]).map((measure, j) => {
    if (j !== k) return measure;
    const also = (measure.also || []).filter((id) => id !== stepId);
    if (on) also.push(stepId);
    const next = { ...measure, also };
    if (!also.length) delete next.also;
    return next;
  });
  setStepMeasures(index, measures);
  if (index !== state.selectedIndex) refreshMeasuresList(); // l'étape ouverte reprenait cette cote
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
      return `<div class="sb-measures__item"><div class="sb-measures__row">
          <span>${escapeHtml(MEASURE_DIRECTIONS[measure.direction].label)} · ${what} <span class="sb-measures__scope">(${scope})</span></span>
          <button type="button" class="btn btn-line js-measure-remove" data-measure="${k}" aria-label="Retirer cette cote" title="Retirer cette cote">✕</button>
        </div>${followListHtml(index, k, measure)}</div>`;
    })
    .join("");
  const here = document.getElementById("measures-followed-here");
  if (here) here.innerHTML = followedHereHtml(index);
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
  const unfollow = event.target.closest(".js-measure-unfollow");
  if (unfollow) {
    const step = state.steps[state.selectedIndex];
    if (step && step.id) setMeasureFollowed(Number(unfollow.dataset.step), Number(unfollow.dataset.measure), step.id, false);
    return;
  }
  const remove = event.target.closest(".js-measure-remove");
  if (remove) {
    openFollowLists.clear();
    const measures = stepMeasures(state.steps[state.selectedIndex]).filter((_m, k) => k !== Number(remove.dataset.measure));
    setStepMeasures(state.selectedIndex, measures);
  }
});

document.getElementById("step-form-section").addEventListener("change", (event) => {
  const box = event.target.closest(".js-measure-follow");
  if (!box || !box.value) return;
  setMeasureFollowed(state.selectedIndex, Number(box.dataset.measure), box.value, box.checked);
});

// ouvrir ou fermer « Suivre aux étapes » : gardé tel quel quand la liste se redessine
document.getElementById("step-form-section").addEventListener(
  "toggle",
  (event) => {
    const details = event.target;
    if (!details.classList || !details.classList.contains("sb-measures__follow")) return;
    const k = Number(details.dataset.measure);
    if (details.open) openFollowLists.add(k);
    else openFollowLists.delete(k);
  },
  true
);
