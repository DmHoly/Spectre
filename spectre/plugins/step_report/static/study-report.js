/* Le rapport pas à pas depuis la fiche d'une étude (plugin step_report) : un bouton « Rapport pas à
   pas » au-dessus de la structure, qui télécharge le diaporama HTML du procédé de la version affichée
   (la pointe, ou la version passée qu'on regarde) - le même que celui du constructeur, fait ici du
   procédé enregistré : on le simule (POST /api/simulations) pour avoir le dessin de chaque étape, et on
   y joint les commentaires de ses étapes (leurs ids sont ceux de l'étude, d'une version à l'autre).
   Rien pour une structure en images ni une expérience sans structure : elles n'ont pas de procédé. */

(() => {
  const LABEL = "Rapport pas à pas";
  const ICON =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8"/><path d="M12 16v4"/><path d="m9 10 2 2 4-4"/></svg>';

  // Les commentaires des étapes, par paquets (au plus 500 ids par appel côté serveur).
  async function loadComments(slug, ids) {
    const comments = {};
    for (let i = 0; i < ids.length; i += 400) {
      const found = (await stepReportApi.list(slug, ids.slice(i, i + 400))).comments || {};
      Object.values(found).forEach((comment) => (comments[comment.step_id] = comment.text));
    }
    return comments;
  }

  async function generate(ctx) {
    const process = ctx.process;
    const simulated = await structuresApi.simulate({
      substrate: process.substrate,
      steps: process.steps,
      declared_params: process.declared_params || {},
      layer_labels: process.layer_labels || {},
      recipes: process.recipes,
      bricks: process.bricks || [],
      preset_origins: process.preset_origins || {},
    });
    const [comments, logoSvg] = await Promise.all([loadComments(ctx.microprojectSlug, process.steps.map((s) => s.id).filter(Boolean)), StepReportCore.loadLogo()]);
    StepReportCore.download(
      StepReportCore.buildReport({
        title: ctx.detail.title || `Étude ${ctx.experimentId}`,
        subtitle: `µprojet ${ctx.microproject.name}${ctx.isTip ? "" : " · version passée"}`,
        logoSvg,
        substrate: process.substrate,
        steps: process.steps.map((step, i) => ({ step, declared: (process.declared_params || {})[String(i)] })),
        frames: simulated.frames,
        colors: simulated.material_colors,
        comments,
      })
    );
  }

  ExperiencePage.registerPanel({
    key: "step-report",
    mount(el, ctx) {
      el.innerHTML = "";
      if (!ctx.process || !(ctx.process.steps || []).length) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-line";
      button.style.cssText = "min-height:32px;padding:5px 12px;font-size:12.5px;";
      button.title = "Télécharger le procédé de cette version, étape par étape, en diaporama HTML (dessin, paramètres, commentaires, code couleur)";
      button.innerHTML = `${ICON} ${LABEL}`;
      button.addEventListener("click", async () => {
        button.disabled = true;
        button.lastChild.textContent = " Génération…";
        try {
          await generate(ctx);
        } catch (err) {
          ctx.showError(err);
        } finally {
          button.disabled = false;
          button.lastChild.textContent = ` ${LABEL}`;
        }
      });
      el.appendChild(button);
    },
  });
})();
