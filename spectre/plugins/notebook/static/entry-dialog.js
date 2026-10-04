/* La boîte d'ajout et d'édition d'une donnée du cahier (#notebook-dialog de la fiche).

   1. Le type : PRISM (les mesures des plaques en base, vues par un composant DataViz) ou chargée à
      la main (fixé une fois l'entrée créée).
   2. Les plaques mesurées, parmi celles que suit la version (toutes cochées par défaut) : la donnée
      les suit d'une version à l'autre. Une plaque que la version ne suit plus reste cochable.
   3. Le stepper du procédé : on coche une ou plusieurs bulles, une mesure par bulle (aucune : une
      mesure non située). Quand on coche la première bulle, la mesure non située y passe ; quand on
      décoche la dernière, la mesure redevient non située.
   4. Le contenu de chaque mesure. PRISM : un type de données, « Charger les données » prend un
      instantané pour chaque étape qui n'en a pas (« Recharger » : un nouvel instantané pour l'une),
      et une vue (composant et réglages) commune à toutes les étapes, pour les comparer. À la main :
      valeur et unité, texte, tableau (un tableau copié d'Excel - du TSV - se colle tel quel et
      devient {columns, rows}), images collées ou déposées (attachments/static/image-drop.js : Ctrl+V
      colle dans la mesure active), images externes (TEM, scans : choisies dans un dossier autorisé
      du serveur, légendées, ordonnées - la première est la principale), fichiers, liens web. Les
      annotations d'une image gardée sont gardées.
   5. Titre, objectif lié, interprétation, observations, et la place dans le rapport.

   L'écriture passe par ctx.write (la version affichée en If-Match) : réussie, la fiche se recharge et
   la boîte se ferme ; un 412 la ferme pour le bandeau « modifiée entre-temps » ; un autre refus
   s'affiche dans la boîte. Un seul global : NotebookEntryDialog.open(ctx, {entry, snapshots}), où
   `snapshots` est le cache d'instantanés du panneau ({load(id), remember(ds)}). */

const NotebookEntryDialog = (() => {
  const $ = (id) => document.getElementById(id);
  const dialog = $("notebook-dialog");
  const errorBox = $("nb-dialog-error");
  const submitBtn = $("nb-add-submit");
  const DOCUMENT_ACCEPT = ".pdf,.csv,.tsv,.txt,.xls,.xlsx,.docx,.pptx";
  const MAX_FILE_BYTES = 10 * 1024 * 1024;
  const MAX_FILES = 12; // fichiers par mesure, images comprises (notebook/service.py)
  const MAX_LINKS = 10;
  const MAX_COLUMNS = 50;
  const MAX_ROWS = 1000;
  const MAX_CELL = 500;
  const MAX_EXTERNAL = 100; // images externes par mesure (notebook/service.py)
  const EXTERNAL_STATUS = {
    missing: "fichier déplacé ou supprimé",
    unsupported: "format que le navigateur n'affiche pas",
    forbidden: "hors des dossiers autorisés",
  };
  const ICONS = {
    file: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>`,
    remove: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>`,
    up: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"/></svg>`,
    down: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`,
  };

  let state = null; // la saisie en cours (voir open)
  let sources = null; // Promise : les types de données qu'on peut charger (catalogue de caractérisation)
  let rootsPromise = null; // Promise : les dossiers autorisés pour les images externes (un appel par page)
  let uid = 0;

  // --- étapes et mesures ---------------------------------------------------------------------------

  function processSteps() {
    return (state.ctx.process && state.ctx.process.steps) || [];
  }

  function stepTitle(key) {
    if (!key) return "Mesure non située";
    const steps = processSteps();
    const i = steps.findIndex((step) => step.id === key);
    return i < 0 ? "Étape retirée du procédé" : `Étape ${i + 1} · ${ExperimentVocabulary.stepLabel(steps[i])}`;
  }

  // Les mesures à saisir, dans l'ordre du stepper : une par bulle cochée, sinon une non située (gardée
  // à côté des autres si l'entrée en avait une, tant qu'on ne la retire pas).
  function keysOf(chosen) {
    if (!chosen.length) return [""];
    return state.keepUnsituated ? ["", ...chosen] : chosen;
  }

  function slotFor(key) {
    if (!state.slots.has(key)) state.slots.set(key, { key, measurement: null, prism: null, form: null });
    return state.slots.get(key);
  }

  function onStepsChange(chosen) {
    const before = state.keys;
    const after = keysOf(chosen);
    // une seule mesure, qui passe d'une bulle à aucune (ou l'inverse) : elle suit, contenu compris
    if (before.length === 1 && after.length === 1 && before[0] !== after[0] && !state.slots.has(after[0]) && state.slots.has(before[0])) {
      const slot = state.slots.get(before[0]);
      state.slots.delete(before[0]);
      slot.key = after[0];
      state.slots.set(after[0], slot);
    }
    // la mesure qu'on vient d'ajouter devient l'active (celle où Ctrl+V colle une image)
    const added = after.filter((key) => !before.includes(key));
    if (added.length) state.activeKey = added[added.length - 1];
    state.keys = after;
    renderSlots();
  }

  function renderSlots() {
    if (state.kind === "prism") renderPrismSlots();
    else renderManualSlots();
  }

  // --- erreurs -------------------------------------------------------------------------------------

  function showError(err) {
    errorBox.textContent = (err && err.message) || String(err);
    errorBox.style.display = "block";
    errorBox.scrollIntoView({ block: "nearest" });
  }

  function hideError() {
    errorBox.style.display = "none";
  }

  // --- plaques -------------------------------------------------------------------------------------

  function renderPlates() {
    const tracked = [...new Set((state.ctx.detail.physical_tracking || []).map((e) => e.sample_id).filter(Boolean))];
    const trackedKeys = new Set(tracked.map(waferKey));
    const measured = state.entry ? state.entry.wafers || [] : null;
    const kept = (measured || []).filter((key) => !trackedKeys.has(key));
    const box = (value, label, checked) =>
      `<label class="viz-check"><input type="checkbox" value="${escapeHtml(value)}"${checked ? " checked" : ""}> <span class="mono">${escapeHtml(label)}</span></label>`;
    $("nb-plates").innerHTML =
      tracked.map((mark) => box(mark, mark, measured ? measured.includes(waferKey(mark)) : true)).join("") +
      kept.map((key) => box(key, `${key} (plus suivie par cette version)`, true)).join("") ||
      `<span class="help" style="margin:0;">Cette version ne suit aucune plaque : la donnée vaudra pour toute la piste.</span>`;
  }

  function chosenPlates() {
    return [...document.querySelectorAll("#nb-plates input:checked")].map((input) => input.value);
  }

  // --- PRISM ---------------------------------------------------------------------------------------

  function snapshotSummary(ds) {
    return { hook: ds.hook, hook_title: ds.hook_title, wafers: ds.wafers, source: ds.source, fetched_at: ds.fetched_at, row_count: (ds.rows || []).length };
  }

  async function renderSources() {
    if (!sources) sources = characterizationApi.list({ status: "implemented", by_wafer: true }).catch(() => []);
    const list = await sources;
    if (!state) return;
    const fixed = state.entry && state.entry.kind === "prism" ? ((state.entry.measurements[0] || {}).snapshot || {}).hook : null;
    const current = state.prism.source ? state.prism.source.key : fixed || (list[0] && list[0].key);
    state.prism.source = list.find((s) => s.key === current) || (fixed ? { key: fixed, title: fixed } : null);
    const shown = fixed && !list.some((s) => s.key === fixed) ? [...list, state.prism.source] : list;
    $("nb-sources").innerHTML = shown.length
      ? shown
          .map(
            (s) => `
          <label class="nb-source">
            <input type="radio" name="nb-source" value="${escapeHtml(s.key)}"${s.key === current ? " checked" : ""}${fixed && s.key !== fixed ? " disabled" : ""}>
            <span class="nb-source__title">${escapeHtml(s.title)}</span>
            <span class="nb-source__cat">${escapeHtml(s.category || "")}</span>
          </label>`
          )
          .join("")
      : `<p class="help">Aucun type de données disponible (PRISM n'est pas configuré sur ce serveur).</p>`;
  }

  function renderPrismSlots() {
    const rows = state.keys.map((key) => {
      const loaded = slotFor(key).prism;
      const status = loaded
        ? `données du ${escapeHtml(formatDate(loaded.summary.fetched_at))} · ${loaded.summary.row_count ?? "?"} ligne${loaded.summary.row_count > 1 ? "s" : ""}${loaded.summary.source === "demo" ? " · démo" : ""}`
        : "à charger";
      return `
        <li class="nb-slot${loaded ? " is-loaded" : ""}">
          <span class="nb-slot__step">${escapeHtml(stepTitle(key))}</span>
          <span class="nb-slot__state">${status}</span>
          ${loaded ? `<button type="button" class="nb-btn" data-reload="${escapeHtml(key)}" aria-label="Recharger les données : ${escapeHtml(stepTitle(key))}">Recharger</button>` : ""}
        </li>`;
    });
    $("nb-prism-slots").innerHTML = rows.join("");
    $("nb-load-btn").hidden = state.keys.every((key) => slotFor(key).prism);
  }

  // Les plaques à charger : les plaques mesurées, plus celles pour comparer ; à défaut (une entrée qui
  // vaut pour toute la piste), celles de l'instantané déjà chargé.
  function snapshotPlates() {
    const extra = $("nb-extra-plates")
      .value.split(/[,;\s]+/)
      .map((w) => w.trim())
      .filter(Boolean);
    const plates = [...new Set([...chosenPlates(), ...extra])];
    if (plates.length) return plates;
    const loaded = state.keys.map((key) => slotFor(key).prism).find(Boolean);
    return loaded ? loaded.summary.wafers || [] : [];
  }

  async function loadPrism(keys, { refresh }) {
    const status = $("nb-load-status");
    if (!state.prism.source) {
      status.textContent = "Choisissez un type de données.";
      return;
    }
    const wafers = snapshotPlates();
    if (!wafers.length) {
      status.textContent = "Choisissez au moins une plaque.";
      return;
    }
    const buttons = [$("nb-load-btn"), ...document.querySelectorAll("#nb-prism-slots [data-reload]")];
    buttons.forEach((b) => (b.disabled = true));
    status.textContent = "Chargement depuis la base…";
    const current = state;
    try {
      const ds = await notebookApi.takeSnapshot(current.ctx.microprojectSlug, { hook: current.prism.source.key, wafers, refresh });
      if (state !== current) return;
      current.snapshots.remember(ds);
      keys.forEach((key) => (slotFor(key).prism = { snapshotId: ds.snapshot_id, summary: snapshotSummary(ds) }));
      $("nb-dialog-demo").hidden = ds.source !== "demo";
      const nWafers = DataViz.byWafer(ds).size;
      status.textContent = `${ds.rows.length} ligne${ds.rows.length > 1 ? "s" : ""} · ${nWafers} plaque${nWafers > 1 ? "s" : ""}${ds.source === "demo" ? " · données de démonstration" : ""}${ds.truncated ? " · tronqué" : ""}`;
      renderPrismSlots();
      paintViews(ds);
    } catch (err) {
      status.textContent = err.message || String(err);
    } finally {
      buttons.forEach((b) => (b.disabled = false));
    }
  }

  // Les vues possibles pour ce jeu de données (préréglages du type d'abord), et l'aperçu de la vue
  // choisie ; la vue (composant et réglages) vaut pour toutes les étapes de l'entrée.
  function paintViews(ds) {
    const prism = state.prism;
    prism.previewDs = ds;
    const presets = DataViz.presetsFor(ds);
    const components = DataViz.componentsFor(ds);
    const card = (attrs, title, sub) =>
      `<button type="button" class="nb-view" ${attrs}><span class="nb-view__title">${escapeHtml(title)}</span><span class="nb-view__sub">${escapeHtml(sub)}</span></button>`;
    const others = `<div class="nb-views__grid">${components.map((c) => card(`data-component="${c.key}"`, c.label, c.description)).join("")}</div>`;
    $("nb-views").innerHTML = presets.length
      ? `<div class="nb-views__label">Pour ce type de données</div><div class="nb-views__grid">${presets.map((p, i) => card(`data-preset="${i}"`, p.title, DataViz.get(p.component).label)).join("")}</div>
         <details class="nb-views__more"><summary>Toutes les vues possibles (${components.length})</summary>${others}</details>`
      : `<div class="nb-views__label">Vues possibles</div>${others}`;
    $("nb-step-view").hidden = false;
    const choose = (btn, component, options, title) => {
      document.querySelectorAll("#nb-views .nb-view").forEach((b) => b.classList.toggle("is-selected", b === btn));
      prism.component = component;
      const def = DataViz.get(component);
      const values = { ...def.defaults(ds), ...options };
      $("nb-preview-options").innerHTML = DataViz.optionsFormHtml(ds, def.options(ds), values, "nbp");
      prism.options = DataViz.readOptions($("nb-preview-options"));
      const titleInput = $("nb-title");
      if (title && (!titleInput.value || titleInput.value === prism.presetTitle)) {
        titleInput.value = title;
        prism.presetTitle = title;
      }
      DataViz.render($("nb-preview-viz"), ds, component, values);
    };
    document.querySelectorAll("#nb-views [data-preset]").forEach((btn) => {
      const p = presets[Number(btn.dataset.preset)];
      btn.addEventListener("click", () => choose(btn, p.component, p.options || {}, p.title));
    });
    document.querySelectorAll("#nb-views [data-component]").forEach((btn) => {
      const c = DataViz.get(btn.dataset.component);
      btn.addEventListener("click", () => choose(btn, c.key, {}, `${c.label} · ${ds.hook_title || ds.hook}`));
    });
    // la vue déjà choisie (une entrée modifiée, un rechargement) reste ; sinon le premier préréglage
    const current = prism.component && document.querySelector(`#nb-views [data-component="${CSS.escape(prism.component)}"]`);
    if (current && DataViz.get(prism.component)) choose(current, prism.component, prism.options || {}, null);
    else document.querySelector("#nb-views [data-preset], #nb-views [data-component]")?.click();
  }

  function prismMeasurements() {
    const prism = state.prism;
    if (!prism.component) throw new Error("Chargez les données et choisissez une vue.");
    return state.keys.map((key) => {
      const loaded = slotFor(key).prism;
      if (!loaded) throw new Error(`Chargez les données de cette mesure : ${stepTitle(key)}.`);
      return { step_id: key || null, snapshot_id: loaded.snapshotId, component: prism.component, options: prism.options || {} };
    });
  }

  // --- une mesure à la main ------------------------------------------------------------------------

  // Un tableau collé : du TSV (une copie d'Excel), ou des « ; » (un CSV français) ; une cellule entre
  // guillemets peut contenir tabulations et retours à la ligne. La première ligne donne les colonnes.
  function splitDelimited(text, sep) {
    const rows = [];
    let row = [];
    let cell = "";
    let quoted = false;
    for (let i = 0; i < text.length; i += 1) {
      const c = text[i];
      if (quoted) {
        if (c === '"' && text[i + 1] === '"') {
          cell += '"';
          i += 1;
        } else if (c === '"') quoted = false;
        else cell += c;
      } else if (c === '"' && cell === "") quoted = true;
      else if (c === sep) {
        row.push(cell);
        cell = "";
      } else if (c === "\n") {
        row.push(cell);
        rows.push(row);
        row = [];
        cell = "";
      } else cell += c;
    }
    row.push(cell);
    rows.push(row);
    return rows;
  }

  function cellValue(raw) {
    const text = raw.trim();
    if (!text) return null;
    if (/^[-+]?(\d+([.,]\d*)?|[.,]\d+)([eE][-+]?\d+)?$/.test(text)) {
      const number = Number(text.replace(",", "."));
      if (Number.isFinite(number)) return number;
    }
    return text;
  }

  // {columns, rows} | null (rien de collé) ; une erreur lisible si le tableau dépasse les bornes.
  function parseTable(text) {
    const raw = text.replace(/\r\n?/g, "\n").replace(/\n+$/, "");
    if (!raw.trim()) return null;
    const sep = raw.includes("\t") ? "\t" : raw.includes(";") ? ";" : "\t";
    const lines = splitDelimited(raw, sep).filter((row) => row.some((cell) => cell.trim()));
    const width = Math.max(...lines.map((row) => row.length));
    if (width > MAX_COLUMNS) throw new Error(`Tableau trop large : ${MAX_COLUMNS} colonnes au plus.`);
    if (lines.length - 1 > MAX_ROWS) throw new Error(`Tableau trop long : ${MAX_ROWS} lignes au plus.`);
    const pad = (row) => [...row, ...Array(width - row.length).fill("")];
    const columns = pad(lines[0]).map((name, i) => name.trim() || `Colonne ${i + 1}`);
    const rows = lines.slice(1).map((row) => pad(row).map(cellValue));
    if ([...columns, ...rows.flat()].some((cell) => typeof cell === "string" && cell.length > MAX_CELL)) {
      throw new Error(`Une cellule du tableau dépasse ${MAX_CELL} caractères.`);
    }
    return { columns, rows };
  }

  function tableText(table) {
    if (!table) return "";
    const cell = (value) => {
      const text = value === null || value === undefined ? "" : String(value);
      return /[\t\n"]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    return [table.columns, ...table.rows].map((row) => row.map(cell).join("\t")).join("\n");
  }

  function tablePreviewHtml(table) {
    const shown = table.rows.slice(0, 8);
    const more = table.rows.length - shown.length;
    return `
      <div class="viz-table-wrap"><table class="viz-table">
        <thead><tr>${table.columns.map((c) => `<th scope="col">${escapeHtml(c)}</th>`).join("")}</tr></thead>
        <tbody>${shown.map((row) => `<tr>${row.map((v) => `<td>${escapeHtml(v === null ? "" : String(v))}</td>`).join("")}</tr>`).join("")}</tbody>
      </table></div>
      <p class="help">${table.columns.length} colonne${table.columns.length > 1 ? "s" : ""} · ${table.rows.length} ligne${table.rows.length > 1 ? "s" : ""}${more > 0 ? ` (${more} de plus, non montrées ici)` : ""}</p>`;
  }

  function formatSize(bytes) {
    if (!bytes && bytes !== 0) return "";
    return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} Mo` : `${Math.max(1, Math.round(bytes / 1024))} ko`;
  }

  function linkRowHtml(link = {}) {
    const n = (uid += 1);
    return `
      <div class="nb-link-row">
        <input class="field" data-link-label maxlength="200" value="${escapeHtml(link.label || "")}" placeholder="Libellé (optionnel)" aria-label="Libellé du lien ${n}">
        <input class="field mono" data-link-url type="url" value="${escapeHtml(link.url || "")}" placeholder="https://…" aria-label="Adresse du lien ${n}">
        <button type="button" class="nb-btn nb-btn--icon" data-remove-link aria-label="Retirer ce lien">${ICONS.remove}</button>
      </div>`;
  }

  function renderFiles(slot) {
    const form = slot.form;
    form.files.innerHTML = slot.files
      .map(
        (file, i) => `
        <li class="nb-file${file.uploading ? " is-uploading" : ""}">
          ${ICONS.file}
          <span class="nb-file__name">${escapeHtml(file.filename || "fichier")}</span>
          <span class="nb-file__size">${file.uploading ? "envoi…" : escapeHtml(formatSize(file.size))}</span>
          <button type="button" class="nb-btn nb-btn--icon" data-remove-file="${i}" aria-label="Retirer ${escapeHtml(file.filename || "ce fichier")}"${file.uploading ? " disabled" : ""}>${ICONS.remove}</button>
        </li>`
      )
      .join("");
  }

  async function uploadFiles(slot, fileList) {
    for (const file of [...fileList]) {
      if (file.size > MAX_FILE_BYTES) {
        showError(new Error(`« ${file.name} » : 10 Mo au maximum par fichier.`));
        continue;
      }
      const item = { id: null, filename: file.name, size: file.size, caption: null, uploading: true };
      slot.files.push(item);
      renderFiles(slot);
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("purpose", "notebook");
      try {
        const uploaded = await attachmentsApi.upload(state.ctx.microprojectSlug, form);
        Object.assign(item, { id: uploaded.id, filename: uploaded.filename, size: uploaded.size, uploading: false });
      } catch (err) {
        slot.files.splice(slot.files.indexOf(item), 1);
        showError(err);
      }
      renderFiles(slot);
    }
  }

  // --- images externes d'une mesure ----------------------------------------------------------------

  // Des images (TEM, scans) lues à leur place sur le disque du serveur, sans copie : on part d'un
  // dossier autorisé (externalImagesApi.roots), on en liste les images (externalImagesApi.browse), on
  // coche celles de la mesure ; ou on donne le chemin d'une image. Le serveur vérifie chaque nouvelle
  // image à l'enregistrement (dossier autorisé, format, fichier présent). Une image déjà sur la mesure
  // s'aperçoit par son `url` (servie par l'entrée) ; une nouvelle, une fois enregistrée.

  function externalName(image) {
    return image.name || String(image.path).split(/[\\/]/).filter(Boolean).pop() || image.path;
  }

  function externalRoots() {
    if (!rootsPromise) rootsPromise = externalImagesApi.roots(state.ctx.microprojectSlug).catch(() => []);
    return rootsPromise;
  }

  function renderExternal(slot) {
    const images = slot.external;
    slot.externalList.innerHTML = images
      .map((image, i) => {
        const name = externalName(image);
        const thumb =
          image.url && image.status === "ok"
            ? `<img src="${escapeHtml(image.url)}" alt="" loading="lazy">`
            : `<span class="nb-ext-item__nothumb">${image.url ? "indisponible" : "aperçu à l'enregistrement"}</span>`;
        const problem = image.status && image.status !== "ok" ? `<span class="nb-ext-item__problem">${escapeHtml(EXTERNAL_STATUS[image.status] || "indisponible")}</span>` : "";
        return `
          <li class="nb-ext-item">
            <span class="nb-ext-item__thumb">${thumb}</span>
            <span class="nb-ext-item__body">
              <span class="nb-ext-item__name">${i === 0 && images.length > 1 ? `<span class="nb-ext-item__main">principale</span>` : ""}${escapeHtml(name)}${problem}</span>
              <span class="nb-ext-item__path" title="${escapeHtml(image.path)}">${escapeHtml(image.path)}</span>
              <input class="field" data-ext-caption="${i}" maxlength="200" value="${escapeHtml(image.caption)}" placeholder="Légende (optionnelle)" aria-label="Légende de ${escapeHtml(name)}">
            </span>
            <span class="nb-ext-item__actions">
              <button type="button" class="nb-btn nb-btn--icon" data-ext-move="${i}" data-step="-1" aria-label="Monter ${escapeHtml(name)}" title="Monter"${i === 0 ? " disabled" : ""}>${ICONS.up}</button>
              <button type="button" class="nb-btn nb-btn--icon" data-ext-move="${i}" data-step="1" aria-label="Descendre ${escapeHtml(name)}" title="Descendre"${i === images.length - 1 ? " disabled" : ""}>${ICONS.down}</button>
              <button type="button" class="nb-btn nb-btn--icon" data-ext-remove="${i}" aria-label="Retirer ${escapeHtml(name)}" title="Retirer">${ICONS.remove}</button>
            </span>
          </li>`;
      })
      .join("");
  }

  function addExternal(slot, picked) {
    const known = new Set(slot.external.map((image) => image.path));
    const fresh = picked.filter((image) => !known.has(image.path));
    if (slot.external.length + fresh.length > MAX_EXTERNAL) {
      showError(new Error(`${MAX_EXTERNAL} images externes au maximum par mesure.`));
      return false;
    }
    hideError();
    slot.external.push(...fresh.map((image) => ({ path: image.path, caption: "", name: image.name || null, status: null, url: null })));
    renderExternal(slot);
    return true;
  }

  function renderBrowsed(slot, picker, listing) {
    const known = new Set(slot.external.map((image) => image.path));
    const results = picker.querySelector("[data-ext-results]");
    const addable = listing.filter((image) => image.displayable && !known.has(image.path));
    results.innerHTML = listing.length
      ? `<p class="nb-ext-results__head">${listing.length} image${listing.length > 1 ? "s" : ""} dans <span class="mono">${escapeHtml(slot.browsedDir)}</span></p>
         <ul class="nb-ext-results__list">${listing
           .map((image, i) => {
             const added = known.has(image.path);
             const note = !image.displayable ? "TIFF : le navigateur ne l'affiche pas, exportez-la en PNG ou en JPEG" : added ? "déjà dans la mesure" : formatSize(image.size);
             return `<li><label class="nb-ext-result${image.displayable && !added ? "" : " is-off"}">
               <input type="checkbox" data-ext-pick="${i}"${image.displayable && !added ? "" : " disabled"}${added ? " checked" : ""}>
               <span class="nb-ext-result__name">${escapeHtml(image.name)}</span>
               <span class="nb-ext-result__note">${escapeHtml(note)}</span>
             </label></li>`;
           })
           .join("")}</ul>`
      : `<p class="help" style="margin:0;">Aucune image dans ce dossier (seules les images sont listées, pas les sous-dossiers).</p>`;
    picker.querySelector("[data-ext-add-row]").hidden = !addable.length;
    updatePickCount(picker);
  }

  function updatePickCount(picker) {
    const n = picker.querySelectorAll("[data-ext-pick]:checked:not(:disabled)").length;
    const btn = picker.querySelector("[data-ext-add]");
    btn.disabled = !n;
    btn.textContent = n ? `Ajouter ${n} image${n > 1 ? "s" : ""}` : "Cochez des images à ajouter";
  }

  async function browseExternal(slot, picker, directory) {
    const results = picker.querySelector("[data-ext-results]");
    if (!directory) return;
    picker.querySelector("[data-ext-dir]").value = directory;
    results.innerHTML = `<p class="help" style="margin:0;">Lecture du dossier…</p>`;
    picker.querySelector("[data-ext-add-row]").hidden = true;
    try {
      slot.browsed = await externalImagesApi.browse(state.ctx.microprojectSlug, directory);
      slot.browsedDir = directory;
      renderBrowsed(slot, picker, slot.browsed);
    } catch (err) {
      slot.browsed = [];
      results.innerHTML = `<p class="nb-table-error" role="alert">${escapeHtml(err.message || String(err))}</p>`;
    }
  }

  async function openPicker(slot, picker) {
    const list = await externalRoots();
    if (!state || !picker.isConnected) return;
    const rootsBox = picker.querySelector("[data-ext-roots]");
    picker.querySelector("[data-ext-browse-row]").hidden = !list.length;
    rootsBox.innerHTML = list.length
      ? `<span class="nb-ext-picker__label">Dossiers autorisés</span>${list
          .map((root, i) => `<button type="button" class="nb-ext-root mono" data-ext-root="${i}" title="Lister les images de ce dossier">${escapeHtml(root)}</button>`)
          .join("")}`
      : `<p class="help" style="margin:0;">Le parcours des dossiers est désactivé sur ce serveur (aucun dossier autorisé, <span class="mono">SPECTRE_EXTERNAL_IMAGE_ROOTS</span>) : donnez le chemin d'une image.</p>`;
    rootsBox.querySelectorAll("[data-ext-root]").forEach((btn) => btn.addEventListener("click", () => browseExternal(slot, picker, list[Number(btn.dataset.extRoot)])));
  }

  function wireExternalImages(slot, el) {
    slot.externalList = el.querySelector(".nb-ext-list");
    slot.browsed = [];
    slot.browsedDir = "";
    renderExternal(slot);
    const picker = el.querySelector(".nb-ext-picker");
    const toggle = el.querySelector("[data-ext-toggle]");
    toggle.addEventListener("click", () => {
      const opening = picker.hidden;
      picker.hidden = !opening;
      toggle.setAttribute("aria-expanded", String(opening));
      toggle.textContent = opening ? "Fermer le choix des images" : "Choisir des images externes…";
      if (opening) openPicker(slot, picker).then(() => picker.querySelector("[data-ext-root], [data-ext-path]")?.focus());
    });
    const dir = picker.querySelector("[data-ext-dir]");
    picker.querySelector("[data-ext-browse]").addEventListener("click", () => browseExternal(slot, picker, dir.value.trim()));
    dir.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      browseExternal(slot, picker, dir.value.trim());
    });
    picker.querySelector("[data-ext-results]").addEventListener("change", () => updatePickCount(picker));
    picker.querySelector("[data-ext-add]").addEventListener("click", () => {
      const picked = [...picker.querySelectorAll("[data-ext-pick]:checked:not(:disabled)")].map((box) => slot.browsed[Number(box.dataset.extPick)]);
      if (addExternal(slot, picked)) renderBrowsed(slot, picker, slot.browsed);
    });
    const path = picker.querySelector("[data-ext-path]");
    const addPath = () => {
      const value = path.value.trim();
      if (!value) return path.focus();
      if (addExternal(slot, [{ path: value }])) path.value = "";
    };
    picker.querySelector("[data-ext-add-path]").addEventListener("click", addPath);
    path.addEventListener("keydown", (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      addPath();
    });
    slot.externalList.addEventListener("input", (event) => {
      const input = event.target.closest("[data-ext-caption]");
      if (input) slot.external[Number(input.dataset.extCaption)].caption = input.value;
    });
    slot.externalList.addEventListener("click", (event) => {
      const move = event.target.closest("[data-ext-move]");
      const remove = event.target.closest("[data-ext-remove]");
      if (move) {
        const i = Number(move.dataset.extMove);
        const j = i + Number(move.dataset.step);
        [slot.external[i], slot.external[j]] = [slot.external[j], slot.external[i]];
        renderExternal(slot);
        const again = slot.externalList.querySelector(`[data-ext-move="${j}"][data-step="${move.dataset.step}"]`);
        (again && !again.disabled ? again : slot.externalList.querySelector(`[data-ext-caption="${j}"]`)).focus();
      } else if (remove) {
        slot.external.splice(Number(remove.dataset.extRemove), 1);
        renderExternal(slot);
        if (slot.browsed.length && !picker.hidden) renderBrowsed(slot, picker, slot.browsed);
        toggle.focus();
      }
    });
  }

  function setActive(slot) {
    state.activeKey = slot.key;
    document.querySelectorAll("#nb-measures .nb-mform").forEach((el) => el.classList.toggle("is-active", el === slot.form.el));
  }

  // Le formulaire d'une mesure, construit une fois (ses images restent en place quand on coche ou
  // décoche d'autres bulles) et prérempli par la mesure qu'il modifie.
  function buildManualForm(slot) {
    const m = slot.measurement || {};
    const n = (uid += 1);
    const el = document.createElement("fieldset");
    el.className = "nb-mform";
    el.innerHTML = `
      <legend class="nb-mform__legend"></legend>
      <button type="button" class="nb-btn nb-mform__drop-unsituated" hidden>Retirer cette mesure non située</button>
      <div class="nb-mform__grid">
        <div class="nb-mform__field">
          <span class="nb-mform__label" id="nbm-${n}-value">Valeur mesurée</span>
          <div class="nb-value-row" role="group" aria-labelledby="nbm-${n}-value">
            <input class="field" data-value-name maxlength="120" placeholder="grandeur (ex : rugosité RMS)" aria-label="Grandeur mesurée">
            <input class="field mono" data-value-number inputmode="decimal" placeholder="valeur" aria-label="Valeur">
            <input class="field" data-value-unit maxlength="40" placeholder="unité" aria-label="Unité">
          </div>
        </div>
        <div class="nb-mform__field">
          <label for="nbm-${n}-text">Texte</label>
          <textarea class="field" id="nbm-${n}-text" data-text rows="2" placeholder="Ce qui a été mesuré, comment, où sont les données brutes…"></textarea>
        </div>
        <div class="nb-mform__field nb-mform__field--wide">
          <label for="nbm-${n}-table">Tableau</label>
          <textarea class="field mono nb-mform__table" id="nbm-${n}-table" data-table rows="3" placeholder="Collez ici un tableau copié d'Excel (Ctrl+V) : la première ligne donne les colonnes" aria-describedby="nbm-${n}-table-state"></textarea>
          <div class="nb-table-preview" id="nbm-${n}-table-state" aria-live="polite"></div>
        </div>
        <div class="nb-mform__field nb-mform__field--wide">
          <span class="nb-mform__label">Images <span class="help" style="display:inline;margin:0;font-weight:400;">- Ctrl+V colle dans la mesure active (encadrée)</span></span>
          <div class="nb-mform__images"></div>
        </div>
        <div class="nb-mform__field nb-mform__field--wide">
          <span class="nb-mform__label" id="nbm-${n}-ext">Images externes <span class="help" style="display:inline;margin:0;font-weight:400;">- TEM, scans : lues à leur place sur le serveur, jamais copiées ; la première est l'image principale</span></span>
          <ul class="nb-ext-list" aria-labelledby="nbm-${n}-ext"></ul>
          <button type="button" class="btn btn-line nb-mform__add" data-ext-toggle aria-expanded="false" aria-controls="nbm-${n}-ext-picker">Choisir des images externes…</button>
          <div class="nb-ext-picker" id="nbm-${n}-ext-picker" hidden>
            <div class="nb-ext-picker__roots" data-ext-roots></div>
            <div class="nb-ext-picker__browse" data-ext-browse-row hidden>
              <label for="nbm-${n}-ext-dir">Dossier</label>
              <div class="nb-ext-picker__bar">
                <input class="field mono" id="nbm-${n}-ext-dir" data-ext-dir placeholder="chemin absolu d'un dossier autorisé" autocomplete="off">
                <button type="button" class="btn btn-line" data-ext-browse>Parcourir</button>
              </div>
            </div>
            <div class="nb-ext-results" data-ext-results aria-live="polite"></div>
            <div class="nb-ext-picker__add" data-ext-add-row hidden>
              <button type="button" class="btn btn-primary" data-ext-add>Ajouter la sélection</button>
            </div>
            <label for="nbm-${n}-ext-path">Ou le chemin d'une image</label>
            <div class="nb-ext-picker__bar">
              <input class="field mono" id="nbm-${n}-ext-path" data-ext-path placeholder="chemin absolu d'une image (PNG, JPEG, GIF, WebP, BMP)" autocomplete="off">
              <button type="button" class="btn btn-line" data-ext-add-path>Ajouter</button>
            </div>
          </div>
        </div>
        <div class="nb-mform__field">
          <span class="nb-mform__label" id="nbm-${n}-files">Fichiers</span>
          <ul class="nb-files" aria-labelledby="nbm-${n}-files"></ul>
          <input type="file" data-file-input multiple accept="${DOCUMENT_ACCEPT}" hidden>
          <button type="button" class="btn btn-line nb-mform__add" data-add-file>Joindre un fichier…</button>
          <p class="help">PDF, Excel, CSV, Word, PowerPoint, texte - 10 Mo max, téléchargeables depuis la fiche.</p>
        </div>
        <div class="nb-mform__field">
          <span class="nb-mform__label" id="nbm-${n}-links">Liens web</span>
          <div class="nb-links-form" role="group" aria-labelledby="nbm-${n}-links"></div>
          <button type="button" class="btn btn-line nb-mform__add" data-add-link>Ajouter un lien</button>
        </div>
      </div>`;
    const form = {
      el,
      name: el.querySelector("[data-value-name]"),
      number: el.querySelector("[data-value-number]"),
      unit: el.querySelector("[data-value-unit]"),
      text: el.querySelector("[data-text]"),
      table: el.querySelector("[data-table]"),
      tableState: el.querySelector(".nb-table-preview"),
      files: el.querySelector(".nb-files"),
      fileInput: el.querySelector("[data-file-input]"),
      links: el.querySelector(".nb-links-form"),
      tableInitial: tableText(m.table),
    };
    slot.form = form;
    slot.files = (m.attachments || []).filter((a) => !(a.content_type || "").startsWith("image/")).map((a) => ({ ...a, uploading: false }));
    slot.annotations = (m.annotations || []).filter((a) => a.attachment_id && (a.type === "arrow" || a.type === "box"));
    // les images externes déjà sur la mesure gardent leur aperçu (leur `url`, servie par l'entrée)
    slot.external = (m.external_images || []).map((image) => ({ path: image.path, caption: image.caption || "", name: image.name, status: image.status, url: image.url }));
    if (m.value) {
      form.name.value = m.value.name || "";
      form.number.value = String(m.value.number);
      form.unit.value = m.value.unit || "";
    }
    form.text.value = m.text || "";
    form.table.value = form.tableInitial;
    form.links.innerHTML = (m.links || []).map(linkRowHtml).join("");
    renderFiles(slot);
    wireExternalImages(slot, el);

    const refreshTable = () => {
      try {
        const table = parseTable(form.table.value);
        form.tableState.innerHTML = table ? tablePreviewHtml(table) : "";
      } catch (err) {
        form.tableState.innerHTML = `<p class="nb-table-error">${escapeHtml(err.message)}</p>`;
      }
    };
    // Une copie d'Excel porte aussi une image du tableau : ici, c'est le texte qu'on colle (et la
    // planche d'images ne le voit pas).
    form.table.addEventListener("paste", (event) => {
      event.stopPropagation();
      const text = event.clipboardData && event.clipboardData.getData("text/plain");
      if (!text) return;
      event.preventDefault();
      form.table.setRangeText(text, form.table.selectionStart, form.table.selectionEnd, "end");
      refreshTable();
    });
    form.table.addEventListener("input", refreshTable);
    refreshTable();

    slot.images = mountImageDrop(el.querySelector(".nb-mform__images"), {
      slug: state.ctx.microprojectSlug,
      purpose: "notebook",
      withKind: false,
      compact: true,
      onChange: hideError,
      onError: showError,
      isActive: () => dialog.open && state && state.kind === "manual" && state.activeKey === slot.key && el.isConnected,
    });
    slot.images.set(
      (m.attachments || [])
        .filter((a) => (a.content_type || "").startsWith("image/"))
        .map((a) => ({ image_id: a.id, url: a.url, filename: a.filename, caption: a.caption || "", kind: "schema" }))
    );

    el.addEventListener("focusin", () => setActive(slot));
    el.addEventListener("pointerdown", () => setActive(slot));
    el.querySelector("[data-add-file]").addEventListener("click", () => form.fileInput.click());
    form.fileInput.addEventListener("change", () => {
      const files = form.fileInput.files;
      if (slot.files.length + slot.images.get().length + files.length > MAX_FILES) showError(new Error(`${MAX_FILES} fichiers au maximum par mesure, images comprises.`));
      else uploadFiles(slot, files);
      form.fileInput.value = "";
    });
    form.files.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-remove-file]");
      if (!btn) return;
      slot.files.splice(Number(btn.dataset.removeFile), 1);
      renderFiles(slot);
      el.querySelector("[data-add-file]").focus();
    });
    el.querySelector("[data-add-link]").addEventListener("click", () => {
      if (form.links.children.length >= MAX_LINKS) return showError(new Error(`${MAX_LINKS} liens au maximum par mesure.`));
      form.links.insertAdjacentHTML("beforeend", linkRowHtml());
      form.links.lastElementChild.querySelector("[data-link-url]").focus();
    });
    form.links.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-remove-link]");
      if (!btn) return;
      btn.closest(".nb-link-row").remove();
      el.querySelector("[data-add-link]").focus();
    });
    el.querySelector(".nb-mform__drop-unsituated").addEventListener("click", () => {
      state.keepUnsituated = false;
      onStepsChange(state.stepper.get());
    });
    return form;
  }

  function renderManualSlots() {
    const host = $("nb-measures");
    const forms = state.keys.map((key) => {
      const slot = slotFor(key);
      const form = slot.form || buildManualForm(slot);
      form.el.querySelector(".nb-mform__legend").innerHTML = `<span class="nb-mform__dot${key ? "" : " is-unsituated"}" aria-hidden="true"></span>${escapeHtml(stepTitle(key))}`;
      form.el.classList.toggle("is-retired", Boolean(key) && !processSteps().some((s) => s.id === key));
      form.el.querySelector(".nb-mform__drop-unsituated").hidden = Boolean(key) || state.keys.length < 2;
      return form.el;
    });
    [...host.children].forEach((el) => !forms.includes(el) && el.remove());
    forms.forEach((el) => host.appendChild(el));
    if (!state.keys.includes(state.activeKey)) setActive(slotFor(state.keys[state.keys.length - 1]));
    else setActive(slotFor(state.activeKey));
  }

  function manualMeasurement(slot) {
    const title = stepTitle(slot.key);
    const form = slot.form;
    const raw = form.number.value.trim();
    const name = form.name.value.trim();
    const unit = form.unit.value.trim();
    let value = null;
    if (raw) {
      const number = Number(raw.replace(/\s/g, "").replace(",", "."));
      if (!Number.isFinite(number)) throw new Error(`${title} : « ${raw} » n'est pas un nombre.`);
      value = { number, unit: unit || null, name: name || null };
    } else if (name || unit) {
      throw new Error(`${title} : indiquez la valeur mesurée (ou videz la grandeur et l'unité).`);
    }
    let table;
    try {
      table = form.table.value === form.tableInitial ? (slot.measurement || {}).table || null : parseTable(form.table.value);
    } catch (err) {
      throw new Error(`${title} : ${err.message}`);
    }
    if (slot.images.isUploading() || slot.files.some((f) => f.uploading)) throw new Error("Un fichier est encore en cours d'envoi - un instant.");
    const images = slot.images.get();
    const attachments = [...images.map((img) => ({ id: img.image_id, caption: (img.caption || "").trim() || null })), ...slot.files.map((f) => ({ id: f.id, caption: f.caption || null }))];
    if (attachments.length > MAX_FILES) throw new Error(`${title} : ${MAX_FILES} fichiers au maximum, images comprises.`);
    const kept = new Set(images.map((img) => img.image_id));
    const links = [...form.links.querySelectorAll(".nb-link-row")]
      .map((row) => ({ label: row.querySelector("[data-link-label]").value.trim() || null, url: row.querySelector("[data-link-url]").value.trim() }))
      .filter((link) => link.url);
    const bad = links.find((link) => !/^https?:\/\/\S+$/i.test(link.url));
    if (bad) throw new Error(`${title} : « ${bad.url} » n'est pas une adresse web (http ou https). Un chemin réseau va dans le texte.`);
    return {
      step_id: slot.key || null,
      value,
      text: form.text.value.trim() || null,
      table,
      attachments,
      // les images externes (TEM, scans référencés sur le serveur), dans l'ordre choisi
      external_images: slot.external.map((image) => ({ path: image.path, caption: (image.caption || "").trim() || null })),
      links,
      annotations: slot.annotations.filter((a) => kept.has(a.attachment_id)),
    };
  }

  function manualMeasurements() {
    const measurements = state.keys.map((key) => manualMeasurement(slotFor(key)));
    const empty = (m) => !m.value && !m.text && !m.table && !m.attachments.length && !m.external_images.length && !m.links.length;
    // une seule mesure, non située et vide : l'entrée n'a pas de mesure
    return measurements.length === 1 && !measurements[0].step_id && empty(measurements[0]) ? [] : measurements;
  }

  // --- type, ouverture, envoi ----------------------------------------------------------------------

  function showKind() {
    const prism = state.kind === "prism";
    $("nb-prism").hidden = !prism;
    $("nb-manual").hidden = prism;
    if (prism) {
      renderSources();
      if (state.prism.previewDs) $("nb-step-view").hidden = false;
    }
    renderSlots();
  }

  function objectiveOptionsHtml(selected) {
    return `<option value="">— aucun —</option>${(state.ctx.detail.objectives || [])
      .map((o) => `<option value="${escapeHtml(o.name)}"${o.name === selected ? " selected" : ""}>${escapeHtml(o.name)}</option>`)
      .join("")}`;
  }

  function open(ctx, { entry = null, snapshots }) {
    const measurements = entry ? entry.measurements || [] : [];
    const first = measurements[0] || {};
    state = {
      ctx,
      entry,
      snapshots,
      kind: entry ? entry.kind : "manual",
      keys: [],
      slots: new Map(),
      activeKey: null,
      stepper: null,
      keepUnsituated: measurements.some((m) => !m.step_id) && measurements.some((m) => m.step_id),
      prism: { source: null, component: entry && entry.kind === "prism" ? first.component : null, options: first.options || {}, presetTitle: "", previewDs: null },
    };
    measurements.forEach((m) => {
      const slot = slotFor(m.step_id || "");
      slot.measurement = m;
      if (m.snapshot_id) slot.prism = { snapshotId: m.snapshot_id, summary: m.snapshot || {} };
    });
    hideError();
    $("nb-dialog-title").textContent = entry ? "Modifier la donnée" : "Ajouter une donnée au cahier";
    submitBtn.textContent = entry ? "Enregistrer" : "Ajouter au cahier";
    submitBtn.disabled = false;
    document.querySelectorAll('input[name="nb-kind"]').forEach((radio) => {
      radio.checked = radio.value === state.kind;
      radio.disabled = Boolean(entry);
    });
    $("nb-dialog-demo").hidden = !measurements.some((m) => m.snapshot && m.snapshot.source === "demo");
    $("nb-measures").innerHTML = "";
    $("nb-views").innerHTML = "";
    $("nb-preview-viz").innerHTML = "";
    $("nb-preview-options").innerHTML = "";
    $("nb-step-view").hidden = true;
    $("nb-load-status").textContent = "";
    $("nb-extra-plates").value = "";
    renderPlates();

    // le stepper : les étapes du procédé, plus celles, retirées, où l'entrée a une mesure
    const steps = (ctx.process && ctx.process.steps) || [];
    const chosen = measurements.filter((m) => m.step_id).map((m) => m.step_id);
    const fresh = document.createElement("div");
    $("nb-stepper-host").replaceChildren(fresh);
    state.stepper = mountStepper(fresh, {
      steps: steps.map((step, i) => ({ id: step.id, label: step.name || ExperimentVocabulary.stepKinds[step.kind] || step.kind, title: `${i + 1}. ${ExperimentVocabulary.stepLabel(step)}` })),
      measured: chosen,
      retired: measurements.filter((m) => m.step_id && m.step_retired).map((m) => m.step_id),
      selectable: true,
      label: "Étapes mesurées",
      onChange: onStepsChange,
    });
    $("nb-stepper-help").textContent = steps.length
      ? "Cochez l'étape (ou les étapes) du procédé après laquelle la mesure a été faite : une mesure par bulle, pour comparer avant et après. Aucune bulle : une mesure non située."
      : "Le procédé de cette version n'a pas d'étapes : la mesure est non située.";
    state.keys = keysOf(state.stepper.get()); // dans l'ordre du stepper

    $("nb-title").value = entry ? entry.title : "";
    $("nb-objective").innerHTML = objectiveOptionsHtml(entry ? entry.objective : null);
    $("nb-interpretation").value = entry ? entry.interpretation || "" : "";
    $("nb-note").value = entry ? entry.note || "" : "";
    $("nb-in-report").checked = !entry || entry.in_report !== false;

    showKind();
    dialog.showModal();
    (entry ? $("nb-title") : document.querySelector('input[name="nb-kind"]:checked')).focus();

    // une entrée PRISM : l'aperçu de sa vue, sur l'instantané de sa première mesure
    if (entry && entry.kind === "prism" && first.snapshot_id) {
      const current = state;
      snapshots
        .load(first.snapshot_id)
        .then((ds) => state === current && paintViews(ds))
        .catch((err) => state === current && ($("nb-load-status").textContent = err.message || String(err)));
    }
  }

  function body() {
    const title = $("nb-title").value.trim();
    if (!title) {
      $("nb-title").focus();
      throw new Error("Donnez un titre à cette donnée.");
    }
    return {
      title,
      wafers: chosenPlates(),
      measurements: state.kind === "prism" ? prismMeasurements() : manualMeasurements(),
      objective: $("nb-objective").value || null,
      interpretation: $("nb-interpretation").value.trim() || null,
      note: $("nb-note").value.trim() || null,
      in_report: $("nb-in-report").checked,
    };
  }

  async function submit() {
    hideError();
    let payload;
    try {
      payload = body();
    } catch (err) {
      showError(err);
      return;
    }
    const { ctx, entry, kind } = state;
    submitBtn.disabled = true;
    const done = await ctx.write(
      () =>
        entry
          ? notebookApi.updateEntry(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, entry.id, payload)
          : notebookApi.addEntry(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, { kind, ...payload }),
      errorBox
    );
    if (done) dialog.close();
    else submitBtn.disabled = false;
  }

  // --- branché une fois --------------------------------------------------------------------------

  $("nb-dialog-close").addEventListener("click", () => dialog.close());
  $("nb-add-cancel").addEventListener("click", () => dialog.close());
  submitBtn.addEventListener("click", submit);
  document.querySelectorAll('input[name="nb-kind"]').forEach((radio) =>
    radio.addEventListener("change", () => {
      state.kind = radio.value;
      showKind();
    })
  );
  $("nb-sources").addEventListener("change", async (event) => {
    const list = await sources;
    state.prism.source = list.find((s) => s.key === event.target.value) || null;
    // un autre type de données : les instantanés chargés ne valent plus
    state.slots.forEach((slot) => (slot.prism = null));
    state.prism.previewDs = null;
    $("nb-step-view").hidden = true;
    renderPrismSlots();
  });
  $("nb-load-btn").addEventListener("click", () =>
    loadPrism(
      state.keys.filter((key) => !slotFor(key).prism),
      { refresh: Boolean(state.entry) } // une étape mesurée plus tard : les données d'aujourd'hui, pas celles du cache
    )
  );
  $("nb-prism-slots").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-reload]");
    if (btn) loadPrism([btn.dataset.reload], { refresh: true });
  });
  $("nb-preview-options").addEventListener("change", () => {
    const prism = state.prism;
    if (!prism.previewDs || !prism.component) return;
    prism.options = DataViz.readOptions($("nb-preview-options"));
    DataViz.render($("nb-preview-viz"), prism.previewDs, prism.component, prism.options);
  });
  // Coller du texte dans un champ (même avec une image dans le presse-papiers, comme une copie de
  // Word ou d'Excel) le colle dans le champ : la planche d'images de la mesure active ne le voit pas.
  dialog.addEventListener("paste", (event) => {
    const target = event.target;
    const textField = target.matches && target.matches("textarea, input:not([type]), input[type=text], input[type=url], input[type=search]");
    if (textField && event.clipboardData && [...event.clipboardData.types].includes("text/plain")) event.stopPropagation();
  });

  return { open };
})();
