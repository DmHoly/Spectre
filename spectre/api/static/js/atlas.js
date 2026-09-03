/* Atlas : vue d'ensemble multi-projets - un cluster par projet, une bulle par étude (la pointe de
   chaque ligne de filiation, pas chaque version - voir GET /api/atlas / spectre.core.atlas), un
   petit point par échantillon physique suivi. Force-layout D3 plutôt que Plotly pour un vrai
   contrôle du zoom (affichage progressif des noms) et du clic (panneau contextuel) - voir la
   conversation de conception pour le pourquoi.

   Liens inter-projets (spectre.core.links) : la seule relation qui traverse deux projets - Follow
   refuse une référence pointée hors de son propre dépôt, donc ça ne pouvait pas vivre là. Dessinés
   en tirets accent par-dessus les clusters, créés/retirés depuis le panneau contextuel d'un projet
   ou d'une entité.

   Pièces jointes (spectre.api.experiments) : contrairement aux liens, ça enregistre une nouvelle
   version Follow (comme une étiquette ou le suivi physique) - l'id d'expérience/l'id de noeud
   change donc après un envoi ou un retrait. Le formulaire réutilise l'id renvoyé par l'upload pour
   resélectionner le bon noeud après refresh() plutôt que l'ancien id, devenu périmé.
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
const panelErrorBox = document.getElementById("panel-error");
let selection = null; // the currently-clicked node's datum, for the side panel
let currentAtlas = null; // the raw /api/atlas payload, for building link lists/pickers
let nodesById = new Map(); // rebuilt on every build() - project:*/experience-id/entity:*:* -> node

function projectColor(index) {
  return `var(--atlas-cat-${(index % 8) + 1})`;
}

function entityKey(ref) {
  return `entity:${ref.experience_id}:${ref.entity_index}`;
}

function matchesEntity(ref, d) {
  return ref.project_slug === d.projectSlug && ref.experience_id === d.experienceId && ref.entity_index === d.entityIndex;
}

function showPanelError(err) {
  panelErrorBox.textContent = err.message || String(err);
  panelErrorBox.style.display = "block";
}

function clearPanelError() {
  panelErrorBox.style.display = "none";
}

function panelEmptyState() {
  return `
    <div class="section-title" style="margin-bottom:10px;">Atlas</div>
    <p class="help">Chaque grande étiquette est un projet. Autour, une bulle par étude toujours en cours ou conclue - la ligne de filiation la plus récente, pas chaque version. Les petits points sont les échantillons physiques suivis. Cliquez un élément pour le détail ici ; zoomez pour voir les noms.</p>`;
}

async function uploadFile(url, formData) {
  // Deliberately not api.post(): that helper always JSON.stringifies its body and forces
  // Content-Type: application/json, both wrong for a multipart upload (the browser needs to set
  // its own Content-Type with the form's boundary). Same error-shape as api.js otherwise.
  const response = await fetch(url, { method: "POST", credentials: "same-origin", body: formData });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (e) {
      data = text;
    }
  }
  if (!response.ok) {
    const detail = data && typeof data === "object" ? data.detail : data;
    throw new Error(typeof detail === "string" ? detail : "Une erreur est survenue.");
  }
  return data;
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function attachmentItemHtml(a, projectSlug) {
  const url = `/api/projects/${encodeURIComponent(projectSlug)}/pieces-jointes/${encodeURIComponent(a.id)}`;
  const isImage = a.content_type.startsWith("image/");
  return `
    <div class="js-attachment-item" data-id="${a.id}" style="padding:8px 0;border-top:1px solid var(--border-soft);font-size:12.5px;">
      ${isImage ? `<a href="${url}" target="_blank" rel="noopener"><img src="${url}" alt="${escapeHtml(a.filename)}" style="max-width:100%;border-radius:var(--radius-sm);margin-bottom:6px;display:block;"></a>` : ""}
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
        <a href="${url}" target="_blank" rel="noopener" style="font-weight:600;word-break:break-all;">${escapeHtml(a.filename)}</a>
        ${deleteLinkButtonHtml("js-delete-attachment", a.id)}
      </div>
      <div style="color:var(--text-faint);margin-top:2px;">${formatFileSize(a.size)}</div>
    </div>`;
}

function attachmentUploadFormHtml() {
  return `
    <form id="attachment-upload-form" style="margin-top:12px;">
      <input class="field" type="file" id="attachment-file-input" required style="margin-bottom:8px;">
      <div class="help" style="margin-bottom:8px;">Image, PDF, CSV ou texte - 10 Mo maximum.</div>
      <button class="btn btn-line btn-block" type="submit">Ajouter un fichier</button>
    </form>`;
}

function deleteLinkButtonHtml(cls, id) {
  return `<button class="${cls}" data-id="${id}" type="button" title="Retirer le lien" style="background:none;border:none;cursor:pointer;color:var(--text-faint);padding:0;font-size:15px;line-height:1;flex:none;">&times;</button>`;
}

function renderProjectPanel(d) {
  const experienceCount = d.experiences.length;
  const entityCount = d.experiences.reduce((n, e) => n + e.entities.length, 0);
  const myLinks = (currentAtlas.project_links || []).filter((l) => l.a.slug === d.slug || l.b.slug === d.slug);
  const otherProjects = currentAtlas.projects.filter((p) => p.slug !== d.slug);

  const linksHtml = myLinks
    .map((l) => {
      const other = l.a.slug === d.slug ? l.b : l.a;
      return `
        <div style="padding:8px 0;border-top:1px solid var(--border-soft);font-size:12.5px;display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
          <div>
            <span style="font-weight:600;">${escapeHtml(other.name)}</span>
            ${l.note ? `<div style="color:var(--text-faint);margin-top:2px;">${escapeHtml(l.note)}</div>` : ""}
          </div>
          ${deleteLinkButtonHtml("js-delete-project-link", l.id)}
        </div>`;
    })
    .join("");

  panel.innerHTML = `
    <div class="section-title" style="margin-bottom:6px;">Projet</div>
    <h2 style="font-size:18px;margin:0 0 8px;">${escapeHtml(d.name)}</h2>
    ${d.description ? `<p style="font-size:13px;color:var(--text-soft);line-height:1.55;margin-bottom:12px;">${escapeHtml(d.description)}</p>` : ""}
    <div style="font-size:12.5px;color:var(--text-faint);margin-bottom:14px;">
      ${escapeHtml(roleLabel(d.role))} &middot; ${experienceCount} étude${experienceCount > 1 ? "s" : ""}${entityCount ? ` &middot; ${entityCount} entité${entityCount > 1 ? "s" : ""} physique${entityCount > 1 ? "s" : ""}` : ""}
    </div>
    <a class="btn btn-primary btn-block" href="/projets/${encodeURIComponent(d.slug)}">Ouvrir le projet &rarr;</a>

    <div class="section-title" style="margin:20px 0 8px;">Projets liés</div>
    ${myLinks.length ? linksHtml : `<div class="help">Aucun lien pour l'instant.</div>`}
    ${
      otherProjects.length
        ? `<form id="project-link-form" style="margin-top:12px;">
            <select class="field" id="project-link-select" style="margin-bottom:6px;">
              ${otherProjects.map((p) => `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}</option>`).join("")}
            </select>
            <input class="field" id="project-link-note" placeholder="Pourquoi ces deux projets se rejoignent (optionnel)" style="margin-bottom:8px;">
            <button class="btn btn-line btn-block" type="submit">Lier à ce projet</button>
          </form>`
        : `<div class="help" style="margin-top:10px;">Aucun autre projet à lier.</div>`
    }`;

  const form = document.getElementById("project-link-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearPanelError();
      try {
        await api.post("/api/liens-projets", {
          project_a: d.slug,
          project_b: document.getElementById("project-link-select").value,
          note: document.getElementById("project-link-note").value.trim(),
        });
        await refresh(`project:${d.slug}`);
      } catch (err) {
        showPanelError(err);
      }
    });
  }
  panel.querySelectorAll(".js-delete-project-link").forEach((btn) => {
    btn.addEventListener("click", async () => {
      clearPanelError();
      try {
        await api.del(`/api/liens-projets/${btn.dataset.id}`);
        await refresh(`project:${d.slug}`);
      } catch (err) {
        showPanelError(err);
      }
    });
  });
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
  const attachmentsHtml = d.attachments.map((a) => attachmentItemHtml(a, d.projectSlug)).join("");
  panel.innerHTML = `
    <div class="section-title" style="margin-bottom:6px;">Étude</div>
    <div style="margin-bottom:8px;">${statusBadgeHtml(d.status)}</div>
    <h2 style="font-size:17px;line-height:1.3;margin:0 0 8px;">${escapeHtml(d.title)}</h2>
    <p style="font-size:13px;color:var(--text-soft);line-height:1.55;margin-bottom:10px;">${escapeHtml(d.intent)}</p>
    ${d.conclusion_summary ? `<div style="font-size:12.5px;background:var(--bg);border-radius:var(--radius-sm);padding:8px 10px;line-height:1.5;margin-bottom:12px;">${escapeHtml(d.conclusion_summary)}</div>` : ""}
    ${objectives ? `<div style="margin-bottom:14px;">${objectives}</div>` : ""}
    <a class="btn btn-primary btn-block" href="/projets/${encodeURIComponent(d.projectSlug)}/experiences/${encodeURIComponent(d.id)}">Ouvrir la fiche &rarr;</a>

    <div class="section-title" style="margin:20px 0 8px;">Pièces jointes</div>
    ${d.attachments.length ? attachmentsHtml : `<div class="help">Aucune pièce jointe.</div>`}
    ${attachmentUploadFormHtml()}`;

  document.getElementById("attachment-upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearPanelError();
    const input = document.getElementById("attachment-file-input");
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    try {
      const result = await uploadFile(`/api/projects/${encodeURIComponent(d.projectSlug)}/experiences/${encodeURIComponent(d.id)}/pieces-jointes`, formData);
      await refresh(result.id);
    } catch (err) {
      showPanelError(err);
    }
  });
  panel.querySelectorAll(".js-delete-attachment").forEach((btn) => {
    btn.addEventListener("click", async () => {
      clearPanelError();
      try {
        const result = await api.del(`/api/projects/${encodeURIComponent(d.projectSlug)}/experiences/${encodeURIComponent(d.id)}/pieces-jointes/${btn.dataset.id}`);
        await refresh(result.id);
      } catch (err) {
        showPanelError(err);
      }
    });
  });
}

function populateEntityLinkExperienceSelect() {
  const projSlug = document.getElementById("entity-link-project-select").value;
  const proj = currentAtlas.projects.find((p) => p.slug === projSlug);
  const withEntities = (proj ? proj.experiences : []).filter((e) => e.entities.length > 0);
  const select = document.getElementById("entity-link-experience-select");
  select.innerHTML = withEntities.length
    ? withEntities.map((e) => `<option value="${escapeHtml(e.id)}">${escapeHtml(e.title)}</option>`).join("")
    : `<option value="">Aucune étude avec entité suivie</option>`;
  populateEntityLinkEntitySelect();
}

function populateEntityLinkEntitySelect() {
  const projSlug = document.getElementById("entity-link-project-select").value;
  const expId = document.getElementById("entity-link-experience-select").value;
  const proj = currentAtlas.projects.find((p) => p.slug === projSlug);
  const exp = proj ? proj.experiences.find((e) => e.id === expId) : null;
  const select = document.getElementById("entity-link-entity-select");
  select.innerHTML = exp
    ? exp.entities.map((ent) => `<option value="${ent.index}">${escapeHtml(ent.sample_id || ent.location || "Échantillon " + (ent.index + 1))}</option>`).join("")
    : "";
}

function renderEntityPanel(d) {
  const myLinks = (currentAtlas.entity_links || []).filter((l) => matchesEntity(l.a, d) || matchesEntity(l.b, d));
  const linksHtml = myLinks
    .map((l) => {
      const other = matchesEntity(l.a, d) ? l.b : l.a;
      const otherNode = nodesById.get(entityKey(other));
      const label = otherNode ? otherNode.sample_id || otherNode.location || "Échantillon" : "Échantillon";
      return `
        <div style="padding:8px 0;border-top:1px solid var(--border-soft);font-size:12.5px;display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
          <div>
            <span style="font-weight:600;">${escapeHtml(label)}</span>
            <div style="color:var(--text-faint);margin-top:2px;">${escapeHtml(other.project_slug)}${l.note ? " — " + escapeHtml(l.note) : ""}</div>
          </div>
          ${deleteLinkButtonHtml("js-delete-entity-link", l.id)}
        </div>`;
    })
    .join("");

  const hasAnyEntityElsewhere = currentAtlas.projects.some((p) => p.experiences.some((e) => e.entities.length > 0));
  const attachmentsHtml = d.attachments.map((a) => attachmentItemHtml(a, d.projectSlug)).join("");

  panel.innerHTML = `
    <div class="section-title" style="margin-bottom:6px;">Entité physique</div>
    <h2 style="font-size:17px;margin:0 0 10px;">${escapeHtml(d.sample_id || "Échantillon sans identifiant")}</h2>
    ${d.location ? `<div style="font-size:13px;color:var(--text-soft);margin-bottom:14px;">Emplacement&nbsp;: ${escapeHtml(d.location)}</div>` : ""}
    <div class="help" style="margin-bottom:10px;">Suivie sur l'étude :</div>
    <div style="font-size:13.5px;font-weight:600;margin-bottom:10px;">${escapeHtml(d.experienceTitle)}</div>
    <a class="btn btn-line btn-block" href="/projets/${encodeURIComponent(d.projectSlug)}/experiences/${encodeURIComponent(d.experienceId)}">Ouvrir la fiche &rarr;</a>

    <div class="section-title" style="margin:20px 0 8px;">Pièces jointes</div>
    ${d.attachments.length ? attachmentsHtml : `<div class="help">Aucune pièce jointe.</div>`}
    ${attachmentUploadFormHtml()}

    <div class="section-title" style="margin:20px 0 8px;">Entités liées</div>
    ${myLinks.length ? linksHtml : `<div class="help">Aucun lien pour l'instant.</div>`}
    ${
      hasAnyEntityElsewhere
        ? `<form id="entity-link-form" style="margin-top:12px;">
            <label style="font-size:11px;">Projet</label>
            <select class="field" id="entity-link-project-select" style="margin-bottom:6px;">
              ${currentAtlas.projects.map((p) => `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}</option>`).join("")}
            </select>
            <label style="font-size:11px;">Étude</label>
            <select class="field" id="entity-link-experience-select" style="margin-bottom:6px;"></select>
            <label style="font-size:11px;">Entité</label>
            <select class="field" id="entity-link-entity-select" style="margin-bottom:6px;"></select>
            <input class="field" id="entity-link-note" placeholder="Pourquoi ces deux échantillons se rejoignent (optionnel)" style="margin-bottom:8px;">
            <button class="btn btn-line btn-block" type="submit">Lier à cette entité</button>
          </form>`
        : `<div class="help" style="margin-top:10px;">Aucune autre entité suivie à lier pour l'instant.</div>`
    }`;

  document.getElementById("attachment-upload-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearPanelError();
    const input = document.getElementById("attachment-file-input");
    const file = input.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("entity_index", String(d.entityIndex));
    try {
      const result = await uploadFile(`/api/projects/${encodeURIComponent(d.projectSlug)}/experiences/${encodeURIComponent(d.experienceId)}/pieces-jointes`, formData);
      await refresh(entityKey({ experience_id: result.id, entity_index: d.entityIndex }));
    } catch (err) {
      showPanelError(err);
    }
  });
  panel.querySelectorAll(".js-delete-attachment").forEach((btn) => {
    btn.addEventListener("click", async () => {
      clearPanelError();
      try {
        const result = await api.del(`/api/projects/${encodeURIComponent(d.projectSlug)}/experiences/${encodeURIComponent(d.experienceId)}/pieces-jointes/${btn.dataset.id}`);
        await refresh(entityKey({ experience_id: result.id, entity_index: d.entityIndex }));
      } catch (err) {
        showPanelError(err);
      }
    });
  });

  const projectSelect = document.getElementById("entity-link-project-select");
  if (projectSelect) {
    projectSelect.addEventListener("change", populateEntityLinkExperienceSelect);
    document.getElementById("entity-link-experience-select").addEventListener("change", populateEntityLinkEntitySelect);
    populateEntityLinkExperienceSelect();

    document.getElementById("entity-link-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      clearPanelError();
      const bProjectSlug = projectSelect.value;
      const bExperienceId = document.getElementById("entity-link-experience-select").value;
      const bEntityIndexRaw = document.getElementById("entity-link-entity-select").value;
      if (!bExperienceId || bEntityIndexRaw === "") {
        showPanelError(new Error("Choisissez une étude et une entité à lier."));
        return;
      }
      try {
        await api.post("/api/liens-entites", {
          a: { project_slug: d.projectSlug, experience_id: d.experienceId, entity_index: d.entityIndex },
          b: { project_slug: bProjectSlug, experience_id: bExperienceId, entity_index: parseInt(bEntityIndexRaw, 10) },
          note: document.getElementById("entity-link-note").value.trim(),
        });
        await refresh(entityKey({ experience_id: d.experienceId, entity_index: d.entityIndex }));
      } catch (err) {
        showPanelError(err);
      }
    });
  }
  panel.querySelectorAll(".js-delete-entity-link").forEach((btn) => {
    btn.addEventListener("click", async () => {
      clearPanelError();
      try {
        await api.del(`/api/liens-entites/${btn.dataset.id}`);
        await refresh(entityKey({ experience_id: d.experienceId, entity_index: d.entityIndex }));
      } catch (err) {
        showPanelError(err);
      }
    });
  });
}

function select(datum, element) {
  selection = datum;
  clearPanelError();
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
  svg.selectAll("*").remove();
  nodesById = new Map();

  const projects = atlas.projects;
  if (projects.length === 0) {
    document.getElementById("atlas-empty").style.display = "";
    return;
  }
  document.getElementById("atlas-empty").style.display = "none";

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
        attachments: exp.attachments.filter((a) => a.entity_index === null),
        color: anchor.color,
        x: anchor.x + (Math.random() - 0.5) * 20,
        y: anchor.y + (Math.random() - 0.5) * 20,
      });
      exp.entities.forEach((entity) => {
        // entity.index is its position in the *raw* physical_tracking list (spectre.core.atlas's
        // entities_for()), not in this already-filtered array - the addressing links/attachments
        // use, so it has to survive some campaign variants being untracked.
        const entityId = `entity:${exp.id}:${entity.index}`;
        entityNodes.push({
          id: entityId,
          type: "entity",
          projectSlug: p.slug,
          experienceId: exp.id,
          experienceTitle: exp.title,
          entityIndex: entity.index,
          sample_id: entity.sample_id,
          location: entity.location,
          attachments: exp.attachments.filter((a) => a.entity_index === entity.index),
          x: anchor.x,
          y: anchor.y,
        });
        links.push({ source: entityId, target: exp.id, kind: "leash" });
      });
    });
    p.edges.forEach((e) => links.push({ source: e.from, target: e.to, kind: "derivation" }));
  });

  const allNodes = [...projectNodes, ...experienceNodes, ...entityNodes];
  allNodes.forEach((n) => nodesById.set(n.id, n));

  const resolvableEntityLinks = (atlas.entity_links || []).filter((l) => nodesById.has(entityKey(l.a)) && nodesById.has(entityKey(l.b)));
  const resolvableProjectLinks = (atlas.project_links || []).filter((l) => projectBySlug.has(l.a.slug) && projectBySlug.has(l.b.slug));

  const g = svg.append("g");
  const haloLayer = g.append("g");
  const edgeLayer = g.append("g");
  const crossLinkLayer = g.append("g");
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

  const projectLinkSelection = crossLinkLayer
    .selectAll("line.atlas-project-link")
    .data(resolvableProjectLinks)
    .join("line")
    .attr("class", "atlas-project-link")
    .attr("x1", (l) => projectBySlug.get(l.a.slug).fx)
    .attr("y1", (l) => projectBySlug.get(l.a.slug).fy)
    .attr("x2", (l) => projectBySlug.get(l.b.slug).fx)
    .attr("y2", (l) => projectBySlug.get(l.b.slug).fy);

  const entityLinkSelection = crossLinkLayer
    .selectAll("line.atlas-entity-link")
    .data(resolvableEntityLinks)
    .join("line")
    .attr("class", "atlas-entity-link");

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

    // Cross-project entity links aren't part of the force simulation (their two ends can belong
    // to unrelated clusters - pulling them together would fight the per-project clustering), so
    // their endpoints are just read live from whichever node they reference.
    entityLinkSelection
      .attr("x1", (l) => nodesById.get(entityKey(l.a)).x)
      .attr("y1", (l) => nodesById.get(entityKey(l.a)).y)
      .attr("x2", (l) => nodesById.get(entityKey(l.b)).x)
      .attr("y2", (l) => nodesById.get(entityKey(l.b)).y);

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

async function refresh(reselectId) {
  const atlas = await api.get("/api/atlas");
  currentAtlas = atlas;
  build(atlas);
  if (reselectId && nodesById.has(reselectId)) {
    select(nodesById.get(reselectId), null);
  } else {
    select(null, null);
  }
}

async function init() {
  select(null, null);
  try {
    await refresh(null);
  } catch (err) {
    panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
  }
}

init();
