/* La barre du haut commune (rendue par le noyau, kernel/pages.py, à partir des NavEntry des
   plugins) : marque la section courante de la navigation principale (aria-current="page",
   souligné or en CSS). Chaque lien porte l'expression régulière de sa section (data-match) ; sans
   elle, c'est son href exact qui compte. Le premier lien qui correspond au chemin de la page gagne ;
   s'il est rangé dans un menu (NavEntry.group), le bouton du menu est souligné aussi.

   Les menus : un clic (ou Entrée, Espace, flèche bas) ouvre le panneau sous son bouton, en position
   fixe pour échapper au défilement horizontal de la nav sur petit écran ; Échap, un clic ailleurs,
   le défilement ou un redimensionnement le referment. Flèches haut/bas d'un lien à l'autre. */

(function () {
  function sectionMatches(link, path) {
    const pattern = link.dataset.match;
    if (!pattern) return link.getAttribute("href") === path;
    try {
      return new RegExp(pattern).test(path);
    } catch (e) {
      return false;
    }
  }

  function markCurrentSection() {
    const path = window.location.pathname;
    const links = [...document.querySelectorAll(".topbar__nav a.topbar__link, .topbar__menu-link, .topbar__tool")];
    const current = links.find((link) => sectionMatches(link, path));
    if (!current) return;
    current.setAttribute("aria-current", "page");
    const group = current.closest(".topbar__group");
    if (group) group.querySelector(".topbar__group-btn").classList.add("is-current");
  }

  function menuOf(button) {
    return document.getElementById(button.getAttribute("aria-controls"));
  }

  function menuLinks(menu) {
    return [...menu.querySelectorAll(".topbar__menu-link")].filter((link) => !link.hidden);
  }

  function closeMenus(except) {
    document.querySelectorAll('.topbar__group-btn[aria-expanded="true"]').forEach((button) => {
      if (button === except) return;
      button.setAttribute("aria-expanded", "false");
      menuOf(button).hidden = true;
    });
  }

  function openMenu(button, focusFirst) {
    closeMenus(button);
    const menu = menuOf(button);
    button.setAttribute("aria-expanded", "true");
    menu.hidden = false;
    const bar = button.closest(".topbar").getBoundingClientRect();
    const rect = button.getBoundingClientRect();
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - menu.offsetWidth - 8));
    menu.style.top = `${Math.round(Math.max(rect.bottom, bar.bottom))}px`;
    menu.style.left = `${Math.round(left)}px`;
    if (focusFirst) menuLinks(menu)[0]?.focus();
  }

  function setupMenus() {
    document.querySelectorAll(".topbar__group-btn").forEach((button) => {
      const menu = menuOf(button);
      button.addEventListener("click", () => {
        if (button.getAttribute("aria-expanded") === "true") closeMenus();
        else openMenu(button, false);
      });
      button.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          openMenu(button, true);
        }
      });
      menu.addEventListener("keydown", (event) => {
        const links = menuLinks(menu);
        const index = links.indexOf(document.activeElement);
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          event.preventDefault();
          const step = event.key === "ArrowDown" ? 1 : -1;
          links[(index + step + links.length) % links.length]?.focus();
        } else if (event.key === "Escape") {
          closeMenus();
          button.focus();
        }
      });
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".topbar__group")) closeMenus();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeMenus();
    });
    document.addEventListener("focusin", (event) => {
      if (!event.target.closest(".topbar__group")) closeMenus();
    });
    window.addEventListener("resize", () => closeMenus());
    window.addEventListener("scroll", () => closeMenus(), { passive: true });
    document.querySelector(".topbar__nav")?.addEventListener("scroll", () => closeMenus(), { passive: true });
  }

  document.addEventListener("DOMContentLoaded", () => {
    markCurrentSection();
    setupMenus();
  });
})();
