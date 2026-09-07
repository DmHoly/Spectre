/* Refs d'un projet : la liste, et comment elles s'enchaînent (spectre.core.refs.ref_graph) -
   rendue comme un arbre indenté plutôt qu'un graphe dessiné : chaque ref n'a jamais qu'un petit
   nombre de refs "suivantes" (voir spectre.core.atlas.condensed_edges, dont ref_graph réutilise
   l'algorithme), donc un arbre texte navigue aussi bien et reste lisible sans bibliothèque de
   rendu supplémentaire. */

const slug = window.location.pathname.split("/").filter(Boolean)[1];
document.getElementById("crumb").textContent = "/ " + slug;
document.getElementById("project-link").href = `/projets/${slug}`;

function refCardHtml(node) {
  const names = node.names
    .map((name) => `<span class="badge badge-role">${escapeHtml(name)}</span>`)
    .join(" ");
  return `
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:10px;flex-wrap:wrap;">
      <div>
        <a href="/projets/${slug}/experiences/${node.experiment_id}" style="font-weight:600;font-size:14px;">${escapeHtml(node.title)}</a>
        <span style="color:var(--text-faint);font-size:12px;margin-left:6px;">v${escapeHtml(node.version)} · ${escapeHtml(node.branch)}</span>
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
        ${names}
        ${statusBadgeHtml(node.status)}
      </div>
    </div>
    <div style="color:var(--text-faint);font-size:11.5px;margin-top:4px;">${formatDate(node.created_at)}</div>`;
}

function renderTree(nodesById, childrenOf, roots, depth = 0) {
  return roots
    .map((id) => {
      const node = nodesById.get(id);
      if (!node) return "";
      const children = childrenOf.get(id) || [];
      return `
        <div style="margin-left:${depth * 22}px;padding:12px 0;${depth > 0 ? "border-top:1px solid var(--border-soft);" : ""}">
          ${refCardHtml(node)}
        </div>
        ${renderTree(nodesById, childrenOf, children, depth + 1)}`;
    })
    .join("");
}

async function init() {
  try {
    const graph = await api.get(`/api/projects/${slug}/refs/graphe`);
    if (graph.nodes.length === 0) {
      document.getElementById("empty-note").style.display = "block";
      return;
    }
    const nodesById = new Map(graph.nodes.map((n) => [n.experiment_id, n]));
    const childrenOf = new Map();
    const hasParent = new Set();
    graph.edges.forEach((edge) => {
      if (!childrenOf.has(edge.from)) childrenOf.set(edge.from, []);
      childrenOf.get(edge.from).push(edge.to);
      hasParent.add(edge.to);
    });
    // newest-first order (graph.nodes already sorted that way) is kept within each level
    const order = graph.nodes.map((n) => n.experiment_id);
    const rank = new Map(order.map((id, i) => [id, i]));
    childrenOf.forEach((ids) => ids.sort((a, b) => rank.get(a) - rank.get(b)));
    const roots = order.filter((id) => !hasParent.has(id));

    const box = document.getElementById("ref-tree");
    box.innerHTML = renderTree(nodesById, childrenOf, roots);
    box.style.display = "block";
  } catch (err) {
    document.getElementById("error").textContent = err.message;
    document.getElementById("error").style.display = "block";
  }
}

init();
