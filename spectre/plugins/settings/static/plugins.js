/* Paramètres > Plugins : une carte par plugin (icône, nom, ce qu'il apporte, interrupteur). Les
   modules d'abord, le noyau ensuite (toujours actif, interrupteur verrouillé). Le serveur dit tout
   (settingsApi.plugins) : l'état effectif (active), ce qui l'éteint (blocked_by) et ce que le
   désactiver éteindrait (dependents) - la page ne calcule rien. Désactiver un plugin dont d'autres
   dépendent demande confirmation. */

(function () {
  const errorBox = document.getElementById("error");
  const flash = document.getElementById("flash");
  const optionalGrid = document.getElementById("optional");
  const coreGrid = document.getElementById("core");
  const searchInput = document.getElementById("plugin-search");
  const countEl = document.getElementById("plugin-count");
  const dialog = document.getElementById("confirm-dialog");

  let plugins = [];
  let filter = "all";
  let pendingConfirm = null;

  function showError(err) {
    errorBox.textContent = err.message || String(err);
    errorBox.style.display = "";
  }
  function showFlash(message) {
    flash.textContent = message;
    flash.style.display = "";
  }
  function clearMessages() {
    errorBox.style.display = "none";
    flash.style.display = "none";
  }

  const titlesOf = (list) => list.map((p) => p.title).join(", ");

  function statusHtml(plugin) {
    if (!plugin.available) return `<span class="plugin-status plugin-status--off"><span class="dot"></span>Indisponible sur cette instance</span>`;
    if (plugin.active) return `<span class="plugin-status plugin-status--on"><span class="dot"></span>Actif</span>`;
    if (plugin.enabled && plugin.blocked_by.length) {
      return `<span class="plugin-status plugin-status--blocked"><span class="dot"></span>Inactif : ${escapeHtml(titlesOf(plugin.blocked_by))} désactivé${plugin.blocked_by.length > 1 ? "s" : ""}</span>`;
    }
    return `<span class="plugin-status plugin-status--off"><span class="dot"></span>Désactivé</span>`;
  }

  function cardHtml(plugin) {
    const titleId = `plugin-title-${plugin.name}`;
    const descId = `plugin-desc-${plugin.name}`;
    const locked = plugin.required || !plugin.available;
    const lockReason = plugin.required ? "Fait partie du noyau : toujours actif" : "Indisponible sur cette instance";
    const control = plugin.required
      ? `<span class="plugin-core-badge" title="${lockReason}">${settingsIcon("lock", 12)}Noyau</span>`
      : `<button type="button" class="switch js-toggle" role="switch" data-name="${escapeHtml(plugin.name)}"
           aria-checked="${plugin.enabled && plugin.available}" aria-labelledby="${titleId}" aria-describedby="${descId}"
           ${locked ? `disabled title="${lockReason}"` : ""}></button>`;
    const deps = plugin.depends_on.length ? `<div class="plugin-card__deps">Dépend de : <strong>${escapeHtml(titlesOf(plugin.depends_on))}</strong></div>` : "";
    const changed = plugin.updated_by
      ? `<div>Modifié par ${escapeHtml(plugin.updated_by.name)}${plugin.updated_at ? ` · ${escapeHtml(timeAgo(plugin.updated_at.replace(" ", "T") + "Z"))}` : ""}</div>`
      : "";
    return `
      <article class="plugin-card${plugin.active ? "" : " is-off"}" data-name="${escapeHtml(plugin.name)}">
        <div class="plugin-card__head">
          <div class="plugin-card__icon">${settingsIcon(plugin.icon)}</div>
          <div>
            <div class="plugin-card__title" id="${titleId}">${escapeHtml(plugin.title)}</div>
            <div class="plugin-card__name">${escapeHtml(plugin.name)}</div>
          </div>
          ${control}
        </div>
        <p class="plugin-card__desc" id="${descId}">${escapeHtml(plugin.description || "Pas de description.")}</p>
        <div class="plugin-card__foot">
          ${statusHtml(plugin)}
          ${deps}
          ${changed}
        </div>
      </article>`;
  }

  function matches(plugin) {
    const query = searchInput.value.trim().toLowerCase();
    if (query && !`${plugin.title} ${plugin.name} ${plugin.description}`.toLowerCase().includes(query)) return false;
    if (filter === "active") return plugin.active;
    if (filter === "inactive") return !plugin.active;
    return true;
  }

  function emptyHtml(text) {
    return `<p class="help" style="grid-column:1/-1;margin:0;">${escapeHtml(text)}</p>`;
  }

  function render() {
    const shown = plugins.filter(matches);
    const optional = shown.filter((p) => !p.required);
    const core = shown.filter((p) => p.required);
    optionalGrid.innerHTML = optional.length ? optional.map(cardHtml).join("") : emptyHtml("Aucun module ne correspond.");
    coreGrid.innerHTML = core.length ? core.map(cardHtml).join("") : emptyHtml("Aucun plugin du noyau ne correspond.");
    optionalGrid.removeAttribute("aria-busy");
    const active = plugins.filter((p) => p.active).length;
    countEl.textContent = `${active} / ${plugins.length} actifs`;
  }

  async function load() {
    plugins = await settingsApi.plugins();
    render();
  }

  async function apply(plugin, enabled) {
    clearMessages();
    const button = document.querySelector(`.js-toggle[data-name="${CSS.escape(plugin.name)}"]`);
    if (button) {
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
    }
    try {
      await settingsApi.updatePlugin(plugin.name, { enabled });
      await load();
      const off = enabled ? [] : plugin.dependents.filter((d) => d.active);
      showFlash(
        `${plugin.title} ${enabled ? "activé" : "désactivé"}${off.length ? ` - ainsi que ${titlesOf(off)}` : ""}. ` +
          "Les pages déjà ouvertes le prennent en compte à leur rechargement."
      );
    } catch (err) {
      showError(err);
      await load().catch(() => {});
    }
  }

  function confirmDisable(plugin) {
    const off = plugin.dependents.filter((d) => d.active);
    if (!off.length) return apply(plugin, false);
    document.getElementById("confirm-title").textContent = `Désactiver « ${plugin.title} » ?`;
    document.getElementById("confirm-text").textContent =
      off.length > 1
        ? `Ces ${off.length} modules en dépendent et seront désactivés eux aussi, jusqu'à ce que vous le réactiviez :`
        : "Ce module en dépend et sera désactivé lui aussi, jusqu'à ce que vous le réactiviez :";
    document.getElementById("confirm-list").innerHTML = off.map((d) => `<li>${escapeHtml(d.title)}</li>`).join("");
    pendingConfirm = plugin;
    dialog.showModal();
  }

  document.getElementById("confirm-ok").addEventListener("click", () => {
    const plugin = pendingConfirm;
    pendingConfirm = null;
    dialog.close();
    if (plugin) apply(plugin, false);
  });
  document.getElementById("confirm-cancel").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    // annulé (bouton ou Échap) : l'interrupteur n'a pas bougé, on lui rend le focus
    if (pendingConfirm) {
      const name = pendingConfirm.name;
      pendingConfirm = null;
      const button = document.querySelector(`.js-toggle[data-name="${CSS.escape(name)}"]`);
      if (button) button.focus();
    }
  });

  document.getElementById("content").addEventListener("click", (event) => {
    const button = event.target.closest(".js-toggle");
    if (!button || button.disabled) return;
    const plugin = plugins.find((p) => p.name === button.dataset.name);
    if (!plugin) return;
    if (button.getAttribute("aria-checked") === "true") confirmDisable(plugin);
    else apply(plugin, true);
  });

  document.querySelectorAll("[data-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      filter = button.dataset.filter;
      document.querySelectorAll("[data-filter]").forEach((other) => {
        const on = other === button;
        other.classList.toggle("active", on);
        other.setAttribute("aria-pressed", String(on));
      });
      render();
    });
  });
  searchInput.addEventListener("input", render);

  load().catch((err) => {
    if (err.status === 403) {
      document.getElementById("content").hidden = true;
      document.getElementById("denied").hidden = false;
      return;
    }
    optionalGrid.innerHTML = "";
    showError(err);
  });
})();
