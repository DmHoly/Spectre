/* La trace d'une brique copiée dans une structure : conforme, modifiée, nouvelle version.

   Une brique insérée garde sa source et la version de la brique de bibliothèque d'alors
   (`brick_source`, `brick_version`) - jamais un lien vivant. Comme pour un préset (presets.js),
   l'inspecteur de la brique dit si elle lui est restée conforme, si elle a été modifiée depuis ou si
   la brique a changé, et propose de la réappliquer, de mettre la brique à jour avec cette copie, ou
   d'oublier d'où elle vient. */

// Le contenu d'une étape de brique, tel qu'on le compare : sans ce qui ne tient qu'à la structure
// (ids, étiquette de brique) ni les ouvertures d'une lithographie ancrée, qui suivent le nombre de
// fils vus (le réseau, une vue).
function brickStepContent(step) {
  const content = presetContentOf(step);
  if (step.lattice_opening) delete content.fields.openings;
  return content;
}

// Le substrat de la structure comparé à celui d'une brique de départ, le nombre de fils vus (et la
// largeur qui en suit) à part.
function sameBrickSubstrate(theirs) {
  const mine = substrateSpec();
  const pitch = (s) => (s.lattice ? s.lattice.pitch : null);
  return mine.material === theirs.material && toNm(mine.thickness) === toNm(theirs.thickness) && pitch(mine) === pitch(theirs);
}

function sameBrickContent(steps, brick, start) {
  if (steps.length !== brick.steps.length) return false;
  if (!steps.every((step, k) => samePresetContent(brickStepContent(step), brickStepContent(brick.steps[k])))) return false;
  // une brique de départ posée en tête : son substrat compte aussi
  if (brick.substrate && start === 0) return sameBrickSubstrate(brick.substrate);
  return true;
}

// {state, brick, version} pour la brique `groupId` de la structure : "same" | "modified" |
// "outdated" (la brique de bibliothèque a une version plus récente) | "missing" (retirée, hors de
// portée) ; null pour une brique sans source.
function brickGroupStatus(groupId) {
  const span = brickGroupSpan(groupId);
  if (!span) return null;
  const first = state.steps[span[0]];
  if (!first.brick_source) return null;
  const brick = findBrickEntry(first.brick_source);
  const version = first.brick_version || null;
  if (!brick) return { state: "missing", brick: null, version };
  if (version && (brick.version || 1) !== version) return { state: "outdated", brick, version };
  return { state: sameBrickContent(state.steps.slice(span[0], span[1] + 1), brick, span[0]) ? "same" : "modified", brick, version };
}

const BRICK_STATUS_TEXT = {
  same: "conforme à la brique",
  modified: "modifiée depuis",
  outdated: "la brique a changé depuis",
  missing: "brique retirée ou introuvable",
};

function renderBrickOrigin(groupId) {
  const holder = document.getElementById("brick-group-origin");
  const status = brickGroupStatus(groupId);
  if (!status) {
    holder.innerHTML = "";
    return;
  }
  const span = brickGroupSpan(groupId);
  const first = state.steps[span[0]];
  const { brick } = status;
  const canReapply = brick && status.state !== "same";
  const canUpdate = brick && brick.can_edit && status.state === "modified";
  const name = brick ? brick.name : first.brick_name || "";
  holder.innerHTML = `
    <div class="sb-preset-origin">
      <div class="sb-preset-origin__line">
        <span class="sb-preset-origin__name">Brique « ${escapeHtml(name)} »${status.version ? ` · v${status.version}` : ""}</span>
        <span class="sb-preset-origin__status is-${status.state}">${BRICK_STATUS_TEXT[status.state]}${status.state === "outdated" ? ` (v${brick.version})` : ""}</span>
      </div>
      <div class="sb-preset-origin__actions">
        ${canReapply ? `<button class="btn btn-line" type="button" id="brick-reapply-btn" title="Remet la brique telle que la bibliothèque la décrit aujourd'hui">Réappliquer la brique</button>` : ""}
        ${canUpdate ? `<button class="btn btn-line" type="button" id="brick-update-btn" title="Enregistre cette copie dans la brique (nouvelle version) - sans toucher aux structures déjà construites">Mettre à jour la brique</button>` : ""}
        <button class="btn btn-line" type="button" id="brick-detach-btn" title="Oublier d'où vient cette brique (elle reste groupée)">Détacher</button>
      </div>
    </div>`;
  const reapply = document.getElementById("brick-reapply-btn");
  if (reapply) reapply.addEventListener("click", () => reapplyBrick(groupId));
  const update = document.getElementById("brick-update-btn");
  if (update) update.addEventListener("click", () => updateLibraryBrick(groupId));
  document.getElementById("brick-detach-btn").addEventListener("click", () => detachBrick(groupId));
}

// La brique `groupId` remplacée par la brique de bibliothèque telle qu'elle est aujourd'hui (même
// groupe, même place ; une brique de départ posée en tête reprend aussi son substrat, le nombre de
// fils vus gardé).
function reapplyBrick(groupId) {
  const status = brickGroupStatus(groupId);
  if (!status || !status.brick) return;
  const span = brickGroupSpan(groupId);
  const brick = status.brick;
  state.steps.splice(span[0], span[1] - span[0] + 1, ...copiedBrickSteps(brick, groupId));
  if (brick.substrate && span[0] === 0) {
    const substrate = JSON.parse(JSON.stringify(brick.substrate));
    const current = substrateLattice();
    if (substrate.lattice && current) substrate.lattice.wires = current.wires;
    setSubstrateFields(substrate);
  }
  applyLatticeToSteps();
  state.collapsedBrickGroups.add(groupId);
  state.selectedStepIndices.clear();
  state.selectedBrickGroup = groupId;
  state.selectedIndex = span[0];
  commitStructure();
}

// La brique de bibliothèque mise à jour avec cette copie : une nouvelle version, que la copie suit.
async function updateLibraryBrick(groupId) {
  const status = brickGroupStatus(groupId);
  if (!status || !status.brick) return;
  clearError();
  const span = brickGroupSpan(groupId);
  const steps = state.steps.slice(span[0], span[1] + 1).map((s) => withoutStepId(stripBrickTag(s)));
  try {
    const updated = await processLibraryApi.updateTechBrick(status.brick.id, {
      steps,
      declared_params: declaredParamsPayload(steps),
      layer_labels: layerLabelsPayload(steps),
      recipes: processRecipesPayload(steps),
      preset_origins: presetOriginsPayload(steps),
      lattice_openings: latticeOpeningsPayload(steps),
      // une brique de départ garde un substrat : celui de la structure quand elle est en tête
      ...(status.brick.substrate && span[0] === 0 ? { substrate: substrateSpec() } : {}),
    });
    state.techBricks = state.techBricks.map((b) => (b.id === updated.id ? updated : b));
    for (let k = span[0]; k <= span[1]; k++) state.steps[k] = { ...state.steps[k], brick_version: updated.version || 1 };
    renderBrickList();
    state.selectedBrickGroup = groupId;
    commitStructure();
  } catch (err) {
    showError(err);
  }
}

function detachBrick(groupId) {
  state.steps.forEach((step, k) => {
    if (step.brick_group_id !== groupId) return;
    const { brick_source, brick_version, ...rest } = step;
    state.steps[k] = rest;
  });
  state.selectedBrickGroup = groupId;
  commitStructure();
}
