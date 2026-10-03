/* Galerie d'images externes (jamais copiées - référencées à leur emplacement d'origine) attachées à
   une expérience ou à une variante précise d'une campagne, chaque jeu affiché à côté de la structure
   simulée pour une comparaison « conçu / mesuré ». Un panneau de la fiche (ExperiencePage.registerPanel,
   onglet « Données »), au-dessus des preuves mais indépendant d'elles. Il reçoit le contexte de la
   fiche (`galleryCtx`) à chaque montage et lit les jeux de la version affichée (externalImagesApi.list) :
   chaque image y porte son état (`ok`, `missing`, `unsupported`, `forbidden`) et son `url`.

   Cliquer une vignette ne fait que l'afficher ; « Épingler cette image » (éditeurs) en fait l'image
   du jeu, et comme toute écriture de la fiche (créer, retirer un jeu), envoie la version affichée
   puis recharge la fiche. */

let galleryCtx = null;
let galleryMounts = 0;

const IMAGE_PROBLEMS = {
  missing: "Image introuvable (déplacée ou supprimée)",
  unsupported: "Format non affichable par le navigateur (TIFF…)",
  forbidden: "Hors des dossiers autorisés",
};

function dataGalleryShowError(message) {
  const box = document.getElementById("data-gallery-error");
  if (!box) return;
  box.textContent = message;
  box.style.display = "block";
}
function dataGalleryClearError() {
  const box = document.getElementById("data-gallery-error");
  if (box) box.style.display = "none";
}

function imageProblemHtml(problem, image) {
  return `<div class="ext-image-problem"><strong>${escapeHtml(problem)}</strong><span class="mono">${escapeHtml(image.path)}</span></div>`;
}

// Une image servie peut encore manquer (déplacée depuis la lecture du jeu) : elle cède alors la place
// au même message qu'une image signalée introuvable par le serveur. Un handler délégué plutôt qu'un
// onerror="..." en ligne, où un chemin Windows (C:\Users\...) serait lu comme du JS.
document.addEventListener(
  "error",
  (event) => {
    const img = event.target;
    if (!(img instanceof HTMLImageElement) || !img.classList.contains("js-ext-image")) return;
    const holder = document.createElement("div");
    holder.innerHTML = imageProblemHtml(IMAGE_PROBLEMS.missing, { path: img.dataset.path });
    img.replaceWith(holder.firstElementChild);
  },
  true // capture : « error » sur un <img> ne remonte pas
);

function imageHtml(image, className) {
  if (image.status !== "ok") return imageProblemHtml(IMAGE_PROBLEMS[image.status] || IMAGE_PROBLEMS.missing, image);
  return `<img class="js-ext-image ${className}" src="${escapeHtml(image.url)}" alt="${escapeHtml(image.name)}" data-path="${escapeHtml(image.path)}" loading="lazy">`;
}

// la matrice de campagne, partagée avec le reste de la fiche (ctx.variants)
function galleryVariants() {
  return galleryCtx.variants().catch(() => null);
}

async function structureCompareHtml(detail, item) {
  if (detail.structure_images) {
    return `${structureBoardHtml(detail.structure_images, { compact: true })}<div class="help ext-caption">Structure (images)</div>`;
  }
  if (item.entity_index == null) {
    return `${detail.structure_svg || ""}<div class="help ext-caption">Structure simulée</div>`;
  }
  const variation = await galleryVariants();
  if (!variation || !variation.svgs || !variation.svgs[item.entity_index]) {
    return `<div class="help">Structure simulée indisponible pour cette variante.</div>`;
  }
  const label = (variation.labels || [])[item.entity_index] || `#${item.entity_index + 1}`;
  return `${variation.svgs[item.entity_index]}<div class="help ext-caption">Structure simulée — ${escapeHtml(label)}</div>`;
}

function mainImageHtml(item, index) {
  const image = item.images[index];
  const pinned = index === item.pinned_index;
  const pin =
    galleryCtx.canEdit && !pinned && image.status === "ok"
      ? `<button class="btn btn-line ext-pin-btn" type="button" data-act="pin" data-report-hide>Épingler cette image</button>`
      : "";
  return `${imageHtml(image, "ext-main-image")}
    <div class="ext-main-meta">
      <span class="help ext-caption">Mesure${item.images.length > 1 ? ` · ${index + 1}/${item.images.length}${pinned ? " · épinglée" : ""}` : ""}</span>
      ${pin}
    </div>`;
}

async function imageSetHtml(detail, item) {
  const thumbs = item.images
    .map(
      (image, i) => `
      <button type="button" class="ext-thumb${i === item.pinned_index ? " is-shown" : ""}" data-index="${i}" aria-label="Afficher ${escapeHtml(image.name)}" aria-pressed="${i === item.pinned_index}">
        ${image.status === "ok" ? imageHtml(image, "ext-thumb__img") : `<span class="ext-thumb__off" title="${escapeHtml(IMAGE_PROBLEMS[image.status] || "")}">${escapeHtml(image.name)}</span>`}
      </button>`
    )
    .join("");
  const structureHtml = await structureCompareHtml(detail, item);
  return `
    <div class="marked-card ext-set" data-set-id="${escapeHtml(item.id)}">
      ${item.title ? `<div class="ext-set__title">${escapeHtml(item.title)}</div>` : ""}
      ${item.note ? `<div class="ext-set__note">${escapeHtml(item.note)}</div>` : ""}
      <div class="data-item-grid">
        <div>
          <div class="ext-main">${mainImageHtml(item, item.pinned_index)}</div>
          ${item.images.length > 1 ? `<div class="ext-thumbs">${thumbs}</div>` : ""}
        </div>
        <div>${structureHtml}</div>
      </div>
      ${galleryCtx.canEdit ? `<button class="btn btn-line" type="button" data-act="remove" data-report-hide>Retirer ces données</button>` : ""}
    </div>`;
}

function wireImageSet(card, item) {
  const ctx = galleryCtx;
  let shown = item.pinned_index;
  card.addEventListener("click", (event) => {
    const thumb = event.target.closest(".ext-thumb");
    if (thumb) {
      // afficher seulement : rien n'est écrit
      shown = Number(thumb.dataset.index);
      card.querySelector(".ext-main").innerHTML = mainImageHtml(item, shown);
      card.querySelectorAll(".ext-thumb").forEach((t) => {
        const on = t === thumb;
        t.classList.toggle("is-shown", on);
        t.setAttribute("aria-pressed", String(on));
      });
      return;
    }
    const act = event.target.closest("[data-act]");
    if (!act) return;
    if (act.dataset.act === "pin") ctx.write(() => externalImagesApi.pin(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, item.id, shown));
    if (act.dataset.act === "remove") ctx.write(() => externalImagesApi.remove(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, item.id));
  });
}

async function renderDataGallery(host) {
  const seq = (galleryMounts += 1);
  const ctx = galleryCtx;
  const sets = await externalImagesApi.list(ctx.microprojectSlug, ctx.experimentId, ctx.isTip ? null : ctx.versionId);
  const htmls = await Promise.all(sets.map((item) => imageSetHtml(ctx.detail, item)));
  if (seq !== galleryMounts) return; // un rechargement plus récent est en route
  ctx.setDataCount("external_images", sets.length);
  host.innerHTML = `<div class="ext-sets">${htmls.join("") || `<div class="help">Aucune donnée externe rattachée.</div>`}</div><div class="ext-add-wrap"></div>`;
  host.querySelectorAll(".ext-set").forEach((card, i) => wireImageSet(card, sets[i]));
  renderDataGalleryAddForm(host.querySelector(".ext-add-wrap"), ctx.detail);
}

function renderDataGalleryAddForm(wrap, detail) {
  if (!galleryCtx.canEdit) return;
  wrap.innerHTML = `
    <div class="ext-add" data-report-hide>
      <div class="ext-set__title">Ajouter des données</div>
      <div id="data-gallery-error" class="help ext-error" role="alert" style="display:none;"></div>

      <div class="ext-field">
        <label for="data-add-title">Titre (optionnel)</label>
        <input class="field" id="data-add-title" placeholder="ex : coupe TEM après recuit">
      </div>
      <div class="ext-field">
        <label for="data-add-note">Note (optionnelle)</label>
        <input class="field" id="data-add-note" placeholder="ex : mesure au centre de la plaque">
      </div>
      ${
        detail.is_batch
          ? `<div class="ext-field">
               <label for="data-add-entity-index">Variante concernée</label>
               <select class="field" id="data-add-entity-index"><option value="">— toute l'expérience —</option></select>
             </div>`
          : ""
      }

      <div class="ext-field">
        <label for="data-add-folder">Parcourir un dossier autorisé</label>
        <div class="field-row">
          <input class="field mono" id="data-add-folder" placeholder="chemin absolu du dossier">
          <button class="btn btn-line" id="data-add-browse-btn" type="button">Parcourir</button>
        </div>
        <div id="data-add-browse-results" class="ext-browse"></div>
        <button class="btn btn-primary" id="data-add-from-folder-btn" type="button" style="display:none;">Ajouter</button>
      </div>

      <div class="ext-field ext-field--split">
        <label for="data-add-single-path">Ou une image unique</label>
        <div class="field-row">
          <input class="field mono" id="data-add-single-path" placeholder="chemin absolu de l'image">
          <button class="btn btn-line" id="data-add-single-btn" type="button">Ajouter cette image</button>
        </div>
      </div>
    </div>`;

  if (detail.is_batch) {
    galleryVariants().then((variation) => {
      const select = document.getElementById("data-add-entity-index");
      if (!select || !variation) return;
      const labels = variation.labels || (variation.svgs || []).map((_, i) => `Variante ${i + 1}`);
      select.innerHTML = `<option value="">— toute l'expérience —</option>${labels.map((label, i) => `<option value="${i}">${escapeHtml(label)}</option>`).join("")}`;
    });
  }

  let browsed = [];
  const results = document.getElementById("data-add-browse-results");
  const fromFolderBtn = document.getElementById("data-add-from-folder-btn");

  document.getElementById("data-add-browse-btn").addEventListener("click", async () => {
    dataGalleryClearError();
    const directory = document.getElementById("data-add-folder").value.trim();
    if (!directory) return;
    try {
      browsed = await externalImagesApi.browse(galleryCtx.microprojectSlug, directory);
    } catch (err) {
      dataGalleryShowError(err.message || String(err));
      return;
    }
    const firstShown = browsed.findIndex((img) => img.displayable);
    fromFolderBtn.style.display = firstShown === -1 ? "none" : "";
    results.innerHTML = browsed.length
      ? browsed
          .map(
            (img, i) => `
        <div class="ext-browse__row${img.displayable ? "" : " is-off"}">
          <input type="checkbox" class="js-browse-check" data-index="${i}" aria-label="Retenir ${escapeHtml(img.name)}"${img.displayable ? " checked" : " disabled"}>
          <input type="radio" name="data-browse-pin" class="js-browse-pin" data-index="${i}" aria-label="Épingler ${escapeHtml(img.name)}"${i === firstShown ? " checked" : ""}${img.displayable ? "" : " disabled"}>
          <span>${escapeHtml(img.name)} <span class="help">${img.displayable ? `${img.size} o` : "TIFF : non affichable par le navigateur, exportez-la en PNG ou en JPEG"}</span></span>
        </div>`
          )
          .join("")
      : `<div class="help">Aucune image dans ce dossier.</div>`;
  });

  fromFolderBtn.addEventListener("click", () => {
    dataGalleryClearError();
    const checked = [...results.querySelectorAll(".js-browse-check:checked")].map((c) => Number(c.dataset.index));
    if (!checked.length) {
      dataGalleryShowError("Sélectionnez au moins une image.");
      return;
    }
    const pinned = results.querySelector(".js-browse-pin:checked");
    const pinnedIndex = pinned ? checked.indexOf(Number(pinned.dataset.index)) : 0;
    submitImageSet({ image_paths: checked.map((i) => browsed[i].path), pinned_index: Math.max(0, pinnedIndex) });
  });

  document.getElementById("data-add-single-btn").addEventListener("click", () => {
    dataGalleryClearError();
    const path = document.getElementById("data-add-single-path").value.trim();
    if (path) submitImageSet({ image_paths: [path], pinned_index: 0 });
  });

  function submitImageSet(images) {
    const entity = document.getElementById("data-add-entity-index");
    const body = {
      title: document.getElementById("data-add-title").value.trim() || null,
      note: document.getElementById("data-add-note").value.trim() || null,
      entity_index: entity && entity.value !== "" ? Number(entity.value) : null,
      ...images,
    };
    const ctx = galleryCtx;
    return ctx.write(() => externalImagesApi.create(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, body), document.getElementById("data-gallery-error"));
  }
}

ExperiencePage.registerPanel({
  key: "external_images",
  mount(el, ctx) {
    galleryCtx = ctx;
    return renderDataGallery(el);
  },
});
