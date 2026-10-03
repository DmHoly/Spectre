/* Le pied du bandeau : les étiquettes de l'étude (ajouter, retirer - une écriture sur la piste) et
   ses refs, les noms donnés à la version affichée (une ref ne crée pas de version). */

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

  function renderRefs(ctx) {
    const row = document.getElementById("refs-row");
    row.innerHTML =
      ctx.detail.ref_names.map((name) => `<span class="badge badge-role" title="Ref">ref ${escapeHtml(name)}</span>`).join("") +
      (ctx.canEdit
        ? `<button id="make-ref-btn" data-report-hide type="button" class="btn btn-line" style="padding:2px 10px;font-size:11.5px;">+ ref</button>
           <input id="new-ref-input" data-report-hide placeholder="surnom (optionnel)" aria-label="Nom de la ref" hidden style="${chipInputStyle}width:150px;">`
        : "");
    const makeBtn = document.getElementById("make-ref-btn");
    const input = document.getElementById("new-ref-input");
    if (!makeBtn) return;
    makeBtn.addEventListener("click", () => {
      makeBtn.style.display = "none";
      input.hidden = false;
      input.focus();
    });
    input.addEventListener("keydown", async (event) => {
      if (event.key !== "Enter") return;
      event.preventDefault();
      try {
        const ref = await experimentsApi.createRef(ctx.microprojectSlug, {
          experiment_id: ctx.experimentId,
          version_id: ctx.versionId,
          name: input.value.trim() || null,
        });
        ctx.detail.ref_names = ref.names;
        renderRefs(ctx);
      } catch (err) {
        ctx.showError(err);
      }
    });
  }

  ExperiencePage.registerPanel({
    key: "tags-refs",
    mount(el, ctx) {
      renderTags(ctx);
      renderRefs(ctx);
    },
  });
})();
