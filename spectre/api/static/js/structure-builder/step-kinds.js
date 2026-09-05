/* Un seul point d'entrée par type d'étape : formulaire (rendu + câblage + lecture + pré-remplissage
   à l'édition), résumé affiché dans la liste, paramètre(s) éligibles à une campagne DOE, et
   génération du code Python StructureForge équivalent. Avant cette modularisation, ajouter ou
   modifier un type d'étape demandait de toucher neuf fonctions différentes (une par
   responsabilité) ; chaque type vit maintenant dans une seule entrée de STEP_KIND_DEFS.
   STEP_KINDS/CAMPAIGN_FIELD_OPTIONS/PY_STEP_CLASS restent exposés sous leur ancienne forme
   (dérivés du registre) car step-list.js, campaign.js et code-export.js les lisent directement. */

const STEP_KIND_DEFS = {
  deposition: {
    label: "Dépôt",
    color: "#1d6fae",
    tint: "#e8f1fa",
    iconPath: '<path d="M12 3v13m0 0l-5-5m5 5l5-5M4 20h16"/>',
    campaignFields: [["thickness", "Épaisseur"]],
    pyClass: "Deposition",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Dépôt"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions()}</select></div>
      <div><label>Préset (optionnel)</label><select class="field" id="f-preset"><option value="">Personnalisé</option>${presetOptionsHtml("deposition")}</select>
        <div class="help" style="margin-top:4px;">Choisit la recette ci-dessous — reste ensuite librement modifiable.</div>
      </div>
      <div><label>Recette</label><select class="field" id="f-recipe">${recipeOptions("deposition")}</select>
        <div class="help" id="f-recipe-hint" style="margin-top:4px;"></div>
      </div>
      <div class="field-row"><div><label>Épaisseur</label><input class="field" id="f-thickness" type="number" value="20"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option><option value="um">µm</option><option value="A">Å</option></select></div></div>`,
    wire: () => wireRecipeField("deposition"),
    buildFromForm: (name) => ({
      kind: "deposition",
      name,
      material: document.getElementById("f-material").value,
      recipe: document.getElementById("f-recipe").value,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
    }),
    fillFields: (step) => {
      document.getElementById("f-material").value = step.material;
      document.getElementById("f-recipe").value = step.recipe;
      document.getElementById("f-thickness").value = step.thickness.value;
      document.getElementById("f-thickness-unit").value = step.thickness.unit;
    },
    summary: (step) => `${step.material} · ${step.thickness.value} ${step.thickness.unit} · ${step.recipe}`,
    pyCode: (step) =>
      `Deposition(name=${pyStr(step.name)}, material=${pyStr(step.material)}, recipe=${pyStr(step.recipe)}, thickness=${pyLength(step.thickness)})`,
  },

  etch: {
    label: "Gravure",
    color: "#a45a3a",
    tint: "#f6ede7",
    iconPath: '<path d="M12 21V8m0 0l-5 5m5-5l5 5M4 4h16"/>',
    campaignFields: [["depth", "Profondeur"]],
    pyClass: "Etch",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Gravure"></div>
      <div><label>Préset (optionnel)</label><select class="field" id="f-preset"><option value="">Personnalisé</option>${presetOptionsHtml("etch")}</select>
        <div class="help" style="margin-top:4px;">Choisit la recette ci-dessous — reste ensuite librement modifiable.</div>
      </div>
      <div><label>Recette</label><select class="field" id="f-recipe">${recipeOptions("etch")}</select>
        <div class="help" id="f-recipe-hint" style="margin-top:4px;"></div>
      </div>
      <div class="field-row"><div><label>Profondeur</label><input class="field" id="f-depth" type="number" value="10"></div>
      <div><label>Unité</label><select class="field" id="f-depth-unit"><option value="nm" selected>nm</option><option value="um">µm</option><option value="A">Å</option></select></div></div>`,
    wire: () => wireRecipeField("etch"),
    buildFromForm: (name) => ({
      kind: "etch",
      name,
      recipe: document.getElementById("f-recipe").value,
      depth: { value: parseFloat(document.getElementById("f-depth").value) || 0, unit: document.getElementById("f-depth-unit").value },
    }),
    fillFields: (step) => {
      document.getElementById("f-recipe").value = step.recipe;
      document.getElementById("f-depth").value = step.depth.value;
      document.getElementById("f-depth-unit").value = step.depth.unit;
    },
    summary: (step) => `${step.recipe} · ${step.depth.value} ${step.depth.unit}`,
    pyCode: (step) => `Etch(name=${pyStr(step.name)}, recipe=${pyStr(step.recipe)}, depth=${pyLength(step.depth)})`,
  },

  planarization: {
    label: "Planarisation",
    color: "#5c655e",
    tint: "#ede9df",
    iconPath: '<path d="M4 12h16M8 6h8M8 18h8"/>',
    campaignFields: [["target_level", "Niveau cible"]],
    pyClass: "Planarization",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Planarisation"></div>
      <div><label>S'arrête sur</label>
        <select class="field" id="f-plana-mode"><option value="level">Un niveau précis</option><option value="material">Un matériau</option></select>
      </div>
      <div id="f-plana-value"><div class="field-row"><div><input class="field" id="f-target-level" type="number" value="0"></div><div><select class="field" id="f-target-level-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div></div>`,
    wire: () => {
      document.getElementById("f-plana-mode").addEventListener("change", (e) => {
        const target = document.getElementById("f-plana-value");
        target.innerHTML =
          e.target.value === "level"
            ? `<div class="field-row"><div><input class="field" id="f-target-level" type="number" value="0"></div><div><select class="field" id="f-target-level-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>`
            : `<select class="field" id="f-stop-material">${materialOptions()}</select>`;
      });
    },
    buildFromForm: (name) => {
      const mode = document.getElementById("f-plana-mode").value;
      if (mode === "level") {
        return {
          kind: "planarization",
          name,
          target_level: { value: parseFloat(document.getElementById("f-target-level").value) || 0, unit: document.getElementById("f-target-level-unit").value },
        };
      }
      return { kind: "planarization", name, stop_material: document.getElementById("f-stop-material").value };
    },
    fillFields: (step) => {
      const mode = step.target_level ? "level" : "material";
      document.getElementById("f-plana-mode").value = mode;
      document.getElementById("f-plana-mode").dispatchEvent(new Event("change"));
      if (mode === "level") {
        document.getElementById("f-target-level").value = step.target_level.value;
        document.getElementById("f-target-level-unit").value = step.target_level.unit;
      } else {
        document.getElementById("f-stop-material").value = step.stop_material;
      }
    },
    summary: (step) => (step.target_level ? `jusqu'à ${step.target_level.value} ${step.target_level.unit}` : `jusqu'au ${step.stop_material}`),
    pyCode: (step) => {
      const name = pyStr(step.name);
      if (step.target_level) return `Planarization(name=${name}, target_level=${pyLength(step.target_level)})`;
      return `Planarization(name=${name}, stop_material=${pyStr(step.stop_material)})`;
    },
  },

  lithography: {
    label: "Lithographie",
    color: "#7a4a97",
    tint: "#f2e9f7",
    iconPath: '<path d="M6 4l12 16M18 4L6 20"/>',
    campaignFields: [["thickness", "Épaisseur"]],
    pyClass: "Lithography",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Lithographie"></div>
      <div><label>Résine</label><select class="field" id="f-resist-material">${materialOptions("Photoresist")}</select></div>
      <div class="field-row"><div><label>Épaisseur</label><input class="field" id="f-thickness" type="number" value="500"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option></select></div></div>
      <div class="card" style="padding:10px 12px;margin:4px 0;background:var(--bg);">
        <div style="font-size:12px;font-weight:600;margin-bottom:6px;">Réseau périodique (optionnel)</div>
        <div class="field-row">
          <div><label>Pas (pitch, nm)</label><input class="field" id="f-litho-pitch" type="number" min="0"></div>
          <div><label>Diamètre d'ouverture (nm)</label><input class="field" id="f-litho-diameter" type="number" min="0"></div>
        </div>
        <div class="field-row">
          <div><label>Nombre (optionnel)</label><input class="field" id="f-litho-count" type="number" min="1" placeholder="rempli le domaine"></div>
          <div><label>Décalage du centre (optionnel)</label><input class="field" id="f-litho-offset" type="number" placeholder="centré"></div>
        </div>
        <button class="btn btn-line btn-block" id="f-litho-generate-btn" type="button" style="margin-top:6px;">Générer les ouvertures</button>
      </div>
      <div><label>Ouvertures (nm)</label><input class="field" id="f-openings" placeholder="ex : 80-140, 300-360"><div class="help">Zones où le masque est ouvert, séparées par des virgules — modifiable librement après génération.</div></div>`,
    wire: () => {
      document.getElementById("f-litho-generate-btn").addEventListener("click", () => {
        const pitch = parseFloat(document.getElementById("f-litho-pitch").value);
        const diameter = parseFloat(document.getElementById("f-litho-diameter").value);
        const countRaw = document.getElementById("f-litho-count").value;
        const offsetRaw = document.getElementById("f-litho-offset").value;
        const domainWidthNm = toNm(substrateSpec().domain_width);
        const openings = generatePeriodicOpenings(
          pitch,
          diameter,
          domainWidthNm,
          countRaw ? parseInt(countRaw, 10) : null,
          offsetRaw ? parseFloat(offsetRaw) : null
        );
        document.getElementById("f-openings").value = openings.map((pair) => pair.join("-")).join(", ");
      });
    },
    buildFromForm: (name) => ({
      kind: "lithography",
      name,
      resist_material: document.getElementById("f-resist-material").value,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
      openings: parseOpenings(document.getElementById("f-openings").value),
    }),
    fillFields: (step) => {
      document.getElementById("f-resist-material").value = step.resist_material;
      document.getElementById("f-thickness").value = step.thickness.value;
      document.getElementById("f-thickness-unit").value = step.thickness.unit;
      document.getElementById("f-openings").value = step.openings.map((pair) => pair.join("-")).join(", ");
    },
    summary: (step) => `${step.resist_material} · ${step.openings.length} ouverture(s)`,
    pyCode: (step) => {
      const openings = step.openings.map(([a, b]) => `(${a}, ${b})`).join(", ");
      return `Lithography(name=${pyStr(step.name)}, resist_material=${pyStr(step.resist_material)}, thickness=${pyLength(step.thickness)}, openings=[${openings}])`;
    },
  },

  chemical: {
    label: "Étape chimique",
    color: "#3f7d4a",
    tint: "#e9f4ea",
    iconPath: '<path d="M9 3h6M10 3v5l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3"/>',
    campaignFields: [],
    pyClass: "ChemicalStep",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Nettoyage"></div>
      <div><label>Description (optionnelle)</label><input class="field" id="f-description" placeholder="ex : bain HF"></div>`,
    buildFromForm: (name) => ({ kind: "chemical", name, description: document.getElementById("f-description").value || null, parameters: {} }),
    fillFields: (step) => {
      document.getElementById("f-description").value = step.description || "";
    },
    summary: (step) => step.description || "sans effet géométrique",
    pyCode: (step) => `ChemicalStep(name=${pyStr(step.name)}${step.description ? `, description=${pyStr(step.description)}` : ""})`,
  },

  resist_strip: {
    label: "Retrait de résine",
    color: "#a45a3a",
    tint: "#f6ede7",
    iconPath: '<path d="M5 5l14 14M5 19L19 5"/>',
    campaignFields: [],
    pyClass: "ResistStrip",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Retrait de résine"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions("Photoresist")}</select></div>`,
    buildFromForm: (name) => ({ kind: "resist_strip", name, material: document.getElementById("f-material").value }),
    fillFields: (step) => {
      document.getElementById("f-material").value = step.material;
    },
    summary: (step) => step.material,
    pyCode: (step) => `ResistStrip(name=${pyStr(step.name)}, material=${pyStr(step.material)})`,
  },

  faceted_growth: {
    label: "Croissance facettée",
    color: "#b8860b",
    tint: "#faf3df",
    iconPath: '<path d="M4 20L12 4L20 20Z"/>',
    campaignFields: [["thickness", "Épaisseur"]],
    pyClass: "FacetedGrowth",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Croissance facettée"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions("GaN")}</select></div>
      <div class="field-row"><div><label>Épaisseur nominale (plan C)</label><input class="field" id="f-thickness" type="number" value="10" min="0.1" step="0.1"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>
      <div class="help">Vitesses relatives par plan cristallin (plan C = référence 1.0). L'épaisseur nominale ci-dessus est celle déposée sur le plan C ; les plans M et semipolaire avancent chacun à leur propre vitesse relative — construction de Wulff cinétique, la même géométrie qu'un nanofil en crayon ou une pointe de LED III-N.</div>
      <div class="field-row"><div><label>Vitesse plan C (réf.)</label><input class="field" id="f-rate-c" type="number" value="1.0" min="0" step="0.05"></div>
      <div><label>Vitesse plan M (flancs)</label><input class="field" id="f-rate-m" type="number" value="0.25" min="0" step="0.05"></div></div>
      <div class="field-row"><div><label>Vitesse semipolaire</label><input class="field" id="f-rate-sp" type="number" value="0.5" min="0" step="0.05"></div>
      <div><label>Angle semipolaire (° depuis l'axe c)</label><input class="field" id="f-angle-sp" type="number" value="30" min="1" max="89" step="1"></div></div>
      <div class="help" id="f-tip-hint" style="margin-top:-6px;"></div>
      <div><label>Matériaux d'amorçage — SAG (optionnel)</label><input class="field" id="f-seed-materials" placeholder="ex : GaN, AlN">
        <div class="help" style="margin-top:4px;">Noms séparés par des virgules. Vide = croissance sur toute surface exposée, sans sélectivité.</div>
      </div>`,
    wire: () => wireFacetedGrowthTipHint(),
    buildFromForm: (name) => ({
      kind: "faceted_growth",
      name,
      material: document.getElementById("f-material").value,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
      rate_c: parseFloat(document.getElementById("f-rate-c").value) || 0,
      rate_m: parseFloat(document.getElementById("f-rate-m").value) || 0,
      rate_sp: parseFloat(document.getElementById("f-rate-sp").value) || 0,
      semi_polar_angle_deg: parseFloat(document.getElementById("f-angle-sp").value) || 30,
      seed_materials: parseCommaList(document.getElementById("f-seed-materials").value),
    }),
    fillFields: (step) => {
      document.getElementById("f-material").value = step.material;
      document.getElementById("f-thickness").value = step.thickness.value;
      document.getElementById("f-thickness-unit").value = step.thickness.unit;
      document.getElementById("f-rate-c").value = step.rate_c;
      document.getElementById("f-rate-m").value = step.rate_m;
      document.getElementById("f-rate-sp").value = step.rate_sp;
      document.getElementById("f-angle-sp").value = step.semi_polar_angle_deg;
      document.getElementById("f-seed-materials").value = (step.seed_materials || []).join(", ");
    },
    summary: (step) =>
      `${step.material} · +${step.thickness.value} ${step.thickness.unit} (C) · M×${step.rate_m} · SP×${step.rate_sp}` +
      (step.seed_materials && step.seed_materials.length ? ` · SAG sur ${step.seed_materials.join("/")}` : ""),
    pyCode: (step) => {
      const parts = [
        `name=${pyStr(step.name)}`,
        `material=${pyStr(step.material)}`,
        `thickness=${pyLength(step.thickness)}`,
        `rate_c=${step.rate_c}`,
        `rate_m=${step.rate_m}`,
        `rate_sp=${step.rate_sp}`,
        `semi_polar_angle_deg=${step.semi_polar_angle_deg}`,
      ];
      if (step.seed_materials && step.seed_materials.length) parts.push(`seed_materials=${pyList(step.seed_materials)}`);
      return `FacetedGrowth(${parts.join(", ")})`;
    },
  },

  epitaxial_growth: {
    label: "Croissance épitaxiale",
    color: "#2e8b57",
    tint: "#e6f4ec",
    iconPath: '<path d="M12 20V4M12 4l-5 5M12 4l5 5M6 14l6-4 6 4"/>',
    campaignFields: [["thickness", "Épaisseur"]],
    pyClass: "EpitaxialGrowth",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Croissance épitaxiale"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions("GaN")}</select></div>
      <div class="field-row"><div><label>Épaisseur</label><input class="field" id="f-thickness" type="number" value="20"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>
      <div><label>Orientation cristalline</label>
        <select class="field" id="f-orientation">
          <option value="c_plane">Plan C [0001] — vertical</option>
          <option value="m_plane">Plan M {10-10} — latéral (flancs)</option>
          <option value="semi_polar">Semi-polaire — incliné</option>
        </select>
      </div>
      <div id="f-angle-wrap" style="display:none;"><label>Angle (° depuis l'axe c)</label><input class="field" id="f-angle" type="number" value="32" min="0.1" max="89.9" step="0.1"></div>
      <div><label>Matériaux d'amorçage — SAG (optionnel)</label><input class="field" id="f-seed-materials" placeholder="ex : GaN, AlN">
        <div class="help" style="margin-top:4px;">Noms séparés par des virgules. Vide = croissance non sélective sur toute surface exposée (buffer, template) ; rempli, bloque la nucléation ailleurs — un vrai masque de croissance sélective (SAG).</div>
      </div>`,
    wire: () => wireEpitaxialOrientationToggle(),
    buildFromForm: (name) => {
      const orientation = document.getElementById("f-orientation").value;
      const step = {
        kind: "epitaxial_growth",
        name,
        material: document.getElementById("f-material").value,
        thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
        orientation,
        seed_materials: parseCommaList(document.getElementById("f-seed-materials").value),
      };
      if (orientation === "semi_polar") step.angle_deg = parseFloat(document.getElementById("f-angle").value) || 0;
      return step;
    },
    fillFields: (step) => {
      document.getElementById("f-material").value = step.material;
      document.getElementById("f-thickness").value = step.thickness.value;
      document.getElementById("f-thickness-unit").value = step.thickness.unit;
      document.getElementById("f-orientation").value = step.orientation;
      document.getElementById("f-angle-wrap").style.display = step.orientation === "semi_polar" ? "" : "none";
      document.getElementById("f-angle").value = step.angle_deg || 32;
      document.getElementById("f-seed-materials").value = (step.seed_materials || []).join(", ");
    },
    summary: (step) => {
      const orientationLabel = { c_plane: "plan C", m_plane: "plan M", semi_polar: `semi-polaire ${step.angle_deg}°` }[step.orientation];
      return (
        `${step.material} · +${step.thickness.value} ${step.thickness.unit} · ${orientationLabel}` +
        (step.seed_materials && step.seed_materials.length ? ` · SAG sur ${step.seed_materials.join("/")}` : "")
      );
    },
    pyCode: (step) => {
      const parts = [
        `name=${pyStr(step.name)}`,
        `material=${pyStr(step.material)}`,
        `thickness=${pyLength(step.thickness)}`,
        `orientation=GrowthOrientation.${step.orientation}`,
      ];
      if (step.orientation === "semi_polar") parts.push(`angle_deg=${step.angle_deg}`);
      if (step.seed_materials && step.seed_materials.length) parts.push(`seed_materials=${pyList(step.seed_materials)}`);
      return `EpitaxialGrowth(${parts.join(", ")})`;
    },
  },

  flip: {
    label: "Retournement",
    color: "#6b5ca5",
    tint: "#efecf9",
    iconPath: '<path d="M7 7l5-4 5 4M12 3v9M7 17l5 4 5-4M12 21v-9"/>',
    campaignFields: [],
    pyClass: "Flip",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Retournement"></div>
      <div class="help">Retourne la structure pour travailler la face arrière (amincissement, via, contact). La face avant n'est plus directement exposée, mais elle reste atteignable : un amincissement ou une gravure de face arrière suffisamment profond la traverse légitimement (comme un via qui vient contacter un plot enterré) — ce n'est pas un bouclier qui la rend immunisée. Nécessite une surface avant plane sur toute la largeur (ex : une planarisation juste avant), comme pour un vrai collage sur support temporaire.</div>`,
    buildFromForm: (name) => ({ kind: "flip", name }),
    summary: () => "face avant ↔ face arrière",
    pyCode: (step) => `Flip(name=${pyStr(step.name)})`,
  },
};

const STEP_KINDS = Object.fromEntries(
  Object.entries(STEP_KIND_DEFS).map(([kind, def]) => [kind, { label: def.label, icon: kind, color: def.color, tint: def.tint }])
);
const CAMPAIGN_FIELD_OPTIONS = Object.fromEntries(Object.entries(STEP_KIND_DEFS).map(([kind, def]) => [kind, def.campaignFields || []]));
const PY_STEP_CLASS = Object.fromEntries(Object.entries(STEP_KIND_DEFS).map(([kind, def]) => [kind, def.pyClass]));

function stepIconHtml(kind) {
  const def = STEP_KIND_DEFS[kind];
  return `
    <div class="step-icon" style="background:${def.tint};color:${def.color};">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${def.iconPath}</svg>
    </div>`;
}

function renderKindFields(kind) {
  const container = document.getElementById("kind-fields");
  const def = STEP_KIND_DEFS[kind];
  container.innerHTML = def.renderFields();
  if (def.wire) def.wire();
}

function buildStepFromForm() {
  const kind = document.getElementById("kind-select").value;
  const def = STEP_KIND_DEFS[kind];
  const name = document.getElementById("f-name").value || def.label;
  return def.buildFromForm(name);
}

function stepSummary(step) {
  return STEP_KIND_DEFS[step.kind].summary(step);
}

function pyStepCode(step) {
  return STEP_KIND_DEFS[step.kind].pyCode(step);
}
