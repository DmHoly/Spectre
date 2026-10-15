/* La fiche d'une brique technologique (pages/brick.html, /briques/{id}) : son en-tête (portée,
   auteur, version courante), sa référence (qui l'a promue, quand, pourquoi), ses versions de la
   plus récente à la première - numéro, niveau du changement, date, auteur, note, et ce qui change
   depuis la précédente (le serveur le dit en mots) -, son aperçu simulé (sur son substrat de
   brique de départ, sinon un substrat d'aperçu), les études qui en ont une copie et sur quelle
   version, ses étapes. Actions : l'ouvrir dans le constructeur (mode brique, sous un µprojet de
   travail), la promouvoir comme brique de référence (le formulaire du plugin promotion), la retirer
   des références. */

(() => {
  const { brick_id: brickId } = routeParams("/briques/{brick_id}");
  const errorBox = document.getElementById("error");
  const SCOPE_LABELS = { builtin: "intégrée", shared: "partagée", microproject: "du µprojet" };
  const LEVEL_TEXT = { initial: "première version", major: "changement majeur", minor: "changement mineur", patch: "retouche", none: "sans changement" };
  const STATUS_LABELS = { draft: "brouillon", running: "en cours", hold: "en pause", concluded: "conclue", continued: "continuée", abandoned: "abandonnée" };
  const WORK_MICROPROJECT_KEY = "spectre.libWorkMicroproject";
  // le substrat d'aperçu d'une brique sans substrat propre
  const PREVIEW_SUBSTRATE = { material: "GaN", domain_width: { value: 400, unit: "nm" }, thickness: { value: 50, unit: "nm" } };

  const state = { brick: null, usages: [], workSlug: null };

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }
  function showFlash(message) {
    const flash = document.getElementById("flash");
    flash.textContent = message;
    flash.hidden = !message;
  }

  function versionKey(number) {
    const [major, minor] = String(number || "0.0").split(".");
    return [Number(major) || 0, Number(minor) || 0];
  }
  function olderThan(a, b) {
    const [am, an] = versionKey(a);
    const [bm, bn] = versionKey(b);
    return am < bm || (am === bm && an < bn);
  }

  // Les étapes telles que le constructeur les envoie : chaque lithographie ancrée au réseau porte
  // son ancrage (rangé à part dans la bibliothèque, `lattice_openings`).
  function anchoredSteps(brick) {
    const anchors = brick.lattice_openings || {};
    return brick.steps.map((step, i) => (anchors[i] || anchors[String(i)] ? { ...step, lattice_opening: anchors[i] || anchors[String(i)] } : step));
  }

  // -- en-tête ---------------------------------------------------------------------------------

  function editorHref() {
    const slug = state.brick.microproject || state.workSlug;
    if (!slug) return null;
    return `/microprojets/${encodeURIComponent(slug)}/briques-technologiques/bibliotheque/${encodeURIComponent(state.brick.id)}?retour=brique`;
  }

  function renderHead() {
    const brick = state.brick;
    const isRef = Boolean(brick.reference);
    document.title = `${brick.name} · Briques — Spectre`;
    document.getElementById("name-crumb").textContent = brick.name;
    document.getElementById("crumb").textContent = `/ Briques / ${brick.name}`;
    document.getElementById("brick-eyebrow").textContent = isRef ? "Brique de référence" : "Brique technologique";
    document.getElementById("brick-name").textContent = brick.name;
    document.getElementById("brick-notes").textContent = brick.notes || "";
    const parts = [
      `${SCOPE_LABELS[brick.scope] || brick.scope}${brick.microproject ? ` ${brick.microproject}` : ""}`,
      brick.created_by && brick.created_by.name ? `créée par ${brick.created_by.name}` : null,
      brick.created_at && brick.created_at !== "preset" ? `le ${formatDate(brick.created_at)}` : null,
      `version ${brick.version}`,
      `${brick.versions.length} version${brick.versions.length > 1 ? "s" : ""}`,
      brick.substrate ? "brique de départ (garde son substrat)" : "s'applique sur la structure existante",
    ].filter(Boolean);
    document.getElementById("brick-meta").textContent = parts.join(" · ");

    const actions = [];
    const editor = editorHref();
    if (editor) actions.push(`<a class="btn btn-line" href="${escapeHtml(editor)}">${brick.can_edit ? "Ouvrir dans le constructeur" : "Dupliquer dans le constructeur"}</a>`);
    if (!isRef && typeof PromotionLink !== "undefined" && pluginEnabled("promotion")) {
      actions.push(PromotionLink.html({ brick: brick.id }, { label: "Promouvoir comme brique de référence", title: "Faire de cette brique la brique de référence que tout le monde reprend : le formulaire de la promotion" }));
    }
    if (isRef && brick.can_edit) actions.push(`<button class="btn btn-line" type="button" id="demote-btn">Retirer des références</button>`);
    document.getElementById("head-actions").innerHTML = actions.join("");
    const demote = document.getElementById("demote-btn");
    if (demote) demote.addEventListener("click", demoteBrick);

    const box = document.getElementById("reference-box");
    box.hidden = !isRef;
    if (isRef) {
      const who = brick.reference.promoted_by && brick.reference.promoted_by.name ? brick.reference.promoted_by.name : "—";
      document.getElementById("reference-text").innerHTML = `
        <div class="promo-panel__text">Promue par ${escapeHtml(who)} le ${escapeHtml(formatDate(brick.reference.promoted_at))}.${brick.reference.note ? ` <span class="sp-brick__why">${escapeHtml(brick.reference.note)}</span>` : ""}</div>
        <div class="help" style="margin:6px 0 0;">Une nouvelle version de cette brique demande une note : pourquoi elle change.</div>`;
    }
  }

  async function demoteBrick() {
    if (!window.confirm(`Retirer « ${state.brick.name} » des briques de référence ? Elle reste partagée, avec ses versions.`)) return;
    try {
      state.brick = await processLibraryApi.demoteTechBrick(state.brick.id);
      renderHead();
      showFlash("La brique n'est plus une brique de référence.");
    } catch (err) {
      showError(err);
    }
  }

  // -- les versions ----------------------------------------------------------------------------

  function versionHtml(version, index) {
    const who = version.created_by && version.created_by.name ? version.created_by.name : null;
    const changes = version.changes && version.changes.length ? `<ul class="sp-brick__changes">${version.changes.map((c) => `<li>${escapeHtml(c)}</li>`).join("")}</ul>` : "";
    const current = version.number === state.brick.version;
    return `
      <li class="sp-brick__version ${current ? "is-current" : ""}">
        <div class="sp-brick__version-head">
          <span class="ref-number">${escapeHtml(version.number)}</span>
          <span class="sp-brick__level sp-brick__level--${escapeHtml(version.level)}">${escapeHtml(LEVEL_TEXT[version.level] || version.level)}</span>
          ${current ? `<span class="sp-brick__current">courante</span>` : ""}
          <span class="sp-brick__version-meta">${escapeHtml(version.created_at === "preset" ? "livrée avec l'instance" : formatDate(version.created_at))}${who ? ` · ${escapeHtml(who)}` : ""}</span>
        </div>
        ${version.note ? `<p class="sp-brick__note">${escapeHtml(version.note)}</p>` : ""}
        ${changes}
        ${index === 0 && !changes ? `<p class="help" style="margin:4px 0 0;">${state.brick.steps.length} étape${state.brick.steps.length > 1 ? "s" : ""}${state.brick.substrate ? " et un substrat" : ""}.</p>` : ""}
      </li>`;
  }

  function renderVersions() {
    const versions = [...state.brick.versions].reverse();
    document.getElementById("versions").innerHTML = versions.map((v, i) => versionHtml(v, versions.length - 1 - i)).join("");
  }

  // -- l'aperçu, les étapes --------------------------------------------------------------------

  async function renderPreview() {
    const brick = state.brick;
    const holder = document.getElementById("preview");
    document.getElementById("preview-substrate").textContent = brick.substrate
      ? `Sur son propre substrat : ${brick.substrate.material}${brick.substrate.lattice ? `, réseau au pas de ${brick.substrate.lattice.pitch} nm` : ""}.`
      : "Sur un substrat d'aperçu (la brique s'applique sur la structure existante).";
    try {
      const result = await structuresApi.simulate({ substrate: brick.substrate || PREVIEW_SUBSTRATE, steps: anchoredSteps(brick) });
      const frames = result.frames || [];
      holder.innerHTML = frames.length ? frames[frames.length - 1].svg : "";
      holder.classList.remove("skeleton");
    } catch (err) {
      holder.classList.remove("skeleton");
      holder.classList.add("is-failed");
      holder.textContent = "Aperçu impossible";
      holder.title = err.message || String(err);
    }
  }

  function renderSteps() {
    document.getElementById("steps").innerHTML = state.brick.steps
      .map((step) => `<li><span class="sp-brick__kind">${escapeHtml(step.kind)}</span> ${escapeHtml(step.name || "")}</li>`)
      .join("");
  }

  // -- où elle sert ----------------------------------------------------------------------------

  function renderUsages() {
    const uses = state.usages;
    const host = document.getElementById("usages");
    if (!uses.length) {
      host.innerHTML = `<span class="help">Utilisée dans aucune étude.</span>`;
      return;
    }
    const current = state.brick.version;
    const older = uses.filter((u) => u.version && olderThan(u.version, current)).length;
    const rows = uses
      .map((u) => {
        const version = u.version ? `v${u.version}` : "v?";
        const stale = u.version && olderThan(u.version, current) ? " is-stale" : "";
        if (!u.linked) return `<li><span class="sp-brick__usage-v${stale}">${escapeHtml(version)}</span> une étude de « ${escapeHtml(u.microproject.name)} »</li>`;
        const href = `/microprojets/${encodeURIComponent(u.microproject.slug)}/experiences/${encodeURIComponent(u.experiment_id)}`;
        return `<li><span class="sp-brick__usage-v${stale}">${escapeHtml(version)}</span> <a href="${href}">${escapeHtml(u.title || u.experiment_id)}</a> <span class="help" style="display:inline;">${escapeHtml(u.microproject.code || u.microproject.name)} · ${escapeHtml(STATUS_LABELS[u.status] || u.status || "")}</span></li>`;
      })
      .join("");
    host.innerHTML = `
      <div class="sp-brick__usage-summary">Utilisée dans ${uses.length} étude${uses.length > 1 ? "s" : ""}${older ? ` · ${older} sur une version antérieure` : ""}</div>
      <ul class="sp-brick__usages">${rows}</ul>`;
  }

  // -- amorce ----------------------------------------------------------------------------------

  async function workMicroproject() {
    try {
      const microprojects = await microprojectsApi.list();
      let remembered = null;
      try {
        remembered = localStorage.getItem(WORK_MICROPROJECT_KEY);
      } catch {
        remembered = null;
      }
      const found = microprojects.find((m) => m.slug === remembered) || microprojects[0];
      return found ? found.slug : null;
    } catch {
      return null;
    }
  }

  async function init() {
    try {
      state.brick = await processLibraryApi.techBrick(brickId);
    } catch (err) {
      document.getElementById("brick-name").textContent = "Brique introuvable";
      showError(err);
      return;
    }
    const filters = state.brick.microproject ? { microproject: state.brick.microproject } : {};
    const [usages, workSlug] = await Promise.all([processLibraryApi.techBrickUsages(filters).catch(() => ({})), state.brick.microproject ? null : workMicroproject()]);
    state.usages = usages[state.brick.id] || [];
    state.workSlug = workSlug;
    renderHead();
    renderVersions();
    renderSteps();
    renderUsages();
    renderPreview();
    if (new URLSearchParams(window.location.search).get("promue") === "1") showFlash("Cette brique est maintenant une brique de référence.");
  }

  init();
})();
