/* Zones (sous-pixels) : une lithographie en sous-pixels (step.lattice_opening.mode "zones") découpe le
   domaine en zones. Une étape d'après peut s'y régler zone par zone : `step.zone_overrides =
   {"<zone>": {champ: valeur}}` ne garde que ce que la zone a de propre, le reste est commun - le serveur
   simule chaque zone seule, avec ses valeurs, puis recolle (spectre.plugins.structures.simulation,
   _simulate_zoned). Sur le dessin, un carré en pointillé par zone ; dans le formulaire d'une étape, un
   sélecteur « Toutes les zones / Zone 1 / ... » : « Toutes » règle les valeurs communes, une zone règle
   ses valeurs propres (ce qui diffère du commun), et revenir à la valeur commune la retire. */

// la zone ouverte dans le formulaire et sur le dessin ; null : les valeurs communes
state.selectedZone = null;

// Ce que le formulaire d'une étape règle d'elle seule, jamais par zone : son identité, ses ajouts de la
// page (commentaire, paramètres déclarés, étiquette, recette propre, trace de préset, brique).
const ZONE_COMMON_KEYS = new Set([
  "id", "kind", "name", "comment", "declaredParams", "layerLabel", "ownRecipe", "presetOrigin", "zone_overrides", "lattice_opening",
  "brick_group_id", "brick_name", "brick_source", "brick_version",
]);

// La zone dont le formulaire de l'étape `index` règle les valeurs, ou null (valeurs communes) : il faut une
// lithographie en sous-pixels avant l'étape, et une zone choisie qui existe.
function activeZone(index = state.selectedIndex) {
  const anchor = zonesAnchor();
  if (!anchor || index <= anchor.index || state.selectedZone == null) return null;
  return state.selectedZone < anchor.windows.length ? state.selectedZone : null;
}

// L'étape telle que la zone la voit : ses valeurs communes, recouvertes de celles qu'elle a en propre.
function stepInZone(step, zone) {
  if (zone == null || !step.zone_overrides || !step.zone_overrides[zone]) return step;
  return { ...step, ...JSON.parse(JSON.stringify(step.zone_overrides[zone])) };
}

function sameValue(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

// L'étape que lit le formulaire quand il règle la zone `zone` de l'étape `common` : ses valeurs communes
// ne bougent pas, et ce que la zone en diffère devient ses valeurs propres (aucune différence : la zone
// reprend le commun). Son nom et ses ajouts de la page se règlent pour toutes.
function stepWithZoneValues(built, common, zone) {
  const merged = { ...built };
  const overrides = { ...(common.zone_overrides || {}) };
  const own = {};
  new Set([...Object.keys(built), ...Object.keys(common)]).forEach((key) => {
    if (ZONE_COMMON_KEYS.has(key)) return;
    if (sameValue(built[key], common[key])) return;
    if (built[key] !== undefined) own[key] = built[key];
    if (common[key] !== undefined) merged[key] = common[key];
    else delete merged[key];
  });
  if (Object.keys(own).length) overrides[zone] = own;
  else delete overrides[zone];
  if (Object.keys(overrides).length) merged.zone_overrides = overrides;
  else delete merged.zone_overrides;
  return merged;
}

// Les champs que chaque zone règle à sa façon sur cette étape, pour l'écrire sous le sélecteur.
function zoneOwnSummary(step, fieldLabel) {
  const overrides = step.zone_overrides || {};
  return Object.keys(overrides)
    .sort((a, b) => a - b)
    .map((zone) => `zone ${Number(zone) + 1} : ${Object.keys(overrides[zone]).map(fieldLabel).join(", ")}`)
    .join(" · ");
}

// Le sélecteur de zone en tête du formulaire d'une étape d'après la lithographie en sous-pixels.
function zoneSelectorHtml(index) {
  const anchor = zonesAnchor();
  if (!anchor || index <= anchor.index) return "";
  const zone = activeZone(index);
  const step = state.steps[index] || {};
  const buttons = [`<button type="button" class="sb-zone-pick${zone == null ? " is-active" : ""}" data-zone="">Toutes</button>`]
    .concat(anchor.windows.map((_w, z) => `<button type="button" class="sb-zone-pick${zone === z ? " is-active" : ""}${step.zone_overrides && step.zone_overrides[z] ? " has-own" : ""}" data-zone="${z}">Zone ${z + 1}</button>`))
    .join("");
  const own = zoneOwnSummary(step, (key) => PARAM_FIELD_LABELS[key] || key);
  const help = zone == null
    ? "Les valeurs ci-dessous valent pour toutes les zones, sauf celles qu'une zone règle en propre."
    : `Vous réglez la zone ${zone + 1} : ce qui diffère des valeurs communes lui devient propre ; remettre la valeur commune la lui retire.`;
  return `
    <div class="sb-zone-selector" id="zone-selector">
      <label>Zones du pixel</label>
      <div class="sb-zone-selector__picks" role="group" aria-label="Zone réglée">${buttons}</div>
      <div class="help">${help}${own ? ` <strong>Valeurs propres : ${escapeHtml(own)}.</strong>` : ""}</div>
    </div>`;
}

function selectZone(zone) {
  state.selectedZone = zone;
  drawZoneOverlay();
  if (state.selectedIndex >= 0 && state.steps[state.selectedIndex] && typeof renderInspector === "function") renderInspector();
}

document.getElementById("step-form-section").addEventListener("click", (event) => {
  const pick = event.target.closest(".sb-zone-pick");
  if (!pick) return;
  selectZone(pick.dataset.zone === "" ? null : Number(pick.dataset.zone));
});

// -- les carrés en pointillé sur le dessin ---------------------------------------------------------------

const SVG_NS = "http://www.w3.org/2000/svg";

// Un carré en pointillé par zone sur l'image d'après la lithographie en sous-pixels : le dessin de
// StructureForge (le <svg> imbriqué quand l'image porte des étiquettes) a la géométrie pour viewBox, en nm,
// y retourné - le carré va d'un bord à l'autre de la zone, sur toute la hauteur de l'image. Un clic sur sa
// pastille ouvre la zone dans le formulaire de l'étape.
function drawZoneOverlay() {
  const container = document.getElementById("svg-container");
  container.querySelectorAll(".sb-zone-box").forEach((node) => node.remove());
  const anchor = zonesAnchor();
  if (!anchor || !state.frames || currentFrameIndex() <= anchor.index) return;
  const svg = container.querySelector("svg.sp-labelled-structure > svg") || container.querySelector("svg");
  const view = svg && svg.viewBox && svg.viewBox.baseVal;
  if (!view || !(view.width > 0)) return;
  const chip = Math.max(view.width, view.height) * 0.028; // la pastille, en nm de dessin
  const selected = activeZone(Math.max(state.selectedIndex, anchor.index + 1));
  const group = document.createElementNS(SVG_NS, "g");
  group.setAttribute("class", "sb-zone-box");
  anchor.windows.forEach(([start, end], zone) => {
    const left = Math.max(start, view.x);
    const right = Math.min(end, view.x + view.width);
    if (!(right > left)) return;
    const box = document.createElementNS(SVG_NS, "g");
    box.setAttribute("class", `sb-zone${selected === zone ? " is-selected" : ""}`);
    box.dataset.zone = String(zone);
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", String(left));
    rect.setAttribute("y", String(view.y));
    rect.setAttribute("width", String(right - left));
    rect.setAttribute("height", String(view.height));
    rect.setAttribute("class", "sb-zone__frame");
    const tab = document.createElementNS(SVG_NS, "rect");
    tab.setAttribute("x", String(left + chip * 0.2));
    tab.setAttribute("y", String(view.y + chip * 0.2));
    tab.setAttribute("width", String(chip * 2.6));
    tab.setAttribute("height", String(chip * 1.2));
    tab.setAttribute("rx", String(chip * 0.25));
    tab.setAttribute("class", "sb-zone__tab");
    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", String(left + chip * 1.5));
    label.setAttribute("y", String(view.y + chip * 1.0));
    label.setAttribute("font-size", String(chip * 0.8));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "sb-zone__label");
    label.textContent = `Zone ${zone + 1}`;
    tab.addEventListener("click", (event) => {
      event.stopPropagation();
      selectZone(selected === zone ? null : zone);
    });
    label.addEventListener("click", (event) => {
      event.stopPropagation();
      selectZone(selected === zone ? null : zone);
    });
    box.append(rect, tab, label);
    group.append(box);
  });
  svg.append(group);
}
