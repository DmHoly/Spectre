/* Vue par défaut du µprojet : le graphe hiérarchique "git-like" de ses expériences (un nœud =
   une expérience, un trait = un lien de filiation classique), plus la carte contextuelle qui
   s'ouvre au clic - voir GET /api/microprojets/{slug}/filiation (spectre.plugins.experiments.api::
   microproject_lineage). Un nœud n'est jamais une version parmi d'autres : seuls les racines, les
   fusions (/combiner) et les commits qui ont réellement fait avancer la structure sont gardés
   (spectre.plugins.experiments.versioning) - "un µprojet = split de structure". Remplace
   l'ancienne vue d'ensemble Plotly, supprimée : rendu D3 pour un vrai contrôle du layout et du
   clic, dans le même esprit qu'atlas.js.

   Le layout et le dessin d'un nœud/trait vivent dans lineage-graph.js (chargé avant ce fichier) -
   partagés avec le mini-arbre qu'atlas.js affiche au clic sur une étude, pour resituer son
   contexte sans dupliquer l'algorithme (et sans collision de noms - voir la note dans ce fichier).
*/

const NODE_RADIUS = 9;
const COL_WIDTH = 150; // place pour le badge wafers (à gauche) et le badge lot (à droite) d'un nœud
const ROW_HEIGHT = 100;
const MARGIN = 56; // assez pour les libellés centrés sous les nœuds des bords

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
    } else if (detail.structure_images) {
      structureBlock = structureBoardHtml(slug, detail.structure_images, { compact: true });
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
      ${fdlsOfTracking(detail.physical_tracking).length ? `<div style="margin-bottom:10px;">${fdlChipsHtml(fdlsOfTracking(detail.physical_tracking))}</div>` : ""}
      ${
        node && node.lots && node.lots.length
          ? `<div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:10px;font-size:12px;color:var(--text-faint);">Dans le lot ${node.lots
              .map((l) => `<a class="lineage-lot-chip" href="/lots/${encodeURIComponent(l.code)}">${escapeHtml(l.code)}</a>`)
              .join("")}</div>`
          : ""
      }
      ${structureBlock}
      ${objectivesBlock}
      ${conclusionBlock}
      ${node && node.started_at ? spanBlockHtml(node) : ""}
      ${
        canEvolve
          ? `<div class="lineage-panel__lot">
              <div class="section-title" style="font-size:12px;margin-bottom:6px;">Lot de fabrication</div>
              <div id="lineage-lot-assign"></div>
            </div>`
          : ""
      }
      <div style="font-size:12px;color:var(--text-faint);margin-top:12px;padding-top:10px;border-top:1px solid var(--border-soft);">
        ${escapeHtml(detail.author || "Auteur inconnu")} &middot; ${timeAgo(detail.created_at)}
      </div>
      <div style="display:flex;gap:8px;margin-top:14px;">
        <a class="btn btn-line" style="flex:1;" href="/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(nodeId)}">Ouvrir la fiche</a>
        ${
          canEvolve
            ? `<a class="btn btn-primary" style="flex:1;" href="/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(nodeId)}/${detail.structure_images ? "evoluer-image" : "evoluer"}">Continuer d'ici</a>`
            : ""
        }
      </div>`;
    if (variation) renderLineageStructureCarousel(variation);
    if (canEvolve) {
      // mettre un wafer de l'expérience dans un lot (lot-picker.js) ; le badge suit dans le graphe
      mountLotAssign(document.getElementById("lineage-lot-assign"), {
        lasermarks: (detail.physical_tracking || []).map((e) => e.sample_id),
        onChange: () => loadLineage(),
      });
    }
  } catch (err) {
    panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
  }
}

// Temps écoulé de l'expérience cliquée (même règle que sous le nœud, voir lineage-graph.js::lineageSpan).
function spanBlockHtml(node) {
  const span = lineageSpan(node);
  const label = { ended: "Durée", continued: "Durée avant la suite", ongoing: "En cours depuis", hold: "Ouverte depuis" }[span.state];
  const hold = lineageHoldLabel(node);
  const duration = formatDuration((span.end ? new Date(span.end) : new Date()) - new Date(span.start));
  return `<div style="display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 8px;margin-top:12px;font-size:12.5px;color:var(--text-soft);">
      <span class="section-title" style="font-size:11px;margin:0;">${label}</span>
      <strong style="font-variant-numeric:tabular-nums;color:var(--text);">${escapeHtml(duration)}</strong>
      <span style="font-family:var(--font-mono);font-size:11px;color:var(--text-faint);">${escapeHtml(lineageDatesLabel(node))}</span>
    </div>${hold ? `<div style="margin-top:4px;font-size:12.5px;font-weight:600;color:var(--hold);">${escapeHtml(hold)}</div>` : ""}`;
}

// Même carrousel (référence + chaque variante) que l'atlas et la fiche (voir common.js::
// mountStructureCarousel) - avant ça, une campagne cliquée ici ne montrait qu'un texte « Campagne —
// N variantes. », sans jamais voir la structure elle-même ni pouvoir comparer les variantes.
function renderLineageStructureCarousel(variation) {
  mountStructureCarousel(document.getElementById("lineage-structure-carousel"), variation);
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

  function select(target, d) {
    svg.selectAll(".lineage-node").classed("lineage-node-selected", false);
    d3.select(target).classed("lineage-node-selected", true);
    selectedId = d.id;
    loadCard(d.id, d);
  }

  const nodeGroups = svg
    .append("g")
    .selectAll("g")
    .data(positioned)
    .join("g")
    .attr("class", "lineage-node")
    .attr("transform", (d) => `translate(${d.x},${d.y})`)
    .attr("data-id", (d) => d.id)
    .attr("tabindex", 0)
    .attr("role", "button")
    .attr("aria-label", (d) => lineageNodeTooltip(d).replace(/\n/g, " · "))
    .on("click", (event, d) => select(event.currentTarget, d))
    .on("keydown", (event, d) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      select(event.currentTarget, d);
    });

  nodeGroups.each(function (d) {
    d3.select(this).html(lineageNodeShapeHtml(d, { radius: NODE_RADIUS }));
    d3.select(this).append("title").text(lineageNodeTooltip(d));
  });

  nodeGroups
    .append("text")
    .attr("class", "lineage-label")
    .attr("y", NODE_RADIUS + 16)
    .attr("text-anchor", "middle")
    .text((d) => (d.title.length > 16 ? d.title.slice(0, 15) + "…" : d.title));

  // Badge du lot (suivi de lots) à droite du nœud : l'expérience suit un wafer de ce lot. Lien
  // vers le lot - un clic dessus ne sélectionne pas le nœud.
  nodeGroups
    .filter((d) => d.lots && d.lots.length)
    .each(function (d) {
      const first = d.lots[0];
      const code = first.code.length > 11 ? `${first.code.slice(0, 10)}…` : first.code;
      const text = d.lots.length > 1 ? `${code} +${d.lots.length - 1}` : code;
      const width = text.length * 6 + 12;
      const active = ["planned", "wip", "hold"].includes(first.status);
      const badge = d3
        .select(this)
        .append("a")
        .attr("class", `lineage-lot${active ? "" : " is-past"}`)
        .attr("href", `/lots/${encodeURIComponent(first.code)}`)
        .attr("transform", `translate(${NODE_RADIUS + 9},${-NODE_RADIUS - 6})`)
        .on("click", (event) => event.stopPropagation())
        .on("keydown", (event) => event.stopPropagation());
      badge.append("title").text(`Dans le lot ${d.lots.map((l) => l.code).join(", ")} - ouvrir le suivi du lot`);
      badge.append("rect").attr("width", width).attr("height", 15).attr("rx", 7.5);
      badge.append("text").attr("x", width / 2).attr("y", 10.5).attr("text-anchor", "middle").text(text);
    });

  // Badge wafers à gauche du nœud : combien de wafers (lasermarks) l'expérience suit - la liste au survol.
  nodeGroups
    .filter((d) => d.wafers && d.wafers.length)
    .each(function (d) {
      const text = String(d.wafers.length);
      const width = 22 + text.length * 6;
      const badge = d3
        .select(this)
        .append("g")
        .attr("class", "lineage-wafers")
        .attr("transform", `translate(${-NODE_RADIUS - 9 - width},${-NODE_RADIUS - 6})`);
      badge.append("title").text(`${d.wafers.length} wafer${d.wafers.length > 1 ? "s" : ""} : ${d.wafers.join(", ")}`);
      badge.append("rect").attr("width", width).attr("height", 15).attr("rx", 7.5);
      // un wafer : un disque au méplat
      badge.append("path").attr("d", "M5,9.4 A4,4 0 1 1 11,9.4 Z");
      badge.append("text").attr("x", 16).attr("y", 10.5).text(text);
    });

  // Temps écoulé du début à la fin (ou à maintenant, « depuis… », tant qu'elle n'est pas terminée).
  nodeGroups
    .append("text")
    .attr("class", (d) => `lineage-duration${{ ongoing: " is-ongoing", hold: " is-hold" }[lineageSpan(d).state] || ""}`)
    .attr("y", NODE_RADIUS + 30)
    .attr("text-anchor", "middle")
    .text((d) => lineageElapsedLabel(d));

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
