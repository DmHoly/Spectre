/* Vue par défaut du µprojet : le graphe hiérarchique "git-like" de ses expériences (un nœud =
   une version de structure d'une piste, un trait = un lien de filiation classique), plus la carte
   contextuelle qui s'ouvre au clic - voir GET /api/microprojects/{slug}/lineage
   (spectre.plugins.experiments.api::microproject_lineage). Un nœud n'est jamais une version parmi
   d'autres : seuls les racines, les fusions et les commits qui ont réellement fait avancer la structure sont gardés
   (spectre.plugins.experiments.versioning) - "un µprojet = split de structure". Remplace
   l'ancienne vue d'ensemble Plotly, supprimée : rendu D3 pour un vrai contrôle du layout et du
   clic, dans le même esprit qu'atlas.js.

   On prévoit aussi les expériences d'après sans quitter l'arbre (spectre.plugins.experiments.plans) :
   le « + » d'un nœud (ou « Prévoir la suite » sur sa carte) ouvre, dans la carte, un formulaire court
   - un titre, une intention, et ce qu'on continue : **les mêmes plaques** (des plaques de cette
   expérience, cochées, pour des tests supplémentaires) ou **de nouvelles plaques** (un nombre
   estimé). L'expérience prévue apparaît en pointillé, pastille « Prévu », reliée à son nœud ; sa
   carte la lance (le constructeur, prérempli : la structure est définie là, le split et les vraies
   plaques aussi), la modifie ou la supprime. planRoot() prévoit une racine (nouvelles plaques).

   Le layout et le dessin d'un nœud/trait vivent dans lineage-graph.js (chargé avant ce fichier) -
   partagés avec le mini-arbre qu'atlas.js affiche au clic sur une étude, pour resituer son
   contexte sans dupliquer l'algorithme (et sans collision de noms - voir la note dans ce fichier).

   mountLineage(el, {microprojectSlug, canEdit}) : `el` contient #lineage-svg, #lineage-empty et
   #lineage-panel ; `canEdit` (rôle editor ou owner) ouvre la prévision, le lancement et l'ajout à un
   lot. Renvoie {reload, planRoot}.
*/

function mountLineage(el, { microprojectSlug, canEdit = false }) {
  const slug = microprojectSlug;

  const NODE_RADIUS = 9;
  const COL_WIDTH = 150; // place pour le badge wafers (à gauche) et le badge lot (à droite) d'un nœud
  const ROW_HEIGHT = 100;
  const MARGIN = 56; // assez pour les libellés centrés sous les nœuds des bords
  const PLAN_PREFIX = "plan-"; // l'id d'un nœud prévisionnel dans le graphe : plan-<id>

  const svg = d3.select(el.querySelector("#lineage-svg"));
  const panel = el.querySelector("#lineage-panel");
  let selectedId = null;
  let positionedById = new Map(); // les nœuds dessinés, par id (réels et prévus)

  function panelEmptyState() {
    return `<p class="help">Cliquez un nœud pour voir la structure, l'objectif et la conclusion de cette expérience ici.</p>`;
  }

  // Un nœud est une version (version_id) d'une piste (experiment_id) : sa pointe, ou une version
  // passée de la piste - qu'on ouvre alors avec ?version=.
  function pageUrl(node, suffix = "") {
    const page = `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(node.experiment_id)}${suffix}`;
    return node.is_tip ? page : `${page}?version=${encodeURIComponent(node.version_id)}`;
  }

  // Lancer une expérience prévue (?prevision=<id> : l'éditeur la préremplit et la retire une fois
  // lancée) : partie de ses plaques (mêmes plaques), de la structure de sa version de départ
  // (nouvelles plaques), ou de rien (une racine) - dans le constructeur, ou en images.
  function planLaunchUrl(plan, { images = false } = {}) {
    const base = `/microprojets/${encodeURIComponent(slug)}`;
    const query = new URLSearchParams({ prevision: String(plan.id) });
    if (plan.mode === "same_wafers") {
      plan.wafers.forEach((mark) => query.append("plaque", mark));
      query.set("depuis-mp", slug);
      query.set("depuis-etude", plan.parent.experiment_id);
      query.set("depuis-version", plan.parent.version_id);
      return `${base}/structures/nouvelle?${query}`;
    }
    if (plan.parent) {
      query.set("version", plan.parent.version_id);
      return `${base}/experiences/${encodeURIComponent(plan.parent.experiment_id)}/${images ? "evoluer-image" : "evoluer"}?${query}`;
    }
    return `${base}/structures/${images ? "image" : "nouvelle"}?${query}`;
  }

  // La version de départ d'une prévision (ses plaques, sa structure) - celle d'un nœud, ou celle
  // qu'une prévision a retenue.
  function fetchVersion(experimentId, versionId) {
    return versionId ? experimentsApi.getVersion(slug, experimentId, versionId) : experimentsApi.get(slug, experimentId);
  }

  async function loadCard(node) {
    panel.innerHTML = `<p class="help">Chargement…</p>`;
    const version = node.is_tip ? null : node.version_id;
    try {
      const detail = await fetchVersion(node.experiment_id, version);
      let structureBlock;
      let variation = null;
      if (detail.is_batch) {
        try {
          variation = await experimentsApi.variants(slug, node.experiment_id, version);
          structureBlock = `<div id="lineage-structure-carousel"></div>`;
        } catch (err) {
          structureBlock = "";
        }
      } else if (detail.structure_images) {
        structureBlock = structureBoardHtml(detail.structure_images, { compact: true });
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

      panel.innerHTML = `
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;">
          <div class="section-title" style="margin-bottom:0;">${escapeHtml(detail.title)}</div>
          ${statusBadgeHtml(detail.status, detail.conclusion.decision)}
        </div>
        <p class="help" style="margin-bottom:10px;">${escapeHtml(detail.intent)}</p>
        ${fdlsOfTracking(detail.physical_tracking, detail.fdl).length ? `<div style="margin-bottom:10px;">${fdlChipsHtml(fdlsOfTracking(detail.physical_tracking, detail.fdl))}</div>` : ""}
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
          canEdit
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
          <a class="btn btn-line" style="flex:1;" href="${pageUrl(node)}">Ouvrir la fiche</a>
          ${canEdit ? `<button class="btn btn-primary" style="flex:1;" type="button" id="lineage-plan-next">Prévoir la suite</button>` : ""}
        </div>`;
      if (variation) renderLineageStructureCarousel(variation);
      if (canEdit) {
        panel.querySelector("#lineage-plan-next").addEventListener("click", () => renderPlanForm({ parent: { node, detail } }));
        if (pluginEnabled("lots")) {
          // mettre un wafer de l'expérience dans un lot (lot-picker.js) ; le badge suit dans le graphe
          mountLotAssign(panel.querySelector("#lineage-lot-assign"), {
            lasermarks: (detail.physical_tracking || []).map((e) => e.sample_id),
            onChange: () => loadLineage(),
          });
        }
      }
    } catch (err) {
      panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  // -- prévoir une expérience ----------------------------------------------------------------------

  // Les plaques qu'une prévision peut reprendre : celles que suit la version de départ (une par
  // variante pour une campagne - deux variantes ne partent pas ensemble).
  function trackedWafers(detail) {
    return (detail.physical_tracking || []).map((e, index) => ({ ...e, index })).filter((e) => e.sample_id);
  }

  function waferChecksHtml(detail, checked) {
    const keys = new Set(checked.map(waferKey));
    return trackedWafers(detail)
      .map(
        (e) => `<label class="plan-wafer">
          <input type="checkbox" value="${escapeHtml(e.sample_id)}" data-variant="${e.index}"${keys.has(waferKey(e.sample_id)) ? " checked" : ""}>
          <span class="plan-wafer__mark">${escapeHtml(e.sample_id)}</span>${detail.is_batch ? `<span class="plan-wafer__variant">variante ${e.index + 1}</span>` : ""}
        </label>`
      )
      .join("");
  }

  // Le formulaire, dans la carte : `parent` = {node, detail} (à la suite d'un nœud), `plan` = la
  // prévision qu'on modifie (sa version de départ est relue), rien = une nouvelle racine.
  async function renderPlanForm({ parent = null, plan = null } = {}) {
    let detail = parent ? parent.detail : null;
    if (plan && plan.parent && !detail) {
      panel.innerHTML = `<p class="help">Chargement…</p>`;
      try {
        detail = await fetchVersion(plan.parent.experiment_id, plan.parent.version_id);
      } catch (err) {
        detail = null; // la version de départ n'existe plus : seules les nouvelles plaques restent possibles
      }
    }
    const hasParent = Boolean(parent || (plan && plan.parent));
    const wafers = detail ? trackedWafers(detail) : [];
    const mode = plan ? plan.mode : "new_wafers";
    const sameAllowed = Boolean(detail) && wafers.length > 0;
    const parentLabel = detail ? `À la suite de « ${escapeHtml(detail.title)} »` : hasParent ? "La version de départ n'existe plus." : "Une nouvelle racine dans l'arbre.";
    panel.innerHTML = `
      <form class="plan-form" id="plan-form" novalidate>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
          <div class="section-title" style="margin-bottom:0;">${plan ? "Modifier la prévision" : "Prévoir une expérience"}</div>
          <span class="badge badge-planned"><span class="dot"></span>Prévisionnelle</span>
        </div>
        <p class="help" style="margin:4px 0 12px;">${parentLabel}</p>
        <div class="plan-form__field">
          <label for="plan-title">Titre</label>
          <input class="field" id="plan-title" maxlength="200" required placeholder="ex : Recuit d'activation Mg" value="${escapeHtml(plan ? plan.title : "")}">
        </div>
        <div class="plan-form__field">
          <label for="plan-intent">Intention</label>
          <textarea class="field" id="plan-intent" rows="3" maxlength="4000" placeholder="Ce que je veux démontrer">${escapeHtml(plan ? plan.intent : "")}</textarea>
        </div>
        ${
          hasParent
            ? `<fieldset class="plan-modes">
                <legend class="plan-form__legend">Plaques</legend>
                <label class="plan-mode${sameAllowed ? "" : " is-disabled"}">
                  <input type="radio" name="plan-mode" value="same_wafers"${mode === "same_wafers" ? " checked" : ""}${sameAllowed ? "" : " disabled"}>
                  <span class="plan-mode__body">
                    <span class="plan-mode__title">Mêmes plaques</span>
                    <span class="plan-mode__desc">${sameAllowed ? "Des tests supplémentaires sur une ou plusieurs plaques de cette expérience." : "Cette expérience ne suit aucune plaque."}</span>
                  </span>
                </label>
                <label class="plan-mode">
                  <input type="radio" name="plan-mode" value="new_wafers"${mode === "new_wafers" || !sameAllowed ? " checked" : ""}>
                  <span class="plan-mode__body">
                    <span class="plan-mode__title">Nouvelles plaques</span>
                    <span class="plan-mode__desc">Relancer de nouvelles plaques pour continuer l'étude, depuis cette structure.</span>
                  </span>
                </label>
              </fieldset>`
            : ""
        }
        <div class="plan-form__field" id="plan-same" hidden>
          <span class="plan-form__legend" id="plan-wafers-label">Plaques reprises</span>
          <div class="plan-wafers" role="group" aria-labelledby="plan-wafers-label">${detail ? waferChecksHtml(detail, plan && plan.mode === "same_wafers" ? plan.wafers : []) : ""}</div>
        </div>
        <div class="plan-form__field" id="plan-new" hidden>
          <label for="plan-count">Nombre de plaques prévu</label>
          <div class="plan-count">
            <input class="field" id="plan-count" type="number" min="1" max="200" step="1" inputmode="numeric" value="${plan && plan.wafer_count ? plan.wafer_count : ""}" placeholder="ex : 4">
            <span class="help" style="margin:0;">une estimation - les vraies plaques se nomment au lancement</span>
          </div>
        </div>
        <div class="error" id="plan-error" role="alert" style="display:none;"></div>
        <div class="plan-form__actions">
          <button class="btn btn-primary" type="submit">${plan ? "Enregistrer" : "Ajouter au prévisionnel"}</button>
          <button class="btn btn-line" type="button" id="plan-launch-now">Lancer maintenant</button>
        </div>
        <button class="btn-link-secondary" type="button" id="plan-cancel">Annuler</button>
      </form>`;

    const form = panel.querySelector("#plan-form");
    const errorEl = form.querySelector("#plan-error");
    const showFormError = (message) => {
      errorEl.textContent = message;
      errorEl.style.display = "block";
    };
    const currentMode = () => {
      const checked = form.querySelector('input[name="plan-mode"]:checked');
      return checked ? checked.value : "new_wafers";
    };
    const syncMode = () => {
      form.querySelector("#plan-same").hidden = currentMode() !== "same_wafers";
      form.querySelector("#plan-new").hidden = currentMode() !== "new_wafers";
    };
    form.querySelectorAll('input[name="plan-mode"]').forEach((input) => input.addEventListener("change", syncMode));
    syncMode();
    form.querySelector("#plan-title").focus();

    function collect() {
      errorEl.style.display = "none";
      const body = { title: form.querySelector("#plan-title").value.trim(), intent: form.querySelector("#plan-intent").value.trim(), mode: currentMode() };
      if (!body.title) {
        form.querySelector("#plan-title").focus();
        return showFormError("Donnez un titre à l'expérience prévue.");
      }
      if (body.mode === "same_wafers") {
        const checked = [...form.querySelectorAll(".plan-wafers input:checked")];
        if (!checked.length) return showFormError("Cochez au moins une plaque à reprendre.");
        if (detail.is_batch && new Set(checked.map((c) => c.dataset.variant)).size > 1) {
          return showFormError("Ces plaques portent des variantes différentes de la campagne : leurs structures diffèrent. Reprenez des plaques d'une même variante.");
        }
        body.wafers = checked.map((c) => c.value);
      } else {
        const count = parseInt(form.querySelector("#plan-count").value, 10);
        if (!(count >= 1 && count <= 200)) {
          form.querySelector("#plan-count").focus();
          return showFormError("Indiquez combien de plaques vous pensez lancer (entre 1 et 200).");
        }
        body.wafer_count = count;
      }
      return body;
    }

    async function save() {
      const body = collect();
      if (!body) return null;
      try {
        if (plan) return await experimentsApi.updatePlan(slug, plan.id, body);
        const source = parent ? { experiment_id: parent.detail.id, version_id: parent.detail.version_id } : null;
        return await experimentsApi.createPlan(slug, source ? { ...body, parent: source } : body);
      } catch (err) {
        showFormError(err.message || String(err));
        return null;
      }
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const saved = await save();
      if (!saved) return;
      selectedId = `${PLAN_PREFIX}${saved.id}`;
      await loadLineage();
    });
    form.querySelector("#plan-launch-now").addEventListener("click", async () => {
      const saved = await save();
      if (!saved) return;
      window.location.href = planLaunchUrl(saved, { images: Boolean(detail && detail.structure_images && saved.mode === "new_wafers") });
    });
    form.querySelector("#plan-cancel").addEventListener("click", () => {
      if (plan) return loadPlanCard(positionedById.get(`${PLAN_PREFIX}${plan.id}`) || { plan });
      if (parent) return loadCard(parent.node);
      panel.innerHTML = panelEmptyState();
    });
  }

  // La carte d'une expérience prévue : ce qu'elle continue, et la lancer, la modifier, la supprimer.
  async function loadPlanCard(node) {
    const plan = node.plan;
    let detail = null;
    if (plan.parent) {
      panel.innerHTML = `<p class="help">Chargement…</p>`;
      detail = await fetchVersion(plan.parent.experiment_id, plan.parent.version_id).catch(() => null);
    }
    const orphan = Boolean(plan.parent) && !detail;
    const parentLine = plan.parent
      ? detail
        ? `À la suite de <button class="btn-link-secondary plan-card__parent" type="button" id="plan-parent-link">« ${escapeHtml(detail.title)} »</button>`
        : `<span style="color:var(--danger);">La version de départ n'existe plus.</span>`
      : "Une nouvelle racine dans l'arbre.";
    const wafersBlock =
      plan.mode === "same_wafers"
        ? `<div class="plan-card__wafers"><span class="plan-card__mode">Mêmes plaques</span>${plan.wafers.map((w) => `<span class="plan-wafer__mark">${escapeHtml(w)}</span>`).join("")}</div>`
        : `<div class="plan-card__wafers"><span class="plan-card__mode">Nouvelles plaques</span><strong class="plan-card__count">~${plan.wafer_count}</strong><span class="help" style="margin:0;">prévue${plan.wafer_count > 1 ? "s" : ""}</span></div>`;
    const imagesLaunch = plan.mode === "new_wafers" && !orphan;
    const launchImages = Boolean(detail && detail.structure_images);
    panel.innerHTML = `
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:6px;">
        <div class="section-title" style="margin-bottom:0;">${escapeHtml(plan.title)}</div>
        <span class="badge badge-planned"><span class="dot"></span>Prévisionnelle</span>
      </div>
      ${plan.intent ? `<p class="help" style="margin-bottom:10px;">${escapeHtml(plan.intent)}</p>` : ""}
      <p style="font-size:12.5px;color:var(--text-soft);margin-bottom:10px;">${parentLine}</p>
      ${wafersBlock}
      <p class="help" style="margin-top:10px;">Pas encore de structure, de split ni de plaques réelles : on les définit au lancement.</p>
      <div style="font-size:12px;color:var(--text-faint);margin-top:12px;padding-top:10px;border-top:1px solid var(--border-soft);">
        Prévue par ${escapeHtml(plan.author || "un membre")} &middot; ${timeAgo(plan.created_at)}
      </div>
      ${
        canEdit
          ? `<div style="display:flex;gap:8px;margin-top:14px;">
              ${orphan && plan.mode === "same_wafers" ? "" : `<a class="btn btn-primary" style="flex:1;" href="${planLaunchUrl(plan, { images: launchImages })}">Lancer</a>`}
              <button class="btn btn-line" style="flex:1;" type="button" id="plan-edit">Modifier</button>
            </div>
            ${
              imagesLaunch
                ? `<a class="btn-link-secondary" style="display:inline-block;margin-top:8px;" href="${planLaunchUrl(plan, { images: !launchImages })}">${launchImages ? "ou lancer dans le constructeur" : "ou lancer avec une structure en images"}</a>`
                : ""
            }
            <button class="btn-link-secondary plan-card__delete" type="button" id="plan-delete">Supprimer la prévision</button>`
          : ""
      }`;
    const parentLink = panel.querySelector("#plan-parent-link");
    if (parentLink) parentLink.addEventListener("click", () => selectNode(node.parentNodeId));
    if (!canEdit) return;
    panel.querySelector("#plan-edit").addEventListener("click", () => renderPlanForm({ plan, parent: detail && positionedById.get(node.parentNodeId) ? { node: positionedById.get(node.parentNodeId), detail } : null }));
    panel.querySelector("#plan-delete").addEventListener("click", async () => {
      if (!window.confirm(`Supprimer l'expérience prévue « ${plan.title} » ?`)) return;
      try {
        await experimentsApi.removePlan(slug, plan.id);
        selectedId = null;
        panel.innerHTML = panelEmptyState();
        await loadLineage();
      } catch (err) {
        panel.insertAdjacentHTML("beforeend", `<div class="error" style="margin-top:10px;">${escapeHtml(err.message || String(err))}</div>`);
      }
    });
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

  // Même carrousel (référence + chaque variante) que l'atlas et la fiche (voir
  // structures/static/campaign-carousel.js::mountStructureCarousel) - avant ça, une campagne cliquée ici ne montrait qu'un texte « Campagne —
  // N variantes. », sans jamais voir la structure elle-même ni pouvoir comparer les variantes.
  function renderLineageStructureCarousel(variation) {
    mountStructureCarousel(panel.querySelector("#lineage-structure-carousel"), variation);
  }

  function highlight(id) {
    svg.selectAll(".lineage-node").classed("lineage-node-selected", false);
    if (id) svg.select(`.lineage-node[data-id="${CSS.escape(id)}"]`).classed("lineage-node-selected", true);
  }

  // Sélectionner un nœud (réel ou prévu) : sa carte ; `andPlan` ouvre aussitôt la prévision de la suite.
  async function selectNode(id, { andPlan = false } = {}) {
    const node = positionedById.get(id);
    if (!node) return;
    selectedId = id;
    highlight(id);
    if (node.is_plan) return loadPlanCard(node);
    if (!andPlan) return loadCard(node);
    panel.innerHTML = `<p class="help">Chargement…</p>`;
    try {
      const detail = await fetchVersion(node.experiment_id, node.is_tip ? null : node.version_id);
      renderPlanForm({ parent: { node, detail } });
    } catch (err) {
      panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  function render(nodes, edges, plans) {
    const real = new Set(nodes.map((n) => n.id));
    const planNodes = plans.map((plan) => ({
      id: `${PLAN_PREFIX}${plan.id}`,
      is_plan: true,
      plan,
      title: plan.title,
      created_at: plan.created_at,
      parentNodeId: plan.parent_node && real.has(plan.parent_node) ? plan.parent_node : null,
    }));
    const allNodes = [...nodes, ...planNodes];
    const allEdges = [...edges, ...planNodes.filter((p) => p.parentNodeId).map((p) => ({ parent: p.parentNodeId, child: p.id, planned: true }))];

    el.querySelector("#lineage-empty").style.display = allNodes.length ? "none" : "";
    if (!allNodes.length) {
      svg.selectAll("*").remove();
      positionedById = new Map();
      return;
    }

    const { positioned, width, height } = lineageLayout(allNodes, allEdges, { colWidth: COL_WIDTH, rowHeight: ROW_HEIGHT, margin: MARGIN });
    const byId = new Map(positioned.map((n) => [n.id, n]));
    positionedById = byId;

    svg.attr("width", width).attr("height", height).attr("viewBox", `0 0 ${width} ${height}`);
    svg.selectAll("*").remove();

    svg
      .append("g")
      .selectAll("path")
      .data(allEdges)
      .join("path")
      .attr("class", (e) => `lineage-edge${e.planned ? " is-planned" : ""}`)
      .attr("d", (e) => lineageEdgePath(byId.get(e.parent), byId.get(e.child)));

    const nodeGroups = svg
      .append("g")
      .selectAll("g")
      .data(positioned)
      .join("g")
      .attr("class", (d) => `lineage-node${d.is_plan ? " is-planned" : ""}`)
      .attr("transform", (d) => `translate(${d.x},${d.y})`)
      .attr("data-id", (d) => d.id)
      .attr("tabindex", 0)
      .attr("role", "button")
      .attr("aria-label", (d) => (d.is_plan ? `Prévue : ${d.title} · ${lineagePlanWafersLabel(d.plan)}` : lineageNodeTooltip(d).replace(/\n/g, " · ")))
      .on("click", (event, d) => selectNode(d.id))
      .on("keydown", (event, d) => {
        if (event.target !== event.currentTarget || (event.key !== "Enter" && event.key !== " ")) return;
        event.preventDefault();
        selectNode(d.id);
      });

    nodeGroups.each(function (d) {
      d3.select(this).html(d.is_plan ? lineagePlanShapeHtml({ radius: NODE_RADIUS }) : lineageNodeShapeHtml(d, { radius: NODE_RADIUS }));
      d3.select(this)
        .append("title")
        .text(d.is_plan ? `${d.title}\nPrévisionnelle · ${lineagePlanWafersLabel(d.plan)}` : lineageNodeTooltip(d));
    });

    nodeGroups
      .append("text")
      .attr("class", "lineage-label")
      .attr("y", NODE_RADIUS + 16)
      .attr("text-anchor", "middle")
      .text((d) => (d.title.length > 16 ? d.title.slice(0, 15) + "…" : d.title));

    // Pastille « Prévu » à droite d'une expérience prévue (à la place du badge de lot d'un nœud réel).
    nodeGroups
      .filter((d) => d.is_plan)
      .append("g")
      .attr("class", "lineage-planned-pill")
      .attr("transform", `translate(${NODE_RADIUS + 9},${-NODE_RADIUS - 6})`)
      .call((pill) => {
        pill.append("rect").attr("width", 40).attr("height", 15).attr("rx", 7.5);
        pill.append("text").attr("x", 20).attr("y", 10.5).attr("text-anchor", "middle").text("PRÉVU");
      });

    // Badge du lot (suivi de lots) à droite du nœud : l'expérience suit un wafer de ce lot. Lien
    // vers le lot - un clic dessus ne sélectionne pas le nœud.
    nodeGroups
      .filter((d) => d.lots && d.lots.length)
      .each(function (d) {
        const first = d.lots[0];
        const code = first.code.length > 11 ? `${first.code.slice(0, 10)}…` : first.code;
        const text = d.lots.length > 1 ? `${code} +${d.lots.length - 1}` : code;
        const width = text.length * 6 + 12;
        const active = first.is_active;
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

    // Temps écoulé du début à la fin (ou à maintenant, « depuis… », tant qu'elle n'est pas terminée) ;
    // pour une expérience prévue, ses plaques (« ~4 plaques prévues », « 2 plaques reprises »).
    nodeGroups
      .append("text")
      .attr("class", (d) => (d.is_plan ? "lineage-duration is-planned" : `lineage-duration${{ ongoing: " is-ongoing", hold: " is-hold" }[lineageSpan(d).state] || ""}`))
      .attr("y", NODE_RADIUS + 30)
      .attr("text-anchor", "middle")
      .text((d) => (d.is_plan ? lineagePlanWafersLabel(d.plan) : lineageElapsedLabel(d)));

    // « + » à droite d'un nœud réel : prévoir une expérience à sa suite, sans quitter l'arbre.
    if (canEdit) {
      nodeGroups
        .filter((d) => !d.is_plan)
        .append("g")
        .attr("class", "lineage-add")
        .attr("transform", `translate(${NODE_RADIUS + 12},${NODE_RADIUS - 2})`)
        .attr("tabindex", 0)
        .attr("role", "button")
        .attr("aria-label", (d) => `Prévoir une expérience à la suite de ${d.title}`)
        .on("click", (event, d) => {
          event.stopPropagation();
          selectNode(d.id, { andPlan: true });
        })
        .on("keydown", (event, d) => {
          if (event.key !== "Enter" && event.key !== " ") return;
          event.preventDefault();
          event.stopPropagation();
          selectNode(d.id, { andPlan: true });
        })
        .call((add) => {
          add.append("title").text("Prévoir une expérience à la suite");
          add.append("circle").attr("r", 10).attr("class", "lineage-add__hit");
          add.append("circle").attr("r", 7.5).attr("class", "lineage-add__disc");
          add.append("path").attr("d", "M-3.5,0 H3.5 M0,-3.5 V3.5");
        });
    }

    if (selectedId && byId.has(selectedId)) highlight(selectedId);
  }

  // Les lots (lotsApi, en une requête) qui contiennent un wafer de chaque nœud : son badge de lot.
  async function attachLots(nodes) {
    const marks = [...new Set(nodes.flatMap((n) => n.wafers || []))];
    const lots = marks.length && pluginEnabled("lots") ? await lotsApi.list({ wafer: marks.map(waferKey), view: "summary" }) : [];
    nodes.forEach((node) => {
      const keys = new Set((node.wafers || []).map(waferKey));
      node.lots = lots.filter((l) => l.wafers.some((w) => keys.has(w.key)));
    });
  }

  async function loadLineage() {
    try {
      const body = await experimentsApi.lineage(slug);
      await attachLots(body.nodes);
      render(body.nodes, body.edges, body.plans || []);
      // une prévision tout juste enregistrée : sa carte
      if (selectedId && selectedId.startsWith(PLAN_PREFIX) && positionedById.has(selectedId)) loadPlanCard(positionedById.get(selectedId));
    } catch (err) {
      panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  // « Prévoir une expérience » (en-tête de la page) : une racine, sur de nouvelles plaques.
  function planRoot() {
    selectedId = null;
    highlight(null);
    renderPlanForm();
    panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  loadLineage();
  return { reload: loadLineage, planRoot };
}
