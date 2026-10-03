const form = document.getElementById("forgot-form");
const errorBox = document.getElementById("error");
const successBox = document.getElementById("success");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.style.display = "none";
  try {
    await accountsApi.forgotPassword({ email: document.getElementById("email").value }, { redirectOn401: false });
    successBox.style.display = "block";
    form.style.display = "none";
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.style.display = "block";
  }
});
