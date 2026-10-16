/* La configuration des KPI suivis d'un µprojet (spectre.plugins.kpi_tracking), partagée par l'onglet
   « Configuration » de la page d'un µprojet et par la page « KPI » du menu Data : la liste des KPI suivis
   (renommer, ne plus suivre) et celle des KPI que PRISM propose (suivre). Le montage ne dessine que dans
   les deux éléments qu'on lui donne ; erreurs et changements remontent par `showError` et `onChange`. */

function mountKpiConfig({ slug, canEdit, catalog, tracked, trackedEl, catalogEl, showError, clearError, onChange }) {
  let current = tracked;

  function renderTracked() {
    if (!current.length) {
      trackedEl.innerHTML = `<p class="help">Aucun KPI suivi pour l'instant${canEdit ? " : choisissez-en dans la liste ci-dessous." : "."}</p>`;
      return;
    }
    trackedEl.innerHTML = current
      .map(
        (k) => `<div class="kt-row" data-id="${k.id}">
          <div>
            <div class="kt-row__name">${escapeHtml(k.title)}</div>
            <div class="kt-row__meta">${escapeHtml(k.hook_title)} · ${escapeHtml(k.column)}${k.unit ? ` · ${escapeHtml(k.unit)}` : ""}${k.available ? "" : ' · <span class="kt-row__missing">n\'est plus dans PRISM</span>'}</div>
          </div>
          <div>${canEdit ? `<input type="text" class="field" data-rename="${k.id}" value="${escapeHtml(k.label)}" maxlength="80" placeholder="Nom affiché (par défaut : ${escapeHtml(k.column)})" aria-label="Nom affiché de ${escapeHtml(k.title)}">` : ""}</div>
          <div>${canEdit ? `<button class="btn btn-line" type="button" data-untrack="${k.id}">Ne plus suivre</button>` : ""}</div>
        </div>`
      )
      .join("");
  }

  function renderCatalog() {
    if (!catalog.length) {
      catalogEl.innerHTML = `<p class="help">PRISM ne propose aucun KPI par plaque pour l'instant.</p>`;
      return;
    }
    const followed = new Set(current.map((k) => `${k.hook}:${k.column}`));
    const byHook = new Map();
    for (const k of catalog) {
      if (!byHook.has(k.hook)) byHook.set(k.hook, { title: k.hook_title, items: [] });
      byHook.get(k.hook).items.push(k);
    }
    catalogEl.innerHTML = [...byHook.entries()]
      .map(
        ([hook, group]) => `<div class="kt-group">
          <div class="kt-group__title">${escapeHtml(group.title)}<span class="kt-group__hook">${escapeHtml(hook)}</span></div>
          ${group.items
            .map(
              (k) => `<div class="kt-row kt-row--catalog">
                <div class="kt-row__name">${escapeHtml(k.column)}${k.unit ? ` <span class="kt-row__meta">${escapeHtml(k.unit)}</span>` : ""}</div>
                <div class="kt-row__desc">${escapeHtml(k.description || "")}</div>
                <div>${
                  followed.has(k.key)
                    ? '<span class="badge badge-concluded"><span class="dot"></span>Suivi</span>'
                    : canEdit
                      ? `<button class="btn btn-tint" type="button" data-track="${escapeHtml(k.key)}">Suivre</button>`
                      : ""
                }</div>
              </div>`
            )
            .join("")}
        </div>`
      )
      .join("");
  }

  function render() {
    renderTracked();
    renderCatalog();
  }

  async function run(action) {
    clearError();
    try {
      await action();
    } catch (err) {
      showError(err);
    }
  }

  async function reload() {
    current = await kpiTrackingApi.list(slug);
    render();
    onChange(current);
  }

  catalogEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-track]");
    const entry = button && catalog.find((k) => k.key === button.dataset.track);
    if (!entry) return;
    button.disabled = true;
    run(async () => {
      try {
        await kpiTrackingApi.track(slug, { hook: entry.hook, column: entry.column });
      } finally {
        await reload();
      }
    });
  });

  trackedEl.addEventListener("click", (event) => {
    const button = event.target.closest("[data-untrack]");
    if (!button) return;
    button.disabled = true;
    run(async () => {
      try {
        await kpiTrackingApi.untrack(slug, button.dataset.untrack);
      } finally {
        await reload();
      }
    });
  });

  trackedEl.addEventListener("change", (event) => {
    const input = event.target.closest("[data-rename]");
    if (!input) return;
    run(async () => {
      const updated = await kpiTrackingApi.rename(slug, input.dataset.rename, input.value);
      current = current.map((k) => (k.id === updated.id ? updated : k));
      render();
      onChange(current);
    });
  });

  render();
  return { tracked: () => current };
}
