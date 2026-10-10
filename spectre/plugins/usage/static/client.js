/* Client de l'API du plugin usage : le rapport d'utilisation d'une période, réservé aux
   administrateurs (403 sinon). */

const usageApi = {
  // params : {start, end (AAAA-MM-JJ, inclus), granularity (day, week, month), team (slug),
  //   user_id, plugin, include_admins} ->
  // {period, tracking_since, catalog, totals, previous, series, plugin_series, plugins, heatmap, routes, users}
  report(params) {
    return api.get(api.withQuery("/api/usage", params));
  },
};
