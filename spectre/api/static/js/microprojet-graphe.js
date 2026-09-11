/* Vue par défaut du µprojet : le graphe hiérarchique "git-like" de ses expériences (un nœud =
   une expérience, un trait = un lien de filiation classique), plus la carte contextuelle qui
   s'ouvre au clic - voir GET /api/microprojets/{slug}/filiation (spectre.api.experiments::
   microproject_lineage). Un nœud n'est jamais une version parmi d'autres : seuls les racines, les
   fusions (/combiner) et les commits qui ont réellement fait avancer la structure sont gardés
   (spectre.core.versioning) - "un µprojet = split de structure". Remplace l'ancienne vue
   d'ensemble Plotly (toujours servie sur /graphe pour les anciens liens, mais plus la vue par
   défaut) : rendu D3 pour un vrai contrôle du layout et du clic, dans le même esprit qu'atlas.js.

   Le layout et le dessin d'un nœud/trait vivent dans lineage-graph.js (chargé avant ce fichier) -
   partagés avec le mini-arbre qu'atlas.js affiche au clic sur une étude, pour resituer son
   contexte sans dupliquer l'algorithme (et sans collision de noms - voir la note dans ce fichier).
*/

const NODE_RADIUS = 9;
const COL_WIDTH = 130;
const ROW_HEIGHT = 100;
const MARGIN = 40;

const svg = d3.select("#lineage-svg");
const panel = document.getElementById("lineage-panel");
let selectedId = null;

function panelEmptyState() {
  return `<p class="help">Cliquez un nœud pour voir la structure, l'objectif et la conclusion de cette expérience ici.</p>`;
}

async function loadCard(nodeId, node) {
  panel.innerHTML = `<p class="help">Chargement…</p>`;
  try {
    const detail = await api.get(`/api/microprojets/${slug}/experiences/${encodeURIComponent(nodeId)}`);
    let structureBlock;
    let variation = null;
    if (detail.is_batch) {
      try {
        variation = await api.get(`/api/microprojets/${slug}/experiences/${encodeURIComponent(nodeId)}/matrice`);
        structureBlock = `<div id="lineage-structure-carousel"></div>`;
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
        ${statusBadgeHtml(detail.status, detail.conclusion.decision)}
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
    if (variation) renderLineageStructureCarousel(variation);
  } catch (err) {
    panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
  }
}

// Même carrousel (référence + chaque variante) que l'atlas (voir atlas.js::renderStructureCarousel)
// - avant ça, une campagne cliquée ici ne montrait qu'un texte "Campagne — N variantes.", sans
// jamais voir la structure elle-même ni pouvoir comparer les variantes entre elles.
function renderLineageStructureCarousel(variation) {
  const container = document.getElementById("lineage-structure-carousel");
  if (!container) return;
  const svgs = variation.svgs || [];
  if (svgs.length === 0) {
    container.innerHTML = "";
    return;
  }
  let index = 0;
  function paint() {
    const isRef = index === 0;
    container.innerHTML = `
      <div class="atlas-carousel">
        <div class="atlas-carousel__badge">${isRef ? `<span class="badge badge-role">RÉF</span>` : ""}<span>${escapeHtml(variantCaption(variation, index))}</span></div>
        <div class="atlas-carousel__stage">${svgs[index]}</div>
        <div class="atlas-carousel__nav">
          <button type="button" class="btn btn-line" data-dir="-1" ${svgs.length < 2 ? "disabled" : ""}>&larr;</button>
          <span class="help">${index + 1} / ${svgs.length}</span>
          <button type="button" class="btn btn-line" data-dir="1" ${svgs.length < 2 ? "disabled" : ""}>&rarr;</button>
        </div>
      </div>`;
    container.querySelectorAll("[data-dir]").forEach((btn) => {
      btn.addEventListener("click", () => {
        index = (index + parseInt(btn.dataset.dir, 10) + svgs.length) % svgs.length;
        paint();
      });
    });
  }
  paint();
}

function render(nodes, edges) {
  document.getElementById("lineage-empty").style.display = nodes.length ? "none" : "";
  if (!nodes.length) {
    svg.selectAll("*").remove();
    return;
  }

  const { positioned, width, height } = lineageLayout(nodes, edges, { colWidth: COL_WIDTH, rowHeight: ROW_HEIGHT, margin: MARGIN });
  const byId = new Map(positioned.map((n) => [n.id, n]));

  svg.attr("width", width).attr("height", height).attr("viewBox", `0 0 ${width} ${height}`);
  svg.selectAll("*").remove();

  svg
    .append("g")
    .selectAll("path")
    .data(edges)
    .join("path")
    .attr("class", "lineage-edge")
    .attr("d", (e) => lineageEdgePath(byId.get(e.parent), byId.get(e.child)));

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
    d3.select(this).html(lineageNodeShapeHtml(d, { radius: NODE_RADIUS }));
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
