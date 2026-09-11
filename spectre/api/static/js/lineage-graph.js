/* Rendu partagé d'un graphe de filiation "git-like" (un nœud = une expérience structurellement
   distincte, voir GET /api/microprojets/{slug}/filiation) : le layout en couches et le dessin
   d'un nœud/trait, utilisés à la fois par microprojet-graphe.js (la vue par défaut d'un µprojet,
   pleine taille) et atlas.js (l'arbre miniature affiché au clic sur une étude, pour resituer son
   contexte sans quitter l'atlas). Tout est fonction pure (aucun accès au DOM ni à `state`) pour
   rester utilisable des deux côtés sans rien partager d'autre qu'un include - voir la note dans
   microprojet-graphe.js sur pourquoi ce n'est pas microprojet-graphe.js lui-même qui est réutilisé
   tel quel (conflits de noms avec les propres constantes d'atlas.js).
*/

const LINEAGE_CONCLUDED_DECISION_COLOR = {
  promote: "var(--done)",
  inconclusive: "var(--abandoned)",
  branch: "var(--running)",
  replicate: "var(--running)",
};
const LINEAGE_STATUS_COLOR = { draft: "var(--draft)", running: "var(--running)", abandoned: "var(--abandoned)" };

function lineageNodeColor({ status, decision }) {
  if (status === "concluded") return LINEAGE_CONCLUDED_DECISION_COLOR[decision] || "var(--done)";
  return LINEAGE_STATUS_COLOR[status] || LINEAGE_STATUS_COLOR.draft;
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

function lineageNodeShapeHtml(node, { radius = 9 } = {}) {
  // Une fusion (/combiner - README : "visible dans le graphe du projet comme un losange") reste
  // un losange ici ; une pointe de piste actuelle porte un anneau accent pour rester repérable
  // même une fois qu'on a cliqué ailleurs.
  const color = lineageNodeColor(node);
  const ring = node.is_tip ? `<circle r="${radius + 4}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="2 2"></circle>` : "";
  if (node.is_merge) {
    const r = radius * 0.9;
    return `${ring}<path class="lineage-shape" d="M0,-${r} L${r},0 L0,${r} L-${r},0 Z" fill="${color}"></path>`;
  }
  return `${ring}<circle class="lineage-shape" r="${radius}" fill="${color}"></circle>`;
}

function lineageEdgePath(source, target) {
  // Coude vertical simple (pas une vraie courbe de Bézier) : assez lisible pour un historique de
  // quelques dizaines de nœuds, à revoir si des filiations très larges le rendent illisible.
  const midY = (source.y + target.y) / 2;
  return `M${source.x},${source.y} C${source.x},${midY} ${target.x},${midY} ${target.x},${target.y}`;
}
