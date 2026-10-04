const params = new URLSearchParams(window.location.search);
const token = params.get("token");
const form = document.getElementById("reset-form");
const errorBox = document.getElementById("error");
const successBox = document.getElementById("success");

if (!token) {
  errorBox.textContent = "Ce lien est incomplet. Redemandez une réinitialisation.";
  errorBox.style.display = "block";
  form.style.display = "none";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.style.display = "none";
  try {
    await accountsApi.completePasswordReset({ token, password: document.getElementById("password").value }, { redirectOn401: false });
    successBox.style.display = "block";
    form.style.display = "none";
    setTimeout(() => (window.location.href = "/connexion"), 1500);
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.style.display = "block";
  }
});
