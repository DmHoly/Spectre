/* Client de l'API du plugin structures : matériaux, recettes, simulation d'une structure et aperçu
   des variantes d'une campagne. */

const structuresApi = {
  materials(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/materials`);
  },
  recipes(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/recettes`);
  },
  simulate(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/structures/simulate`, body);
  },
  previewCampaign(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/structures/variantes`, body);
  },
};
