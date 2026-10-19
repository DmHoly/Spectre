/* L'onglet « Data » de la page d'une plaque (wafers/pages/wafer.html), monté par wafer.js quand une étude la suit
   (elle est alors rattachée à un µprojet, donc à un projet corporate) - PlateData.mount(plate).

   Dans l'onglet « Data » de la page (PlateTabs, wafer.js - montré aussi par sem_images pour ses images MEB),
   chargé au premier affichage seulement - le calcul peut lire PRISM :
   - les données principales de la plaque, bloc par bloc, telles que le projet corporate les a configurées
     (/fiche-data) : valeurs (situées parmi les plaques du projet déjà calculées), histogrammes, boîtes à
     moustaches, nuages de points, cartographies, courbes (charts.js), galeries d'images (vignettes, puis la
     visionneuse : viewer.js). Une plaque de deux projets : une bascule entre eux. GET /api/wafers/{lasermark}/data ;
     « Rafraîchir » relit les bases (?refresh=true) ;
   - sa généalogie : par µprojet dont on est membre, la partie de son arbre d'études qui la concerne - les études
     qui la suivent (halo), celles d'où elles viennent et celles qui les ont reprises (GET .../lineage,
     experiments) - et ses autres noms (renommages XX -> YY, passeport `links`). */

const PlateData = (() => {
  const C = WaferDataCharts;
  let plate = null;
  let loaded = false;
  let sheet = null;
  let areaIndex = 0;
  const imageFilter = new Map(); // bloc d'images -> groupe montré (null : tous)
  const GALLERY = 12; // vignettes montrées dans la carte ; la visionneuse les a toutes

  const icon = (path) => `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
  const REFRESH = '<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/>';
  const GEAR = '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>';

  // --- l'onglet « Data » (PlateTabs, wafer.js) ----------------------------------------------------

  function mount(passport) {
    plate = passport;
    if (!document.getElementById("plate-tabs")) return;
    document.getElementById("plate-data-main").hidden = false;
    document.getElementById("plate-genealogy").hidden = false;
    PlateTabs.show();
    PlateTabs.onShow("data", () => {
      if (!loaded) load();
    });
  }

  // --- les données ----------------------------------------------------------------------------------

  async function load({ refresh = false } = {}) {
    loaded = true;
    const body = document.querySelector("#plate-tab-data .js-data-body");
    const button = document.querySelector("#plate-tab-data .js-data-refresh");
    if (!sheet || refresh) body.innerHTML = skeletonHtml();
    button.disabled = true;
    try {
      sheet = await waferDataApi.sheet(plate.lasermark, { refresh });
      areaIndex = Math.min(areaIndex, Math.max(sheet.areas.length - 1, 0));
      render();
    } catch (err) {
      body.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
    } finally {
      button.disabled = false;
    }
    if (!refresh) Genealogy.render(document.querySelector("#plate-tab-data .js-genealogy"), plate);
  }

  function skeletonHtml() {
    return `<div class="wd-values">${'<div class="card wd-tile skeleton" style="height:118px;"></div>'.repeat(3)}</div>
      <div class="wd-charts">${'<div class="card skeleton" style="height:260px;"></div>'.repeat(2)}</div>`;
  }

  function freshness(blocks) {
    const dates = blocks.map((b) => b.computed_at).filter(Boolean).sort();
    if (!dates.length) return "";
    const oldest = dates[0];
    return `Calculée le ${escapeHtml(formatDate(oldest))}${sheet.source === "demo" ? " · données de démonstration" : ""}`;
  }

  function render() {
    const body = document.querySelector("#plate-tab-data .js-data-body");
    const meta = document.querySelector("#plate-tab-data .js-data-meta");
    if (!sheet.areas.length) {
      meta.textContent = "";
      body.innerHTML = `<p class="help">Aucun µprojet de cette plaque n'est rangé dans un projet corporate : rien ne dit encore quelles données montrer.</p>`;
      return;
    }
    const current = sheet.areas[areaIndex];
    const switcher =
      sheet.areas.length > 1
        ? `<div class="view-toggle wd-area-toggle" role="group" aria-label="Projet corporate">${sheet.areas
            .map((a, i) => `<button type="button" class="view-toggle__btn${i === areaIndex ? " active" : ""}" data-area="${i}" aria-pressed="${i === areaIndex}">${escapeHtml(a.area.name)}</button>`)
            .join("")}</div>`
        : "";
    meta.innerHTML = freshness(current.blocks);
    const configure = `/fiche-data?projet=${encodeURIComponent(current.area.slug)}`;
    const head = `<div class="wd-area-head">
        ${switcher}
        <p class="help wd-area-head__text">Ce que le projet <strong>${escapeHtml(current.area.name)}</strong> montre sur ses plaques${current.microprojects.length ? ` - elle y entre par ${current.microprojects.map((m) => `<a class="fiche-code" href="/microprojets/${encodeURIComponent(m.slug)}">${escapeHtml(m.code || m.name)}</a>`).join(" ")}` : ""}.</p>
        ${current.can_manage ? `<a class="btn btn-line" href="${configure}">${icon(GEAR)}Configurer la fiche</a>` : ""}
      </div>`;
    if (!current.blocks.length) {
      body.innerHTML = `${head}<div class="card card-pad wd-empty">
        <p class="wd-empty__title">Le projet n'a pas encore choisi les données de ses fiches.</p>
        <p class="help">Des valeurs (une médiane d'EQE, un rendement), des histogrammes, des cartographies de PL, des courbes, des images : ${current.can_manage ? `<a href="${configure}">configurez la fiche data du projet</a>.` : "un manager du projet les choisit sur la page « Fiche data » du menu Data."}</p>
      </div>`;
    } else {
      const values = current.blocks.filter((b) => b.kind === "value");
      const charts = current.blocks.filter((b) => ["histogram", "boxplot", "scatter", "wafermap", "curve"].includes(b.kind));
      const images = current.blocks.filter((b) => b.kind === "images");
      body.innerHTML = `${head}
        ${values.length ? `<div class="wd-values">${values.map(valueHtml).join("")}</div>` : ""}
        ${charts.length ? `<div class="wd-charts">${charts.map(chartHtml).join("")}</div>` : ""}
        ${images.map(imagesHtml).join("")}`;
    }
    body.querySelectorAll("[data-area]").forEach((b) =>
      b.addEventListener("click", () => {
        areaIndex = Number(b.dataset.area);
        render();
      })
    );
  }

  // la galerie : un groupe choisi (puce), une vignette ouverte dans la visionneuse
  document.addEventListener("click", (event) => {
    const host = event.target.closest("#plate-tab-data .wd-images[data-block]");
    if (!host || !sheet) return;
    const block = sheet.areas[areaIndex].blocks.find((b) => String(b.id) === host.dataset.block);
    if (!block) return;
    const chip = event.target.closest("[data-image-group]");
    const thumb = event.target.closest("[data-image]");
    const all = event.target.closest("[data-images-all]");
    if (chip) {
      imageFilter.set(block.id, chip.dataset.imageGroup === "" ? null : Number(chip.dataset.imageGroup));
      host.outerHTML = imagesHtml(block);
    } else if (thumb || all) {
      const group = imageFilter.has(block.id) ? imageFilter.get(block.id) : null;
      WaferDataViewer.open({ title: block.title, images: block.data.images, groups: block.data.groups || [], index: thumb ? Number(thumb.dataset.image) : shown(block)[0], group });
    }
  });

  function statusHtml(block) {
    if (block.status === "error") return `<p class="wd-state wd-state--error">${escapeHtml(block.message || "Calcul impossible.")}</p>`;
    if (block.status === "empty") {
      const why = block.data && block.data.reason === "not_vectors" ? "Ces colonnes ne portent pas de courbes (une valeur par ligne, pas une série) : choisissez deux colonnes de type vecteur." : block.message || "Pas encore de mesure pour cette plaque.";
      return `<p class="wd-state">${escapeHtml(why)}</p>`;
    }
    return "";
  }

  const COUNTED = { curve: ["courbe", "courbes"], images: ["image", "images"], boxplot: ["valeur", "valeurs"] };

  function sourceLine(block) {
    const d = block.data || {};
    const parts = [escapeHtml(block.hook_title || "Fichiers")];
    const [one, many] = COUNTED[block.kind] || ["point", "points"];
    const n = block.kind === "images" ? d.total : d.n;
    if (n) parts.push(`${n} ${n > 1 ? many : one}`);
    if (d.date) parts.push(`mesure du ${escapeHtml(formatDate(d.date))}${d.dates && d.dates.length > 1 ? ` (${d.dates.length} dates)` : ""}`);
    (block.config.filters || []).forEach((f) => parts.push(escapeHtml(typeof kpiFilterText === "function" ? kpiFilterText(f) : `${f.column} ${f.op} ${f.value}`)));
    return `<p class="wd-source">${parts.join(" · ")}</p>`;
  }

  function valueHtml(block) {
    const d = block.data || {};
    const ok = block.status === "ok";
    const population = block.population;
    return `<div class="card wd-tile">
      <div class="wd-tile__label" title="${escapeHtml(block.title)}">${escapeHtml(block.title)}</div>
      ${ok ? `<div class="wd-tile__value">${C.fmt(d.value)}${block.unit ? `<span class="wd-tile__unit">${escapeHtml(block.unit)}</span>` : ""}</div>` : statusHtml(block)}
      ${ok && population ? `<div class="wd-tile__rank">${C.strip(population, d.value)}<p>${escapeHtml(C.rankText(population, block.config.better))}</p></div>` : ok ? `<p class="wd-tile__rank help">Seule plaque calculée du projet pour l'instant.</p>` : ""}
      ${sourceLine(block)}
    </div>`;
  }

  function chartHtml(block) {
    const d = block.data;
    const c = block.config;
    const units = block.units || {};
    let figure = statusHtml(block);
    let caption = "";
    let keys = "";
    if (block.status === "ok") {
      if (block.kind === "histogram") {
        figure = C.histogram(d, block.unit, { color: c.color, xLabel: C.label(c.column, block.unit) });
        keys = C.legend(d.groups, C.groupColors(d.groups), c.color_by);
        caption = `Médiane <strong>${C.fmt(d.median)}</strong> · Q1 ${C.fmt(d.q1)} · Q3 ${C.fmt(d.q3)} · moyenne ${C.fmt(d.mean)}`;
      } else if (block.kind === "boxplot") {
        figure = C.boxplot(d, block.unit, { color: c.color, yLabel: C.label(c.column, block.unit) });
        const one = d.boxes.length === 1 ? d.boxes[0] : null;
        caption = one
          ? `Médiane <strong>${C.fmt(one.median)}</strong> · Q1 ${C.fmt(one.q1)} · Q3 ${C.fmt(one.q3)} · ${one.outliers.length} valeur${one.outliers.length > 1 ? "s" : ""} hors des moustaches`
          : `Une boîte par ${escapeHtml(c.group_by)} · moustaches à 1,5 × l'écart interquartile`;
      } else if (block.kind === "scatter") {
        figure = C.scatter(d, { color: c.color, xLabel: C.label(c.x, units.x), yLabel: C.label(c.y, units.y) });
        keys = C.legend(d.groups, C.groupColors(d.groups), c.color_by);
        caption = d.shown < d.n ? `${d.shown} points montrés sur ${d.n}, pris à pas réguliers` : "";
      } else if (block.kind === "wafermap") {
        figure = C.wafermap(d, block.unit);
        caption = `Médiane <strong>${C.fmt(d.median)}</strong> · de ${C.fmt(d.minimum)} à ${C.fmt(d.maximum)}${block.unit ? " " + escapeHtml(block.unit) : ""} · échelle bornée aux moustaches`;
      } else {
        figure = C.curve(d, block.unit, { color: c.color, xLabel: C.label(c.x, units.x), yLabel: C.label(c.y, units.y) });
        keys = C.legend(d.groups, C.groupColors(d.groups), c.color_by);
        const tint = d.series ? "var(--text-soft)" : C.single(c.color);
        if (d.curves) caption = `${d.curves.length} courbe${d.curves.length > 1 ? "s" : ""} montrée${d.curves.length > 1 ? "s" : ""}${d.curves.length < d.n ? ` sur ${d.n}` : ""} · <span class="wd-key wd-key--overall"></span>médiane de toutes`;
        else caption = `<span class="wd-key wd-key--line" style="background:${tint}"></span>médiane <span class="wd-key wd-key--band" style="background:${tint}"></span>10 - 90 % des courbes${d.series ? " de chaque groupe" : ""}`;
      }
    }
    return `<figure class="card wd-chart wd-chart--${block.kind}">
      <figcaption class="wd-chart__head"><span class="wd-chart__title">${escapeHtml(block.title)}</span><span class="wd-chart__kind">${escapeHtml(block.kind_label)}</span></figcaption>
      <div class="wd-chart__figure">${figure}</div>
      ${keys}
      ${caption ? `<p class="wd-chart__caption">${caption}</p>` : ""}
      ${sourceLine(block)}
    </figure>`;
  }

  // les indices des images du groupe choisi dans la galerie d'un bloc
  function shown(block) {
    const group = imageFilter.has(block.id) ? imageFilter.get(block.id) : null;
    return (block.data.images || []).map((_, i) => i).filter((i) => group === null || block.data.images[i].g === group);
  }

  function imagesHtml(block) {
    const d = block.data || {};
    const head = `<div class="wd-chart__head"><span class="wd-chart__title">${escapeHtml(block.title)}</span><span class="wd-chart__kind">${escapeHtml(block.kind_label)}</span></div>`;
    if (block.status !== "ok") return `<section class="card wd-images" data-block="${block.id}">${head}${statusHtml(block)}${block.hook ? sourceLine(block) : ""}</section>`;
    const images = d.images || [];
    const groups = d.groups || [];
    const group = imageFilter.has(block.id) ? imageFilter.get(block.id) : null;
    const chips = groups.length
      ? `<div class="wd-images__groups" role="group" aria-label="Groupes d'images">${[["", "Toutes", d.total], ...groups.map((g, i) => [String(i), g, (d.counts || [])[i]])]
          .map(([key, name, n]) => {
            const on = (key === "" && group === null) || Number(key) === group;
            return `<button type="button" class="wd-viewer__chip" data-image-group="${key}" aria-pressed="${on}">${escapeHtml(name)} <span>${n ?? ""}</span></button>`;
          })
          .join("")}</div>`
      : "";
    const list = shown(block);
    const thumbs = list
      .slice(0, GALLERY)
      .map((i) => {
        const img = images[i];
        const caption = Object.values(img.meta || {}).join(" · ") || img.name;
        return `<button type="button" class="wd-image" data-image="${i}" title="${escapeHtml(img.name)}" aria-label="Agrandir ${escapeHtml(img.name)}">
          <img src="${escapeHtml(img.url)}" alt="" loading="lazy">
          <span class="wd-image__name">${escapeHtml(caption)}</span></button>`;
      })
      .join("");
    const kept = d.total - images.length;
    const notes = [];
    if (list.length > GALLERY) notes.push(`<button type="button" class="btn btn-line" data-images-all>Voir les ${list.length} images</button>`);
    if (kept > 0) notes.push(`<span class="help">${images.length} images gardées sur ${d.total}${d.directory ? ` dans <span class="mono">${escapeHtml(d.directory)}</span>` : ""}${block.hook && groups.length ? ", prises tour à tour dans chaque groupe" : ""}.</span>`);
    if (d.blocked) notes.push(`<span class="help">${d.blocked} hors des dossiers autorisés : elles ne s'afficheront pas.</span>`);
    return `<section class="card wd-images" data-block="${block.id}">${head}${chips}
      <div class="wd-images__grid">${thumbs}</div>
      ${notes.length ? `<div class="wd-images__more">${notes.join("")}</div>` : ""}
      ${block.hook ? sourceLine(block) : ""}
    </section>`;
  }

  return {
    mount,
    refresh: () => load({ refresh: true }),
  };
})();

/* La généalogie d'une plaque : pour chaque µprojet qui la suit (dont on est membre), la partie de son arbre
   d'études qui la touche - les nœuds qui la portent (halo), leurs ancêtres (d'où elle vient) et leurs
   descendants (ce qui l'a reprise) - au même dessin que l'arbre d'un µprojet (experiments/lineage-graph.js). */
const Genealogy = (() => {
  function subgraph(graph, key) {
    const mine = new Set(graph.nodes.filter((n) => (n.wafers || []).some((w) => waferKey(w) === key)).map((n) => n.id));
    if (!mine.size) return null;
    const up = new Map(), down = new Map();
    graph.edges.forEach((e) => {
      (up.get(e.child) || up.set(e.child, []).get(e.child)).push(e.parent);
      (down.get(e.parent) || down.set(e.parent, []).get(e.parent)).push(e.child);
    });
    const walk = (start, links) => {
      const seen = new Set(), stack = [...start];
      while (stack.length) {
        const id = stack.pop();
        (links.get(id) || []).forEach((next) => {
          if (!seen.has(next)) {
            seen.add(next);
            stack.push(next);
          }
        });
      }
      return seen;
    };
    const ancestors = walk(mine, up), descendants = walk(mine, down);
    const kept = new Set([...mine, ...ancestors, ...descendants]);
    return {
      nodes: graph.nodes.filter((n) => kept.has(n.id)),
      edges: graph.edges.filter((e) => kept.has(e.parent) && kept.has(e.child)),
      mine,
      ancestors: [...ancestors].filter((id) => !mine.has(id)).length,
      descendants: [...descendants].filter((id) => !mine.has(id)).length,
    };
  }

  function short(text, n = 16) {
    const t = String(text || "");
    return t.length > n ? `${t.slice(0, n - 1)}…` : t;
  }

  function treeHtml(slug, sub) {
    const R = 7;
    const { positioned, width } = lineageLayout(sub.nodes, sub.edges, { colWidth: 130, rowHeight: 72, margin: 64 });
    // la hauteur juste nécessaire (le layout en garde 200 au moins) : la place des libellés sous la dernière rangée
    positioned.forEach((n) => (n.y -= 40));
    const height = Math.max(...positioned.map((n) => n.y)) + 44;
    const byId = new Map(positioned.map((n) => [n.id, n]));
    const edges = sub.edges
      .map((e) => `<path d="${lineageEdgePath(byId.get(e.parent), byId.get(e.child))}" class="wd-tree__edge${e.attached ? " wd-tree__edge--attached" : ""}"></path>`)
      .join("");
    const nodes = positioned
      .map((n) => {
        const mine = sub.mine.has(n.id);
        const page = `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(n.experiment_id)}${n.is_tip ? "" : `?version=${encodeURIComponent(n.version_id)}`}`;
        return `<a href="${page}" class="wd-tree__node${mine ? " wd-tree__node--mine" : ""}" aria-label="${escapeHtml(n.title)}${mine ? " - suit cette plaque" : ""}">
          <g transform="translate(${n.x},${n.y})">${lineageNodeShapeHtml(n, { radius: mine ? R + 1.5 : R, selected: mine })}
            <title>${escapeHtml(lineageNodeTooltip(n))}</title>
            <text y="${R + 18}" text-anchor="middle" class="wd-tree__label">${escapeHtml(short(n.title))}</text></g></a>`;
      })
      .join("");
    return `<div class="wd-tree__scroll"><svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" class="wd-tree__svg">${edges}${nodes}</svg></div>`;
  }

  function namesHtml(plate) {
    const chain = plate.links;
    if (!chain || (!chain.before.length && !chain.after.length)) return "";
    const name = (item) => `<a class="wd-name" href="/plaques/${encodeURIComponent(item.lasermark || item.key)}">${escapeHtml(item.lasermark || item.key)}</a>`;
    const arrow = `<span class="wd-names__arrow" aria-hidden="true">→</span>`;
    return `<div class="card card-pad wd-names">
      <div class="wd-chart__head"><span class="wd-chart__title">Ses noms</span><span class="wd-chart__kind">collage, report</span></div>
      <p class="wd-names__chain">${[...chain.before.map(name), `<strong class="wd-name wd-name--current">${escapeHtml(plate.lasermark)}</strong>`, ...chain.after.map(name)].join(arrow)}</p>
    </div>`;
  }

  async function render(host, plate) {
    if (!host) return;
    const key = waferKey(plate.lasermark);
    const microprojects = [];
    plate.occurrences.forEach((o) => {
      const mp = o.experiment.microproject;
      const found = microprojects.find((m) => m.slug === mp.slug);
      if (found) found.member = found.member || o.experiment.member;
      else microprojects.push({ ...mp, member: o.experiment.member });
    });
    host.innerHTML = `${namesHtml(plate)}<div class="js-trees">${microprojects.map(() => '<div class="card skeleton" style="height:180px;margin-bottom:12px;"></div>').join("")}</div>`;
    const trees = await Promise.all(
      microprojects.map(async (mp) => {
        const head = `<div class="wd-chart__head"><a class="fiche-code" href="/microprojets/${encodeURIComponent(mp.slug)}">${escapeHtml(mp.code || mp.name)}</a><span class="wd-chart__title">${escapeHtml(mp.name)}</span></div>`;
        if (!mp.member) return `<div class="card card-pad wd-tree">${head}<p class="help">Un µprojet dont vous n'êtes pas membre : son arbre ne vous est pas ouvert.</p></div>`;
        try {
          const sub = subgraph(await experimentsApi.lineage(mp.slug), key);
          if (!sub) return `<div class="card card-pad wd-tree">${head}<p class="help">Elle n'apparaît dans aucun nœud de l'arbre de ce µprojet.</p></div>`;
          const said = [`${sub.mine.size} étude${sub.mine.size > 1 ? "s la suivent" : " la suit"}`];
          said.push(sub.ancestors ? `elle vient de ${sub.ancestors} étude${sub.ancestors > 1 ? "s" : ""} antérieure${sub.ancestors > 1 ? "s" : ""}` : "aucune étude avant elle");
          said.push(sub.descendants ? `${sub.descendants} étude${sub.descendants > 1 ? "s ont continué" : " a continué"} depuis ses études` : "pas encore de suite");
          return `<div class="card card-pad wd-tree">${head}<p class="help wd-tree__summary">${said.join(" · ")}.</p>${treeHtml(mp.slug, sub)}</div>`;
        } catch (err) {
          return `<div class="card card-pad wd-tree">${head}<p class="help">Arbre indisponible : ${escapeHtml(err.message || String(err))}</p></div>`;
        }
      })
    );
    host.querySelector(".js-trees").innerHTML = trees.join("") + `<div class="wd-legend">${lineageLegendHtml({ merge: true, tip: true })}<span class="wd-legend__mine"><svg width="22" height="22" viewBox="-11 -11 22 22" aria-hidden="true"><circle r="9" fill="none" stroke="var(--accent)" stroke-width="2"></circle><circle r="5" fill="var(--surface)" stroke="var(--draft)" stroke-width="2"></circle></svg>une étude qui suit cette plaque</span></div>`;
  }

  return { render, subgraph };
})();

document.addEventListener("click", (event) => {
  if (event.target.closest("#plate-tab-data .js-data-refresh")) PlateData.refresh();
});
