/* Le menu latéral de PRISM : une entrée par section. Une nouvelle sous-page ajoute ici son entrée
   (et sa page, dans le manifeste du plugin prism). Les icônes sont celles des paramètres
   (settings/static/icons.js). */

const PRISM_SECTIONS = [
  { href: "/prism/donnees", label: "Données", icon: "database", match: /^\/prism\/donnees/ },
];

function mountPrismNav() {
  const nav = document.getElementById("prism-nav");
  if (!nav) return;
  const path = window.location.pathname;
  nav.innerHTML = PRISM_SECTIONS.map((section) => {
    const current = section.match.test(path) ? ' aria-current="page"' : "";
    return `<a class="settings-side__link" href="${escapeHtml(section.href)}"${current}>${settingsIcon(section.icon, 18)}<span>${escapeHtml(section.label)}</span></a>`;
  }).join("");
}

document.addEventListener("DOMContentLoaded", mountPrismNav);
