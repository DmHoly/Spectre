/* Fiche d'identité d'une expérience : en-tête, frise chronologique, structure actuelle (+diff),
   objectifs, conclusion (ou formulaire pour la rédiger), comparaison avec une autre expérience. */

const pathParts = window.location.pathname.split("/").filter(Boolean);
const slug = pathParts[1];
const experienceId = pathParts[3];

const REFERENCE_ROLE_LABELS = {
  baseline: "Référence",
  control: "Témoin",
  prior_art: "Antériorité",
  benchmark: "Point de comparaison",
  target_spec: "Spécification cible",
  merge_source: "Source combinée",
};

const OBJECTIVE_STATUS_LABELS = {
  met: "Atteint",
  not_met: "Non atteint",
  partially_met: "Partiellement atteint",
  inconclusive: "Non concluant",
};

const EVIDENCE_KIND_LABELS = {
  standard: "Standard",
  image: "Image",
  graph: "Graphique",
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

let currentRole = null;
let currentProjectName = null;
let currentDetail = null;
let currentProcess = null; // {substrate, steps} from /process - absent for structures without an
// editable StructureForge recipe recorded (e.g. a campaign's representative entry).

function isEditorRole() {
  return currentRole === "editor" || currentRole === "owner";
}

function objectiveResultFor(detail, objectiveName) {
  return (detail.conclusion.objective_results || []).find((r) => r.objective === objectiveName);
}

function renderHeader(detail) {
  document.getElementById("status-badge").innerHTML = statusBadgeHtml(detail.status);
  document.getElementById("exp-title").textContent = detail.title;
  document.getElementById("exp-intent").textContent = detail.intent;
  document.getElementById("exp-meta").innerHTML = `
    Responsable&nbsp;: <span class="meta-value">${escapeHtml(detail.author || "inconnu")}</span>
    &middot; Débutée le&nbsp;: <span class="meta-value">${formatDate(detail.created_at)}</span>
    ${detail.hypothesis ? `<br>Hypothèse&nbsp;: ${escapeHtml(detail.hypothesis)}` : ""}
  `;
  document.getElementById("crumb").textContent = "/ " + detail.title;
}

function renderObjectives(detail) {
  const list = document.getElementById("objectives-list");
  const summary = document.getElementById("objectives-summary");
  if (detail.objectives.length === 0) {
    summary.style.display = "none";
    list.innerHTML = `<div class="help">Aucun objectif défini.</div>`;
    return;
  }
  const metCount = detail.objectives.filter((o) => {
    const result = objectiveResultFor(detail, o.name);
    return result && result.status === "met";
  }).length;
  summary.style.display = "";
  summary.textContent = `${metCount} / ${detail.objectives.length} atteint${metCount > 1 ? "s" : ""}`;
  list.innerHTML = detail.objectives
    .map((o) => {
      const result = objectiveResultFor(detail, o.name);
      const met = result && result.status === "met";
      const iconBg = met ? "var(--done-tint)" : "var(--border-soft)";
      const iconColor = met ? "var(--done)" : "var(--text-faint)";
      const icon = met
        ? '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><path d="M5 13l4 4L19 7"/></svg>'
        : '<svg width="9" height="9" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>';
      const statusText = result ? OBJECTIVE_STATUS_LABELS[result.status] || result.status : "En cours de vérification";
      const verification = (detail.objective_verification || {})[o.name];
      return `
        <div class="marked-card" style="display:flex;gap:10px;align-items:flex-start;">
          <div style="width:18px;height:18px;border-radius:999px;background:${iconBg};color:${iconColor};display:flex;align-items:center;justify-content:center;flex:none;margin-top:1px;">${icon}</div>
          <div>
            <div style="font-size:13px;font-weight:600;">${escapeHtml(o.name)}</div>
            <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(statusText)}</div>
            ${o.rationale ? `<div style="font-size:11.5px;color:var(--text-soft);margin-top:3px;">${escapeHtml(o.rationale)}</div>` : ""}
            ${verification ? `<div style="font-size:11px;color:var(--text-faint);margin-top:2px;font-style:italic;">Vérification&nbsp;: ${escapeHtml(verification)}</div>` : ""}
          </div>
        </div>`;
    })
    .join("");
}

// Niveau de changement de procédé/structure (voir spectre.core.versioning) -> libellé affiché à
// côté du numéro de version. "none" n'apparaît que dans l'historique complet (voir
// renderFullHistory) : la frise des versions ne garde que les entrées qui en ont un.
const CHANGE_LEVEL_LABELS = {
  initial: "version initiale",
  major: "changement majeur",
  minor: "changement mineur",
  patch: "ajustement mineur",
  none: null,
};

function versionBadge(item) {
  return `<span class="timeline-version" title="${escapeHtml(CHANGE_LEVEL_LABELS[item.change_level] || "")}">v${escapeHtml(item.version)}</span>`;
}

// item.is_current vient du serveur (la toute dernière entrée de la piste) - jamais déduit de la
// position dans la liste affichée, puisque la frise des versions peut omettre des entrées
// intermédiaires (voir renderTimeline) et donc ne pas se terminer sur le vrai commit courant.
function renderTimelineItem(item, extraClass) {
  return `
    <div class="timeline-item ${item.is_current ? "current" : ""} ${extraClass || ""}">
      <div class="timeline-date">${formatDate(item.created_at)}${item.is_current ? " · version actuelle" : ""} ${versionBadge(item)}</div>
      <div class="timeline-title">${escapeHtml(item.title)}</div>
      <div class="timeline-desc">${escapeHtml(item.intent)}</div>
    </div>`;
}

function renderTimeline(versions) {
  const el = document.getElementById("timeline");
  // Most recent first - #timeline is a .builder-col__scroll box that starts scrolled to the top,
  // so the last few commits are visible without scrolling ; le reste (dont chaque étape qui n'a
  // pas fait bouger la version) est dans l'historique complet en bas de la fiche, pas ici.
  el.innerHTML = [...versions].reverse().map((item) => renderTimelineItem(item)).join("");
}

function renderFullHistory(items) {
  const el = document.getElementById("full-history");
  if (!el) return;
  el.innerHTML = [...items]
    .reverse()
    .map((item) => renderTimelineItem(item, item.change_level === "none" ? "no-version-change" : ""))
    .join("");
}

function renderStructure(detail, diff) {
  document.getElementById("structure-svg").innerHTML = detail.structure_svg || "<div class='help'>Pas de schéma pour ce type de structure.</div>";
  document.getElementById("structure-click-hint").style.display = currentProcess ? "" : "none";
  const diffNote = document.getElementById("diff-note");
  const diffDetails = document.getElementById("diff-details");
  if (!diff || !diff.target || diff.entries.length === 0) {
    diffNote.textContent = diff && diff.target ? "identique à la version précédente" : "";
    diffDetails.innerHTML = "";
    return;
  }
  diffNote.innerHTML = `<span style="color:var(--abandoned);font-weight:600;">${diff.entries.length} paramètre${diff.entries.length > 1 ? "s" : ""} modifié${diff.entries.length > 1 ? "s" : ""}</span>`;
  diffDetails.innerHTML = diff.entries
    .slice(0, 12)
    .map((e) => `<div class="mono" style="font-size:11.5px;color:var(--text-soft);padding:2px 0;">${escapeHtml(e.path)} : ${escapeHtml(JSON.stringify(e.before))} &rarr; ${escapeHtml(JSON.stringify(e.after))}</div>`)
    .join("");
}

// Cliquer une couche du dessin ouvre une modale avec les paramètres de l'étape qui l'a produite
// - même convention data-layer-index que le constructeur de structure (0 = substrat, N = l'étape
// N-1 du procédé) sur le même SVG (structures.render_structure_svg réutilise frame_to_svg).

const STEP_KIND_LABELS = {
  deposition: "Dépôt",
  etch: "Gravure",
  lithography: "Lithographie",
  resist_strip: "Retrait de résine",
  planarization: "Planarisation",
  chemical: "Étape chimique",
  faceted_growth: "Croissance facettée",
  epitaxial_growth: "Croissance épitaxiale",
  flip: "Retournement",
};

const STEP_FIELD_LABELS = {
  material: "Matériau",
  recipe: "Recette",
  angle_deg: "Angle",
  thickness: "Épaisseur",
  depth: "Profondeur",
  resist_material: "Résine",
  openings: "Ouvertures",
  target_level: "Niveau cible",
  stop_material: "S'arrête sur",
  orientation: "Orientation",
  rate_c: "Vitesse relative (plan C)",
  rate_m: "Vitesse relative (plan M)",
  rate_sp: "Vitesse relative (semipolaire)",
  semi_polar_angle_deg: "Angle semipolaire",
  seed_materials: "Matériaux d'amorçage (SAG)",
};

function formatStepValue(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "object" && !Array.isArray(value) && "value" in value && "unit" in value) {
    return `${value.value}${value.unit ? " " + value.unit : ""}`;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(", ");
  }
  if (typeof value === "object") {
    const entries = Object.entries(value)
      .map(([k, v]) => [k, formatStepValue(v)])
      .filter(([, v]) => v !== null);
    return entries.length ? entries.map(([k, v]) => `${k} : ${v}`).join(" · ") : null;
  }
  return String(value);
}

function openLayerModal(title, fields) {
  document.getElementById("layer-modal-title").textContent = title;
  document.getElementById("layer-modal-body").innerHTML = fields.length
    ? fields
        .map(
          ([label, value]) => `
      <div style="padding:8px 0;border-top:1px solid var(--border-soft);">
        <span style="color:var(--text-faint);font-size:11px;text-transform:uppercase;letter-spacing:.02em;">${escapeHtml(label)}</span><br>
        <span>${escapeHtml(value)}</span>
      </div>`
        )
        .join("")
    : `<div class="help">Pas de paramètre à afficher pour cette couche.</div>`;
  document.getElementById("layer-modal").showModal();
}

function showLayerModal(layerIndex) {
  if (!currentProcess) return;
  if (layerIndex === 0) {
    const s = currentProcess.substrate || {};
    const fields = [
      ["Matériau", s.material],
      ["Largeur du domaine", formatStepValue(s.domain_width)],
      ["Épaisseur", formatStepValue(s.thickness)],
    ].filter(([, v]) => v);
    openLayerModal("Substrat", fields);
    return;
  }
  const step = (currentProcess.steps || [])[layerIndex - 1];
  if (!step) return;
  const fields = Object.entries(step)
    .filter(([key]) => key !== "kind" && key !== "name")
    .map(([key, value]) => [STEP_FIELD_LABELS[key] || key, formatStepValue(value)])
    .filter(([, value]) => value !== null);
  openLayerModal(`${STEP_KIND_LABELS[step.kind] || step.kind} — ${step.name}`, fields);
}

// Survoler une couche affiche un aperçu condensé (nom + quelques paramètres clés) dans une
// infobulle qui suit le curseur - même source de champs que la modale (showLayerModal), juste
// limitée aux 4 premiers pour rester lisible dans un petit encart.
function layerSummaryFields(layerIndex) {
  if (!currentProcess) return null;
  if (layerIndex === 0) {
    const s = currentProcess.substrate || {};
    const fields = [
      ["Matériau", s.material],
      ["Largeur du domaine", formatStepValue(s.domain_width)],
      ["Épaisseur", formatStepValue(s.thickness)],
    ].filter(([, v]) => v);
    return { title: "Substrat", fields };
  }
  const step = (currentProcess.steps || [])[layerIndex - 1];
  if (!step) return null;
  const fields = Object.entries(step)
    .filter(([key]) => key !== "kind" && key !== "name")
    .map(([key, value]) => [STEP_FIELD_LABELS[key] || key, formatStepValue(value)])
    .filter(([, value]) => value !== null)
    .slice(0, 4);
  return { title: `${STEP_KIND_LABELS[step.kind] || step.kind} — ${step.name}`, fields };
}

function showLayerTooltip(layerIndex, x, y) {
  const summary = layerSummaryFields(layerIndex);
  const tooltip = document.getElementById("layer-tooltip");
  if (!summary) {
    hideLayerTooltip();
    return;
  }
  tooltip.innerHTML = `
    <strong>${escapeHtml(summary.title)}</strong>
    ${summary.fields.map(([label, value]) => `${escapeHtml(label)} : ${escapeHtml(value)}`).join("<br>")}`;
  tooltip.style.display = "";
  // décalé du curseur pour ne pas se retrouver caché par la pointe de la souris.
  tooltip.style.left = `${x + 14}px`;
  tooltip.style.top = `${y + 14}px`;
}

function hideLayerTooltip() {
  document.getElementById("layer-tooltip").style.display = "none";
}

document.getElementById("structure-svg").addEventListener("click", (event) => {
  const path = event.target.closest("[data-layer-index]");
  if (!path) return;
  showLayerModal(parseInt(path.dataset.layerIndex, 10));
});

document.getElementById("structure-svg").addEventListener("mousemove", (event) => {
  const path = event.target.closest("[data-layer-index]");
  if (!path) {
    hideLayerTooltip();
    return;
  }
  showLayerTooltip(parseInt(path.dataset.layerIndex, 10), event.clientX, event.clientY);
});

document.getElementById("structure-svg").addEventListener("mouseleave", hideLayerTooltip);

document.getElementById("layer-modal-close-btn").addEventListener("click", () => {
  document.getElementById("layer-modal").close();
});

// Rendu partagé d'une ligne "entité physique" (identifiant + emplacement), utilisé une fois pour
// l'unique entité d'une expérience simple (renderPhysicalTracking) et une fois par variante d'un
// lot (renderBatchMatrix, compact=true - tient sous une vignette plutôt qu'à côté). Les deux champs
// portent une autocomplétion (list=, remplie depuis /entites/historique - voir populateEntityHistory)
// et sont marqués data-report-hide + accompagnés d'un miroir texte .report-only, même mécanique que
// partout ailleurs sur la fiche depuis la suppression du mode vue (voir generateReportHtml).
function entityFieldsHtml(current, indexAttr, canEdit, compact) {
  const sampleId = current.sample_id || "";
  const location = current.location || "";
  const roText = sampleId || location
    ? `${sampleId ? `Identifiant&nbsp;: <strong>${escapeHtml(sampleId)}</strong>` : ""}${location ? `${sampleId ? "<br>" : ""}Emplacement&nbsp;: <strong>${escapeHtml(location)}</strong>` : ""}`
    : "";
  if (!canEdit) {
    return roText
      ? `<div style="font-size:${compact ? "11px" : "13px"};">${roText}</div>`
      : `<div class="help">Aucun suivi physique enregistré.</div>`;
  }
  const idInput = `<input class="field js-entity-sample-id" data-index="${indexAttr}" data-report-hide list="entity-sample-id-history" value="${escapeHtml(sampleId)}" placeholder="${compact ? "identifiant" : "ex : W12-A3"}" style="${compact ? "margin-top:6px;font-size:11px;padding:4px 6px;" : ""}">`;
  const locInput = `<input class="field js-entity-location" data-index="${indexAttr}" data-report-hide list="entity-location-history" value="${escapeHtml(location)}" placeholder="${compact ? "emplacement" : "ex : congélateur B, tiroir 2"}" style="${compact ? "margin-top:4px;font-size:11px;padding:4px 6px;" : ""}">`;
  const layout = compact
    ? `${idInput}${locInput}`
    : `<div class="field-row" style="margin-bottom:10px;"><div><label>Identifiant physique</label>${idInput}</div><div><label>Emplacement</label>${locInput}</div></div>`;
  const roMirror = roText ? `<span class="report-only" style="font-size:${compact ? "11px" : "13px"};margin-top:4px;">${roText}</span>` : "";
  return `${layout}${roMirror}`;
}

async function renderBatchMatrix(detail) {
  const card = document.getElementById("matrix-card");
  if (!detail.is_batch) {
    card.style.display = "none";
    return;
  }
  card.style.display = "";
  try {
    const variation = await api.get(`/api/projects/${slug}/experiences/${experienceId}/matrice`);
    const labels = variation.labels || variation.svgs.map((_, i) => `#${i + 1}`);
    const canEdit = isEditorRole();
    const tracking = variation.physical_tracking || [];

    // Cartographie : une vignette par échantillon, la structure réelle telle que StructureForge
    // l'a simulée - pas juste la référence, chaque variante. Identifiant + emplacement se posent
    // juste en dessous (entityFieldsHtml, mode compact - voir sa doc plus haut).
    document.getElementById("atlas-content").innerHTML = `
      <div class="atlas-grid">
        ${variation.svgs
          .map((svg, i) => {
            const idField = entityFieldsHtml(tracking[i] || {}, i, canEdit, true);
            return `<div class="atlas-tile">${svg}<div class="atlas-label">${escapeHtml(labels[i])}</div>${idField}</div>`;
          })
          .join("")}
      </div>
      ${canEdit ? `<button class="btn btn-line" id="save-atlas-tracking-btn" type="button" data-report-hide style="margin-top:10px;">Enregistrer les identifiants physiques</button>` : ""}`;

    if (canEdit) {
      document.getElementById("save-atlas-tracking-btn").addEventListener("click", () => {
        const entities = variation.svgs.map((_, i) => {
          const sampleInput = document.querySelector(`.js-entity-sample-id[data-index="${i}"]`);
          const locInput = document.querySelector(`.js-entity-location[data-index="${i}"]`);
          return { sample_id: sampleInput.value.trim() || null, location: locInput.value.trim() || null };
        });
        savePhysicalTracking(entities);
      });
    }

    const el = document.getElementById("matrix-content");
    const hasFactors = variation.factor_labels && variation.factor_labels.length > 0;
    if (variation.varying.length === 0 && !hasFactors) {
      el.innerHTML = `<div class="help">Les ${variation.entity_count} échantillons sont identiques sur tous les paramètres suivis.</div>`;
      return;
    }

    // Feuille de split : une ligne par échantillon, une colonne par paramètre réellement varié -
    // lisible directement, pas les chemins de structure bruts (gardés en détail technique en
    // dessous). factor_labels/factor_values are absent on campaigns saved before multi-paramètre
    // support - fall back to the single generic "Paramètre" column labels already covered.
    const factorLabels = variation.factor_labels && variation.factor_labels.length ? variation.factor_labels : ["Paramètre"];
    const splitSheet = `
      <table style="border-collapse:collapse;font-size:13px;width:100%;">
        <thead><tr style="text-align:left;color:var(--text-faint);font-size:11px;text-transform:uppercase;">
          <th style="padding:4px 10px 4px 0;">Échantillon</th>
          ${factorLabels.map((label) => `<th style="padding:4px 10px;">${escapeHtml(label)}</th>`).join("")}
        </tr></thead>
        <tbody>
          ${labels
            .map((label, i) => {
              const values = variation.factor_values && variation.factor_values[i] ? variation.factor_values[i] : [label];
              return `<tr style="border-top:1px solid var(--border-soft);">
                <td class="mono" style="padding:6px 10px 6px 0;">${escapeHtml(label)}</td>
                ${values.map((v) => `<td class="mono" style="padding:6px 10px;">${escapeHtml(String(v))}</td>`).join("")}
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;

    const rawTable = variation.varying.length
      ? `
      <table style="border-collapse:collapse;font-size:12px;width:100%;">
        <thead><tr style="text-align:left;color:var(--text-faint);font-size:11px;text-transform:uppercase;">
          <th style="padding:4px 10px 4px 0;">Repère interne</th>
          ${variation.varying[0].values.map((_, i) => `<th style="padding:4px 10px;">#${i + 1}</th>`).join("")}
        </tr></thead>
        <tbody>
          ${variation.varying
            .map(
              (f) => `<tr style="border-top:1px solid var(--border-soft);">
                <td class="mono" style="padding:6px 10px 6px 0;color:var(--text-soft);">${escapeHtml(f.path)}</td>
                ${f.values.map((v) => `<td class="mono" style="padding:6px 10px;">${escapeHtml(JSON.stringify(v))}</td>`).join("")}
              </tr>`
            )
            .join("")}
        </tbody>
      </table>`
      : `<div class="help">Ces paramètres ne changent pas la géométrie simulée (ex : un paramètre process ou une estimation) - rien à comparer structure par structure.</div>`;

    el.innerHTML = `
      <div style="overflow-x:auto;">${splitSheet}</div>
      <details style="margin-top:12px;">
        <summary style="cursor:pointer;font-size:12px;color:var(--text-faint);">Détails techniques</summary>
        <div style="overflow-x:auto;margin-top:8px;">${rawTable}</div>
      </details>`;
  } catch (err) {
    showError(err);
  }
}

function renderConclusion(detail) {
  const container = document.getElementById("conclusion-section");
  const isConcluded = detail.status === "concluded" || detail.status === "abandoned";
  if (isConcluded) {
    const c = detail.conclusion;
    const answers = c.objective_results
      .map((r) => {
        const objective = detail.objectives.find((o) => o.name === r.objective);
        return `
          <div style="padding:8px 0;border-top:1px solid var(--border-soft);">
            <div style="font-size:13px;font-weight:600;">${escapeHtml(r.objective)}</div>
            ${objective && objective.rationale ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:1px;">${escapeHtml(objective.rationale)}</div>` : ""}
            <div style="font-size:12.5px;color:var(--text-soft);margin-top:4px;">${escapeHtml(OBJECTIVE_STATUS_LABELS[r.status] || r.status)}${r.reasoning ? " — " + escapeHtml(r.reasoning) : ""}</div>
          </div>`;
      })
      .join("");
    container.innerHTML = `
      <div class="section-title" style="margin-bottom:14px;">Conclusion</div>
      ${c.summary ? `<p style="font-size:13.5px;line-height:1.6;margin-bottom:10px;">${escapeHtml(c.summary)}</p>` : ""}
      ${c.decision ? `<div style="font-size:12.5px;color:var(--text-soft);">Décision&nbsp;: <strong>${escapeHtml(c.decision)}</strong></div>` : ""}
      ${c.next_steps ? `<div style="font-size:12.5px;color:var(--text-soft);margin-top:4px;">Suite&nbsp;: ${escapeHtml(c.next_steps)}</div>` : ""}
      ${answers ? `<div style="margin-top:14px;">${answers}</div>` : ""}
    `;
    return;
  }
  if (!isEditorRole()) {
    container.innerHTML = `<div class="section-title" style="margin-bottom:14px;">Conclusion</div><div class="help" style="font-style:italic;">Pas encore conclue — expérience en cours.</div>`;
    return;
  }
  container.innerHTML = `
    <div class="section-title" style="margin-bottom:14px;">Conclure l'expérience</div>
    <span class="report-only help" style="font-style:italic;">Pas encore conclue — expérience en cours.</span>
    <form id="conclude-form" class="field-group" data-report-hide>
      <div id="objective-results"></div>
      <div><label>Résumé</label><textarea class="field" id="conclude-summary" rows="2"></textarea></div>
      <div class="field-row">
        <div><label>Décision</label>
          <select class="field" id="conclude-decision">
            <option value="">—</option>
            <option value="promote">Retenir comme référence</option>
            <option value="branch">Explorer une variante</option>
            <option value="replicate">Reproduire pour confirmer</option>
            <option value="abandon">Abandonner la piste</option>
            <option value="inconclusive">Non concluant</option>
          </select>
        </div>
        <div><label>Statut final</label>
          <select class="field" id="conclude-status">
            <option value="concluded">Conclue</option>
            <option value="abandoned">Abandonnée</option>
          </select>
        </div>
      </div>
      <div><label>Prochaine étape (optionnelle)</label><input class="field" id="conclude-next-steps"></div>
      <button class="btn btn-primary btn-block" type="submit">Enregistrer la conclusion</button>
    </form>
  `;
  const verification = currentDetail.objective_verification || {};
  document.getElementById("objective-results").innerHTML = currentDetail.objectives
    .map(
      (o, i) => `
      <div style="margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid var(--border-soft);">
        <label style="margin-bottom:2px;">${escapeHtml(o.name)}</label>
        ${o.rationale ? `<div style="font-size:11.5px;color:var(--text-faint);margin-bottom:2px;">Pourquoi&nbsp;: ${escapeHtml(o.rationale)}</div>` : ""}
        ${verification[o.name] ? `<div style="font-size:11.5px;color:var(--text-faint);margin-bottom:6px;">Vérification prévue&nbsp;: ${escapeHtml(verification[o.name])}</div>` : ""}
        <select class="field" data-objective="${escapeHtml(o.name)}" id="obj-result-${i}" style="margin-bottom:6px;">
          <option value="met">Atteint</option>
          <option value="not_met">Non atteint</option>
          <option value="partially_met">Partiellement atteint</option>
          <option value="inconclusive">Non concluant</option>
        </select>
        <textarea class="field" id="obj-reasoning-${i}" rows="2" placeholder="Réponse : qu'a-t-on constaté ?"></textarea>
      </div>`
    )
    .join("");

  document.getElementById("conclude-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const objectiveResults = currentDetail.objectives.map((o, i) => ({
      objective: o.name,
      status: document.getElementById(`obj-result-${i}`).value,
      reasoning: document.getElementById(`obj-reasoning-${i}`).value.trim() || null,
    }));
    try {
      const result = await api.post(`/api/projects/${slug}/experiences/${experienceId}/conclure`, {
        status: document.getElementById("conclude-status").value,
        decision: document.getElementById("conclude-decision").value || null,
        summary: document.getElementById("conclude-summary").value || null,
        next_steps: document.getElementById("conclude-next-steps").value || null,
        objective_results: objectiveResults,
      });
      // conclure records a new version carrying the conclusion (experiences are immutable) -
      // go to it, not back to this now-superseded draft.
      window.location.href = `/projets/${slug}/experiences/${result.id}`;
    } catch (err) {
      showError(err);
    }
  });
}

async function populateCompareProjectSelect() {
  const projectSelect = document.getElementById("compare-project-select");
  try {
    const myProjects = await api.get("/api/projects");
    projectSelect.innerHTML = myProjects
      .map((p) => `<option value="${p.slug}">${escapeHtml(p.name)}${p.slug === slug ? " (ce projet)" : ""}</option>`)
      .join("");
    projectSelect.value = slug;
  } catch (err) {
    // silent: comparison is a secondary feature
  }
  await populateCompareExperienceSelect(projectSelect.value);
}

async function populateCompareExperienceSelect(targetSlug) {
  const select = document.getElementById("compare-select");
  try {
    const data = await api.get(`/api/projects/${targetSlug}/experiences?status=all&limit=200`);
    const others = data.items.filter((item) => !(targetSlug === slug && item.id === experienceId));
    select.innerHTML = others.length
      ? others.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("")
      : `<option value="">Aucune expérience à comparer</option>`;
  } catch (err) {
    select.innerHTML = `<option value="">—</option>`;
  }
}

document.getElementById("compare-project-select").addEventListener("change", (event) => {
  populateCompareExperienceSelect(event.target.value);
});

document.getElementById("compare-btn").addEventListener("click", async () => {
  const targetProject = document.getElementById("compare-project-select").value;
  const target = document.getElementById("compare-select").value;
  if (!target) return;
  const box = document.getElementById("compare-result");
  try {
    const endpoint =
      targetProject === slug
        ? `/api/projects/${slug}/experiences/${experienceId}/diff?against=${target}`
        : `/api/projects/${slug}/experiences/${experienceId}/diff-externe?autre_projet=${targetProject}&autre_experience=${target}`;
    const diff = await api.get(endpoint);
    if (diff.entries.length === 0) {
      box.innerHTML = `<div class="help">Aucune différence de structure.</div>`;
    } else {
      box.innerHTML = diff.entries
        .slice(0, 20)
        .map((e) => `<div class="mono" style="font-size:11px;color:var(--text-soft);padding:2px 0;">${escapeHtml(e.path)} : ${escapeHtml(JSON.stringify(e.before))} &rarr; ${escapeHtml(JSON.stringify(e.after))}</div>`)
        .join("");
    }
  } catch (err) {
    showError(err);
  }
});

// Pièces jointes - même pattern que atlas.js:70-118 (panneau Atlas), porté ici pour les preuves de
// type "image" plutôt que dupliqué tel quel : atlas.js liste des pièces jointes autonomes avec un
// bouton de suppression, alors qu'ici une pièce jointe est propriété d'une preuve précise et ne se
// supprime qu'en même temps qu'elle - pas besoin de deleteLinkButtonHtml.
async function uploadFile(url, formData) {
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

async function saveAnnotations(evidenceId, annotations) {
  clearError();
  try {
    const result = await api.post(`/api/projects/${slug}/experiences/${experienceId}/preuves/${evidenceId}/annotations`, {
      annotations,
    });
    window.location.href = `/projets/${slug}/experiences/${result.id}`;
  } catch (err) {
    showError(err);
  }
}

// Superposition SVG des annotations (flèche / cadre) sur une image de preuve. Les coordonnées sont
// stockées en % de l'image (x/y/x2/y2) - le viewBox 0..100 avec preserveAspectRatio="none" les
// reprojette directement sur les dimensions réelles affichées, quel que soit le ratio de l'image.
function annotationMarkersSvg(annotations) {
  const shapes = (annotations || [])
    .map((a) => {
      if (a.type === "arrow") {
        return `<line x1="${a.x}" y1="${a.y}" x2="${a.x2}" y2="${a.y2}" stroke="var(--accent)" stroke-width="0.8" vector-effect="non-scaling-stroke" marker-end="url(#annotation-arrowhead)"/>`;
      }
      const x = Math.min(a.x, a.x2);
      const y = Math.min(a.y, a.y2);
      const w = Math.abs(a.x2 - a.x);
      const h = Math.abs(a.y2 - a.y);
      return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="var(--accent)" fill-opacity="0.18" stroke="var(--accent)" stroke-width="0.8" vector-effect="non-scaling-stroke"/>`;
    })
    .join("");
  return `
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;">
      <defs>
        <marker id="annotation-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" viewBox="0 0 8 6">
          <path d="M0,0 L8,3 L0,6 z" fill="var(--accent)"/>
        </marker>
      </defs>
      ${shapes}
    </svg>`;
}

function imageEvidenceHtml(detail, e) {
  const attachment = (detail.attachments || []).find((a) => a.evidence_id === e.id);
  if (!attachment) {
    return `<div class="help" style="margin-top:8px;">Image en cours d'envoi ou absente.</div>`;
  }
  const url = `/api/projects/${encodeURIComponent(slug)}/pieces-jointes/${encodeURIComponent(attachment.id)}`;
  const canEdit = isEditorRole();
  const annotations = e.image_annotations || [];
  const annotationsListHtml = annotations
    .map(
      (a, i) => `
      <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;padding:3px 0;">
        <span>${a.type === "arrow" ? "Flèche" : "Cadre"}${a.label ? " — " + escapeHtml(a.label) : ""}</span>
        ${
          canEdit
            ? `<button type="button" class="js-remove-annotation" data-evidence-id="${e.id}" data-index="${i}" data-report-hide style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;line-height:1;">&times;</button>`
            : ""
        }
      </div>`
    )
    .join("");
  return `
    <div style="margin-top:10px;">
      <div class="js-annotation-image" data-evidence-id="${e.id}" data-attachment-id="${attachment.id}" style="position:relative;display:inline-block;max-width:100%;cursor:${canEdit ? "crosshair" : "default"};">
        <img src="${url}" alt="${escapeHtml(attachment.filename)}" style="max-width:100%;display:block;border-radius:var(--radius-sm);">
        ${annotationMarkersSvg(annotations)}
      </div>
      ${annotationsListHtml ? `<div style="margin-top:6px;">${annotationsListHtml}</div>` : ""}
      ${
        canEdit
          ? `<div class="js-annotation-tools" data-evidence-id="${e.id}" data-report-hide style="margin-top:8px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
              <button type="button" class="btn btn-line js-annotation-tool" data-tool="arrow" style="padding:4px 10px;font-size:11.5px;">Flèche</button>
              <button type="button" class="btn btn-line js-annotation-tool" data-tool="box" style="padding:4px 10px;font-size:11.5px;">Cadre</button>
              <button type="button" class="btn btn-primary js-annotation-save" style="padding:4px 10px;font-size:11.5px;">Enregistrer les annotations</button>
              <span class="help js-annotation-hint" style="margin:0;"></span>
            </div>`
          : ""
      }
    </div>`;
}

function graphEvidenceHtml(e) {
  const cfg = e.graph_config || {};
  if (!cfg.data_source_url) {
    return `
      <div style="margin-top:10px;padding:12px 14px;background:var(--bg);border-radius:var(--radius-sm);border:1px dashed var(--border-soft);">
        <div style="font-size:11.5px;font-weight:600;color:var(--text-faint);">En attente de connexion</div>
        ${cfg.title ? `<div style="font-size:12.5px;margin-top:4px;">${escapeHtml(cfg.title)}</div>` : ""}
        ${
          cfg.x_label || cfg.y_label
            ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:2px;">${escapeHtml(cfg.x_label || "")}${cfg.x_label && cfg.y_label ? " / " : ""}${escapeHtml(cfg.y_label || "")}</div>`
            : ""
        }
        ${cfg.query ? `<div class="mono" style="font-size:11px;color:var(--text-faint);margin-top:6px;">${escapeHtml(cfg.query)}</div>` : ""}
      </div>`;
  }
  return `<div class="js-graph-mount" data-url="${escapeHtml(cfg.data_source_url)}" data-title="${escapeHtml(cfg.title || "")}" data-x-label="${escapeHtml(cfg.x_label || "")}" data-y-label="${escapeHtml(cfg.y_label || "")}" style="margin-top:10px;min-height:120px;background:var(--bg);border-radius:var(--radius-sm);padding:12px;font-size:11.5px;color:var(--text-faint);">Chargement du graphique…</div>`;
}

// Trace un nuage de points/ligne à la main en SVG (pas de bibliothèque de graphiques - cohérent
// avec le reste de l'app, sans étape de build).
function svgPlotHtml(points, title, xLabel, yLabel) {
  const w = 320;
  const h = 180;
  const pad = 28;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  const sx = (x) => pad + ((x - xMin) / xRange) * (w - 2 * pad);
  const sy = (y) => h - pad - ((y - yMin) / yRange) * (h - 2 * pad);
  const sorted = [...points].sort((a, b) => a.x - b.x);
  const linePoints = sorted.map((p) => `${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
  const dots = points.map((p) => `<circle cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="2.5" fill="var(--accent)"/>`).join("");
  return `
    ${title ? `<div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:6px;">${escapeHtml(title)}</div>` : ""}
    <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;">
      <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="var(--border-soft)"/>
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h - pad}" stroke="var(--border-soft)"/>
      <polyline points="${linePoints}" fill="none" stroke="var(--accent)" stroke-width="1.4"/>
      ${dots}
    </svg>
    <div style="display:flex;justify-content:space-between;font-size:10.5px;color:var(--text-faint);margin-top:2px;">
      <span>${escapeHtml(xLabel || "")}</span><span>${escapeHtml(yLabel || "")}</span>
    </div>`;
}

// fetch() côté client, jamais côté serveur : un fetch serveur vers une URL fournie par
// l'utilisateur ouvrirait une vraie surface SSRF pour une cible encore inconnue (le futur service
// de données de graph_config.data_source_url) ; le fetch navigateur n'a pas ce problème, au prix
// du CORS que devra exposer ce futur service - documenté dans l'aide du champ du formulaire.
async function drawGraphFromUrl(mount) {
  try {
    const response = await fetch(mount.dataset.url);
    if (!response.ok) throw new Error("réponse HTTP " + response.status);
    const data = await response.json();
    const points = Array.isArray(data.points) ? data.points : [];
    if (!points.length) {
      mount.innerHTML = `<div class="help" style="margin:0;">Aucune donnée renvoyée.</div>`;
      return;
    }
    mount.innerHTML = svgPlotHtml(points, mount.dataset.title, mount.dataset.xLabel, mount.dataset.yLabel);
  } catch (err) {
    mount.innerHTML = `<div class="help" style="margin:0;">Impossible de charger le graphique (${escapeHtml(err.message || String(err))}).</div>`;
  }
}

function evidenceFormFieldsHtml(kind) {
  if (kind === "image") {
    return `<div><label>Image</label><input class="field" type="file" id="evidence-image-input" accept="image/png,image/jpeg,image/gif,image/webp" required><div class="help">10 Mo maximum - une flèche ou un cadre pourront être ajoutés une fois la preuve créée.</div></div>`;
  }
  if (kind === "graph") {
    return `
      <div><label>Source</label><input class="field" id="evidence-source" placeholder="lien, fichier ou référence"></div>
      <div class="field-row">
        <input class="field" id="evidence-graph-x-label" placeholder="libellé axe X">
        <input class="field" id="evidence-graph-y-label" placeholder="libellé axe Y">
      </div>
      <div><label>Requête</label><input class="field" id="evidence-graph-query" placeholder="ex : split vs intensité PL">
        <div class="help">Sera interprété par un futur service de données - laissez tel quel en attendant.</div>
      </div>
      <div><label>URL de source de données (optionnel)</label><input class="field" id="evidence-graph-url" placeholder="https://...">
        <div class="help">Si renseignée, le graphique se trace dès maintenant à partir de ce qu'elle renvoie (JSON {points:[{x,y},...]}).</div>
      </div>`;
  }
  const stepOptions = currentProcess
    ? `<div><label>Étape associée (optionnel)</label><select class="field" id="evidence-step-select">
         <option value="">— aucune —</option>
         ${(currentProcess.steps || []).map((s, i) => `<option value="${i}">${escapeHtml(stepLabelFor(i))}</option>`).join("")}
       </select></div>`
    : "";
  return `
    <div><label>Source</label><input class="field" id="evidence-source" placeholder="lien, fichier ou référence" required></div>
    ${stepOptions}
    <div class="field-row">
      <input class="field" id="evidence-metric-name" placeholder="mesure (optionnel)">
      <input class="field" id="evidence-metric-value" type="number" placeholder="valeur">
    </div>`;
}

function renderEvidence(detail) {
  const list = document.getElementById("evidence-list");
  list.innerHTML = detail.evidence.length
    ? detail.evidence
        .map((e) => {
          const metricEntries = Object.entries(e.metrics || {});
          const metricText = metricEntries
            .map(([name, q]) => `${escapeHtml(name)} : ${escapeHtml(String(q.value))}${q.unit ? " " + escapeHtml(q.unit) : ""}`)
            .join(" · ");
          const stepBadge =
            e.step_index != null
              ? `<span class="badge badge-role" style="font-size:10.5px;margin-left:6px;">${escapeHtml(stepLabelFor(e.step_index))}</span>`
              : "";
          const kindBadge = `<span class="badge badge-role" style="font-size:10.5px;margin-left:6px;">${EVIDENCE_KIND_LABELS[e.kind] || e.kind}</span>`;
          const objectiveLine = e.objective
            ? `<div style="font-size:12px;color:var(--text-soft);margin-top:4px;">Objectif visé&nbsp;: <strong>${escapeHtml(e.objective)}</strong></div>`
            : "";
          const interpretationBlock = e.interpretation
            ? `<div style="font-size:12.5px;color:var(--text-soft);margin-top:6px;line-height:1.5;font-style:italic;">${escapeHtml(e.interpretation)}</div>`
            : "";
          let bodyHtml = "";
          if (e.kind === "image") {
            bodyHtml = imageEvidenceHtml(detail, e);
          } else if (e.kind === "graph") {
            bodyHtml = graphEvidenceHtml(e);
          }
          return `
            <div class="marked-card" style="margin-top:12px;">
              <div style="font-size:13px;font-weight:600;">${escapeHtml(e.description)}${stepBadge}${kindBadge}</div>
              ${e.source ? `<div style="font-size:12px;color:var(--text-soft);margin-top:2px;word-break:break-all;">${e.source.startsWith("http") ? `<a href="${escapeHtml(e.source)}" target="_blank" rel="noopener">${escapeHtml(e.source)}</a>` : escapeHtml(e.source)}</div>` : ""}
              ${metricText ? `<div class="mono" style="font-size:11.5px;color:var(--text-faint);margin-top:4px;">${metricText}</div>` : ""}
              ${objectiveLine}
              ${interpretationBlock}
              ${bodyHtml}
            </div>`;
        })
        .join("")
    : `<div class="help">Aucune preuve enregistrée.</div>`;

  document.querySelectorAll(".js-graph-mount").forEach((mount) => drawGraphFromUrl(mount));

  document.querySelectorAll(".js-remove-annotation").forEach((btn) => {
    btn.addEventListener("click", () => {
      const evidenceId = btn.dataset.evidenceId;
      const idx = parseInt(btn.dataset.index, 10);
      const evidence = detail.evidence.find((ev) => ev.id === evidenceId);
      if (!evidence) return;
      const updated = (evidence.image_annotations || []).filter((_, i) => i !== idx);
      saveAnnotations(evidenceId, updated);
    });
  });

  document.querySelectorAll(".js-annotation-image").forEach((container) => {
    const evidenceId = container.dataset.evidenceId;
    const evidence = detail.evidence.find((ev) => ev.id === evidenceId);
    const toolsBar = document.querySelector(`.js-annotation-tools[data-evidence-id="${evidenceId}"]`);
    if (!evidence || !toolsBar) return;
    const hint = toolsBar.querySelector(".js-annotation-hint");
    const localAnnotations = (evidence.image_annotations || []).map((a) => ({ ...a }));
    let tool = null;
    let dragStart = null;

    function redraw() {
      const svg = container.querySelector("svg");
      if (svg) svg.remove();
      container.insertAdjacentHTML("beforeend", annotationMarkersSvg(localAnnotations));
    }

    function pct(evt) {
      const rect = container.getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(100, ((evt.clientX - rect.left) / rect.width) * 100)),
        y: Math.max(0, Math.min(100, ((evt.clientY - rect.top) / rect.height) * 100)),
      };
    }

    function finishAnnotation(shape) {
      const label = window.prompt("Libellé de l'annotation (optionnel)");
      localAnnotations.push({ attachment_id: container.dataset.attachmentId, ...shape, label: label || null });
      redraw();
      tool = null;
      hint.textContent = "";
    }

    toolsBar.querySelectorAll(".js-annotation-tool").forEach((btn) => {
      btn.addEventListener("click", () => {
        tool = btn.dataset.tool;
        dragStart = null;
        hint.textContent = tool === "arrow" ? "Cliquez le départ puis l'arrivée de la flèche." : "Cliquez-glissez pour dessiner le cadre.";
      });
    });
    container.addEventListener("mousedown", (evt) => {
      if (tool !== "box") return;
      dragStart = pct(evt);
    });
    container.addEventListener("mouseup", (evt) => {
      if (tool !== "box" || !dragStart) return;
      finishAnnotation({ type: "box", x: dragStart.x, y: dragStart.y, x2: pct(evt).x, y2: pct(evt).y });
      dragStart = null;
    });
    container.addEventListener("click", (evt) => {
      if (tool !== "arrow") return;
      const point = pct(evt);
      if (!dragStart) {
        dragStart = point;
        hint.textContent = "Cliquez l'arrivée de la flèche.";
      } else {
        finishAnnotation({ type: "arrow", x: dragStart.x, y: dragStart.y, x2: point.x, y2: point.y });
        dragStart = null;
      }
    });
    toolsBar.querySelector(".js-annotation-save").addEventListener("click", () => saveAnnotations(evidenceId, localAnnotations));
  });

  renderEvidenceCompareTool(detail);

  const formWrap = document.getElementById("add-evidence-wrap");
  if (!isEditorRole()) {
    formWrap.innerHTML = "";
    return;
  }
  const objectiveField = detail.objectives.length
    ? `<div><label>Objectif visé (optionnel)</label><select class="field" id="evidence-objective-select">
         <option value="">— aucun —</option>
         ${detail.objectives.map((o) => `<option value="${escapeHtml(o.name)}">${escapeHtml(o.name)}</option>`).join("")}
       </select></div>`
    : "";
  formWrap.innerHTML = `
    <form id="evidence-form" class="field-group" data-report-hide style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border-soft);">
      <div><label>Type de preuve</label>
        <select class="field" id="evidence-kind-select">
          <option value="standard">Standard</option>
          <option value="image">Image</option>
          <option value="graph">Graphique</option>
        </select>
      </div>
      <div><label>Description</label><input class="field" id="evidence-description" placeholder="ex : mesure d'épaisseur au profilomètre" required></div>
      ${objectiveField}
      <div><label>Interprétation (optionnel)</label><textarea class="field" id="evidence-interpretation" rows="2" placeholder="pourquoi ce résultat est cohérent avec le changement"></textarea></div>
      <div id="evidence-kind-fields">${evidenceFormFieldsHtml("standard")}</div>
      <button class="btn btn-line btn-block" type="submit">Ajouter la preuve</button>
    </form>`;
  document.getElementById("evidence-kind-select").addEventListener("change", (event) => {
    document.getElementById("evidence-kind-fields").innerHTML = evidenceFormFieldsHtml(event.target.value);
  });
  document.getElementById("evidence-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const kind = document.getElementById("evidence-kind-select").value;
    const objectiveSelect = document.getElementById("evidence-objective-select");
    const interpretation = document.getElementById("evidence-interpretation").value.trim();
    let source = "";
    let graphConfig = null;
    let imageFile = null;
    try {
      if (kind === "image") {
        imageFile = document.getElementById("evidence-image-input").files[0];
        if (!imageFile) throw new Error("Choisissez une image.");
        source = imageFile.name;
      } else if (kind === "graph") {
        source = document.getElementById("evidence-source").value.trim();
        graphConfig = {
          title: document.getElementById("evidence-description").value.trim(),
          x_label: document.getElementById("evidence-graph-x-label").value.trim() || null,
          y_label: document.getElementById("evidence-graph-y-label").value.trim() || null,
          query: document.getElementById("evidence-graph-query").value.trim() || null,
          data_source_url: document.getElementById("evidence-graph-url").value.trim() || null,
        };
      } else {
        source = document.getElementById("evidence-source").value;
      }
      const metricNameEl = document.getElementById("evidence-metric-name");
      const metricValueEl = document.getElementById("evidence-metric-value");
      const stepSelect = document.getElementById("evidence-step-select");
      const result = await api.post(`/api/projects/${slug}/experiences/${experienceId}/preuves`, {
        description: document.getElementById("evidence-description").value,
        source,
        kind,
        objective: objectiveSelect && objectiveSelect.value ? objectiveSelect.value : null,
        interpretation: interpretation || null,
        graph_config: graphConfig,
        metric_name: metricNameEl ? metricNameEl.value.trim() || null : null,
        metric_value: metricValueEl && metricValueEl.value ? parseFloat(metricValueEl.value) : null,
        step_index: stepSelect && stepSelect.value !== "" ? parseInt(stepSelect.value, 10) : null,
      });
      // preuves records a new version carrying the evidence (experiences are immutable) - go to
      // it, not back to this now-superseded version. For an image preuve, the upload itself
      // records yet another version - navigate to that one instead once it's done.
      let finalId = result.id;
      if (kind === "image" && imageFile) {
        const formData = new FormData();
        formData.append("file", imageFile);
        formData.append("evidence_id", result.evidence_id);
        const uploadResult = await uploadFile(`/api/projects/${slug}/experiences/${result.id}/pieces-jointes`, formData);
        finalId = uploadResult.id;
      }
      window.location.href = `/projets/${slug}/experiences/${finalId}`;
    } catch (err) {
      showError(err);
    }
  });
}

// Texte "Kind — nom" pour l'étape à cet index dans le procédé courant (currentProcess.steps),
// réutilisant STEP_KIND_LABELS déjà utilisé pour la modale de couche ci-dessus. Une preuve dont
// step_index ne correspond plus au procédé *actuel* (une évolution ultérieure a raccourci ou
// changé la liste d'étapes) dégrade proprement vers "introuvable" plutôt que de planter - aucun
// lien vivant vers la version où elle a été prise n'est maintenu.
function stepLabelFor(index) {
  const step = currentProcess?.steps?.[index];
  if (!step) return `étape #${index + 1} (introuvable)`;
  return `${STEP_KIND_LABELS[step.kind] || step.kind} — ${step.name}`;
}

// Comparaison de deux preuves entre elles (ex : une mesure après un dépôt d'ITO à 400 nm puis à
// 200 nm) - entièrement côté client, detail.evidence est déjà chargé en entier avec ses mesures.
function renderEvidenceCompareTool(detail) {
  const tool = document.getElementById("evidence-compare-tool");
  if (detail.evidence.length < 2) {
    tool.style.display = "none";
    return;
  }
  tool.style.display = "block";
  const options = detail.evidence
    .map(
      (e) =>
        `<option value="${e.id}">${escapeHtml(e.description)}${e.step_index != null ? " — " + escapeHtml(stepLabelFor(e.step_index)) : ""}</option>`
    )
    .join("");
  const selectA = document.getElementById("evidence-compare-a");
  const selectB = document.getElementById("evidence-compare-b");
  selectA.innerHTML = options;
  selectB.innerHTML = options;
  // par défaut, les deux preuves les plus récentes - le cas le plus probable ("comparer où j'en suis
  // par rapport à juste avant").
  selectA.selectedIndex = Math.max(0, detail.evidence.length - 2);
  selectB.selectedIndex = detail.evidence.length - 1;
  document.getElementById("evidence-compare-result").innerHTML = "";
}

document.getElementById("evidence-compare-btn").addEventListener("click", () => {
  const idA = document.getElementById("evidence-compare-a").value;
  const idB = document.getElementById("evidence-compare-b").value;
  const box = document.getElementById("evidence-compare-result");
  if (!idA || !idB) return;
  if (idA === idB) {
    box.innerHTML = `<div class="help">Choisissez deux preuves différentes.</div>`;
    return;
  }
  const a = currentDetail.evidence.find((e) => e.id === idA);
  const b = currentDetail.evidence.find((e) => e.id === idB);
  const names = [...new Set([...Object.keys(a.metrics || {}), ...Object.keys(b.metrics || {})])];
  if (names.length === 0) {
    box.innerHTML = `<div class="help">Aucune des deux preuves n'a de mesure chiffrée à comparer.</div>`;
    return;
  }
  const fmt = (q) => (q ? `${q.value}${q.unit ? " " + q.unit : ""}` : "—");
  const rows = names
    .map((name) => {
      const qa = (a.metrics || {})[name];
      const qb = (b.metrics || {})[name];
      let delta = "—";
      if (qa && qb && typeof qa.value === "number" && typeof qb.value === "number") {
        if (qa.unit === qb.unit) {
          const d = qb.value - qa.value;
          delta = `${d > 0 ? "+" : ""}${d}${qb.unit ? " " + qb.unit : ""}`;
        } else {
          delta = "unités différentes";
        }
      }
      return `<tr><td>${escapeHtml(name)}</td><td class="mono">${escapeHtml(fmt(qa))}</td><td class="mono">${escapeHtml(fmt(qb))}</td><td class="mono">${escapeHtml(delta)}</td></tr>`;
    })
    .join("");
  box.innerHTML = `
    <table style="width:100%;font-size:12.5px;border-collapse:collapse;">
      <thead><tr style="color:var(--text-faint);text-align:left;"><th>Mesure</th><th>${escapeHtml(a.description)}</th><th>${escapeHtml(b.description)}</th><th>Écart</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
});

function renderForksNote(detail) {
  const box = document.getElementById("forks-note");
  if (detail.children.length < 2) {
    box.style.display = "none";
    return;
  }
  box.style.display = "block";
  box.innerHTML = `
    <div style="font-size:12px;color:var(--text-faint);margin-bottom:6px;">Cette version a donné plusieurs pistes :</div>
    ${detail.children
      .map((c) => `<div style="font-size:13px;margin-bottom:4px;"><a href="/projets/${slug}/experiences/${c.id}">${escapeHtml(c.title)}</a></div>`)
      .join("")}
    <a href="/projets/${slug}/graphe" style="font-size:12px;">Voir la vue d'ensemble &rarr;</a>`;
}

function renderTags(detail) {
  const row = document.getElementById("tags-row");
  const canEdit = isEditorRole();
  const chips = detail.tags
    .map(
      (t, i) => `
      <span class="badge badge-role">
        ${escapeHtml(t)}
        ${
          canEdit
            ? `<button class="js-remove-tag" data-index="${i}" type="button" data-report-hide style="background:none;border:none;cursor:pointer;color:inherit;padding:0;margin-left:2px;font-size:13px;line-height:1;">&times;</button>`
            : ""
        }
      </span>`
    )
    .join("");
  row.innerHTML =
    chips +
    (canEdit
      ? `<input id="new-tag-input" data-report-hide placeholder="+ étiquette" style="border:1px dashed var(--border-soft);border-radius:999px;padding:4px 10px;font-size:12px;width:110px;background:transparent;">`
      : "");

  row.querySelectorAll(".js-remove-tag").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = [...detail.tags];
      next.splice(parseInt(btn.dataset.index, 10), 1);
      updateTags(next);
    });
  });
  const input = document.getElementById("new-tag-input");
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && input.value.trim()) {
        event.preventDefault();
        updateTags([...detail.tags, input.value.trim()]);
      }
    });
  }
}

async function updateTags(tags) {
  clearError();
  try {
    const result = await api.post(`/api/projects/${slug}/experiences/${experienceId}/etiquettes`, { tags });
    // like conclure/preuves, tagging records a new version - follow it there.
    window.location.href = `/projets/${slug}/experiences/${result.id}`;
  } catch (err) {
    showError(err);
  }
}

function renderRefs(detail) {
  const row = document.getElementById("refs-row");
  const canEdit = isEditorRole();
  const chips = detail.ref_names
    .map((name) => `<span class="badge badge-role" title="Ref">🏷 ${escapeHtml(name)}</span>`)
    .join("");
  row.innerHTML =
    chips +
    (canEdit
      ? `<button id="make-ref-btn" data-report-hide type="button" class="btn btn-line" style="padding:2px 10px;font-size:11.5px;">+ ref</button>
         <input id="new-ref-input" data-report-hide placeholder="surnom (optionnel)" style="display:none;border:1px dashed var(--border-soft);border-radius:999px;padding:4px 10px;font-size:12px;width:150px;background:transparent;">`
      : "");

  const makeBtn = document.getElementById("make-ref-btn");
  const input = document.getElementById("new-ref-input");
  if (makeBtn) {
    makeBtn.addEventListener("click", () => {
      makeBtn.style.display = "none";
      input.style.display = "";
      input.focus();
    });
  }
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        createRef(input.value.trim());
      }
    });
  }
}

async function createRef(name) {
  clearError();
  try {
    await api.post(`/api/projects/${slug}/experiences/${experienceId}/ref`, { name: name || null });
    currentDetail = await api.get(`/api/projects/${slug}/experiences/${experienceId}`);
    renderRefs(currentDetail);
  } catch (err) {
    showError(err);
  }
}

async function populateCombineSelect() {
  try {
    const data = await api.get(`/api/projects/${slug}/experiences?status=all&limit=200`);
    const options = data.items
      .filter((exp) => exp.id !== experienceId)
      .map((exp) => `<option value="${exp.id}">${escapeHtml(exp.title)}</option>`)
      .join("");
    document.getElementById("combine-select").innerHTML = options || `<option value="">Aucune autre expérience à combiner</option>`;
  } catch (err) {
    // silent: advanced/secondary panel
  }
}

document.getElementById("combine-btn").addEventListener("click", async () => {
  clearError();
  const otherId = document.getElementById("combine-select").value;
  const title = document.getElementById("combine-title").value.trim();
  const intent = document.getElementById("combine-intent").value.trim();
  if (!otherId || !title || !intent) {
    showError(new Error("Choisissez une expérience, un titre et une raison de combiner."));
    return;
  }
  try {
    const result = await api.post(`/api/projects/${slug}/experiences/${experienceId}/combiner`, {
      other_id: otherId,
      title,
      intent,
    });
    window.location.href = `/projets/${slug}/experiences/${result.id}`;
  } catch (err) {
    showError(err);
  }
});

async function savePhysicalTracking(entities) {
  clearError();
  try {
    const result = await api.post(`/api/projects/${slug}/experiences/${experienceId}/entites`, { entities });
    // like tags/preuves, this records a new version - follow it there.
    window.location.href = `/projets/${slug}/experiences/${result.id}`;
  } catch (err) {
    showError(err);
  }
}

function renderPhysicalTracking(detail) {
  const card = document.getElementById("physical-tracking-content");
  if (detail.is_batch) {
    card.innerHTML = `<div class="help">Un identifiant physique par échantillon se pose juste sous chaque vignette de la cartographie des variantes, plus haut.</div>`;
    return;
  }
  const canEdit = isEditorRole();
  const current = detail.physical_tracking[0] || {};
  card.innerHTML = `
    ${entityFieldsHtml(current, 0, canEdit, false)}
    ${canEdit ? `<button class="btn btn-line" id="save-physical-tracking-btn" type="button" data-report-hide>Enregistrer</button>` : ""}`;
  if (canEdit) {
    document.getElementById("save-physical-tracking-btn").addEventListener("click", () => {
      const sampleInput = document.querySelector('.js-entity-sample-id[data-index="0"]');
      const locInput = document.querySelector('.js-entity-location[data-index="0"]');
      savePhysicalTracking([{ sample_id: sampleInput.value.trim() || null, location: locInput.value.trim() || null }]);
    });
  }
}

function renderReferences(detail) {
  const el = document.getElementById("references-list");
  if (detail.references.length === 0) {
    el.innerHTML = `<div class="help">Aucun lien enregistré.</div>`;
    return;
  }
  el.innerHTML = detail.references
    .map((r) => {
      const label = REFERENCE_ROLE_LABELS[r.role] || r.role;
      const target = r.experiment_id
        ? `<a href="/projets/${slug}/experiences/${r.experiment_id}">${escapeHtml(r.label)}</a>`
        : escapeHtml(r.label);
      return `<div style="font-size:13px;margin-bottom:8px;"><span style="color:var(--text-faint);font-size:11px;text-transform:uppercase;letter-spacing:.02em;">${escapeHtml(label)}</span><br>${target}</div>`;
    })
    .join("");
}

// Le rapport est une capture de ce qui est affiché, purgée de tout ce qui n'a de sens que dans
// l'appli vivante - plutôt que de dépendre d'un mode dédié qui garantissait autrefois qu'aucun
// formulaire d'édition ne traînait dans le DOM au moment de l'export (l'ancien "mode vue"), chaque
// section est clonée puis débarrassée de tout nœud marqué data-report-hide (un formulaire, un
// bouton d'action, un champ éditable...) ; le miroir texte .report-only qui l'accompagne parfois
// (cf. entityFieldsHtml) - invisible sur la fiche vivante - est alors révélé pour porter la valeur
// à sa place. Ne garde que les cartes qui ont un sens hors de l'appli (pas "Comparer avec", un
// outil interactif, ni "Actions avancées").
const REPORT_SECTION_IDS = ["header-card", "matrix-card", "physical-tracking-card", "evidence-card", "conclusion-section", "references-card"];

function cleanSectionForReport(el) {
  const clone = el.cloneNode(true);
  clone.querySelectorAll("[data-report-hide]").forEach((node) => node.remove());
  return clone.outerHTML;
}

async function generateReportHtml() {
  const css = await fetch("/static/css/style.css").then((r) => r.text());
  const threeCol = document.querySelector(".fiche-3col");
  const sections = [document.getElementById("header-card"), threeCol, ...REPORT_SECTION_IDS.slice(1).map((id) => document.getElementById(id))]
    .filter((el) => el)
    .map((el) => cleanSectionForReport(el))
    .join("\n");
  const generatedAt = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" }).format(new Date());
  return `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(currentDetail.title)} — rapport d'expérience</title>
<style>${css}</style>
<style>
  body{background:var(--bg);padding:28px 16px;}
  .report-page{max-width:1180px;margin:0 auto;}
  .report-banner{background:var(--surface);border:1px solid var(--border-soft);border-radius:var(--radius-sm);padding:10px 14px;margin-bottom:20px;font-size:12px;color:var(--text-faint);}
  .report-only{display:inline !important;}
</style>
</head>
<body>
  <div class="report-page">
    <div class="report-banner">Rapport d'expérience — extrait de Spectre (projet « ${escapeHtml(currentProjectName || "")} ») le ${generatedAt}. Document autonome : une photographie de cette fiche à cet instant, sans lien avec les données vivantes du projet.</div>
    ${sections}
  </div>
</body>
</html>`;
}

async function downloadReport() {
  clearError();
  try {
    const html = await generateReportHtml();
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rapport-${slug}-${experienceId}.html`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError(err);
  }
}

function goToEvolve() {
  window.location.href = `/projets/${slug}/experiences/${experienceId}/evoluer`;
}

function applyModeVisibility() {
  const editing = isEditorRole();
  document.getElementById("evolve-btn").style.display = editing ? "" : "none";
  // currentProcess n'est connu qu'après le chargement de /process (voir init()) - avant ça, ce
  // lien reste caché même si editing est vrai, applyModeVisibility() étant rappelée une fois de
  // plus dès que currentProcess est résolu.
  document.getElementById("structure-evolve-link").style.display = editing && currentProcess ? "" : "none";
  document.getElementById("advanced-actions").style.display = editing ? "" : "none";
  // le rapport reste disponible pour tout le monde en permanence - un éditeur voit ses propres
  // formulaires d'édition sur la fiche vivante, mais l'export les retire toujours (data-report-hide,
  // voir generateReportHtml) : plus besoin d'un mode dédié pour garantir un rapport propre.
  document.getElementById("export-report-btn").style.display = "";
}

async function init() {
  try {
    currentDetail = await api.get(`/api/projects/${slug}/experiences/${experienceId}`);
    const project = await api.get(`/api/projects/${slug}`);
    currentRole = project.role;
    currentProjectName = project.name;
    document.getElementById("project-crumb").textContent = project.name;
    document.getElementById("project-crumb").href = `/projets/${slug}`;

    renderHeader(currentDetail);
    renderTags(currentDetail);
    renderRefs(currentDetail);
    renderObjectives(currentDetail);
    renderForksNote(currentDetail);
    renderReferences(currentDetail);
    renderConclusion(currentDetail);
    renderBatchMatrix(currentDetail);
    renderPhysicalTracking(currentDetail);

    if (isEditorRole()) {
      document.getElementById("evolve-btn").addEventListener("click", goToEvolve);
      document.getElementById("structure-evolve-link").addEventListener("click", goToEvolve);
      populateCombineSelect();
    }
    document.getElementById("export-report-btn").addEventListener("click", downloadReport);
    applyModeVisibility();

    const [timeline, diff, process, entityHistory] = await Promise.all([
      api.get(`/api/projects/${slug}/experiences/${experienceId}/timeline`),
      api.get(`/api/projects/${slug}/experiences/${experienceId}/diff`),
      api.get(`/api/projects/${slug}/experiences/${experienceId}/process`).catch(() => null),
      api.get(`/api/projects/${slug}/entites/historique`).catch(() => ({ sample_ids: [], locations: [] })),
    ]);
    currentProcess = process;
    document.getElementById("entity-sample-id-history").innerHTML = entityHistory.sample_ids.map((v) => `<option value="${escapeHtml(v)}">`).join("");
    document.getElementById("entity-location-history").innerHTML = entityHistory.locations.map((v) => `<option value="${escapeHtml(v)}">`).join("");
    // rejoués maintenant que currentProcess est connu - applyModeVisibility gère #structure-evolve-link,
    // renderEvidence le badge/select par étape et l'outil de comparaison (voir stepLabelFor).
    applyModeVisibility();
    renderEvidence(currentDetail);
    renderTimeline(timeline.versions);
    renderFullHistory(timeline.items);
    renderStructure(currentDetail, diff);
    populateCompareProjectSelect();
  } catch (err) {
    showError(err);
  }
}

init();
