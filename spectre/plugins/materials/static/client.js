/* Client de l'API du plugin materials : la bibliothèque de matériaux de l'instance, en un document. */

const materialsApi = {
  // -> {revision, can_edit, exists, problem, categories: [{value, label}],
  //   materials: [{name, category, color, density_g_cm3, refractive_index, notes}],
  //   gradients: {InGaN|AlGaN: {stops: [{x, color}], generic_x}}, defaults (les dégradés livrés),
  //   available (les matériaux de StructureForge pas encore dans la liste)}
  library() {
    return api.get("/api/material-library");
  },
  // document : {revision (celle lue), materials, gradients} - administrateur ; 409 si le fichier a
  // changé depuis la lecture. Renvoie le document relu.
  saveLibrary(document) {
    return api.put("/api/material-library", document);
  },
};
