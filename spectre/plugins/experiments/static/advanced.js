/* « Actions avancées », pour un éditeur sur la dernière version : combiner une autre étude du µprojet
   dans celle-ci (sa structure reste, l'historique et le cahier de données de l'autre la rejoignent) et
   supprimer la piste. Les préconditions sont celles du serveur : un refus (409 : une autre piste en
   découle...) s'affiche tel quel. */

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

  document.getElementById("combine-btn").addEventListener("click", () => {
    if (!select.value) return ctx.showError(new Error("Choisissez l'expérience à combiner avec celle-ci."));
    const other = select.value;
    ctx.write(() => experimentsApi.merge(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, other));
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
