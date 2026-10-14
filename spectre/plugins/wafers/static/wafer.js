/* Page d'une plaque (wafer.html, /plaques/<lasermark>) : la structure qu'elle a vue (celle de la
   dernière étude de vos µprojets qui la suit), où elle est, ses FDL, ses données en base, son
   parcours - chaque étude qui la suit (la plus récente d'abord), avec son µprojet, son statut, la
   variante qu'elle porte dans une campagne, l'emplacement et les FDL notés dans cette étude - et sa
   vie en ligne (tracking.js) ; « Comparer sa structure » ouvre le comparateur sur elle. On y arrive
   depuis la recherche de la topbar ou un lasermark cliqué sur une fiche. */

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

// Sans structure : « pas de structure encore définie », et les trois départs qui existent déjà sur
// la page d'un µprojet - un dessin collé (structures/image), le constructeur (structures/nouvelle),
// une structure existante (référence ou bibliothèque : « D'où part-elle ? », ?nouvelle-experience=1).
// Dans le µprojet d'une étude qui suit la plaque dont on est membre (le premier ; un choix s'il y en
// a plusieurs) ; sans µprojet lisible, on dit d'abord de suivre la plaque dans une étude.
function renderNoStructure(plate, aside, figure) {
  const slugs = [];
  plate.occurrences.forEach((o) => {
    const mp = o.experiment.microproject;
    if (o.experiment.member && !slugs.some((s) => s.slug === mp.slug)) slugs.push(mp);
  });
  const lasermark = encodeURIComponent(plate.lasermark);
  const url = (slug, path) => `/microprojets/${encodeURIComponent(slug)}/${path}`;
  const options = (slug) => [
    { href: url(slug, `structures/image`), title: "Coller un dessin", desc: "Une image de la structure (coupe, schéma), annotée, et la plaque suivie dessus." },
    { href: url(slug, `structures/nouvelle`), title: "Dessiner avec le constructeur", desc: "La structure couche par couche, étape par étape, simulée par StructureForge." },
    { href: `${url(slug, "")}?nouvelle-experience=1&plaque=${lasermark}`.replace("/?", "?"), title: "Partir d'une structure existante", desc: "La référence, la meilleure plaque d'une étude, une structure de la bibliothèque." },
  ];
  const cards = (slug) =>
    options(slug)
      .map((o) => `<a class="study-start-card plate-structure__option" href="${o.href}"><span class="study-start-card__title">${escapeHtml(o.title)}</span><span class="study-start-card__desc">${escapeHtml(o.desc)}</span></a>`)
      .join("");
  figure.innerHTML = `
    <div class="plate-structure__empty">
      <p class="plate-structure__empty-title">Pas de structure encore définie.</p>
      ${
        slugs.length
          ? `<p class="help" style="margin:0 0 8px;">Définissez-la en lançant une expérience qui suit cette plaque${slugs.length > 1 ? ", dans" : ` dans ${escapeHtml(slugs[0].code || slugs[0].name)}`}&nbsp;:</p>
             ${slugs.length > 1 ? `<select class="plate-structure__mp js-structure-mp" aria-label="µprojet">${slugs.map((m) => `<option value="${escapeHtml(m.slug)}">${escapeHtml(m.code || m.name)} - ${escapeHtml(m.name)}</option>`).join("")}</select>` : ""}
             <div class="plate-structure__options js-structure-options">${cards(slugs[0].slug)}</div>`
          : `<p class="help" style="margin:0;">Suivez d'abord cette plaque dans une étude d'un de vos <a href="/">µprojets</a> : sa structure se définit au lancement (dessin collé, constructeur ou structure existante).</p>`
      }
    </div>`;
  const select = figure.querySelector(".js-structure-mp");
  if (select) select.addEventListener("change", () => (figure.querySelector(".js-structure-options").innerHTML = cards(select.value)));
  aside.querySelector(".js-structure-caption").innerHTML = "";
  aside.hidden = false;
}

// La structure qu'a vue la plaque : le dessin de la dernière étude dont on est membre (la même
// que « Comparer sa structure »), agrandissable ; sans étude lisible ou sans dessin, les départs
// possibles (renderNoStructure).
async function renderStructure(plate) {
  const aside = document.getElementById("plate-structure");
  const figure = aside.querySelector(".js-structure-figure");
  const latest = plate.occurrences.find((o) => o.experiment.member && o.experiment.version_id);
  let detail = null;
  if (latest) {
    try {
      detail = await experimentsApi.getVersion(latest.experiment.microproject.slug, latest.experiment.id, latest.experiment.version_id);
    } catch (err) {
      detail = null;
    }
  }
  if (detail && detail.structure_svg) {
    const exp = latest.experiment;
    figure.innerHTML = `<button type="button" class="builder-canvas-svg structure-zoomable js-structure-zoom" aria-label="Agrandir la structure" title="Agrandir et zoomer">${detail.structure_svg}${STRUCTURE_ZOOM_BADGE}</button>`;
    figure.querySelector(".js-structure-zoom").addEventListener("click", () => openStructureZoom({ title: `${plate.lasermark} - ${exp.title}`, items: [{ html: detail.structure_svg }] }));
  } else if (detail && detail.structure_images && detail.structure_images.length) {
    const image = detail.structure_images[0];
    figure.innerHTML = `<img class="plate-structure__image" src="${escapeHtml(image.url)}" alt="${escapeHtml(image.caption || "Structure en images")}">`;
  } else {
    renderNoStructure(plate, aside, figure);
    return;
  }
  const exp = latest.experiment;
  aside.querySelector(".js-structure-caption").innerHTML = `Vue dans <a href="/microprojets/${encodeURIComponent(exp.microproject.slug)}/experiences/${encodeURIComponent(exp.id)}">${escapeHtml(exp.title)}</a>${latest.variant ? ` · variante <strong class="mono">${escapeHtml(latest.variant)}</strong>` : ""}`;
  aside.hidden = false;
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
    // la structure qu'elle a vue, dans le comparateur (une étude d'un de vos µprojets la suit)
    if (plate.occurrences.some((o) => o.experiment.member)) {
      const compare = document.getElementById("plate-compare");
      compare.href = Comparator.pageUrl([Comparator.waferItem(plate.lasermark)]);
      compare.hidden = false;
    }
    if (n && pluginEnabled("characterization")) renderWaferDbLinks(document.querySelectorAll(".js-db-link"), [plate.lasermark]);
    renderStructure(plate);
    initWaferTracking(document.getElementById("plate-life"), plate.lasermark);
  } catch (err) {
    showError(err);
  }
}

init();
