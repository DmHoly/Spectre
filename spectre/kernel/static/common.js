/* Utilitaires partagés par les pages connectées : identité de l'utilisateur dans la barre du
   haut, déconnexion, badges de statut, formatage de dates - rien de spécifique à un écran. */

const STATUS_LABELS = {
  draft: { label: "Brouillon", cls: "badge-draft" },
  running: { label: "En cours", cls: "badge-running" },
  hold: { label: "En pause", cls: "badge-hold" }, // statut propre à Spectre (metadata « hold »)
  continued: { label: "Continuée", cls: "badge-continued" }, // brouillon repris par une version suivante
  concluded: { label: "Conclue", cls: "badge-concluded" },
  abandoned: { label: "Abandonnée", cls: "badge-abandoned" },
};

// Conclusion.status alone ("concluded") doesn't say what kind of conclusion it was -
// Conclusion.decision (posé par /conclure : promote/branch/replicate/abandon/inconclusive)
// already carries that nuance, just not shown anywhere before. Reusing the existing .badge-*
// classes (each already fixes the right colour/teinte pair) rather than inventing new ones -
// only the label changes. "concluded" with no decision (older data, or never set) keeps the
// generic "Conclue" from STATUS_LABELS above.
// « À poursuivre » a sa propre couleur (violet) : en bleu, on la confondait avec « En cours » ; une
// conclusion « Abandonner la piste » est une piste abandonnée, pas une « Conclue » verte.
const CONCLUDED_DECISION_LABELS = {
  promote: { label: "Concluante", cls: "badge-concluded" },
  inconclusive: { label: "Non concluante", cls: "badge-abandoned" },
  branch: { label: "À poursuivre", cls: "badge-continue" },
  replicate: { label: "À poursuivre", cls: "badge-continue" },
  abandon: { label: "Abandonnée", cls: "badge-abandoned" },
};

// L'issue d'une expérience en une clé (draft, continued, running, hold, promote, concluded, continue,
// inconclusive, abandoned) : la même partout - badge (statusBadgeHtml), nœud du graphe et frise (lineage-graph.js).
const OUTCOME_BY_DECISION = { promote: "promote", inconclusive: "inconclusive", branch: "continue", replicate: "continue", abandon: "abandoned" };

function experimentOutcome(status, decision) {
  if (status === "concluded") return OUTCOME_BY_DECISION[decision] || "concluded";
  return STATUS_LABELS[status] ? status : "draft";
}

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

// Durée compacte en français : « 40 min », « 5 h », « 3 j », « 2 sem. », « 4 mois », « 1 an 2 mois ».
function formatDuration(ms) {
  const minutes = Math.max(0, Math.round(ms / 60000));
  if (minutes < 60) return minutes < 1 ? "< 1 min" : `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days} j`;
  if (days < 60) return `${Math.round(days / 7)} sem.`;
  const months = Math.round(days / 30.44);
  if (months < 12) return `${months} mois`;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  return `${years} an${years > 1 ? "s" : ""}${rest ? ` ${rest} mois` : ""}`;
}

// Temps écoulé d'une expérience : du début à la fin, ou jusqu'à maintenant tant qu'elle n'est pas
// terminée (`ended` vide) - « 12 j » ou « depuis 12 j ».
function elapsedLabel(started, ended) {
  if (!started) return "";
  const end = ended ? new Date(ended) : new Date();
  const span = formatDuration(end - new Date(started));
  return ended ? span : `depuis ${span}`;
}

// « Propriétaire » d'un µprojet : le premier (son créateur s'il l'est toujours), « +N » s'il y en a d'autres.
function ownerChipHtml(owners, { label = true } = {}) {
  if (!owners || !owners.length) return "";
  const [first, ...others] = owners;
  const all = owners.map((o) => o.name).join(", ");
  return `<span class="owner-chip" title="Propriétaire${owners.length > 1 ? "s" : ""} : ${escapeHtml(all)}">
      <span class="avatar avatar--xs" aria-hidden="true">${escapeHtml(initials(first.name))}</span>
      ${label ? `<span class="owner-chip__label">Propriétaire</span>` : ""}
      <span class="owner-chip__name">${escapeHtml(first.name)}</span>${others.length ? `<span class="owner-chip__more">+${others.length}</span>` : ""}
    </span>`;
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
// carrousel de structure de atlas.js et lineage-view.js). Retombe sur `labels[i]` seul si
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

/* FDL - feuille de lancement (ticket JIRA) : le numéro de suivi avec lequel un wafer passe en
   ligne, celui qu'on cite pour le retrouver. Un wafer peut en avoir plusieurs (une par passage) :
   elles s'empilent, dans l'ordre. Même écriture partout que côté serveur (spectre.core.fdl) :
   « fdl 1234 », « 1234 » -> FDL-1234 ; une autre clé JIRA « abc 12 » -> ABC-12. */
function normalizeFdl(text) {
  const value = String(text || "").replace(/\s+/g, " ").trim().replace(/^["']+|["']+$/g, "").trim();
  if (!value) return null;
  let match = value.match(/^(?:fdl)?[\s_\-#:]*(\d{1,8})$/i);
  if (match) return `FDL-${parseInt(match[1], 10)}`;
  match = value.match(/^([A-Za-z][A-Za-z0-9]{1,9})[\s_\-#:]*(\d{1,8})$/);
  if (match) return `${match[1].toUpperCase()}-${parseInt(match[2], 10)}`;
  return value.slice(0, 40);
}

// Pastilles en lecture seule (en-tête de fiche, graphe, atlas) - vide s'il n'y en a aucune.
function fdlChipsHtml(fdls, { label = true } = {}) {
  if (!fdls || !fdls.length) return "";
  return `<span class="fdl-chips">${label ? `<span class="fdl-chips__label">FDL</span>` : ""}${fdls
    .map((f) => `<span class="fdl-chip" title="Feuille de lancement ${escapeHtml(f)}">${escapeHtml(f)}</span>`)
    .join("")}</span>`;
}

// Toutes les FDL des entités d'une expérience, chacune une fois.
function fdlsOfTracking(tracking) {
  const seen = [];
  (tracking || []).forEach((entry) => (entry.fdl || []).forEach((f) => seen.includes(f) || seen.push(f)));
  return seen;
}

/* Champ de saisie des FDL d'un wafer : taper le numéro puis Entrée (ou virgule, point-virgule, Tab)
   l'empile en pastille ; coller « FDL-1, FDL-2 » en ajoute plusieurs ; × ou Retour arrière (champ
   vide) retire la dernière. `datalistId` : l'autocomplétion des FDL déjà utilisées dans le µprojet.
   Renvoie {get, set}. */
function mountFdlField(container, { values = [], onChange = () => {}, datalistId = null, compact = false, label = "FDL" } = {}) {
  let fdls = [];
  container.classList.add("fdl-field");
  if (compact) container.classList.add("fdl-field--compact");
  container.innerHTML = `<span class="fdl-field__chips"></span><input class="fdl-field__input" type="text" autocomplete="off" spellcheck="false" placeholder="${fdls.length ? "" : "FDL-…"}" aria-label="${escapeHtml(label)} (Entrée pour ajouter)"${datalistId ? ` list="${datalistId}"` : ""}>`;
  const chips = container.querySelector(".fdl-field__chips");
  const input = container.querySelector("input");

  function paint() {
    chips.innerHTML = fdls
      .map((f, i) => `<span class="fdl-chip">${escapeHtml(f)}<button type="button" class="fdl-chip__x" data-index="${i}" aria-label="Retirer ${escapeHtml(f)}">×</button></span>`)
      .join("");
    input.placeholder = fdls.length ? "+ FDL" : "FDL-…";
  }
  function add(text) {
    let added = false;
    String(text || "")
      .split(/[,;\n]+|\s{2,}/)
      .map(normalizeFdl)
      .filter(Boolean)
      .forEach((f) => {
        if (!fdls.includes(f)) {
          fdls.push(f);
          added = true;
        }
      });
    if (added) {
      paint();
      onChange(fdls.slice());
    }
  }
  function commit() {
    if (!input.value.trim()) return false;
    add(input.value);
    input.value = "";
    return true;
  }

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === "," || event.key === ";" || (event.key === "Tab" && input.value.trim())) {
      if (commit() || event.key === "Enter") event.preventDefault();
    } else if (event.key === "Backspace" && !input.value && fdls.length) {
      fdls.pop();
      paint();
      onChange(fdls.slice());
    }
  });
  // un numéro choisi dans l'autocomplétion s'empile tout de suite
  input.addEventListener("input", (event) => {
    if (event.inputType === "insertReplacementText" || (datalistId && event.inputType === undefined)) commit();
  });
  input.addEventListener("paste", (event) => {
    const text = event.clipboardData && event.clipboardData.getData("text");
    if (text && /[,;\n]/.test(text)) {
      event.preventDefault();
      add(text);
    }
  });
  input.addEventListener("blur", commit);
  chips.addEventListener("click", (event) => {
    const btn = event.target.closest(".fdl-chip__x");
    if (!btn) return;
    fdls.splice(Number(btn.dataset.index), 1);
    paint();
    onChange(fdls.slice());
    input.focus();
  });
  container.addEventListener("click", (event) => {
    if (event.target === container || event.target === chips) input.focus();
  });

  fdls = (values || []).map(normalizeFdl).filter(Boolean);
  paint();
  return {
    get() {
      commit(); // ce qui est encore tapé compte aussi
      return fdls.slice();
    },
    set(next) {
      fdls = (next || []).map(normalizeFdl).filter(Boolean);
      paint();
    },
  };
}

// La page d'une plaque (son parcours d'une étude à l'autre, voir wafer.html).
function plateUrl(lasermark) {
  return `/plaques/${encodeURIComponent(lasermark)}`;
}

/* « Données en base » : les requêtes PRISM (page Data) qui prennent des lasermarks, ouvertes sur
   les plaques données - un clic, et la requête part avec ces wafers (data-types.js, ?wafers=). Rien
   n'est affiché si PRISM n'a aucune requête de ce genre (ou s'il n'y a aucun lasermark). Utilisé par
   la fiche d'expérience et la page d'une plaque. */
let waferHooksPromise = null;
function waferHooks() {
  if (!waferHooksPromise) {
    waferHooksPromise = api
      .get("/api/donnees/hooks")
      .then((data) => (data.hooks || []).filter((h) => h.status === "implemented" && (h.parameters || []).includes("wafer_names")))
      .catch(() => []);
  }
  return waferHooksPromise;
}

async function renderWaferDbLinks(hosts, lasermarkList) {
  const lasermarks = [...new Set((lasermarkList || []).filter(Boolean))];
  const hooks = lasermarks.length ? await waferHooks() : [];
  if (!hooks.length) {
    hosts.forEach((h) => (h.innerHTML = ""));
    return;
  }
  const wafers = encodeURIComponent(lasermarks.join(","));
  const items = hooks
    .map((h) => `<li><a href="/donnees/${encodeURIComponent(h.key)}?wafers=${wafers}" target="_blank" rel="noopener">${escapeHtml(h.title)}<span>${escapeHtml(h.category || "")}</span></a></li>`)
    .join("");
  const icon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/></svg>`;
  hosts.forEach((host) => {
    host.innerHTML = `
      <details class="db-menu">
        <summary class="btn btn-line db-menu__btn" title="Les données de ${lasermarks.length > 1 ? "ces plaques" : "cette plaque"} en base (PRISM)">${icon}Données en base</summary>
        <div class="db-menu__pop">
          <div class="db-menu__title">Ouvrir dans Data, pour ${escapeHtml(lasermarks.length > 3 ? `${lasermarks.length} plaques` : lasermarks.join(", "))}</div>
          <ul>${items}</ul>
        </div>
      </details>`;
  });
}

document.addEventListener("click", (event) => {
  document.querySelectorAll(".db-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.removeAttribute("open");
  });
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll(".db-menu[open]").forEach((menu) => {
    menu.removeAttribute("open");
    menu.querySelector("summary").focus();
  });
});

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

  // un résultat : {type: "microproject", slug, code, name, management_area}, {type: "lot", code, title,
  // status, priority, wafer}, {type: "plate", sample_id, count, microprojects, latest} ou
  // {type: "fdl", fdl, sample_id, experience, microproject}
  const open = (hit) => {
    window.location.href =
      hit.type === "fdl"
        ? `/microprojets/${encodeURIComponent(hit.microproject.slug)}/experiences/${encodeURIComponent(hit.experience.id)}`
        : hit.type === "plate"
          ? plateUrl(hit.sample_id)
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
                 ${p.management_area ? `<span class="topbar-search__area">${escapeHtml(p.management_area.name)}</span>` : ""}`;
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
      const q = encodeURIComponent(query);
      const longEnough = query.replace(/[\s_\-./#:]/g, "").length >= 2;
      const [projects, plateHits, fdlHits, lotHits] = await Promise.all([
        api.get(`/api/microprojets/recherche?q=${q}`),
        longEnough ? api.get(`/api/plaques/recherche?q=${q}`).catch(() => []) : Promise.resolve([]),
        /\d/.test(query) ? api.get(`/api/microprojets/recherche-fdl?q=${q}`).catch(() => []) : Promise.resolve([]),
        longEnough ? api.get(`/api/lots/recherche?q=${q}`).catch(() => []) : Promise.resolve([]),
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
  ["/lots", /^\/lots/],
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
