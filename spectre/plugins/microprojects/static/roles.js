/* Rôles d'un membre de µprojet et puce « Propriétaire » d'un µprojet. */

const ROLE_LABELS = {
  owner: "Propriétaire",
  editor: "Peut modifier",
  viewer: "Lecture seule",
};

// D'où vient un rôle effectif, quand ce n'est pas l'adhésion (role_source d'un µprojet).
const ROLE_SOURCE_LABELS = {
  team_manager: "manager",
  admin: "admin",
};

// « Propriétaire », ou « Propriétaire (manager) » avec role_source : le rôle effectif tel que le
// serveur l'a calculé (manager de l'équipe du µprojet, administrateur), sans rien recalculer.
function roleLabel(role, source) {
  const label = ROLE_LABELS[role] || role;
  return ROLE_SOURCE_LABELS[source] ? `${label} (${ROLE_SOURCE_LABELS[source]})` : label;
}

// « Propriétaire » d'un µprojet : le premier (son créateur s'il l'est toujours), « +N » s'il y en a d'autres.
function ownerChipHtml(owners, { label = true } = {}) {
  if (!owners || !owners.length) return "";
  const [first, ...others] = owners;
  const all = owners.map((o) => o.name).join(", ");
  return `<span class="owner-chip" title="Propriétaire${owners.length > 1 ? "s" : ""} : ${escapeHtml(all)}">
      <span class="avatar avatar--xs" aria-hidden="true">${escapeHtml(initials(first.name))}</span>
      ${label ? `<span class="owner-chip__label">Propriétaire</span>` : ""}
      <span class="owner-chip__name">${escapeHtml(first.name)}</span>${others.length ? `<span class="owner-chip__more">+${others.length}</span>` : ""}
    </span>`;
}
