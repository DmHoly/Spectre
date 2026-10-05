/* « Partir d'une référence » (global `ReferenceStartPicker`) : le premier choix d'une nouvelle
   expérience. On cherche une référence, sa dernière version est proposée (une autre au choix), on
   voit sa structure, puis le constructeur s'ouvre avec elle, dans le µprojet voulu - l'étude lancée
   retient la version dont elle part (`reference_origin`, structures/static/builder). Partir d'une
   structure vierge reste possible, en lien secondaire - et de plaques existantes, quand la page le
   propose (`onWafers`). Ouvert depuis la page d'un µprojet (dont juste après sa création),
   l'accueil et la page d'une référence (« Partir de cette version ») :

     ReferenceStartPicker.open({microprojectSlug?, reference?, version?, intro?, onBlank?, onWafers?})

   Sans `microprojectSlug`, la boîte demande le µprojet, parmi ceux où l'on peut lancer une étude
   (éditeur). `reference` / `version` : la version proposée d'office. `onBlank(microprojectSlug)` :
   ce que fait « Partir d'une structure vierge » (sinon : le constructeur vide de ce µprojet).
   `onWafers(microprojectSlug)` : ce que fait « Partir de plaques existantes » (le lien n'apparaît
   qu'avec lui - wafers/static/start-picker.js, que la page charge). */

const ReferenceStartPicker = (() => {
  let dialog = null;
  let options = {};
  let references = [];
  let chosen = null; // {slug, number}
  let searchTimer = null;
  let previewToken = 0;

  function builderUrl(microprojectSlug, params) {
    const query = params ? `?${new URLSearchParams(params).toString()}` : "";
    return `/microprojets/${encodeURIComponent(microprojectSlug)}/structures/nouvelle${query}`;
  }

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "ref-dialog ref-dialog--wide";
    dialog.setAttribute("aria-labelledby", "ref-start-title");
    dialog.innerHTML = `
      <div class="card-pad ref-dialog__inner">
        <h2 class="ref-dialog__title" id="ref-start-title">Partir d'une référence</h2>
        <p class="help ref-dialog__lead" id="ref-start-intro"></p>
        <div class="error" role="alert" id="ref-start-error" hidden></div>
        <div class="ref-field" id="ref-start-mp-group" hidden>
          <label for="ref-start-mp">µprojet de la nouvelle expérience</label>
          <select class="field" id="ref-start-mp"></select>
        </div>
        <div class="ref-start">
          <div class="ref-start__list">
            <label for="ref-start-search">Référence</label>
            <input class="field" id="ref-start-search" type="search" placeholder="Chercher une référence" autocomplete="off">
            <ul class="ref-start__options" id="ref-start-options" role="listbox" aria-label="Références"></ul>
          </div>
          <div class="ref-start__preview" id="ref-start-preview" aria-live="polite">
            <p class="help">Choisissez une référence : sa dernière version est proposée.</p>
          </div>
        </div>
        <div class="ref-dialog__actions ref-dialog__actions--split">
          <span class="ref-dialog__actions">
            <button class="btn-link-secondary" type="button" id="ref-start-blank">Partir d'une structure vierge</button>
            <button class="btn-link-secondary" type="button" id="ref-start-wafers" hidden>Partir de plaques existantes</button>
          </span>
          <span class="ref-dialog__actions">
            <button class="btn btn-line" type="button" id="ref-start-cancel">Annuler</button>
            <button class="btn btn-primary" type="button" id="ref-start-go" disabled>Partir de cette version</button>
          </span>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("#ref-start-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelector("#ref-start-search").addEventListener("input", (event) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadReferences(event.target.value.trim()), 200);
    });
    dialog.querySelector("#ref-start-options").addEventListener("click", (event) => {
      const option = event.target.closest("[data-slug]");
      if (option) choose(option.dataset.slug, null);
    });
    dialog.querySelector("#ref-start-options").addEventListener("keydown", onOptionsKey);
    dialog.querySelector("#ref-start-preview").addEventListener("change", (event) => {
      if (event.target.id === "ref-start-version" && chosen) choose(chosen.slug, event.target.value);
    });
    dialog.querySelector("#ref-start-mp").addEventListener("change", updateButtons);
    dialog.querySelector("#ref-start-go").addEventListener("click", go);
    dialog.querySelector("#ref-start-blank").addEventListener("click", blank);
    dialog.querySelector("#ref-start-wafers").addEventListener("click", () => {
      const mp = microprojectSlug();
      if (!mp || !options.onWafers) return;
      dialog.close();
      options.onWafers(mp);
    });
  }

  function showError(err) {
    const box = dialog.querySelector("#ref-start-error");
    box.textContent = err ? err.message || String(err) : "";
    box.hidden = !err;
  }

  function microprojectSlug() {
    return options.microprojectSlug || dialog.querySelector("#ref-start-mp").value || null;
  }

  function updateButtons() {
    const mp = microprojectSlug();
    dialog.querySelector("#ref-start-go").disabled = !(mp && chosen && chosen.number);
    dialog.querySelector("#ref-start-blank").disabled = !mp;
    dialog.querySelector("#ref-start-wafers").disabled = !mp;
  }

  // -- la liste des références ------------------------------------------------------------------

  function optionsHtml() {
    const usable = references.filter((ref) => ref.latest_version);
    if (!usable.length) {
      return `<li class="ref-start__empty">Aucune référence publiée${dialog.querySelector("#ref-start-search").value ? " pour cette recherche" : ""}.</li>`;
    }
    return usable
      .map((ref) => {
        const latest = ref.latest_version;
        const source = latest.source && latest.source.microproject ? latest.source.microproject.name : "";
        const selected = chosen && chosen.slug === ref.slug;
        return `
          <li class="ref-start__option" role="option" tabindex="${selected || (!chosen && ref === usable[0]) ? 0 : -1}" aria-selected="${selected}" data-slug="${escapeHtml(ref.slug)}">
            <span class="ref-start__name">${escapeHtml(ref.name)}</span>
            <span class="ref-start__meta"><span class="ref-number">${escapeHtml(latest.number)}</span> · ${escapeHtml(formatDate(latest.published_at))}${source ? ` · ${escapeHtml(source)}` : ""}</span>
          </li>`;
      })
      .join("");
  }

  function renderOptions() {
    dialog.querySelector("#ref-start-options").innerHTML = optionsHtml();
  }

  function onOptionsKey(event) {
    const items = [...dialog.querySelectorAll(".ref-start__option")];
    const at = items.indexOf(document.activeElement);
    let next = null;
    if (event.key === "ArrowDown") next = items[Math.min(at + 1, items.length - 1)];
    else if (event.key === "ArrowUp") next = items[Math.max(at - 1, 0)];
    else if ((event.key === "Enter" || event.key === " ") && at >= 0) {
      event.preventDefault();
      choose(items[at].dataset.slug, null);
      return;
    }
    if (!next) return;
    event.preventDefault();
    items.forEach((item) => (item.tabIndex = item === next ? 0 : -1));
    next.focus();
  }

  async function loadReferences(q) {
    try {
      references = await referencesApi.list(q);
      renderOptions();
    } catch (err) {
      showError(err);
    }
  }

  // -- la version choisie -------------------------------------------------------------------------

  async function choose(slug, number) {
    const token = ++previewToken;
    chosen = { slug, number: null };
    showError(null);
    renderOptions();
    dialog.querySelector(`.ref-start__option[data-slug="${CSS.escape(slug)}"]`)?.focus();
    const preview = dialog.querySelector("#ref-start-preview");
    preview.innerHTML = `<div class="skeleton" style="height:22px;width:60%;"></div><div class="skeleton" style="height:180px;margin-top:10px;"></div>`;
    updateButtons();
    try {
      const graph = await referencesApi.versions(slug);
      if (token !== previewToken) return;
      if (!graph.nodes.length) {
        preview.innerHTML = `<p class="help">Cette référence n'a encore aucune version.</p>`;
        return;
      }
      const latest = graph.nodes[graph.nodes.length - 1].number;
      const wanted = number && graph.nodes.some((node) => node.number === number) ? number : latest;
      const version = await referencesApi.version(slug, wanted);
      if (token !== previewToken) return;
      chosen = { slug, number: wanted };
      const source = version.source && version.source.microproject ? version.source.microproject.name : "";
      preview.innerHTML = `
        <div class="ref-start__head">
          <div>
            <div class="ref-start__title">${escapeHtml(graph.reference.name)}</div>
            <div class="ref-start__meta">${escapeHtml(version.published_by ? version.published_by.name : "Repère importé")} · ${escapeHtml(formatDate(version.published_at))}${source ? ` · depuis ${escapeHtml(source)}` : ""}</div>
          </div>
          <label class="ref-start__version">
            <span class="ref-visually-hidden">Version</span>
            <select class="field" id="ref-start-version">
              ${graph.nodes
                .slice()
                .reverse()
                .map((node) => `<option value="${escapeHtml(node.number)}"${node.number === wanted ? " selected" : ""}>${escapeHtml(node.number)}${node.number === latest ? " (dernière)" : ""}</option>`)
                .join("")}
            </select>
          </label>
        </div>
        ${version.note ? `<p class="ref-start__note">${escapeHtml(version.note)}</p>` : ""}
        <div class="ref-start__svg">${version.structure_svg || `<p class="help">Aperçu indisponible.</p>`}</div>
        <a class="ref-start__link" href="/references/${encodeURIComponent(slug)}?version=${encodeURIComponent(wanted)}" target="_blank" rel="noopener">Voir l'évolution de la référence</a>`;
      updateButtons();
    } catch (err) {
      if (token === previewToken) {
        preview.innerHTML = "";
        showError(err);
      }
    }
  }

  function go() {
    const mp = microprojectSlug();
    if (!mp || !chosen || !chosen.number) return;
    window.location.href = builderUrl(mp, { reference: chosen.slug, version: chosen.number });
  }

  function blank() {
    const mp = microprojectSlug();
    if (!mp) return;
    if (options.onBlank) {
      dialog.close();
      options.onBlank(mp);
    } else {
      window.location.href = builderUrl(mp, null);
    }
  }

  async function loadMicroprojects() {
    const group = dialog.querySelector("#ref-start-mp-group");
    const select = dialog.querySelector("#ref-start-mp");
    group.hidden = Boolean(options.microprojectSlug);
    if (options.microprojectSlug) return;
    select.innerHTML = `<option value="">Chargement…</option>`;
    const mine = (await microprojectsApi.list()).filter((mp) => mp.can_edit);
    select.innerHTML = mine.length
      ? `<option value="">Choisir un µprojet…</option>` +
        mine.map((mp) => `<option value="${escapeHtml(mp.slug)}">${escapeHtml(mp.code ? `${mp.code} · ${mp.name}` : mp.name)}</option>`).join("")
      : `<option value="">Aucun µprojet où vous pouvez lancer une étude</option>`;
    if (mine.length === 1) select.value = mine[0].slug;
  }

  async function open(opts = {}) {
    if (!dialog) build();
    options = opts;
    chosen = null;
    previewToken++;
    showError(null);
    dialog.querySelector("#ref-start-intro").textContent =
      opts.intro || "La plupart des expériences partent d'une structure de référence : choisissez-la, sa dernière version est proposée. L'étude retiendra la version dont elle part.";
    dialog.querySelector("#ref-start-search").value = "";
    dialog.querySelector("#ref-start-wafers").hidden = !opts.onWafers;
    dialog.querySelector("#ref-start-preview").innerHTML = `<p class="help">Choisissez une référence : sa dernière version est proposée.</p>`;
    dialog.querySelector("#ref-start-options").innerHTML = `<li class="ref-start__empty"><div class="skeleton" style="height:16px;"></div></li>`;
    updateButtons();
    dialog.showModal();
    try {
      await Promise.all([loadMicroprojects(), loadReferences("")]);
      updateButtons();
      if (opts.reference) await choose(opts.reference, opts.version || null);
      else dialog.querySelector("#ref-start-search").focus();
    } catch (err) {
      showError(err);
    }
  }

  return { open };
})();
