/* Page « structure en image » (structure-image.html) : lancer une expérience sans passer par le
   constructeur - la structure est donnée en images (schéma PowerPoint, coupes TEM/MEB, photo),
   collées, déposées ou choisies sur la planche de gauche (js/image-drop.js) ; l'intention,
   l'entité physique et les objectifs à droite. Deux adresses :
   - /microprojets/{slug}/structures/image : nouvelle expérience (POST /experiences/image) ;
   - /microprojets/{slug}/experiences/{id}/evoluer-image : continuer une expérience (dessinée ou
     en images) avec de nouvelles images (POST /experiences/{id}/evoluer-image), préremplie depuis
     la version de départ.
   objectives.js / intention-copy.js / intent-form.js du constructeur sont repris tels quels : ils
   lisent `slug` et `state`, définis ici. */

const pathParts = window.location.pathname.split("/").filter(Boolean);
const slug = pathParts[1];
const evolveExperienceId = pathParts[2] === "experiences" ? pathParts[3] : null;
const state = { objectives: [] };

let imageDrop = null;
let entityFdlField = null;

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}
errorBox.title = "Cliquer pour fermer";
errorBox.addEventListener("click", clearError);

function setPageTitle(text) {
  document.getElementById("page-title").textContent = text;
  document.title = `${text} — Spectre`;
  document.getElementById("crumb").innerHTML = `/ <a href="/microprojets/${encodeURIComponent(slug)}">${escapeHtml(slug)}</a> / ${escapeHtml(text)}`;
}

async function loadEntityHistory() {
  try {
    const history = await api.get(`/api/microprojets/${slug}/entites/historique`);
    document.getElementById("entity-sample-id-history").innerHTML = history.sample_ids.map((v) => `<option value="${escapeHtml(v)}">`).join("");
    document.getElementById("entity-location-history").innerHTML = history.locations.map((v) => `<option value="${escapeHtml(v)}">`).join("");
    document.getElementById("entity-fdl-history").innerHTML = (history.fdls || []).map((v) => `<option value="${escapeHtml(v)}">`).join("");
  } catch (err) {
    // autocomplétion seulement
  }
}

async function loadParent() {
  const detail = await api.get(`/api/microprojets/${slug}/experiences/${evolveExperienceId}`);
  document.getElementById("exp-title").value = detail.title;
  document.getElementById("exp-intent").value = detail.intent;
  document.getElementById("exp-hypothesis").value = detail.hypothesis || "";
  document.getElementById("exp-context").value = detail.context || "";
  const verification = detail.objective_verification || {};
  state.objectives = detail.objectives.map((o) => ({ ...o, verification_method: verification[o.name] || null }));
  renderObjectives();
  fillIntentFormAnswers(detail.form_answers);

  const entity = (detail.physical_tracking || []).find((e) => e.sample_id) || {};
  document.getElementById("exp-entity-sample-id").value = entity.sample_id || "";
  document.getElementById("exp-entity-location").value = entity.location || "";
  entityFdlField.set(entity.fdl || []);
  document.getElementById("entity-field-label").textContent = "Plaque suivie - lasermark";
  document.getElementById("entity-field-hint").textContent = entity.sample_id
    ? detail.is_batch
      ? "Reprise du premier échantillon de la campagne - la nouvelle version n'en suit qu'un, changez-le si besoin."
      : "Reprise de la version précédente - modifiez-la si besoin."
    : "Aucune entité physique n'a encore été renseignée sur cette piste - il en faut une pour continuer.";

  if (detail.structure_images) {
    imageDrop.set(detail.structure_images);
    document.getElementById("previous-image-note").hidden = false;
  }
  return detail;
}

function collectPayload() {
  const images = imageDrop.get();
  const title = document.getElementById("exp-title").value.trim();
  const intent = document.getElementById("exp-intent").value.trim();
  const sampleId = document.getElementById("exp-entity-sample-id").value.trim();
  if (imageDrop.isUploading()) return { error: "Une image est encore en cours d'envoi - un instant.", focus: null };
  if (!images.length) return { error: "Collez ou choisissez d'abord au moins une image de la structure.", focus: document.querySelector(".img-board__add:not([disabled])") };
  if (!title) return { error: "Le titre est obligatoire.", focus: document.getElementById("exp-title") };
  if (!intent) return { error: "L'intention est obligatoire.", focus: document.getElementById("exp-intent") };
  if (!evolveExperienceId && !sampleId) {
    return { error: "L'entité physique (l'échantillon réel suivi) est obligatoire.", focus: document.getElementById("exp-entity-sample-id") };
  }
  const payload = {
    images: images.map((img) => ({ ...img, caption: (img.caption || "").trim() || null })),
    title,
    intent,
    hypothesis: document.getElementById("exp-hypothesis").value.trim() || null,
    context: document.getElementById("exp-context").value,
    objectives: state.objectives,
    entities: sampleId ? [{ sample_id: sampleId, location: document.getElementById("exp-entity-location").value.trim() || null, fdl: entityFdlField.get() }] : [],
    form_answers: collectIntentFormAnswers(),
  };
  if (evolveExperienceId && document.getElementById("branch-fork").checked) {
    const branchName = document.getElementById("new-branch-name").value.trim();
    if (!branchName) return { error: "Donnez un nom à la nouvelle piste.", focus: document.getElementById("new-branch-name") };
    payload.new_branch = branchName;
  }
  return { payload };
}

async function launch() {
  clearError();
  const { payload, error, focus } = collectPayload();
  if (error) {
    showError(new Error(error));
    if (focus) focus.focus();
    return;
  }
  const button = document.getElementById("launch-btn");
  button.disabled = true;
  try {
    const endpoint = evolveExperienceId
      ? `/api/microprojets/${slug}/experiences/${evolveExperienceId}/evoluer-image`
      : `/api/microprojets/${slug}/experiences/image`;
    const result = await api.post(endpoint, payload);
    window.location.href = `/microprojets/${slug}/experiences/${result.id}`;
  } catch (err) {
    const formMessage = intentFormErrorMessage(err);
    showError(formMessage ? new Error(formMessage) : err);
    button.disabled = false;
  }
}

async function initStructureImagePage() {
  const builderLink = document.getElementById("builder-link");
  const cancelLink = document.getElementById("cancel-link");
  if (evolveExperienceId) {
    setPageTitle("Éditer la fiche · structure en images");
    document.getElementById("launch-btn").textContent = "Enregistrer les modifications";
    document.getElementById("branch-choice-wrap").hidden = false;
    builderLink.href = `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(evolveExperienceId)}/evoluer`;
    builderLink.textContent = "Continuer dans le constructeur";
    cancelLink.href = `/microprojets/${encodeURIComponent(slug)}/experiences/${encodeURIComponent(evolveExperienceId)}`;
  } else {
    setPageTitle("Nouvelle expérience · structure en image");
    builderLink.href = `/microprojets/${encodeURIComponent(slug)}/structures/nouvelle`;
    cancelLink.href = `/microprojets/${encodeURIComponent(slug)}`;
  }

  entityFdlField = mountFdlField(document.getElementById("exp-entity-fdl"), { datalistId: "entity-fdl-history", label: "FDL du wafer" });
  document.querySelector("#exp-entity-fdl .fdl-field__input").id = "exp-entity-fdl-input";
  imageDrop = mountImageDrop(document.getElementById("image-drop"), {
    slug,
    onChange: () => clearError(),
    onError: showError,
    // pas quand une fenêtre (ex. un <dialog>) est ouverte par-dessus
    isActive: () => !document.querySelector("dialog[open]"),
  });

  document.getElementById("launch-btn").addEventListener("click", launch);
  // Ctrl+Entrée depuis n'importe quel champ : lancer
  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      launch();
    }
  });
  document.getElementById("branch-continue").addEventListener("change", () => {
    document.getElementById("new-branch-name").hidden = true;
  });
  document.getElementById("branch-fork").addEventListener("change", () => {
    document.getElementById("new-branch-name").hidden = false;
    document.getElementById("new-branch-name").focus();
  });
  // un objectif ajouté replie le petit formulaire : la liste reste lisible
  document.getElementById("objective-form").addEventListener("submit", () => {
    if (document.getElementById("obj-name").value === "") document.getElementById("objective-add").open = false;
  });

  renderObjectives();
  loadEntityHistory();
  try {
    const microproject = await api.get(`/api/microprojets/${slug}`);
    if (microproject.role !== "editor" && microproject.role !== "owner") {
      showError(new Error("Vous n'avez qu'un accès en lecture à ce µprojet : impossible d'y lancer une expérience."));
      document.getElementById("launch-btn").disabled = true;
    }
    const label = microproject.code ? `${microproject.code} · ${microproject.name}` : microproject.name;
    document.getElementById("crumb").innerHTML = `/ <a href="/microprojets/${encodeURIComponent(slug)}">${escapeHtml(label)}</a> / ${escapeHtml(document.getElementById("page-title").textContent)}`;
    await loadIntentForm();
    if (evolveExperienceId) await loadParent();
  } catch (err) {
    showError(err);
  }
  if (!evolveExperienceId) document.getElementById("exp-title").focus({ preventScroll: true });
}
