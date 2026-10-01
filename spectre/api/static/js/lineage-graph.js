/* Rendu partagé d'un graphe de filiation "git-like" (un nœud = une expérience structurellement
   distincte, voir GET /api/microprojets/{slug}/filiation) : le layout en couches et le dessin
   d'un nœud/trait, utilisés à la fois par microprojet-graphe.js (la vue par défaut d'un µprojet,
   pleine taille) et atlas.js (l'arbre miniature affiché au clic sur une étude, pour resituer son
   contexte sans quitter l'atlas). Tout est fonction pure (aucun accès au DOM ni à `state`) pour
   rester utilisable des deux côtés sans rien partager d'autre qu'un include - voir la note dans
   microprojet-graphe.js sur pourquoi ce n'est pas microprojet-graphe.js lui-même qui est réutilisé
   tel quel (conflits de noms avec les propres constantes d'atlas.js).
*/

// Code d'un nœud, par issue (experimentOutcome, common.js - la même clé que les badges) : jamais la
// couleur seule. Creux = pas encore terminée (brouillon : anneau gris ; en cours : anneau bleu + point
// central ; en pause : anneau ambre + ‖), plein = terminée ou reprise ailleurs, avec un pictogramme
// blanc qui dit l'issue (continuée : chevron vers la suite, en dessous dans le graphe). Avant,
// « à poursuivre » avait le bleu d'« en cours » et « non concluante » le brun d'« abandonnée ».
const LINEAGE_OUTCOME_STYLE = {
  draft: { color: "var(--draft)", filled: false, label: "Brouillon" },
  continued: { color: "var(--draft)", filled: true, glyph: "chevron", label: "Continuée" },
  running: { color: "var(--running)", filled: false, dot: true, label: "En cours" },
  hold: { color: "var(--hold)", filled: false, glyph: "pause", label: "En pause" },
  promote: { color: "var(--done)", filled: true, glyph: "check", label: "Concluante" },
  concluded: { color: "var(--done)", filled: true, label: "Conclue" },
  continue: { color: "var(--continue)", filled: true, glyph: "arrow", label: "À poursuivre" },
  inconclusive: { color: "var(--abandoned)", filled: true, glyph: "dash", label: "Non concluante" },
  abandoned: { color: "var(--abandoned)", filled: true, glyph: "cross", label: "Abandonnée" },
};
const LINEAGE_GLYPH_PATH = {
  check: "M-3.6,0.2 L-1.1,2.7 L3.7,-2.5",
  arrow: "M-3.3,0 L3.1,0 M0.5,-2.8 L3.3,0 L0.5,2.8",
  dash: "M-3.3,0 L3.3,0",
  cross: "M-2.7,-2.7 L2.7,2.7 M2.7,-2.7 L-2.7,2.7",
  chevron: "M-3.2,-1.5 L0,1.7 L3.2,-1.5",
  pause: "M-1.7,-2.9 L-1.7,2.9 M1.7,-2.9 L1.7,2.9",
};

function lineageOutcomeStyle({ status, decision }) {
  return LINEAGE_OUTCOME_STYLE[experimentOutcome(status, decision)] || LINEAGE_OUTCOME_STYLE.draft;
}

function lineageNodeColor(node) {
  return lineageOutcomeStyle(node).color;
}

// Début et fin d'une expérience, pour son temps écoulé (GET .../filiation : started_at, ended_at,
// continued_at) : conclue ou abandonnée -> sa conclusion ; brouillon continué par une version
// suivante -> le lancement de cette suite ; sinon pas terminée (fin = maintenant) - en pause compris.
function lineageSpan(node) {
  if (node.ended_at) return { start: node.started_at, end: node.ended_at, state: "ended" };
  if (node.continued_at && (node.status === "continued" || node.status === "draft")) {
    return { start: node.started_at, end: node.continued_at, state: "continued" };
  }
  return { start: node.started_at, end: null, state: node.status === "hold" ? "hold" : "ongoing" };
}

function lineageElapsedLabel(node) {
  const span = lineageSpan(node);
  return elapsedLabel(span.start, span.end);
}

// « 3 mars 2026 → 15 mars 2026 », « … → aujourd'hui », « … → 15 mars 2026 (continuée) ».
function lineageDatesLabel(node) {
  const span = lineageSpan(node);
  if (!span.start) return "";
  const end = span.end ? formatDate(span.end) : "aujourd'hui";
  return `${formatDate(span.start)} → ${end}${span.state === "continued" ? " (continuée)" : ""}`;
}

// « En pause depuis le 3 mars 2026 (2 sem.) · Bâti en maintenance » - vide si elle n'est pas en pause.
function lineageHoldLabel(node) {
  if (node.status !== "hold" || !node.hold || !node.hold.since) return "";
  const since = `En pause depuis le ${formatDate(node.hold.since)} (${formatDuration(new Date() - new Date(node.hold.since))})`;
  return node.hold.reason ? `${since} · ${node.hold.reason}` : since;
}

// Bulle native au survol d'un nœud : titre, issue, temps écoulé, dates, pause.
function lineageNodeTooltip(node) {
  const style = lineageOutcomeStyle(node);
  return [node.title, [style.label, lineageElapsedLabel(node)].filter(Boolean).join(" · "), lineageDatesLabel(node), lineageHoldLabel(node)]
    .filter(Boolean)
    .join("\n");
}

// Une rangée par profondeur (plus long chemin depuis une racine), les nœuds d'une même rangée
// ordonnés par barycentre itératif (descendant puis montant, plusieurs passes) pour limiter les
// croisements - une seule passe descendante ignorait complètement les enfants d'un nœud pour le
// positionner, ce qui laissait des branches se recroiser sans raison réelle. Toujours une
// heuristique (pas un vrai compte de croisements façon Sugiyama), mais nettement plus stable en
// pratique. `colWidth`/`rowHeight`/`margin` sont paramétrables pour un rendu miniature (atlas.js).
function lineageLayout(nodes, edges, { colWidth = 130, rowHeight = 100, margin = 40 } = {}) {
  const parentsOf = new Map(nodes.map((n) => [n.id, []]));
  const childrenOf = new Map(nodes.map((n) => [n.id, []]));
  edges.forEach((e) => {
    if (parentsOf.has(e.child)) parentsOf.get(e.child).push(e.parent);
    if (childrenOf.has(e.parent)) childrenOf.get(e.parent).push(e.child);
  });

  const depthOf = new Map();
  function depthOfNode(id) {
    if (depthOf.has(id)) return depthOf.get(id);
    depthOf.set(id, 0); // garde-fou anti-boucle - une filiation ne devrait jamais en avoir
    const parents = parentsOf.get(id) || [];
    const depth = parents.length ? Math.max(...parents.map(depthOfNode)) + 1 : 0;
    depthOf.set(id, depth);
    return depth;
  }
  nodes.forEach((n) => depthOfNode(n.id));

  const byId = new Map(nodes.map((n) => [n.id, n]));
  const maxDepth = Math.max(0, ...nodes.map((n) => depthOf.get(n.id)));
  const rows = Array.from({ length: maxDepth + 1 }, () => []);
  nodes.forEach((n) => rows[depthOf.get(n.id)].push(n.id));
  rows.forEach((row) => row.sort((a, b) => byId.get(a).created_at.localeCompare(byId.get(b).created_at)));

  function positionsOf(row) {
    const pos = new Map();
    row.forEach((id, i) => pos.set(id, i));
    return pos;
  }
  function reorderRow(row, neighborsOf, neighborPositions) {
    const barycenter = (id) => {
      const neighbors = (neighborsOf.get(id) || []).filter((n) => neighborPositions.has(n));
      if (!neighbors.length) return neighborPositions.size ? -1 : 0; // aucun voisin repositionné : garde sa place relative (trié en premier)
      return neighbors.reduce((sum, n) => sum + neighborPositions.get(n), 0) / neighbors.length;
    };
    return row
      .map((id) => ({ id, b: barycenter(id) }))
      .sort((a, b) => a.b - b.b || a.id.localeCompare(b.id))
      .map((e) => e.id);
  }

  const PASSES = 4;
  for (let pass = 0; pass < PASSES; pass++) {
    for (let d = 1; d <= maxDepth; d++) rows[d] = reorderRow(rows[d], parentsOf, positionsOf(rows[d - 1]));
    for (let d = maxDepth - 1; d >= 0; d--) rows[d] = reorderRow(rows[d], childrenOf, positionsOf(rows[d + 1]));
  }

  const colIndex = new Map();
  rows.forEach((row) => row.forEach((id, i) => colIndex.set(id, i)));

  const maxCols = Math.max(1, ...rows.map((row) => row.length));
  const width = margin * 2 + (maxCols - 1) * colWidth;
  const height = margin * 2 + maxDepth * rowHeight;
  const positioned = nodes.map((n) => {
    const d = depthOf.get(n.id);
    const cols = rows[d].length;
    const centeredOffset = ((maxCols - cols) / 2) * colWidth;
    return { ...n, x: margin + centeredOffset + colIndex.get(n.id) * colWidth, y: margin + d * rowHeight };
  });
  return { positioned, width: Math.max(width, 260), height: Math.max(height, 200) };
}

function lineageNodeShapeHtml(node, { radius = 9, selected = false, tipRing = true } = {}) {
  // Une fusion (/combiner - README : "visible dans le graphe du projet comme un losange") reste
  // un losange ici ; une pointe de piste actuelle porte un anneau accent pointillé pour rester
  // repérable même une fois qu'on a cliqué ailleurs. Le halo `.lineage-halo` marque la sélection
  // (visible avec `selected`, ou par la classe .lineage-node-selected du groupe - voir projet.html).
  const style = lineageOutcomeStyle(node);
  const k = radius / 9;
  const halo = `<circle class="lineage-halo" r="${radius + 7}" fill="none" stroke="var(--accent)" stroke-width="2"${selected ? "" : ` visibility="hidden"`}></circle>`;
  const ring =
    tipRing && node.is_tip ? `<circle r="${radius + 4}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="2 2"></circle>` : "";
  // style="" plutôt que des attributs : une feuille de style (ex. .lineage-shape) ne peut pas l'écraser.
  const paint = style.filled
    ? `fill="${style.color}" style="stroke:var(--surface);stroke-width:1.5px"`
    : `fill="var(--surface)" style="stroke:${style.color};stroke-width:${(2.2 * k).toFixed(2)}px"`;
  const r = style.filled ? radius : radius - 1.1 * k;
  const shape = node.is_merge
    ? `<path class="lineage-shape" d="M0,${-r * 1.15} L${r * 1.15},0 L0,${r * 1.15} L${-r * 1.15},0 Z" ${paint}></path>`
    : `<circle class="lineage-shape" r="${r}" ${paint}></circle>`;
  const dot = style.dot ? `<circle r="${(radius * 0.36).toFixed(2)}" fill="${style.color}"></circle>` : "";
  const glyph = style.glyph
    ? `<path d="${LINEAGE_GLYPH_PATH[style.glyph]}" transform="scale(${k.toFixed(3)})" fill="none" stroke="${style.filled ? "var(--surface)" : style.color}" stroke-width="${style.filled ? 1.8 : 2}" stroke-linecap="round" stroke-linejoin="round" pointer-events="none"></path>`
    : "";
  return `${halo}${ring}${shape}${dot}${glyph}`;
}

// Légende du code ci-dessus (une puce par issue + fusion + pointe de piste) - affichée sous le graphe
// d'un µprojet et au-dessus de la frise d'une thématique, pour qu'aucune couleur ne reste à deviner.
function lineageLegendHtml({ merge = true, tip = true } = {}) {
  const icon = (node) =>
    `<svg width="20" height="20" viewBox="-10 -10 20 20" aria-hidden="true">${lineageNodeShapeHtml(node, { radius: 6.5, tipRing: false })}</svg>`;
  const items = [
    ["draft", { status: "draft" }],
    ["continued", { status: "continued" }],
    ["running", { status: "running" }],
    ["hold", { status: "hold" }],
    ["promote", { status: "concluded", decision: "promote" }],
    ["continue", { status: "concluded", decision: "branch" }],
    ["inconclusive", { status: "concluded", decision: "inconclusive" }],
    ["abandoned", { status: "abandoned" }],
  ].map(([key, node]) => `<li>${icon(node)}${LINEAGE_OUTCOME_STYLE[key].label}</li>`);
  if (merge || tip) items.push(`<li class="status-legend__sep" aria-hidden="true"></li>`);
  if (merge) items.push(`<li>${icon({ status: "draft", is_merge: true })}Fusion de deux pistes</li>`);
  if (tip) {
    items.push(
      `<li><svg width="20" height="20" viewBox="-10 -10 20 20" aria-hidden="true"><circle r="8.5" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="2 2"></circle><circle r="4.5" fill="var(--surface)" style="stroke:var(--draft);stroke-width:1.6px"></circle></svg>Dernière version d'une piste</li>`
    );
  }
  return `<ul class="status-legend" aria-label="Légende des expériences">${items.join("")}</ul>`;
}

function lineageEdgePath(source, target) {
  // Coude vertical simple (pas une vraie courbe de Bézier) : assez lisible pour un historique de
  // quelques dizaines de nœuds, à revoir si des filiations très larges le rendent illisible.
  const midY = (source.y + target.y) / 2;
  return `M${source.x},${source.y} C${source.x},${midY} ${target.x},${midY} ${target.x},${target.y}`;
}
