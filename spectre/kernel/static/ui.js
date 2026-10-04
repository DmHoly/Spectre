/* Utilitaires d'affichage du noyau, sans rien de métier : échappement HTML, dates et durées en
   français, initiales, et paramètres de chemin d'une page (routeParams). Chargé par toutes les
   pages après api.js. */

function escapeHtml(value) {
  // textContent->innerHTML escapes & < > but NOT quotes - every call site in this codebase also
  // interpolates the result inside a double-quoted HTML attribute (value="...", data-x="...",
  // href="..."), where an unescaped `"` breaks out and lets attacker-controlled text (a structure
  // name, a preset name, a link of a notebook entry - anything a microproject editor can set) inject a
  // live attribute (onmouseover=...) that fires for any other member who views the page. Escaping
  // both quote characters here closes that regardless of which attribute a caller uses it in.
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function initials(name) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : parts[0].slice(0, 2);
  return letters.toUpperCase();
}

function formatDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  return date.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

function timeAgo(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  const steps = [
    [60, "seconde"],
    [60, "minute"],
    [24, "heure"],
    [30, "jour"],
    [12, "mois"],
    [Infinity, "an"],
  ];
  let value = seconds;
  let unit = "seconde";
  for (const [size, name] of steps) {
    if (value < size) {
      unit = name;
      break;
    }
    value = Math.floor(value / size);
    unit = name;
  }
  if (unit === "seconde" && value < 10) return "à l'instant";
  const plural = value > 1 && !unit.endsWith("s") ? "s" : "";
  return `il y a ${value} ${unit}${plural}`;
}

// Durée compacte en français : « 40 min », « 5 h », « 3 j », « 2 sem. », « 4 mois », « 1 an 2 mois ».
function formatDuration(ms) {
  const minutes = Math.max(0, Math.round(ms / 60000));
  if (minutes < 60) return minutes < 1 ? "< 1 min" : `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days} j`;
  if (days < 60) return `${Math.round(days / 7)} sem.`;
  const months = Math.round(days / 30.44);
  if (months < 12) return `${months} mois`;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  return `${years} an${years > 1 ? "s" : ""}${rest ? ` ${rest} mois` : ""}`;
}

// Temps écoulé entre deux dates, ou jusqu'à maintenant tant que la seconde est vide - « 12 j » ou
// « depuis 12 j ».
function elapsedLabel(started, ended) {
  if (!started) return "";
  const end = ended ? new Date(ended) : new Date();
  const span = formatDuration(end - new Date(started));
  return ended ? span : `depuis ${span}`;
}

/* Les paramètres nommés d'une page, lus dans location.pathname avec le gabarit de sa route (celui
   de son Page(...) côté serveur) : routeParams("/microprojets/{slug}/refs") -> {slug: "..."},
   décodés. Plusieurs gabarits possibles (une page servie sous plusieurs routes) : le premier qui
   correspond. null si aucun ne correspond. */
function routeParams(patterns, path = window.location.pathname) {
  const list = Array.isArray(patterns) ? patterns : [patterns];
  for (const pattern of list) {
    const names = [];
    const source = pattern
      .split(/(\{\w+\})/)
      .map((part) => {
        const name = part.match(/^\{(\w+)\}$/);
        if (name) {
          names.push(name[1]);
          return "([^/]+)";
        }
        return part.replace(/[.*+?^$()|[\]\\]/g, "\\$&");
      })
      .join("");
    const match = new RegExp(`^${source}/?$`).exec(path);
    if (!match) continue;
    const params = {};
    names.forEach((name, i) => {
      try {
        params[name] = decodeURIComponent(match[i + 1]);
      } catch (e) {
        params[name] = match[i + 1];
      }
    });
    return params;
  }
  return null;
}
