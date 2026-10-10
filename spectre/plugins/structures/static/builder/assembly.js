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
    candidates.forEach((b) => {
      options.push(`<option value="${escapeHtml(b.id)}" ${current && current.brick_source === b.id ? "selected" : ""}>${escapeHtml(b.name)}</option>`);
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
