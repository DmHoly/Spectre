/* Page d'une équipe (/equipes/{slug}) : ses membres et leur rôle (manager ou membre), et les
   projets corporate qu'elle possède (areasApi.list({team})). L'équipe dit ce que l'appelant peut
   faire : can_edit (renommer, supprimer : un administrateur), can_manage (gérer ses membres : un
   administrateur ou un de ses managers). */

const { slug } = routeParams("/equipes/{slug}");
const TEAM_ROLE_LABELS = { manager: "Manager", member: "Membre" };

const errorBox = document.getElementById("error");
const flashBox = document.getElementById("flash");
function showError(err) {
  flashBox.style.display = "none";
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function flash(message) {
  errorBox.style.display = "none";
  flashBox.textContent = message;
  flashBox.style.display = "block";
  setTimeout(() => (flashBox.style.display = "none"), 3000);
}

let team = null;

function roleCell(member) {
  if (!team.can_manage) {
    return `<span class="team-role${member.role === "manager" ? " team-role--manager" : ""}">${escapeHtml(TEAM_ROLE_LABELS[member.role] || member.role)}</span>`;
  }
  const options = Object.entries(TEAM_ROLE_LABELS)
    .map(([role, label]) => `<option value="${role}"${role === member.role ? " selected" : ""}>${label}</option>`)
    .join("");
  return `<select class="field member__role js-member-role" data-user-id="${member.id}" aria-label="Rôle de ${escapeHtml(member.name)} dans l'équipe">${options}</select>`;
}

function memberItem(member) {
  const remove = team.can_manage
    ? `<button type="button" class="btn btn-line member__remove js-remove-member" data-user-id="${member.id}" data-name="${escapeHtml(member.name)}">Retirer</button>`
    : "";
  return `
    <li class="member">
      <span class="avatar avatar--xs" aria-hidden="true">${escapeHtml(initials(member.name))}</span>
      <div class="member__who">
        <div class="member__name">${escapeHtml(member.name)}</div>
        <div class="member__email">${escapeHtml(member.email)}</div>
      </div>
      ${roleCell(member)}
      ${remove}
    </li>`;
}

function renderTeam() {
  document.title = `${team.name} — Spectre`;
  document.getElementById("team-crumb").textContent = team.name;
  document.getElementById("crumb").textContent = `/ Équipes / ${team.name}`;
  document.getElementById("team-name").textContent = team.name;
  const managers = team.managers.map((m) => m.name).join(", ");
  document.getElementById("team-summary").textContent = managers
    ? `Manager${team.managers.length > 1 ? "s" : ""} : ${managers}.`
    : "Cette équipe n'a pas encore de manager.";
  document.getElementById("rename-team-btn").style.display = team.can_edit ? "" : "none";
  document.getElementById("delete-team-btn").style.display = team.can_edit ? "" : "none";
  document.getElementById("add-member-form").style.display = team.can_manage ? "" : "none";
  document.getElementById("members-help").textContent = team.can_manage
    ? "Une équipe garde au moins un manager : nommez-en un autre avant de retirer ou de rétrograder le dernier."
    : "Seuls un administrateur ou un manager de l'équipe en gèrent les membres.";
}

async function loadMembers() {
  const list = document.getElementById("members");
  const members = await teamsApi.members(slug);
  document.getElementById("members-count").textContent = `${members.length} membre${members.length > 1 ? "s" : ""}`;
  list.innerHTML = members.length
    ? members.map(memberItem).join("")
    : `<li class="teams-empty">Aucun membre pour l'instant.</li>`;
  list.removeAttribute("aria-busy");
}

async function loadAreas() {
  const list = document.getElementById("team-areas");
  const areas = await areasApi.list({ team: slug });
  list.innerHTML = areas.length
    ? areas
        .map(
          (area) =>
            `<li><a href="/management/${encodeURIComponent(area.slug)}"><span>${escapeHtml(area.name)}</span>${
              area.code_prefix ? `<span class="mono" title="Préfixe des numéros de ses µprojets">${escapeHtml(area.code_prefix)}</span>` : ""
            }</a></li>`
        )
        .join("")
    : `<li class="teams-empty">Aucun projet corporate rattaché à cette équipe.</li>`;
  list.removeAttribute("aria-busy");
}

async function load() {
  try {
    team = await teamsApi.get(slug);
    renderTeam();
    await Promise.all([loadMembers(), loadAreas()]);
  } catch (err) {
    showError(err);
  }
}

// Une écriture sur l'équipe : l'équipe et ses membres se relisent, réussie ou refusée (409 : le
// dernier manager, par exemple) - un manager qui se retire lui-même perd aussitôt ses droits.
async function write(call, message) {
  try {
    await call();
    if (message) flash(message);
  } catch (err) {
    showError(err);
  }
  try {
    team = await teamsApi.get(slug);
    renderTeam();
    await loadMembers();
  } catch (err) {
    showError(err);
  }
}

document.getElementById("members").addEventListener("change", (event) => {
  const select = event.target.closest(".js-member-role");
  if (select) write(() => teamsApi.updateMember(slug, select.dataset.userId, { role: select.value }), "Rôle mis à jour.");
});
document.getElementById("members").addEventListener("click", (event) => {
  const button = event.target.closest(".js-remove-member");
  if (!button || !window.confirm(`Retirer ${button.dataset.name} de l'équipe ?`)) return;
  write(() => teamsApi.removeMember(slug, button.dataset.userId), "Membre retiré.");
});
document.getElementById("add-member-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const email = document.getElementById("member-email");
  const role = document.getElementById("member-role");
  write(async () => {
    await teamsApi.addMember(slug, { email: email.value, role: role.value });
    email.value = "";
  }, "Membre ajouté.");
});

const renameDialog = document.getElementById("rename-team-dialog");
document.getElementById("rename-team-btn").addEventListener("click", () => {
  document.getElementById("rename-team-name").value = team.name;
  renameDialog.showModal();
});
document.getElementById("rename-team-cancel").addEventListener("click", () => renameDialog.close());
document.getElementById("rename-team-form").addEventListener("submit", (event) => {
  event.preventDefault();
  renameDialog.close();
  write(() => teamsApi.update(slug, { name: document.getElementById("rename-team-name").value }), "Équipe renommée.");
});
document.getElementById("delete-team-btn").addEventListener("click", async () => {
  if (!window.confirm(`Supprimer l'équipe « ${team.name} » ? Ses projets corporate restent, sans équipe : seul un administrateur les gère alors.`)) return;
  try {
    await teamsApi.remove(slug);
    window.location.href = "/equipes";
  } catch (err) {
    showError(err);
  }
});

load();
