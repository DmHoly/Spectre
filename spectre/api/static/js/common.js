/* Utilitaires partagés par les pages connectées : identité de l'utilisateur dans la barre du
   haut, déconnexion, badges de statut, formatage de dates - rien de spécifique à un écran. */

const STATUS_LABELS = {
  draft: { label: "Brouillon", cls: "badge-draft" },
  running: { label: "En cours", cls: "badge-running" },
  concluded: { label: "Conclue", cls: "badge-concluded" },
  abandoned: { label: "Abandonnée", cls: "badge-abandoned" },
};

const ROLE_LABELS = {
  owner: "Propriétaire",
  editor: "Peut modifier",
  viewer: "Lecture seule",
};

function statusBadgeHtml(status) {
  const info = STATUS_LABELS[status] || STATUS_LABELS.draft;
  return `<span class="badge ${info.cls}"><span class="dot"></span>${info.label}</span>`;
}

function roleLabel(role) {
  return ROLE_LABELS[role] || role;
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

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

async function mountUserBadge() {
  const nameEls = document.querySelectorAll(".js-user-name");
  const initialsEls = document.querySelectorAll(".js-user-initials");
  try {
    const user = await api.get("/api/auth/me");
    nameEls.forEach((el) => (el.textContent = user.name));
    initialsEls.forEach((el) => (el.textContent = initials(user.name)));
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
        await api.post("/api/auth/logout", {}, { redirectOn401: false });
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
