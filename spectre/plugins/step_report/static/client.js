/* Client de l'API du plugin step_report : les commentaires des étapes d'un µprojet. */

const stepReportApi = {
  // stepIds : les ids d'étape à lire (au plus 500) -> {comments: {step_id: {step_id, text, updated_at, updated_by}}}
  // - une étape sans commentaire est absente
  list(slug, stepIds) {
    return api.get(api.withQuery(`/api/microprojects/${encodeURIComponent(slug)}/step-comments`, { step_id: stepIds }));
  },
  // écrit le commentaire d'une étape (texte vide : il est retiré) -> {step_id, text, ...}
  // keepalive : l'écriture part même si la page se ferme (le dernier texte tapé avant de quitter)
  put(slug, stepId, text, { keepalive = false } = {}) {
    return api.put(`/api/microprojects/${encodeURIComponent(slug)}/step-comments/${encodeURIComponent(stepId)}`, { text }, { keepalive });
  },
};
