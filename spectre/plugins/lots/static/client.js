/* Client de l'API du plugin lots : lots de fabrication, leurs wafers et leurs thématiques visées.
   `lotId` : l'id d'un lot (son code se cherche avec list({code})). */

const lotsApi = {
  // filters : {status: "planned,wip,hold", q, wafer: [clés de wafer], code, view: "summary"}
  list(filters) {
    // l'API lit `wafer` en une liste séparée par des virgules : répété (?wafer=a&wafer=b), seul le dernier compterait
    const { wafer, ...rest } = filters || {};
    return api.get(api.withQuery("/api/lots", { ...rest, wafer: Array.isArray(wafer) ? wafer.join(",") : wafer }));
  },
  // les priorités proposées à la saisie (P10, P20...)
  priorities() {
    return api.get("/api/lot-priorities");
  },
  create(body) {
    return api.post("/api/lots", body);
  },
  get(lotId) {
    return api.get(`/api/lots/${encodeURIComponent(lotId)}`);
  },
  // ifMatch : la version affichée (updated_at du lot)
  update(lotId, body, ifMatch) {
    return api.patch(`/api/lots/${encodeURIComponent(lotId)}`, body, { ifMatch });
  },
  remove(lotId) {
    return api.del(`/api/lots/${encodeURIComponent(lotId)}`);
  },
  addWafers(lotId, body) {
    return api.post(`/api/lots/${encodeURIComponent(lotId)}/wafers`, body);
  },
  removeWafer(lotId, waferKey) {
    return api.del(`/api/lots/${encodeURIComponent(lotId)}/wafers/${encodeURIComponent(waferKey)}`);
  },
  setThematics(lotId, body) {
    return api.put(`/api/lots/${encodeURIComponent(lotId)}/thematics`, body);
  },
};
