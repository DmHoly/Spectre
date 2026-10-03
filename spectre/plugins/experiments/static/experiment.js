/* Fiche d'identité d'une expérience : un en-tête qui en est le super résumé (statut, version, qui
   et quand, le contexte, ce qu'on veut démontrer et comment - les objectifs, avec le verdict en
   badge -, les plaques suivies, leurs FDL et le lien vers leurs données en base), puis trois
   onglets qui vivent chacun leur vie - « Structure & plaques » (structure actuelle + diff, en
   carrousel pour une campagne, et à côté les plaques ; versions, cartographie), « Données »
   (données mesurées + preuves), « Conclusion » (ou le formulaire pour la rédiger).
   L'onglet ouvert est dans l'adresse (#structure / #donnees / #conclusion) et survit aux actions
   qui enregistrent une nouvelle version (voir goToVersion). Le rapport téléchargé reprend les trois. */

const { slug, experience_id: experienceId } = routeParams("/microprojets/{slug}/experiences/{experience_id}");

const REFERENCE_ROLE_LABELS = {
  baseline: "Référence",
  control: "Témoin",
  prior_art: "Antériorité",
  benchmark: "Point de comparaison",
  target_spec: "Spécification cible",
  merge_source: "Source combinée",
};

const OBJECTIVE_STATUS_LABELS = {
  met: "Atteint",
  not_met: "Non atteint",
  partially_met: "Partiellement atteint",
  inconclusive: "Non concluant",
};

// mêmes libellés que les options du formulaire de conclusion (renderConcludeForm)
const DECISION_LABELS = {
  promote: "Retenir comme référence",
  branch: "Explorer une variante",
  replicate: "Reproduire pour confirmer",
  abandon: "Abandonner la piste",
  inconclusive: "Non concluant",
};

const EVIDENCE_KIND_LABELS = {
  standard: "Standard",
  image: "Image",
  graph: "Graphique",
};

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

let currentRole = null;
let currentMicroprojectName = null;
let currentMicroprojectCode = null;
let currentDetail = null;
let currentProcess = null; // {substrate, steps} from /process - absent for structures without an
// editable StructureForge recipe recorded (e.g. a campaign's representative entry).

function isEditorRole() {
  return currentRole === "editor" || currentRole === "owner";
}

// Chaque action (preuve, étiquette, conclusion...) enregistre une nouvelle version immuable : on la
// suit, en gardant l'onglet ouvert (#donnees...) plutôt que de revenir au premier.
function goToVersion(id) {
  window.location.href = `/microprojets/${slug}/experiences/${id}${window.location.hash}`;
}

// La matrice d'une campagne (/matrice : une structure par variante, facteurs, suivi physique) - un
// seul appel partagé par le carrousel de structure, la cartographie et la galerie de données.
let batchVariationPromise = null;
function getBatchVariation() {
  if (!batchVariationPromise) {
    batchVariationPromise = experimentsApi.variants(slug, experienceId).catch((err) => {
      batchVariationPromise = null;
      throw err;
    });
  }
  return batchVariationPromise;
}

// --- onglets ------------------------------------------------------------------------------------

const FICHE_TABS = ["structure", "donnees", "conclusion"];

function showTab(name, { focus = false } = {}) {
  const tab = FICHE_TABS.includes(name) ? name : "structure";
  FICHE_TABS.forEach((key) => {
    const button = document.getElementById(`tab-${key}`);
    const selected = key === tab;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
    document.getElementById(`panel-${key}`).hidden = !selected;
  });
  if (focus) document.getElementById(`tab-${tab}`).focus();
  const hash = tab === "structure" ? "" : `#${tab}`;
  if (window.location.hash !== hash) history.replaceState(null, "", `${window.location.pathname}${window.location.search}${hash}`);
}

document.querySelector(".fiche-tabs").addEventListener("click", (event) => {
  const button = event.target.closest("[data-tab]");
  if (button) showTab(button.dataset.tab);
});
document.querySelector(".fiche-tabs").addEventListener("keydown", (event) => {
  const current = FICHE_TABS.indexOf(document.querySelector(".fiche-tabs [aria-selected='true']").dataset.tab);
  let next = null;
  if (event.key === "ArrowRight") next = (current + 1) % FICHE_TABS.length;
  else if (event.key === "ArrowLeft") next = (current - 1 + FICHE_TABS.length) % FICHE_TABS.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = FICHE_TABS.length - 1;
  if (next === null) return;
  event.preventDefault();
  showTab(FICHE_TABS[next], { focus: true });
});
window.addEventListener("hashchange", () => showTab(window.location.hash.slice(1)));
showTab(window.location.hash.slice(1));

// Repères sur les onglets : combien de données, et si l'étude est conclue.
function updateTabBadges(detail) {
  const count = (detail.evidence || []).length + (detail.data_items || []).length + (detail.data_notebook || []).length;
  document.getElementById("tab-donnees-count").textContent = count ? String(count) : "";
  const state = document.getElementById("tab-conclusion-state");
  const concluded = detail.status === "concluded" || detail.status === "abandoned";
  state.textContent = concluded ? "✓" : "à rédiger";
  state.classList.toggle("is-done", concluded);
  state.classList.toggle("is-open", !concluded);
  state.title = concluded ? "Étude conclue" : "Pas encore conclue";
}

function objectiveResultFor(detail, objectiveName) {
  return (detail.conclusion.objective_results || []).find((r) => r.objective === objectiveName);
}

function renderHeader(detail) {
  document.getElementById("status-badge").innerHTML = statusBadgeHtml(detail.status, detail.conclusion.decision);
  renderStatusActions(detail);
  renderStatusNote(detail);
  document.getElementById("hero-code").innerHTML = currentMicroprojectCode
    ? `<a class="fiche-code" href="/microprojets/${encodeURIComponent(slug)}" title="µprojet ${escapeHtml(currentMicroprojectName || "")}">${escapeHtml(currentMicroprojectCode)}</a>`
    : "";
  document.getElementById("exp-title").textContent = detail.title;
  document.getElementById("exp-intent").textContent = detail.intent;
  const hypothesis = document.getElementById("exp-hypothesis");
  hypothesis.style.display = detail.hypothesis ? "" : "none";
  hypothesis.innerHTML = detail.hypothesis ? `<strong>Hypothèse</strong> : ${escapeHtml(detail.hypothesis)}` : "";
  document.getElementById("exp-meta").innerHTML = [
    currentMicroprojectName ? `<span>${escapeHtml(currentMicroprojectName)}</span>` : "",
    `<span>Responsable&nbsp;: <span class="meta-value">${escapeHtml(detail.author || "inconnu")}</span></span>`,
    `<span id="hero-dates">Débutée le&nbsp;: <span class="meta-value">${formatDate(detail.created_at)}</span></span>`,
  ]
    .filter(Boolean)
    .join('<span class="fiche-hero__dot" aria-hidden="true">·</span>');

  // le contexte : une description sommaire qui remet l'expérience dans son histoire
  const context = document.getElementById("hero-context");
  if (detail.context) {
    context.textContent = detail.context;
    context.classList.remove("is-empty");
    context.style.display = "";
  } else if (isEditorRole()) {
    context.innerHTML = `<button type="button" class="fiche-hero__add" data-report-hide>+ Ajouter un contexte : d'où part cette expérience, pourquoi maintenant</button>`;
    context.classList.add("is-empty");
    context.style.display = "";
    context.querySelector("button").addEventListener("click", () => goToEvolve("intention"));
  } else {
    context.style.display = "none";
  }

  document.getElementById("crumb").textContent = "/ " + (currentMicroprojectCode ? `${currentMicroprojectCode} / ` : "") + detail.title;
  document.title = `${detail.title} — Spectre`;
  renderHeroPlates(detail);
  renderVerdict(detail);
  renderHeroConclusion(detail);
}

// Les plaques suivies, en résumé : leurs lasermarks, puis toutes leurs FDL (feuilles de lancement JIRA).
function renderHeroPlates(detail) {
  const lasermarks = (detail.physical_tracking || []).map((e) => e.sample_id).filter(Boolean);
  const shown = lasermarks.slice(0, 8);
  document.getElementById("hero-wafers").innerHTML = lasermarks.length
    ? shown.map((l) => `<a class="hero-wafer" href="${plateUrl(l)}" title="Le parcours de la plaque ${escapeHtml(l)}">${escapeHtml(l)}</a>`).join("") +
      (lasermarks.length > shown.length ? `<span class="hero-wafer hero-wafer--more">+${lasermarks.length - shown.length}</span>` : "")
    : `<span class="help" style="margin:0;">Aucun lasermark renseigné</span>`;
  document.getElementById("fdl-row").innerHTML = fdlChipsHtml(fdlsOfTracking(detail.physical_tracking));
}

// Le verdict des objectifs, en badge : un anneau (un segment par objectif, coloré selon son
// résultat) + une icône + un libellé - jamais la couleur seule.
const VERDICT_SEGMENT_COLORS = {
  met: "var(--done)",
  partially_met: "var(--gold)",
  not_met: "var(--danger)",
  inconclusive: "var(--draft)",
  pending: "var(--border)",
};
const VERDICT_ICONS = {
  met: '<path d="M5 13l4 4L19 7"/>',
  not_met: '<path d="M6 6l12 12M18 6L6 18"/>',
  partial: '<path d="M12 3a9 9 0 1 0 0 18z" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="9"/>',
  inconclusive: '<path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
  pending: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  none: '<path d="M5 12h14"/>',
};

function objectiveVerdict(detail) {
  const objectives = detail.objectives || [];
  const statuses = objectives.map((o) => {
    const result = objectiveResultFor(detail, o.name);
    return result ? result.status : "pending";
  });
  const count = (status) => statuses.filter((st) => st === status).length;
  const n = statuses.length;
  const met = count("met");
  const pending = count("pending");
  const concluded = detail.status === "concluded" || detail.status === "abandoned";
  let state;
  let label;
  if (!n) [state, label] = ["none", "Aucun objectif défini"];
  else if (pending === n) [state, label] = ["pending", concluded ? "Objectifs non évalués" : "En cours de vérification"];
  else if (met === n) [state, label] = ["met", n > 1 ? "Objectifs atteints" : "Objectif atteint"];
  else if (met === 0 && count("partially_met") === 0 && count("not_met") > 0) [state, label] = ["not_met", n > 1 ? "Objectifs non atteints" : "Objectif non atteint"];
  else if (met === 0 && count("partially_met") === 0 && count("not_met") === 0) [state, label] = ["inconclusive", "Non concluant"];
  else [state, label] = ["partial", "Partiellement atteint"];
  return { state, label, statuses, met, n, pending };
}

function verdictRingSvg(statuses) {
  const r = 19;
  const c = 2 * Math.PI * r;
  const n = statuses.length || 1;
  const gap = n > 1 ? 3 : 0;
  const seg = c / n;
  const arcs = (statuses.length ? statuses : ["pending"])
    .map((st, i) => {
      const length = Math.max(seg - gap, 1);
      return `<circle cx="24" cy="24" r="${r}" fill="none" stroke="${VERDICT_SEGMENT_COLORS[st] || VERDICT_SEGMENT_COLORS.pending}" stroke-width="6" stroke-dasharray="${length.toFixed(2)} ${(c - length).toFixed(2)}" stroke-dashoffset="${(-(i * seg) + c / 4).toFixed(2)}"/>`;
    })
    .join("");
  return `<svg class="verdict__ring" viewBox="0 0 48 48" aria-hidden="true"><circle cx="24" cy="24" r="${r}" fill="none" stroke="var(--border-soft)" stroke-width="6"/>${arcs}</svg>`;
}

function renderVerdict(detail) {
  const v = objectiveVerdict(detail);
  const sub = v.n
    ? v.pending === v.n
      ? `${v.n} objectif${v.n > 1 ? "s" : ""} à vérifier`
      : `${v.met} sur ${v.n} atteint${v.met > 1 ? "s" : ""}`
    : isEditorRole()
      ? "Le « comment » se décrit avec des objectifs"
      : "";
  document.getElementById("hero-verdict").innerHTML = `
    <div class="verdict verdict--${v.state}" role="status" aria-label="${escapeHtml(`${v.label}${sub ? " - " + sub : ""}`)}">
      <div class="verdict__ring-wrap">
        ${verdictRingSvg(v.statuses)}
        <span class="verdict__count">${v.n ? `${v.met}/${v.n}` : "–"}</span>
      </div>
      <div class="verdict__text">
        <div class="verdict__label"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${VERDICT_ICONS[v.state]}</svg>${escapeHtml(v.label)}</div>
        ${sub ? `<div class="verdict__sub">${escapeHtml(sub)}</div>` : ""}
      </div>
    </div>`;
}

// Une étude conclue : sa décision et son résumé, dès l'en-tête (le détail reste dans l'onglet Conclusion).
function renderHeroConclusion(detail) {
  const box = document.getElementById("hero-conclusion");
  const c = detail.conclusion || {};
  const concluded = detail.status === "concluded" || detail.status === "abandoned";
  if (!concluded || (!c.summary && !c.decision)) {
    box.style.display = "none";
    return;
  }
  box.style.display = "";
  box.innerHTML = `
    <div class="fiche-hero__label">Conclusion</div>
    ${c.decision ? `<div class="fiche-hero__decision">${escapeHtml(DECISION_LABELS[c.decision] || c.decision)}</div>` : ""}
    ${c.summary ? `<p class="fiche-hero__summary">${escapeHtml(c.summary)}</p>` : ""}
    <button type="button" class="fiche-hero__more" data-report-hide>Lire la conclusion &rarr;</button>`;
  box.querySelector(".fiche-hero__more").addEventListener("click", () => {
    showTab("conclusion", { focus: true });
    document.querySelector(".fiche-tabs").scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

// Transitions de statut (voir POST .../statut) : une étude nouvellement lancée est « brouillon » ;
// elle passe « en cours », peut être mise « en pause » (hold, avec un motif) puis reprise. Une étude
// conclue peut être rouverte pour revoir sa conclusion. Un brouillon « continuée » (repris par une
// version suivante) se déduit du graphe : rien à faire pour l'obtenir. Chaque changement enregistre
// une nouvelle version (études immuables).
function renderStatusNote(detail) {
  const note = document.getElementById("status-note");
  note.className = "fiche-status-note";
  if (detail.status === "hold" && detail.hold) {
    const since = detail.hold.since;
    note.classList.add("fiche-status-note--hold");
    note.innerHTML = `<span>En pause depuis le ${escapeHtml(formatDate(since))} (${escapeHtml(formatDuration(new Date() - new Date(since)))})${detail.hold.by ? ` · par ${escapeHtml(detail.hold.by)}` : ""}</span>${
      detail.hold.reason ? `<span class="fiche-status-note__reason">${escapeHtml(detail.hold.reason)}</span>` : ""
    }`;
    note.hidden = false;
  } else if (detail.status === "continued" && detail.continued_at) {
    note.innerHTML = `<span>Brouillon continué par une version suivante le ${escapeHtml(formatDate(detail.continued_at))} - <a href="/microprojets/${encodeURIComponent(slug)}">voir la suite dans le graphe</a></span>`;
    note.hidden = false;
  } else {
    note.hidden = true;
    note.innerHTML = "";
  }
}

function renderStatusActions(detail) {
  const host = document.getElementById("status-actions");
  host.innerHTML = "";
  if (!isEditorRole()) return;
  const addBtn = (label, targetStatus, cls) => {
    const b = document.createElement("button");
    b.className = `btn ${cls}`;
    b.style.cssText = "padding:4px 11px;font-size:12px;";
    b.textContent = label;
    b.addEventListener("click", () => changeStatus(targetStatus, b));
    host.appendChild(b);
  };
  if (detail.status === "draft") {
    addBtn("Marquer « en cours »", "running", "btn-primary");
    addBtn("Mettre en pause", "hold", "btn-line");
  } else if (detail.status === "continued") {
    addBtn("Marquer « en cours »", "running", "btn-line");
  } else if (detail.status === "running") {
    addBtn("Mettre en pause", "hold", "btn-line");
    addBtn("Repasser en brouillon", "draft", "btn-line");
  } else if (detail.status === "hold") {
    // reprendre = revenir au statut qu'elle avait avant la pause (brouillon ou en cours)
    addBtn("Reprendre", detail.conclusion.status === "draft" ? "draft" : "running", "btn-primary");
  } else {
    addBtn("Rouvrir pour revoir la conclusion", "running", "btn-line");
  }
}

// Le motif d'une mise en pause : null si la personne annule.
function askHoldReason() {
  const dialog = document.getElementById("hold-dialog");
  const input = document.getElementById("hold-reason");
  input.value = "";
  return new Promise((resolve) => {
    const done = (value) => {
      dialog.removeEventListener("close", onClose);
      resolve(value);
    };
    const onClose = () => done(dialog.returnValue === "ok" ? input.value.trim() : null);
    dialog.addEventListener("close", onClose);
    dialog.returnValue = ""; // Échap ne doit pas réutiliser le « ok » d'une fois précédente
    dialog.showModal();
    input.focus();
  });
}
document.getElementById("hold-form").addEventListener("submit", (event) => {
  event.preventDefault();
  document.getElementById("hold-dialog").close("ok");
});
document.getElementById("hold-cancel").addEventListener("click", () => document.getElementById("hold-dialog").close("cancel"));

async function changeStatus(targetStatus, btn) {
  clearError();
  const body = { status: targetStatus };
  if (targetStatus === "hold") {
    const reason = await askHoldReason();
    if (reason === null) return;
    body.reason = reason || null;
  }
  if (btn) btn.disabled = true;
  try {
    const result = await experimentsApi.setStatus(slug, experienceId, body);
    goToVersion(result.id);
  } catch (err) {
    showError(err);
    if (btn) btn.disabled = false;
  }
}

const OBJECTIVE_DIRECTION_TEXT = { observe: "observer", maximize: "maximiser", minimize: "minimiser", target: "cible" };

function renderObjectives(detail) {
  const list = document.getElementById("objectives-list");
  if (detail.objectives.length === 0) {
    list.innerHTML = `<li class="hero-objectives__empty">Aucun objectif défini${
      isEditorRole() ? ` - <button type="button" class="fiche-hero__add js-add-objectives" data-report-hide>ajouter les objectifs</button>` : ""
    }.</li>`;
    const add = list.querySelector(".js-add-objectives");
    if (add) add.addEventListener("click", () => goToEvolve("intention"));
    return;
  }
  const icons = {
    met: '<path d="M5 13l4 4L19 7"/>',
    not_met: '<path d="M6 6l12 12M18 6L6 18"/>',
    partially_met: '<path d="M5 12h14"/>',
    inconclusive: '<path d="M12 17h.01"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/>',
    pending: '<circle cx="12" cy="12" r="3" fill="currentColor"/>',
  };
  list.innerHTML = detail.objectives
    .map((o) => {
      const result = objectiveResultFor(detail, o.name);
      const status = result ? result.status : "pending";
      const statusText = result ? OBJECTIVE_STATUS_LABELS[result.status] || result.status : "À vérifier";
      const verification = (detail.objective_verification || {})[o.name];
      const how = [o.metric, OBJECTIVE_DIRECTION_TEXT[o.direction] || o.direction, o.target != null ? `cible ${o.target}` : ""].filter(Boolean).join(" · ");
      const observed = result && result.observed ? `observé ${result.observed.value}${result.observed.unit ? " " + result.observed.unit : ""}` : "";
      return `
        <li class="hero-objective hero-objective--${status}">
          <span class="hero-objective__icon" aria-hidden="true"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">${icons[status] || icons.pending}</svg></span>
          <div class="hero-objective__body">
            <div class="hero-objective__head">
              <span class="hero-objective__name">${escapeHtml(o.name)}</span>
              <span class="hero-objective__status">${escapeHtml(statusText)}</span>
            </div>
            ${how || observed ? `<div class="hero-objective__how mono">${escapeHtml([how, observed].filter(Boolean).join(" — "))}</div>` : ""}
            ${verification ? `<div class="hero-objective__verif">Vérification&nbsp;: ${escapeHtml(verification)}</div>` : ""}
            ${o.rationale ? `<div class="hero-objective__why">Pourquoi&nbsp;: ${escapeHtml(o.rationale)}</div>` : ""}
          </div>
        </li>`;
    })
    .join("");
}

// Niveau de changement de procédé/structure (voir spectre.core.versioning) -> libellé affiché à
// côté du numéro de version. "none" n'apparaît que dans l'historique complet (voir
// renderFullHistory) : la frise des versions ne garde que les entrées qui en ont un.
const CHANGE_LEVEL_LABELS = {
  initial: "version initiale",
  major: "changement majeur",
  minor: "changement mineur",
  patch: "ajustement mineur",
  none: null,
};

function versionBadge(item) {
  return `<span class="timeline-version" title="${escapeHtml(CHANGE_LEVEL_LABELS[item.change_level] || "")}">v${escapeHtml(item.version)}</span>`;
}

// item.is_current vient du serveur (la toute dernière entrée de la piste) - jamais déduit de la
// position dans la liste affichée, puisque la frise des versions peut omettre des entrées
// intermédiaires (voir renderTimeline) et donc ne pas se terminer sur le vrai commit courant.
function renderTimelineItem(item, extraClass) {
  return `
    <div class="timeline-item ${item.is_current ? "current" : ""} ${extraClass || ""}">
      <div class="timeline-date">${formatDate(item.created_at)}${item.is_current ? " · version actuelle" : ""} ${versionBadge(item)}</div>
      <div class="timeline-title">${escapeHtml(item.title)}</div>
      <div class="timeline-desc">${escapeHtml(item.intent)}</div>
    </div>`;
}

function renderTimeline(versions) {
  const el = document.getElementById("timeline");
  // Most recent first - #timeline is a .builder-col__scroll box that starts scrolled to the top,
  // so the last few commits are visible without scrolling ; le reste (dont chaque étape qui n'a
  // pas fait bouger la version) est dans l'historique complet en bas de la fiche, pas ici.
  el.innerHTML = [...versions].reverse().map((item) => renderTimelineItem(item)).join("");
}

function renderFullHistory(items) {
  const el = document.getElementById("full-history");
  if (!el) return;
  el.innerHTML = [...items]
    .reverse()
    .map((item) => renderTimelineItem(item, item.change_level === "none" ? "no-version-change" : ""))
    .join("");
}

// Index de la variante affichée par le carrousel d'une campagne (0 = la référence). Le détail des
// couches au survol/clic ne vaut que pour la référence : c'est son procédé que /process décrit.
let structureVariantIndex = 0;

// Ce qui a changé quand une structure en images est en jeu : le résumé en clair calculé par /diff
// (spectre.core.structures.describe_image_changes) plutôt que les chemins bruts (images[1].image_id...).
function diffSummaryHtml(lines) {
  return lines.map((line) => `<div style="font-size:12.5px;color:var(--text-soft);padding:2px 0;">${escapeHtml(line)}</div>`).join("");
}

async function renderStructure(detail, diff) {
  const container = document.getElementById("structure-svg");
  structureVariantIndex = 0;
  if (detail.structure_images) {
    // une structure en images (schéma, coupes TEM...) : la planche, et ce qui a changé
    const images = detail.structure_images;
    document.getElementById("structure-title").textContent =
      images.length > 1 ? `Structure · ${images.length} images` : `Structure · ${STRUCTURE_IMAGE_KIND_LABELS[images[0].kind] || "Image"}`;
    container.classList.remove("builder-canvas-svg", "layer-clickable");
    container.innerHTML = structureBoardHtml(slug, images);
    document.getElementById("structure-click-hint").style.display = "none";
    const lines = (diff && diff.target && diff.summary) || [];
    document.getElementById("diff-note").textContent = diff && diff.target && !lines.length ? "identique à la version précédente" : "";
    document.getElementById("diff-details").innerHTML = diffSummaryHtml(lines);
    return;
  }
  if (detail.is_batch) {
    // une campagne : un carrousel (référence + chaque variante, avec ses paramètres variés)
    document.getElementById("structure-title").textContent = "Structures des variantes";
    container.classList.remove("builder-canvas-svg");
    container.classList.add("fiche-structure-carousel");
    try {
      const variation = await getBatchVariation();
      mountStructureCarousel(container, variation, {
        onChange: (index) => {
          structureVariantIndex = index;
          hideLayerTooltip();
          document.getElementById("structure-click-hint").style.display = currentProcess && index === 0 ? "" : "none";
        },
      });
    } catch (err) {
      container.innerHTML = detail.structure_svg || "";
    }
  } else {
    container.innerHTML = detail.structure_svg || "<div class='help'>Pas de schéma pour ce type de structure.</div>";
  }
  document.getElementById("structure-click-hint").style.display = currentProcess ? "" : "none";
  const diffNote = document.getElementById("diff-note");
  const diffDetails = document.getElementById("diff-details");
  if (!diff || !diff.target || diff.entries.length === 0) {
    diffNote.textContent = diff && diff.target ? "identique à la version précédente" : "";
    diffDetails.innerHTML = "";
    return;
  }
  if (diff.summary) {
    // la version précédente était donnée en images : pas de liste de paramètres qui ait un sens
    diffNote.textContent = "";
    diffDetails.innerHTML = diffSummaryHtml(diff.summary);
    return;
  }
  diffNote.innerHTML = `<span style="color:var(--abandoned);font-weight:600;">${diff.entries.length} paramètre${diff.entries.length > 1 ? "s" : ""} modifié${diff.entries.length > 1 ? "s" : ""}</span>`;
  diffDetails.innerHTML = diff.entries
    .slice(0, 12)
    .map((e) => `<div class="mono" style="font-size:11.5px;color:var(--text-soft);padding:2px 0;">${escapeHtml(e.path)} : ${escapeHtml(JSON.stringify(e.before))} &rarr; ${escapeHtml(JSON.stringify(e.after))}</div>`)
    .join("");
}

// Cliquer une couche du dessin ouvre une modale avec les paramètres de l'étape qui l'a produite
// - même convention data-layer-index que le constructeur de structure (0 = substrat, N = l'étape
// N-1 du procédé) sur le même SVG (structures.render_structure_svg réutilise frame_to_svg).

const STEP_KIND_LABELS = {
  deposition: "Dépôt",
  etch: "Gravure",
  lithography: "Lithographie",
  resist_strip: "Retrait de résine",
  planarization: "Planarisation",
  chemical: "Étape chimique",
  faceted_growth: "Croissance facettée",
  epitaxial_growth: "Croissance épitaxiale",
  flip: "Retournement",
};

const STEP_FIELD_LABELS = {
  material: "Matériau",
  recipe: "Recette",
  angle_deg: "Angle",
  thickness: "Épaisseur",
  depth: "Profondeur",
  resist_material: "Résine",
  openings: "Ouvertures",
  target_level: "Niveau cible",
  stop_material: "S'arrête sur",
  orientation: "Orientation",
  rate_c: "Vitesse relative (plan C)",
  rate_m: "Vitesse relative (plan M)",
  rate_sp: "Vitesse relative (semipolaire)",
  semi_polar_angle_deg: "Angle semipolaire",
  seed_materials: "Matériaux d'amorçage (SAG)",
};

function formatStepValue(value) {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "object" && !Array.isArray(value) && "value" in value && "unit" in value) {
    return `${value.value}${value.unit ? " " + value.unit : ""}`;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return value.map((v) => (typeof v === "object" ? JSON.stringify(v) : String(v))).join(", ");
  }
  if (typeof value === "object") {
    const entries = Object.entries(value)
      .map(([k, v]) => [k, formatStepValue(v)])
      .filter(([, v]) => v !== null);
    return entries.length ? entries.map(([k, v]) => `${k} : ${v}`).join(" · ") : null;
  }
  return String(value);
}

function openLayerModal(title, fields) {
  document.getElementById("layer-modal-title").textContent = title;
  document.getElementById("layer-modal-body").innerHTML = fields.length
    ? fields
        .map(
          ([label, value]) => `
      <div style="padding:8px 0;border-top:1px solid var(--border-soft);">
        <span style="color:var(--text-faint);font-size:11px;text-transform:uppercase;letter-spacing:.02em;">${escapeHtml(label)}</span><br>
        <span>${escapeHtml(value)}</span>
      </div>`
        )
        .join("")
    : `<div class="help">Pas de paramètre à afficher pour cette couche.</div>`;
  document.getElementById("layer-modal").showModal();
}

function showLayerModal(layerIndex) {
  if (!currentProcess) return;
  if (layerIndex === 0) {
    const s = currentProcess.substrate || {};
    const fields = [
      ["Matériau", s.material],
      ["Largeur du domaine", formatStepValue(s.domain_width)],
      ["Épaisseur", formatStepValue(s.thickness)],
    ].filter(([, v]) => v);
    openLayerModal("Substrat", fields);
    return;
  }
  const step = (currentProcess.steps || [])[layerIndex - 1];
  if (!step) return;
  const fields = Object.entries(step)
    .filter(([key]) => key !== "kind" && key !== "name")
    .map(([key, value]) => [STEP_FIELD_LABELS[key] || key, formatStepValue(value)])
    .filter(([, value]) => value !== null);
  openLayerModal(`${STEP_KIND_LABELS[step.kind] || step.kind} — ${step.name}`, fields);
}

// Survoler une couche affiche un aperçu condensé (nom + quelques paramètres clés) dans une
// infobulle qui suit le curseur - même source de champs que la modale (showLayerModal), juste
// limitée aux 4 premiers pour rester lisible dans un petit encart.
function layerSummaryFields(layerIndex) {
  if (!currentProcess) return null;
  if (layerIndex === 0) {
    const s = currentProcess.substrate || {};
    const fields = [
      ["Matériau", s.material],
      ["Largeur du domaine", formatStepValue(s.domain_width)],
      ["Épaisseur", formatStepValue(s.thickness)],
    ].filter(([, v]) => v);
    return { title: "Substrat", fields };
  }
  const step = (currentProcess.steps || [])[layerIndex - 1];
  if (!step) return null;
  const fields = Object.entries(step)
    .filter(([key]) => key !== "kind" && key !== "name")
    .map(([key, value]) => [STEP_FIELD_LABELS[key] || key, formatStepValue(value)])
    .filter(([, value]) => value !== null)
    .slice(0, 4);
  return { title: `${STEP_KIND_LABELS[step.kind] || step.kind} — ${step.name}`, fields };
}

function showLayerTooltip(layerIndex, x, y) {
  const summary = layerSummaryFields(layerIndex);
  const tooltip = document.getElementById("layer-tooltip");
  if (!summary) {
    hideLayerTooltip();
    return;
  }
  tooltip.innerHTML = `
    <strong>${escapeHtml(summary.title)}</strong>
    ${summary.fields.map(([label, value]) => `${escapeHtml(label)} : ${escapeHtml(value)}`).join("<br>")}`;
  tooltip.style.display = "";
  // décalé du curseur pour ne pas se retrouver caché par la pointe de la souris.
  tooltip.style.left = `${x + 14}px`;
  tooltip.style.top = `${y + 14}px`;
}

function hideLayerTooltip() {
  document.getElementById("layer-tooltip").style.display = "none";
}

document.getElementById("structure-svg").addEventListener("click", (event) => {
  const path = event.target.closest("[data-layer-index]");
  if (!path || structureVariantIndex > 0) return;
  showLayerModal(parseInt(path.dataset.layerIndex, 10));
});

document.getElementById("structure-svg").addEventListener("mousemove", (event) => {
  const path = event.target.closest("[data-layer-index]");
  if (!path || structureVariantIndex > 0) {
    hideLayerTooltip();
    return;
  }
  showLayerTooltip(parseInt(path.dataset.layerIndex, 10), event.clientX, event.clientY);
});

document.getElementById("structure-svg").addEventListener("mouseleave", hideLayerTooltip);

document.getElementById("layer-modal-close-btn").addEventListener("click", () => {
  document.getElementById("layer-modal").close();
});

// Les champs FDL (mountFdlField, wafers/static/fdl.js) de chaque plaque affichée, par index - remplis par
// mountEntityFdlFields une fois le HTML posé, relus à l'enregistrement.
let entityFdlFields = {};

function mountEntityFdlFields(tracking) {
  entityFdlFields = {};
  document.querySelectorAll(".js-entity-fdl").forEach((el) => {
    const index = Number(el.dataset.index);
    entityFdlFields[index] = mountFdlField(el, {
      values: (tracking[index] || {}).fdl || [],
      datalistId: "entity-fdl-history",
      label: `FDL de la plaque ${index + 1}`,
    });
  });
}

function entityFdlValues(index) {
  return entityFdlFields[index] ? entityFdlFields[index].get() : [];
}

// Une plaque (entité physique) dans la carte « Plaques & entités physiques » : son lasermark, son
// emplacement et ses FDL - en champs pour un éditeur, en lecture sinon. `label` : la variante
// d'une campagne. Les champs portent une autocomplétion (list=, depuis /entites/historique) et
// sont data-report-hide, avec un miroir texte .report-only pour le rapport (voir generateReportHtml).
function plateRowHtml(current, index, canEdit, label) {
  const lasermark = current.sample_id || "";
  const location = current.location || "";
  const fdls = current.fdl || [];
  const head = label ? `<div class="plate-row__label">${escapeHtml(label)}</div>` : "";
  const readonly = `
    <div class="plate-row__ro">
      ${
        lasermark
          ? `<a class="plate-row__lasermark" href="${plateUrl(lasermark)}" title="Le parcours de cette plaque">${escapeHtml(lasermark)}</a>`
          : `<span class="plate-row__lasermark is-missing">lasermark non renseigné</span>`
      }
      ${location ? `<span class="plate-row__location">${escapeHtml(location)}</span>` : ""}
      ${fdls.length ? `<span class="plate-row__fdl">${fdlChipsHtml(fdls, { label: false })}</span>` : ""}
    </div>`;
  if (!canEdit) return `<div class="plate-row">${head}${readonly}</div>`;
  return `
    <div class="plate-row">
      ${head}
      <div class="plate-row__fields" data-report-hide>
        <div><label for="plate-lasermark-${index}">Lasermark${lasermark ? ` <a class="plate-row__trail" href="${plateUrl(lasermark)}">parcours &rarr;</a>` : ""}</label><input class="field mono js-entity-sample-id" id="plate-lasermark-${index}" data-index="${index}" list="entity-sample-id-history" value="${escapeHtml(lasermark)}" placeholder="ex : W12-A3" autocomplete="off"></div>
        <div><label for="plate-location-${index}">Emplacement</label><input class="field js-entity-location" id="plate-location-${index}" data-index="${index}" list="entity-location-history" value="${escapeHtml(location)}" placeholder="ex : boîte B, tiroir 2" autocomplete="off"></div>
        <div class="plate-row__fdl-field"><label>FDL</label><div class="js-entity-fdl" data-index="${index}"></div></div>
      </div>
      <div class="report-only">${readonly}</div>
    </div>`;
}

async function renderBatchMatrix(detail) {
  const card = document.getElementById("matrix-card");
  if (!detail.is_batch) {
    card.style.display = "none";
    return;
  }
  card.style.display = "";
  try {
    const variation = await getBatchVariation();
    const labels = variation.labels || variation.svgs.map((_, i) => `#${i + 1}`);
    const tracking = variation.physical_tracking || [];

    // Cartographie : une vignette par échantillon, la structure réelle telle que StructureForge
    // l'a simulée - pas juste la référence, chaque variante, avec le lasermark de sa plaque (qui se
    // renseigne, avec ses FDL, dans la carte « Plaques » à côté de la structure).
    document.getElementById("atlas-content").innerHTML = `
      <div class="atlas-grid">
        ${variation.svgs
          .map((svg, i) => {
            const lasermark = (tracking[i] || {}).sample_id;
            return `<div class="atlas-tile">${svg}<div class="atlas-label">${escapeHtml(labels[i])}</div>${lasermark ? `<div class="atlas-tile__lasermark mono">${escapeHtml(lasermark)}</div>` : ""}</div>`;
          })
          .join("")}
      </div>`;

    const el = document.getElementById("matrix-content");
    const hasFactors = variation.factor_labels && variation.factor_labels.length > 0;
    if (variation.varying.length === 0 && !hasFactors) {
      el.innerHTML = `<div class="help">Les ${variation.entity_count} échantillons sont identiques sur tous les paramètres suivis.</div>`;
      return;
    }

    // Feuille de split : une ligne par échantillon, une colonne par paramètre réellement varié -
    // lisible directement, pas les chemins de structure bruts (gardés en détail technique en
    // dessous). factor_labels/factor_values are absent on campaigns saved before multi-paramètre
    // support - fall back to the single generic "Paramètre" column labels already covered.
    const factorLabels = variation.factor_labels && variation.factor_labels.length ? variation.factor_labels : ["Paramètre"];
    const splitSheet = `
      <table style="border-collapse:collapse;font-size:13px;width:100%;">
        <thead><tr style="text-align:left;color:var(--text-faint);font-size:11px;text-transform:uppercase;">
          <th style="padding:4px 10px 4px 0;">Échantillon</th>
          ${factorLabels
            .map((label, j) => {
              const log = (variation.factor_scales || [])[j] === "log";
              return `<th style="padding:4px 10px;">${escapeHtml(label)}${log ? ` <span style="text-transform:none;font-weight:500;">(échelle log)</span>` : ""}</th>`;
            })
            .join("")}
        </tr></thead>
        <tbody>
          ${labels
            .map((label, i) => {
              const values = variation.factor_values && variation.factor_values[i] ? variation.factor_values[i] : [label];
              return `<tr style="border-top:1px solid var(--border-soft);">
                <td class="mono" style="padding:6px 10px 6px 0;">${escapeHtml(label)}</td>
                ${values.map((v) => `<td class="mono" style="padding:6px 10px;">${escapeHtml(formatParamValue(v))}</td>`).join("")}
              </tr>`;
            })
            .join("")}
        </tbody>
      </table>`;

    const rawTable = variation.varying.length
      ? `
      <table style="border-collapse:collapse;font-size:12px;width:100%;">
        <thead><tr style="text-align:left;color:var(--text-faint);font-size:11px;text-transform:uppercase;">
          <th style="padding:4px 10px 4px 0;">Repère interne</th>
          ${variation.varying[0].values.map((_, i) => `<th style="padding:4px 10px;">#${i + 1}</th>`).join("")}
        </tr></thead>
        <tbody>
          ${variation.varying
            .map(
              (f) => `<tr style="border-top:1px solid var(--border-soft);">
                <td class="mono" style="padding:6px 10px 6px 0;color:var(--text-soft);">${escapeHtml(f.path)}</td>
                ${f.values.map((v) => `<td class="mono" style="padding:6px 10px;">${escapeHtml(JSON.stringify(v))}</td>`).join("")}
              </tr>`
            )
            .join("")}
        </tbody>
      </table>`
      : `<div class="help">Ces paramètres ne changent pas la géométrie simulée (ex : un paramètre process ou une estimation) - rien à comparer structure par structure.</div>`;

    el.innerHTML = `
      <div style="overflow-x:auto;">${splitSheet}</div>
      <details style="margin-top:12px;">
        <summary style="cursor:pointer;font-size:12px;color:var(--text-faint);">Détails techniques</summary>
        <div style="overflow-x:auto;margin-top:8px;">${rawTable}</div>
      </details>`;
  } catch (err) {
    showError(err);
  }
}

function concludedViewHtml(detail) {
  const c = detail.conclusion;
  const answers = c.objective_results
    .map((r) => {
      const objective = detail.objectives.find((o) => o.name === r.objective);
      return `
        <div style="padding:8px 0;border-top:1px solid var(--border-soft);">
          <div style="font-size:13px;font-weight:600;">${escapeHtml(r.objective)}</div>
          ${objective && objective.rationale ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:1px;">${escapeHtml(objective.rationale)}</div>` : ""}
          <div style="font-size:12.5px;color:var(--text-soft);margin-top:4px;">${escapeHtml(OBJECTIVE_STATUS_LABELS[r.status] || r.status)}${r.reasoning ? " — " + escapeHtml(r.reasoning) : ""}</div>
        </div>`;
    })
    .join("");
  return `
    <div class="section-title" style="margin-bottom:14px;">Conclusion</div>
    ${c.summary ? `<p style="font-size:13.5px;line-height:1.6;margin-bottom:10px;">${escapeHtml(c.summary)}</p>` : ""}
    ${c.decision ? `<div style="font-size:12.5px;color:var(--text-soft);">Décision&nbsp;: <strong>${escapeHtml(DECISION_LABELS[c.decision] || c.decision)}</strong></div>` : ""}
    ${c.next_steps ? `<div style="font-size:12.5px;color:var(--text-soft);margin-top:4px;">Suite&nbsp;: ${escapeHtml(c.next_steps)}</div>` : ""}
    ${answers ? `<div style="margin-top:14px;">${answers}</div>` : ""}
  `;
}

function renderConclusion(detail) {
  const container = document.getElementById("conclusion-section");
  const isConcluded = detail.status === "concluded" || detail.status === "abandoned";
  if (isConcluded) {
    container.innerHTML =
      concludedViewHtml(detail) +
      (isEditorRole()
        ? `<button class="btn btn-line" id="edit-conclusion-btn" data-report-hide style="margin-top:16px;padding:5px 12px;font-size:12px;">Modifier la conclusion</button>`
        : "");
    const editBtn = document.getElementById("edit-conclusion-btn");
    if (editBtn) editBtn.addEventListener("click", () => renderConcludeForm(detail, detail.conclusion));
    return;
  }
  if (!isEditorRole()) {
    container.innerHTML = `<div class="section-title" style="margin-bottom:14px;">Conclusion</div><div class="help" style="font-style:italic;">Pas encore conclue — expérience en cours.</div>`;
    return;
  }
  // Une étude rouverte (concluded -> running via .../statut) garde ses réponses d'objectifs et son
  // résumé : on repré-remplit le formulaire avec, plutôt que de repartir de zéro.
  const c = detail.conclusion || {};
  const hasPrior = (c.objective_results || []).length > 0 || c.summary || c.decision || c.next_steps;
  renderConcludeForm(detail, hasPrior ? c : null);
}

// `prefill` = detail.conclusion quand on modifie une conclusion existante, null pour une première
// conclusion. Dans les deux cas le formulaire poste sur /conclure, qui enregistre une nouvelle
// version (études immuables) - on la suit ensuite.
function renderConcludeForm(detail, prefill) {
  const container = document.getElementById("conclusion-section");
  const editing = Boolean(prefill);
  // "Annuler" ne fait sens que si une vue lecture seule existe pour y revenir (étude déjà conclue).
  const canCancel = detail.status === "concluded" || detail.status === "abandoned";
  container.innerHTML = `
    <div class="section-title" style="margin-bottom:14px;">${editing ? "Modifier la conclusion" : "Conclure l'expérience"}</div>
    <span class="report-only help" style="font-style:italic;">Pas encore conclue — expérience en cours.</span>
    <form id="conclude-form" class="field-group" data-report-hide>
      <div id="objective-results"></div>
      <div><label>Résumé</label><textarea class="field" id="conclude-summary" rows="2"></textarea></div>
      <div class="field-row">
        <div><label>Décision</label>
          <select class="field" id="conclude-decision">
            <option value="">—</option>
            <option value="promote">Retenir comme référence</option>
            <option value="branch">Explorer une variante</option>
            <option value="replicate">Reproduire pour confirmer</option>
            <option value="abandon">Abandonner la piste</option>
            <option value="inconclusive">Non concluant</option>
          </select>
        </div>
        <div><label>Statut final</label>
          <select class="field" id="conclude-status">
            <option value="concluded">Conclue</option>
            <option value="abandoned">Abandonnée</option>
          </select>
        </div>
      </div>
      <div><label>Prochaine étape (optionnelle)</label><input class="field" id="conclude-next-steps"></div>
      <div style="display:flex;gap:10px;">
        <button class="btn btn-primary" style="flex:1;" type="submit">${editing ? "Enregistrer les modifications" : "Enregistrer la conclusion"}</button>
        ${canCancel ? `<button class="btn btn-line" id="conclude-cancel-btn" type="button">Annuler</button>` : ""}
      </div>
    </form>
  `;
  if (canCancel) {
    document.getElementById("conclude-cancel-btn").addEventListener("click", () => renderConclusion(detail));
  }
  const verification = currentDetail.objective_verification || {};
  document.getElementById("objective-results").innerHTML = currentDetail.objectives
    .map(
      (o, i) => `
      <div style="margin-bottom:14px;padding-bottom:14px;border-bottom:1px solid var(--border-soft);">
        <label style="margin-bottom:2px;">${escapeHtml(o.name)}</label>
        ${o.rationale ? `<div style="font-size:11.5px;color:var(--text-faint);margin-bottom:2px;">Pourquoi&nbsp;: ${escapeHtml(o.rationale)}</div>` : ""}
        ${verification[o.name] ? `<div style="font-size:11.5px;color:var(--text-faint);margin-bottom:6px;">Vérification prévue&nbsp;: ${escapeHtml(verification[o.name])}</div>` : ""}
        <select class="field" data-objective="${escapeHtml(o.name)}" id="obj-result-${i}" style="margin-bottom:6px;">
          <option value="met">Atteint</option>
          <option value="not_met">Non atteint</option>
          <option value="partially_met">Partiellement atteint</option>
          <option value="inconclusive">Non concluant</option>
        </select>
        <textarea class="field" id="obj-reasoning-${i}" rows="2" placeholder="Réponse : qu'a-t-on constaté ?"></textarea>
      </div>`
    )
    .join("");

  if (prefill) {
    document.getElementById("conclude-summary").value = prefill.summary || "";
    document.getElementById("conclude-decision").value = prefill.decision || "";
    document.getElementById("conclude-status").value = prefill.status === "abandoned" ? "abandoned" : "concluded";
    document.getElementById("conclude-next-steps").value = prefill.next_steps || "";
    (prefill.objective_results || []).forEach((r) => {
      const i = currentDetail.objectives.findIndex((o) => o.name === r.objective);
      if (i < 0) return;
      document.getElementById(`obj-result-${i}`).value = r.status;
      document.getElementById(`obj-reasoning-${i}`).value = r.reasoning || "";
    });
  }

  document.getElementById("conclude-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const objectiveResults = currentDetail.objectives.map((o, i) => ({
      objective: o.name,
      status: document.getElementById(`obj-result-${i}`).value,
      reasoning: document.getElementById(`obj-reasoning-${i}`).value.trim() || null,
    }));
    try {
      const result = await experimentsApi.conclude(slug, experienceId, {
        status: document.getElementById("conclude-status").value,
        decision: document.getElementById("conclude-decision").value || null,
        summary: document.getElementById("conclude-summary").value || null,
        next_steps: document.getElementById("conclude-next-steps").value || null,
        objective_results: objectiveResults,
      });
      // conclure records a new version carrying the conclusion (experiences are immutable) -
      // go to it, not back to this now-superseded draft.
      goToVersion(result.id);
    } catch (err) {
      showError(err);
    }
  });
}

async function populateCompareMicroprojectSelect() {
  const microprojectSelect = document.getElementById("compare-microproject-select");
  try {
    const myMicroprojects = await microprojectsApi.list();
    microprojectSelect.innerHTML = myMicroprojects
      .map((p) => `<option value="${p.slug}">${escapeHtml(p.name)}${p.slug === slug ? " (ce µprojet)" : ""}</option>`)
      .join("");
    microprojectSelect.value = slug;
  } catch (err) {
    // silent: comparison is a secondary feature
  }
  await populateCompareExperienceSelect(microprojectSelect.value);
}

async function populateCompareExperienceSelect(targetSlug) {
  const select = document.getElementById("compare-select");
  try {
    const data = await experimentsApi.list(targetSlug, { status: "all", limit: 200 });
    const others = data.items.filter((item) => !(targetSlug === slug && item.id === experienceId));
    select.innerHTML = others.length
      ? others.map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("")
      : `<option value="">Aucune expérience à comparer</option>`;
  } catch (err) {
    select.innerHTML = `<option value="">—</option>`;
  }
}

document.getElementById("compare-microproject-select").addEventListener("change", (event) => {
  populateCompareExperienceSelect(event.target.value);
});

document.getElementById("compare-btn").addEventListener("click", async () => {
  const targetMicroproject = document.getElementById("compare-microproject-select").value;
  const target = document.getElementById("compare-select").value;
  if (!target) return;
  const box = document.getElementById("compare-result");
  try {
    const diff =
      targetMicroproject === slug
        ? await experimentsApi.diff(slug, experienceId, target)
        : await experimentsApi.diffExternal(slug, experienceId, targetMicroproject, target);
    if (diff.note) {
      box.innerHTML = `<div class="help">${escapeHtml(diff.note)}</div>`;
    } else if (diff.entries.length === 0) {
      box.innerHTML = `<div class="help">Aucune différence de structure.</div>`;
    } else {
      box.innerHTML = diff.entries
        .slice(0, 20)
        .map((e) => `<div class="mono" style="font-size:11px;color:var(--text-soft);padding:2px 0;">${escapeHtml(e.path)} : ${escapeHtml(JSON.stringify(e.before))} &rarr; ${escapeHtml(JSON.stringify(e.after))}</div>`)
        .join("");
    }
  } catch (err) {
    showError(err);
  }
});

async function saveAnnotations(evidenceId, annotations) {
  clearError();
  try {
    const result = await evidenceApi.updateAnnotations(slug, experienceId, evidenceId, {
      annotations,
    });
    goToVersion(result.id);
  } catch (err) {
    showError(err);
  }
}

// Superposition SVG des annotations (flèche / cadre) sur une image de preuve. Les coordonnées sont
// stockées en % de l'image (x/y/x2/y2) - le viewBox 0..100 avec preserveAspectRatio="none" les
// reprojette directement sur les dimensions réelles affichées, quel que soit le ratio de l'image.
function annotationMarkersSvg(annotations) {
  const shapes = (annotations || [])
    .map((a) => {
      if (a.type === "arrow") {
        return `<line x1="${a.x}" y1="${a.y}" x2="${a.x2}" y2="${a.y2}" stroke="var(--accent)" stroke-width="0.8" vector-effect="non-scaling-stroke" marker-end="url(#annotation-arrowhead)"/>`;
      }
      const x = Math.min(a.x, a.x2);
      const y = Math.min(a.y, a.y2);
      const w = Math.abs(a.x2 - a.x);
      const h = Math.abs(a.y2 - a.y);
      return `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="var(--accent)" fill-opacity="0.18" stroke="var(--accent)" stroke-width="0.8" vector-effect="non-scaling-stroke"/>`;
    })
    .join("");
  return `
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" style="position:absolute;inset:0;width:100%;height:100%;">
      <defs>
        <marker id="annotation-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto" viewBox="0 0 8 6">
          <path d="M0,0 L8,3 L0,6 z" fill="var(--accent)"/>
        </marker>
      </defs>
      ${shapes}
    </svg>`;
}

// Les images d'une preuve : ses pièces jointes images (collées dans le formulaire, ou l'image d'une
// ancienne preuve « Image ») - affichées quel que soit le type de la preuve. Chacune porte ses
// propres annotations (flèche / cadre), qui se posent en cliquant dessus.
function evidenceImagesHtml(detail, e) {
  const images = (detail.attachments || []).filter((a) => a.evidence_id === e.id && (a.content_type || "image/").startsWith("image/"));
  if (!images.length) return e.kind === "image" ? `<div class="help" style="margin-top:8px;">Image en cours d'envoi ou absente.</div>` : "";
  const canEdit = isEditorRole();
  const all = e.image_annotations || [];
  return `<div class="evidence-images" data-count="${Math.min(images.length, 3)}">${images
    .map((attachment) => {
      const url = attachmentsApi.contentUrl(slug, attachment.id);
      const mine = all.map((a, i) => ({ ...a, globalIndex: i })).filter((a) => !a.attachment_id || a.attachment_id === attachment.id);
      const annotationsListHtml = mine
        .map(
          (a) => `
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:11.5px;padding:3px 0;">
            <span>${a.type === "arrow" ? "Flèche" : "Cadre"}${a.label ? " — " + escapeHtml(a.label) : ""}</span>
            ${
              canEdit
                ? `<button type="button" class="js-remove-annotation" data-evidence-id="${e.id}" data-index="${a.globalIndex}" data-report-hide aria-label="Retirer l'annotation" style="background:none;border:none;cursor:pointer;color:var(--text-faint);font-size:14px;line-height:1;">&times;</button>`
                : ""
            }
          </div>`
        )
        .join("");
      return `
      <figure class="evidence-image">
        <div class="js-annotation-image" data-evidence-id="${e.id}" data-attachment-id="${attachment.id}" style="position:relative;display:inline-block;max-width:100%;cursor:${canEdit ? "crosshair" : "default"};">
          <img src="${url}" alt="${escapeHtml(attachment.caption || attachment.filename || "Image de la preuve")}" style="max-width:100%;display:block;border-radius:var(--radius-sm);">
          ${annotationMarkersSvg(mine)}
        </div>
        ${attachment.caption ? `<figcaption class="evidence-image__caption">${escapeHtml(attachment.caption)}</figcaption>` : ""}
        ${annotationsListHtml ? `<div style="margin-top:4px;">${annotationsListHtml}</div>` : ""}
        ${
          canEdit
            ? `<div class="js-annotation-tools" data-evidence-id="${e.id}" data-attachment-id="${attachment.id}" data-report-hide style="margin-top:6px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
                <button type="button" class="btn btn-line js-annotation-tool" data-tool="arrow" style="min-height:30px;padding:3px 9px;font-size:11.5px;">Flèche</button>
                <button type="button" class="btn btn-line js-annotation-tool" data-tool="box" style="min-height:30px;padding:3px 9px;font-size:11.5px;">Cadre</button>
                <button type="button" class="btn btn-primary js-annotation-save" style="min-height:30px;padding:3px 9px;font-size:11.5px;">Enregistrer les annotations</button>
                <span class="help js-annotation-hint" style="margin:0;"></span>
              </div>`
            : ""
        }
      </figure>`;
    })
    .join("")}</div>`;
}

// Un lien de preuve : une adresse web (SharePoint, Teams...) s'ouvre dans un onglet ; un chemin
// réseau ou disque (\\serveur\partage\..., S:\...) - que le navigateur refuse d'ouvrir depuis une
// page web - se copie, pour le coller dans l'explorateur ou PowerPoint.
const LINK_ICONS = {
  folder: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>`,
  slides: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8"/><path d="M7 12l3-3 2 2 4-4"/></svg>`,
  file: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/></svg>`,
  web: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/></svg>`,
};

function describeEvidenceLink(link) {
  const isWeb = /^https?:\/\//i.test(link);
  let tail = link.replace(/[\\/]+$/, "");
  if (isWeb) {
    try {
      const u = new URL(link);
      tail = decodeURIComponent(u.pathname.replace(/\/+$/, "").split("/").pop() || u.hostname);
    } catch (e) {
      tail = link;
    }
  } else {
    tail = tail.split(/[\\/]/).pop() || link;
  }
  const ext = (tail.match(/\.([a-z0-9]{2,5})$/i) || [])[1];
  const lower = (ext || "").toLowerCase();
  let kind = "file";
  let label = "Fichier";
  if (["ppt", "pptx", "pptm", "odp"].includes(lower)) [kind, label] = ["slides", "Présentation"];
  else if (!ext) [kind, label] = isWeb ? ["web", "Page"] : ["folder", "Dossier"];
  else if (lower === "pdf") label = "PDF";
  else if (["xls", "xlsx", "xlsm", "csv"].includes(lower)) label = "Tableur";
  else if (["doc", "docx"].includes(lower)) label = "Document";
  return { isWeb, name: tail || link, kind, label };
}

function evidenceLinksHtml(links) {
  if (!links || !links.length) return "";
  return `<ul class="evidence-links">${links
    .map((link) => {
      const d = describeEvidenceLink(link);
      const action = d.isWeb
        ? `<a class="evidence-link__action" href="${escapeHtml(link)}" target="_blank" rel="noopener" aria-label="Ouvrir ${escapeHtml(d.name)} (nouvel onglet)">Ouvrir</a>`
        : `<button type="button" class="evidence-link__action js-copy-link" data-link="${escapeHtml(link)}" data-report-hide aria-label="Copier le chemin de ${escapeHtml(d.name)}" title="Le navigateur ne peut pas ouvrir un chemin réseau : copiez-le, puis collez-le dans l'explorateur">Copier le chemin</button>`;
      return `
      <li class="evidence-link evidence-link--${d.kind}">
        <span class="evidence-link__icon" title="${d.label}">${LINK_ICONS[d.kind]}</span>
        <span class="evidence-link__text"><span class="evidence-link__name">${escapeHtml(d.name)}</span><span class="evidence-link__path">${escapeHtml(link)}</span></span>
        ${action}
      </li>`;
    })
    .join("")}</ul>`;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (err) {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.cssText = "position:fixed;opacity:0;";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}

document.getElementById("evidence-list").addEventListener("click", async (event) => {
  const btn = event.target.closest(".js-copy-link");
  if (!btn) return;
  const ok = await copyText(btn.dataset.link);
  const label = btn.textContent;
  btn.textContent = ok ? "Copié ✓" : "Copie impossible";
  setTimeout(() => (btn.textContent = label), 1600);
});

function graphEvidenceHtml(e) {
  const cfg = e.graph_config || {};
  if (!cfg.data_source_url) {
    return `
      <div style="margin-top:10px;padding:12px 14px;background:var(--bg);border-radius:var(--radius-sm);border:1px dashed var(--border-soft);">
        <div style="font-size:11.5px;font-weight:600;color:var(--text-faint);">En attente de connexion</div>
        ${cfg.title ? `<div style="font-size:12.5px;margin-top:4px;">${escapeHtml(cfg.title)}</div>` : ""}
        ${
          cfg.x_label || cfg.y_label
            ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:2px;">${escapeHtml(cfg.x_label || "")}${cfg.x_label && cfg.y_label ? " / " : ""}${escapeHtml(cfg.y_label || "")}</div>`
            : ""
        }
        ${cfg.query ? `<div class="mono" style="font-size:11px;color:var(--text-faint);margin-top:6px;">${escapeHtml(cfg.query)}</div>` : ""}
      </div>`;
  }
  return `<div class="js-graph-mount" data-url="${escapeHtml(cfg.data_source_url)}" data-title="${escapeHtml(cfg.title || "")}" data-x-label="${escapeHtml(cfg.x_label || "")}" data-y-label="${escapeHtml(cfg.y_label || "")}" style="margin-top:10px;min-height:120px;background:var(--bg);border-radius:var(--radius-sm);padding:12px;font-size:11.5px;color:var(--text-faint);">Chargement du graphique…</div>`;
}

// Trace un nuage de points/ligne à la main en SVG (pas de bibliothèque de graphiques - cohérent
// avec le reste de l'app, sans étape de build).
function svgPlotHtml(points, title, xLabel, yLabel) {
  const w = 320;
  const h = 180;
  const pad = 28;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const xRange = xMax - xMin || 1;
  const yRange = yMax - yMin || 1;
  const sx = (x) => pad + ((x - xMin) / xRange) * (w - 2 * pad);
  const sy = (y) => h - pad - ((y - yMin) / yRange) * (h - 2 * pad);
  const sorted = [...points].sort((a, b) => a.x - b.x);
  const linePoints = sorted.map((p) => `${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
  const dots = points.map((p) => `<circle cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="2.5" fill="var(--accent)"/>`).join("");
  return `
    ${title ? `<div style="font-size:12px;font-weight:600;color:var(--text);margin-bottom:6px;">${escapeHtml(title)}</div>` : ""}
    <svg viewBox="0 0 ${w} ${h}" style="width:100%;height:auto;">
      <line x1="${pad}" y1="${h - pad}" x2="${w - pad}" y2="${h - pad}" stroke="var(--border-soft)"/>
      <line x1="${pad}" y1="${pad}" x2="${pad}" y2="${h - pad}" stroke="var(--border-soft)"/>
      <polyline points="${linePoints}" fill="none" stroke="var(--accent)" stroke-width="1.4"/>
      ${dots}
    </svg>
    <div style="display:flex;justify-content:space-between;font-size:10.5px;color:var(--text-faint);margin-top:2px;">
      <span>${escapeHtml(xLabel || "")}</span><span>${escapeHtml(yLabel || "")}</span>
    </div>`;
}

// fetch() côté client, jamais côté serveur : un fetch serveur vers une URL fournie par
// l'utilisateur ouvrirait une vraie surface SSRF pour une cible encore inconnue (le futur service
// de données de graph_config.data_source_url) ; le fetch navigateur n'a pas ce problème, au prix
// du CORS que devra exposer ce futur service - documenté dans l'aide du champ du formulaire.
async function drawGraphFromUrl(mount) {
  try {
    const response = await fetch(mount.dataset.url);
    if (!response.ok) throw new Error("réponse HTTP " + response.status);
    const data = await response.json();
    const points = Array.isArray(data.points) ? data.points : [];
    if (!points.length) {
      mount.innerHTML = `<div class="help" style="margin:0;">Aucune donnée renvoyée.</div>`;
      return;
    }
    mount.innerHTML = svgPlotHtml(points, mount.dataset.title, mount.dataset.xLabel, mount.dataset.yLabel);
  } catch (err) {
    mount.innerHTML = `<div class="help" style="margin:0;">Impossible de charger le graphique (${escapeHtml(err.message || String(err))}).</div>`;
  }
}

function evidenceFormFieldsHtml(kind) {
  if (kind === "graph") {
    return `
      <div><label>Source</label><input class="field" id="evidence-source" placeholder="lien, fichier ou référence"></div>
      <div class="field-row">
        <input class="field" id="evidence-graph-x-label" placeholder="libellé axe X">
        <input class="field" id="evidence-graph-y-label" placeholder="libellé axe Y">
      </div>
      <div><label>Requête</label><input class="field" id="evidence-graph-query" placeholder="ex : split vs intensité PL">
        <div class="help">Sera interprété par un futur service de données - laissez tel quel en attendant.</div>
      </div>
      <div><label>URL de source de données (optionnel)</label><input class="field" id="evidence-graph-url" placeholder="https://...">
        <div class="help">Si renseignée, le graphique se trace dès maintenant à partir de ce qu'elle renvoie (JSON {points:[{x,y},...]}).</div>
      </div>`;
  }
  const stepOptions = currentProcess
    ? `<div><label>Étape associée (optionnel)</label><select class="field" id="evidence-step-select">
         <option value="">— aucune —</option>
         ${(currentProcess.steps || []).map((s, i) => `<option value="${i}">${escapeHtml(stepLabelFor(i))}</option>`).join("")}
       </select></div>`
    : "";
  return `
    <div><label for="evidence-links">Liens <span class="help" style="display:inline;margin:0;font-weight:400;">- un dossier, une présentation PowerPoint, une page SharePoint… un par ligne</span></label>
      <textarea class="field" id="evidence-links" rows="2" placeholder="\\\\serveur\\partage\\Runs\\W42\\revue.pptx&#10;https://…sharepoint.com/…"></textarea></div>
    <div><label>Images <span class="help" style="display:inline;margin:0;font-weight:400;">- collez (Ctrl+V), glissez-déposez ou choisissez une ou plusieurs images</span></label>
      <div id="evidence-images-drop"></div></div>
    <div><label for="evidence-source">Référence (optionnel)</label><input class="field" id="evidence-source" placeholder="appareil, fichier de mesure, référence…"></div>
    ${stepOptions}
    <div class="field-row">
      <input class="field" id="evidence-metric-name" placeholder="mesure (optionnel)">
      <input class="field" id="evidence-metric-value" type="number" placeholder="valeur">
    </div>`;
}

// La planche d'images du formulaire de preuve (image-drop.js, sans type d'image) - remontée à
// chaque fois que les champs « standard » sont (re)posés.
let evidenceImagesDrop = null;
function mountEvidenceImagesDrop() {
  const zone = document.getElementById("evidence-images-drop");
  evidenceImagesDrop = zone
    ? mountImageDrop(zone, {
        slug,
        purpose: "evidence",
        withKind: false,
        compact: true,
        onChange: () => clearError(),
        onError: showError,
        // coller une image ne vise ce formulaire que quand l'onglet Données est affiché
        isActive: () => !document.querySelector("dialog[open]") && !document.getElementById("panel-donnees").hidden,
      })
    : null;
}

function renderEvidence(detail) {
  const list = document.getElementById("evidence-list");
  list.innerHTML = detail.evidence.length
    ? detail.evidence
        .map((e) => {
          const metricEntries = Object.entries(e.metrics || {});
          const metricText = metricEntries
            .map(([name, q]) => `${escapeHtml(name)} : ${escapeHtml(String(q.value))}${q.unit ? " " + escapeHtml(q.unit) : ""}`)
            .join(" · ");
          const stepBadge =
            e.step_index != null
              ? `<span class="badge badge-role" style="font-size:10.5px;margin-left:6px;">${escapeHtml(stepLabelFor(e.step_index))}</span>`
              : "";
          const kindBadge =
            e.kind && e.kind !== "standard" && EVIDENCE_KIND_LABELS[e.kind]
              ? `<span class="badge badge-role" style="font-size:10.5px;margin-left:6px;">${EVIDENCE_KIND_LABELS[e.kind]}</span>`
              : "";
          const links = (detail.evidence_links || {})[e.id] || [];
          const objectiveLine = e.objective
            ? `<div style="font-size:12px;color:var(--text-soft);margin-top:4px;">Objectif visé&nbsp;: <strong>${escapeHtml(e.objective)}</strong></div>`
            : "";
          const interpretationBlock = e.interpretation
            ? `<div style="font-size:12.5px;color:var(--text-soft);margin-top:6px;line-height:1.5;font-style:italic;">${escapeHtml(e.interpretation)}</div>`
            : "";
          let bodyHtml = evidenceImagesHtml(detail, e);
          if (e.kind === "graph") bodyHtml += graphEvidenceHtml(e);
          return `
            <div class="marked-card" style="margin-top:12px;">
              <div style="font-size:13px;font-weight:600;">${escapeHtml(e.description)}${stepBadge}${kindBadge}</div>
              ${e.source && !links.includes(e.source) ? `<div style="font-size:12px;color:var(--text-soft);margin-top:2px;word-break:break-all;">${e.source.startsWith("http") ? `<a href="${escapeHtml(e.source)}" target="_blank" rel="noopener">${escapeHtml(e.source)}</a>` : escapeHtml(e.source)}</div>` : ""}
              ${evidenceLinksHtml(links)}
              ${metricText ? `<div class="mono" style="font-size:11.5px;color:var(--text-faint);margin-top:4px;">${metricText}</div>` : ""}
              ${objectiveLine}
              ${interpretationBlock}
              ${bodyHtml}
            </div>`;
        })
        .join("")
    : `<div class="help">Aucune preuve enregistrée.</div>`;

  document.querySelectorAll(".js-graph-mount").forEach((mount) => drawGraphFromUrl(mount));

  document.querySelectorAll(".js-remove-annotation").forEach((btn) => {
    btn.addEventListener("click", () => {
      const evidenceId = btn.dataset.evidenceId;
      const idx = parseInt(btn.dataset.index, 10);
      const evidence = detail.evidence.find((ev) => ev.id === evidenceId);
      if (!evidence) return;
      const updated = (evidence.image_annotations || []).filter((_, i) => i !== idx);
      saveAnnotations(evidenceId, updated);
    });
  });

  document.querySelectorAll(".js-annotation-image").forEach((container) => {
    const evidenceId = container.dataset.evidenceId;
    const attachmentId = container.dataset.attachmentId;
    const evidence = detail.evidence.find((ev) => ev.id === evidenceId);
    const toolsBar = document.querySelector(`.js-annotation-tools[data-attachment-id="${attachmentId}"]`);
    if (!evidence || !toolsBar) return;
    const hint = toolsBar.querySelector(".js-annotation-hint");
    const others = (evidence.image_annotations || []).filter((a) => a.attachment_id && a.attachment_id !== attachmentId);
    const localAnnotations = (evidence.image_annotations || []).filter((a) => !a.attachment_id || a.attachment_id === attachmentId).map((a) => ({ ...a, attachment_id: attachmentId }));
    let tool = null;
    let dragStart = null;

    function redraw() {
      const svg = container.querySelector("svg");
      if (svg) svg.remove();
      container.insertAdjacentHTML("beforeend", annotationMarkersSvg(localAnnotations));
    }

    function pct(evt) {
      const rect = container.getBoundingClientRect();
      return {
        x: Math.max(0, Math.min(100, ((evt.clientX - rect.left) / rect.width) * 100)),
        y: Math.max(0, Math.min(100, ((evt.clientY - rect.top) / rect.height) * 100)),
      };
    }

    function finishAnnotation(shape) {
      const label = window.prompt("Libellé de l'annotation (optionnel)");
      localAnnotations.push({ attachment_id: container.dataset.attachmentId, ...shape, label: label || null });
      redraw();
      tool = null;
      hint.textContent = "";
    }

    toolsBar.querySelectorAll(".js-annotation-tool").forEach((btn) => {
      btn.addEventListener("click", () => {
        tool = btn.dataset.tool;
        dragStart = null;
        hint.textContent = tool === "arrow" ? "Cliquez le départ puis l'arrivée de la flèche." : "Cliquez-glissez pour dessiner le cadre.";
      });
    });
    container.addEventListener("mousedown", (evt) => {
      if (tool !== "box") return;
      dragStart = pct(evt);
    });
    container.addEventListener("mouseup", (evt) => {
      if (tool !== "box" || !dragStart) return;
      finishAnnotation({ type: "box", x: dragStart.x, y: dragStart.y, x2: pct(evt).x, y2: pct(evt).y });
      dragStart = null;
    });
    container.addEventListener("click", (evt) => {
      if (tool !== "arrow") return;
      const point = pct(evt);
      if (!dragStart) {
        dragStart = point;
        hint.textContent = "Cliquez l'arrivée de la flèche.";
      } else {
        finishAnnotation({ type: "arrow", x: dragStart.x, y: dragStart.y, x2: point.x, y2: point.y });
        dragStart = null;
      }
    });
    toolsBar.querySelector(".js-annotation-save").addEventListener("click", () => saveAnnotations(evidenceId, [...others, ...localAnnotations]));
  });

  renderEvidenceCompareTool(detail);

  const formWrap = document.getElementById("add-evidence-wrap");
  if (!isEditorRole()) {
    formWrap.innerHTML = "";
    return;
  }
  const objectiveField = detail.objectives.length
    ? `<div><label>Objectif visé (optionnel)</label><select class="field" id="evidence-objective-select">
         <option value="">— aucun —</option>
         ${detail.objectives.map((o) => `<option value="${escapeHtml(o.name)}">${escapeHtml(o.name)}</option>`).join("")}
       </select></div>`
    : "";
  formWrap.innerHTML = `
    <form id="evidence-form" class="field-group" data-report-hide style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border-soft);">
      <div><label>Type de preuve</label>
        <select class="field" id="evidence-kind-select">
          <option value="standard">Mesure, document, images</option>
          <option value="graph">Graphique</option>
        </select>
      </div>
      <div><label>Description</label><input class="field" id="evidence-description" placeholder="ex : mesure d'épaisseur au profilomètre" required></div>
      ${objectiveField}
      <div><label>Interprétation (optionnel)</label><textarea class="field" id="evidence-interpretation" rows="2" placeholder="pourquoi ce résultat est cohérent avec le changement"></textarea></div>
      <div id="evidence-kind-fields">${evidenceFormFieldsHtml("standard")}</div>
      <button class="btn btn-line btn-block" type="submit">Ajouter la preuve</button>
    </form>`;
  mountEvidenceImagesDrop();
  document.getElementById("evidence-kind-select").addEventListener("change", (event) => {
    document.getElementById("evidence-kind-fields").innerHTML = evidenceFormFieldsHtml(event.target.value);
    mountEvidenceImagesDrop();
  });
  document.getElementById("evidence-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const kind = document.getElementById("evidence-kind-select").value;
    const objectiveSelect = document.getElementById("evidence-objective-select");
    const interpretation = document.getElementById("evidence-interpretation").value.trim();
    let source = "";
    let graphConfig = null;
    let links = [];
    let images = [];
    try {
      if (kind === "graph") {
        source = document.getElementById("evidence-source").value.trim();
        graphConfig = {
          title: document.getElementById("evidence-description").value.trim(),
          x_label: document.getElementById("evidence-graph-x-label").value.trim() || null,
          y_label: document.getElementById("evidence-graph-y-label").value.trim() || null,
          query: document.getElementById("evidence-graph-query").value.trim() || null,
          data_source_url: document.getElementById("evidence-graph-url").value.trim() || null,
        };
      } else {
        source = document.getElementById("evidence-source").value.trim();
        links = document.getElementById("evidence-links").value.split(/\n+/).map((l) => l.trim()).filter(Boolean);
        if (evidenceImagesDrop && evidenceImagesDrop.isUploading()) throw new Error("Une image est encore en cours d'envoi - un instant.");
        images = evidenceImagesDrop ? evidenceImagesDrop.get().map((img) => ({ image_id: img.image_id, caption: (img.caption || "").trim() || null })) : [];
      }
      const metricNameEl = document.getElementById("evidence-metric-name");
      const metricValueEl = document.getElementById("evidence-metric-value");
      const stepSelect = document.getElementById("evidence-step-select");
      const result = await evidenceApi.add(slug, experienceId, {
        description: document.getElementById("evidence-description").value,
        source,
        kind,
        objective: objectiveSelect && objectiveSelect.value ? objectiveSelect.value : null,
        interpretation: interpretation || null,
        graph_config: graphConfig,
        metric_name: metricNameEl ? metricNameEl.value.trim() || null : null,
        metric_value: metricValueEl && metricValueEl.value ? parseFloat(metricValueEl.value) : null,
        step_index: stepSelect && stepSelect.value !== "" ? parseInt(stepSelect.value, 10) : null,
        links,
        images,
      });
      // preuves records a new version carrying the evidence - its links and images included
      // (experiences are immutable) - go to it, not back to this now-superseded version.
      goToVersion(result.id);
    } catch (err) {
      showError(err);
    }
  });
}

// Texte "Kind — nom" pour l'étape à cet index dans le procédé courant (currentProcess.steps),
// réutilisant STEP_KIND_LABELS déjà utilisé pour la modale de couche ci-dessus. Une preuve dont
// step_index ne correspond plus au procédé *actuel* (une évolution ultérieure a raccourci ou
// changé la liste d'étapes) dégrade proprement vers "introuvable" plutôt que de planter - aucun
// lien vivant vers la version où elle a été prise n'est maintenu.
function stepLabelFor(index) {
  const step = currentProcess?.steps?.[index];
  if (!step) return `étape #${index + 1} (introuvable)`;
  return `${STEP_KIND_LABELS[step.kind] || step.kind} — ${step.name}`;
}

// Comparaison de deux preuves entre elles (ex : une mesure après un dépôt d'ITO à 400 nm puis à
// 200 nm) - entièrement côté client, detail.evidence est déjà chargé en entier avec ses mesures.
function renderEvidenceCompareTool(detail) {
  const tool = document.getElementById("evidence-compare-tool");
  if (detail.evidence.length < 2) {
    tool.style.display = "none";
    return;
  }
  tool.style.display = "block";
  const options = detail.evidence
    .map(
      (e) =>
        `<option value="${e.id}">${escapeHtml(e.description)}${e.step_index != null ? " — " + escapeHtml(stepLabelFor(e.step_index)) : ""}</option>`
    )
    .join("");
  const selectA = document.getElementById("evidence-compare-a");
  const selectB = document.getElementById("evidence-compare-b");
  selectA.innerHTML = options;
  selectB.innerHTML = options;
  // par défaut, les deux preuves les plus récentes - le cas le plus probable ("comparer où j'en suis
  // par rapport à juste avant").
  selectA.selectedIndex = Math.max(0, detail.evidence.length - 2);
  selectB.selectedIndex = detail.evidence.length - 1;
  document.getElementById("evidence-compare-result").innerHTML = "";
}

document.getElementById("evidence-compare-btn").addEventListener("click", () => {
  const idA = document.getElementById("evidence-compare-a").value;
  const idB = document.getElementById("evidence-compare-b").value;
  const box = document.getElementById("evidence-compare-result");
  if (!idA || !idB) return;
  if (idA === idB) {
    box.innerHTML = `<div class="help">Choisissez deux preuves différentes.</div>`;
    return;
  }
  const a = currentDetail.evidence.find((e) => e.id === idA);
  const b = currentDetail.evidence.find((e) => e.id === idB);
  const names = [...new Set([...Object.keys(a.metrics || {}), ...Object.keys(b.metrics || {})])];
  if (names.length === 0) {
    box.innerHTML = `<div class="help">Aucune des deux preuves n'a de mesure chiffrée à comparer.</div>`;
    return;
  }
  const fmt = (q) => (q ? `${q.value}${q.unit ? " " + q.unit : ""}` : "—");
  const rows = names
    .map((name) => {
      const qa = (a.metrics || {})[name];
      const qb = (b.metrics || {})[name];
      let delta = "—";
      if (qa && qb && typeof qa.value === "number" && typeof qb.value === "number") {
        if (qa.unit === qb.unit) {
          const d = qb.value - qa.value;
          delta = `${d > 0 ? "+" : ""}${d}${qb.unit ? " " + qb.unit : ""}`;
        } else {
          delta = "unités différentes";
        }
      }
      return `<tr><td>${escapeHtml(name)}</td><td class="mono">${escapeHtml(fmt(qa))}</td><td class="mono">${escapeHtml(fmt(qb))}</td><td class="mono">${escapeHtml(delta)}</td></tr>`;
    })
    .join("");
  box.innerHTML = `
    <table style="width:100%;font-size:12.5px;border-collapse:collapse;">
      <thead><tr style="color:var(--text-faint);text-align:left;"><th>Mesure</th><th>${escapeHtml(a.description)}</th><th>${escapeHtml(b.description)}</th><th>Écart</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
});

function renderForksNote(detail) {
  const box = document.getElementById("forks-note");
  if (detail.children.length < 2) {
    box.style.display = "none";
    return;
  }
  box.style.display = "block";
  box.innerHTML = `
    <div style="font-size:12px;color:var(--text-faint);margin-bottom:6px;">Cette version a donné plusieurs pistes :</div>
    ${detail.children
      .map((c) => `<div style="font-size:13px;margin-bottom:4px;"><a href="/microprojets/${slug}/experiences/${c.id}">${escapeHtml(c.title)}</a></div>`)
      .join("")}
    <a href="/microprojets/${slug}" style="font-size:12px;">Voir le µprojet &rarr;</a>`;
}

function renderTags(detail) {
  const row = document.getElementById("tags-row");
  const canEdit = isEditorRole();
  const chips = detail.tags
    .map(
      (t, i) => `
      <span class="badge badge-role">
        ${escapeHtml(t)}
        ${
          canEdit
            ? `<button class="js-remove-tag" data-index="${i}" type="button" data-report-hide style="background:none;border:none;cursor:pointer;color:inherit;padding:0;margin-left:2px;font-size:13px;line-height:1;">&times;</button>`
            : ""
        }
      </span>`
    )
    .join("");
  row.innerHTML =
    chips +
    (canEdit
      ? `<input id="new-tag-input" data-report-hide placeholder="+ étiquette" style="border:1px dashed var(--border-soft);border-radius:999px;padding:4px 10px;font-size:12px;width:110px;background:transparent;">`
      : "");

  row.querySelectorAll(".js-remove-tag").forEach((btn) => {
    btn.addEventListener("click", () => {
      const next = [...detail.tags];
      next.splice(parseInt(btn.dataset.index, 10), 1);
      updateTags(next);
    });
  });
  const input = document.getElementById("new-tag-input");
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && input.value.trim()) {
        event.preventDefault();
        updateTags([...detail.tags, input.value.trim()]);
      }
    });
  }
}

async function updateTags(tags) {
  clearError();
  try {
    const result = await experimentsApi.setTags(slug, experienceId, { tags });
    // like conclure/preuves, tagging records a new version - follow it there.
    goToVersion(result.id);
  } catch (err) {
    showError(err);
  }
}

function renderRefs(detail) {
  const row = document.getElementById("refs-row");
  const canEdit = isEditorRole();
  const chips = detail.ref_names
    .map((name) => `<span class="badge badge-role" title="Ref">🏷 ${escapeHtml(name)}</span>`)
    .join("");
  row.innerHTML =
    chips +
    (canEdit
      ? `<button id="make-ref-btn" data-report-hide type="button" class="btn btn-line" style="padding:2px 10px;font-size:11.5px;">+ ref</button>
         <input id="new-ref-input" data-report-hide placeholder="surnom (optionnel)" style="display:none;border:1px dashed var(--border-soft);border-radius:999px;padding:4px 10px;font-size:12px;width:150px;background:transparent;">`
      : "");

  const makeBtn = document.getElementById("make-ref-btn");
  const input = document.getElementById("new-ref-input");
  if (makeBtn) {
    makeBtn.addEventListener("click", () => {
      makeBtn.style.display = "none";
      input.style.display = "";
      input.focus();
    });
  }
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        createRef(input.value.trim());
      }
    });
  }
}

async function createRef(name) {
  clearError();
  try {
    await experimentsApi.createRef(slug, experienceId, { name: name || null });
    currentDetail = await experimentsApi.get(slug, experienceId);
    renderRefs(currentDetail);
  } catch (err) {
    showError(err);
  }
}

function formatIntentFormAnswer(field, value) {
  if (field && field.type === "boolean") return value ? "Oui" : "Non";
  return String(value);
}

// Petite boîte d'infos : les réponses au formulaire d'intention du µprojet (spectre.core.
// intent_forms), avec les libellés du formulaire actuellement actif quand on les retrouve - une
// expérience plus ancienne peut avoir été répondue à un formulaire depuis modifié, auquel cas le
// nom brut du champ sert de repli plutôt que de cacher la réponse.
async function renderIntentFormInfo(detail) {
  const box = document.getElementById("intent-form-info-box");
  const answers = detail.form_answers || {};
  if (Object.keys(answers).length === 0) {
    box.style.display = "none";
    return;
  }
  let activeForm = null;
  try {
    const active = await intentFormsApi.active(slug);
    activeForm = active ? active.form : null;
  } catch (err) {
    // pas bloquant : on retombe sur les noms de champs bruts
  }
  const fieldByName = new Map((activeForm ? activeForm.fields : []).map((f) => [f.name, f]));
  const rows = Object.entries(answers)
    .map(([name, value]) => {
      const field = fieldByName.get(name);
      const label = field ? field.label : name;
      return `<div class="fiche-hero__answer"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(formatIntentFormAnswer(field, value))}</dd></div>`;
    })
    .join("");
  box.innerHTML = `<div class="fiche-hero__label">${escapeHtml(activeForm ? activeForm.title : "Formulaire d'intention")}</div><dl class="fiche-hero__answers-list">${rows}</dl>`;
  box.style.display = "block";
}

async function populateCombineSelect() {
  try {
    const data = await experimentsApi.list(slug, { status: "all", limit: 200 });
    const options = data.items
      .filter((exp) => exp.id !== experienceId)
      .map((exp) => `<option value="${exp.id}">${escapeHtml(exp.title)}</option>`)
      .join("");
    document.getElementById("combine-select").innerHTML = options || `<option value="">Aucune autre expérience à combiner</option>`;
  } catch (err) {
    // silent: advanced/secondary panel
  }
}

document.getElementById("combine-btn").addEventListener("click", async () => {
  clearError();
  const otherId = document.getElementById("combine-select").value;
  const title = document.getElementById("combine-title").value.trim();
  const intent = document.getElementById("combine-intent").value.trim();
  if (!otherId || !title || !intent) {
    showError(new Error("Choisissez une expérience, un titre et une raison de combiner."));
    return;
  }
  try {
    const result = await experimentsApi.combine(slug, experienceId, {
      other_id: otherId,
      title,
      intent,
    });
    goToVersion(result.id);
  } catch (err) {
    showError(err);
  }
});

async function savePhysicalTracking(entities) {
  clearError();
  try {
    const result = await experimentsApi.setEntities(slug, experienceId, { entities });
    // like tags/preuves, this records a new version - follow it there.
    goToVersion(result.id);
  } catch (err) {
    showError(err);
  }
}

async function renderPhysicalTracking(detail) {
  const card = document.getElementById("physical-tracking-content");
  const canEdit = isEditorRole();
  const tracking = detail.physical_tracking || [];
  let labels = null;
  if (detail.is_batch) {
    try {
      const variation = await getBatchVariation();
      labels = variation.labels || null;
    } catch (err) {
      labels = null;
    }
  }
  const rows = (tracking.length ? tracking : [{}]).map((entry, i) =>
    plateRowHtml(entry, i, canEdit, detail.is_batch ? (labels && labels[i]) || `Variante ${i + 1}` : null)
  );
  card.innerHTML = `
    <div class="plates-list${detail.is_batch ? " plates-list--batch" : ""}">${rows.join("")}</div>
    ${canEdit ? `<button class="btn btn-line" id="save-physical-tracking-btn" type="button" data-report-hide style="margin-top:12px;">Enregistrer les plaques</button>` : ""}
    ${
      canEdit
        ? `<div class="plates-lot" data-report-hide>
            <div class="section-title" style="font-size:12px;margin-bottom:6px;">Lot de fabrication</div>
            <div id="plates-lot-assign"></div>
          </div>`
        : ""
    }`;
  if (!canEdit) return;
  // mettre une plaque de l'expérience dans un lot (lot-picker.js) - les lasermarks enregistrés
  mountLotAssign(document.getElementById("plates-lot-assign"), { lasermarks: tracking.map((e) => e.sample_id) });
  mountEntityFdlFields(tracking);
  document.getElementById("save-physical-tracking-btn").addEventListener("click", () => {
    const count = Math.max(tracking.length, 1);
    const entities = Array.from({ length: count }, (_, i) => {
      const sampleInput = document.querySelector(`.js-entity-sample-id[data-index="${i}"]`);
      const locInput = document.querySelector(`.js-entity-location[data-index="${i}"]`);
      return { sample_id: sampleInput.value.trim() || null, location: locInput.value.trim() || null, fdl: entityFdlValues(i) };
    });
    savePhysicalTracking(entities);
  });
}

// « Données en base » (characterization/static/wafer-data-links.js::renderWaferDbLinks) : les requêtes PRISM ouvertes sur les plaques de l'expérience.
function renderDbLinks(detail) {
  renderWaferDbLinks(document.querySelectorAll(".js-db-link"), (detail.physical_tracking || []).map((e) => e.sample_id));
}

function renderReferences(detail) {
  const el = document.getElementById("references-list");
  document.getElementById("references-card").style.display = detail.references.length ? "" : "none";
  if (detail.references.length === 0) {
    el.innerHTML = "";
    return;
  }
  el.innerHTML = detail.references
    .map((r) => {
      const label = REFERENCE_ROLE_LABELS[r.role] || r.role;
      const target = r.experiment_id
        ? `<a href="/microprojets/${slug}/experiences/${r.experiment_id}">${escapeHtml(r.label)}</a>`
        : escapeHtml(r.label);
      return `<div style="font-size:13px;margin-bottom:8px;"><span style="color:var(--text-faint);font-size:11px;text-transform:uppercase;letter-spacing:.02em;">${escapeHtml(label)}</span><br>${target}</div>`;
    })
    .join("");
}

// Le rapport est une capture de ce qui est affiché, purgée de tout ce qui n'a de sens que dans
// l'appli vivante : chaque bloc est cloné puis débarrassé de tout nœud marqué data-report-hide (un
// formulaire, un bouton d'action, un champ éditable, la barre d'onglets...) ; le miroir texte
// .report-only qui l'accompagne parfois (cf. plateRowHtml) - invisible sur la fiche vivante -
// est alors révélé pour porter la valeur à sa place. Les trois onglets y figurent tous, l'un après
// l'autre sous leur titre, quel que soit celui qui est ouvert à l'écran (un onglet masqué est
// dévoilé dans la copie) ; les flèches d'un carrousel de variantes disparaissent, la cartographie
// montrant déjà chaque variante.
function cleanSectionForReport(el, inlined = {}) {
  const clone = el.cloneNode(true);
  clone.removeAttribute("hidden");
  clone.querySelectorAll("[data-report-hide], .atlas-carousel__nav").forEach((node) => node.remove());
  clone.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id")); // pas de doublons d'id dans le document
  // Les images servies par l'appli (dessin d'une structure en image, données, preuves) ne
  // s'ouvriraient pas hors de Spectre : le rapport les embarque (data: URL, voir inlineReportImages).
  clone.querySelectorAll("img").forEach((img) => {
    const src = img.getAttribute("src");
    if (src && inlined[src]) img.setAttribute("src", inlined[src]);
    img.removeAttribute("loading");
  });
  clone.querySelectorAll("a[href]").forEach((link) => {
    if (api.isApiUrl(link.getAttribute("href"))) link.removeAttribute("href");
  });
  return clone.outerHTML;
}

async function inlineReportImages(roots) {
  const sources = new Set();
  roots.forEach((root) =>
    root.querySelectorAll("img[src]").forEach((img) => {
      if (api.isApiUrl(img.getAttribute("src"))) sources.add(img.getAttribute("src"));
    })
  );
  const inlined = {};
  await Promise.all(
    [...sources].map(async (src) => {
      try {
        const blob = await api.get(src, { as: "blob", redirectOn401: false });
        inlined[src] = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = reject;
          reader.readAsDataURL(blob);
        });
      } catch (err) {
        // image indisponible : le rapport garde le lien d'origine
      }
    })
  );
  return inlined;
}

async function generateReportHtml() {
  // toutes les feuilles de style de la page (noyau puis plugins, dans leur ordre) - lues dans ses <link>
  const sheets = [...document.querySelectorAll('link[rel="stylesheet"]')].filter((link) => new URL(link.href).origin === window.location.origin);
  const css = (await Promise.all(sheets.map((link) => fetch(link.href).then((r) => (r.ok ? r.text() : ""))))).join("\n");
  // styles propres à la page (infobulles de couches...) : repris tels quels
  const pageCss = [...document.querySelectorAll("head style")].map((el) => el.textContent).join("\n");
  const panelEls = ["panel-structure", "panel-donnees", "panel-conclusion"].map((id) => document.getElementById(id)).filter((el) => el);
  const inlined = await inlineReportImages(panelEls);
  const panels = panelEls
    .map((el) => `<h2 class="report-section-title">${escapeHtml(el.dataset.reportTitle || "")}</h2>${cleanSectionForReport(el, inlined)}`)
    .join("\n");
  const sections = cleanSectionForReport(document.getElementById("header-card")) + panels;
  const generatedAt = new Intl.DateTimeFormat("fr-FR", { dateStyle: "long", timeStyle: "short" }).format(new Date());
  const project = [currentMicroprojectCode, currentMicroprojectName].filter(Boolean).join(" · ");
  return `<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(currentDetail.title)} — rapport d'expérience</title>
<style>${css}</style>
<style>${pageCss}</style>
<style>
  body{background:var(--bg);padding:28px 16px;}
  .report-page{max-width:1180px;margin:0 auto;}
  .report-banner{background:var(--surface);border:1px solid var(--border-soft);border-radius:var(--radius-sm);padding:10px 14px;margin-bottom:20px;font-size:12px;color:var(--text-faint);}
  .report-only{display:inline !important;}
  .fiche-panel{margin-bottom:8px;}
  .fiche-card__scroll,.fiche-history .timeline{max-height:none;overflow:visible;}
  @media print{body{padding:0;background:#fff;}.card{box-shadow:none;break-inside:avoid;}.report-section-title{break-after:avoid;}}
</style>
</head>
<body>
  <div class="report-page">
    <div class="report-banner">Rapport d'expérience — extrait de Spectre (µprojet « ${escapeHtml(project)} ») le ${generatedAt}. Document autonome : une photographie de cette fiche à cet instant, sans lien avec les données vivantes du µprojet.</div>
    ${sections}
  </div>
</body>
</html>`;
}

async function downloadReport() {
  clearError();
  try {
    const html = await generateReportHtml();
    const blob = new Blob([html], { type: "text/html" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `rapport-${currentMicroprojectCode || slug}-${experienceId}.html`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError(err);
  }
}

// « Éditer la fiche » : l'éditeur de la fiche, prérempli - la page « structure en images » pour une
// structure donnée en images, sinon le constructeur, ouvert sur l'écran « intention » (en-tête :
// contexte, ce qu'on veut démontrer, objectifs) ou sur la structure (« Modifier la structure »).
function goToEvolve(stage = null) {
  const mode = currentDetail && currentDetail.structure_images ? "evoluer-image" : "evoluer";
  const query = stage && mode === "evoluer" ? `?etape=${encodeURIComponent(stage)}` : "";
  window.location.href = `/microprojets/${slug}/experiences/${experienceId}/${mode}${query}`;
}

// --- structure en images : modifier la planche ---------------------------------------------------

let replaceDrawingDrop = null;

function showReplaceDrawingError(err) {
  const box = document.getElementById("replace-drawing-error");
  box.textContent = err ? err.message || String(err) : "";
  box.style.display = err ? "block" : "none";
}

function openReplaceDrawing() {
  const dialog = document.getElementById("replace-drawing-dialog");
  if (!replaceDrawingDrop) {
    replaceDrawingDrop = mountImageDrop(document.getElementById("replace-drawing-drop"), {
      slug,
      onChange: () => showReplaceDrawingError(null),
      onError: showReplaceDrawingError,
      isActive: () => dialog.open,
    });
    document.getElementById("replace-drawing-cancel").addEventListener("click", () => dialog.close());
    document.getElementById("replace-drawing-save").addEventListener("click", saveReplacedDrawing);
  }
  replaceDrawingDrop.set(currentDetail.structure_images);
  showReplaceDrawingError(null);
  document.getElementById("replace-drawing-save").disabled = false;
  dialog.showModal();
  document.querySelector("#replace-drawing-drop .img-board__bar .img-board__add")?.focus();
}

async function saveReplacedDrawing() {
  const images = replaceDrawingDrop.get();
  if (replaceDrawingDrop.isUploading()) return showReplaceDrawingError(new Error("Une image est encore en cours d'envoi - un instant."));
  if (!images.length) return showReplaceDrawingError(new Error("Il faut au moins une image."));
  const button = document.getElementById("replace-drawing-save");
  button.disabled = true;
  try {
    const result = await experimentsApi.replaceDrawing(slug, experienceId, {
      images: images.map((img) => ({ ...img, caption: (img.caption || "").trim() || null })),
    });
    if (result.id === experienceId) {
      document.getElementById("replace-drawing-dialog").close();
      return;
    }
    goToVersion(result.id);
  } catch (err) {
    showReplaceDrawingError(err);
    button.disabled = false;
  }
}

function wireDeleteExperience() {
  const btn = document.getElementById("delete-experience-btn");
  const hint = document.getElementById("delete-experience-hint");
  btn.addEventListener("click", async () => {
    const children = currentDetail.children || [];
    const title = currentDetail.title || "cette étude";
    if (children.length) {
      const sameBranch = children.some((c) => c.branch === currentDetail.branch);
      hint.textContent = sameBranch
        ? "Vous consultez une version ancienne — ouvrez la version courante de cette piste pour la supprimer."
        : `Impossible : ${children.length} piste(s) découlent de cette version. Supprimez-les d'abord.`;
      return;
    }
    if (!window.confirm(`Supprimer définitivement « ${title} » (cette version et les précédentes de cette piste) ? Cette action est irréversible.`)) return;
    btn.disabled = true;
    clearError();
    try {
      const result = await experimentsApi.remove(slug, experienceId);
      hint.textContent = `${result.count} version(s) supprimée(s).`;
      window.location.href = `/microprojets/${slug}`;
    } catch (err) {
      showError(err);
      btn.disabled = false;
    }
  });
}

function applyModeVisibility() {
  const editing = isEditorRole();
  document.getElementById("evolve-btn").style.display = editing ? "" : "none";
  // currentProcess n'est connu qu'après le chargement de /process (voir init()) - avant ça, ce
  // lien reste caché même si editing est vrai, applyModeVisibility() étant rappelée une fois de
  // plus dès que currentProcess est résolu.
  document.getElementById("structure-evolve-link").style.display = editing && currentProcess ? "" : "none";
  document.getElementById("structure-replace-btn").style.display = editing && currentDetail && currentDetail.structure_images ? "" : "none";
  // "Actions avancées" (combiner / supprimer) : réservé à l'éditeur - les Liens, eux, sont dans
  // l'onglet « Structure & intention », visibles de tous.
  document.getElementById("advanced-actions").style.display = editing ? "" : "none";
  // le rapport reste disponible pour tout le monde en permanence - un éditeur voit ses propres
  // formulaires d'édition sur la fiche vivante, mais l'export les retire toujours (data-report-hide,
  // voir generateReportHtml) : plus besoin d'un mode dédié pour garantir un rapport propre.
  document.getElementById("export-report-btn").style.display = "";
}

async function init() {
  try {
    currentDetail = await experimentsApi.get(slug, experienceId);
    const microproject = await microprojectsApi.get(slug);
    currentRole = microproject.role;
    currentMicroprojectName = microproject.name;
    currentMicroprojectCode = microproject.code || null;
    document.getElementById("microproject-crumb").textContent = microproject.code ? `${microproject.code} · ${microproject.name}` : microproject.name;
    document.getElementById("microproject-crumb").href = `/microprojets/${slug}`;
    const areaCrumb = document.getElementById("area-crumb");
    if (microproject.management_area) {
      areaCrumb.textContent = microproject.management_area.name;
      areaCrumb.href = `/management/${encodeURIComponent(microproject.management_area.slug)}`;
    } else {
      areaCrumb.textContent = "Non classé";
    }
    document.getElementById("thematic-crumb").textContent = microproject.thematique ? " / " + microproject.thematique.name : "";

    renderHeader(currentDetail);
    updateTabBadges(currentDetail);
    renderTags(currentDetail);
    renderRefs(currentDetail);
    renderIntentFormInfo(currentDetail);
    renderObjectives(currentDetail);
    renderForksNote(currentDetail);
    renderReferences(currentDetail);
    renderConclusion(currentDetail);
    renderBatchMatrix(currentDetail);
    renderPhysicalTracking(currentDetail);
    renderDbLinks(currentDetail);

    if (isEditorRole()) {
      document.getElementById("evolve-btn").addEventListener("click", () => goToEvolve("intention"));
      document.getElementById("structure-evolve-link").addEventListener("click", () => goToEvolve());
      document.getElementById("structure-replace-btn").addEventListener("click", openReplaceDrawing);
      populateCombineSelect();
      wireDeleteExperience();
    }
    document.getElementById("export-report-btn").addEventListener("click", downloadReport);
    applyModeVisibility();

    const [timeline, diff, process, entityHistory] = await Promise.all([
      experimentsApi.timeline(slug, experienceId),
      experimentsApi.diff(slug, experienceId),
      currentDetail.has_editable_process
        ? experimentsApi.process(slug, experienceId).catch(() => null)
        : Promise.resolve(null),
      wafersApi.entityHistory(slug).catch(() => ({ sample_ids: [], locations: [], fdls: [] })),
    ]);
    currentProcess = process;
    document.getElementById("entity-sample-id-history").innerHTML = entityHistory.sample_ids.map((v) => `<option value="${escapeHtml(v)}">`).join("");
    document.getElementById("entity-location-history").innerHTML = entityHistory.locations.map((v) => `<option value="${escapeHtml(v)}">`).join("");
    document.getElementById("entity-fdl-history").innerHTML = (entityHistory.fdls || []).map((v) => `<option value="${escapeHtml(v)}">`).join("");
    // rejoués maintenant que currentProcess est connu - applyModeVisibility gère #structure-evolve-link,
    // renderEvidence le badge/select par étape et l'outil de comparaison (voir stepLabelFor).
    applyModeVisibility();
    renderEvidence(currentDetail);
    if (typeof renderDataGallery === "function") renderDataGallery(currentDetail);
    if (typeof renderNotebook === "function") renderNotebook(currentDetail);
    renderTimeline(timeline.versions);
    renderFullHistory(timeline.items);
    const current = timeline.items.find((item) => item.is_current);
    document.getElementById("hero-version").textContent = current ? `v${current.version}` : "";
    // « Débutée le » : le début de la version de structure actuelle (vX.Y.Z) - pas le commit qu'on
    // regarde, puisque chaque édition, étiquette ou preuve en crée un ; ni le tout début de la filiation.
    if (timeline.items.length) {
      const latest = current || timeline.items[timeline.items.length - 1];
      const started = timeline.items.find((item) => item.version === latest.version).created_at;
      const updated = latest.created_at;
      document.getElementById("hero-dates").innerHTML =
        `Débutée le&nbsp;: <span class="meta-value">${formatDate(started)}</span>` +
        (formatDate(updated) !== formatDate(started) ? ` &middot; modifiée le&nbsp;: <span class="meta-value">${formatDate(updated)}</span>` : "");
    }
    renderStructure(currentDetail, diff);
    populateCompareMicroprojectSelect();
  } catch (err) {
    showError(err);
  }
}

init();
