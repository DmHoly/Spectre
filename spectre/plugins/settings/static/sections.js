/* Le menu latéral des paramètres : une entrée par section. Une nouvelle couche de réglages
   ajoute ici son entrée (et sa page, dans le manifeste du plugin settings). */

const SETTINGS_SECTIONS = [
  { href: "/parametres/plugins", label: "Plugins", icon: "puzzle" },
  { href: "/parametres/base-de-donnees", label: "Base de données", icon: "database" },
];

function mountSettingsNav() {
  const nav = document.getElementById("settings-nav");
  if (!nav) return;
  const path = window.location.pathname;
  nav.innerHTML = SETTINGS_SECTIONS.map((section) => {
    const current = path === section.href ? ' aria-current="page"' : "";
    return `<a class="settings-side__link" href="${escapeHtml(section.href)}"${current}>${settingsIcon(section.icon, 18)}<span>${escapeHtml(section.label)}</span></a>`;
  }).join("");
}

document.addEventListener("DOMContentLoaded", mountSettingsNav);
