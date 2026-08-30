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
let currentDetail = null;

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
      return `
        <div style="display:flex;gap:10px;align-items:flex-start;">
          <div style="width:18px;height:18px;border-radius:999px;background:${iconBg};color:${iconColor};display:flex;align-items:center;justify-content:center;flex:none;margin-top:1px;">${icon}</div>
          <div>
            <div style="font-size:13px;font-weight:600;">${escapeHtml(o.name)}</div>
            <div style="font-size:12px;color:var(--text-faint);">${escapeHtml(statusText)}</div>
          </div>
        </div>`;
    })
    .join("");
}

function renderTimeline(items) {
  const el = document.getElementById("timeline");
  el.innerHTML = items
    .map((item, i) => {
      const isLast = i === items.length - 1;
      return `
        <div class="timeline-item ${isLast ? "current" : ""}">
          <div class="timeline-date">${formatDate(item.created_at)}${isLast ? " · version actuelle" : ""}</div>
          <div class="timeline-title">${escapeHtml(item.title)}</div>
          <div class="timeline-desc">${escapeHtml(item.intent)}</div>
        </div>`;
    })
    .join("");
}

function renderStructure(detail, diff) {
  document.getElementById("structure-svg").innerHTML = detail.structure_svg || "<div class='help'>Pas de schéma pour ce type de structure.</div>";
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

async function renderBatchMatrix(detail) {
  const card = document.getElementById("matrix-card");
  if (!detail.is_batch) {
    card.style.display = "none";
    return;
  }
  card.style.display = "";
  try {
    const variation = await api.get(`/api/projects/${slug}/experiences/${experienceId}/matrice`);
    const el = document.getElementById("matrix-content");
    if (variation.varying.length === 0) {
      el.innerHTML = `<div class="help">Les ${variation.entity_count} échantillons sont identiques sur tous les paramètres suivis.</div>`;
      return;
    }
    const summary = variation.factor_label
      ? `<div style="font-size:14px;font-weight:600;margin-bottom:4px;">${escapeHtml(variation.factor_label)}</div>
         <div style="font-size:13px;color:var(--text-soft);margin-bottom:14px;">${variation.entity_count} échantillons &middot; valeurs : ${variation.factor_values.map((v) => escapeHtml(String(v))).join(", ")}</div>`
      : `<div style="font-size:12.5px;color:var(--text-soft);margin-bottom:10px;">${variation.entity_count} échantillons &middot; ${variation.varying.length} paramètre(s) réellement variable(s)</div>`;

    const rawTable = `
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
      </table>`;

    el.innerHTML = `
      ${summary}
      <details>
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
    container.innerHTML = `
      <div class="section-title" style="margin-bottom:14px;">Conclusion</div>
      ${c.summary ? `<p style="font-size:13.5px;line-height:1.6;margin-bottom:10px;">${escapeHtml(c.summary)}</p>` : ""}
      ${c.decision ? `<div style="font-size:12.5px;color:var(--text-soft);">Décision&nbsp;: <strong>${escapeHtml(c.decision)}</strong></div>` : ""}
      ${c.next_steps ? `<div style="font-size:12.5px;color:var(--text-soft);margin-top:4px;">Suite&nbsp;: ${escapeHtml(c.next_steps)}</div>` : ""}
    `;
    return;
  }
  if (currentRole !== "editor" && currentRole !== "owner") {
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
  document.getElementById("objective-results").innerHTML = currentDetail.objectives
    .map(
      (o, i) => `
      <div style="margin-bottom:6px;">
        <label>${escapeHtml(o.name)}</label>
        <select class="field" data-objective="${escapeHtml(o.name)}" id="obj-result-${i}">
          <option value="met">Atteint</option>
          <option value="not_met">Non atteint</option>
          <option value="partially_met">Partiellement atteint</option>
          <option value="inconclusive">Non concluant</option>
        </select>
      </div>`
    )
    .join("");

  document.getElementById("conclude-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const objectiveResults = currentDetail.objectives.map((o, i) => ({
      objective: o.name,
      status: document.getElementById(`obj-result-${i}`).value,
    }));
    try {
      await api.post(`/api/projects/${slug}/experiences/${experienceId}/conclure`, {
        status: document.getElementById("conclude-status").value,
        decision: document.getElementById("conclude-decision").value || null,
        summary: document.getElementById("conclude-summary").value || null,
        next_steps: document.getElementById("conclude-next-steps").value || null,
        objective_results: objectiveResults,
      });
      window.location.reload();
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
  if (currentRole !== "editor" && currentRole !== "owner") {
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
      await api.post(`/api/projects/${slug}/experiences/${experienceId}/preuves`, {
        description: document.getElementById("evidence-description").value,
        source: document.getElementById("evidence-source").value,
        metric_name: metricName || null,
        metric_value: metricValueRaw ? parseFloat(metricValueRaw) : null,
      });
      window.location.reload();
    } catch (err) {
      showError(err);
    }
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

async function init() {
  try {
    currentDetail = await api.get(`/api/projects/${slug}/experiences/${experienceId}`);
    const project = await api.get(`/api/projects/${slug}`);
    currentRole = project.role;
    document.getElementById("project-crumb").textContent = project.name;
    document.getElementById("project-crumb").href = `/projets/${slug}`;

    renderHeader(currentDetail);
    renderObjectives(currentDetail);
    renderReferences(currentDetail);
    renderConclusion(currentDetail);
    renderBatchMatrix(currentDetail);
    renderEvidence(currentDetail);

    if (currentRole === "editor" || currentRole === "owner") {
      document.getElementById("evolve-btn").style.display = "";
      document.getElementById("evolve-btn").addEventListener("click", () => {
        window.location.href = `/projets/${slug}/experiences/${experienceId}/evoluer`;
      });
    }

    const [timeline, diff] = await Promise.all([
      api.get(`/api/projects/${slug}/experiences/${experienceId}/timeline`),
      api.get(`/api/projects/${slug}/experiences/${experienceId}/diff`),
    ]);
    renderTimeline(timeline.items);
    renderStructure(currentDetail, diff);
    populateCompareProjectSelect();
  } catch (err) {
    showError(err);
  }
}

init();
