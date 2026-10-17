/* Les images MEB du G4 d'une plaque, sur sa page (wafer.html) : PRISM les retrouve sur le partage par les FDL de la
   plaque (et par son index des dossiers - le partage n'en a pas), semImagesApi les liste rangées par acquisition et
   les sert rendues à la volée (GET /api/wafers/{key}/sem-images[/file|/meta]) : rien n'est copié.

   Une acquisition = un dossier de wafer : son étape, sa FDL, son procédé, sa zone du partage, ses passes (r1, r2).
   La plus récente est ouverte ; ses vignettes se chargent quand elles deviennent visibles. Un clic ouvre la
   visionneuse (SemViewer) : l'image entière, zoom à la molette et déplacement, barre d'échelle tirée du champ de
   vue du TIF, ses détecteurs (une trame chacun), la fiche du défaut revu, précédente / suivante au clavier.
   Sans image : où l'on a cherché, l'index en construction (la recherche reprend d'elle-même), et un champ pour
   chercher avec une autre FDL. */

// 'YYYY-MM-DDTHH:MM:SS+00:00' -> « 17 oct. 2026, 05:40 » (heure locale)
function semDate(iso, withTime = true) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return escapeHtml(iso);
  const day = date.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
  return withTime ? `${day}, ${date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}` : day;
}

function semImageLabel(image) {
  if (image.die === null || image.die === undefined) return image.name;
  return `d${image.die}${image.round ? ` · r${image.round}` : ""}`;
}

/* La visionneuse : un seul <dialog>, rempli à chaque ouverture (la liste d'images d'une acquisition et l'index). */
const SemViewer = (() => {
  let dialog = null;
  let ctx = null; // {lasermark, fdl, group, images, index}
  let view = { scale: 1, x: 0, y: 0, frame: 0 };
  let meta = null;
  let drag = null;
  let token = 0;

  function el(selector) {
    return dialog.querySelector(selector);
  }

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "sem-viewer";
    dialog.setAttribute("aria-labelledby", "sem-viewer-title");
    dialog.innerHTML = `
      <div class="sem-viewer__layout">
        <div class="sem-viewer__stage js-stage" tabindex="0" aria-label="Image MEB : molette pour zoomer, glisser pour déplacer">
          <img class="sem-viewer__img js-img" alt="" draggable="false">
          <div class="sem-viewer__loading js-loading" hidden>Chargement…</div>
          <div class="sem-viewer__tools">
            <div class="sem-viewer__frames js-frames" role="group" aria-label="Détecteur"></div>
            <div class="sem-viewer__zoom" role="group" aria-label="Zoom">
              <button type="button" class="sem-viewer__tool js-zoom-out" aria-label="Dézoomer" title="Dézoomer (-)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14"/></svg>
              </button>
              <button type="button" class="sem-viewer__tool sem-viewer__tool--text js-zoom-reset" title="Image entière (0)">100 %</button>
              <button type="button" class="sem-viewer__tool js-zoom-in" aria-label="Zoomer" title="Zoomer (+)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
              </button>
            </div>
          </div>
          <div class="sem-viewer__scale js-scale" hidden><span class="sem-viewer__scale-bar js-scale-bar"></span><span class="js-scale-label"></span></div>
          <button type="button" class="sem-viewer__nav sem-viewer__nav--prev js-prev" aria-label="Image précédente" title="Précédente (←)">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
          </button>
          <button type="button" class="sem-viewer__nav sem-viewer__nav--next js-next" aria-label="Image suivante" title="Suivante (→)">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>
          </button>
        </div>
        <aside class="sem-viewer__side">
          <div class="sem-viewer__head">
            <div>
              <div class="page-eyebrow js-sub"></div>
              <h2 class="sem-viewer__title" id="sem-viewer-title"></h2>
              <p class="sem-viewer__count js-count"></p>
            </div>
            <button type="button" class="btn btn-line sem-viewer__close js-close" aria-label="Fermer">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>
            </button>
          </div>
          <dl class="sem-viewer__facts js-facts"></dl>
          <div class="sem-viewer__file">
            <div class="sem-viewer__label">Fichier sur le partage</div>
            <p class="mono js-file"></p>
            <button type="button" class="btn btn-line js-copy">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg><span class="js-copy-label">Copier le chemin</span>
            </button>
          </div>
        </aside>
      </div>`;
    document.body.appendChild(dialog);

    el(".js-close").addEventListener("click", () => dialog.close());
    el(".js-prev").addEventListener("click", () => step(-1));
    el(".js-next").addEventListener("click", () => step(1));
    el(".js-zoom-in").addEventListener("click", () => zoomAt(1.5));
    el(".js-zoom-out").addEventListener("click", () => zoomAt(1 / 1.5));
    el(".js-zoom-reset").addEventListener("click", resetView);
    el(".js-copy").addEventListener("click", copyPath);
    el(".js-img").addEventListener("load", () => {
      el(".js-loading").hidden = true;
      el(".js-img").classList.remove("is-loading");
      renderScale();
    });
    el(".js-img").addEventListener("error", () => {
      el(".js-loading").hidden = false;
      el(".js-loading").textContent = "Image illisible : le fichier a peut-être été déplacé.";
    });
    dialog.addEventListener("keydown", onKey);
    dialog.addEventListener("close", () => {
      ctx = null;
      el(".js-img").removeAttribute("src");
    });

    const stage = el(".js-stage");
    stage.addEventListener("wheel", (event) => {
      event.preventDefault();
      zoomAt(event.deltaY < 0 ? 1.25 : 1 / 1.25, event);
    }, { passive: false });
    stage.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || event.target.closest("button")) return;
      drag = { x: event.clientX - view.x, y: event.clientY - view.y };
      stage.setPointerCapture(event.pointerId);
      stage.classList.add("is-dragging");
    });
    stage.addEventListener("pointermove", (event) => {
      if (!drag) return;
      view.x = event.clientX - drag.x;
      view.y = event.clientY - drag.y;
      applyView();
    });
    const endDrag = () => {
      drag = null;
      stage.classList.remove("is-dragging");
    };
    stage.addEventListener("pointerup", endDrag);
    stage.addEventListener("pointercancel", endDrag);
    stage.addEventListener("dblclick", (event) => (view.scale > 1 ? resetView() : zoomAt(2.5, event)));
    window.addEventListener("resize", () => dialog.open && renderScale());
  }

  function onKey(event) {
    if (event.target.closest("input, textarea")) return;
    const keys = { ArrowLeft: () => step(-1), ArrowRight: () => step(1), "+": () => zoomAt(1.5), "=": () => zoomAt(1.5), "-": () => zoomAt(1 / 1.5), 0: resetView };
    const action = keys[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  }

  function applyView() {
    el(".js-img").style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
    el(".js-zoom-reset").textContent = `${Math.round(view.scale * 100)} %`;
    renderScale();
  }

  function resetView() {
    view = { ...view, scale: 1, x: 0, y: 0 };
    applyView();
  }

  // zoome d'un facteur autour du pointeur (ou du centre) : le point visé reste sous le pointeur
  function zoomAt(factor, event) {
    const stage = el(".js-stage").getBoundingClientRect();
    const next = Math.min(16, Math.max(1, view.scale * factor));
    const k = next / view.scale;
    const px = event && event.clientX !== undefined ? event.clientX - stage.left - stage.width / 2 : 0;
    const py = event && event.clientY !== undefined ? event.clientY - stage.top - stage.height / 2 : 0;
    view.x = px - (px - view.x) * k;
    view.y = py - (py - view.y) * k;
    view.scale = next;
    if (next === 1) view.x = view.y = 0;
    applyView();
  }

  // une barre de longueur « ronde » (1, 2, 5 x 10^n µm) d'environ un cinquième de la largeur affichée
  function renderScale() {
    const box = el(".js-scale");
    const img = el(".js-img");
    if (!meta || !meta.fov_um || !img.naturalWidth || !img.clientWidth) {
      box.hidden = true;
      return;
    }
    // l'image est « contenue » dans la boîte : sa largeur affichée est celle de la boîte ou celle que sa hauteur permet
    const shown = Math.min(img.clientWidth, (img.clientHeight * img.naturalWidth) / img.naturalHeight);
    const pxPerUm = (shown * view.scale) / meta.fov_um[0];
    const target = el(".js-stage").clientWidth / 5 / pxPerUm;
    const power = 10 ** Math.floor(Math.log10(target));
    const nice = [1, 2, 5, 10].map((m) => m * power).filter((v) => v <= target).pop() || power;
    el(".js-scale-bar").style.width = `${Math.round(nice * pxPerUm)}px`;
    el(".js-scale-label").textContent = nice >= 1 ? `${nice} µm` : `${Math.round(nice * 1000)} nm`;
    box.hidden = false;
  }

  function fact(label, value) {
    return value === null || value === undefined || value === "" ? "" : `<div><dt>${escapeHtml(label)}</dt><dd>${value}</dd></div>`;
  }

  function mm(value) {
    return (value / 1000).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function renderFacts() {
    const image = ctx.images[ctx.index];
    const g = ctx.group;
    const m = meta || {};
    const pixel = m.pixel_um ? (m.pixel_um >= 1 ? `${m.pixel_um.toFixed(2)} µm` : `${Math.round(m.pixel_um * 1000)} nm`) : "";
    el(".js-facts").innerHTML = [
      fact("Défaut revu", m.defect_id ? `n° ${escapeHtml(m.defect_id)}${m.defect_class ? ` · ${escapeHtml(m.defect_class)}` : ""}` : ""),
      fact("Position sur la plaque", m.location_um ? `<span class="mono">x ${mm(m.location_um[0])} · y ${mm(m.location_um[1])} mm</span>` : ""),
      fact("Die", m.die_index ? `<span class="mono">${escapeHtml(m.die_index)}</span>` : ""),
      fact("Champ de vue", m.fov_um ? `<span class="mono">${m.fov_um[0]} × ${m.fov_um[1]} µm</span> <span class="sem-viewer__hint">(${m.width} px, ${pixel} / px)</span>` : ""),
      fact("Tension · inclinaison", m.kv ? `<span class="mono">${m.kv} kV · ${m.tilt ?? 0}°</span>` : ""),
      fact("Acquise le", m.acquired ? semDate(m.acquired) : semDate(image.modified)),
      fact("Étape", `<span class="mono">${escapeHtml(g.step || "—")}</span>${g.process ? ` <span class="sem-viewer__hint">procédé ${escapeHtml(g.process)}</span>` : ""}`),
      fact("FDL · lot", `<span class="mono">${escapeHtml(g.fdl || g.lot || "—")}</span>`),
    ].join("");
    el(".js-file").textContent = m.file || `${image.path}`;
  }

  function renderFrames() {
    const frames = (meta && meta.frames) || 1;
    const box = el(".js-frames");
    box.hidden = frames < 2;
    box.innerHTML = frames < 2 ? "" : Array.from({ length: frames }, (_, i) => `<button type="button" class="sem-viewer__tool sem-viewer__tool--text${i === view.frame ? " active" : ""}" data-frame="${i}" aria-pressed="${i === view.frame}" title="Détecteur ${i + 1}">D${i + 1}</button>`).join("");
    box.querySelectorAll("[data-frame]").forEach((button) =>
      button.addEventListener("click", () => {
        view.frame = Number(button.dataset.frame);
        renderFrames();
        loadImage();
      })
    );
  }

  function loadImage() {
    const image = ctx.images[ctx.index];
    const img = el(".js-img");
    el(".js-loading").hidden = false;
    el(".js-loading").textContent = "Chargement…";
    img.classList.add("is-loading");
    img.alt = `Image MEB ${semImageLabel(image)} de ${ctx.lasermark}`;
    img.src = semImagesApi.fileUrl(ctx.lasermark, image.path, { variant: "view", frame: view.frame, fdl: ctx.fdl });
  }

  async function show(index) {
    ctx.index = (index + ctx.images.length) % ctx.images.length;
    const image = ctx.images[ctx.index];
    const mine = ++token;
    meta = null;
    view = { scale: 1, x: 0, y: 0, frame: view.frame };
    el(".js-sub").textContent = [ctx.group.step, ctx.group.fdl ? `FDL ${ctx.group.fdl}` : ctx.group.lot].filter(Boolean).join(" · ");
    el("#sem-viewer-title").textContent = image.die !== null && image.die !== undefined ? `Die ${image.die}${image.round ? `, passe ${image.round}` : ""}` : image.name;
    el(".js-count").textContent = `${ctx.index + 1} / ${ctx.images.length} · ${ctx.lasermark}`;
    el(".js-prev").hidden = el(".js-next").hidden = ctx.images.length < 2;
    applyView();
    renderFacts();
    loadImage();
    try {
      const fresh = await semImagesApi.meta(ctx.lasermark, image.path, { fdl: ctx.fdl });
      if (mine !== token) return;
      meta = fresh;
      if (view.frame >= (meta.frames || 1)) {
        view.frame = 0;
        loadImage();
      }
      renderFacts();
      renderFrames();
      renderScale();
    } catch (err) {
      if (mine === token) el(".js-facts").insertAdjacentHTML("beforeend", `<div class="sem-viewer__hint">Métadonnées illisibles : ${escapeHtml(err.message)}</div>`);
    }
  }

  function step(delta) {
    if (ctx && ctx.images.length > 1) show(ctx.index + delta);
  }

  async function copyPath() {
    const text = el(".js-file").textContent;
    const label = el(".js-copy-label");
    try {
      await navigator.clipboard.writeText(text);
      label.textContent = "Chemin copié";
    } catch (err) {
      label.textContent = "Copie impossible";
    }
    setTimeout(() => (label.textContent = "Copier le chemin"), 1600);
  }

  function open({ lasermark, fdl, group, images, index }) {
    if (!dialog) build();
    ctx = { lasermark, fdl, group, images, index };
    view.frame = 0;
    if (!dialog.open) dialog.showModal();
    show(index);
    el(".js-stage").focus({ preventScroll: true });
  }

  return { open };
})();

const PlateSem = (() => {
  const POLL_MS = 8000;

  function mount(section, lasermark) {
    const state = { lasermark, data: null, extra: [], open: new Set(), round: {}, poll: null, busy: false };
    section.hidden = false;
    section.innerHTML = `
      <div class="plate-life__head">
        <h2 class="section-title" id="plate-sem-title">Images MEB - G4</h2>
        <span class="sem-meta js-sem-meta"></span>
        <button type="button" class="btn btn-line sem-refresh js-sem-refresh" title="Relire le partage des images MEB maintenant">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/></svg>Relire
        </button>
      </div>
      <div class="js-sem-body"><div class="skeleton" style="height:120px;"></div></div>`;
    section.querySelector(".js-sem-refresh").addEventListener("click", () => load(state, section, { refresh: true }));
    // une vignette arrivée arrête son reflet d'attente
    section.addEventListener("load", (event) => event.target.closest && event.target.closest(".sem-thumb") && event.target.classList.add("is-loaded"), true);
    load(state, section);
    return {
      // la vie en ligne vient de lire ses FDL : une FDL qu'on n'avait pas cherchée relance la recherche
      fdlsChanged(fdls) {
        if (!state.data || state.busy) return;
        const searched = new Set((state.data.fdls || []).map((f) => f.toUpperCase()));
        if ((fdls || []).some((f) => f && !searched.has(String(f).toUpperCase()))) load(state, section);
      },
    };
  }

  async function load(state, section, { refresh = false } = {}) {
    const button = section.querySelector(".js-sem-refresh");
    state.busy = true;
    button.classList.add("is-busy");
    button.disabled = true;
    try {
      state.data = await semImagesApi.list(state.lasermark, { fdl: state.extra, refresh });
      if (state.data.groups.length && !state.open.size) state.open.add(state.data.groups[0].folder);
      render(state, section);
    } catch (err) {
      section.querySelector(".js-sem-meta").textContent = "";
      section.querySelector(".js-sem-body").innerHTML = `<div class="plate-banner plate-banner--bad">${escapeHtml(err.message)}</div>`;
    } finally {
      state.busy = false;
      button.classList.remove("is-busy");
      button.disabled = false;
    }
    schedulePoll(state, section);
  }

  // l'index se construit : on revient voir, puis on relit la plaque quand il est prêt
  function schedulePoll(state, section) {
    clearTimeout(state.poll);
    const index = state.data && state.data.index;
    if (!index || !(index.building || index.updating) || state.data.count) return;
    state.poll = setTimeout(async () => {
      if (!section.isConnected) return;
      try {
        const now = await semImagesApi.index();
        if (now.building || now.updating) {
          state.data.index = now;
          render(state, section);
          schedulePoll(state, section);
        } else {
          load(state, section, { refresh: true });
        }
      } catch (err) {
        /* on réessaiera à la prochaine visite */
      }
    }, POLL_MS);
  }

  function indexText(index) {
    if (!index) return "";
    if (index.building) return "L'index des dossiers du partage se construit (environ 2 minutes) : la recherche reprendra d'elle-même.";
    if (index.error) return `L'index des dossiers n'a pas pu être lu : ${index.error}`;
    if (!index.exists) return "Le partage n'a pas encore d'index des dossiers : seules les FDL connues sont cherchées.";
    return `Index du partage : ${Number(index.wafers || 0).toLocaleString("fr-FR")} plaques, mis à jour ${timeAgo(index.checked_at)}.`;
  }

  function render(state, section) {
    const data = state.data;
    const n = data.count;
    const fdlText = data.fdls.length ? `FDL ${data.fdls.slice(0, 3).join(", ")}${data.fdls.length > 3 ? ` +${data.fdls.length - 3}` : ""}` : "aucune FDL connue";
    section.querySelector(".js-sem-meta").innerHTML = n
      ? `${n} image${n > 1 ? "s" : ""} · ${data.groups.length} acquisition${data.groups.length > 1 ? "s" : ""} · <span title="${escapeHtml(indexText(data.index))}">${escapeHtml(fdlText)}${data.index && data.index.exists ? " + index du partage" : ""}</span>`
      : "";
    const body = section.querySelector(".js-sem-body");
    if (!n) {
      body.innerHTML = emptyHtml(data);
      wireSearch(state, section, body);
      return;
    }
    body.innerHTML = `${data.groups.map((g) => groupHtml(state, g)).join("")}${searchHtml(true)}`;
    wireSearch(state, section, body);
    body.querySelectorAll("[data-toggle]").forEach((button) =>
      button.addEventListener("click", () => {
        const folder = button.dataset.toggle;
        state.open.has(folder) ? state.open.delete(folder) : state.open.add(folder);
        render(state, section);
      })
    );
    body.querySelectorAll("[data-round]").forEach((button) =>
      button.addEventListener("click", () => {
        state.round[button.dataset.folder] = button.dataset.round === "" ? null : Number(button.dataset.round);
        render(state, section);
      })
    );
    body.querySelectorAll("[data-image]").forEach((button) =>
      button.addEventListener("click", () => {
        const group = data.groups.find((g) => g.folder === button.dataset.folder);
        const images = visibleImages(state, group);
        SemViewer.open({ lasermark: state.lasermark, fdl: state.extra, group, images, index: Number(button.dataset.image) });
      })
    );
  }

  function visibleImages(state, group) {
    const round = state.round[group.folder];
    return round === null || round === undefined ? group.images : group.images.filter((i) => i.round === round);
  }

  function groupHtml(state, g) {
    const open = state.open.has(g.folder);
    const round = state.round[g.folder];
    const images = visibleImages(state, g);
    const rounds = g.rounds.length > 1
      ? `<div class="view-toggle sem-group__rounds" role="group" aria-label="Passe">
          ${[null, ...g.rounds].map((r) => `<button type="button" class="view-toggle__btn${(round ?? null) === r ? " active" : ""}" data-folder="${escapeHtml(g.folder)}" data-round="${r ?? ""}" aria-pressed="${(round ?? null) === r}">${r === null ? "Toutes" : `r${r}`}</button>`).join("")}
        </div>`
      : "";
    const dates = g.first && g.last && g.first.slice(0, 10) !== g.last.slice(0, 10) ? `${semDate(g.first, false)} → ${semDate(g.last, false)}` : semDate(g.last, false);
    return `
      <article class="card sem-group${open ? " is-open" : ""}">
        <div class="sem-group__head">
          <button type="button" class="sem-group__toggle" data-toggle="${escapeHtml(g.folder)}" aria-expanded="${open}">
            <svg class="sem-group__chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>
            <span class="sem-group__step">${escapeHtml(g.step || g.folder)}</span>
            ${g.fdl ? `<span class="plate-tag" title="FDL du dossier de lot">FDL ${escapeHtml(g.fdl)}</span>` : g.lot ? `<span class="plate-tag plate-tag--mute" title="Lot (sans FDL reconnue)">${escapeHtml(g.lot)}</span>` : ""}
            ${g.process ? `<span class="plate-tag plate-tag--mute" title="Procédé">${escapeHtml(g.process)}</span>` : ""}
            <span class="sem-group__facts">${dates} · ${g.count} image${g.count > 1 ? "s" : ""}</span>
          </button>
          <span class="sem-group__area" title="${escapeHtml(g.folder)}">${escapeHtml(g.area_label || "")}</span>
          ${rounds}
        </div>
        ${open ? `<div class="sem-grid">${images.map((image, i) => thumbHtml(state, g, image, i)).join("")}</div>` : ""}
      </article>`;
  }

  function thumbHtml(state, g, image, i) {
    const label = semImageLabel(image);
    return `
      <button type="button" class="sem-thumb" data-folder="${escapeHtml(g.folder)}" data-image="${i}" title="${escapeHtml(image.name)}">
        <img src="${escapeHtml(semImagesApi.fileUrl(state.lasermark, image.path, { fdl: state.extra }))}" alt="${escapeHtml(`Image MEB ${label}`)}" loading="lazy" decoding="async" width="160" height="160">
        <span class="sem-thumb__label mono">${escapeHtml(label)}</span>
      </button>`;
  }

  function emptyHtml(data) {
    const where = data.fdls.length
      ? `Cherchées dans les dossiers des FDL <span class="mono">${data.fdls.map(escapeHtml).join(", ")}</span>${data.index && data.index.exists ? " et dans l'index du partage" : ""}.`
      : "Spectre ne lui connaît aucune FDL (sa vie en ligne n'a pas encore été lue ?).";
    return `
      <div class="card card-pad sem-empty">
        <p class="sem-empty__title">Aucune image du G4 trouvée pour cette plaque.</p>
        <p class="help">${where}</p>
        <p class="help${data.index && data.index.building ? " sem-empty__building" : ""}">${escapeHtml(indexText(data.index))}</p>
        ${searchHtml(false)}
      </div>`;
  }

  function searchHtml(compact) {
    return `
      <form class="sem-search${compact ? " sem-search--compact" : ""} js-sem-search">
        <label for="sem-fdl-input">${compact ? "Une autre FDL ?" : "Chercher avec une FDL"}</label>
        <input id="sem-fdl-input" class="mono js-sem-fdl" type="text" inputmode="numeric" placeholder="2026-41155" pattern="\\s*\\d{4}-\\d{5}.*" autocomplete="off" required>
        <button type="submit" class="btn btn-line">Chercher</button>
      </form>`;
  }

  function wireSearch(state, section, body) {
    const form = body.querySelector(".js-sem-search");
    if (!form) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const value = form.querySelector(".js-sem-fdl").value.trim();
      if (!value) return;
      if (!state.extra.includes(value)) state.extra.push(value);
      state.open.clear();
      load(state, section);
    });
  }

  return { mount };
})();
