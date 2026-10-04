/* Process flow : le stepper horizontal en tête de l'atelier (le substrat, puis une puce par étape,
   les briques regroupées sous un même cadre), et toutes les opérations structurelles sur la liste
   d'étapes - insertion (outil de la palette, « + » entre deux puces, glisser-déposer),
   déplacement, duplication, suppression, groupement en brique.

   La sélection (state.selectedIndex, -1 = substrat) pilote tout le reste : l'inspecteur
   (inspector.js) édite l'étape sélectionnée en direct, et le dessin (simulation.js) montre la
   structure *après* cette étape - le flow sert donc aussi de frise chronologique. */

// ---------------------------------------------------------------------------------------------
// Briques : bornes, échanges de blocs, étiquettes
// ---------------------------------------------------------------------------------------------

// Bornes [début, fin] (incluses) du bloc auquel appartient l'étape à `index` - toute la brique si
// elle en fait partie, sinon juste elle-même. Un bracket de brique doit toujours rester un unique
// morceau contigu (voir le bug historique : un groupe scindé en deux moitiés affichant le même nom).
function brickSpanAt(index) {
  const groupId = state.steps[index].brick_group_id;
  if (!groupId) return [index, index];
  let start = index;
  while (start > 0 && state.steps[start - 1].brick_group_id === groupId) start -= 1;
  let end = index;
  while (end < state.steps.length - 1 && state.steps[end + 1].brick_group_id === groupId) end += 1;
  return [start, end];
}

// Bornes d'une brique par son identifiant (null si elle n'existe plus, ex : après un Ctrl+Z).
function brickGroupSpan(groupId) {
  const start = state.steps.findIndex((s) => s.brick_group_id === groupId);
  return start === -1 ? null : brickSpanAt(start);
}

// Échange deux blocs adjacents et contigus de `steps` en place.
function swapBlocks(steps, aStart, aEnd, bStart, bEnd) {
  const blockA = steps.slice(aStart, aEnd + 1);
  const blockB = steps.slice(bStart, bEnd + 1);
  steps.splice(aStart, bEnd - aStart + 1, ...blockB, ...blockA);
}

function generateBrickGroupId() {
  return `brick-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

// Une brique enregistrée dans la bibliothèque reste "propre" (jamais étiquetée) - l'étiquette
// n'existe que sur les copies vivantes dans une structure en cours, posée fraîche à chaque
// groupement ou insertion.
function stripBrickTag(step) {
  const { brick_group_id, brick_name, ...rest } = step;
  return rest;
}

// L'id d'une étape (step.id) vient toujours du serveur : le procédé relu (GET .../process), ou la
// simulation qui suit l'ajout d'une étape (adoptStepIds, simulation.js). Le constructeur le garde
// tel quel (déplacement, édition, annuler/rétablir) et ne l'invente jamais : une copie (étape
// dupliquée, brique insérée, étapes d'un modèle) part sans id, le serveur lui en donne un neuf.
function withoutStepId(step) {
  const { id, ...rest } = step;
  return rest;
}

// Un « trou » d'insertion `gap` (0..n, avant l'étape d'index `gap`) tombe-t-il à l'intérieur d'une
// brique (entre deux de ses étapes) ? Renvoie alors son identifiant, sinon null.
function brickGroupInsideGap(gap) {
  if (gap <= 0 || gap >= state.steps.length) return null;
  const before = state.steps[gap - 1].brick_group_id;
  return before && before === state.steps[gap].brick_group_id ? before : null;
}

// Ramène un trou situé à l'intérieur d'une brique sur l'un de ses bords - pour un déplacement ou
// l'insertion d'une autre brique, qui ne doivent jamais scinder ce bracket.
function snapGapOutsideBricks(gap, preferEnd) {
  const groupId = brickGroupInsideGap(gap);
  if (!groupId) return gap;
  const [start, end] = brickGroupSpan(groupId);
  return preferEnd ? end + 1 : start;
}

// ---------------------------------------------------------------------------------------------
// Sélection
// ---------------------------------------------------------------------------------------------

function hasMultiSelection() {
  return state.selectedStepIndices.size >= 2;
}

// Où insérer « après la sélection » (outil de la palette, touches 1-9, brique cliquée) : après
// l'étape sélectionnée (ou la brique, ou la sélection multiple), en tête si c'est le substrat.
function defaultInsertIndex() {
  if (state.selectedBrickGroup) {
    const span = brickGroupSpan(state.selectedBrickGroup);
    if (span) return span[1] + 1;
  }
  if (hasMultiSelection()) return Math.max(...state.selectedStepIndices) + 1;
  if (state.selectedIndex >= 0 && state.selectedIndex < state.steps.length) return state.selectedIndex + 1;
  return state.selectedIndex === -1 ? 0 : state.steps.length;
}

// Clic sur une puce : sélection simple, ou multiple avec Ctrl/⌘ (bascule) et Maj (plage depuis
// l'ancre). `fromCanvas` : sélection faite en cliquant une couche du dessin - la vue en cours est
// conservée (voir state.frameLock dans simulation.js) au lieu de sauter à cette étape.
function selectStep(index, { toggle = false, range = false, fromCanvas = false } = {}) {
  const n = state.steps.length;
  if (index < -1 || index >= n) return;
  if (state.wizardScreen === "variations") {
    startVaryingLayer(index); // -1 : le substrat se fait varier aussi
    return;
  }
  const frameBefore = currentFrameIndex(); // l'image à l'écran avant ce clic (voir fromCanvas)
  state.selectedBrickGroup = null;
  if (index >= 0 && (toggle || range)) {
    const anchor = state.selectedIndex;
    if (range && anchor >= 0) {
      state.selectedStepIndices = new Set();
      for (let k = Math.min(anchor, index); k <= Math.max(anchor, index); k++) state.selectedStepIndices.add(k);
    } else {
      if (state.selectedStepIndices.size === 0 && anchor >= 0) state.selectedStepIndices.add(anchor);
      if (state.selectedStepIndices.has(index)) state.selectedStepIndices.delete(index);
      else state.selectedStepIndices.add(index);
    }
    if (state.selectedStepIndices.size === 1) {
      index = [...state.selectedStepIndices][0];
      state.selectedStepIndices.clear();
    } else if (state.selectedStepIndices.size === 0) {
      state.selectedStepIndices.clear();
    }
  } else {
    state.selectedStepIndices.clear();
  }
  state.selectedIndex = index;
  if (!fromCanvas) state.frameLock = null;
  else if (state.frameLock == null) state.frameLock = frameBefore;
  if (!fromCanvas) hideLayerProvenance();
  renderRail();
  renderInspector();
  renderFrame();
}

function selectBrickGroup(groupId) {
  if (state.wizardScreen === "variations") return;
  const span = brickGroupSpan(groupId);
  if (!span) return;
  state.selectedStepIndices.clear();
  state.selectedBrickGroup = groupId;
  state.selectedIndex = span[1];
  state.frameLock = null;
  hideLayerProvenance();
  renderRail();
  renderInspector();
  renderFrame();
}

function clearMultiSelection() {
  if (!hasMultiSelection() && !state.selectedBrickGroup) return false;
  state.selectedStepIndices.clear();
  state.selectedBrickGroup = null;
  renderRail();
  renderInspector();
  return true;
}

// Sélection initiale après un chargement (structure existante, modèle, brique...) : la dernière
// étape, pour que le dessin montre la structure finale et que la palette ajoute à la suite.
function selectLastStep() {
  state.selectedIndex = state.steps.length - 1; // -1 (substrat) si la liste est vide
  state.selectedStepIndices.clear();
  state.selectedBrickGroup = null;
  state.frameLock = null;
}

// ---------------------------------------------------------------------------------------------
// Opérations structurelles - toutes finissent par commitStructure()
// ---------------------------------------------------------------------------------------------

// Après tout changement de la liste d'étapes : les variations (index d'étapes) sont invalidées, le
// flow et l'inspecteur redessinés, l'historique capturé, la simulation relancée.
function commitStructure() {
  state.frameLock = null;
  invalidateVariations();
  renderRail();
  renderInspector();
  captureHistory();
  scheduleSimulate();
  updateStageMeta();
}

// Compatibilité : les autres modules (chargement d'un procédé, historique...) appellent encore
// renderSteps() après avoir remplacé state.steps.
function renderSteps() {
  if (state.selectedIndex >= state.steps.length) state.selectedIndex = state.steps.length - 1;
  commitStructure();
}

function insertSteps(at, newSteps) {
  state.steps.splice(at, 0, ...newSteps);
  state.selectedStepIndices.clear();
  state.selectedBrickGroup = null;
  state.selectedIndex = at + newSteps.length - 1;
  hideLayerProvenance();
  commitStructure();
  scrollChipIntoView(state.selectedIndex);
}

// Nouvelle étape d'un type donné, avec les valeurs par défaut de son formulaire - insérée à `at`
// et sélectionnée, l'inspecteur est aussitôt prêt à la régler. Dans une brique (entre deux de ses
// étapes), elle en fait partie : le bracket reste contigu.
function insertStepOfKind(kind, at = defaultInsertIndex()) {
  if (state.wizardScreen !== "structure") return;
  clearError();
  const step = defaultStepOfKind(kind);
  const groupId = brickGroupInsideGap(at);
  if (groupId) {
    step.brick_group_id = groupId;
    step.brick_name = state.steps[at].brick_name;
  }
  insertSteps(at, [step]);
}

// Une brique technologique est une séquence d'étapes préenregistrée (voir brick-mode.js /
// spectre.core.tech_bricks) - l'insérer copie ses étapes une bonne fois pour toutes, comme un
// préset : aucun lien vivant après coup avec la brique elle-même. Elle arrive repliée.
function insertBrickAt(brick, at = defaultInsertIndex()) {
  if (state.wizardScreen !== "structure" || !brick || !brick.steps || !brick.steps.length) return;
  clearError();
  const target = snapGapOutsideBricks(at, true);
  const groupId = generateBrickGroupId();
  const copied = JSON.parse(JSON.stringify(brick.steps)).map((s) => ({ ...withoutStepId(stripBrickTag(s)), brick_group_id: groupId, brick_name: brick.name }));
  state.collapsedBrickGroups.add(groupId);
  insertSteps(target, copied);
  state.selectedBrickGroup = groupId;
  renderRail();
  renderInspector();
  renderFrame();
}

// Déplace le bloc (une brique entière si `index` en fait partie, sinon l'étape seule) d'un cran,
// en échange avec son voisin - qui peut lui-même être une brique entière, auquel cas on la dépasse
// en un clic plutôt que d'atterrir au milieu.
function moveStep(index, delta) {
  if (index < 0 || index >= state.steps.length) return;
  const selectedStep = state.selectedIndex >= 0 ? state.steps[state.selectedIndex] : null;
  const [start, end] = brickSpanAt(index);
  if (delta === -1) {
    if (start === 0) return;
    const [neighborStart, neighborEnd] = brickSpanAt(start - 1);
    swapBlocks(state.steps, neighborStart, neighborEnd, start, end);
  } else if (delta === 1) {
    if (end === state.steps.length - 1) return;
    const [neighborStart, neighborEnd] = brickSpanAt(end + 1);
    swapBlocks(state.steps, start, end, neighborStart, neighborEnd);
  } else {
    return;
  }
  if (selectedStep) state.selectedIndex = state.steps.indexOf(selectedStep);
  state.selectedStepIndices.clear();
  commitStructure();
  scrollChipIntoView(state.selectedIndex);
}

// Glisser-déposer : amène le bloc [start, end] au trou `gap` (indices d'avant le déplacement).
function moveBlockToGap(start, end, gap) {
  if (gap >= start && gap <= end + 1) return; // lâché sur place
  const target = snapGapOutsideBricks(gap, gap > end);
  if (target >= start && target <= end + 1) return;
  const selectedStep = state.selectedIndex >= 0 ? state.steps[state.selectedIndex] : null;
  const block = state.steps.splice(start, end - start + 1);
  const insertAt = target > end ? target - block.length : target;
  state.steps.splice(insertAt, 0, ...block);
  if (selectedStep) state.selectedIndex = state.steps.indexOf(selectedStep);
  state.selectedStepIndices.clear();
  commitStructure();
}

function duplicateStep(index) {
  if (index < 0 || index >= state.steps.length) return;
  // garde l'étiquette de brique : la copie atterrit juste après, le bracket reste contigu ; pas
  // l'id : c'est une nouvelle étape
  const copy = withoutStepId(JSON.parse(JSON.stringify(state.steps[index])));
  insertSteps(index + 1, [copy]);
}

function deleteSteps(indices) {
  const sorted = [...new Set(indices)].filter((i) => i >= 0 && i < state.steps.length).sort((a, b) => b - a);
  if (!sorted.length) return;
  sorted.forEach((i) => state.steps.splice(i, 1));
  const first = sorted[sorted.length - 1];
  state.selectedStepIndices.clear();
  state.selectedBrickGroup = null;
  // on se replace sur l'étape d'avant (ou le substrat) : c'est là que la suivante s'insérerait
  state.selectedIndex = Math.min(first - 1, state.steps.length - 1);
  hideLayerProvenance();
  commitStructure();
}

// Suppr / bouton poubelle : la sélection multiple, sinon la brique sélectionnée, sinon l'étape.
function deleteCurrentSelection() {
  if (hasMultiSelection()) deleteSteps([...state.selectedStepIndices]);
  else if (state.selectedBrickGroup) deleteBrickGroup(state.selectedBrickGroup);
  else if (state.selectedIndex >= 0) deleteSteps([state.selectedIndex]);
}

function toggleBrickCollapse(groupId) {
  if (state.collapsedBrickGroups.has(groupId)) state.collapsedBrickGroups.delete(groupId);
  else state.collapsedBrickGroups.add(groupId);
  // replier une brique qui contient la sélection : on sélectionne la brique elle-même, sinon la
  // puce sélectionnée disparaîtrait dans le repli (et la brique se redéplierait d'office)
  const span = brickGroupSpan(groupId);
  if (span && state.collapsedBrickGroups.has(groupId) && state.selectedIndex >= span[0] && state.selectedIndex <= span[1]) {
    state.selectedBrickGroup = groupId;
    state.selectedStepIndices.clear();
  }
  renderRail();
  renderInspector();
}

function ungroupBrick(groupId) {
  state.steps.forEach((s, i) => {
    if (s.brick_group_id === groupId) state.steps[i] = stripBrickTag(s);
  });
  state.collapsedBrickGroups.delete(groupId);
  if (state.selectedBrickGroup === groupId) state.selectedBrickGroup = null;
  commitStructure();
}

function deleteBrickGroup(groupId) {
  const span = brickGroupSpan(groupId);
  if (!span) return;
  const indices = [];
  for (let k = span[0]; k <= span[1]; k++) indices.push(k);
  deleteSteps(indices);
}

// Grouper une sélection d'étapes déjà présentes en une nouvelle brique réutilisable - l'inverse de
// « insérer une brique ». L'ordre des étapes étant physiquement significatif, seule une sélection
// contiguë peut être bracketée sensément ; une sélection éparpillée est refusée plutôt que
// silencieusement réordonnée.
async function groupSelectionIntoBrick() {
  clearError();
  const indices = [...state.selectedStepIndices].sort((a, b) => a - b);
  if (indices.length < 2) return;
  const contiguous = indices.every((idx, k) => k === 0 || idx === indices[k - 1] + 1);
  if (!contiguous) {
    showError(new Error("Les étapes sélectionnées doivent être consécutives pour former une brique."));
    return;
  }
  if (indices.some((idx) => state.steps[idx].brick_group_id)) {
    showError(new Error("Une de ces étapes appartient déjà à une brique - dissociez-la d'abord."));
    return;
  }
  const nameInput = document.getElementById("group-brick-name");
  const name = nameInput.value.trim();
  if (!name) {
    showError(new Error("Donnez un nom à la brique."));
    nameInput.focus();
    return;
  }
  try {
    const selectedSteps = indices.map((idx) => withoutStepId(stripBrickTag(state.steps[idx])));
    const created = await processLibraryApi.createTechBrick({
      name,
      steps: selectedSteps,
      declared_params: declaredParamsPayload(selectedSteps),
      scope: "microproject",
      microproject: slug,
    });
    state.techBricks = [...state.techBricks, created];
    const groupId = generateBrickGroupId();
    indices.forEach((idx) => {
      state.steps[idx] = { ...state.steps[idx], brick_group_id: groupId, brick_name: name };
    });
    renderBrickList();
    nameInput.value = "";
    state.selectedStepIndices.clear();
    state.selectedBrickGroup = groupId;
    state.selectedIndex = indices[indices.length - 1];
    commitStructure();
  } catch (err) {
    showError(err);
  }
}

// ---------------------------------------------------------------------------------------------
// Rendu du flow
// ---------------------------------------------------------------------------------------------

// Matériau "produit" par une étape - sa pastille reprend la couleur du dessin et de la légende.
function stepMaterial(step) {
  if (step.kind === "lithography") return step.resist_material;
  if (step.kind === "deposition" || step.kind === "epitaxial_growth" || step.kind === "faceted_growth") return step.material;
  return null;
}

function chipSubtitle(step) {
  return stepSummary(step).split(" · ").slice(0, 2).join(" · ");
}


function lengthLabel(length) {
  return `${length.value} ${length.unit === "um" ? "µm" : length.unit}`;
}

function substrateChipHtml() {
  const substrate = substrateSpec();
  const variations = state.wizardScreen === "variations";
  const selected = variations ? variationEditingStepIndex === -1 : state.selectedIndex === -1 && !hasMultiSelection() && !state.selectedBrickGroup;
  const color = state.materialColors[substrate.material];
  const factorCount = variations ? factorsOnStep(-1).reduce((acc, f) => acc * f.values.length, 1) : 1;
  const hasFactor = variations && factorsOnStep(-1).length > 0;
  return `
    <div class="sb-chip sb-chip--substrate ${selected ? "is-selected" : ""}" role="button" id="sb-chip--1" data-index="-1"
         tabindex="${selected ? 0 : -1}" aria-pressed="${selected}" title="Substrat : ${escapeHtml(substrate.material)}">
      <span class="sb-chip__mat" style="${color ? `--mat:${color};` : ""}" aria-hidden="true"></span>
      <span class="sb-chip__icon sb-chip__icon--substrate" aria-hidden="true">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="14" width="18" height="6" rx="1"/><path d="M3 10h18"/></svg>
      </span>
      <span class="sb-chip__body">
        <span class="sb-chip__top"><span class="sb-chip__num">S</span><span class="sb-chip__name">Substrat</span></span>
        <span class="sb-chip__sub">${escapeHtml(substrate.material)} · ${escapeHtml(lengthLabel(substrate.thickness))}</span>
      </span>
      ${hasFactor ? `<span class="sb-chip__badge sb-chip__badge--factor" title="Paramètre varié">×${factorCount}</span>` : ""}
    </div>`;
}

function stepChipHtml(i) {
  const step = state.steps[i];
  const def = STEP_KIND_DEFS[step.kind];
  const variations = state.wizardScreen === "variations";
  const multi = state.selectedStepIndices.has(i);
  const selected = (variations ? variationEditingStepIndex === i : state.selectedIndex === i && !state.selectedBrickGroup) || multi;
  const dim = variations && !isVariableTarget(i);
  const material = stepMaterial(step);
  const color = material ? state.materialColors[material] : null;
  const factorCount = variations ? factorsOnStep(i).reduce((acc, f) => acc * f.values.length, 1) : 1;
  const hasFactor = variations && factorsOnStep(i).length > 0;
  const declared = step.declaredParams && step.declaredParams.length;
  const title = dim ? `${step.name} - aucun paramètre à faire varier sur ce type d'étape` : `${def.label} — ${step.name}\n${stepSummary(step)}`;
  return `
    <div class="sb-chip ${selected ? "is-selected" : ""} ${multi ? "is-multi" : ""} ${dim ? "is-dim" : ""}" role="button" id="sb-chip-${i}" data-index="${i}"
         tabindex="${selected && !multi ? 0 : -1}" aria-pressed="${selected}" aria-disabled="${dim}" draggable="${variations ? "false" : "true"}"
         title="${escapeHtml(title)}" style="--kind:${def.color};--kind-tint:${def.tint};">
      <span class="sb-chip__mat" style="${color ? `--mat:${color};` : ""}" aria-hidden="true"></span>
      <span class="sb-chip__icon" aria-hidden="true"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${def.iconPath}</svg></span>
      <span class="sb-chip__body">
        <span class="sb-chip__top"><span class="sb-chip__num">${String(i + 1).padStart(2, "0")}</span><span class="sb-chip__name">${escapeHtml(step.name)}</span></span>
        <span class="sb-chip__sub">${escapeHtml(chipSubtitle(step))}</span>
      </span>
      ${declared ? `<span class="sb-chip__badge" title="${declared} paramètre(s) déclaré(s)">+${declared}</span>` : ""}
      ${hasFactor ? `<span class="sb-chip__badge sb-chip__badge--factor" title="Paramètre varié">×${factorCount}</span>` : ""}
      ${multi ? `<span class="sb-chip__check" aria-hidden="true"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg></span>` : ""}
    </div>`;
}

function gapHtml(gap) {
  const disabled = state.wizardScreen !== "structure";
  return `
    <div class="sb-gap" data-gap="${gap}" aria-hidden="${disabled}">
      <span class="sb-gap__line" aria-hidden="true"></span>
      ${disabled ? "" : `<button class="sb-gap__add" type="button" tabindex="-1" data-gap="${gap}" title="Insérer une étape ici" aria-label="Insérer une étape ici">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
      </button>`}
    </div>`;
}

function brickGroupHtml(groupId, start, end) {
  const name = state.steps[start].brick_name || "Brique";
  const count = end - start + 1;
  const variations = state.wizardScreen === "variations";
  const containsSelection =
    (state.selectedIndex >= start && state.selectedIndex <= end && state.selectedBrickGroup !== groupId) ||
    [...state.selectedStepIndices].some((k) => k >= start && k <= end) ||
    (variations && variationEditingStepIndex !== null && variationEditingStepIndex >= start && variationEditingStepIndex <= end);
  // une brique repliée se déplie d'office si ce qui est sélectionné est à l'intérieur - et à
  // l'écran variations, où il faut pouvoir cliquer chacune de ses étapes
  const collapsed = state.collapsedBrickGroups.has(groupId) && !containsSelection && !variations;
  const selected = state.selectedBrickGroup === groupId && !variations;
  let inner;
  if (collapsed) {
    const kinds = state.steps.slice(start, end + 1).map((s) => STEP_KIND_DEFS[s.kind]);
    inner = `
      <div class="sb-chip sb-chip--brick ${selected ? "is-selected" : ""}" role="button" data-brick="${escapeHtml(groupId)}" tabindex="${selected ? 0 : -1}"
           aria-pressed="${selected}" draggable="${variations ? "false" : "true"}" title="${escapeHtml(name)} - ${count} étapes (repliée)">
        <span class="sb-chip__body">
          <span class="sb-chip__top"><span class="sb-chip__num">${String(start + 1).padStart(2, "0")}–${String(end + 1).padStart(2, "0")}</span><span class="sb-chip__name">${escapeHtml(name)}</span></span>
          <span class="sb-chip__kinds">${kinds
            .slice(0, 6)
            .map((def) => `<span class="sb-chip__kind" style="--kind:${def.color};--kind-tint:${def.tint};"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4">${def.iconPath}</svg></span>`)
            .join("")}${kinds.length > 6 ? `<span class="sb-chip__more">+${kinds.length - 6}</span>` : ""}</span>
        </span>
      </div>`;
  } else {
    const parts = [];
    for (let k = start; k <= end; k++) {
      parts.push(stepChipHtml(k));
      if (k < end) parts.push(gapHtml(k + 1));
    }
    inner = parts.join("");
  }
  return `
    <div class="sb-brick ${collapsed ? "is-collapsed" : ""} ${selected ? "is-selected" : ""}" data-group-id="${escapeHtml(groupId)}">
      <div class="sb-brick__label" data-brick-drag="${escapeHtml(groupId)}" draggable="${variations ? "false" : "true"}">
        <button class="sb-brick__toggle js-toggle-brick" type="button" data-group-id="${escapeHtml(groupId)}" aria-expanded="${!collapsed}" aria-label="${collapsed ? "Déplier" : "Replier"} la brique ${escapeHtml(name)}" title="${collapsed ? "Déplier" : "Replier"}">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="transform:rotate(${collapsed ? -90 : 0}deg);"><path d="M6 9l6 6 6-6"/></svg>
        </button>
        <button class="sb-brick__name js-select-brick" type="button" data-group-id="${escapeHtml(groupId)}" title="Sélectionner la brique">
          <span class="sb-brick__tag">Brique</span>${escapeHtml(name)}${collapsed ? "" : ` <span class="sb-brick__count">· ${count}</span>`}
        </button>
      </div>
      <div class="sb-brick__chips">${inner}</div>
    </div>`;
}

function addChipHtml() {
  if (state.wizardScreen !== "structure") return "";
  return `
    <button class="sb-chip sb-chip--add" type="button" id="add-step-shortcut-btn" data-gap="${state.steps.length}" title="Ajouter une étape à la fin">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
      <span>Ajouter une étape</span>
    </button>`;
}

function renderRail() {
  const track = document.getElementById("steps-list");
  const n = state.steps.length;
  document.getElementById("steps-count").textContent = n;
  document.getElementById("steps-count-plural").textContent = n > 1 ? "s" : "";
  const focusInside = track.contains(document.activeElement);
  const parts = [substrateChipHtml(), gapHtml(0)];
  let i = 0;
  while (i < n) {
    const groupId = state.steps[i].brick_group_id;
    if (!groupId) {
      parts.push(stepChipHtml(i), gapHtml(i + 1));
      i += 1;
      continue;
    }
    const [start, end] = brickSpanAt(i);
    parts.push(brickGroupHtml(groupId, start, end), gapHtml(end + 1));
    i = end + 1;
  }
  parts.push(addChipHtml());
  if (n === 0 && state.wizardScreen === "structure") {
    parts.push(`<div class="sb-flow__empty">Commencez par un outil de la palette - ou glissez-le ici.</div>`);
  }
  track.innerHTML = parts.join("");
  track.classList.toggle("is-varying", state.wizardScreen === "variations");
  updateFlowHint();
  if (focusInside) {
    const focusTarget = track.querySelector('[tabindex="0"]');
    if (focusTarget) focusTarget.focus({ preventScroll: true });
  }
  highlightSelectedLayer();
}

function updateFlowHint() {
  const hint = document.getElementById("steps-list-help");
  if (state.wizardScreen === "variations") {
    hint.innerHTML = "Cliquez une étape pour faire varier un de ses paramètres";
  } else if (hasMultiSelection()) {
    hint.innerHTML = `<strong>${state.selectedStepIndices.size} étapes sélectionnées</strong> · <kbd>Échap</kbd> pour désélectionner`;
  } else {
    hint.innerHTML = "Clic : sélectionner · glisser : réordonner · <kbd>Ctrl</kbd>+clic : sélection multiple";
  }
}

function scrollChipIntoView(index) {
  const chip = document.getElementById(`sb-chip-${index}`);
  if (chip) chip.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
}

// ---------------------------------------------------------------------------------------------
// Interactions du flow (délégation : le contenu est reconstruit à chaque rendu)
// ---------------------------------------------------------------------------------------------

const flowTrack = document.getElementById("steps-list");

flowTrack.addEventListener("click", (event) => {
  const addBtn = event.target.closest(".sb-gap__add, .sb-chip--add");
  if (addBtn) {
    openKindMenu(addBtn, parseInt(addBtn.dataset.gap, 10));
    return;
  }
  const toggle = event.target.closest(".js-toggle-brick");
  if (toggle) {
    toggleBrickCollapse(toggle.dataset.groupId);
    return;
  }
  const brickName = event.target.closest(".js-select-brick");
  if (brickName) {
    selectBrickGroup(brickName.dataset.groupId);
    return;
  }
  const collapsedBrick = event.target.closest(".sb-chip--brick");
  if (collapsedBrick) {
    selectBrickGroup(collapsedBrick.dataset.brick);
    return;
  }
  const chip = event.target.closest(".sb-chip[data-index]");
  if (!chip) return;
  selectStep(parseInt(chip.dataset.index, 10), { toggle: event.ctrlKey || event.metaKey, range: event.shiftKey });
});

// Double-clic sur une puce : on file directement au premier champ de l'inspecteur.
flowTrack.addEventListener("dblclick", (event) => {
  if (event.target.closest(".sb-chip[data-index]")) focusInspector();
});

// Molette verticale -> défilement horizontal du flow (sans Maj), tant qu'il déborde.
flowTrack.addEventListener(
  "wheel",
  (event) => {
    if (event.ctrlKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
    if (flowTrack.scrollWidth <= flowTrack.clientWidth) return;
    flowTrack.scrollLeft += event.deltaY;
    event.preventDefault();
  },
  { passive: false }
);

// -- glisser-déposer : réordonner les puces, ou déposer un outil / une brique de la palette -----

let dragPayload = null; // {type: "move", start, end} | {type: "kind", kind} | {type: "brick", brick}

function startFlowDrag(event, payload) {
  dragPayload = payload;
  event.dataTransfer.effectAllowed = payload.type === "move" ? "move" : "copy";
  try {
    event.dataTransfer.setData("text/plain", payload.type);
  } catch (err) {
    /* certains navigateurs refusent setData hors dragstart - sans conséquence ici */
  }
  document.getElementById("sb-flow").classList.add("is-dragging");
}

function endFlowDrag() {
  dragPayload = null;
  document.getElementById("sb-flow").classList.remove("is-dragging");
  flowTrack.querySelectorAll(".is-drop-target, .is-drag-source").forEach((el) => el.classList.remove("is-drop-target", "is-drag-source"));
}

flowTrack.addEventListener("dragstart", (event) => {
  if (state.wizardScreen !== "structure") return;
  const label = event.target.closest("[data-brick-drag]");
  const collapsed = event.target.closest(".sb-chip--brick");
  const chip = event.target.closest(".sb-chip[data-index]");
  let span = null;
  if (label || collapsed) span = brickGroupSpan((label && label.dataset.brickDrag) || collapsed.dataset.brick);
  else if (chip && chip.dataset.index !== "-1") span = brickSpanAt(parseInt(chip.dataset.index, 10));
  if (!span) {
    event.preventDefault();
    return;
  }
  startFlowDrag(event, { type: "move", start: span[0], end: span[1] });
  (label ? label.closest(".sb-brick") : collapsed || chip.closest(".sb-brick") || chip).classList.add("is-drag-source");
});

// Le trou le plus proche horizontalement du pointeur - c'est là que le dépôt insérera.
function nearestGap(clientX) {
  let best = null;
  let bestDistance = Infinity;
  flowTrack.querySelectorAll(".sb-gap").forEach((gap) => {
    const rect = gap.getBoundingClientRect();
    const distance = Math.abs(rect.left + rect.width / 2 - clientX);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = gap;
    }
  });
  return best;
}

flowTrack.addEventListener("dragover", (event) => {
  if (!dragPayload) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = dragPayload.type === "move" ? "move" : "copy";
  const gap = nearestGap(event.clientX);
  flowTrack.querySelectorAll(".sb-gap.is-drop-target").forEach((el) => el !== gap && el.classList.remove("is-drop-target"));
  if (gap) gap.classList.add("is-drop-target");
  // défilement automatique près des bords
  const rect = flowTrack.getBoundingClientRect();
  if (event.clientX < rect.left + 48) flowTrack.scrollLeft -= 14;
  else if (event.clientX > rect.right - 48) flowTrack.scrollLeft += 14;
});

flowTrack.addEventListener("dragleave", (event) => {
  if (!flowTrack.contains(event.relatedTarget)) flowTrack.querySelectorAll(".sb-gap.is-drop-target").forEach((el) => el.classList.remove("is-drop-target"));
});

flowTrack.addEventListener("drop", (event) => {
  if (!dragPayload) return;
  event.preventDefault();
  const gapEl = nearestGap(event.clientX);
  const payload = dragPayload;
  endFlowDrag();
  if (!gapEl) return;
  const gap = parseInt(gapEl.dataset.gap, 10);
  if (payload.type === "move") moveBlockToGap(payload.start, payload.end, gap);
  else if (payload.type === "kind") insertStepOfKind(payload.kind, gap);
  else if (payload.type === "brick") insertBrickAt(payload.brick, gap);
});

document.addEventListener("dragend", endFlowDrag);
