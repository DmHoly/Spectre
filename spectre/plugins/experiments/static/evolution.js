/* Évolution des structures d'un µprojet (pages/evolution.html) : le diagramme façon git de
   GET .../structure-history - une colonne par piste, une rangée par version, les fourches et les
   combinaisons (une version à deux parents : une nouvelle piste issue de deux études, ou une
   fusion d'avant, sur la piste de son premier parent) -, et le panneau d'une version : les
   versions de référence publiées depuis elle (badges « R nom 1.1 », referencesApi.publishedFrom ; une version publiée qui serait masquée
   est demandée en plus, include_versions), « Publier comme référence »
   (references/static/publish-dialog.js), la comparer à une autre (structure-diff), partir d'elle
   (l'éditeur sur ?version=, une nouvelle piste), voir sa structure (étiquettes de couches comprises, agrandie au clic ; une structure en images : sa
   première image, annotations comprises). Le dessin est celui d'evolution-graph.js, partagé avec la
   page d'une référence. Le serveur donne tout ce qui est dessiné : numéros, niveaux, pistes, arêtes ;
   la page ne fait que poser chaque chose à sa place.

   Clavier : la liste des versions est une seule étape de tabulation ; flèches haut et bas (Début,
   Fin) pour s'y déplacer, Entrée ou Espace pour choisir, Échap pour annuler une comparaison. */

(() => {
  const { slug } = routeParams("/microprojets/{slug}/evolution");
  const query = new URLSearchParams(window.location.search);

  const LEVEL_TEXT = {
    initial: "première",
    major: "majeur",
    minor: "mineur",
    patch: "retouche",
    none: "sans changement",
  };

  const state = {
    microproject: null,
    canEdit: false,
    allVersions: query.get("toutes") === "1",
    history: { lanes: [], nodes: [], edges: [] },
    published: [], // les versions de référence publiées depuis le µprojet (referencesApi.publishedFrom)
    selectedId: null,
    focusId: null,
    compareFrom: null, // la version de départ d'une comparaison en cours
    diff: null, // {fromId, toId, result} : la dernière comparaison, montrée avec sa cible
    panelError: "",
    // version_id -> {svg} (le dessin, étiquettes de couches comprises) ou {images} (une structure en
    // images, annotations comprises) ; undefined pendant la lecture, null sans rien à montrer
    structures: {},
    origins: {}, // version_id -> reference_origin de la version (lu avec sa structure)
  };

  const errorBox = document.getElementById("error");
  const rowsEl = document.getElementById("rows");
  const panel = document.getElementById("panel");

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }

  // -- adresses ------------------------------------------------------------------------------

  function microprojectUrl() {
    return `/microprojets/${encodeURIComponent(slug)}`;
  }
  function fichUrl(node) {
    const page = `${microprojectUrl()}/experiences/${encodeURIComponent(node.experiment_id)}`;
    return node.is_tip ? page : `${page}?version=${encodeURIComponent(node.version_id)}`;
  }
  function forkUrl(node) {
    const mode = node.structure_kind === "images" ? "evoluer-image" : node.structure_kind === "declared" ? "evoluer-sans-structure" : "evoluer";
    return `${microprojectUrl()}/experiences/${encodeURIComponent(node.experiment_id)}/${mode}?version=${encodeURIComponent(node.version_id)}`;
  }
  function syncUrl() {
    const params = new URLSearchParams();
    if (state.allVersions) params.set("toutes", "1");
    const text = params.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${text ? `?${text}` : ""}`);
  }

  // -- lecture du graphe ---------------------------------------------------------------------

  function nodeById(id) {
    return state.history.nodes.find((node) => node.version_id === id) || null;
  }
  function laneOf(node) {
    return state.history.lanes[node.lane];
  }
  // -- dessin (evolution-graph.js) -------------------------------------------------------------

  // les versions de référence publiées depuis une version (badges « R nom 1.1 »)
  function publishedOf(node) {
    return state.published.filter((entry) => entry.version_id === node.version_id);
  }
  function badgesHtml(node) {
    return publishedOf(node)
      .map((entry) => `<span class="ref-badge" title="Version de référence">${escapeHtml(entry.label)}</span>`)
      .join("");
  }

  function rowLabel(node, index) {
    const lane = laneOf(node);
    const parts = [node.label, LEVEL_TEXT[node.change_level] || node.change_level, node.title, `piste ${lane.experiment_id}`];
    if (node.is_merge) parts.push(`combinaison${mergeParents(node, index) ? ` de ${mergeParents(node, index)}` : ""}`);
    if (publishedOf(node).length) parts.push(`publiée comme ${publishedOf(node).map((entry) => entry.label.replace(/^R /, "référence ")).join(", ")}`);
    if (node.is_tip) parts.push("dernière version de la piste");
    return parts.join(", ");
  }

  // Les deux parents d'une combinaison, « v1.2 (piste 1) et v2.0 (piste 2) » ; "" sinon.
  function mergeParents(node, index) {
    if (!node.is_merge) return "";
    const parents = state.history.edges
      .filter((edge) => edge.child === node.version_id)
      .map((edge) => index.get(edge.parent))
      .filter(Boolean)
      .map(({ node: parent }) => `${parent.label} (piste ${laneOf(parent).index + 1})`);
    return parents.length > 1 ? parents.join(" et ") : "";
  }

  function forkNote(node, index) {
    const parents = mergeParents(node, index);
    if (parents) return `<span class="evo-row__fork">· issue de ${escapeHtml(parents)}</span>`;
    const fork = state.history.edges.find((edge) => edge.child === node.version_id && edge.kind === "fork");
    if (!fork) return "";
    const from = index.get(fork.parent);
    return from ? `<span class="evo-row__fork">· nouvelle piste depuis ${escapeHtml(from.node.label)}</span>` : "";
  }

  function renderGraph() {
    const { lanes, nodes, edges } = state.history;
    const empty = nodes.length === 0;
    document.getElementById("graph-loading").hidden = true;
    document.getElementById("graph-empty").hidden = !empty;
    document.getElementById("graph-scroll").hidden = empty;
    document.getElementById("graph-foot").hidden = empty;
    if (empty) {
      rowsEl.innerHTML = "";
      return;
    }

    const index = new Map(nodes.map((node, row) => [node.version_id, { node, row }]));
    rowsEl.style.setProperty("--evo-graph-w", `${EvolutionGraph.width(lanes.length) + 8}px`);

    document.getElementById("lane-header").innerHTML = EvolutionGraph.laneTagsHtml(
      lanes.map((lane) => ({ lane: lane.index, text: String(lane.index + 1), title: lane.experiment_id, retired: !lane.is_active }))
    );

    EvolutionGraph.draw(document.getElementById("graph-svg"), {
      laneCount: lanes.length,
      nodes,
      edges,
      idOf: (node) => node.version_id,
      shapeOf: (node) => ({ ...node, marked: publishedOf(node).length > 0 }),
    });

    if (!state.focusId || !index.has(state.focusId)) state.focusId = state.selectedId && index.has(state.selectedId) ? state.selectedId : nodes[nodes.length - 1].version_id;
    rowsEl.innerHTML = nodes
      .map((node) => {
        const lane = laneOf(node);
        const compareTag = state.compareFrom && state.compareFrom.version_id === node.version_id ? `<span class="evo-compare-tag">A</span>` : "";
        return `
          <li class="evo-row" role="option" id="row-${node.version_id}" data-id="${node.version_id}"
              aria-selected="${node.version_id === state.selectedId}" tabindex="${node.version_id === state.focusId ? 0 : -1}"
              aria-label="${escapeHtml(rowLabel(node, index))}" title="${escapeHtml(node.title)}">
            ${compareTag}
            <span class="evo-row__label">${escapeHtml(node.label)}</span>
            <span class="evo-row__level">${escapeHtml(node.is_merge ? "combinaison" : LEVEL_TEXT[node.change_level] || "")}</span>
            <span class="evo-row__title">${escapeHtml(node.title)} ${forkNote(node, index)}</span>
            <span class="evo-row__refs">${badgesHtml(node)}</span>
            <span class="evo-row__meta" title="Piste ${escapeHtml(lane.experiment_id)}"><span class="evo-lanes__tag evo-lanes__tag--inline${lane.is_active ? "" : " is-retired"}">${lane.index + 1}</span> ${escapeHtml(formatDate(node.created_at))}</span>
          </li>`;
      })
      .join("");

    renderLaneList();
  }

  function renderLaneList() {
    document.getElementById("lane-list").innerHTML = state.history.lanes
      .map((lane) => {
        const name = lane.is_active
          ? `<a class="mono" href="${microprojectUrl()}/experiences/${encodeURIComponent(lane.experiment_id)}">${escapeHtml(lane.experiment_id)}</a>`
          : `<span class="mono">${escapeHtml(lane.experiment_id)}</span>`;
        const where = lane.is_active ? `pointe ${escapeHtml(lane.tip_label)}` : "piste supprimée";
        return `<li><span class="evo-lanes__tag${lane.is_active ? "" : " is-retired"}">${lane.index + 1}</span>${name}<span>${escapeHtml(lane.title)} · ${where}</span></li>`;
      })
      .join("");
  }

  function renderLegend() {
    document.getElementById("legend").innerHTML = EvolutionGraph.legendHtml([
      [{ change_level: "major" }, "Première version ou changement majeur"],
      [{ change_level: "minor" }, "Changement mineur"],
      [{ change_level: "patch" }, "Retouche, même numéro (nom d'étape, étiquette de couche)"],
      [{ change_level: "none" }, "Sans changement de structure"],
      [{ change_level: "none", is_merge: true }, "Combinaison de deux études (deux parents)"],
      [{ change_level: "minor", marked: true }, "Publiée comme version de référence"],
      [{ change_level: "minor", is_tip: true }, "Dernière version d'une piste"],
    ]);
  }

  // -- bandeau de mode (comparaison) ------------------------------------------

  function renderBanner() {
    const banner = document.getElementById("mode-banner");
    const text = document.getElementById("mode-banner-text");
    const cancel = document.getElementById("mode-banner-cancel");
    if (state.compareFrom) {
      text.textContent = `Comparer ${state.compareFrom.label} (${state.compareFrom.experiment_id}) : choisissez l'autre version dans le diagramme.`;
      cancel.textContent = "Annuler la comparaison";
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  }

  document.getElementById("mode-banner-cancel").addEventListener("click", () => {
    state.compareFrom = null;
    render();
  });

  // -- le panneau ----------------------------------------------------------------------------

  function diffHtml() {
    const diff = state.diff;
    if (!diff || diff.toId !== state.selectedId) return "";
    const from = nodeById(diff.fromId);
    const to = nodeById(diff.toId);
    const title = `${escapeHtml(from ? from.label : "?")} → ${escapeHtml(to ? to.label : "?")}`;
    const body = EvolutionGraph.diffBodyHtml(diff.result);
    return `
      <div class="evo-panel__section">
        <div class="section-title">Comparaison ${title}</div>
        <div class="evo-diff">${body}</div>
      </div>`;
  }

  // Les versions de référence publiées depuis cette version, et « Publier comme référence » (une
  // structure dessinée seulement : ni des images, ni une campagne).
  function referencesHtml(node) {
    const published = publishedOf(node)
      .map(
        (entry) =>
          `<a class="ref-badge" href="/references/${encodeURIComponent(entry.reference.slug)}?version=${encodeURIComponent(entry.number)}" title="Voir l'évolution de la référence">${escapeHtml(entry.label)}</a>`
      )
      .join(" ");
    const canPublish = state.canEdit && node.structure_kind === "process" && node.has_process && pluginEnabled("references");
    if (!published && !canPublish) return "";
    return `
      <div class="evo-panel__section">
        <div class="section-title">Références</div>
        ${published ? `<div class="evo-panel__refs">${published}</div>` : `<p class="help" style="margin:0 0 8px;">Pas encore publiée comme référence.</p>`}
        ${canPublish ? `<button class="btn btn-tint js-publish" type="button" style="margin-top:8px;">Publier comme référence</button>` : ""}
      </div>`;
  }

  // La structure de la version choisie, telle que la fiche la montre : le dessin (étiquettes de
  // couches comprises) ou, pour une structure en images, sa première image avec ses annotations
  // (structure-images.js) ; un clic l'ouvre en grand, pour zoomer (structure-zoom.js). Lue une fois
  // par version.
  async function loadStructure(node) {
    if (node.version_id in state.structures) return;
    state.structures[node.version_id] = undefined;
    let shown = null;
    try {
      const detail = await experimentsApi.getVersion(slug, node.experiment_id, node.version_id);
      state.origins[node.version_id] = detail.reference_origin;
      if (detail.structure_svg) shown = { svg: detail.structure_svg };
      else if ((detail.structure_images || []).length) shown = { images: detail.structure_images };
    } catch (err) {
      shown = null; // la structure est secondaire ici : le reste du panneau suffit
    }
    state.structures[node.version_id] = shown;
    if (state.selectedId === node.version_id) renderPanel();
  }

  function structureHtml(node) {
    const shown = state.structures[node.version_id];
    if (shown === null) return "";
    let body = `<div class="skeleton" style="height:120px;"></div>`;
    if (shown && shown.svg) {
      body = `<button type="button" class="evo-structure structure-zoomable js-enlarge" aria-label="Agrandir la structure de ${escapeHtml(node.label)}" title="Agrandir et zoomer">${shown.svg}${STRUCTURE_ZOOM_BADGE}</button>`;
    } else if (shown) {
      body = structureBoardHtml(shown.images, { compact: true, zoomable: true });
    }
    return `
      <div class="evo-panel__section">
        <div class="section-title">Structure${node.structure_kind === "campaign" ? " · référence" : ""}</div>
        ${body}
      </div>`;
  }

  function renderPanel() {
    const node = nodeById(state.selectedId);
    if (!node) {
      panel.innerHTML = `<p class="help">Choisissez une version dans le diagramme (clic, ou flèches puis Entrée) pour voir son détail, la comparer, la publier comme référence ou partir d'elle.</p>`;
      return;
    }
    const lane = laneOf(node);
    const level = node.is_merge ? "combinaison" : LEVEL_TEXT[node.change_level] || node.change_level;
    panel.innerHTML = `
      <div class="page-eyebrow">${escapeHtml(lane.experiment_id)}</div>
      <h2 class="evo-panel__title">${escapeHtml(node.title)}</h2>
      <p class="evo-panel__meta">
        <span class="mono" style="font-weight:600;color:var(--accent-dark);">${escapeHtml(node.label)}</span> · ${escapeHtml(level)}${node.is_tip ? " · dernière version" : ""}<br>
        ${escapeHtml(node.author || "Auteur inconnu")} · ${escapeHtml(formatDate(node.created_at))}
      </p>
      ${state.panelError ? `<div class="error" role="alert" style="margin-bottom:12px;">${escapeHtml(state.panelError)}</div>` : ""}
      <div class="evo-actions">
        <a class="btn btn-primary" href="${fichUrl(node)}">Ouvrir la fiche</a>
        <button class="btn btn-line js-compare" type="button">${state.compareFrom ? "Comparer à cette version" : "Comparer avec une autre version"}</button>
        ${state.canEdit ? `<a class="btn btn-line" href="${forkUrl(node)}" title="Ouvre l'éditeur sur cette version : enregistrer crée une nouvelle piste qui en part (ou continue la piste depuis sa dernière version)">Partir de cette version</a>` : ""}
      </div>
      ${diffHtml()}
      ${structureHtml(node)}
      ${referencesHtml(node)}`;
    loadStructure(node);
  }

  function render() {
    renderGraph();
    renderBanner();
    renderPanel();
  }

  // -- actions -------------------------------------------------------------------------------

  async function load() {
    // les versions publiées comme référence se montrent même légères (include_versions) ; aucune
    // sans le plugin references
    state.published = pluginEnabled("references") ? await referencesApi.publishedFrom(slug) : [];
    state.history = await experimentsApi.structureHistory(slug, state.allVersions, state.published.map((entry) => entry.version_id));
    if (state.selectedId && !nodeById(state.selectedId)) state.selectedId = null;
    if (state.compareFrom && !nodeById(state.compareFrom.version_id)) state.compareFrom = null;
    syncUrl();
    render();
  }

  async function select(id) {
    const node = nodeById(id);
    if (!node) return;
    state.focusId = id;
    state.panelError = "";
    if (state.compareFrom && state.compareFrom.version_id !== id) {
      const from = state.compareFrom;
      state.compareFrom = null;
      state.selectedId = id;
      try {
        const result = await experimentsApi.structureDiff(slug, node.experiment_id, {
          version: node.version_id,
          against_experiment: from.experiment_id,
          against_version: from.version_id,
        });
        state.diff = { fromId: from.version_id, toId: id, result };
      } catch (err) {
        state.panelError = err.message || String(err);
      }
    } else {
      state.compareFrom = null;
      state.selectedId = id;
    }
    render();
    document.getElementById(`row-${id}`)?.focus();
  }

  EvolutionGraph.bindListbox(rowsEl, {
    ids: () => state.history.nodes.map((node) => node.version_id),
    getFocus: () => state.focusId,
    setFocus: (id) => (state.focusId = id),
    onChoose: async (id, viaClick) => {
      await select(id);
      // une colonne (écran étroit) : le panneau est sous le diagramme, on l'amène à la vue
      if (viaClick && window.matchMedia("(max-width: 1000px)").matches) panel.scrollIntoView({ block: "start" });
    },
    onEscape: () => {
      if (!state.compareFrom) return false;
      state.compareFrom = null;
      render();
      return true;
    },
  });

  panel.addEventListener("click", (event) => {
    const node = nodeById(state.selectedId);
    const target = event.target.closest("button");
    if (!node || !target) return;
    if (target.classList.contains("js-compare")) {
      state.diff = null;
      state.compareFrom = node;
      render();
      document.getElementById(`row-${node.version_id}`)?.focus();
    } else if (target.classList.contains("js-publish")) {
      openPublish(node);
    }
  });

  panel.addEventListener("click", (event) => {
    const node = nodeById(state.selectedId);
    const shown = node && state.structures[node.version_id];
    if (!shown) return;
    const title = `${node.title} · ${node.label}`;
    if (shown.svg && event.target.closest(".js-enlarge")) openStructureZoom({ title, items: [{ html: shown.svg }] });
    else if (shown.images && event.target.closest(".structure-thumb")) enlargeStructureImages(event, title, shown.images);
  });

  // « Publier comme référence » : la référence proposée est celle dont vient l'étude (son origine,
  // lue avec la structure de la version) ; publiée, la page se relit (badges « R nom 1.1 »)
  async function openPublish(node) {
    if (!(node.version_id in state.origins)) {
      try {
        const detail = await experimentsApi.getVersion(slug, node.experiment_id, node.version_id);
        state.origins[node.version_id] = detail.reference_origin;
      } catch (err) {
        state.origins[node.version_id] = null;
      }
    }
    // les versions dont elle descend (à travers les versions masquées, comme les arêtes)
    const ancestors = new Set();
    const queue = [node.version_id];
    while (queue.length) {
      const id = queue.shift();
      state.history.edges.forEach((edge) => {
        if (edge.child === id && !ancestors.has(edge.parent)) {
          ancestors.add(edge.parent);
          queue.push(edge.parent);
        }
      });
    }
    ReferencePublishDialog.open({
      microprojectSlug: slug,
      experimentId: node.experiment_id,
      versionId: node.version_id,
      origin: state.origins[node.version_id],
      ancestors,
      onPublished: () => load().catch(showError),
    });
  }

  function setAllVersions(value) {
    state.allVersions = value;
    document.getElementById("show-all").classList.toggle("active", value);
    document.getElementById("show-all").setAttribute("aria-pressed", String(value));
    document.getElementById("show-structural").classList.toggle("active", !value);
    document.getElementById("show-structural").setAttribute("aria-pressed", String(!value));
  }
  document.getElementById("show-structural").addEventListener("click", () => {
    setAllVersions(false);
    load().catch(showError);
  });
  document.getElementById("show-all").addEventListener("click", () => {
    setAllVersions(true);
    load().catch(showError);
  });

  // -- amorce ----------------------------------------------------------------------------------

  function renderHeader(microproject) {
    const area = microproject.area;
    const thematic = microproject.thematic;
    const areaCrumb = document.getElementById("area-crumb");
    if (area) {
      areaCrumb.textContent = area.name;
      areaCrumb.href = `/management/${encodeURIComponent(area.slug)}`;
    } else {
      areaCrumb.textContent = "Non classé";
    }
    document.getElementById("thematic-crumb").innerHTML =
      thematic && area
        ? ` / <a href="/management/${encodeURIComponent(area.slug)}/thematiques/${encodeURIComponent(thematic.slug)}">${escapeHtml(thematic.name)}</a>`
        : thematic
          ? ` / ${escapeHtml(thematic.name)}`
          : "";
    const crumb = document.getElementById("microproject-crumb");
    crumb.textContent = microproject.name;
    crumb.href = microprojectUrl();
    if (microproject.code) {
      const code = document.getElementById("microproject-code");
      code.textContent = `µprojet ${microproject.code}`;
      code.hidden = false;
    }
    document.getElementById("crumb").textContent = `/ ${microproject.code || microproject.name} / évolution`;
    document.title = `Évolution des structures · ${microproject.name} — Spectre`;
  }

  async function init() {
    setAllVersions(state.allVersions);
    renderLegend();
    try {
      const microproject = await microprojectsApi.get(slug);
      state.microproject = microproject;
      state.canEdit = Boolean(microproject.can_edit);
      renderHeader(microproject);
      await load();
    } catch (err) {
      document.getElementById("graph-loading").hidden = true;
      showError(err);
    }
  }

  init();
})();
