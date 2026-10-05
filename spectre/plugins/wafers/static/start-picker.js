/* « Partir de plaques existantes » (global `WaferStartPicker`) : une nouvelle expérience qui reprend
   une ou plusieurs plaques déjà suivies. On cherche les plaques (lasermark ou FDL ; sans recherche,
   celles du µprojet), on en coche une ou plusieurs ; la boîte cherche l'étude qui les suit toutes
   (leur passeport, GET /api/wafers/{key}) - sa structure est la leur - et la montre. Plusieurs
   plaques sont des réplicats : elles partent d'une même structure (une même étude simple, ou une
   seule variante d'une campagne) ; sinon la boîte dit pourquoi et ne lance rien (le serveur refuse
   de même). Le constructeur s'ouvre ensuite avec cette structure et ces plaques
   (structures/static/builder : ?plaque=…&depuis-mp=…&depuis-etude=…&depuis-version=…), et
   l'étude lancée retient d'où elles viennent (`wafer_origin`) :

     WaferStartPicker.open({microprojectSlug})

   Une plaque n'est lisible que dans les µprojets dont on est membre : celle qui n'est suivie
   qu'ailleurs se coche, mais ne peut pas servir de départ. Dépend de wafersApi, experimentsApi,
   waferKey (fdl.js) et statusBadgeHtml (experiments/static/status.js). */

const WaferStartPicker = (() => {
  const MAX_RESULTS = 60;
  let dialog = null;
  let options = {};
  let results = []; // les plaques listées (wafersApi.list)
  let selected = new Map(); // clé -> {lasermark, passport | null, error}
  let candidates = []; // les études qui suivent toutes les plaques cochées (computeCandidates)
  let chosen = null; // la clé de l'étude de départ retenue
  const previews = new Map(); // étude (et variante) -> SVG de sa structure, lu une fois
  let searchTimer = null;
  let searchToken = 0;
  let previewToken = 0;

  function builderUrl(microprojectSlug, candidate) {
    const params = new URLSearchParams();
    for (const { lasermark } of selected.values()) params.append("plaque", lasermark);
    params.set("depuis-mp", candidate.microproject.slug);
    params.set("depuis-etude", candidate.experiment.id);
    params.set("depuis-version", candidate.experiment.version_id);
    return `/microprojets/${encodeURIComponent(microprojectSlug)}/structures/nouvelle?${params.toString()}`;
  }

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "wafer-dialog";
    dialog.setAttribute("aria-labelledby", "wafer-start-title");
    dialog.innerHTML = `
      <div class="card-pad wafer-dialog__inner">
        <h2 class="wafer-dialog__title" id="wafer-start-title">Partir de plaques existantes</h2>
        <p class="help wafer-dialog__lead">Cochez une ou plusieurs plaques déjà suivies : la nouvelle expérience reprend leur structure actuelle - celle de l'étude qui les suit - et les suit à son tour. Plusieurs plaques sont des réplicats : elles doivent partir de la même structure.</p>
        <div class="error" role="alert" id="wafer-start-error" hidden></div>
        <div class="wafer-start">
          <div class="wafer-start__list">
            <label for="wafer-start-search">Plaques</label>
            <input class="field" id="wafer-start-search" type="search" placeholder="Lasermark ou FDL" autocomplete="off">
            <div class="wafer-start__scope help" id="wafer-start-scope" aria-live="polite"></div>
            <ul class="wafer-start__options" id="wafer-start-options" role="listbox" aria-multiselectable="true" aria-label="Plaques"></ul>
          </div>
          <div class="wafer-start__side" aria-live="polite">
            <div class="section-title">Plaques choisies</div>
            <ul class="wafer-start__chips" id="wafer-start-chips"></ul>
            <div class="section-title wafer-start__origin-title">Structure de départ</div>
            <div class="wafer-start__origin" id="wafer-start-origin"></div>
          </div>
        </div>
        <div class="wafer-dialog__actions">
          <button class="btn btn-line" type="button" id="wafer-start-cancel">Annuler</button>
          <button class="btn btn-primary" type="button" id="wafer-start-go" disabled>Partir de ces plaques</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("#wafer-start-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelector("#wafer-start-search").addEventListener("input", (event) => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadResults(event.target.value.trim()), 200);
    });
    const list = dialog.querySelector("#wafer-start-options");
    list.addEventListener("click", (event) => {
      const option = event.target.closest("[data-key]");
      if (option) toggle(option.dataset.key);
    });
    list.addEventListener("keydown", onOptionsKey);
    dialog.querySelector("#wafer-start-chips").addEventListener("click", (event) => {
      const remove = event.target.closest("[data-remove]");
      if (remove) toggle(remove.dataset.remove);
    });
    dialog.querySelector("#wafer-start-origin").addEventListener("change", (event) => {
      if (event.target.id === "wafer-start-study") {
        chosen = event.target.value;
        renderOrigin();
      }
    });
    dialog.querySelector("#wafer-start-go").addEventListener("click", go);
  }

  function showError(err) {
    const box = dialog.querySelector("#wafer-start-error");
    box.textContent = err ? err.message || String(err) : "";
    box.hidden = !err;
  }

  // -- la liste des plaques -----------------------------------------------------------------------

  function microprojectLabel(mp) {
    return mp.code || mp.name;
  }

  // Où la plaque est suivie, telle que le lecteur la voit : l'étude la plus récente (titre et
  // variante pour un membre de son µprojet), et combien d'études la suivent.
  function waferMeta(wafer) {
    const exp = wafer.latest.experiment;
    const parts = [microprojectLabel(exp.microproject)];
    if (exp.member && exp.title) parts.push(exp.title);
    if (wafer.latest.variant) parts.push(`variante ${wafer.latest.variant}`);
    if (wafer.count > 1) parts.push(`${wafer.count} études`);
    return parts.join(" · ");
  }

  function renderResults() {
    const list = dialog.querySelector("#wafer-start-options");
    if (!results.length) {
      const q = dialog.querySelector("#wafer-start-search").value.trim();
      list.innerHTML = `<li class="wafer-start__empty">${q ? "Aucune plaque suivie ne correspond." : "Aucune plaque suivie dans ce µprojet : cherchez-en une par son lasermark ou une FDL."}</li>`;
      return;
    }
    const focused = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.key : null;
    list.innerHTML = results
      .map((wafer, i) => {
        const isSelected = selected.has(wafer.key);
        const tabbable = focused ? focused === wafer.key : i === 0;
        return `
          <li class="wafer-start__option" role="option" tabindex="${tabbable ? 0 : -1}" aria-selected="${isSelected}" data-key="${escapeHtml(wafer.key)}">
            <span class="wafer-start__check" aria-hidden="true">${isSelected ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>` : ""}</span>
            <span class="wafer-start__text">
              <span class="wafer-start__lasermark">${escapeHtml(wafer.lasermark)}</span>
              <span class="wafer-start__meta">${escapeHtml(waferMeta(wafer))}</span>
            </span>
          </li>`;
      })
      .join("");
    if (focused) list.querySelector(`[data-key="${CSS.escape(focused)}"]`)?.focus();
  }

  function onOptionsKey(event) {
    const items = [...dialog.querySelectorAll(".wafer-start__option")];
    const at = items.indexOf(document.activeElement);
    let next = null;
    if (event.key === "ArrowDown") next = items[Math.min(at + 1, items.length - 1)];
    else if (event.key === "ArrowUp") next = items[Math.max(at - 1, 0)];
    else if ((event.key === "Enter" || event.key === " ") && at >= 0) {
      event.preventDefault();
      toggle(items[at].dataset.key);
      return;
    }
    if (!next) return;
    event.preventDefault();
    items.forEach((item) => (item.tabIndex = item === next ? 0 : -1));
    next.focus();
  }

  // Sans recherche : les plaques du µprojet ; sinon celles dont le lasermark ou une FDL correspond
  // (le lasermark d'abord), de tous les µprojets.
  async function loadResults(q) {
    const token = ++searchToken;
    const scope = dialog.querySelector("#wafer-start-scope");
    try {
      let found;
      if (!q) {
        found = await wafersApi.list({ microproject: options.microprojectSlug });
        scope.textContent = "Plaques suivies dans ce µprojet - cherchez pour en trouver ailleurs.";
      } else {
        const [byLasermark, byFdl] = await Promise.all([wafersApi.list({ q }), wafersApi.list({ fdl: q })]);
        const keys = new Set(byLasermark.map((w) => w.key));
        found = [...byLasermark, ...byFdl.filter((w) => !keys.has(w.key))];
        scope.textContent = found.length > MAX_RESULTS ? `Les ${MAX_RESULTS} premières - précisez la recherche.` : "";
      }
      if (token !== searchToken) return;
      results = found.slice(0, MAX_RESULTS);
      renderResults();
    } catch (err) {
      if (token === searchToken) showError(err);
    }
  }

  // -- les plaques choisies et leur étude commune ---------------------------------------------------

  async function toggle(key) {
    showError(null);
    if (selected.has(key)) {
      selected.delete(key);
    } else {
      const wafer = results.find((w) => w.key === key);
      if (!wafer) return;
      selected.set(key, { lasermark: wafer.lasermark, passport: null, error: null });
      wafersApi
        .get(key)
        .then((passport) => {
          const entry = selected.get(key);
          if (entry) entry.passport = passport;
        })
        .catch((err) => {
          const entry = selected.get(key);
          if (entry) entry.error = err;
        })
        .finally(refreshSelection);
    }
    renderResults();
    refreshSelection();
  }

  const studyKey = (occurrence) => {
    const exp = occurrence.experiment;
    return `${exp.microproject.slug}|${exp.id}|${exp.version_id}`;
  };

  // Les études (leur version actuelle) qui suivent toutes les plaques cochées, d'après leurs
  // passeports - celles d'un µprojet dont on est membre : la plus récemment rejointe d'abord. Une
  // campagne n'en est une que si les plaques y portent la même variante (`conflict` sinon).
  function computeCandidates(entries) {
    const byStudy = new Map();
    entries.forEach((entry, index) => {
      for (const occurrence of entry.passport.occurrences.filter((o) => o.experiment.member)) {
        const key = studyKey(occurrence);
        if (!byStudy.has(key)) byStudy.set(key, { key, experiment: occurrence.experiment, microproject: occurrence.experiment.microproject, occurrences: [] });
        const study = byStudy.get(key);
        if (study.occurrences.length === index) study.occurrences.push(occurrence); // une fois par plaque
      }
    });
    return [...byStudy.values()]
      .filter((study) => study.occurrences.length === entries.length)
      .map((study) => {
        const indexes = [...new Set(study.occurrences.map((o) => o.entity_index))];
        return {
          ...study,
          conflict: study.experiment.campaign && indexes.length > 1,
          variant: study.experiment.campaign && indexes.length === 1 ? { index: indexes[0], label: study.occurrences[0].variant } : null,
          since: study.occurrences.map((o) => o.experiment.tracked_since).sort().pop(),
        };
      })
      .sort((a, b) => Number(a.conflict) - Number(b.conflict) || String(b.since).localeCompare(String(a.since)));
  }

  function renderChips() {
    const chips = dialog.querySelector("#wafer-start-chips");
    chips.innerHTML = selected.size
      ? [...selected.entries()]
          .map(
            ([key, entry]) => `
              <li class="wafer-start__chip">
                <span class="mono">${escapeHtml(entry.lasermark)}</span>
                <button type="button" class="wafer-start__chip-remove" data-remove="${escapeHtml(key)}" aria-label="Retirer ${escapeHtml(entry.lasermark)}">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
                </button>
              </li>`
          )
          .join("")
      : `<li class="help">Aucune plaque cochée.</li>`;
  }

  function refreshSelection() {
    renderChips();
    const entries = [...selected.values()];
    candidates = entries.length && entries.every((e) => e.passport) ? computeCandidates(entries) : [];
    if (!candidates.some((c) => c.key === chosen && !c.conflict)) chosen = (candidates.find((c) => !c.conflict) || {}).key || null;
    renderOrigin();
  }

  function setGo(enabled) {
    dialog.querySelector("#wafer-start-go").disabled = !enabled;
  }

  function notice(text) {
    return `<p class="wafer-start__notice">${text}</p>`;
  }

  function names(entries) {
    return entries.map((e) => `<span class="mono">${escapeHtml(e.lasermark)}</span>`).join(", ");
  }

  // Pourquoi les plaques cochées ne peuvent pas partir ensemble - ou l'étude dont elles partent.
  function renderOrigin() {
    const box = dialog.querySelector("#wafer-start-origin");
    const entries = [...selected.values()];
    setGo(false);
    if (!entries.length) {
      box.innerHTML = `<p class="help">Cochez une plaque : la structure qu'elle porte aujourd'hui s'affiche ici.</p>`;
      return;
    }
    const failed = entries.filter((e) => e.error);
    if (failed.length) {
      box.innerHTML = notice(`Impossible de lire le parcours de ${names(failed)} : ${escapeHtml(failed[0].error.message || String(failed[0].error))}`);
      return;
    }
    if (entries.some((e) => !e.passport)) {
      box.innerHTML = `<div class="skeleton" style="height:18px;width:70%;"></div><div class="skeleton" style="height:160px;margin-top:10px;"></div>`;
      return;
    }
    const unreadable = entries.filter((e) => !e.passport.occurrences.some((o) => o.experiment.member));
    if (unreadable.length) {
      const many = unreadable.length > 1;
      box.innerHTML = notice(
        `${names(unreadable)} ${many ? "ne sont suivies" : "n'est suivie"} que dans des µprojets dont vous n'êtes pas membre : ${many ? "leur structure ne vous est pas lisible" : "sa structure ne vous est pas lisible"}. Demandez à en être membre, ou retirez-${many ? "les" : "la"}.`
      );
      return;
    }
    const usable = candidates.filter((c) => !c.conflict);
    if (!usable.length) {
      const campaign = candidates.find((c) => c.conflict);
      box.innerHTML = campaign
        ? notice(
            `${names(entries)} portent des variantes différentes de la campagne « ${escapeHtml(campaign.experiment.title)} » : leurs structures diffèrent. Partez d'une seule de ces plaques, ou de réplicats d'une même structure.`
          )
        : notice(
            `${names(entries)} ne sont suivies par aucune même étude : leurs structures diffèrent. Plusieurs plaques doivent être des réplicats d'une même étude - partez de plaques d'une même étude, ou d'une seule.`
          );
      return;
    }
    const candidate = usable.find((c) => c.key === chosen) || usable[0];
    const sameMicroproject = candidate.microproject.slug === options.microprojectSlug;
    const exp = candidate.experiment;
    const studyUrl = `/microprojets/${encodeURIComponent(candidate.microproject.slug)}/experiences/${encodeURIComponent(exp.id)}`;
    box.innerHTML = `
      ${
        usable.length > 1
          ? `<label class="wafer-start__study-label" for="wafer-start-study">${entries.length > 1 ? "Ces plaques sont suivies" : "Cette plaque est suivie"} par ${usable.length} études - partir de :</label>
             <select class="field" id="wafer-start-study">${usable
               .map((c) => {
                 const where = c.microproject.slug === options.microprojectSlug ? "" : ` (${microprojectLabel(c.microproject)})`;
                 return `<option value="${escapeHtml(c.key)}"${c.key === candidate.key ? " selected" : ""}>${escapeHtml(c.experiment.title + where)}</option>`;
               })
               .join("")}</select>`
          : ""
      }
      <div class="wafer-start__head">
        <a class="wafer-start__study" href="${studyUrl}" target="_blank" rel="noopener">${escapeHtml(exp.title)}</a>
        ${statusBadgeHtml(exp.status)}
      </div>
      <div class="wafer-start__meta">
        ${escapeHtml(microprojectLabel(candidate.microproject))}${candidate.variant && candidate.variant.label ? ` · variante <strong class="mono">${escapeHtml(candidate.variant.label)}</strong>` : ""} · suivie${entries.length > 1 ? "s" : ""} depuis le ${escapeHtml(formatDate(candidate.since))}
      </div>
      <div class="wafer-start__svg" id="wafer-start-svg"><div class="skeleton" style="height:160px;"></div></div>
      <p class="help wafer-start__filiation">${
        sameMicroproject
          ? "La nouvelle expérience descendra de cette étude (filiation, comparaison de structure)."
          : "Étude d'un autre µprojet : la nouvelle expérience en reprend la structure, et sa fiche dira d'où viennent ses plaques (pas de filiation d'un µprojet à l'autre)."
      }${entries.length > 1 ? ` Les ${entries.length} plaques seront suivies comme réplicats.` : ""}</p>`;
    setGo(true);
    loadPreview(candidate);
  }

  // L'aperçu de la structure : celle de la version (le dessin d'une variante pour une campagne).
  async function loadPreview(candidate) {
    const token = ++previewToken;
    const exp = candidate.experiment;
    const mp = candidate.microproject.slug;
    const cacheKey = `${candidate.key}|${candidate.variant ? candidate.variant.index : ""}`;
    try {
      if (!previews.has(cacheKey)) {
        const svg = candidate.variant
          ? ((await experimentsApi.variants(mp, exp.id, exp.version_id)).svgs || [])[candidate.variant.index]
          : (await experimentsApi.getVersion(mp, exp.id, exp.version_id)).structure_svg;
        previews.set(cacheKey, svg || "");
      }
      if (token !== previewToken) return;
      const box = dialog.querySelector("#wafer-start-svg");
      if (box) box.innerHTML = previews.get(cacheKey) || `<p class="help">Structure donnée en images : le constructeur partira du substrat.</p>`;
    } catch (err) {
      if (token !== previewToken) return;
      const box = dialog.querySelector("#wafer-start-svg");
      if (box) box.innerHTML = `<p class="help">Aperçu indisponible.</p>`;
    }
  }

  function go() {
    const candidate = candidates.find((c) => c.key === chosen && !c.conflict);
    if (!candidate || !options.microprojectSlug) return;
    window.location.href = builderUrl(options.microprojectSlug, candidate);
  }

  async function open(opts = {}) {
    if (!dialog) build();
    options = opts;
    selected = new Map();
    candidates = [];
    chosen = null;
    results = [];
    showError(null);
    dialog.querySelector("#wafer-start-search").value = "";
    dialog.querySelector("#wafer-start-options").innerHTML = `<li class="wafer-start__empty"><div class="skeleton" style="height:16px;"></div></li>`;
    refreshSelection();
    dialog.showModal();
    dialog.querySelector("#wafer-start-search").focus();
    await loadResults("");
  }

  return { open };
})();
