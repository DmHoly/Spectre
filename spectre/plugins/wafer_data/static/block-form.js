/* Le formulaire d'un bloc de fiche data (global `WaferBlockForm`) : choisir un genre (valeur, histogramme, boîte,
   nuage, cartographie, courbes, images), un type de données PRISM par plaque et ses colonnes - chaque liste ne
   propose que les colonnes du bon type (deux vecteurs pour des courbes, une colonne de liens pour une galerie) -,
   la couleur, les mesures gardées, les filtres et un nom. Le même formulaire sert la fiche data d'un projet
   (config.js) et les blocs libres d'une analyse de plaques (plugin meta_analysis) : ce qu'il fait d'un bloc
   validé, comment il lit les vraies colonnes d'un type et corrige un type de colonne, c'est l'appelant qui le dit.

     WaferBlockForm.mount(host, {
       catalog,                        // GET .../wafer-data/catalog : {hooks, types, roles, kinds, aggregates, ...}
       titleEl,                        // facultatif : l'intitulé du formulaire (« Ajouter un bloc » / « Modifier… »)
       canEditTypes,                   // corriger le type d'une colonne (pour tous les projets)
       probe(hook) -> hook à jour,     // lire les vraies colonnes ; null : jamais
       setColumnType(hook, column, type) -> hook à jour,
       submit({kind, hook, config, label}, editingId) -> Promise,
       titleOf(editingId) -> le nom du bloc modifié,
       kindNotes: {kind: texte},       // facultatif : la description d'un genre, propre à l'appelant
       showError(err), clearError(),
     }) -> {edit(block), reset(), editing(), render()}

   Utilitaires : WaferBlockForm.describe(block, catalog) - ce qu'un bloc lit, en une ligne (HTML) ; KIND_INFO. */

const WaferBlockForm = (() => {
  const KIND_INFO = {
    value: { desc: "Un chiffre : médiane, moyenne, part des LED allumées… situé parmi les plaques du projet.", glyph: '<path d="M4 19h16"/><path d="M7 15V9"/><path d="M12 15V5"/><path d="M17 15v-3"/>' },
    histogram: { desc: "La distribution d'un scalaire sur les dispositifs, colorée par catégorie si besoin.", glyph: '<path d="M3 20h18"/><rect x="5" y="12" width="3" height="8"/><rect x="10.5" y="6" width="3" height="14"/><rect x="16" y="10" width="3" height="10"/>' },
    boxplot: { desc: "Une boîte à moustaches d'un scalaire, une par valeur d'une catégorie (taille, design…).", glyph: '<path d="M7 3v4M7 17v4M17 6v3M17 15v3"/><rect x="4" y="7" width="6" height="10" rx="1"/><rect x="14" y="9" width="6" height="6" rx="1"/><path d="M4 12h6M14 12h6"/>' },
    scatter: { desc: "Un scalaire en fonction d'un autre, un point par dispositif, coloré par catégorie.", glyph: '<path d="M3 3v18h18"/><circle cx="8" cy="15" r="1.5"/><circle cx="12" cy="11" r="1.5"/><circle cx="16" cy="8" r="1.5"/><circle cx="18" cy="13" r="1.5"/>' },
    wafermap: { desc: "Un scalaire par position (X, Y) : une carte de la plaque, comme une PL.", glyph: '<circle cx="12" cy="12" r="9"/><path d="M8 8h3v3H8zM13 8h3v3h-3zM8 13h3v3H8z"/>' },
    curve: { desc: "Deux vecteurs l'un contre l'autre (EQE en fonction de V) : médiane et enveloppe, ou chaque courbe.", glyph: '<path d="M3 20h18"/><path d="M4 17c4-1 5-10 8-10s4 6 8 7"/>' },
    images: { desc: "Une galerie : une colonne de liens (EL pattern) ou un modèle de chemin, dans une visionneuse.", glyph: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 17-5-5-9 8"/>' },
  };
  const TYPE_SHORT = { number: "scalaire", vector: "vecteur", matrix: "vecteurs", image: "image", flag: "booléen", category: "catégorie", date: "date", other: "autre" };
  const DATE_LABEL = { latest: "mesure la plus récente", all: "toutes les mesures" };
  const BETTER_LABEL = { high: "plus haut = mieux", low: "plus bas = mieux", "": "" };
  const COLOR_NAMES = ["Bleu", "Ocre", "Vert", "Rouge", "Violet", "Sarcelle", "Brun", "Gris"];

  const svgIcon = (path, size = 16) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;

  // Ce qu'un bloc lit, en une ligne : son type de données, ses colonnes, sa couleur, ses mesures et ses filtres.
  function describe(b, catalog) {
    const c = b.config;
    const aggregates = Object.fromEntries(catalog.aggregates.map((a) => [a.key, a.label]));
    const hook = catalog.hooks.find((h) => h.hook === b.hook);
    if (b.kind === "images" && !b.hook) return [`<span class="mono">${escapeHtml(c.pattern)}</span>`, `${c.max} images au plus`].join(" · ");
    const parts = [escapeHtml(b.hook_title || (hook ? hook.title : b.hook))];
    if (b.kind === "value") parts.push(`${escapeHtml(c.column)} · ${escapeHtml(aggregates[c.aggregate] || c.aggregate)}${c.better ? ` · ${BETTER_LABEL[c.better]}` : ""}`);
    if (b.kind === "histogram") parts.push(escapeHtml(c.column));
    if (b.kind === "boxplot") parts.push(`${escapeHtml(c.column)}${c.group_by ? ` par ${escapeHtml(c.group_by)}` : ""}${c.log_y ? " (log)" : ""}`);
    if (b.kind === "wafermap") parts.push(`${escapeHtml(c.column)} par ${escapeHtml(c.x)}, ${escapeHtml(c.y)}`);
    if (b.kind === "curve" || b.kind === "scatter") parts.push(`${escapeHtml(c.y)} en fonction de ${escapeHtml(c.x)}${c.log_x ? " (x log)" : ""}${c.log_y ? " (y log)" : ""}`);
    if (b.kind === "curve") parts.push(c.mode === "curves" ? "chaque courbe" : "médiane et enveloppe");
    if (b.kind === "images") parts.push(`${escapeHtml(c.column)}${c.group_by ? ` par ${escapeHtml(c.group_by)}` : ""} · ${c.max} au plus`);
    if (c.color_by) parts.push(`couleur : ${escapeHtml(c.color_by)}`);
    else if (c.color && c.color !== 1 && !c.group_by) parts.push(`<span class="wd-keys__swatch" style="display:inline-block;background:var(--viz-${c.color})"></span> ${COLOR_NAMES[c.color - 1].toLowerCase()}`);
    if (c.date && hook && hook.dated) parts.push(DATE_LABEL[c.date]);
    (c.filters || []).forEach((f) => parts.push(escapeHtml(kpiFilterText(f))));
    if (b.available === false) parts.push('<span class="wd-row__missing">n\'est plus dans PRISM</span>');
    return parts.join(" · ");
  }

  function mount(host, opts) {
    const { catalog, titleEl = null, canEditTypes = false, kindNotes = {} } = opts;
    const hooks = catalog.hooks;
    const roles = catalog.roles;
    const showError = opts.showError || (() => {});
    const clearError = opts.clearError || (() => {});
    const probing = new Set(); // types de données en cours de lecture
    const probed = new Set(); // déjà lus (ou tentés) depuis l'ouverture : pas de relecture automatique

    const hookOf = (key) => hooks.find((h) => h.hook === key);
    const columnOf = (hook, name) => (hook ? hook.columns.find((c) => c.name === name) : null);
    // les colonnes proposées : une fois les vraies colonnes lues, celles que PRISM rend (ou typées à la main)
    const pool = (hook) => (hook.observed_at ? hook.columns.filter((c) => c.observed || c.chosen) : hook.columns);
    const fits = (column, role) => !column.type || roles[role].includes(column.type);

    function blank(kind = "value") {
      return {
        editing: null, kind, hook: (hooks.find((h) => h.representative) || hooks[0] || {}).hook || "", source: "column",
        column: "", x: "", y: "", aggregate: "", better: "", color_by: "", group_by: "", color: 1, log_x: null, log_y: false,
        mode: "envelope", date: "latest", filters: [], caption: ["", "", ""], max: null, pattern: "", label: "",
      };
    }

    function fromBlock(b) {
      const c = b.config;
      return {
        ...blank(b.kind), editing: b.id, hook: b.hook, source: b.kind === "images" && !b.hook ? "pattern" : "column",
        column: c.column || "", x: c.x || "", y: c.y || "", aggregate: c.aggregate || "", better: c.better || "",
        color_by: c.color_by || "", group_by: c.group_by || "", color: c.color || 1, log_x: !!c.log_x, log_y: !!c.log_y,
        mode: c.mode || "envelope", date: c.date || "latest", filters: [...(c.filters || [])],
        caption: [...(c.caption || []), "", "", ""].slice(0, 3), max: c.max || null, pattern: c.pattern || "", label: b.label || "",
      };
    }

    let form = blank();

    const options = (items, selected) => items.map(([value, text]) => `<option value="${escapeHtml(value)}"${value === selected ? " selected" : ""}>${escapeHtml(text)}</option>`).join("");
    const field = (id, label, control, wide = false) => `<div${wide ? ' class="wd-form__wide"' : ""}><label for="${id}">${label}</label>${control}</div>`;
    const faint = (text) => `<span class="help" style="display:inline;margin:0;font-weight:400;">${text}</span>`;

    // les colonnes d'un usage : celles du bon type - et, tant que le type n'est que deviné, les autres aussi
    function columnsFor(hook, role) {
      if (!hook) return [];
      return pool(hook).filter((c) => fits(c, role) || !c.sure).sort((a, b) => Number(fits(b, role)) - Number(fits(a, role)));
    }
    const columnText = (c) => `${c.name}${c.unit ? ` (${c.unit})` : ""} · ${c.type ? TYPE_SHORT[c.type] : "type inconnu"}${c.sure ? "" : " ?"}`;
    function pick(value, list, preferred = []) {
      const names = list.map((c) => c.name);
      if (names.includes(value)) return value;
      return preferred.find((p) => names.includes(p)) || names[0] || "";
    }
    function columnSelect(id, key, list, { optional = "", empty = "" } = {}) {
      if (!list.length && !optional) return `<p class="help" style="margin:0;">${empty}</p>`;
      const items = list.map((c) => [c.name, columnText(c)]);
      return `<select class="field" id="${id}" data-field="${key}">${optional ? options([["", optional]], form[key]) : ""}${options(items, form[key])}</select>`;
    }

    // les choix qui dépendent du type de données : les colonnes par défaut, gardées si elles conviennent encore
    function settle(hook) {
      const k = form.kind;
      if (!hook) return;
      if (k === "curve") {
        const vectors = columnsFor(hook, "vector");
        form.x = pick(form.x, vectors, ["I", "J", "V"]);
        form.y = pick(form.y, vectors.filter((c) => c.name !== form.x), ["EQE", "L", "WPE"]);
        if (form.log_x === null) form.log_x = ["I", "J"].includes(form.x);
      } else if (k === "scatter") {
        const numbers = columnsFor(hook, "number").filter((c) => ![hook.x, hook.y].includes(c.name));
        form.x = pick(form.x, numbers, ["J_at_MaxEQE", "V at Max EQE"]);
        form.y = pick(form.y, numbers.filter((c) => c.name !== form.x), [hook.representative]);
      } else if (k === "images") {
        form.column = pick(form.column, columnsFor(hook, "image").filter((c) => fits(c, "image")), ["full_path"]) || pick(form.column, columnsFor(hook, "image"));
      } else {
        const role = k === "value" ? "aggregate" : "number";
        const list = columnsFor(hook, role).filter((c) => k === "value" || ![hook.x, hook.y].includes(c.name));
        form.column = pick(form.column, list, [hook.representative]);
        if (k === "value") {
          const flag = (columnOf(hook, form.column) || {}).type === "flag";
          if (flag) form.aggregate = "share";
          else if (!form.aggregate || (form.aggregate === "share" && !form.editing)) form.aggregate = "median";
        }
      }
      if (form.log_x === null) form.log_x = false;
    }

    function hookLine(hook) {
      if (!hook) return "";
      const busy = probing.has(hook.hook);
      const said = hook.observed_at
        ? `Types lus sur de vraies lignes le ${escapeHtml(formatDate(hook.observed_at))}`
        : "Types devinés d'après la fiche PRISM (marqués « ? »)";
      const columns = hook.columns
        .map((c) => {
          const source = c.chosen ? ["chosen", "choisi"] : c.observed_type ? ["observed", "observé"] : hook.observed_at && !c.observed ? ["guessed", "pas rendue"] : ["guessed", "deviné"];
          const auto = c.observed_type || c.guessed;
          const choices = [["", `Automatique${auto ? ` (${TYPE_SHORT[auto]})` : ""}`], ...catalog.types.map((t) => [t.key, t.label])];
          return `<tr>
            <td class="mono">${escapeHtml(c.name)}${c.unit ? ` <span class="help" style="display:inline;">(${escapeHtml(c.unit)})</span>` : ""}</td>
            <td><select class="field" data-type-col="${escapeHtml(c.name)}" aria-label="Type de ${escapeHtml(c.name)}" ${canEditTypes ? "" : "disabled"}>${options(choices, c.chosen || "")}</select></td>
            <td><span class="wd-type-src wd-type-src--${source[0]}">${source[1]}</span></td>
            <td class="mono" title="${escapeHtml(c.description)}">${escapeHtml(c.example || "")}</td>
          </tr>`;
        })
        .join("");
      return `<div class="wd-hookline">
          <span>${said}</span>
          ${opts.probe ? `<button type="button" class="btn btn-line" data-probe="${escapeHtml(hook.hook)}" ${busy ? "disabled" : ""}>${busy ? "Lecture des colonnes…" : hook.observed_at ? "Relire" : "Lire les vraies colonnes"}</button>` : ""}
        </div>
        <details class="wd-types-box"${form.typesOpen ? " open" : ""}>
          <summary class="help" style="cursor:pointer;margin-top:6px;">Colonnes et types (${hook.columns.length})${canEditTypes ? " - un type mal reconnu se corrige ici, pour tous les projets" : ""}</summary>
          <div class="wd-types"><table><thead><tr><th>Colonne</th><th>Type</th><th>Source</th><th>Exemple</th></tr></thead><tbody>${columns}</tbody></table></div>
        </details>`;
    }

    function swatches() {
      return `<div class="wd-swatches" role="radiogroup" aria-label="Couleur">${COLOR_NAMES.map(
        (name, i) => `<button type="button" class="wd-swatch" role="radio" data-color="${i + 1}" aria-checked="${form.color === i + 1}" aria-label="${name}" title="${name}" style="background:var(--viz-${i + 1})" tabindex="${form.color === i + 1 ? 0 : -1}"></button>`
      ).join("")}</div>`;
    }

    function render() {
      const k = form.kind;
      const pattern = k === "images" && form.source === "pattern";
      // les types de données qui ont une colonne du type que ce genre lit (vecteurs pour des courbes...)
      const role = { value: "aggregate", curve: "vector", images: "image" }[k] || "number";
      let usable = hooks.filter((h) => pool(h).some((c) => c.type && roles[role].includes(c.type)) && (k !== "wafermap" || (h.x && h.y)));
      if (!usable.length && k !== "wafermap") usable = hooks;
      if (!pattern && !usable.some((h) => h.hook === form.hook)) form.hook = usable[0] ? usable[0].hook : "";
      const hook = pattern ? null : hookOf(form.hook);
      settle(hook);
      if (hook && opts.probe && !hook.observed_at && !probed.has(hook.hook)) probe(hook.hook, { quiet: true });

      const editing = form.editing !== null;
      if (titleEl) titleEl.textContent = editing ? `Modifier le bloc « ${opts.titleOf ? opts.titleOf(form.editing) : ""} »` : "Ajouter un bloc";
      const kinds = catalog.kinds
        .map(
          (kind) => `<button type="button" class="wd-kind" data-kind="${kind.key}" aria-pressed="${kind.key === k}" ${editing && kind.key !== k ? "disabled" : ""}>
            <span class="wd-kind__title">${svgIcon(KIND_INFO[kind.key].glyph)}${escapeHtml(kind.label)}</span>
            <span class="wd-kind__desc">${escapeHtml(kindNotes[kind.key] || KIND_INFO[kind.key].desc)}</span></button>`
        )
        .join("");
      let fields = "";
      if (k === "images") {
        fields += field(
          "wd-f-source",
          "Où sont les images",
          `<div class="wd-mode" id="wd-f-source">
            <label><input type="radio" name="wd-source" data-field="source" value="column" ${form.source === "column" ? "checked" : ""} ${editing ? "disabled" : ""}> Une colonne de liens d'un type de données PRISM (EL pattern…)</label>
            <label><input type="radio" name="wd-source" data-field="source" value="pattern" ${pattern ? "checked" : ""} ${editing ? "disabled" : ""}> Un modèle de chemin</label>
          </div>`,
          true
        );
      }
      if (pattern) {
        fields += field(
          "wd-f-pattern",
          "Où chercher les images",
          `<input type="text" class="field mono" id="wd-f-pattern" data-field="pattern" value="${escapeHtml(form.pattern)}" placeholder="\\\\serveur\\mesures\\PL\\{lot}\\{lasermark}_*.png" maxlength="500">
           <p class="help" style="margin-top:6px;">Un chemin de fichier : ${catalog.placeholders.map((p) => `<span class="mono">{${p}}</span>`).join(", ")} prennent les valeurs de la plaque (le lot et le run viennent de sa vie en ligne) ; <span class="mono">*</span> et <span class="mono">?</span> dans le nom du fichier. Le dossier doit être sous un dossier autorisé pour les images externes.</p>`,
          true
        );
        fields += field("wd-f-max", "Images au plus", `<input type="number" class="field" id="wd-f-max" data-field="max" min="1" max="${catalog.limits.pattern_images}" value="${form.max || 8}">`);
      } else if (!hook) {
        const why = { wafermap: "Aucun type de données PRISM n'a de colonnes de position (X, Y).", images: "Aucun type de données PRISM n'a de colonne de liens vers des images." }[k];
        fields += `<p class="help wd-form__wide">${why || "PRISM ne propose aucun type de données par plaque pour l'instant."}</p>`;
      } else {
        fields += `<div class="wd-form__wide"><label for="wd-f-hook">Type de données</label>
          <select class="field" id="wd-f-hook" data-field="hook" style="max-width:520px;" ${editing ? "disabled" : ""}>${options(usable.map((h) => [h.hook, `${h.title} · ${h.category}`]), form.hook)}</select>
          ${hookLine(hook)}</div>`;
        const groups = columnsFor(hook, "group").filter((c) => fits(c, "group"));
        const groupSelect = (key, label, hint) => field(`wd-f-${key}`, `${label} ${faint(hint)}`, columnSelect(`wd-f-${key}`, key, groups, { optional: "Aucune (une seule couleur)" }));
        if (k === "curve" || k === "scatter") {
          const role = k === "curve" ? "vector" : "number";
          const list = columnsFor(hook, role);
          const empty = `Aucune colonne de type ${TYPE_SHORT[role]} dans « ${escapeHtml(hook.title)} » : lisez les vraies colonnes, ou corrigez un type ci-dessus.`;
          fields += field("wd-f-x", `Abscisse ${faint(k === "curve" ? "(un vecteur)" : "(un scalaire)")}`, columnSelect("wd-f-x", "x", list, { empty }));
          fields += field("wd-f-y", `Ordonnée ${faint(k === "curve" ? "(un vecteur)" : "(un scalaire)")}`, columnSelect("wd-f-y", "y", list, { empty }));
          fields += `<div class="wd-form__checks"><label><input type="checkbox" id="wd-f-logx" data-field="log_x" ${form.log_x ? "checked" : ""}> abscisse en log</label><label><input type="checkbox" id="wd-f-logy" data-field="log_y" ${form.log_y ? "checked" : ""}> ordonnée en log</label></div>`;
          if (k === "curve") {
            fields += field(
              "wd-f-mode",
              "Montrer",
              `<div class="wd-mode" id="wd-f-mode">${catalog.curve_modes
                .map((m) => `<label><input type="radio" name="wd-mode" data-field="mode" value="${m.key}" ${form.mode === m.key ? "checked" : ""}> ${escapeHtml(m.label)}</label>`)
                .join("")}</div>`
            );
          }
          fields += groupSelect("color_by", "Colorer par", "(une couleur par valeur)");
        } else if (k === "images") {
          const links = columnsFor(hook, "image");
          fields += field("wd-f-column", `Colonne des liens ${faint("(un chemin d'image par ligne)")}`, columnSelect("wd-f-column", "column", links, { empty: `Aucune colonne de liens vers des images dans « ${escapeHtml(hook.title)} ».` }));
          fields += field("wd-f-group_by", `Grouper par ${faint("(type d'image…)")}`, columnSelect("wd-f-group_by", "group_by", groups, { optional: "Aucun groupe" }));
          const captions = pool(hook).filter((c) => fits(c, "caption") && c.name !== form.column);
          fields += `<div class="wd-form__wide"><label for="wd-f-caption0">Légende ${faint(`(jusqu'à ${catalog.limits.caption} colonnes de la ligne : device, numéro d'image…)`)}</label>
            <div class="wd-filter-row" style="grid-template-columns:repeat(3, minmax(140px, 1fr));">${[0, 1, 2]
              .map((i) => `<select class="field" id="wd-f-caption${i}" data-caption="${i}" aria-label="Légende ${i + 1}">${options([["", "—"]], form.caption[i])}${options(captions.map((c) => [c.name, c.name]), form.caption[i])}</select>`)
              .join("")}</div></div>`;
          fields += field("wd-f-max", `Images gardées par plaque ${faint(`(${catalog.limits.images} au plus)`)}`, `<input type="number" class="field" id="wd-f-max" data-field="max" min="1" max="${catalog.limits.images}" value="${form.max || 60}">`);
        } else {
          const role = k === "value" ? "aggregate" : "number";
          const list = columnsFor(hook, role);
          fields += field("wd-f-column", k === "wafermap" ? "Colonne à cartographier" : `Colonne ${faint(k === "value" ? "(un scalaire ou un booléen)" : "(un scalaire)")}`, columnSelect("wd-f-column", "column", list, { empty: `Aucune colonne de type scalaire dans « ${escapeHtml(hook.title)} ».` }));
          if (k === "value") {
            const flag = (columnOf(hook, form.column) || {}).type === "flag";
            const allowed = flag ? catalog.aggregates.filter((a) => a.key === "share") : catalog.aggregates;
            fields += field("wd-f-aggregate", "Agrégat sur les lignes de la plaque", `<select class="field" id="wd-f-aggregate" data-field="aggregate">${options(allowed.map((a) => [a.key, a.label]), form.aggregate)}</select>`);
            fields += field("wd-f-better", "Sens", `<select class="field" id="wd-f-better" data-field="better">${options([["", "Neutre"], ["high", "Plus haut = mieux"], ["low", "Plus bas = mieux"]], form.better)}</select>`);
          }
          if (k === "histogram") fields += groupSelect("color_by", "Colorer par", "(barres empilées par valeur)");
          if (k === "boxplot") {
            fields += groupSelect("group_by", "Une boîte par", "(taille, design, capteur…)");
            fields += `<div class="wd-form__checks"><label><input type="checkbox" id="wd-f-logy" data-field="log_y" ${form.log_y ? "checked" : ""}> échelle log</label></div>`;
          }
        }
        if (["histogram", "boxplot", "scatter", "curve"].includes(k) && !form.color_by && !form.group_by) fields += field("wd-f-color", "Couleur", swatches());
        if (hook.dated) fields += field("wd-f-date", "Mesures", `<select class="field" id="wd-f-date" data-field="date">${options([["latest", "La plus récente"], ["all", "Toutes, mêlées"]], form.date)}</select>`);
        const filterable = pool(hook).filter((c) => !["vector", "matrix"].includes(c.type));
        const chips = form.filters.map((f, i) => `<span class="wd-chip">${escapeHtml(kpiFilterText(f))}<button type="button" class="wd-chip__x" data-drop-filter="${i}" aria-label="Retirer le filtre ${escapeHtml(kpiFilterText(f))}">×</button></span>`).join("");
        fields += `<div class="wd-form__wide"><label for="wd-f-fcol">Filtres ${faint("(les lignes gardées les passent tous)")}</label>
          ${chips ? `<div class="wd-filters" style="margin-bottom:8px;">${chips}</div>` : ""}
          <div class="wd-filter-row">
            <select class="field" id="wd-f-fcol" aria-label="Colonne à filtrer">${options(filterable.map((c) => [c.name, columnText(c)]), (filterable[0] || {}).name)}</select>
            <select class="field" id="wd-f-fop" aria-label="Comparaison">${options(KPI_OPERATORS, "eq")}</select>
            <input type="text" class="field" id="wd-f-fval" placeholder="Valeur (ex : LightImage)" aria-label="Valeur du filtre">
            <button type="button" class="btn btn-tint" id="wd-f-fadd">Ajouter le filtre</button>
          </div></div>`;
      }
      fields += field("wd-f-label", `Nom affiché ${faint("(facultatif)")}`, `<input type="text" class="field" id="wd-f-label" data-field="label" maxlength="80" value="${escapeHtml(form.label)}">`);
      host.innerHTML = `<div class="wd-kinds" role="group" aria-label="Genre de bloc">${kinds}</div>
        <div class="wd-form">${fields}</div>
        <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap;">
          <button type="button" class="btn btn-primary" id="wd-f-submit">${editing ? "Enregistrer les changements" : "Ajouter le bloc"}</button>
          ${editing || opts.onCancel ? '<button type="button" class="btn btn-line" id="wd-f-cancel">Annuler</button>' : ""}
        </div>`;
    }

    // re-rend le formulaire en gardant le focus sur le même contrôle
    function rerender() {
      const id = document.activeElement && host.contains(document.activeElement) ? document.activeElement.id : null;
      const color = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.color : null;
      render();
      const again = color ? host.querySelector(`[data-color="${color}"]`) : id ? host.querySelector(`#${id}`) : null;
      if (again) again.focus();
    }

    async function probe(hook, { quiet = false } = {}) {
      probing.add(hook);
      probed.add(hook);
      if (!quiet) rerender();
      try {
        const fresh = await opts.probe(hook);
        hooks.splice(hooks.findIndex((h) => h.hook === hook), 1, fresh);
      } catch (err) {
        if (!quiet) showError(err); // en silence : sans plaque où lire, les types devinés restent
      } finally {
        probing.delete(hook);
        rerender();
      }
    }

    function configOf() {
      const k = form.kind;
      if (k === "images" && form.source === "pattern") return { source: "pattern", pattern: form.pattern, max: Number(form.max) || 8 };
      const config = { date: form.date, filters: form.filters };
      if (k === "curve" || k === "scatter") Object.assign(config, { x: form.x, y: form.y, log_x: !!form.log_x, log_y: !!form.log_y, color_by: form.color_by || null });
      else config.column = form.column;
      if (k === "curve") config.mode = form.mode;
      if (k === "value") Object.assign(config, { aggregate: form.aggregate, better: form.better });
      if (k === "histogram") config.color_by = form.color_by || null;
      if (k === "boxplot") Object.assign(config, { group_by: form.group_by || null, log_y: !!form.log_y });
      if (k === "images") Object.assign(config, { group_by: form.group_by || null, caption: form.caption.filter(Boolean), max: Number(form.max) || 60 });
      if (["histogram", "boxplot", "scatter", "curve"].includes(k)) config.color = form.color;
      return config;
    }

    host.addEventListener("click", async (event) => {
      const kind = event.target.closest("[data-kind]");
      const drop = event.target.closest("[data-drop-filter]");
      const color = event.target.closest("[data-color]");
      const probeBtn = event.target.closest("[data-probe]");
      if (kind && form.editing === null) {
        const keep = { hook: form.hook, filters: form.filters, label: form.label };
        form = { ...blank(kind.dataset.kind), ...keep };
        render();
        host.querySelector(`[data-kind="${form.kind}"]`).focus();
      } else if (color) {
        form.color = Number(color.dataset.color);
        rerender();
      } else if (probeBtn) {
        clearError();
        probe(probeBtn.dataset.probe);
      } else if (drop) {
        form.filters.splice(Number(drop.dataset.dropFilter), 1);
        render();
      } else if (event.target.closest("#wd-f-fadd")) {
        const raw = host.querySelector("#wd-f-fval").value.trim();
        if (!raw) return host.querySelector("#wd-f-fval").focus();
        form.filters.push({ column: host.querySelector("#wd-f-fcol").value, op: host.querySelector("#wd-f-fop").value, value: raw });
        render();
      } else if (event.target.closest("#wd-f-cancel")) {
        form = blank();
        render();
        if (opts.onCancel) opts.onCancel();
      } else if (event.target.closest("#wd-f-submit")) {
        clearError();
        const button = event.target.closest("#wd-f-submit");
        button.disabled = true;
        try {
          const pattern = form.kind === "images" && form.source === "pattern";
          await opts.submit({ kind: form.kind, hook: pattern ? "" : form.hook, config: configOf(), label: form.label || "" }, form.editing);
          form = { ...blank(form.kind), hook: form.hook };
          render();
        } catch (err) {
          button.disabled = false;
          showError(err);
        }
      }
    });
    host.addEventListener("keydown", (event) => {
      const swatch = event.target.closest("[data-color]");
      if (!swatch || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      form.color = ((form.color - 1 + (event.key === "ArrowRight" ? 1 : -1) + COLOR_NAMES.length) % COLOR_NAMES.length) + 1;
      rerender();
      host.querySelector(`[data-color="${form.color}"]`).focus();
      event.preventDefault();
    });
    host.addEventListener("input", (event) => {
      const key = event.target.dataset.field;
      if (key && event.target.type === "text") form[key] = event.target.value;
    });
    host.addEventListener(
      "toggle",
      (event) => {
        if (event.target.classList && event.target.classList.contains("wd-types-box")) form.typesOpen = event.target.open;
      },
      true
    );
    host.addEventListener("change", async (event) => {
      const el = event.target;
      if (el.dataset.typeCol) {
        clearError();
        try {
          const fresh = await opts.setColumnType(form.hook, el.dataset.typeCol, el.value || null);
          hooks.splice(hooks.findIndex((h) => h.hook === form.hook), 1, fresh);
          rerender();
        } catch (err) {
          showError(err);
        }
        return;
      }
      if (el.dataset.caption !== undefined) {
        form.caption[Number(el.dataset.caption)] = el.value;
        return;
      }
      const key = el.dataset.field;
      if (!key || el.type === "text") return;
      form[key] = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
      if (key === "hook") {
        form.filters = [];
        form.column = form.x = form.y = form.color_by = form.group_by = "";
        form.caption = ["", "", ""];
        form.log_x = null;
      }
      if (key === "x" && form.kind === "curve") form.log_x = ["I", "J"].includes(form.x);
      rerender();
    });

    render();
    return {
      render,
      editing: () => form.editing,
      edit(block) {
        form = fromBlock(block);
        render();
      },
      reset() {
        form = blank();
        render();
      },
    };
  }

  return { mount, describe, KIND_INFO, COLOR_NAMES };
})();
