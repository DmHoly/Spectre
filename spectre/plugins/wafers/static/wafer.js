/* Page d'une plaque (wafer.html, /plaques/<lasermark>) : où elle est, ses FDL, ses données en base,
   et son parcours - chaque étude qui la suit (la plus récente d'abord), avec son µprojet, son
   statut, la variante qu'elle porte dans une campagne, l'emplacement et les FDL notés dans cette
   étude. On y arrive depuis la recherche de la topbar ou un lasermark cliqué sur une fiche. */

const lasermark = decodeURIComponent(window.location.pathname.split("/").filter(Boolean)[1] || "");

function showError(err) {
  const box = document.getElementById("error");
  box.textContent = err.message || String(err);
  box.style.display = "block";
}

function trailItemHtml(o) {
  const exp = o.experience;
  const mp = o.microproject;
  const url = `/microprojets/${encodeURIComponent(mp.slug)}/experiences/${encodeURIComponent(exp.id)}`;
  return `
    <li class="plate-trail__item">
      <span class="plate-trail__dot" aria-hidden="true"></span>
      <div class="card plate-trail__card">
        <div class="plate-trail__head">
          ${statusBadgeHtml(exp.status)}
          <a class="fiche-code" href="/microprojets/${encodeURIComponent(mp.slug)}" title="µprojet ${escapeHtml(mp.name)}">${escapeHtml(mp.code || mp.name)}</a>
          <span class="plate-trail__date">mise à jour le ${formatDate(exp.updated_at)}</span>
        </div>
        <a class="plate-trail__title" href="${url}">${escapeHtml(exp.title)}</a>
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
    const plate = await api.get(`/api/plaques/${encodeURIComponent(lasermark)}`);
    const n = plate.occurrences.length;
    document.getElementById("plate-lasermark").textContent = plate.sample_id;
    document.getElementById("plate-summary").textContent = n
      ? `Suivie dans ${n} étude${n > 1 ? "s" : ""}${plate.microprojects.length > 1 ? `, sur ${plate.microprojects.length} µprojets` : ""}.`
      : "Aucune étude de vos µprojets ne suit cette plaque.";
    document.getElementById("plate-location").textContent = plate.last_location || "—";
    document.getElementById("plate-fdl").innerHTML = plate.fdl.length ? fdlChipsHtml(plate.fdl, { label: false }) : "—";
    document.getElementById("plate-microprojects").innerHTML = plate.microprojects.length
      ? plate.microprojects
          .map((m) => `<a class="fiche-code" href="/microprojets/${encodeURIComponent(m.slug)}" title="${escapeHtml(m.name)}">${escapeHtml(m.code || m.name)}</a>`)
          .join(" ")
      : "—";
    // le(s) lot(s) de fabrication qui la contiennent (suivi de lots, /lots)
    document.getElementById("plate-lots").innerHTML = (plate.lots || []).length
      ? plate.lots.map((l) => `<a class="fiche-code" href="/lots/${encodeURIComponent(l.code)}" title="${escapeHtml(l.title || "Lot")}">${escapeHtml(l.code)}</a>`).join(" ")
      : "—";
    document.getElementById("plate-trail").innerHTML = n
      ? plate.occurrences.map(trailItemHtml).join("")
      : `<li class="help">Le lasermark se renseigne dans la carte « Plaques & entités physiques » d'une fiche, ou au lancement d'une expérience.</li>`;
    if (n) renderWaferDbLinks(document.querySelectorAll(".js-db-link"), [plate.sample_id]);
  } catch (err) {
    showError(err);
  }
}

init();
