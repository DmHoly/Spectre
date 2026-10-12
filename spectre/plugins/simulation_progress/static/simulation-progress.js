/* La barre de chargement du constructeur (plugin simulation_progress) : tant qu'une simulation tourne,
   une barre fine borde le haut de la zone de dessin et une pastille dit l'étape en cours ("Étape 4 / 12
   · Croissance p-GaN") et le temps écoulé.

   Le constructeur (builder/simulation.js) démarre un suivi par simulation :

     const run = SimulationProgress.start();     // run.id : à passer à structuresApi.simulate(body, run.id)
     ...
     run.stop();                                 // la simulation est revenue (ou a échoué)

   Le suivi interroge le serveur toutes les POLL_MS ; la barre n'apparaît qu'à la première réponse
   « en cours » - une simulation rapide n'en montre rien - et s'efface un instant après stop(), sans
   clignoter quand une autre simulation repart aussitôt. */

const SimulationProgress = (() => {
  const POLL_MS = 250;
  const HIDE_DELAY_MS = 400; // plus long qu'un sondage : la simulation suivante reprend la même barre
  const FALLBACK_STEP_SECONDS = 2; // durée supposée d'une étape tant qu'aucune n'a été calculée
  const CURRENT_STEP_SHARE_MAX = 0.9; // l'étape en cours ne remplit jamais plus que ça de sa part

  let bar = null; // {root, fill, step, time}
  let hideTimer = null;

  function newRunId() {
    const bytes = new Uint8Array(12);
    crypto.getRandomValues(bytes); // et non randomUUID : absent hors contexte sécurisé (http)
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function ensureBar() {
    if (bar && bar.root.isConnected) return bar;
    const canvas = document.getElementById("sb-canvas");
    if (!canvas) return null;
    const root = document.createElement("div");
    root.className = "sbp";
    root.hidden = true;
    root.setAttribute("role", "progressbar");
    root.setAttribute("aria-label", "Progression de la simulation");
    root.setAttribute("aria-valuemin", "0");
    root.setAttribute("aria-valuemax", "100");
    root.innerHTML =
      '<div class="sbp__track"><div class="sbp__fill"></div></div>' +
      '<div class="sbp__pill"><span class="sbp__step"></span><span class="sbp__time"></span></div>';
    canvas.appendChild(root);
    bar = { root, canvas, fill: root.querySelector(".sbp__fill"), step: root.querySelector(".sbp__step"), time: root.querySelector(".sbp__time") };
    return bar;
  }

  function show() {
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }
    const b = ensureBar();
    if (!b) return null;
    b.root.hidden = false;
    b.canvas.classList.add("has-progress"); // la pastille remplace le « Simulation… » de la barre d'outils
    return b;
  }

  function hide() {
    hideTimer = null;
    if (!bar) return;
    bar.root.hidden = true;
    bar.canvas.classList.remove("has-progress");
    bar.fill.style.width = "0";
  }

  function scheduleHide() {
    if (!bar || bar.root.hidden) return;
    bar.fill.style.width = "100%";
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, HIDE_DELAY_MS);
  }

  function seconds(value) {
    return `${value.toFixed(1).replace(".", ",")} s`;
  }

  // Part de la barre déjà faite : les étapes finies, plus une part de l'étape en cours qui monte
  // vers - sans jamais atteindre - la fin de la sienne, au rythme moyen des étapes calculées jusqu'ici.
  function fractionOf(progress, stepSeconds) {
    if (progress.total === 0) return 1;
    if (progress.state === "done") return 1;
    const computed = progress.done - progress.resumed;
    const average = computed > 0 ? progress.elapsed / computed : FALLBACK_STEP_SECONDS;
    const current = progress.step ? Math.min(CURRENT_STEP_SHARE_MAX, 1 - Math.exp(-stepSeconds / Math.max(average, 0.2))) : 0;
    return Math.min(1, (progress.done + current) / progress.total);
  }

  function render(progress, stepSeconds) {
    const b = show();
    if (!b) return;
    const percent = Math.round(fractionOf(progress, stepSeconds) * 100);
    b.fill.style.width = `${percent}%`;
    b.root.setAttribute("aria-valuenow", String(percent));
    const label = progress.step
      ? `Étape ${progress.step.index + 1} / ${progress.total}${progress.step.name ? ` · ${progress.step.name}` : ""}`
      : progress.done > 0
        ? `${progress.done} / ${progress.total} étapes`
        : "Reprise…";
    b.step.textContent = label;
    b.time.textContent = seconds(progress.elapsed);
    b.root.setAttribute("aria-valuetext", label);
    b.root.title = progress.resumed > 0 ? `${progress.resumed} étape${progress.resumed > 1 ? "s" : ""} déjà calculée${progress.resumed > 1 ? "s" : ""}, reprise${progress.resumed > 1 ? "s" : ""} sans recalcul` : "";
  }

  function start() {
    const id = newRunId();
    let stopped = false;
    let timer = null;
    let lastDone = -1;
    let stepSince = performance.now();

    async function tick() {
      try {
        const progress = await simulationProgressApi.get(id);
        if (stopped) return;
        if (progress.done !== lastDone) {
          lastDone = progress.done;
          stepSince = performance.now();
        }
        if (progress.state === "running") render(progress, (performance.now() - stepSince) / 1000);
      } catch (err) {
        // pas encore partie (404), ou le réseau a bronché : la barre attend le sondage suivant
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS);
    }

    timer = setTimeout(tick, POLL_MS);
    return {
      id,
      stop() {
        stopped = true;
        clearTimeout(timer);
        scheduleHide();
      },
    };
  }

  return { start };
})();
