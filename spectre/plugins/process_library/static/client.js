/* Client de l'API du plugin process_library : structures enregistrées, présets d'étape et briques
   technologiques, en collections à plat. Chaque élément porte `id`, `name`, `scope` ("builtin",
   "shared" ou "microproject"), `microproject`, `created_by`, `updated_by` et `can_edit`.
   `filters` : `{microproject, scope}` - sans µprojet, la liste ne contient que les éléments intégrés
   et partagés. */

const processLibraryApi = {
  savedStructures(filters) {
    return api.get(api.withQuery("/api/saved-structures", filters));
  },
  savedStructure(structureId) {
    return api.get(`/api/saved-structures/${encodeURIComponent(structureId)}`);
  },
  createSavedStructure(body) {
    return api.post("/api/saved-structures", body);
  },
  updateSavedStructure(structureId, changes) {
    return api.patch(`/api/saved-structures/${encodeURIComponent(structureId)}`, changes);
  },
  deleteSavedStructure(structureId) {
    return api.del(`/api/saved-structures/${encodeURIComponent(structureId)}`);
  },
  stepPresets(filters) {
    return api.get(api.withQuery("/api/step-presets", filters));
  },
  stepPreset(presetId) {
    return api.get(`/api/step-presets/${encodeURIComponent(presetId)}`);
  },
  createStepPreset(body) {
    return api.post("/api/step-presets", body);
  },
  updateStepPreset(presetId, changes) {
    return api.patch(`/api/step-presets/${encodeURIComponent(presetId)}`, changes);
  },
  deleteStepPreset(presetId) {
    return api.del(`/api/step-presets/${encodeURIComponent(presetId)}`);
  },
  techBricks(filters) {
    return api.get(api.withQuery("/api/tech-bricks", filters));
  },
  techBrick(brickId) {
    return api.get(`/api/tech-bricks/${encodeURIComponent(brickId)}`);
  },
  createTechBrick(body) {
    return api.post("/api/tech-bricks", body);
  },
  updateTechBrick(brickId, changes) {
    return api.patch(`/api/tech-bricks/${encodeURIComponent(brickId)}`, changes);
  },
  deleteTechBrick(brickId) {
    return api.del(`/api/tech-bricks/${encodeURIComponent(brickId)}`);
  },
};
