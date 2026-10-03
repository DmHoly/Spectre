const { slug } = routeParams("/microprojets/{slug}");
const errorBox = document.getElementById("error");
let currentUser = null;
let currentRole = null;
let currentMicroprojectName = null;

// Messages : dans le dialogue des membres quand il est ouvert (la page est derrière), sur la page sinon.
const inMembersDialog = () => document.getElementById("members-dialog").open;

function showError(err) {
  const box = inMembersDialog() ? document.getElementById("members-error") : errorBox;
  box.textContent = err.message || String(err);
  box.style.display = "block";
}

function clearErrorFlash() {
  for (const id of ["error", "flash", "members-error", "members-flash"]) document.getElementById(id).style.display = "none";
}

function showFlash(message) {
  const flashBox = document.getElementById(inMembersDialog() ? "members-flash" : "flash");
  flashBox.textContent = message;
  flashBox.style.display = "block";
}

// Le rôle d'un membre : une liste pour un propriétaire (sauf pour le créateur, qui le reste), un badge sinon.
function memberRoleCell(member) {
  if (currentRole !== "owner" || member.is_creator) {
    return `<span class="badge badge-role">${escapeHtml(roleLabel(member.role))}</span>`;
  }
  const options = Object.keys(ROLE_LABELS)
    .map((role) => `<option value="${role}"${role === member.role ? " selected" : ""}>${escapeHtml(roleLabel(role))}</option>`)
    .join("");
  return `<select class="field js-member-role" data-user-id="${member.id}" aria-label="Droit de ${escapeHtml(member.name)}" style="padding:4px 8px;font-size:12.5px;">${options}</select>`;
}

function memberRow(member) {
  const canRemove = currentRole === "owner" && !member.is_creator;
  return `
    <tr style="border-top:1px solid var(--border-soft);">
      <td style="padding:10px 0;">
        <div style="font-weight:600;">${escapeHtml(member.name)}</div>
        <div style="color:var(--text-faint);font-size:12px;">${escapeHtml(member.email)}${member.is_creator ? " &middot; a créé le µprojet" : ""}</div>
      </td>
      <td>${memberRoleCell(member)}</td>
      <td style="text-align:right;">
        ${canRemove ? `<button class="btn btn-line js-remove-member" data-user-id="${member.id}" style="padding:5px 10px;font-size:12px;">Retirer</button>` : ""}
      </td>
    </tr>`;
}

async function loadMembers() {
  try {
    const members = await microprojectsApi.members(slug);
    document.getElementById("members-body").innerHTML = members.map(memberRow).join("");
  } catch (err) {
    showError(err);
  }
}

// Une écriture sur les membres : la liste se relit, réussie ou refusée (409 : le dernier propriétaire, par exemple).
async function writeMembers(call) {
  clearErrorFlash();
  try {
    await call();
  } catch (err) {
    showError(err);
  }
  loadMembers();
}

document.getElementById("members-body").addEventListener("change", (event) => {
  const select = event.target.closest(".js-member-role");
  if (select) writeMembers(() => microprojectsApi.updateMember(slug, select.dataset.userId, { role: select.value }));
});
document.getElementById("members-body").addEventListener("click", (event) => {
  const button = event.target.closest(".js-remove-member");
  if (button) writeMembers(() => microprojectsApi.removeMember(slug, button.dataset.userId));
});

function invitationRow(invitation) {
  return `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--border-soft);">
      <div>
        <div style="font-size:13px;">${escapeHtml(invitation.email)}</div>
        <div style="font-size:11.5px;color:var(--text-faint);">Invitation envoyée &middot; ${escapeHtml(roleLabel(invitation.role))}</div>
      </div>
      <button class="btn btn-line js-cancel-invitation" data-invitation-id="${invitation.id}" style="padding:5px 10px;font-size:12px;">Annuler</button>
    </div>`;
}

async function loadInvitations() {
  const wrap = document.getElementById("invitations-wrap");
  if (currentRole !== "owner") {
    wrap.innerHTML = "";
    return;
  }
  try {
    const invitations = await microprojectsApi.invitations(slug);
    wrap.innerHTML = invitations.length
      ? `<div style="margin-top:14px;"><div class="section-title" style="margin-bottom:4px;">Invitations en attente</div>${invitations.map(invitationRow).join("")}</div>`
      : "";
    document.querySelectorAll(".js-cancel-invitation").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await microprojectsApi.cancelInvitation(slug, btn.dataset.invitationId);
          loadInvitations();
        } catch (err) {
          showError(err);
        }
      });
    });
  } catch (err) {
    // silent: owner-only, non-critical secondary list
  }
}

const membersDialog = document.getElementById("members-dialog");
document.getElementById("members-btn").addEventListener("click", () => {
  clearErrorFlash();
  hideInviteOffer();
  membersDialog.showModal();
});
document.getElementById("close-members-dialog").addEventListener("click", () => membersDialog.close());

document.getElementById("delete-microproject-btn").addEventListener("click", async () => {
  const typed = document.getElementById("delete-confirm-name").value.trim();
  if (typed !== currentMicroprojectName) {
    showError(new Error("Le nom saisi ne correspond pas au nom du µprojet."));
    return;
  }
  try {
    await microprojectsApi.remove(slug, typed);
    window.location.href = "/";
  } catch (err) {
    showError(err);
  }
});

// Ajouter un membre : un compte existant d'abord ; sans compte (404 « no_account »), on propose de
// l'inviter par e-mail - un second appel, explicite.
const inviteOffer = document.getElementById("invite-offer");
let pendingInvite = null;

function hideInviteOffer() {
  pendingInvite = null;
  inviteOffer.style.display = "none";
}

document.getElementById("add-member-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearErrorFlash();
  hideInviteOffer();
  const body = { email: document.getElementById("member-email").value, role: document.getElementById("member-role").value };
  try {
    await microprojectsApi.addMember(slug, body);
    document.getElementById("member-email").value = "";
    showFlash("Personne ajoutée au µprojet.");
    loadMembers();
  } catch (err) {
    if (err.status === 404 && err.data && err.data.code === "no_account") {
      pendingInvite = body;
      document.getElementById("invite-offer-text").textContent = `Aucun compte Spectre pour ${body.email}. Lui envoyer une invitation par e-mail ?`;
      inviteOffer.style.display = "";
    } else {
      showError(err);
    }
  }
});

document.getElementById("invite-offer-btn").addEventListener("click", async () => {
  const body = pendingInvite;
  hideInviteOffer();
  if (!body) return;
  try {
    await microprojectsApi.invite(slug, body);
    document.getElementById("member-email").value = "";
    showFlash(`Invitation envoyée à ${body.email}.`);
    loadInvitations();
  } catch (err) {
    showError(err);
  }
});
document.getElementById("invite-offer-cancel").addEventListener("click", hideInviteOffer);

const newExperienceDialog = document.getElementById("new-experience-dialog");

async function fetchSavedStructures() {
  return processLibraryApi.savedStructures({ microproject: slug });
}

function savedStructureOptionsHtml(entries) {
  if (!entries.length) return { html: `<option value="">Aucune structure enregistrée</option>`, empty: true };
  const scopeSuffix = { builtin: " (intégrée)", shared: " (partagée)", microproject: "" };
  const html = entries
    .map((s) => `<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)}${scopeSuffix[s.scope] || ""}</option>`)
    .join("");
  return { html, empty: false };
}

async function openNewExperienceDialog() {
  clearErrorFlash();
  try {
    const [experiences, library] = await Promise.all([
      experimentsApi.list(slug, { status: "all", limit: 200 }),
      fetchSavedStructures(),
    ]);
    const expOptions = experiences.items.map((exp) => `<option value="${exp.id}">${escapeHtml(exp.title)}</option>`).join("");
    document.getElementById("continue-select").innerHTML = experiences.items.length
      ? expOptions
      : `<option value="">Aucune expérience pour l'instant</option>`;
    document.getElementById("template-select").innerHTML = savedStructureOptionsHtml(library).html;

    newExperienceDialog.showModal();
  } catch (err) {
    showError(err);
  }
}

document.getElementById("option-scratch").addEventListener("click", () => {
  window.location.href = `/microprojets/${encodeURIComponent(slug)}/structures/nouvelle`;
});

document.getElementById("option-image").addEventListener("click", () => {
  window.location.href = `/microprojets/${encodeURIComponent(slug)}/structures/image`;
});

document.getElementById("option-template").addEventListener("click", () => {
  const source = document.getElementById("template-select").value;
  if (!source) return;
  window.location.href = `/microprojets/${encodeURIComponent(slug)}/structures/nouvelle?structure=${encodeURIComponent(source)}`;
});

document.getElementById("option-new-library-structure").addEventListener("click", (event) => {
  event.preventDefault();
  window.location.href = `/microprojets/${encodeURIComponent(slug)}/structures/bibliotheque/nouvelle?retour=nouvelle-experience`;
});

document.getElementById("option-continue").addEventListener("click", () => {
  const source = document.getElementById("continue-select").value;
  if (!source) return;
  window.location.href = `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(source)}/evoluer`;
});

document.getElementById("option-continue-image").addEventListener("click", () => {
  const source = document.getElementById("continue-select").value;
  if (!source) return;
  window.location.href = `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(source)}/evoluer-image`;
});

document.getElementById("cancel-new-experience").addEventListener("click", () => newExperienceDialog.close());

async function init() {
  try {
    const microproject = await microprojectsApi.get(slug);
    currentRole = microproject.role;
    currentMicroprojectName = microproject.name;
    document.getElementById("microproject-name").textContent = microproject.name;
    document.getElementById("microproject-description").textContent = microproject.description;
    const codeEl = document.getElementById("microproject-code");
    if (microproject.code) {
      codeEl.textContent = `µprojet ${microproject.code}`;
      codeEl.style.display = "";
      document.title = `${microproject.code} · ${microproject.name} — Spectre`;
    }
    const area = microproject.area;
    const areaCrumb = document.getElementById("area-crumb");
    if (area) {
      areaCrumb.textContent = area.name;
      areaCrumb.href = `/management/${encodeURIComponent(area.slug)}`;
    } else {
      areaCrumb.textContent = "Non classé";
    }
    const thematic = microproject.thematic;
    const thematicCrumb = document.getElementById("thematic-crumb");
    thematicCrumb.innerHTML =
      thematic && area
        ? ` / <a href="/management/${encodeURIComponent(area.slug)}/thematiques/${encodeURIComponent(thematic.slug)}">${escapeHtml(thematic.name)}</a>`
        : thematic
          ? ` / ${escapeHtml(thematic.name)}`
          : "";
    document.getElementById("microproject-owner").innerHTML = ownerChipHtml(microproject.owners);
    document.getElementById("crumb").textContent =
      "/ " + [area && area.name, thematic && thematic.name, microproject.code || microproject.name].filter(Boolean).join(" / ");

    if (currentRole === "editor" || currentRole === "owner") {
      document.getElementById("new-structure-btn").style.display = "";
      document.getElementById("new-structure-btn").addEventListener("click", openNewExperienceDialog);
    }
    if (currentRole === "owner") {
      document.getElementById("add-member-form").style.display = "grid";
      document.getElementById("danger-zone").style.display = "block";
    }
  } catch (err) {
    showError(err);
    return;
  }

  document.getElementById("lineage-legend").innerHTML = lineageLegendHtml({ lot: true, wafers: true });
  mountLineage(document.querySelector(".lineage-layout"), { microprojectSlug: slug, canEdit: currentRole === "editor" || currentRole === "owner" });
  loadMembers();
  loadInvitations();
}

init();
