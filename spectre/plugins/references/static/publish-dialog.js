/* « Publier comme référence » (global `ReferencePublishDialog`) : la boîte qui publie une version
   d'étude comme nouvelle version d'une référence de toute l'application. Ouverte depuis la fiche
   d'une étude (experiments/static/tags-refs.js) et la page d'évolution d'un µprojet
   (experiments/static/evolution.js), qui ne lui donnent que l'étude :

     ReferencePublishDialog.open({microprojectSlug, experimentId, versionId, origin, ancestors?, onPublished})

   La référence proposée d'office est celle dont vient l'étude : son origine (`reference_origin`,
   que la page a lue), sinon la dernière référence où a été publiée une version dont elle descend
   (`ancestors`, les ids que la page d'évolution lit dans son graphe ; sans eux - la fiche, sur la
   pointe -, une version de la même piste ; referencesApi.publishedFrom). On peut en choisir une autre, ou en créer une. La version dont elle
   dérive (le parent) est proposée de même - la dernière publiée depuis la piste, sinon la version
   d'origine -, « automatique » laissant le serveur décider (la même règle). Le numéro (1.1, 2.0...) est calculé par le
   serveur et montré après la publication ; un refus (« identique à la version 1.1 ») s'affiche tel
   quel. Une référence créée ici puis refusée (structure identique, droits) est retirée aussitôt :
   on ne laisse pas une référence vide derrière un échec. */

const ReferencePublishDialog = (() => {
  const LEVEL_TEXT = { initial: "première version", major: "changement majeur", minor: "changement mineur", patch: "correctif", none: "sans changement" };
  const NEW = "__new__";
  let dialog = null;
  let current = null; // {options, references, published, suggestion}

  function referenceUrl(slug, number) {
    return `/references/${encodeURIComponent(slug)}${number ? `?version=${encodeURIComponent(number)}` : ""}`;
  }

  function build() {
    dialog = document.createElement("dialog");
    dialog.className = "ref-dialog";
    dialog.setAttribute("aria-labelledby", "ref-publish-title");
    dialog.innerHTML = `
      <div class="card-pad ref-dialog__inner">
        <h2 class="ref-dialog__title" id="ref-publish-title">Publier comme référence</h2>
        <p class="help ref-dialog__lead">La structure de cette version devient une nouvelle version de la référence, utilisable par tous les µprojets. Son numéro est calculé : un changement majeur ouvre X+1.0, un changement mineur ou un correctif donne X.Y+1.</p>
        <div class="error" role="alert" id="ref-publish-error" hidden></div>
        <form id="ref-publish-form" class="ref-dialog__form">
          <div class="ref-field">
            <label for="ref-publish-target">Référence</label>
            <select class="field" id="ref-publish-target" required></select>
            <p class="help" id="ref-publish-hint"></p>
          </div>
          <div class="ref-dialog__new" id="ref-publish-new" hidden>
            <div class="ref-field">
              <label for="ref-publish-name">Nom de la nouvelle référence</label>
              <input class="field" id="ref-publish-name" maxlength="120" autocomplete="off">
            </div>
            <div class="ref-field">
              <label for="ref-publish-description">Description <span class="ref-dialog__optional">(facultative)</span></label>
              <textarea class="field" id="ref-publish-description" rows="2" maxlength="2000"></textarea>
            </div>
          </div>
          <div class="ref-field" id="ref-publish-parent-group" hidden>
            <label for="ref-publish-parent">Dérive de la version</label>
            <select class="field" id="ref-publish-parent"></select>
            <p class="help">Le numéro est calculé en comparant la structure à cette version.</p>
          </div>
          <div class="ref-field">
            <label for="ref-publish-note">Note <span class="ref-dialog__optional">(ce qui change, pourquoi)</span></label>
            <textarea class="field" id="ref-publish-note" rows="3" maxlength="2000"></textarea>
          </div>
          <div class="ref-dialog__actions">
            <button class="btn btn-line" type="button" id="ref-publish-cancel">Annuler</button>
            <button class="btn btn-primary" type="submit" id="ref-publish-submit">Publier</button>
          </div>
        </form>
        <div id="ref-publish-done" hidden></div>
      </div>`;
    document.body.appendChild(dialog);
    dialog.querySelector("#ref-publish-cancel").addEventListener("click", () => dialog.close());
    dialog.querySelector("#ref-publish-target").addEventListener("change", onTargetChange);
    dialog.querySelector("#ref-publish-form").addEventListener("submit", onSubmit);
    dialog.querySelector("#ref-publish-done").addEventListener("click", (event) => {
      if (event.target.closest(".js-ref-close")) dialog.close();
    });
  }

  function showError(err) {
    const box = dialog.querySelector("#ref-publish-error");
    box.textContent = err ? err.message || String(err) : "";
    box.hidden = !err;
  }

  // La référence d'où vient l'étude : son origine, sinon la plus récente où la piste a été publiée.
  // Le parent : la dernière version de cette référence publiée depuis la piste (republier une étude
  // partie d'une référence continue sa suite : 1.1 puis 1.2, pas deux branches de 1.0), sinon la
  // version d'origine. `published` : les plus récentes d'abord ; `ancestors` (facultatif) : les ids
  // des versions dont descend celle qu'on publie - une version publiée plus loin sur la piste n'en
  // est alors pas la source.
  function suggestion(origin, published, experimentId, ancestors) {
    const fromLine = (entry) => (ancestors ? ancestors.has(entry.version_id) : entry.experiment_id === experimentId);
    if (origin && origin.reference) {
      const same = published.find((entry) => entry.reference.slug === origin.reference && fromLine(entry));
      if (same) return { slug: origin.reference, parent: same.number, why: `l'étude en est partie (${origin.version}) et y a été publiée (${same.number})` };
      return { slug: origin.reference, parent: origin.version, why: "l'étude en est partie" };
    }
    const same = published.find(fromLine);
    if (same) return { slug: same.reference.slug, parent: same.number, why: `une version dont elle descend y a été publiée (${same.number})` };
    return null;
  }

  function targetOptionsHtml(references, suggested) {
    const options = references.map((ref) => {
      const latest = ref.latest_version ? ` · ${ref.latest_version.number}` : " · sans version";
      const mark = suggested && suggested.slug === ref.slug ? " (proposée)" : "";
      return `<option value="${escapeHtml(ref.slug)}">${escapeHtml(ref.name)}${escapeHtml(latest)}${mark}</option>`;
    });
    return `<option value="${NEW}">+ Nouvelle référence…</option>${options.join("")}`;
  }

  async function onTargetChange() {
    const slug = dialog.querySelector("#ref-publish-target").value;
    const isNew = slug === NEW;
    dialog.querySelector("#ref-publish-new").hidden = !isNew;
    const hint = dialog.querySelector("#ref-publish-hint");
    const suggested = current.suggestion;
    hint.textContent =
      suggested && suggested.slug === slug
        ? `Proposée : ${suggested.why}.`
        : isNew
          ? "La structure en sera la version 1.0."
          : "";
    const group = dialog.querySelector("#ref-publish-parent-group");
    const parent = dialog.querySelector("#ref-publish-parent");
    group.hidden = true;
    parent.innerHTML = "";
    if (isNew) {
      dialog.querySelector("#ref-publish-name").focus();
      return;
    }
    try {
      const graph = await referencesApi.versions(slug);
      if (dialog.querySelector("#ref-publish-target").value !== slug) return; // un autre choix entre-temps
      if (!graph.nodes.length) return; // une référence sans version : la structure en sera la 1.0
      const latest = graph.nodes[graph.nodes.length - 1].number;
      const preferred = suggested && suggested.slug === slug && graph.nodes.some((n) => n.number === suggested.parent) ? suggested.parent : "";
      parent.innerHTML =
        `<option value="">Automatique (${escapeHtml(preferred || latest)})</option>` +
        graph.nodes
          .slice()
          .reverse()
          .map((node) => `<option value="${escapeHtml(node.number)}">${escapeHtml(node.number)} · ${escapeHtml(LEVEL_TEXT[node.change_level] || node.change_level)} · ${escapeHtml(formatDate(node.published_at))}</option>`)
          .join("");
      parent.value = preferred;
      group.hidden = false;
    } catch (err) {
      showError(err);
    }
  }

  async function onSubmit(event) {
    event.preventDefault();
    showError(null);
    const submit = dialog.querySelector("#ref-publish-submit");
    let slug = dialog.querySelector("#ref-publish-target").value;
    const note = dialog.querySelector("#ref-publish-note").value.trim();
    const parent = dialog.querySelector("#ref-publish-parent").value || null;
    let created = null;
    submit.disabled = true;
    try {
      if (slug === NEW) {
        const name = dialog.querySelector("#ref-publish-name").value.trim();
        if (!name) {
          showError(new Error("Donnez un nom à la nouvelle référence."));
          dialog.querySelector("#ref-publish-name").focus();
          return;
        }
        created = await referencesApi.create({ name, description: dialog.querySelector("#ref-publish-description").value.trim() });
        slug = created.slug;
      }
      const { microprojectSlug, experimentId, versionId } = current.options;
      let version;
      try {
        version = await referencesApi.publish(slug, {
          microproject: microprojectSlug,
          experiment_id: experimentId,
          version_id: versionId || null,
          note,
          parent: created ? null : parent,
        });
      } catch (err) {
        if (created) await referencesApi.remove(created.slug).catch(() => {}); // pas de référence vide derrière un échec
        throw err;
      }
      showDone(version);
      if (current.options.onPublished) current.options.onPublished(version);
    } catch (err) {
      showError(err);
    } finally {
      submit.disabled = false;
    }
  }

  function showDone(version) {
    dialog.querySelector("#ref-publish-form").hidden = true;
    const done = dialog.querySelector("#ref-publish-done");
    const level = LEVEL_TEXT[version.change_level] || version.change_level;
    done.innerHTML = `
      <div class="flash flash-ok" role="status">
        Publiée : <strong>${escapeHtml(version.reference.name)} ${escapeHtml(version.number)}</strong> (${escapeHtml(level)}${version.parent ? `, depuis ${escapeHtml(version.parent)}` : ""}).
      </div>
      <div class="ref-dialog__actions">
        <button class="btn btn-line js-ref-close" type="button">Fermer</button>
        <a class="btn btn-primary" href="${referenceUrl(version.reference.slug, version.number)}">Voir la référence</a>
      </div>`;
    done.hidden = false;
    done.querySelector(".btn-primary").focus();
  }

  async function open(options) {
    if (!dialog) build();
    current = { options, suggestion: null };
    showError(null);
    dialog.querySelector("#ref-publish-form").hidden = false;
    dialog.querySelector("#ref-publish-form").reset();
    dialog.querySelector("#ref-publish-done").hidden = true;
    dialog.querySelector("#ref-publish-target").innerHTML = `<option>Chargement…</option>`;
    dialog.showModal();
    try {
      const [references, published] = await Promise.all([referencesApi.list(), referencesApi.publishedFrom(options.microprojectSlug)]);
      const suggested = suggestion(options.origin, published, options.experimentId, options.ancestors);
      current.suggestion = suggested && references.some((ref) => ref.slug === suggested.slug) ? suggested : null;
      const target = dialog.querySelector("#ref-publish-target");
      target.innerHTML = targetOptionsHtml(references, current.suggestion);
      target.value = current.suggestion ? current.suggestion.slug : NEW;
      await onTargetChange();
      target.focus();
    } catch (err) {
      showError(err);
    }
  }

  return { open };
})();
