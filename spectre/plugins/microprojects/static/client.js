/* Client de l'API du plugin microprojects : µprojets, membres et invitations. Les compteurs
   d'expériences d'une liste de µprojets viennent d'experimentsApi.stats. */

const microprojectsApi = {
  // les miens ; {scope: "all"} (admin) ; {area, thematic} ; {q, limit} ou {code} : toute la société, champs réduits
  list(params) {
    return api.get(api.withQuery("/api/microprojects", params));
  },
  // {name, description, area, thematic}
  create(body) {
    return api.post("/api/microprojects", body);
  },
  get(microprojectSlug) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}`);
  },
  // renommer, ou déplacer dans un autre projet / une autre thématique : {name, description, area, thematic}
  update(microprojectSlug, body) {
    return api.patch(`/api/microprojects/${encodeURIComponent(microprojectSlug)}`, body);
  },
  remove(microprojectSlug, confirmName) {
    return api.del(api.withQuery(`/api/microprojects/${encodeURIComponent(microprojectSlug)}`, { confirm_name: confirmName }));
  },
  members(microprojectSlug) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/members`);
  },
  // {email, role} : un compte existant (404 « no_account » sinon : l'inviter)
  addMember(microprojectSlug, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/members`, body);
  },
  // {role}
  updateMember(microprojectSlug, userId, body) {
    return api.patch(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/members/${encodeURIComponent(userId)}`, body);
  },
  removeMember(microprojectSlug, userId) {
    return api.del(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/members/${encodeURIComponent(userId)}`);
  },
  invitations(microprojectSlug) {
    return api.get(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/invitations`);
  },
  // {email, role} : un e-mail part avec le lien d'inscription
  invite(microprojectSlug, body) {
    return api.post(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/invitations`, body);
  },
  cancelInvitation(microprojectSlug, invitationId) {
    return api.del(`/api/microprojects/${encodeURIComponent(microprojectSlug)}/invitations/${encodeURIComponent(invitationId)}`);
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
