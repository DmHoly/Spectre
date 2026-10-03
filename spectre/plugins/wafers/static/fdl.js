/* FDL d'un wafer (normalisation, pastilles, champ de saisie), lien vers la page d'une plaque, clé
   d'une plaque et autocomplétion des plaques d'un µprojet. */

/* FDL - feuille de lancement (ticket JIRA) : le numéro de suivi avec lequel un wafer passe en
   ligne, celui qu'on cite pour le retrouver. Un wafer peut en avoir plusieurs (une par passage) :
   elles s'empilent, dans l'ordre. Même écriture partout que côté serveur (spectre.plugins.experiments.entities.normalize_fdl) :
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

// La clé d'une plaque (`key` des réponses de l'API) : son lasermark sans casse ni séparateurs,
// comme côté serveur (spectre.plugins.wafers.service.wafer_key) - « w12-a3 » = « W12 A3 ».
function waferKey(lasermark) {
  return String(lasermark || "").replace(/[\s_\-./#:]/g, "").toUpperCase();
}

// L'autocomplétion des plaques d'un µprojet (wafersApi.list({microproject})) : les lasermarks,
// emplacements et FDL déjà notés, chacun une fois.
function waferSuggestions(wafers) {
  const unique = (values) => [...new Set(values.filter(Boolean))].sort();
  return {
    sample_ids: unique(wafers.map((w) => w.lasermark)),
    locations: unique(wafers.flatMap((w) => w.locations || [])),
    fdls: unique(wafers.flatMap((w) => w.fdl || [])),
  };
}
