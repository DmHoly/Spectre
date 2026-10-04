/* La liste des références de toute l'application (pages/references.html) : nom, dernière version,
   date de sa dernière mise à jour, µprojet source, nombre d'usages, la plus récemment mise à jour
   d'abord (l'ordre du serveur) ; la recherche (?q= du serveur : sans casse ni accents) ; « Nouvelle
   référence » ; « Nouvelle expérience depuis une référence » (start-picker.js, le µprojet à choisir). */

(() => {
  const errorBox = document.getElementById("error");
  const list = document.getElementById("list");
  let searchTimer = null;
  let token = 0;

  function showError(err) {
    errorBox.textContent = err ? err.message || String(err) : "";
    errorBox.hidden = !err;
  }

  function referenceUrl(ref) {
    return `/references/${encodeURIComponent(ref.slug)}`;
  }

  function rowHtml(ref) {
    const latest = ref.latest_version;
    const source = latest && latest.source && latest.source.microproject;
    const sourceText = source ? `${source.code ? `${source.code} · ` : ""}${source.name}${source.deleted ? " (supprimé)" : ""}` : "—";
    const usages = ref.usage_count ? `${ref.usage_count} étude${ref.usage_count > 1 ? "s" : ""}` : "aucun";
    const updated = latest ? latest.published_at : ref.updated_at || ref.created_at;
    const versions = latest ? `${ref.version_count} version${ref.version_count > 1 ? "s" : ""}` : "sans version";
    return `
      <li>
        <a class="ref-list__row" href="${referenceUrl(ref)}" aria-label="${escapeHtml(`${ref.name}, ${latest ? `dernière version ${latest.number}` : "sans version"}, mise à jour ${formatDate(updated)}`)}">
          <span>
            <span class="ref-list__name">${escapeHtml(ref.name)}</span>
            ${ref.description ? `<span class="ref-list__desc" title="${escapeHtml(ref.description)}">${escapeHtml(ref.description)}</span>` : ""}
          </span>
          <span class="ref-list__cell"><span class="ref-list__label">Dernière : </span>${latest ? `<span class="ref-number">${escapeHtml(latest.number)}</span>` : "—"} <span class="ref-list__cell--mono" style="color:var(--text-faint);">${escapeHtml(versions)}</span></span>
          <span class="ref-list__cell ref-list__cell--mono"><span class="ref-list__label">Mise à jour : </span>${escapeHtml(formatDate(updated))}</span>
          <span class="ref-list__cell"><span class="ref-list__label">Source : </span>${escapeHtml(sourceText)}</span>
          <span class="ref-list__cell"><span class="ref-list__label">Usages : </span>${escapeHtml(usages)}</span>
        </a>
      </li>`;
  }

  async function load(q) {
    const mine = ++token;
    try {
      const references = await referencesApi.list(q);
      if (mine !== token) return;
      document.getElementById("loading").hidden = true;
      document.getElementById("empty").hidden = references.length > 0;
      document.getElementById("empty-text").textContent = q
        ? `Aucune référence ne correspond à « ${q} ».`
        : "Aucune référence pour l'instant. Publiez une étude comme référence depuis sa fiche ou la page d'évolution de son µprojet.";
      document.getElementById("count").textContent = `${references.length} référence${references.length > 1 ? "s" : ""}`;
      list.innerHTML = references.map(rowHtml).join("");
      showError(null);
    } catch (err) {
      document.getElementById("loading").hidden = true;
      showError(err);
    }
  }

  const search = document.getElementById("search");
  search.value = new URLSearchParams(window.location.search).get("q") || "";
  search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      const q = search.value.trim();
      window.history.replaceState(null, "", q ? `?q=${encodeURIComponent(q)}` : window.location.pathname);
      load(q);
    }, 200);
  });

  // -- nouvelle référence --------------------------------------------------------------------

  const dialog = document.getElementById("new-reference-dialog");
  const dialogError = document.getElementById("new-reference-error");
  document.getElementById("new-reference-btn").addEventListener("click", () => {
    document.getElementById("new-reference-form").reset();
    dialogError.hidden = true;
    dialog.showModal();
    document.getElementById("new-reference-name").focus();
  });
  document.getElementById("new-reference-cancel").addEventListener("click", () => dialog.close());
  document.getElementById("new-reference-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const created = await referencesApi.create({
        name: document.getElementById("new-reference-name").value.trim(),
        description: document.getElementById("new-reference-description").value.trim(),
      });
      window.location.href = referenceUrl(created);
    } catch (err) {
      dialogError.textContent = err.message || String(err);
      dialogError.hidden = false;
    }
  });

  document.getElementById("start-btn").addEventListener("click", () => ReferenceStartPicker.open());

  load(search.value.trim());
})();
