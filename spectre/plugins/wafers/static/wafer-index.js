/* L'index des plaques (wafer-index.html, /plaques) : toutes celles que Spectre connaît - suivies
   par une étude, ou enregistrées pour elles-mêmes (une fiche de plaque, sans étude) -, un champ de
   recherche, un tri. La recherche part au serveur (wafersApi.list) : par lasermark (q) et par FDL
   (fdl), les deux à la fois - un « 1234 » est une FDL, un « W12 » un lasermark, le serveur ne rend
   que celles qui correspondent à l'un ou à l'autre, le lasermark exact d'abord ; plusieurs lasermarks
   (virgules, points-virgules, retours à la ligne) se cherchent d'un coup. Une plaque d'un µprojet
   dont on n'est pas membre s'y montre sans FDL ni emplacement (règle de visibilité du plugin).

   Le monde d'avant Spectre : « Chercher dans la base » (wafersApi.lookup) retrouve des lasermarks
   collés dans Spectre puis dans la MES et Gozer, par PRISM ; ceux que la base connaît et que Spectre
   ignore se cochent, « Créer les fiches » (wafersApi.createRecords) les fait exister ici. Quand la
   recherche ne trouve pas un lasermark, la page propose d'aller le chercher dans la base. */

const PAGE_SIZE = 100;
const state = { wafers: [], sort: "lasermark", shown: PAGE_SIZE, query: "", token: 0 };

const rowsEl = document.getElementById("wafer-rows");
const tableEl = document.getElementById("wafer-table");
const countEl = document.getElementById("wafer-count");
const emptyEl = document.getElementById("wafer-empty");
const missingEl = document.getElementById("wafer-missing");
const moreEl = document.getElementById("wafer-more");
const errorEl = document.getElementById("error");

function showError(err) {
  errorEl.textContent = err.message || String(err);
  errorEl.style.display = "block";
}

function debounce(fn, ms = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// Les textes cherchés : un seul, ou plusieurs lasermarks séparés par des virgules, des
// points-virgules ou des retours à la ligne (un lasermark peut contenir une espace : « W12 A3 »).
function terms(query) {
  return query
    .split(/[,;\n]+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

function looksLikeAnFdl(text) {
  return /^\s*(fdl)?[\s_\-#:]*\d+\s*$/i.test(text);
}

// Les plaques dont le lasermark ou une FDL correspond : les deux recherches ensemble, une plaque une
// fois (le lasermark d'abord, puis la FDL). Sans texte, toutes les plaques. Plusieurs textes : tous
// les lasermarks d'un coup, et chaque texte qui ressemble à une FDL cherché comme FDL.
async function search(query) {
  const wanted = terms(query);
  if (!wanted.length) return wafersApi.list({});
  const fdlTerms = wanted.length === 1 ? wanted : wanted.filter(looksLikeAnFdl);
  const [byLasermark, ...byFdl] = await Promise.all([wafersApi.list({ q: wanted }), ...fdlTerms.map((t) => wafersApi.list({ fdl: t }))]);
  const seen = new Set(byLasermark.map((w) => w.key));
  const out = [...byLasermark];
  byFdl.flat().forEach((w) => {
    if (!seen.has(w.key)) {
      seen.add(w.key);
      out.push(w);
    }
  });
  return out;
}

function sorted(wafers) {
  const list = [...wafers];
  const when = (w) => (w.latest ? String(w.latest.experiment.updated_at) : w.record ? String(w.record.created_at) : "");
  if (state.sort === "recent") {
    list.sort((a, b) => when(b).localeCompare(when(a)));
  } else if (!state.query.trim()) {
    list.sort((a, b) => a.lasermark.localeCompare(b.lasermark, "fr", { numeric: true }));
  } // une recherche garde l'ordre du serveur : la plaque exacte, puis celles qui commencent par ce texte
  return list;
}

function microprojectsHtml(wafer) {
  return wafer.microprojects
    .map((m) => `<a class="fiche-code" href="/microprojets/${encodeURIComponent(m.slug)}" title="${escapeHtml(m.name)}">${escapeHtml(m.code || m.name)}</a>`)
    .join(" ");
}

// la dernière colonne : la dernière étude qui suit la plaque, ou sa fiche (sans étude)
function latestHtml(wafer) {
  if (wafer.latest) {
    const latest = wafer.latest.experiment;
    const title = latest.member ? `<span class="wafer-index__study" title="${escapeHtml(latest.title)}">${escapeHtml(latest.title)}</span>` : "";
    return `
      <div class="wafer-index__latest">${statusBadgeHtml(latest.status)}${title}</div>
      <div class="help wafer-index__date">${escapeHtml(formatDate(latest.updated_at))}</div>`;
  }
  const record = wafer.record;
  const summary = WaferRecords.summaryHtml(record.summary);
  return `
    <div class="wafer-index__latest">${WaferRecords.chipHtml(record)}<span class="wafer-index__study help">${summary || "aucune étude ne la suit encore"}</span></div>
    <div class="help wafer-index__date">fiche du ${escapeHtml(formatDate(record.created_at))} · ${escapeHtml(record.created_by)}</div>`;
}

// une plaque qui a changé de nom : « trouvée par XX » quand c'est son autre nom qui a répondu,
// sinon ses autres noms
function aliasHtml(wafer) {
  const runs = wafer.run_names || [];
  const run = runs.length ? `<span class="wafer-index__alias">run <strong class="mono">${escapeHtml(runs[0])}</strong>${runs.length > 1 ? `, aussi ${runs.slice(1).map((r) => `<span class="mono">${escapeHtml(r)}</span>`).join(", ")}` : ""}</span>` : "";
  if (wafer.matched_kind === "lot") return `${run}<span class="wafer-index__alias">trouvée par son lot <span class="mono">${escapeHtml(wafer.matched_alias)}</span></span>`;
  if (wafer.matched_alias && runs.includes(wafer.matched_alias)) return `${run}<span class="wafer-index__alias">trouvée par son run <span class="mono">${escapeHtml(wafer.matched_alias)}</span></span>`;
  if (wafer.matched_alias) return `${run}<span class="wafer-index__alias">trouvée par son autre nom <span class="mono">${escapeHtml(wafer.matched_alias)}</span></span>`;
  const names = wafer.aliases || [];
  return run + (names.length ? `<span class="wafer-index__alias">aussi ${names.map((n) => `<span class="mono">${escapeHtml(n)}</span>`).join(", ")}</span>` : "");
}

function rowHtml(wafer) {
  return `
    <tr${wafer.latest ? "" : ' class="wafer-index__row--record"'}>
      <td><a class="wafer-index__lasermark mono" href="${plateUrl(wafer.lasermark)}">${escapeHtml(wafer.lasermark)}</a>${wafer.latest && wafer.record ? ` ${WaferRecords.chipHtml(wafer.record)}` : ""}${
        (wafer.lots || []).map((l) => ` <span class="plate-tag plate-tag--mute" title="Lot">${escapeHtml(l)}</span>`).join("")
      }${aliasHtml(wafer)}</td>
      <td>${microprojectsHtml(wafer) || '<span class="help">—</span>'}</td>
      <td class="mono">${wafer.count || '<span class="help">—</span>'}</td>
      <td>${fdlChipsHtml([...wafer.fdl, ...(wafer.line_fdl || []).filter((f) => !wafer.fdl.includes(f))], { label: false }) || '<span class="help">—</span>'}</td>
      <td>${wafer.locations.length ? escapeHtml(wafer.locations[0]) : '<span class="help">—</span>'}</td>
      <td>${latestHtml(wafer)}</td>
    </tr>`;
}

// Les lasermarks cherchés que Spectre ne connaît pas (aucune plaque trouvée ne les contient) :
// la page propose de les chercher dans la base.
function missingTerms() {
  const wanted = terms(state.query).filter((t) => !looksLikeAnFdl(t) || terms(state.query).length === 1);
  const keys = state.wafers.flatMap((w) => [w.key, ...(w.aliases || []).map(waferKey), ...(w.run_names || []).map(waferKey)]);
  return wanted.filter((t) => {
    const key = waferKey(t);
    return key && !keys.some((k) => k.includes(key));
  });
}

function renderMissing() {
  const missing = missingTerms();
  missingEl.hidden = !missing.length;
  if (!missing.length) return;
  const n = missing.length;
  missingEl.innerHTML = `
    <span>${n > 1 ? `${n} lasermarks sont inconnus de Spectre` : `« ${escapeHtml(missing[0])} » est inconnue de Spectre`}${n > 1 ? ` (${missing.map((t) => `<span class="mono">${escapeHtml(t)}</span>`).join(", ")})` : ""}.</span>
    <button type="button" class="btn btn-line" id="wafer-missing-lookup">Chercher dans la base de la ligne</button>`;
  missingEl.querySelector("#wafer-missing-lookup").addEventListener("click", () => Lookup.open(missing));
}

function render() {
  const list = sorted(state.wafers);
  const visible = list.slice(0, state.shown);
  rowsEl.innerHTML = visible.map(rowHtml).join("");
  tableEl.setAttribute("aria-busy", "false");
  tableEl.hidden = !list.length;
  moreEl.hidden = list.length <= state.shown;
  countEl.textContent = `${list.length} plaque${list.length > 1 ? "s" : ""}`;
  emptyEl.hidden = list.length > 0;
  if (!list.length) {
    emptyEl.textContent = state.query.trim()
      ? `Aucune plaque ne correspond à « ${state.query.trim()} ». Une plaque est connue dès qu'une étude la suit - son lasermark se renseigne dans la carte « Plaques & entités physiques » d'une fiche, ou au lancement d'une expérience - ou dès qu'elle a une fiche de plaque.`
      : "Aucune plaque n'est encore suivie par une étude, ni enregistrée par une fiche.";
  }
  renderMissing();
}

async function load() {
  const token = ++state.token;
  try {
    const wafers = await search(state.query);
    if (token !== state.token) return; // une recherche plus récente est partie entre-temps
    errorEl.style.display = "none";
    state.wafers = wafers;
    state.shown = PAGE_SIZE;
    render();
  } catch (err) {
    if (token === state.token) showError(err);
  }
}

// -- Chercher dans la base ---------------------------------------------------------------------------

const Lookup = (() => {
  const panel = document.getElementById("wafer-lookup");
  const toggle = document.getElementById("wafer-lookup-toggle");
  const input = document.getElementById("wafer-lookup-input");
  const hint = document.getElementById("wafer-lookup-hint");
  const error = document.getElementById("wafer-lookup-error");
  const results = document.getElementById("wafer-lookup-results");
  const rows = document.getElementById("wafer-lookup-rows");
  const all = document.getElementById("wafer-lookup-all");
  const summary = document.getElementById("wafer-lookup-summary");
  const createBtn = document.getElementById("wafer-lookup-create");
  const goBtn = document.getElementById("wafer-lookup-go");
  let items = []; // les lignes de la dernière recherche (wafersApi.lookup)
  let checked = new Set(); // les clés cochées

  function show(open) {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.classList.toggle("active", open);
    if (open) input.focus();
  }

  // ouvre le panneau avec ces lasermarks, et cherche tout de suite
  function open(lasermarks) {
    show(true);
    if (lasermarks && lasermarks.length) {
      input.value = lasermarks.join("\n");
      run();
    }
  }

  function showError(err) {
    error.textContent = err ? err.message || String(err) : "";
    error.hidden = !err;
  }

  // une plaque se coche quand Spectre ne l'a pas encore en fiche (la base la connaisse ou non :
  // une plaque d'avant toute base reçoit une fiche « saisie à la main », en le disant)
  function creatable(item) {
    return !item.record;
  }

  function spectreHtml(item) {
    const parts = [];
    if (item.record) parts.push(`${WaferRecords.chipHtml(item.record)} <a href="${plateUrl(item.record.lasermark)}">sa page</a>`);
    if (item.studies) {
      const codes = item.microprojects.map((m) => escapeHtml(m.code || m.name)).join(", ");
      parts.push(`${item.studies} étude${item.studies > 1 ? "s" : ""} (${codes}) · <a href="${plateUrl(item.lasermark)}">sa page</a>`);
    }
    return parts.length ? parts.join("<br>") : `<span class="help">inconnue</span>`;
  }

  function baseHtml(item, baseDown) {
    if (item.base) return `<span class="wafer-lookup__found">connue</span> · ${WaferRecords.summaryHtml(item.base) || "fiche Gozer"}`;
    if (baseDown) return `<span class="help">la base n'a pas répondu</span>`;
    return `<span class="wafer-lookup__unknown">introuvable</span>`;
  }

  function renderRows(baseDown) {
    rows.innerHTML = items
      .map((item) => {
        const can = creatable(item);
        return `
          <tr class="${item.base ? "" : "wafer-lookup__row--unknown"}">
            <td>${can ? `<input type="checkbox" data-key="${escapeHtml(item.key)}" aria-label="Créer la fiche de ${escapeHtml(item.lasermark)}"${checked.has(item.key) ? " checked" : ""}>` : ""}</td>
            <td class="mono wafer-lookup__lasermark">${escapeHtml(item.lasermark)}</td>
            <td>${spectreHtml(item)}</td>
            <td>${baseHtml(item, baseDown)}</td>
          </tr>`;
      })
      .join("");
    renderSummary();
  }

  function renderSummary() {
    const n = checked.size;
    const manual = items.filter((i) => checked.has(i.key) && !i.base).length;
    createBtn.disabled = !n;
    createBtn.textContent = n ? `Créer ${n} fiche${n > 1 ? "s" : ""}` : "Créer les fiches";
    const known = items.filter((i) => i.base).length;
    const parts = [`${items.length} plaque${items.length > 1 ? "s" : ""} cherchée${items.length > 1 ? "s" : ""}`, `${known} connue${known > 1 ? "s" : ""} de la base`];
    if (manual) parts.push(`${manual} cochée${manual > 1 ? "s" : ""} hors base : fiche « saisie à la main »`);
    summary.textContent = parts.join(" · ");
    const candidates = items.filter((i) => creatable(i) && i.base);
    all.checked = candidates.length > 0 && candidates.every((i) => checked.has(i.key));
    all.disabled = !candidates.length;
  }

  async function run() {
    const lasermarks = WaferRecords.parseLasermarks(input.value);
    if (!lasermarks.length) {
      hint.textContent = "Collez au moins un lasermark.";
      input.focus();
      return;
    }
    if (lasermarks.length > 100) {
      hint.textContent = `Au plus 100 plaques à la fois (${lasermarks.length} collées).`;
      return;
    }
    hint.textContent = `Recherche de ${lasermarks.length} plaque${lasermarks.length > 1 ? "s" : ""}…`;
    goBtn.disabled = true;
    showError(null);
    try {
      const found = await wafersApi.lookup(lasermarks);
      items = found.items;
      // cochées d'office : celles que la base connaît et que Spectre n'a pas encore
      checked = new Set(items.filter((i) => creatable(i) && i.base).map((i) => i.key));
      results.hidden = false;
      renderRows(Boolean(found.base_error));
      hint.textContent = found.base_error ? "" : `Source : ${WaferRecords.sourceLabel(found.source)}.`;
      if (found.base_error) showError(new Error(`La base n'a pas répondu : ${found.base_error}. Spectre a répondu seul ; une fiche créée maintenant serait « saisie à la main ».`));
    } catch (err) {
      showError(err);
    } finally {
      goBtn.disabled = false;
    }
  }

  async function create() {
    const lasermarks = items.filter((i) => checked.has(i.key)).map((i) => i.lasermark);
    if (!lasermarks.length) return;
    createBtn.disabled = true;
    showError(null);
    try {
      const made = await wafersApi.createRecords(lasermarks);
      const byKey = new Map(made.items.map((r) => [r.key, r]));
      items = items.map((i) => (byKey.has(i.key) ? { ...i, record: byKey.get(i.key) } : i));
      checked = new Set();
      renderRows(Boolean(made.base_error));
      const n = made.items.filter((r) => r.created).length;
      hint.textContent = `${n} fiche${n > 1 ? "s" : ""} créée${n > 1 ? "s" : ""}.`;
      if (made.base_error) showError(new Error(`La base n'a pas répondu : ${made.base_error}. Les fiches sont « saisies à la main » ; leur vie en ligne se lira dès que la base répond.`));
      load(); // la liste les montre
    } catch (err) {
      showError(err);
      renderSummary();
    }
  }

  toggle.addEventListener("click", () => show(panel.hidden));
  document.getElementById("wafer-lookup-close").addEventListener("click", () => show(false));
  document.getElementById("wafer-lookup-form").addEventListener("submit", (event) => {
    event.preventDefault();
    run();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      run();
    }
  });
  rows.addEventListener("change", (event) => {
    const box = event.target.closest("input[data-key]");
    if (!box) return;
    if (box.checked) checked.add(box.dataset.key);
    else checked.delete(box.dataset.key);
    renderSummary();
  });
  all.addEventListener("change", () => {
    items.filter((i) => creatable(i) && i.base).forEach((i) => (all.checked ? checked.add(i.key) : checked.delete(i.key)));
    rows.querySelectorAll("input[data-key]").forEach((box) => (box.checked = checked.has(box.dataset.key)));
    renderSummary();
  });
  createBtn.addEventListener("click", create);

  return { open };
})();

document.getElementById("wafer-search").addEventListener(
  "input",
  debounce((event) => {
    state.query = event.target.value;
    load();
  })
);

document.querySelectorAll("[data-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    state.sort = button.dataset.sort;
    document.querySelectorAll("[data-sort]").forEach((b) => {
      const active = b === button;
      b.classList.toggle("active", active);
      b.setAttribute("aria-pressed", String(active));
    });
    render();
  });
});

document.getElementById("wafer-more-btn").addEventListener("click", () => {
  state.shown += PAGE_SIZE;
  render();
});

// ?base=W12-A3,W12-A4 : la page s'ouvre sur la recherche dans la base (un lien, une autre page)
const initial = new URLSearchParams(window.location.search).get("base");
if (initial) Lookup.open(WaferRecords.parseLasermarks(initial));

load();
