/* La page /promotion : le formulaire qui choisit une structure comme référence.

   Ouverte de partout (PromotionLink, link.js) avec ce qu'on sait déjà dans l'adresse : ?microprojet=
   &etude= &version= (une version passée ; la dernière sinon) &variante= (un split) &reference= (la
   référence visée) &retour= (la page d'où l'on vient). Chaque changement relit l'aperçu du serveur
   (promotionApi.preview) : le numéro que prendrait la version, la structure dessinée et le verdict
   de chaque règle - ce sont elles qui disent ce qui manque, la page ne décide de rien. */

(() => {
  const params = new URLSearchParams(window.location.search);
  const $ = (id) => document.getElementById(id);
  const errorBox = $("error");
  const state = {
    references: [],
    studies: [],
    preview: null,
    // la version demandée par l'adresse vaut pour l'étude de l'adresse seulement
    pinned: { experimentId: params.get("etude"), versionId: params.get("version") },
    variant: params.get("variante"),
    targetChosen: Boolean(params.get("reference")),
    token: 0,
    timer: null,
  };

  const RULE_ICONS = {
    ok: '<path d="M5 13l4 4L19 7"/>',
    warn: '<path d="M12 8v5"/><path d="M12 16.5h.01"/>',
    block: '<path d="M7 7l10 10M17 7 7 17"/>',
  };
  const RULE_WORDS = { ok: "Vérifié", warn: "À savoir", block: "Bloquant" };

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }

  function studyUrl(slug, experimentId, versionId) {
    return `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(experimentId)}${versionId ? `?version=${encodeURIComponent(versionId)}` : ""}`;
  }

  function referenceUrl(slug, number) {
    return `/references/${encodeURIComponent(slug)}${number ? `?version=${encodeURIComponent(number)}` : ""}`;
  }

  function mode() {
    return $("mode-new").checked ? "new" : "existing";
  }

  // -- le corps envoyé (aperçu et promotion) ---------------------------------------------------------

  function body() {
    const experimentId = $("f-study").value;
    const result = {
      microproject: $("f-microproject").value,
      experiment_id: experimentId,
      note: $("f-note").value,
    };
    if (state.pinned.versionId && experimentId === state.pinned.experimentId) result.version_id = state.pinned.versionId;
    if (!$("f-variant-group").hidden && $("f-variant").value !== "") result.variant = Number($("f-variant").value);
    else if (state.variant !== null && state.variant !== "" && experimentId === state.pinned.experimentId) result.variant = Number(state.variant);
    if (mode() === "new") {
      result.new_reference = { name: $("f-name").value, description: $("f-description").value };
    } else if ($("f-reference").value) {
      result.reference = $("f-reference").value;
      if ($("f-parent").value) result.parent = $("f-parent").value;
    }
    return result;
  }

  // -- l'aperçu ----------------------------------------------------------------------------------

  function schedule(delay = 250) {
    clearTimeout(state.timer);
    state.timer = setTimeout(refresh, delay);
  }

  async function refresh() {
    if (!$("f-microproject").value || !$("f-study").value) {
      state.preview = null;
      renderEmpty();
      return;
    }
    const mine = ++state.token;
    try {
      const preview = await promotionApi.preview(body());
      if (mine !== state.token) return;
      state.preview = preview;
      showError(null);
      render(preview);
    } catch (err) {
      if (mine !== state.token) return;
      showError(err);
      renderEmpty();
    }
  }

  function renderEmpty() {
    $("outcome").innerHTML = `<span class="help">Choisissez une structure.</span>`;
    $("structure").innerHTML = "";
    $("rules").innerHTML = "";
    $("submit-btn").disabled = true;
    $("submit-hint").textContent = "";
  }

  function render(preview) {
    const source = preview.source;
    // la variante d'un split
    const group = $("f-variant-group");
    const select = $("f-variant");
    if (source.variants.length) {
      const chosen = source.variant !== null ? String(source.variant) : select.value;
      select.innerHTML =
        `<option value="">— Choisir la variante —</option>` +
        source.variants.map((v) => `<option value="${v.index}">${escapeHtml(v.label)}</option>`).join("");
      select.value = chosen || "";
      group.hidden = false;
    } else {
      group.hidden = true;
      select.innerHTML = "";
    }
    // la version : la dernière, ou une version passée demandée par l'adresse
    const study = state.studies.find((s) => s.id === source.experiment_id);
    const note = $("f-version-note");
    const past = study && study.version_id !== source.version_id;
    note.hidden = false;
    note.innerHTML = `${past ? "Une version passée de l'étude" : "La dernière version de l'étude"} - <a href="${studyUrl(source.microproject.slug, source.experiment_id, past ? source.version_id : null)}">ouvrir la fiche</a>`;

    // la référence proposée (celle dont part l'étude) : choisie d'office tant qu'on n'a rien choisi
    if (!state.targetChosen) {
      state.targetChosen = true;
      if (preview.suggestion) {
        $("mode-existing").checked = true;
        $("f-reference").value = preview.suggestion.reference;
      } else if (!state.references.length) {
        $("mode-new").checked = true;
      }
      applyMode();
      schedule(0);
    }
    markSuggestion(preview.suggestion);
    const hint = $("f-reference-hint");
    hint.textContent = preview.suggestion && $("f-reference").value === preview.suggestion.reference ? `Proposée : ${preview.suggestion.why}.` : "";

    // la version dont elle dérive
    const parentGroup = $("f-parent-group");
    const parent = $("f-parent");
    if (mode() === "existing" && preview.parents.length) {
      const current = parent.value;
      parent.innerHTML =
        `<option value="">Automatique${preview.base ? ` (${escapeHtml(preview.base)})` : ""}</option>` +
        preview.parents.map((p) => `<option value="${escapeHtml(p.number)}">${escapeHtml(p.number)} · ${escapeHtml(formatDate(p.published_at))}</option>`).join("");
      parent.value = preview.parents.some((p) => p.number === current) ? current : "";
      parentGroup.hidden = false;
    } else {
      parentGroup.hidden = true;
      parent.innerHTML = "";
    }

    // le résultat
    const name = preview.target.reference ? preview.target.reference.name : (preview.target.new_name || "").trim() || "Nouvelle référence";
    $("outcome").innerHTML = preview.number
      ? `<div class="promo-outcome__label">Deviendra</div>
         <div class="promo-outcome__ref"><span class="promo-outcome__r" aria-hidden="true">R</span>${escapeHtml(name)} <span class="ref-number">${escapeHtml(preview.number)}</span></div>
         <div class="promo-outcome__level">${escapeHtml(preview.level_text)}${preview.base ? ` depuis la ${escapeHtml(preview.base)}` : ""}</div>`
      : `<span class="help">${source.variants.length && source.variant === null ? "Choisissez la variante." : "Pas de numéro : voyez les vérifications."}</span>`;
    $("structure").innerHTML = source.structure_svg ? `<div class="promo-structure__svg">${source.structure_svg}</div>` : "";

    // les règles
    $("rules").innerHTML = preview.rules
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
    $("submit-btn").disabled = !preview.can_promote;
    $("submit-hint").textContent = blocking.length
      ? `${blocking.length} point${blocking.length > 1 ? "s" : ""} bloquant${blocking.length > 1 ? "s" : ""} : ${blocking[0].message}`
      : warnings.length
        ? `Prête, avec ${warnings.length} point${warnings.length > 1 ? "s" : ""} à savoir.`
        : "Prête.";
  }

  // -- les choix ---------------------------------------------------------------------------------

  function referenceOptions(selected) {
    $("f-reference").innerHTML =
      `<option value="">— Choisir une référence —</option>` +
      state.references
        .map((ref) => `<option value="${escapeHtml(ref.slug)}">${escapeHtml(ref.name)}${ref.latest_version ? ` · ${escapeHtml(ref.latest_version.number)}` : " · sans version"}</option>`)
        .join("");
    $("f-reference").value = selected || "";
  }

  function markSuggestion(suggestion) {
    [...$("f-reference").options].forEach((option) => {
      option.textContent = option.textContent.replace(/ \(proposée\)$/, "");
      if (suggestion && option.value === suggestion.reference) option.textContent += " (proposée)";
    });
  }

  function applyMode() {
    const isNew = mode() === "new";
    $("existing-group").hidden = isNew;
    $("new-group").hidden = !isNew;
  }

  async function loadStudies(microproject, selected) {
    const select = $("f-study");
    select.disabled = true;
    select.innerHTML = `<option value="">Chargement…</option>`;
    try {
      const page = await experimentsApi.list(microproject, { limit: 200 });
      state.studies = page.items;
      select.innerHTML =
        `<option value="">— Choisir l'étude —</option>` +
        page.items.map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.title || s.id)}</option>`).join("");
      if (selected && !page.items.some((s) => s.id === selected)) select.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(selected)}">${escapeHtml(selected)}</option>`);
      select.value = selected || "";
      select.disabled = false;
    } catch (err) {
      showError(err);
      select.innerHTML = `<option value="">—</option>`;
    }
  }

  $("f-microproject").addEventListener("change", async () => {
    $("f-variant-group").hidden = true;
    await loadStudies($("f-microproject").value, null);
    schedule(0);
  });
  $("f-study").addEventListener("change", () => {
    $("f-variant-group").hidden = true;
    $("f-variant").innerHTML = "";
    schedule(0);
  });
  $("f-variant").addEventListener("change", () => schedule(0));
  $("f-reference").addEventListener("change", () => {
    $("f-parent").value = "";
    schedule(0);
  });
  $("f-parent").addEventListener("change", () => schedule(0));
  document.querySelectorAll('input[name="target-mode"]').forEach((input) =>
    input.addEventListener("change", () => {
      applyMode();
      if (mode() === "new") $("f-name").focus();
      schedule(0);
    })
  );
  ["f-name", "f-description", "f-note"].forEach((id) => $(id).addEventListener("input", () => schedule()));

  // -- promouvoir --------------------------------------------------------------------------------

  $("promo-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = $("submit-btn");
    button.disabled = true;
    showError(null);
    try {
      const version = await promotionApi.promote(body());
      showDone(version);
      loadJournal();
    } catch (err) {
      showError(err);
      button.disabled = false;
      refresh();
    }
  });

  function backUrl() {
    const back = params.get("retour");
    return back && back.startsWith("/") && !back.startsWith("//") ? back : null;
  }

  function showDone(version) {
    const level = state.preview ? state.preview.level_text : "";
    const back = backUrl();
    $("promo-layout").hidden = true;
    const done = $("done");
    done.innerHTML = `
      <div class="promo-done__mark" aria-hidden="true">${PROMO_ICON}</div>
      <div class="promo-done__body">
        <h2 class="promo-done__title" id="done-title">Promue : <span class="promo-outcome__r" aria-hidden="true">R</span>${escapeHtml(version.reference.name)} <span class="ref-number">${escapeHtml(version.number)}</span></h2>
        <p class="promo-done__text">${escapeHtml(level || version.change_level)}${version.parent ? `, depuis la ${escapeHtml(version.parent)}` : ""}. Elle est maintenant proposée à tous les µprojets comme point de départ.</p>
        <div class="promo-done__actions">
          <a class="btn btn-primary" href="${referenceUrl(version.reference.slug, version.number)}">Voir la référence</a>
          ${back ? `<a class="btn btn-line" href="${escapeHtml(back)}">Revenir à la page d'avant</a>` : ""}
          <a class="btn btn-line" href="/promotion">Promouvoir une autre structure</a>
        </div>
      </div>`;
    done.hidden = false;
    done.focus();
  }

  const PROMO_ICON = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 3h12v18l-6-4-6 4Z"/><path d="m9.5 10 2 2 3.5-3.5"/></svg>';

  // -- le journal --------------------------------------------------------------------------------

  async function loadJournal() {
    const list = $("journal");
    try {
      const entries = await promotionApi.journal({ limit: 15 });
      list.innerHTML = entries.length
        ? entries.map(journalRow).join("")
        : `<li class="promo-journal__empty help">Aucune promotion pour l'instant.</li>`;
    } catch (err) {
      list.innerHTML = `<li class="promo-journal__empty help">${escapeHtml(err.message || String(err))}</li>`;
    }
  }

  function journalRow(entry) {
    const ref = `<span class="promo-outcome__r" aria-hidden="true">R</span>${escapeHtml(entry.reference.name)} <span class="ref-number">${escapeHtml(entry.number)}</span>`;
    const source = entry.source;
    const where = source.linked
      ? `<a href="${studyUrl(source.microproject.slug, source.experiment_id, source.version_id)}">${escapeHtml(source.title || source.experiment_id)}</a> · ${escapeHtml(source.microproject.name)}`
      : escapeHtml(source.microproject.name || "µprojet supprimé");
    const warnings = entry.warnings.length
      ? `<span class="promo-journal__warn" title="${escapeHtml(entry.warnings.map((w) => `${w.label} : ${w.message}`).join("\n"))}">${entry.warnings.length} à savoir</span>`
      : "";
    return `
      <li class="promo-journal__row">
        <span class="promo-journal__date">${escapeHtml(formatDate(entry.promoted_at))}</span>
        <span class="promo-journal__ref">${entry.reference.exists ? `<a href="${referenceUrl(entry.reference.slug, entry.number)}">${ref}</a>` : ref}${entry.created_reference ? ` <span class="promo-journal__new">nouvelle</span>` : ""}</span>
        <span class="promo-journal__source">${where}</span>
        <span class="promo-journal__by">${escapeHtml(entry.promoted_by || "—")} ${warnings}</span>
        ${entry.note ? `<span class="promo-journal__note">${escapeHtml(entry.note)}</span>` : ""}
      </li>`;
  }

  // -- amorce ------------------------------------------------------------------------------------

  async function init() {
    const back = backUrl();
    if (back) {
      $("back-link").href = back;
      $("back-link").hidden = false;
    }
    loadJournal();
    try {
      const [sources, references] = await Promise.all([promotionApi.sources(), referencesApi.list()]);
      state.references = references;
      referenceOptions(params.get("reference"));
      const wanted = params.get("microprojet");
      const select = $("f-microproject");
      select.innerHTML =
        `<option value="">— Choisir le µprojet —</option>` + sources.map((m) => `<option value="${escapeHtml(m.slug)}">${escapeHtml(m.name)}</option>`).join("");
      // un µprojet où l'on n'est pas éditeur : la règle « Droit de promouvoir » le dira
      if (wanted && !sources.some((m) => m.slug === wanted)) select.insertAdjacentHTML("beforeend", `<option value="${escapeHtml(wanted)}">${escapeHtml(wanted)}</option>`);
      select.value = wanted || "";
      if (!sources.length && !wanted) $("submit-hint").textContent = "Vous n'êtes éditeur d'aucun µprojet : promouvoir demande ce rôle.";
      if (select.value) await loadStudies(select.value, params.get("etude"));
      applyMode();
      await refresh();
    } catch (err) {
      showError(err);
    }
  }

  init();
})();
