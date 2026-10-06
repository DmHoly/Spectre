/* Paramètres > Base de données : la sauvegarde ZIP du dossier de données, l'explorateur des tables
   SQL (liste, recherche, pages, modifier une ligne, la supprimer) et la liste de toutes les études
   (elles vivent dans le dépôt de leur µprojet : lues et supprimées par experimentsApi, qu'un admin
   peut appeler sur tout µprojet). Le serveur dit tout : colonnes, clés étrangères, colonnes
   secrètes (masquées, non modifiables), tables en lecture seule. */

(function () {
  const PAGE_SIZE = 50;
  const errorBox = document.getElementById("error");
  const flash = document.getElementById("flash");
  const rowDialog = document.getElementById("row-dialog");
  const confirmDialog = document.getElementById("confirm-dialog");

  const state = { tables: [], table: null, page: null, offset: 0, q: "", sort: null, desc: false, editing: null, confirm: null };

  function showError(err) {
    errorBox.textContent = err.message || String(err);
    errorBox.style.display = "";
    flash.style.display = "none";
  }
  function showFlash(message) {
    flash.textContent = message;
    flash.style.display = "";
    errorBox.style.display = "none";
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} o`;
    const units = ["Ko", "Mo", "Go"];
    let value = bytes / 1024;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${value.toFixed(value < 10 ? 1 : 0)} ${units[unit]}`;
  }

  function debounce(fn, ms = 250) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  }

  // -- confirmation -------------------------------------------------------------------------

  function confirmAction(title, text, action) {
    document.getElementById("confirm-title").textContent = title;
    document.getElementById("confirm-text").textContent = text;
    state.confirm = action;
    confirmDialog.showModal();
  }
  document.getElementById("confirm-cancel").addEventListener("click", () => confirmDialog.close());
  document.getElementById("confirm-ok").addEventListener("click", () => {
    const action = state.confirm;
    state.confirm = null;
    confirmDialog.close();
    if (action) action();
  });

  // -- sauvegarde ---------------------------------------------------------------------------

  document.getElementById("backup-icon").innerHTML = settingsIcon("database", 22);

  async function loadSummary() {
    const summary = await settingsApi.databaseSummary();
    document.getElementById("backup-facts").innerHTML = `
      <div><dt>Base SQL</dt><dd class="mono">${escapeHtml(formatBytes(summary.database_bytes))}</dd></div>
      <div><dt>Fichiers</dt><dd class="mono">${summary.files} · ${escapeHtml(formatBytes(summary.files_bytes))}</dd></div>
      <div><dt>Dossier</dt><dd class="mono db-backup__path" title="${escapeHtml(summary.data_dir)}">${escapeHtml(summary.data_dir)}</dd></div>`;
  }

  const backupBtn = document.getElementById("backup-btn");
  backupBtn.addEventListener("click", async () => {
    backupBtn.disabled = true;
    backupBtn.setAttribute("aria-busy", "true");
    backupBtn.textContent = "Préparation de l'archive…";
    try {
      const blob = await settingsApi.databaseBackup();
      const stamp = new Date().toISOString().slice(0, 19).replace(/[-:]/g, "").replace("T", "-");
      const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `spectre-${stamp}.zip` });
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 10000);
      showFlash(`Sauvegarde téléchargée (${formatBytes(blob.size)}).`);
    } catch (err) {
      showError(err);
    } finally {
      backupBtn.disabled = false;
      backupBtn.removeAttribute("aria-busy");
      backupBtn.textContent = "Télécharger la sauvegarde";
    }
  });

  // -- onglets ------------------------------------------------------------------------------

  const TABS = ["tables", "experiments"];
  let experimentsLoaded = false;
  function showTab(name) {
    TABS.forEach((key) => {
      const selected = key === name;
      const button = document.getElementById(`tab-${key}`);
      button.classList.toggle("active", selected);
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
      document.getElementById(`panel-${key}`).hidden = !selected;
    });
    if (name === "experiments" && !experimentsLoaded) {
      experimentsLoaded = true;
      loadExperiments().catch(showError);
    }
  }
  document.querySelectorAll(".db-tabs [data-tab]").forEach((button) => button.addEventListener("click", () => showTab(button.dataset.tab)));

  // -- tables -------------------------------------------------------------------------------

  function renderTableList() {
    const filter = document.getElementById("table-filter").value.trim().toLowerCase();
    const shown = state.tables.filter((t) => !filter || t.name.toLowerCase().includes(filter));
    document.getElementById("table-list").innerHTML = shown.length
      ? shown
          .map(
            (t) => `<li><button type="button" class="db-tables__item" data-table="${escapeHtml(t.name)}"${t.name === state.table ? ' aria-current="true"' : ""}>
              <span class="db-tables__name mono">${escapeHtml(t.name)}</span>
              ${t.editable ? "" : `<span class="db-tables__lock" title="Lecture seule">${settingsIcon("lock", 12)}</span>`}
              <span class="db-tables__count mono">${t.rows}</span>
            </button></li>`
          )
          .join("")
      : `<li class="help" style="padding:8px 12px;">Aucune table.</li>`;
  }

  async function loadTables() {
    state.tables = await settingsApi.tables();
    renderTableList();
  }

  document.getElementById("table-filter").addEventListener("input", renderTableList);
  document.getElementById("table-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-table]");
    if (!button) return;
    openTable(button.dataset.table);
  });

  function openTable(name) {
    state.table = name;
    state.offset = 0;
    state.q = "";
    state.sort = null;
    state.desc = false;
    const search = document.getElementById("row-search");
    search.value = "";
    search.disabled = false;
    renderTableList();
    loadRows().catch(showError);
  }

  async function loadRows() {
    const page = await settingsApi.rows(state.table, {
      q: state.q,
      sort: state.sort,
      desc: state.desc ? "true" : null,
      offset: state.offset,
      limit: PAGE_SIZE,
    });
    state.page = page;
    renderGrid();
  }

  function cellHtml(value, column) {
    if (value === null) return `<span class="db-null">NULL</span>`;
    if (column.secret) return `<span class="db-secret">${escapeHtml(String(value))}</span>`;
    const text = String(value);
    const short = text.length > 80 ? `${text.slice(0, 80)}…` : text;
    return `<span title="${escapeHtml(text.length > 80 ? text : "")}">${escapeHtml(short)}</span>`;
  }

  function headerHtml(column) {
    const sorted = state.sort === column.name;
    const arrow = sorted ? (state.desc ? " ↓" : " ↑") : "";
    const hints = [column.type, column.primary_key ? "clé primaire" : "", column.references ? `→ ${column.references}` : "", column.secret ? "secrète" : ""]
      .filter(Boolean)
      .join(" · ");
    const aria = sorted ? (state.desc ? "descending" : "ascending") : "none";
    return `<th scope="col" aria-sort="${aria}"><button type="button" class="db-sort" data-sort="${escapeHtml(column.name)}" title="${escapeHtml(hints)}">${escapeHtml(column.name)}${arrow}</button>${
      column.references ? `<span class="db-fk mono">→ ${escapeHtml(column.references)}</span>` : ""
    }</th>`;
  }

  function renderGrid() {
    const page = state.page;
    document.getElementById("grid-title").textContent = page.table;
    document.getElementById("grid-meta").innerHTML =
      `${page.total} ligne${page.total > 1 ? "s" : ""}${state.q ? ` pour « ${escapeHtml(state.q)} »` : ""} · ${page.columns.length} colonnes` +
      (page.editable ? "" : ` · <span class="plugin-core-badge">${settingsIcon("lock", 12)}Lecture seule</span>`);
    const scroll = document.getElementById("grid-scroll");
    if (!page.items.length) {
      scroll.innerHTML = `<p class="help db-grid__empty">${state.q ? "Aucune ligne ne correspond." : "Table vide."}</p>`;
    } else {
      const actions = page.editable;
      scroll.innerHTML = `<table class="db-table">
        <thead><tr>${actions ? '<th scope="col" class="db-actions-col"><span class="visually-hidden">Actions</span></th>' : ""}${page.columns.map(headerHtml).join("")}</tr></thead>
        <tbody>${page.items
          .map(
            (item) => `<tr>${
              actions
                ? `<td class="db-actions-col"><div class="db-row-actions">
                    <button type="button" class="db-icon-btn js-edit" data-rowid="${item.rowid}" aria-label="Modifier la ligne ${item.rowid}" title="Modifier">${settingsIcon("pencil", 15)}</button>
                    <button type="button" class="db-icon-btn db-icon-btn--danger js-delete" data-rowid="${item.rowid}" aria-label="Supprimer la ligne ${item.rowid}" title="Supprimer">${settingsIcon("trash", 15)}</button>
                  </div></td>`
                : ""
            }${page.columns.map((column) => `<td>${cellHtml(item.values[column.name], column)}</td>`).join("")}</tr>`
          )
          .join("")}</tbody>
      </table>`;
    }
    const end = Math.min(state.offset + PAGE_SIZE, page.total);
    document.getElementById("grid-range").textContent = page.total ? `${state.offset + 1}–${end} sur ${page.total}` : "";
    document.getElementById("prev-page").disabled = state.offset === 0;
    document.getElementById("next-page").disabled = end >= page.total;
  }

  document.getElementById("row-search").addEventListener(
    "input",
    debounce((event) => {
      state.q = event.target.value.trim();
      state.offset = 0;
      loadRows().catch(showError);
    })
  );
  document.getElementById("prev-page").addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - PAGE_SIZE);
    loadRows().catch(showError);
  });
  document.getElementById("next-page").addEventListener("click", () => {
    state.offset += PAGE_SIZE;
    loadRows().catch(showError);
  });

  document.getElementById("grid-scroll").addEventListener("click", (event) => {
    const sort = event.target.closest("[data-sort]");
    if (sort) {
      if (state.sort === sort.dataset.sort) state.desc = !state.desc;
      else {
        state.sort = sort.dataset.sort;
        state.desc = false;
      }
      state.offset = 0;
      loadRows().catch(showError);
      return;
    }
    const edit = event.target.closest(".js-edit");
    if (edit) return openRowDialog(Number(edit.dataset.rowid));
    const remove = event.target.closest(".js-delete");
    if (remove) {
      const rowid = Number(remove.dataset.rowid);
      const table = state.table;
      confirmAction(
        `Supprimer la ligne ${rowid} de ${table} ?`,
        "La suppression est définitive. Les lignes qui en dépendent suivent le schéma (supprimées avec elle, ou détachées) ; si la base refuse, rien n'est supprimé.",
        async () => {
          try {
            await settingsApi.deleteRow(table, rowid);
            showFlash(`Ligne ${rowid} supprimée de ${table}.`);
            await Promise.all([loadRows(), loadTables(), loadSummary()]);
          } catch (err) {
            showError(err);
          }
        }
      );
    }
  });

  // -- modifier une ligne -------------------------------------------------------------------

  function fieldHtml(column, value, index) {
    const id = `row-field-${index}`;
    const disabled = column.secret;
    const isNull = value === null;
    const hint = [column.type || "sans type", column.not_null ? "obligatoire" : "", column.primary_key ? "clé primaire" : "", column.references ? `→ ${column.references}` : ""]
      .filter(Boolean)
      .join(" · ");
    const text = isNull ? "" : String(value);
    const multiline = text.length > 60 || text.includes("\n");
    const input = multiline
      ? `<textarea class="field mono" id="${id}" data-column="${escapeHtml(column.name)}" rows="3"${disabled ? " disabled" : ""}>${escapeHtml(text)}</textarea>`
      : `<input class="field mono" id="${id}" data-column="${escapeHtml(column.name)}" value="${escapeHtml(text)}"${disabled ? " disabled" : ""}>`;
    const nullBox =
      !column.not_null && !disabled
        ? `<label class="db-null-toggle"><input type="checkbox" data-null-for="${escapeHtml(column.name)}"${isNull ? " checked" : ""}> NULL</label>`
        : "";
    return `<div class="db-row-field">
      <div class="db-row-field__label"><label for="${id}" class="mono">${escapeHtml(column.name)}</label><span class="db-row-field__hint">${escapeHtml(disabled ? "secrète : non modifiable ici" : hint)}</span></div>
      ${input}${nullBox}
    </div>`;
  }

  function openRowDialog(rowid) {
    const item = state.page.items.find((row) => row.rowid === rowid);
    if (!item) return;
    state.editing = { rowid, original: item.values };
    document.getElementById("row-dialog-title").textContent = `${state.table} · ligne ${rowid}`;
    document.getElementById("row-fields").innerHTML = state.page.columns.map((column, i) => fieldHtml(column, item.values[column.name], i)).join("");
    rowDialog.showModal();
  }

  // Une valeur saisie, dans le type de sa colonne : un entier ou un réel s'il en a la forme
  // (INTEGER, REAL, NUMERIC), sinon le texte.
  function typedValue(column, text) {
    const type = (column.type || "").toUpperCase();
    const numeric = /INT|REAL|FLOA|DOUB|NUM|DEC/.test(type);
    if (numeric && /^-?\d+(\.\d+)?$/.test(text.trim())) return Number(text.trim());
    return text;
  }

  document.getElementById("row-cancel").addEventListener("click", () => rowDialog.close());
  document.getElementById("row-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const { rowid, original } = state.editing;
    const values = {};
    state.page.columns.forEach((column) => {
      if (column.secret) return;
      const field = rowDialog.querySelector(`[data-column="${CSS.escape(column.name)}"]`);
      const nullBox = rowDialog.querySelector(`[data-null-for="${CSS.escape(column.name)}"]`);
      const value = nullBox && nullBox.checked ? null : typedValue(column, field.value);
      const before = original[column.name];
      const same = value === null ? before === null : before !== null && String(before) === String(value);
      if (!same) values[column.name] = value;
    });
    if (!Object.keys(values).length) {
      rowDialog.close();
      return;
    }
    try {
      await settingsApi.updateRow(state.table, rowid, { values });
      rowDialog.close();
      showFlash(`Ligne ${rowid} de ${state.table} modifiée (${Object.keys(values).join(", ")}).`);
      await loadRows();
    } catch (err) {
      rowDialog.close();
      showError(err);
    }
  });

  // -- études -------------------------------------------------------------------------------

  let experiments = [];

  async function loadExperiments() {
    const microprojects = await microprojectsApi.list({ scope: "all" });
    const lists = await Promise.all(
      microprojects.map((mp) =>
        experimentsApi
          .list(mp.slug, { status: "all", limit: 200 })
          .then((page) => page.items.map((exp) => ({ ...exp, microproject: mp })))
          .catch(() => [])
      )
    );
    experiments = lists.flat().sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    renderExperiments();
  }

  function renderExperiments() {
    const q = document.getElementById("experiment-search").value.trim().toLowerCase();
    const shown = experiments.filter(
      (exp) => !q || [exp.title, exp.id, exp.author, exp.microproject.name, exp.microproject.code].some((text) => (text || "").toLowerCase().includes(q))
    );
    const scroll = document.getElementById("experiments-scroll");
    if (!shown.length) {
      scroll.innerHTML = `<p class="help db-grid__empty">${experiments.length ? "Aucune étude ne correspond." : "Aucune étude."}</p>`;
      return;
    }
    scroll.innerHTML = `<table class="db-table">
      <thead><tr>
        <th scope="col" class="db-actions-col"><span class="visually-hidden">Actions</span></th>
        <th scope="col">µprojet</th><th scope="col">Étude</th><th scope="col">Piste</th><th scope="col">Statut</th><th scope="col">Auteur</th><th scope="col">Créée</th>
      </tr></thead>
      <tbody>${shown
        .map((exp) => {
          const url = `/microprojets/${encodeURIComponent(exp.microproject.slug)}/experiences/${encodeURIComponent(exp.id)}`;
          return `<tr>
            <td class="db-actions-col"><div class="db-row-actions">
              <button type="button" class="db-icon-btn db-icon-btn--danger js-delete-exp" data-mp="${escapeHtml(exp.microproject.slug)}" data-exp="${escapeHtml(exp.id)}" aria-label="Supprimer l'étude ${escapeHtml(exp.title)}" title="Supprimer">${settingsIcon("trash", 15)}</button>
            </div></td>
            <td><a href="/microprojets/${encodeURIComponent(exp.microproject.slug)}" class="mono">${escapeHtml(exp.microproject.code || exp.microproject.name)}</a></td>
            <td><a href="${url}">${escapeHtml(exp.title)}</a></td>
            <td class="mono">${escapeHtml(exp.id)}</td>
            <td>${typeof statusBadgeHtml === "function" ? statusBadgeHtml(exp.status) : escapeHtml(exp.status)}</td>
            <td>${escapeHtml(exp.author || "")}</td>
            <td class="mono">${escapeHtml(formatDate(exp.created_at))}</td>
          </tr>`;
        })
        .join("")}</tbody>
    </table>`;
  }

  document.getElementById("experiment-search").addEventListener("input", renderExperiments);
  document.getElementById("experiments-scroll").addEventListener("click", (event) => {
    const button = event.target.closest(".js-delete-exp");
    if (!button) return;
    const exp = experiments.find((e) => e.microproject.slug === button.dataset.mp && e.id === button.dataset.exp);
    if (!exp) return;
    confirmAction(
      `Supprimer l'étude « ${exp.title} » ?`,
      `Sa piste (${exp.id}) et toutes ses versions sont supprimées du µprojet ${exp.microproject.code || exp.microproject.name}. Une étude dont une autre descend ne peut pas être supprimée.`,
      async () => {
        try {
          await experimentsApi.remove(exp.microproject.slug, exp.id, exp.version_id);
          showFlash(`Étude « ${exp.title} » supprimée.`);
          await loadExperiments();
        } catch (err) {
          showError(err);
        }
      }
    );
  });

  // -- démarrage ----------------------------------------------------------------------------

  Promise.all([loadSummary(), loadTables()]).catch((err) => {
    if (err.status === 403) {
      document.getElementById("content").hidden = true;
      document.getElementById("denied").hidden = false;
      return;
    }
    showError(err);
  });
})();
