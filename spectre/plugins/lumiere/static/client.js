/* Client de l'API du plugin lumiere : les modèles de rapport (lecture, création, modification), le catalogue des
   blocs, l'aperçu d'une slide, les rapports générés (demande, état, fichier). */

const lumiereApi = {
  // {templates: [{key, name, description, context, slides, outline, builtin, owner_id, owner_name, updated_at}], contexts}
  templates(context = null) {
    return api.get(api.withQuery("/api/lumiere/templates", { context }));
  },
  template(key) {
    return api.get(`/api/lumiere/templates/${encodeURIComponent(key)}`);
  },
  // {name, description?, context?, slides?, copy_of?} -> 201 le modèle
  createTemplate(body) {
    return api.post("/api/lumiere/templates", body);
  },
  // {name?, description?, slides?} -> le modèle (son auteur ou un administrateur ; pas un modèle livré)
  updateTemplate(key, body) {
    return api.put(`/api/lumiere/templates/${encodeURIComponent(key)}`, body);
  },
  removeTemplate(key) {
    return api.del(`/api/lumiere/templates/${encodeURIComponent(key)}`);
  },
  // {blocks: [{key, label, description, group, needs, options: [{key, label, kind, default, help, choices, min, max}]}], slide_kinds, max_grid}
  blocks(context = "wafer") {
    return api.get(api.withQuery("/api/lumiere/blocks", { context }));
  },
  // l'aperçu d'une slide d'un modèle en cours d'édition, rendu sur une plaque : {html}
  preview(context, slides, index, key) {
    return api.post("/api/lumiere/preview", { context, slides, index, key });
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
