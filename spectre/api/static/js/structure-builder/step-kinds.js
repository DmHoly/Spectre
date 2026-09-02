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
      </details>`,
    wire: () => {
      wireDepositionAdvanced();
      wireModeAngleToggle("deposition");
    },
    buildFromForm: (name) => ({
      kind: "deposition",
      name,
      material: document.getElementById("f-material").value,
      mode: document.getElementById("f-mode").value,
      angle_deg: parseFloat(document.getElementById("f-angle").value) || 0,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
      process_parameters: currentProcessParameters(),
      derived_estimates: currentDerivedEstimates(),
    }),
    fillFields: (step) => {
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
    },
    summary: (step) => `${step.material} · ${step.thickness.value} ${step.thickness.unit} · ${modeSummary(step.mode, step.angle_deg)}`,
    pyCode: (step) => {
      const name = pyStr(step.name);
      const parts = [`name=${name}`, `material=${pyStr(step.material)}`, `mode=DepositionMode.${step.mode}`];
      if (step.angle_deg) parts.push(`angle_deg=${step.angle_deg}`);
      parts.push(`thickness=${pyLength(step.thickness)}`);
      if (step.process_parameters && Object.keys(step.process_parameters).length) parts.push(`process_parameters=${pyDict(step.process_parameters)}`);
      return `Deposition(${parts.join(", ")})`;
    },
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
      <div><label>Unité</label><select class="field" id="f-depth-unit"><option value="nm" selected>nm</option><option value="um">µm</option><option value="A">Å</option></select></div></div>`,
    wire: () => {
      document.getElementById("f-add-selectivity-btn").addEventListener("click", () => addSelectivityRow());
      wireModeAngleToggle("etch");
    },
    buildFromForm: (name) => ({
      kind: "etch",
      name,
      mode: document.getElementById("f-mode").value,
      angle_deg: parseFloat(document.getElementById("f-angle").value) || 0,
      default_factor: parseFloat(document.getElementById("f-default-factor").value) || 1.0,
      selectivity_by_material: currentSelectivityByMaterial(),
      depth: { value: parseFloat(document.getElementById("f-depth").value) || 0, unit: document.getElementById("f-depth-unit").value },
    }),
    fillFields: (step) => {
      document.getElementById("f-mode").value = step.mode;
      document.getElementById("f-angle").value = step.angle_deg || 0;
      document.getElementById("f-angle-wrap").style.display = step.mode === "directional" ? "" : "none";
      document.getElementById("f-default-factor").value = step.default_factor != null ? step.default_factor : 1.0;
      Object.entries(step.selectivity_by_material || {}).forEach(([material, factor]) => addSelectivityRow(material, factor));
      document.getElementById("f-depth").value = step.depth.value;
      document.getElementById("f-depth-unit").value = step.depth.unit;
    },
    summary: (step) => `${modeSummary(step.mode, step.angle_deg)} · ${step.depth.value} ${step.depth.unit}`,
    pyCode: (step) => {
      const name = pyStr(step.name);
      const parts = [`name=${name}`, `mode=EtchMode.${step.mode}`];
      if (step.angle_deg) parts.push(`angle_deg=${step.angle_deg}`);
      if (step.selectivity_by_material && Object.keys(step.selectivity_by_material).length) parts.push(`selectivity_by_material=${pyDict(step.selectivity_by_material)}`);
      if (step.default_factor != null && step.default_factor !== 1.0) parts.push(`default_factor=${step.default_factor}`);
      parts.push(`depth=${pyLength(step.depth)}`);
      return `Etch(${parts.join(", ")})`;
    },
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
      <div><label>Ouvertures (nm)</label><input class="field" id="f-openings" placeholder="ex : 80-140, 300-360"><div class="help">Zones où le masque est ouvert, séparées par des virgules.</div></div>`,
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

  semipolar_facet: {
    label: "Facette semipolaire",
    color: "#b8860b",
    tint: "#faf3df",
    iconPath: '<path d="M4 20L12 4L20 20Z"/>',
    campaignFields: [],
    pyClass: "SemipolarFacet",
    renderFields: () => `
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
      </div>`,
    buildFromForm: (name) => {
      const positionRaw = document.getElementById("f-position").value;
      return {
        kind: "semipolar_facet",
        name,
        orientation: document.getElementById("f-orientation").value,
        base_half_width: { value: parseFloat(document.getElementById("f-base-half-width").value) || 0, unit: document.getElementById("f-base-half-width-unit").value },
        tip_half_width: { value: parseFloat(document.getElementById("f-tip-half-width").value) || 0, unit: document.getElementById("f-tip-half-width-unit").value },
        facet_angle_deg: parseFloat(document.getElementById("f-facet-angle").value) || 60,
        position: positionRaw ? { value: parseFloat(positionRaw) || 0, unit: "nm" } : null,
      };
    },
    fillFields: (step) => {
      document.getElementById("f-orientation").value = step.orientation;
      document.getElementById("f-base-half-width").value = step.base_half_width.value;
      document.getElementById("f-base-half-width-unit").value = step.base_half_width.unit;
      document.getElementById("f-tip-half-width").value = step.tip_half_width.value;
      document.getElementById("f-tip-half-width-unit").value = step.tip_half_width.unit;
      document.getElementById("f-facet-angle").value = step.facet_angle_deg;
      document.getElementById("f-position").value = step.position != null ? step.position.value : "";
    },
    summary: (step) => {
      const orientationLabel = step.orientation === "notch" ? "creux (V-pit)" : "pointe (anti-V-pit)";
      return `${orientationLabel} · ${step.facet_angle_deg}° · base ${step.base_half_width.value} ${step.base_half_width.unit}`;
    },
    pyCode: (step) => {
      const parts = [
        `name=${pyStr(step.name)}`,
        `orientation=${pyStr(step.orientation)}`,
        `base_half_width=${pyLength(step.base_half_width)}`,
        `tip_half_width=${pyLength(step.tip_half_width)}`,
        `facet_angle_deg=${step.facet_angle_deg}`,
      ];
      if (step.position) parts.push(`position=${pyLength(step.position)}`);
      return `SemipolarFacet(${parts.join(", ")})`;
    },
  },

  selective_growth: {
    label: "Croissance sélective",
    color: "#2e8b57",
    tint: "#e6f4ec",
    iconPath: '<path d="M12 20V4M12 4l-5 5M12 4l5 5M6 14l6-4 6 4"/>',
    campaignFields: [],
    pyClass: "SelectiveGrowth",
    renderFields: () => `
      <div><label>Nom de l'étape</label><input class="field" id="f-name" value="Croissance sélective"></div>
      <div><label>Matériau</label><select class="field" id="f-material">${materialOptions()}</select>
        <div class="help" style="margin-top:4px;">La croissance ne reprend que sur ce matériau — ailleurs (substrat, masque...) rien ne pousse, comme un masque de croissance réel. Sans dépôt existant de ce matériau, la toute première couche pousse sur toute la surface exposée (à amorcer avec un dépôt classique avant, comme dans l'exemple de préset nanofil).</div>
      </div>
      <div class="field-row"><div><label>Épaisseur (plan C, le plus rapide)</label><input class="field" id="f-thickness" type="number" value="10"></div>
      <div><label>Unité</label><select class="field" id="f-thickness-unit"><option value="nm" selected>nm</option><option value="um">µm</option></select></div></div>
      <div><label>Vitesse relative — plan M (flancs verticaux)</label><input class="field" id="f-rate-m" type="number" value="0.4" step="0.01" min="0" max="1"></div>
      <div><label>Vitesse relative — facette semipolaire</label><input class="field" id="f-rate-sp" type="number" value="0.15" step="0.01" min="0" max="1"></div>
      <div class="help" id="f-rate-order-hint" style="margin-top:-6px;">Doit vérifier C (1.0) &gt; plan M &gt; semipolaire, sinon la facette la plus lente ne l'emporte jamais — c'est ce qui referme la pointe au fil des étapes.</div>`,
    wire: () => wireSelectiveGrowthRateCheck(),
    buildFromForm: (name) => ({
      kind: "selective_growth",
      name,
      material: document.getElementById("f-material").value,
      thickness: { value: parseFloat(document.getElementById("f-thickness").value) || 0, unit: document.getElementById("f-thickness-unit").value },
      rate_m: parseFloat(document.getElementById("f-rate-m").value),
      rate_sp: parseFloat(document.getElementById("f-rate-sp").value),
    }),
    fillFields: (step) => {
      document.getElementById("f-material").value = step.material;
      document.getElementById("f-thickness").value = step.thickness.value;
      document.getElementById("f-thickness-unit").value = step.thickness.unit;
      document.getElementById("f-rate-m").value = step.rate_m;
      document.getElementById("f-rate-sp").value = step.rate_sp;
    },
    summary: (step) => `${step.material} · +${step.thickness.value} ${step.thickness.unit} (C) · M×${step.rate_m} · SP×${step.rate_sp}`,
    pyCode: (step) => `SelectiveGrowth(name=${pyStr(step.name)}, material=${pyStr(step.material)}, thickness=${pyLength(step.thickness)}, rate_m=${step.rate_m}, rate_sp=${step.rate_sp})`,
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
