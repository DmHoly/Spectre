/* Le pied du bandeau : les étiquettes de l'étude (ajouter, retirer - une écriture sur la piste),
   la référence dont elle part (« Issue de la référence X 1.1 »), l'étude d'où viennent ses plaques
   (« Plaques reprises de Y », pour une étude partie de plaques existantes). « Promouvoir comme référence » est en tête
   de fiche (plugin promotion). */

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

  // L'origine de l'étude, « Issue de la référence X 1.1 » (un lien vers la page de la référence) :
  // le nom se lit dans referencesApi.versions ; une référence retirée, ou une version qu'elle n'a
  // pas, se dit « inconnue ».
  async function renderOrigin(ctx, box) {
    const origin = ctx.detail.reference_origin;
    if (!origin) return;
    if (!pluginEnabled("references")) {
      // plugin désactivé : l'origine se dit, sans lien ni lecture du nom
      box.innerHTML = `<span class="ref-origin">Issue de la référence ${escapeHtml(origin.reference)} ${escapeHtml(origin.version)}</span>`;
      return;
    }
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

  // Une étude partie de plaques existantes : « Plaques reprises de X » (un lien vers l'étude qui les
  // suivait, sa variante pour une campagne). Son titre se lit chez elle - hors de son µprojet (403),
  // seul son µprojet se dit.
  async function renderWaferOrigin(ctx, box) {
    const origin = ctx.detail.wafer_origin;
    if (!origin) return;
    const elsewhere = origin.microproject !== ctx.microprojectSlug;
    const say = (inner) => (box.innerHTML = `<span class="ref-origin">Plaques reprises de ${inner}</span>`);
    say(`l'étude d'origine${elsewhere ? ` du µprojet ${escapeHtml(origin.microproject)}` : ""}`);
    try {
      const source = await experimentsApi.getVersion(origin.microproject, origin.experiment_id, origin.version_id);
      const url = `/microprojets/${encodeURIComponent(origin.microproject)}/experiences/${encodeURIComponent(origin.experiment_id)}`;
      let variant = "";
      if (origin.variant !== null && source.is_batch) {
        const labels = ((await experimentsApi.variants(origin.microproject, origin.experiment_id, origin.version_id).catch(() => null)) || {}).labels || [];
        variant = ` (variante ${escapeHtml(labels[origin.variant] || `n° ${origin.variant + 1}`)})`;
      }
      let where = "";
      if (elsewhere) {
        const mp = await microprojectsApi.get(origin.microproject).catch(() => null);
        where = ` · µprojet ${escapeHtml(mp ? mp.code || mp.name : origin.microproject)}`;
      }
      say(`<a href="${url}">${escapeHtml(source.title)}</a>${variant}${where}`);
    } catch (err) {
      // pas membre de ce µprojet, ou étude supprimée : le texte d'attente reste
    }
  }

  // Partie de la meilleure plaque d'une étude : « Depuis la plaque W07 de X » ; combinée au marché :
  // d'où vient chaque brique (« EBL ← B · W03 »), les études sources en liens.
  async function renderStartOrigin(ctx, box) {
    const start = ctx.detail.start_wafer;
    const composition = ctx.detail.composition;
    const studyUrl = (id, version) =>
      `/microprojets/${encodeURIComponent(ctx.microprojectSlug)}/experiences/${encodeURIComponent(id)}${version ? `?version=${encodeURIComponent(version)}` : ""}`;
    if (start) {
      const mark = start.sample_id ? `<span class="mono">${escapeHtml(start.sample_id)}</span>` : `n° ${start.place + 1}`;
      const say = (title) => (box.innerHTML = `<span class="ref-origin">Depuis la plaque ${mark} de <a href="${studyUrl(start.experiment_id, start.version_id)}">${escapeHtml(title)}</a></span>`);
      say(start.experiment_id);
      const source = await experimentsApi.getVersion(ctx.microprojectSlug, start.experiment_id, start.version_id).catch(() => null);
      if (source) say(source.title);
      return;
    }
    if (!composition) return;
    const label = (source) =>
      source.kind === "study"
        ? `<a href="${studyUrl(source.experiment_id, source.version_id)}">${escapeHtml(source.label)}</a>`
        : pluginEnabled("references")
          ? `<a href="/references/${encodeURIComponent(source.reference)}?version=${encodeURIComponent(source.version)}">${escapeHtml(source.label)}</a>`
          : escapeHtml(source.label);
    // la principale, puis ce qui vient d'ailleurs (le détail de chaque brique en infobulle)
    const main = composition.sources[0];
    const items = composition.steps && composition.steps.length ? composition.steps : composition.bricks;
    const replacedNames = new Set(items.map((item) => item.replaces).filter(Boolean));
    const picks = items
      .filter((item) => !(item.source === null && replacedNames.has(item.name)))
      .filter((item) => item.source !== 0 && (item.source === null || composition.sources[item.source]))
      .map((item) =>
        item.source === null
          ? `sans ${escapeHtml(item.name)}`
          : item.replaces
            ? `${escapeHtml(item.name)} (${label(composition.sources[item.source])}) remplace ${escapeHtml(item.replaces)}`
            : `${escapeHtml(item.name)} ← ${label(composition.sources[item.source])}`
      );
    const detail = items
      .map((item) => `${item.brick ? `${item.brick} › ` : ""}${item.name} : ${item.source === null ? "non reprise" : (composition.sources[item.source] || {}).label || "?"}${item.replaces ? ` (remplace ${item.replaces})` : ""}`)
      .join("\n");
    box.innerHTML = `<span class="ref-origin" title="${escapeHtml(`Combinée au marché - la source de chaque étape :\n${detail}`)}">Combinaison : ${label(main)}${picks.length ? `, avec ${picks.join(" · ")}` : ""}</span>`;
  }

  function renderRefs(ctx) {
    const row = document.getElementById("refs-row");
    const evolutionUrl = `/microprojets/${encodeURIComponent(ctx.microprojectSlug)}/evolution`;
    // « Promouvoir comme référence » est en tête de fiche (plugin promotion : promotion/static/fiche.js)
    row.innerHTML =
      `<span id="reference-origin"></span>` +
      `<span id="wafer-origin"></span>` +
      `<span id="start-origin"></span>` +
      `<a class="btn btn-line" data-report-hide href="${evolutionUrl}" style="padding:2px 10px;font-size:11.5px;" title="Les pistes du µprojet, leurs versions et leurs versions de référence">Évolution des structures</a>`;
    renderOrigin(ctx, document.getElementById("reference-origin"));
    renderWaferOrigin(ctx, document.getElementById("wafer-origin"));
    renderStartOrigin(ctx, document.getElementById("start-origin"));
  }

  ExperiencePage.registerPanel({
    key: "tags-refs",
    mount(el, ctx) {
      renderTags(ctx);
      renderRefs(ctx);
    },
  });
})();
