/* Page /bibliotheque : hub global (commun à tous les µprojets) vers les éditeurs de structures /
   présets / briques. Le contenu réutilisable vit dans les portées "intégré" (library/*.yml) et
   "partagé" (data/*_partages.json) - indépendantes de tout projet. Mais créer/éditer un élément
   passe par le constructeur ou les pages de gestion, qui ont besoin d'un µprojet (permissions +
   simulation) : d'où le sélecteur "projet de travail", mémorisé en local. */

const WORK_MICROPROJECT_KEY = "spectre.libWorkMicroproject";

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

function rememberedMicroproject() {
  try {
    return localStorage.getItem(WORK_MICROPROJECT_KEY);
  } catch {
    return null;
  }
}

function applyMicroproject(microproject) {
  // microproject = { slug, role } ou null
  const editorOnly = document.querySelectorAll(".js-editor-only");
  if (!microproject) {
    editorOnly.forEach((el) => (el.style.display = "none"));
    return;
  }
  try {
    localStorage.setItem(WORK_MICROPROJECT_KEY, microproject.slug);
  } catch {
    /* mode privé : on continue sans mémoriser */
  }
  const s = encodeURIComponent(microproject.slug);
  const set = (id, href) => {
    const el = document.getElementById(id);
    if (el) el.href = href;
  };
  set("new-structure-link", `/microprojets/${s}/structures/bibliotheque/nouvelle?retour=bibliotheque&partagee=1`);
  set("manage-structures-link", `/microprojets/${s}#structures`);
  set("presets-link", `/microprojets/${s}/presets-etapes?partagee=1`);
  set("new-brick-link", `/microprojets/${s}/briques-technologiques/bibliotheque/nouvelle?retour=bibliotheque&partagee=1`);
  set("manage-bricks-link", `/microprojets/${s}/briques-technologiques`);

  const canEdit = microproject.role === "editor" || microproject.role === "owner";
  editorOnly.forEach((el) => (el.style.display = canEdit ? "" : "none"));
}

async function init() {
  let microprojects;
  try {
    microprojects = await api.get("/api/microprojets");
  } catch (err) {
    showError(err);
    return;
  }

  if (microprojects.length === 0) {
    document.getElementById("no-microproject-msg").style.display = "";
    applyMicroproject(null);
    return;
  }

  const select = document.getElementById("work-microproject");
  select.innerHTML = microprojects
    .map((p) => `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}</option>`)
    .join("");

  const remembered = rememberedMicroproject();
  const initial = microprojects.find((p) => p.slug === remembered) || microprojects[0];
  select.value = initial.slug;
  document.getElementById("work-microproject-row").style.display = microprojects.length > 1 ? "" : "none";
  applyMicroproject(initial);

  select.addEventListener("change", () => {
    const chosen = microprojects.find((p) => p.slug === select.value);
    if (chosen) applyMicroproject(chosen);
  });
}

init();
