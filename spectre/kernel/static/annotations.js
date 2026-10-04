/* Les annotations d'une image : des flèches et des cadres, chacun avec un libellé facultatif, posés
   sur toute image que Spectre montre (une image du cahier, téléversée ou externe ; une image d'une
   structure en images). Une seule forme, celle du noyau (spectre/kernel/annotations.py) :
   {type: "arrow" | "box", x, y, x2, y2, label}, en % de l'image - une annotation reste à sa place
   quelle que soit la taille d'affichage (vignette, fiche, rapport). Le composant ne connaît aucun
   plugin : ce qui range les annotations (la mesure du cahier, l'image de la structure) les lui
   donne et reçoit la liste à enregistrer.

   - Lecture seule, sans rien monter : une <img> qui porte `ImageAnnotations.attr(annotations)` voit
     ses annotations dessinées à son chargement (vignettes, planches, aperçus d'une boîte).
   - `ImageAnnotations.mount(host, {img, annotations, editable, onSave, name})` : les annotations
     dessinées et numérotées, leur liste dans `host` (les libellés) ; pour un éditeur, les outils
     (« Flèche » : cliquer-glisser du départ à l'arrivée, ou un clic puis un autre ; « Cadre » :
     cliquer-glisser ; Échap annule), un libellé modifiable et un bouton de retrait par annotation,
     puis « Enregistrer les annotations » (`onSave(liste)`, une promesse : vraie, c'est enregistré)
     ou « Annuler ».

   Le dessin est un <svg class="annot-layer"> placé juste après l'image, dont le repère a les
   proportions de l'image (`preserveAspectRatio` « meet » : il épouse aussi une image en
   `object-fit: contain`) ; l'hôte le pose sur l'image - une image enveloppée dans `.annot-frame`
   (kernel.css), ou une règle de sa feuille. Pas de <marker> (le rapport retire les id) : la pointe
   d'une flèche est un triangle. Les éléments propres à l'édition portent data-report-hide : le
   rapport d'une étude garde les images annotées et la liste des libellés. */

const ImageAnnotations = (() => {
  const TYPES = { arrow: "Flèche", box: "Cadre" };

  // une annotation telle qu'on l'enregistre : la forme seule, sans la clé d'image de l'hôte
  function shape(a) {
    return { type: a.type, x: a.x, y: a.y, x2: a.x2 ?? null, y2: a.y2 ?? null, label: a.label || null };
  }

  function valid(a) {
    return a && (a.type === "arrow" || a.type === "box") && Number.isFinite(a.x) && Number.isFinite(a.y);
  }

  // L'attribut d'une <img> dont les annotations se dessinent à son chargement (rien sans annotation).
  function attr(annotations) {
    const list = (annotations || []).filter(valid).map(shape);
    return list.length ? ` data-annotations="${escapeHtml(JSON.stringify(list))}"` : "";
  }

  function svgMarkup(annotations, ratio, { numbered = false, pending = null } = {}) {
    const h = 100 * ratio;
    const one = (a, i) => {
      const x = a.x;
      const y = a.y * ratio;
      const x2 = a.x2 ?? a.x;
      const y2 = (a.y2 ?? a.y) * ratio;
      let body;
      if (a.type === "point") return `<g class="annot annot--pending"><circle class="annot__halo" cx="${x}" cy="${y}" r="1.2"/><circle cx="${x}" cy="${y}" r="1.2"/></g>`;
      if (a.type === "arrow") {
        const angle = Math.atan2(y2 - y, x2 - x);
        const head = (side) => `${x2 - 3.2 * Math.cos(angle + side)},${y2 - 3.2 * Math.sin(angle + side)}`;
        body = `<line class="annot__halo" x1="${x}" y1="${y}" x2="${x2}" y2="${y2}"/><line x1="${x}" y1="${y}" x2="${x2}" y2="${y2}"/><polygon points="${x2},${y2} ${head(0.45)} ${head(-0.45)}"/>`;
      } else {
        const rect = `x="${Math.min(x, x2)}" y="${Math.min(y, y2)}" width="${Math.abs(x2 - x)}" height="${Math.abs(y2 - y)}"`;
        body = `<rect class="annot__halo" ${rect}/><rect ${rect}/>`;
      }
      // le numéro de l'annotation dans la liste : au départ d'une flèche, au coin d'un cadre
      const nx = Math.min(Math.max(a.type === "box" ? Math.min(x, x2) : x, 2.6), 97.4);
      const ny = Math.min(Math.max(a.type === "box" ? Math.min(y, y2) : y, 2.6), h - 2.6);
      const badge = numbered && i != null ? `<circle class="annot__badge" cx="${nx}" cy="${ny}" r="2.6"/><text class="annot__num" x="${nx}" y="${ny}">${i + 1}</text>` : "";
      return `<g class="annot annot--${a.type}${i == null ? " annot--pending" : ""}">${body}${badge}</g>`;
    };
    const shapes = annotations.map((a, i) => one(a, i)).join("") + (pending ? one(pending, null) : "");
    return `<svg class="annot-layer" viewBox="0 0 100 ${h}" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">${shapes}</svg>`;
  }

  // Dessine `annotations` sur `img` (déjà chargée) : remplace le dessin précédent.
  function draw(img, annotations, options = {}) {
    const next = img.nextElementSibling;
    if (next && next.classList.contains("annot-layer")) next.remove();
    if (!img.naturalWidth || (!annotations.length && !options.pending)) return;
    img.insertAdjacentHTML("afterend", svgMarkup(annotations, img.naturalHeight / img.naturalWidth, options));
  }

  // Lecture seule : toute image marquée par attr() se dessine à son chargement ('load' ne remonte
  // pas : écouté en capture).
  document.addEventListener(
    "load",
    (event) => {
      const img = event.target;
      if (!(img instanceof HTMLImageElement) || !img.dataset.annotations) return;
      try {
        draw(img, JSON.parse(img.dataset.annotations).filter(valid));
      } catch (err) {
        // des annotations illisibles : l'image reste, sans dessin
      }
    },
    true
  );

  // Le point visé, en % de l'image affichée (son contenu : ni marge intérieure, ni bandes d'un
  // `object-fit: contain`).
  function pointAt(img, event) {
    const rect = img.getBoundingClientRect();
    const cs = getComputedStyle(img);
    const px = (name) => parseFloat(cs[name]) || 0;
    let left = rect.left + px("paddingLeft") + px("borderLeftWidth");
    let top = rect.top + px("paddingTop") + px("borderTopWidth");
    let width = rect.width - px("paddingLeft") - px("paddingRight") - px("borderLeftWidth") - px("borderRightWidth");
    let height = rect.height - px("paddingTop") - px("paddingBottom") - px("borderTopWidth") - px("borderBottomWidth");
    if ((cs.objectFit === "contain" || cs.objectFit === "scale-down") && img.naturalWidth) {
      const ratio = img.naturalHeight / img.naturalWidth;
      if (height / width > ratio) {
        top += (height - width * ratio) / 2;
        height = width * ratio;
      } else {
        left += (width - height / ratio) / 2;
        width = height / ratio;
      }
    }
    const clamp = (v) => Math.round(Math.max(0, Math.min(100, v)) * 100) / 100;
    return { x: clamp(((event.clientX - left) / width) * 100), y: clamp(((event.clientY - top) / height) * 100) };
  }

  function listHtml(list, editable, name) {
    if (!list.length) return "";
    return `<ol class="annot-list">${list
      .map((a, i) => {
        const text = a.label ? ` - ${escapeHtml(a.label)}` : "";
        const input = editable
          ? `<input class="field annot-list__input" data-label="${i}" maxlength="200" value="${escapeHtml(a.label || "")}" placeholder="Libellé (facultatif)" aria-label="Libellé de l'annotation ${i + 1}${name ? ` de ${escapeHtml(name)}` : ""}" data-report-hide>`
          : "";
        const remove = editable
          ? `<button type="button" class="annot-list__remove" data-remove="${i}" aria-label="Retirer l'annotation ${i + 1}" title="Retirer" data-report-hide>×</button>`
          : "";
        return `<li class="annot-list__item"><span class="annot-list__num" aria-hidden="true">${i + 1}</span><span class="annot-list__type">${TYPES[a.type]}</span>${input}<span class="annot-list__text">${text}</span>${remove}</li>`;
      })
      .join("")}</ol>`;
  }

  /* Monte les annotations d'une image : `host` reçoit la liste (et, pour un éditeur, les outils).
     `annotations` : celles de cette image ; `onSave(liste)` : la liste à enregistrer (les formes
     seules), une promesse - vraie, c'est enregistré (la page se relit alors d'ordinaire). `name` :
     le nom de l'image, pour les libellés d'accessibilité. Renvoie {get()}. */
  function mount(host, { img, annotations = [], editable = false, onSave = null, name = "" }) {
    img.removeAttribute("data-annotations"); // le dessin est à ce composant désormais
    const saved = annotations.filter(valid).map(shape);
    let list = saved.map((a) => ({ ...a }));
    let tool = null;
    let start = null; // le départ d'une flèche posée en deux clics
    let drag = null; // {from, to} pendant un cliquer-glisser

    host.classList.add("annot-host");
    host.innerHTML = `
      <div class="annot-host__list"></div>
      ${
        editable
          ? `<div class="annot-tools" data-report-hide>
               <button type="button" class="btn btn-line annot-tool" data-tool="arrow" aria-pressed="false">Flèche</button>
               <button type="button" class="btn btn-line annot-tool" data-tool="box" aria-pressed="false">Cadre</button>
               <button type="button" class="btn btn-primary annot-save" hidden>Enregistrer les annotations</button>
               <button type="button" class="btn btn-line annot-cancel" hidden>Annuler</button>
               <span class="annot-hint" role="status" aria-live="polite"></span>
             </div>`
          : ""
      }`;
    const listHost = host.querySelector(".annot-host__list");
    const frame = img.parentElement;

    const render = (pending = null) => {
      const shown = () => draw(img, list, { numbered: true, pending });
      if (img.complete && img.naturalWidth) shown();
      else img.addEventListener("load", shown, { once: true });
    };
    const renderList = () => {
      listHost.innerHTML = listHtml(list, editable, name);
    };
    render();
    renderList();
    if (!editable) return { get: () => list.map(shape) };

    const tools = host.querySelector(".annot-tools");
    const hint = tools.querySelector(".annot-hint");
    const save = tools.querySelector(".annot-save");
    const cancel = tools.querySelector(".annot-cancel");
    const dirty = () => JSON.stringify(list.map(shape)) !== JSON.stringify(saved);
    const changed = () => {
      save.hidden = cancel.hidden = !dirty();
      save.disabled = false;
    };
    const setTool = (next) => {
      tool = next;
      start = null;
      drag = null;
      tools.querySelectorAll("[data-tool]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tool === tool)));
      frame.classList.toggle("is-annotating", Boolean(tool));
      hint.textContent =
        tool === "arrow" ? "Cliquez-glissez du départ à l'arrivée de la flèche (ou cliquez le départ, puis l'arrivée). Échap : annuler." : tool === "box" ? "Cliquez-glissez pour tracer le cadre. Échap : annuler." : "";
      render();
    };
    const add = (a) => {
      list = [...list, { ...a, label: null }];
      setTool(null);
      renderList();
      changed();
      hint.textContent = `${TYPES[a.type]} ${list.length} ${a.type === "box" ? "ajouté" : "ajoutée"} - donnez-lui un libellé si besoin.`;
      listHost.querySelector(`[data-label="${list.length - 1}"]`)?.focus();
    };
    const far = (a, b) => Math.abs(a.x - b.x) >= 1 || Math.abs(a.y - b.y) >= 1;

    tools.querySelectorAll("[data-tool]").forEach((btn) => btn.addEventListener("click", () => setTool(tool === btn.dataset.tool ? null : btn.dataset.tool)));
    img.addEventListener("pointerdown", (event) => {
      if (!tool || event.button !== 0) return;
      event.preventDefault();
      img.setPointerCapture?.(event.pointerId);
      const from = start || pointAt(img, event);
      drag = { from, to: from, moved: false };
    });
    img.addEventListener("pointermove", (event) => {
      if (!drag) return;
      drag.to = pointAt(img, event);
      drag.moved = drag.moved || far(drag.from, drag.to);
      if (drag.moved) render({ type: tool, x: drag.from.x, y: drag.from.y, x2: drag.to.x, y2: drag.to.y });
    });
    img.addEventListener("pointerup", (event) => {
      if (!drag) return;
      const { from } = drag;
      const to = pointAt(img, event);
      drag = null;
      if (far(from, to)) return add({ type: tool, x: from.x, y: from.y, x2: to.x, y2: to.y });
      if (tool === "arrow" && !start) {
        start = from; // un simple clic : le départ d'une flèche en deux clics
        hint.textContent = "Cliquez l'arrivée de la flèche.";
        render({ type: "point", x: from.x, y: from.y });
      } else render();
    });
    // dans un lien (l'image en grand), un clic d'annotation n'ouvre rien
    img.addEventListener("click", (event) => {
      if (tool) event.preventDefault();
    });
    host.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && tool) setTool(null);
    });
    listHost.addEventListener("input", (event) => {
      const input = event.target.closest("[data-label]");
      if (!input) return;
      list[Number(input.dataset.label)].label = input.value.trim() || null;
      changed();
    });
    listHost.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-remove]");
      if (!btn) return;
      const i = Number(btn.dataset.remove);
      list = list.filter((_, j) => j !== i);
      renderList();
      render();
      changed();
      hint.textContent = `Annotation ${i + 1} retirée.`;
      (listHost.querySelector(`[data-remove="${Math.min(i, list.length - 1)}"]`) || tools.querySelector("[data-tool]")).focus();
    });
    cancel.addEventListener("click", () => {
      list = saved.map((a) => ({ ...a }));
      setTool(null);
      renderList();
      changed();
      tools.querySelector("[data-tool]").focus();
    });
    save.addEventListener("click", async () => {
      save.disabled = true;
      const done = await onSave(list.map(shape));
      if (!done) save.disabled = false;
    });
    return { get: () => list.map(shape) };
  }

  return { attr, mount };
})();
