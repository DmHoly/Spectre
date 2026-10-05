/* Le pied du bandeau : les étiquettes de l'étude (ajouter, retirer - une écriture sur la piste),
   la référence dont elle part (« Issue de la référence X 1.1 »), ses refs locales (des repères du
   µprojet sur la version affichée) et « Publier comme référence » (references/static/publish-dialog.js). */

(() => {
  const chipInputStyle = "border:1px dashed var(--border-soft);border-radius:999px;padding:4px 10px;font-size:12px;background:transparent;";

  async function saveTags(ctx, tags) {
    const done = await ctx.write(() => experimentsApi.setTags(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, { tags }));
    if (done) document.getElementById("new-tag-input")?.focus(); // pour en enchaîner une autre
  }

  function renderTags(ctx) {
    const row = document.getElementById("tags-row");
    const tags = ctx.detail.tags;
    row.innerHTML =
      tags
        .map(
          (t, i) => `
        <span class="badge badge-role">
          ${escapeHtml(t)}
          ${
            ctx.canEdit
              ? `<button class="js-remove-tag" data-index="${i}" type="button" data-report-hide aria-label="Retirer l'étiquette ${escapeHtml(t)}" style="background:none;border:none;cursor:pointer;color:inherit;padding:0;margin-left:2px;font-size:13px;line-height:1;">&times;</button>`
              : ""
          }
        </span>`
        )
        .join("") +
      (ctx.canEdit ? `<input id="new-tag-input" data-report-hide placeholder="+ étiquette" aria-label="Ajouter une étiquette" style="${chipInputStyle}width:110px;">` : "");

    row.querySelectorAll(".js-remove-tag").forEach((btn) => {
      btn.addEventListener("click", () => saveTags(ctx, tags.filter((_, i) => i !== Number(btn.dataset.index))));
    });
    const input = document.getElementById("new-tag-input");
    if (input) {
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && input.value.trim()) {
          event.preventDefault();
          saveTags(ctx, [...tags, input.value.trim()]);
        }
      });
    }
  }

  // Une structure dessinée dans le constructeur (ni des images, ni une campagne) : la seule qui se
  // publie comme référence.
  const isDrawnProcess = (detail) => detail.has_editable_process && !detail.is_batch && !(detail.structure_images || []).length;

  // L'origine de l'étude, « Issue de la référence X 1.1 » (un lien vers la page de la référence) :
  // le nom se lit dans referencesApi.versions ; une référence retirée, ou une version qu'elle n'a
  // pas, se dit « inconnue ».
  async function renderOrigin(ctx, box) {
    const origin = ctx.detail.reference_origin;
    if (!origin) return;
    const text = (name, known) =>
      known
        ? `<a href="/references/${encodeURIComponent(origin.reference)}?version=${encodeURIComponent(origin.version)}">${escapeHtml(name)} ${escapeHtml(origin.version)}</a>`
        : `${escapeHtml(origin.reference)} ${escapeHtml(origin.version)} (référence inconnue)`;
    box.innerHTML = `<span class="ref-origin">Issue de la référence ${text(origin.reference, true)}</span>`;
    try {
      const graph = await referencesApi.versions(origin.reference);
      const known = graph.nodes.some((node) => node.number === origin.version);
      box.innerHTML = `<span class="ref-origin">Issue de la référence ${text(graph.reference.name, known)}</span>`;
    } catch (err) {
      if (err.status !== 404) return; // le lien reste, avec le slug pour nom
      box.innerHTML = `<span class="ref-origin">Issue de la référence ${text(origin.reference, false)}</span>`;
    }
  }

  function renderRefs(ctx) {
    const row = document.getElementById("refs-row");
    const evolutionUrl = `/microprojets/${encodeURIComponent(ctx.microprojectSlug)}/evolution`;
    const canPublish = ctx.canEdit && isDrawnProcess(ctx.detail);
    row.innerHTML =
      `<span id="reference-origin"></span>` +
      ctx.detail.ref_names.map((name) => `<span class="badge badge-role" title="Ref locale du µprojet">ref ${escapeHtml(name)}</span>`).join("") +
      (canPublish
        ? `<button id="publish-reference-btn" data-report-hide type="button" class="btn btn-line" style="padding:2px 10px;font-size:11.5px;" title="Partager cette structure avec tous les µprojets, comme nouvelle version d'une référence">Publier comme référence</button>`
        : "") +
      `<a class="btn btn-line" data-report-hide href="${evolutionUrl}" style="padding:2px 10px;font-size:11.5px;" title="Les pistes du µprojet, leurs versions, leurs refs et leurs versions de référence">Évolution des structures</a>`;
    renderOrigin(ctx, document.getElementById("reference-origin"));
    const publish = document.getElementById("publish-reference-btn");
    if (!publish) return;
    publish.addEventListener("click", () =>
      ReferencePublishDialog.open({
        microprojectSlug: ctx.microprojectSlug,
        experimentId: ctx.experimentId,
        versionId: ctx.versionId,
        origin: ctx.detail.reference_origin,
      })
    );
  }

  ExperiencePage.registerPanel({
    key: "tags-refs",
    mount(el, ctx) {
      renderTags(ctx);
      renderRefs(ctx);
    },
  });
})();
