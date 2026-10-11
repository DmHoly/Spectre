/* Assemblage d'une structure en macro-étapes : un gabarit SAG (substrat, masque, lithographie sur le
   réseau de fils), une épitaxie (des croissances, sans position) et un procédé (ce qu'on fait
   par-dessus) - chacun une brique de bibliothèque d'un rôle donné (`brick.role`), une seule par
   structure. Choisir une brique dans un emplacement la copie à sa place (avant l'épi pour le SAG,
   entre les deux pour l'épi, après pour le procédé) ou remplace celle du même rôle ; un gabarit SAG
   apporte aussi son substrat. Comme toute brique, une copie : aucun lien vivant. */

const BRICK_ROLE_DEFS = [
  { key: "sag", label: "Gabarit SAG", short: "SAG" },
  { key: "epi", label: "Épitaxie", short: "Épi" },
  { key: "process", label: "Procédé", short: "Procédé" },
];
const BRICK_ROLE_ORDER = BRICK_ROLE_DEFS.map((def) => def.key);

function brickRoleDef(role) {
  return BRICK_ROLE_DEFS.find((def) => def.key === role) || null;
}

function brickRoleLabel(role) {
  const def = brickRoleDef(role);
  return def ? def.label : "Brique";
}

function brickRoleShort(role) {
  const def = brickRoleDef(role);
  return def ? def.short : "Brique";
}

// [début, fin, id de groupe] de la brique de rôle `role` dans la structure, null sans elle.
function roleGroupSpan(role) {
  const start = state.steps.findIndex((s) => s.brick_role === role);
  if (start === -1) return null;
  const [first, end] = brickSpanAt(start);
  return [first, end, state.steps[start].brick_group_id];
}

// Où poser une macro-étape absente : le SAG en tête ; l'épi après le SAG (sinon avant le procédé,
// sinon à la fin) ; le procédé après l'épi (sinon après le SAG, sinon à la fin).
function assemblyInsertIndex(role) {
  const index = BRICK_ROLE_ORDER.indexOf(role);
  if (role === "sag") return 0;
  for (let k = index - 1; k >= 0; k--) {
    const span = roleGroupSpan(BRICK_ROLE_ORDER[k]);
    if (span) return span[1] + 1;
  }
  for (let k = index + 1; k < BRICK_ROLE_ORDER.length; k++) {
    const span = roleGroupSpan(BRICK_ROLE_ORDER[k]);
    if (span) return span[0];
  }
  return state.steps.length;
}

// Le substrat d'un gabarit SAG, le nombre de fils vus gardé (une vue, pas le gabarit).
function applySagSubstrate(brick) {
  if (!brick.substrate) return;
  const substrate = JSON.parse(JSON.stringify(brick.substrate));
  const current = substrateLattice();
  if (substrate.lattice && current) substrate.lattice.wires = current.wires;
  setSubstrateFields(substrate);
}

function assembleBrick(role, brick) {
  if (state.wizardScreen !== "structure") return;
  clearError();
  const span = roleGroupSpan(role);
  const groupId = span ? span[2] : generateBrickGroupId();
  const copied = copiedBrickSteps({ ...brick, role }, groupId);
  if (span) state.steps.splice(span[0], span[1] - span[0] + 1, ...copied);
  else state.steps.splice(assemblyInsertIndex(role), 0, ...copied);
  if (role === "sag") applySagSubstrate(brick);
  applyLatticeToSteps();
  state.collapsedBrickGroups.add(groupId);
  state.selectedStepIndices.clear();
  state.selectedBrickGroup = groupId;
  state.selectedIndex = state.steps.findIndex((s) => s.brick_group_id === groupId);
  commitStructure();
}

function removeAssembledBrick(role) {
  const span = roleGroupSpan(role);
  if (!span) return;
  const indices = [];
  for (let k = span[0]; k <= span[1]; k++) indices.push(k);
  deleteSteps(indices);
}

function renderAssembly() {
  const box = document.getElementById("assembly-slots");
  if (!box) return;
  // un préset est une seule étape : rien à assembler
  document.getElementById("palette-assembly").hidden = isPresetMode;
  const bricks = allTechBricks();
  box.innerHTML = BRICK_ROLE_DEFS.map((def) => {
    const span = roleGroupSpan(def.key);
    const current = span ? state.steps[span[0]] : null;
    const candidates = bricks.filter((b) => b.role === def.key);
    const known = current && candidates.some((b) => b.id === current.brick_source);
    const options = [`<option value="">${span ? "Retirer" : "—"}</option>`];
    if (current && !known) options.push(`<option value="__current" selected>${escapeHtml(current.brick_name || def.label)}</option>`);
    const mark = span ? brickStatusMark(span[2]) : "";
    candidates.forEach((b) => {
      const chosen = current && current.brick_source === b.id;
      options.push(`<option value="${escapeHtml(b.id)}" ${chosen ? "selected" : ""}>${escapeHtml(b.name)}${chosen ? escapeHtml(mark) : ""}</option>`);
    });
    if (!span) options[0] = `<option value="" selected>—</option>`;
    const empty = !candidates.length && !current;
    return `
      <label class="sb-assembly__slot ${span ? "is-filled" : ""}">
        <span class="sb-assembly__role sb-brick__tag sb-brick__tag--${def.key}">${escapeHtml(def.short)}</span>
        <select class="field sb-assembly__select" data-role="${def.key}" ${empty || state.wizardScreen !== "structure" ? "disabled" : ""}
                title="${escapeHtml(empty ? `Aucune brique « ${def.label} » dans la bibliothèque : enregistrez-en une (mode brique, ou « Grouper en brique »)` : def.label)}">
          ${options.join("")}
        </select>
      </label>`;
  }).join("");
}

document.getElementById("assembly-slots").addEventListener("change", (event) => {
  const select = event.target.closest(".sb-assembly__select");
  if (!select) return;
  const role = select.dataset.role;
  if (select.value === "__current") return;
  if (!select.value) {
    removeAssembledBrick(role);
    return;
  }
  const brick = findBrickEntry(select.value);
  if (brick) assembleBrick(role, brick);
});

// Le rôle proposé pour une sélection groupée en brique : ceux que la structure n'a pas encore.
function renderGroupRoleOptions() {
  const select = document.getElementById("group-brick-role");
  const chosen = select.value;
  select.innerHTML =
    `<option value="">Brique libre</option>` +
    BRICK_ROLE_DEFS.filter((def) => !roleGroupSpan(def.key)).map((def) => `<option value="${def.key}">${escapeHtml(def.label)}</option>`).join("");
  if ([...select.options].some((o) => o.value === chosen)) select.value = chosen;
}

// -- la trace d'une brique copiée : conforme, modifiée, nouvelle version ----------------------------
//
// Une brique insérée (ou posée par l'assemblage) garde sa source et la version de la brique de
// bibliothèque d'alors (`brick_source`, `brick_version`) - jamais un lien vivant. Comme pour un
// préset (presets.js), l'inspecteur de la brique dit si elle lui est restée conforme, si elle a été
// modifiée depuis ou si la brique a changé, et propose de la réappliquer, de mettre la brique à jour
// avec cette copie, ou d'oublier d'où elle vient.

// Le contenu d'une étape de brique, tel qu'on le compare : sans ce qui ne tient qu'à la structure
// (ids, étiquette de brique) ni les ouvertures d'une lithographie ancrée, qui suivent le nombre de
// fils vus (le réseau, une vue).
function brickStepContent(step) {
  const content = presetContentOf(step);
  if (step.lattice_opening) delete content.fields.openings;
  return content;
}

function sameBrickContent(steps, brick) {
  if (steps.length !== brick.steps.length) return false;
  if (!steps.every((step, k) => samePresetContent(brickStepContent(step), brickStepContent(brick.steps[k])))) return false;
  if (brick.role !== "sag" || !brick.substrate) return true;
  // un gabarit SAG : son substrat compte aussi, le nombre de fils vus (et la largeur qui en suit) à part
  const mine = substrateSpec();
  const theirs = brick.substrate;
  const pitch = (s) => (s.lattice ? s.lattice.pitch : null);
  return mine.material === theirs.material && toNm(mine.thickness) === toNm(theirs.thickness) && pitch(mine) === pitch(theirs);
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
  return { state: sameBrickContent(state.steps.slice(span[0], span[1] + 1), brick) ? "same" : "modified", brick, version };
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
// groupe, même place ; un gabarit SAG reprend aussi son substrat).
function reapplyBrick(groupId) {
  const status = brickGroupStatus(groupId);
  if (!status || !status.brick) return;
  const span = brickGroupSpan(groupId);
  const role = state.steps[span[0]].brick_role;
  if (role) {
    assembleBrick(role, status.brick);
    return;
  }
  state.steps.splice(span[0], span[1] - span[0] + 1, ...copiedBrickSteps(status.brick, groupId));
  applyLatticeToSteps();
  state.selectedBrickGroup = groupId;
  commitStructure();
}

// La brique de bibliothèque mise à jour avec cette copie : une nouvelle version, que la copie suit.
async function updateLibraryBrick(groupId) {
  const status = brickGroupStatus(groupId);
  if (!status || !status.brick) return;
  clearError();
  const span = brickGroupSpan(groupId);
  const steps = state.steps.slice(span[0], span[1] + 1).map((s) => withoutStepId(stripBrickTag(s)));
  const role = state.steps[span[0]].brick_role || null;
  try {
    const updated = await processLibraryApi.updateTechBrick(status.brick.id, {
      steps,
      declared_params: declaredParamsPayload(steps),
      layer_labels: layerLabelsPayload(steps),
      recipes: processRecipesPayload(steps),
      preset_origins: presetOriginsPayload(steps),
      lattice_openings: latticeOpeningsPayload(steps),
      ...(role === "sag" ? { substrate: substrateSpec() } : {}),
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

// Le petit mot de l'assemblage sur une macro-étape qui n'est plus celle de la bibliothèque.
function brickStatusMark(groupId) {
  const status = brickGroupStatus(groupId);
  if (!status) return "";
  if (status.state === "modified") return " · modifiée";
  if (status.state === "outdated") return ` · v${status.brick.version} disponible`;
  return "";
}
