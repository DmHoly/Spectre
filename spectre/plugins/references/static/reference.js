/* L'évolution d'une référence (pages/reference.html) : le diagramme des seules versions de
   référence (GET .../versions : une colonne par branche parallèle, une rangée par version 1.0,
   1.1, 2.0..., dessiné par experiments/static/evolution-graph.js comme l'évolution des structures
   d'un µprojet), le µprojet source et les usages de chaque version, les rattachements déduits à
   l'import des refs locales (trait pointillé) ; le panneau d'une version : sa structure étiquetée
   (le SVG du serveur), son auteur, sa date, sa note, sa source (un lien pour un membre du µprojet
   source), ses usages repliables, la comparer à une autre version, « Partir de cette version »
   (start-picker.js : le µprojet où lancer l'étude) ; renommer, décrire, retirer pour son créateur ou
   un admin (can_edit, calculé par le serveur). ?version=1.1 choisit une version. */

(() => {
  const { slug } = routeParams("/references/{slug}");
  const query = new URLSearchParams(window.location.search);

  const LEVEL_TEXT = {
    initial: "première",
    major: "majeur",
    minor: "mineur",
    patch: "correctif",
    none: "identique",
  };
  const LEVEL_LONG = {
    initial: "première version",
    major: "changement majeur",
    minor: "changement mineur",
    patch: "correctif (étiquettes, noms, unités)",
    none: "identique à sa parente (repère importé)",
  };

  const state = {
    graph: { reference: null, lanes: [], nodes: [], edges: [] },
    selected: query.get("version"),
    focus: null,
    compareFrom: null, // le numéro de départ d'une comparaison en cours
    diff: null, // {from, to, result}
    details: {}, // numéro -> la version lue (structure_svg...) ; undefined pendant la lecture, null en échec
    panelError: "",
  };

  const errorBox = document.getElementById("error");
  const rowsEl = document.getElementById("rows");
  const panel = document.getElementById("panel");

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }

  // -- adresses ------------------------------------------------------------------------------

  function syncUrl() {
    const params = state.selected ? `?version=${encodeURIComponent(state.selected)}` : "";
    window.history.replaceState(null, "", `${window.location.pathname}${params}`);
  }
  function studyUrl(microproject, experimentId, versionId) {
    const page = `/microprojets/${encodeURIComponent(microproject.slug)}/experiences/${encodeURIComponent(experimentId)}`;
    return versionId ? `${page}?version=${encodeURIComponent(versionId)}` : page;
  }

  // -- lecture -------------------------------------------------------------------------------

  const nodeOf = (number) => state.graph.nodes.find((node) => node.number === number) || null;
  const isHead = (node) => state.graph.lanes.some((lane) => lane.head === node.number);
  const reference = () => state.graph.reference;

  function sourceText(source) {
    const mp = source && source.microproject;
    if (!mp) return "µprojet inconnu";
    return `${mp.code ? `${mp.code} · ` : ""}${mp.name}${mp.deleted ? " (supprimé)" : ""}`;
  }

  // -- en-tête -------------------------------------------------------------------------------

  function renderHead() {
    const ref = reference();
    document.title = `${ref.name} · Références — Spectre`;
    document.getElementById("name-crumb").textContent = ref.name;
    document.getElementById("crumb").textContent = `/ Références / ${ref.name}`;
    document.getElementById("reference-name").textContent = ref.name;
    document.getElementById("reference-description").textContent = ref.description || "";
    const latest = ref.latest_version;
    const parts = [
      ref.created_by ? `Créée par ${ref.created_by.name}` : "Créée à l'import des refs locales",
      `le ${formatDate(ref.created_at)}`,
      `${ref.version_count} version${ref.version_count > 1 ? "s" : ""}`,
      ref.usage_count ? `${ref.usage_count} étude${ref.usage_count > 1 ? "s en sont parties" : " en est partie"}` : "aucune étude n'en est encore partie",
    ];
    if (latest) parts.push(`dernière mise à jour : ${latest.number} le ${formatDate(latest.published_at)}`);
    document.getElementById("reference-meta").textContent = parts.join(" · ");
    document.getElementById("head-actions").innerHTML = `
      ${latest ? `<button class="btn btn-primary js-start" type="button" data-number="${escapeHtml(latest.number)}">Partir de la dernière version (${escapeHtml(latest.number)})</button>` : ""}
      ${ref.can_edit ? `<button class="btn btn-line" type="button" id="edit-btn">Renommer / décrire</button><button class="btn btn-danger" type="button" id="remove-btn">Retirer</button>` : ""}`;
  }

  document.getElementById("head-actions").addEventListener("click", (event) => {
    const target = event.target.closest("button");
    if (!target) return;
    if (target.classList.contains("js-start")) startFrom(target.dataset.number);
    else if (target.id === "edit-btn") openEdit();
    else if (target.id === "remove-btn") openRemove();
  });

  // -- renommer, décrire, retirer --------------------------------------------------------------

  const editForm = document.getElementById("edit-form");
  function openEdit() {
    const ref = reference();
    document.getElementById("remove-confirm").hidden = true;
    document.getElementById("edit-name").value = ref.name;
    document.getElementById("edit-description").value = ref.description || "";
    editForm.hidden = false;
    document.getElementById("edit-name").focus();
  }
  document.getElementById("edit-cancel").addEventListener("click", () => (editForm.hidden = true));
  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await referencesApi.update(slug, {
        name: document.getElementById("edit-name").value.trim(),
        description: document.getElementById("edit-description").value.trim(),
      });
      editForm.hidden = true;
      showError(null);
      await load();
    } catch (err) {
      showError(err);
    }
  });

  function openRemove() {
    const ref = reference();
    editForm.hidden = true;
    const n = ref.version_count;
    document.getElementById("remove-confirm-text").textContent = n
      ? `Retirer la référence « ${ref.name} » ? Ses ${n} version${n > 1 ? "s" : ""} partent avec elle ; les études qui en sont parties garderont une origine inconnue.`
      : `Retirer la référence « ${ref.name} » ?`;
    document.getElementById("remove-confirm").hidden = false;
    document.getElementById("remove-cancel-btn").focus();
  }
  document.getElementById("remove-cancel-btn").addEventListener("click", () => (document.getElementById("remove-confirm").hidden = true));
  document.getElementById("remove-confirm-btn").addEventListener("click", async () => {
    try {
      await referencesApi.remove(slug);
      window.location.href = "/references";
    } catch (err) {
      document.getElementById("remove-confirm").hidden = true;
      showError(err);
    }
  });

  // -- le diagramme --------------------------------------------------------------------------

  function branchNote(node) {
    const edge = state.graph.edges.find((e) => e.child === node.number);
    if (!edge) return "";
    const notes = [];
    if (edge.kind === "branch") notes.push(`<span class="evo-row__fork">· branche depuis ${escapeHtml(edge.parent)}</span>`);
    if (edge.inferred) notes.push(`<span class="ref-row__inferred">· rattachement déduit</span>`);
    return notes.join(" ");
  }

  function rowLabel(node) {
    const edge = state.graph.edges.find((e) => e.child === node.number);
    const parts = [`version ${node.number}`, LEVEL_LONG[node.change_level] || node.change_level, `depuis ${sourceText(node.source)}`];
    if (edge) parts.push(`dérive de ${edge.parent}${edge.inferred ? " (rattachement déduit)" : ""}`);
    parts.push(`${node.usage_count} usage${node.usage_count > 1 ? "s" : ""}`);
    if (isHead(node)) parts.push("dernière version de sa branche");
    return parts.join(", ");
  }

  function renderGraph() {
    const { lanes, nodes, edges } = state.graph;
    const empty = nodes.length === 0;
    document.getElementById("graph-loading").hidden = true;
    document.getElementById("graph-empty").hidden = !empty;
    document.getElementById("graph-scroll").hidden = empty;
    document.getElementById("graph-foot").hidden = empty;
    if (empty) {
      rowsEl.innerHTML = "";
      return;
    }
    rowsEl.style.setProperty("--evo-graph-w", `${EvolutionGraph.width(lanes.length) + 8}px`);
    document.getElementById("lane-header").innerHTML = EvolutionGraph.laneTagsHtml(
      lanes.map((lane) => ({ lane: lane.index, text: String(lane.index + 1), title: `Branche partie de ${lane.start}` }))
    );
    EvolutionGraph.draw(document.getElementById("graph-svg"), {
      laneCount: lanes.length,
      nodes,
      edges,
      idOf: (node) => node.number,
      shapeOf: (node) => ({ change_level: node.change_level, is_tip: isHead(node) }),
      edgeClass: (edge) => (edge.inferred ? "evo-edge--inferred" : ""),
    });

    if (!state.focus || !nodeOf(state.focus)) state.focus = state.selected && nodeOf(state.selected) ? state.selected : nodes[nodes.length - 1].number;
    rowsEl.innerHTML = nodes
      .map((node) => {
        const source = node.source || {};
        const title = source.linked && source.title ? `${sourceText(source)} — ${source.title}` : sourceText(source);
        const compareTag = state.compareFrom === node.number ? `<span class="evo-compare-tag">A</span>` : "";
        return `
          <li class="evo-row" role="option" id="row-${escapeHtml(node.number)}" data-id="${escapeHtml(node.number)}"
              aria-selected="${node.number === state.selected}" tabindex="${node.number === state.focus ? 0 : -1}"
              aria-label="${escapeHtml(rowLabel(node))}" title="${escapeHtml(title)}">
            ${compareTag}
            <span class="evo-row__label">${escapeHtml(node.number)}</span>
            <span class="evo-row__level">${escapeHtml(LEVEL_TEXT[node.change_level] || node.change_level)}</span>
            <span class="evo-row__title">${escapeHtml(title)} ${branchNote(node)}</span>
            <span class="ref-row__usages">${node.usage_count ? `${node.usage_count} usage${node.usage_count > 1 ? "s" : ""}` : ""}</span>
            <span class="evo-row__meta">${escapeHtml(formatDate(node.published_at))}</span>
          </li>`;
      })
      .join("");

    document.getElementById("lane-list").innerHTML = lanes
      .map((lane) => `<li><span class="evo-lanes__tag">${lane.index + 1}</span><span>depuis <span class="ref-number">${escapeHtml(lane.start)}</span> · dernière <span class="ref-number">${escapeHtml(lane.head)}</span></span></li>`)
      .join("");
  }

  function renderLegend() {
    document.getElementById("legend").innerHTML =
      EvolutionGraph.legendHtml([
        [{ change_level: "major" }, "Première version ou changement majeur (X.0)"],
        [{ change_level: "minor" }, "Changement mineur (X.Y)"],
        [{ change_level: "patch" }, "Correctif : étiquettes, noms d'étape, unités (X.Y)"],
        [{ change_level: "none" }, "Identique à sa parente (repère importé)"],
        [{ change_level: "minor", is_tip: true }, "Dernière version d'une branche"],
      ]) + `<li><span class="ref-legend-edge" aria-hidden="true"></span>Rattachement déduit à l'import des refs locales</li>`;
  }

  function renderBanner() {
    const banner = document.getElementById("mode-banner");
    if (state.compareFrom) {
      document.getElementById("mode-banner-text").textContent = `Comparer la version ${state.compareFrom} : choisissez l'autre version dans le diagramme.`;
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

  async function loadDetail(number) {
    if (number in state.details) return;
    state.details[number] = undefined;
    try {
      state.details[number] = await referencesApi.version(slug, number);
    } catch (err) {
      state.details[number] = null;
    }
    if (state.selected === number) renderPanel();
  }

  function structureHtml(node) {
    const detail = state.details[node.number];
    if (detail === null) return `<p class="help">La structure de cette version n'a pas pu être dessinée.</p>`;
    const body = detail
      ? `<button type="button" class="evo-structure structure-zoomable js-enlarge" aria-label="Agrandir la structure de la version ${escapeHtml(node.number)}" title="Agrandir et zoomer">${detail.structure_svg || ""}${STRUCTURE_ZOOM_BADGE}</button>`
      : `<div class="skeleton" style="height:140px;"></div>`;
    return `<div class="evo-panel__section"><div class="section-title">Structure</div>${body}</div>`;
  }

  function sourceHtml(node) {
    const source = node.source || {};
    const mp = source.microproject || {};
    let study;
    if (source.linked) {
      study = `<a href="${studyUrl(mp, source.experiment_id, source.version_id)}">${escapeHtml(source.title || source.experiment_id)}</a> <span class="mono" style="font-size:11.5px;color:var(--text-faint);">${escapeHtml(source.experiment_id)}</span>`;
      if (source.local_tag) study += `<br>Repère local « ${escapeHtml(source.local_tag)} » de ce µprojet`;
    } else {
      study = mp.deleted ? "Le µprojet source a été supprimé." : "Vous n'êtes pas membre de ce µprojet : l'étude source n'est pas montrée.";
    }
    const edge = state.graph.edges.find((e) => e.child === node.number);
    const parent = edge
      ? `<br>Dérive de la version <span class="ref-number">${escapeHtml(edge.parent)}</span>${edge.inferred ? ` <span class="ref-row__inferred">(rattachement déduit à l'import : l'étude ne descend pas de cette version dans son µprojet)</span>` : ""}`
      : "";
    return `
      <div class="evo-panel__section">
        <div class="section-title">Source</div>
        <div class="ref-panel__source">µprojet ${escapeHtml(sourceText(source))}<br>${study}${parent}</div>
      </div>`;
  }

  function usagesHtml(node) {
    if (!node.usage_count) return `<div class="evo-panel__section"><div class="section-title">Usages</div><p class="help" style="margin:0;">Aucune étude n'est encore partie de cette version.</p></div>`;
    const items = node.usages
      .map((usage) => {
        const mp = usage.microproject || {};
        if (!usage.linked) return `<li>Une étude de ${escapeHtml(mp.name || "µprojet inconnu")}</li>`;
        return `<li><a href="${studyUrl(mp, usage.experiment_id)}">${escapeHtml(usage.title || usage.experiment_id)}</a> ${statusBadgeHtml(usage.status)}<br>${escapeHtml(sourceText(usage))} · ${escapeHtml(formatDate(usage.updated_at))}</li>`;
      })
      .join("");
    const n = node.usage_count;
    return `
      <div class="evo-panel__section">
        <div class="section-title">Usages</div>
        <details class="ref-usages">
          <summary>${n} étude${n > 1 ? "s en sont parties" : " en est partie"}</summary>
          <ul>${items}</ul>
        </details>
      </div>`;
  }

  function diffHtml() {
    const diff = state.diff;
    if (!diff || diff.to !== state.selected) return "";
    return `
      <div class="evo-panel__section">
        <div class="section-title">Comparaison ${escapeHtml(diff.from)} → ${escapeHtml(diff.to)}</div>
        <div class="evo-diff">${EvolutionGraph.diffBodyHtml(diff.result)}</div>
      </div>`;
  }

  function renderPanel() {
    const node = nodeOf(state.selected);
    if (!node) {
      panel.innerHTML = `<p class="help">Choisissez une version dans le diagramme (clic, ou flèches puis Entrée) pour voir sa structure, d'où elle vient, qui en est parti, la comparer ou partir d'elle.</p>`;
      return;
    }
    const edge = state.graph.edges.find((e) => e.child === node.number);
    const author = node.published_by ? node.published_by.name : node.imported ? "Repère importé" : "Auteur inconnu";
    panel.innerHTML = `
      <div class="ref-meta" style="margin:0 0 2px;">${escapeHtml(reference().name)}</div>
      <h2 class="evo-panel__title">Version <span class="ref-number">${escapeHtml(node.number)}</span></h2>
      <p class="evo-panel__meta">
        ${escapeHtml(LEVEL_LONG[node.change_level] || node.change_level)}${isHead(node) ? " · dernière de sa branche" : ""}<br>
        ${escapeHtml(author)} · ${escapeHtml(formatDate(node.published_at))}
      </p>
      ${node.note ? `<p class="ref-panel__note">${escapeHtml(node.note)}</p>` : ""}
      ${state.panelError ? `<div class="error" role="alert" style="margin:12px 0;">${escapeHtml(state.panelError)}</div>` : ""}
      <div class="evo-actions" style="margin-top:12px;">
        <button class="btn btn-primary js-start" type="button" data-number="${escapeHtml(node.number)}">Partir de cette version</button>
        <button class="btn btn-line js-compare" type="button">${state.compareFrom ? "Comparer à cette version" : "Comparer avec une autre version"}</button>
        ${edge ? `<button class="btn btn-line js-compare-parent" type="button">Comparer à sa parente (${escapeHtml(edge.parent)})</button>` : ""}
      </div>
      ${diffHtml()}
      ${structureHtml(node)}
      ${sourceHtml(node)}
      ${usagesHtml(node)}`;
    loadDetail(node.number);
  }

  function render() {
    renderGraph();
    renderBanner();
    renderPanel();
  }

  // -- actions -------------------------------------------------------------------------------

  function startFrom(number) {
    ReferenceStartPicker.open({
      reference: slug,
      version: number,
      intro: `Lancer une nouvelle expérience depuis « ${reference().name} » : choisissez le µprojet où la lancer. L'étude retiendra la version dont elle part.`,
    });
  }

  async function compare(from, to) {
    try {
      const result = await referencesApi.versionDiff(slug, to, from);
      state.diff = { from, to, result };
    } catch (err) {
      state.panelError = err.message || String(err);
    }
  }

  async function select(number, viaClick) {
    if (!nodeOf(number)) return;
    state.focus = number;
    state.panelError = "";
    if (state.compareFrom && state.compareFrom !== number) {
      const from = state.compareFrom;
      state.compareFrom = null;
      state.selected = number;
      await compare(from, number);
    } else {
      state.compareFrom = null;
      state.selected = number;
    }
    syncUrl();
    render();
    document.getElementById(`row-${number}`)?.focus();
    if (viaClick && window.matchMedia("(max-width: 1000px)").matches) panel.scrollIntoView({ block: "start" });
  }

  EvolutionGraph.bindListbox(rowsEl, {
    ids: () => state.graph.nodes.map((node) => node.number),
    getFocus: () => state.focus,
    setFocus: (number) => (state.focus = number),
    onChoose: select,
    onEscape: () => {
      if (!state.compareFrom) return false;
      state.compareFrom = null;
      render();
      return true;
    },
  });

  panel.addEventListener("click", async (event) => {
    const node = nodeOf(state.selected);
    const target = event.target.closest("button");
    if (!node || !target) return;
    if (target.classList.contains("js-start")) {
      startFrom(node.number);
    } else if (target.classList.contains("js-compare")) {
      state.diff = null;
      state.compareFrom = node.number;
      render();
      document.getElementById(`row-${node.number}`)?.focus();
    } else if (target.classList.contains("js-compare-parent")) {
      const edge = state.graph.edges.find((e) => e.child === node.number);
      if (!edge) return;
      await compare(edge.parent, node.number);
      renderPanel();
    } else if (target.classList.contains("js-enlarge")) {
      // en grand, pour zoomer sur ses détails (structure-zoom.js)
      const detail = state.details[node.number];
      if (detail && detail.structure_svg) openStructureZoom({ title: `${reference().name} ${node.number}`, items: [{ html: detail.structure_svg }] });
    }
  });

  // -- amorce ----------------------------------------------------------------------------------

  async function load() {
    state.graph = await referencesApi.versions(slug);
    if (state.selected && !nodeOf(state.selected)) state.selected = null;
    if (!state.selected && state.graph.nodes.length) state.selected = state.graph.nodes[state.graph.nodes.length - 1].number;
    renderHead();
    syncUrl();
    render();
  }

  renderLegend();
  load().catch((err) => {
    document.getElementById("graph-loading").hidden = true;
    document.getElementById("reference-name").textContent = err.status === 404 ? "Référence introuvable" : "Référence";
    showError(err);
  });
})();
