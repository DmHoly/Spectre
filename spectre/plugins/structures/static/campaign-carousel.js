/* Les variantes d'une campagne : valeur d'un paramètre telle qu'on l'écrit (formatParamValue),
   légende d'une variante (variantCaption) et carrousel des structures (mountStructureCarousel),
   partagés par le constructeur, la fiche d'expérience, l'atlas, la vue d'ensemble d'un µprojet et
   les graphiques du cahier de données. */

// Une valeur de paramètre telle qu'on l'écrit : 20 (pas 20.000001), et en notation scientifique
// pour les très grandes/petites grandeurs - 1e17, 3.16e17 (un dopage), jamais 100000000000000000.
// Même règle que spectre.core.structures.format_number côté serveur. Affichage seulement (3
// chiffres significatifs) : pour pré-remplir un champ, voir formatNumberInput (form-widgets.js).
function formatParamValue(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return value == null ? "" : String(value);
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1e5 || abs < 1e-3) {
    const [mantissa, exponent] = value.toExponential(2).split("e");
    return `${mantissa.replace(/\.?0+$/, "")}e${parseInt(exponent, 10)}`;
  }
  return Number.isInteger(value) ? String(value) : String(parseFloat(value.toPrecision(6)));
}

// Ce qui change entre deux variantes d'une campagne, pour l'entité `i` d'un `/matrice`
// (spectre.api.experiments::experience_batch) : "Épaisseur — Dépôt : 10" plutôt que le simple "10"
// de `variation.labels[i]`, qui ne dit jamais *quel* paramètre a cette valeur (utilisé par le
// carrousel de structure de atlas.js et lineage-view.js). Retombe sur `labels[i]` seul si
// `factor_labels`/`factor_values` sont absents (campagnes lancées avant leur ajout).
function variantCaption(variation, i) {
  const factorLabels = variation.factor_labels || [];
  const factorValues = (variation.factor_values || [])[i];
  if (factorLabels.length && factorValues) {
    return factorLabels.map((label, j) => `${label} : ${formatParamValue(factorValues[j])}`).join(" · ");
  }
  const labels = variation.labels || [];
  return labels[i] != null ? String(labels[i]) : `#${i + 1}`;
}

// Carrousel des structures d'une campagne (réponse de /matrice : `svgs`, `labels`, facteurs) : la
// référence (1re variante, marquée « RÉF » comme partout ailleurs - voir
// structures.render_structure_svg) puis chaque variante, avec la valeur de ses paramètres variés.
// Flèches, points, et ← → au clavier une fois le carrousel focalisé. `onChange(index)` suit le
// défilement. Partagé par la fiche d'expérience, l'atlas et la vue d'ensemble d'un µprojet.
function mountStructureCarousel(container, variation, { onChange } = {}) {
  const svgs = (variation && variation.svgs) || [];
  if (!container || svgs.length === 0) {
    if (container) container.innerHTML = "";
    return null;
  }
  let index = 0;
  function paint() {
    const single = svgs.length < 2;
    container.innerHTML = `
      <div class="atlas-carousel" tabindex="0" role="group" aria-roledescription="carrousel" aria-label="Structures des ${svgs.length} variantes">
        <div class="atlas-carousel__badge">${index === 0 ? `<span class="badge badge-role">RÉF</span>` : ""}<span>${escapeHtml(variantCaption(variation, index))}</span></div>
        <div class="atlas-carousel__stage">${svgs[index]}</div>
        <div class="atlas-carousel__nav">
          <button type="button" class="btn btn-line" data-dir="-1" aria-label="Variante précédente" ${single ? "disabled" : ""}>&larr;</button>
          <span class="atlas-carousel__dots" aria-hidden="true">${
            svgs.length <= 24 ? svgs.map((_, i) => `<span class="atlas-carousel__dot${i === index ? " is-active" : ""}" data-go="${i}"></span>`).join("") : ""
          }</span>
          <span class="help">${index + 1} / ${svgs.length}</span>
          <button type="button" class="btn btn-line" data-dir="1" aria-label="Variante suivante" ${single ? "disabled" : ""}>&rarr;</button>
        </div>
      </div>`;
  }
  function go(next, focus) {
    index = (next + svgs.length) % svgs.length;
    paint();
    if (focus) container.querySelector(".atlas-carousel").focus();
    if (onChange) onChange(index);
  }
  container.onclick = (event) => {
    const dir = event.target.closest("[data-dir]");
    if (dir) return go(index + parseInt(dir.dataset.dir, 10), false);
    const dot = event.target.closest("[data-go]");
    if (dot) go(parseInt(dot.dataset.go, 10), false);
  };
  container.onkeydown = (event) => {
    if (!event.target.closest(".atlas-carousel")) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      go(index + (event.key === "ArrowLeft" ? -1 : 1), true);
    }
  };
  paint();
  return {
    get index() {
      return index;
    },
    go: (i) => go(i, false),
  };
}
