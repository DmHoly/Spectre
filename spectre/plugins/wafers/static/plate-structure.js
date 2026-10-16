/* « Attacher une structure » à une plaque (global `WaferStructurePicker`), sans étude ni µprojet :
   une version d'une référence (aperçu du dessin du serveur) ou une structure de la bibliothèque des
   procédés (simulée par le serveur au moment d'attacher). PUT /api/wafers/{key}/structure ; la
   plaque n'en a qu'une, une nouvelle remplace l'ancienne.

     WaferStructurePicker.open({lasermark, onDone})

   Dépend de wafersApi, referencesApi (plugin references), processLibraryApi (plugin
   process_library), pluginEnabled, escapeHtml. */

const WaferStructurePicker = (() => {
  let dialog = null;
  let options = {};
  let tab = "reference";
  let choice = null; // {kind, source_id, version}
  let searchTimer = null;

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "wafer-dialog wafer-dialog--narrow";
    dialog.setAttribute("aria-labelledby", "wafer-structure-title");
    dialog.innerHTML = `
      <div class="card-pad wafer-dialog__inner">
        <h2 class="wafer-dialog__title" id="wafer-structure-title">Attacher une structure</h2>
        <p class="help wafer-dialog__lead js-ws-lead"></p>
        <div class="error" role="alert" hidden></div>
        <div class="plate-ws__tabs" role="tablist">
          <button type="button" class="tab js-ws-tab" role="tab" data-tab="reference">Une référence</button>
          <button type="button" class="tab js-ws-tab" role="tab" data-tab="saved">La bibliothèque</button>
        </div>
        <div class="plate-ws__pane js-ws-pane-reference">
          <input type="search" class="field js-ws-q" placeholder="Chercher une référence…" aria-label="Chercher une référence">
          <ul class="plate-ws__list js-ws-refs"></ul>
          <label class="wafer-attach__field js-ws-version-field" hidden>
            <span>Version</span>
            <select class="field js-ws-version"></select>
          </label>
          <div class="plate-ws__preview js-ws-preview" hidden></div>
        </div>
        <div class="plate-ws__pane js-ws-pane-saved" hidden>
          <input type="search" class="field js-ws-saved-q" placeholder="Filtrer la bibliothèque…" aria-label="Filtrer la bibliothèque">
          <ul class="plate-ws__list js-ws-saved"></ul>
          <p class="help" style="margin:8px 0 0;">Le dessin est calculé par StructureForge au moment d'attacher.</p>
        </div>
        <div class="wafer-dialog__actions">
          <button class="btn btn-line js-ws-cancel" type="button">Annuler</button>
          <button class="btn btn-primary js-ws-go" type="button" disabled>Attacher</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector(".js-ws-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelectorAll(".js-ws-tab").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
    dialog.querySelector(".js-ws-q").addEventListener("input", (e) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadReferences(e.target.value), 200);
    });
    dialog.querySelector(".js-ws-saved-q").addEventListener("input", (e) => filterSaved(e.target.value));
    dialog.querySelector(".js-ws-refs").addEventListener("click", (e) => {
      const b = e.target.closest("[data-slug]");
      if (b) pickReference(b.dataset.slug, b.dataset.latest || "");
    });
    dialog.querySelector(".js-ws-saved").addEventListener("click", (e) => {
      const b = e.target.closest("[data-id]");
      if (!b) return;
      dialog.querySelectorAll(".js-ws-saved [data-id]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      choose({ kind: "saved", source_id: b.dataset.id, version: null });
    });
    dialog.querySelector(".js-ws-version").addEventListener("change", (e) => previewVersion(choice.source_id, e.target.value));
    dialog.querySelector(".js-ws-go").addEventListener("click", go);
  }

  function showError(err) {
    const box = dialog.querySelector(".error");
    box.textContent = err ? err.message || String(err) : "";
    box.hidden = !err;
  }

  function choose(value) {
    choice = value;
    dialog.querySelector(".js-ws-go").disabled = !choice;
  }

  function showTab(name) {
    tab = name;
    dialog.querySelectorAll(".js-ws-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === name);
      b.setAttribute("aria-selected", String(b.dataset.tab === name));
    });
    dialog.querySelector(".js-ws-pane-reference").hidden = name !== "reference";
    dialog.querySelector(".js-ws-pane-saved").hidden = name !== "saved";
    choose(null);
    dialog.querySelectorAll("[aria-pressed]").forEach((x) => x.setAttribute("aria-pressed", "false"));
    dialog.querySelector(".js-ws-version-field").hidden = true;
    dialog.querySelector(".js-ws-preview").hidden = true;
    if (name === "saved" && !dialog.dataset.savedLoaded) loadSaved();
  }

  async function loadReferences(q) {
    const list = dialog.querySelector(".js-ws-refs");
    if (!pluginEnabled("references")) {
      list.innerHTML = `<li class="help">Les références sont désactivées sur cette instance.</li>`;
      return;
    }
    try {
      const refs = (await referencesApi.list(q || "")).filter((r) => r.latest_version);
      list.innerHTML = refs.length
        ? refs
            .map(
              (r) => `<li><button type="button" class="plate-ws__item" data-slug="${escapeHtml(r.slug)}" data-latest="${escapeHtml(r.latest_version.number)}" aria-pressed="false">
                <strong>${escapeHtml(r.name)}</strong> <span class="mono help" style="display:inline;margin:0;">${escapeHtml(r.latest_version.number)}</span>
                ${r.description ? `<span class="plate-ws__desc">${escapeHtml(r.description)}</span>` : ""}</button></li>`
            )
            .join("")
        : `<li class="help">Aucune référence publiée${q ? " ne correspond" : ""}.</li>`;
    } catch (err) {
      showError(err);
    }
  }

  async function pickReference(slug, latest) {
    dialog.querySelectorAll(".js-ws-refs [data-slug]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.slug === slug)));
    showError(null);
    const select = dialog.querySelector(".js-ws-version");
    let numbers = latest ? [latest] : [];
    try {
      const graph = await referencesApi.versions(slug);
      const found = (graph.nodes || []).map((n) => n.number).filter(Boolean);
      if (found.length) numbers = found;
    } catch (err) {
      /* la dernière version suffit */
    }
    const current = latest || numbers[numbers.length - 1];
    select.innerHTML = numbers
      .slice()
      .reverse()
      .map((n) => `<option value="${escapeHtml(n)}"${n === current ? " selected" : ""}>${escapeHtml(n)}${n === latest ? " (dernière)" : ""}</option>`)
      .join("");
    dialog.querySelector(".js-ws-version-field").hidden = false;
    choose({ kind: "reference", source_id: slug, version: current });
    previewVersion(slug, current);
  }

  async function previewVersion(slug, number) {
    const box = dialog.querySelector(".js-ws-preview");
    choose({ kind: "reference", source_id: slug, version: number });
    box.hidden = false;
    box.innerHTML = `<p class="help" style="margin:0;">Dessin de la version ${escapeHtml(number)}…</p>`;
    try {
      const version = await referencesApi.version(slug, number);
      box.innerHTML = version.structure_svg
        ? `<div class="builder-canvas-svg">${version.structure_svg}</div>`
        : `<p class="help" style="margin:0;">Cette version n'a pas de dessin.</p>`;
    } catch (err) {
      box.innerHTML = `<p class="help" style="margin:0;">${escapeHtml(err.message || String(err))}</p>`;
    }
  }

  let saved = [];
  async function loadSaved() {
    const list = dialog.querySelector(".js-ws-saved");
    if (!pluginEnabled("process_library")) {
      list.innerHTML = `<li class="help">La bibliothèque des procédés est désactivée sur cette instance.</li>`;
      return;
    }
    list.innerHTML = `<li class="help">Chargement…</li>`;
    try {
      saved = await processLibraryApi.savedStructures({});
      dialog.dataset.savedLoaded = "1";
      filterSaved(dialog.querySelector(".js-ws-saved-q").value);
    } catch (err) {
      showError(err);
    }
  }

  function filterSaved(q) {
    const wanted = (q || "").trim().toLowerCase();
    const items = saved.filter((s) => !wanted || s.name.toLowerCase().includes(wanted));
    const scope = { builtin: "intégrée", shared: "partagée", microproject: "µprojet" };
    dialog.querySelector(".js-ws-saved").innerHTML = items.length
      ? items
          .map(
            (s) => `<li><button type="button" class="plate-ws__item" data-id="${escapeHtml(s.id)}" aria-pressed="false">
              <strong>${escapeHtml(s.name)}</strong> <span class="plate-tag plate-tag--mute">${escapeHtml(scope[s.scope] || s.scope)}</span></button></li>`
          )
          .join("")
      : `<li class="help">Aucune structure${wanted ? " ne correspond" : " dans la bibliothèque"}.</li>`;
  }

  async function go() {
    if (!choice) return;
    const button = dialog.querySelector(".js-ws-go");
    button.disabled = true;
    button.textContent = choice.kind === "saved" ? "Simulation…" : "Attacher";
    showError(null);
    try {
      const attached = await wafersApi.setStructure(options.lasermark, choice);
      dialog.close();
      if (options.onDone) options.onDone(attached);
    } catch (err) {
      showError(err);
    } finally {
      button.disabled = !choice;
      button.textContent = "Attacher";
    }
  }

  async function open(opts) {
    if (!dialog) build();
    options = opts || {};
    showError(null);
    dialog.querySelector(".js-ws-lead").textContent = `La structure de « ${options.lasermark} », sans passer par une étude : une version de référence ou une structure de la bibliothèque. Elle remplace celle qui lui était attachée ; une étude qui suit la plaque garde la sienne.`;
    dialog.querySelector(".js-ws-q").value = "";
    showTab("reference");
    dialog.showModal();
    loadReferences("");
  }

  return { open };
})();
