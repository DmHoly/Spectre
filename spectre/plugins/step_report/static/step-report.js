/* Commentaires d'étape et rapport pas à pas du constructeur (plugin step_report).

   Deux choses, toutes deux branchées sur le constructeur sans qu'il en dépende :

   - le champ « Commentaire » de l'inspecteur d'étape : un texte libre. Dans une expérience, il est rangé
     sous l'id de l'étape (stepReportApi) et enregistré au fil de la frappe ; dans une structure de la
     bibliothèque (qui ne garde pas les ids), il vit sur l'étape (`step.comment`) et s'enregistre avec
     la structure (`step_comments`, par rang d'étape : StepReport.commentsPayload / .attach). Une
     structure de la bibliothèque dont on part pour une expérience lui passe ses commentaires. Pas de
     commentaire dans une brique ou un préset. Une puce du flow qui porte un commentaire a un point doré.
   - le bouton « Rapport étape par étape » de la barre d'édition : télécharge un diaporama HTML
     (report-html.js), fabriqué ici (report-core.js) de ce que le constructeur a à l'écran - le
     dessin de chaque étape (state.frames), ses paramètres (les paramètres déclarés marqués), son
     commentaire et la légende des matériaux (state.materialColors). La fiche d'une étude fait le
     même rapport de son procédé enregistré (study-report.js).

   Le constructeur appelle `StepReport.sync()` quand le flow, la sélection ou les ids d'étape
   changent (renderRail, renderStepInspector, après une simulation), et `attach` / `commentsPayload`
   là où il lit et enregistre une structure de la bibliothèque. */

const StepReport = (() => {
  const SAVE_DELAY_MS = 700;
  const MAX_LENGTH = 4000;
  const HINT = "Pourquoi cette étape, ce qu'on y a observé, ce qui reste à vérifier…";

  const cache = new Map(); // id d'étape -> texte ("" : on sait qu'il n'y en a pas)
  const asked = new Set(); // ids déjà demandés au serveur (ou en cours)
  const pending = new Map(); // id -> minuterie d'une écriture à venir
  let panel = null; // {root, text, status, foot}
  let bound = null; // ce que le champ montre : l'id de l'étape (mode « server »), son rang (mode « local »)

  // Où vit le commentaire :
  //   "server" - une expérience : sous l'id de l'étape, côté serveur (stepReportApi), enregistré au fil de la frappe ;
  //   "local"  - une structure de la bibliothèque : sur l'étape elle-même (step.comment), enregistré avec la
  //              structure (`step_comments`, par rang d'étape) - elle ne garde pas les ids d'étape ;
  //   null     - une brique, un préset : pas de commentaire.
  function mode() {
    if (isBrickMode || isPresetMode) return null;
    return isLibraryMode ? "local" : "server";
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

  // Les commentaires d'une structure de la bibliothèque, par rang d'étape (le corps de l'enregistrement).
  function commentsPayload(steps) {
    const out = {};
    steps.forEach((step, i) => {
      if (typeof step.comment === "string" && step.comment.trim()) out[i] = step.comment.trim();
    });
    return out;
  }

  // Pose les commentaires qu'une structure a gardés (`step_comments`, par rang) sur ses étapes.
  function attach(steps, comments) {
    if (!comments) return steps;
    return steps.map((step, i) => (comments[i] || comments[String(i)] ? { ...step, comment: comments[i] || comments[String(i)] } : step));
  }

  // Les étapes qui arrivent avec un commentaire (parties d'une structure de la bibliothèque) et qui ont
  // maintenant leur id : le commentaire passe côté serveur, sous cet id, et quitte l'étape.
  function adoptSeeds() {
    state.steps.forEach((step) => {
      if (!step.id || typeof step.comment !== "string") return;
      if (step.comment.trim() && !asked.has(step.id)) {
        asked.add(step.id);
        cache.set(step.id, step.comment.trim());
        schedule(step.id);
      }
      delete step.comment;
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
      '<div class="sbr-comment__foot"><span class="help"></span><span class="sbr-comment__status" role="status" aria-live="polite"></span></div>';
    // en tête de l'inspecteur, sous le préset : au bas d'un formulaire long, il passait inaperçu
    const anchor = document.getElementById("step-preset-panel");
    body.insertBefore(root, anchor ? anchor.nextSibling : body.firstChild);
    panel = { root, text: root.querySelector("textarea"), status: root.querySelector(".sbr-comment__status"), foot: root.querySelector(".sbr-comment__foot") };
    panel.text.addEventListener("input", () => {
      if (bound === null) return;
      if (mode() === "local") {
        const step = state.steps[bound];
        if (!step) return;
        if (panel.text.value) step.comment = panel.text.value;
        else delete step.comment;
        setStatus(bound, "Sera enregistré avec la structure");
      } else {
        cache.set(bound, panel.text.value);
        setStatus(bound, "Modifié…");
        schedule(bound);
      }
      decorateChips();
    });
    panel.text.addEventListener("change", () => {
      if (mode() === "local" && typeof captureHistory === "function") captureHistory(); // la saisie retenue entre dans l'historique
    });
    panel.text.addEventListener("blur", () => flush());
    return panel;
  }

  function setStatus(key, message, isError = false) {
    if (!panel || key !== bound) return;
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
    p.root.hidden = !step;
    if (p.root.hidden) return;
    const where = mode();
    p.text.hidden = where === null;
    p.foot.querySelector(".help").textContent =
      where === "server"
        ? "Repris dans le rapport étape par étape."
        : where === "local"
          ? "Enregistré avec la structure · repris dans le rapport."
          : "Les commentaires se saisissent dans une expérience ou une structure de la bibliothèque : une brique ou un préset ne les gardent pas.";
    if (where === null) return;
    if (where === "local") {
      const index = state.selectedIndex;
      if (index !== bound) {
        bound = index;
        p.status.textContent = "";
        p.text.value = step.comment || "";
      } else if (document.activeElement !== p.text && p.text.value !== (step.comment || "")) {
        p.text.value = step.comment || "";
      }
      p.text.disabled = false;
      p.text.placeholder = HINT;
      return;
    }
    const id = step.id || null;
    if (id !== bound) {
      flush();
      bound = id;
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
    const where = mode();
    if (!where) return;
    state.steps.forEach((step, i) => {
      const chip = document.getElementById(`sb-chip-${i}`);
      const text = where === "local" ? step.comment : step.id && cache.get(step.id);
      if (chip) chip.classList.toggle("has-comment", Boolean((text || "").trim()));
    });
  }

  // À appeler quand le flow, la sélection ou les ids d'étape ont changé.
  function sync() {
    if (mode() === "server") {
      adoptSeeds();
      load(state.steps.map((s) => s.id).filter(Boolean));
    }
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
      comments: mode() === "server"
        ? Object.fromEntries(state.steps.filter((s) => s.id).map((s) => [s.id, cache.get(s.id) || ""]))
        : mode() === "local"
          ? Object.fromEntries(state.steps.filter((s) => s.id).map((s) => [s.id, s.comment || ""]))
          : null,
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
    if (mode() === "server") {
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

  return { sync, attach, commentsPayload };
})();
