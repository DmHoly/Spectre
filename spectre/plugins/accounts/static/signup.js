/* Inscription, et l'autre bout d'un e-mail d'invitation (/inscription?invitation=<jeton>) : on crée
   le compte puis on accepte l'invitation - ou, si un compte existe déjà pour l'adresse invitée, on
   se connecte (retour ici ensuite) puis on l'accepte. */

const form = document.getElementById("register-form");
const errorBox = document.getElementById("error");
const note = document.getElementById("invitation-note");
const joinPanel = document.getElementById("invitation-join");
const invitationToken = new URLSearchParams(window.location.search).get("invitation");
// la connexion revient sur cette page, invitation comprise
const loginUrl = "/connexion?suite=" + encodeURIComponent(window.location.pathname + window.location.search);
let invitation = null;

function showError(message) {
  errorBox.textContent = message;
  errorBox.style.display = "block";
}

// remplace le formulaire par une phrase et un bouton
function offer(text, label, action) {
  form.style.display = "none";
  document.getElementById("invitation-join-text").textContent = text;
  const button = document.getElementById("invitation-join-btn");
  button.textContent = label;
  button.onclick = async () => {
    errorBox.style.display = "none";
    button.disabled = true;
    try {
      await action();
    } catch (err) {
      showError(err.message);
      button.disabled = false;
    }
  };
  joinPanel.style.display = "block";
}

// rejoint le µprojet avec le compte connecté, puis ouvre sa page
async function acceptInvitation() {
  const { microproject } = await microprojectsApi.acceptInvitation(invitationToken, { redirectOn401: false });
  window.location.href = `/microprojets/${encodeURIComponent(microproject.slug)}`;
}

function offerLogin() {
  offer(`Un compte existe déjà pour ${invitation.email} : connectez-vous pour rejoindre le µprojet.`, "Se connecter", async () => {
    window.location.href = loginUrl;
  });
}

async function loadInvitation() {
  if (!invitationToken) return;
  try {
    invitation = await microprojectsApi.invitation(invitationToken, { redirectOn401: false });
  } catch (err) {
    note.className = "error";
    note.textContent = "Ce lien d'invitation est invalide ou a expiré - vous pouvez tout de même créer un compte.";
    note.style.display = "block";
    return;
  }
  document.getElementById("subtitle").textContent = `Vous rejoignez le µprojet « ${invitation.microproject_name} ».`;
  document.getElementById("login-link").href = loginUrl;
  const emailField = document.getElementById("email");
  emailField.value = invitation.email;
  emailField.readOnly = true;

  // sans compte pour l'adresse invitée, le formulaire suffit ; sinon il faut s'y connecter
  if (!invitation.account_exists) return;
  const user = await accountsApi.me({ redirectOn401: false }).catch(() => null);
  if (user && user.email === invitation.email) {
    offer(`Vous êtes connecté(e) en tant que ${user.email}.`, "Rejoindre le µprojet", acceptInvitation);
  } else if (user) {
    offer(`Vous êtes connecté(e) avec ${user.email}, mais cette invitation est adressée à ${invitation.email}.`, "Changer de compte", async () => {
      await accountsApi.logout({ redirectOn401: false });
      window.location.reload();
    });
  } else {
    offerLogin();
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.style.display = "none";
  const name = document.getElementById("name").value;
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  try {
    await accountsApi.register({ name, email, password }, { redirectOn401: false });
  } catch (err) {
    if (err.status === 409 && invitation) offerLogin();
    else showError(err.message);
    return;
  }
  if (!invitation) {
    window.location.href = "/";
    return;
  }
  try {
    await acceptInvitation();
  } catch (err) {
    showError(`Votre compte est créé, mais l'invitation n'a pas pu être acceptée : ${err.message}`);
    form.style.display = "none";
  }
});

loadInvitation();
