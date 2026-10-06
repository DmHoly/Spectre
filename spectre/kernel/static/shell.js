/* La barre du haut commune (rendue par le noyau, kernel/pages.py, à partir des NavEntry des
   plugins) : marque la section courante de la navigation principale (aria-current="page",
   souligné or en CSS). Chaque lien porte l'expression régulière de sa section (data-match) ; sans
   elle, c'est son href exact qui compte. Le premier lien qui correspond au chemin de la page gagne. */

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
    const links = [...document.querySelectorAll(".topbar__nav .topbar__link, .topbar__tool")];
    const current = links.find((link) => sectionMatches(link, path));
    if (current) current.setAttribute("aria-current", "page");
  }

  document.addEventListener("DOMContentLoaded", markCurrentSection);
})();
