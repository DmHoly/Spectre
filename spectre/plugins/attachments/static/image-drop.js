/* Planche d'images d'une structure en images : une ou plusieurs images (un schéma PowerPoint, une
   coupe TEM d'ensemble, un zoom...), dans l'ordre où les lire, chacune avec son type et sa légende.
   On en ajoute en collant (Ctrl+V), en glissant-déposant (un ou plusieurs fichiers) ou en les
   choisissant ; on les réordonne (← →), les remplace (bouton, ou fichier déposé sur l'image) ou les
   retire. Chaque image part aussitôt au serveur (attachmentsApi.uploadStructureImage, voir
   attachments/static/client.js) - la planche ne garde que son id. Partagée par la page « structure en
   image » (nouvelle expérience, évolution), la fenêtre « Modifier les images » de la fiche et le
   formulaire de preuve (sans type d'image, en version compacte - options withKind/compact).
   Coller marche partout dans la page (ou la fenêtre) tant que `isActive()` le permet : une image
   dans le presse-papiers ne se colle nulle part ailleurs, donc rien n'est volé à un champ texte.
   L'affichage d'une planche (structureBoardHtml, libellés des types) est dans
   structures/static/structure-images.js. */

const STRUCTURE_IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];
const STRUCTURE_IMAGE_MAX_BYTES = 10 * 1024 * 1024;
const STRUCTURE_IMAGE_MAX_COUNT = 12; // spectre.core.structures.MAX_STRUCTURE_IMAGES

// `purpose` : "structure" (une image de structure) ou "evidence" (une image collée dans une preuve).
async function uploadStructureImage(slug, file, purpose = "structure") {
  const form = new FormData();
  form.append("file", file, file.name || "image-collee.png");
  try {
    return purpose === "evidence" ? await attachmentsApi.uploadImage(slug, form) : await attachmentsApi.uploadStructureImage(slug, form);
  } catch (err) {
    const detail = err.data && err.data.detail;
    if (!detail) err.message = "L'envoi de l'image a échoué.";
    throw err;
  }
}

// Une coupe TEM/MEB se reconnaît souvent à son nom de fichier - un coup de pouce pour le type
// d'image, jamais imposé (le choix reste modifiable).
function guessStructureImageKind(filename) {
  return /(^|[^a-z])(s?tem|sem|meb|fib|haadf)([^a-z]|$)|coupe/i.test(filename || "") ? "coupe" : null;
}

function imageFileProblem(file) {
  const type = (file.type || "").toLowerCase();
  if (type === "image/tiff" || type === "image/bmp" || /\.(tiff?|bmp)$/i.test(file.name || "")) {
    return "Ce format (TIFF, BMP) ne s'affiche pas dans le navigateur : copiez l'image depuis votre logiciel puis collez-la ici (Ctrl+V), ou exportez-la en PNG.";
  }
  if (!STRUCTURE_IMAGE_TYPES.includes(type)) return "Il faut une image : PNG, JPEG, GIF ou WebP.";
  if (file.size > STRUCTURE_IMAGE_MAX_BYTES) return "Image trop volumineuse (10 Mo maximum).";
  if (!file.size) return "Image vide.";
  return null;
}

const IMAGE_ICON = `<svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/></svg>`;
const TILE_ICONS = {
  left: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>`,
  right: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>`,
  replace: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/></svg>`,
  remove: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>`,
};

// colonnes de la planche selon le nombre d'images (1 : pleine largeur ; 2 à 4 : deux ; puis trois, quatre)
function boardColumns(count) {
  return count <= 1 ? 1 : count <= 4 ? 2 : count <= 9 ? 3 : 4;
}

/* Monte la planche dans `zone`. `onChange(images)` reçoit la liste à jour ({image_id, kind,
   caption}, images déjà enregistrées côté serveur seulement) ; `onError(err)` un souci d'envoi ou
   de format. `purpose` : à quoi sert chaque image ("structure" par défaut, "evidence" pour une preuve) ; `withKind` :
   le choix du type (schéma, coupe...) sur chaque image ; `compact` : une planche plus basse, pour
   un formulaire. Renvoie {get, set, isUploading, add}. */
function mountImageDrop(
  zone,
  { slug, onChange = () => {}, onError = () => {}, isActive = () => true, pasteTarget = document, purpose = "structure", withKind = true, compact = false } = {}
) {
  let items = []; // {key, image_id, url, filename, kind, caption, uploading}
  let nextKey = 1;
  let replaceKey = null;
  let dragDepth = 0;

  zone.classList.add("img-board");
  zone.classList.toggle("img-board--compact", compact);
  zone.innerHTML = `
    <input type="file" class="img-board__file" accept="${STRUCTURE_IMAGE_TYPES.join(",")}" multiple tabindex="-1" aria-hidden="true" hidden>
    <input type="file" class="img-board__file-one" accept="${STRUCTURE_IMAGE_TYPES.join(",")}" tabindex="-1" aria-hidden="true" hidden>
    <div class="img-board__empty">
      <span class="img-board__icon">${IMAGE_ICON}</span>
      <p class="img-board__title">${withKind ? "Collez l'image de votre structure" : "Collez une ou plusieurs images"}</p>
      <p class="img-board__keys"><kbd>Ctrl</kbd> + <kbd>V</kbd> n'importe où sur la page, ou glissez-déposez un ou plusieurs fichiers ici</p>
      <button type="button" class="btn btn-line img-board__add">Choisir des fichiers…</button>
      <p class="img-board__hint">Un schéma copié depuis PowerPoint (sélectionnez la forme ou la diapositive, Ctrl+C), des coupes TEM ou MEB, une photo - plusieurs images si une seule ne suffit pas. PNG, JPEG, GIF ou WebP, 10 Mo max par image.</p>
    </div>
    <div class="img-board__grid" role="list" aria-label="Images de la structure"></div>
    <div class="img-board__bar">
      <button type="button" class="btn btn-line img-board__add">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
        Ajouter une image
      </button>
      <span class="img-board__again"><kbd>Ctrl</kbd>+<kbd>V</kbd> ou glisser-déposer pour en ajouter · déposer sur une image pour la remplacer</span>
      <span class="img-board__count"></span>
    </div>
    <div class="img-board__overlay" aria-hidden="true">Déposez pour ajouter</div>`;

  const fileInput = zone.querySelector(".img-board__file");
  const fileOne = zone.querySelector(".img-board__file-one");
  const empty = zone.querySelector(".img-board__empty");
  const grid = zone.querySelector(".img-board__grid");
  const bar = zone.querySelector(".img-board__bar");
  const count = zone.querySelector(".img-board__count");

  const saved = () => items.filter((it) => it.image_id && !it.uploading).map((it) => ({ image_id: it.image_id, kind: it.kind, caption: it.caption || null }));
  const changed = () => onChange(saved());

  function tileHtml(item, i, n) {
    const num = i + 1;
    const kindOptions = Object.entries(STRUCTURE_IMAGE_KIND_LABELS)
      .map(([value, label]) => `<option value="${value}"${value === item.kind ? " selected" : ""}>${value === "autre" ? "Autre" : label}</option>`)
      .join("");
    const tool = (act, label, disabled) =>
      `<button type="button" class="img-tile__btn" data-act="${act}" aria-label="${label}" title="${label}"${disabled ? " disabled" : ""}>${TILE_ICONS[act]}</button>`;
    return `
      <figure class="img-tile${item.uploading ? " is-uploading" : ""}" data-key="${item.key}" role="listitem">
        <div class="img-tile__head">
          <span class="img-tile__num" aria-hidden="true">${num}</span>
          ${withKind ? `<select class="img-tile__kind" aria-label="Type de l'image ${num}">${kindOptions}</select>` : ""}
          <span class="img-tile__tools">
            ${n > 1 ? tool("left", `Placer l'image ${num} avant`, i === 0) + tool("right", `Placer l'image ${num} après`, i === n - 1) : ""}
            ${tool("replace", `Remplacer l'image ${num}`, item.uploading)}
            ${tool("remove", `Retirer l'image ${num}`, false)}
          </span>
        </div>
        <div class="img-tile__frame">
          <img class="img-tile__img" src="${escapeHtml(item.url)}" alt="Image ${num} de la structure">
          <div class="img-tile__busy" role="status"${item.uploading ? "" : " hidden"}><span class="img-board__spinner" aria-hidden="true"></span>Envoi…</div>
          <div class="img-tile__drop" aria-hidden="true">Déposer pour remplacer</div>
        </div>
        <input class="field img-tile__caption" maxlength="200" value="${escapeHtml(item.caption || "")}" placeholder="Légende (optionnelle)" aria-label="Légende de l'image ${num}">
      </figure>`;
  }

  // re-rendu complet, en gardant le focus (et le curseur d'une légende) là où il était
  function render() {
    const active = document.activeElement;
    const activeTile = active && zone.contains(active) ? active.closest(".img-tile") : null;
    const focusKey = activeTile ? activeTile.dataset.key : null;
    const focusSel = active && activeTile
      ? active.dataset.act ? `[data-act="${active.dataset.act}"]` : active.classList.contains("img-tile__caption") ? ".img-tile__caption" : withKind ? ".img-tile__kind" : ".img-tile__caption"
      : null;
    const caret = active && active.classList && active.classList.contains("img-tile__caption") ? active.selectionStart : null;

    const n = items.length;
    zone.classList.toggle("has-image", n > 0);
    empty.hidden = n > 0;
    grid.hidden = n === 0;
    bar.hidden = n === 0;
    zone.dataset.count = String(n);
    grid.style.setProperty("--cols", String(boardColumns(n)));
    grid.innerHTML = items.map((item, i) => tileHtml(item, i, n)).join("");
    count.textContent = n > 1 ? `${n} images` : "";
    zone.querySelectorAll(".img-board__bar .img-board__add").forEach((btn) => {
      btn.disabled = n >= STRUCTURE_IMAGE_MAX_COUNT;
      btn.title = n >= STRUCTURE_IMAGE_MAX_COUNT ? `${STRUCTURE_IMAGE_MAX_COUNT} images au maximum` : "";
    });

    if (focusKey) {
      const target = grid.querySelector(`.img-tile[data-key="${focusKey}"] ${focusSel}`);
      if (target && !target.disabled) {
        target.focus();
        if (caret != null) target.setSelectionRange(caret, caret);
      } else if (target) {
        // arrivée en bout de planche (« avant » devenu inactif...) : le bouton inverse, pour revenir
        const tile = grid.querySelector(`.img-tile[data-key="${focusKey}"]`);
        const opposite = { '[data-act="left"]': '[data-act="right"]', '[data-act="right"]': '[data-act="left"]' }[focusSel];
        ((opposite && tile.querySelector(`${opposite}:not(:disabled)`)) || tile.querySelector(".img-tile__kind, .img-tile__caption")).focus();
      }
    }
  }

  function itemByKey(key) {
    return items.find((it) => String(it.key) === String(key));
  }

  async function uploadInto(item, file, previous) {
    const localUrl = URL.createObjectURL(file);
    Object.assign(item, { url: localUrl, filename: file.name || "Image collée", uploading: true });
    render();
    try {
      const result = await uploadStructureImage(slug, file, purpose);
      if (!items.includes(item)) return; // retirée entre-temps
      Object.assign(item, { image_id: result.image_id, url: result.url, filename: result.filename, uploading: false });
      render();
      changed();
    } catch (err) {
      if (previous) Object.assign(item, previous, { uploading: false });
      else items = items.filter((it) => it !== item);
      render();
      onError(err);
    } finally {
      URL.revokeObjectURL(localUrl);
    }
  }

  function addFiles(fileList, { at = null } = {}) {
    const files = [...(fileList || [])];
    if (!files.length) return;
    for (const file of files) {
      const problem = imageFileProblem(file);
      if (problem) {
        onError(new Error(problem));
        continue;
      }
      if (items.length >= STRUCTURE_IMAGE_MAX_COUNT) {
        onError(new Error(`${STRUCTURE_IMAGE_MAX_COUNT} images au maximum.`));
        break;
      }
      const item = { key: nextKey++, image_id: null, url: "", filename: "", kind: guessStructureImageKind(file.name) || "schema", caption: "", uploading: true };
      if (at == null) items.push(item);
      else items.splice(at++, 0, item);
      uploadInto(item, file, null);
    }
  }

  function replaceFile(key, file) {
    const item = itemByKey(key);
    if (!item || !file || item.uploading) return;
    const problem = imageFileProblem(file);
    if (problem) {
      onError(new Error(problem));
      return;
    }
    const previous = { image_id: item.image_id, url: item.url, filename: item.filename };
    const guessed = guessStructureImageKind(file.name);
    if (guessed) item.kind = guessed;
    uploadInto(item, file, previous);
  }

  // -- actions des vignettes ---------------------------------------------------------------------
  grid.addEventListener("click", (event) => {
    const btn = event.target.closest("[data-act]");
    if (!btn) return;
    const tile = btn.closest(".img-tile");
    const index = items.findIndex((it) => String(it.key) === tile.dataset.key);
    if (index < 0) return;
    const act = btn.dataset.act;
    if (act === "left" || act === "right") {
      const to = act === "left" ? index - 1 : index + 1;
      if (to < 0 || to >= items.length) return;
      [items[index], items[to]] = [items[to], items[index]];
      render();
      changed();
    } else if (act === "replace") {
      replaceKey = tile.dataset.key;
      fileOne.click();
    } else if (act === "remove") {
      items.splice(index, 1);
      render();
      // le focus passe à l'image suivante (ou au bouton d'ajout)
      const next = grid.querySelectorAll(".img-tile")[Math.min(index, items.length - 1)];
      (next ? next.querySelector('[data-act="remove"]') : zone.querySelector(".img-board__add:not([hidden])"))?.focus();
      changed();
    }
  });
  grid.addEventListener("change", (event) => {
    if (!event.target.classList.contains("img-tile__kind")) return;
    const item = itemByKey(event.target.closest(".img-tile").dataset.key);
    if (item) item.kind = event.target.value;
    changed();
  });
  grid.addEventListener("input", (event) => {
    if (!event.target.classList.contains("img-tile__caption")) return;
    const item = itemByKey(event.target.closest(".img-tile").dataset.key);
    if (item) item.caption = event.target.value;
    changed();
  });
  grid.addEventListener(
    "load",
    (event) => {
      const img = event.target;
      if (!img.classList || !img.classList.contains("img-tile__img")) return;
      const item = itemByKey(img.closest(".img-tile").dataset.key);
      const name = item && item.filename && !/^image(-collee)?\.png$/i.test(item.filename) ? item.filename : "Image collée";
      img.title = `${name} · ${img.naturalWidth} × ${img.naturalHeight} px`;
    },
    true // capture : 'load' sur un <img> ne remonte pas
  );

  zone.querySelectorAll(".img-board__add").forEach((btn) => btn.addEventListener("click", () => fileInput.click()));
  empty.addEventListener("click", (event) => {
    if (!event.target.closest("button")) fileInput.click();
  });
  fileInput.addEventListener("change", () => {
    addFiles(fileInput.files);
    fileInput.value = "";
  });
  fileOne.addEventListener("change", () => {
    if (replaceKey) replaceFile(replaceKey, fileOne.files[0]);
    replaceKey = null;
    fileOne.value = "";
  });

  // -- glisser-déposer : sur une image, la remplace ; ailleurs sur la planche, ajoute ------------
  const hasFiles = (event) => event.dataTransfer && [...event.dataTransfer.types].includes("Files");
  function markDropTarget(tile) {
    grid.querySelectorAll(".img-tile.is-dragover").forEach((el) => el !== tile && el.classList.remove("is-dragover"));
    if (tile) tile.classList.add("is-dragover");
    zone.classList.toggle("is-dragover-tile", Boolean(tile));
  }
  zone.addEventListener("dragenter", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth += 1;
    zone.classList.add("is-dragover");
  });
  zone.addEventListener("dragover", (event) => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    markDropTarget(event.target.closest(".img-tile:not(.is-uploading)"));
  });
  zone.addEventListener("dragleave", () => {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) {
      zone.classList.remove("is-dragover");
      markDropTarget(null);
    }
  });
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    dragDepth = 0;
    zone.classList.remove("is-dragover");
    const tile = event.target.closest(".img-tile:not(.is-uploading)");
    markDropTarget(null);
    const files = [...event.dataTransfer.files];
    if (tile && files.length) {
      const index = items.findIndex((it) => String(it.key) === tile.dataset.key);
      replaceFile(tile.dataset.key, files[0]);
      addFiles(files.slice(1), { at: index + 1 });
    } else {
      addFiles(files);
    }
  });

  // -- coller : ajoute ---------------------------------------------------------------------------
  pasteTarget.addEventListener("paste", (event) => {
    if (!zone.isConnected || !isActive() || !event.clipboardData) return; // une planche retirée de la page n'écoute plus
    const files = [...event.clipboardData.items].filter((i) => i.kind === "file" && i.type.startsWith("image/")).map((i) => i.getAsFile());
    if (!files.length) return; // du texte : on laisse le champ qui a le focus le recevoir
    event.preventDefault();
    addFiles(files);
  });

  render();
  return {
    get: saved,
    set(images) {
      items = (images || []).map((image) => ({
        key: nextKey++,
        image_id: image.image_id,
        url: image.url || structureImageUrl(slug, image.image_id),
        filename: image.filename || "Image actuelle",
        kind: image.kind || "schema",
        caption: image.caption || "",
        uploading: false,
      }));
      render();
    },
    isUploading: () => items.some((it) => it.uploading),
    add: () => fileInput.click(),
  };
}
