const form = document.getElementById("login-form");
const errorBox = document.getElementById("error");

// la page d'où l'on venait (posée par api.js sur un 401) - un chemin de Spectre seulement
function suiteUrl() {
  const suite = new URLSearchParams(window.location.search).get("suite") || "/";
  return suite.startsWith("/") && !suite.startsWith("//") ? suite : "/";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.style.display = "none";
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  try {
    await accountsApi.login({ email, password }, { redirectOn401: false });
    window.location.href = suiteUrl();
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.style.display = "block";
  }
});
