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
const LAYER_STEP_KINDS = new Set(["deposition", "epitaxial_growth", "faceted_growth", "lithography"]);
// Ceux qui n'en créent pas : une marque d'interface (simulation.INTERFACE_STEP_KINDS côté serveur).
const INTERFACE_STEP_KINDS = new Set(["etch", "planarization", "chemical", "resist_strip"]);
const LABELLED_STEP_KINDS = new Set([...LAYER_STEP_KINDS, ...INTERFACE_STEP_KINDS]);

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
    return label ? { ...step, layerLabel: { text: label.text || "", values: [...(label.values || [])] } } : step;
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
        <div class="help" style="margin:8px 0 0;">${help}</div>
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
  state.formLayerLabel = { text: document.getElementById("layer-label-text").value.trim(), values };
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
  if (!on) return;
  const text = document.getElementById("layer-label-text");
  if (!text.value.trim()) text.value = layerLabelDefaultText(step);
  const boxes = [...document.querySelectorAll("#layer-label-values .js-layer-label-value")];
  if (!boxes.some((box) => box.checked)) {
    const size = boxes.find((box) => box.value === "thickness" || box.value === "depth");
    if (size) size.checked = true;
  }
});
