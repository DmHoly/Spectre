/* Le bandeau de la fiche, son super résumé à lire d'un coup d'œil : statut (et ses transitions,
   dont la mise en pause), version, qui et quand, le contexte, ce qu'on veut démontrer, le verdict des
   objectifs en badge, la conclusion en bref, les plaques suivies avec leurs FDL et le lien vers leurs
   données en base. Une version passée y est signalée, en lecture seule, avec de quoi en partir. */

(() => {
  let ctx = null;

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

  const isConcluded = (detail) => detail.status === "concluded" || detail.status === "abandoned";

  function objectiveVerdict(detail) {
    const results = detail.conclusion.objective_results || [];
    const statuses = (detail.objectives || []).map((o) => {
      const result = results.find((r) => r.objective === o.name);
      return result ? result.status : "pending";
    });
    const count = (status) => statuses.filter((st) => st === status).length;
    const n = statuses.length;
    const met = count("met");
    const pending = count("pending");
    let state;
    let label;
    if (!n) [state, label] = ["none", "Aucun objectif défini"];
    else if (pending === n) [state, label] = ["pending", isConcluded(detail) ? "Objectifs non évalués" : "En cours de vérification"];
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
      : ctx.canEdit
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
    if (!isConcluded(detail) || (!c.summary && !c.decision)) {
      box.style.display = "none";
      return;
    }
    box.style.display = "";
    box.innerHTML = `
      <div class="fiche-hero__label">Conclusion</div>
      ${c.decision ? `<div class="fiche-hero__decision">${escapeHtml(ExperimentVocabulary.decisions[c.decision] || c.decision)}</div>` : ""}
      ${c.summary ? `<p class="fiche-hero__summary">${escapeHtml(c.summary)}</p>` : ""}
      <button type="button" class="fiche-hero__more" data-report-hide>Lire la conclusion &rarr;</button>`;
    box.querySelector(".fiche-hero__more").addEventListener("click", () => {
      ExperiencePage.showTab("conclusion", { focus: true });
      document.querySelector(".fiche-tabs").scrollIntoView({ behavior: "smooth", block: "start" });
    });
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
    // « Données en base » (characterization/static/wafer-data-links.js) : les requêtes ouvertes sur ses plaques
    renderWaferDbLinks(document.querySelectorAll(".js-db-link"), lasermarks);
  }

  // Une version passée (lecture seule, avec de quoi en partir sur une nouvelle piste), une pause et
  // son motif, ou un brouillon continué par une version suivante.
  function renderStatusNote(detail) {
    const note = document.getElementById("status-note");
    note.className = "fiche-status-note";
    note.hidden = false;
    if (!ctx.isTip) {
      const current = ExperiencePage.pageUrl({ experiment_id: ctx.experimentId, is_tip: true });
      const editor = ctx.role === "editor" || ctx.role === "owner";
      note.classList.add("fiche-status-note--past");
      note.innerHTML = `<span>Version du ${escapeHtml(formatDate(detail.created_at))}, en lecture seule - <a href="${current}">voir la version actuelle</a></span>${
        editor
          ? `<a class="btn btn-line fiche-status-note__action" href="${ExperiencePage.evolveUrl({ fork: true })}" data-report-hide title="Ouvre l'éditeur sur cette version : enregistrer crée une nouvelle piste qui en part">Partir de cette version</a>`
          : ""
      }`;
    } else if (detail.status === "hold" && detail.hold) {
      const since = detail.hold.since;
      note.classList.add("fiche-status-note--hold");
      note.innerHTML = `<span>En pause depuis le ${escapeHtml(formatDate(since))} (${escapeHtml(formatDuration(new Date() - new Date(since)))})${detail.hold.by ? ` · par ${escapeHtml(detail.hold.by)}` : ""}</span>${
        detail.hold.reason ? `<span class="fiche-status-note__reason">${escapeHtml(detail.hold.reason)}</span>` : ""
      }`;
    } else if (detail.status === "continued" && detail.continued_at) {
      note.innerHTML = `<span>Brouillon continué par une version suivante le ${escapeHtml(formatDate(detail.continued_at))} - <a href="/microprojets/${encodeURIComponent(ctx.microprojectSlug)}">voir la suite dans le graphe</a></span>`;
    } else {
      note.hidden = true;
      note.innerHTML = "";
    }
  }

  // Transitions de statut (PUT .../status) : une étude lancée est « brouillon » ; elle passe « en
  // cours », peut être mise « en pause » (avec un motif) puis reprise ; une étude conclue peut être
  // rouverte pour revoir sa conclusion. « Continuée » se déduit du graphe : rien à faire pour l'obtenir.
  function renderStatusActions(detail) {
    const host = document.getElementById("status-actions");
    host.innerHTML = "";
    if (!ctx.canEdit) return;
    const addBtn = (label, targetStatus, cls) => {
      const b = document.createElement("button");
      b.type = "button";
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

  const holdDialog = document.getElementById("hold-dialog");
  const holdReason = document.getElementById("hold-reason");

  // Le motif d'une mise en pause : null si la personne annule (bouton, Échap).
  let settleHold = null;
  function askHoldReason() {
    holdReason.value = "";
    holdDialog.showModal();
    holdReason.focus();
    return new Promise((resolve) => {
      settleHold = (value) => {
        settleHold = null;
        if (holdDialog.open) holdDialog.close();
        resolve(value);
      };
    });
  }
  document.getElementById("hold-form").addEventListener("submit", (event) => {
    event.preventDefault();
    settleHold?.(holdReason.value.trim());
  });
  document.getElementById("hold-cancel").addEventListener("click", () => settleHold?.(null));
  holdDialog.addEventListener("close", () => settleHold?.(null));

  async function changeStatus(targetStatus, btn) {
    const body = { status: targetStatus };
    if (targetStatus === "hold") {
      const reason = await askHoldReason();
      if (reason === null) return;
      body.hold_reason = reason || null;
    }
    btn.disabled = true;
    const done = await ctx.write(() => experimentsApi.setStatus(ctx.microprojectSlug, ctx.experimentId, ctx.versionId, body));
    if (!done) btn.disabled = false;
  }

  // le contexte : une description sommaire qui remet l'expérience dans son histoire
  function renderContext(detail) {
    const context = document.getElementById("hero-context");
    context.classList.toggle("is-empty", !detail.context);
    if (detail.context) {
      context.textContent = detail.context;
      context.style.display = "";
    } else if (ctx.canEdit) {
      context.innerHTML = `<button type="button" class="fiche-hero__add" data-report-hide>+ Ajouter un contexte : d'où part cette expérience, pourquoi maintenant</button>`;
      context.querySelector("button").addEventListener("click", goToIntention);
      context.style.display = "";
    } else {
      context.style.display = "none";
    }
  }

  // v1.2.0, « Débutée le » et « modifiée le » : le début de la version de structure affichée - pas le
  // commit qu'on regarde (chaque étiquette ou preuve en crée un), ni le tout début de la filiation.
  function renderMeta(detail) {
    const history = ctx.versions;
    const current = history.find((item) => item.version_id === detail.version_id);
    document.getElementById("hero-version").textContent = current ? `v${current.version}` : "";
    let dates = `Débutée le&nbsp;: <span class="meta-value">${formatDate(detail.created_at)}</span>`;
    if (current) {
      const started = history.find((item) => item.version === current.version).created_at;
      dates = `Débutée le&nbsp;: <span class="meta-value">${formatDate(started)}</span>`;
      if (formatDate(current.created_at) !== formatDate(started)) dates += ` &middot; modifiée le&nbsp;: <span class="meta-value">${formatDate(current.created_at)}</span>`;
    }
    const microproject = ctx.microproject;
    document.getElementById("exp-meta").innerHTML = [
      `<span>${escapeHtml(microproject.name)}</span>`,
      `<span>Responsable&nbsp;: <span class="meta-value">${escapeHtml(detail.author || "inconnu")}</span></span>`,
      `<span>${dates}</span>`,
    ].join('<span class="fiche-hero__dot" aria-hidden="true">·</span>');
  }

  function goToIntention() {
    window.location.href = ExperiencePage.evolveUrl({ stage: "intention" });
  }
  const evolveBtn = document.getElementById("evolve-btn");
  evolveBtn.addEventListener("click", goToIntention);

  ExperiencePage.registerPanel({
    key: "header",
    mount(el, context) {
      ctx = context;
      const { detail, microproject } = ctx;
      document.getElementById("status-badge").innerHTML = statusBadgeHtml(detail.status, detail.conclusion.decision);
      renderStatusActions(detail);
      renderStatusNote(detail);
      document.getElementById("hero-code").innerHTML = microproject.code
        ? `<a class="fiche-code" href="/microprojets/${encodeURIComponent(ctx.microprojectSlug)}" title="µprojet ${escapeHtml(microproject.name)}">${escapeHtml(microproject.code)}</a>`
        : "";
      document.getElementById("exp-title").textContent = detail.title;
      document.getElementById("exp-intent").textContent = detail.intent;
      const hypothesis = document.getElementById("exp-hypothesis");
      hypothesis.style.display = detail.hypothesis ? "" : "none";
      hypothesis.innerHTML = detail.hypothesis ? `<strong>Hypothèse</strong> : ${escapeHtml(detail.hypothesis)}` : "";
      renderMeta(detail);
      renderContext(detail);
      document.getElementById("crumb").textContent = "/ " + (microproject.code ? `${microproject.code} / ` : "") + detail.title;
      document.title = `${detail.title} — Spectre`;
      evolveBtn.style.display = ctx.canEdit ? "" : "none";
      renderHeroPlates(detail);
      renderVerdict(detail);
      renderHeroConclusion(detail);
    },
  });
})();
