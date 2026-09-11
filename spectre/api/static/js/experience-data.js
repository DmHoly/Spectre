/* Galerie "DATA" : images externes (jamais copiées - référencées à leur emplacement d'origine)
   attachées à une expérience ou à une variante précise d'une campagne, affichées en carrousel à
   côté de la structure simulée pour une comparaison "conçu vs mesuré". Vit dans le même bloc que
   les Preuves historiques (voir experience.js::renderEvidence) mais est un mécanisme totalement
   indépendant - metadata["data_items"], pas Evidence/kind. Dépend des globals définis par
   experience.js (slug, experienceId, currentDetail, isEditorRole, escapeHtml) - ce fichier est
   chargé juste après lui. */

let _dataMatrixCache = null; // {promise} - la matrice de campagne n'est chargée qu'une fois par
// rendu même si plusieurs items de data pointent vers une entité (voir renderDataGallery).

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

function dataImageUrl(path) {
  return `/api/microprojets/${slug}/data/image?chemin=${encodeURIComponent(path)}`;
}

// Un chemin Windows (C:\Users\...) interpolé tel quel dans un attribut onerror="..." se fait
// dépecer par le parseur JS de l'attribut (`\U`, `\t`... lus comme des séquences d'échappement -
// "\t" devient une vraie tabulation) plutôt que d'être affiché tel quel. data-path (un attribut
// HTML ordinaire, jamais interprété comme du JS) + un handler délégué évitent le problème plutôt
// que d'essayer d'échapper correctement un chemin arbitraire dans du JS inline.
document.addEventListener(
  "error",
  (event) => {
    const img = event.target;
    if (!(img instanceof HTMLImageElement) || !img.classList.contains("js-data-image")) return;
    const placeholder = document.createElement("div");
    placeholder.className = "help";
    placeholder.textContent = `image introuvable : ${img.dataset.path}`;
    img.replaceWith(placeholder);
  },
  true // capture: 'error' sur un <img> ne bulle pas
);

function dataImageTag(path, extraStyle) {
  const safePath = escapeHtml(path);
  return `<img class="js-data-image" src="${dataImageUrl(path)}" alt="${safePath}" data-path="${safePath}" style="${extraStyle || ""}">`;
}

async function fetchBatchVariationCached() {
  if (!_dataMatrixCache) {
    _dataMatrixCache = api.get(`/api/microprojets/${slug}/experiences/${experienceId}/matrice`).catch(() => null);
  }
  return _dataMatrixCache;
}

async function structureCompareHtml(detail, item) {
  if (item.entity_index == null) {
    return `${detail.structure_svg || ""}<div class="help" style="margin-top:4px;">Structure simulée</div>`;
  }
  const variation = await fetchBatchVariationCached();
  if (!variation || !variation.svgs || !variation.svgs[item.entity_index]) {
    return `<div class="help">Structure simulée indisponible pour cette variante.</div>`;
  }
  const label = (variation.labels || [])[item.entity_index] || `#${item.entity_index + 1}`;
  return `${variation.svgs[item.entity_index]}<div class="help" style="margin-top:4px;">Structure simulée — ${escapeHtml(label)}</div>`;
}

async function dataItemHtml(detail, item) {
  const pinnedPath = item.image_paths[item.pinned_index] ?? item.image_paths[0];
  const thumbs = item.image_paths
    .map(
      (path, i) => `
      <div class="js-data-thumb" data-item-id="${item.id}" data-index="${i}"
           style="display:inline-block;width:64px;height:64px;margin:0 6px 6px 0;cursor:pointer;
                  border:2px solid ${i === item.pinned_index ? "var(--accent, #4a7dff)" : "transparent"};border-radius:6px;overflow:hidden;">
        ${dataImageTag(path, "width:100%;height:100%;object-fit:cover;display:block;")}
      </div>`
    )
    .join("");

  const structureHtml = await structureCompareHtml(detail, item);
  const canEdit = isEditorRole();

  return `
    <div class="marked-card" style="margin-top:12px;">
      ${item.title ? `<div style="font-size:13px;font-weight:600;">${escapeHtml(item.title)}</div>` : ""}
      ${item.note ? `<div style="font-size:12px;color:var(--text-soft);margin-top:2px;">${escapeHtml(item.note)}</div>` : ""}
      <div class="data-item-grid" style="margin-top:10px;">
        <div>
          ${dataImageTag(pinnedPath, "max-width:100%;display:block;border-radius:var(--radius-sm);")}
          <div class="help" style="margin-top:4px;">Mesure</div>
          ${item.image_paths.length > 1 ? `<div style="margin-top:8px;">${thumbs}</div>` : ""}
        </div>
        <div>${structureHtml}</div>
      </div>
      ${canEdit ? `<button class="btn btn-line js-data-delete" data-item-id="${item.id}" type="button" style="margin-top:10px;">Retirer ces données</button>` : ""}
    </div>`;
}

async function renderDataGallery(detail) {
  _dataMatrixCache = null; // one fresh fetch per render pass, shared across items
  const list = document.getElementById("data-gallery-list");
  const items = detail.data_items || [];
  if (!items.length) {
    list.innerHTML = `<div class="help">Aucune donnée externe rattachée.</div>`;
  } else {
    const htmls = await Promise.all(items.map((item) => dataItemHtml(detail, item)));
    list.innerHTML = htmls.join("");
  }

  list.querySelectorAll(".js-data-thumb").forEach((el) => {
    el.addEventListener("click", async () => {
      dataGalleryClearError();
      try {
        // Comme toute évolution légère de cette fiche (tags, pièces jointes...), épingler une
        // autre image enregistre une nouvelle version - on navigue dessus plutôt que de rafraîchir
        // sur place, sans quoi la page resterait sur une version désormais figée (immuable) qui ne
        // porte plus ce changement.
        const result = await api.patch(`/api/microprojets/${slug}/experiences/${experienceId}/data/${el.dataset.itemId}/epingle`, {
          pinned_index: parseInt(el.dataset.index, 10),
        });
        window.location.href = `/microprojets/${slug}/experiences/${result.id}`;
      } catch (err) {
        dataGalleryShowError(err.message || String(err));
      }
    });
  });

  list.querySelectorAll(".js-data-delete").forEach((btn) => {
    btn.addEventListener("click", async () => {
      dataGalleryClearError();
      try {
        const result = await api.del(`/api/microprojets/${slug}/experiences/${experienceId}/data/${btn.dataset.itemId}`);
        window.location.href = `/microprojets/${slug}/experiences/${result.id}`;
      } catch (err) {
        dataGalleryShowError(err.message || String(err));
      }
    });
  });

  renderDataGalleryAddForm(detail);
}

function renderDataGalleryAddForm(detail) {
  const wrap = document.getElementById("data-gallery-add-wrap");
  if (!isEditorRole()) {
    wrap.innerHTML = "";
    return;
  }

  const entitySelect = detail.is_batch
    ? `<div style="margin-top:8px;">
         <label style="font-size:11px;">Variante concernée</label>
         <select class="field" id="data-add-entity-index">
           <option value="">— toute l'expérience —</option>
         </select>
       </div>`
    : "";

  wrap.innerHTML = `
    <div style="margin-top:16px;padding-top:14px;border-top:1px solid var(--border-soft);" data-report-hide>
      <div style="font-size:13px;font-weight:600;">Ajouter des données</div>
      <div id="data-gallery-error" class="help" style="display:none;color:var(--danger);margin-top:6px;"></div>

      <div style="margin-top:10px;">
        <label style="font-size:11px;">Titre (optionnel)</label>
        <input class="field" id="data-add-title" placeholder="ex : coupe TEM après recuit">
      </div>
      <div style="margin-top:8px;">
        <label style="font-size:11px;">Note (optionnelle)</label>
        <input class="field" id="data-add-note" placeholder="ex : mesure au centre de la plaque">
      </div>
      ${entitySelect}

      <div style="margin-top:14px;">
        <label style="font-size:11px;">Parcourir un dossier</label>
        <div class="field-row" style="margin-top:4px;">
          <input class="field" id="data-add-folder" placeholder="chemin absolu du dossier">
          <button class="btn btn-line" id="data-add-browse-btn" type="button">Parcourir</button>
        </div>
        <div id="data-add-browse-results" style="margin-top:8px;"></div>
        <button class="btn btn-primary" id="data-add-from-folder-btn" type="button" style="margin-top:8px;display:none;">Ajouter</button>
      </div>

      <div style="margin-top:14px;padding-top:10px;border-top:1px solid var(--border-soft);">
        <label style="font-size:11px;">Ou une image unique (pas de dossier)</label>
        <div class="field-row" style="margin-top:4px;">
          <input class="field" id="data-add-single-path" placeholder="chemin absolu de l'image">
          <button class="btn btn-line" id="data-add-single-btn" type="button">Ajouter cette image</button>
        </div>
      </div>
    </div>`;

  if (detail.is_batch) {
    fetchBatchVariationCached().then((variation) => {
      const select = document.getElementById("data-add-entity-index");
      if (!select || !variation) return;
      const labels = variation.labels || (variation.svgs || []).map((_, i) => `Variante ${i + 1}`);
      select.innerHTML =
        `<option value="">— toute l'expérience —</option>` +
        labels.map((label, i) => `<option value="${i}">${escapeHtml(label)}</option>`).join("");
    });
  }

  let browsedImages = [];

  document.getElementById("data-add-browse-btn").addEventListener("click", async () => {
    dataGalleryClearError();
    const folder = document.getElementById("data-add-folder").value.trim();
    if (!folder) return;
    try {
      const result = await api.get(`/api/microprojets/${slug}/data/parcourir?dossier=${encodeURIComponent(folder)}`);
      browsedImages = result.images || [];
      const resultsEl = document.getElementById("data-add-browse-results");
      if (!browsedImages.length) {
        resultsEl.innerHTML = `<div class="help">Aucune image trouvée dans ce dossier.</div>`;
        document.getElementById("data-add-from-folder-btn").style.display = "none";
        return;
      }
      resultsEl.innerHTML = browsedImages
        .map(
          (img, i) => `
        <div style="display:flex;align-items:center;gap:8px;padding:3px 0;">
          <input type="checkbox" class="js-data-browse-check" data-index="${i}" checked>
          <input type="radio" name="data-browse-pin" class="js-data-browse-pin" data-index="${i}" ${i === 0 ? "checked" : ""}>
          <span style="font-size:12.5px;">${escapeHtml(img.name)} <span class="help" style="display:inline;">(${img.size} o)</span></span>
        </div>`
        )
        .join("");
      document.getElementById("data-add-from-folder-btn").style.display = "";
    } catch (err) {
      dataGalleryShowError(err.message || String(err));
    }
  });

  document.getElementById("data-add-from-folder-btn").addEventListener("click", async () => {
    dataGalleryClearError();
    const checks = Array.from(document.querySelectorAll(".js-data-browse-check")).filter((c) => c.checked);
    if (!checks.length) {
      dataGalleryShowError("sélectionnez au moins une image");
      return;
    }
    const checkedIndexes = checks.map((c) => parseInt(c.dataset.index, 10));
    const pinnedRadio = document.querySelector(".js-data-browse-pin:checked");
    const pinnedFullIndex = pinnedRadio ? parseInt(pinnedRadio.dataset.index, 10) : checkedIndexes[0];
    let pinnedIndex = checkedIndexes.indexOf(pinnedFullIndex);
    if (pinnedIndex === -1) pinnedIndex = 0;

    await submitDataItem({
      image_paths: checkedIndexes.map((i) => browsedImages[i].path),
      pinned_index: pinnedIndex,
    });
  });

  document.getElementById("data-add-single-btn").addEventListener("click", async () => {
    dataGalleryClearError();
    const path = document.getElementById("data-add-single-path").value.trim();
    if (!path) return;
    await submitDataItem({ image_paths: [path], pinned_index: 0 });
  });

  async function submitDataItem(extra) {
    const entitySelectEl = document.getElementById("data-add-entity-index");
    const entityIndexRaw = entitySelectEl ? entitySelectEl.value : "";
    const body = {
      title: document.getElementById("data-add-title").value.trim() || null,
      note: document.getElementById("data-add-note").value.trim() || null,
      entity_index: entityIndexRaw === "" ? null : parseInt(entityIndexRaw, 10),
      ...extra,
    };
    try {
      const result = await api.post(`/api/microprojets/${slug}/experiences/${experienceId}/data`, body);
      window.location.href = `/microprojets/${slug}/experiences/${result.id}`;
    } catch (err) {
      dataGalleryShowError(err.message || String(err));
    }
  }
}
