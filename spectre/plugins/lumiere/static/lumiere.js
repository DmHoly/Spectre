/* La page « Rapports » (/lumiere) : les rapports générés par Lumière - les vôtres, tous pour un administrateur -
   avec leur état, à télécharger ou à retirer ; les modèles de rapport (livrés et enregistrés), à copier, modifier
   (son auteur, un administrateur) ou retirer, et l'éditeur slide par slide (editor.js). Un rapport se lance depuis
   la page de son contexte (la page d'une plaque). Un rapport en cours est suivi jusqu'à « prêt ».
   Dépend de lumiereApi, LumiereUI, LumiereEditor, accountsApi, escapeHtml, formatDate. */

(function () {
  const list = document.getElementById("lm-list");
  const templatesBox = document.getElementById("lm-templates");
  const errorBox = document.getElementById("error");
  const refresh = document.getElementById("lm-refresh");
  const storageBox = document.getElementById("lm-storage");
  const editorHost = document.getElementById("lm-editor");
  let stopFollow = null;
  let me = null;

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }

  function contextLink(report) {
    if (report.context.kind === "wafer") return `<a class="fiche-code mono" href="/plaques/${encodeURIComponent(report.context.key)}">${escapeHtml(report.context.key)}</a>`;
    return escapeHtml(report.context.key);
  }

  function rowHtml(report) {
    return LumiereUI.rowHtml(report).replace('<div class="lm-report__meta">', `<div class="lm-report__meta">${contextLink(report)} · `);
  }

  function canEdit(t) {
    return !t.builtin && me && (me.is_admin || t.owner_id === me.id);
  }

  function templateCard(t, contexts) {
    const who = t.builtin ? "livré avec Spectre" : `par ${escapeHtml(t.owner_name || "?")}${t.updated_at ? ` · ${escapeHtml(formatDate(t.updated_at))}` : ""}`;
    return `<div class="card card-pad lm-template-card" data-template="${escapeHtml(t.key)}">
      <div class="lm-template__name">${escapeHtml(t.name)} <span class="help" style="display:inline;margin:0;">· ${escapeHtml(contexts[t.context] || t.context)}</span></div>
      <p class="help" style="margin:2px 0 6px;">${escapeHtml(t.description || "")}</p>
      <div class="lm-template__slides">${t.outline.map((s) => `<span>${escapeHtml(s)}</span>`).join("")}</div>
      <div class="lm-template-card__foot">
        <span class="help" style="margin:0;">${who}</span>
        <span class="lm-template-card__actions">
          ${canEdit(t) ? `<button type="button" class="btn btn-line" data-edit="${escapeHtml(t.key)}">Modifier</button>` : `<button type="button" class="btn btn-line" data-view="${escapeHtml(t.key)}">Voir</button>`}
          <button type="button" class="btn btn-line" data-copy="${escapeHtml(t.key)}" title="Un nouveau modèle, à partir de celui-ci">Copier</button>
          ${canEdit(t) ? `<button type="button" class="btn btn-line" data-remove-template="${escapeHtml(t.key)}">Retirer</button>` : ""}
        </span>
      </div>
    </div>`;
  }

  async function load() {
    try {
      if (!me) me = await accountsApi.me().catch(() => null);
      const [{ reports }, { templates, contexts }] = await Promise.all([lumiereApi.list(), lumiereApi.templates()]);
      list.innerHTML = reports.length ? reports.map(rowHtml).join("") : `<li class="help">Aucun rapport généré pour l'instant. Le bouton « Rapport » de la page d'une plaque en lance un.</li>`;
      templatesBox.innerHTML = templates.map((t) => templateCard(t, contexts)).join("");
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
      if (!me) me = await accountsApi.me();
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

  templatesBox.addEventListener("click", async (event) => {
    const t = event.target;
    try {
      const edit = t.closest("[data-edit], [data-view]");
      if (edit) return LumiereEditor.open(await lumiereApi.template(edit.dataset.edit || edit.dataset.view));
      const copy = t.closest("[data-copy]");
      if (copy) return LumiereEditor.create({ copyOf: copy.dataset.copy });
      const remove = t.closest("[data-remove-template]");
      if (remove) {
        if (!window.confirm("Retirer ce modèle de rapport ?")) return;
        await lumiereApi.removeTemplate(remove.dataset.removeTemplate);
        await load();
      }
    } catch (err) {
      showError(err);
    }
  });
  document.getElementById("lm-new-template").addEventListener("click", () => LumiereEditor.create({ context: "wafer" }).catch(showError));
  refresh.addEventListener("click", load);

  LumiereEditor.mount(editorHost, { onSaved: () => load() });
  load();
  loadStorage();
})();
