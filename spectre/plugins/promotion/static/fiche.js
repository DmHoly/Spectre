/* La promotion sur la fiche d'une étude (deux panneaux de ExperiencePage, plugin experiments) :

   - « promotion-action » : le bouton « Promouvoir comme référence » en tête de fiche, à côté de
     « Éditer la fiche » - toujours là, quelle que soit la structure (un split : la variante se
     choisit dans le formulaire ; une structure en images : le formulaire dit pourquoi elle ne peut
     pas l'être) et sur une version passée (c'est elle qu'on promeut) ;
   - « promotion » : le bloc « Référence » à droite de l'en-tête - les versions de référence promues
     depuis cette étude (« R Epi standard 1.2 »), ou, quand la conclusion a décidé de la retenir et
     que rien n'est encore promu, l'appel à le faire. */

(() => {
  const enabled = () => pluginEnabled("promotion") && pluginEnabled("references");

  function target(ctx, variant) {
    return {
      microproject: ctx.microprojectSlug,
      experimentId: ctx.experimentId,
      versionId: ctx.isTip ? null : ctx.versionId,
      variant,
    };
  }

  ExperiencePage.registerPanel({
    key: "promotion-action",
    mount(el, ctx) {
      el.innerHTML = enabled() ? PromotionLink.html(target(ctx)) : "";
    },
  });

  ExperiencePage.registerPanel({
    key: "promotion",
    async mount(el, ctx) {
      if (!enabled()) {
        el.hidden = true;
        return;
      }
      let published = [];
      try {
        published = (await referencesApi.publishedFrom(ctx.microprojectSlug)).filter((entry) => entry.experiment_id === ctx.experimentId);
      } catch (err) {
        published = [];
      }
      const decided = ctx.detail.conclusion && ctx.detail.conclusion.decision === "promote";
      el.hidden = false;
      if (published.length) {
        const badges = published
          .map((entry) => {
            const variant = entry.variant !== null && entry.variant !== undefined ? ` · variante ${entry.variant + 1}` : "";
            return `<a class="promo-badge" href="/references/${encodeURIComponent(entry.reference.slug)}?version=${encodeURIComponent(entry.number)}" title="Promue le ${escapeHtml(formatDate(entry.published_at))}">R ${escapeHtml(entry.reference.name)} ${escapeHtml(entry.number)}${escapeHtml(variant)}</a>`;
          })
          .join("");
        el.innerHTML = `
          <div class="promo-panel">
            <div class="promo-panel__label">Référence</div>
            <div class="promo-panel__badges">${badges}</div>
            <p class="promo-panel__text">Promue depuis cette étude${published.length > 1 ? ` (${published.length} versions)` : ""}.</p>
          </div>`;
      } else if (decided) {
        el.innerHTML = `
          <div class="promo-panel promo-panel--call">
            <div class="promo-panel__label">Référence</div>
            <p class="promo-panel__text">La conclusion retient cette structure comme référence : elle n'est pas encore promue.</p>
            <div>${PromotionLink.html(target(ctx), { compact: true, label: "Promouvoir maintenant" })}</div>
          </div>`;
      } else {
        el.innerHTML = `
          <div class="promo-panel">
            <div class="promo-panel__label">Référence</div>
            <p class="promo-panel__text">Pas encore promue comme référence.</p>
          </div>`;
      }
    },
  });
})();
