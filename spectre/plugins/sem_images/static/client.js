/* Client de l'API du plugin sem_images : les images MEB du G4 d'une plaque, lues sur le partage par PRISM et
   rendues à la volée (rien n'est copié), et l'index des dossiers du partage. */

const semImagesApi = {
  // {lasermark, fdls, root, groups: [{folder, area, area_label, lot, fdl, process, step, count, rounds, first, last,
  // images: [{path, name, die, round, size, modified}]}], count, read_at, index} - fdl : FDL en plus de celles que
  // Spectre connaît à la plaque ; refresh : relit le partage
  list(lasermark, { fdl = [], refresh = false } = {}) {
    return api.get(api.withQuery(`/api/wafers/${encodeURIComponent(lasermark)}/sem-images`, { fdl, refresh: refresh ? "true" : "" }));
  },
  // l'adresse d'une image de la liste : variant "thumb" (JPEG 320 px) ou "view" (PNG entier), frame = détecteur
  fileUrl(lasermark, path, { variant = "thumb", frame = 0, fdl = [] } = {}) {
    return api.withQuery(`/api/wafers/${encodeURIComponent(lasermark)}/sem-images/file`, { path, variant, frame: frame || "", fdl });
  },
  // ce que le TIF dit de lui-même : {width, height, frames, fov_um, pixel_um, location_um, die_index, defect_id,
  // defect_class, kv, tilt, acquired, file, ...}
  meta(lasermark, path, { fdl = [] } = {}) {
    return api.get(api.withQuery(`/api/wafers/${encodeURIComponent(lasermark)}/sem-images/meta`, { path, fdl }));
  },
  // {exists, built_at, checked_at, folders, wafers, building, updating, error} - l'index se construit et se met à
  // jour de lui-même (POST /api/sem-images/index le force, sans bouton ici)
  index() {
    return api.get("/api/sem-images/index");
  },
};
