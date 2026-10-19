/* « Rapport » sur la page de ce qu'un rapport décrit (plugin lumiere, global `LumiereReport`) : un bouton ouvre
   une fenêtre qui liste les modèles de rapport du contexte (lumiereApi.templates), lance la génération
   (lumiereApi.request : en tâche de fond, suivie ici jusqu'à « prêt ») et montre les rapports déjà générés pour ce
   contexte (télécharger, retirer).

     LumiereReport.mount(host, { kind, key, before })   // le bouton est posé dans (ou avant) `host`
     <span data-lumiere-report data-kind="lot" data-route="/lots/{code}" data-key="{code}"></span>
                                                         // monté tout seul au chargement : la clé se lit dans
                                                         // l'adresse de la page (routeParams)

   Dépend de lumiereApi, LumiereUI, escapeHtml, routeParams, pluginEnabled. */

const LumiereReport = (() => {
  const LABELS = { wafer: "Rapport de la plaque", analysis: "Rapport de l'analyse", study: "Rapport de l'étude", microproject: "Rapport du µprojet", lot: "Rapport du lot" };
  let dialog = null;
  let context = null; // {kind, key}
  let templates = [];
  let stopFollow = null;

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "wafer-dialog wafer-dialog--narrow lm-dialog";
    dialog.setAttribute("aria-labelledby", "lumiere-report-title");
    dialog.innerHTML = `
      <div class="card-pad wafer-dialog__inner">
        <h2 class="wafer-dialog__title" id="lumiere-report-title">Rapport</h2>
        <p class="help wafer-dialog__lead js-lead">Un fichier HTML autonome, généré par Lumière avec ce que Spectre sait : il s'ouvre hors ligne, se transmet tel quel et s'imprime.</p>
        <div class="error" role="alert" hidden></div>
        <div class="lm-templates js-templates"></div>
        <h3 class="lm-subtitle">Rapports déjà générés</h3>
        <ul class="lm-reports js-reports"><li class="help">Chargement…</li></ul>
        <div class="wafer-dialog__actions">
          <a class="btn btn-line" href="/lumiere">Tous les rapports et les modèles</a>
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
    if (!templates.length) return `<p class="help">Aucun modèle de rapport pour ce contexte. <a href="/lumiere">En composer un</a>.</p>`;
    return templates
      .map(
        (t, i) => `<label class="lm-template">
          <input type="radio" name="lumiere-report-template" value="${escapeHtml(t.key)}" ${i === 0 ? "checked" : ""}>
          <span class="lm-template__body">
            <span class="lm-template__name">${escapeHtml(t.name)}${t.builtin ? "" : ` <span class="help" style="display:inline;margin:0;">· ${escapeHtml(t.owner_name || "")}</span>`}</span>
            <span class="lm-template__desc">${escapeHtml(t.description)}</span>
            <span class="lm-template__slides">${t.outline.map((s) => `<span>${escapeHtml(s)}</span>`).join("")}</span>
          </span>
        </label>`
      )
      .join("");
  }

  async function loadTemplates() {
    templates = (await lumiereApi.templates(context.kind)).templates;
    dialog.querySelector(".js-templates").innerHTML = templatesHtml();
    dialog.querySelector("[data-generate]").disabled = !templates.length;
  }

  async function loadReports() {
    const { reports } = await lumiereApi.list({ kind: context.kind, key: context.key });
    const list = dialog.querySelector(".js-reports");
    list.innerHTML = reports.length ? reports.map((r) => LumiereUI.rowHtml(r, { context: false })).join("") : `<li class="help">Aucun rapport encore.</li>`;
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
    const chosen = dialog.querySelector("input[name=lumiere-report-template]:checked");
    if (!chosen) return;
    const button = dialog.querySelector("[data-generate]");
    button.disabled = true;
    showError(null);
    try {
      const report = await lumiereApi.request(chosen.value, context);
      const list = dialog.querySelector(".js-reports");
      if (list.querySelector(".help")) list.innerHTML = "";
      list.insertAdjacentHTML("afterbegin", LumiereUI.rowHtml(report, { context: false }));
      watch(report.id);
    } catch (err) {
      showError(err);
      button.disabled = false;
    }
  }

  async function open(ctx) {
    context = ctx;
    if (!dialog) build();
    dialog.querySelector("#lumiere-report-title").textContent = LABELS[ctx.kind] || "Rapport";
    showError(null);
    dialog.showModal();
    try {
      await Promise.all([loadTemplates(), loadReports()]);
    } catch (err) {
      showError(err);
    }
  }

  // host : l'élément qui reçoit le bouton (remplacé s'il porte data-lumiere-report, sinon le bouton y est ajouté,
  // ou inséré devant lui avec `before`)
  function mount(host, { kind, key, before = false, primary = false } = {}) {
    if (!host || !kind || !key || document.getElementById(`lumiere-report-${kind}`)) return null;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `btn ${primary ? "btn-primary" : "btn-line"}`;
    button.id = `lumiere-report-${kind}`;
    button.title = "Générer un rapport Lumière : un fichier HTML autonome, à partir d'un modèle de rapport";
    button.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3v5h5"/><path d="M6 3h8l5 5v13H6z"/><path d="M9 13h6"/><path d="M9 17h6"/></svg>Rapport`;
    button.addEventListener("click", () => open({ kind, key }));
    if (host.hasAttribute("data-lumiere-report")) host.replaceWith(button);
    else if (before) host.parentNode.insertBefore(button, host);
    else host.appendChild(button);
    return button;
  }

  // les emplacements déclarés dans la page : la clé se lit dans l'adresse
  function mountDeclared() {
    if (typeof pluginEnabled === "function" && !pluginEnabled("lumiere")) return;
    document.querySelectorAll("[data-lumiere-report]").forEach((host) => {
      const params = host.dataset.route ? routeParams(host.dataset.route) : {};
      const key = (host.dataset.key || "").replace(/\{(\w+)\}/g, (_, name) => params[name] || "");
      if (!key || key.includes("{")) return;
      mount(host, { kind: host.dataset.kind, key: decodeURIComponent(key), primary: host.dataset.primary === "true" });
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountDeclared);
  else mountDeclared();

  return { mount, open };
})();
