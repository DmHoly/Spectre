/* Client de l'API du plugin attachments : téléversement des fichiers d'un µprojet et URL de leurs
   octets (une <img src>, un lien « ouvrir en grand »). */

const attachmentsApi = {
  // `formData` : file, et purpose ("structure" : une image de structure ; "evidence" : une image de
  // preuve) - renvoie {id, url, filename, content_type, size, purpose, uploaded_by, uploaded_at}
  upload(microprojectSlug, formData) {
    return api.upload(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/attachments`, formData);
  },
  // transitoire : les images d'une structure et d'une preuve arrivent encore sans leur `url`
  contentUrl(microprojectSlug, attachmentId) {
    return `/api/microprojects/${encodeURIComponent(microprojectSlug)}/attachments/${encodeURIComponent(attachmentId)}/content`;
  },
};
