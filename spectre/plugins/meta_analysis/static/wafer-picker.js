/* Le sélecteur de plaques d'une analyse (global `WaferPicker`) : on tape ce qu'on sait d'elles, comme dans la barre
   du haut - un lasermark (ou un ancien nom), un run d'épitaxie, un lot, un µprojet, une FDL - et chaque réponse est
   un groupe de plaques (GET /api/analyses/wafer-search) : son en-tête ajoute tout le groupe, chaque plaque s'ajoute
   seule. Plusieurs lasermarks collés (séparés par des virgules ou des points-virgules) s'ajoutent tels quels ; une
   plaque que Spectre ne connaît pas encore aussi.

     WaferPicker.mount({input, listbox, onPick(lasermarks), has(key)}) - input : le champ (role=combobox),
     listbox : sa liste (role=listbox) ; onPick reçoit les lasermarks choisis ; has dit qu'une plaque y est déjà. */

const WaferPicker = (() => {
  const KINDS = { wafer: "Plaques", run: "Run d'épitaxie", lot: "Lot", name: "Ancien nom", microproject: "µprojet", fdl: "FDL" };
  const SHOWN = 6; // plaques montrées sous un groupe ; « ajouter » les prend toutes
  const keyOf = (lasermark) => String(lasermark || "").replace(/[^0-9a-z]/gi, "").toUpperCase();

  function mount({ input, listbox, onPick, has }) {
    let options = [];
    let active = -1;
    let timer = null;
    let ticket = 0;

    function close() {
      listbox.hidden = true;
      listbox.innerHTML = "";
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
      options = [];
      active = -1;
    }

    function optionHtml(option, index) {
      const id = `${listbox.id}-${index}`;
      const selected = `aria-selected="${index === active}"`;
      if (option.type === "group") {
        const g = option.group;
        const fresh = g.wafers.filter((w) => !has(w.key)).length;
        const action = fresh
          ? `+ ajouter ${fresh > 1 ? `les ${fresh}${g.total > g.wafers.length ? " premières" : ""}` : "la plaque"}`
          : "déjà toutes dans l'analyse";
        return `<li class="ma-pick-group${fresh ? "" : " is-added"}" role="option" id="${id}" data-index="${index}" ${selected}>
          <span class="ma-pick-group__kind">${KINDS[g.kind] || g.kind}</span>
          <span class="ma-pick-group__label">${escapeHtml(g.label)}</span>
          <span class="ma-pick-group__detail">${escapeHtml(g.detail)} · ${g.total} plaque${g.total > 1 ? "s" : ""}</span>
          <span class="ma-pick-group__add">${action}</span>
        </li>`;
      }
      if (option.type === "more") return `<li class="ma-pick-more" role="presentation">… et ${option.count} autre${option.count > 1 ? "s" : ""}, avec « ajouter » au-dessus</li>`;
      if (option.type === "typed") {
        return `<li class="cmp-option ma-pick-typed" role="option" id="${id}" data-index="${index}" ${selected}>
          <span class="cmp-option__label">Ajouter ${option.lasermarks.length > 1 ? `ces ${option.lasermarks.length} plaques` : "la plaque"} telle${option.lasermarks.length > 1 ? "s" : ""} qu'écrite${option.lasermarks.length > 1 ? "s" : ""}</span>
          <span class="cmp-option__sub mono">${escapeHtml(option.lasermarks.join(", "))}</span>
        </li>`;
      }
      const w = option.wafer;
      const added = has(w.key);
      return `<li class="cmp-option ma-pick-wafer${added ? " is-added" : ""}" role="option" id="${id}" data-index="${index}" ${selected}>
        <span class="cmp-option__label mono">${escapeHtml(w.lasermark)}${added ? ` <span class="help" style="margin:0;">· déjà dans l'analyse</span>` : ""}</span>
        ${w.detail ? `<span class="cmp-option__sub">${escapeHtml(w.detail)}</span>` : ""}
      </li>`;
    }

    function render() {
      listbox.innerHTML = options.length
        ? options.map(optionHtml).join("")
        : `<li class="cmp-options__empty" role="presentation">Rien ne répond : un lasermark, un run d'épitaxie, un lot, un µprojet ou une FDL.</li>`;
      listbox.hidden = false;
      input.setAttribute("aria-expanded", "true");
      if (active >= 0) input.setAttribute("aria-activedescendant", `${listbox.id}-${active}`);
      else input.removeAttribute("aria-activedescendant");
    }

    const selectable = (i) => options[i] && options[i].type !== "more";
    function move(step) {
      if (!options.some((o, i) => selectable(i))) return;
      do active = (active + step + options.length) % options.length;
      while (!selectable(active));
      render();
      document.getElementById(`${listbox.id}-${active}`)?.scrollIntoView({ block: "nearest" });
    }

    function pick(option) {
      let lasermarks = [];
      if (option.type === "group") lasermarks = option.group.wafers.filter((w) => !has(w.key)).map((w) => w.lasermark);
      else if (option.type === "typed") lasermarks = option.lasermarks.filter((l) => !has(keyOf(l)));
      else if (!has(option.wafer.key)) lasermarks = [option.wafer.lasermark];
      input.value = "";
      close();
      if (lasermarks.length) onPick(lasermarks);
    }

    function build(query, groups) {
      const list = [];
      const typed = query.split(/[,;\n]+/).map((v) => v.trim()).filter(Boolean);
      if (typed.length > 1) list.push({ type: "typed", lasermarks: typed });
      groups.forEach((group) => {
        list.push({ type: "group", group });
        group.wafers.slice(0, SHOWN).forEach((wafer) => list.push({ type: "wafer", wafer }));
        if (group.total > SHOWN) list.push({ type: "more", count: group.total - SHOWN });
      });
      if (!groups.length && typed.length === 1) list.push({ type: "typed", lasermarks: typed });
      return list;
    }

    input.addEventListener("input", () => {
      clearTimeout(timer);
      const query = input.value.trim();
      if (!query) return close();
      timer = setTimeout(async () => {
        const mine = ++ticket;
        const several = query.split(/[,;\n]+/).filter((v) => v.trim()).length > 1;
        try {
          const found = several ? { groups: [] } : await metaAnalysisApi.searchWafers(query);
          if (mine !== ticket || input.value.trim() !== query) return;
          options = build(query, found.groups);
          active = options.findIndex((o, i) => selectable(i));
          render();
        } catch (err) {
          listbox.innerHTML = `<li class="cmp-options__empty" role="presentation">${escapeHtml(err.message || String(err))}</li>`;
          listbox.hidden = false;
        }
      }, 220);
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") return close();
      if (listbox.hidden || !options.length) return;
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        move(event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Enter" && selectable(active)) {
        event.preventDefault();
        pick(options[active]);
      }
    });
    listbox.addEventListener("mousedown", (event) => event.preventDefault()); // garder le focus dans le champ
    listbox.addEventListener("click", (event) => {
      const row = event.target.closest("[data-index]");
      if (row) pick(options[Number(row.dataset.index)]);
    });
    input.addEventListener("blur", () => setTimeout(close, 120));
    return { close };
  }

  return { mount, keyOf };
})();
