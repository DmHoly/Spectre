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

// Mode vue : masque les formulaires d'édition (évoluer, conclure, ajouter une preuve, etc.) pour
// une fiche épurée, exportable telle quelle en rapport autonome (voir generateReportHtml plus bas).
// Un simple visiteur (rôle viewer) est déjà toujours en mode vue - seuls editor/owner basculent.
let viewMode = false;
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
  if (detail.objectives.length === 0) {
    list.innerHTML = `<div class="help">Aucun objectif défini.</div>`;
    return;
  }
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
        <div style="display:flex;gap:10px;align-items:flex-start;">
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

function renderTimeline(items) {
  const el = document.getElementById("timeline");
  // Most recent first - #timeline is a .builder-col__scroll box that starts scrolled to the top,
  // so the last few commits are visible without scrolling ; the rest of the history is a scroll
  // away instead of pushing the page down (and stretched to match the other two columns' height
  // - see .fiche-3col in style.css).
  el.innerHTML = [...items]
    .reverse()
    .map((item, i) => {
      const isCurrent = i === 0;
      return `
        <div class="timeline-item ${isCurrent ? "current" : ""}">
          <div class="timeline-date">${formatDate(item.created_at)}${isCurrent ? " · version actuelle" : ""}</div>
          <div class="timeline-title">${escapeHtml(item.title)}</div>
          <div class="timeline-desc">${escapeHtml(item.intent)}</div>
        </div>`;
    })
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
  selective_growth: "Croissance sélective",
  flip: "Retournement",
};

const STEP_FIELD_LABELS = {
  material: "Matériau",
  mode: "Mode",
  angle_deg: "Angle",
  thickness: "Épaisseur",
  depth: "Profondeur",
  default_factor: "Facteur par défaut",
  selectivity_by_material: "Sélectivité par matériau",
  resist_material: "Résine",
  openings: "Ouvertures",
  process_parameters: "Paramètres procédé",
  derived_estimates: "Estimations dérivées",
  target_level: "Niveau cible",
  rate_m: "Vitesse relative (plan M)",
  rate_sp: "Vitesse relative (semipolaire)",
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
    const canEdit = isEditorRole() && !viewMode;
    const tracking = variation.physical_tracking || [];

    // Cartographie : une vignette par échantillon, la structure réelle telle que StructureForge
    // l'a simulée - pas juste la référence, chaque variante. L'identifiant physique de
    // l'échantillon (s'il y en a un) se pose juste en dessous.
    document.getElementById("atlas-content").innerHTML = `
      <div class="atlas-grid">
        ${variation.svgs
          .map((svg, i) => {
            const sampleId = (tracking[i] && tracking[i].sample_id) || "";
            const idField = canEdit
              ? `<input class="field js-atlas-sample-id" data-index="${i}" value="${escapeHtml(sampleId)}" placeholder="identifiant" style="margin-top:6px;font-size:11px;padding:4px 6px;">`
              : sampleId
                ? `<div style="font-size:11px;color:var(--text-faint);margin-top:4px;">${escapeHtml(sampleId)}</div>`
                : "";
            return `<div class="atlas-tile">${svg}<div class="atlas-label">${escapeHtml(labels[i])}</div>${idField}</div>`;
          })
          .join("")}
      </div>
      ${canEdit ? `<button class="btn btn-line" id="save-atlas-tracking-btn" type="button" style="margin-top:10px;">Enregistrer les identifiants physiques</button>` : ""}`;

    if (canEdit) {
      document.getElementById("save-atlas-tracking-btn").addEventListener("click", () => {
        const entities = variation.svgs.map((_, i) => {
          const input = document.querySelector(`.js-atlas-sample-id[data-index="${i}"]`);
          return { sample_id: input.value.trim() || null, location: (tracking[i] && tracking[i].location) || null };
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
  if (!isEditorRole() || viewMode) {
    container.innerHTML = `<div class="section-title" style="margin-bottom:14px;">Conclusion</div><div class="help" style="font-style:italic;">Pas encore conclue — expérience en cours.</div>`;
    return;
  }
  container.innerHTML = `
    <div class="section-title" style="margin-bottom:14px;">Conclure l'expérience</div>
    <form id="conclude-form" class="field-group">
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

function renderEvidence(detail) {
  const list = document.getElementById("evidence-list");
  list.innerHTML = detail.evidence.length
    ? detail.evidence
        .map((e) => {
          const metricEntries = Object.entries(e.metrics || {});
          const metricText = metricEntries
            .map(([name, q]) => `${escapeHtml(name)} : ${escapeHtml(String(q.value))}${q.unit ? " " + escapeHtml(q.unit) : ""}`)
            .join(" · ");
          return `
            <div style="padding:10px 0;border-top:1px solid var(--border-soft);">
              <div style="font-size:13px;font-weight:600;">${escapeHtml(e.description)}</div>
              <div style="font-size:12px;color:var(--text-soft);margin-top:2px;word-break:break-all;">${e.source.startsWith("http") ? `<a href="${escapeHtml(e.source)}" target="_blank" rel="noopener">${escapeHtml(e.source)}</a>` : escapeHtml(e.source)}</div>
              ${metricText ? `<div class="mono" style="font-size:11.5px;color:var(--text-faint);margin-top:4px;">${metricText}</div>` : ""}
            </div>`;
        })
        .join("")
    : `<div class="help">Aucune preuve enregistrée.</div>`;

  const formWrap = document.getElementById("add-evidence-wrap");
  if (!isEditorRole() || viewMode) {
    formWrap.innerHTML = "";
    return;
  }
  formWrap.innerHTML = `
    <form id="evidence-form" class="field-group" style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border-soft);">
      <div><label>Description</label><input class="field" id="evidence-description" placeholder="ex : mesure d'épaisseur au profilomètre" required></div>
      <div><label>Source</label><input class="field" id="evidence-source" placeholder="lien, fichier ou référence" required></div>
      <div class="field-row">
        <input class="field" id="evidence-metric-name" placeholder="mesure (optionnel)">
        <input class="field" id="evidence-metric-value" type="number" placeholder="valeur">
      </div>
      <button class="btn btn-line btn-block" type="submit">Ajouter la preuve</button>
    </form>`;
  document.getElementById("evidence-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const metricName = document.getElementById("evidence-metric-name").value.trim();
    const metricValueRaw = document.getElementById("evidence-metric-value").value;
    try {
      const result = await api.post(`/api/projects/${slug}/experiences/${experienceId}/preuves`, {
        description: document.getElementById("evidence-description").value,
        source: document.getElementById("evidence-source").value,
        metric_name: metricName || null,
        metric_value: metricValueRaw ? parseFloat(metricValueRaw) : null,
      });
      // preuves records a new version carrying the evidence (experiences are immutable) - go to
      // it, not back to this now-superseded version.
      window.location.href = `/projets/${slug}/experiences/${result.id}`;
    } catch (err) {
      showError(err);
    }
  });
}

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
  const canEdit = isEditorRole() && !viewMode;
  const chips = detail.tags
    .map(
      (t, i) => `
      <span class="badge badge-role">
        ${escapeHtml(t)}
        ${
          canEdit
            ? `<button class="js-remove-tag" data-index="${i}" type="button" style="background:none;border:none;cursor:pointer;color:inherit;padding:0;margin-left:2px;font-size:13px;line-height:1;">&times;</button>`
            : ""
        }
      </span>`
    )
    .join("");
  row.innerHTML =
    chips +
    (canEdit
      ? `<input id="new-tag-input" placeholder="+ étiquette" style="border:1px dashed var(--border-soft);border-radius:999px;padding:4px 10px;font-size:12px;width:110px;background:transparent;">`
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
  const canEdit = isEditorRole() && !viewMode;
  const current = detail.physical_tracking[0] || {};
  if (!canEdit) {
    card.innerHTML =
      current.sample_id || current.location
        ? `<div style="font-size:13px;">
            ${current.sample_id ? `Identifiant&nbsp;: <strong>${escapeHtml(current.sample_id)}</strong>` : ""}
            ${current.location ? `<br>Emplacement&nbsp;: <strong>${escapeHtml(current.location)}</strong>` : ""}
          </div>`
        : `<div class="help">Aucun suivi physique enregistré.</div>`;
    return;
  }
  card.innerHTML = `
    <div class="field-row" style="margin-bottom:10px;">
      <div><label>Identifiant physique</label><input class="field" id="physical-sample-id" value="${escapeHtml(current.sample_id || "")}" placeholder="ex : W12-A3"></div>
      <div><label>Emplacement</label><input class="field" id="physical-location" value="${escapeHtml(current.location || "")}" placeholder="ex : congélateur B, tiroir 2"></div>
    </div>
    <button class="btn btn-line" id="save-physical-tracking-btn" type="button">Enregistrer</button>`;
  document.getElementById("save-physical-tracking-btn").addEventListener("click", () => {
    savePhysicalTracking([
      {
        sample_id: document.getElementById("physical-sample-id").value.trim() || null,
        location: document.getElementById("physical-location").value.trim() || null,
      },
    ]);
  });
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

// Le rapport reprend tel quel le contenu déjà affiché (le mode vue garantit qu'aucun formulaire
// d'édition ne s'y trouve) - pas de génération séparée à maintenir en double, juste les cartes qui
// ont un sens hors de l'appli (pas "Comparer avec", un outil interactif, ni "Actions avancées").
const REPORT_SECTION_IDS = ["header-card", "matrix-card", "physical-tracking-card", "evidence-card", "conclusion-section", "references-card"];

async function generateReportHtml() {
  const css = await fetch("/static/css/style.css").then((r) => r.text());
  const threeCol = document.querySelector(".fiche-3col");
  const sections = [document.getElementById("header-card"), threeCol, ...REPORT_SECTION_IDS.slice(1).map((id) => document.getElementById(id))]
    .filter((el) => el)
    .map((el) => el.outerHTML)
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
  #evolve-btn,#mode-toggle-btn,#export-report-btn,#advanced-actions{display:none !important;}
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

function applyModeVisibility() {
  const editing = isEditorRole() && !viewMode;
  document.getElementById("evolve-btn").style.display = editing ? "" : "none";
  document.getElementById("advanced-actions").style.display = editing ? "" : "none";
  document.getElementById("mode-toggle-btn").textContent = viewMode ? "Repasser en mode édition" : "Passer en mode vue";
  // un visiteur (rôle viewer) est déjà en permanence sur une fiche épurée - le bouton d'export lui
  // reste donc toujours proposé, sans passer par le bouton de bascule qui n'a de sens que pour
  // editor/owner.
  document.getElementById("export-report-btn").style.display = !isEditorRole() || viewMode ? "" : "none";
}

function toggleViewMode() {
  viewMode = !viewMode;
  applyModeVisibility();
  renderTags(currentDetail);
  renderPhysicalTracking(currentDetail);
  renderEvidence(currentDetail);
  renderConclusion(currentDetail);
  renderBatchMatrix(currentDetail);
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
    renderObjectives(currentDetail);
    renderForksNote(currentDetail);
    renderReferences(currentDetail);
    renderConclusion(currentDetail);
    renderBatchMatrix(currentDetail);
    renderPhysicalTracking(currentDetail);
    renderEvidence(currentDetail);

    if (isEditorRole()) {
      document.getElementById("mode-toggle-btn").style.display = "";
      document.getElementById("mode-toggle-btn").addEventListener("click", toggleViewMode);
      document.getElementById("evolve-btn").addEventListener("click", () => {
        window.location.href = `/projets/${slug}/experiences/${experienceId}/evoluer`;
      });
      populateCombineSelect();
    }
    document.getElementById("export-report-btn").addEventListener("click", downloadReport);
    applyModeVisibility();

    const [timeline, diff, process] = await Promise.all([
      api.get(`/api/projects/${slug}/experiences/${experienceId}/timeline`),
      api.get(`/api/projects/${slug}/experiences/${experienceId}/diff`),
      api.get(`/api/projects/${slug}/experiences/${experienceId}/process`).catch(() => null),
    ]);
    currentProcess = process;
    renderTimeline(timeline.items);
    renderStructure(currentDetail, diff);
    populateCompareProjectSelect();
  } catch (err) {
    showError(err);
  }
}

init();
