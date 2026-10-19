/* L'éditeur de modèles de rapport (page /lumiere, global `LumiereEditor`) : un modèle se compose slide par slide,
   comme un petit PowerPoint. À gauche la bande des slides (ajouter une grille, une section, un titre, un
   sommaire ; dupliquer, déplacer, retirer) ; au centre la slide en cours - son titre, sa grille (1×1 à 3×3) et
   ses cellules, chacune portant un bloc du catalogue (lumiereApi.blocks) ; à droite le bloc de la cellule
   choisie et le formulaire de ses options, généré depuis le catalogue ; en bas l'aperçu de la slide rendue sur
   une plaque d'essai (lumiereApi.preview, dans un cadre). « Enregistrer » envoie le modèle entier
   (lumiereApi.createTemplate / updateTemplate).

     LumiereEditor.mount(host, { onSaved, onClosed })   // le conteneur de l'éditeur (lumiere.html)
     LumiereEditor.open(template)                       // modifier un modèle enregistré
     LumiereEditor.create({ copyOf, context })          // un nouveau modèle, vide ou copié d'un autre

   Dépend de lumiereApi, escapeHtml. */

const LumiereEditor = (() => {
  const GRIDS = [
    [1, 1], [1, 2], [2, 1], [2, 2], [1, 3], [3, 1], [2, 3],
  ];
  const KIND_LABELS = { title: "Titre", section: "Section", summary: "Sommaire", grid: "Grille" };
  let host = null;
  let hooks = {};
  let catalog = null; // {blocks, max_grid}
  let template = null; // {key|null, name, description, context, slides}
  let at = 0; // la slide en cours
  let cell = null; // {r, c} la cellule choisie
  let dirty = false;
  let previewKey = "";

  // --- l'état -----------------------------------------------------------------------------------------

  function blockOf(key) {
    return (catalog.blocks || []).find((b) => b.key === key) || null;
  }

  function slide() {
    return template.slides[at];
  }

  function cellAt(s, r, c) {
    return (s.cells || []).find((x) => x.r === r && x.c === c) || null;
  }

  function defaults(block) {
    const options = {};
    block.options.forEach((o) => (options[o.key] = o.default));
    return options;
  }

  function touch() {
    dirty = true;
    host.querySelector(".js-save").disabled = false;
  }

  function newSlide(kind) {
    if (kind === "grid") return { kind: "grid", title: `Slide ${template.slides.length + 1}`, nrows: 1, ncols: 1, row_heights: ["1fr"], col_widths: ["1fr"], cells: [] };
    if (kind === "section") return { kind: "section", title: "Section", subtitle: "" };
    return { kind };
  }

  // --- le rendu ---------------------------------------------------------------------------------------

  function render() {
    renderHead();
    renderStrip();
    renderCanvas();
    renderSide();
  }

  function renderHead() {
    host.querySelector(".js-name").value = template.name;
    host.querySelector(".js-description").value = template.description || "";
    host.querySelector(".js-context").textContent = hooks.contexts && hooks.contexts[template.context] ? hooks.contexts[template.context] : template.context;
    host.querySelector(".js-save").disabled = !dirty;
  }

  function stripItem(s, i) {
    const label = s.kind === "grid" ? s.title || `Slide ${i + 1}` : s.kind === "section" ? s.title : KIND_LABELS[s.kind];
    const sub = s.kind === "grid" ? `${s.nrows}×${s.ncols} · ${(s.cells || []).length} bloc${(s.cells || []).length > 1 ? "s" : ""}` : KIND_LABELS[s.kind];
    return `<li class="lm-strip__item${i === at ? " is-current" : ""}" data-slide="${i}">
      <button type="button" class="lm-strip__card" data-select="${i}" aria-current="${i === at ? "true" : "false"}">
        <span class="lm-strip__num">${i + 1}</span>
        <span class="lm-strip__thumb lm-strip__thumb--${s.kind}">${s.kind === "grid" ? gridThumb(s) : ""}</span>
        <span class="lm-strip__label">${escapeHtml(label)}</span>
        <span class="lm-strip__sub">${escapeHtml(sub)}</span>
      </button>
    </li>`;
  }

  function gridThumb(s) {
    const cells = [];
    for (let r = 0; r < s.nrows; r++) for (let c = 0; c < s.ncols; c++) cells.push(`<i class="${cellAt(s, r, c) ? "is-filled" : ""}"></i>`);
    return `<span class="lm-thumb-grid" style="grid-template-columns:repeat(${s.ncols},1fr);grid-template-rows:repeat(${s.nrows},1fr)">${cells.join("")}</span>`;
  }

  function renderStrip() {
    host.querySelector(".js-strip").innerHTML = template.slides.map(stripItem).join("");
  }

  function renderCanvas() {
    const s = slide();
    const canvas = host.querySelector(".js-canvas");
    const tools = `<div class="lm-canvas__tools">
        <button type="button" class="btn btn-line" data-move="-1" ${at === 0 ? "disabled" : ""} title="Monter cette slide">↑</button>
        <button type="button" class="btn btn-line" data-move="1" ${at === template.slides.length - 1 ? "disabled" : ""} title="Descendre cette slide">↓</button>
        <button type="button" class="btn btn-line" data-duplicate title="Dupliquer cette slide">Dupliquer</button>
        <button type="button" class="btn btn-line" data-remove-slide ${template.slides.length === 1 ? "disabled" : ""} title="Retirer cette slide">Retirer</button>
      </div>`;
    if (s.kind === "title" || s.kind === "summary") {
      canvas.innerHTML = `${tools}<div class="lm-canvas__special lm-canvas__special--${s.kind}">
          <div class="page-eyebrow">${s.kind === "title" ? "Page de titre" : "Sommaire"}</div>
          <p class="help">${s.kind === "title" ? "Le titre du rapport (le contexte : « Plaque T001 »), le nom du modèle, l'auteur et la date : Lumière les remplit." : "La liste des slides du rapport, numérotées : Lumière la compose."}</p>
        </div>`;
      return;
    }
    if (s.kind === "section") {
      canvas.innerHTML = `${tools}<div class="lm-canvas__special lm-canvas__special--section">
          <div class="page-eyebrow">Section</div>
          <label class="lm-field"><span>Titre</span><input class="field js-slide-title" type="text" value="${escapeHtml(s.title || "")}" maxlength="80"></label>
          <label class="lm-field"><span>Sous-titre</span><input class="field js-slide-subtitle" type="text" value="${escapeHtml(s.subtitle || "")}" maxlength="80"></label>
        </div>`;
      return;
    }
    const grids = GRIDS.map(([r, c]) => `<button type="button" class="lm-gridpick${s.nrows === r && s.ncols === c ? " is-on" : ""}" data-grid="${r}x${c}" title="${r} ligne${r > 1 ? "s" : ""} × ${c} colonne${c > 1 ? "s" : ""}"><span class="lm-thumb-grid" style="grid-template-columns:repeat(${c},1fr);grid-template-rows:repeat(${r},1fr)">${"<i></i>".repeat(r * c)}</span></button>`).join("");
    const cells = [];
    for (let r = 0; r < s.nrows; r++) {
      for (let c = 0; c < s.ncols; c++) {
        const found = cellAt(s, r, c);
        const block = found ? blockOf(found.block.type) : null;
        const on = cell && cell.r === r && cell.c === c;
        cells.push(`<button type="button" class="lm-cell${found ? " is-filled" : ""}${on ? " is-on" : ""}" data-cell="${r},${c}" style="grid-row:${r + 1};grid-column:${c + 1}">
            ${found ? `<span class="lm-cell__block">${escapeHtml(block ? block.label : found.block.type)}</span><span class="lm-cell__opts">${escapeHtml(optionsSummary(found, block))}</span>` : `<span class="lm-cell__empty">+ un bloc</span>`}
          </button>`);
      }
    }
    canvas.innerHTML = `${tools}
      <label class="lm-field lm-field--title"><span>Titre de la slide</span><input class="field js-slide-title" type="text" value="${escapeHtml(s.title || "")}" maxlength="80"></label>
      <div class="lm-gridpicks" role="group" aria-label="Grille de la slide">${grids}</div>
      <div class="lm-grid" style="grid-template-columns:${(s.col_widths || []).join(" ") || "1fr"};grid-template-rows:${(s.row_heights || []).join(" ") || "1fr"}">${cells.join("")}</div>
      <p class="help" style="margin:8px 0 0;">Cliquez une cellule pour y poser un bloc ou régler ses options. Largeurs des colonnes : <input class="field lm-inline js-col-widths" type="text" value="${escapeHtml((s.col_widths || []).join(" "))}" placeholder="1fr 1fr" size="12"> · hauteurs des lignes : <input class="field lm-inline js-row-heights" type="text" value="${escapeHtml((s.row_heights || []).join(" "))}" placeholder="1fr" size="10"></p>`;
  }

  function optionsSummary(found, block) {
    if (!block) return "";
    const parts = block.options
      .filter((o) => o.kind !== "textarea")
      .map((o) => {
        const v = found.block.options[o.key];
        if (v === undefined || v === "" || v === null) return "";
        if (o.kind === "bool") return v ? o.label : "";
        if (o.kind === "choice") {
          const choice = (o.choices || []).find((x) => x.value === v);
          return choice ? choice.label : String(v);
        }
        return `${o.label.toLowerCase()} ${v}`;
      })
      .filter(Boolean);
    return parts.join(" · ");
  }

  function renderSide() {
    const side = host.querySelector(".js-side");
    const s = slide();
    if (s.kind !== "grid" || !cell) {
      side.innerHTML = `<p class="help">${s.kind === "grid" ? "Choisissez une cellule de la grille." : "Cette slide n'a pas de bloc."}</p>`;
      return;
    }
    const found = cellAt(s, cell.r, cell.c);
    const groups = {};
    catalog.blocks.forEach((b) => (groups[b.group] = groups[b.group] || []).push(b));
    const picker = Object.entries(groups)
      .map(([g, list]) => `<div class="lm-picker__group"><div class="lm-subtitle" style="margin:8px 0 4px;">${escapeHtml(g)}</div>${list
        .map((b) => `<button type="button" class="lm-picker__item${found && found.block.type === b.key ? " is-on" : ""}" data-block="${escapeHtml(b.key)}" title="${escapeHtml(b.description)}"><strong>${escapeHtml(b.label)}</strong><span>${escapeHtml(b.description)}</span>${b.needs ? `<em>${escapeHtml(b.needs)}</em>` : ""}${b.expands ? `<em>seul sur sa slide : une slide par élément</em>` : ""}</button>`)
        .join("")}</div>`)
      .join("");
    const block = found ? blockOf(found.block.type) : null;
    const form = found && block ? optionsForm(block, found.block.options) : "";
    side.innerHTML = `<div class="lm-side__head"><strong>Cellule ${cell.r + 1}, ${cell.c + 1}</strong>${found ? `<button type="button" class="btn btn-line" data-clear-cell>Vider</button>` : ""}</div>
      ${found ? `<div class="lm-side__current">${escapeHtml(block ? block.label : found.block.type)}</div>${form}<details class="lm-picker"><summary>Changer de bloc</summary>${picker}</details>` : `<p class="help" style="margin:0 0 6px;">Quel bloc poser ici ?</p>${picker}`}`;
  }

  function optionsForm(block, options) {
    if (!block.options.length) return `<p class="help">Ce bloc n'a pas d'option.</p>`;
    return `<div class="lm-options">${block.options
      .map((o) => {
        const v = options[o.key] === undefined ? o.default : options[o.key];
        const help = o.help ? `<small>${escapeHtml(o.help)}</small>` : "";
        if (o.kind === "textarea") return `<label class="lm-field"><span>${escapeHtml(o.label)}</span><textarea class="field" rows="6" data-option="${escapeHtml(o.key)}">${escapeHtml(v || "")}</textarea>${help}</label>`;
        if (o.kind === "bool") return `<label class="lm-check"><input type="checkbox" data-option="${escapeHtml(o.key)}" ${v ? "checked" : ""}> ${escapeHtml(o.label)}${help}</label>`;
        if (o.kind === "number") return `<label class="lm-field"><span>${escapeHtml(o.label)}</span><input class="field" type="number" data-option="${escapeHtml(o.key)}" value="${escapeHtml(String(v ?? ""))}" ${o.min !== null ? `min="${o.min}"` : ""} ${o.max !== null ? `max="${o.max}"` : ""}>${help}</label>`;
        if (o.kind === "choice") {
          const known = (o.choices || []).some((c) => c.value === v);
          return `<label class="lm-field"><span>${escapeHtml(o.label)}</span><select class="field" data-option="${escapeHtml(o.key)}">${(o.choices || []).map((c) => `<option value="${escapeHtml(c.value)}" ${c.value === v ? "selected" : ""}>${escapeHtml(c.label)}</option>`).join("")}${!known && v ? `<option value="${escapeHtml(v)}" selected>${escapeHtml(v)} (inconnu ici)</option>` : ""}</select>${help}</label>`;
        }
        return `<label class="lm-field"><span>${escapeHtml(o.label)}</span><input class="field" type="text" data-option="${escapeHtml(o.key)}" value="${escapeHtml(v || "")}">${help}</label>`;
      })
      .join("")}</div>`;
  }

  // --- les actions ------------------------------------------------------------------------------------

  function select(index) {
    at = Math.max(0, Math.min(index, template.slides.length - 1));
    cell = null;
    render();
    host.querySelector(".js-preview-frame").hidden = true;
  }

  function setGrid(r, c) {
    const s = slide();
    s.nrows = r;
    s.ncols = c;
    s.cells = (s.cells || []).filter((x) => x.r < r && x.c < c).map((x) => ({ ...x, rowspan: Math.min(x.rowspan || 1, r - x.r), colspan: Math.min(x.colspan || 1, c - x.c) }));
    s.row_heights = Array.from({ length: r }, (_, i) => (s.row_heights || [])[i] || "1fr");
    s.col_widths = Array.from({ length: c }, (_, i) => (s.col_widths || [])[i] || "1fr");
    if (cell && (cell.r >= r || cell.c >= c)) cell = null;
    touch();
    render();
  }

  function setBlock(key) {
    const s = slide();
    const block = blockOf(key);
    if (!block || !cell) return;
    const found = cellAt(s, cell.r, cell.c);
    if (found) found.block = { type: key, options: defaults(block) };
    else s.cells.push({ r: cell.r, c: cell.c, rowspan: 1, colspan: 1, block: { type: key, options: defaults(block) } });
    touch();
    render();
  }

  function setOption(key, value) {
    const found = cellAt(slide(), cell.r, cell.c);
    if (!found) return;
    found.block.options[key] = value;
    touch();
    renderStrip();
    renderCanvas();
  }

  function fractions(text, n) {
    const parts = String(text || "").trim().split(/[\s,]+/).filter(Boolean);
    const out = Array.from({ length: n }, (_, i) => (/^\d+(\.\d+)?fr$/.test(parts[i] || "") ? parts[i] : "1fr"));
    return out;
  }

  async function preview() {
    const frame = host.querySelector(".js-preview-frame");
    const box = host.querySelector(".js-preview-error");
    previewKey = host.querySelector(".js-preview-key").value.trim();
    if (!previewKey) {
      box.textContent = "Indiquez une plaque (son lasermark) pour l'aperçu.";
      box.hidden = false;
      return;
    }
    box.hidden = true;
    const button = host.querySelector(".js-preview");
    button.disabled = true;
    button.textContent = "Rendu…";
    try {
      const { html } = await lumiereApi.preview(template.context, template.slides, at, previewKey);
      frame.hidden = false;
      frame.srcdoc = html;
    } catch (err) {
      box.textContent = err.message || String(err);
      box.hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = "Aperçu de cette slide";
    }
  }

  async function save() {
    const box = host.querySelector(".js-error");
    box.hidden = true;
    const body = { name: host.querySelector(".js-name").value, description: host.querySelector(".js-description").value, slides: template.slides };
    try {
      const saved = template.key ? await lumiereApi.updateTemplate(template.key, body) : await lumiereApi.createTemplate({ ...body, context: template.context });
      template = { key: saved.key, name: saved.name, description: saved.description, context: saved.context, slides: saved.slides };
      dirty = false;
      render();
      if (options.onSaved) options.onSaved(saved);
    } catch (err) {
      box.textContent = err.message || String(err);
      box.hidden = false;
    }
  }

  function close() {
    if (dirty && !window.confirm("Des changements ne sont pas enregistrés. Fermer quand même ?")) return;
    host.hidden = true;
    template = null;
    dirty = false;
    if (options.onClosed) options.onClosed();
  }

  let options = {};

  function wire() {
    host.addEventListener("click", (event) => {
      const t = event.target;
      const sel = t.closest("[data-select]");
      if (sel) return select(Number(sel.dataset.select));
      const add = t.closest("[data-add-slide]");
      if (add) {
        template.slides.splice(at + 1, 0, newSlide(add.dataset.addSlide));
        touch();
        return select(at + 1);
      }
      const move = t.closest("[data-move]");
      if (move) {
        const to = at + Number(move.dataset.move);
        if (to < 0 || to >= template.slides.length) return;
        [template.slides[at], template.slides[to]] = [template.slides[to], template.slides[at]];
        touch();
        return select(to);
      }
      if (t.closest("[data-duplicate]")) {
        template.slides.splice(at + 1, 0, JSON.parse(JSON.stringify(slide())));
        touch();
        return select(at + 1);
      }
      if (t.closest("[data-remove-slide]")) {
        if (template.slides.length === 1) return;
        template.slides.splice(at, 1);
        touch();
        return select(Math.min(at, template.slides.length - 1));
      }
      const grid = t.closest("[data-grid]");
      if (grid) {
        const [r, c] = grid.dataset.grid.split("x").map(Number);
        return setGrid(r, c);
      }
      const picked = t.closest("[data-cell]");
      if (picked) {
        const [r, c] = picked.dataset.cell.split(",").map(Number);
        cell = { r, c };
        renderCanvas();
        return renderSide();
      }
      const block = t.closest("[data-block]");
      if (block) return setBlock(block.dataset.block);
      if (t.closest("[data-clear-cell]")) {
        const s = slide();
        s.cells = s.cells.filter((x) => !(x.r === cell.r && x.c === cell.c));
        touch();
        return render();
      }
      if (t.closest(".js-save")) return save();
      if (t.closest(".js-close")) return close();
      if (t.closest(".js-preview")) return preview();
    });
    host.addEventListener("input", (event) => {
      const t = event.target;
      if (t.classList.contains("js-name") || t.classList.contains("js-description")) return touch();
      if (t.classList.contains("js-slide-title")) {
        slide().title = t.value;
        touch();
        return renderStrip();
      }
      if (t.classList.contains("js-slide-subtitle")) {
        slide().subtitle = t.value;
        return touch();
      }
      if (t.dataset.option !== undefined) {
        const value = t.type === "checkbox" ? t.checked : t.type === "number" ? (t.value === "" ? "" : Number(t.value)) : t.value;
        return setOption(t.dataset.option, value);
      }
    });
    host.addEventListener("change", (event) => {
      const t = event.target;
      if (t.classList.contains("js-col-widths")) {
        slide().col_widths = fractions(t.value, slide().ncols);
        touch();
        return renderCanvas();
      }
      if (t.classList.contains("js-row-heights")) {
        slide().row_heights = fractions(t.value, slide().nrows);
        touch();
        return renderCanvas();
      }
      if (t.dataset.option !== undefined && t.tagName === "SELECT") return setOption(t.dataset.option, t.value);
    });
    host.querySelector(".js-preview-key").addEventListener("keydown", (event) => {
      if (event.key === "Enter") preview();
    });
  }

  async function ensureCatalog(context) {
    if (!catalog || catalog.context !== context) {
      const [blocks, templates] = await Promise.all([lumiereApi.blocks(context), lumiereApi.templates(context)]);
      catalog = { ...blocks, context };
      hooks = templates;
    }
  }

  async function start(t) {
    await ensureCatalog(t.context);
    template = { key: t.key || null, name: t.name, description: t.description || "", context: t.context, slides: JSON.parse(JSON.stringify(t.slides)) };
    at = 0;
    cell = null;
    host.hidden = false;
    host.querySelector(".js-preview-frame").hidden = true;
    host.querySelector(".js-error").hidden = true;
    host.querySelector(".js-preview-key").value = previewKey;
    render();
    host.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function mount(element, opts = {}) {
    host = element;
    options = opts;
    host.innerHTML = `
      <div class="lm-editor__head">
        <div class="lm-editor__fields">
          <label class="lm-field"><span>Nom du modèle</span><input class="field js-name" type="text" maxlength="80"></label>
          <label class="lm-field lm-field--wide"><span>Description</span><input class="field js-description" type="text" maxlength="500" placeholder="Ce que le rapport contient, pour qui"></label>
          <span class="help lm-editor__context">Contexte : <strong class="js-context"></strong></span>
        </div>
        <div class="lm-editor__actions">
          <button type="button" class="btn btn-line js-close">Fermer</button>
          <button type="button" class="btn btn-primary js-save" disabled>Enregistrer</button>
        </div>
      </div>
      <div class="error js-error" role="alert" hidden></div>
      <div class="lm-editor__body">
        <aside class="lm-strip-col">
          <ol class="lm-strip js-strip"></ol>
          <div class="lm-strip__add">
            <span class="help" style="margin:0 0 4px;">Ajouter après celle-ci</span>
            <button type="button" class="btn btn-line" data-add-slide="grid">+ Grille</button>
            <button type="button" class="btn btn-line" data-add-slide="section">+ Section</button>
            <button type="button" class="btn btn-line" data-add-slide="title">+ Titre</button>
            <button type="button" class="btn btn-line" data-add-slide="summary">+ Sommaire</button>
          </div>
        </aside>
        <section class="lm-canvas js-canvas" aria-label="Slide en cours"></section>
        <aside class="lm-side js-side" aria-label="Bloc de la cellule"></aside>
      </div>
      <div class="lm-preview">
        <div class="lm-preview__bar">
          <label class="lm-field lm-field--inline"><span>Plaque d'essai</span><input class="field js-preview-key" type="text" placeholder="lasermark" size="16"></label>
          <button type="button" class="btn btn-line js-preview">Aperçu de cette slide</button>
          <span class="help" style="margin:0;">Le rendu réel de la slide en cours, sur cette plaque (quelques secondes).</span>
        </div>
        <div class="error js-preview-error" role="alert" hidden></div>
        <iframe class="lm-preview__frame js-preview-frame" title="Aperçu de la slide" sandbox="allow-scripts" hidden></iframe>
      </div>`;
    host.hidden = true;
    wire();
  }

  return {
    mount,
    open: (t) => start(t),
    create: async ({ copyOf = null, context = "wafer" } = {}) => {
      if (copyOf) {
        const source = await lumiereApi.template(copyOf);
        return start({ key: null, name: `${source.name} (copie)`, description: source.description, context: source.context, slides: source.slides });
      }
      return start({ key: null, name: "Nouveau modèle", description: "", context, slides: [{ kind: "title" }, { kind: "grid", title: "Slide 2", nrows: 1, ncols: 1, row_heights: ["1fr"], col_widths: ["1fr"], cells: [] }, { kind: "summary" }] });
    },
    isOpen: () => Boolean(template),
  };
})();
