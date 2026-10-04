/* La fiche d'une expérience : l'amorce, le contexte partagé, les onglets et le registre des panneaux.

   L'adresse désigne la piste (/microprojets/{slug}/experiences/{experiment_id}) : la fiche montre sa
   dernière version, ou une version passée avec ?version=, en lecture seule. Tout ce qui s'affiche est
   un panneau, enregistré par ExperiencePage.registerPanel({key, mount(el, ctx)}) et monté dans
   l'élément [data-panel="<key>"] de la page (un panneau sans élément sur la page est ignoré) : ceux
   de la fiche (header.js, objectives.js...), puis ceux des autres plugins (preuves, galerie, lots,
   cahier), dans l'ordre de chargement de leurs scripts.

   `mount` est rappelé, sur le même élément, à chaque rechargement de la fiche : il le remplit de
   nouveau. Il reçoit `ctx`, le même objet d'un rechargement à l'autre, dont les champs suivent la
   version affichée :
     microprojectSlug, experimentId   - la piste
     versionId, isTip                 - la version affichée ; isTip : la pointe, ouverte sans ?version=
     role, canEdit                    - le rôle dans le µprojet ; canEdit : éditeur sur la pointe
     detail                           - l'étude (GET .../experiments/{id}, ou la version demandée)
     microproject, versions, process  - le µprojet, la frise de la piste, le procédé éditable (ou null)
     variants()                       - la matrice d'une campagne (/variants), un appel par chargement
     reload()                         - relit la fiche sur place (même adresse, dernière version)
     showError(err, box?)             - un refus de l'API : 412 -> le bandeau « modifiée entre-temps »,
                                        sinon le message, dans `box` (une erreur près du formulaire)
                                        ou en tête de page
     write(call, box?)                - une écriture sur la piste : `call()` envoie ctx.versionId en
                                        If-Match ; réussie, la fiche se recharge ; refusée, showError
                                        (la saisie reste en place) ; renvoie true si elle est passée
     setDataCount(key, n)             - un panneau de l'onglet « Données » qui lit sa propre ressource
                                        y dit combien d'éléments il montre (le repère de l'onglet) */

const ExperiencePage = (() => {
  const { slug: microprojectSlug, experiment_id: experimentId } = routeParams("/microprojets/{slug}/experiences/{experiment_id}");
  let requestedVersion = new URLSearchParams(window.location.search).get("version");
  const panels = [];
  const errorBox = document.getElementById("error");
  const conflictBanner = document.getElementById("conflict-banner");

  function clearError() {
    errorBox.style.display = "none";
  }

  function showError(err, box = errorBox) {
    if (err && err.status === 412) {
      document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close()); // le bandeau doit se voir
      conflictBanner.hidden = false;
      conflictBanner.focus(); // annoncé (role="alert") et ramené dans la vue
      return;
    }
    box.textContent = (err && err.message) || String(err);
    box.style.display = "block";
    if (box === errorBox) box.scrollIntoView({ block: "nearest" }); // une action en bas de page : le refus en tête
  }

  let variantsPromise = null;
  function variants() {
    if (!variantsPromise) {
      variantsPromise = experimentsApi.variants(microprojectSlug, experimentId, ctx.versionId).catch((err) => {
        variantsPromise = null;
        throw err;
      });
    }
    return variantsPromise;
  }

  async function write(call, box) {
    clearError();
    try {
      await call();
    } catch (err) {
      showError(err, box);
      return false;
    }
    await reload();
    return true;
  }

  const ctx = {
    microprojectSlug,
    experimentId,
    versionId: null,
    isTip: false,
    role: null,
    canEdit: false,
    detail: null,
    microproject: null,
    versions: [],
    process: null,
    variants,
    reload,
    showError,
    write,
    setDataCount,
  };

  function registerPanel(panel) {
    panels.push(panel);
  }

  // --- adresses -----------------------------------------------------------------------------------

  // La page d'une version : sa piste, avec ?version= quand ce n'est pas la pointe.
  function pageUrl({ experiment_id, version_id, is_tip }) {
    const page = `/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experiment_id)}`;
    return is_tip ? page : `${page}?version=${encodeURIComponent(version_id)}`;
  }

  // L'éditeur de la fiche, prérempli : la page « structure en images » pour une structure donnée en
  // images, sinon le constructeur (`stage` : l'écran où l'ouvrir, « intention »). `fork` : partir de
  // la version affichée, sur une nouvelle piste (POST /experiments avec from_version).
  function evolveUrl({ stage = null, fork = false } = {}) {
    const mode = ctx.detail.structure_images ? "evoluer-image" : "evoluer";
    const query = new URLSearchParams();
    if (stage && mode === "evoluer") query.set("etape", stage);
    if (fork) query.set("version", ctx.versionId);
    const text = query.toString();
    return `/microprojets/${encodeURIComponent(microprojectSlug)}/experiences/${encodeURIComponent(experimentId)}/${mode}${text ? `?${text}` : ""}`;
  }

  // Les autres études d'un µprojet qui répondent à `q` (?q= : titre, intention, étiquettes, piste) -
  // un appel par recherche et par chargement, partagé par « Comparer » et « Combiner ».
  const othersCache = new Map();
  function otherExperiments(targetSlug, q = "") {
    const key = `${targetSlug}\n${q}`;
    if (!othersCache.has(key)) {
      othersCache.set(
        key,
        experimentsApi
          .list(targetSlug, { status: "all", q, limit: 100 })
          .then((data) => data.items.filter((item) => !(targetSlug === microprojectSlug && item.id === experimentId)))
          .catch((err) => {
            othersCache.delete(key);
            throw err;
          })
      );
    }
    return othersCache.get(key);
  }

  // --- onglets ------------------------------------------------------------------------------------

  // L'onglet ouvert est dans l'adresse (#structure / #donnees / #conclusion) et survit au rechargement.
  const TABS = ["structure", "donnees", "conclusion"];
  const tabList = document.querySelector(".fiche-tabs");

  function showTab(name, { focus = false } = {}) {
    const tab = TABS.includes(name) ? name : "structure";
    TABS.forEach((key) => {
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

  tabList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (button) showTab(button.dataset.tab);
  });
  tabList.addEventListener("keydown", (event) => {
    const current = TABS.indexOf(tabList.querySelector("[aria-selected='true']").dataset.tab);
    const next = { ArrowRight: (current + 1) % TABS.length, ArrowLeft: (current - 1 + TABS.length) % TABS.length, Home: 0, End: TABS.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    showTab(TABS[next], { focus: true });
  });
  window.addEventListener("hashchange", () => showTab(window.location.hash.slice(1)));

  // Repères sur les onglets : combien de données (le nombre de preuves du détail, plus ce que les
  // panneaux qui lisent leur propre ressource déclarent), et si l'étude est conclue.
  const dataCounts = new Map();
  function renderDataCount() {
    const count = (ctx.detail.evidence_count || 0) + [...dataCounts.values()].reduce((sum, n) => sum + n, 0);
    document.getElementById("tab-donnees-count").textContent = count ? String(count) : "";
  }

  function setDataCount(key, count) {
    dataCounts.set(key, count);
    renderDataCount();
  }

  function updateTabBadges(detail) {
    renderDataCount();
    const state = document.getElementById("tab-conclusion-state");
    const concluded = detail.status === "concluded" || detail.status === "abandoned";
    state.textContent = concluded ? "✓" : "à rédiger";
    state.classList.toggle("is-done", concluded);
    state.classList.toggle("is-open", !concluded);
    state.title = concluded ? "Étude conclue" : "Pas encore conclue";
  }

  function renderCrumbs(microproject) {
    const crumb = document.getElementById("microproject-crumb");
    crumb.textContent = microproject.code ? `${microproject.code} · ${microproject.name}` : microproject.name;
    crumb.href = `/microprojets/${encodeURIComponent(microprojectSlug)}`;
    const areaCrumb = document.getElementById("area-crumb");
    if (microproject.area) {
      areaCrumb.textContent = microproject.area.name;
      areaCrumb.href = `/management/${encodeURIComponent(microproject.area.slug)}`;
    } else {
      areaCrumb.textContent = "Non classé";
    }
    document.getElementById("thematic-crumb").textContent = microproject.thematic ? " / " + microproject.thematic.name : "";
  }

  // --- chargement ---------------------------------------------------------------------------------

  let loads = 0;
  async function load() {
    const seq = (loads += 1);
    const [detail, microproject] = await Promise.all([
      requestedVersion
        ? experimentsApi.getVersion(microprojectSlug, experimentId, requestedVersion)
        : experimentsApi.get(microprojectSlug, experimentId),
      ctx.microproject || microprojectsApi.get(microprojectSlug),
    ]);
    const [versions, process] = await Promise.all([
      experimentsApi.versions(microprojectSlug, experimentId),
      detail.has_editable_process ? experimentsApi.process(microprojectSlug, experimentId, detail.version_id).catch(() => null) : null,
    ]);
    if (seq !== loads) return; // un rechargement plus récent est en route
    if (requestedVersion && detail.is_tip) {
      // ?version= désigne la pointe (lien d'une ref, d'une version enfant...) : la fiche actuelle,
      // à son adresse de pointe, que les rechargements après écriture relisent
      requestedVersion = null;
      history.replaceState(null, "", `${window.location.pathname}${window.location.hash}`);
    }
    const isTip = detail.is_tip;
    Object.assign(ctx, {
      detail,
      microproject,
      versions,
      process,
      versionId: detail.version_id,
      isTip,
      role: microproject.role,
      canEdit: isTip && (microproject.role === "editor" || microproject.role === "owner"),
    });
    variantsPromise = null;
    othersCache.clear();
    conflictBanner.hidden = true;
    renderCrumbs(microproject);
    updateTabBadges(detail);
    await Promise.all(
      panels.map(async (panel) => {
        const el = document.querySelector(`[data-panel="${panel.key}"]`);
        if (!el) return;
        try {
          await panel.mount(el, ctx);
        } catch (err) {
          showError(err);
        }
      })
    );
  }

  function reload() {
    clearError();
    return load().catch((err) => showError(err));
  }

  document.getElementById("conflict-reload-btn").addEventListener("click", reload);

  // les scripts des panneaux sont tous chargés (et enregistrés) quand le document est prêt
  document.addEventListener("DOMContentLoaded", () => {
    showTab(window.location.hash.slice(1));
    reload();
  });

  return { registerPanel, showTab, pageUrl, evolveUrl, otherExperiments };
})();
