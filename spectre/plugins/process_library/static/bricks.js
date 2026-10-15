/* La liste des briques de référence de toute l'application (pages/bricks.html) : nom, version
   courante, date de la dernière version, qui l'a promue, nombre d'études qui en ont une copie
   (GET /api/tech-brick-usages) ; la plus récemment mise à jour d'abord ; une recherche sur place
   (nom, notes). Chaque ligne ouvre la fiche de la brique (/briques/{id}). */

(() => {
  const errorBox = document.getElementById("error");
  const list = document.getElementById("list");
  const state = { bricks: [], usages: {} };

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }

  function latestOf(brick) {
    return brick.versions && brick.versions.length ? brick.versions[brick.versions.length - 1] : null;
  }

  function fold(text) {
    return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function rowHtml(brick) {
    const latest = latestOf(brick);
    const uses = state.usages[brick.id] || [];
    const usages = uses.length ? `${uses.length} étude${uses.length > 1 ? "s" : ""}` : "aucun";
    const updated = latest ? latest.created_at : brick.created_at;
    const versions = `${brick.versions.length} version${brick.versions.length > 1 ? "s" : ""}`;
    const by = brick.reference && brick.reference.promoted_by && brick.reference.promoted_by.name ? brick.reference.promoted_by.name : "—";
    return `
      <li>
        <a class="ref-list__row sp-bricks__row" href="/briques/${encodeURIComponent(brick.id)}" aria-label="${escapeHtml(`${brick.name}, version ${brick.version}, mise à jour ${formatDate(updated)}`)}">
          <span>
            <span class="ref-list__name">${escapeHtml(brick.name)}</span>
            ${brick.notes ? `<span class="ref-list__desc" title="${escapeHtml(brick.notes)}">${escapeHtml(brick.notes)}</span>` : ""}
          </span>
          <span class="ref-list__cell"><span class="ref-list__label">Version : </span><span class="ref-number">${escapeHtml(brick.version)}</span> <span class="ref-list__cell--mono" style="color:var(--text-faint);">${escapeHtml(versions)}</span></span>
          <span class="ref-list__cell ref-list__cell--mono"><span class="ref-list__label">Mise à jour : </span>${escapeHtml(formatDate(updated))}</span>
          <span class="ref-list__cell"><span class="ref-list__label">Promue par : </span>${escapeHtml(by)}</span>
          <span class="ref-list__cell"><span class="ref-list__label">Usages : </span>${escapeHtml(usages)}</span>
        </a>
      </li>`;
  }

  function render(q) {
    const needle = fold(q);
    const shown = state.bricks.filter((b) => !needle || fold(b.name).includes(needle) || fold(b.notes).includes(needle));
    document.getElementById("loading").hidden = true;
    document.getElementById("empty").hidden = shown.length > 0;
    document.getElementById("empty-text").textContent = q
      ? `Aucune brique de référence ne correspond à « ${q} ».`
      : "Aucune brique de référence pour l'instant. « Promouvoir une brique », en haut de la page, en choisit une.";
    document.getElementById("count").textContent = `${shown.length} brique${shown.length > 1 ? "s" : ""}`;
    list.innerHTML = shown.map(rowHtml).join("");
  }

  async function load() {
    try {
      const [bricks, usages] = await Promise.all([
        processLibraryApi.techBricks({ reference: "true" }),
        processLibraryApi.techBrickUsages({}).catch(() => ({})), // un renseignement : la page s'affiche sans
      ]);
      const updated = (b) => (latestOf(b) ? latestOf(b).created_at : b.created_at);
      state.bricks = bricks.sort((a, b) => (updated(a) < updated(b) ? 1 : -1));
      state.usages = usages;
      render(search.value.trim());
      showError(null);
    } catch (err) {
      document.getElementById("loading").hidden = true;
      showError(err);
    }
  }

  const search = document.getElementById("search");
  search.value = new URLSearchParams(window.location.search).get("q") || "";
  let searchTimer = null;
  search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const q = search.value.trim();
      window.history.replaceState(null, "", q ? `?q=${encodeURIComponent(q)}` : window.location.pathname);
      render(q);
    }, 150);
  });

  document.getElementById("pick-btn").addEventListener("click", () => BrickPicker.open());

  load();
})();
