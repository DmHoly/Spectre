const { slug } = routeParams("/microprojets/{slug}");
const errorBox = document.getElementById("error");
let currentUser = null;
let currentRole = null;
let currentMicroprojectName = null;

function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

function clearErrorFlash() {
  errorBox.style.display = "none";
  document.getElementById("flash").style.display = "none";
}

function showFlash(message) {
  const flashBox = document.getElementById("flash");
  flashBox.textContent = message;
  flashBox.style.display = "block";
}

function memberRow(member) {
  const canManage = currentRole === "owner";
  return `
    <tr style="border-top:1px solid var(--border-soft);">
      <td style="padding:10px 0;">
        <div style="font-weight:600;">${escapeHtml(member.name)}</div>
        <div style="color:var(--text-faint);font-size:12px;">${escapeHtml(member.email)}</div>
      </td>
      <td><span class="badge badge-role">${escapeHtml(roleLabel(member.role))}</span></td>
      <td style="text-align:right;">
        ${canManage ? `<button class="btn btn-line js-remove-member" data-user-id="${member.id}" style="padding:5px 10px;font-size:12px;">Retirer</button>` : ""}
      </td>
    </tr>`;
}

async function loadMembers() {
  try {
    const members = await microprojectsApi.members(slug);
    document.getElementById("members-body").innerHTML = members.map(memberRow).join("");
    document.querySelectorAll(".js-remove-member").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await microprojectsApi.removeMember(slug, btn.dataset.userId);
          loadMembers();
        } catch (err) {
          showError(err);
        }
      });
    });
  } catch (err) {
    showError(err);
  }
}

function invitationRow(invitation) {
  return `
    <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--border-soft);">
      <div>
        <div style="font-size:13px;">${escapeHtml(invitation.email)}</div>
        <div style="font-size:11.5px;color:var(--text-faint);">Invitation envoyée &middot; ${escapeHtml(roleLabel(invitation.role))}</div>
      </div>
      <button class="btn btn-line js-cancel-invitation" data-token="${escapeHtml(invitation.token)}" style="padding:5px 10px;font-size:12px;">Annuler</button>
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
          await microprojectsApi.cancelInvitation(slug, btn.dataset.token);
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

document.getElementById("add-member-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearErrorFlash();
  const email = document.getElementById("member-email").value;
  const role = document.getElementById("member-role").value;
  try {
    const result = await microprojectsApi.addMember(slug, { email, role });
    document.getElementById("member-email").value = "";
    showFlash(result.status === "invited" ? "Invitation envoyée par e-mail." : "Personne ajoutée au µprojet.");
    loadMembers();
    loadInvitations();
  } catch (err) {
    showError(err);
  }
});

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
    const area = microproject.management_area;
    const areaCrumb = document.getElementById("area-crumb");
    if (area) {
      areaCrumb.textContent = area.name;
      areaCrumb.href = `/management/${encodeURIComponent(area.slug)}`;
    } else {
      areaCrumb.textContent = "Non classé";
    }
    const thematic = microproject.thematique;
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
