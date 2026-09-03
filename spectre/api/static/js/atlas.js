/* Atlas : vue d'ensemble multi-projets - un cluster par projet, une bulle par étude (la pointe de
   chaque ligne de filiation, pas chaque version - voir GET /api/atlas / spectre.core.atlas), un
   petit point par échantillon physique suivi. Force-layout D3 plutôt que Plotly pour un vrai
   contrôle du zoom (affichage progressif des noms) et du clic (panneau contextuel) - voir la
   conversation de conception pour le pourquoi.
*/

const STATUS_COLOR = {
  draft: "var(--draft)",
  running: "var(--running)",
  concluded: "var(--done)",
  abandoned: "var(--abandoned)",
};

const OBJECTIVE_STATUS_LABELS = {
  met: "Atteint",
  not_met: "Non atteint",
  partially_met: "Partiellement atteint",
  inconclusive: "Non concluant",
};

const EXPERIENCE_RADIUS = 9;
const ENTITY_RADIUS = 4;
const CLUSTER_PADDING = 46;

const svg = d3.select("#atlas-svg");
const panel = document.getElementById("atlas-panel");
let selection = null; // the currently-clicked node's datum, for the side panel

function projectColor(index) {
  return `var(--atlas-cat-${(index % 8) + 1})`;
}

function panelEmptyState() {
  return `
    <div class="section-title" style="margin-bottom:10px;">Atlas</div>
    <p class="help">Chaque grande étiquette est un projet. Autour, une bulle par étude toujours en cours ou conclue - la ligne de filiation la plus récente, pas chaque version. Les petits points sont les échantillons physiques suivis. Cliquez un élément pour le détail ici ; zoomez pour voir les noms.</p>`;
}

function renderProjectPanel(d) {
  const experienceCount = d.experiences.length;
  const entityCount = d.experiences.reduce((n, e) => n + e.entities.length, 0);
  panel.innerHTML = `
    <div class="section-title" style="margin-bottom:6px;">Projet</div>
    <h2 style="font-size:18px;margin:0 0 8px;">${escapeHtml(d.name)}</h2>
    ${d.description ? `<p style="font-size:13px;color:var(--text-soft);line-height:1.55;margin-bottom:12px;">${escapeHtml(d.description)}</p>` : ""}
    <div style="font-size:12.5px;color:var(--text-faint);margin-bottom:14px;">
      ${escapeHtml(roleLabel(d.role))} &middot; ${experienceCount} étude${experienceCount > 1 ? "s" : ""}${entityCount ? ` &middot; ${entityCount} entité${entityCount > 1 ? "s" : ""} physique${entityCount > 1 ? "s" : ""}` : ""}
    </div>
    <a class="btn btn-primary btn-block" href="/projets/${encodeURIComponent(d.slug)}">Ouvrir le projet &rarr;</a>`;
}

function renderExperiencePanel(d) {
  const objectives = d.objectives
    .map(
      (o) => `
      <div style="padding:6px 0;border-top:1px solid var(--border-soft);font-size:12.5px;">
        <span style="font-weight:600;">${escapeHtml(o.name)}</span>
        <span style="color:var(--text-faint);"> — ${escapeHtml(o.status ? OBJECTIVE_STATUS_LABELS[o.status] || o.status : "en cours de vérification")}</span>
      </div>`
    )
    .join("");
  panel.innerHTML = `
    <div class="section-title" style="margin-bottom:6px;">Étude</div>
    <div style="margin-bottom:8px;">${statusBadgeHtml(d.status)}</div>
    <h2 style="font-size:17px;line-height:1.3;margin:0 0 8px;">${escapeHtml(d.title)}</h2>
    <p style="font-size:13px;color:var(--text-soft);line-height:1.55;margin-bottom:10px;">${escapeHtml(d.intent)}</p>
    ${d.conclusion_summary ? `<div style="font-size:12.5px;background:var(--bg);border-radius:var(--radius-sm);padding:8px 10px;line-height:1.5;margin-bottom:12px;">${escapeHtml(d.conclusion_summary)}</div>` : ""}
    ${objectives ? `<div style="margin-bottom:14px;">${objectives}</div>` : ""}
    <a class="btn btn-primary btn-block" href="/projets/${encodeURIComponent(d.projectSlug)}/experiences/${encodeURIComponent(d.id)}">Ouvrir la fiche &rarr;</a>`;
}

function renderEntityPanel(d) {
  panel.innerHTML = `
    <div class="section-title" style="margin-bottom:6px;">Entité physique</div>
    <h2 style="font-size:17px;margin:0 0 10px;">${escapeHtml(d.sample_id || "Échantillon sans identifiant")}</h2>
    ${d.location ? `<div style="font-size:13px;color:var(--text-soft);margin-bottom:14px;">Emplacement&nbsp;: ${escapeHtml(d.location)}</div>` : ""}
    <div class="help" style="margin-bottom:10px;">Suivie sur l'étude :</div>
    <div style="font-size:13.5px;font-weight:600;margin-bottom:10px;">${escapeHtml(d.experienceTitle)}</div>
    <a class="btn btn-line btn-block" href="/projets/${encodeURIComponent(d.projectSlug)}/experiences/${encodeURIComponent(d.experienceId)}">Ouvrir la fiche &rarr;</a>`;
}

function select(datum, element) {
  selection = datum;
  svg.selectAll(".atlas-node-selected").classed("atlas-node-selected", false);
  if (element) d3.select(element).classed("atlas-node-selected", true);
  if (!datum) {
    panel.innerHTML = panelEmptyState();
  } else if (datum.type === "project") {
    renderProjectPanel(datum);
  } else if (datum.type === "experience") {
    renderExperiencePanel(datum);
  } else {
    renderEntityPanel(datum);
  }
}

function build(atlas) {
  const projects = atlas.projects;
  if (projects.length === 0) {
    document.getElementById("atlas-empty").style.display = "";
    return;
  }

  const width = svg.node().clientWidth;
  const height = svg.node().clientHeight;
  const center = { x: width / 2, y: height / 2 };
  // An ellipse rather than a circle - the canvas is wide, not square, so this spreads clusters
  // across the space actually available instead of stacking them awkwardly (two projects on a
  // circle land directly above/below each other).
  const radiusX = width * 0.28;
  const radiusY = height * 0.28;

  const projectNodes = projects.map((p, i) => {
    const angle = (2 * Math.PI * i) / projects.length;
    const anchor = projects.length === 1 ? center : { x: center.x + radiusX * Math.cos(angle), y: center.y + radiusY * Math.sin(angle) };
    return { id: `project:${p.slug}`, type: "project", slug: p.slug, name: p.name, description: p.description, role: p.role, experiences: p.experiences, color: projectColor(i), fx: anchor.x, fy: anchor.y, x: anchor.x, y: anchor.y };
  });
  const projectBySlug = new Map(projectNodes.map((n) => [n.slug, n]));

  const experienceNodes = [];
  const entityNodes = [];
  const links = [];

  projects.forEach((p) => {
    p.experiences.forEach((exp) => {
      const anchor = projectBySlug.get(p.slug);
      experienceNodes.push({
        id: exp.id,
        type: "experience",
        projectSlug: p.slug,
        title: exp.title,
        intent: exp.intent,
        status: exp.status,
        conclusion_summary: exp.conclusion_summary,
        objectives: exp.objectives,
        color: anchor.color,
        x: anchor.x + (Math.random() - 0.5) * 20,
        y: anchor.y + (Math.random() - 0.5) * 20,
      });
      exp.entities.forEach((entity, i) => {
        const entityId = `entity:${exp.id}:${i}`;
        entityNodes.push({
          id: entityId,
          type: "entity",
          projectSlug: p.slug,
          experienceId: exp.id,
          experienceTitle: exp.title,
          sample_id: entity.sample_id,
          location: entity.location,
          x: anchor.x,
          y: anchor.y,
        });
        links.push({ source: entityId, target: exp.id, kind: "leash" });
      });
    });
    p.edges.forEach((e) => links.push({ source: e.from, target: e.to, kind: "derivation" }));
  });

  const allNodes = [...projectNodes, ...experienceNodes, ...entityNodes];

  const g = svg.append("g");
  const haloLayer = g.append("g");
  const edgeLayer = g.append("g");
  const nodeLayer = g.append("g");
  const labelLayer = g.append("g");

  const edgeSelection = edgeLayer
    .selectAll("path")
    .data(links.filter((l) => l.kind === "derivation"))
    .join("path")
    .attr("class", "atlas-edge");

  const leashSelection = edgeLayer
    .selectAll("line")
    .data(links.filter((l) => l.kind === "leash"))
    .join("line")
    .attr("class", "atlas-leash");

  const haloSelection = haloLayer
    .selectAll("circle")
    .data(projectNodes)
    .join("circle")
    .attr("class", "atlas-cluster-halo")
    .attr("fill", (d) => d.color)
    .attr("stroke", (d) => d.color)
    .attr("cx", (d) => d.fx)
    .attr("cy", (d) => d.fy)
    .attr("r", CLUSTER_PADDING)
    .on("click", (event, d) => select(d, event.currentTarget));

  const projectLabels = labelLayer
    .selectAll("text.atlas-label-project")
    .data(projectNodes)
    .join("text")
    .attr("class", "atlas-label atlas-label-project")
    .attr("text-anchor", "middle")
    .style("cursor", "pointer")
    .text((d) => d.name)
    .on("click", (event, d) => select(d, null));

  const experienceSelection = nodeLayer
    .selectAll("circle.atlas-node-experience")
    .data(experienceNodes)
    .join("circle")
    .attr("class", "atlas-node-experience")
    .attr("r", EXPERIENCE_RADIUS)
    .attr("fill", (d) => STATUS_COLOR[d.status] || STATUS_COLOR.draft)
    .on("click", (event, d) => select(d, event.currentTarget));

  const experienceLabels = labelLayer
    .selectAll("text.atlas-label-experience")
    .data(experienceNodes)
    .join("text")
    .attr("class", "atlas-label atlas-label-experience")
    .attr("dy", -EXPERIENCE_RADIUS - 4)
    .attr("text-anchor", "middle")
    .text((d) => (d.title.length > 28 ? d.title.slice(0, 27) + "…" : d.title));

  const entitySelection = nodeLayer
    .selectAll("circle.atlas-node-entity")
    .data(entityNodes)
    .join("circle")
    .attr("class", "atlas-node-entity")
    .attr("r", ENTITY_RADIUS)
    .on("click", (event, d) => select(d, event.currentTarget));

  const entityLabels = labelLayer
    .selectAll("text.atlas-label-entity")
    .data(entityNodes)
    .join("text")
    .attr("class", "atlas-label atlas-label-entity")
    .attr("dy", -ENTITY_RADIUS - 3)
    .attr("text-anchor", "middle")
    .text((d) => d.sample_id || d.location || "");

  svg.on("click", (event) => {
    if (event.target === svg.node()) select(null, null);
  });

  const simulation = d3
    .forceSimulation(allNodes)
    .force(
      "link",
      d3
        .forceLink(links)
        .id((d) => d.id)
        .distance((l) => (l.kind === "leash" ? 16 : 46))
        .strength((l) => (l.kind === "leash" ? 0.9 : 0.5))
    )
    .force("charge", d3.forceManyBody().strength((d) => (d.type === "project" ? 0 : d.type === "experience" ? -90 : -12)))
    .force("collide", d3.forceCollide().radius((d) => (d.type === "project" ? CLUSTER_PADDING : d.type === "experience" ? EXPERIENCE_RADIUS + 3 : ENTITY_RADIUS + 2)))
    .force(
      "cluster-x",
      d3.forceX((d) => (d.type === "project" ? d.fx : projectBySlug.get(d.projectSlug).x)).strength((d) => (d.type === "project" ? 0 : d.type === "experience" ? 0.12 : 0.03))
    )
    .force(
      "cluster-y",
      d3.forceY((d) => (d.type === "project" ? d.fy : projectBySlug.get(d.projectSlug).y)).strength((d) => (d.type === "project" ? 0 : d.type === "experience" ? 0.12 : 0.03))
    )
    .on("tick", ticked);

  function ticked() {
    experienceSelection.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
    experienceLabels.attr("x", (d) => d.x).attr("y", (d) => d.y);
    entitySelection.attr("cx", (d) => d.x).attr("cy", (d) => d.y);
    entityLabels.attr("x", (d) => d.x).attr("y", (d) => d.y);
    projectLabels.attr("x", (d) => d.fx).attr("y", (d) => d.fy - CLUSTER_PADDING - 10);

    leashSelection
      .attr("x1", (d) => d.source.x)
      .attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x)
      .attr("y2", (d) => d.target.y);
    edgeSelection.attr("d", (d) => `M${d.source.x},${d.source.y} L${d.target.x},${d.target.y}`);

    // The halo is sized to whatever currently sits farthest from its project's anchor, so it
    // keeps enclosing the cluster as the simulation settles rather than a guessed fixed radius.
    haloSelection.attr("r", (d) => {
      let maxDist = CLUSTER_PADDING;
      experienceNodes.forEach((e) => {
        if (e.projectSlug !== d.slug) return;
        const dist = Math.hypot(e.x - d.fx, e.y - d.fy) + EXPERIENCE_RADIUS + 22;
        if (dist > maxDist) maxDist = dist;
      });
      return maxDist;
    });
  }

  const zoom = d3
    .zoom()
    .scaleExtent([0.25, 6])
    .on("zoom", (event) => {
      g.attr("transform", event.transform);
      const k = event.transform.k;
      svg.attr("data-zoom", k >= 2.2 ? "close" : k >= 0.9 ? "mid" : "far");
    });
  svg.call(zoom);

  document.getElementById("atlas-zoom-in").addEventListener("click", () => svg.transition().duration(200).call(zoom.scaleBy, 1.4));
  document.getElementById("atlas-zoom-out").addEventListener("click", () => svg.transition().duration(200).call(zoom.scaleBy, 1 / 1.4));
  document.getElementById("atlas-zoom-reset").addEventListener("click", () => svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity));
}

async function init() {
  select(null, null);
  try {
    const atlas = await api.get("/api/atlas");
    build(atlas);
  } catch (err) {
    panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
  }
}

init();
