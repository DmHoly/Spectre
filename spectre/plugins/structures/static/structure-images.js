/* Affichage d'une structure en images (planche, aperçu) ; l'URL d'une image passe par
   attachmentsApi (attachments/static/client.js). */

/* Structure en images (spectre.core.structures.StructureImage) : un schéma collé depuis PowerPoint,
   des coupes TEM... à la place d'une structure dessinée - une ou plusieurs images, dans l'ordre où
   les lire. Affichées ainsi sur la fiche (la planche entière), le graphe d'un µprojet, l'atlas et
   la galerie de données (la première, avec le nombre d'images). L'éditeur pour les coller, les
   ordonner ou les remplacer est dans image-drop.js. */
const STRUCTURE_IMAGE_KIND_LABELS = { schema: "Schéma", coupe: "Coupe TEM / MEB", autre: "Image" };

function structureImageUrl(slug, imageId) {
  return attachmentsApi.contentUrl(slug, imageId);
}

function structurePictureHtml(slug, image, { index = null } = {}) {
  const url = structureImageUrl(slug, image.image_id);
  const kind = STRUCTURE_IMAGE_KIND_LABELS[image.kind] || "Image";
  const alt = image.caption ? `${kind} : ${image.caption}` : `${kind} de la structure`;
  return `
    <figure class="structure-picture">
      <a class="structure-picture__frame" href="${url}" target="_blank" rel="noopener" title="Ouvrir l'image en grand">
        <img src="${url}" alt="${escapeHtml(alt)}" loading="lazy">
      </a>
      <figcaption class="structure-picture__caption">${index != null ? `<span class="structure-picture__num">${index}</span>` : ""}<span class="structure-picture__kind">${escapeHtml(kind)}</span>${image.caption ? `<span>${escapeHtml(image.caption)}</span>` : ""}</figcaption>
    </figure>`;
}

// La planche : toutes les images (numérotées dès qu'il y en a plusieurs) ; `compact` - un aperçu
// (graphe, atlas, galerie) : la première seulement, avec « +N » s'il y en a d'autres.
function structureBoardHtml(slug, images, { compact = false } = {}) {
  if (!images || !images.length) return "";
  if (compact) {
    const first = images[0];
    const url = structureImageUrl(slug, first.image_id);
    const kind = STRUCTURE_IMAGE_KIND_LABELS[first.kind] || "Image";
    const more = images.length - 1;
    return `
      <a class="structure-thumb" href="${url}" target="_blank" rel="noopener" title="Ouvrir l'image en grand">
        <img src="${url}" alt="${escapeHtml(first.caption ? `${kind} : ${first.caption}` : `${kind} de la structure`)}" loading="lazy">
        ${more ? `<span class="structure-thumb__more">+${more} image${more > 1 ? "s" : ""}</span>` : ""}
      </a>`;
  }
  const numbered = images.length > 1;
  return `<div class="structure-board" data-count="${Math.min(images.length, 3)}">${images
    .map((image, i) => structurePictureHtml(slug, image, { index: numbered ? i + 1 : null }))
    .join("")}</div>`;
}
