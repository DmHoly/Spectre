/* Écrans de l'atelier. En mode bibliothèque/brique, il n'y en a qu'un (la structure). En mode
   expérience, le bandeau porte les trois étapes du lancement - 1. structure, 2. intention et
   objectifs, 3. variations et échantillons - chacune occupe l'atelier à tour de rôle, sans
   défilement de page ; les boutons d'action du bandeau suivent l'écran courant. */

const STAGES = ["structure", "intention", "variations"];

function setStage(stage) {
  if (!STAGES.includes(stage)) return;
  state.wizardScreen = stage;
  const shell = document.getElementById("sb-shell");
  shell.dataset.stage = stage;
  const intention = stage === "intention";
  const variations = stage === "variations";
  document.getElementById("wizard-step-intention").hidden = !intention;
  document.getElementById("sb-flow").hidden = intention;
  document.getElementById("sb-work").hidden = intention;
  document.getElementById("sb-palette").hidden = variations;
  document.getElementById("wizard-step-variations").hidden = !variations;
  document.getElementById("samples-panel").hidden = !variations;

  document.querySelectorAll(".sb-stage").forEach((btn) => {
    const current = btn.dataset.stage === stage;
    btn.classList.toggle("is-current", current);
    if (current) btn.setAttribute("aria-current", "step");
    else btn.removeAttribute("aria-current");
  });
  document.querySelectorAll("#stage-actions [data-show-on]").forEach((btn) => {
    const onThisStage = btn.dataset.showOn.split(" ").includes(stage);
    // #launch-btn (évolution directe) n'existe que pour une évolution - main.js le démasque
    btn.classList.toggle("sb-off-stage", !onThisStage);
  });
  closeKindMenu();
  hideLayerProvenance();
  renderRail();
  renderInspector();
  renderFrame();
  updateStageMeta();
}

// Petits repères d'avancement sous les étapes : nombre d'étapes de procédé, intention remplie.
function updateStageMeta() {
  const structureMeta = document.getElementById("stage-meta-structure");
  if (!structureMeta) return;
  const n = state.steps.length;
  structureMeta.textContent = `${n} étape${n > 1 ? "s" : ""}`;
  const ready = document.getElementById("exp-title").value.trim() && document.getElementById("exp-intent").value.trim();
  const intentionMeta = document.getElementById("stage-meta-intention");
  intentionMeta.textContent = ready ? "prête" : "à compléter";
  intentionMeta.classList.toggle("is-done", Boolean(ready));
}

document.querySelectorAll(".sb-stage").forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.stage;
    if (target === "variations") goToVariations();
    else setStage(target);
  });
});

document.getElementById("to-intention-btn").addEventListener("click", () => setStage("intention"));
document.getElementById("back-to-structure-btn").addEventListener("click", () => setStage("structure"));
["exp-title", "exp-intent"].forEach((id) => document.getElementById(id).addEventListener("input", updateStageMeta));

// Popover des raccourcis clavier (bouton du bandeau, ou « ? »).
const shortcutsPopover = document.getElementById("shortcuts-popover");
const shortcutsBtn = document.getElementById("shortcuts-btn");

function toggleShortcuts(force) {
  const open = force ?? shortcutsPopover.hidden;
  shortcutsPopover.hidden = !open;
  shortcutsBtn.setAttribute("aria-expanded", String(open));
  return open;
}

shortcutsBtn.addEventListener("click", () => toggleShortcuts());
document.addEventListener("mousedown", (event) => {
  if (!shortcutsPopover.hidden && !shortcutsPopover.contains(event.target) && !shortcutsBtn.contains(event.target)) toggleShortcuts(false);
});
