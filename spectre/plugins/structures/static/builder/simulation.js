/* Aperçu simulé : l'appel à POST /api/simulations (StructureForge fait le calcul, cette page
   assemble la requête et affiche ce qui revient), et la zone de dessin de l'atelier - l'image
   affichée suit la sélection du process flow (la structure *après* l'étape sélectionnée, ou la
   structure finale), zoom ajusté/molette/déplacement, et le lien couche <-> étape dans les deux
   sens (clic sur une couche = sélection de l'étape qui l'a produite ; étape sélectionnée = ses
   couches soulignées dans le dessin). */

// ---------------------------------------------------------------------------------------------
// Quelle image afficher
// ---------------------------------------------------------------------------------------------

// frames[0] est le substrat seul, frames[k + 1] l'état après l'étape k (voir
// spectre.core.structures._apply_declared_params : même convention côté serveur).
function currentFrameIndex() {
  if (!state.frames || state.frames.length === 0) return 0;
  const last = state.frames.length - 1;
  if (state.previewMode === "final") return last;
  if (state.frameLock != null) return Math.min(state.frameLock, last);
  let index;
  if (state.selectedBrickGroup) {
    const span = brickGroupSpan(state.selectedBrickGroup);
    index = span ? span[1] + 1 : last;
  } else if (state.wizardScreen === "variations") {
    index = last;
  } else {
    index = (state.selectedIndex == null ? -1 : state.selectedIndex) + 1;
  }
  return Math.max(0, Math.min(last, index));
}

// Pour chaque image, l'étape d'origine de chacune de ses couches (-1 = substrat, null = inconnue)
// - en alignant la suite de matériaux d'une image sur la précédente : une couche retrouvée dans
// le même ordre garde son origine, une couche nouvelle vient de l'étape de cette image, une couche
// disparue (résine retirée, couche entièrement gravée) est simplement sautée.
function computeLayerOrigins(frames) {
  const origins = [];
  let previous = [];
  frames.forEach((frame, f) => {
    const current = [];
    let p = 0;
    frame.layers.forEach((layer) => {
      let q = p;
      while (q < previous.length && previous[q].material !== layer.material) q += 1;
      if (q < previous.length) {
        current.push({ material: layer.material, origin: previous[q].origin });
        p = q + 1;
      } else {
        current.push({ material: layer.material, origin: f === 0 ? -1 : f - 1 });
      }
    });
    origins.push(current.map((c) => c.origin));
    previous = current;
  });
  return origins;
}

function layerOrigin(frameIndex, layerIndex) {
  const row = state.layerOrigins && state.layerOrigins[frameIndex];
  if (!row || layerIndex >= row.length) return null;
  return row[layerIndex];
}

// Étapes dont on souligne les couches : la sélection (simple, multiple, brique, ou l'étape dont on
// règle une variation).
function highlightedStepIndices() {
  if (state.wizardScreen === "variations") return variationEditingStepIndex != null ? new Set([variationEditingStepIndex]) : new Set();
  if (hasMultiSelection()) return state.selectedStepIndices;
  if (state.selectedBrickGroup) {
    const span = brickGroupSpan(state.selectedBrickGroup);
    const set = new Set();
    if (span) for (let k = span[0]; k <= span[1]; k++) set.add(k);
    return set;
  }
  return new Set(state.selectedIndex >= 0 ? [state.selectedIndex] : []);
}

function highlightSelectedLayer() {
  const container = document.getElementById("svg-container");
  const frameIndex = currentFrameIndex();
  const highlighted = highlightedStepIndices();
  container.querySelectorAll("[data-layer-index]").forEach((path) => {
    const origin = layerOrigin(frameIndex, parseInt(path.dataset.layerIndex, 10));
    path.classList.toggle("is-highlighted", origin != null && highlighted.has(origin));
  });
}

// ---------------------------------------------------------------------------------------------
// Rendu
// ---------------------------------------------------------------------------------------------

function frameLabel(frameIndex) {
  if (!state.frames || state.frames.length === 0) return "Pas encore simulé";
  const n = state.frames.length - 1;
  if (frameIndex === 0) return n === 0 ? "Substrat seul" : `Substrat · avant l'étape 1`;
  const frame = state.frames[frameIndex];
  const prefix = state.previewMode === "final" ? "Structure finale · " : "";
  const locked = state.frameLock != null && state.previewMode !== "final" ? " · vue conservée" : "";
  return `${prefix}Après l'étape ${frameIndex} / ${n} · ${frame.step_name}${locked}`;
}

function renderFrame() {
  const frameIndex = currentFrameIndex();
  const frame = state.frames ? state.frames[frameIndex] : null;
  const container = document.getElementById("svg-container");
  if (container.dataset.frameKey !== frameKey(frame, frameIndex)) {
    container.innerHTML = frame ? frame.svg : "";
    container.dataset.frameKey = frameKey(frame, frameIndex);
  }
  document.getElementById("scrubber-label").textContent = frameLabel(frameIndex);
  const legend = document.getElementById("legend");
  const materials = frame ? frame.materials : [];
  legend.innerHTML = materials
    .map((name) => `<span class="legend-item"><span class="legend-swatch" style="background:${escapeHtml(state.materialColors[name] || "var(--text-faint)")};"></span>${escapeHtml(name)}</span>`)
    .join("");
  const prev = document.getElementById("frame-prev-btn");
  const next = document.getElementById("frame-next-btn");
  const varying = state.wizardScreen === "variations";
  prev.disabled = varying || state.selectedIndex <= -1;
  next.disabled = varying || state.selectedIndex >= state.steps.length - 1;
  document.getElementById("preview-step-btn").classList.toggle("active", state.previewMode === "step");
  document.getElementById("preview-final-btn").classList.toggle("active", state.previewMode === "final");
  highlightSelectedLayer();
  applyZoom();
}

// Évite de réinjecter le même SVG (et de perdre un survol) quand seule la sélection a changé.
let frameKeyCounter = 0;
function frameKey(frame, frameIndex) {
  if (!frame) return "";
  if (!frame.__key) frame.__key = `f${++frameKeyCounter}`;
  return `${frame.__key}:${frameIndex}`;
}

function setPreviewMode(mode) {
  state.previewMode = mode;
  state.frameLock = null;
  renderFrame();
}

document.getElementById("preview-step-btn").addEventListener("click", () => setPreviewMode("step"));
document.getElementById("preview-final-btn").addEventListener("click", () => setPreviewMode("final"));
document.getElementById("frame-prev-btn").addEventListener("click", () => {
  if (state.previewMode === "final") state.previewMode = "step";
  selectStep(Math.max(-1, state.selectedIndex - 1));
});
document.getElementById("frame-next-btn").addEventListener("click", () => {
  if (state.previewMode === "final") state.previewMode = "step";
  selectStep(Math.min(state.steps.length - 1, state.selectedIndex + 1));
});

// ---------------------------------------------------------------------------------------------
// Traçabilité d'une couche (carte flottante sur le dessin)
// ---------------------------------------------------------------------------------------------

// Un dérivé "null" (mesuré/donné directement) ; un dict (déclaré ou calculé depuis une formule
// dérivée type Length) affiche ses clés ; toute autre forme retombe sur un JSON brut lisible.
function formatDerivation(derivation) {
  if (derivation === null || derivation === undefined) return "mesuré / donné directement";
  if (typeof derivation === "object" && !Array.isArray(derivation)) {
    const entries = Object.entries(derivation);
    if (entries.length === 0) return "mesuré / donné directement";
    return entries.map(([k, v]) => `${escapeHtml(k)}=${escapeHtml(String(v))}`).join(", ");
  }
  return escapeHtml(JSON.stringify(derivation));
}

function renderLayerProvenance(layer) {
  const panel = document.getElementById("layer-provenance-panel");
  const content = document.getElementById("layer-provenance-content");
  if (!layer) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  const provenance = layer.provenance;
  if (!provenance) {
    content.innerHTML = `<div class="help">Aucune traçabilité enregistrée pour cette couche (${escapeHtml(layer.material)}).</div>`;
    return;
  }
  const params = Object.entries(provenance.parameters || {});
  content.innerHTML = `
    <div class="sb-provenance__what"><strong>${escapeHtml(layer.material)}</strong> · ${escapeHtml(provenance.step_kind)} — ${escapeHtml(provenance.step_name)}</div>
    ${
      params.length === 0
        ? `<div class="help">Aucun paramètre enregistré.</div>`
        : `<div class="sb-provenance__params">
            ${params
              .map(
                ([name, traced]) => `
              <div class="sb-provenance__param">
                <div><strong>${escapeHtml(name)}</strong> = <span class="mono">${escapeHtml(formatParamValue(traced.value))}</span></div>
                <div class="help">${formatDerivation(traced.derivation)}</div>
              </div>`
              )
              .join("")}
          </div>`
    }`;
}

function hideLayerProvenance() {
  document.getElementById("layer-provenance-panel").hidden = true;
}

document.getElementById("layer-provenance-close").addEventListener("click", hideLayerProvenance);

// ---------------------------------------------------------------------------------------------
// Interactions sur le dessin : clic sur une couche, survol, zoom molette, déplacement
// ---------------------------------------------------------------------------------------------

const svgViewport = document.getElementById("svg-viewport");
const svgContainer = document.getElementById("svg-container");
let panState = null; // {x, y, left, top, moved}
let suppressNextClick = false;

svgContainer.addEventListener("click", (event) => {
  if (suppressNextClick) {
    suppressNextClick = false;
    return;
  }
  const path = event.target.closest("[data-layer-index]");
  if (!path || !state.frames) return;
  const frameIndex = currentFrameIndex();
  const frame = state.frames[frameIndex];
  const layerIndex = parseInt(path.dataset.layerIndex, 10);
  const origin = layerOrigin(frameIndex, layerIndex);
  if (state.wizardScreen === "variations") {
    if (origin != null) startVaryingLayer(origin); // -1 : le substrat, variable lui aussi
    return;
  }
  if (origin != null && origin < state.steps.length) selectStep(origin, { fromCanvas: true });
  renderLayerProvenance(frame && frame.layers ? frame.layers[layerIndex] || null : null);
});

// Survol d'une couche : la puce de l'étape qui l'a produite s'illumine dans le flow.
svgContainer.addEventListener("mouseover", (event) => {
  const path = event.target.closest("[data-layer-index]");
  document.querySelectorAll(".sb-chip.is-hover").forEach((chip) => chip.classList.remove("is-hover"));
  if (!path) return;
  const origin = layerOrigin(currentFrameIndex(), parseInt(path.dataset.layerIndex, 10));
  const chip = origin != null ? document.getElementById(`sb-chip-${origin}`) : null;
  if (chip) chip.classList.add("is-hover");
});
svgContainer.addEventListener("mouseleave", () => {
  document.querySelectorAll(".sb-chip.is-hover").forEach((chip) => chip.classList.remove("is-hover"));
});

// Et l'inverse : survol d'une puce du flow -> ses couches s'illuminent dans le dessin.
function hoverStepLayers(stepIndex) {
  const frameIndex = currentFrameIndex();
  svgContainer.querySelectorAll("[data-layer-index]").forEach((path) => {
    const origin = stepIndex == null ? null : layerOrigin(frameIndex, parseInt(path.dataset.layerIndex, 10));
    path.classList.toggle("is-hover", origin != null && origin === stepIndex);
  });
}
document.getElementById("steps-list").addEventListener("mouseover", (event) => {
  const chip = event.target.closest(".sb-chip[data-index]");
  hoverStepLayers(chip ? parseInt(chip.dataset.index, 10) : null);
});
document.getElementById("steps-list").addEventListener("mouseleave", () => hoverStepLayers(null));

// Zoom : 1 = ajusté à la zone (le SVG garde ses proportions grâce à son viewBox) ; au-delà, la
// zone de dessin défile et se déplace à la souris.
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 8;

function applyZoom() {
  const z = state.zoom;
  svgContainer.style.width = `${z * 100}%`;
  svgContainer.style.height = `${z * 100}%`;
  svgContainer.style.left = svgContainer.style.top = z < 1 ? `${(1 - z) * 50}%` : "0";
  svgViewport.classList.toggle("is-zoomed", z > 1);
  document.getElementById("zoom-level-label").textContent = z === 1 ? "Ajusté" : `${Math.round(z * 100)} %`;
}

// Zoome en gardant fixe le point sous le curseur (ou le centre de la zone).
function setZoom(nextZoom, clientX, clientY) {
  const z = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(nextZoom * 100) / 100));
  const rect = svgViewport.getBoundingClientRect();
  const px = (clientX ?? rect.left + rect.width / 2) - rect.left;
  const py = (clientY ?? rect.top + rect.height / 2) - rect.top;
  const ratioX = (svgViewport.scrollLeft + px) / Math.max(1, svgContainer.offsetWidth);
  const ratioY = (svgViewport.scrollTop + py) / Math.max(1, svgContainer.offsetHeight);
  state.zoom = z;
  applyZoom();
  svgViewport.scrollLeft = ratioX * svgContainer.offsetWidth - px;
  svgViewport.scrollTop = ratioY * svgContainer.offsetHeight - py;
}

document.getElementById("zoom-in-btn").addEventListener("click", () => setZoom(state.zoom * 1.25));
document.getElementById("zoom-out-btn").addEventListener("click", () => setZoom(state.zoom / 1.25));
document.getElementById("zoom-reset-btn").addEventListener("click", () => setZoom(1));

svgViewport.addEventListener(
  "wheel",
  (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    setZoom(state.zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15), event.clientX, event.clientY);
  },
  { passive: false }
);

svgViewport.addEventListener("mousedown", (event) => {
  if (event.button !== 0 || state.zoom <= 1) return;
  panState = { x: event.clientX, y: event.clientY, left: svgViewport.scrollLeft, top: svgViewport.scrollTop, moved: false };
});
window.addEventListener("mousemove", (event) => {
  if (!panState) return;
  const dx = event.clientX - panState.x;
  const dy = event.clientY - panState.y;
  if (!panState.moved && Math.hypot(dx, dy) < 4) return;
  panState.moved = true;
  svgViewport.classList.add("is-panning");
  svgViewport.scrollLeft = panState.left - dx;
  svgViewport.scrollTop = panState.top - dy;
});
window.addEventListener("mouseup", () => {
  if (panState && panState.moved) suppressNextClick = true;
  panState = null;
  svgViewport.classList.remove("is-panning");
});

// ---------------------------------------------------------------------------------------------
// Appel au serveur
// ---------------------------------------------------------------------------------------------

function showSimulationError(err) {
  const box = document.getElementById("sim-error");
  box.textContent = `Simulation impossible : ${err.message || err}`;
  box.hidden = false;
  document.getElementById("sb-canvas").classList.add("is-stale");
}

function clearSimulationError() {
  document.getElementById("sim-error").hidden = true;
  document.getElementById("sb-canvas").classList.remove("is-stale");
}

// Numéro de la dernière requête partie : une réponse plus ancienne arrivée après coup (réseau
// lent, frappe rapide) est ignorée plutôt que d'écraser un aperçu plus récent.
let simulateSeq = 0;

// La simulation rend l'id de chaque étape envoyée (`step_ids`) : celui qu'elle avait, ou un neuf
// pour une nouvelle étape - c'est ainsi qu'une étape ajoutée reçoit le sien, du serveur (le
// constructeur n'en invente jamais, voir withoutStepId). Il est posé sur l'étape envoyée si elle
// est toujours dans la liste (sinon la simulation suivante s'en chargera).
function adoptStepIds(sent, ids) {
  if (!Array.isArray(ids)) return;
  const before = currentHistorySnapshot();
  let changed = false;
  sent.forEach((step, i) => {
    if (ids[i] && step.id !== ids[i] && state.steps.includes(step)) {
      step.id = ids[i];
      changed = true;
    }
  });
  if (changed) absorbAdoptedStepIds(before);
}

async function simulateNow() {
  const seq = ++simulateSeq;
  const busy = document.getElementById("sim-busy");
  const busyTimer = setTimeout(() => (busy.hidden = false), 250);
  const sent = state.steps.slice();
  try {
    const result = await structuresApi.simulate({
      substrate: substrateSpec(),
      steps: sent,
      declared_params: declaredParamsPayload(sent),
    });
    if (seq !== simulateSeq) return;
    adoptStepIds(sent, result.step_ids);
    const colorsChanged = JSON.stringify(result.material_colors) !== JSON.stringify(state.materialColors);
    state.frames = result.frames;
    state.materialColors = result.material_colors;
    state.layerOrigins = computeLayerOrigins(state.frames);
    clearSimulationError();
    renderFrame();
    if (colorsChanged) renderRail(); // pastilles de matériau des puces, aux couleurs du dessin
  } catch (err) {
    if (seq === simulateSeq) showSimulationError(err);
  } finally {
    clearTimeout(busyTimer);
    if (seq === simulateSeq) busy.hidden = true;
  }
}

// Regroupe les appels rapprochés (plusieurs rendus dans le même instant, frappe au clavier) en une
// seule simulation, sans que l'aperçu ait l'air d'attendre.
let simulateTimer = null;
function scheduleSimulate(delay = 140) {
  if (simulateTimer) clearTimeout(simulateTimer);
  simulateTimer = setTimeout(() => {
    simulateTimer = null;
    simulateNow();
  }, delay);
}

["substrate-material", "substrate-width", "substrate-width-unit", "substrate-thickness", "substrate-thickness-unit"].forEach((id) => {
  const el = document.getElementById(id);
  // "input" : aperçu instantané à chaque frappe/sélection, sans capturer d'historique (un Ctrl+Z
  // par caractère tapé serait inutilisable). "change" (au blur, ou déjà déclenché par "input" pour
  // un <select>) capture l'historique une fois la valeur retenue.
  el.addEventListener("input", () => scheduleSimulate());
  el.addEventListener("change", () => {
    captureHistory();
    scheduleSimulate();
  });
});
