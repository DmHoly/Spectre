/* « Actions avancées », pour un éditeur sur la dernière version : combiner cette étude et une autre du
   µprojet, et supprimer la piste. Les préconditions sont celles du serveur : un refus (409 : une
   autre piste en découle ; 422 : deux types de structure...) s'affiche tel quel.

   « Combiner… » ouvre #combine-dialog : l'autre étude (recherche parmi celles du µprojet), le titre
   (proposé « A + B » tant qu'on ne l'a pas changé), l'intention, l'hypothèse et la nouvelle plaque
   (lasermark, emplacement, FDL : les champs d'un lancement, avec l'autocomplétion du µprojet). Puis
   POST /experiments avec merge_of (celle-ci à la version affichée, l'autre à sa pointe) : une
   nouvelle étude issue des deux, avec la structure de celle-ci ; les deux ne changent pas, son
   cahier démarre vide. Créée, sa fiche s'ouvre. */

(() => {
  let ctx = null;
  const $ = (id) => document.getElementById(id);
  const dialog = $("combine-dialog");
  const form = $("combine-form");
  const search = $("combine-search");
  const select = $("combine-select");
  const searchState = $("combine-search-state");
  const titleInput = $("combine-title");
  const errorBox = $("combine-error");
  const submitBtn = $("combine-submit");
  const fdlField = mountFdlField($("combine-fdl"), { datalistId: "entity-fdl-history", label: "FDL de la nouvelle plaque" });
  $("combine-fdl").querySelector(".fdl-field__input").id = "combine-fdl-input";

  let others = []; // les études trouvées par la recherche
  let proposedTitle = ""; // le titre proposé (« A + B ») : il suit le choix tant qu'on ne l'a pas changé

  function showError(err) {
    errorBox.textContent = (err && err.message) || String(err);
    errorBox.style.display = "block";
    errorBox.scrollIntoView({ block: "nearest" });
  }

  function hideError() {
    errorBox.style.display = "none";
  }

  function proposeTitle() {
    const other = others.find((item) => item.id === select.value);
    const next = other ? `${ctx.detail.title} + ${other.title}` : "";
    if (!titleInput.value.trim() || titleInput.value === proposedTitle) titleInput.value = next.slice(0, 200);
    proposedTitle = next.slice(0, 200);
  }

  let searches = 0;
  async function fillSelect() {
    const seq = (searches += 1);
    const q = search.value.trim();
    searchState.textContent = "Recherche…";
    try {
      const items = await ExperiencePage.otherExperiments(ctx.microprojectSlug, q);
      if (seq !== searches) return;
      const kept = select.value;
      others = items;
      select.innerHTML = items.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title)} · ${escapeHtml(item.id)}</option>`).join("");
      if (items.some((item) => item.id === kept)) select.value = kept;
      else if (items.length) select.selectedIndex = 0;
      searchState.textContent = items.length
        ? `${items.length} étude${items.length > 1 ? "s" : ""}${q ? ` pour « ${q} »` : " du µprojet"}`
        : q
          ? `Aucune autre étude pour « ${q} ».`
          : "Aucune autre étude dans ce µprojet.";
    } catch (err) {
      if (seq !== searches) return;
      others = [];
      select.innerHTML = "";
      searchState.textContent = err.message || String(err);
    }
    proposeTitle();
  }

  let searchTimer = null;
  search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(fillSelect, 250);
  });
  select.addEventListener("change", proposeTitle);

  function open() {
    hideError();
    form.reset();
    fdlField.set([]);
    proposedTitle = "";
    submitBtn.disabled = false;
    $("combine-first-title").textContent = `« ${ctx.detail.title} » (cette fiche)`;
    $("combine-plate-help").textContent = ctx.detail.is_batch
      ? "La plaque de la première variante de la campagne ; les autres se renseignent ensuite dans « Plaques & entités physiques »."
      : "Chaque étude est reliée à un échantillon réel : c'est cet identifiant qui permet de la retrouver.";
    dialog.showModal();
    search.focus();
    fillSelect();
  }

  function body() {
    const required = (input, message) => {
      if (input.value.trim()) return input.value.trim();
      input.focus();
      throw new Error(message);
    };
    if (!select.value) {
      search.focus();
      throw new Error("Choisissez l'étude à combiner avec celle-ci.");
    }
    const title = required(titleInput, "Donnez un titre à la nouvelle étude.");
    const intent = required($("combine-intent"), "Dites ce que la nouvelle étude veut démontrer.");
    const sampleId = required($("combine-sample-id"), "La nouvelle plaque est obligatoire : indiquez son lasermark.");
    return {
      merge_of: [{ experiment_id: ctx.experimentId, version_id: ctx.versionId }, { experiment_id: select.value }],
      title,
      intent,
      hypothesis: $("combine-hypothesis").value.trim() || null,
      entities: [{ sample_id: sampleId, location: $("combine-location").value.trim() || null, fdl: fdlField.get() }],
    };
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault(); // method="dialog" fermerait la boîte
    hideError();
    let payload;
    try {
      payload = body();
    } catch (err) {
      showError(err);
      return;
    }
    submitBtn.disabled = true;
    try {
      const created = await experimentsApi.create(ctx.microprojectSlug, payload);
      window.location.href = ExperiencePage.pageUrl({ experiment_id: created.id, is_tip: true });
    } catch (err) {
      showError(err);
      submitBtn.disabled = false;
    }
  });
  $("combine-cancel").addEventListener("click", () => dialog.close());
  $("combine-open-btn").addEventListener("click", open);

  const deleteBtn = $("delete-experience-btn");
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
      if (!ctx.canEdit && dialog.open) dialog.close();
    },
  });
})();
