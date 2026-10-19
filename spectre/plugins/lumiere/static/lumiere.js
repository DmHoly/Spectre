/* La page « Rapports » (/lumiere) : les rapports générés par Lumière - les vôtres, tous pour un administrateur -
   avec leur état, à télécharger ou à retirer, et les modèles disponibles (pour l'instant, un rapport se lance
   depuis la page de son contexte : la page d'une plaque). Un rapport en cours est suivi jusqu'à « prêt ».
   Dépend de lumiereApi, LumiereUI, accountsApi, escapeHtml. */

(function () {
  const list = document.getElementById("lm-list");
  const templatesBox = document.getElementById("lm-templates");
  const errorBox = document.getElementById("error");
  const refresh = document.getElementById("lm-refresh");
  const storageBox = document.getElementById("lm-storage");
  let stopFollow = null;

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }

  function contextLink(report) {
    if (report.context.kind === "wafer") return `<a class="fiche-code mono" href="/plaques/${encodeURIComponent(report.context.key)}">${escapeHtml(report.context.key)}</a>`;
    return escapeHtml(report.context.key);
  }

  function rowHtml(report) {
    return LumiereUI.rowHtml(report).replace(
      '<div class="lm-report__meta">',
      `<div class="lm-report__meta">${contextLink(report)} · `
    );
  }

  async function load() {
    try {
      const [{ reports }, { templates, contexts }] = await Promise.all([lumiereApi.list(), lumiereApi.templates()]);
      list.innerHTML = reports.length ? reports.map(rowHtml).join("") : `<li class="help">Aucun rapport généré pour l'instant. Le bouton « Rapport » de la page d'une plaque en lance un.</li>`;
      templatesBox.innerHTML = templates
        .map(
          (t) => `<div class="card card-pad lm-template-card">
            <div class="lm-template__name">${escapeHtml(t.name)} <span class="help" style="display:inline;margin:0;">· ${escapeHtml(contexts[t.context] || t.context)}</span></div>
            <p class="help" style="margin:4px 0 6px;">${escapeHtml(t.description)}</p>
            <div class="lm-template__slides">${t.slides.map((s) => `<span>${escapeHtml(s)}</span>`).join("")}</div>
          </div>`
        )
        .join("");
      const busy = reports.find((r) => r.status === "queued" || r.status === "running");
      if (busy) watch(busy.id);
      showError(null);
    } catch (err) {
      showError(err);
    }
  }

  function watch(id) {
    if (stopFollow) stopFollow();
    stopFollow = LumiereUI.follow(id, (report) => {
      const row = list.querySelector(`[data-report="${report.id}"]`);
      if (row) row.outerHTML = rowHtml(report);
      if (report.status !== "queued" && report.status !== "running") {
        stopFollow = null;
        loadStorage();
      }
    });
  }

  async function loadStorage() {
    try {
      const me = await accountsApi.me();
      if (!me.is_admin) return;
      const s = await lumiereApi.storage();
      storageBox.hidden = false;
      storageBox.textContent = `${s.reports} rapport${s.reports > 1 ? "s" : ""} gardé${s.reports > 1 ? "s" : ""} · ${LumiereUI.weight(s.bytes) || "0 Ko"}${s.running ? ` · ${s.running} en cours` : ""}`;
    } catch (err) {
      storageBox.hidden = true;
    }
  }

  list.addEventListener("click", async (event) => {
    const remove = event.target.closest("[data-remove]");
    if (!remove) return;
    remove.disabled = true;
    try {
      await lumiereApi.remove(remove.dataset.remove);
      await load();
      loadStorage();
    } catch (err) {
      showError(err);
    }
  });
  refresh.addEventListener("click", load);

  load();
  loadStorage();
})();
