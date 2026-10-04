/* La carte « Versions du procédé » : la frise des versions de structure (X.Y.Z), l'historique complet
   de la piste (données, étiquettes, titres... en retrait), les pistes qui partent de la version
   affichée et ses liens (référence, témoin, source combinée...). Une version passée s'ouvre en
   lecture (?version=). */

(() => {
  const REFERENCE_ROLE_LABELS = {
    baseline: "Référence",
    control: "Témoin",
    prior_art: "Antériorité",
    benchmark: "Point de comparaison",
    target_spec: "Spécification cible",
    merge_source: "Source combinée",
  };

  // Niveau de changement de procédé/structure -> libellé à côté du numéro de version ; « none » (rien
  // n'a bougé dans la structure) n'apparaît que dans l'historique complet.
  const CHANGE_LEVEL_LABELS = {
    initial: "version initiale",
    major: "changement majeur",
    minor: "changement mineur",
    patch: "ajustement mineur",
  };

  // `item.is_tip` vient du serveur, jamais de la position dans la liste : la frise omet des entrées.
  // Une version, même héritée de la piste d'où celle-ci part, s'ouvre dans cette piste-ci.
  function itemHtml(ctx, item, extraClass = "") {
    const shown = item.version_id === ctx.versionId;
    const url = ExperiencePage.pageUrl({ ...item, experiment_id: ctx.experimentId }) + window.location.hash;
    const date = item.is_tip
      ? `${ctx.isTip ? formatDate(item.created_at) : `<a href="${url}">${formatDate(item.created_at)}</a>`} · version actuelle`
      : `<a href="${url}">${formatDate(item.created_at)}</a>${shown ? " · version affichée" : ""}`;
    return `
      <div class="timeline-item ${item.is_tip ? "current" : ""} ${extraClass}">
        <div class="timeline-date">${date} <span class="timeline-version" title="${escapeHtml(CHANGE_LEVEL_LABELS[item.change_level] || "")}">v${escapeHtml(item.version)}</span></div>
        <div class="timeline-title">${escapeHtml(item.title)}</div>
        <div class="timeline-desc">${escapeHtml(item.intent)}</div>
      </div>`;
  }

  // la plus récente d'abord : les dernières sont visibles sans faire défiler
  function renderTimelines(ctx) {
    const recentFirst = [...ctx.versions].reverse();
    document.getElementById("timeline").innerHTML = recentFirst
      .filter((item) => item.change_level !== "none")
      .map((item) => itemHtml(ctx, item))
      .join("");
    document.getElementById("full-history").innerHTML = recentFirst
      .map((item) => itemHtml(ctx, item, item.change_level === "none" ? "no-version-change" : ""))
      .join("");
  }

  function renderForks(ctx) {
    const box = document.getElementById("forks-note");
    const children = ctx.detail.children;
    box.style.display = children.length < 2 ? "none" : "block";
    if (children.length < 2) return;
    box.innerHTML = `
      <div style="font-size:12px;color:var(--text-faint);margin-bottom:6px;">Cette version a donné plusieurs pistes :</div>
      ${children.map((c) => `<div style="font-size:13px;margin-bottom:4px;"><a href="${ExperiencePage.pageUrl(c)}">${escapeHtml(c.title)}</a></div>`).join("")}
      <a href="/microprojets/${encodeURIComponent(ctx.microprojectSlug)}" style="font-size:12px;">Voir le µprojet &rarr;</a>`;
  }

  // Une version à deux parents (une combinaison) : ses deux études d'origine plutôt qu'une
  // « référence » et une « source combinée ».
  const COMBINATION_ROLE_LABELS = {
    baseline: "Combinaison de - structure reprise",
    merge_source: "Combinaison de",
  };

  function renderReferences(ctx) {
    const references = ctx.detail.references;
    const combined = (ctx.detail.parents || []).length > 1;
    document.getElementById("references-card").style.display = references.length ? "" : "none";
    document.getElementById("references-list").innerHTML = references
      .map((r) => {
        const target = r.experiment_id ? `<a href="${ExperiencePage.pageUrl({ experiment_id: r.experiment_id, is_tip: true })}">${escapeHtml(r.label)}</a>` : escapeHtml(r.label);
        const role = (combined && COMBINATION_ROLE_LABELS[r.role]) || REFERENCE_ROLE_LABELS[r.role] || r.role;
        return `<div style="font-size:13px;margin-bottom:8px;"><span style="color:var(--text-faint);font-size:11px;text-transform:uppercase;letter-spacing:.02em;">${escapeHtml(role)}</span><br>${target}</div>`;
      })
      .join("");
  }

  ExperiencePage.registerPanel({
    key: "versions",
    mount(el, ctx) {
      renderTimelines(ctx);
      renderForks(ctx);
      renderReferences(ctx);
    },
  });
})();
