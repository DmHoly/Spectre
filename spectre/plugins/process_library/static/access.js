/* Qui modifie un élément partagé de la bibliothèque (structure, préset, brique) : son auteur - avec
   le badge de son équipe -, les comptes et les équipes à qui l'auteur a donné la main. `badgesHtml`
   les dit sur une ligne de liste ; `open` est la fenêtre où l'auteur (ou un administrateur) les
   choisit. Suppose roles.js (ownerChipHtml), ui.js (teamBadge) et le client des équipes. */

const LibraryAccess = (() => {
  function badgesHtml(item) {
    if (!item || item.scope !== "shared") return "";
    const owner = item.created_by && item.created_by.name ? ownerChipHtml([item.created_by], { label: false }) : "";
    const owner_teams = (item.owner_teams || []).map((team) => teamBadge(team, { compact: true })).join("");
    return `<span class="library-owner" style="display:inline-flex;align-items:center;gap:6px;vertical-align:middle;">${owner}${owner_teams}</span>`;
  }

  function el(tag, attrs, html) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => node.setAttribute(key, value));
    if (html !== undefined) node.innerHTML = html;
    return node;
  }

  /* Ouvre la fenêtre des accès de `item` (partagé, `can_manage_access`) : `save({emails, team_slugs})`
     enregistre et rend l'élément à jour, que `onSaved` reçoit. */
  async function open(item, { save, onSaved }) {
    let teams = [];
    try {
      teams = await teamsApi.list();
    } catch {
      /* la liste des équipes est un renseignement : on peut quand même donner la main à un compte */
    }
    let current = item;
    const dialog = el("dialog", { style: "border:none;border-radius:14px;padding:0;box-shadow:var(--shadow);max-width:480px;width:calc(100% - 32px);" });
    dialog.innerHTML = `
      <div style="padding:22px;">
        <h3 style="margin:0 0 4px;">Qui peut modifier « <span class="js-name"></span> » ?</h3>
        <p class="help" style="margin-bottom:12px;">Tout le monde le voit et le réutilise. Son auteur et les administrateurs le modifient toujours ; ajoutez des comptes ou des équipes pour partager la main (seul l'auteur le supprime).</p>
        <div class="js-owner" style="margin-bottom:12px;"></div>
        <div class="js-error" style="display:none;color:var(--danger);font-size:12.5px;margin-bottom:8px;"></div>
        <div class="field-label">Comptes</div>
        <div class="js-editors" style="margin-bottom:8px;"></div>
        <form class="js-add-email" style="display:flex;gap:6px;margin-bottom:14px;">
          <input class="field" type="email" placeholder="adresse e-mail d'un compte" aria-label="Adresse e-mail d'un compte" required style="flex:1;">
          <button class="btn btn-line" type="submit">Ajouter</button>
        </form>
        <div class="field-label">Équipes</div>
        <div class="js-teams" style="margin-bottom:8px;"></div>
        <form class="js-add-team" style="display:flex;gap:6px;margin-bottom:14px;">
          <select class="field" aria-label="Équipe à ajouter" style="flex:1;"></select>
          <button class="btn btn-line" type="submit">Ajouter</button>
        </form>
        <div style="text-align:right;"><button class="btn btn-primary js-close" type="button">Fermer</button></div>
      </div>`;
    document.body.appendChild(dialog);
    const q = (selector) => dialog.querySelector(selector);
    q(".js-name").textContent = item.name;
    q(".js-owner").innerHTML = badgesHtml(item);

    const showError = (err) => {
      q(".js-error").textContent = err.message || String(err);
      q(".js-error").style.display = "block";
    };
    const rowHtml = (label, key) =>
      `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13px;"><span style="flex:1;min-width:0;">${label}</span><button class="btn btn-line js-remove" data-key="${escapeHtml(key)}" type="button" style="padding:3px 9px;font-size:12px;">Retirer</button></div>`;

    function render() {
      q(".js-editors").innerHTML =
        current.editors.map((e) => rowHtml(`${escapeHtml(e.name)} <span style="color:var(--text-faint);">${escapeHtml(e.email)}</span>`, `email:${e.email}`)).join("") ||
        `<div class="help">Personne d'autre pour l'instant.</div>`;
      q(".js-teams").innerHTML =
        current.editor_teams.map((t) => rowHtml(teamBadge(t), `team:${t.slug}`)).join("") || `<div class="help">Aucune équipe.</div>`;
      const free = teams.filter((t) => !current.editor_teams.some((chosen) => chosen.slug === t.slug));
      const select = q(".js-add-team select");
      select.innerHTML = free.map((t) => `<option value="${escapeHtml(t.slug)}">${escapeHtml(t.name)}</option>`).join("");
      q(".js-add-team").style.display = free.length ? "" : "none";
    }

    async function apply(emails, teamSlugs) {
      q(".js-error").style.display = "none";
      try {
        current = await save({ emails, team_slugs: teamSlugs });
        render();
        if (onSaved) onSaved(current);
      } catch (err) {
        showError(err);
      }
    }
    const emails = () => current.editors.map((e) => e.email);
    const teamSlugs = () => current.editor_teams.map((t) => t.slug);

    q(".js-add-email").addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = q(".js-add-email input");
      const email = input.value.trim();
      if (!email) return;
      await apply([...emails(), email], teamSlugs());
      if (q(".js-error").style.display === "none") input.value = "";
    });
    q(".js-add-team").addEventListener("submit", async (event) => {
      event.preventDefault();
      const slug = q(".js-add-team select").value;
      if (slug) await apply(emails(), [...teamSlugs(), slug]);
    });
    dialog.addEventListener("click", async (event) => {
      const remove = event.target.closest(".js-remove");
      if (!remove) return;
      const [kind, value] = [remove.dataset.key.split(":")[0], remove.dataset.key.slice(remove.dataset.key.indexOf(":") + 1)];
      await apply(kind === "email" ? emails().filter((e) => e !== value) : emails(), kind === "team" ? teamSlugs().filter((s) => s !== value) : teamSlugs());
    });
    const close = () => {
      dialog.close();
      dialog.remove();
    };
    q(".js-close").addEventListener("click", close);
    dialog.addEventListener("cancel", () => dialog.remove());
    render();
    dialog.showModal();
  }

  return { badgesHtml, open };
})();
