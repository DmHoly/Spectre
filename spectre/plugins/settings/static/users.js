/* Paramètres > Utilisateurs : la liste des comptes et, par compte, la réinitialisation d'un mot de
   passe oublié (settingsApi.resetUserPassword). Le mot de passe provisoire n'est affiché qu'une fois,
   à l'administrateur qui le transmet ; le compte devra en choisir un nouveau à sa prochaine connexion. */

(function () {
  const errorBox = document.getElementById("error");
  const tempBox = document.getElementById("temp");
  const body = document.getElementById("users-body");
  const denied = document.getElementById("denied");
  const content = document.getElementById("content");
  let me = null;

  function showError(err) {
    errorBox.textContent = err.message || String(err);
    errorBox.style.display = "";
  }

  function rowHtml(user) {
    const state = user.must_change_password ? "Doit changer son mot de passe" : "Actif";
    const action = me && user.id === me.id
      ? `<span class="help">Vous</span>`
      : `<button type="button" class="btn btn-line js-reset" data-id="${user.id}" data-name="${escapeHtml(user.name)}">Réinitialiser le mot de passe</button>`;
    return `<tr style="border-top:1px solid var(--line, #e5e7eb);">
      <td style="padding:8px 6px;">${escapeHtml(user.name)}</td>
      <td style="padding:8px 6px;" class="mono">${escapeHtml(user.email)}</td>
      <td style="padding:8px 6px;">${user.is_admin ? "Administrateur" : "Utilisateur"}</td>
      <td style="padding:8px 6px;">${state}</td>
      <td style="padding:8px 6px;text-align:right;">${action}</td>
    </tr>`;
  }

  async function load() {
    try {
      me = await accountsApi.me();
      if (!me.is_admin) {
        denied.hidden = false;
        content.hidden = true;
        return;
      }
      const users = await settingsApi.users();
      body.innerHTML = users.map(rowHtml).join("");
    } catch (err) {
      showError(err);
    }
  }

  body.addEventListener("click", async (event) => {
    const button = event.target.closest(".js-reset");
    if (!button) return;
    const name = button.dataset.name;
    if (!window.confirm(`Réinitialiser le mot de passe de ${name} ? Il sera déconnecté partout.`)) return;
    errorBox.style.display = "none";
    try {
      const result = await settingsApi.resetUserPassword(button.dataset.id);
      tempBox.innerHTML = `Mot de passe provisoire de <strong>${escapeHtml(result.user.name)}</strong> (à lui transmettre, il ne sera plus affiché) :
        <code class="mono" style="user-select:all;font-size:15px;margin-left:6px;">${escapeHtml(result.temporary_password)}</code>`;
      tempBox.style.display = "";
      load();
    } catch (err) {
      showError(err);
    }
  });

  load();
})();
