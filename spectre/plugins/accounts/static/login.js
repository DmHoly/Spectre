const form = document.getElementById("login-form");
const errorBox = document.getElementById("error");

// la page d'où l'on venait (posée par api.js sur un 401) - une page de Spectre seulement : l'URL
// est résolue comme le navigateur le fera (« /\hote », « /<tab>/hote »... visent un autre site)
// et rendue absolue : un chemin relatif « //hote » (issu de « /.//hote ») viserait un autre site
function suiteUrl() {
  const suite = new URLSearchParams(window.location.search).get("suite") || "/";
  try {
    const url = new URL(suite, window.location.origin);
    return url.origin === window.location.origin ? url.href : "/";
  } catch {
    return "/";
  }
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
