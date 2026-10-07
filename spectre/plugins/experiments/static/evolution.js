/* Évolution des structures d'un µprojet (pages/evolution.html) : le diagramme façon git de
   GET .../structure-history - une colonne par piste, une rangée par version, les fourches et les
   combinaisons (une version à deux parents : une nouvelle piste issue de deux études, ou une
   fusion d'avant, sur la piste de son premier parent) -, et le panneau d'une version : ses refs
   locales (renommer, retirer - des repères du µprojet), les versions de référence publiées depuis
   elle (badges « R nom 1.1 », referencesApi.publishedFrom ; une version publiée qui serait masquée
   est demandée en plus, include_versions), « Publier comme référence »
   (references/static/publish-dialog.js), la comparer à une autre (structure-diff), partir d'elle
   (l'éditeur sur ?version=, une nouvelle piste), suivre une ref (ses descendants en évidence), voir
   sa structure (étiquettes de couches comprises, agrandie au clic ; une structure en images : sa
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
    patch: "correctif",
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
    follow: query.get("suivre"), // le nom de la ref suivie
    editing: null, // {kind: "rename" | "remove", ref}
    flash: "",
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
    if (state.follow) params.set("suivre", state.follow);
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
  function followedNode() {
    return state.follow ? state.history.nodes.find((node) => node.refs.includes(state.follow)) || null : null;
  }
  // la version suivie et tout ce qui en descend (fourches et combinaisons comprises)
  function followedSet() {
    const start = followedNode();
    if (!start) return null;
    const seen = new Set([start.version_id]);
    const queue = [start.version_id];
    while (queue.length) {
      const id = queue.shift();
      state.history.edges.forEach((edge) => {
        if (edge.parent === id && !seen.has(edge.child)) {
          seen.add(edge.child);
          queue.push(edge.child);
        }
      });
    }
    return seen;
  }

  // -- dessin (evolution-graph.js) -------------------------------------------------------------

  // les versions de référence publiées depuis une version (badges « R nom 1.1 »)
  function publishedOf(node) {
    return state.published.filter((entry) => entry.version_id === node.version_id);
  }
  function badgesHtml(node) {
    const refs = node.refs.map((name) => `<span class="evo-ref">${escapeHtml(name)}</span>`);
    const published = publishedOf(node).map((entry) => `<span class="ref-badge" title="Version de référence">${escapeHtml(entry.label)}</span>`);
    return published.concat(refs).join("");
  }

  function rowLabel(node, index) {
    const lane = laneOf(node);
    const parts = [node.label, LEVEL_TEXT[node.change_level] || node.change_level, node.title, `piste ${lane.experiment_id}`];
    if (node.is_merge) parts.push(`combinaison${mergeParents(node, index) ? ` de ${mergeParents(node, index)}` : ""}`);
    if (node.refs.length) parts.push(`refs : ${node.refs.join(", ")}`);
    if (publishedOf(node).length) parts.push(`publiée comme ${publishedOf(node).map((entry) => entry.label.replace(/^R /, "référence ")).join(", ")}`);
    if (node.is_tip) parts.push("dernière version de la piste");
    return parts.join(", ");
  }

  // Les deux parents d'une combinaison, « v1.2.0 (piste 1) et v2.0.0 (piste 2) » ; "" sinon.
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
    const followed = followedSet();
    rowsEl.style.setProperty("--evo-graph-w", `${EvolutionGraph.width(lanes.length) + 8}px`);

    document.getElementById("lane-header").innerHTML = EvolutionGraph.laneTagsHtml(
      lanes.map((lane) => ({ lane: lane.index, text: String(lane.index + 1), title: lane.experiment_id, retired: !lane.is_active }))
    );

    EvolutionGraph.draw(document.getElementById("graph-svg"), {
      laneCount: lanes.length,
      nodes,
      edges,
      idOf: (node) => node.version_id,
      shapeOf: (node) => ({ ...node, marked: node.refs.length > 0 || publishedOf(node).length > 0 }),
      nodeClass: (node) => (followed && !followed.has(node.version_id) ? "is-dimmed" : ""),
      edgeClass: (edge) => {
        const inFollow = followed && followed.has(edge.parent) && followed.has(edge.child);
        return inFollow ? "is-followed" : followed ? "is-dimmed" : "";
      },
    });

    if (!state.focusId || !index.has(state.focusId)) state.focusId = state.selectedId && index.has(state.selectedId) ? state.selectedId : nodes[nodes.length - 1].version_id;
    rowsEl.innerHTML = nodes
      .map((node) => {
        const lane = laneOf(node);
        const compareTag = state.compareFrom && state.compareFrom.version_id === node.version_id ? `<span class="evo-compare-tag">A</span>` : "";
        const dimmed = followed && !followed.has(node.version_id) ? " is-dimmed" : "";
        return `
          <li class="evo-row${dimmed}" role="option" id="row-${node.version_id}" data-id="${node.version_id}"
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
      [{ change_level: "patch" }, "Correctif (nom d'étape, étiquette de couche)"],
      [{ change_level: "none" }, "Sans changement de structure"],
      [{ change_level: "none", is_merge: true }, "Combinaison de deux études (deux parents)"],
      [{ change_level: "minor", marked: true }, "Porte une ref ou une version de référence"],
      [{ change_level: "minor", is_tip: true }, "Dernière version d'une piste"],
    ]);
  }

  // -- bandeau de mode (comparaison, suivi d'une ref) ------------------------------------------

  function renderBanner() {
    const banner = document.getElementById("mode-banner");
    const text = document.getElementById("mode-banner-text");
    const cancel = document.getElementById("mode-banner-cancel");
    if (state.compareFrom) {
      text.textContent = `Comparer ${state.compareFrom.label} (${state.compareFrom.experiment_id}) : choisissez l'autre version dans le diagramme.`;
      cancel.textContent = "Annuler la comparaison";
      banner.hidden = false;
    } else if (followedNode()) {
      const descendants = followedSet().size - 1;
      text.textContent = `Vous suivez la ref « ${state.follow} » : ${descendants} version${descendants > 1 ? "s" : ""} affichée${descendants > 1 ? "s" : ""} en descend${descendants > 1 ? "ent" : ""}.`;
      cancel.textContent = "Arrêter de suivre";
      banner.hidden = false;
    } else {
      banner.hidden = true;
    }
  }

  document.getElementById("mode-banner-cancel").addEventListener("click", () => {
    if (state.compareFrom) state.compareFrom = null;
    else state.follow = null;
    syncUrl();
    render();
  });

  // -- le panneau ----------------------------------------------------------------------------

  const PENCIL = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>`;
  const CROSS = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>`;

  function refRowHtml(name) {
    const editing = state.editing && state.editing.ref === name ? state.editing.kind : null;
    if (editing === "rename") {
      return `
        <form class="evo-inline-form js-rename-form" data-ref="${escapeHtml(name)}">
          <input class="field" name="name" value="${escapeHtml(name)}" aria-label="Nouveau nom de la ref ${escapeHtml(name)}" required>
          <button class="btn btn-primary" type="submit">Renommer</button>
          <button class="btn btn-line js-cancel-edit" type="button">Annuler</button>
        </form>`;
    }
    if (editing === "remove") {
      return `
        <div class="evo-panel__ref">
          <span>Retirer la ref <span class="evo-ref">${escapeHtml(name)}</span> ? La version reste.</span>
          <button class="btn btn-danger js-confirm-remove" type="button" data-ref="${escapeHtml(name)}">Retirer</button>
          <button class="btn btn-line js-cancel-edit" type="button">Annuler</button>
        </div>`;
    }
    const tools = state.canEdit
      ? `<button class="evo-icon-btn js-rename" type="button" data-ref="${escapeHtml(name)}" aria-label="Renommer la ref ${escapeHtml(name)}" title="Renommer">${PENCIL}</button>
         <button class="evo-icon-btn evo-icon-btn--danger js-remove" type="button" data-ref="${escapeHtml(name)}" aria-label="Retirer la ref ${escapeHtml(name)}" title="Retirer">${CROSS}</button>`
      : "";
    const following = state.follow === name;
    return `
      <div class="evo-panel__ref">
        <span class="evo-ref">${escapeHtml(name)}</span>
        ${tools}
        <button class="btn btn-line js-follow" type="button" data-ref="${escapeHtml(name)}" aria-pressed="${following}" style="min-height:30px;padding:3px 10px;font-size:12px;">
          ${following ? "Ne plus suivre" : "Suivre cette ref"}
        </button>
      </div>`;
  }

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
  // couches comprises, « Agrandir » l'ouvre en grand) ou, pour une structure en images, sa première
  // image avec ses annotations (structure-images.js, un clic l'ouvre). Lue une fois par version.
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
      body = `<button type="button" class="evo-structure js-enlarge" aria-label="Agrandir la structure de ${escapeHtml(node.label)}" title="Agrandir">${shown.svg}</button>`;
    } else if (shown) {
      body = structureBoardHtml(shown.images, { compact: true });
    }
    return `
      <div class="evo-panel__section">
        <div class="section-title">Structure${node.structure_kind === "campaign" ? " · référence" : ""}</div>
        ${body}
      </div>`;
  }

  const structureDialog = document.getElementById("structure-dialog");
  document.getElementById("structure-dialog-close").addEventListener("click", () => structureDialog.close());

  function renderPanel() {
    const node = nodeById(state.selectedId);
    if (!node) {
      panel.innerHTML = `<p class="help">Choisissez une version dans le diagramme (clic, ou flèches puis Entrée) pour voir son détail, la comparer, la publier comme référence ou partir d'elle.</p>`;
      return;
    }
    const lane = laneOf(node);
    const level = node.is_merge ? "combinaison" : LEVEL_TEXT[node.change_level] || node.change_level;
    const refs = node.refs.map(refRowHtml).join("");
    panel.innerHTML = `
      <div class="page-eyebrow">${escapeHtml(lane.experiment_id)}</div>
      <h2 class="evo-panel__title">${escapeHtml(node.title)}</h2>
      <p class="evo-panel__meta">
        <span class="mono" style="font-weight:600;color:var(--accent-dark);">${escapeHtml(node.label)}</span> · ${escapeHtml(level)}${node.is_tip ? " · dernière version" : ""}<br>
        ${escapeHtml(node.author || "Auteur inconnu")} · ${escapeHtml(formatDate(node.created_at))}
      </p>
      ${state.flash ? `<div class="flash flash-ok" role="status">${state.flash}</div>` : ""}
      ${state.panelError ? `<div class="error" role="alert" style="margin-bottom:12px;">${escapeHtml(state.panelError)}</div>` : ""}
      <div class="evo-actions">
        <a class="btn btn-primary" href="${fichUrl(node)}">Ouvrir la fiche</a>
        <button class="btn btn-line js-compare" type="button">${state.compareFrom ? "Comparer à cette version" : "Comparer avec une autre version"}</button>
        ${state.canEdit ? `<a class="btn btn-line" href="${forkUrl(node)}" title="Ouvre l'éditeur sur cette version : enregistrer crée une nouvelle piste qui en part (ou continue la piste depuis sa dernière version)">Partir de cette version</a>` : ""}
      </div>
      ${diffHtml()}
      ${structureHtml(node)}
      ${referencesHtml(node)}
      ${
        refs
          ? `<div class="evo-panel__section">
               <div class="section-title">Refs locales</div>
               <p class="help" style="margin:0 0 6px;">Des repères propres au µprojet. Pour partager une structure entre µprojets, publiez-la comme référence.</p>
               <div class="evo-panel__refs">${refs}</div>
             </div>`
          : ""
      }`;
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
    if (state.follow && !followedNode()) state.follow = null;
    syncUrl();
    render();
  }

  // une écriture depuis le panneau : en cas de succès, le graphe est relu et `message` affiché
  async function act(call, message) {
    state.panelError = "";
    try {
      const result = await call();
      state.editing = null;
      state.flash = typeof message === "function" ? message(result) : message;
      await load();
    } catch (err) {
      state.panelError = err.message || String(err);
      renderPanel();
    }
  }

  async function select(id) {
    const node = nodeById(id);
    if (!node) return;
    state.focusId = id;
    state.flash = "";
    state.panelError = "";
    state.editing = null;
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
    } else if (target.classList.contains("js-follow")) {
      state.follow = state.follow === target.dataset.ref ? null : target.dataset.ref;
      syncUrl();
      render();
    } else if (target.classList.contains("js-rename") || target.classList.contains("js-remove")) {
      state.editing = { kind: target.classList.contains("js-rename") ? "rename" : "remove", ref: target.dataset.ref };
      renderPanel();
      panel.querySelector(".js-rename-form input, .js-confirm-remove")?.focus();
    } else if (target.classList.contains("js-cancel-edit")) {
      state.editing = null;
      renderPanel();
    } else if (target.classList.contains("js-publish")) {
      openPublish(node);
    } else if (target.classList.contains("js-confirm-remove")) {
      const name = target.dataset.ref;
      act(() => experimentsApi.deleteRef(slug, name), `Ref « ${escapeHtml(name)} » retirée ; la version reste.`);
    }
  });

  panel.addEventListener("click", (event) => {
    const enlarge = event.target.closest(".js-enlarge");
    if (!enlarge) return;
    const node = nodeById(state.selectedId);
    document.getElementById("structure-dialog-title").textContent = node ? `${node.title} · ${node.label}` : "Structure";
    document.getElementById("structure-dialog-body").innerHTML = enlarge.innerHTML;
    structureDialog.showModal();
  });

  panel.addEventListener("submit", (event) => {
    event.preventDefault();
    const node = nodeById(state.selectedId);
    const form = event.target;
    if (!node) return;
    if (form.classList.contains("js-rename-form")) {
      const old = form.dataset.ref;
      const name = form.elements.name.value.trim();
      act(
        () => experimentsApi.renameRef(slug, old, name),
        (ref) => {
          if (state.follow === old) state.follow = ref.name; // on suit la même ref sous son nouveau nom
          return `Ref renommée en « ${escapeHtml(ref.name)} ».`;
        }
      );
    }
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

  panel.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.editing) {
      state.editing = null;
      renderPanel();
    }
  });

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
      const followed = followedNode();
      if (followed) {
        state.selectedId = followed.version_id;
        state.focusId = followed.version_id;
        render();
      }
    } catch (err) {
      document.getElementById("graph-loading").hidden = true;
      showError(err);
    }
  }

  init();
})();
