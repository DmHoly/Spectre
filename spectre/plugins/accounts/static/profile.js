const profileError = document.getElementById("profile-error");
const profileSuccess = document.getElementById("profile-success");
const passwordError = document.getElementById("password-error");

async function loadProfile() {
  try {
    const user = await accountsApi.me();
    document.getElementById("profile-name").value = user.name;
    document.getElementById("profile-email").value = user.email;
  } catch (err) {
    profileError.textContent = err.message;
    profileError.style.display = "block";
  }
}

document.getElementById("profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  profileError.style.display = "none";
  profileSuccess.style.display = "none";
  try {
    await accountsApi.updateProfile({ name: document.getElementById("profile-name").value });
    profileSuccess.style.display = "block";
    mountUserBadge();
  } catch (err) {
    profileError.textContent = err.message;
    profileError.style.display = "block";
  }
});

document.getElementById("password-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  passwordError.style.display = "none";
  try {
    await accountsApi.changePassword({
      current_password: document.getElementById("current-password").value,
      new_password: document.getElementById("new-password").value,
    });
    window.location.href = "/connexion";
  } catch (err) {
    passwordError.textContent = err.message;
    passwordError.style.display = "block";
  }
});

loadProfile();
