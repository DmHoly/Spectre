/* Onglet « Structure & plaques », côté structure : la structure affichée et ce qui a changé depuis la
   version de structure précédente (en carrousel pour une campagne, en planche pour une structure en
   images), le détail de chaque couche (aperçu au survol, paramètres de l'étape au clic), les étapes
   du procédé avec le nombre de données du cahier de chacune (un clic filtre le cahier), la
   cartographie et la feuille de split d'une campagne, la comparaison avec une autre étude, et la
   modification des images d'une structure en images. */

(() => {
  let ctx = null;
  let variantIndex = 0; // la variante affichée par le carrousel d'une campagne (0 = la référence)

  // Ce qui a changé quand une structure en images est en jeu : le résumé en clair calculé par le
  // serveur plutôt que les chemins bruts (images[1].image_id...).
  function summaryHtml(lines) {
    return lines.map((line) => `<div style="font-size:12.5px;color:var(--text-soft);padding:2px 0;">${escapeHtml(line)}</div>`).join("");
  }

  function entriesHtml(entries, limit, fontSize) {
    return entries
      .slice(0, limit)
      .map((e) => `<div class="mono" style="font-size:${fontSize};color:var(--text-soft);padding:2px 0;">${escapeHtml(e.path)} : ${escapeHtml(JSON.stringify(e.before))} &rarr; ${escapeHtml(JSON.stringify(e.after))}</div>`)
      .join("");
  }

  async function renderStructure(detail) {
    const container = document.getElementById("structure-svg");
    const hint = document.getElementById("structure-click-hint");
    const diffNote = document.getElementById("diff-note");
    const diffDetails = document.getElementById("diff-details");
    variantIndex = 0;
    const diffPromise = experimentsApi.structureDiff(ctx.microprojectSlug, ctx.experimentId, { version: ctx.versionId });

    if (detail.structure_images) {
      // une structure en images (schéma, coupes TEM...) : la planche
      const images = detail.structure_images;
      document.getElementById("structure-title").textContent =
        images.length > 1 ? `Structure · ${images.length} images` : `Structure · ${STRUCTURE_IMAGE_KIND_LABELS[images[0].kind] || "Image"}`;
      container.className = "";
      container.innerHTML = structureBoardHtml(images);
      hint.style.display = "none";
    } else if (detail.is_batch) {
      // une campagne : un carrousel (référence + chaque variante, avec ses paramètres variés)
      document.getElementById("structure-title").textContent = "Structures des variantes";
      container.className = "layer-clickable fiche-structure-carousel";
      try {
        mountStructureCarousel(container, await ctx.variants(), {
          onChange: (index) => {
            variantIndex = index;
            hideTooltip();
            hint.style.display = ctx.process && index === 0 ? "" : "none";
          },
        });
      } catch (err) {
        container.innerHTML = detail.structure_svg || "";
      }
      hint.style.display = ctx.process ? "" : "none";
    } else {
      document.getElementById("structure-title").textContent = "Structure actuelle";
      container.className = "layer-clickable builder-canvas-svg";
      container.innerHTML = detail.structure_svg || "<div class='help'>Pas de schéma pour ce type de structure.</div>";
      hint.style.display = ctx.process ? "" : "none";
    }

    const diff = await diffPromise;
    const lines = diff.summary || [];
    if (!diff.target) {
      diffNote.textContent = "";
      diffDetails.innerHTML = "";
    } else if (diff.summary) {
      // une structure en images d'un côté ou de l'autre : pas de liste de paramètres qui ait un sens
      diffNote.textContent = lines.length ? "" : "identique à la version précédente";
      diffDetails.innerHTML = summaryHtml(lines);
    } else if (!diff.entries.length) {
      diffNote.textContent = "identique à la version précédente";
      diffDetails.innerHTML = "";
    } else {
      const n = diff.entries.length;
      diffNote.innerHTML = `<span style="color:var(--abandoned);font-weight:600;">${n} paramètre${n > 1 ? "s" : ""} modifié${n > 1 ? "s" : ""}</span>`;
      diffDetails.innerHTML = entriesHtml(diff.entries, 12, "11.5px");
    }
  }

  // --- les couches : la convention data-layer-index du constructeur (0 = substrat, N = l'étape N-1) --

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

  // Le titre et les paramètres de la couche `layerIndex` ; null si le procédé ne la décrit pas.
  function layerFields(layerIndex) {
    if (!ctx.process) return null;
    if (layerIndex === 0) {
      const s = ctx.process.substrate || {};
      const fields = [
        ["Matériau", s.material],
        ["Largeur du domaine", formatStepValue(s.domain_width)],
        ["Épaisseur", formatStepValue(s.thickness)],
      ].filter(([, v]) => v);
      return { title: "Substrat", fields };
    }
    const step = (ctx.process.steps || [])[layerIndex - 1];
    if (!step) return null;
    const fields = Object.entries(step)
      .filter(([key]) => key !== "id" && key !== "kind" && key !== "name")
      .map(([key, value]) => [ExperimentVocabulary.stepFields[key] || key, formatStepValue(value)])
      .filter(([, value]) => value !== null);
    return { title: ExperimentVocabulary.stepLabel(step), fields };
  }

  function showLayerModal(layerIndex) {
    const layer = layerFields(layerIndex);
    if (!layer) return;
    document.getElementById("layer-modal-title").textContent = layer.title;
    document.getElementById("layer-modal-body").innerHTML = layer.fields.length
      ? layer.fields
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

  // Au survol, un aperçu condensé (les 4 premiers paramètres) qui suit le curseur.
  const tooltip = document.getElementById("layer-tooltip");
  function showTooltip(layerIndex, x, y) {
    const layer = layerFields(layerIndex);
    if (!layer) return hideTooltip();
    tooltip.innerHTML = `<strong>${escapeHtml(layer.title)}</strong>${layer.fields
      .slice(0, 4)
      .map(([label, value]) => `${escapeHtml(label)} : ${escapeHtml(value)}`)
      .join("<br>")}`;
    tooltip.style.display = "";
    tooltip.style.left = `${x + 14}px`; // décalé pour ne pas passer sous la pointe de la souris
    tooltip.style.top = `${y + 14}px`;
  }
  function hideTooltip() {
    tooltip.style.display = "none";
  }

  const structureSvg = document.getElementById("structure-svg");
  const layerAt = (event) => (variantIndex > 0 ? null : event.target.closest("[data-layer-index]"));
  structureSvg.addEventListener("click", (event) => {
    const layer = layerAt(event);
    if (layer) showLayerModal(Number(layer.dataset.layerIndex));
  });
  structureSvg.addEventListener("mousemove", (event) => {
    const layer = layerAt(event);
    if (layer) showTooltip(Number(layer.dataset.layerIndex), event.clientX, event.clientY);
    else hideTooltip();
  });
  structureSvg.addEventListener("mouseleave", hideTooltip);
  document.getElementById("layer-modal-close-btn").addEventListener("click", () => document.getElementById("layer-modal").close());

  // --- les étapes du procédé, avec les données du cahier qui les concernent -------------------------

  // Le nombre de données par étape (les entrées qui s'appliquent à cette version et y ont une mesure)
  // vient du panneau du cahier (ctx.notebook.stepCounts) : la fiche ne lit pas le cahier elle-même.
  const processCard = document.getElementById("process-card");
  const processSteps = document.getElementById("process-steps");
  const DATA_ICON = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/></svg>`;

  function renderProcessSteps() {
    const steps = (ctx.process && ctx.process.steps) || [];
    processCard.hidden = !steps.length;
    const counts = (ctx.notebook && ctx.notebook.stepCounts) || {};
    processSteps.innerHTML = steps
      .map((step, i) => {
        const n = counts[step.id] || 0;
        const kind = ExperimentVocabulary.stepKinds[step.kind] || step.kind;
        const label = `${i + 1}. ${ExperimentVocabulary.stepLabel(step)}`;
        const badge = n
          ? `<button type="button" class="process-step__data" data-step="${escapeHtml(step.id)}" title="Voir ces données dans le cahier" aria-label="${n} donnée${n > 1 ? "s" : ""} à l'étape ${escapeHtml(label)} : les voir dans le cahier">${DATA_ICON}${n}</button>`
          : "";
        return `
          <li class="process-step${n ? " has-data" : ""}" title="${escapeHtml(label)}">
            <span class="process-step__num" aria-hidden="true">${i + 1}</span>
            <span class="process-step__text"><span class="process-step__name">${escapeHtml(step.name || kind)}</span><span class="process-step__kind">${escapeHtml(kind)}</span></span>
            ${badge}
          </li>`;
      })
      .join("");
    const measured = steps.filter((step) => counts[step.id]).length;
    document.getElementById("process-steps-note").textContent = ctx.notebook
      ? measured
        ? `données du cahier à ${measured} étape${measured > 1 ? "s" : ""} - un clic les montre`
        : "aucune donnée du cahier rattachée à une étape"
      : "";
  }

  processSteps.addEventListener("click", (event) => {
    const badge = event.target.closest("[data-step]");
    if (badge) ctx.filterNotebook(badge.dataset.step);
  });
  ExperiencePage.onNotebook(() => {
    if (ctx) renderProcessSteps();
  });

  // --- une campagne : cartographie des variantes et feuille de split --------------------------------

  async function renderBatchMatrix(detail) {
    const card = document.getElementById("matrix-card");
    card.style.display = detail.is_batch ? "" : "none";
    if (!detail.is_batch) return;
    const variation = await ctx.variants();
    const labels = variation.labels || variation.svgs.map((_, i) => `#${i + 1}`);
    const tracking = variation.physical_tracking || [];

    // Cartographie : chaque variante telle que StructureForge l'a simulée, avec le lasermark de sa plaque.
    document.getElementById("atlas-content").innerHTML = `
      <div class="atlas-grid">
        ${variation.svgs
          .map((svg, i) => {
            const lasermark = (tracking[i] || {}).sample_id;
            return `<div class="atlas-tile">${svg}<div class="atlas-label">${escapeHtml(labels[i])}</div>${lasermark ? `<div class="atlas-tile__lasermark mono">${escapeHtml(lasermark)}</div>` : ""}</div>`;
          })
          .join("")}
      </div>`;

    const el = document.getElementById("matrix-content");
    const hasFactors = variation.factor_labels && variation.factor_labels.length > 0;
    if (variation.varying.length === 0 && !hasFactors) {
      el.innerHTML = `<div class="help">Les ${variation.entity_count} échantillons sont identiques sur tous les paramètres suivis.</div>`;
      return;
    }

    // Feuille de split : une ligne par échantillon, une colonne par paramètre varié (les campagnes
    // d'avant le multi-paramètre n'ont pas factor_labels : une colonne « Paramètre »).
    const factorLabels = hasFactors ? variation.factor_labels : ["Paramètre"];
    const splitSheet = `
      <table style="border-collapse:collapse;font-size:13px;width:100%;">
        <thead><tr style="text-align:left;color:var(--text-faint);font-size:11px;text-transform:uppercase;">
          <th style="padding:4px 10px 4px 0;">Échantillon</th>
          ${factorLabels
            .map((label, j) => {
              const log = (variation.factor_scales || [])[j] === "log";
              return `<th style="padding:4px 10px;">${escapeHtml(label)}${log ? ` <span style="text-transform:none;font-weight:500;">(échelle log)</span>` : ""}</th>`;
            })
            .join("")}
        </tr></thead>
        <tbody>
          ${labels
            .map((label, i) => {
              const values = variation.factor_values && variation.factor_values[i] ? variation.factor_values[i] : [label];
              return `<tr style="border-top:1px solid var(--border-soft);">
                <td class="mono" style="padding:6px 10px 6px 0;">${escapeHtml(label)}</td>
                ${values.map((v) => `<td class="mono" style="padding:6px 10px;">${escapeHtml(formatParamValue(v))}</td>`).join("")}
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
  }

  // --- comparer la structure avec une autre étude (de ce µprojet ou d'un autre) ---------------------

  const compareMicroproject = document.getElementById("compare-microproject-select");
  const compareSearch = document.getElementById("compare-search");
  const compareSelect = document.getElementById("compare-select");
  const compareResult = document.getElementById("compare-result");

  async function fillCompareSelect() {
    try {
      const items = await ExperiencePage.otherExperiments(compareMicroproject.value || ctx.microprojectSlug, compareSearch.value.trim());
      compareSelect.innerHTML = items.length
        ? items.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)}</option>`).join("")
        : `<option value="">Aucune expérience à comparer</option>`;
    } catch (err) {
      compareSelect.innerHTML = `<option value="">—</option>`;
    }
  }

  let microprojectsLoaded = false;
  async function renderCompare() {
    compareResult.innerHTML = "";
    if (!microprojectsLoaded) {
      microprojectsLoaded = true;
      try {
        const mine = await microprojectsApi.list();
        compareMicroproject.innerHTML = mine
          .map((p) => `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}${p.slug === ctx.microprojectSlug ? " (ce µprojet)" : ""}</option>`)
          .join("");
        compareMicroproject.value = ctx.microprojectSlug;
      } catch (err) {
        // la comparaison est secondaire : ce µprojet seulement
      }
    }
    await fillCompareSelect();
  }

  let searchTimer = null;
  compareSearch.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fillCompareSelect, 250);
  });
  compareMicroproject.addEventListener("change", fillCompareSelect);
  document.getElementById("compare-btn").addEventListener("click", async () => {
    const target = compareSelect.value;
    if (!target) return;
    const other = compareMicroproject.value || ctx.microprojectSlug;
    try {
      const diff = await experimentsApi.structureDiff(ctx.microprojectSlug, ctx.experimentId, {
        version: ctx.versionId,
        against_experiment: target,
        against_microproject: other === ctx.microprojectSlug ? null : other,
      });
      if (diff.summary) compareResult.innerHTML = summaryHtml(diff.summary);
      else if (!diff.entries.length) compareResult.innerHTML = `<div class="help">Aucune différence de structure.</div>`;
      else compareResult.innerHTML = entriesHtml(diff.entries, 20, "11px");
    } catch (err) {
      ctx.showError(err);
    }
  });

  // --- structure en images : modifier la planche, sans nouvelle version de structure ----------------

  const replaceDialog = document.getElementById("replace-drawing-dialog");
  const replaceError = document.getElementById("replace-drawing-error");
  const replaceSave = document.getElementById("replace-drawing-save");
  let replaceDrop = null;

  function showReplaceError(err) {
    replaceError.textContent = err ? err.message || String(err) : "";
    replaceError.style.display = err ? "block" : "none";
  }

  function openReplaceDrawing() {
    if (!replaceDrop) {
      replaceDrop = mountImageDrop(document.getElementById("replace-drawing-drop"), {
        slug: ctx.microprojectSlug,
        onChange: () => showReplaceError(null),
        onError: showReplaceError,
        isActive: () => replaceDialog.open,
      });
    }
    replaceDrop.set(ctx.detail.structure_images);
    showReplaceError(null);
    replaceSave.disabled = false;
    replaceDialog.showModal();
    document.querySelector("#replace-drawing-drop .img-board__bar .img-board__add")?.focus();
  }

  replaceSave.addEventListener("click", async () => {
    const images = replaceDrop.get();
    if (replaceDrop.isUploading()) return showReplaceError(new Error("Une image est encore en cours d'envoi - un instant."));
    if (!images.length) return showReplaceError(new Error("Il faut au moins une image."));
    replaceSave.disabled = true;
    const body = { images: images.map((img) => ({ ...img, caption: (img.caption || "").trim() || null })) };
    // un refus s'affiche dans la modale ; un 412 la ferme, pour le bandeau
    const done = await ctx.write(() => experimentsApi.replaceStructureImages(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, body), replaceError);
    if (done) replaceDialog.close();
    else replaceSave.disabled = false;
  });
  document.getElementById("replace-drawing-cancel").addEventListener("click", () => replaceDialog.close());

  const evolveLink = document.getElementById("structure-evolve-link");
  const replaceBtn = document.getElementById("structure-replace-btn");
  evolveLink.addEventListener("click", () => (window.location.href = ExperiencePage.evolveUrl()));
  replaceBtn.addEventListener("click", openReplaceDrawing);

  ExperiencePage.registerPanel({
    key: "structure",
    mount(el, context) {
      ctx = context;
      evolveLink.style.display = ctx.canEdit && ctx.process ? "" : "none";
      replaceBtn.style.display = ctx.canEdit && ctx.detail.structure_images ? "" : "none";
      renderProcessSteps();
      return Promise.all([renderStructure(ctx.detail), renderBatchMatrix(ctx.detail), renderCompare()]);
    },
  });
})();
