/* Le menu latéral des paramètres : une entrée par section. Une nouvelle couche de réglages
   ajoute ici son entrée (et sa page, dans le manifeste du plugin settings). Une section apportée
   par un plugin optionnel le nomme (plugin) : elle disparaît quand il est éteint. */

const SETTINGS_SECTIONS = [
  { href: "/parametres/plugins", label: "Plugins", icon: "puzzle" },
  { href: "/parametres/base-de-donnees", label: "Base de données", icon: "database" },
  { href: "/parametres/utilisation", label: "Utilisation", icon: "activity", plugin: "usage" },
];

function mountSettingsNav() {
  const nav = document.getElementById("settings-nav");
  if (!nav) return;
  const path = window.location.pathname;
  const sections = SETTINGS_SECTIONS.filter((section) => !section.plugin || pluginEnabled(section.plugin));
  nav.innerHTML = sections.map((section) => {
    const current = path === section.href ? ' aria-current="page"' : "";
    return `<a class="settings-side__link" href="${escapeHtml(section.href)}"${current}>${settingsIcon(section.icon, 18)}<span>${escapeHtml(section.label)}</span></a>`;
  }).join("");
}

document.addEventListener("DOMContentLoaded", mountSettingsNav);
