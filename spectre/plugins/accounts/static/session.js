/* La session dans la barre du haut : nom et initiales de l'utilisateur, entrées réservées aux
   administrateurs, déconnexion - via accountsApi (accounts/static/client.js). */

async function mountUserBadge() {
  const nameEls = document.querySelectorAll(".js-user-name");
  const initialsEls = document.querySelectorAll(".js-user-initials");
  try {
    const user = await accountsApi.me();
    nameEls.forEach((el) => (el.textContent = user.name));
    initialsEls.forEach((el) => (el.textContent = initials(user.name)));
    // les entrées de la barre du haut réservées aux administrateurs (NavEntry.admin), rendues cachées
    if (user.is_admin) document.querySelectorAll("[data-admin-only]").forEach((el) => (el.hidden = false));
    return user;
  } catch (err) {
    return null;
  }
}

function initLogout() {
  document.querySelectorAll(".js-logout").forEach((el) => {
    el.addEventListener("click", async (event) => {
      event.preventDefault();
      try {
        await accountsApi.logout({ redirectOn401: false });
      } finally {
        window.location.href = "/connexion";
      }
    });
  });
}

document.addEventListener("DOMContentLoaded", () => {
  mountUserBadge();
  initLogout();
});
