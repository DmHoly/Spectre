/* La page /promotion ouverte sur une brique (?brique=<id>&retour=) : promouvoir une brique
   technologique comme brique de référence. La même page que la promotion d'une structure, avec
   son propre formulaire (la brique, le pourquoi), son aperçu simulé et ses règles (le serveur :
   promotionApi.previewBrick) ; le formulaire des structures reste caché. */

(() => {
  const params = new URLSearchParams(window.location.search);
  const brickId = params.get("brique");
  if (!brickId) return;
  const $ = (id) => document.getElementById(id);
  const errorBox = $("error");
  const state = { brick: null, timer: null, token: 0 };
  const RULE_ICONS = {
    ok: '<path d="M5 13l4 4L19 7"/>',
    warn: '<path d="M12 8v5"/><path d="M12 16.5h.01"/>',
    block: '<path d="M7 7l10 10M17 7 7 17"/>',
  };
  const RULE_WORDS = { ok: "Vérifié", warn: "À savoir", block: "Bloquant" };
  const SCOPE_LABELS = { builtin: "intégrée", shared: "partagée", microproject: "du µprojet" };
  const PREVIEW_SUBSTRATE = { material: "GaN", domain_width: { value: 400, unit: "nm" }, thickness: { value: 50, unit: "nm" } };

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }

  function backUrl() {
    const back = params.get("retour");
    return back && back.startsWith("/") && !back.startsWith("//") ? back : null;
  }

  function brickUrl(id) {
    return `/briques/${encodeURIComponent(id)}`;
  }

  function body() {
    return { brick_id: brickId, note: $("b-note").value };
  }

  function anchoredSteps(brick) {
    const anchors = brick.lattice_openings || {};
    return brick.steps.map((step, i) => (anchors[i] || anchors[String(i)] ? { ...step, lattice_opening: anchors[i] || anchors[String(i)] } : step));
  }

  function renderSummary(brick) {
    const scope = `${SCOPE_LABELS[brick.scope] || brick.scope}${brick.microproject ? ` ${brick.microproject}` : ""}`;
    $("brick-summary").innerHTML = `
      <div style="font-size:15px;font-weight:700;"><a href="${brickUrl(brick.id)}">${escapeHtml(brick.name)}</a></div>
      <div class="help" style="margin:4px 0 0;">${escapeHtml(scope)} · version ${escapeHtml(brick.version)} · ${brick.steps.length} étape${brick.steps.length > 1 ? "s" : ""}${brick.substrate ? " · brique de départ (garde son substrat)" : ""}${brick.created_by && brick.created_by.name ? ` · par ${escapeHtml(brick.created_by.name)}` : ""}</div>
      ${brick.notes ? `<p style="margin:8px 0 0;font-size:13px;color:var(--text-soft);">${escapeHtml(brick.notes)}</p>` : ""}`;
  }

  function renderRules(preview) {
    $("brick-rules").innerHTML = preview.rules
      .map(
        (r) => `
        <li class="promo-rule promo-rule--${r.level}">
          <span class="promo-rule__icon" aria-hidden="true"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">${RULE_ICONS[r.level]}</svg></span>
          <span class="promo-rule__body">
            <span class="promo-rule__label">${escapeHtml(r.label)} <span class="promo-rule__word">${RULE_WORDS[r.level]}</span></span>
            <span class="promo-rule__message">${escapeHtml(r.message)}</span>
          </span>
        </li>`
      )
      .join("");
    const blocking = preview.rules.filter((r) => r.level === "block");
    const warnings = preview.rules.filter((r) => r.level === "warn");
    $("brick-submit-btn").disabled = !preview.can_promote;
    $("brick-submit-hint").textContent = blocking.length
      ? `${blocking.length} point${blocking.length > 1 ? "s" : ""} bloquant${blocking.length > 1 ? "s" : ""} : ${blocking[0].message}`
      : warnings.length
        ? `Prête, avec ${warnings.length} point${warnings.length > 1 ? "s" : ""} à savoir.`
        : "Prête.";
    const brick = preview.brick;
    $("brick-outcome").innerHTML = preview.can_promote
      ? `<div class="promo-outcome__label">Deviendra</div>
         <div class="promo-outcome__ref"><span class="promo-outcome__r" aria-hidden="true">B</span>${escapeHtml(brick.name)} <span class="ref-number">${escapeHtml(brick.version)}</span></div>
         <div class="promo-outcome__level">brique de référence, partagée avec tous les µprojets</div>`
      : `<span class="help">Pas encore : voyez les vérifications.</span>`;
  }

  async function renderPreviewArt(brick) {
    try {
      const result = await structuresApi.simulate({ substrate: brick.substrate || PREVIEW_SUBSTRATE, steps: anchoredSteps(brick) });
      const frames = result.frames || [];
      $("brick-structure").innerHTML = frames.length ? `<div class="promo-structure__svg">${frames[frames.length - 1].svg}</div>` : "";
    } catch {
      $("brick-structure").innerHTML = "";
    }
  }

  async function refresh() {
    const mine = ++state.token;
    try {
      const preview = await promotionApi.previewBrick(body());
      if (mine !== state.token) return;
      if (!state.brick) {
        state.brick = preview.brick;
        renderSummary(preview.brick);
        renderPreviewArt(preview.brick);
      }
      renderRules(preview);
      showError(null);
    } catch (err) {
      if (mine !== state.token) return;
      showError(err);
      $("brick-submit-btn").disabled = true;
    }
  }

  function schedule(delay = 250) {
    clearTimeout(state.timer);
    state.timer = setTimeout(refresh, delay);
  }

  $("b-note").addEventListener("input", () => schedule());

  $("brick-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("brick-submit-btn");
    button.disabled = true;
    showError(null);
    try {
      const brick = await promotionApi.promoteBrick(body());
      showDone(brick);
    } catch (err) {
      showError(err);
      refresh();
    }
  });

  function showDone(brick) {
    const back = backUrl();
    $("brick-layout").hidden = true;
    const done = $("done");
    done.innerHTML = `
      <div class="promo-done__mark" aria-hidden="true"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12v18l-6-4-6 4Z"/><path d="m9.5 10 2 2 3.5-3.5"/></svg></div>
      <div class="promo-done__body">
        <h2 class="promo-done__title" id="done-title">Promue : <span class="promo-outcome__r" aria-hidden="true">B</span>${escapeHtml(brick.name)} <span class="ref-number">${escapeHtml(brick.version)}</span></h2>
        <p class="promo-done__text">Brique de référence, partagée avec tous les µprojets : le constructeur la propose à chacun, et ses prochaines versions diront pourquoi elles changent.</p>
        <div class="promo-done__actions">
          <a class="btn btn-primary" href="${brickUrl(brick.id)}?promue=1">Voir la brique</a>
          ${back && !back.startsWith(brickUrl(brick.id)) ? `<a class="btn btn-line" href="${escapeHtml(back)}">Revenir à la page d'avant</a>` : ""}
          <a class="btn btn-line" href="/briques">Toutes les briques de référence</a>
        </div>
      </div>`;
    done.hidden = false;
    done.focus();
  }

  function init() {
    document.title = "Promouvoir une brique de référence — Spectre";
    const crumb = $("crumb");
    if (crumb) crumb.textContent = "/ Promouvoir une brique de référence";
    document.querySelector(".page-eyebrow").textContent = "Briques de référence";
    document.querySelector(".promo-head__title").textContent = "Promouvoir une brique comme brique de référence";
    document.querySelector(".promo-head__lead").textContent =
      "La brique que tout le monde reprend : partagée avec tous les µprojets, suivie sur la page des briques de référence, et dont chaque nouvelle version dit pourquoi elle change. Les vérifications, à droite, disent ce qui est prêt et ce qui manque.";
    const back = backUrl();
    $("back-link").href = back || "/briques";
    $("back-link").hidden = false;
    $("promo-layout").hidden = true;
    document.querySelector(".promo-journal").hidden = true;
    $("brick-layout").hidden = false;
    refresh();
  }

  init();
})();
