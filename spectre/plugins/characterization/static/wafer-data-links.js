/* Menu « Données en base » des plaques d'une page, via characterizationApi
   (characterization/static/client.js). */

/* « Données en base » : les types de données implémentés qui prennent des lasermarks (page Data),
   ouverts sur les plaques données - un clic, et la requête part avec ces wafers (data-types.js,
   ?wafers=). Rien n'est affiché s'il n'y a aucun type de ce genre (ou aucun lasermark). Utilisé par
   la fiche d'expérience et la page d'une plaque. */
let byWaferDataTypesPromise = null;
function byWaferDataTypes() {
  if (!byWaferDataTypesPromise) {
    byWaferDataTypesPromise = characterizationApi.list({ status: "implemented", by_wafer: true }).catch(() => []);
  }
  return byWaferDataTypesPromise;
}

async function renderWaferDbLinks(hosts, lasermarkList) {
  const lasermarks = [...new Set((lasermarkList || []).filter(Boolean))];
  const dataTypes = lasermarks.length ? await byWaferDataTypes() : [];
  if (!dataTypes.length) {
    hosts.forEach((h) => (h.innerHTML = ""));
    return;
  }
  const wafers = encodeURIComponent(lasermarks.join(","));
  const items = dataTypes
    .map((t) => `<li><a href="/donnees/${encodeURIComponent(t.key)}?wafers=${wafers}" target="_blank" rel="noopener">${escapeHtml(t.title)}<span>${escapeHtml(t.category || "")}</span></a></li>`)
    .join("");
  const icon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>`;
  hosts.forEach((host) => {
    host.innerHTML = `
      <details class="db-menu">
        <summary class="btn btn-line db-menu__btn" title="Les données de ${lasermarks.length > 1 ? "ces plaques" : "cette plaque"} en base (PRISM)">${icon}Données en base</summary>
        <div class="db-menu__pop">
          <div class="db-menu__title">Ouvrir dans Data, pour ${escapeHtml(lasermarks.length > 3 ? `${lasermarks.length} plaques` : lasermarks.join(", "))}</div>
          <ul>${items}</ul>
        </div>
      </details>`;
  });
}

document.addEventListener("click", (event) => {
  document.querySelectorAll(".db-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute("open");
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll(".db-menu[open]").forEach((menu) => {
    menu.removeAttribute("open");
    menu.querySelector("summary").focus();
  });
});
