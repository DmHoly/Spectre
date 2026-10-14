/* Ce qu'il faut pour faire le rapport d'un procédé, quelle que soit la page qui le demande (le
   constructeur, la fiche d'une étude) : lire les paramètres d'une étape, composer les données de
   report-html.js à partir d'un procédé, de ses images simulées et de ses commentaires, et télécharger
   le document.

   Rien ici ne lit la page ni le serveur - sauf `loadLogo` et `download`, les deux seuls gestes du
   navigateur. Les paramètres d'une étape se lisent sur l'étape elle-même (ses champs, tels que
   StructureForge les enregistre et que le constructeur les envoie) : un type d'étape de plus
   n'a pas à être déclaré ici pour apparaître, il s'affiche sous le nom de son champ. */

const StepReportCore = (() => {
  // Le nom, la couleur et la teinte de chaque type d'étape - ceux des puces du process flow
  // (structures/static/builder/step-kinds.js, STEP_KIND_DEFS : à tenir ensemble).
  const KINDS = {
    deposition: { label: "Dépôt", color: "#1d6fae", tint: "#e8f1fa" },
    etch: { label: "Gravure", color: "#a45a3a", tint: "#f6ede7" },
    planarization: { label: "Planarisation", color: "#5c655e", tint: "#ede9df" },
    lithography: { label: "Lithographie", color: "#7a4a97", tint: "#f2e9f7" },
    chemical: { label: "Étape chimique", color: "#3f7d4a", tint: "#e9f4ea" },
    resist_strip: { label: "Retrait de résine", color: "#a45a3a", tint: "#f6ede7" },
    faceted_growth: { label: "Croissance facettée", color: "#b8860b", tint: "#faf3df" },
    facet_envelope: { label: "Rattrapage des plans", color: "#9a6b12", tint: "#f7efdc" },
    epitaxial_growth: { label: "Croissance épitaxiale", color: "#2e8b57", tint: "#e6f4ec" },
    flip: { label: "Retournement", color: "#6b5ca5", tint: "#efecf9" },
  };

  const LABELS = {
    thickness: "Épaisseur",
    depth: "Profondeur",
    target_level: "Niveau cible",
    domain_width: "Largeur du domaine",
    rate_c: "Vitesse plan C",
    rate_m: "Vitesse plan M",
    rate_sp: "Vitesse semipolaire",
    rate_sp_inv: "Vitesse semipolaire inversée",
    semi_polar_angle_deg: "Angle semipolaire",
    top_level: "Niveau de troncature",
    angle_deg: "Angle",
    material: "Matériau",
    material_c: "Matériau plan C",
    material_m: "Matériau plan M",
    material_sp: "Matériau semipolaire",
    material_sp_inv: "Matériau semipolaire inversé",
    resist_material: "Résine",
    stop_material: "Matériau d'arrêt",
    recipe: "Recette",
    orientation: "Orientation",
    description: "Description",
    seed_materials: "Matériaux d'amorçage",
  };
  const UNITS = { semi_polar_angle_deg: "°", angle_deg: "°", rate_c: "× réf.", rate_m: "× réf.", rate_sp: "× réf.", rate_sp_inv: "× réf." };
  const ORIENTATIONS = { c_plane: "Plan C [0001]", m_plane: "Plan M {10-10}", semi_polar: "Semi-polaire" };
  // comment une lithographie s'ancre au réseau de fils (structures/static/builder/substrate.js, LATTICE_OPENING_MODES)
  const LATTICE_MODES = {
    wires: { label: "Sur chaque fil (un trou par fil)", size: "diameter", sizeLabel: "Diamètre d'ouverture" },
    between: { label: "Entre les fils", size: "width", sizeLabel: "Largeur entre les fils" },
    pixel: { label: "Pixel entier (avec marge)", size: "margin", sizeLabel: "Marge du pixel" },
  };
  // ce qui n'est pas un paramètre de l'étape : son identité, sa brique, sa trace de préset, ses ajouts de la page
  const NOT_PARAMS = new Set([
    "id", "kind", "name", "declaredParams", "layerLabel", "ownRecipe", "presetOrigin", "parameters", "openings", "lattice_opening",
    "brick_group_id", "brick_name", "brick_source", "brick_role", "brick_version",
  ]);

  function kindInfo(kind) {
    return KINDS[kind] || { label: kind || "Étape", color: "#1b2440", tint: "#eceef2" };
  }

  function unitText(unit) {
    return unit === "um" ? "µm" : unit === "A" ? "Å" : unit || "";
  }

  function prettyKey(key) {
    const text = key.replace(/_/g, " ");
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function isLength(value) {
    return value && typeof value === "object" && "value" in value && "unit" in value;
  }

  function lengthText(value) {
    return `${value.value} ${unitText(value.unit)}`.trim();
  }

  // Le texte d'une valeur de champ - null quand elle n'a rien à dire (vide, objet inconnu).
  function valueText(key, value) {
    if (value === null || value === undefined || value === "") return null;
    if (isLength(value)) return lengthText(value);
    if (typeof value === "number") return `${value}${UNITS[key] ? ` ${UNITS[key]}` : ""}`;
    if (typeof value === "boolean") return value ? "oui" : "non";
    if (typeof value === "string") return key === "orientation" ? ORIENTATIONS[value] || value : value;
    if (Array.isArray(value)) return value.length && value.every((item) => typeof item === "string" || typeof item === "number") ? value.join(", ") : null;
    return null;
  }

  function openingsText(openings) {
    const shown = openings.slice(0, 4).map((pair) => `${pair[0]}–${pair[1]}`).join(", ");
    return `${openings.length} (${shown}${openings.length > 4 ? ", …" : ""} nm)`;
  }

  // Les lignes « paramètre : valeur » d'une étape : ses champs (dans leur ordre), puis ses paramètres
  // déclarés (`declared` : [{name, value, unit, obtention}]), marqués. [{label, value, declared, detail}]
  function stepRows(step, declared) {
    const rows = [];
    Object.keys(step).forEach((key) => {
      if (NOT_PARAMS.has(key) || (key === "angle_deg" && step.orientation !== "semi_polar")) return;
      const text = valueText(key, step[key]);
      if (text !== null) rows.push({ label: LABELS[key] || prettyKey(key), value: text, declared: false });
    });
    if (step.lattice_opening) {
      const mode = LATTICE_MODES[step.lattice_opening.mode || "wires"] || LATTICE_MODES.wires;
      rows.push({ label: "Ouvertures", value: mode.label, declared: false });
      if (typeof step.lattice_opening[mode.size] === "number") rows.push({ label: mode.sizeLabel, value: `${step.lattice_opening[mode.size]} nm`, declared: false });
    } else if (Array.isArray(step.openings) && step.openings.length) {
      rows.push({ label: "Ouvertures", value: openingsText(step.openings), declared: false });
    }
    (declared || []).forEach((p) => {
      if (!p || !p.name) return;
      const detail = Object.entries(p.obtention || {})
        .filter(([key, value]) => value !== "" && value != null && !["unit", "unité", "unite"].includes(key))
        .map(([key, value]) => `${key} : ${value}`)
        .join(" · ");
      const unit = p.unit || (p.obtention && (p.obtention.unit || p.obtention["unité"] || p.obtention.unite)) || "";
      rows.push({ label: p.name, value: `${p.value}${unit ? ` ${unit}` : ""}`, declared: true, detail });
    });
    return rows;
  }

  function substrateRows(substrate) {
    const rows = [
      { label: "Matériau", value: substrate.material },
      { label: "Largeur du domaine", value: lengthText(substrate.domain_width) },
      { label: "Épaisseur", value: lengthText(substrate.thickness) },
    ];
    if (substrate.lattice) rows.push({ label: "Réseau de fils", value: `${substrate.lattice.wires} fil${substrate.lattice.wires > 1 ? "s" : ""} · pas ${substrate.lattice.pitch} nm` });
    return rows.map((row) => ({ ...row, declared: false }));
  }

  // Le résumé d'une étape, sous son titre : ses trois premiers paramètres.
  function summaryOf(rows) {
    return rows.filter((row) => !row.declared).slice(0, 3).map((row) => row.value).join(" · ");
  }

  function legendOf(frame, colors) {
    return (frame ? frame.materials : []).map((name) => ({ name, color: colors[name] || "#c3c8d4" }));
  }

  // Marque dans le dessin les couches que produit l'étape `stepIndex` (leur classe sbr-new) : celles
  // dont le serveur a noté l'étape d'origine (`step_index` de chaque couche de l'image).
  function withNewLayers(svg, frame, stepIndex) {
    const origin = (frame.layers || []).map((layer) => (layer.step_index == null ? null : layer.step_index));
    return svg.replace(/data-layer-index="(\d+)"/g, (match, layer) => (origin[parseInt(layer, 10)] === stepIndex ? `${match} class="sbr-new"` : match));
  }

  // Les données de report-html.js.
  //   title, subtitle, logoSvg
  //   substrate : {material, domain_width, thickness, lattice?}
  //   steps     : [{step, declared}] - `step.id` l'id de l'étape, `declared` ses paramètres déclarés
  //   frames    : les images de la simulation (frames[0] : le substrat seul, frames[k + 1] : après l'étape k)
  //   colors    : la couleur de chaque matériau
  //   comments  : {id d'étape: texte}, ou null quand les commentaires n'ont pas de sens ici
  function buildReport({ title, subtitle, logoSvg, substrate, steps, frames, colors, comments }) {
    const last = frames.length - 1;
    const reported = steps.map(({ step, declared }, i) => {
      const info = kindInfo(step.kind);
      const rows = stepRows(step, declared);
      const tags = [];
      if (step.brick_name) tags.push(`Brique : ${step.brick_name}`);
      if (step.presetOrigin) tags.push(`Préset : ${step.presetOrigin.name}`);
      return {
        index: i + 1,
        kind: step.kind,
        kindLabel: info.label,
        color: info.color,
        tint: info.tint,
        name: step.name,
        summary: summaryOf(rows),
        tags,
        svg: withNewLayers(frames[i + 1].svg, frames[i + 1], i),
        materials: legendOf(frames[i + 1], colors),
        params: rows,
        comment: comments && step.id ? comments[step.id] || "" : "",
      };
    });
    const commented = reported.filter((s) => s.comment.trim()).length;
    return {
      logoSvg,
      title,
      subtitle,
      date: new Date().toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }),
      cover: {
        svg: frames[last].svg,
        materials: legendOf(frames[last], colors),
        stats: [
          { label: reported.length > 1 ? "étapes" : "étape", value: String(reported.length) },
          { label: "matériaux", value: String(frames[last].materials.length) },
          ...(comments ? [{ label: commented > 1 ? "étapes commentées" : "étape commentée", value: String(commented) }] : []),
        ],
      },
      start: { svg: frames[0].svg, materials: legendOf(frames[0], colors), params: substrateRows(substrate) },
      steps: reported,
    };
  }

  // Le logo Aledia du noyau, lu une fois (le rapport l'embarque : il n'a rien à charger) ; sans lui, le rapport n'a pas de logo.
  let logoPromise = null;
  function loadLogo() {
    if (!logoPromise) {
      logoPromise = fetch("/static/kernel/img/aledia-logo.svg")
        .then((response) => (response.ok ? response.text() : ""))
        .catch(() => "");
    }
    return logoPromise;
  }

  function fileName(title) {
    const base = title.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
    return `rapport-${base || "structure"}.html`;
  }

  // Télécharge le rapport (les données de buildReport) comme un fichier HTML.
  function download(report) {
    const blob = new Blob([StepReportHtml.build(report)], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = fileName(report.title);
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  return { kindInfo, stepRows, substrateRows, buildReport, loadLogo, download, fileName };
})();
