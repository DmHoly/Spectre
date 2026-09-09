/* Aperçu simulé : la scrubber (une image par étape), le zoom, et l'appel à /structures/simulate
   qui redessine tout - StructureForge fait le calcul, cette page assemble la requête et affiche
   ce qui revient. */

function renderScrubber() {
  const track = document.getElementById("scrubber-track");
  const label = document.getElementById("scrubber-label");
  if (!state.frames || state.frames.length === 0) {
    track.innerHTML = "";
    label.textContent = "Pas encore simulé";
    return;
  }
  const n = state.frames.length;
  track.innerHTML = state.frames
    .map((f, i) => {
      const pct = n === 1 ? 0 : (i / (n - 1)) * 100;
      return `<div class="scrubber-dot" data-index="${i}" style="left:${pct}%;"></div>`;
    })
    .join("");
  track.querySelectorAll(".scrubber-dot").forEach((dot) => {
    dot.addEventListener("click", () => {
      state.currentFrame = parseInt(dot.dataset.index, 10);
      renderFrame();
    });
  });
  const current = state.frames[state.currentFrame];
  label.textContent = `${state.currentFrame + 1} / ${n} · ${current.step_name}`;
}

function applyZoom() {
  const svg = document.querySelector("#svg-container svg");
  if (svg) svg.style.transform = `scale(${state.zoom})`;
  document.getElementById("zoom-level-label").textContent = `${Math.round(state.zoom * 100)}%`;
}

function renderFrame() {
  const frame = state.frames ? state.frames[state.currentFrame] : null;
  document.getElementById("svg-container").innerHTML = frame ? frame.svg : "";
  const legend = document.getElementById("legend");
  const materials = frame ? frame.materials : [];
  legend.innerHTML = materials
    .map((name) => `<div class="legend-item"><span class="legend-swatch" style="background:${state.materialColors[name] || "#999"};"></span>${escapeHtml(name)}</div>`)
    .join("");
  renderScrubber();
  highlightSelectedLayer();
  applyZoom();
}

// `overrideSteps` simule une liste d'étapes différente de `state.steps` sans la commiter (aperçu
// d'une étape en cours d'ajout, pas encore validée). `silent` avale l'erreur au lieu de l'afficher
// - une valeur transitoire pendant la frappe (un champ encore vide, une plage mal formée) ne doit
// pas clignoter un message d'erreur à chaque caractère ; seul un clic délibéré sur "Ajouter"/
// "Enregistrer" doit remonter un vrai échec de validation.
async function simulateNow(overrideSteps, { silent = false } = {}) {
  clearError();
  try {
    const result = await api.post(`/api/microprojets/${slug}/structures/simulate`, {
      substrate: substrateSpec(),
      steps: overrideSteps || state.steps,
    });
    state.frames = result.frames;
    state.materialColors = result.material_colors;
    state.currentFrame = state.frames.length - 1;
    renderFrame();
  } catch (err) {
    if (!silent) showError(err);
  }
}

// Coalesces the several renderSteps()/substrate-change/keystroke calls that can happen in the
// same tick into a single simulate call, without making the auto-preview feel like a deliberate
// delay - not a debounce for its own sake.
let simulateTimer = null;
let simulatePending = null;
function scheduleSimulate(delay = 120, overrideSteps, opts) {
  if (simulateTimer) clearTimeout(simulateTimer);
  simulatePending = { overrideSteps, opts };
  simulateTimer = setTimeout(() => {
    simulateTimer = null;
    const { overrideSteps: steps, opts: pendingOpts } = simulatePending;
    simulatePending = null;
    simulateNow(steps, pendingOpts);
  }, delay);
}

["substrate-material", "substrate-width", "substrate-width-unit", "substrate-thickness", "substrate-thickness-unit"].forEach((id) => {
  const el = document.getElementById(id);
  // "input" : aperçu instantané à chaque frappe/sélection, sans capturer d'historique (un Ctrl+Z
  // par caractère tapé serait inutilisable). "change" (au blur, ou déjà déclenché par "input" pour
  // un <select>) capture l'historique une fois la valeur retenue - la double simulation que ça
  // provoque pour un <select> est absorbée par le debounce ci-dessus.
  el.addEventListener("input", () => scheduleSimulate());
  el.addEventListener("change", () => {
    captureHistory();
    scheduleSimulate();
  });
});

document.getElementById("zoom-in-btn").addEventListener("click", () => {
  state.zoom = Math.min(4, +(state.zoom + 0.25).toFixed(2));
  applyZoom();
});
document.getElementById("zoom-out-btn").addEventListener("click", () => {
  state.zoom = Math.max(0.25, +(state.zoom - 0.25).toFixed(2));
  applyZoom();
});
document.getElementById("zoom-reset-btn").addEventListener("click", () => {
  state.zoom = 1;
  applyZoom();
});
