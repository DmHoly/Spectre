/* Client de l'API du plugin microprojects : µprojets, recherche, membres et invitations. */

const microprojectsApi = {
  list() {
    return api.get("/api/microprojets");
  },
  listAll() {
    return api.get("/api/microprojets/tous");
  },
  create(body) {
    return api.post("/api/microprojets", body);
  },
  get(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}`);
  },
  // renommer, ou déplacer dans un autre projet / une autre thématique : {name, description, area, thematic}
  update(microprojectSlug, body) {
    return api.patch(`/api/microprojects/${encodeURIComponent(microprojectSlug)}`, body);
  },
  remove(microprojectSlug, confirmName) {
    return api.del(api.withQuery(`/api/microprojets/${encodeURIComponent(microprojectSlug)}`, { confirm_name: confirmName }));
  },
  members(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/members`);
  },
  addMember(microprojectSlug, body) {
    return api.post(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/members`, body);
  },
  removeMember(microprojectSlug, userId) {
    return api.del(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/members/${encodeURIComponent(userId)}`);
  },
  invitations(microprojectSlug) {
    return api.get(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/invitations`);
  },
  cancelInvitation(microprojectSlug, token) {
    return api.del(`/api/microprojets/${encodeURIComponent(microprojectSlug)}/invitations/${encodeURIComponent(token)}`);
  },
  // l'invitation derrière le lien reçu par e-mail (page d'inscription, sans session)
  invitation(token, options) {
    return api.get(`/api/invitations/${encodeURIComponent(token)}`, options);
  },
  // rejoindre le µprojet avec le compte connecté (même adresse que l'invitation)
  acceptInvitation(token, options) {
    return api.post(`/api/invitations/${encodeURIComponent(token)}/acceptance`, {}, options);
  },
};
