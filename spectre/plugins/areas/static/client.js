/* Client de l'API du plugin areas : projets corporate, leurs thématiques et leurs objectifs. */

const areasApi = {
  // tous les projets ; {team} : ceux où une équipe travaille. Chacun porte teams (les badges des équipes
  // du projet), attachable_teams (celles que l'appelant peut y rattacher), manageable_teams (celles
  // pour lesquelles il crée une thématique), placement_teams (celles dont un µprojet qu'il y crée peut
  // être), can_manage, can_delete et can_place_microproject (y créer ou y déplacer un µprojet)
  list(params) {
    return api.get(api.withQuery("/api/areas", params));
  },
  // {name, description, strategy, code_prefix, team} : team (l'équipe qui y travaille d'abord) obligatoire pour un manager (l'une des siennes)
  create(body) {
    return api.post("/api/areas", body);
  },
  get(areaSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}`);
  },
  // {name, description, strategy, objectives_period, code_prefix}
  update(areaSlug, body) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}`, body);
  },
  // l'équipe travaille dans le projet : un admin, ou le manager de cette équipe. Renvoie le projet
  attachTeam(areaSlug, teamSlug) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/teams`, { team: teamSlug });
  },
  // 409 « team_has_content » tant que l'équipe y possède des thématiques ou des µprojets. Renvoie le projet
  detachTeam(areaSlug, teamSlug) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}/teams/${encodeURIComponent(teamSlug)}`);
  },
  remove(areaSlug) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}`);
  },
  // les thématiques que l'appelant voit, à plat ({id, slug, name, area, team}) ; celles d'un seul projet avec areaSlug
  listThematics(areaSlug) {
    return api.get(api.withQuery("/api/thematics", { area: areaSlug }));
  },
  // {name, description, team} : team (slug) seulement quand plusieurs conviennent (422 « team_required »)
  createThematic(areaSlug, body) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/thematics`, body);
  },
  // team, invited_teams (lues seulement), invitable_teams, can_manage, can_place_microproject ; 404 si l'appelant ne la voit pas
  getThematic(areaSlug, thematicSlug) {
    return api.get(`/api/areas/${encodeURIComponent(areaSlug)}/thematics/${encodeURIComponent(thematicSlug)}`);
  },
  updateThematic(areaSlug, thematicSlug, body) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}/thematics/${encodeURIComponent(thematicSlug)}`, body);
  },
  removeThematic(areaSlug, thematicSlug) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}/thematics/${encodeURIComponent(thematicSlug)}`);
  },
  // l'équipe invitée lit la thématique et ses µprojets (409 « owner_team » pour l'équipe qui la possède). Renvoie la thématique
  inviteTeam(areaSlug, thematicSlug, teamSlug) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/thematics/${encodeURIComponent(thematicSlug)}/teams`, { team: teamSlug });
  },
  uninviteTeam(areaSlug, thematicSlug, teamSlug) {
    return api.del(
      `/api/areas/${encodeURIComponent(areaSlug)}/thematics/${encodeURIComponent(thematicSlug)}/teams/${encodeURIComponent(teamSlug)}`
    );
  },
  createObjective(areaSlug, body) {
    return api.post(`/api/areas/${encodeURIComponent(areaSlug)}/objectives`, body);
  },
  updateObjective(areaSlug, objectiveId, body) {
    return api.patch(`/api/areas/${encodeURIComponent(areaSlug)}/objectives/${encodeURIComponent(objectiveId)}`, body);
  },
  removeObjective(areaSlug, objectiveId) {
    return api.del(`/api/areas/${encodeURIComponent(areaSlug)}/objectives/${encodeURIComponent(objectiveId)}`);
  },
};
