/* Client de l'API du plugin attachments : téléversement des images d'un µprojet et URL de leurs
   octets (une <img src>, un lien « ouvrir en grand »). */

const attachmentsApi = {
  // une image collée dans une preuve
  uploadImage(microprojectSlug, formData) {
    return api.upload(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/images`, formData);
  },
  // une image d'une structure en images
  uploadStructureImage(microprojectSlug, formData) {
    return api.upload(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/structures/images`, formData);
  },
  contentUrl(microprojectSlug, attachmentId) {
    return `/api/microprojets/${encodeURIComponent(microprojectSlug)}/pieces-jointes/${encodeURIComponent(attachmentId)}`;
  },
};
