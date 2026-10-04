/* Client de l'API du plugin teams : les équipes et leurs membres. Chaque équipe dit ce que
   l'appelant peut en faire : my_role (manager, member ou null), can_edit (renommer, supprimer :
   un admin) et can_manage (ses membres : un admin ou un de ses managers). */

const teamsApi = {
  list() {
    return api.get("/api/teams");
  },
  // {name} (admin)
  create(body) {
    return api.post("/api/teams", body);
  },
  get(teamSlug) {
    return api.get(`/api/teams/${encodeURIComponent(teamSlug)}`);
  },
  // {name} (admin)
  update(teamSlug, body) {
    return api.patch(`/api/teams/${encodeURIComponent(teamSlug)}`, body);
  },
  remove(teamSlug) {
    return api.del(`/api/teams/${encodeURIComponent(teamSlug)}`);
  },
  // [{id, name, email, role}], les managers d'abord
  members(teamSlug) {
    return api.get(`/api/teams/${encodeURIComponent(teamSlug)}/members`);
  },
  // {email, role} : un compte existant (404 « no_account » sinon)
  addMember(teamSlug, body) {
    return api.post(`/api/teams/${encodeURIComponent(teamSlug)}/members`, body);
  },
  // {role} : 409 « last_manager » si l'équipe resterait sans manager
  updateMember(teamSlug, userId, body) {
    return api.patch(`/api/teams/${encodeURIComponent(teamSlug)}/members/${encodeURIComponent(userId)}`, body);
  },
  removeMember(teamSlug, userId) {
    return api.del(`/api/teams/${encodeURIComponent(teamSlug)}/members/${encodeURIComponent(userId)}`);
  },
};
