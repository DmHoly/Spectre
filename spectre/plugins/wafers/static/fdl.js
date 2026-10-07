/* FDL d'un wafer (normalisation, pastilles, champ de saisie), FDL d'une étude et plaques qu'elles
   contiennent (menu déroulant d'association), lien vers la page d'une plaque, clé d'une plaque et
   autocomplétion des plaques d'un µprojet. */

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

// Toutes les FDL d'une expérience - les siennes (`studyFdl`, detail.fdl) puis celles de ses plaques -,
// chacune une fois.
function fdlsOfTracking(tracking, studyFdl = []) {
  const seen = [];
  (studyFdl || []).forEach((f) => seen.includes(f) || seen.push(f));
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

/* -- Les FDL d'une étude et les plaques qu'elles contiennent ------------------------------------
   Une étude porte ses FDL (detail.fdl) ; chacune est lue dans la base (wafersApi.fdl : la démo, la
   base locale saisie à la main, PRISM plus tard) et ses plaques alimentent le menu déroulant de
   chaque place de l'étude (une par variante d'une campagne, ses réplicats sinon) : on associe, à la
   main, chaque place à la vraie plaque. */

const FDL_SOURCE_LABELS = { demo: "démo", local: "saisie dans Spectre", prism: "PRISM" };

/* Le champ des FDL de l'étude et, sous lui, ce que la base dit de chacune : ses plaques, ou « inconnue »
   avec de quoi coller ses lasermarks quand la source l'accepte (base locale). `onChange(fdls,
   contents)` : à chaque FDL lue - contents : [{fdl, source, editable, known, wafers, error?}].
   Renvoie {get, contents}. */
function mountStudyFdl(container, { values = [], datalistId = null, onChange = () => {} } = {}) {
  let contents = [];
  let seq = 0;
  let editing = null; // la FDL dont on saisit les plaques
  container.classList.add("study-fdl");
  container.innerHTML = `<div class="study-fdl__field"></div><ul class="study-fdl__sheets" aria-live="polite"></ul>`;
  const list = container.querySelector(".study-fdl__sheets");
  const field = mountFdlField(container.querySelector(".study-fdl__field"), {
    values,
    datalistId,
    label: "FDL de l'étude",
    onChange: (fdls) => load(fdls),
  });

  function sheetHtml(sheet) {
    const name = `<span class="fdl-chip">${escapeHtml(sheet.fdl)}</span>`;
    if (sheet.loading) return `<li class="study-fdl__sheet">${name}<span class="study-fdl__state">lecture…</span></li>`;
    if (sheet.error) return `<li class="study-fdl__sheet is-error">${name}<span class="study-fdl__state">illisible : ${escapeHtml(sheet.error)}</span></li>`;
    if (editing === sheet.fdl) {
      return `
        <li class="study-fdl__sheet study-fdl__sheet--editing">
          ${name}
          <label class="study-fdl__state" for="study-fdl-paste">Les lasermarks de cette FDL, dans l'ordre du lot (un par ligne, ou séparés par des virgules)</label>
          <textarea class="field mono study-fdl__paste" id="study-fdl-paste" rows="4" spellcheck="false">${escapeHtml(sheet.wafers.map((w) => w.lasermark).join("\n"))}</textarea>
          <span class="study-fdl__actions">
            <button type="button" class="btn btn-primary js-fdl-save" data-fdl="${escapeHtml(sheet.fdl)}">Enregistrer</button>
            <button type="button" class="btn btn-line js-fdl-cancel">Annuler</button>
          </span>
        </li>`;
    }
    const source = FDL_SOURCE_LABELS[sheet.source] || sheet.source;
    const edit = sheet.editable
      ? `<button type="button" class="study-fdl__link js-fdl-edit" data-fdl="${escapeHtml(sheet.fdl)}">${sheet.known ? "modifier la liste" : "saisir ses plaques"}</button>`
      : "";
    if (!sheet.known) {
      return `<li class="study-fdl__sheet is-unknown">${name}<span class="study-fdl__state">${
        sheet.editable ? "plaques inconnues pour l'instant" : `inconnue de la base (${escapeHtml(source)})`
      }</span>${edit}</li>`;
    }
    const n = sheet.wafers.length;
    return `<li class="study-fdl__sheet">${name}<span class="study-fdl__state">${n} plaque${n > 1 ? "s" : ""} · ${escapeHtml(source)}</span>${edit}</li>`;
  }
  function paint(sheets) {
    list.innerHTML = sheets.map(sheetHtml).join("");
    const paste = list.querySelector(".study-fdl__paste");
    if (paste) paste.focus();
  }
  async function load(fdls) {
    const mine = ++seq;
    paint(fdls.map((fdl) => ({ fdl, loading: true })));
    const loaded = await Promise.all(fdls.map((fdl) => wafersApi.fdl(fdl).catch((err) => ({ fdl, error: err.message || String(err) }))));
    if (mine !== seq) return;
    contents = loaded;
    paint(contents);
    onChange(fdls.slice(), contents);
  }

  list.addEventListener("click", async (event) => {
    const editBtn = event.target.closest(".js-fdl-edit");
    if (editBtn) {
      editing = editBtn.dataset.fdl;
      paint(contents);
      return;
    }
    if (event.target.closest(".js-fdl-cancel")) {
      editing = null;
      paint(contents);
      return;
    }
    const saveBtn = event.target.closest(".js-fdl-save");
    if (!saveBtn) return;
    const lasermarks = list.querySelector(".study-fdl__paste").value.split(/[\n,;\t]+/).map((v) => v.trim()).filter(Boolean);
    saveBtn.disabled = true;
    try {
      const saved = await wafersApi.setFdlWafers(saveBtn.dataset.fdl, lasermarks);
      contents = contents.map((sheet) => (sheet.fdl === saved.fdl ? saved : sheet));
      editing = null;
      paint(contents);
      onChange(field.get(), contents);
    } catch (err) {
      saveBtn.disabled = false;
      const state = list.querySelector(".study-fdl__sheet--editing .study-fdl__state");
      state.textContent = err.message || String(err);
      state.classList.add("is-error");
    }
  });

  if (values && values.length) load(field.get());
  return {
    get: () => field.get(),
    contents: () => contents,
  };
}

// Les plaques que proposent les FDL lues : [{lasermark, fdl, slot}], chacune une fois.
function fdlWaferChoices(contents) {
  const seen = new Set();
  const choices = [];
  (contents || []).forEach((sheet) =>
    (sheet.wafers || []).forEach((w) => {
      const key = waferKey(w.lasermark);
      if (seen.has(key)) return;
      seen.add(key);
      choices.push({ lasermark: w.lasermark, fdl: sheet.fdl, slot: w.slot });
    })
  );
  return choices;
}

/* Le menu déroulant d'une place : « à associer », puis les plaques de chaque FDL (une déjà prise par
   une autre place est grisée). Une plaque déjà nommée hors de ces FDL reste proposée, telle quelle.
   `attrs` : les attributs de la balise (classe, data-index, id, aria-label). */
function fdlWaferSelectHtml({ value = "", choices = [], taken = [], attrs = "" } = {}) {
  const current = waferKey(value);
  const takenKeys = new Set(taken.map(waferKey).filter((key) => key && key !== current));
  const option = (c) => {
    const key = waferKey(c.lasermark);
    const slot = c.slot ? ` · fente ${c.slot}` : "";
    return `<option value="${escapeHtml(c.lasermark)}" data-fdl="${escapeHtml(c.fdl)}"${key === current ? " selected" : ""}${takenKeys.has(key) ? " disabled" : ""}>${escapeHtml(c.lasermark)}${slot}${takenKeys.has(key) ? " (déjà associée)" : ""}</option>`;
  };
  const byFdl = [];
  choices.forEach((c) => {
    let group = byFdl.find((g) => g.fdl === c.fdl);
    if (!group) byFdl.push((group = { fdl: c.fdl, choices: [] }));
    group.choices.push(c);
  });
  const outside = value && !choices.some((c) => waferKey(c.lasermark) === current)
    ? `<option value="${escapeHtml(value)}" selected>${escapeHtml(value)} (hors FDL)</option>`
    : "";
  return `<select ${attrs}>
    <option value=""${value ? "" : " selected"}>— à associer —</option>
    ${outside}
    ${byFdl.map((g) => `<optgroup label="${escapeHtml(g.fdl)}">${g.choices.map(option).join("")}</optgroup>`).join("")}
  </select>`;
}

// Les FDL d'une place après qu'on l'a associée à une plaque lue dans `fdl` : celle-ci s'y ajoute.
function withFdl(fdls, fdl) {
  const list = (fdls || []).slice();
  if (fdl && !list.includes(fdl)) list.push(fdl);
  return list;
}
