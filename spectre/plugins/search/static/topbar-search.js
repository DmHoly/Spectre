/* Recherche de la barre du haut, sur toutes les pages connectées : µprojets, lots, plaques et FDL,
   via microprojectsApi, wafersApi et lotsApi (les client.js de ces plugins). */

// Recherche de µprojet dans la topbar, sur toutes les pages connectées : son numéro tel qu'on le
// dit (« Nat 4 », « Nat_0004 », « nat4 ») ou un bout de son nom ; une plaque par son lasermark
// (« W12-A3 », séparateurs et casse ignorés : sa page, toutes les études qui la suivent) ; et, dès
// qu'on tape un chiffre, une FDL (« 1234 », « FDL-1234 ») : les expériences dont un wafer la porte. Suggestions au fil de
// la frappe (↑ ↓ pour choisir, Entrée pour ouvrir, Échap pour fermer). « / » ou Ctrl+K y place le
// curseur depuis n'importe où. Injectée ici plutôt que recopiée dans chaque page HTML.
function initTopbarSearch() {
  const topbar = document.querySelector(".topbar");
  const actions = topbar && topbar.querySelector(".topbar__actions");
  if (!actions || topbar.querySelector(".topbar-search")) return;
  const form = document.createElement("form");
  form.className = "topbar-search";
  form.setAttribute("role", "search");
  form.innerHTML = `
    <svg class="topbar-search__icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <input class="topbar-search__input" type="search" autocomplete="off" spellcheck="false" placeholder="µprojet, lot, plaque, FDL…"
      aria-label="Aller à un µprojet (numéro ou nom), un lot (code ou wafer), une plaque (lasermark) ou une FDL" role="combobox" aria-expanded="false" aria-controls="topbar-search-list" aria-autocomplete="list">
    <kbd class="topbar-search__key" aria-hidden="true" title="Raccourci : / ou Ctrl+K">/</kbd>
    <ul class="topbar-search__list" id="topbar-search-list" role="listbox" aria-label="Résultats de recherche" hidden></ul>`;
  topbar.insertBefore(form, actions);

  const input = form.querySelector("input");
  const list = form.querySelector("ul");
  let results = [];
  let active = -1;
  let timer = null;
  let seq = 0;

  // un résultat : {type: "microproject", slug, code, name, area}, {type: "lot", code, title,
  // status, priority, wafer}, {type: "plate", sample_id, count, microprojects, latest} ou
  // {type: "fdl", fdl, sample_id, experience, microproject}
  const open = (hit) => {
    window.location.href =
      hit.type === "fdl"
        ? `/microprojets/${encodeURIComponent(hit.microproject.slug)}/experiences/${encodeURIComponent(hit.experience.id)}`
        : hit.type === "plate"
          ? `/plaques/${encodeURIComponent(hit.sample_id)}`
          : hit.type === "lot"
            ? `/lots/${encodeURIComponent(hit.code)}`
            : `/microprojets/${encodeURIComponent(hit.slug)}`;
  };
  const GROUP_LABELS = { microproject: "µprojets", lot: "Lots", plate: "Plaques", fdl: "FDL" };
  const LOT_WHERE = { planned: "en préparation", wip: "en cours", hold: "en pause", done: "sorti", cancelled: "annulé" };
  const close = () => {
    list.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  };
  const paint = (message) => {
    if (!results.length) {
      list.innerHTML = message ? `<li class="topbar-search__empty">${escapeHtml(message)}</li>` : "";
    } else {
      let previousType = null;
      list.innerHTML = results
        .map((p, i) => {
          const group = p.type !== previousType ? `<li class="topbar-search__group" role="presentation">${GROUP_LABELS[p.type]}</li>` : "";
          previousType = p.type;
          const body =
            p.type === "fdl"
              ? `<span class="topbar-search__code topbar-search__code--fdl">${escapeHtml(p.fdl)}</span>
                 <span class="topbar-search__name">${escapeHtml(p.experience.title)}${p.sample_id ? ` · ${escapeHtml(p.sample_id)}` : ""}</span>
                 <span class="topbar-search__area">${escapeHtml(p.microproject.code || p.microproject.name)}</span>`
              : p.type === "lot"
                ? `<span class="topbar-search__code topbar-search__code--lot">${escapeHtml(p.code)}</span>
                   <span class="topbar-search__name">${escapeHtml(p.wafer ? `contient ${p.wafer}` : p.title || "Lot")}</span>
                   <span class="topbar-search__area">${escapeHtml([p.priority, LOT_WHERE[p.status]].filter(Boolean).join(" · "))}</span>`
              : p.type === "plate"
                ? `<span class="topbar-search__code topbar-search__code--plate">${escapeHtml(p.sample_id)}</span>
                   <span class="topbar-search__name">${p.count > 1 ? `${p.count} études` : escapeHtml(p.latest.title)}</span>
                   <span class="topbar-search__area">${escapeHtml(p.microprojects.slice(0, 2).join(", "))}${p.microprojects.length > 2 ? "…" : ""}</span>`
                : `${p.code ? `<span class="topbar-search__code">${escapeHtml(p.code)}</span>` : ""}
                 <span class="topbar-search__name">${escapeHtml(p.name)}</span>
                 ${p.area ? `<span class="topbar-search__area">${escapeHtml(p.area.name)}</span>` : ""}`;
          return `${group}
          <li class="topbar-search__item${i === active ? " is-active" : ""}" id="topbar-search-${i}" role="option" aria-selected="${i === active}" data-index="${i}">
            ${body}
          </li>`;
        })
        .join("");
    }
    const show = Boolean(results.length || message);
    list.hidden = !show;
    input.setAttribute("aria-expanded", String(show && results.length > 0));
    if (active >= 0) input.setAttribute("aria-activedescendant", `topbar-search-${active}`);
    else input.removeAttribute("aria-activedescendant");
  };
  const fetchResults = async () => {
    const query = input.value.trim();
    const mine = ++seq;
    if (!query) {
      results = [];
      close();
      return;
    }
    try {
      const longEnough = query.replace(/[\s_\-./#:]/g, "").length >= 2;
      const [projects, plateHits, fdlHits, lotHits] = await Promise.all([
        microprojectsApi.list({ q: query }),
        longEnough ? wafersApi.search(query).catch(() => []) : Promise.resolve([]),
        /\d/.test(query) ? microprojectsApi.searchFdl(query).catch(() => []) : Promise.resolve([]),
        longEnough ? lotsApi.search(query).catch(() => []) : Promise.resolve([]),
      ]);
      if (mine !== seq) return; // une frappe plus récente a déjà relancé la recherche
      const projectHits = projects.map((p) => ({ ...p, type: "microproject" }));
      const plateItems = plateHits.map((h) => ({ ...h, type: "plate" }));
      const fdlItems = fdlHits.map((h) => ({ ...h, type: "fdl" }));
      const lotItems = lotHits.map((h) => ({ ...h, type: "lot" }));
      // « 1234 », « FDL 12 » : on cherche d'abord une FDL ; sinon les µprojets, les lots, puis les plaques
      const fdlFirst = /^\s*(fdl)?[\s_\-#:]*\d+\s*$/i.test(query);
      const found = fdlFirst
        ? [...fdlItems, ...plateItems, ...lotItems, ...projectHits]
        : [...projectHits, ...lotItems, ...plateItems, ...fdlItems];
      results = found;
      active = found.length ? 0 : -1;
      paint(found.length ? "" : `Rien pour « ${query} » (µprojet, lot, plaque ou FDL)`);
    } catch (err) {
      if (mine === seq) {
        results = [];
        paint("Recherche indisponible");
      }
    }
  };

  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(fetchResults, 140);
  });
  input.addEventListener("focus", () => {
    if (input.value.trim() && results.length) paint();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!results.length) return;
      event.preventDefault();
      active = (active + (event.key === "ArrowDown" ? 1 : -1) + results.length) % results.length;
      paint();
      const item = document.getElementById(`topbar-search-${active}`);
      if (item) item.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Escape") {
      event.preventDefault();
      if (!list.hidden) close();
      else input.blur();
    }
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearTimeout(timer);
    if (results.length && active >= 0) return open(results[active]);
    await fetchResults(); // Entrée avant que les suggestions n'arrivent : on cherche tout de suite
    if (results.length) open(results[0]);
  });
  list.addEventListener("mousedown", (event) => {
    event.preventDefault(); // garde le focus dans le champ le temps du clic
    const item = event.target.closest("[data-index]");
    if (item) open(results[Number(item.dataset.index)]);
  });
  input.addEventListener("blur", () => setTimeout(close, 120));

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    const typing = target && (["input", "textarea", "select"].includes((target.tagName || "").toLowerCase()) || target.isContentEditable);
    const shortcut = (event.key === "/" && !typing && !event.ctrlKey && !event.metaKey && !event.altKey) || ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k");
    if (!shortcut || document.querySelector("dialog[open]")) return;
    event.preventDefault();
    input.focus();
    input.select();
  });
}

document.addEventListener("DOMContentLoaded", initTopbarSearch);
