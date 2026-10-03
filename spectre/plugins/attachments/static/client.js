/* Client de l'API du plugin attachments : téléversement des fichiers d'un µprojet. L'URL de leurs
   octets arrive toujours avec eux (`url`) : le front ne la construit pas. */

const attachmentsApi = {
  // `formData` : file, et purpose ("structure" : une image de structure ; "evidence" : une image de
  // preuve) - renvoie {id, url, filename, content_type, size, purpose, uploaded_by, uploaded_at}
  upload(microprojectSlug, formData) {
    return api.upload(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/attachments`, formData);
  },
};
