/* Commentaires d'étape et rapport pas à pas du constructeur (plugin step_report).

   Deux choses, toutes deux branchées sur le constructeur sans qu'il en dépende :

   - le champ « Commentaire » de l'inspecteur d'étape : un texte libre rangé sous l'id de l'étape
     (stepReportApi), enregistré au fil de la frappe. Seulement en mode expérience : l'id d'une étape
     n'y survit qu'avec l'étude (une structure de bibliothèque, une brique ou un préset ne gardent pas
     les ids). Une puce du flow qui porte un commentaire a un point doré.
   - le bouton « Rapport étape par étape » de la barre d'édition : télécharge un diaporama HTML
     (report-html.js), fabriqué ici (report-core.js) de ce que le constructeur a à l'écran - le
     dessin de chaque étape (state.frames), ses paramètres (les paramètres déclarés marqués), son
     commentaire et la légende des matériaux (state.materialColors). La fiche d'une étude fait le
     même rapport de son procédé enregistré (study-report.js).

   Le constructeur appelle `StepReport.sync()` quand le flow, la sélection ou les ids d'étape
   changent (renderRail, renderStepInspector, après une simulation) ; rien d'autre. */

const StepReport = (() => {
  const SAVE_DELAY_MS = 700;
  const MAX_LENGTH = 4000;
  const HINT = "Pourquoi cette étape, ce qu'on y a observé, ce qui reste à vérifier…";

  const cache = new Map(); // id d'étape -> texte ("" : on sait qu'il n'y en a pas)
  const asked = new Set(); // ids déjà demandés au serveur (ou en cours)
  const pending = new Map(); // id -> minuterie d'une écriture à venir
  let panel = null; // {root, text, status}
  let boundId = null; // l'id d'étape que le champ montre

  // Les commentaires n'ont de sens qu'en mode expérience (voir l'en-tête).
  function commentsAvailable() {
    return !isLibraryMode && !isBrickMode && !isPresetMode;
  }

  // ---------------------------------------------------------------------------------------------
  // Commentaires : lecture, écriture
  // ---------------------------------------------------------------------------------------------

  async function load(ids) {
    const wanted = ids.filter((id) => !asked.has(id));
    if (!wanted.length) return;
    wanted.forEach((id) => asked.add(id));
    try {
      for (let i = 0; i < wanted.length; i += 400) {
        const batch = wanted.slice(i, i + 400);
        const found = (await stepReportApi.list(slug, batch)).comments || {};
        batch.forEach((id) => {
          if (!pending.has(id)) cache.set(id, found[id] ? found[id].text : "");
        });
      }
    } catch (err) {
      wanted.forEach((id) => asked.delete(id)); // au prochain sync
      return;
    }
    decorateChips();
    renderPanel();
  }

  async function save(id) {
    pending.delete(id);
    const text = cache.get(id) || "";
    setStatus(id, "Enregistrement…");
    try {
      await stepReportApi.put(slug, id, text);
      setStatus(id, text ? "Enregistré" : "");
    } catch (err) {
      setStatus(id, err.status === 403 ? "Lecture seule : commentaire non enregistré." : `Non enregistré : ${err.message}`, true);
    }
  }

  function schedule(id) {
    if (pending.has(id)) clearTimeout(pending.get(id));
    pending.set(id, setTimeout(() => save(id), SAVE_DELAY_MS));
  }

  // Écrit tout de suite ce qui attend (changement d'étape, perte du focus).
  function flush(keepalive = false) {
    [...pending.keys()].forEach((id) => {
      clearTimeout(pending.get(id));
      pending.delete(id);
      if (keepalive) stepReportApi.put(slug, id, cache.get(id) || "", { keepalive: true }).catch(() => {});
      else save(id);
    });
  }

  // ---------------------------------------------------------------------------------------------
  // Le champ de l'inspecteur
  // ---------------------------------------------------------------------------------------------

  function ensurePanel() {
    if (panel && panel.root.isConnected) return panel;
    const body = document.querySelector("#step-form-section .sb-insp__body");
    if (!body) return null;
    const root = document.createElement("div");
    root.className = "sbr-comment";
    root.innerHTML =
      '<label for="sbr-comment-text">Commentaire de l\'étape</label>' +
      `<textarea class="field" id="sbr-comment-text" rows="3" maxlength="${MAX_LENGTH}" placeholder="${HINT}"></textarea>` +
      '<div class="sbr-comment__foot"><span class="help">Repris dans le rapport étape par étape.</span><span class="sbr-comment__status" role="status" aria-live="polite"></span></div>';
    body.appendChild(root);
    panel = { root, text: root.querySelector("textarea"), status: root.querySelector(".sbr-comment__status") };
    panel.text.addEventListener("input", () => {
      if (!boundId) return;
      cache.set(boundId, panel.text.value);
      setStatus(boundId, "Modifié…");
      schedule(boundId);
      decorateChips();
    });
    panel.text.addEventListener("blur", () => flush());
    return panel;
  }

  function setStatus(id, message, isError = false) {
    if (!panel || id !== boundId) return;
    panel.status.textContent = message;
    panel.status.classList.toggle("is-error", isError);
  }

  function selectedStep() {
    const i = state.selectedIndex;
    return state.wizardScreen !== "variations" && i >= 0 && i < state.steps.length ? state.steps[i] : null;
  }

  function renderPanel() {
    const p = ensurePanel();
    if (!p) return;
    const step = selectedStep();
    p.root.hidden = !commentsAvailable() || !step;
    if (p.root.hidden) return;
    const id = step.id || null;
    if (id !== boundId) {
      flush();
      boundId = id;
      p.status.textContent = "";
      p.text.value = id && cache.has(id) ? cache.get(id) : "";
    } else if (id && document.activeElement !== p.text && cache.has(id) && p.text.value !== cache.get(id)) {
      p.text.value = cache.get(id);
    }
    const ready = Boolean(id) && cache.has(id);
    p.text.disabled = !ready;
    p.text.placeholder = id ? HINT : "Disponible dès que la structure est simulée.";
  }

  // Un point doré sur les puces du flow qui portent un commentaire (le flow est reconstruit à chaque rendu).
  function decorateChips() {
    if (!commentsAvailable()) return;
    state.steps.forEach((step, i) => {
      const chip = document.getElementById(`sb-chip-${i}`);
      if (chip) chip.classList.toggle("has-comment", Boolean(step.id && (cache.get(step.id) || "").trim()));
    });
  }

  // À appeler quand le flow, la sélection ou les ids d'étape ont changé.
  function sync() {
    if (!commentsAvailable()) return;
    load(state.steps.map((s) => s.id).filter(Boolean));
    decorateChips();
    renderPanel();
  }

  // ---------------------------------------------------------------------------------------------
  // Le rapport
  // ---------------------------------------------------------------------------------------------

  function reportTitle() {
    const named = ["exp-title", "library-name", "brick-name", "preset-name"].map((id) => document.getElementById(id)).find((el) => el && el.value.trim());
    return named ? named.value.trim() : `Process flow — ${slug}`;
  }

  // Les données du rapport, de ce que le constructeur a à l'écran (le procédé, ses images simulées).
  function collect(logoSvg) {
    return StepReportCore.buildReport({
      title: reportTitle(),
      subtitle: `µprojet ${slug}`,
      logoSvg,
      substrate: substrateSpec(),
      steps: state.steps.map((step) => ({ step, declared: step.declaredParams })),
      frames: state.frames,
      colors: state.materialColors,
      comments: commentsAvailable() ? Object.fromEntries(state.steps.filter((s) => s.id).map((s) => [s.id, cache.get(s.id) || ""])) : null,
    });
  }

  // Attend que la simulation en cours (ou sur le point de partir) ait rendu son dessin.
  async function settled() {
    for (let waited = 0; waited < 60000; waited += 100) {
      if (!simulating && !simulateTimer && !simulateAgain) return;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
  }

  async function download() {
    clearError();
    flush();
    await settled();
    if (!state.frames || state.frames.length < 2 || state.frames.length !== state.steps.length + 1) {
      showError(new Error("Le rapport se fait d'une structure simulée : ajoutez une étape et attendez le dessin."));
      return;
    }
    if (commentsAvailable()) {
      const ids = state.steps.map((s) => s.id).filter(Boolean);
      asked.clear();
      await load(ids).catch(() => {});
    }
    StepReportCore.download(collect(await StepReportCore.loadLogo()));
  }

  function mountButton() {
    const bar = document.querySelector(".sb-iconbar");
    if (!bar || document.getElementById("step-report-btn")) return;
    const button = document.createElement("button");
    button.className = "sb-iconbtn";
    button.id = "step-report-btn";
    button.type = "button";
    button.title = "Télécharger le rapport étape par étape (diaporama HTML)";
    button.setAttribute("aria-label", "Télécharger le rapport étape par étape");
    button.innerHTML =
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/><path d="m9 10 2 2 4-4"/></svg>';
    button.addEventListener("click", () => download().catch(showError));
    bar.insertBefore(button, document.getElementById("shortcuts-btn"));
  }

  mountButton();
  window.addEventListener("pagehide", () => flush(true));

  return { sync };
})();
