/* Le panneau des plaques jumelles (global `Twins`) de la page /comparateur : cherche, parmi toutes les
   plaques de vos µprojets, celles qui ont la structure de la ligne de base - exactement, ou à une ou
   deux variations près - et les ajoute à la comparaison. Le serveur cherche et compte
   (GET /api/wafer-twins, twins/service.py) ; le panneau ne compare rien. Une variation est une
   différence que le tableau colorerait : un paramètre modifié ou ajouté, une couche en plus ou
   absente, une étape déplacée.

   Twins.mount(el, {getBase, has, onAdd}) -> {update()}
     getBase() -> {item, label} | null : la ligne de base du tableau ;
     has(item) -> bool : la plaque est déjà une ligne du tableau ;
     onAdd(items) : les jetons des plaques à ajouter.
   update() : à rappeler quand le tableau a changé (la base, ses lignes).
   Les pages qui le montent chargent aussi /static/twins/twins.css (et celle du comparateur). */

const Twins = (() => {
  const TOLERANCES = [
    [0, "Identique"],
    [1, "1 variation"],
    [2, "2 variations"],
  ];
  // les mêmes marques que la légende du tableau (comparator-table.js)
  const MARKS = { changed: "≠", added_param: "+", added_layer: "+", moved: "↕", absent: "−" };

  function plural(n, one, many) {
    return `${n} ${n > 1 ? many : one}`;
  }

  function differenceText(d) {
    const where = d.parameter ? `${d.step} · ${d.parameter}` : d.step;
    if (d.kind === "changed") return `${where} : ${d.from} → ${d.to}`;
    if (d.kind === "added_param") return `${where} ajouté : ${d.to}`;
    if (d.kind === "added_layer") return `Couche en plus : ${d.step}`;
    if (d.kind === "moved") return `Étape déplacée : ${d.step}`;
    return `Couche absente : ${d.step}`;
  }

  function twinHtml(twin, index, added) {
    const badge = twin.variations ? plural(twin.variations, "variation", "variations") : "identique";
    const sub = [twin.study, twin.microproject, twin.version].filter(Boolean).join(" · ");
    const study = twin.url ? `<a class="twin__sub" href="${escapeHtml(twin.url)}">${escapeHtml(sub)}</a>` : `<span class="twin__sub">${escapeHtml(sub)}</span>`;
    const diffs = twin.differences
      .map((d) => `<li><span class="cmp-swatch cmp-swatch--${d.kind}" aria-hidden="true">${MARKS[d.kind]}</span>${escapeHtml(differenceText(d))}</li>`)
      .join("");
    return `
      <li class="twin${added ? " is-added" : ""}">
        <input type="checkbox" class="twin__check" id="twin-${index}" data-index="${index}" ${added ? "disabled" : "checked"}>
        <div class="twin__body">
          <label for="twin-${index}" class="twin__top">
            <span class="twin__name">${escapeHtml(twin.lasermark)}</span>
            <span class="twin__badge${twin.variations ? "" : " is-same"}">${escapeHtml(badge)}</span>
            ${added ? `<span class="twin__note">déjà dans le tableau</span>` : ""}
          </label>
          ${study}
          ${diffs ? `<ul class="twin__diffs">${diffs}</ul>` : ""}
        </div>
      </li>`;
  }

  function mount(el, options) {
    const state = { max: 0, loading: false, result: null, base: null, error: "" };

    function resultText() {
      const { twins, scanned, skipped, truncated } = state.result;
      const kind = state.result.max_variations ? `à ${plural(state.result.max_variations, "variation", "variations")} près` : "de structure identique";
      const found = twins.length ? `${plural(twins.length, "plaque trouvée", "plaques trouvées")} ${kind}` : `Aucune plaque ${kind}`;
      const scope = `${plural(scanned, "plaque examinée", "plaques examinées")}${skipped ? `, ${plural(skipped, "sans structure comparable", "sans structure comparable")}` : ""}`;
      return `${found} (${scope})${truncated ? " - les plus proches seulement" : ""}.`;
    }

    function render() {
      const base = options.getBase();
      const form = TOLERANCES.map(
        ([value, label]) => `
          <label class="twins__option">
            <input type="radio" name="twins-max" value="${value}" ${state.max === value ? "checked" : ""}>
            <span>${label}</span>
          </label>`
      ).join("");
      let body = "";
      if (state.error) {
        body = `<p class="twins__status is-error" role="alert">${escapeHtml(state.error)}</p>`;
      } else if (state.loading) {
        body = `<p class="twins__status" aria-live="polite">Recherche en cours…</p>`;
      } else if (state.result) {
        const items = state.result.twins;
        const todo = items.filter((twin) => !options.has(twin.item)).length;
        body = `
          <p class="twins__status" aria-live="polite">${escapeHtml(resultText())}</p>
          ${items.length ? `<ul class="twins__list">${items.map((twin, i) => twinHtml(twin, i, options.has(twin.item))).join("")}</ul>` : ""}
          ${todo ? `<div class="twins__actions"><button type="button" class="btn btn-primary js-twins-add"></button></div>` : ""}`;
      }
      el.innerHTML = `
        <section class="card card-pad twins" aria-labelledby="twins-title">
          <div class="twins__head">
            <h2 id="twins-title" class="twins__title">Plaques jumelles</h2>
            <p class="twins__lead">Parmi toutes les plaques de vos µprojets, celles qui ont la structure de la ligne de base - ou qui n'en diffèrent que par une ou deux variations.</p>
          </div>
          <div class="twins__form">
            <fieldset class="twins__range"><legend class="cmp-sr">Écart toléré avec la base</legend>${form}</fieldset>
            <button type="button" class="btn btn-line js-twins-search" ${base && !state.loading ? "" : "disabled"}>${base ? `Chercher les jumelles de ${escapeHtml(base.label)}` : "Ajoutez d'abord une ligne de base"}</button>
          </div>
          ${body}
        </section>`;
      refreshAddButton();
    }

    function checkedTwins() {
      return [...el.querySelectorAll(".twin__check:checked")].map((box) => state.result.twins[Number(box.dataset.index)]);
    }

    function refreshAddButton() {
      const button = el.querySelector(".js-twins-add");
      if (!button) return;
      const count = checkedTwins().length;
      button.disabled = !count;
      button.textContent = count ? `Ajouter ${plural(count, "plaque", "plaques")} au tableau` : "Aucune plaque cochée";
    }

    async function search() {
      const base = options.getBase();
      if (!base || state.loading) return;
      state.loading = true;
      state.error = "";
      state.result = null;
      state.base = base.item;
      render();
      try {
        state.result = await twinsApi.find(base.item, state.max);
      } catch (err) {
        state.error = err.message || String(err);
      }
      state.loading = false;
      render();
      el.querySelector(".js-twins-search")?.focus();
    }

    el.addEventListener("change", (event) => {
      if (event.target.name === "twins-max") state.max = Number(event.target.value);
      else if (event.target.classList.contains("twin__check")) refreshAddButton();
    });
    el.addEventListener("click", (event) => {
      if (event.target.closest(".js-twins-search")) search();
      else if (event.target.closest(".js-twins-add")) {
        const items = checkedTwins().map((twin) => twin.item);
        if (items.length) options.onAdd(items);
      }
    });

    render();
    return {
      update() {
        // des jumelles d'une autre base ne sont plus à jour
        const base = options.getBase();
        if (state.result && (!base || base.item !== state.base)) {
          state.result = null;
          state.error = "";
        }
        if (!state.loading) render();
      },
    };
  }

  return { mount, differenceText };
})();
