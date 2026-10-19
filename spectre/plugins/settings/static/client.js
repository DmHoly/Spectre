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

  // -- utilisateurs (plugin accounts) --
  // [{id, email, name, is_admin, must_change_password}]
  users() {
    return api.get("/api/users");
  },
  // {user, temporary_password} : le mot de passe provisoire n'est montré qu'une fois ; le compte est
  // déconnecté partout et devra en choisir un nouveau à sa prochaine connexion
  resetUserPassword(userId) {
    return api.post(`/api/users/${encodeURIComponent(userId)}/password-resets`);
  },

  // -- base de données (kernel/database.py) --
  // {data_dir, database_bytes, files, files_bytes} : ce que la sauvegarde emportera
  databaseSummary() {
    return api.get("/api/database");
  },
  // le ZIP de tout le dossier de données (Blob)
  databaseBackup() {
    return api.get("/api/database/backup", { as: "blob" });
  },
  // [{name, rows, columns, editable}]
  tables() {
    return api.get("/api/database/tables");
  },
  // params : {q, sort, desc, offset, limit} -> {table, columns, editable, items: [{rowid, values}], total}
  rows(tableName, params) {
    return api.get(api.withQuery(`/api/database/tables/${encodeURIComponent(tableName)}/rows`, params));
  },
  // {values: {colonne: valeur}} -> la ligne écrite ; 409 « integrity_error » si la base refuse
  updateRow(tableName, rowId, body) {
    return api.patch(`/api/database/tables/${encodeURIComponent(tableName)}/rows/${encodeURIComponent(rowId)}`, body);
  },
  // les clés étrangères suivent le schéma (cascade), ou 409 « integrity_error »
  deleteRow(tableName, rowId) {
    return api.del(`/api/database/tables/${encodeURIComponent(tableName)}/rows/${encodeURIComponent(rowId)}`);
  },
};
