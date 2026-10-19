/* Client de l'API du plugin lumiere : les modèles de rapport, les rapports générés (demande, état, fichier). */

const lumiereApi = {
  // {templates: [{key, name, description, context, slides}], contexts: {wafer: "une plaque"}}
  templates(context = null) {
    return api.get(api.withQuery("/api/lumiere/templates", { context }));
  },
  // {template, context: {kind, key}} -> 202 : le rapport {id, title, status: "queued", ...} ; la génération part en fond
  request(template, context) {
    return api.post("/api/lumiere/reports", { template, context });
  },
  // vos rapports (tous pour un administrateur), les plus récents d'abord, filtrés par contexte
  list({ kind = null, key = null } = {}) {
    return api.get(api.withQuery("/api/lumiere/reports", { context_kind: kind, context_key: key }));
  },
  // {id, title, status: queued|running|done|error, message, bytes, file_url, created_at, finished_at, ...}
  get(id) {
    return api.get(`/api/lumiere/reports/${encodeURIComponent(id)}`);
  },
  fileUrl(id) {
    return `/api/lumiere/reports/${encodeURIComponent(id)}/file`;
  },
  remove(id) {
    return api.del(`/api/lumiere/reports/${encodeURIComponent(id)}`);
  },
  // {reports, bytes, running} - administrateurs
  storage() {
    return api.get("/api/lumiere/storage");
  },
};
