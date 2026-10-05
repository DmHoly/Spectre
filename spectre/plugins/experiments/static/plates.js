/* La carte « Plaques & entités physiques » : chaque plaque suivie (une par variante d'une campagne),
   son lasermark, son emplacement et ses FDL - en champs pour un éditeur, en lecture sinon -, avec
   l'autocomplétion des valeurs déjà utilisées dans le µprojet. La mise en lot est un panneau du
   plugin lots (lot-picker.js), monté juste en dessous. */

(() => {
  let fdlFields = {}; // index de la plaque -> champ FDL (mountFdlField, wafers/static/fdl.js)

  // Une plaque : en champs pour un éditeur (data-report-hide), avec un miroir texte .report-only
  // pour le rapport (voir report.js). `label` : la variante d'une campagne.
  function plateRowHtml(current, index, canEdit, label) {
    const lasermark = current.sample_id || "";
    const location = current.location || "";
    const fdls = current.fdl || [];
    const head = label ? `<div class="plate-row__label">${escapeHtml(label)}</div>` : "";
    const readonly = `
      <div class="plate-row__ro">
        ${
          lasermark
            ? `<a class="plate-row__lasermark" href="${plateUrl(lasermark)}" title="Le parcours de cette plaque">${escapeHtml(lasermark)}</a>`
            : `<span class="plate-row__lasermark is-missing">lasermark non renseigné</span>`
        }
        ${location ? `<span class="plate-row__location">${escapeHtml(location)}</span>` : ""}
        ${fdls.length ? `<span class="plate-row__fdl">${fdlChipsHtml(fdls, { label: false })}</span>` : ""}
      </div>`;
    if (!canEdit) return `<div class="plate-row">${head}${readonly}</div>`;
    return `
      <div class="plate-row">
        ${head}
        <div class="plate-row__fields" data-report-hide>
          <div><label for="plate-lasermark-${index}">Lasermark${lasermark ? ` <a class="plate-row__trail" href="${plateUrl(lasermark)}">parcours &rarr;</a>` : ""}</label><input class="field mono js-entity-sample-id" id="plate-lasermark-${index}" data-index="${index}" list="entity-sample-id-history" value="${escapeHtml(lasermark)}" placeholder="ex : W12-A3" autocomplete="off"></div>
          <div><label for="plate-location-${index}">Emplacement</label><input class="field js-entity-location" id="plate-location-${index}" data-index="${index}" list="entity-location-history" value="${escapeHtml(location)}" placeholder="ex : boîte B, tiroir 2" autocomplete="off"></div>
          <div class="plate-row__fdl-field"><label>FDL</label><div class="js-entity-fdl" data-index="${index}"></div></div>
        </div>
        <div class="report-only">${readonly}</div>
      </div>`;
  }

  let historyLoaded = false;
  async function fillHistory(ctx) {
    if (historyLoaded) return;
    historyLoaded = true;
    const history = waferSuggestions(await wafersApi.list({ microproject: ctx.microprojectSlug }).catch(() => []));
    const options = (values) => (values || []).map((v) => `<option value="${escapeHtml(v)}">`).join("");
    document.getElementById("entity-sample-id-history").innerHTML = options(history.sample_ids);
    document.getElementById("entity-location-history").innerHTML = options(history.locations);
    document.getElementById("entity-fdl-history").innerHTML = options(history.fdls);
  }

  async function renderPlates(ctx) {
    const { detail, canEdit } = ctx;
    const host = document.getElementById("physical-tracking-content");
    const tracking = detail.physical_tracking || [];
    const labels = detail.is_batch ? ((await ctx.variants().catch(() => null)) || {}).labels || [] : null;
    const rows = (tracking.length ? tracking : [{}]).map((entry, i) => plateRowHtml(entry, i, canEdit, labels ? labels[i] || `Variante ${i + 1}` : null));
    // une étude simple suit autant de réplicats qu'on veut ; une campagne, une plaque par variante
    const canAdd = canEdit && !detail.is_batch;
    host.innerHTML = `
      <div class="plates-list${detail.is_batch ? " plates-list--batch" : ""}">${rows.join("")}</div>
      ${
        canEdit
          ? `<div class="plates-actions" data-report-hide>
               <button class="btn btn-line" id="save-physical-tracking-btn" type="button">Enregistrer les plaques</button>
               ${canAdd ? `<button class="btn btn-tint" id="add-plate-btn" type="button" title="Une autre plaque passée par la même structure (un réplicat)">+ Ajouter une plaque</button>` : ""}
             </div>
             ${canAdd ? `<p class="help plates-actions__hint" data-report-hide>Plusieurs plaques sont des réplicats de la même structure ; videz un lasermark pour retirer sa plaque.</p>` : ""}`
          : ""
      }`;
    if (!canEdit) return;
    fdlFields = {};
    const mountFdl = (el) => {
      const index = Number(el.dataset.index);
      fdlFields[index] = mountFdlField(el, {
        values: (tracking[index] || {}).fdl || [],
        datalistId: "entity-fdl-history",
        label: `FDL de la plaque ${index + 1}`,
      });
    };
    host.querySelectorAll(".js-entity-fdl").forEach(mountFdl);
    const list = host.querySelector(".plates-list");
    const addButton = document.getElementById("add-plate-btn");
    if (addButton) {
      addButton.addEventListener("click", () => {
        const index = list.querySelectorAll(".js-entity-sample-id").length;
        list.insertAdjacentHTML("beforeend", plateRowHtml({}, index, true, null));
        mountFdl(list.querySelector(`.js-entity-fdl[data-index="${index}"]`));
        document.getElementById(`plate-lasermark-${index}`).focus();
      });
    }
    document.getElementById("save-physical-tracking-btn").addEventListener("click", () => {
      // les lignes vides de fin ne comptent pas (le serveur les retire), une ligne vidée au milieu
      // garde sa place : les liens d'entité désignent une plaque par sa position
      const count = list.querySelectorAll(".js-entity-sample-id").length;
      const entities = Array.from({ length: count }, (_, i) => ({
        sample_id: host.querySelector(`.js-entity-sample-id[data-index="${i}"]`).value.trim() || null,
        location: host.querySelector(`.js-entity-location[data-index="${i}"]`).value.trim() || null,
        fdl: fdlFields[i] ? fdlFields[i].get() : [],
      }));
      ctx.write(() => experimentsApi.setEntities(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, { entities }));
    });
  }

  ExperiencePage.registerPanel({
    key: "plates",
    mount(el, ctx) {
      return Promise.all([renderPlates(ctx), ctx.canEdit ? fillHistory(ctx) : null]);
    },
  });
})();
