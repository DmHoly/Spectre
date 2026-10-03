const form = document.getElementById("register-form");
const errorBox = document.getElementById("error");
const invitationToken = new URLSearchParams(window.location.search).get("invitation");

async function loadInvitation() {
  if (!invitationToken) return;
  try {
    const invitation = await microprojectsApi.invitation(invitationToken, { redirectOn401: false });
    document.getElementById("subtitle").textContent = `Vous rejoignez le µprojet « ${invitation.microproject_name} ».`;
    const emailField = document.getElementById("email");
    emailField.value = invitation.email;
    emailField.readOnly = true;
  } catch (err) {
    document.getElementById("invitation-note").className = "error";
    document.getElementById("invitation-note").textContent = "Ce lien d'invitation est invalide ou a expiré - vous pouvez tout de même créer un compte.";
    document.getElementById("invitation-note").style.display = "block";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.style.display = "none";
  const name = document.getElementById("name").value;
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  try {
    await accountsApi.register({ name, email, password, invitation: invitationToken || null }, { redirectOn401: false });
    window.location.href = "/";
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.style.display = "block";
  }
});

loadInvitation();
