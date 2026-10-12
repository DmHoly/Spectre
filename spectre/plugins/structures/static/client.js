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
  // ({frames, material_colors, step_ids}) donne celui de chaque étape (un neuf pour une nouvelle) ;
  // run : l'identifiant de cette simulation (8 à 64 caractères, lettres, chiffres, - et _), pour
  // en suivre l'avancement pendant qu'elle tourne (plugin simulation_progress)
  simulate(body, run) {
    return api.post(api.withQuery("/api/simulations", { run }), body);
  },
  // body : {substrate, steps, declared_params, plan} ; un facteur du plan désigne son étape par
  // step_id (l'id de l'étape, "substrate" pour le substrat)
  previewCampaign(body) {
    return api.post("/api/campaign-previews", body);
  },
  // combiner au marché : {sources: [procédé, ...] (la principale d'abord), choices: [index de source
  // | null, ...] | null} -> {rows: [{key, name, present, same_as, chosen, in_main}], process, warnings}
  compose(body) {
    return api.post("/api/compositions", body);
  },
};
