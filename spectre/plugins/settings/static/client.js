/* Client de l'API du plugin settings : les paramètres de l'application, réservés aux
   administrateurs (403 sinon). Chaque plugin dit ce qu'il est (title, description, icon), s'il est
   du noyau (required), son choix enregistré (enabled) et ce qui en découle (active, blocked_by :
   les plugins éteints qui l'éteignent ; dependents : ce que le désactiver éteindrait). */

const settingsApi = {
  // [{name, title, description, icon, required, available, enabled, active, blocked_by,
  //   depends_on, dependents, updated_at, updated_by}], dans l'ordre des dépendances
  plugins() {
    return api.get("/api/plugins");
  },
  // {enabled} : à chaud, sans redémarrage ; 409 « plugin_required » pour un plugin du noyau
  updatePlugin(pluginName, body) {
    return api.patch(`/api/plugins/${encodeURIComponent(pluginName)}`, body);
  },
};
