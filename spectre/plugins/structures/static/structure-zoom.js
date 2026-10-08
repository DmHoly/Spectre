/* Une structure en grand, qu'on zoome pour en lire les détails : le dessin d'une version (étiquettes
   de couches comprises), chaque variante d'une campagne, ou les images d'une structure en images
   (annotations comprises). Une seule boîte, créée au premier usage et partagée par toute la page.

   - openStructureZoom({title, items, index, onClose}) : `items` = [{html, caption, badge}] - le
     balisage à montrer (un <svg>, ou une image dans son `.annot-frame`), une légende et une
     pastille facultatives (« RÉF ») ; `index` l'élément ouvert d'abord ; `onClose(index)` reçoit
     celui où l'on s'est arrêté (le carrousel d'où l'on vient s'y cale et reprend le focus).
   - STRUCTURE_ZOOM_BADGE : la loupe posée dans le coin d'un aperçu cliquable, pour dire qu'il
     s'agrandit (`position: relative` sur l'aperçu).

   À l'ouverture, la structure est ajustée à la fenêtre. Molette (ou pincement) : zoom autour du
   point visé ; glisser : se déplacer ; double-clic : zoom ×2 à cet endroit ; + − 0 au clavier
   (0 = ajuster), ← → d'un élément à l'autre, Échap ferme. Le contenu est redimensionné (pas mis à
   l'échelle par une transformation) : un SVG reste net à tout zoom.

   Le calcul de la vue (zoomFit, zoomAt, zoomClamp) est pur, sans DOM : voir
   tests_js/structure-zoom.test.js. */

const STRUCTURE_ZOOM_BADGE = `<span class="structure-zoomable__badge" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/><path d="M11 8v6M8 11h6"/></svg></span>`;

const STRUCTURE_ZOOM = {
  min: 0.5, // × l'ajustement à la fenêtre
  max: 16,
  step: 1.4, // un clic sur + ou −
  pad: 24, // marge autour de la structure ajustée (px)
};

// La vue ajustée : la structure (w × h, ses proportions) centrée dans le cadre (vw × vh), marges
// comprises. `k` = pixels affichés par unité de la structure.
function zoomFit(w, h, vw, vh, pad = STRUCTURE_ZOOM.pad) {
  const k = Math.max(1e-6, Math.min((vw - 2 * pad) / w, (vh - 2 * pad) / h));
  return { k, x: (vw - w * k) / 2, y: (vh - h * k) / 2 };
}

// Zoomer jusqu'à `k` en gardant fixe le point du cadre (px, py) : ce qui est sous le curseur y reste.
function zoomAt(view, k, px, py) {
  const ratio = k / view.k;
  return { k, x: px - (px - view.x) * ratio, y: py - (py - view.y) * ratio };
}

// La structure ne s'échappe pas du cadre : centrée sur un axe où elle tient, sinon ses bords ne
// décollent pas des bords du cadre de plus que la marge.
function zoomClamp(view, w, h, vw, vh, pad = STRUCTURE_ZOOM.pad) {
  const axis = (pos, size, frame) => (size <= frame ? (frame - size) / 2 : Math.min(pad, Math.max(frame - size - pad, pos)));
  return { k: view.k, x: axis(view.x, w * view.k, vw), y: axis(view.y, h * view.k, vh) };
}

const openStructureZoom = (() => {
  const ICON = (d) =>
    `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  let dialog = null;
  let el = {}; // les éléments de la boîte
  let items = [];
  let index = 0;
  let onClose = null;
  let size = null; // {w, h} : les proportions de la structure montrée (null tant qu'une image charge)
  let fitK = 1;
  let view = { k: 1, x: 0, y: 0 };
  let frame = null; // requestAnimationFrame en attente

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "sz-dialog";
    dialog.setAttribute("aria-labelledby", "sz-title");
    dialog.innerHTML = `
      <div class="sz-head">
        <div class="sz-head__text">
          <h2 class="sz-title" id="sz-title"></h2>
          <div class="sz-caption"></div>
        </div>
        <div class="sz-tools">
          <div class="sz-zoom" role="group" aria-label="Zoom">
            <button class="sz-iconbtn" type="button" data-zoom="out" aria-label="Zoom arrière" title="Zoom arrière (−)">${ICON('<path d="M5 12h14"/>')}</button>
            <button class="sz-level" type="button" data-zoom="fit" title="Ajuster à la fenêtre (0)">Ajusté</button>
            <button class="sz-iconbtn" type="button" data-zoom="in" aria-label="Zoom avant" title="Zoom avant (+)">${ICON('<path d="M12 5v14M5 12h14"/>')}</button>
          </div>
          <button class="btn btn-line sz-close" type="button">Fermer</button>
        </div>
      </div>
      <div class="sz-viewport" tabindex="-1" aria-describedby="sz-hint">
        <div class="sz-content"></div>
      </div>
      <div class="sz-foot">
        <p class="sz-hint" id="sz-hint">Molette : zoomer · glisser : se déplacer · double-clic : zoomer ici · 0 : ajuster</p>
        <div class="sz-nav">
          <button class="sz-iconbtn" type="button" data-dir="-1" aria-label="Précédente" title="Précédente (←)">${ICON('<path d="m15 18-6-6 6-6"/>')}</button>
          <span class="sz-count"></span>
          <button class="sz-iconbtn" type="button" data-dir="1" aria-label="Suivante" title="Suivante (→)">${ICON('<path d="m9 18 6-6-6-6"/>')}</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    el = {
      title: dialog.querySelector(".sz-title"),
      caption: dialog.querySelector(".sz-caption"),
      level: dialog.querySelector(".sz-level"),
      viewport: dialog.querySelector(".sz-viewport"),
      content: dialog.querySelector(".sz-content"),
      nav: dialog.querySelector(".sz-nav"),
      count: dialog.querySelector(".sz-count"),
    };

    dialog.querySelector(".sz-close").addEventListener("click", () => dialog.close());
    // un clic sur le voile (hors de la boîte) ferme aussi
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener("close", () => {
      const done = onClose;
      el.content.innerHTML = "";
      items = [];
      onClose = null;
      if (done) done(index);
    });
    dialog.querySelector(".sz-zoom").addEventListener("click", (event) => {
      const button = event.target.closest("[data-zoom]");
      if (!button) return;
      if (button.dataset.zoom === "fit") fit();
      else zoomBy(button.dataset.zoom === "in" ? STRUCTURE_ZOOM.step : 1 / STRUCTURE_ZOOM.step);
    });
    el.nav.addEventListener("click", (event) => {
      const button = event.target.closest("[data-dir]");
      if (button) show(index + parseInt(button.dataset.dir, 10));
    });
    dialog.addEventListener("keydown", (event) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (event.key === "+" || event.key === "=") zoomBy(STRUCTURE_ZOOM.step);
      else if (event.key === "-" || event.key === "_") zoomBy(1 / STRUCTURE_ZOOM.step);
      else if (event.key === "0") fit();
      else if ((event.key === "ArrowLeft" || event.key === "ArrowRight") && items.length > 1) show(index + (event.key === "ArrowLeft" ? -1 : 1));
      else return;
      event.preventDefault();
    });

    const viewport = el.viewport;
    viewport.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        const lines = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? viewport.clientHeight : 1;
        const [px, py] = local(event);
        setK(view.k * Math.exp(-event.deltaY * lines * 0.0015), px, py);
      },
      { passive: false }
    );
    viewport.addEventListener("dblclick", (event) => {
      const [px, py] = local(event);
      setK(view.k * 2, px, py);
    });

    // glisser (un doigt ou la souris) pour se déplacer, pincer (deux doigts) pour zoomer
    const pointers = new Map();
    viewport.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "mouse" && event.button !== 0) return;
      event.preventDefault(); // ni sélection de texte, ni glisser-déposer natif d'une image
      viewport.focus({ preventScroll: true });
      viewport.setPointerCapture(event.pointerId);
      pointers.set(event.pointerId, local(event));
      viewport.classList.add("is-panning");
    });
    viewport.addEventListener("pointermove", (event) => {
      if (!pointers.has(event.pointerId) || !size) return;
      const before = [...pointers.values()];
      pointers.set(event.pointerId, local(event));
      const after = [...pointers.values()];
      if (after.length === 1) {
        view = { k: view.k, x: view.x + after[0][0] - before[0][0], y: view.y + after[0][1] - before[0][1] };
        render();
      } else if (after.length === 2) {
        const mid = (p) => [(p[0][0] + p[1][0]) / 2, (p[0][1] + p[1][1]) / 2];
        const dist = (p) => Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]) || 1;
        const [mx, my] = mid(before);
        const [nx, ny] = mid(after);
        setK(view.k * (dist(after) / dist(before)), mx, my, { x: nx - mx, y: ny - my });
      }
    });
    const release = (event) => {
      pointers.delete(event.pointerId);
      if (!pointers.size) viewport.classList.remove("is-panning");
    };
    viewport.addEventListener("pointerup", release);
    viewport.addEventListener("pointercancel", release);

    // la fenêtre redimensionnée : toujours ajustée si on l'était, sinon la vue gardée dans le cadre
    new ResizeObserver(() => {
      if (!dialog.open || !size) return;
      const atFit = Math.abs(view.k / fitK - 1) < 0.01;
      fitK = zoomFit(size.w, size.h, viewport.clientWidth, viewport.clientHeight).k;
      if (atFit) fit();
      else render();
    }).observe(viewport);
  }

  // Un point d'un événement, dans le repère du cadre.
  function local(event) {
    const rect = el.viewport.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  }

  function frameSize() {
    return [el.viewport.clientWidth, el.viewport.clientHeight];
  }

  function setK(k, px, py, pan = { x: 0, y: 0 }) {
    if (!size) return;
    const bounded = Math.min(fitK * STRUCTURE_ZOOM.max, Math.max(fitK * STRUCTURE_ZOOM.min, k));
    const next = zoomAt(view, bounded, px, py);
    view = { k: bounded, x: next.x + pan.x, y: next.y + pan.y };
    render();
  }

  function zoomBy(factor) {
    const [vw, vh] = frameSize();
    setK(view.k * factor, vw / 2, vh / 2);
  }

  function fit() {
    if (!size) return;
    const [vw, vh] = frameSize();
    view = zoomFit(size.w, size.h, vw, vh);
    fitK = view.k;
    render();
  }

  function render() {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = null;
      if (!size) return;
      const [vw, vh] = frameSize();
      view = zoomClamp(view, size.w, size.h, vw, vh);
      const style = el.content.style;
      style.width = `${size.w * view.k}px`;
      style.height = `${size.h * view.k}px`;
      style.transform = `translate(${view.x}px, ${view.y}px)`;
      const ratio = view.k / fitK;
      el.level.textContent = Math.abs(ratio - 1) < 0.01 ? "Ajusté" : `${Math.round(ratio * 100)} %`;
    });
  }

  // Les proportions de la structure montrée : la viewBox d'un SVG (ses width/height à défaut), la
  // taille réelle d'une image une fois chargée.
  function measure(node, done) {
    if (node instanceof SVGSVGElement) {
      const box = node.viewBox && node.viewBox.baseVal;
      if (box && box.width > 0 && box.height > 0) return done({ w: box.width, h: box.height });
      const w = parseFloat(node.getAttribute("width"));
      const h = parseFloat(node.getAttribute("height"));
      return done(w > 0 && h > 0 ? { w, h } : { w: 4, h: 3 });
    }
    const img = node && (node.tagName === "IMG" ? node : node.querySelector("img"));
    if (!img) return done({ w: 4, h: 3 });
    const ready = () => done(img.naturalWidth ? { w: img.naturalWidth, h: img.naturalHeight } : { w: 4, h: 3 });
    if (img.complete) return ready();
    img.addEventListener("load", ready, { once: true });
    img.addEventListener("error", ready, { once: true });
  }

  function show(next) {
    if (!items.length) return;
    index = (next + items.length) % items.length;
    const item = items[index];
    size = null;
    el.content.style.visibility = "hidden";
    el.content.innerHTML = item.html || "";
    el.caption.innerHTML = `${item.badge ? `<span class="badge badge-role">${escapeHtml(item.badge)}</span>` : ""}${item.caption ? `<span>${escapeHtml(item.caption)}</span>` : ""}`;
    el.caption.hidden = !item.badge && !item.caption;
    el.nav.hidden = items.length < 2;
    el.count.textContent = `${index + 1} / ${items.length}`;
    const shown = index;
    measure(el.content.firstElementChild, (measured) => {
      if (shown !== index || !dialog.open) return; // déjà passé à un autre élément
      size = measured;
      el.content.style.visibility = "";
      fit();
    });
  }

  return function openStructureZoom({ title = "Structure", items: list = [], index: start = 0, onClose: done = null } = {}) {
    if (!list.length) return;
    if (!dialog) build();
    el.title.textContent = title;
    items = list;
    onClose = done;
    if (!dialog.open) dialog.showModal();
    show(start);
    el.viewport.focus({ preventScroll: true });
  };
})();
