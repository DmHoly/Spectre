/* Utilitaires partagés par les pages connectées : identité de l'utilisateur dans la barre du
   haut, déconnexion, badges de statut, formatage de dates - rien de spécifique à un écran. */

const STATUS_LABELS = {
  draft: { label: "Brouillon", cls: "badge-draft" },
  running: { label: "En cours", cls: "badge-running" },
  concluded: { label: "Conclue", cls: "badge-concluded" },
  abandoned: { label: "Abandonnée", cls: "badge-abandoned" },
};

// Conclusion.status alone ("concluded") doesn't say what kind of conclusion it was -
// Conclusion.decision (posé par /conclure : promote/branch/replicate/abandon/inconclusive)
// already carries that nuance, just not shown anywhere before. Reusing the existing .badge-*
// classes (each already fixes the right colour/teinte pair) rather than inventing new ones -
// only the label changes. "concluded" with no decision (older data, or never set) keeps the
// generic "Conclue" from STATUS_LABELS above.
const CONCLUDED_DECISION_LABELS = {
  promote: { label: "Concluante", cls: "badge-concluded" },
  inconclusive: { label: "Non concluante", cls: "badge-abandoned" },
  branch: { label: "À poursuivre", cls: "badge-running" },
  replicate: { label: "À poursuivre", cls: "badge-running" },
};

const ROLE_LABELS = {
  owner: "Propriétaire",
  editor: "Peut modifier",
  viewer: "Lecture seule",
};

// `decision` is optional (Conclusion.decision, only meaningful when status === "concluded") -
// every call site should pass it when it has it (an experiment's ``conclusion.decision`` or a
// node payload's ``decision``) so "Concluante"/"Non concluante"/"À poursuivre" show up instead of
// the generic "Conclue" wherever a status badge appears.
function statusBadgeHtml(status, decision) {
  const info = (status === "concluded" && CONCLUDED_DECISION_LABELS[decision]) || STATUS_LABELS[status] || STATUS_LABELS.draft;
  return `<span class="badge ${info.cls}"><span class="dot"></span>${info.label}</span>`;
}

function roleLabel(role) {
  return ROLE_LABELS[role] || role;
}

function initials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : parts[0].slice(0, 2);
  return letters.toUpperCase();
}

function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return date.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  const steps = [
    [60, "seconde"],
    [60, "minute"],
    [24, "heure"],
    [30, "jour"],
    [12, "mois"],
    [Infinity, "an"],
  ];
  let value = seconds;
  let unit = "seconde";
  for (const [size, name] of steps) {
    if (value < size) {
      unit = name;
      break;
    }
    value = Math.floor(value / size);
    unit = name;
  }
  if (unit === "seconde" && value < 10) return "à l'instant";
  const plural = value > 1 && !unit.endsWith("s") ? "s" : "";
  return `il y a ${value} ${unit}${plural}`;
}

function escapeHtml(value) {
  // textContent->innerHTML escapes & < > but NOT quotes - every call site in this codebase also
  // interpolates the result inside a double-quoted HTML attribute (value="...", data-x="...",
  // href="..."), where an unescaped `"` breaks out and lets attacker-controlled text (a structure
  // name, a preset name, an evidence source URL - anything a microproject editor can set) inject a
  // live attribute (onmouseover=...) that fires for any other member who views the page. Escaping
  // both quote characters here closes that regardless of which attribute a caller uses it in.
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// Une valeur de paramètre telle qu'on l'écrit : 20 (pas 20.000001), et en notation scientifique
// pour les très grandes/petites grandeurs - 1e17, 3.16e17 (un dopage), jamais 100000000000000000.
// Même règle que spectre.core.structures.format_number côté serveur. Affichage seulement (3
// chiffres significatifs) : pour pré-remplir un champ, voir formatNumberInput (form-widgets.js).
function formatParamValue(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return value == null ? "" : String(value);
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1e5 || abs < 1e-3) {
    const [mantissa, exponent] = value.toExponential(2).split("e");
    return `${mantissa.replace(/\.?0+$/, "")}e${parseInt(exponent, 10)}`;
  }
  return Number.isInteger(value) ? String(value) : String(parseFloat(value.toPrecision(6)));
}

// Ce qui change entre deux variantes d'une campagne, pour l'entité `i` d'un `/matrice`
// (spectre.api.experiments::experience_batch) : "Épaisseur — Dépôt : 10" plutôt que le simple "10"
// de `variation.labels[i]`, qui ne dit jamais *quel* paramètre a cette valeur (utilisé par le
// carrousel de structure de atlas.js et microprojet-graphe.js). Retombe sur `labels[i]` seul si
// `factor_labels`/`factor_values` sont absents (campagnes lancées avant leur ajout).
function variantCaption(variation, i) {
  const factorLabels = variation.factor_labels || [];
  const factorValues = (variation.factor_values || [])[i];
  if (factorLabels.length && factorValues) {
    return factorLabels.map((label, j) => `${label} : ${formatParamValue(factorValues[j])}`).join(" · ");
  }
  const labels = variation.labels || [];
  return labels[i] != null ? String(labels[i]) : `#${i + 1}`;
}

// Carrousel des structures d'une campagne (réponse de /matrice : `svgs`, `labels`, facteurs) : la
// référence (1re variante, marquée « RÉF » comme partout ailleurs - voir
// structures.render_structure_svg) puis chaque variante, avec la valeur de ses paramètres variés.
// Flèches, points, et ← → au clavier une fois le carrousel focalisé. `onChange(index)` suit le
// défilement. Partagé par la fiche d'expérience, l'atlas et la vue d'ensemble d'un µprojet.
function mountStructureCarousel(container, variation, { onChange } = {}) {
  const svgs = (variation && variation.svgs) || [];
  if (!container || svgs.length === 0) {
    if (container) container.innerHTML = "";
    return null;
  }
  let index = 0;
  function paint() {
    const single = svgs.length < 2;
    container.innerHTML = `
      <div class="atlas-carousel" tabindex="0" role="group" aria-roledescription="carrousel" aria-label="Structures des ${svgs.length} variantes">
        <div class="atlas-carousel__badge">${index === 0 ? `<span class="badge badge-role">RÉF</span>` : ""}<span>${escapeHtml(variantCaption(variation, index))}</span></div>
        <div class="atlas-carousel__stage">${svgs[index]}</div>
        <div class="atlas-carousel__nav">
          <button type="button" class="btn btn-line" data-dir="-1" aria-label="Variante précédente" ${single ? "disabled" : ""}>&larr;</button>
          <span class="atlas-carousel__dots" aria-hidden="true">${
            svgs.length <= 24 ? svgs.map((_, i) => `<span class="atlas-carousel__dot${i === index ? " is-active" : ""}" data-go="${i}"></span>`).join("") : ""
          }</span>
          <span class="help">${index + 1} / ${svgs.length}</span>
          <button type="button" class="btn btn-line" data-dir="1" aria-label="Variante suivante" ${single ? "disabled" : ""}>&rarr;</button>
        </div>
      </div>`;
  }
  function go(next, focus) {
    index = (next + svgs.length) % svgs.length;
    paint();
    if (focus) container.querySelector(".atlas-carousel").focus();
    if (onChange) onChange(index);
  }
  container.onclick = (event) => {
    const dir = event.target.closest("[data-dir]");
    if (dir) return go(index + parseInt(dir.dataset.dir, 10), false);
    const dot = event.target.closest("[data-go]");
    if (dot) go(parseInt(dot.dataset.go, 10), false);
  };
  container.onkeydown = (event) => {
    if (!event.target.closest(".atlas-carousel")) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      go(index + (event.key === "ArrowLeft" ? -1 : 1), true);
    }
  };
  paint();
  return {
    get index() {
      return index;
    },
    go: (i) => go(i, false),
  };
}

/* Structure en images (spectre.core.structures.StructureImage) : un schéma collé depuis PowerPoint,
   des coupes TEM... à la place d'une structure dessinée - une ou plusieurs images, dans l'ordre où
   les lire. Affichées ainsi sur la fiche (la planche entière), le graphe d'un µprojet, l'atlas et
   la galerie de données (la première, avec le nombre d'images). L'éditeur pour les coller, les
   ordonner ou les remplacer est dans image-drop.js. */
const STRUCTURE_IMAGE_KIND_LABELS = { schema: "Schéma", coupe: "Coupe TEM / MEB", autre: "Image" };

function structureImageUrl(slug, imageId) {
  return `/api/microprojets/${encodeURIComponent(slug)}/pieces-jointes/${encodeURIComponent(imageId)}`;
}

function structurePictureHtml(slug, image, { index = null } = {}) {
  const url = structureImageUrl(slug, image.image_id);
  const kind = STRUCTURE_IMAGE_KIND_LABELS[image.kind] || "Image";
  const alt = image.caption ? `${kind} : ${image.caption}` : `${kind} de la structure`;
  return `
    <figure class="structure-picture">
      <a class="structure-picture__frame" href="${url}" target="_blank" rel="noopener" title="Ouvrir l'image en grand">
        <img src="${url}" alt="${escapeHtml(alt)}" loading="lazy">
      </a>
      <figcaption class="structure-picture__caption">${index != null ? `<span class="structure-picture__num">${index}</span>` : ""}<span class="structure-picture__kind">${escapeHtml(kind)}</span>${image.caption ? `<span>${escapeHtml(image.caption)}</span>` : ""}</figcaption>
    </figure>`;
}

// La planche : toutes les images (numérotées dès qu'il y en a plusieurs) ; `compact` - un aperçu
// (graphe, atlas, galerie) : la première seulement, avec « +N » s'il y en a d'autres.
function structureBoardHtml(slug, images, { compact = false } = {}) {
  if (!images || !images.length) return "";
  if (compact) {
    const first = images[0];
    const url = structureImageUrl(slug, first.image_id);
    const kind = STRUCTURE_IMAGE_KIND_LABELS[first.kind] || "Image";
    const more = images.length - 1;
    return `
      <a class="structure-thumb" href="${url}" target="_blank" rel="noopener" title="Ouvrir l'image en grand">
        <img src="${url}" alt="${escapeHtml(first.caption ? `${kind} : ${first.caption}` : `${kind} de la structure`)}" loading="lazy">
        ${more ? `<span class="structure-thumb__more">+${more} image${more > 1 ? "s" : ""}</span>` : ""}
      </a>`;
  }
  const numbered = images.length > 1;
  return `<div class="structure-board" data-count="${Math.min(images.length, 3)}">${images
    .map((image, i) => structurePictureHtml(slug, image, { index: numbered ? i + 1 : null }))
    .join("")}</div>`;
}

// Recherche de µprojet dans la topbar, sur toutes les pages connectées : son numéro tel qu'on le
// dit (« Nat 4 », « Nat_0004 », « nat4 ») ou un bout de son nom, avec des suggestions au fil de la
// frappe (↑ ↓ pour choisir, Entrée pour ouvrir, Échap pour fermer). « / » ou Ctrl+K y place le
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
    <input class="topbar-search__input" type="search" autocomplete="off" spellcheck="false" placeholder="µprojet : Nat 4, nom…"
      aria-label="Aller au µprojet (numéro ou nom)" role="combobox" aria-expanded="false" aria-controls="topbar-search-list" aria-autocomplete="list">
    <kbd class="topbar-search__key" aria-hidden="true" title="Raccourci : / ou Ctrl+K">/</kbd>
    <ul class="topbar-search__list" id="topbar-search-list" role="listbox" aria-label="µprojets trouvés" hidden></ul>`;
  topbar.insertBefore(form, actions);

  const input = form.querySelector("input");
  const list = form.querySelector("ul");
  let results = [];
  let active = -1;
  let timer = null;
  let seq = 0;

  const open = (slug) => {
    window.location.href = `/microprojets/${encodeURIComponent(slug)}`;
  };
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
      list.innerHTML = results
        .map(
          (p, i) => `
          <li class="topbar-search__item${i === active ? " is-active" : ""}" id="topbar-search-${i}" role="option" aria-selected="${i === active}" data-index="${i}">
            ${p.code ? `<span class="topbar-search__code">${escapeHtml(p.code)}</span>` : ""}
            <span class="topbar-search__name">${escapeHtml(p.name)}</span>
            ${p.management_area ? `<span class="topbar-search__area">${escapeHtml(p.management_area.name)}</span>` : ""}
          </li>`
        )
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
      const found = await api.get(`/api/microprojets/recherche?q=${encodeURIComponent(query)}`);
      if (mine !== seq) return; // une frappe plus récente a déjà relancé la recherche
      results = found;
      active = found.length ? 0 : -1;
      paint(found.length ? "" : `Aucun µprojet pour « ${query} »`);
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
    if (results.length && active >= 0) return open(results[active].slug);
    await fetchResults(); // Entrée avant que les suggestions n'arrivent : on cherche tout de suite
    if (results.length) open(results[0].slug);
  });
  list.addEventListener("mousedown", (event) => {
    event.preventDefault(); // garde le focus dans le champ le temps du clic
    const item = event.target.closest("[data-index]");
    if (item) open(results[Number(item.dataset.index)].slug);
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

async function mountUserBadge() {
  const nameEls = document.querySelectorAll(".js-user-name");
  const initialsEls = document.querySelectorAll(".js-user-initials");
  try {
    const user = await api.get("/api/auth/me");
    nameEls.forEach((el) => (el.textContent = user.name));
    initialsEls.forEach((el) => (el.textContent = initials(user.name)));
    return user;
  } catch (err) {
    return null;
  }
}

function initLogout() {
  document.querySelectorAll(".js-logout").forEach((el) => {
    el.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        await api.post("/api/auth/logout", {}, { redirectOn401: false });
      } finally {
        window.location.href = "/connexion";
      }
    });
  });
}

// Marque la section courante dans la navigation principale de la topbar (aria-current="page",
// souligné or en CSS). Tout ce qui vit sous un projet corporate (projet, µprojet, expérience...)
// relève de « Projets » - sauf l'atlas d'un projet, qui a son propre lien sur la page du projet.
const NAV_SECTIONS = [
  ["/bibliotheque", /^\/bibliotheque/],
  ["/donnees", /^\/donnees/],
  ["/docs", /^\/docs/],
  ["/", /^\/(management|microprojets|$)/],
];

function initNavActive() {
  const path = window.location.pathname;
  const atlas = document.getElementById("atlas-link");
  if (atlas && /\/atlas$/.test(path)) {
    atlas.setAttribute("aria-current", "page");
    return;
  }
  const match = NAV_SECTIONS.find(([, re]) => re.test(path));
  if (!match) return;
  document.querySelectorAll(".topbar__nav .topbar__link").forEach((link) => {
    if (link.getAttribute("href") === match[0]) link.setAttribute("aria-current", "page");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  mountUserBadge();
  initLogout();
  initNavActive();
  initTopbarSearch();
});

/* Docs pages only: highlights the nav link matching whichever <section id="..."> is currently in
   view, using IntersectionObserver rather than a scroll listener (cheaper, no manual throttling). */
function initDocsNav() {
  const nav = document.querySelector(".docs-nav");
  const sections = document.querySelectorAll(".docs-content section[id]");
  if (!nav || sections.length === 0) return;
  const links = new Map([...nav.querySelectorAll("a")].map((a) => [a.getAttribute("href").slice(1), a]));
  const setActive = (id) => {
    links.forEach((a) => a.classList.remove("active"));
    const link = links.get(id);
    if (link) link.classList.add("active");
  };
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries.filter((e) => e.isIntersecting);
      if (visible.length > 0) setActive(visible[0].target.id);
    },
    { rootMargin: "-10% 0px -70% 0px" }
  );
  sections.forEach((section) => observer.observe(section));
  if (sections[0]) setActive(sections[0].id);
}
