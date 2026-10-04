/* « Actions avancées », pour un éditeur sur la dernière version : combiner cette étude et une autre du
   µprojet en une nouvelle étude (POST /experiments avec merge_of : la structure de celle-ci, un titre,
   une intention et une nouvelle plaque ; les deux études ne changent pas) et supprimer la piste. Les
   préconditions sont celles du serveur : un refus (409 : une autre piste en découle...) s'affiche tel
   quel. */

(() => {
  let ctx = null;
  const search = document.getElementById("combine-search");
  const select = document.getElementById("combine-select");

  async function fillSelect() {
    try {
      const items = await ExperiencePage.otherExperiments(ctx.microprojectSlug, search.value.trim());
      select.innerHTML = items.length
        ? items.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)}</option>`).join("")
        : `<option value="">Aucune autre expérience à combiner</option>`;
    } catch (err) {
      select.innerHTML = `<option value="">—</option>`;
    }
  }

  let searchTimer = null;
  search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fillSelect, 250);
  });

  const combineBtn = document.getElementById("combine-btn");
  combineBtn.addEventListener("click", async () => {
    if (!select.value) return ctx.showError(new Error("Choisissez l'expérience à combiner avec celle-ci."));
    const body = {
      merge_of: [{ experiment_id: ctx.experimentId, version_id: ctx.versionId }, { experiment_id: select.value }],
      title: document.getElementById("combine-title").value.trim(),
      intent: document.getElementById("combine-intent").value.trim(),
      entities: [{ sample_id: document.getElementById("combine-wafer").value.trim() || null }],
    };
    combineBtn.disabled = true;
    try {
      const created = await experimentsApi.create(ctx.microprojectSlug, body);
      window.location.href = `/microprojets/${encodeURIComponent(ctx.microprojectSlug)}/experiences/${encodeURIComponent(created.id)}`;
    } catch (err) {
      ctx.showError(err);
      combineBtn.disabled = false;
    }
  });

  const deleteBtn = document.getElementById("delete-experience-btn");
  deleteBtn.addEventListener("click", async () => {
    if (!window.confirm(`Supprimer définitivement « ${ctx.detail.title} » (toutes les versions de cette piste) ? Cette action est irréversible.`)) return;
    deleteBtn.disabled = true;
    try {
      await experimentsApi.remove(ctx.microprojectSlug, ctx.experimentId, ctx.versionId);
      window.location.href = `/microprojets/${encodeURIComponent(ctx.microprojectSlug)}`;
    } catch (err) {
      ctx.showError(err);
      deleteBtn.disabled = false;
    }
  });

  ExperiencePage.registerPanel({
    key: "advanced",
    mount(el, context) {
      ctx = context;
      el.hidden = !ctx.canEdit;
      if (ctx.canEdit) return fillSelect();
    },
  });
})();
