/* Liste des équipes (/equipes) : chacune avec ses managers, son nombre de membres et le rôle de
   l'appelant ; un administrateur en crée (accountsApi.me : is_admin). */

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

const TEAM_ROLE_LABELS = { manager: "Manager", member: "Membre" };

function teamCard(team) {
  const managers = team.managers.length
    ? `Manager${team.managers.length > 1 ? "s" : ""} : ${team.managers.map((m) => escapeHtml(m.name)).join(", ")}`
    : "Aucun manager pour l'instant";
  const mine = team.my_role
    ? `<span class="team-role${team.my_role === "manager" ? " team-role--manager" : ""}" title="Votre rôle dans l'équipe">Vous : ${escapeHtml(TEAM_ROLE_LABELS[team.my_role] || team.my_role)}</span>`
    : "";
  return `
    <a class="team-card" href="/equipes/${encodeURIComponent(team.slug)}">
      <div class="team-card__head">
        <div class="team-card__name">${escapeHtml(team.name)}</div>
        ${mine}
      </div>
      <div class="team-card__managers">${managers}</div>
      <div class="team-card__foot"><span>${team.member_count} membre${team.member_count > 1 ? "s" : ""}</span></div>
    </a>`;
}

async function load() {
  const grid = document.getElementById("teams");
  try {
    const [teams, me] = await Promise.all([teamsApi.list(), accountsApi.me()]);
    grid.innerHTML = teams.length
      ? teams.map(teamCard).join("")
      : `<div class="empty-state card" style="grid-column:1/-1;"><div style="font-weight:600;color:var(--text-soft);">Aucune équipe</div><div class="teams-empty" style="margin-top:4px;">${
          me.is_admin ? "Créez la première avec « + Nouvelle équipe »." : "Un administrateur crée les équipes."
        }</div></div>`;
    grid.removeAttribute("aria-busy");
    if (me.is_admin) document.getElementById("new-team-btn").style.display = "";
  } catch (err) {
    grid.innerHTML = "";
    showError(err);
  }
}

const dialog = document.getElementById("new-team-dialog");
document.getElementById("new-team-btn").addEventListener("click", () => {
  document.getElementById("team-name").value = "";
  dialog.showModal();
});
document.getElementById("cancel-team").addEventListener("click", () => dialog.close());
document.getElementById("new-team-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const team = await teamsApi.create({ name: document.getElementById("team-name").value });
    window.location.href = `/equipes/${encodeURIComponent(team.slug)}`;
  } catch (err) {
    dialog.close();
    showError(err);
  }
});

load();
