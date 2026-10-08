/* « D'où part la nouvelle étude ? » (global `StudyStart`) : le premier choix de « Nouvelle
   expérience », sur la page d'un µprojet. Trois cas, toujours la même idée :

   - depuis la référence (sa dernière version proposée - references/static/start-picker.js, via
     `onReference`) ;
   - depuis une plaque : la meilleure plaque d'une étude du µprojet, choisie à la main - la structure
     de sa variante, sur de nouvelles plaques (le constructeur, ?etude=&etude-version=&place=) ;
   - en combinant des études « au marché » : 2 à 4 sources (une plaque d'une étude, ou une version de
     référence), puis, brique par brique (alignées par leur nom), d'où vient chacune - le
     constructeur s'ouvre sur la structure assemblée (?composition=).

   Les autres départs (dessiner de zéro, une image, sans structure, la bibliothèque, des plaques
   existantes) restent derrière « Autres départs » (`onOthers`).

     StudyStart.open({microprojectSlug, intro?, onReference?, onOthers?})

   Le constructeur réutilise `StudyStart.composeSources(slug, sources, choices)` pour reconstruire
   la combinaison qu'on lui passe dans l'adresse. */

const StudyStart = (() => {
  let dialog = null;
  let options = {};
  let studies = null; // les études du µprojet (une promesse), pour les deux derniers cas
  let references = null; // les références publiées (une promesse)
  const details = new Map(); // `${id}` -> la fiche d'une étude (une promesse)
  const variantsOf = new Map(); // `${id}@${version}` -> ses variantes (une promesse)

  // place : {experimentId, versionId, place} ; compose : les sources et le résultat de la combinaison
  let placeChoice = null;
  let placeStudy = null;
  let sources = [];
  let composed = null; // {rows, process, warnings, choices}
  let composeToken = 0;

  const referencesOn = () => typeof referencesApi !== "undefined" && pluginEnabled("references");

  function builderUrl(slug, params) {
    return `/microprojets/${encodeURIComponent(slug)}/structures/nouvelle?${new URLSearchParams(params).toString()}`;
  }

  // -- données ------------------------------------------------------------------------------------

  function loadStudies() {
    if (!studies) {
      studies = experimentsApi
        .list(options.microprojectSlug, { limit: 200 })
        .then((page) => page.items || [])
        .catch(() => []);
    }
    return studies;
  }

  function loadReferences() {
    if (!references) {
      references = referencesOn()
        ? referencesApi
            .list()
            .then((items) => items.filter((ref) => ref.latest_version))
            .catch(() => [])
        : Promise.resolve([]);
    }
    return references;
  }

  function detailOf(slug, experimentId) {
    const key = `${slug}/${experimentId}`;
    if (!details.has(key)) details.set(key, experimentsApi.get(slug, experimentId));
    return details.get(key);
  }

  function variantsFor(slug, detail) {
    const key = `${slug}/${detail.id}@${detail.version_id}`;
    if (!variantsOf.has(key)) variantsOf.set(key, experimentsApi.variants(slug, detail.id, detail.version_id).catch(() => null));
    return variantsOf.get(key);
  }

  // Les places d'une étude, telles qu'on les choisit : [{place, sample_id, label, values, svg,
  // witness}] - le libellé de sa variante (campagne) ou son rôle (étude simple), et la plaque témoin
  // (une répétition de la référence) marquée : on n'en part pas.
  async function placesOf(slug, detail) {
    const tracking = detail.physical_tracking && detail.physical_tracking.length ? detail.physical_tracking : [{}];
    const witness = detail.reference_repeat ? detail.reference_repeat.place : -1;
    const variation = detail.is_batch ? await variantsFor(slug, detail) : null;
    return tracking.map((entry, place) => {
      if (place === witness) {
        return { place, sample_id: entry.sample_id || "", label: "Témoin", values: `Réf. ${detail.reference_repeat.reference} ${detail.reference_repeat.version}`, svg: "", witness: true };
      }
      if (detail.is_batch) {
        const labels = (variation && variation.labels) || [];
        const values = variation && variation.factor_values && variation.factor_values[place];
        return {
          place,
          sample_id: entry.sample_id || "",
          label: place === detail.reference_place ? "Référence" : `Variante ${place + 1}`,
          values: values ? values.map((v, j) => `${(variation.factor_labels || [])[j] || ""} ${formatParamValue(v)}`.trim()).join(" · ") : labels[place] || "",
          svg: (variation && variation.svgs && variation.svgs[place]) || "",
          witness: false,
        };
      }
      return { place, sample_id: entry.sample_id || "", label: tracking.length > 1 ? `Plaque ${place + 1}` : "Plaque", values: "", svg: detail.structure_svg || "", witness: false };
    });
  }

  // Le procédé d'une source (celui de la variante de sa plaque, pour une campagne ; celui d'une
  // version de référence), au format éditable - ce que POST /api/compositions assemble.
  async function sourceProcess(slug, source) {
    if (source.kind === "reference") {
      const version = await referencesApi.version(source.reference, source.version);
      if (!version.process) throw new Error(`La référence « ${source.label} » n'a pas de procédé dessiné.`);
      return version.process;
    }
    const detail = source.version_id ? await experimentsApi.getVersion(slug, source.experiment_id, source.version_id) : await detailOf(slug, source.experiment_id);
    const variant = detail.is_batch && source.place !== null && source.place !== undefined ? source.place : undefined;
    try {
      return await experimentsApi.process(slug, source.experiment_id, detail.version_id, variant);
    } catch (err) {
      if (err.status === 404) throw new Error(`« ${source.label} » est donnée en images ou sans structure : elle n'a pas de briques à reprendre.`);
      throw err;
    }
  }

  // Les procédés des sources, puis la combinaison (les choix par défaut sans `choices`).
  async function composeSources(slug, chosenSources, choices) {
    const processes = await Promise.all(chosenSources.map((source) => sourceProcess(slug, source)));
    return structuresApi.compose({ sources: processes, choices: choices || null });
  }

  // -- la boîte -----------------------------------------------------------------------------------

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "ref-dialog ref-dialog--wide study-start";
    dialog.setAttribute("aria-labelledby", "study-start-title");
    dialog.innerHTML = `
      <div class="card-pad ref-dialog__inner">
        <div class="study-start__head">
          <button class="btn-link-secondary study-start__back" type="button" id="study-start-back" hidden>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
            Les trois départs
          </button>
          <h2 class="ref-dialog__title" id="study-start-title">D'où part la nouvelle étude ?</h2>
          <p class="help ref-dialog__lead" id="study-start-lead"></p>
        </div>
        <div class="error" role="alert" id="study-start-error" hidden></div>
        <div id="study-start-body"></div>
        <div class="ref-dialog__actions ref-dialog__actions--split" id="study-start-actions"></div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("#study-start-back").addEventListener("click", showChoice);
    dialog.addEventListener("click", onClick);
    dialog.addEventListener("change", onChange);
  }

  function showError(err) {
    const box = dialog.querySelector("#study-start-error");
    box.textContent = err ? err.message || String(err) : "";
    box.hidden = !err;
  }

  function setView({ title, lead, body, actions, back }) {
    showError(null);
    dialog.querySelector("#study-start-title").textContent = title;
    dialog.querySelector("#study-start-lead").innerHTML = lead;
    dialog.querySelector("#study-start-body").innerHTML = body;
    dialog.querySelector("#study-start-actions").innerHTML = actions;
    dialog.querySelector("#study-start-back").hidden = !back;
  }

  // Le petit empilement d'un cas : une couche par brique, la couleur dit d'où elle vient.
  function stackHtml(origins) {
    return `<span class="study-start-card__stack" aria-hidden="true">${origins.map((o) => `<span class="study-start-card__layer is-${o}"></span>`).join("")}</span>`;
  }

  // -- 1. les trois cas ---------------------------------------------------------------------------

  function showChoice() {
    const refs = referencesOn();
    setView({
      title: "D'où part la nouvelle étude ?",
      lead: options.intro ? escapeHtml(options.intro) : "Toujours la même idée : on repart de la référence, de la meilleure plaque d'une étude, ou de plusieurs études combinées.",
      body: `
        <div class="study-start-cards">
          ${
            refs
              ? `<button class="study-start-card" type="button" data-start="reference">
                   ${stackHtml(["ref", "ref", "ref", "ref"])}
                   <span class="study-start-card__title">Depuis la référence</span>
                   <span class="study-start-card__desc">On repart de la structure de référence, dans sa dernière version.</span>
                 </button>`
              : ""
          }
          <button class="study-start-card" type="button" data-start="place">
            ${stackHtml(["a", "a", "a", "a"])}
            <span class="study-start-card__title">Depuis une plaque</span>
            <span class="study-start-card__desc">La meilleure plaque d'une étude : on reprend sa structure, sur de nouvelles plaques.</span>
          </button>
          <button class="study-start-card" type="button" data-start="compose">
            ${stackHtml(["ref", "a", "b", "a"])}
            <span class="study-start-card__title">Combiner des études</span>
            <span class="study-start-card__desc">Comme au marché : la zone active de l'une, l'EBL d'une autre, le p-GaN d'une troisième.</span>
          </button>
        </div>
        <p class="help study-start__note">Dans les trois cas, l'écran du split propose d'inclure une répétition exacte de la dernière version connue de la référence. Pour faire d'autres tests sur les mêmes plaques, utilisez le « + » d'une étude dans l'arbre.</p>`,
      actions: `
        <span class="ref-dialog__actions">${options.onOthers ? `<button class="btn-link-secondary" type="button" data-action="others">Autres départs : dessiner, image, sans structure, bibliothèque, plaques existantes</button>` : ""}</span>
        <span class="ref-dialog__actions"><button class="btn btn-line" type="button" data-action="close">Annuler</button></span>`,
      back: false,
    });
    const first = dialog.querySelector(".study-start-card");
    if (first) first.focus();
  }

  // -- 2. depuis une plaque -----------------------------------------------------------------------

  async function showPlace() {
    placeChoice = null;
    placeStudy = null;
    setView({
      title: "Depuis une plaque",
      lead: "Choisissez l'étude, puis la plaque que vous retenez : la nouvelle étude part de sa structure (sa variante, pour une campagne), sur de nouvelles plaques, et descend de cette étude.",
      body: `
        <div class="study-start-place">
          <div class="study-start-place__studies">
            <label for="study-start-search">Étude</label>
            <input class="field" id="study-start-search" type="search" placeholder="Chercher une étude" autocomplete="off">
            <ul class="ref-start__options" id="study-start-studies" role="listbox" aria-label="Études du µprojet"><li class="ref-start__empty">Chargement…</li></ul>
          </div>
          <div class="study-start-place__wafers" id="study-start-wafers" aria-live="polite">
            <p class="help">Choisissez une étude : ses plaques s'affichent ici.</p>
          </div>
        </div>`,
      actions: `
        <span></span>
        <span class="ref-dialog__actions">
          <button class="btn btn-line" type="button" data-action="close">Annuler</button>
          <button class="btn btn-primary" type="button" data-action="go-place" disabled>Partir de cette plaque</button>
        </span>`,
      back: true,
    });
    dialog.querySelector("#study-start-search").addEventListener("input", paintStudyList);
    await paintStudyList();
    dialog.querySelector("#study-start-search").focus();
  }

  async function paintStudyList() {
    const list = dialog.querySelector("#study-start-studies");
    if (!list) return;
    const needle = (dialog.querySelector("#study-start-search").value || "").trim().toLowerCase();
    const items = (await loadStudies()).filter((s) => !needle || `${s.title} ${s.id}`.toLowerCase().includes(needle));
    if (!dialog.querySelector("#study-start-studies")) return;
    list.innerHTML = items.length
      ? items
          .map(
            (s) => `<li class="ref-start__option" role="option" tabindex="0" aria-selected="${placeStudy === s.id}" data-study="${escapeHtml(s.id)}">
                      <span class="ref-start__name">${escapeHtml(s.title)}</span>
                      <span class="ref-start__meta mono">${escapeHtml(s.id)}</span>
                    </li>`
          )
          .join("")
      : `<li class="ref-start__empty">Aucune étude${needle ? " pour cette recherche" : " dans ce µprojet"}.</li>`;
  }

  async function chooseStudy(experimentId) {
    placeStudy = experimentId;
    placeChoice = null;
    updatePlaceButton();
    dialog.querySelectorAll("#study-start-studies [data-study]").forEach((li) => li.setAttribute("aria-selected", String(li.dataset.study === experimentId)));
    const host = dialog.querySelector("#study-start-wafers");
    host.innerHTML = `<p class="help">Chargement des plaques…</p>`;
    try {
      const slug = options.microprojectSlug;
      const detail = await detailOf(slug, experimentId);
      if (placeStudy !== experimentId) return;
      if (!detail.has_editable_process) {
        host.innerHTML = `<p class="help">« ${escapeHtml(detail.title)} » est donnée en images ou sans structure : il n'y a pas de structure dessinée à reprendre. Partez de la référence, ou dessinez la structure (« Autres départs »).</p>`;
        return;
      }
      const places = await placesOf(slug, detail);
      if (placeStudy !== experimentId) return;
      host.innerHTML = `
        <div class="study-start__subtitle">${escapeHtml(detail.title)} <span class="help">· ${places.length} plaque${places.length > 1 ? "s" : ""}</span></div>
        <div class="study-start-wafers" role="radiogroup" aria-label="Plaque de départ">
          ${places
            .map(
              (p) => `<label class="study-start-wafer${p.witness ? " is-disabled" : ""}">
                        <input type="radio" name="study-start-place" value="${p.place}"${p.witness ? " disabled" : ""}>
                        ${p.svg ? `<span class="study-start-wafer__thumb">${p.svg}</span>` : ""}
                        <span class="study-start-wafer__body">
                          <span class="study-start-wafer__mark mono">${escapeHtml(p.sample_id || "à associer")}</span>
                          <span class="study-start-wafer__label">${escapeHtml(p.label)}${p.values ? ` · <span class="mono">${escapeHtml(p.values)}</span>` : ""}</span>
                          ${p.witness ? `<span class="help">La répétition de la référence : partez plutôt de la référence.</span>` : ""}
                        </span>
                      </label>`
            )
            .join("")}
        </div>`;
      host.dataset.versionId = detail.version_id;
      // une seule plaque utilisable : choisie d'office
      const usable = places.filter((p) => !p.witness);
      if (usable.length === 1) {
        host.querySelector(`input[value="${usable[0].place}"]`).checked = true;
        placeChoice = { experimentId, versionId: detail.version_id, place: usable[0].place };
        updatePlaceButton();
      }
    } catch (err) {
      host.innerHTML = "";
      showError(err);
    }
  }

  function updatePlaceButton() {
    const go = dialog.querySelector('[data-action="go-place"]');
    if (go) go.disabled = !placeChoice;
  }

  function goPlace() {
    if (!placeChoice) return;
    window.location.href = builderUrl(options.microprojectSlug, {
      etude: placeChoice.experimentId,
      "etude-version": placeChoice.versionId,
      place: String(placeChoice.place),
    });
  }

  // -- 3. combiner au marché ----------------------------------------------------------------------

  async function showCompose() {
    sources = [{ kind: "study" }, { kind: "study" }];
    composed = null;
    setView({
      title: "Combiner des études",
      lead: "Choisissez les sources - la première donne l'ordre des couches et la filiation - puis, étape par étape (ou brique par brique, d'un clic), d'où vient chacune. Une étape d'une autre source peut s'ajouter, ou en remplacer une.",
      body: `
        <div class="study-compose__sources" id="study-compose-sources"></div>
        <div class="study-compose__more">
          <button class="btn btn-tint" type="button" data-action="add-source">+ Ajouter une source</button>
          <button class="btn btn-line" type="button" data-action="compose">Voir les étapes</button>
        </div>
        <div class="study-compose__result" id="study-compose-result" aria-live="polite"></div>`,
      actions: `
        <span></span>
        <span class="ref-dialog__actions">
          <button class="btn btn-line" type="button" data-action="close">Annuler</button>
          <button class="btn btn-primary" type="button" data-action="go-compose" disabled>Ouvrir dans le constructeur</button>
        </span>`,
      back: true,
    });
    await paintSources();
  }

  async function paintSources() {
    const [items, refs] = await Promise.all([loadStudies(), loadReferences()]);
    const host = dialog.querySelector("#study-compose-sources");
    if (!host) return;
    const rows = await Promise.all(sources.map((source, i) => sourceRowHtml(source, i, items, refs)));
    host.innerHTML = rows.join("");
    dialog.querySelector('[data-action="add-source"]').hidden = sources.length >= 4;
  }

  async function sourceRowHtml(source, index, items, refs) {
    const slug = options.microprojectSlug;
    const kindSelect = refs.length
      ? `<select class="field study-compose__kind" data-source="${index}" data-field="kind" aria-label="Type de la source ${index + 1}">
           <option value="study"${source.kind === "study" ? " selected" : ""}>Une plaque d'une étude</option>
           <option value="reference"${source.kind === "reference" ? " selected" : ""}>Une version de référence</option>
         </select>`
      : "";
    let fields;
    if (source.kind === "reference") {
      let versionOptions = `<option value="">-</option>`;
      if (source.reference) {
        const graph = await referencesApi.versions(source.reference).catch(() => null);
        const numbers = graph ? graph.nodes.map((n) => n.number) : [];
        if (!source.version && numbers.length) source.version = numbers[numbers.length - 1];
        versionOptions = numbers
          .map((n, i) => `<option value="${escapeHtml(n)}"${n === source.version ? " selected" : ""}>${escapeHtml(n)}${i === numbers.length - 1 ? " (dernière)" : ""}</option>`)
          .reverse()
          .join("");
      }
      fields = `
        <select class="field" data-source="${index}" data-field="reference" aria-label="Référence de la source ${index + 1}">
          <option value="">- choisir une référence -</option>
          ${refs.map((r) => `<option value="${escapeHtml(r.slug)}"${r.slug === source.reference ? " selected" : ""}>${escapeHtml(r.name)}</option>`).join("")}
        </select>
        <select class="field study-compose__narrow" data-source="${index}" data-field="version" aria-label="Version de la source ${index + 1}">${versionOptions}</select>`;
    } else {
      let placeOptions = `<option value="">-</option>`;
      if (source.experiment_id) {
        const detail = await detailOf(slug, source.experiment_id).catch(() => null);
        if (detail) {
          source.version_id = detail.version_id;
          const places = detail.has_editable_process ? (await placesOf(slug, detail)).filter((p) => !p.witness) : [];
          if ((source.place === undefined || source.place === null) && places.length) source.place = places[0].place;
          placeOptions = places.length
            ? places
                .map((p) => `<option value="${p.place}"${p.place === source.place ? " selected" : ""}>${escapeHtml(p.sample_id || `place ${p.place + 1}`)} · ${escapeHtml(p.label)}${p.values ? ` (${escapeHtml(p.values)})` : ""}</option>`)
                .join("")
            : `<option value="">pas de structure dessinée</option>`;
        }
      }
      fields = `
        <select class="field" data-source="${index}" data-field="experiment_id" aria-label="Étude de la source ${index + 1}">
          <option value="">- choisir une étude -</option>
          ${items.map((s) => `<option value="${escapeHtml(s.id)}"${s.id === source.experiment_id ? " selected" : ""}>${escapeHtml(s.title)}</option>`).join("")}
        </select>
        <select class="field" data-source="${index}" data-field="place" aria-label="Plaque de la source ${index + 1}">${placeOptions}</select>`;
    }
    return `
      <div class="study-compose__source">
        <span class="study-compose__tag is-${index === 0 ? "main" : `s${index}`}">${index === 0 ? "Principale" : `Source ${index + 1}`}</span>
        ${kindSelect}
        ${fields}
        ${index >= 2 ? `<button class="sb-samples-table__remove" type="button" data-action="remove-source" data-source="${index}" aria-label="Retirer la source ${index + 1}" title="Retirer cette source"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg></button>` : ""}
      </div>`;
  }

  // Le libellé d'une source sur la fiche : « Étude · W07 » ou « Référence 1.3 ».
  async function sourceLabel(source) {
    if (source.kind === "reference") {
      const refs = await loadReferences();
      const ref = refs.find((r) => r.slug === source.reference);
      return `${ref ? ref.name : source.reference} ${source.version}`;
    }
    const detail = await detailOf(options.microprojectSlug, source.experiment_id);
    const entry = (detail.physical_tracking || [])[source.place] || {};
    return `${detail.title} · ${entry.sample_id || `plaque ${source.place + 1}`}`;
  }

  function readySources() {
    return sources.every((s) => (s.kind === "reference" ? s.reference && s.version : s.experiment_id && s.place !== null && s.place !== undefined && s.place !== ""));
  }

  async function runCompose(choices) {
    const token = ++composeToken;
    const host = dialog.querySelector("#study-compose-result");
    if (!readySources()) {
      showError(new Error("Choisissez chaque source (l'étude et sa plaque, ou la référence et sa version)."));
      return;
    }
    showError(null);
    host.innerHTML = `<p class="help">Lecture des étapes…</p>`;
    try {
      const labelled = await Promise.all(sources.map(async (s) => ({ ...s, label: await sourceLabel(s) })));
      const result = await composeSources(options.microprojectSlug, labelled, choices);
      if (token !== composeToken) return;
      composed = { ...result, sources: labelled, choices: result.rows.map((r) => ({ source: r.chosen, replaces: r.replaces })) };
      paintMarket();
    } catch (err) {
      if (token !== composeToken) return;
      composed = null;
      host.innerHTML = "";
      showError(err);
    }
    dialog.querySelector('[data-action="go-compose"]').disabled = !composed;
  }

  // Les lignes regroupées par brique (les étapes consécutives d'une même brique ; hors brique, une
  // à une) : [{brick, rows: [index...]}].
  function rowGroups(rows) {
    const groups = [];
    rows.forEach((row, r) => {
      const last = groups[groups.length - 1];
      if (row.brick && last && last.brick === row.brick) last.rows.push(r);
      else groups.push({ brick: row.brick, rows: [r] });
    });
    return groups;
  }

  // Une brique dépliée d'office quand ses étapes ne viennent pas toutes de la même source, ou
  // qu'une source y a une étape différente ou en plus ; sinon repliée (une ligne, un choix).
  const expandedBricks = new Set();
  function isExpanded(group, rows) {
    const key = `${group.brick}@${rows[group.rows[0]].key}`;
    if (expandedBricks.has(key)) return true;
    if (expandedBricks.has(`-${key}`)) return false;
    const picked = new Set(group.rows.map((r) => rows[r].chosen));
    const differs = group.rows.some((r) => !rows[r].in_main || rows[r].same_as.some((same, i) => same !== null && same !== rows[r].same_as[0]));
    return picked.size > 1 || differs || group.rows.some((r) => rows[r].replaces);
  }

  // Le tableau « au marché » : une ligne par étape, regroupées par brique (une ligne de brique coche
  // toutes ses étapes d'un coup, et se déplie), une colonne par source, un choix par ligne.
  function paintMarket() {
    const host = dialog.querySelector("#study-compose-result");
    const { rows, sources: labelled, warnings } = composed;
    const replacedBy = new Map(rows.filter((row) => row.replaces).map((row) => [row.replaces, row.name]));
    const header = labelled.map((s, i) => `<th scope="col"><span class="study-compose__tag is-${i === 0 ? "main" : `s${i}`}">${i === 0 ? "Principale" : `Source ${i + 1}`}</span><span class="study-compose__source-name">${escapeHtml(s.label)}</span></th>`).join("");

    const stepRow = (row, r, nested) => {
      const replaced = replacedBy.get(row.key);
      const cells = labelled
        .map((_, i) => {
          if (!row.present[i]) return `<td class="study-compose__absent">-</td>`;
          const same = i > 0 && row.same_as[i] === 0;
          const value = same ? `<span class="help study-compose__same">= principale</span>` : row.summary[i] ? `<span class="study-compose__value mono">${escapeHtml(row.summary[i])}</span>` : "";
          const differs = i > 0 && row.present[0] && row.same_as[i] !== 0 ? `<span class="study-compose__diff" title="Différente de celle de la principale">≠</span>` : "";
          return `<td><label class="study-compose__pick"><input type="radio" name="compose-row-${r}" value="${i}" data-row="${r}"${row.chosen === i ? " checked" : ""}${replaced ? " disabled" : ""} aria-label="${escapeHtml(row.name)} depuis ${escapeHtml(labelled[i].label)}">${value}${differs}</label></td>`;
        })
        .join("");
      const none =
        row.key === "substrat"
          ? `<td></td>`
          : `<td><label class="study-compose__pick"><input type="radio" name="compose-row-${r}" value="" data-row="${r}"${row.chosen === null || replaced ? " checked" : ""}${replaced ? " disabled" : ""} aria-label="${escapeHtml(row.name)} non reprise"></label></td>`;
      // une étape ajoutée, reprise : elle peut prendre la place d'une étape de la principale
      const targets = rows.filter((other) => other.in_main && other.key !== "substrat" && other.key !== row.key && (!replacedBy.has(other.key) || other.key === row.replaces));
      const replaceSelect =
        !row.in_main && row.chosen !== null
          ? `<select class="field study-compose__replace" data-replaces="${r}" aria-label="Étape que « ${escapeHtml(row.name)} » remplace">
               <option value="">en plus</option>
               ${targets.map((other) => `<option value="${escapeHtml(other.key)}"${row.replaces === other.key ? " selected" : ""}>remplace ${escapeHtml(other.name)}${other.brick ? ` (${escapeHtml(other.brick)})` : ""}</option>`).join("")}
             </select>`
          : "";
      const tags = [
        !row.in_main && row.key !== "substrat" ? `<span class="study-compose__tag-step is-added">ajoutée</span>` : "",
        replaced ? `<span class="study-compose__tag-step is-replaced">remplacée par ${escapeHtml(replaced)}</span>` : "",
      ].join("");
      return `<tr class="${nested ? "is-nested" : ""}${replaced ? " is-replaced" : ""}"><th scope="row"><span class="study-compose__step">${escapeHtml(row.name)}</span>${tags}${replaceSelect}</th>${cells}${none}</tr>`;
    };

    const body = rowGroups(rows)
      .map((group, g) => {
        if (!group.brick) return group.rows.map((r) => stepRow(rows[r], r, false)).join("");
        const open = isExpanded(group, rows);
        const picks = new Set(group.rows.map((r) => rows[r].chosen));
        const brickCells = labelled
          .map((_, i) => {
            const has = group.rows.some((r) => rows[r].present[i]);
            if (!has) return `<td class="study-compose__absent">-</td>`;
            const all = picks.size === 1 && picks.has(i);
            return `<td><label class="study-compose__pick"><input type="radio" name="compose-brick-${g}" value="${i}" data-group="${g}"${all ? " checked" : ""} aria-label="Toute la brique ${escapeHtml(group.brick)} depuis ${escapeHtml(labelled[i].label)}">${picks.size > 1 && picks.has(i) ? `<span class="help study-compose__same">en partie</span>` : ""}</label></td>`;
          })
          .join("");
        const noneAll = picks.size === 1 && picks.has(null);
        const head = `<tr class="study-compose__brick"><th scope="row">
            <button class="study-compose__toggle" type="button" data-action="toggle-brick" data-group="${g}" aria-expanded="${open}">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="${open ? "M6 9l6 6 6-6" : "M9 6l6 6-6 6"}"/></svg>
              ${escapeHtml(group.brick)}
            </button>
            <span class="help">${group.rows.length} étape${group.rows.length > 1 ? "s" : ""}</span>
          </th>${brickCells}<td><label class="study-compose__pick"><input type="radio" name="compose-brick-${g}" value="" data-group="${g}"${noneAll ? " checked" : ""} aria-label="Brique ${escapeHtml(group.brick)} non reprise"></label></td></tr>`;
        return head + (open ? group.rows.map((r) => stepRow(rows[r], r, true)).join("") : "");
      })
      .join("");
    host.innerHTML = `
      <div class="study-compose__table-wrap">
        <table class="study-compose__table">
          <thead><tr><th scope="col">Étape</th>${header}<th scope="col">Non reprise</th></tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      ${warnings.length ? `<ul class="study-compose__warnings">${warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join("")}</ul>` : ""}
      <p class="help">Une même étape (même identifiant, ou même nom dans la même brique) est une seule ligne. Une étape « ajoutée » se place avant celle qui la suit dans sa source, ou à la place d'une étape de la principale (« remplace… »). Tout reste modifiable dans le constructeur.</p>`;
  }

  function goCompose() {
    if (!composed) return;
    const payload = {
      sources: composed.sources.map((s) =>
        s.kind === "reference"
          ? { kind: "reference", label: s.label, reference: s.reference, version: s.version }
          : { kind: "study", label: s.label, experiment_id: s.experiment_id, version_id: s.version_id || null, place: Number(s.place) }
      ),
      choices: composed.choices,
    };
    window.location.href = builderUrl(options.microprojectSlug, { composition: JSON.stringify(payload) });
  }

  // -- événements ---------------------------------------------------------------------------------

  function onClick(event) {
    const start = event.target.closest("[data-start]");
    if (start) {
      if (start.dataset.start === "reference") {
        dialog.close();
        if (options.onReference) options.onReference();
      } else if (start.dataset.start === "place") {
        showPlace();
      } else {
        showCompose();
      }
      return;
    }
    const study = event.target.closest("[data-study]");
    if (study) {
      chooseStudy(study.dataset.study);
      return;
    }
    const action = event.target.closest("[data-action]");
    if (!action) return;
    switch (action.dataset.action) {
      case "close":
        dialog.close();
        break;
      case "others":
        dialog.close();
        options.onOthers();
        break;
      case "go-place":
        goPlace();
        break;
      case "add-source":
        sources.push({ kind: "study" });
        invalidateComposition();
        paintSources();
        break;
      case "remove-source":
        sources.splice(parseInt(action.dataset.source, 10), 1);
        invalidateComposition();
        paintSources();
        break;
      case "compose":
        runCompose(null);
        break;
      case "go-compose":
        goCompose();
        break;
      case "toggle-brick": {
        const group = rowGroups(composed.rows)[parseInt(action.dataset.group, 10)];
        const key = `${group.brick}@${composed.rows[group.rows[0]].key}`;
        const open = isExpanded(group, composed.rows);
        expandedBricks.delete(key);
        expandedBricks.delete(`-${key}`);
        expandedBricks.add(open ? `-${key}` : key);
        paintMarket();
        const again = dialog.querySelector(`[data-action="toggle-brick"][data-group="${action.dataset.group}"]`);
        if (again) again.focus();
        break;
      }
      default:
        break;
    }
  }

  function invalidateComposition() {
    composed = null;
    composeToken++;
    const host = dialog.querySelector("#study-compose-result");
    if (host) host.innerHTML = "";
    const go = dialog.querySelector('[data-action="go-compose"]');
    if (go) go.disabled = true;
  }

  function onChange(event) {
    const target = event.target;
    if (target.name === "study-start-place") {
      const host = dialog.querySelector("#study-start-wafers");
      placeChoice = { experimentId: placeStudy, versionId: host.dataset.versionId, place: parseInt(target.value, 10) };
      updatePlaceButton();
      return;
    }
    if (target.dataset.row !== undefined && composed) {
      const r = parseInt(target.dataset.row, 10);
      const source = target.value === "" ? null : parseInt(target.value, 10);
      composed.choices[r] = { source, replaces: source === null ? null : composed.choices[r].replaces };
      // l'aperçu se recalcule (le serveur revérifie les choix)
      runCompose(composed.choices.map((c) => ({ ...c })));
      return;
    }
    if (target.dataset.group !== undefined && composed) {
      // toute une brique : chacune de ses étapes depuis cette source (celles qu'elle a), ou aucune
      const group = rowGroups(composed.rows)[parseInt(target.dataset.group, 10)];
      const source = target.value === "" ? null : parseInt(target.value, 10);
      group.rows.forEach((r) => {
        if (source === null) composed.choices[r] = { source: null, replaces: null };
        else if (composed.rows[r].present[source]) composed.choices[r] = { ...composed.choices[r], source };
      });
      runCompose(composed.choices.map((c) => ({ ...c })));
      return;
    }
    if (target.dataset.replaces !== undefined && composed) {
      const r = parseInt(target.dataset.replaces, 10);
      composed.choices[r] = { ...composed.choices[r], replaces: target.value || null };
      runCompose(composed.choices.map((c) => ({ ...c })));
      return;
    }
    if (target.dataset.source !== undefined && target.dataset.field) {
      const source = sources[parseInt(target.dataset.source, 10)];
      const field = target.dataset.field;
      if (field === "kind") {
        sources[parseInt(target.dataset.source, 10)] = { kind: target.value };
      } else if (field === "place") {
        source.place = target.value === "" ? null : parseInt(target.value, 10);
      } else {
        source[field] = target.value || null;
        if (field === "experiment_id") {
          source.place = null;
          source.version_id = null;
        }
        if (field === "reference") source.version = null;
      }
      invalidateComposition();
      paintSources();
    }
  }

  function open(opts) {
    options = opts || {};
    studies = null;
    details.clear();
    variantsOf.clear();
    if (!dialog) build();
    showChoice();
    if (!dialog.open) dialog.showModal();
  }

  return { open, composeSources };
})();
