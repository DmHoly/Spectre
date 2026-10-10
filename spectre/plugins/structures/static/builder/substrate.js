/* Lecture/écriture du formulaire de substrat - utilisé par le rendu (simulation.js), l'export de
   code (code-export.js) et le chargement d'un procédé existant (experience-launch.js, library-mode.js).

   Le réseau de fils (gabarit SAG, `substrate.lattice = {pitch, wires}`) fixe la largeur du domaine
   (pas × fils) et les ouvertures des lithographies ancrées (`step.lattice_opening = {diameter}`, un
   trou par fil, centré dans sa maille) - le serveur les recalcule de même
   (spectre.plugins.structures.simulation.resolve_lattice) ; ici, on les tient à jour pour que la
   puce, le formulaire et l'export disent la même chose que le dessin. */

const MAX_LATTICE_WIRES = 50;

function setSubstrateFields(substrate) {
  ensureSelectValue("substrate-material", substrate.material);
  document.getElementById("substrate-width").value = substrate.domain_width.value;
  ensureSelectValue("substrate-width-unit", substrate.domain_width.unit, "");
  document.getElementById("substrate-thickness").value = substrate.thickness.value;
  ensureSelectValue("substrate-thickness-unit", substrate.thickness.unit, "");
  const lattice = substrate.lattice || null;
  document.getElementById("substrate-lattice-on").checked = Boolean(lattice);
  if (lattice) {
    document.getElementById("substrate-lattice-pitch").value = lattice.pitch;
    document.getElementById("substrate-lattice-wires").value = lattice.wires;
  }
  syncLatticeUi();
}

// Le réseau du formulaire, null sans réseau (ou un pas illisible).
function substrateLattice() {
  if (!document.getElementById("substrate-lattice-on").checked) return null;
  const pitch = parseFloat(document.getElementById("substrate-lattice-pitch").value);
  if (!(pitch > 0)) return null;
  const wires = Math.min(MAX_LATTICE_WIRES, Math.max(1, parseInt(document.getElementById("substrate-lattice-wires").value, 10) || 1));
  return { pitch, wires };
}

function substrateSpec() {
  const lattice = substrateLattice();
  const spec = {
    material: document.getElementById("substrate-material").value,
    domain_width: lattice ? { value: roundNm(lattice.pitch * lattice.wires), unit: "nm" } : lengthValue("substrate-width"),
    thickness: lengthValue("substrate-thickness"),
  };
  if (lattice) spec.lattice = lattice;
  return spec;
}

function roundNm(value) {
  return Math.round(value * 1000) / 1000;
}

// Un trou de `diameter` nm centré sur chaque fil du réseau (même calcul que le serveur).
function latticeOpenings(lattice, diameter) {
  const half = diameter / 2;
  const openings = [];
  for (let i = 0; i < lattice.wires; i++) {
    const center = (i + 0.5) * lattice.pitch;
    openings.push([roundNm(center - half), roundNm(center + half)]);
  }
  return openings;
}

// Recalcule les ouvertures des lithographies ancrées au réseau (sans réseau : elles gardent les
// leurs). Renvoie vrai si une étape a changé.
function applyLatticeToSteps(steps = state.steps) {
  const lattice = substrateLattice();
  if (!lattice) return false;
  let changed = false;
  steps.forEach((step) => {
    if (step.kind !== "lithography" || !step.lattice_opening || !(step.lattice_opening.diameter > 0)) return;
    const openings = latticeOpenings(lattice, step.lattice_opening.diameter);
    if (JSON.stringify(openings) !== JSON.stringify(step.openings)) {
      step.openings = openings;
      changed = true;
    }
  });
  return changed;
}

// Une bibliothèque (structure enregistrée, brique) range l'ancrage de ses lithographies par
// position d'étape, à part des étapes (que le serveur relit en étapes StructureForge) ; un procédé
// d'étude, lui, le garde sur l'étape même (`lattice_opening`).
function latticeOpeningsPayload(steps) {
  const out = {};
  steps.forEach((step, i) => {
    if (step.kind === "lithography" && step.lattice_opening) out[i] = step.lattice_opening;
  });
  return out;
}

function attachLatticeOpenings(steps, openings) {
  if (!openings) return steps;
  return steps.map((step, i) => {
    const opening = openings[i] || openings[String(i)];
    return opening && step.kind === "lithography" ? { ...step, lattice_opening: { ...opening } } : step;
  });
}

// Largeur du domaine figée (et tenue à jour) quand le réseau la fixe ; l'outil « fils » du dessin.
function syncLatticeUi() {
  const on = document.getElementById("substrate-lattice-on").checked;
  document.getElementById("substrate-lattice-fields").hidden = !on;
  const width = document.getElementById("substrate-width");
  const widthUnit = document.getElementById("substrate-width-unit");
  const lattice = substrateLattice();
  width.disabled = Boolean(lattice);
  widthUnit.disabled = Boolean(lattice);
  width.title = lattice ? "Fixée par le réseau de fils : pas × fils" : "";
  if (lattice) {
    width.value = roundNm(lattice.pitch * lattice.wires);
    widthUnit.value = "nm";
  }
  const tool = document.getElementById("sb-wires");
  tool.hidden = !lattice;
  if (lattice) {
    document.getElementById("wires-label").textContent = `${lattice.wires} fil${lattice.wires > 1 ? "s" : ""}`;
    document.getElementById("wires-less-btn").disabled = lattice.wires <= 1;
    document.getElementById("wires-more-btn").disabled = lattice.wires >= MAX_LATTICE_WIRES;
  }
}

// Une retouche du réseau : la largeur, les lithographies ancrées, la puce, le formulaire ouvert.
function latticeChanged() {
  syncLatticeUi();
  applyLatticeToSteps();
  if (typeof renderRail === "function") renderRail();
  if (state.selectedIndex >= 0 && state.steps[state.selectedIndex] && state.steps[state.selectedIndex].kind === "lithography" && typeof renderInspector === "function") {
    renderInspector();
  }
  if (typeof invalidateVariations === "function") invalidateVariations();
  scheduleSimulate();
}

// Pose (ou remplace) le réseau - depuis une lithographie aux ouvertures régulières (step-kinds.js).
function setSubstrateLattice(lattice) {
  document.getElementById("substrate-lattice-on").checked = true;
  document.getElementById("substrate-lattice-pitch").value = lattice.pitch;
  document.getElementById("substrate-lattice-wires").value = lattice.wires;
  latticeChanged();
}

function setLatticeWires(wires) {
  const lattice = substrateLattice();
  if (!lattice) return;
  const next = Math.min(MAX_LATTICE_WIRES, Math.max(1, wires));
  if (next === lattice.wires) return;
  document.getElementById("substrate-lattice-wires").value = next;
  latticeChanged();
  captureHistory();
}

["substrate-lattice-on", "substrate-lattice-pitch", "substrate-lattice-wires"].forEach((id) => {
  const el = document.getElementById(id);
  el.addEventListener("input", latticeChanged);
  el.addEventListener("change", () => {
    latticeChanged();
    captureHistory();
  });
});
document.getElementById("wires-less-btn").addEventListener("click", () => {
  const lattice = substrateLattice();
  if (lattice) setLatticeWires(lattice.wires - 1);
});
document.getElementById("wires-more-btn").addEventListener("click", () => {
  const lattice = substrateLattice();
  if (lattice) setLatticeWires(lattice.wires + 1);
});
document.getElementById("wires-one-btn").addEventListener("click", () => setLatticeWires(1));
