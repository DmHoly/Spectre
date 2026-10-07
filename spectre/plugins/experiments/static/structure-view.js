/* Onglet « Structure & plaques », côté structure : la structure affichée (en carrousel pour une
   campagne, en planche pour une structure en images), le détail de chaque couche (aperçu au survol,
   paramètres de l'étape au clic), la feuille de split - une ligne par plaque, avec ce qu'on en sait -,
   les étapes du procédé avec le nombre de données du cahier de chacune (un clic filtre le cahier), et
   la modification des images d'une structure en images et de leurs annotations. Les étiquettes de
   couches, dessinées par le serveur à droite de la structure, se masquent et s'affichent
   (préférence de ce navigateur). */

(() => {
  let ctx = null;
  let variantIndex = 0; // la variante affichée par le carrousel d'une campagne (0 = la première)

  // --- les étiquettes de couches : affichées par défaut, masquées au choix ---------------------------

  const LABELS_PREF_KEY = "spectre.structure-labels";
  const labelsBtn = document.getElementById("structure-labels-btn");

  // la préférence de ce navigateur (le stockage peut manquer : navigation privée...)
  let labelsVisible = true;
  try {
    labelsVisible = window.localStorage.getItem(LABELS_PREF_KEY) !== "hidden";
  } catch (err) {
    labelsVisible = true;
  }
  const labelsShown = () => labelsVisible;

  // Chaque structure étiquetée (svg.sp-labelled-structure, rendering.labelled_svg) : avec ses
  // étiquettes, ou réduite au seul dessin (data-bare-viewbox) quand on les masque.
  function applyLabels(root) {
    const shown = labelsShown();
    root.querySelectorAll("svg.sp-labelled-structure").forEach((svg) => {
      if (!svg.dataset.labelledViewbox) svg.dataset.labelledViewbox = svg.getAttribute("viewBox");
      const viewBox = shown ? svg.dataset.labelledViewbox : svg.dataset.bareViewbox;
      const [, , width, height] = viewBox.split(" ");
      svg.setAttribute("viewBox", viewBox);
      svg.setAttribute("width", width);
      svg.setAttribute("height", height);
      const labels = svg.querySelector(".sp-layer-labels");
      if (labels) labels.style.display = shown ? "" : "none";
    });
    const container = document.getElementById("structure-svg");
    const labelled = Boolean(container.querySelector("svg.sp-labelled-structure"));
    container.classList.toggle("has-layer-labels", labelled && shown);
  }

  function refreshLabelsButton() {
    const any = Boolean(document.querySelector("#panel-structure svg.sp-labelled-structure"));
    labelsBtn.style.display = any ? "" : "none";
    const shown = labelsShown();
    labelsBtn.setAttribute("aria-pressed", String(shown));
    labelsBtn.title = shown ? "Masquer les étiquettes des couches (ce navigateur s'en souvient)" : "Afficher les étiquettes des couches";
    document.getElementById("structure-labels-btn-text").textContent = shown ? "Étiquettes : masquer" : "Étiquettes : afficher";
  }

  function applyLabelsEverywhere() {
    applyLabels(document.getElementById("panel-structure"));
    refreshLabelsButton();
  }

  labelsBtn.addEventListener("click", () => {
    labelsVisible = !labelsVisible;
    try {
      window.localStorage.setItem(LABELS_PREF_KEY, labelsVisible ? "shown" : "hidden");
    } catch (err) {
      // pas de stockage : le choix vaut pour cette page
    }
    applyLabelsEverywhere();
  });

  // Les annotations de chaque image de la planche (kernel/static/annotations.js) : leur liste ; pour
  // un éditeur, leurs outils. Les enregistrer remplace la planche telle quelle, avec les annotations
  // de cette image (PUT .../structure-images) : une écriture légère, pas de nouvelle version de
  // structure.
  function mountPictureAnnotations(container, images) {
    container.querySelectorAll(".structure-picture").forEach((figure, i) => {
      const image = images[i];
      const img = figure.querySelector("img");
      ImageAnnotations.mount(figure.querySelector(".structure-picture__annotations"), {
        img,
        annotations: image.annotations || [],
        editable: ctx.canEdit,
        name: `l'image ${i + 1}`,
        onSave: (annotations) => {
          const body = {
            images: images.map((other) => ({
              image_id: other.image_id,
              kind: other.kind,
              caption: other.caption || null,
              annotations: other === image ? annotations : other.annotations || [],
            })),
          };
          return ctx.write(() => experimentsApi.replaceStructureImages(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, body));
        },
      });
    });
  }

  async function renderStructure(detail) {
    const container = document.getElementById("structure-svg");
    const hint = document.getElementById("structure-click-hint");
    variantIndex = 0;

    if (detail.structure_images) {
      // une structure en images (schéma, coupes TEM...) : la planche
      const images = detail.structure_images;
      document.getElementById("structure-title").textContent =
        images.length > 1 ? `Structure · ${images.length} images` : `Structure · ${STRUCTURE_IMAGE_KIND_LABELS[images[0].kind] || "Image"}`;
      container.className = "";
      container.innerHTML = structureBoardHtml(images);
      mountPictureAnnotations(container, images);
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
            applyLabelsEverywhere();
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
    applyLabelsEverywhere();
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

  // --- la feuille de split : une ligne par plaque, avec ce qu'on en sait ------------------------------

  // Une campagne : une place par variante, ses paramètres variés en colonnes (les campagnes d'avant le
  // multi-paramètre n'ont pas factor_labels : une colonne « Paramètre »), la plaque de référence
  // choisie au lancement (reference_place ; sans elle, la plaque d'une étude proche citée pour
  // comparaison, dans la note). Une étude simple : ses réplicats, la même structure - « répétition »
  // quand ils ont été déclarés comme tels au lancement.
  // Une campagne sans plaque de référence dans son split : la plaque citée pour comparaison (lasermark
  // et étude, en liens - le titre de l'étude lu chez elle, son id faute de mieux), sinon le dire. Du
  // HTML échappé ; rien quand le split a sa référence.
  async function comparisonNote(detail) {
    if (detail.reference_place !== null && detail.reference_place !== undefined) return "";
    const cited = detail.comparison_reference;
    if (!cited) return "pas de référence dans le split";
    const study = await experimentsApi.get(ctx.microprojectSlug, cited.experiment_id).catch(() => null);
    const studyUrl = `/microprojets/${encodeURIComponent(ctx.microprojectSlug)}/experiences/${encodeURIComponent(cited.experiment_id)}${
      cited.version_id ? `?version=${encodeURIComponent(cited.version_id)}` : ""
    }`;
    const studyLink = `<a href="${studyUrl}" title="L'étude de la plaque de comparaison">${escapeHtml(study ? study.title : cited.experiment_id)}</a>`;
    return cited.sample_id
      ? `comparaison : <a class="mono" href="${plateUrl(cited.sample_id)}" title="Le parcours de cette plaque">${escapeHtml(cited.sample_id)}</a> (${studyLink})`
      : `comparaison : ${studyLink}`;
  }

  async function renderSplit(detail) {
    const tracking = detail.physical_tracking && detail.physical_tracking.length ? detail.physical_tracking : [{}];
    let factorLabels = [];
    let factorScales = [];
    let rows;
    if (detail.is_batch) {
      const variation = await ctx.variants().catch(() => null);
      const labels = (variation && variation.labels) || tracking.map((_, i) => `Variante ${i + 1}`);
      const hasFactors = variation && variation.factor_labels && variation.factor_labels.length > 0;
      factorLabels = hasFactors ? variation.factor_labels : ["Paramètre"];
      factorScales = (variation && variation.factor_scales) || [];
      // la plaque de référence choisie au lancement, marquée « RÉF » aussi dans le carrousel
      rows = labels.map((label, i) => ({
        variant: i === detail.reference_place ? "Référence" : `Variante ${i + 1}`,
        values: hasFactors && variation.factor_values[i] ? variation.factor_values[i].map(formatParamValue) : [label],
        entry: tracking[i] || {},
      }));
    } else {
      const many = tracking.length > 1;
      rows = tracking.map((entry, i) => ({
        variant: !many ? "Référence" : detail.repeats ? (i === 0 ? "Référence" : "Répétition de la réf.") : `Réplicat ${i + 1}`,
        values: [],
        entry,
      }));
    }

    const named = rows.filter((r) => r.entry.sample_id).length;
    const studyFdl = detail.fdl || [];
    document.getElementById("split-note").innerHTML = [
      `${rows.length} plaque${rows.length > 1 ? "s" : ""}`,
      named === rows.length ? "toutes associées" : `${rows.length - named} à associer`,
      detail.is_batch ? await comparisonNote(detail) : detail.repeats && rows.length > 1 ? "répétitions exactes de la référence" : "",
    ]
      .filter(Boolean)
      .map((part, i) => (i < 2 ? escapeHtml(part) : part))
      .join(" · ");

    const plateCell = (entry) =>
      entry.sample_id
        ? `<a class="split-table__plate mono" href="${plateUrl(entry.sample_id)}" title="Le parcours de cette plaque">${escapeHtml(entry.sample_id)}</a>`
        : `<span class="split-table__missing ${studyFdl.length ? "is-fdl" : ""}">à associer${studyFdl.length ? " (FDL)" : ""}</span>`;
    document.getElementById("split-content").innerHTML = `
      <table class="split-table">
        <thead><tr>
          <th scope="col">#</th>
          <th scope="col">${detail.is_batch ? "Variante" : "Rôle"}</th>
          ${factorLabels
            .map((label, j) => `<th scope="col">${escapeHtml(label)}${factorScales[j] === "log" ? ` <span class="split-table__scale">log</span>` : ""}</th>`)
            .join("")}
          <th scope="col">Plaque</th>
          <th scope="col">FDL</th>
          <th scope="col">Emplacement</th>
        </tr></thead>
        <tbody>
          ${rows
            .map(
              (row, i) => `<tr>
                <td class="mono split-table__idx">${i + 1}</td>
                <td>${escapeHtml(row.variant)}</td>
                ${row.values.map((v) => `<td class="mono">${escapeHtml(v)}</td>`).join("")}
                <td>${plateCell(row.entry)}</td>
                <td>${row.entry.fdl && row.entry.fdl.length ? fdlChipsHtml(row.entry.fdl, { label: false }) : `<span class="split-table__empty">-</span>`}</td>
                <td>${row.entry.location ? escapeHtml(row.entry.location) : `<span class="split-table__empty">-</span>`}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

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
      return Promise.all([renderStructure(ctx.detail), renderSplit(ctx.detail)]);
    },
  });
})();
