/* Le diagramme façon git des évolutions (global `EvolutionGraph`) : une colonne par piste ou par
   branche, une rangée par version, des arêtes parent -> enfant. Partagé par la page d'évolution des
   structures d'un µprojet (evolution.js : pistes et versions Follow) et la page d'une référence
   (references/static/reference.js : versions de référence 1.0, 1.1, 2.0...). Il ne connaît ni l'une
   ni l'autre : il reçoit des nœuds déjà rangés (`lane`, l'ordre des rangées), des arêtes déjà
   résolues, et dessine ; chaque page écrit ses rangées (le texte) et son panneau. Il porte aussi
   ce que les deux pages font pareil : la liste des rangées au clavier (`bindListbox`) et le corps
   d'une comparaison de structures (`diffBodyHtml`).

   Forme d'un nœud = niveau du changement (plein : première ou majeur ; anneau : mineur ; petit
   point : correctif ; petit cercle creux : sans changement ; losange : combinaison) ; anneau or :
   un repère nommé (ref, version de référence) ; anneau pointillé : la tête d'une colonne. Jamais la
   forme seule : chaque page écrit le niveau en toutes lettres et pose la légende (`legendHtml`). */

const EvolutionGraph = (() => {
  const COL = 26; // écart entre deux colonnes
  const PAD = 18; // marge du diagramme
  const ROW = 44; // hauteur d'une rangée (cible tactile)

  const laneX = (lane) => PAD + lane * COL;
  const rowY = (index) => index * ROW + ROW / 2;
  const width = (laneCount) => PAD * 2 + (Math.max(laneCount, 1) - 1) * COL;

  function nodeShape({ change_level, is_merge = false, marked = false, is_tip = false }) {
    let shape = "";
    if (is_tip) shape += `<circle r="13" fill="none" stroke="var(--navy-500)" stroke-width="1.5" stroke-dasharray="2 2"></circle>`;
    if (marked) shape += `<circle r="10" fill="none" stroke="var(--gold)" stroke-width="2.5"></circle>`;
    if (is_merge) {
      shape += `<path d="M0,-7 L7,0 L0,7 L-7,0 Z" fill="var(--surface)" stroke="var(--navy)" stroke-width="2"></path>`;
    } else if (change_level === "initial" || change_level === "major") {
      shape += `<circle r="6.5" fill="var(--navy)" stroke="var(--surface)" stroke-width="1.5"></circle>`;
    } else if (change_level === "minor") {
      shape += `<circle r="5.5" fill="var(--surface)" stroke="var(--navy-500)" stroke-width="2.5"></circle>`;
    } else if (change_level === "patch") {
      shape += `<circle r="3.5" fill="var(--text-faint)"></circle>`;
    } else {
      shape += `<circle r="3.5" fill="var(--surface)" stroke="var(--text-faint)" stroke-width="1.5"></circle>`;
    }
    return shape;
  }

  // Le tracé d'une arête entre deux positions {lane, row} : droit dans une même colonne ; vers une
  // combinaison (`merge`), il descend la colonne du parent puis la rejoint ; sinon (une fourche,
  // une branche) il quitte le parent puis descend la nouvelle colonne.
  function edgePath(from, to, kind) {
    const x1 = laneX(from.lane);
    const x2 = laneX(to.lane);
    const y1 = rowY(from.row);
    const y2 = rowY(to.row);
    if (x1 === x2) return `M${x1},${y1} L${x2},${y2}`;
    if (kind === "merge") {
      return `M${x1},${y1} L${x1},${y2 - ROW * 0.8} C${x1},${y2 - ROW * 0.3} ${x2},${y2 - ROW * 0.5} ${x2},${y2}`;
    }
    return `M${x1},${y1} C${x1},${y1 + ROW * 0.5} ${x2},${y1 + ROW * 0.3} ${x2},${y1 + ROW * 0.8} L${x2},${y2}`;
  }

  // Dessine dans `svg` (un <svg>, avec d3) : `nodes` dans l'ordre des rangées, chacun avec `lane` ;
  // `edges` : {parent, child, kind} (des ids que donne `idOf`) ; `nodeClass(node)`, `edgeClass(edge)` :
  // les classes en plus ; `shapeOf(node)` : l'argument de nodeShape.
  function draw(svg, { laneCount, nodes, edges, idOf, shapeOf, nodeClass = () => "", edgeClass = () => "" }) {
    const index = new Map(nodes.map((node, row) => [idOf(node), { lane: node.lane, row }]));
    const drawn = edges.filter((edge) => index.has(edge.parent) && index.has(edge.child));
    const root = d3.select(svg).attr("width", width(laneCount)).attr("height", nodes.length * ROW);
    root
      .selectAll("path.evo-edge")
      .data(drawn, (edge) => `${edge.parent}>${edge.child}`)
      .join("path")
      .attr("class", (edge) => `evo-edge evo-edge--${edge.kind} ${edgeClass(edge)}`.trim())
      .attr("d", (edge) => edgePath(index.get(edge.parent), index.get(edge.child), edge.kind));
    root
      .selectAll("g.evo-node")
      .data(nodes, idOf)
      .join("g")
      .attr("class", (node) => `evo-node ${nodeClass(node)}`.trim())
      .attr("transform", (node, row) => `translate(${laneX(node.lane)},${rowY(row)})`)
      .html((node) => nodeShape(shapeOf(node)))
      .raise();
  }

  // Les étiquettes des colonnes, au-dessus du diagramme : [{lane, text, title, retired}].
  function laneTagsHtml(tags) {
    return tags
      .map(
        (tag) =>
          `<span class="evo-lanes__tag${tag.retired ? " is-retired" : ""}" style="left:${laneX(tag.lane)}px" title="${escapeHtml(tag.title || "")}">${escapeHtml(tag.text)}</span>`
      )
      .join("");
  }

  // La légende : [[argument de nodeShape, texte]].
  function legendHtml(items) {
    const icon = (shape) => `<svg width="30" height="30" viewBox="-15 -15 30 30" aria-hidden="true">${nodeShape(shape)}</svg>`;
    return items.map(([shape, text]) => `<li>${icon(shape)}${escapeHtml(text)}</li>`).join("");
  }

  // La liste des rangées (role="listbox", chaque rangée `.evo-row` porte `data-id` et l'id
  // `row-<id>`) : une seule étape de tabulation ; flèches haut et bas, Début, Fin pour s'y
  // déplacer, Entrée ou Espace pour choisir (`onChoose(id, viaClick)`), Échap (`onEscape()`, vrai s'il a
  // servi). `getFocus()` / `setFocus(id)` : la rangée focalisable, que la page garde d'un rendu à
  // l'autre.
  function bindListbox(list, { ids, getFocus, setFocus, onChoose, onEscape = () => false }) {
    list.addEventListener("click", (event) => {
      const row = event.target.closest(".evo-row");
      if (row) onChoose(row.dataset.id, true);
    });
    list.addEventListener("keydown", (event) => {
      const all = ids();
      const at = all.indexOf(getFocus());
      let next = null;
      if (event.key === "ArrowDown") next = all[Math.min(at + 1, all.length - 1)];
      else if (event.key === "ArrowUp") next = all[Math.max(at - 1, 0)];
      else if (event.key === "Home") next = all[0];
      else if (event.key === "End") next = all[all.length - 1];
      else if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        onChoose(getFocus());
        return;
      } else if (event.key === "Escape") {
        if (onEscape()) document.getElementById(`row-${getFocus()}`)?.focus();
        return;
      }
      if (next === null || next === undefined) return;
      event.preventDefault();
      list.querySelectorAll(".evo-row").forEach((row) => (row.tabIndex = row.dataset.id === next ? 0 : -1));
      setFocus(next);
      const row = document.getElementById(`row-${next}`);
      row.focus();
      row.scrollIntoView({ block: "nearest" });
    });
  }

  // Le corps d'une comparaison de structures (la réponse d'un structure-diff : `summary` ou
  // `entries`, puis à part les étapes renommées, les paramètres déclarés et les étiquettes de couches).
  function diffBodyHtml(result) {
    let body;
    if (result.summary) body = result.summary.map((line) => `<div>${escapeHtml(line)}</div>`).join("") || "<div>Aucune différence de structure.</div>";
    else if (!result.entries.length) body = "<div>Aucune différence de structure.</div>";
    else {
      const n = result.entries.length;
      body =
        `<div style="font-family:var(--font-ui);font-weight:600;color:var(--abandoned);">${n} paramètre${n > 1 ? "s" : ""} modifié${n > 1 ? "s" : ""}</div>` +
        result.entries.map((e) => `<div>${escapeHtml(e.path)} : ${escapeHtml(JSON.stringify(e.before))} → ${escapeHtml(JSON.stringify(e.after))}</div>`).join("");
    }
    [
      ["Étapes", result.step_changes || []],
      ["Paramètres", result.param_changes || []],
      ["Étiquettes", result.label_changes || []],
    ].forEach(([key, changes]) => {
      if (changes.length) body += `<div class="evo-diff__labels"><strong>${key} :</strong> ${changes.map((c) => escapeHtml(c.line)).join(" ; ")}</div>`;
    });
    return body;
  }

  return { ROW, laneX, width, nodeShape, draw, laneTagsHtml, legendHtml, bindListbox, diffBodyHtml };
})();
