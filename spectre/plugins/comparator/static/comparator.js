/* Page /comparateur : choisir des plaques, des études et des versions de référence, et les comparer
   dans le tableau du plugin (comparator-table.js). Les lignes vivent dans l'adresse
   (?item=…&item=…&base=n) : un lien partage la comparaison. Le serveur détaille chaque jeton (une
   campagne devient une ligne par variante) : la page reprend alors les jetons des lignes rendues,
   pour qu'on puisse en retirer, déplacer ou choisir comme base chacune. Le panneau des plaques
   jumelles (plugin twins, s'il est actif) cherche les plaques de la structure de la base et en ajoute
   au tableau. */

(() => {
  const state = { items: [], baseline: 0, result: null, options: [], active: -1, loading: 0 };
  const input = document.getElementById("picker-input");
  const listbox = document.getElementById("picker-options");
  const errorEl = document.getElementById("error");
  const copyBtn = document.getElementById("copy-link");
  const clearBtn = document.getElementById("clear");
  const EMPTY = { baseline: 0, rows: [], groups: [], summary: {} };

  // comparator.service.MAX_ITEMS : une comparaison ne porte pas plus de lignes
  const MAX_ITEMS = 30;
  const SOURCE_TITLES = { wafer: "Plaques", study: "Études", reference: "Références" };

  function readUrl() {
    const params = new URLSearchParams(location.search);
    state.items = params.getAll("item").filter(Boolean);
    const base = Number(params.get("base") || 0);
    state.baseline = Number.isInteger(base) && base >= 0 && base < state.items.length ? base : 0;
  }

  function syncUrl() {
    const url = state.items.length ? Comparator.pageUrl(state.items, state.baseline) : "/comparateur";
    history.replaceState(null, "", url);
    copyBtn.hidden = clearBtn.hidden = !state.items.length;
    syncAnalyse();
  }

  // « Analyser ces plaques » (plugin meta_analysis) : une nouvelle analyse des plaques du tableau, la base en
  // référence (la première plaque si la base n'en est pas une)
  const analyseLink = document.getElementById("analyse");
  function syncAnalyse() {
    if (!pluginEnabled("meta_analysis")) return;
    const wafer = (item) => (item && item.startsWith("wafer:") ? item.slice("wafer:".length) : null);
    const lasermarks = state.items.map(wafer).filter(Boolean);
    const base = wafer(state.items[state.baseline]) || lasermarks[0];
    analyseLink.hidden = !base;
    if (!base) return;
    const others = lasermarks.filter((l) => l !== base);
    analyseLink.href = `/analyses?${new URLSearchParams({ ref: base, plaques: others.join(",") })}`;
  }

  function showError(message) {
    errorEl.textContent = message || "";
    errorEl.hidden = !message;
  }

  const table = Comparator.mount(document.getElementById("comparison"), EMPTY, {
    tools: true,
    emptyText: "Ajoutez des plaques, des études ou des références : la première sera la base.",
    onBaseline: (index) => {
      state.baseline = index;
      refresh();
    },
    onRemove: (index) => {
      state.items.splice(index, 1);
      if (state.baseline === index) state.baseline = 0;
      else if (state.baseline > index) state.baseline -= 1;
      refresh();
    },
    onMove: (index, delta) => {
      const to = index + delta;
      if (to < 0 || to >= state.items.length) return;
      const [item] = state.items.splice(index, 1);
      state.items.splice(to, 0, item);
      if (state.baseline === index) state.baseline = to;
      else if (state.baseline === to) state.baseline = index;
      refresh();
    },
  });

  const twins =
    pluginEnabled("twins") && typeof Twins !== "undefined"
      ? Twins.mount(document.getElementById("twins"), {
          getBase: () => {
            const item = state.items[state.baseline];
            return item ? { item, label: state.result?.rows?.[state.baseline]?.label || item } : null;
          },
          has: (item) => state.items.includes(item),
          onAdd: addMany,
        })
      : null;

  async function refresh() {
    syncUrl();
    showError("");
    if (!state.items.length) {
      state.result = EMPTY;
      table.update(EMPTY);
      twins?.update();
      return;
    }
    const ticket = ++state.loading;
    try {
      const result = await comparatorApi.compare(state.items, state.baseline);
      if (ticket !== state.loading) return;
      // une campagne ajoutée devient ses variantes : la page suit les lignes rendues
      state.items = result.rows.map((row) => row.item);
      state.baseline = result.baseline || 0;
      state.result = result;
      syncUrl();
      table.update(result);
      twins?.update();
    } catch (err) {
      if (ticket === state.loading) showError(err.message || String(err));
    }
  }

  // plusieurs lignes d'un coup (les plaques jumelles) : celles que le tableau n'a pas, dans la limite de ses lignes
  function addMany(items) {
    const fresh = items.filter((item) => !state.items.includes(item));
    const room = Math.max(MAX_ITEMS - state.items.length, 0);
    state.items.push(...fresh.slice(0, room));
    refresh();
    if (fresh.length > room) showError(`Une comparaison porte ${MAX_ITEMS} lignes au plus : ${room ? `${room} plaques ajoutées sur ${fresh.length}` : "retirez des lignes pour en ajouter"}.`);
  }

  function add(item) {
    if (!state.items.includes(item)) state.items.push(item);
    input.value = "";
    closeOptions();
    refresh();
  }

  // -- suggestions (combobox) -------------------------------------------------------------------

  function closeOptions() {
    listbox.hidden = true;
    listbox.innerHTML = "";
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    state.options = [];
    state.active = -1;
  }

  function renderOptions(query) {
    if (!state.options.length) {
      listbox.innerHTML = `<li class="cmp-options__empty" role="presentation">Rien ne répond à « ${escapeHtml(query)} » dans vos µprojets.</li>`;
    } else {
      let html = "";
      let previous = null;
      state.options.forEach((option, index) => {
        if (option.source !== previous) {
          html += `<li class="cmp-options__group" role="presentation">${escapeHtml(SOURCE_TITLES[option.source] || option.source)}</li>`;
          previous = option.source;
        }
        const added = state.items.includes(option.item);
        html += `
          <li class="cmp-option${added ? " is-added" : ""}" role="option" id="picker-option-${index}" data-index="${index}" aria-selected="${index === state.active}">
            <span class="cmp-option__label">${escapeHtml(option.label)}${added ? " · déjà dans le tableau" : ""}</span>
            ${option.sublabel ? `<span class="cmp-option__sub">${escapeHtml(option.sublabel)}</span>` : ""}
          </li>`;
      });
      listbox.innerHTML = html;
    }
    listbox.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (state.active >= 0) input.setAttribute("aria-activedescendant", `picker-option-${state.active}`);
    else input.removeAttribute("aria-activedescendant");
  }

  let timer = null;
  let searchTicket = 0;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    const query = input.value.trim();
    if (!query) {
      closeOptions();
      return;
    }
    timer = setTimeout(async () => {
      const ticket = ++searchTicket;
      try {
        const options = await comparatorApi.candidates(query);
        if (ticket !== searchTicket || input.value.trim() !== query) return;
        state.options = options;
        state.active = options.length ? 0 : -1;
        renderOptions(query);
      } catch (err) {
        showError(err.message || String(err));
      }
    }, 200);
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeOptions();
      return;
    }
    if (listbox.hidden || !state.options.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      state.active = (state.active + step + state.options.length) % state.options.length;
      renderOptions(input.value.trim());
      document.getElementById(`picker-option-${state.active}`)?.scrollIntoView({ block: "nearest" });
    } else if (event.key === "Enter" && state.active >= 0) {
      event.preventDefault();
      add(state.options[state.active].item);
    }
  });

  listbox.addEventListener("mousedown", (event) => event.preventDefault()); // garder le focus dans le champ
  listbox.addEventListener("click", (event) => {
    const option = event.target.closest(".cmp-option");
    if (option) add(state.options[Number(option.dataset.index)].item);
  });
  input.addEventListener("blur", () => setTimeout(closeOptions, 120));

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      copyBtn.textContent = "Lien copié";
    } catch (err) {
      copyBtn.textContent = "Copie impossible";
    }
    setTimeout(() => (copyBtn.textContent = "Copier le lien"), 1600);
  });
  clearBtn.addEventListener("click", () => {
    state.items = [];
    state.baseline = 0;
    refresh();
    input.focus();
  });

  readUrl();
  refresh();
})();
