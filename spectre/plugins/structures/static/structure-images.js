/* Affichage d'une structure en images (planche, aperçu) ; chaque image arrive avec l'`url` de ses
   octets (structure_images du détail d'une expérience) - rien ici ne la construit. */

/* Structure en images (spectre.core.structures.StructureImage) : un schéma collé depuis PowerPoint,
   des coupes TEM... à la place d'une structure dessinée - une ou plusieurs images, dans l'ordre où
   les lire. Affichées ainsi sur la fiche (la planche entière), le graphe d'un µprojet et l'atlas
   (la première, avec le nombre d'images). L'éditeur pour les coller, les
   ordonner ou les remplacer est dans image-drop.js. Chaque image porte ses annotations (flèches,
   cadres : kernel/static/annotations.js), dessinées partout où elle se montre ; la fiche monte sous
   chacune leur liste (.structure-picture__annotations) et, pour un éditeur, leurs outils. */
const STRUCTURE_IMAGE_KIND_LABELS = { schema: "Schéma", coupe: "Coupe TEM / MEB", autre: "Image" };

function structurePictureHtml(image, { index = null } = {}) {
  const url = image.url;
  const kind = STRUCTURE_IMAGE_KIND_LABELS[image.kind] || "Image";
  const alt = image.caption ? `${kind} : ${image.caption}` : `${kind} de la structure`;
  return `
    <figure class="structure-picture" data-image-id="${escapeHtml(image.image_id || "")}">
      <a class="structure-picture__frame" href="${url}" target="_blank" rel="noopener" title="Ouvrir l'image en grand">
        <span class="annot-frame"><img src="${url}" alt="${escapeHtml(alt)}" loading="lazy" draggable="false"${ImageAnnotations.attr(image.annotations)}></span>
      </a>
      <figcaption class="structure-picture__caption">${index != null ? `<span class="structure-picture__num">${index}</span>` : ""}<span class="structure-picture__kind">${escapeHtml(kind)}</span>${image.caption ? `<span>${escapeHtml(image.caption)}</span>` : ""}</figcaption>
      <div class="structure-picture__annotations"></div>
    </figure>`;
}

// La planche : toutes les images (numérotées dès qu'il y en a plusieurs) ; `compact` - un aperçu
// (graphe, atlas) : la première seulement, avec « +N » s'il y en a d'autres. `zoomable` : l'aperçu
// porte la loupe de structure-zoom.js - la page l'ouvre en grand au clic (structureImageZoomItems),
// le lien reste pour Ctrl+clic.
function structureBoardHtml(images, { compact = false, zoomable = false } = {}) {
  if (!images || !images.length) return "";
  if (compact) {
    const first = images[0];
    const url = first.url;
    const kind = STRUCTURE_IMAGE_KIND_LABELS[first.kind] || "Image";
    const more = images.length - 1;
    return `
      <a class="structure-thumb${zoomable ? " structure-zoomable" : ""}" href="${url}" target="_blank" rel="noopener" title="${zoomable ? "Agrandir et zoomer" : "Ouvrir l'image en grand"}">
        <span class="annot-frame"><img src="${url}" alt="${escapeHtml(first.caption ? `${kind} : ${first.caption}` : `${kind} de la structure`)}" loading="lazy"${ImageAnnotations.attr(first.annotations)}></span>
        ${more ? `<span class="structure-thumb__more">+${more} image${more > 1 ? "s" : ""}</span>` : ""}${zoomable ? STRUCTURE_ZOOM_BADGE : ""}
      </a>`;
  }
  const numbered = images.length > 1;
  return `<div class="structure-board" data-count="${Math.min(images.length, 3)}">${images
    .map((image, i) => structurePictureHtml(image, { index: numbered ? i + 1 : null }))
    .join("")}</div>`;
}

// Les images d'une structure pour la boîte agrandie (structure-zoom.js::openStructureZoom), dans
// l'ordre où les lire, annotations comprises : chacune avec son type et sa légende.
function structureImageZoomItems(images) {
  return (images || []).map((image) => {
    const kind = STRUCTURE_IMAGE_KIND_LABELS[image.kind] || "Image";
    const alt = image.caption ? `${kind} : ${image.caption}` : `${kind} de la structure`;
    return {
      html: `<span class="annot-frame"><img src="${escapeHtml(image.url)}" alt="${escapeHtml(alt)}" draggable="false"${ImageAnnotations.attr(image.annotations)}></span>`,
      caption: image.caption ? `${kind} · ${image.caption}` : kind,
    };
  });
}

// Un clic sur un aperçu `zoomable` : ses images en grand ; Ctrl/Maj+clic garde le lien (un nouvel
// onglet). Vrai quand le clic est pris.
function enlargeStructureImages(event, title, images) {
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.button !== 0 || !(images || []).length) return false;
  event.preventDefault();
  openStructureZoom({ title, items: structureImageZoomItems(images) });
  return true;
}
