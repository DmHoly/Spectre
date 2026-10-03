/* Client de l'API du plugin process_library : présets d'étape, structures enregistrées et briques
   technologiques d'un µprojet. `shared` (booléen) : l'élément de la bibliothèque partagée plutôt
   que celui du µprojet. */

const processLibraryApi = {
  stepPresets(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/presets-etapes`);
  },
  createStepPreset(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/presets-etapes`, body);
  },
  updateStepPreset(microprojectSlug, name, shared, body) {
    return api.put(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/presets-etapes/${encodeURIComponent(name)}?partagee=${Boolean(shared)}`, body);
  },
  removeStepPreset(microprojectSlug, name, shared) {
    return api.del(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/presets-etapes/${encodeURIComponent(name)}?partagee=${Boolean(shared)}`);
  },
  savedStructures(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/structures-sauvegardees`);
  },
  createSavedStructure(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/structures-sauvegardees`, body);
  },
  updateSavedStructure(microprojectSlug, name, shared, body) {
    return api.put(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/structures-sauvegardees/${encodeURIComponent(name)}?partagee=${Boolean(shared)}`,
      body
    );
  },
  techBricks(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/briques-technologiques`);
  },
  createTechBrick(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/briques-technologiques`, body);
  },
  updateTechBrick(microprojectSlug, name, shared, body) {
    return api.put(
      `/api/microprojets/${encodeURIComponent(microprojectSlug)}/briques-technologiques/${encodeURIComponent(name)}?partagee=${Boolean(shared)}`,
      body
    );
  },
  removeTechBrick(microprojectSlug, name, shared) {
    return api.del(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/briques-technologiques/${encodeURIComponent(name)}?partagee=${Boolean(shared)}`);
  },
};
