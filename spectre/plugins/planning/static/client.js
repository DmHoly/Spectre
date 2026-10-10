/* Client de l'API du plugin planning : le planning d'une équipe (lecture seule). Les lots prévus se
   créent et se remplissent par lotsApi (statut « planned »). */

const planningApi = {
  // sans teamSlug : la première équipe que l'on manage ({team: null} si aucune)
  // -> {teams, team, today, areas, groups: [{area, thematic, microprojects: [{slug, code, name, url,
  //    studies: [{id, version_id, title, status, decision, started_at, ended_at, url, wafers}], plans}]}], lots}
  board(teamSlug) {
    return api.get(teamSlug ? `/api/team-plannings/${encodeURIComponent(teamSlug)}` : "/api/team-plannings");
  },
};
