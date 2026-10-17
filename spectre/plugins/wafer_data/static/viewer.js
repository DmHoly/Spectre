/* La visionneuse d'images de la fiche data (spectre.plugins.wafer_data) : une galerie s'ouvre en grand dans un
   <dialog> - l'image à la taille de la fenêtre (un clic : taille réelle, qu'on fait défiler ; un autre : ajustée),
   sa légende (nom du fichier + les colonnes choisies : device, numéro d'image...), précédente / suivante, une
   bande de vignettes, et les groupes (type d'image : LightImage, LIVSweepImages...) pour n'en parcourir qu'un.
   Clavier : ← → (précédente, suivante), Début / Fin, Z (taille réelle), Échap (fermer).

   WaferDataViewer.open({title, images: [{url, name, meta, g}], groups, index}) */

const WaferDataViewer = (() => {
  let dialog = null;
  let state = null;

  const icon = (path, size = 18) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
  const PREV = '<path d="m15 18-6-6 6-6"/>';
  const NEXT = '<path d="m9 18 6-6-6-6"/>';
  const CLOSE = '<path d="M18 6 6 18M6 6l12 12"/>';
  const ZOOM = '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3M11 8v6M8 11h6"/>';
  const OPEN = '<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>';

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "wd-viewer";
    dialog.setAttribute("aria-label", "Visionneuse d'images");
    dialog.innerHTML = `<div class="wd-viewer__bar">
        <div class="wd-viewer__title"><span class="js-title"></span> <span class="wd-viewer__count js-count" aria-live="polite"></span></div>
        <div class="wd-viewer__groups js-groups" role="group" aria-label="Groupes d'images"></div>
        <button type="button" class="wd-viewer__btn js-zoom" aria-pressed="false" title="Taille réelle (Z)">${icon(ZOOM)}<span class="visually-hidden">Taille réelle</span></button>
        <a class="wd-viewer__btn js-open" target="_blank" rel="noopener" title="Ouvrir l'original dans un onglet">${icon(OPEN)}<span class="visually-hidden">Ouvrir l'original</span></a>
        <button type="button" class="wd-viewer__btn js-close" title="Fermer (Échap)">${icon(CLOSE)}<span class="visually-hidden">Fermer</span></button>
      </div>
      <div class="wd-viewer__stage">
        <button type="button" class="wd-viewer__nav wd-viewer__nav--prev js-prev" aria-label="Image précédente">${icon(PREV, 26)}</button>
        <div class="wd-viewer__frame js-frame"><img class="js-img" alt=""></div>
        <button type="button" class="wd-viewer__nav wd-viewer__nav--next js-next" aria-label="Image suivante">${icon(NEXT, 26)}</button>
      </div>
      <div class="wd-viewer__caption js-caption"></div>
      <div class="wd-viewer__strip js-strip" role="listbox" aria-label="Vignettes"></div>`;
    document.body.appendChild(dialog);
    dialog.querySelector(".js-close").addEventListener("click", () => dialog.close());
    dialog.querySelector(".js-prev").addEventListener("click", () => step(-1));
    dialog.querySelector(".js-next").addEventListener("click", () => step(1));
    dialog.querySelector(".js-zoom").addEventListener("click", toggleZoom);
    dialog.querySelector(".js-img").addEventListener("click", toggleZoom);
    dialog.querySelector(".js-strip").addEventListener("click", (event) => {
      const thumb = event.target.closest("[data-at]");
      if (thumb) show(Number(thumb.dataset.at));
    });
    dialog.querySelector(".js-groups").addEventListener("click", (event) => {
      const chip = event.target.closest("[data-group]");
      if (!chip) return;
      state.group = chip.dataset.group === "" ? null : Number(chip.dataset.group);
      renderStrip();
      show(visible()[0]);
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close(); // un clic sur le fond
    });
    dialog.addEventListener("keydown", (event) => {
      if (event.target.closest("input, select, textarea")) return;
      const keys = { ArrowLeft: () => step(-1), ArrowRight: () => step(1), Home: () => show(visible()[0]), End: () => show(visible().at(-1)), z: toggleZoom, Z: toggleZoom };
      if (keys[event.key]) {
        keys[event.key]();
        event.preventDefault();
      }
    });
  }

  // les indices des images montrées (celles du groupe choisi, ou toutes)
  const visible = () => state.images.map((_, i) => i).filter((i) => state.group === null || state.images[i].g === state.group);

  function step(delta) {
    const list = visible();
    const at = list.indexOf(state.index);
    show(list[(at + delta + list.length) % list.length]);
  }

  function toggleZoom() {
    const frame = dialog.querySelector(".js-frame");
    const on = !frame.classList.contains("is-actual");
    frame.classList.toggle("is-actual", on);
    dialog.querySelector(".js-zoom").setAttribute("aria-pressed", String(on));
  }

  function captionHtml(image) {
    const meta = Object.entries(image.meta || {})
      .map(([k, v]) => `<span class="wd-viewer__meta"><span>${escapeHtml(k)}</span>${escapeHtml(v)}</span>`)
      .join("");
    const group = state.groups.length ? `<span class="wd-viewer__meta"><span>groupe</span>${escapeHtml(state.groups[image.g])}</span>` : "";
    return `<span class="mono wd-viewer__name">${escapeHtml(image.name)}</span>${group}${meta}`;
  }

  function show(index) {
    if (index === undefined) return;
    state.index = index;
    const image = state.images[index];
    const img = dialog.querySelector(".js-img");
    img.src = image.url;
    img.alt = image.name;
    dialog.querySelector(".js-open").href = image.url;
    dialog.querySelector(".js-caption").innerHTML = captionHtml(image);
    const list = visible();
    dialog.querySelector(".js-count").textContent = `${list.indexOf(index) + 1} / ${list.length}`;
    const single = list.length < 2;
    dialog.querySelector(".js-prev").hidden = single;
    dialog.querySelector(".js-next").hidden = single;
    dialog.querySelectorAll(".js-strip [data-at]").forEach((thumb) => {
      const on = Number(thumb.dataset.at) === index;
      thumb.setAttribute("aria-selected", String(on));
      if (on) thumb.scrollIntoView({ block: "nearest", inline: "nearest" });
    });
  }

  function renderStrip() {
    dialog.querySelector(".js-strip").innerHTML = visible()
      .map((i) => `<button type="button" class="wd-viewer__thumb" role="option" data-at="${i}" aria-selected="false" title="${escapeHtml(state.images[i].name)}"><img src="${escapeHtml(state.images[i].url)}" alt="" loading="lazy"></button>`)
      .join("");
    dialog.querySelector(".js-groups").innerHTML = state.groups.length
      ? [["", "Tous", state.images.length], ...state.groups.map((g, i) => [String(i), g, state.images.filter((im) => im.g === i).length])]
          .filter(([, , n]) => n)
          .map(([key, name, n]) => {
            const on = (key === "" && state.group === null) || Number(key) === state.group;
            return `<button type="button" class="wd-viewer__chip" data-group="${key}" aria-pressed="${on}">${escapeHtml(name)} <span>${n}</span></button>`;
          })
          .join("")
      : "";
  }

  function open({ title = "", images = [], groups = [], index = 0, group = null }) {
    if (!images.length) return;
    if (!dialog) build();
    state = { images, groups: groups || [], index, group };
    dialog.querySelector(".js-title").textContent = title;
    dialog.querySelector(".js-frame").classList.remove("is-actual");
    dialog.querySelector(".js-zoom").setAttribute("aria-pressed", "false");
    renderStrip();
    dialog.showModal();
    show(index);
    dialog.querySelector(".js-next").focus();
  }

  return { open };
})();
