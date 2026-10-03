/* Client de l'API du plugin accounts : comptes, sessions, profil, mot de passe. Une fonction par
   appel réseau ; chacune renvoie la promesse de api.js (kernel/static/api.js). */

const accountsApi = {
  register(body, options) {
    return api.post("/api/auth/register", body, options);
  },
  login(body, options) {
    return api.post("/api/auth/login", body, options);
  },
  logout(options) {
    return api.post("/api/auth/logout", {}, options);
  },
  me(options) {
    return api.get("/api/auth/me", options);
  },
  updateProfile(body, options) {
    return api.put("/api/auth/me", body, options);
  },
  changePassword(body, options) {
    return api.post("/api/auth/mot-de-passe", body, options);
  },
  forgotPassword(body, options) {
    return api.post("/api/auth/mot-de-passe-oublie", body, options);
  },
  resetPassword(body, options) {
    return api.post("/api/auth/reinitialiser", body, options);
  },
};
