/* Rôles d'un membre de µprojet et puce « Propriétaire » d'un µprojet. */

const ROLE_LABELS = {
  owner: "Propriétaire",
  editor: "Peut modifier",
  viewer: "Lecture seule",
};

function roleLabel(role) {
  return ROLE_LABELS[role] || role;
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
