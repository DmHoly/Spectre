/* « Rapport » sur la page d'une plaque (wafer.html, plugin lumiere) - PlateReport.mount(plate) : un bouton dans
   les actions de l'en-tête ouvre une fenêtre qui liste les modèles de rapport d'une plaque (lumiereApi.templates),
   lance la génération (lumiereApi.request : en tâche de fond, suivie ici jusqu'à « prêt »), et montre les rapports
   déjà générés pour cette plaque (télécharger, retirer). Dépend de lumiereApi, LumiereUI, escapeHtml. */

const PlateReport = (() => {
  let dialog = null;
  let plate = null;
  let templates = [];
  let stopFollow = null;

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "wafer-dialog wafer-dialog--narrow lm-dialog";
    dialog.setAttribute("aria-labelledby", "plate-report-title");
    dialog.innerHTML = `
      <div class="card-pad wafer-dialog__inner">
        <h2 class="wafer-dialog__title" id="plate-report-title">Rapport de la plaque</h2>
        <p class="help wafer-dialog__lead js-lead">Un fichier HTML autonome, généré par Lumière avec ce que Spectre sait de cette plaque : il s'ouvre hors ligne, se transmet tel quel et s'imprime.</p>
        <div class="error" role="alert" hidden></div>
        <div class="lm-templates js-templates"></div>
        <h3 class="lm-subtitle">Rapports déjà générés</h3>
        <ul class="lm-reports js-reports"><li class="help">Chargement…</li></ul>
        <div class="wafer-dialog__actions">
          <a class="btn btn-line" href="/lumiere">Tous les rapports</a>
          <button class="btn btn-line" type="button" data-close>Fermer</button>
          <button class="btn btn-primary" type="button" data-generate>Générer</button>
        </div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.querySelector("[data-generate]").addEventListener("click", generate);
    dialog.addEventListener("click", async (event) => {
      const remove = event.target.closest("[data-remove]");
      if (!remove) return;
      remove.disabled = true;
      try {
        await lumiereApi.remove(remove.dataset.remove);
        await loadReports();
      } catch (err) {
        showError(err);
      }
    });
    dialog.addEventListener("close", () => {
      if (stopFollow) stopFollow();
      stopFollow = null;
    });
  }

  function showError(err) {
    const box = dialog.querySelector(".error");
    box.textContent = err ? err.message || String(err) : "";
    box.hidden = !err;
  }

  function templatesHtml() {
    if (!templates.length) return `<p class="help">Aucun modèle de rapport pour une plaque.</p>`;
    return templates
      .map(
        (t, i) => `<label class="lm-template">
          <input type="radio" name="plate-report-template" value="${escapeHtml(t.key)}" ${i === 0 ? "checked" : ""}>
          <span class="lm-template__body">
            <span class="lm-template__name">${escapeHtml(t.name)}</span>
            <span class="lm-template__desc">${escapeHtml(t.description)}</span>
            <span class="lm-template__slides">${t.slides.map((s) => `<span>${escapeHtml(s)}</span>`).join("")}</span>
          </span>
        </label>`
      )
      .join("");
  }

  async function loadTemplates() {
    templates = (await lumiereApi.templates("wafer")).templates;
    dialog.querySelector(".js-templates").innerHTML = templatesHtml();
    dialog.querySelector("[data-generate]").disabled = !templates.length;
  }

  async function loadReports() {
    const { reports } = await lumiereApi.list({ kind: "wafer", key: plate.lasermark });
    const list = dialog.querySelector(".js-reports");
    list.innerHTML = reports.length ? reports.map((r) => LumiereUI.rowHtml(r, { context: false })).join("") : `<li class="help">Aucun rapport encore pour cette plaque.</li>`;
    const busy = reports.find((r) => r.status === "queued" || r.status === "running");
    if (busy && !stopFollow) watch(busy.id);
  }

  function watch(id) {
    if (stopFollow) stopFollow();
    stopFollow = LumiereUI.follow(id, (report) => {
      const row = dialog.querySelector(`[data-report="${report.id}"]`);
      if (row) row.outerHTML = LumiereUI.rowHtml(report, { context: false });
      if (report.status !== "queued" && report.status !== "running") {
        stopFollow = null;
        dialog.querySelector("[data-generate]").disabled = false;
      }
    });
  }

  async function generate() {
    const chosen = dialog.querySelector("input[name=plate-report-template]:checked");
    if (!chosen) return;
    const button = dialog.querySelector("[data-generate]");
    button.disabled = true;
    showError(null);
    try {
      const report = await lumiereApi.request(chosen.value, { kind: "wafer", key: plate.lasermark });
      const list = dialog.querySelector(".js-reports");
      if (list.querySelector(".help")) list.innerHTML = "";
      list.insertAdjacentHTML("afterbegin", LumiereUI.rowHtml(report, { context: false }));
      watch(report.id);
    } catch (err) {
      showError(err);
      button.disabled = false;
    }
  }

  async function open() {
    if (!dialog) build();
    showError(null);
    dialog.showModal();
    try {
      await Promise.all([loadTemplates(), loadReports()]);
    } catch (err) {
      showError(err);
    }
  }

  function mount(passport) {
    plate = passport;
    const actions = document.querySelector(".plate-hero__actions");
    if (!actions || document.getElementById("plate-report")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-line";
    button.id = "plate-report";
    button.title = "Générer le rapport Lumière de cette plaque : un fichier HTML autonome (contexte, vie en ligne, données, images MEB)";
    button.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3v5h5"/><path d="M6 3h8l5 5v13H6z"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>Rapport`;
    button.addEventListener("click", open);
    const anchor = actions.querySelector(".js-db-link");
    actions.insertBefore(button, anchor);
  }

  return { mount, open };
})();
