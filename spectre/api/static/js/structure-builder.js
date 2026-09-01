/* Constructeur de structure : formulaire de substrat + étapes de procédé, aperçu simulé
   (StructureForge fait tout le calcul et dessine le SVG - cette page ne fait qu'assembler la
   requête et afficher ce qui revient), puis lancement du suivi ou enregistrement d'une évolution. */

const STEP_KINDS = {
  deposition: { label: "Dépôt", icon: "deposition", color: "#1d6fae", tint: "#e8f1fa" },
  etch: { label: "Gravure", icon: "etch", color: "#a45a3a", tint: "#f6ede7" },
  planarization: { label: "Planarisation", icon: "planarization", color: "#5c655e", tint: "#ede9df" },
  lithography: { label: "Lithographie", icon: "lithography", color: "#7a4a97", tint: "#f2e9f7" },
  chemical: { label: "Étape chimique", icon: "chemical", color: "#3f7d4a", tint: "#e9f4ea" },
  resist_strip: { label: "Retrait de résine", icon: "resist_strip", color: "#a45a3a", tint: "#f6ede7" },
  semipolar_facet: { label: "Facette semipolaire", icon: "semipolar_facet", color: "#b8860b", tint: "#faf3df" },
  selective_growth: { label: "Croissance sélective", icon: "selective_growth", color: "#2e8b57", tint: "#e6f4ec" },
};

const STEP_ICON_PATHS = {
  deposition: '<path d="M12 3v13m0 0l-5-5m5 5l5-5M4 20h16"/>',
  etch: '<path d="M12 21V8m0 0l-5 5m5-5l5 5M4 4h16"/>',
  planarization: '<path d="M4 12h16M8 6h8M8 18h8"/>',
  lithography: '<path d="M6 4l12 16M18 4L6 20"/>',
  chemical: '<path d="M9 3h6M10 3v5l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3"/>',
  resist_strip: '<path d="M5 5l14 14M5 19L19 5"/>',
  semipolar_facet: '<path d="M4 20L12 4L20 20Z"/>',
  selective_growth: '<path d="M12 20V4M12 4l-5 5M12 4l5 5M6 14l6-4 6 4"/>',
};

function stepIconHtml(kind) {
  const info = STEP_KINDS[kind];
  return `
    <div class="step-icon" style="background:${info.tint};color:${info.color};">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${STEP_ICON_PATHS[kind]}</svg>
    </div>`;
}

const pathParts = window.location.pathname.split("/").filter(Boolean);
const slug = pathParts[1];
const isLibraryMode = pathParts[2] === "structures" && pathParts[3] === "bibliotheque";
const libraryStructureName = isLibraryMode && pathParts[4] !== "nouvelle" ? decodeURIComponent(pathParts[4]) : null;
const queryParams = new URLSearchParams(window.location.search);
const librarySourceScope = queryParams.get("scope") || "projet";
const libraryDuplicateMode = queryParams.get("dupliquer") === "1";
const evolveExperienceId = !isLibraryMode && pathParts[2] === "experiences" ? pathParts[3] : null;
const templateExperienceId = !isLibraryMode && !evolveExperienceId ? queryParams.get("depuis") : null;
const chosenStructureName = !isLibraryMode && !evolveExperienceId ? queryParams.get("structure") : null;
const chosenStructureScope = queryParams.get("scope") || "projet";
const returnTo = queryParams.get("retour"); // where "Enregistrer" in library mode sends you back to

const state = {
  materials: [],
  stepPresets: { presets: [], partagees: [], projet: [] },
  steps: [],
  objectives: [],
  frames: null,
  materialColors: {},
  currentFrame: 0,
  campaignPlan: null,
  editingIndex: null,
  viewMode: "couches", // "couches" (click a layer, epitaxy-style) or "etapes" (full step list)
  showStepForm: false, // couches mode only: whether the add/edit form is open
  derivedFrom: null, // library mode only: name of the structure this one was derived from, if any
  editingLibraryName: null, // library mode only: name of the saved structure being edited in place (null = new)
  editingLibraryScope: null, // library mode only: "projet" or "partagee", matching editingLibraryName
  zoom: 1,
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

function lengthValue(id) {
  return { value: parseFloat(document.getElementById(id).value) || 0, unit: document.getElementById(id + "-unit").value };
}

function materialOptions(selectedValue) {
  return state.materials
    .map((m) => `<option value="${escapeHtml(m.name)}" ${m.name === selectedValue ? "selected" : ""}>${escapeHtml(m.name)}</option>`)
    .join("");
}

function presetOptionsHtml(kind) {
  const entries = [
    ...state.stepPresets.presets.map((p) => ({ ...p, scope: "preset" })),
    ...state.stepPresets.partagees.map((p) => ({ ...p, scope: "partagee" })),
    ...state.stepPresets.projet.map((p) => ({ ...p, scope: "projet" })),
  ].filter((p) => p.payload.kind === kind);
  const scopeSuffix = { preset: " (préset)", partagee: " (partagée)", projet: "" };
  return entries
    .map((p) => `<option value="${p.scope}::${encodeURIComponent(p.name)}">${escapeHtml(p.name)}${scopeSuffix[p.scope]}</option>`)
    .join("");
}

function findStepPreset(scope, name) {
  const bucket = scope === "preset" ? state.stepPresets.presets : scope === "partagee" ? state.stepPresets.partagees : state.stepPresets.projet;
  return (bucket || []).find((p) => p.name === name) || null;
}

function wireModeAngleToggle(kind) {
  const modeSelect = document.getElementById("f-mode");
  const angleWrap = document.getElementById("f-angle-wrap");
  const update = () => {
    angleWrap.style.display = modeSelect.value === "directional" ? "" : "none";
  };
  modeSelect.addEventListener("change", update);
  update();
  document.getElementById("f-preset").addEventListener("change", (e) => {
    const value = e.target.value;
    if (!value) return;
    const [scope, name] = value.split("::");
    const preset = findStepPreset(scope, decodeURIComponent(name));
    if (!preset) return;
    modeSelect.value = preset.payload.mode;
    document.getElementById("f-angle").value = preset.payload.angle_deg || 0;
    update();
    if (kind === "etch") {
      document.getElementById("f-default-factor").value = preset.payload.default_factor != null ? preset.payload.default_factor : 1.0;
      document.getElementById("f-selectivity-rows").innerHTML = "";
      Object.entries(preset.payload.selectivity_by_material || {}).forEach(([material, factor]) => addSelectivityRow(material, factor));
    }
  });
}

function addSelectivityRow(material, factor) {
  const row = document.createElement("div");
  row.className = "field-row js-selectivity-row";
  row.style.gridTemplateColumns = "1fr 100px auto";
  row.innerHTML = `
    <select class="field js-sel-material">${materialOptions(material)}</select>
    <input class="field js-sel-factor" type="number" step="0.01" min="0" placeholder="facteur" value="${factor != null ? factor : ""}">
    <button class="js-sel-remove" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;">&times;</button>`;
  document.getElementById("f-selectivity-rows").appendChild(row);
  row.querySelector(".js-sel-remove").addEventListener("click", () => row.remove());
}

function currentSelectivityByMaterial() {
  const out = {};
  document.querySelectorAll("#f-selectivity-rows .js-selectivity-row").forEach((row) => {
    const material = row.querySelector(".js-sel-material").value;
    const factor = parseFloat(row.querySelector(".js-sel-factor").value);
    if (material && !Number.isNaN(factor)) out[material] = factor;
  });
  return out;
}

function wireSelectiveGrowthRateCheck() {
  const check = () => {
    const rateM = parseFloat(document.getElementById("f-rate-m").value);
    const rateSp = parseFloat(document.getElementById("f-rate-sp").value);
    const hint = document.getElementById("f-rate-order-hint");
    const ok = rateSp > 0 && rateM > rateSp && rateM < 1.0;
    hint.style.color = ok ? "" : "var(--danger)";
  };
  document.getElementById("f-rate-m").addEventListener("input", check);
  document.getElementById("f-rate-sp").addEventListener("input", check);
  check();
}

function renderKindFields(kind) {
  const container = document.getElementById("kind-fields");
  if (kind === "deposition") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Dépôt"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions()}</select></div>
      <div><label>Préset (optionnel)</label><select class="field" id="f-preset"><option value="">Personnalisé</option>${presetOptionsHtml("deposition")}</select>
        <div class="help" style="margin-top:4px;">Préremplit le mode et l'angle ci-dessous — reste ensuite librement modifiable.</div>
      </div>
      <div><label>Mode</label>
        <select class="field" id="f-mode"><option value="conformal">Conforme</option><option value="directional">Directionnel</option></select>
      </div>
      <div id="f-angle-wrap" style="display:none;"><label>Angle (degrés, 0 = incidence normale)</label><input class="field" id="f-angle" type="number" value="0"></div>
      <div class="field-row"><div><label>Épaisseur</label><input class="field" id="f-thickness" type="number" value="20"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option><option value="um">µm</option><option value="A">Å</option></select></div></div>
      <details id="f-deposition-advanced" class="card" style="padding:0;overflow:hidden;margin-top:4px;flex-shrink:0;">
        <summary class="disclosure-btn disclosure-btn--tint" style="padding:10px 12px;font-size:13px;">
          <span>
            Paramètres process &amp; dopage
            <span class="disclosure-btn__sub">Ajoutez un flux, une puissance... et une grandeur calculée à partir d'eux (ex : dopage).</span>
          </span>
          <svg class="disclosure-btn__chevron" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"/></svg>
        </summary>
        <div style="padding:10px 12px 12px;display:flex;flex-direction:column;gap:12px;">
          <div>
            <label>Paramètres process</label>
            <div class="help" style="margin-bottom:6px;">Une grandeur du procédé (ex : flux) à suivre ou à faire varier.</div>
            <div id="f-process-params-rows" style="display:flex;flex-direction:column;gap:6px;margin-bottom:6px;"></div>
            <button class="btn btn-line" id="f-add-process-param-btn" type="button" style="padding:6px 12px;font-size:12.5px;">+ Ajouter un paramètre</button>
          </div>
          <div>
            <label>Grandeurs physiques estimées (ex : dopage)</label>
            <div class="help" style="margin-bottom:6px;">Une grandeur qu'on ne simule pas directement, calculée à partir d'un paramètre process qui sert de proxy — par exemple <code>dopage = flux &times; 2</code>.</div>
            <div id="f-estimates-rows" style="display:flex;flex-direction:column;gap:8px;margin-bottom:6px;"></div>
            <button class="btn btn-line" id="f-add-estimate-btn" type="button" style="padding:6px 12px;font-size:12.5px;">+ Ajouter une estimation</button>
          </div>
        </div>
      </details>`;
    wireDepositionAdvanced();
    wireModeAngleToggle("deposition");
  } else if (kind === "etch") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Gravure"></div>
      <div><label>Préset (optionnel)</label><select class="field" id="f-preset"><option value="">Personnalisé</option>${presetOptionsHtml("etch")}</select>
        <div class="help" style="margin-top:4px;">Préremplit mode/angle/sélectivité ci-dessous — reste ensuite librement modifiable.</div>
      </div>
      <div><label>Mode</label>
        <select class="field" id="f-mode"><option value="isotropic">Isotrope</option><option value="directional">Directionnel</option></select>
      </div>
      <div id="f-angle-wrap" style="display:none;"><label>Angle (degrés, 0 = incidence normale)</label><input class="field" id="f-angle" type="number" value="0"></div>
      <div><label>Facteur par défaut</label><input class="field" id="f-default-factor" type="number" value="1.0" step="0.01" min="0"></div>
      <div>
        <label>Sélectivité par matériau (optionnel)</label>
        <div class="help" style="margin-bottom:6px;">Vitesse relative de gravure pour un matériau donné (1 = normal, plus grand = gravé plus vite, 0 = protégé).</div>
        <div id="f-selectivity-rows" style="display:flex;flex-direction:column;gap:6px;margin-bottom:6px;"></div>
        <button class="btn btn-line" id="f-add-selectivity-btn" type="button" style="padding:6px 12px;font-size:12.5px;">+ Ajouter un matériau</button>
      </div>
      <div class="field-row"><div><label>Profondeur</label><input class="field" id="f-depth" type="number" value="10"></div>
      <div><label>Unité</label><select class="field" id="f-depth-unit"><option value="nm" selected>nm</option><option value="um">µm</option><option value="A">Å</option></select></div></div>`;
    document.getElementById("f-add-selectivity-btn").addEventListener("click", () => addSelectivityRow());
    wireModeAngleToggle("etch");
  } else if (kind === "planarization") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Planarisation"></div>
      <div><label>S'arrête sur</label>
        <select class="field" id="f-plana-mode"><option value="level">Un niveau précis</option><option value="material">Un matériau</option></select>
      </div>
      <div id="f-plana-value"><div class="field-row"><div><input class="field" id="f-target-level" type="number" value="0"></div><div><select class="field" id="f-target-level-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div></div>`;
    document.getElementById("f-plana-mode").addEventListener("change", (e) => {
      const target = document.getElementById("f-plana-value");
      target.innerHTML =
        e.target.value === "level"
          ? `<div class="field-row"><div><input class="field" id="f-target-level" type="number" value="0"></div><div><select class="field" id="f-target-level-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>`
          : `<select class="field" id="f-stop-material">${materialOptions()}</select>`;
    });
  } else if (kind === "lithography") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Lithographie"></div>
      <div><label>Résine</label><select class="field" id="f-resist-material">${materialOptions("Photoresist")}</select></div>
      <div class="field-row"><div><label>Épaisseur</label><input class="field" id="f-thickness" type="number" value="500"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option></select></div></div>
      <div><label>Ouvertures (nm)</label><input class="field" id="f-openings" placeholder="ex : 80-140, 300-360"><div class="help">Zones où le masque est ouvert, séparées par des virgules.</div></div>`;
  } else if (kind === "chemical") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Nettoyage"></div>
      <div><label>Description (optionnelle)</label><input class="field" id="f-description" placeholder="ex : bain HF"></div>`;
  } else if (kind === "resist_strip") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Retrait de résine"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions("Photoresist")}</select></div>`;
  } else if (kind === "semipolar_facet") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Facette semipolaire"></div>
      <div><label>Sens</label>
        <select class="field" id="f-orientation">
          <option value="tip">Pointe (anti-V-pit, croît vers le haut)</option>
          <option value="notch">Creux (V-pit, s'enfonce vers le bas)</option>
        </select>
        <div class="help" style="margin-top:4px;">Une facette symétrique à angle précis, comme sur un flanc semipolaire de nanofil ou de LED III-N &mdash; ni un dépôt/gravure directionnel ni isotrope ne peut produire cette forme.</div>
      </div>
      <div class="field-row"><div><label>Largeur de base</label><input class="field" id="f-base-half-width" type="number" value="30"></div>
      <div><label>Unité</label><select class="field" id="f-base-half-width-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>
      <div class="field-row"><div><label>Largeur de pointe</label><input class="field" id="f-tip-half-width" type="number" value="0"></div>
      <div><label>Unité</label><select class="field" id="f-tip-half-width-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>
      <div class="help" style="margin-top:-6px;">0 = converge en une pointe. Doit rester strictement inférieure à la largeur de base.</div>
      <div><label>Angle de facette (degrés depuis l'horizontale)</label><input class="field" id="f-facet-angle" type="number" value="60"></div>
      <div><label>Position (optionnelle)</label><input class="field" id="f-position" type="number" placeholder="laisser vide = centre du domaine">
        <div class="help" style="margin-top:4px;">Position en nm depuis le bord gauche. Vide = centrée automatiquement.</div>
      </div>`;
  } else if (kind === "selective_growth") {
    container.innerHTML = `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Croissance sélective"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions()}</select>
        <div class="help" style="margin-top:4px;">La croissance ne reprend que sur ce matériau — ailleurs (substrat, masque...) rien ne pousse, comme un masque de croissance réel. Sans dépôt existant de ce matériau, la toute première couche pousse sur toute la surface exposée (à amorcer avec un dépôt classique avant, comme dans l'exemple de préset nanofil).</div>
      </div>
      <div class="field-row"><div><label>Épaisseur (plan C, le plus rapide)</label><input class="field" id="f-thickness" type="number" value="10"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>
      <div><label>Vitesse relative — plan M (flancs verticaux)</label><input class="field" id="f-rate-m" type="number" value="0.4" step="0.01" min="0" max="1"></div>
      <div><label>Vitesse relative — facette semipolaire</label><input class="field" id="f-rate-sp" type="number" value="0.15" step="0.01" min="0" max="1"></div>
      <div class="help" id="f-rate-order-hint" style="margin-top:-6px;">Doit vérifier C (1.0) &gt; plan M &gt; semipolaire, sinon la facette la plus lente ne l'emporte jamais — c'est ce qui referme la pointe au fil des étapes.</div>`;
    wireSelectiveGrowthRateCheck();
  }
}

function currentProcessParameters() {
  const params = {};
  document.querySelectorAll(".js-process-param-row").forEach((row) => {
    const name = row.querySelector(".js-pp-name").value.trim();
    const value = parseFloat(row.querySelector(".js-pp-value").value);
    if (name && !Number.isNaN(value)) params[name] = value;
  });
  return params;
}

function currentDerivedEstimates() {
  return [...document.querySelectorAll(".js-estimate-row")]
    .map((row) => ({
      name: row.querySelector(".js-est-name").value.trim(),
      parameter: row.querySelector(".js-est-parameter").value,
      coefficient: parseFloat(row.querySelector(".js-est-coefficient").value),
      offset: parseFloat(row.querySelector(".js-est-offset").value) || 0,
      unit: row.querySelector(".js-est-unit").value.trim() || null,
    }))
    .filter((e) => e.name && e.parameter && !Number.isNaN(e.coefficient));
}

function refreshEstimateParameterOptions() {
  const names = [...document.querySelectorAll(".js-pp-name")].map((el) => el.value.trim()).filter(Boolean);
  document.querySelectorAll(".js-est-parameter").forEach((select) => {
    const previous = select.value;
    select.innerHTML = names.length
      ? names.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("")
      : `<option value="">Ajoutez un paramètre process d'abord</option>`;
    if (names.includes(previous)) select.value = previous;
  });
  updateEstimatePreviews();
}

function updateEstimatePreviews() {
  const params = currentProcessParameters();
  document.querySelectorAll(".js-estimate-row").forEach((row) => {
    const parameter = row.querySelector(".js-est-parameter").value;
    const coefficient = parseFloat(row.querySelector(".js-est-coefficient").value);
    const offset = parseFloat(row.querySelector(".js-est-offset").value) || 0;
    const unit = row.querySelector(".js-est-unit").value.trim();
    const preview = row.querySelector(".js-est-preview");
    if (parameter && parameter in params && !Number.isNaN(coefficient)) {
      const value = offset + coefficient * params[parameter];
      preview.textContent = `≈ ${value}${unit ? " " + unit : ""}`;
    } else {
      preview.textContent = "";
    }
  });
}

function addProcessParamRow(name, value) {
  const row = document.createElement("div");
  row.className = "field-row js-process-param-row";
  row.style.gridTemplateColumns = "1fr 100px auto";
  row.innerHTML = `
    <input class="field js-pp-name" placeholder="nom (ex : flux)" value="${escapeHtml(name || "")}">
    <input class="field js-pp-value" type="number" step="any" placeholder="valeur" value="${value != null ? value : ""}">
    <button class="js-pp-remove" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;">&times;</button>`;
  document.getElementById("f-process-params-rows").appendChild(row);
  row.querySelector(".js-pp-name").addEventListener("input", refreshEstimateParameterOptions);
  row.querySelector(".js-pp-value").addEventListener("input", updateEstimatePreviews);
  row.querySelector(".js-pp-remove").addEventListener("click", () => {
    row.remove();
    refreshEstimateParameterOptions();
  });
}

function addEstimateRow(estimate) {
  estimate = estimate || {};
  const row = document.createElement("div");
  row.className = "js-estimate-row";
  row.style = "border:1px solid var(--border-soft);border-radius:8px;padding:8px;display:flex;flex-direction:column;gap:6px;";
  row.innerHTML = `
    <div style="display:flex;justify-content:space-between;gap:6px;">
      <input class="field js-est-name" placeholder="nom (ex : dopage)" style="flex:1;" value="${escapeHtml(estimate.name || "")}">
      <button class="js-est-remove" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;">&times;</button>
    </div>
    <select class="field js-est-parameter"></select>
    <div class="field-row">
      <input class="field js-est-coefficient" type="number" step="any" value="${estimate.coefficient != null ? estimate.coefficient : 1}" placeholder="coefficient">
      <input class="field js-est-offset" type="number" step="any" value="${estimate.offset != null ? estimate.offset : 0}" placeholder="décalage">
    </div>
    <input class="field js-est-unit" placeholder="unité (optionnel)" value="${escapeHtml(estimate.unit || "")}">
    <div class="js-est-preview" style="font-size:11.5px;color:var(--text-faint);"></div>`;
  document.getElementById("f-estimates-rows").appendChild(row);
  row.querySelectorAll("input").forEach((input) => input.addEventListener("input", updateEstimatePreviews));
  row.querySelector(".js-est-remove").addEventListener("click", () => row.remove());
  refreshEstimateParameterOptions();
  if (estimate.parameter) row.querySelector(".js-est-parameter").value = estimate.parameter;
  updateEstimatePreviews();
}

function wireDepositionAdvanced() {
  document.getElementById("f-add-process-param-btn").addEventListener("click", () => addProcessParamRow());
  document.getElementById("f-add-estimate-btn").addEventListener("click", () => addEstimateRow());
}

function parseOpenings(text) {
  if (!text.trim()) return [];
  return text.split(",").map((part) => {
    const [a, b] = part.split("-").map((n) => parseFloat(n.trim()));
    return [a, b];
  });
}

function buildStepFromForm() {
  const kind = document.getElementById("kind-select").value;
  const name = document.getElementById("f-name").value || STEP_KINDS[kind].label;
  if (kind === "deposition") {
    return {
      kind,
      name,
      material: document.getElementById("f-material").value,
      mode: document.getElementById("f-mode").value,
      angle_deg: parseFloat(document.getElementById("f-angle").value) || 0,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
      process_parameters: currentProcessParameters(),
      derived_estimates: currentDerivedEstimates(),
    };
  }
  if (kind === "etch") {
    return {
      kind,
      name,
      mode: document.getElementById("f-mode").value,
      angle_deg: parseFloat(document.getElementById("f-angle").value) || 0,
      default_factor: parseFloat(document.getElementById("f-default-factor").value) || 1.0,
      selectivity_by_material: currentSelectivityByMaterial(),
      depth: { value: parseFloat(document.getElementById("f-depth").value) || 0, unit: document.getElementById("f-depth-unit").value },
    };
  }
  if (kind === "selective_growth") {
    return {
      kind,
      name,
      material: document.getElementById("f-material").value,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
      rate_m: parseFloat(document.getElementById("f-rate-m").value),
      rate_sp: parseFloat(document.getElementById("f-rate-sp").value),
    };
  }
  if (kind === "planarization") {
    const mode = document.getElementById("f-plana-mode").value;
    if (mode === "level") {
      return {
        kind,
        name,
        target_level: { value: parseFloat(document.getElementById("f-target-level").value) || 0, unit: document.getElementById("f-target-level-unit").value },
      };
    }
    return { kind, name, stop_material: document.getElementById("f-stop-material").value };
  }
  if (kind === "lithography") {
    return {
      kind,
      name,
      resist_material: document.getElementById("f-resist-material").value,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
      openings: parseOpenings(document.getElementById("f-openings").value),
    };
  }
  if (kind === "chemical") {
    return { kind, name, description: document.getElementById("f-description").value || null, parameters: {} };
  }
  if (kind === "semipolar_facet") {
    const positionRaw = document.getElementById("f-position").value;
    return {
      kind,
      name,
      orientation: document.getElementById("f-orientation").value,
      base_half_width: { value: parseFloat(document.getElementById("f-base-half-width").value) || 0, unit: document.getElementById("f-base-half-width-unit").value },
      tip_half_width: { value: parseFloat(document.getElementById("f-tip-half-width").value) || 0, unit: document.getElementById("f-tip-half-width-unit").value },
      facet_angle_deg: parseFloat(document.getElementById("f-facet-angle").value) || 60,
      position: positionRaw ? { value: parseFloat(positionRaw) || 0, unit: "nm" } : null,
    };
  }
  return { kind, name, material: document.getElementById("f-material").value };
}

const MODE_LABELS = { conformal: "conforme", directional: "directionnel", isotropic: "isotrope", anisotropic: "anisotrope" };

function modeSummary(mode, angle_deg) {
  const label = MODE_LABELS[mode] || mode;
  return angle_deg ? `${label} (${angle_deg}°)` : label;
}

function stepSummary(step) {
  if (step.kind === "deposition") return `${step.material} · ${step.thickness.value} ${step.thickness.unit} · ${modeSummary(step.mode, step.angle_deg)}`;
  if (step.kind === "etch") return `${modeSummary(step.mode, step.angle_deg)} · ${step.depth.value} ${step.depth.unit}`;
  if (step.kind === "selective_growth") return `${step.material} · +${step.thickness.value} ${step.thickness.unit} (C) · M×${step.rate_m} · SP×${step.rate_sp}`;
  if (step.kind === "planarization") return step.target_level ? `jusqu'à ${step.target_level.value} ${step.target_level.unit}` : `jusqu'au ${step.stop_material}`;
  if (step.kind === "lithography") return `${step.resist_material} · ${step.openings.length} ouverture(s)`;
  if (step.kind === "chemical") return step.description || "sans effet géométrique";
  if (step.kind === "semipolar_facet") {
    const orientationLabel = step.orientation === "notch" ? "creux (V-pit)" : "pointe (anti-V-pit)";
    return `${orientationLabel} · ${step.facet_angle_deg}° · base ${step.base_half_width.value} ${step.base_half_width.unit}`;
  }
  return step.material;
}

function stepRowHtml(step, i, compact) {
  const highlight = state.editingIndex === i ? "border-color:var(--accent);background:var(--accent-tint);" : "";
  if (compact) {
    return `
      <div class="step-row js-step-row" data-index="${i}" style="cursor:pointer;${highlight}">
        ${stepIconHtml(step.kind)}
        <div style="flex:1;min-width:0;font-size:13px;font-weight:600;">${i + 1}. ${escapeHtml(step.name)}</div>
        <button class="step-remove js-step-remove" data-index="${i}" title="Retirer" type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
        </button>
      </div>`;
  }
  return `
    <div class="step-row js-step-row" data-index="${i}" style="cursor:pointer;${highlight}">
      ${stepIconHtml(step.kind)}
      <div style="flex:1;min-width:0;">
        <div style="font-size:13px;font-weight:600;">${i + 1}. ${escapeHtml(STEP_KINDS[step.kind].label)} &mdash; ${escapeHtml(step.name)}</div>
        <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(stepSummary(step))}</div>
      </div>
      <div style="display:flex;flex-direction:column;">
        <button class="step-remove js-step-up" data-index="${i}" title="Monter" type="button" ${i === 0 ? "disabled style='opacity:.3;'" : ""}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 15l7-7 7 7"/></svg>
        </button>
        <button class="step-remove js-step-down" data-index="${i}" title="Descendre" type="button" ${i === state.steps.length - 1 ? "disabled style='opacity:.3;'" : ""}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 9l7 7 7-7"/></svg>
        </button>
      </div>
      <button class="step-remove js-step-remove" data-index="${i}" title="Retirer" type="button">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
      </button>
    </div>`;
}

function updateViewModeAvailability() {
  const eligible = state.steps.length === 0 || state.steps.every((s) => s.kind === "deposition");
  const couchesBtn = document.getElementById("view-mode-couches");
  couchesBtn.disabled = !eligible;
  couchesBtn.title = eligible
    ? ""
    : "Disponible uniquement pour un empilement de dépôts (pas de gravure, planarisation, lithographie...)";
  if (!eligible && state.viewMode === "couches") {
    state.viewMode = "etapes";
    state.showStepForm = true;
    document.getElementById("view-mode-help").textContent =
      "Passé en vue par étapes : cette structure contient une étape autre que dépôt.";
  }
  couchesBtn.classList.toggle("active", state.viewMode === "couches");
  document.getElementById("view-mode-etapes").classList.toggle("active", state.viewMode === "etapes");
  document.getElementById("steps-list-help").textContent =
    state.viewMode === "couches"
      ? "Cliquez une couche (dans le dessin ou ci-dessous) pour l'éditer."
      : "Cliquez une étape pour la modifier ; ▲▼ pour la déplacer.";
}

function updateStepFormVisibility() {
  const formVisible = state.viewMode === "etapes" || state.editingIndex !== null || state.showStepForm;
  document.getElementById("step-form-section").style.display = formVisible ? "" : "none";
  document.getElementById("context-panel-empty").style.display = formVisible ? "none" : "";
  document.getElementById("add-step-shortcut-btn").style.display =
    !formVisible && state.viewMode === "couches" ? "" : "none";
  document.getElementById("cancel-edit-btn").style.display =
    state.editingIndex !== null || (state.viewMode === "couches" && state.showStepForm) ? "" : "none";
}

function highlightSelectedLayer() {
  const container = document.getElementById("svg-container");
  container.querySelectorAll("[data-layer-index]").forEach((path) => {
    const stepIndex = parseInt(path.dataset.layerIndex, 10) - 1; // layer 0 is always the substrate
    const selected = state.viewMode === "couches" && state.editingIndex === stepIndex;
    path.style.stroke = selected ? "var(--accent)" : "";
    path.style.strokeWidth = selected ? "2.5" : "";
  });
}

function renderSteps() {
  updateViewModeAvailability(); // may fall back to étapes mode before we render rows below
  const list = document.getElementById("steps-list");
  document.getElementById("steps-count").textContent = state.steps.length;
  if (state.steps.length === 0) {
    list.innerHTML = `<div class="help" style="padding:12px 0;">Aucune étape pour l'instant.</div>`;
  } else {
    const compact = state.viewMode === "couches";
    list.innerHTML = state.steps.map((step, i) => stepRowHtml(step, i, compact)).join("");
    list.querySelectorAll(".js-step-row").forEach((row) => {
      row.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        startEditingStep(parseInt(row.dataset.index, 10));
      });
    });
    list.querySelectorAll(".js-step-remove").forEach((btn) => {
      btn.addEventListener("click", () => {
        const index = parseInt(btn.dataset.index, 10);
        state.steps.splice(index, 1);
        if (state.editingIndex === index) cancelEditingStep();
        else renderSteps();
      });
    });
    list.querySelectorAll(".js-step-up").forEach((btn) => {
      btn.addEventListener("click", () => moveStep(parseInt(btn.dataset.index, 10), -1));
    });
    list.querySelectorAll(".js-step-down").forEach((btn) => {
      btn.addEventListener("click", () => moveStep(parseInt(btn.dataset.index, 10), 1));
    });
  }
  refreshCampaignFactorSteps();
  state.campaignPlan = null;
  document.getElementById("campaign-result").innerHTML = "";
  updateStepFormVisibility();
  highlightSelectedLayer();
  scheduleSimulate();
}

function fillKindFields(step) {
  document.getElementById("kind-select").value = step.kind;
  renderKindFields(step.kind);
  document.getElementById("f-name").value = step.name;
  if (step.kind === "deposition") {
    document.getElementById("f-material").value = step.material;
    document.getElementById("f-mode").value = step.mode;
    document.getElementById("f-angle").value = step.angle_deg || 0;
    document.getElementById("f-angle-wrap").style.display = step.mode === "directional" ? "" : "none";
    document.getElementById("f-thickness").value = step.thickness.value;
    document.getElementById("f-thickness-unit").value = step.thickness.unit;
    const processParameters = step.process_parameters || {};
    const derivedEstimates = step.derived_estimates || [];
    Object.entries(processParameters).forEach(([name, value]) => addProcessParamRow(name, value));
    derivedEstimates.forEach((estimate) => addEstimateRow(estimate));
    document.getElementById("f-deposition-advanced").open =
      Object.keys(processParameters).length > 0 || derivedEstimates.length > 0;
  } else if (step.kind === "etch") {
    document.getElementById("f-mode").value = step.mode;
    document.getElementById("f-angle").value = step.angle_deg || 0;
    document.getElementById("f-angle-wrap").style.display = step.mode === "directional" ? "" : "none";
    document.getElementById("f-default-factor").value = step.default_factor != null ? step.default_factor : 1.0;
    Object.entries(step.selectivity_by_material || {}).forEach(([material, factor]) => addSelectivityRow(material, factor));
    document.getElementById("f-depth").value = step.depth.value;
    document.getElementById("f-depth-unit").value = step.depth.unit;
  } else if (step.kind === "selective_growth") {
    document.getElementById("f-material").value = step.material;
    document.getElementById("f-thickness").value = step.thickness.value;
    document.getElementById("f-thickness-unit").value = step.thickness.unit;
    document.getElementById("f-rate-m").value = step.rate_m;
    document.getElementById("f-rate-sp").value = step.rate_sp;
  } else if (step.kind === "planarization") {
    const mode = step.target_level ? "level" : "material";
    document.getElementById("f-plana-mode").value = mode;
    document.getElementById("f-plana-mode").dispatchEvent(new Event("change"));
    if (mode === "level") {
      document.getElementById("f-target-level").value = step.target_level.value;
      document.getElementById("f-target-level-unit").value = step.target_level.unit;
    } else {
      document.getElementById("f-stop-material").value = step.stop_material;
    }
  } else if (step.kind === "lithography") {
    document.getElementById("f-resist-material").value = step.resist_material;
    document.getElementById("f-thickness").value = step.thickness.value;
    document.getElementById("f-thickness-unit").value = step.thickness.unit;
    document.getElementById("f-openings").value = step.openings.map((pair) => pair.join("-")).join(", ");
  } else if (step.kind === "chemical") {
    document.getElementById("f-description").value = step.description || "";
  } else if (step.kind === "resist_strip") {
    document.getElementById("f-material").value = step.material;
  } else if (step.kind === "semipolar_facet") {
    document.getElementById("f-orientation").value = step.orientation;
    document.getElementById("f-base-half-width").value = step.base_half_width.value;
    document.getElementById("f-base-half-width-unit").value = step.base_half_width.unit;
    document.getElementById("f-tip-half-width").value = step.tip_half_width.value;
    document.getElementById("f-tip-half-width-unit").value = step.tip_half_width.unit;
    document.getElementById("f-facet-angle").value = step.facet_angle_deg;
    document.getElementById("f-position").value = step.position != null ? step.position.value : "";
  }
}

function startEditingStep(index) {
  state.editingIndex = index;
  fillKindFields(state.steps[index]);
  document.getElementById("step-form-title").textContent = `Modifier l'étape ${index + 1}`;
  document.getElementById("add-step-btn-label").textContent = "Enregistrer les modifications";
  renderSteps();
}

function cancelEditingStep() {
  state.editingIndex = null;
  if (state.viewMode === "couches") state.showStepForm = false;
  document.getElementById("step-form-title").textContent = "Ajouter une étape";
  document.getElementById("add-step-btn-label").textContent = "Ajouter cette étape";
  renderKindFields(document.getElementById("kind-select").value);
  renderSteps();
}

function startAddingStep() {
  state.editingIndex = null;
  state.showStepForm = true;
  document.getElementById("step-form-title").textContent = "Ajouter une étape";
  document.getElementById("add-step-btn-label").textContent = "Ajouter cette étape";
  renderKindFields(document.getElementById("kind-select").value);
  renderSteps();
}

function setViewMode(mode) {
  state.viewMode = mode;
  state.showStepForm = false;
  document.getElementById("view-mode-help").textContent =
    mode === "couches"
      ? "Cliquez une couche du dessin pour l'éditer. Disponible tant que la structure n'est faite que de dépôts (empilement d'épitaxie)."
      : "Cliquez une étape pour la modifier ; ▲▼ pour la déplacer.";
  renderSteps();
}

document.getElementById("view-mode-couches").addEventListener("click", () => setViewMode("couches"));
document.getElementById("view-mode-etapes").addEventListener("click", () => setViewMode("etapes"));

document.getElementById("add-step-shortcut-btn").addEventListener("click", startAddingStep);

document.getElementById("svg-container").addEventListener("click", (event) => {
  if (state.viewMode !== "couches") return;
  const path = event.target.closest("[data-layer-index]");
  if (!path) return;
  const layerIndex = parseInt(path.dataset.layerIndex, 10);
  if (layerIndex === 0) {
    document.getElementById("substrate-section").scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  const stepIndex = layerIndex - 1;
  if (stepIndex >= 0 && stepIndex < state.steps.length) startEditingStep(stepIndex);
});

function moveStep(index, delta) {
  const target = index + delta;
  if (target < 0 || target >= state.steps.length) return;
  const [step] = state.steps.splice(index, 1);
  state.steps.splice(target, 0, step);
  if (state.editingIndex === index) state.editingIndex = target;
  else if (state.editingIndex === target) state.editingIndex = index;
  renderSteps();
}

function renderObjectives() {
  const list = document.getElementById("objectives-list");
  list.innerHTML = state.objectives
    .map(
      (o, i) => `
      <div class="step-row" style="align-items:flex-start;">
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:600;">${escapeHtml(o.name)}</div>
          <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(o.metric)} &middot; ${escapeHtml(o.direction)}${o.target != null ? " · cible " + o.target : ""}</div>
          ${o.rationale ? `<div style="font-size:12px;color:var(--text-soft);margin-top:4px;">${escapeHtml(o.rationale)}</div>` : ""}
          ${o.verification_method ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:2px;">Vérification : ${escapeHtml(o.verification_method)}</div>` : ""}
        </div>
        <button class="step-remove" data-index="${i}" type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
        </button>
      </div>`
    )
    .join("");
  list.querySelectorAll(".step-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.objectives.splice(parseInt(btn.dataset.index, 10), 1);
      renderObjectives();
    });
  });
}

const CAMPAIGN_FIELD_OPTIONS = {
  deposition: [["thickness", "Épaisseur"]],
  etch: [["depth", "Profondeur"]],
  planarization: [["target_level", "Niveau cible"]],
  lithography: [["thickness", "Épaisseur"]],
  chemical: [],
  resist_strip: [],
};

function campaignStepOptionsHtml() {
  if (state.steps.length === 0) return `<option value="">Ajoutez au moins une étape d'abord</option>`;
  return state.steps
    .map((s, i) => `<option value="${i}">${i + 1}. ${escapeHtml(STEP_KINDS[s.kind].label)} — ${escapeHtml(s.name)}</option>`)
    .join("");
}

function campaignFieldOptionsHtml(stepIndex) {
  const step = state.steps[stepIndex];
  const options = step ? CAMPAIGN_FIELD_OPTIONS[step.kind] || [] : [];
  const estimateOptions = step && step.derived_estimates ? step.derived_estimates : [];
  const optionsHtml = options.map(([value, label]) => `<option value="${value}">${label}</option>`);
  // a derived estimate (ex : dopage) is split by choosing target estimate values directly - the
  // step's process parameter is solved from them server-side (see _step_with_estimate_value).
  const estimateOptionsHtml = estimateOptions.map(
    (e) => `<option value="estimate:${escapeHtml(e.name)}">${escapeHtml(e.name)} (estimée)</option>`
  );
  const all = [...optionsHtml, ...estimateOptionsHtml];
  return all.length ? all.join("") : `<option value="">Aucun paramètre modifiable sur cette étape</option>`;
}

function addCampaignFactorRow() {
  const row = document.createElement("div");
  row.className = "js-campaign-factor-row";
  row.style = "border:1px solid var(--border-soft);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:8px;";
  row.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <label style="margin:0;">Étape</label>
      <button class="js-remove-factor" type="button" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;line-height:1;">&times;</button>
    </div>
    <select class="field js-factor-step">${campaignStepOptionsHtml()}</select>
    <label>Paramètre</label>
    <select class="field js-factor-field"></select>
    <label>Valeurs</label>
    <input class="field js-factor-values" placeholder="ex : 10, 20, 30">`;
  document.getElementById("campaign-factors").appendChild(row);
  const stepSelect = row.querySelector(".js-factor-step");
  const fieldSelect = row.querySelector(".js-factor-field");
  const refreshField = () => {
    fieldSelect.innerHTML = campaignFieldOptionsHtml(parseInt(stepSelect.value, 10));
  };
  stepSelect.addEventListener("change", refreshField);
  refreshField();
  row.querySelector(".js-remove-factor").addEventListener("click", () => row.remove());
}

document.getElementById("campaign-add-factor-btn").addEventListener("click", addCampaignFactorRow);

function refreshCampaignFactorSteps() {
  document.querySelectorAll(".js-campaign-factor-row").forEach((row) => {
    const stepSelect = row.querySelector(".js-factor-step");
    const previous = stepSelect.value;
    stepSelect.innerHTML = campaignStepOptionsHtml();
    stepSelect.value = [...stepSelect.options].some((o) => o.value === previous) ? previous : stepSelect.value;
    row.querySelector(".js-factor-field").innerHTML = campaignFieldOptionsHtml(parseInt(stepSelect.value, 10));
  });
}

function campaignPlan() {
  const rows = [...document.querySelectorAll(".js-campaign-factor-row")];
  if (rows.length === 0) return null;
  const factors = [];
  for (const row of rows) {
    const stepIndex = parseInt(row.querySelector(".js-factor-step").value, 10);
    const fieldValue = row.querySelector(".js-factor-field").value;
    const values = row
      .querySelector(".js-factor-values")
      .value.split(",")
      .map((v) => parseFloat(v.trim()))
      .filter((v) => !Number.isNaN(v));
    if (Number.isNaN(stepIndex) || !fieldValue || values.length === 0) return null;
    if (fieldValue.startsWith("estimate:")) {
      factors.push({ step_index: stepIndex, via_estimate: fieldValue.slice("estimate:".length), values });
    } else {
      factors.push({ step_index: stepIndex, field: fieldValue, values });
    }
  }
  return { factors };
}

document.getElementById("campaign-preview-btn").addEventListener("click", async () => {
  clearError();
  const plan = campaignPlan();
  if (!plan) {
    showError(new Error("Pour chaque paramètre : choisissez une étape, un paramètre et au moins une valeur."));
    return;
  }
  try {
    const result = await api.post(`/api/projects/${slug}/structures/variantes`, {
      substrate: substrateSpec(),
      steps: state.steps,
      plan,
    });
    state.campaignPlan = plan;
    const variation = result.variation;
    document.getElementById("campaign-result").innerHTML = `
      <div style="font-size:12.5px;color:var(--text-soft);margin-top:10px;">
        ${variation.entity_count} échantillons &middot; ${result.factor_labels.join(" &times; ")}
      </div>
      <div style="display:flex;gap:8px;margin-top:8px;overflow-x:auto;">
        ${result.svgs.map((svg, i) => `<div style="flex:none;width:120px;border:1px solid var(--border-soft);border-radius:6px;padding:4px;text-align:center;">${svg}<div class="mono" style="font-size:11px;color:var(--text-soft);margin-top:4px;">${escapeHtml(result.labels[i])}</div></div>`).join("")}
      </div>`;
  } catch (err) {
    showError(err);
  }
});

document.getElementById("campaign-clear-btn").addEventListener("click", () => {
  state.campaignPlan = null;
  document.getElementById("campaign-factors").innerHTML = "";
  document.getElementById("campaign-result").innerHTML = "";
  addCampaignFactorRow();
});

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

async function loadPickers() {
  state.materials = await api.get(`/api/projects/${slug}/materials`);
  state.stepPresets = await api.get(`/api/projects/${slug}/presets-etapes`);
  document.getElementById("substrate-material").innerHTML = materialOptions("Si");
  renderKindFields(document.getElementById("kind-select").value);
}

async function loadExistingProcess() {
  if (!evolveExperienceId) return;
  try {
    const data = await api.get(`/api/projects/${slug}/experiences/${evolveExperienceId}/process`);
    setSubstrateFields(data.substrate);
    state.steps = data.steps;
    renderSteps();
    document.getElementById("page-title").textContent = "Enregistrer une évolution";
    document.getElementById("launch-btn").textContent = "Enregistrer cette évolution";

    const detail = await api.get(`/api/projects/${slug}/experiences/${evolveExperienceId}`);
    document.getElementById("exp-title").value = detail.title;
    document.getElementById("exp-intent").value = detail.intent;
    document.getElementById("exp-hypothesis").value = detail.hypothesis || "";
    const verification = detail.objective_verification || {};
    state.objectives = detail.objectives.map((o) => ({ ...o, verification_method: verification[o.name] || null }));
    renderObjectives();
  } catch (err) {
    showError(err);
  }
}

function setSubstrateFields(substrate) {
  document.getElementById("substrate-material").value = substrate.material;
  document.getElementById("substrate-width").value = substrate.domain_width.value;
  document.getElementById("substrate-width-unit").value = substrate.domain_width.unit;
  document.getElementById("substrate-thickness").value = substrate.thickness.value;
  document.getElementById("substrate-thickness-unit").value = substrate.thickness.unit;
}

function substrateSpec() {
  return {
    material: document.getElementById("substrate-material").value,
    domain_width: lengthValue("substrate-width"),
    thickness: lengthValue("substrate-thickness"),
  };
}

document.getElementById("kind-select").addEventListener("change", (e) => renderKindFields(e.target.value));

document.getElementById("add-step-btn").addEventListener("click", () => {
  clearError();
  try {
    const step = buildStepFromForm();
    if (state.editingIndex !== null) {
      state.steps[state.editingIndex] = step;
    } else {
      state.steps.push(step);
    }
    cancelEditingStep();
  } catch (err) {
    showError(err);
  }
});

document.getElementById("cancel-edit-btn").addEventListener("click", () => {
  clearError();
  cancelEditingStep();
});

document.getElementById("objective-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const name = document.getElementById("obj-name").value.trim();
  const metric = document.getElementById("obj-metric").value.trim();
  if (!name || !metric) return;
  const targetRaw = document.getElementById("obj-target").value;
  state.objectives.push({
    name,
    metric,
    direction: document.getElementById("obj-direction").value,
    target: targetRaw ? parseFloat(targetRaw) : null,
    rationale: document.getElementById("obj-rationale").value.trim() || null,
    verification_method: document.getElementById("obj-verification").value.trim() || null,
  });
  document.getElementById("objective-form").reset();
  renderObjectives();
});

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

document.getElementById("launch-btn").addEventListener("click", async () => {
  clearError();
  const title = document.getElementById("exp-title").value.trim();
  const intent = document.getElementById("exp-intent").value.trim();
  if (!title || !intent) {
    showError(new Error("Le titre et l'intention sont obligatoires."));
    return;
  }
  const payload = {
    substrate: substrateSpec(),
    steps: state.steps,
    title,
    intent,
    hypothesis: document.getElementById("exp-hypothesis").value || null,
    objectives: state.objectives,
  };
  if (evolveExperienceId && document.getElementById("branch-fork").checked) {
    const branchName = document.getElementById("new-branch-name").value.trim();
    if (!branchName) {
      showError(new Error("Donnez un nom à la nouvelle piste."));
      return;
    }
    payload.new_branch = branchName;
  }
  try {
    let endpoint;
    if (state.campaignPlan) {
      payload.plan = state.campaignPlan;
      endpoint = `/api/projects/${slug}/experiences/campagne`;
    } else if (evolveExperienceId) {
      endpoint = `/api/projects/${slug}/experiences/${evolveExperienceId}/evoluer`;
    } else {
      endpoint = `/api/projects/${slug}/experiences`;
    }
    const result = await api.post(endpoint, payload);
    window.location.href = `/projets/${slug}/experiences/${result.id}`;
  } catch (err) {
    showError(err);
  }
});

document.getElementById("branch-continue").addEventListener("change", () => {
  document.getElementById("new-branch-name").style.display = "none";
});
document.getElementById("branch-fork").addEventListener("change", () => {
  document.getElementById("new-branch-name").style.display = "";
});

async function loadTemplateProcess() {
  if (!templateExperienceId) return;
  document.getElementById("page-title").textContent = "Nouvelle expérience (structure reprise)";
  try {
    const data = await api.get(`/api/projects/${slug}/experiences/${templateExperienceId}/process`);
    setSubstrateFields(data.substrate);
    state.steps = data.steps;
    renderSteps();
  } catch (err) {
    showError(err);
  }
}

async function fetchSavedStructures() {
  return api.get(`/api/projects/${slug}/structures-sauvegardees`);
}

function findSavedStructure(list, name, scope) {
  const bucket = scope === "preset" ? list.presets : scope === "partagee" ? list.partagees : list.projet;
  return (bucket || []).find((s) => s.name === name) || null;
}

async function loadChosenStructureForExperience() {
  if (!chosenStructureName) return;
  try {
    const list = await fetchSavedStructures();
    const found = findSavedStructure(list, chosenStructureName, chosenStructureScope);
    if (!found) {
      showError(new Error(`Structure "${chosenStructureName}" introuvable dans la bibliothèque.`));
      return;
    }
    setSubstrateFields(found.substrate);
    state.steps = found.steps;
    renderSteps();
    document.getElementById("based-on-note").style.display = "";
    document.getElementById("based-on-name").textContent = found.name;
    document.getElementById("edit-structure-link").href =
      `/projets/${slug}/structures/bibliotheque/${encodeURIComponent(found.name)}` +
      `?scope=${chosenStructureScope}&dupliquer=1&retour=nouvelle-experience`;
  } catch (err) {
    showError(err);
  }
}

document.getElementById("library-save-btn").addEventListener("click", () => saveLibraryStructure(false));
document.getElementById("library-save-as-btn").addEventListener("click", () => saveLibraryStructure(true));

async function saveLibraryStructure(forceNew) {
  clearError();
  const name = document.getElementById("library-name").value.trim();
  if (!name) {
    showError(new Error("Donnez un nom à cette structure pour l'enregistrer."));
    return;
  }
  const partagee = document.getElementById("library-shared-checkbox").checked;
  const payload = {
    name,
    substrate: substrateSpec(),
    steps: state.steps,
    derived_from: state.derivedFrom || null,
    partagee,
  };
  try {
    if (!forceNew && state.editingLibraryName) {
      await api.put(
        `/api/projects/${slug}/structures-sauvegardees/${encodeURIComponent(state.editingLibraryName)}` +
          `?partagee=${state.editingLibraryScope === "partagee"}`,
        payload
      );
    } else {
      await api.post(`/api/projects/${slug}/structures-sauvegardees`, payload);
    }
    const scope = partagee ? "partagee" : "projet";
    if (returnTo === "nouvelle-experience") {
      window.location.href = `/projets/${slug}/structures/nouvelle?structure=${encodeURIComponent(name)}&scope=${scope}`;
    } else {
      window.location.href = `/projets/${slug}#structures`;
    }
  } catch (err) {
    showError(err);
  }
}

async function initLibraryMode() {
  document.getElementById("library-header").style.display = "";
  document.getElementById("experience-sections").style.display = "none";

  if (!libraryStructureName) {
    document.getElementById("page-title").textContent = "Nouvelle structure";
    return;
  }
  try {
    const list = await fetchSavedStructures();
    const found = findSavedStructure(list, libraryStructureName, librarySourceScope);
    if (!found) {
      showError(new Error(`Structure "${libraryStructureName}" introuvable.`));
      return;
    }
    setSubstrateFields(found.substrate);
    state.steps = found.steps;
    renderSteps();
    // A preset (structureforge built-in) has no backing store to edit in place - forcing
    // duplicate mode turns "Modifier" into "dupliquer sous un nouveau nom", which is the only
    // thing that makes sense for it.
    const duplicateMode = libraryDuplicateMode || librarySourceScope === "preset";
    if (duplicateMode) {
      document.getElementById("page-title").textContent =
        librarySourceScope === "preset" ? "Enregistrer ce préset sous un nouveau nom" : "Dupliquer une structure";
      document.getElementById("library-name").placeholder = `ex : ${found.name} + ...`;
      state.derivedFrom = found.name;
      document.getElementById("library-derived-note").style.display = "";
      document.getElementById("library-derived-note").textContent = `Dérivée de : ${found.name}`;
    } else {
      document.getElementById("page-title").textContent = "Modifier la structure";
      document.getElementById("library-name").value = found.name;
      document.getElementById("library-shared-checkbox").checked = librarySourceScope === "partagee";
      state.derivedFrom = found.derived_from || null;
      state.editingLibraryName = found.name;
      state.editingLibraryScope = librarySourceScope;
      document.getElementById("library-save-as-btn").style.display = "";
      if (found.derived_from) {
        document.getElementById("library-derived-note").style.display = "";
        document.getElementById("library-derived-note").textContent = `Dérivée de : ${found.derived_from}`;
      }
    }
  } catch (err) {
    showError(err);
  }
}

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

/* -- "Voir le code" : sérialise le substrat + les étapes courantes en script StructureForge
   autonome, indépendant de Spectre - mêmes classes/champs que structureforge.process.steps. */

const LENGTH_TO_NM = { A: 0.1, nm: 1, um: 1000, mm: 1_000_000 };
const PY_STEP_CLASS = {
  deposition: "Deposition",
  etch: "Etch",
  planarization: "Planarization",
  chemical: "ChemicalStep",
  lithography: "Lithography",
  resist_strip: "ResistStrip",
  semipolar_facet: "SemipolarFacet",
  selective_growth: "SelectiveGrowth",
};

function toNm(length) {
  return length.value * (LENGTH_TO_NM[length.unit] || 1);
}

function pyStr(value) {
  return JSON.stringify(String(value));
}

function pyLength(length) {
  return `Length(value=${length.value}, unit=${pyStr(length.unit)})`;
}

function pyDict(obj) {
  const entries = Object.entries(obj || {});
  if (entries.length === 0) return "{}";
  return `{${entries.map(([k, v]) => `${pyStr(k)}: ${v}`).join(", ")}}`;
}

function pyStepCode(step) {
  const name = pyStr(step.name);
  if (step.kind === "deposition") {
    const parts = [`name=${name}`, `material=${pyStr(step.material)}`, `mode=DepositionMode.${step.mode}`];
    if (step.angle_deg) parts.push(`angle_deg=${step.angle_deg}`);
    parts.push(`thickness=${pyLength(step.thickness)}`);
    if (step.process_parameters && Object.keys(step.process_parameters).length) parts.push(`process_parameters=${pyDict(step.process_parameters)}`);
    return `Deposition(${parts.join(", ")})`;
  }
  if (step.kind === "etch") {
    const parts = [`name=${name}`, `mode=EtchMode.${step.mode}`];
    if (step.angle_deg) parts.push(`angle_deg=${step.angle_deg}`);
    if (step.selectivity_by_material && Object.keys(step.selectivity_by_material).length) parts.push(`selectivity_by_material=${pyDict(step.selectivity_by_material)}`);
    if (step.default_factor != null && step.default_factor !== 1.0) parts.push(`default_factor=${step.default_factor}`);
    parts.push(`depth=${pyLength(step.depth)}`);
    return `Etch(${parts.join(", ")})`;
  }
  if (step.kind === "selective_growth") {
    return `SelectiveGrowth(name=${name}, material=${pyStr(step.material)}, thickness=${pyLength(step.thickness)}, rate_m=${step.rate_m}, rate_sp=${step.rate_sp})`;
  }
  if (step.kind === "planarization") {
    if (step.target_level) return `Planarization(name=${name}, target_level=${pyLength(step.target_level)})`;
    return `Planarization(name=${name}, stop_material=${pyStr(step.stop_material)})`;
  }
  if (step.kind === "chemical") {
    return `ChemicalStep(name=${name}${step.description ? `, description=${pyStr(step.description)}` : ""})`;
  }
  if (step.kind === "lithography") {
    const openings = step.openings.map(([a, b]) => `(${a}, ${b})`).join(", ");
    return `Lithography(name=${name}, resist_material=${pyStr(step.resist_material)}, thickness=${pyLength(step.thickness)}, openings=[${openings}])`;
  }
  if (step.kind === "resist_strip") {
    return `ResistStrip(name=${name}, material=${pyStr(step.material)})`;
  }
  if (step.kind === "semipolar_facet") {
    const parts = [
      `name=${name}`,
      `orientation=${pyStr(step.orientation)}`,
      `base_half_width=${pyLength(step.base_half_width)}`,
      `tip_half_width=${pyLength(step.tip_half_width)}`,
      `facet_angle_deg=${step.facet_angle_deg}`,
    ];
    if (step.position) parts.push(`position=${pyLength(step.position)}`);
    return `SemipolarFacet(${parts.join(", ")})`;
  }
  return `# étape non reconnue: ${step.kind}`;
}

function generateStructureForgeCode() {
  const substrate = substrateSpec();
  const usedKinds = [...new Set(state.steps.map((s) => s.kind))];
  const importNames = new Set(["Geometry", "Length", "default_library", "save_svg", "simulate"]);
  usedKinds.forEach((k) => importNames.add(PY_STEP_CLASS[k] || k));
  if (usedKinds.includes("deposition")) importNames.add("DepositionMode");
  if (usedKinds.includes("etch")) importNames.add("EtchMode");
  const stepsLines = state.steps.length ? state.steps.map((s) => `    ${pyStepCode(s)},`).join("\n") : "    # aucune étape pour l'instant";
  return `from structureforge import (
    ${[...importNames].sort().join(",\n    ")},
)

materials = default_library()
geometry = Geometry.substrate(
    ${pyStr(substrate.material)},
    domain_width_nm=${toNm(substrate.domain_width)},
    thickness_nm=${toNm(substrate.thickness)},
)

steps = [
${stepsLines}
]

frames = simulate(geometry, steps, materials)
material_colors = {m.name: m.color for m in materials}
save_svg("structure.svg", frames[-1], material_colors)
`;
}

document.getElementById("show-code-btn").addEventListener("click", () => {
  document.getElementById("code-modal-pre").textContent = generateStructureForgeCode();
  document.getElementById("code-modal").showModal();
});
document.getElementById("code-modal-close-btn").addEventListener("click", () => {
  document.getElementById("code-modal").close();
});
document.getElementById("code-modal-copy-btn").addEventListener("click", async () => {
  const btn = document.getElementById("code-modal-copy-btn");
  try {
    await navigator.clipboard.writeText(document.getElementById("code-modal-pre").textContent);
    const original = btn.textContent;
    btn.textContent = "Copié !";
    setTimeout(() => (btn.textContent = original), 1500);
  } catch (err) {
    showError(new Error("Impossible de copier automatiquement - sélectionnez le code et copiez-le manuellement."));
  }
});

async function init() {
  document.getElementById("crumb").textContent = "/ " + slug;
  if (evolveExperienceId) {
    document.getElementById("campaign-section").style.display = "none";
    document.getElementById("branch-choice-wrap").style.display = "block";
  }
  await loadPickers();
  renderSteps();
  renderObjectives();
  renderFrame();
  if (isLibraryMode) {
    await initLibraryMode();
  } else {
    await loadExistingProcess();
    await loadTemplateProcess();
    await loadChosenStructureForExperience();
  }
  addCampaignFactorRow();
}

init();
