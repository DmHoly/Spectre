/* Le tableau d'une comparaison de structures (global `Comparator`), le même partout où l'on compare
   des structures : la page /comparateur, l'évolution d'un µprojet, l'évolution d'une référence.

   Ce que le serveur rend (GET /api/comparisons, comparator/table.py) est montré tel quel : une ligne
   par plaque ou structure, une colonne par paramètre regroupée par étape (le substrat d'abord), et
   le statut de chaque cellule face à la ligne de base. La page ne compare rien elle-même.

   Code couleur (la légende est toujours au-dessus du tableau, jamais la couleur seule : chaque
   en-tête marqué porte aussi son mot, chaque cellule son infobulle) :
   rouge = paramètre modifié, violet = paramètre ajouté (une colonne que la base n'a pas),
   vert = couche en plus, orange = étape déplacée, hachuré = couche absente.

   Comparator.mount(el, result, {tools, onBaseline, onRemove, onMove, emptyText}) -> {update(result)} :
   `tools` ajoute à chaque ligne « Base », monter, descendre, retirer (la page du comparateur).
   Comparator.studyItem / waferItem / referenceItem : les jetons d'une ligne ; pageUrl(items, baseline) :
   l'adresse du comparateur sur ces lignes. */

const Comparator = (() => {
  const ONLY_DIFF_KEY = "spectre.comparator.onlyDifferences";

  const LEGEND = [
    ["changed", "≠", "Paramètre modifié"],
    ["added_param", "+", "Paramètre ajouté"],
    ["added_layer", "+", "Couche en plus"],
    ["moved", "↕", "Ordre des étapes changé"],
    ["absent", "−", "Couche absente"],
  ];
  const STATUS_WORDS = {
    changed: "modifié",
    added_param: "paramètre ajouté",
    added_layer: "couche en plus",
    moved: "étape déplacée",
    absent: "couche absente",
  };

  function studyItem(microprojectSlug, experimentId, versionId, place) {
    return `study:${microprojectSlug}/${experimentId}${versionId ? `@${versionId}` : ""}${place !== undefined && place !== null ? `~${place}` : ""}`;
  }
  function waferItem(lasermark) {
    return `wafer:${lasermark}`;
  }
  function referenceItem(referenceSlug, number) {
    return `reference:${referenceSlug}${number ? `@${number}` : ""}`;
  }
  function pageUrl(items, baseline) {
    const query = new URLSearchParams();
    items.forEach((item) => query.append("item", item));
    if (baseline) query.set("base", String(baseline));
    return `/comparateur?${query.toString()}`;
  }

  function readOnlyDiff() {
    try {
      return localStorage.getItem(ONLY_DIFF_KEY) === "1";
    } catch (err) {
      return false;
    }
  }
  function saveOnlyDiff(value) {
    try {
      localStorage.setItem(ONLY_DIFF_KEY, value ? "1" : "0");
    } catch (err) {
      /* sans stockage : le choix vaut pour cette page */
    }
  }

  function plural(n, one, many) {
    return `${n} ${n > 1 ? many : one}`;
  }

  // « 3 paramètres modifiés · 1 couche en plus » - ce qui distingue une ligne (ou le tableau) de la base
  function summaryText(summary) {
    const parts = [];
    if (summary.changed) parts.push(plural(summary.changed, "paramètre modifié", "paramètres modifiés"));
    if (summary.added_params) parts.push(plural(summary.added_params, "paramètre ajouté", "paramètres ajoutés"));
    if (summary.added_layers) parts.push(plural(summary.added_layers, "couche en plus", "couches en plus"));
    if (summary.moved_layers) parts.push(plural(summary.moved_layers, "étape déplacée", "étapes déplacées"));
    if (summary.absent_layers) parts.push(plural(summary.absent_layers, "couche absente", "couches absentes"));
    return parts.join(" · ");
  }

  function legendHtml() {
    return `<ul class="cmp-legend" aria-label="Code couleur">${LEGEND.map(
      ([status, mark, text]) => `<li><span class="cmp-swatch cmp-swatch--${status}" aria-hidden="true">${mark}</span>${text}</li>`
    ).join("")}</ul>`;
  }

  const ICONS = {
    up: '<path d="m6 15 6-6 6 6"/>',
    down: '<path d="m6 9 6 6 6-6"/>',
    remove: '<path d="M6 6l12 12M18 6 6 18"/>',
  };
  function icon(name) {
    return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
  }

  function rowHeadHtml(row, index, count, options) {
    const title = row.url ? `<a class="cmp-row__label" href="${escapeHtml(row.url)}">${escapeHtml(row.label)}</a>` : `<span class="cmp-row__label">${escapeHtml(row.label)}</span>`;
    const version = row.version ? `<span class="cmp-row__version">${escapeHtml(row.version)}</span>` : "";
    const badge = row.badge ? `<span class="cmp-row__badge" title="La plaque de référence de la campagne">${escapeHtml(row.badge)}</span>` : "";
    const base = row.baseline ? `<span class="cmp-row__base">Base</span>` : "";
    const sub = [row.sublabel, row.context].filter(Boolean).join(" · ");
    let diff = "";
    if (!row.baseline && row.cells) {
      const text = summaryText(row.summary);
      diff = `<span class="cmp-row__diff${text ? "" : " is-same"}">${escapeHtml(text || "identique à la base")}</span>`;
    }
    let tools = "";
    if (options.tools) {
      const name = escapeHtml(row.label);
      tools = `
        <span class="cmp-row__tools">
          ${row.baseline ? "" : `<button type="button" class="cmp-tool cmp-tool--base" data-action="baseline" data-index="${index}" aria-label="Prendre ${name} comme base" title="Prendre comme base">Base</button>`}
          <button type="button" class="cmp-tool" data-action="up" data-index="${index}" aria-label="Monter ${name}" title="Monter" ${index === 0 ? "disabled" : ""}>${icon("up")}</button>
          <button type="button" class="cmp-tool" data-action="down" data-index="${index}" aria-label="Descendre ${name}" title="Descendre" ${index === count - 1 ? "disabled" : ""}>${icon("down")}</button>
          <button type="button" class="cmp-tool cmp-tool--remove" data-action="remove" data-index="${index}" aria-label="Retirer ${name} de la comparaison" title="Retirer">${icon("remove")}</button>
        </span>`;
    }
    return `
      <th scope="row" class="cmp-row__head">
        <div class="cmp-row__top">${title}${version}${badge}${base}</div>
        ${sub ? `<div class="cmp-row__sub">${escapeHtml(sub)}</div>` : ""}
        ${diff || tools ? `<div class="cmp-row__foot">${diff}${tools}</div>` : ""}
      </th>`;
  }

  function cellHtml(cell, first) {
    const classes = ["cmp-cell", `cmp-cell--${cell.status}`];
    if (cell.changed) classes.push("is-changed");
    if (first) classes.push("is-first");
    const word = cell.changed ? `${STATUS_WORDS[cell.status]}, modifié` : STATUS_WORDS[cell.status];
    const hidden = word ? `<span class="cmp-sr"> (${word})</span>` : "";
    const title = cell.title ? ` title="${escapeHtml(cell.title)}"` : "";
    return `<td class="${classes.join(" ")}"${title}>${escapeHtml(cell.text)}${hidden}</td>`;
  }

  function flagHtml(status) {
    if (status === "added_layer") return `<span class="cmp-flag cmp-flag--added_layer">+ couche</span>`;
    if (status === "moved") return `<span class="cmp-flag cmp-flag--moved">↕ déplacée</span>`;
    if (status === "added_param") return `<span class="cmp-flag cmp-flag--added_param">+ paramètre</span>`;
    return "";
  }

  function tableHtml(result, options, onlyDiff) {
    const rows = result.rows;
    // les colonnes montrées : toutes, ou celles qui diffèrent de la base (un groupe sans colonne tombe)
    const groups = result.groups
      .map((group, g) => {
        const start = result.groups.slice(0, g).reduce((n, other) => n + other.columns.length, 0);
        const columns = group.columns.map((column, c) => ({ ...column, flat: start + c })).filter((column) => !onlyDiff || column.differs);
        return { ...group, shown: columns };
      })
      .filter((group) => group.shown.length);
    const width = groups.reduce((n, group) => n + group.shown.length, 0);

    const groupHead = groups
      .map((group) => {
        const where = group.position ? `n° ${group.position}` : "";
        const kind = group.kind_label && group.kind_label !== group.label ? group.kind_label : "";
        const meta = [kind, where].filter(Boolean).join(" · ");
        return `
          <th scope="colgroup" colspan="${group.shown.length}" class="cmp-group${group.status ? ` cmp-group--${group.status}` : ""}">
            <span class="cmp-group__name">${escapeHtml(group.label)}</span>
            ${meta ? `<span class="cmp-group__meta">${escapeHtml(meta)}</span>` : ""}
            ${flagHtml(group.status)}
          </th>`;
      })
      .join("");
    const columnHead = groups
      .map((group) =>
        group.shown
          .map(
            (column, c) =>
              `<th scope="col" class="cmp-col${column.status ? ` cmp-col--${column.status}` : ""}${c === 0 ? " is-first" : ""}">${escapeHtml(column.label)}${flagHtml(column.status)}</th>`
          )
          .join("")
      )
      .join("");
    const body = rows
      .map((row, index) => {
        const head = rowHeadHtml(row, index, rows.length, options);
        let cells;
        if (!row.cells) {
          const text = row.error || row.note || "";
          cells = `<td class="cmp-cell cmp-cell--${row.error ? "error" : "note"}" colspan="${Math.max(width, 1)}">${escapeHtml(text)}</td>`;
        } else if (!width) {
          cells = `<td class="cmp-cell cmp-cell--note">—</td>`;
        } else {
          cells = groups
            .map((group) => group.shown.map((column, c) => cellHtml(row.cells[column.flat], c === 0)).join(""))
            .join("");
        }
        return `<tr class="cmp-row${row.baseline ? " is-base" : ""}${row.error ? " is-error" : ""}">${head}${cells}</tr>`;
      })
      .join("");
    const emptyColumns = !width && rows.some((row) => row.cells);
    return `
      <div class="cmp-scroll" role="region" aria-label="Tableau de comparaison (défile horizontalement)" tabindex="0">
        <table class="cmp-table">
          <thead>
            <tr class="cmp-head-groups"><th scope="col" rowspan="2" class="cmp-corner">Plaque ou structure</th>${groupHead}</tr>
            <tr class="cmp-head-columns">${columnHead}</tr>
          </thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      ${emptyColumns && onlyDiff ? `<p class="cmp-empty">Aucune différence avec la base : décochez « Seulement les différences » pour voir tous les paramètres.</p>` : ""}`;
  }

  function notesHtml(result) {
    const items = result.rows.filter((row) => row.notes && row.notes.length);
    if (!items.length) return "";
    return `
      <div class="cmp-notes">
        <div class="section-title">Retouches, sans effet sur la structure</div>
        <ul>${items.map((row) => `<li><strong>${escapeHtml(row.label)}${row.version ? ` ${escapeHtml(row.version)}` : ""}</strong> : ${row.notes.map(escapeHtml).join(" ; ")}</li>`).join("")}</ul>
      </div>`;
  }

  // la deuxième ligne d'en-tête colle sous la première : son décalage est la hauteur de celle-ci
  function stickHeader(el) {
    const first = el.querySelector(".cmp-head-groups");
    const table = el.querySelector(".cmp-table");
    if (first && table) table.style.setProperty("--cmp-head-1", `${first.getBoundingClientRect().height}px`);
  }

  function mount(el, result, options = {}) {
    let current = result;
    let onlyDiff = readOnlyDiff();

    function render() {
      const summary = summaryText(current.summary || {});
      const comparable = current.rows.filter((row) => row.cells).length;
      let lead;
      if (!current.rows.length) lead = options.emptyText || "Rien à comparer pour l'instant.";
      else if (comparable < 2) lead = "Ajoutez au moins une autre plaque ou structure à comparer à la base.";
      else lead = summary ? `Face à la base : ${summary}.` : "Aucune différence avec la base.";
      el.innerHTML = `
        <div class="cmp">
          <div class="cmp-bar">
            ${legendHtml()}
            <label class="cmp-only"><input type="checkbox" class="js-only-diff" ${onlyDiff ? "checked" : ""}> Seulement les différences</label>
          </div>
          <p class="cmp-summary" aria-live="polite">${escapeHtml(lead)}</p>
          ${current.rows.length ? tableHtml(current, options, onlyDiff) : ""}
          ${notesHtml(current)}
        </div>`;
      stickHeader(el);
    }

    el.addEventListener("change", (event) => {
      if (!event.target.classList.contains("js-only-diff")) return;
      onlyDiff = event.target.checked;
      saveOnlyDiff(onlyDiff);
      render();
      el.querySelector(".js-only-diff")?.focus();
    });
    el.addEventListener("click", (event) => {
      const button = event.target.closest(".cmp-tool");
      if (!button || button.disabled) return;
      const index = Number(button.dataset.index);
      const action = button.dataset.action;
      if (action === "baseline" && options.onBaseline) options.onBaseline(index);
      else if (action === "remove" && options.onRemove) options.onRemove(index);
      else if (action === "up" && options.onMove) options.onMove(index, -1);
      else if (action === "down" && options.onMove) options.onMove(index, 1);
    });

    render();
    return {
      update(next) {
        current = next;
        render();
      },
    };
  }

  return { mount, legendHtml, summaryText, studyItem, waferItem, referenceItem, pageUrl };
})();
