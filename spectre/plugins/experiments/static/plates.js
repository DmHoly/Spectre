/* La carte « Plaques & entités physiques » : les FDL de l'étude, puis chacune de ses places (une par
   variante d'une campagne, ses réplicats sinon) associée à une vraie plaque - choisie dans un menu
   déroulant parmi les plaques que la base connaît pour ces FDL (mountStudyFdl, wafers/static/fdl.js),
   tapée sinon -, son emplacement et ses FDL ; en champs pour un éditeur, en lecture sinon, avec
   l'autocomplétion des valeurs déjà utilisées dans le µprojet. Une place peut rester « à associer » :
   il en faut une associée pour conclure. La mise en lot est un panneau du plugin lots
   (lot-picker.js), monté juste en dessous. */

(() => {
  // Une place, en lecture : sa plaque (ou « à associer »), son emplacement, ses FDL.
  function readonlyHtml(entry) {
    const lasermark = entry.sample_id || "";
    const fdls = entry.fdl || [];
    return `
      <div class="plate-row__ro">
        ${
          lasermark
            ? `<a class="plate-row__lasermark" href="${plateUrl(lasermark)}" title="Le parcours de cette plaque">${escapeHtml(lasermark)}</a>`
            : `<span class="plate-row__lasermark is-missing">plaque à associer</span>`
        }
        ${entry.location ? `<span class="plate-row__location">${escapeHtml(entry.location)}</span>` : ""}
        ${fdls.length ? `<span class="plate-row__fdl">${fdlChipsHtml(fdls, { label: false })}</span>` : ""}
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
    const labels = detail.is_batch ? ((await ctx.variants().catch(() => null)) || {}).labels || [] : null;
    const labelOf = (i) => (labels ? labels[i] || `Variante ${i + 1}` : null);
    const tracking = detail.physical_tracking || [];
    const studyFdl = detail.fdl || [];

    if (!canEdit) {
      const rows = (tracking.length ? tracking : [{}]).map((entry, i) => {
        const label = labelOf(i);
        return `<div class="plate-row">${label ? `<div class="plate-row__label">${escapeHtml(label)}</div>` : ""}${readonlyHtml(entry)}</div>`;
      });
      host.innerHTML = `
        ${studyFdl.length ? `<div class="plates-study-fdl">${fdlChipsHtml(studyFdl)}</div>` : ""}
        <div class="plates-list${detail.is_batch ? " plates-list--batch" : ""}">${rows.join("")}</div>`;
      return;
    }

    // les places telles qu'on les modifie : la carte se redessine à partir d'elles
    let entries = (tracking.length ? tracking : [{}]).map((e) => ({ sample_id: e.sample_id || "", location: e.location || "", fdl: (e.fdl || []).slice() }));
    let contents = [];
    let fdlFields = {};
    const canAdd = !detail.is_batch; // une étude simple suit autant de réplicats qu'on veut ; une campagne, une plaque par variante

    host.innerHTML = `
      <div class="plates-study" data-report-hide>
        <label for="plates-study-fdl-input">FDL de l'étude <span class="help">- ses plaques se choisissent ensuite place par place</span></label>
        <div id="plates-study-fdl"></div>
      </div>
      <div class="report-only">${studyFdl.length ? `<div class="plates-study-fdl">${fdlChipsHtml(studyFdl)}</div>` : ""}</div>
      <p class="help plates-summary" data-report-hide aria-live="polite"></p>
      <div class="plates-list${detail.is_batch ? " plates-list--batch" : ""}"></div>
      <div class="plates-actions" data-report-hide>
        <button class="btn btn-line" id="save-physical-tracking-btn" type="button">Enregistrer les plaques</button>
        ${canAdd ? `<button class="btn btn-tint" id="add-plate-btn" type="button" title="Une autre plaque passée par la même structure (un réplicat)">+ Ajouter une place</button>` : ""}
      </div>`;
    const list = host.querySelector(".plates-list");
    const summary = host.querySelector(".plates-summary");

    const studyField = mountStudyFdl(document.getElementById("plates-study-fdl"), {
      values: studyFdl,
      datalistId: "entity-fdl-history",
      onChange: (_, loaded) => {
        contents = loaded;
        paint();
      },
    });
    document.querySelector("#plates-study-fdl .fdl-field__input").id = "plates-study-fdl-input";

    // ce que les champs FDL des places contiennent encore (un numéro tapé sans Entrée compte aussi)
    function collectFdls() {
      Object.entries(fdlFields).forEach(([i, field]) => {
        if (entries[i]) entries[i].fdl = field.get();
      });
    }

    function rowHtml(entry, index, choices, removable) {
      const label = labelOf(index);
      const lasermark = entry.sample_id;
      const pick = choices.length
        ? fdlWaferSelectHtml({
            value: lasermark,
            choices,
            taken: entries.map((e) => e.sample_id),
            attrs: `class="field mono js-entity-pick" id="plate-lasermark-${index}" data-index="${index}"`,
          })
        : `<input class="field mono js-entity-sample-id" id="plate-lasermark-${index}" data-index="${index}" list="entity-sample-id-history" value="${escapeHtml(lasermark)}" placeholder="à associer" autocomplete="off">`;
      return `
        <div class="plate-row">
          ${label ? `<div class="plate-row__label">${escapeHtml(label)}</div>` : ""}
          <div class="plate-row__fields" data-report-hide>
            <div><label for="plate-lasermark-${index}">Plaque${lasermark ? ` <a class="plate-row__trail" href="${plateUrl(lasermark)}">parcours &rarr;</a>` : ""}</label>${pick}</div>
            <div><label for="plate-location-${index}">Emplacement</label><input class="field js-entity-location" id="plate-location-${index}" data-index="${index}" list="entity-location-history" value="${escapeHtml(entry.location)}" placeholder="ex : boîte B, tiroir 2" autocomplete="off"></div>
            <div class="plate-row__fdl-field"><label>FDL de la plaque</label><div class="js-entity-fdl" data-index="${index}"></div></div>
            ${
              removable
                ? `<button type="button" class="plate-row__remove js-remove-plate" data-index="${index}" aria-label="Retirer la place ${index + 1}" title="Retirer cette place">
                     <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
                   </button>`
                : ""
            }
          </div>
          <div class="report-only">${readonlyHtml(entry)}</div>
        </div>`;
    }

    function paint(focusSelector) {
      const choices = fdlWaferChoices(contents);
      const removable = canAdd && entries.length > 1;
      list.innerHTML = entries.map((entry, i) => rowHtml(entry, i, choices, removable)).join("");
      fdlFields = {};
      list.querySelectorAll(".js-entity-fdl").forEach((el) => {
        const index = Number(el.dataset.index);
        fdlFields[index] = mountFdlField(el, {
          values: entries[index].fdl,
          datalistId: "entity-fdl-history",
          label: `FDL de la plaque ${index + 1}`,
          onChange: (fdl) => (entries[index].fdl = fdl),
        });
      });
      const named = entries.filter((e) => e.sample_id.trim()).length;
      const left = entries.length - named;
      summary.textContent =
        left === 0
          ? `${named} plaque${named > 1 ? "s" : ""} associée${named > 1 ? "s" : ""}.`
          : named
            ? `${named} place${named > 1 ? "s" : ""} associée${named > 1 ? "s" : ""} sur ${entries.length} - ${left} à associer.`
            : `${left} place${left > 1 ? "s" : ""} à associer (il en faut une associée pour conclure).`;
      const el = focusSelector && list.querySelector(focusSelector);
      if (el) el.focus();
    }

    list.addEventListener("input", (event) => {
      const i = Number(event.target.dataset.index);
      if (event.target.classList.contains("js-entity-sample-id")) entries[i].sample_id = event.target.value;
      if (event.target.classList.contains("js-entity-location")) entries[i].location = event.target.value;
    });
    // une plaque choisie dans les FDL de l'étude : la place la suit, avec cette FDL
    list.addEventListener("change", (event) => {
      if (!event.target.classList.contains("js-entity-pick")) return;
      const i = Number(event.target.dataset.index);
      const picked = event.target.selectedOptions[0];
      collectFdls();
      entries[i].sample_id = event.target.value;
      entries[i].fdl = withFdl(entries[i].fdl, picked && picked.dataset.fdl);
      paint(`#plate-lasermark-${i}`);
    });
    list.addEventListener("click", (event) => {
      const btn = event.target.closest(".js-remove-plate");
      if (!btn) return;
      collectFdls();
      entries.splice(Number(btn.dataset.index), 1);
      paint();
    });
    const addButton = document.getElementById("add-plate-btn");
    if (addButton) {
      addButton.addEventListener("click", () => {
        collectFdls();
        entries.push({ sample_id: "", location: "", fdl: [] });
        paint(`#plate-lasermark-${entries.length - 1}`);
      });
    }
    document.getElementById("save-physical-tracking-btn").addEventListener("click", () => {
      collectFdls();
      // chaque place garde sa position, vide comprise (à associer) : les liens d'entité désignent une plaque par sa position
      const entities = entries.map((e) => ({ sample_id: e.sample_id.trim() || null, location: e.location.trim() || null, fdl: e.fdl }));
      ctx.write(() => experimentsApi.setEntities(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, { entities, fdl: studyField.get() }));
    });
    paint();
  }

  ExperiencePage.registerPanel({
    key: "plates",
    mount(el, ctx) {
      return Promise.all([renderPlates(ctx), ctx.canEdit ? fillHistory(ctx) : null]);
    },
  });
})();
