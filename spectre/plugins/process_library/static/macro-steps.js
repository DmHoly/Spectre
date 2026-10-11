/* Page des macro-étapes d'un µprojet : les briques technologiques à rôle (gabarit SAG, épitaxie,
   procédé - voir structures/static/builder/assembly.js), une colonne par rôle. Chaque carte montre la
   brique simulée sur son contexte (une épi sur le gabarit sur lequel on l'a composée, un procédé sur
   son gabarit et son épi : `preview_on`), sa version et ce qu'elle porte. On les crée et les modifie
   dans le constructeur (mode brique) ; on en assemble une structure, ouverte dans le constructeur
   (`?assemblage=`). */

const { slug } = routeParams("/microprojets/{slug}/macro-etapes");

const ROLES = [
  { key: "sag", title: "Gabarits SAG", short: "SAG", noun: "un gabarit SAG", empty: "Substrat, masque et lithographie sur le réseau de fils : le départ d'une structure." },
  { key: "epi", title: "Épitaxies", short: "Épi", noun: "une épitaxie", empty: "Des croissances, sans position : elles se posent sur n'importe quel gabarit." },
  { key: "process", title: "Procédés", short: "Procédé", noun: "un procédé", empty: "Ce qu'on fait par-dessus l'épi : passivation, contacts, ouvertures sur le pixel…" },
];
const SCOPE_LABELS = { builtin: "intégrée", shared: "partagée", microproject: "µprojet" };
// le substrat d'aperçu d'une épi ou d'un procédé composé sans gabarit
const PREVIEW_SUBSTRATE = { material: "GaN", domain_width: { value: 400, unit: "nm" }, thickness: { value: 50, unit: "nm" } };

const state = {
  bricks: [],
  usages: {}, // id de brique -> les études qui en ont une copie (GET /api/tech-brick-usages)
  role: null, // le rôle du compte dans le µprojet (créer : editor, owner)
  chosen: { sag: "", epi: "", process: "" },
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
  document.getElementById("flash").style.display = "none";
}
function showFlash(message) {
  const flash = document.getElementById("flash");
  flash.textContent = message;
  flash.style.display = "block";
  errorBox.style.display = "none";
}

function canCreate() {
  return state.role === "editor" || state.role === "owner";
}

function brickById(id) {
  return state.bricks.find((b) => b.id === id) || null;
}

function editorHref(id, extra = "") {
  return `/microprojets/${encodeURIComponent(slug)}/briques-technologiques/bibliotheque/${encodeURIComponent(id)}?retour=macro-etapes${extra}`;
}

function newHref(role) {
  return `/microprojets/${encodeURIComponent(slug)}/briques-technologiques/bibliotheque/nouvelle?role=${role}&retour=macro-etapes`;
}

// Les étapes d'une brique telles que le constructeur les envoie : chaque lithographie ancrée au
// réseau porte son ancrage (rangé à part dans la bibliothèque, `lattice_openings`).
function anchoredSteps(brick) {
  const anchors = brick.lattice_openings || {};
  return brick.steps.map((step, i) => (anchors[i] || anchors[String(i)] ? { ...step, lattice_opening: anchors[i] || anchors[String(i)] } : step));
}

// Ce sur quoi une brique se montre : ses briques d'aperçu, dans l'ordre de l'assemblage - et, pour
// chaque rôle d'avant qu'elles n'ont pas, la première brique de ce rôle (un aperçu par défaut :
// `assumed`), pour qu'une épi composée sans gabarit se voie quand même sur des fils.
function contextOf(brick) {
  const order = ROLES.map((r) => r.key);
  const before = order.slice(0, order.indexOf(brick.role));
  const own = (brick.preview_on || []).map(brickById).filter((b) => b && before.includes(b.role));
  return before
    .map((role) => {
      const chosen = own.find((b) => b.role === role);
      if (chosen) return { brick: chosen, assumed: false };
      const first = state.bricks.find((b) => b.role === role);
      return first ? { brick: first, assumed: true } : null;
    })
    .filter(Boolean);
}

// La requête de simulation d'un assemblage (des briques dans l'ordre SAG, épi, procédé).
function assemblyBody(bricks) {
  const sag = bricks.find((b) => b.role === "sag" && b.substrate);
  return { substrate: sag ? sag.substrate : PREVIEW_SUBSTRATE, steps: bricks.flatMap(anchoredSteps) };
}

function cardHtml(brick) {
  const context = contextOf(brick);
  const on = context.length
    ? `<div class="sp-macro__on">sur ${context
        .map(({ brick: b, assumed }) => (assumed ? `<em title="Aperçu par défaut : composée sans ${escapeHtml(b.role === "sag" ? "gabarit" : "épi")}">${escapeHtml(b.name)}</em>` : `<span>${escapeHtml(b.name)}</span>`))
        .join(" + ")}</div>`
    : "";
  const lattice = brick.substrate && brick.substrate.lattice ? ` · pas ${brick.substrate.lattice.pitch} nm` : "";
  const actions = [];
  if (brick.can_edit) actions.push(`<a class="btn btn-line" href="${editorHref(brick.id)}">Modifier</a>`);
  if (canCreate()) actions.push(`<a class="btn btn-line" href="${editorHref(brick.id, "&dupliquer=1")}">Dupliquer</a>`);
  actions.push(`<button class="btn btn-line js-assemble" type="button" data-id="${escapeHtml(brick.id)}" title="La choisir dans l'assemblage ci-dessus">Assembler</button>`);
  if (brick.can_edit) actions.push(`<button class="btn btn-line sp-macro__remove js-remove" type="button" data-id="${escapeHtml(brick.id)}">Supprimer</button>`);
  return `
    <article class="sp-macro__card" data-id="${escapeHtml(brick.id)}">
      <div class="sp-macro__art skeleton" data-art="${escapeHtml(brick.id)}" aria-hidden="true"></div>
      <div class="sp-macro__body">
        <div class="sp-macro__name">${escapeHtml(brick.name)}</div>
        <div class="sp-macro__meta">v${brick.version || 1} · ${SCOPE_LABELS[brick.scope] || escapeHtml(brick.scope)} · ${brick.steps.length} étape${brick.steps.length > 1 ? "s" : ""}${lattice}</div>
        ${on}
        ${brick.notes ? `<p class="sp-macro__notes">${escapeHtml(brick.notes)}</p>` : ""}
        ${usageHtml(brick)}
        <div class="sp-macro__actions">${actions.join("")}</div>
      </div>
    </article>`;
}

const STATUS_LABELS = {
  draft: "brouillon",
  running: "en cours",
  hold: "en pause",
  concluded: "conclue",
  continued: "continuée",
  abandoned: "abandonnée",
};

// Où sert une brique : le nombre d'études dont la version courante en a une copie, et combien
// portent une version antérieure de la brique ; la liste s'ouvre (liens vers les études des µprojets
// dont on est membre, le nom du µprojet seul pour les autres).
function usageHtml(brick) {
  const uses = state.usages[brick.id];
  if (!uses) return "";
  if (!uses.length) return `<div class="sp-macro__usage is-unused">Utilisée dans aucune étude</div>`;
  const current = brick.version || 1;
  const older = uses.filter((u) => u.version && u.version < current).length;
  const summary = `Utilisée dans ${uses.length} étude${uses.length > 1 ? "s" : ""}${older ? ` · ${older} sur une version antérieure` : ""}`;
  const rows = uses
    .map((u) => {
      const version = u.version ? `v${u.version}` : "v?";
      const stale = u.version && u.version < current ? " is-stale" : "";
      if (!u.linked) return `<li><span class="sp-macro__usage-v${stale}">${version}</span> une étude de « ${escapeHtml(u.microproject.name)} »</li>`;
      const href = `/microprojets/${encodeURIComponent(u.microproject.slug)}/experiences/${encodeURIComponent(u.experiment_id)}`;
      const where = u.microproject.slug === slug ? "" : ` <span class="sp-macro__usage-mp">${escapeHtml(u.microproject.code || u.microproject.name)}</span>`;
      return `<li><span class="sp-macro__usage-v${stale}">${version}</span> <a href="${href}">${escapeHtml(u.title || u.experiment_id)}</a>${where} <span class="sp-macro__usage-status">${escapeHtml(STATUS_LABELS[u.status] || u.status || "")}</span></li>`;
    })
    .join("");
  return `<details class="sp-macro__usage"><summary>${summary}</summary><ul>${rows}</ul></details>`;
}

function renderColumns() {
  document.getElementById("macro-columns").innerHTML = ROLES.map((role) => {
    const bricks = state.bricks.filter((b) => b.role === role.key);
    return `
      <section class="sp-macro__col" aria-labelledby="col-${role.key}">
        <header class="sp-macro__col-head">
          <span class="sb-brick__tag sb-brick__tag--${role.key}">${escapeHtml(role.short)}</span>
          <h2 class="sp-macro__col-title" id="col-${role.key}">${escapeHtml(role.title)}</h2>
          <span class="sp-macro__count">${bricks.length}</span>
          ${canCreate() ? `<a class="btn btn-line sp-macro__new" href="${newHref(role.key)}">+ Nouveau</a>` : ""}
        </header>
        <div class="sp-macro__list">
          ${bricks.length ? bricks.map(cardHtml).join("") : `<p class="help sp-macro__empty">${escapeHtml(role.empty)}${canCreate() ? " Créez-en avec « + Nouveau », ou en groupant des étapes dans le constructeur." : ""}</p>`}
        </div>
      </section>`;
  }).join("");
  document.querySelectorAll(".js-remove").forEach((btn) => btn.addEventListener("click", () => removeBrick(btn.dataset.id)));
  document.querySelectorAll(".js-assemble").forEach((btn) =>
    btn.addEventListener("click", () => {
      const brick = brickById(btn.dataset.id);
      if (!brick) return;
      state.chosen[brick.role] = brick.id;
      renderAssembly();
      document.getElementById("assemble-title").scrollIntoView({ behavior: "smooth", block: "start" });
    })
  );
}

function renderAssembly() {
  const slots = ROLES.map((role) => {
    const options = state.bricks.filter((b) => b.role === role.key);
    return `
      <label class="sp-macro__slot">
        <span class="sb-brick__tag sb-brick__tag--${role.key}">${escapeHtml(role.short)}</span>
        <select class="field" data-role="${role.key}" aria-label="${escapeHtml(role.title)}" ${options.length ? "" : "disabled"}>
          <option value="">—</option>
          ${options.map((b) => `<option value="${escapeHtml(b.id)}" ${state.chosen[role.key] === b.id ? "selected" : ""}>${escapeHtml(b.name)}</option>`).join("")}
        </select>
      </label>`;
  });
  const ids = ROLES.map((r) => state.chosen[r.key]).filter(Boolean);
  const href = `/microprojets/${encodeURIComponent(slug)}/structures/nouvelle?assemblage=${ids.map(encodeURIComponent).join(",")}`;
  document.getElementById("assemble-slots").innerHTML =
    slots.join("") +
    (ids.length && canCreate()
      ? `<a class="btn btn-primary sp-macro__open" href="${href}">Ouvrir dans le constructeur</a>`
      : `<button class="btn btn-primary sp-macro__open" type="button" disabled>Ouvrir dans le constructeur</button>`);
  document.querySelectorAll("#assemble-slots select").forEach((select) =>
    select.addEventListener("change", () => {
      state.chosen[select.dataset.role] = select.value;
      renderAssembly();
    })
  );
}

async function removeBrick(id) {
  const brick = brickById(id);
  if (!brick) return;
  const shared = brick.scope === "shared" ? " Elle est partagée : elle disparaîtra de tous les µprojets." : "";
  if (!window.confirm(`Supprimer la macro-étape « ${brick.name} » ?${shared} Les structures qui l'ont reprise gardent leur copie.`)) return;
  try {
    await processLibraryApi.deleteTechBrick(id);
    Object.keys(state.chosen).forEach((role) => {
      if (state.chosen[role] === id) state.chosen[role] = "";
    });
    await loadBricks();
    showFlash(`Macro-étape « ${brick.name} » supprimée.`);
  } catch (err) {
    showError(err);
  }
}

// Les aperçus, une simulation à la fois (le serveur garde les débuts communs : un gabarit partagé
// par plusieurs épis n'est simulé qu'une fois).
async function renderThumbnails() {
  for (const brick of state.bricks.filter((b) => b.role)) {
    const holder = document.querySelector(`[data-art="${CSS.escape(brick.id)}"]`);
    if (!holder) continue;
    try {
      const result = await structuresApi.simulate(assemblyBody([...contextOf(brick).map((c) => c.brick), brick]));
      const frames = result.frames || [];
      holder.innerHTML = frames.length ? frames[frames.length - 1].svg : "";
      holder.classList.remove("skeleton");
    } catch (err) {
      holder.classList.remove("skeleton");
      holder.classList.add("is-failed");
      holder.textContent = "Aperçu impossible";
      holder.title = err.message || String(err);
    }
  }
}

async function loadBricks() {
  const [bricks, usages] = await Promise.all([
    processLibraryApi.techBricks({ microproject: slug }),
    // les usages ne sont qu'un renseignement : la page s'affiche sans eux s'ils échouent
    processLibraryApi.techBrickUsages({ microproject: slug }).catch(() => ({})),
  ]);
  state.bricks = bricks.filter((b) => b.role);
  state.usages = usages;
  renderColumns();
  renderAssembly();
  renderThumbnails();
}

async function init() {
  try {
    const microproject = await microprojectsApi.get(slug);
    state.role = microproject.role;
    document.getElementById("crumb").textContent = "/ " + microproject.name;
    document.title = `Macro-étapes · ${microproject.name} — Spectre`;
    await loadBricks();
  } catch (err) {
    showError(err);
  }
}

init();
