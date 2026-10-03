/* Client de l'API du plugin structures : matériaux, recettes, simulation d'une structure et aperçu
   des variantes d'une campagne (des calculs : rien n'est enregistré). */

const structuresApi = {
  listMaterials() {
    return api.get("/api/materials");
  },
  // {deposition: [...], etch: [...]}
  listRecipes() {
    return api.get("/api/recipes");
  },
  // body : {substrate, steps, declared_params}
  simulate(body) {
    return api.post("/api/simulations", body);
  },
  // body : {substrate, steps, declared_params, plan}
  previewCampaign(body) {
    return api.post("/api/campaign-previews", body);
  },
};
