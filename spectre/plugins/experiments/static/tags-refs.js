/* Le pied du bandeau : les étiquettes de l'étude (ajouter, retirer - une écriture sur la piste),
   la référence qu'elle suit et celle dont elle part (« Issue de la référence X 1.1 », ou
   « Référence : Y 1.0 · issue de X 1.1 » quand elle en suit une autre ; « Suivre une autre
   référence » : un petit dialogue, pour cette piste ou toute sa branche), l'étude d'où viennent ses plaques
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

  // Une version de référence citée, « X 1.1 » (un lien vers la page de la référence) : le nom se
  // lit dans referencesApi.versions ; une référence retirée, ou une version qu'elle n'a pas, se dit
  // « inconnue ». Rendu deux fois : le slug d'abord, le nom dès qu'il est lu.
  function citedHtml(cited, name, known) {
    if (!pluginEnabled("references")) return `${escapeHtml(cited.reference)} ${escapeHtml(cited.version)}`;
    return known
      ? `<a href="/references/${encodeURIComponent(cited.reference)}?version=${encodeURIComponent(cited.version)}">${escapeHtml(name)} ${escapeHtml(cited.version)}</a>`
      : `${escapeHtml(cited.reference)} ${escapeHtml(cited.version)} (référence inconnue)`;
  }

  async function resolveCited(cited) {
    if (!cited || !pluginEnabled("references")) return { name: cited ? cited.reference : "", known: true };
    try {
      const graph = await referencesApi.versions(cited.reference);
      return { name: graph.reference.name, known: graph.nodes.some((node) => node.number === cited.version) };
    } catch (err) {
      return { name: cited.reference, known: err.status !== 404 };
    }
  }

  const sameRef = (a, b) => Boolean(a && b) && a.reference === b.reference && a.version === b.version;

  // La référence de l'étude : « Issue de la référence X 1.1 » tant qu'elle suit son origine ;
  // « Référence : Y 1.0 · issue de X 1.1 » quand elle en a choisi une autre après coup (le plugin
  // promotion, ou « Suivre une autre référence » ici). L'origine reste l'histoire.
  async function renderOrigin(ctx, box) {
    const origin = ctx.detail.reference_origin;
    const followed = ctx.detail.reference_followed;
    const changeLink =
      ctx.canEdit && pluginEnabled("references")
        ? ` <button type="button" class="js-follow-reference" data-report-hide style="background:none;border:none;padding:0;cursor:pointer;color:var(--accent-dark);font:inherit;font-size:inherit;text-decoration:underline;">${followed ? "Suivre une autre référence" : "Suivre une référence"}</button>`
        : "";
    if (!origin && !followed) {
      box.innerHTML = changeLink ? `<span class="ref-origin">${changeLink.trim()}</span>` : "";
      bindFollow(ctx, box);
      return;
    }
    const say = (originName, originKnown, followedName, followedKnown) => {
      let text;
      if (!followed || sameRef(followed, origin)) text = `Issue de la référence ${citedHtml(origin, originName, originKnown)}`;
      else if (!origin) text = `Référence : ${citedHtml(followed, followedName, followedKnown)}`;
      else text = `Référence : ${citedHtml(followed, followedName, followedKnown)} · issue de ${citedHtml(origin, originName, originKnown)}`;
      box.innerHTML = `<span class="ref-origin">${text}${changeLink}</span>`;
      bindFollow(ctx, box);
    };
    say(origin && origin.reference, true, followed && followed.reference, true);
    const [o, f] = await Promise.all([resolveCited(origin), resolveCited(followed)]);
    say(o.name, o.known, f.name, f.known);
  }

  function bindFollow(ctx, box) {
    box.querySelector(".js-follow-reference")?.addEventListener("click", () => openFollowDialog(ctx));
  }

  // Le dialogue « Suivre une autre référence » : une référence existante, une de ses versions, la
  // portée (cette étude, ou toute sa branche). Une retouche de la piste, enregistrée par le plugin
  // experiments (PUT .../reference) ; choisir une *nouvelle* référence reste le fait de la promotion.
  let followDialog = null;

  function ensureFollowDialog() {
    if (followDialog) return followDialog;
    followDialog = document.createElement("dialog");
    followDialog.id = "follow-reference-dialog";
    followDialog.setAttribute("style", "border:none;border-radius:14px;padding:0;box-shadow:var(--shadow);");
    followDialog.innerHTML = `
      <form class="card-pad field-group" id="follow-reference-form" method="dialog" style="width:min(440px,92vw);">
        <h2 style="font-size:16px;margin-bottom:4px;">Suivre une autre référence</h2>
        <p class="help" style="margin-bottom:10px;">L'étude cite désormais cette version de référence ; celle dont elle est partie reste dans son histoire. Pour promouvoir une structure comme nouvelle référence, passez par « Promouvoir comme référence ».</p>
        <div><label for="follow-ref">Référence</label><select class="field" id="follow-ref" required></select></div>
        <div><label for="follow-version">Version</label><select class="field" id="follow-version" required></select></div>
        <fieldset style="border:none;padding:0;margin:0;">
          <legend style="font-size:12px;font-weight:600;margin-bottom:6px;">Portée</legend>
          <label style="display:flex;gap:8px;align-items:flex-start;margin-bottom:6px;"><input type="radio" name="follow-scope" value="study" checked><span>Cette étude seulement</span></label>
          <label style="display:flex;gap:8px;align-items:flex-start;"><input type="radio" name="follow-scope" value="branch"><span>Cette étude et toute sa branche<span class="help" style="display:block;">Les pistes qui en descendent la suivent aussi.</span></span></label>
        </fieldset>
        <div id="follow-error" class="error" role="alert" hidden></div>
        <div style="display:flex;gap:10px;margin-top:8px;">
          <button type="button" id="follow-cancel" class="btn btn-line btn-block">Annuler</button>
          <button type="submit" id="follow-submit" class="btn btn-primary btn-block">Suivre cette référence</button>
        </div>
      </form>`;
    document.body.appendChild(followDialog);
    followDialog.querySelector("#follow-cancel").addEventListener("click", () => followDialog.close());
    return followDialog;
  }

  async function fillFollowVersions(slug, selected) {
    const select = document.getElementById("follow-version");
    select.innerHTML = `<option value="">Chargement…</option>`;
    if (!slug) {
      select.innerHTML = `<option value="">— Choisir d'abord la référence —</option>`;
      return;
    }
    try {
      const graph = await referencesApi.versions(slug);
      const numbers = graph.nodes.map((node) => node.number).reverse();
      select.innerHTML = numbers.length
        ? numbers.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("")
        : `<option value="">Aucune version publiée</option>`;
      select.value = selected && numbers.includes(selected) ? selected : numbers[0] || "";
    } catch (err) {
      select.innerHTML = `<option value="">—</option>`;
    }
  }

  async function openFollowDialog(ctx) {
    const dialog = ensureFollowDialog();
    const form = dialog.querySelector("form");
    const refSelect = dialog.querySelector("#follow-ref");
    const error = dialog.querySelector("#follow-error");
    error.hidden = true;
    const current = ctx.detail.reference_followed;
    refSelect.innerHTML = `<option value="">Chargement…</option>`;
    dialog.showModal();
    let refs = [];
    try {
      refs = await referencesApi.list();
    } catch (err) {
      error.textContent = err.message || String(err);
      error.hidden = false;
    }
    refSelect.innerHTML =
      `<option value="">— Choisir une référence —</option>` +
      refs.map((r) => `<option value="${escapeHtml(r.slug)}">${escapeHtml(r.name)}${r.latest_version ? ` · ${escapeHtml(r.latest_version.number)}` : ""}</option>`).join("");
    refSelect.value = current && refs.some((r) => r.slug === current.reference) ? current.reference : "";
    await fillFollowVersions(refSelect.value, current ? current.version : null);
    refSelect.onchange = () => fillFollowVersions(refSelect.value, null);
    form.onsubmit = async (event) => {
      event.preventDefault();
      const reference = refSelect.value;
      const version = dialog.querySelector("#follow-version").value;
      if (!reference || !version) {
        error.textContent = "Choisissez une référence et une de ses versions.";
        error.hidden = false;
        return;
      }
      const scope = dialog.querySelector('input[name="follow-scope"]:checked').value;
      const submit = dialog.querySelector("#follow-submit");
      submit.disabled = true;
      try {
        await experimentsApi.setReference(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, { reference, version, scope });
        dialog.close();
        await ctx.reload();
      } catch (err) {
        error.textContent = err.message || String(err);
        error.hidden = false;
      } finally {
        submit.disabled = false;
      }
    };
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
