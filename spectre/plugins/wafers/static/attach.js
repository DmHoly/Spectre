/* « Rattacher à une étude » (global `WaferAttach`) : une plaque que Spectre connaît - par sa fiche,
   ou déjà suivie ailleurs - entre dans une étude existante, après coup : on choisit le µprojet (ceux
   où l'on peut éditer), l'étude, puis la place qu'elle y prend - une place encore « à associer »
   d'une campagne ou d'un split déclaré (une par variante, par ligne), une place vide ou un réplicat
   de plus pour une étude simple - et, si l'on veut, où elle est rangée. La carte « Plaques & entités
   physiques » de l'étude est réécrite (experimentsApi.setEntities, If-Match sur la version
   affichée) : la plaque est suivie, sa structure est celle de l'étude, ses données se saisissent
   dans le cahier de l'étude. C'est le lien entre le monde d'avant Spectre et une étude.

     WaferAttach.open({lasermark, onDone})

   Dépend de microprojectsApi, experimentsApi, waferKey (fdl.js), statusBadgeHtml
   (experiments/static/status.js), escapeHtml. */

const WaferAttach = (() => {
  const NEW_PLACE = "__new__";
  let dialog = null;
  let options = {};
  let detail = null; // l'étude choisie (experimentsApi.get)
  let labels = null; // les noms des places d'une campagne (variants), s'ils se lisent
  let slug = "";

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "wafer-dialog wafer-dialog--narrow";
    dialog.setAttribute("aria-labelledby", "wafer-attach-title");
    dialog.innerHTML = `
      <div class="card-pad wafer-dialog__inner">
        <h2 class="wafer-dialog__title" id="wafer-attach-title">Rattacher à une étude</h2>
        <p class="help wafer-dialog__lead" id="wafer-attach-lead"></p>
        <div class="error" role="alert" id="wafer-attach-error" hidden></div>
        <div class="wafer-attach">
          <label class="wafer-attach__field">
            <span>µprojet</span>
            <select class="field" id="wafer-attach-mp"><option value="">Chargement…</option></select>
          </label>
          <label class="wafer-attach__field">
            <span>Étude</span>
            <select class="field" id="wafer-attach-study" disabled><option value="">Choisissez d'abord un µprojet</option></select>
          </label>
          <fieldset class="wafer-attach__places" id="wafer-attach-places" hidden>
            <legend>Sa place dans l'étude</legend>
            <div id="wafer-attach-places-list"></div>
          </fieldset>
          <label class="wafer-attach__field" id="wafer-attach-location-field" hidden>
            <span>Emplacement <span class="help" style="display:inline;">(facultatif)</span></span>
            <input class="field" id="wafer-attach-location" type="text" placeholder="boîte 12, étagère B…" autocomplete="off">
          </label>
        </div>
        <div class="wafer-dialog__actions">
          <button class="btn btn-line" type="button" id="wafer-attach-cancel">Annuler</button>
          <button class="btn btn-primary" type="button" id="wafer-attach-go" disabled>Rattacher</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("#wafer-attach-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelector("#wafer-attach-mp").addEventListener("change", (event) => loadStudies(event.target.value));
    dialog.querySelector("#wafer-attach-study").addEventListener("change", (event) => loadPlaces(event.target.value));
    dialog.querySelector("#wafer-attach-places-list").addEventListener("change", updateButton);
    dialog.querySelector("#wafer-attach-go").addEventListener("click", go);
  }

  function statusLabel(status) {
    const known = typeof STATUS_LABELS !== "undefined" && STATUS_LABELS[status];
    return known ? known.label : status;
  }

  function showError(err) {
    const box = dialog.querySelector("#wafer-attach-error");
    box.textContent = err ? err.message || String(err) : "";
    box.hidden = !err;
  }

  function updateButton() {
    const chosen = dialog.querySelector("#wafer-attach-places-list input:checked");
    dialog.querySelector("#wafer-attach-go").disabled = !detail || !chosen;
  }

  async function loadMicroprojects() {
    const select = dialog.querySelector("#wafer-attach-mp");
    const mine = (await microprojectsApi.list()).filter((mp) => mp.can_edit);
    select.innerHTML = mine.length
      ? `<option value="">Choisir un µprojet…</option>` +
        mine.map((mp) => `<option value="${escapeHtml(mp.slug)}">${escapeHtml(mp.code ? `${mp.code} · ${mp.name}` : mp.name)}</option>`).join("")
      : `<option value="">Aucun µprojet où vous pouvez éditer une étude</option>`;
    if (mine.length === 1) {
      select.value = mine[0].slug;
      await loadStudies(mine[0].slug);
    }
  }

  async function loadStudies(microprojectSlug) {
    slug = microprojectSlug;
    detail = null;
    const select = dialog.querySelector("#wafer-attach-study");
    dialog.querySelector("#wafer-attach-places").hidden = true;
    dialog.querySelector("#wafer-attach-location-field").hidden = true;
    updateButton();
    if (!slug) {
      select.disabled = true;
      select.innerHTML = `<option value="">Choisissez d'abord un µprojet</option>`;
      return;
    }
    select.disabled = true;
    select.innerHTML = `<option value="">Chargement…</option>`;
    try {
      const { items } = await experimentsApi.list(slug, { status: "all", limit: 200 });
      select.innerHTML = items.length
        ? `<option value="">Choisir une étude…</option>` + items.map((e) => `<option value="${escapeHtml(e.id)}">${escapeHtml(e.title)} · ${escapeHtml(statusLabel(e.status))}</option>`).join("")
        : `<option value="">Aucune étude dans ce µprojet</option>`;
      select.disabled = !items.length;
    } catch (err) {
      showError(err);
    }
  }

  // les places de l'étude : une par variante d'une campagne ou ligne d'un split déclaré (vides
  // seulement) ; pour une étude simple, ses places vides et « une place de plus »
  async function loadPlaces(experimentId) {
    detail = null;
    labels = null;
    const box = dialog.querySelector("#wafer-attach-places");
    const list = dialog.querySelector("#wafer-attach-places-list");
    box.hidden = true;
    updateButton();
    if (!experimentId) return;
    showError(null);
    try {
      detail = await experimentsApi.get(slug, experimentId);
      if (detail.is_batch) labels = ((await experimentsApi.variants(slug, experimentId, detail.version_id).catch(() => null)) || {}).labels || null;
    } catch (err) {
      showError(err);
      return;
    }
    const key = waferKey(options.lasermark);
    const tracking = detail.physical_tracking || [];
    const declared = detail.declared_structure;
    const perSlot = detail.is_batch || Boolean(declared);
    const witness = detail.reference_repeat;
    const labelOf = (i) =>
      witness && i === witness.place
        ? `Témoin - réf. ${witness.reference} ${witness.version}`
        : declared
          ? declared.wafers[i] && declared.wafers[i].label ? declared.wafers[i].label : `Plaque ${i + 1}`
          : labels
            ? labels[i] || `Variante ${i + 1}`
            : detail.is_batch
              ? `Variante ${i + 1}`
              : `Place ${i + 1}`;
    if (tracking.some((e) => waferKey(e.sample_id) === key)) {
      list.innerHTML = `<p class="help" style="margin:0;">Cette étude suit déjà la plaque.</p>`;
      box.hidden = false;
      return;
    }
    const empty = tracking.map((e, i) => ({ e, i })).filter(({ e, i }) => !e.sample_id && !(witness && i === witness.place));
    const rows = empty.map(
      ({ i }) => `<label class="wafer-attach__place"><input type="radio" name="wafer-attach-place" value="${i}"> <span>${escapeHtml(labelOf(i))}</span> <span class="help">place à associer</span></label>`
    );
    if (!perSlot) rows.push(`<label class="wafer-attach__place"><input type="radio" name="wafer-attach-place" value="${NEW_PLACE}"> <span>Une place de plus</span> <span class="help">un réplicat de l'étude</span></label>`);
    if (!rows.length) {
      list.innerHTML = `<p class="help" style="margin:0;">Toutes les places de cette ${detail.is_batch ? "campagne" : "étude"} sont déjà associées à une plaque${perSlot ? " : une par variante, pas une de plus." : "."}</p>`;
      box.hidden = false;
      return;
    }
    list.innerHTML = rows.join("");
    const first = list.querySelector("input");
    if (list.querySelectorAll("input").length === 1 && first) first.checked = true;
    box.hidden = false;
    dialog.querySelector("#wafer-attach-location-field").hidden = false;
    updateButton();
  }

  async function go() {
    const chosen = dialog.querySelector("#wafer-attach-places-list input:checked");
    if (!detail || !chosen) return;
    const button = dialog.querySelector("#wafer-attach-go");
    button.disabled = true;
    showError(null);
    const location = dialog.querySelector("#wafer-attach-location").value.trim() || null;
    const entities = (detail.physical_tracking || []).map((e) => ({ sample_id: e.sample_id || null, location: e.location || null, fdl: e.fdl || [] }));
    const entry = { sample_id: options.lasermark, location, fdl: [] };
    if (chosen.value === NEW_PLACE) entities.push(entry);
    else entities[Number(chosen.value)] = entry;
    try {
      await experimentsApi.setEntities(slug, detail.id, detail.version_id, { entities });
      dialog.close();
      if (options.onDone) options.onDone({ microproject: slug, experiment: detail });
    } catch (err) {
      showError(err);
      button.disabled = false;
    }
  }

  async function open(opts) {
    if (!dialog) build();
    options = opts || {};
    detail = null;
    showError(null);
    dialog.querySelector("#wafer-attach-lead").textContent = `La plaque « ${options.lasermark} » entre dans une étude existante : elle y prend une place, en reçoit la structure, et ses données se saisissent dans le cahier de l'étude. Pour une nouvelle expérience, partez plutôt de la page du µprojet.`;
    dialog.querySelector("#wafer-attach-mp").innerHTML = `<option value="">Chargement…</option>`;
    dialog.querySelector("#wafer-attach-location").value = "";
    await loadStudies("");
    dialog.showModal();
    try {
      await loadMicroprojects();
    } catch (err) {
      showError(err);
    }
  }

  return { open };
})();
