/* La configuration des KPI suivis d'un projet corporate (spectre.plugins.kpi_tracking), montée par la page
   « KPI » du menu Data : la liste des KPI suivis (renommer, filtrer les lignes, ne plus suivre) et celle
   des KPI que PRISM propose (suivre, avec ou sans filtre). Un filtre garde les lignes d'un type de données
   où une de ses colonnes satisfait une comparaison - « Dominant WL(nm) > 613 », « Led_Name contient MONO2 » ;
   les lignes d'un KPI doivent passer tous ses filtres. Le montage ne dessine que dans les deux éléments
   qu'on lui donne ; erreurs et changements remontent par `showError` et `onChange`. */

const KPI_OPERATORS = [
  ["gt", ">"],
  ["gte", "≥"],
  ["lt", "<"],
  ["lte", "≤"],
  ["eq", "="],
  ["ne", "≠"],
  ["contains", "contient"],
  ["in", "dans la liste"],
];

function kpiFilterText(f) {
  const value = Array.isArray(f.value) ? f.value.join(", ") : f.value;
  const op = (KPI_OPERATORS.find(([key]) => key === f.op) || [f.op, f.op])[1];
  return `${f.column} ${op} ${value}`;
}

// Le formulaire d'un filtre (colonne, comparaison, valeur) ; `data-filter-form` le désigne pour ses boutons.
// La valeur est une saisie libre jusqu'à ce que les valeurs de la colonne soient lues (voir drawValueControl) :
// alors une liste à choisir - une seule valeur pour « = » et « ≠ », plusieurs pour « dans la liste ».
function kpiFilterFormHtml(formId, hook, columns, buttonLabel) {
  return `<div class="kt-filter-form" data-filter-form="${escapeHtml(formId)}" data-hook="${escapeHtml(hook)}">
    <select class="field" data-filter-column aria-label="Colonne à filtrer">${columns.map((c) => `<option>${escapeHtml(c)}</option>`).join("")}</select>
    <select class="field" data-filter-op aria-label="Comparaison">${KPI_OPERATORS.map(([key, text]) => `<option value="${key}">${escapeHtml(text)}</option>`).join("")}</select>
    <span class="kt-filter-value" data-filter-value-slot><input type="text" class="field" data-filter-value placeholder="Valeur (ex : 613)" aria-label="Valeur"></span>
    <button type="button" class="btn btn-tint" data-filter-submit="${escapeHtml(formId)}">${escapeHtml(buttonLabel)}</button>
  </div>`;
}

function mountKpiConfig({ slug, canEdit, catalog, tracked, trackedEl, catalogEl, showError, clearError, onChange }) {
  let current = tracked;
  const columnsOf = (hook, column) => {
    const entry = catalog.find((k) => k.hook === hook && k.column === column);
    return entry ? entry.filter_columns : [];
  };

  function renderTracked() {
    if (!current.length) {
      trackedEl.innerHTML = `<p class="help">Aucun KPI suivi pour l'instant${canEdit ? " : choisissez-en dans la liste ci-dessous." : "."}</p>`;
      return;
    }
    trackedEl.innerHTML = current
      .map((k) => {
        const columns = columnsOf(k.hook, k.column);
        const chips = k.filters.length
          ? `<div class="kt-chips">${k.filters
              .map(
                (f, i) =>
                  `<span class="kt-chip">${escapeHtml(kpiFilterText(f))}${canEdit ? `<button type="button" class="kt-chip__x" data-drop-filter="${k.id}:${i}" aria-label="Retirer le filtre ${escapeHtml(kpiFilterText(f))}">×</button>` : ""}</span>`
              )
              .join("")}</div>`
          : `<p class="kt-row__meta" style="margin-top:6px;">Aucun filtre : toutes les lignes comptent.</p>`;
        return `<div class="kt-row kt-row--tracked" data-id="${k.id}">
          <div>
            <div class="kt-row__name">${escapeHtml(k.title)}</div>
            <div class="kt-row__meta">${escapeHtml(k.hook_title)} · ${escapeHtml(k.column)}${k.unit ? ` · ${escapeHtml(k.unit)}` : ""}${k.available ? "" : ' · <span class="kt-row__missing">n\'est plus dans PRISM</span>'}</div>
          </div>
          <div>${canEdit ? `<input type="text" class="field" data-rename="${k.id}" value="${escapeHtml(k.label)}" maxlength="80" placeholder="Nom affiché (par défaut : colonne et filtres)" aria-label="Nom affiché de ${escapeHtml(k.title)}">` : ""}</div>
          <div>${canEdit ? `<button class="btn btn-line" type="button" data-untrack="${k.id}">Ne plus suivre</button>` : ""}</div>
          <div class="kt-row__filters">
            ${chips}
            ${canEdit && k.available && columns.length ? kpiFilterFormHtml(`edit:${k.id}`, k.hook, columns, "Ajouter le filtre") : ""}
          </div>
        </div>`;
      })
      .join("");
  }

  function renderCatalog() {
    if (!catalog.length) {
      catalogEl.innerHTML = `<p class="help">PRISM ne propose aucun KPI par plaque pour l'instant.</p>`;
      return;
    }
    const plain = new Set(current.filter((k) => !k.filters.length).map((k) => `${k.hook}:${k.column}`));
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
                <div class="kt-row__actions">${
                  canEdit
                    ? `${plain.has(k.key) ? '<span class="badge badge-concluded"><span class="dot"></span>Suivi</span>' : `<button class="btn btn-tint" type="button" data-track="${escapeHtml(k.key)}">Suivre</button>`}
                       <button class="btn btn-line" type="button" data-open-filter="${escapeHtml(k.key)}">Avec un filtre…</button>`
                    : plain.has(k.key)
                      ? '<span class="badge badge-concluded"><span class="dot"></span>Suivi</span>'
                      : ""
                }</div>
                <div class="kt-row__filters" data-filter-slot="${escapeHtml(k.key)}" hidden></div>
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

  // Le filtre saisi dans le formulaire `form` : {column, op, value} (la valeur est vérifiée côté serveur).
  function readFilter(form) {
    const control = form.querySelector("[data-filter-value]");
    const value = control.multiple ? [...control.selectedOptions].map((o) => o.value) : control.value;
    return { column: form.querySelector("[data-filter-column]").value, op: form.querySelector("[data-filter-op]").value, value };
  }

  // Les valeurs d'une colonne, lues une fois par type de données et colonne (une requête PRISM par plaque, en cache
  // côté serveur) : null si on ne peut pas les lire - la saisie libre reste alors.
  const valuesCache = new Map();
  function loadValues(hook, column) {
    const key = `${hook}:${column}`;
    if (!valuesCache.has(key)) valuesCache.set(key, kpiTrackingApi.values(slug, hook, column).catch(() => null));
    return valuesCache.get(key);
  }

  function kindHint(info) {
    if (!info || info.kind === "empty") return "Aucune valeur lue (pas de plaque suivie, ou colonne vide).";
    if (info.kind === "number") return `${info.distinct} valeur${info.distinct > 1 ? "s" : ""}, de ${info.minimum} à ${info.maximum}`;
    return `${info.distinct} valeur${info.distinct > 1 ? "s" : ""} sur ${info.wafers} plaque${info.wafers > 1 ? "s" : ""}`;
  }

  // La saisie de la valeur selon la colonne et la comparaison : une liste pour « = » et « ≠ » (une valeur) ou
  // « dans la liste » (plusieurs) quand les valeurs sont connues ; sinon un champ libre (« contient », « > »...,
  // dont le placeholder dit l'étendue des valeurs d'une colonne numérique).
  function drawValueControl(form, info) {
    const slot = form.querySelector("[data-filter-value-slot]");
    const op = form.querySelector("[data-filter-op]").value;
    const listed = info && info.values.length && ["eq", "ne", "in"].includes(op);
    const options = listed
      ? info.values.map((v) => `<option value="${escapeHtml(v.value)}">${escapeHtml(String(v.value))} (${v.count})</option>`).join("")
      : "";
    if (listed) {
      const many = op === "in";
      slot.innerHTML = `<select class="field" data-filter-value ${many ? 'multiple size="6"' : ""} aria-label="Valeur${many ? "s" : ""}">${options}</select>
        <span class="kt-filter-hint">${escapeHtml(kindHint(info))}${info.distinct > info.values.length ? ` - les ${info.values.length} plus fréquentes` : ""}</span>`;
      return;
    }
    const range = info && info.kind === "number" ? `${info.minimum} – ${info.maximum}` : "";
    const placeholder = op === "in" ? "Valeurs séparées par des virgules" : range ? `Valeur (${range})` : "Valeur (ex : 613)";
    slot.innerHTML = `<input type="text" class="field" data-filter-value placeholder="${escapeHtml(placeholder)}" aria-label="Valeur">${
      info && info.kind !== "number" && info.kind !== "empty" ? `<span class="kt-filter-hint">${escapeHtml(kindHint(info))}</span>` : ""
    }`;
  }

  async function refreshValueControl(form) {
    const column = form.querySelector("[data-filter-column]").value;
    const info = await loadValues(form.dataset.hook, column);
    if (form.querySelector("[data-filter-column]").value === column) drawValueControl(form, info); // un autre choix entre-temps
  }

  function onFormChange(event) {
    const form = event.target.closest("[data-filter-form]");
    if (form && event.target.closest("[data-filter-column], [data-filter-op]")) refreshValueControl(form);
  }

  // à la première prise de focus d'un formulaire, ses valeurs se lisent (pas avant : un formulaire par KPI)
  function onFormFocus(event) {
    const form = event.target.closest("[data-filter-form]");
    if (form && !form.dataset.ready) {
      form.dataset.ready = "1";
      refreshValueControl(form);
    }
  }

  function onClick(event) {
    const track = event.target.closest("[data-track]");
    if (track) {
      const entry = catalog.find((k) => k.key === track.dataset.track);
      if (!entry) return;
      track.disabled = true;
      run(async () => {
        try {
          await kpiTrackingApi.track(slug, { hook: entry.hook, column: entry.column });
        } finally {
          await reload();
        }
      });
      return;
    }
    const open = event.target.closest("[data-open-filter]");
    if (open) {
      const entry = catalog.find((k) => k.key === open.dataset.openFilter);
      const slot = catalogEl.querySelector(`[data-filter-slot="${CSS.escape(entry.key)}"]`);
      slot.hidden = !slot.hidden;
      if (!slot.hidden && !slot.innerHTML) {
        slot.innerHTML = kpiFilterFormHtml(`new:${entry.key}`, entry.hook, entry.filter_columns, "Suivre avec ce filtre");
        const form = slot.querySelector("[data-filter-form]");
        form.dataset.ready = "1";
        refreshValueControl(form);
      }
      return;
    }
    const submit = event.target.closest("[data-filter-submit]");
    if (submit) {
      const form = submit.closest("[data-filter-form]");
      const [kind, ref] = submit.dataset.filterSubmit.split(/:(.*)/s);
      const filter = readFilter(form);
      submit.disabled = true;
      run(async () => {
        try {
          if (kind === "new") {
            const entry = catalog.find((k) => k.key === ref);
            await kpiTrackingApi.track(slug, { hook: entry.hook, column: entry.column, filters: [filter] });
          } else {
            const kpi = current.find((k) => String(k.id) === ref);
            await kpiTrackingApi.update(slug, kpi.id, { filters: [...kpi.filters, filter] });
          }
        } finally {
          await reload();
        }
      });
      return;
    }
    const drop = event.target.closest("[data-drop-filter]");
    if (drop) {
      const [id, index] = drop.dataset.dropFilter.split(":");
      const kpi = current.find((k) => String(k.id) === id);
      drop.disabled = true;
      run(async () => {
        try {
          await kpiTrackingApi.update(slug, kpi.id, { filters: kpi.filters.filter((_, i) => i !== Number(index)) });
        } finally {
          await reload();
        }
      });
      return;
    }
    const untrack = event.target.closest("[data-untrack]");
    if (untrack) {
      untrack.disabled = true;
      run(async () => {
        try {
          await kpiTrackingApi.untrack(slug, untrack.dataset.untrack);
        } finally {
          await reload();
        }
      });
    }
  }

  for (const el of [catalogEl, trackedEl]) {
    el.addEventListener("click", onClick);
    el.addEventListener("change", onFormChange);
    el.addEventListener("focusin", onFormFocus);
  }

  trackedEl.addEventListener("change", (event) => {
    const input = event.target.closest("[data-rename]");
    if (!input) return;
    run(async () => {
      const updated = await kpiTrackingApi.update(slug, input.dataset.rename, { label: input.value });
      current = current.map((k) => (k.id === updated.id ? updated : k));
      render();
      onChange(current);
    });
  });

  render();
  return { tracked: () => current };
}
