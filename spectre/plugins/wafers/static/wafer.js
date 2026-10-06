/* Page d'une plaque (wafer.html, /plaques/<lasermark>) : où elle est, ses FDL, ses données en base,
   et son parcours - chaque étude qui la suit (la plus récente d'abord), avec son µprojet, son
   statut, la variante qu'elle porte dans une campagne, l'emplacement et les FDL notés dans cette
   étude. On y arrive depuis la recherche de la topbar ou un lasermark cliqué sur une fiche. */

const { lasermark } = routeParams("/plaques/{lasermark}");

function showError(err) {
  const box = document.getElementById("error");
  box.textContent = err.message || String(err);
  box.style.display = "block";
}

// Une étude d'un µprojet dont on n'est pas membre : son µprojet, son statut et sa date, sans titre
// ni lien (le serveur ne les donne pas).
function trailItemHtml(o) {
  const exp = o.experiment;
  const mp = exp.microproject;
  const title = exp.member
    ? `<a class="plate-trail__title" href="/microprojets/${encodeURIComponent(mp.slug)}/experiences/${encodeURIComponent(exp.id)}">${escapeHtml(exp.title)}</a>`
    : `<span class="plate-trail__title help">Étude d'un µprojet dont vous n'êtes pas membre</span>`;
  return `
    <li class="plate-trail__item">
      <span class="plate-trail__dot" aria-hidden="true"></span>
      <div class="card plate-trail__card">
        <div class="plate-trail__head">
          ${statusBadgeHtml(exp.status)}
          <a class="fiche-code" href="/microprojets/${encodeURIComponent(mp.slug)}" title="µprojet ${escapeHtml(mp.name)}">${escapeHtml(mp.code || mp.name)}</a>
          <span class="plate-trail__date">mise à jour le ${formatDate(exp.updated_at)}</span>
        </div>
        ${title}
        <div class="plate-trail__meta">
          <span>${escapeHtml(mp.name)}</span>
          ${o.variant ? `<span>Variante&nbsp;: <strong class="mono">${escapeHtml(o.variant)}</strong></span>` : ""}
          ${o.location ? `<span>Emplacement&nbsp;: <strong>${escapeHtml(o.location)}</strong></span>` : ""}
        </div>
        ${o.fdl && o.fdl.length ? `<div class="plate-trail__fdl">${fdlChipsHtml(o.fdl)}</div>` : ""}
      </div>
    </li>`;
}

async function init() {
  document.getElementById("plate-crumb").textContent = lasermark;
  document.getElementById("crumb").textContent = `/ Plaques / ${lasermark}`;
  document.title = `${lasermark} — Spectre`;
  try {
    const lotsOn = pluginEnabled("lots");
    const [plate, lots] = await Promise.all([
      wafersApi.get(lasermark),
      lotsOn ? lotsApi.list({ wafer: lasermark, view: "summary" }) : [],
    ]);
    const n = plate.occurrences.length;
    document.getElementById("plate-lasermark").textContent = plate.lasermark;
    document.getElementById("plate-summary").textContent = n
      ? `Suivie dans ${n} étude${n > 1 ? "s" : ""}${plate.microprojects.length > 1 ? `, sur ${plate.microprojects.length} µprojets` : ""}.`
      : "Aucune étude ne suit cette plaque.";
    document.getElementById("plate-location").textContent = plate.last_location || "—";
    document.getElementById("plate-fdl").innerHTML = plate.fdl.length ? fdlChipsHtml(plate.fdl, { label: false }) : "—";
    document.getElementById("plate-microprojects").innerHTML = plate.microprojects.length
      ? plate.microprojects
          .map((m) => `<a class="fiche-code" href="/microprojets/${encodeURIComponent(m.slug)}" title="${escapeHtml(m.name)}">${escapeHtml(m.code || m.name)}</a>`)
          .join(" ")
      : "—";
    // le(s) lot(s) de fabrication qui la contiennent (suivi de lots, /lots)
    document.getElementById("plate-lots").innerHTML = !lotsOn
      ? `<span class="help" style="margin:0;">Suivi des lots désactivé</span>`
      : lots.length
      ? lots.map((l) => `<a class="fiche-code" href="/lots/${encodeURIComponent(l.code)}" title="${escapeHtml(l.title || "Lot")}">${escapeHtml(l.code)}</a>`).join(" ")
      : "—";
    document.getElementById("plate-trail").innerHTML = n
      ? plate.occurrences.map(trailItemHtml).join("")
      : `<li class="help">Le lasermark se renseigne dans la carte « Plaques & entités physiques » d'une fiche, ou au lancement d'une expérience.</li>`;
    if (n && pluginEnabled("characterization")) renderWaferDbLinks(document.querySelectorAll(".js-db-link"), [plate.lasermark]);
  } catch (err) {
    showError(err);
  }
}

init();
