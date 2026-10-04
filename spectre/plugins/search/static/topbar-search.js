/* Recherche de la barre du haut, sur toutes les pages connectées : µprojets, lots, plaques et FDL,
   en une requête par frappe (searchApi.search : GET /api/search, qui interroge les fournisseurs des
   plugins et donne l'adresse de chaque résultat). */

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

  // un résultat (GET /api/search) : {type, label, detail, badge, url} - l'adresse vient du serveur
  const open = (hit) => {
    window.location.href = hit.url;
  };
  const GROUP_LABELS = { microproject: "µprojets", lot: "Lots", wafer: "Plaques", fdl: "FDL" };
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
        .map((hit, i) => {
          const group = hit.type !== previousType ? `<li class="topbar-search__group" role="presentation">${escapeHtml(GROUP_LABELS[hit.type] || hit.type)}</li>` : "";
          previousType = hit.type;
          return `${group}
          <li class="topbar-search__item${i === active ? " is-active" : ""}" id="topbar-search-${i}" role="option" aria-selected="${i === active}" data-index="${i}">
            <span class="topbar-search__code topbar-search__code--${escapeHtml(hit.type)}">${escapeHtml(hit.label)}</span>
            ${hit.detail ? `<span class="topbar-search__name">${escapeHtml(hit.detail)}</span>` : ""}
            ${hit.badge ? `<span class="topbar-search__area">${escapeHtml(hit.badge)}</span>` : ""}
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
      const found = await searchApi.search(query);
      if (mine !== seq) return; // une frappe plus récente a déjà relancé la recherche
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
