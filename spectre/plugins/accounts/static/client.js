/* Client de l'API du plugin accounts : comptes, sessions, profil, mot de passe. Une fonction par
   appel réseau ; chacune renvoie la promesse de api.js (kernel/static/api.js). */

const accountsApi = {
  // crée le compte et ouvre sa session
  register(body, options) {
    return api.post("/api/users", body, options);
  },
  login(body, options) {
    return api.post("/api/sessions", body, options);
  },
  logout(options) {
    return api.del("/api/sessions/current", options);
  },
  me(options) {
    return api.get("/api/users/me", options);
  },
  updateMe(body, options) {
    return api.patch("/api/users/me", body, options);
  },
  // ferme toutes les sessions du compte, celle-ci comprise
  changePassword(body, options) {
    return api.put("/api/users/me/password", body, options);
  },
  requestPasswordReset(body, options) {
    return api.post("/api/password-resets", body, options);
  },
  completePasswordReset(body, options) {
    return api.post("/api/password-resets/completions", body, options);
  },
};
