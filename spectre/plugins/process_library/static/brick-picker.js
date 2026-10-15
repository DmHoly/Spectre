/* « Promouvoir une brique » (global `BrickPicker`) : une boîte avec une recherche qui liste les
   briques qui ne sont pas encore des références - celles que le compte peut modifier, partagées ou
   de ses µprojets -, et un bouton « Promouvoir » qui ouvre le formulaire de la promotion sur la brique
   choisie (PromotionLink, plugin promotion). Les briques intégrées ne se promeuvent pas : elles ne sont
   pas listées. */

const BrickPicker = (() => {
  let dialog = null;
  let bricks = null; // chargées à la première ouverture
  let chosen = null;

  function fold(text) {
    return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  const SCOPE_LABELS = { shared: "partagée", microproject: "µprojet" };

  // Toutes les briques visibles - partagées et celles de chaque µprojet du compte - sans doublon.
  async function load() {
    const microprojects = await microprojectsApi.list().catch(() => []);
    const lists = await Promise.all([
      processLibraryApi.techBricks({}),
      ...microprojects.map((m) => processLibraryApi.techBricks({ microproject: m.slug }).catch(() => [])),
    ]);
    const byId = new Map();
    lists.flat().forEach((brick) => byId.set(brick.id, brick));
    return [...byId.values()].filter((b) => !b.reference && b.scope !== "builtin" && b.can_edit).sort((a, b) => a.name.localeCompare(b.name, "fr"));
  }

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "ref-dialog";
    dialog.setAttribute("aria-labelledby", "brick-pick-title");
    dialog.innerHTML = `
      <div class="card-pad ref-dialog__inner">
        <h2 class="ref-dialog__title" id="brick-pick-title">Promouvoir une brique</h2>
        <p class="help ref-dialog__lead">Cherchez la brique à faire passer en brique de référence : seules celles qui n'en sont pas déjà une, et que vous pouvez modifier, sont listées.</p>
        <label for="brick-pick-search" class="ref-visually-hidden">Chercher une brique</label>
        <input class="field" id="brick-pick-search" type="search" placeholder="Chercher une brique (nom, notes)" autocomplete="off">
        <ul class="ref-start__options" id="brick-pick-list" role="listbox" aria-label="Briques"></ul>
        <div class="ref-dialog__actions ref-dialog__actions--split">
          <button class="btn btn-line" type="button" id="brick-pick-cancel">Annuler</button>
          <span id="brick-pick-go"></span>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("#brick-pick-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelector("#brick-pick-search").addEventListener("input", render);
    dialog.querySelector("#brick-pick-list").addEventListener("click", (event) => {
      const row = event.target.closest("[data-id]");
      if (!row) return;
      chosen = row.dataset.id;
      render();
    });
    dialog.querySelector("#brick-pick-list").addEventListener("dblclick", (event) => {
      const row = event.target.closest("[data-id]");
      if (row) window.location.href = PromotionLink.url({ brick: row.dataset.id });
    });
  }

  function render() {
    const needle = fold(dialog.querySelector("#brick-pick-search").value.trim());
    const shown = (bricks || []).filter((b) => !needle || fold(b.name).includes(needle) || fold(b.notes).includes(needle));
    const list = dialog.querySelector("#brick-pick-list");
    list.innerHTML = shown.length
      ? shown
          .map(
            (b) => `
        <li class="ref-start__option" role="option" tabindex="0" data-id="${escapeHtml(b.id)}" aria-selected="${b.id === chosen}">
          <span class="ref-start__name">${escapeHtml(b.name)}</span>
          <span class="ref-start__meta">${escapeHtml(SCOPE_LABELS[b.scope] || b.scope)}${b.microproject ? ` ${escapeHtml(b.microproject)}` : ""} · v${escapeHtml(b.version || "1.0")} · ${b.steps.length} étape${b.steps.length > 1 ? "s" : ""}</span>
        </li>`
          )
          .join("")
      : `<li class="ref-start__empty">${bricks && bricks.length ? "Aucune brique ne correspond." : "Aucune brique à promouvoir : toutes sont déjà des références, ou vous ne pouvez modifier aucune brique."}</li>`;
    const go = dialog.querySelector("#brick-pick-go");
    go.innerHTML = chosen && shown.some((b) => b.id === chosen) ? PromotionLink.html({ brick: chosen, back: "/briques" }, { label: "Promouvoir cette brique" }) : "";
  }

  async function open() {
    if (!dialog) build();
    chosen = null;
    dialog.querySelector("#brick-pick-search").value = "";
    dialog.querySelector("#brick-pick-list").innerHTML = `<li class="ref-start__empty">Chargement…</li>`;
    dialog.showModal();
    try {
      bricks = await load();
    } catch (err) {
      bricks = [];
      dialog.querySelector("#brick-pick-list").innerHTML = `<li class="ref-start__empty">${escapeHtml(err.message || String(err))}</li>`;
      return;
    }
    render();
    dialog.querySelector("#brick-pick-search").focus();
  }

  return { open };
})();
