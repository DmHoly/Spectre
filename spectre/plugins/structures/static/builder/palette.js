/* Palette d'outils (colonne de gauche de l'atelier) : un bouton par type d'étape, groupés par
   famille de procédé, et la liste des briques technologiques disponibles. Clic = insérer après
   l'étape sélectionnée ; glisser = insérer où l'on veut dans le process flow (voir step-list.js).
   Aussi le petit menu d'insertion ouvert par les « + » du flow. */

const TOOL_GROUPS = [
  { title: "Ajout de matière", kinds: ["deposition", "epitaxial_growth", "faceted_growth", "facet_envelope"] },
  { title: "Motif & retrait", kinds: ["lithography", "etch", "resist_strip", "planarization"] },
  { title: "Autres", kinds: ["chemical", "flip"] },
];
const TOOL_ORDER = TOOL_GROUPS.flatMap((g) => g.kinds); // aussi l'ordre des raccourcis 1-9 (les neuf premiers)
const TOOL_HINTS = {
  epitaxial_growth: "SAG, nanofils",
  faceted_growth: "pointe crayon / pyramide",
  facet_envelope: "forme facettée imposée",
  flip: "face arrière",
};

function toolIconHtml(kind, size = 15) {
  const def = STEP_KIND_DEFS[kind];
  return `<span class="sb-tool__icon" style="--kind:${def.color};--kind-tint:${def.tint};" aria-hidden="true"><svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">${def.iconPath}</svg></span>`;
}

function renderPaletteTools() {
  document.getElementById("palette-tools").innerHTML = TOOL_GROUPS.map(
    (group) => `
      <div class="sb-palette__group">
        <div class="sb-palette__group-title">${escapeHtml(group.title)}</div>
        ${group.kinds
          .map((kind) => {
            const def = STEP_KIND_DEFS[kind];
            const key = TOOL_ORDER.indexOf(kind) + 1;
            const hint = TOOL_HINTS[kind] ? ` (${TOOL_HINTS[kind]})` : "";
            return `
              <button class="sb-tool" type="button" draggable="true" data-kind="${kind}" title="${escapeHtml(def.label + hint)} - clic : insérer après la sélection · glisser : dans le flow${key <= 9 ? ` · touche ${key}` : ""}">
                ${toolIconHtml(kind)}
                <span class="sb-tool__label">${escapeHtml(def.label)}</span>
                ${key <= 9 ? `<kbd class="sb-tool__key">${key}</kbd>` : ""}
              </button>`;
          })
          .join("")}
      </div>`
  ).join("");
}

const paletteTools = document.getElementById("palette-tools");
paletteTools.addEventListener("click", (event) => {
  const tool = event.target.closest(".sb-tool");
  if (tool) insertStepOfKind(tool.dataset.kind);
});
paletteTools.addEventListener("dragstart", (event) => {
  const tool = event.target.closest(".sb-tool");
  if (tool) startFlowDrag(event, { type: "kind", kind: tool.dataset.kind });
});

// -- briques ------------------------------------------------------------------------------------

const BRICK_SCOPE_LABELS = { builtin: "intégrée", shared: "partagée", microproject: "µprojet", reference: "référence" };

// Une structure complète est aussi une brique du constructeur, sous son nom, sans rien créer :
// chaque structure de la bibliothèque (`structure:<id>`) et la dernière version de chaque
// référence (`reference:<slug>@<numéro>`). Insérée, elle copie ses étapes en un seul groupe (ses
// briques internes aplaties) et, dans une structure vide, apporte son substrat ; sa copie garde la
// source, comme une brique (brick-origin.js). Une version de référence n'est lue qu'au moment de
// l'insérer (`pending` : son procédé vient de referencesApi.version, gardé dans state.referenceBricks).
const STRUCTURE_SOURCE_PREFIX = "structure:";
const REFERENCE_SOURCE_PREFIX = "reference:";

function withStepExtras(b) {
  // paramètres déclarés et étiquettes rattachés à leurs étapes : une brique insérée garde son dopage & co
  return { ...b, steps: attachLatticeOpenings(attachPresetOrigins(attachRecipes(attachLayerLabels(attachDeclaredParams(b.steps || [], b.declared_params), b.layer_labels), b.recipes), b.preset_origins), b.lattice_openings) };
}

function structureBrick(structure) {
  return {
    id: STRUCTURE_SOURCE_PREFIX + structure.id,
    name: structure.name,
    virtual: "structure",
    scope: structure.scope,
    can_edit: false,
    notes: null,
    version: null,
    substrate: structure.substrate,
    steps: structure.steps,
    declared_params: structure.declared_params,
    layer_labels: structure.layer_labels,
    recipes: structure.recipes,
    preset_origins: structure.preset_origins,
    lattice_openings: structure.lattice_openings,
    bricks: [],
  };
}

function referenceBrickId(slug, number) {
  return `${REFERENCE_SOURCE_PREFIX}${slug}@${number}`;
}

// La dernière version d'une référence, pas encore lue : juste de quoi la lister et la demander.
function referenceBrickStub(ref) {
  const latest = ref.latest_version;
  return { id: referenceBrickId(ref.slug, latest.number), name: `${ref.name} ${latest.number}`, virtual: "reference", pending: true, reference_slug: ref.slug, reference_name: ref.name, number: latest.number, version: latest.number, scope: "reference", can_edit: false, notes: null, steps: [], substrate: null };
}

function latestReferenceNumber(slug, fallback) {
  const ref = state.references.find((r) => r.slug === slug);
  return ref && ref.latest_version ? ref.latest_version.number : fallback;
}

// La version de référence `id` (`reference:<slug>@<numéro>`) comme brique, lue une fois.
async function loadReferenceBrick(id) {
  if (state.referenceBricks[id]) return state.referenceBricks[id];
  const [slug, number] = id.slice(REFERENCE_SOURCE_PREFIX.length).split("@");
  const version = await referencesApi.version(slug, number);
  const data = version.process || { substrate: null, steps: [] };
  const brick = {
    id,
    name: `${version.reference.name} ${number}`,
    virtual: "reference",
    reference_slug: slug,
    reference_name: version.reference.name,
    number,
    version: latestReferenceNumber(slug, number), // la dernière : la copie d'une autre se sait en retard
    scope: "reference",
    can_edit: false,
    notes: version.note || null,
    substrate: data.substrate,
    steps: data.steps,
    declared_params: data.declared_params,
    layer_labels: data.layer_labels,
    recipes: data.recipes,
    preset_origins: data.preset_origins,
    lattice_openings: data.lattice_openings,
    bricks: [],
  };
  state.referenceBricks[id] = brick;
  return brick;
}

// Les versions de référence copiées dans la structure chargée, lues en arrière-plan : l'inspecteur
// pourra dire si chaque copie leur est restée conforme.
function prefetchReferenceBricks() {
  const ids = new Set(state.steps.map((s) => s.brick_source).filter((id) => id && id.startsWith(REFERENCE_SOURCE_PREFIX) && !state.referenceBricks[id]));
  ids.forEach((id) =>
    loadReferenceBrick(id)
      .then(() => {
        if (state.selectedBrickGroup) renderInspector();
      })
      .catch(() => {
        /* une version retirée : la copie se dira « introuvable » */
      })
  );
}

function allTechBricks() {
  const references = state.references.filter((r) => r.latest_version).map((r) => state.referenceBricks[referenceBrickId(r.slug, r.latest_version.number)] || referenceBrickStub(r));
  return [...state.techBricks, ...state.savedStructures.map(structureBrick), ...references].map(withStepExtras);
}

function findBrickEntry(id) {
  const found = allTechBricks().find((b) => b.id === id);
  if (found) return found;
  // une version de référence qui n'est plus la dernière : lue si on l'a déjà demandée, sinon demandée
  if (id && id.startsWith(REFERENCE_SOURCE_PREFIX)) {
    if (state.referenceBricks[id]) return withStepExtras(state.referenceBricks[id]);
    const [slug, number] = id.slice(REFERENCE_SOURCE_PREFIX.length).split("@");
    const ref = state.references.find((r) => r.slug === slug);
    if (!ref || !ref.latest_version) return null;
    loadReferenceBrick(id).then(() => state.selectedBrickGroup && renderInspector()).catch(() => {});
    return { ...referenceBrickStub(ref), id, number, name: `${ref.name} ${number}` };
  }
  return null;
}

function brickToolHtml(b) {
  const meta =
    b.virtual === "structure"
      ? `structure · ${b.steps.length} étape${b.steps.length > 1 ? "s" : ""} · ${BRICK_SCOPE_LABELS[b.scope] || b.scope}`
      : b.virtual === "reference"
        ? `version de référence${b.pending ? "" : ` · ${b.steps.length} étape${b.steps.length > 1 ? "s" : ""}`}`
        : `${b.reference ? "Réf. · " : ""}${b.substrate ? "départ · " : ""}v${escapeHtml(b.version || "1.0")} · ${b.steps.length} étape${b.steps.length > 1 ? "s" : ""} · ${BRICK_SCOPE_LABELS[b.scope] || b.scope}`;
  const what = b.virtual === "structure" ? "La structure entière, en une brique" : b.virtual === "reference" ? "La dernière version de la référence, en une brique" : `${b.steps.length} étape(s)`;
  return `
      <button class="sb-brick-tool" type="button" draggable="true" data-id="${escapeHtml(b.id)}"
              title="${escapeHtml(b.name)}${b.notes ? ` - ${escapeHtml(b.notes)}` : ""}&#10;${escapeHtml(what)} · clic : insérer après la sélection · glisser : dans le flow">
        <span class="sb-brick-tool__name">${escapeHtml(b.name)}</span>
        <span class="sb-brick-tool__meta">${meta}</span>
      </button>`;
}

function renderBrickList() {
  const list = document.getElementById("insert-brick-list");
  const filter = document.getElementById("brick-search").value.trim().toLowerCase();
  const all = allTechBricks();
  document.getElementById("brick-search").hidden = all.length < 6;
  const shown = all.filter((b) => !filter || b.name.toLowerCase().includes(filter));
  if (all.length === 0) {
    list.innerHTML = `<div class="help">Aucune brique pour l'instant. Sélectionnez plusieurs étapes (Ctrl+clic) pour en créer une.</div>`;
    return;
  }
  if (shown.length === 0) {
    list.innerHTML = `<div class="help">Aucune brique ne correspond.</div>`;
    return;
  }
  const sections = [
    ["Briques", shown.filter((b) => !b.virtual)],
    ["Structures de la bibliothèque", shown.filter((b) => b.virtual === "structure")],
    ["Références (dernière version)", shown.filter((b) => b.virtual === "reference")],
  ].filter(([, items]) => items.length);
  list.innerHTML = sections
    .map(([title, items]) => `${sections.length > 1 ? `<div class="sb-palette__sub">${escapeHtml(title)}</div>` : ""}${items.map(brickToolHtml).join("")}`)
    .join("");
}

const brickList = document.getElementById("insert-brick-list");
brickList.addEventListener("click", (event) => {
  const btn = event.target.closest(".sb-brick-tool");
  if (btn) insertBrickAt(findBrickEntry(btn.dataset.id));
});
brickList.addEventListener("dragstart", (event) => {
  const btn = event.target.closest(".sb-brick-tool");
  const brick = btn && findBrickEntry(btn.dataset.id);
  if (brick) startFlowDrag(event, { type: "brick", brick });
});
document.getElementById("brick-search").addEventListener("input", renderBrickList);

// -- palette repliable (icônes seules) : mémorisée par navigateur -------------------------------

const PALETTE_COLLAPSED_KEY = "spectre.builder.paletteCollapsed";

function setPaletteCollapsed(collapsed) {
  document.getElementById("sb-shell").classList.toggle("is-palette-collapsed", collapsed);
  const btn = document.getElementById("palette-collapse-btn");
  btn.setAttribute("aria-expanded", String(!collapsed));
  btn.setAttribute("aria-label", collapsed ? "Déplier la palette d'outils" : "Replier la palette d'outils");
  btn.title = collapsed ? "Déplier la palette" : "Replier la palette";
  try {
    localStorage.setItem(PALETTE_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch (err) {
    /* stockage indisponible (navigation privée...) : simple confort perdu */
  }
}

document.getElementById("palette-collapse-btn").addEventListener("click", () => {
  setPaletteCollapsed(!document.getElementById("sb-shell").classList.contains("is-palette-collapsed"));
});

(function restorePaletteCollapsed() {
  let collapsed = false;
  try {
    collapsed = localStorage.getItem(PALETTE_COLLAPSED_KEY) === "1";
  } catch (err) {
    collapsed = false;
  }
  if (collapsed) setPaletteCollapsed(true);
})();

// -- menu d'insertion des « + » du flow -----------------------------------------------------------

const kindMenu = document.getElementById("kind-menu");
let kindMenuAnchor = null;

function openKindMenu(anchor, gap) {
  if (state.wizardScreen !== "structure") return;
  kindMenuAnchor = anchor;
  kindMenu.innerHTML =
    `<div class="sb-popover__title">Insérer ${gap === 0 ? "en tête" : gap >= state.steps.length ? "à la fin" : `après l'étape ${gap}`}</div>` +
    TOOL_ORDER.map(
      (kind, k) => `
        <button class="sb-kind-menu__item" type="button" role="menuitem" data-kind="${kind}" data-gap="${gap}">
          ${toolIconHtml(kind, 13)}<span>${escapeHtml(STEP_KIND_DEFS[kind].label)}</span>${k < 9 ? `<kbd>${k + 1}</kbd>` : ""}
        </button>`
    ).join("");
  kindMenu.hidden = false;
  const rect = anchor.getBoundingClientRect();
  const menuRect = kindMenu.getBoundingClientRect();
  const left = Math.min(Math.max(8, rect.left + rect.width / 2 - menuRect.width / 2), window.innerWidth - menuRect.width - 8);
  const top = rect.bottom + menuRect.height + 8 > window.innerHeight ? rect.top - menuRect.height - 6 : rect.bottom + 6;
  kindMenu.style.left = `${left}px`;
  kindMenu.style.top = `${Math.max(8, top)}px`;
  const first = kindMenu.querySelector(".sb-kind-menu__item");
  if (first) first.focus();
}

function closeKindMenu({ restoreFocus = false } = {}) {
  if (kindMenu.hidden) return false;
  kindMenu.hidden = true;
  if (restoreFocus && kindMenuAnchor && document.body.contains(kindMenuAnchor)) kindMenuAnchor.focus();
  kindMenuAnchor = null;
  return true;
}

kindMenu.addEventListener("click", (event) => {
  const item = event.target.closest(".sb-kind-menu__item");
  if (!item) return;
  closeKindMenu();
  insertStepOfKind(item.dataset.kind, parseInt(item.dataset.gap, 10));
});

kindMenu.addEventListener("keydown", (event) => {
  const items = [...kindMenu.querySelectorAll(".sb-kind-menu__item")];
  const current = items.indexOf(document.activeElement);
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const next = (current + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next].focus();
  } else if (/^[1-9]$/.test(event.key) && items[parseInt(event.key, 10) - 1]) {
    event.preventDefault();
    items[parseInt(event.key, 10) - 1].click();
  } else if (event.key === "Escape") {
    event.preventDefault();
    event.stopPropagation();
    closeKindMenu({ restoreFocus: true });
  }
});

document.addEventListener("mousedown", (event) => {
  if (!kindMenu.hidden && !kindMenu.contains(event.target) && !(kindMenuAnchor && kindMenuAnchor.contains(event.target))) closeKindMenu();
});
window.addEventListener("resize", () => closeKindMenu());
document.getElementById("steps-list").addEventListener("scroll", () => closeKindMenu());
