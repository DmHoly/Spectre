/* Historique d'édition (annuler / rétablir) du constructeur de structure. Prend un instantané de
   {substrat + étapes} après chaque modification et permet de revenir en arrière (Ctrl+Z) ou de
   rétablir (Ctrl+Maj+Z / Ctrl+Y), ou via les boutons ↶ / ↷ de la barre du dessin.

   Purement côté client : n'annule que l'état de la structure en cours d'édition. Une brique déjà
   enregistrée dans la bibliothèque via « Grouper en brique » n'est pas supprimée du serveur par un
   Ctrl+Z (seules les étiquettes 🧱 posées sur les étapes courantes sont retirées). */

const undoStack = [];
const redoStack = [];
let historyBaseline = null; // dernier état connu, sérialisé
let historyReady = false; // reste faux pendant le chargement initial (modes bibliothèque/évolution...)

function currentHistorySnapshot() {
  return JSON.stringify({ steps: state.steps, substrate: substrateSpec() });
}

// Appelé une fois le chargement terminé : l'état courant devient le point zéro, rien à annuler.
function resetHistory() {
  undoStack.length = 0;
  redoStack.length = 0;
  historyBaseline = currentHistorySnapshot();
  historyReady = true;
  updateHistoryButtons();
}

// Appelé après chaque rendu de la liste d'étapes (renderSteps) et à chaque changement du substrat :
// si l'état a bougé depuis le dernier instantané, on empile l'ancien pour pouvoir y revenir.
function captureHistory() {
  if (!historyReady) return;
  const snap = currentHistorySnapshot();
  if (snap === historyBaseline) return;
  undoStack.push(historyBaseline);
  if (undoStack.length > 100) undoStack.shift();
  redoStack.length = 0;
  historyBaseline = snap;
  updateHistoryButtons();
}

function applyHistorySnapshot(serialized) {
  const snap = JSON.parse(serialized);
  state.steps = snap.steps;
  setSubstrateFields(snap.substrate);
  state.editingIndex = null;
  state.showStepForm = false;
  state.selectedStepIndices.clear();
  historyBaseline = serialized; // avant renderSteps pour que le captureHistory qu'il déclenche soit un no-op
  document.getElementById("step-form-title").textContent = "Ajouter une étape";
  document.getElementById("add-step-btn-label").textContent = "Ajouter cette étape";
  renderKindFields(document.getElementById("kind-select").value);
  renderSteps();
  updateHistoryButtons();
}

function undoEdit() {
  if (!undoStack.length) return;
  redoStack.push(historyBaseline);
  applyHistorySnapshot(undoStack.pop());
}

function redoEdit() {
  if (!redoStack.length) return;
  undoStack.push(historyBaseline);
  applyHistorySnapshot(redoStack.pop());
}

function updateHistoryButtons() {
  const undoBtn = document.getElementById("undo-edit-btn");
  const redoBtn = document.getElementById("redo-edit-btn");
  if (undoBtn) undoBtn.disabled = undoStack.length === 0;
  if (redoBtn) redoBtn.disabled = redoStack.length === 0;
}

document.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey)) return;
  // Dans un champ de saisie, on laisse Ctrl+Z faire l'annulation native du texte.
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "input" || tag === "select" || tag === "textarea") return;
  const key = e.key.toLowerCase();
  if (key === "z" && !e.shiftKey) {
    e.preventDefault();
    undoEdit();
  } else if ((key === "z" && e.shiftKey) || key === "y") {
    e.preventDefault();
    redoEdit();
  }
});

document.getElementById("undo-edit-btn").addEventListener("click", undoEdit);
document.getElementById("redo-edit-btn").addEventListener("click", redoEdit);
