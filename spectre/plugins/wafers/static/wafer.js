/* Page d'une plaque (wafer.html, /plaques/<lasermark>) : la structure qu'elle a vue (celle de la
   dernière étude de vos µprojets qui la suit), où elle est, ses FDL, ses données en base, sa fiche
   de plaque (une plaque enregistrée pour elle-même, avant toute étude : records.js), son parcours -
   chaque étude qui la suit (la plus récente d'abord), avec son µprojet, son statut, la variante
   qu'elle porte dans une campagne, l'emplacement et les FDL notés dans cette étude - et sa vie en
   ligne (tracking.js) ; « Comparer sa structure » ouvre le comparateur sur elle, « Rattacher à une
   étude » (attach.js) la fait entrer dans une étude existante. On y arrive depuis la recherche de
   la topbar, l'index des plaques ou un lasermark cliqué sur une fiche.

   Sans étude, une plaque peut aussi porter sa propre structure (« Attacher une structure »,
   plate-structure.js : une version de référence ou une structure de la bibliothèque). Ses FDL et son
   lot JIRA viennent aussi de sa vie en ligne (repris dans l'en-tête dès qu'elle est lue), et une
   plaque qui a changé de nom (XX devenue YY après un collage) montre sa lignée (plate-links.js).
   Son nom courant est son run d'épitaxie (« la VA1725 ») : le plus récent est le principal, ses
   runs d'avant la désignent aussi - tous la retrouvent, et /plaques/VA1725 mène à elle. */

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
      <p class="plate-structure__attach" style="margin:0 0 10px;"><button type="button" class="btn btn-primary js-structure-direct">Attacher une structure</button></p>
      <p class="help" style="margin:0 0 10px;">Une version de référence ou une structure de la bibliothèque, directement sur la plaque - sans µprojet. Ou bien&nbsp;:</p>
      ${
        slugs.length
          ? `<p class="help" style="margin:0 0 8px;">Définissez-la en lançant une expérience qui suit cette plaque${slugs.length > 1 ? ", dans" : ` dans ${escapeHtml(slugs[0].code || slugs[0].name)}`}&nbsp;:</p>
             ${slugs.length > 1 ? `<select class="plate-structure__mp js-structure-mp" aria-label="µprojet">${slugs.map((m) => `<option value="${escapeHtml(m.slug)}">${escapeHtml(m.code || m.name)} - ${escapeHtml(m.name)}</option>`).join("")}</select>` : ""}
             <div class="plate-structure__options js-structure-options">${cards(slugs[0].slug)}</div>`
          : `<p class="help" style="margin:0;">Sa structure sera celle de l'étude qui la suivra : une étude existante d'un de vos µprojets, ou une nouvelle expérience lancée depuis la page du <a href="/">µprojet</a> (dessin collé, constructeur ou structure existante) en la suivant dans la carte « Plaques & entités physiques ».</p>
             <p class="plate-structure__attach"><button type="button" class="btn btn-line js-structure-attach">Rattacher à une étude</button></p>`
      }
    </div>`;
  figure.querySelector(".js-structure-direct").addEventListener("click", () => openStructurePicker(plate));
  const attach = figure.querySelector(".js-structure-attach");
  if (attach) attach.addEventListener("click", () => openAttach(plate));
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
  } else if (plate.structure) {
    renderAttachedStructure(plate, aside, figure);
    return;
  } else {
    renderNoStructure(plate, aside, figure);
    return;
  }
  const exp = latest.experiment;
  aside.querySelector(".js-structure-caption").innerHTML = `Vue dans <a href="/microprojets/${encodeURIComponent(exp.microproject.slug)}/experiences/${encodeURIComponent(exp.id)}">${escapeHtml(exp.title)}</a>${latest.variant ? ` · variante <strong class="mono">${escapeHtml(latest.variant)}</strong>` : ""}`;
  aside.hidden = false;
}

// La structure attachée à la plaque elle-même (sans étude) : son dessin, d'où elle vient, et de quoi
// la changer ou la retirer.
function renderAttachedStructure(plate, aside, figure) {
  const st = plate.structure;
  figure.innerHTML = st.svg
    ? `<button type="button" class="builder-canvas-svg structure-zoomable js-structure-zoom" aria-label="Agrandir la structure" title="Agrandir et zoomer">${st.svg}${STRUCTURE_ZOOM_BADGE}</button>`
    : `<div class="plate-structure__empty"><p class="plate-structure__empty-title">${escapeHtml(st.label)}</p><p class="help" style="margin:0;">Pas de dessin pour cette structure.</p></div>`;
  const zoom = figure.querySelector(".js-structure-zoom");
  if (zoom) zoom.addEventListener("click", () => openStructureZoom({ title: `${plate.lasermark} - ${st.label}`, items: [{ html: st.svg }] }));
  const origin = st.kind === "reference" ? "version de référence" : "structure de la bibliothèque";
  aside.querySelector(".js-structure-caption").innerHTML = `
    <strong>${escapeHtml(st.label)}</strong> · ${origin}, attachée à la plaque le ${escapeHtml(formatDate(st.attached_at))} par ${escapeHtml(st.attached_by)}
    <span class="plate-structure__actions"><button type="button" class="btn-link js-structure-change">Changer</button> · <button type="button" class="btn-link js-structure-remove">Retirer</button></span>`;
  aside.querySelector(".js-structure-change").addEventListener("click", () => openStructurePicker(plate));
  aside.querySelector(".js-structure-remove").addEventListener("click", async () => {
    if (!window.confirm(`Retirer la structure « ${st.label} » de la plaque ?`)) return;
    try {
      await wafersApi.removeStructure(plate.key);
      window.location.reload();
    } catch (err) {
      showError(err);
    }
  });
  aside.hidden = false;
}

function openStructurePicker(plate) {
  WaferStructurePicker.open({ lasermark: plate.lasermark, onDone: () => window.location.reload() });
}

// « Rattacher à une étude » : la plaque entre dans une étude existante ; la page se relit ensuite
// (son parcours la montre).
function openAttach(plate) {
  WaferAttach.open({ lasermark: plate.lasermark, onDone: () => window.location.reload() });
}

// La fiche de plaque : quand, par qui, depuis quelle base, et ce que la base en disait ce jour-là
function renderRecord(plate) {
  const record = plate.record;
  const fact = document.getElementById("plate-record-fact");
  const remove = document.getElementById("plate-record-delete");
  if (!record) {
    fact.hidden = true;
    remove.hidden = true;
    return;
  }
  const summary = WaferRecords.summaryHtml(record.summary);
  document.getElementById("plate-record").innerHTML = `${WaferRecords.chipHtml(record, { title: false })} créée le ${escapeHtml(formatDate(record.created_at))} par ${escapeHtml(record.created_by)}, depuis ${escapeHtml(WaferRecords.sourceLabel(record.source))}${summary ? `<span class="plate-hero__record-summary">${summary}</span>` : ""}`;
  fact.hidden = false;
  remove.hidden = false;
  remove.addEventListener("click", async () => {
    const n = plate.occurrences.length;
    if (!window.confirm(`Retirer la fiche de la plaque « ${plate.lasermark} » ?${n ? ` Les ${n} étude${n > 1 ? "s" : ""} qui la suivent restent.` : " Elle ne sera plus listée tant qu'aucune étude ne la suit."}`)) return;
    remove.disabled = true;
    try {
      await wafersApi.deleteRecord(plate.key);
      window.location.href = n ? window.location.pathname : "/plaques";
    } catch (err) {
      showError(err);
      remove.disabled = false;
    }
  });
}

// Les FDL de l'en-tête : celles notées dans ses études (chez les membres) et celles que sa vie en
// ligne lui connaît (JIRA, Gozer) - ces dernières marquées « en ligne ».
function renderFdl(studyFdl, lineFdl) {
  const extra = (lineFdl || []).filter((f) => !studyFdl.includes(f));
  const html = [
    studyFdl.length ? fdlChipsHtml(studyFdl, { label: false }) : "",
    extra.length ? `<span title="Lues dans JIRA et Gozer (vie de la plaque en ligne)">${fdlChipsHtml(extra, { label: false })}</span> <span class="plate-tag plate-tag--mute">en ligne</span>` : "",
  ].filter(Boolean).join(" ");
  document.getElementById("plate-fdl").innerHTML = html || "—";
}

// Les lots de la plaque (plugin lots) en badges ; le lot JIRA lu en ligne, s'il n'a pas (encore)
// de lot dans Spectre, en simple étiquette.
function renderLots(lots, lotName) {
  const el = document.getElementById("plate-lots");
  if (!pluginEnabled("lots")) {
    el.innerHTML = lotName ? `<span class="mono">${escapeHtml(lotName)}</span>` : `<span class="help" style="margin:0;">Suivi des lots désactivé</span>`;
    return;
  }
  const badges = lots.map(
    (l) => `<a class="fiche-code" href="/lots/${encodeURIComponent(l.code)}" title="${escapeHtml(l.title || "Lot")}${l.source === "prism" ? " - lot de la ligne (JIRA)" : ""}">${escapeHtml(l.code)}</a>`
  );
  if (lotName && !lots.some((l) => l.code.toUpperCase() === lotName.toUpperCase())) badges.push(`<span class="mono" title="Lot JIRA lu en ligne">${escapeHtml(lotName)}</span>`);
  el.innerHTML = badges.length ? badges.join(" ") : "—";
}

// Ses noms de run d'épitaxie sous le lasermark : le principal (le plus récent) en avant, ses runs
// d'avant ensuite
function renderRuns(names) {
  const el = document.getElementById("plate-runs");
  el.hidden = !names.length;
  if (!names.length) return;
  el.innerHTML = `<span class="plate-hero__run-label">Run</span> <strong class="mono" title="Son run d'épitaxie principal (le plus récent) : le nom sous lequel on la désigne">${escapeHtml(names[0])}</strong>${
    names.length > 1 ? ` <span class="plate-hero__run-more">aussi ${names.slice(1).map((n) => `<span class="mono" title="Un run d'épitaxie d'avant">${escapeHtml(n)}</span>`).join(", ")}</span>` : ""
  }`;
}

// « /plaques/VA1725 » : ce nom n'est pas une plaque mais le run d'épitaxie d'une (ou de plusieurs)
// - on va à elle s'il n'y en a qu'une, sinon on les liste.
function followRun(plate) {
  const runOf = plate.run_of || [];
  const known = plate.occurrences.length || plate.record || plate.structure || (plate.links && plate.links.links.length);
  if (!runOf.length || known) return false;
  if (runOf.length === 1) {
    window.location.replace(`${plateUrl(runOf[0].lasermark)}?run=${encodeURIComponent(plate.lasermark)}`);
    return true;
  }
  plate.runBanner = `<div class="plate-banner plate-banner--info">« ${escapeHtml(plate.lasermark)} » est le run d'épitaxie de ${runOf.length} plaques : ${runOf
    .map((p) => `<a class="mono" href="${plateUrl(p.lasermark)}">${escapeHtml(p.lasermark)}</a>${p.principal ? "" : " (run d'avant)"}`)
    .join(", ")}.</div>`;
  return false;
}

function renderLinks(plate, user) {
  document.getElementById("plate-links-banner").innerHTML = (plate.runBanner || "") + WaferLinks.bannerHtml(plate);
  const fact = document.getElementById("plate-names-fact");
  const html = WaferLinks.factHtml(plate, user);
  fact.hidden = !html;
  document.getElementById("plate-names").innerHTML = html || "—";
  document.querySelectorAll("#plate-names [data-link]").forEach((button) =>
    button.addEventListener("click", async () => {
      if (!window.confirm("Retirer ce lien entre les deux noms ?")) return;
      try {
        await wafersApi.deleteLink(button.dataset.link);
        window.location.reload();
      } catch (err) {
        showError(err);
      }
    })
  );
}

async function init() {
  document.getElementById("plate-crumb").textContent = lasermark;
  document.getElementById("crumb").textContent = `/ Plaques / ${lasermark}`;
  document.title = `${lasermark} — Spectre`;
  try {
    const lotsOn = pluginEnabled("lots");
    const [plate, lots, user] = await Promise.all([
      wafersApi.get(lasermark),
      lotsOn ? lotsApi.list({ wafer: lasermark, view: "summary" }) : [],
      accountsApi.me().catch(() => null),
    ]);
    if (followRun(plate)) return;
    const n = plate.occurrences.length;
    document.getElementById("plate-lasermark").textContent = plate.lasermark;
    renderRuns(plate.run_names || []);
    const viaRun = new URLSearchParams(window.location.search).get("run");
    document.getElementById("plate-summary").textContent = n
      ? `Suivie dans ${n} étude${n > 1 ? "s" : ""}${plate.microprojects.length > 1 ? `, sur ${plate.microprojects.length} µprojets` : ""}.`
      : plate.record
        ? "Une plaque d'avant Spectre : sa fiche existe, aucune étude ne la suit encore."
        : "Aucune étude ne suit cette plaque, et elle n'a pas de fiche.";
    renderRecord(plate);
    document.getElementById("plate-attach").addEventListener("click", () => openAttach(plate));
    document.getElementById("plate-structure-attach").addEventListener("click", () => openStructurePicker(plate));
    document.getElementById("plate-link-add").addEventListener("click", () => WaferLinks.open({ lasermark: plate.lasermark, onDone: () => window.location.reload() }));
    renderLinks(plate, user);
    if (viaRun) document.getElementById("plate-links-banner").insertAdjacentHTML("afterbegin", `<div class="plate-banner plate-banner--info">Arrivé par le run <strong class="mono">${escapeHtml(viaRun)}</strong> : c'est un run d'épitaxie de cette plaque.</div>`);
    document.getElementById("plate-location").textContent = plate.last_location || "—";
    renderFdl(plate.fdl, plate.line_fdl);
    document.getElementById("plate-microprojects").innerHTML = plate.microprojects.length
      ? plate.microprojects
          .map((m) => `<a class="fiche-code" href="/microprojets/${encodeURIComponent(m.slug)}" title="${escapeHtml(m.name)}">${escapeHtml(m.code || m.name)}</a>`)
          .join(" ")
      : "—";
    // le(s) lot(s) de fabrication qui la contiennent (suivi de lots, /lots), et son lot JIRA
    renderLots(lots, plate.lot_name);
    document.getElementById("plate-trail").innerHTML = n
      ? plate.occurrences.map(trailItemHtml).join("")
      : `<li class="help">Aucune étude encore. « Rattacher à une étude » la fait entrer dans une étude existante ; sinon, son lasermark se renseigne dans la carte « Plaques & entités physiques » d'une fiche, ou au lancement d'une expérience.</li>`;
    // la structure qu'elle a vue, dans le comparateur (une étude d'un de vos µprojets la suit)
    if (plate.occurrences.some((o) => o.experiment.member)) {
      const compare = document.getElementById("plate-compare");
      compare.href = Comparator.pageUrl([Comparator.waferItem(plate.lasermark)]);
      compare.hidden = false;
    }
    if (n && pluginEnabled("characterization")) renderWaferDbLinks(document.querySelectorAll(".js-db-link"), [plate.lasermark]);
    renderStructure(plate);
    // la vie en ligne : ses FDL et son lot JIRA rejoignent l'en-tête (la lecture vient peut-être de
    // créer le lot détecté, ou des liens de renommage vus dans la MES : on les relit alors)
    let linksSeen = (plate.links && plate.links.links.length) || 0;
    initWaferTracking(document.getElementById("plate-life"), plate.lasermark, async (data) => {
      renderFdl(plate.fdl, data.fdl_numbers || plate.line_fdl);
      if (data.run_names) renderRuns(data.run_names);
      let current = lots;
      if (lotsOn && data.lot_name && !lots.some((l) => l.code.toUpperCase() === data.lot_name.toUpperCase())) {
        current = await lotsApi.list({ wafer: lasermark, view: "summary" }).catch(() => lots);
      }
      renderLots(current, data.lot_name);
      if ((data.renames || []).length > linksSeen) {
        const fresh = await wafersApi.get(lasermark).catch(() => null);
        if (fresh) {
          plate.links = fresh.links;
          linksSeen = fresh.links.links.length;
          renderLinks(plate, user);
        }
      }
    });
  } catch (err) {
    showError(err);
  }
}

init();
