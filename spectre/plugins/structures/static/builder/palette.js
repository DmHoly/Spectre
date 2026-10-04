/* Palette d'outils (colonne de gauche de l'atelier) : un bouton par type d'étape, groupés par
   famille de procédé, et la liste des briques technologiques disponibles. Clic = insérer après
   l'étape sélectionnée ; glisser = insérer où l'on veut dans le process flow (voir step-list.js).
   Aussi le petit menu d'insertion ouvert par les « + » du flow. */

const TOOL_GROUPS = [
  { title: "Ajout de matière", kinds: ["deposition", "epitaxial_growth", "faceted_growth"] },
  { title: "Motif & retrait", kinds: ["lithography", "etch", "resist_strip", "planarization"] },
  { title: "Autres", kinds: ["chemical", "flip"] },
];
const TOOL_ORDER = TOOL_GROUPS.flatMap((g) => g.kinds); // aussi l'ordre des raccourcis 1-9
const TOOL_HINTS = {
  epitaxial_growth: "SAG, nanofils",
  faceted_growth: "pointe crayon / pyramide",
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
              <button class="sb-tool" type="button" draggable="true" data-kind="${kind}" title="${escapeHtml(def.label + hint)} - clic : insérer après la sélection · glisser : dans le flow · touche ${key}">
                ${toolIconHtml(kind)}
                <span class="sb-tool__label">${escapeHtml(def.label)}</span>
                <kbd class="sb-tool__key">${key}</kbd>
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

const BRICK_SCOPE_LABELS = { builtin: "intégrée", shared: "partagée", microproject: "µprojet" };

function allTechBricks() {
  // paramètres déclarés rattachés à leurs étapes : une brique insérée garde son dopage & co
  return state.techBricks.map((b) => ({ ...b, steps: attachDeclaredParams(b.steps, b.declared_params) }));
}

function findBrickEntry(id) {
  return allTechBricks().find((b) => b.id === id) || null;
}

function renderBrickList() {
  const list = document.getElementById("insert-brick-list");
  const filter = document.getElementById("brick-search").value.trim().toLowerCase();
  const bricks = allTechBricks();
  document.getElementById("brick-search").hidden = bricks.length < 6;
  const shown = bricks.filter((b) => !filter || b.name.toLowerCase().includes(filter));
  if (bricks.length === 0) {
    list.innerHTML = `<div class="help">Aucune brique pour l'instant. Sélectionnez plusieurs étapes (Ctrl+clic) pour en créer une.</div>`;
    return;
  }
  if (shown.length === 0) {
    list.innerHTML = `<div class="help">Aucune brique ne correspond.</div>`;
    return;
  }
  list.innerHTML = shown
    .map(
      (b) => `
      <button class="sb-brick-tool" type="button" draggable="true" data-id="${escapeHtml(b.id)}"
              title="${escapeHtml(b.name)}${b.notes ? ` - ${escapeHtml(b.notes)}` : ""}&#10;${b.steps.length} étape(s) · clic : insérer après la sélection · glisser : dans le flow">
        <span class="sb-brick-tool__name">${escapeHtml(b.name)}</span>
        <span class="sb-brick-tool__meta">${b.steps.length} étape${b.steps.length > 1 ? "s" : ""} · ${BRICK_SCOPE_LABELS[b.scope] || b.scope}</span>
      </button>`
    )
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
          ${toolIconHtml(kind, 13)}<span>${escapeHtml(STEP_KIND_DEFS[kind].label)}</span><kbd>${k + 1}</kbd>
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
