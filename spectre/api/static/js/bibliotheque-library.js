/* La partie "fichiers YAML" de la page /bibliotheque : une carte par famille (matériaux, recettes,
   présets, briques, formulaire d'intention), chacune ouvrant un vrai éditeur (CodeMirror, coloration
   YAML) dans une modale - plutôt qu'un simple <textarea> - pour éditer confortablement un fichier de
   plusieurs dizaines d'entrées. Enregistre via PUT /api/bibliotheque/fichiers/{key} - validé côté
   serveur (voir spectre.core.registry.validate_library_yaml) avant d'écrire quoi que ce soit sur
   disque, réservé aux administrateurs (les autres voient le contenu en lecture seule, pour
   comprendre le format sans casser ce que tout le monde partage). */

const libraryErrorBox = document.getElementById("library-files-error");
function showLibraryError(err) {
  libraryErrorBox.textContent = err.message || String(err);
  libraryErrorBox.style.display = "block";
}
function clearLibraryError() {
  libraryErrorBox.style.display = "none";
}

function libraryCardHtml(file) {
  return `
    <div class="card card-pad" data-key="${escapeHtml(file.key)}" style="display:flex;flex-direction:column;gap:10px;">
      <div style="font-size:15.5px;font-weight:700;">${escapeHtml(file.title)}</div>
      <div style="font-size:13px;color:var(--text-soft);line-height:1.55;">${escapeHtml(file.description)}</div>
      <div style="font-size:12px;color:var(--text-faint);"><code>library/${escapeHtml(file.filename)}</code></div>
      <button class="btn btn-line js-open-library-editor" data-key="${escapeHtml(file.key)}" type="button" style="align-self:flex-start;">Voir / modifier &rarr;</button>
    </div>`;
}

// Une seule instance CodeMirror réutilisée par la modale (recréer un éditeur à chaque ouverture
// est inutile et plus lent) - son contenu est remplacé à chaque ouverture via editor.setValue().
let libraryCodeMirror = null;
function getLibraryCodeMirror() {
  if (!libraryCodeMirror) {
    libraryCodeMirror = CodeMirror(document.getElementById("library-editor-host"), {
      mode: "yaml",
      theme: "eclipse",
      lineNumbers: true,
      tabSize: 2,
      indentUnit: 2,
      viewportMargin: Infinity,
    });
  }
  return libraryCodeMirror;
}

const libraryModal = document.getElementById("library-editor-modal");
let libraryEditingKey = null;

function closeLibraryEditor() {
  libraryModal.close();
  libraryEditingKey = null;
}

document.getElementById("library-editor-close-btn").addEventListener("click", closeLibraryEditor);
document.getElementById("library-editor-cancel-btn").addEventListener("click", closeLibraryEditor);

document.getElementById("library-editor-save-btn").addEventListener("click", async () => {
  if (!libraryEditingKey) return;
  const saveBtn = document.getElementById("library-editor-save-btn");
  const saveErrorBox = document.getElementById("library-editor-save-error");
  saveErrorBox.style.display = "none";
  saveBtn.disabled = true;
  try {
    const content = getLibraryCodeMirror().getValue();
    await api.put(`/api/bibliotheque/fichiers/${encodeURIComponent(libraryEditingKey)}`, { content });
    saveBtn.textContent = "Enregistré ✓";
    setTimeout(() => (saveBtn.textContent = "Enregistrer"), 1500);
  } catch (err) {
    saveErrorBox.textContent = err.message || String(err);
    saveErrorBox.style.display = "block";
  } finally {
    saveBtn.disabled = false;
  }
});

async function openLibraryEditor(key) {
  clearLibraryError();
  document.getElementById("library-editor-save-error").style.display = "none";
  document.getElementById("library-editor-title").textContent = "Chargement…";
  document.getElementById("library-editor-filename").textContent = "";
  libraryModal.showModal();
  try {
    const detail = await api.get(`/api/bibliotheque/fichiers/${encodeURIComponent(key)}`);
    libraryEditingKey = key;
    document.getElementById("library-editor-title").textContent = detail.title;
    document.getElementById("library-editor-filename").textContent = `library/${detail.filename}`;
    document.getElementById("library-editor-readonly-note").style.display = detail.can_edit ? "none" : "";
    document.getElementById("library-editor-save-btn").style.display = detail.can_edit ? "" : "none";

    const editor = getLibraryCodeMirror();
    editor.setValue(detail.content);
    editor.setOption("readOnly", detail.can_edit ? false : "nocursor");
    // La modale n'a pas encore de taille tant que le navigateur ne l'a pas peinte une première
    // fois - sans ce refresh différé, CodeMirror mesure une largeur nulle et n'affiche rien tant
    // qu'on ne redimensionne pas la fenêtre.
    setTimeout(() => editor.refresh(), 0);
  } catch (err) {
    closeLibraryEditor();
    showLibraryError(err);
  }
}

async function initLibraryFiles() {
  const list = document.getElementById("library-files-list");
  try {
    const body = await api.get("/api/bibliotheque/fichiers");
    list.innerHTML = body.files.map(libraryCardHtml).join("");
    list.querySelectorAll(".js-open-library-editor").forEach((btn) => {
      btn.addEventListener("click", () => openLibraryEditor(btn.dataset.key));
    });
  } catch (err) {
    showLibraryError(err);
  }
}

initLibraryFiles();
