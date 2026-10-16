/* « Lots JIRA » sur la page des lots : tous les lots cités par les feuilles de lancement
   (jira_nom_lots, hook PRISM jira_lots), filtrables, chacun avec le lot Spectre du même nom s'il
   existe ; « Importer » crée (ou complète) le lot avec toutes ses plaques et leur fiche de plaque
   (lotsApi.importJiraLot). La page se relit à la fermeture si un lot a été importé.

   Dépend de lotsApi, escapeHtml, formatDate. */

(() => {
  const button = document.getElementById("jira-lots-btn");
  if (!button) return;
  let dialog = null;
  let items = [];
  let changed = false;

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "jira-lots";
    dialog.setAttribute("aria-labelledby", "jira-lots-title");
    dialog.innerHTML = `
      <div class="card-pad jira-lots__inner">
        <h2 id="jira-lots-title" style="font-size:16px;margin:0 0 4px;">Lots JIRA</h2>
        <p class="help" style="margin:0 0 12px;">Les noms de lot qu'écrivent les feuilles de lancement (champ « nom des lots »). Importer un lot le fait exister ici avec toutes ses plaques, chacune avec sa fiche de plaque. Un lot se crée aussi tout seul dès qu'on ouvre la page d'une de ses plaques.</p>
        <div class="error" role="alert" hidden></div>
        <input type="search" class="field js-jira-q" placeholder="Filtrer : QMDE, QT1…" aria-label="Filtrer les lots JIRA">
        <ul class="jira-lots__list js-jira-list"><li class="jira-lots__row help">Lecture de JIRA…</li></ul>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:12px;">
          <span class="help js-jira-source" style="margin:0;"></span>
          <button type="button" class="btn btn-line js-jira-close">Fermer</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector(".js-jira-close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      if (changed) window.location.reload();
    });
    dialog.querySelector(".js-jira-q").addEventListener("input", (e) => render(e.target.value));
    dialog.querySelector(".js-jira-list").addEventListener("click", (e) => {
      const b = e.target.closest("[data-import]");
      if (b) importLot(b.dataset.import, b);
    });
  }

  function showError(err) {
    const box = dialog.querySelector(".error");
    box.textContent = err ? err.message || String(err) : "";
    box.hidden = !err;
  }

  function rowHtml(lot) {
    const here = lot.spectre;
    const dates = [lot.first, lot.last].filter(Boolean);
    return `
      <li class="jira-lots__row">
        <span class="jira-lots__name">${escapeHtml(lot.name)}</span>
        <span class="jira-lots__meta">${lot.n_fdl} FDL${dates.length ? ` · ${escapeHtml(formatDate(dates[0]))}${dates[1] && dates[1] !== dates[0] ? ` → ${escapeHtml(formatDate(dates[1]))}` : ""}` : ""}${
          lot.raw.length > 1 || lot.raw[0] !== lot.name ? ` · écrit ${lot.raw.map((r) => `« ${escapeHtml(r)} »`).join(", ")}` : ""
        }</span>
        ${here ? `<a class="fiche-code" href="/lots/${encodeURIComponent(here.code)}">${escapeHtml(here.code)}</a> <span class="help" style="margin:0;">${here.wafers} plaque${here.wafers > 1 ? "s" : ""}</span>` : ""}
        <button type="button" class="btn btn-line btn-sm" data-import="${escapeHtml(lot.name)}">${here ? "Compléter" : "Importer"}</button>
      </li>`;
  }

  function render(q) {
    const wanted = (q || "").replace(/\s+/g, "").toUpperCase();
    const shown = items.filter((l) => !wanted || l.name.replace(/\s+/g, "").toUpperCase().includes(wanted));
    dialog.querySelector(".js-jira-list").innerHTML = shown.length
      ? shown.map(rowHtml).join("")
      : `<li class="jira-lots__row help">${items.length ? "Aucun lot ne correspond." : "Aucun lot cité par les FDL."}</li>`;
  }

  async function importLot(name, b) {
    b.disabled = true;
    b.textContent = "Import…";
    showError(null);
    try {
      const r = await lotsApi.importJiraLot(name);
      changed = true;
      const row = b.closest(".jira-lots__row");
      row.insertAdjacentHTML(
        "beforeend",
        `<span class="jira-lots__result">${r.created ? "Lot créé" : "Lot complété"} : ${r.added} plaque${r.added > 1 ? "s" : ""} ajoutée${r.added > 1 ? "s" : ""} sur ${r.wafers}, ${r.records_created} fiche${r.records_created > 1 ? "s" : ""} créée${r.records_created > 1 ? "s" : ""}${r.base_error ? ` (base de la ligne injoignable : ${escapeHtml(r.base_error)})` : ""} - <a href="/lots/${encodeURIComponent(r.lot.code)}">voir le lot</a></span>`
      );
      b.textContent = "Importé";
    } catch (err) {
      showError(err);
      b.disabled = false;
      b.textContent = "Importer";
    }
  }

  async function open() {
    if (!dialog) build();
    changed = false;
    showError(null);
    dialog.showModal();
    try {
      const data = await lotsApi.jiraLots("");
      items = data.items;
      dialog.querySelector(".js-jira-source").textContent = data.source === "demo" ? "Source : démonstration" : "Source : JIRA (PRISM)";
      render(dialog.querySelector(".js-jira-q").value);
    } catch (err) {
      dialog.querySelector(".js-jira-list").innerHTML = "";
      showError(err);
    }
  }

  button.addEventListener("click", open);
})();
