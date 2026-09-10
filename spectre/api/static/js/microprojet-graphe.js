/* Vue par défaut du µprojet : le graphe hiérarchique "git-like" de ses expériences (un nœud =
   une expérience, un trait = un lien de filiation classique), plus la carte contextuelle qui
   s'ouvre au clic - voir GET /api/microprojets/{slug}/filiation (spectre.api.experiments::
   microproject_lineage). Un nœud n'est jamais une version parmi d'autres : seuls les racines, les
   fusions (/combiner) et les commits qui ont réellement fait avancer la structure sont gardés
   (spectre.core.versioning) - "un µprojet = split de structure". Remplace l'ancienne vue
   d'ensemble Plotly (toujours servie sur /graphe pour les anciens liens, mais plus la vue par
   défaut) : rendu D3 pour un vrai contrôle du layout et du clic, dans le même esprit qu'atlas.js.

   Layout : une rangée par profondeur (plus long chemin depuis une racine), les nœuds d'une même
   rangée ordonnés par le barycentre x de leurs parents (une seule passe - suffisant pour la
   plupart des historiques, pas un vrai algorithme anti-croisements). À affiner plus tard, comme
   convenu - la carte aussi.
*/

const STATUS_COLOR = {
  draft: "var(--draft)",
  running: "var(--running)",
  concluded: "var(--done)",
  abandoned: "var(--abandoned)",
};

const NODE_RADIUS = 9;
const COL_WIDTH = 130;
const ROW_HEIGHT = 100;
const MARGIN = 40;

const svg = d3.select("#lineage-svg");
const panel = document.getElementById("lineage-panel");
let selectedId = null;

function layout(nodes, edges) {
  const parentsOf = new Map(nodes.map((n) => [n.id, []]));
  edges.forEach((e) => {
    if (parentsOf.has(e.child)) parentsOf.get(e.child).push(e.parent);
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
  const rows = new Map();
  nodes.forEach((n) => {
    const d = depthOf.get(n.id);
    if (!rows.has(d)) rows.set(d, []);
    rows.get(d).push(n.id);
  });
  const maxDepth = Math.max(...rows.keys());

  const colIndex = new Map();
  for (let d = 0; d <= maxDepth; d++) {
    const row = rows.get(d) || [];
    if (d === 0) {
      row.sort((a, b) => byId.get(a).created_at.localeCompare(byId.get(b).created_at));
    } else {
      row.sort((a, b) => {
        const barycenter = (id) => {
          const parents = parentsOf.get(id) || [];
          if (!parents.length) return 0;
          return parents.reduce((sum, p) => sum + (colIndex.get(p) ?? 0), 0) / parents.length;
        };
        return barycenter(a) - barycenter(b);
      });
    }
    row.forEach((id, i) => colIndex.set(id, i));
  }

  const maxCols = Math.max(1, ...[...rows.values()].map((row) => row.length));
  const width = MARGIN * 2 + (maxCols - 1) * COL_WIDTH;
  const height = MARGIN * 2 + maxDepth * ROW_HEIGHT;
  const rowWidth = (d) => (rows.get(d) || []).length;
  const positioned = nodes.map((n) => {
    const d = depthOf.get(n.id);
    const cols = rowWidth(d);
    const centeredOffset = ((maxCols - cols) / 2) * COL_WIDTH;
    return { ...n, x: MARGIN + centeredOffset + colIndex.get(n.id) * COL_WIDTH, y: MARGIN + d * ROW_HEIGHT };
  });
  return { positioned, width: Math.max(width, 260), height: Math.max(height, 200) };
}

function nodeShapeHtml(node) {
  // Une fusion (/combiner - README : "visible dans le graphe du projet comme un losange") reste
  // un losange ici ; une pointe de piste actuelle porte un anneau accent pour rester repérable
  // même une fois qu'on a cliqué ailleurs.
  const color = STATUS_COLOR[node.status] || STATUS_COLOR.draft;
  const ring = node.is_tip ? `<circle r="${NODE_RADIUS + 4}" fill="none" stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="2 2"></circle>` : "";
  if (node.is_merge) {
    const r = NODE_RADIUS * 0.9;
    return `${ring}<path class="lineage-shape" d="M0,-${r} L${r},0 L0,${r} L-${r},0 Z" fill="${color}"></path>`;
  }
  return `${ring}<circle class="lineage-shape" r="${NODE_RADIUS}" fill="${color}"></circle>`;
}

function edgePath(source, target) {
  // Coude vertical simple (pas une vraie courbe de Bézier) : assez lisible pour un historique de
  // quelques dizaines de nœuds, à revoir si des filiations très larges le rendent illisible.
  const midY = (source.y + target.y) / 2;
  return `M${source.x},${source.y} C${source.x},${midY} ${target.x},${midY} ${target.x},${target.y}`;
}

function panelEmptyState() {
  return `<p class="help">Cliquez un nœud pour voir la structure, l'objectif et la conclusion de cette expérience ici.</p>`;
}

async function loadCard(nodeId, node) {
  panel.innerHTML = `<p class="help">Chargement…</p>`;
  try {
    const detail = await api.get(`/api/microprojets/${slug}/experiences/${encodeURIComponent(nodeId)}`);
    let structureBlock;
    if (detail.is_batch) {
      try {
        const matrix = await api.get(`/api/microprojets/${slug}/experiences/${encodeURIComponent(nodeId)}/matrice`);
        structureBlock = `<div class="help">Campagne — ${matrix.labels.length} variante${matrix.labels.length > 1 ? "s" : ""}.</div>`;
      } catch (err) {
        structureBlock = "";
      }
    } else if (detail.structure_svg) {
      structureBlock = `<div class="builder-canvas-svg" style="height:150px;">${detail.structure_svg}</div>`;
    } else {
      structureBlock = "";
    }

    const objectivesBlock = detail.objectives.length
      ? `<div style="margin-top:10px;">
          <div class="section-title" style="font-size:12px;margin-bottom:6px;">Objectifs</div>
          <ul style="margin:0;padding-left:18px;font-size:12.5px;color:var(--text-soft);line-height:1.6;">
            ${detail.objectives
              .map((o) => `<li>${escapeHtml(o.name)}${o.target != null ? ` · cible ${o.target}${o.metric ? " " + escapeHtml(o.metric) : ""}` : ""}</li>`)
              .join("")}
          </ul>
        </div>`
      : "";

    const conclusionBlock = detail.conclusion.summary
      ? `<div style="margin-top:10px;font-size:12.5px;color:var(--text);background:var(--bg);border-radius:var(--radius-sm);padding:8px 10px;line-height:1.5;">${escapeHtml(detail.conclusion.summary)}</div>`
      : "";

    const canEvolve = currentRole === "editor" || currentRole === "owner";
    panel.innerHTML = `
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;">
        <div class="section-title" style="margin-bottom:0;">${escapeHtml(detail.title)}</div>
        ${statusBadgeHtml(detail.status)}
      </div>
      <p class="help" style="margin-bottom:10px;">${escapeHtml(detail.intent)}</p>
      ${structureBlock}
      ${objectivesBlock}
      ${conclusionBlock}
      <div style="font-size:12px;color:var(--text-faint);margin-top:12px;padding-top:10px;border-top:1px solid var(--border-soft);">
        ${escapeHtml(detail.author || "Auteur inconnu")} &middot; ${timeAgo(detail.created_at)}
      </div>
      <div style="display:flex;gap:8px;margin-top:14px;">
        <a class="btn btn-line" style="flex:1;" href="/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(nodeId)}">Ouvrir la fiche</a>
        ${
          canEvolve
            ? `<a class="btn btn-primary" style="flex:1;" href="/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(nodeId)}/evoluer">Continuer d'ici</a>`
            : ""
        }
      </div>`;
  } catch (err) {
    panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
  }
}

function render(nodes, edges) {
  document.getElementById("lineage-empty").style.display = nodes.length ? "none" : "";
  if (!nodes.length) {
    svg.selectAll("*").remove();
    return;
  }

  const { positioned, width, height } = layout(nodes, edges);
  const byId = new Map(positioned.map((n) => [n.id, n]));

  svg.attr("width", width).attr("height", height).attr("viewBox", `0 0 ${width} ${height}`);
  svg.selectAll("*").remove();

  svg
    .append("g")
    .selectAll("path")
    .data(edges)
    .join("path")
    .attr("class", "lineage-edge")
    .attr("d", (e) => edgePath(byId.get(e.parent), byId.get(e.child)));

  const nodeGroups = svg
    .append("g")
    .selectAll("g")
    .data(positioned)
    .join("g")
    .attr("class", "lineage-node")
    .attr("transform", (d) => `translate(${d.x},${d.y})`)
    .attr("data-id", (d) => d.id)
    .on("click", (event, d) => {
      svg.selectAll(".lineage-node").classed("lineage-node-selected", false);
      d3.select(event.currentTarget).classed("lineage-node-selected", true);
      selectedId = d.id;
      loadCard(d.id, d);
    });

  nodeGroups.each(function (d) {
    d3.select(this).html(nodeShapeHtml(d));
  });

  nodeGroups
    .append("text")
    .attr("class", "lineage-label")
    .attr("y", NODE_RADIUS + 16)
    .attr("text-anchor", "middle")
    .text((d) => (d.title.length > 16 ? d.title.slice(0, 15) + "…" : d.title));

  if (selectedId && byId.has(selectedId)) {
    svg.select(`.lineage-node[data-id="${CSS.escape(selectedId)}"]`).classed("lineage-node-selected", true);
  }
}

async function loadLineage() {
  try {
    const body = await api.get(`/api/microprojets/${encodeURIComponent(slug)}/filiation`);
    render(body.nodes, body.edges);
  } catch (err) {
    panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
  }
}
