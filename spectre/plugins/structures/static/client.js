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
  // body : {substrate, steps, declared_params} ; chaque étape peut porter son id - la réponse
  // ({frames, material_colors, step_ids}) donne celui de chaque étape (un neuf pour une nouvelle)
  simulate(body) {
    return api.post("/api/simulations", body);
  },
  // body : {substrate, steps, declared_params, plan} ; un facteur du plan désigne son étape par
  // step_id (l'id de l'étape, "substrate" pour le substrat)
  previewCampaign(body) {
    return api.post("/api/campaign-previews", body);
  },
};
