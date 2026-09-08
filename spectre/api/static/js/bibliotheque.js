/* Page /bibliotheque : hub global (commun à tous les projets) vers les éditeurs de structures /
   présets / briques. Le contenu réutilisable vit dans les portées "intégré" (library/*.yml) et
   "partagé" (data/*_partages.json) - indépendantes de tout projet. Mais créer/éditer un élément
   passe par le constructeur ou les pages de gestion, qui ont besoin d'un projet (permissions +
   simulation) : d'où le sélecteur "projet de travail", mémorisé en local. */

const WORK_PROJECT_KEY = "spectre.libWorkProject";

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}

function rememberedProject() {
  try {
    return localStorage.getItem(WORK_PROJECT_KEY);
  } catch {
    return null;
  }
}

function applyProject(project) {
  // project = { slug, role } ou null
  const editorOnly = document.querySelectorAll(".js-editor-only");
  if (!project) {
    editorOnly.forEach((el) => (el.style.display = "none"));
    return;
  }
  try {
    localStorage.setItem(WORK_PROJECT_KEY, project.slug);
  } catch {
    /* mode privé : on continue sans mémoriser */
  }
  const s = encodeURIComponent(project.slug);
  const set = (id, href) => {
    const el = document.getElementById(id);
    if (el) el.href = href;
  };
  set("new-structure-link", `/projets/${s}/structures/bibliotheque/nouvelle?retour=bibliotheque&partagee=1`);
  set("manage-structures-link", `/projets/${s}#structures`);
  set("presets-link", `/projets/${s}/presets-etapes?partagee=1`);
  set("new-brick-link", `/projets/${s}/briques-technologiques/bibliotheque/nouvelle?retour=bibliotheque&partagee=1`);
  set("manage-bricks-link", `/projets/${s}/briques-technologiques`);

  const canEdit = project.role === "editor" || project.role === "owner";
  editorOnly.forEach((el) => (el.style.display = canEdit ? "" : "none"));
}

async function init() {
  let projects;
  try {
    projects = await api.get("/api/projects");
  } catch (err) {
    showError(err);
    return;
  }

  if (projects.length === 0) {
    document.getElementById("no-project-msg").style.display = "";
    applyProject(null);
    return;
  }

  const select = document.getElementById("work-project");
  select.innerHTML = projects
    .map((p) => `<option value="${escapeHtml(p.slug)}">${escapeHtml(p.name)}</option>`)
    .join("");

  const remembered = rememberedProject();
  const initial = projects.find((p) => p.slug === remembered) || projects[0];
  select.value = initial.slug;
  document.getElementById("work-project-row").style.display = projects.length > 1 ? "" : "none";
  applyProject(initial);

  select.addEventListener("change", () => {
    const chosen = projects.find((p) => p.slug === select.value);
    if (chosen) applyProject(chosen);
  });
}

init();
