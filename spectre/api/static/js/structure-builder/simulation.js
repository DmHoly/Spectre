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

async function simulateNow() {
  clearError();
  try {
    const result = await api.post(`/api/projects/${slug}/structures/simulate`, {
      substrate: substrateSpec(),
      steps: state.steps,
    });
    state.frames = result.frames;
    state.materialColors = result.material_colors;
    state.currentFrame = state.frames.length - 1;
    renderFrame();
  } catch (err) {
    showError(err);
  }
}

// Coalesces the several renderSteps()/substrate-change calls that can happen in the same tick
// (e.g. moving a step touches editingIndex then re-renders) into a single simulate call, without
// making the auto-preview feel like a deliberate delay - not a debounce for its own sake.
let simulateTimer = null;
function scheduleSimulate(delay = 120) {
  if (simulateTimer) clearTimeout(simulateTimer);
  simulateTimer = setTimeout(() => {
    simulateTimer = null;
    simulateNow();
  }, delay);
}

["substrate-material", "substrate-width", "substrate-width-unit", "substrate-thickness", "substrate-thickness-unit"].forEach(
  (id) => document.getElementById(id).addEventListener("change", () => scheduleSimulate())
);

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
