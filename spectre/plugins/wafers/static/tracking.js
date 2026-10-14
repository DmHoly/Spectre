/* La vie d'une plaque en ligne, sur sa page (wafer.html) : ce que la MES, Gozer et JIRA en disent,
   via wafersApi.tracking / refreshTracking (GET et POST /api/wafers/{key}/tracking[/refresh]) - son
   statut et son étape courante, son lot, son épitaxie, ses FDL et leur avancement, ses tests, son
   parcours MES étape par étape et sa fiche Gozer. Un bandeau de fraîcheur dit de quand datent les
   données (vert : moins de 24 h ; ambre : moins de 7 j ; rouge : au-delà), si la plaque est
   immobile (plus de 30 j sans mouvement : plus de relecture automatique) et laisse rafraîchir. */

const TRACKING_STATUS = {
  "en cours": { cls: "badge-running", label: "En cours" },
  "en attente": { cls: "badge-hold", label: "En attente" },
  clos: { cls: "badge-concluded", label: "Clos" },
  introuvable: { cls: "badge-draft", label: "Introuvable en MES" },
};

const FRESHNESS_LABELS = { fresh: "à jour", aging: "de plus d'un jour", stale: "de plus d'une semaine" };

// 'YYYY-MM-DD HH:MM' (heure de la base) -> « 14 oct. 2026, 09:12 » ; sinon le texte tel quel
function trackingDate(value) {
  if (!value) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})(?: (\d{2}):(\d{2}))?/.exec(value);
  if (!match) return escapeHtml(value);
  const date = new Date(+match[1], +match[2] - 1, +match[3], +(match[4] || 0), +(match[5] || 0));
  const day = date.toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });
  return match[4] ? `${day}, ${match[4]}:${match[5]}` : day;
}

function trackingHours(hours) {
  if (hours === null || hours === undefined) return "";
  return formatDuration(hours * 3600 * 1000);
}

function trackingBadge(status) {
  const info = TRACKING_STATUS[status] || TRACKING_STATUS.introuvable;
  return `<span class="badge ${info.cls}"><span class="dot"></span>${info.label}</span>`;
}

function kvHtml(pairs) {
  const rows = pairs.filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!rows.length) return `<p class="help" style="margin:0;">—</p>`;
  return `<dl class="plate-kv">${rows.map(([key, value, raw]) => `<dt>${escapeHtml(key)}</dt><dd>${raw ? value : escapeHtml(String(value))}</dd>`).join("")}</dl>`;
}

function freshnessHtml(meta) {
  const fetched = new Date(meta.fetched_at);
  const when = fetched.toLocaleString("fr-FR", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  const level = meta.dormant ? "dormant" : meta.freshness;
  const rule = meta.dormant
    ? `Plaque immobile depuis plus de ${meta.rules.dormant_days} jours : plus de relecture automatique, le bouton relit quand même.`
    : `Relues d'elles-mêmes au plus toutes les ${meta.rules.auto_refresh_hours} h.`;
  const text = meta.dormant ? "plaque immobile" : FRESHNESS_LABELS[meta.freshness] || meta.freshness;
  return `<span class="plate-fresh plate-fresh--${level}" title="${escapeHtml(rule)}"><span class="plate-fresh__dot" aria-hidden="true"></span>Données du ${escapeHtml(when)} · ${escapeHtml(timeAgo(meta.fetched_at))} · ${escapeHtml(text)}</span>`;
}

function fdlBarHtml(flow) {
  if (!flow || !flow.steps.length) return "";
  const segments = flow.steps
    .map((s) => {
      const title = `${s.stage || s.key} · ${s.status || "?"}${s.assignee ? ` · ${s.assignee}` : ""}${s.closed ? ` · clos le ${trackingDate(s.closed)}` : s.estimated ? ` · prévu le ${trackingDate(s.estimated)}` : ""}`;
      return `<span class="plate-fdl-bar__step plate-fdl-bar__step--${s.category}${s.late ? " is-late" : ""}" title="${escapeHtml(title)}"></span>`;
    })
    .join("");
  const now = flow.running.length ? `En cours : ${escapeHtml(flow.running.join(", "))}` : flow.next.length ? `Prochaine : ${escapeHtml(flow.next.join(", "))}` : flow.pct === 100 ? "Toutes les étapes faites" : "";
  return `
    <div class="plate-fdl-bar" role="img" aria-label="${flow.n_done} étapes faites sur ${flow.n - flow.n_skipped}">${segments}</div>
    <div class="plate-fdl-bar__meta"><strong>${flow.pct === null ? "—" : `${flow.pct} %`}</strong> · ${flow.n_done}/${flow.n - flow.n_skipped} étapes${flow.n_hold ? ` · ${flow.n_hold} en pause` : ""}${flow.n_late ? ` · <span class="plate-late">${flow.n_late} en retard</span>` : ""}${now ? ` · ${now}` : ""}</div>`;
}

function ticketHtml(ticket, flow) {
  return `
    <li class="plate-ticket">
      <div class="plate-ticket__head">
        ${fdlChipsHtml([ticket.request], { label: false })}
        <span class="plate-tag ${ticket.state === "clos" ? "plate-tag--done" : "plate-tag--open"}">${ticket.state === "clos" ? "close" : "ouverte"}</span>
        ${ticket.via === "lot" ? `<span class="plate-tag plate-tag--mute" title="Ticket posé sur le lot entier, pas sur cette plaque">via le lot</span>` : ""}
        ${ticket.task_code ? `<span class="mono plate-ticket__code">${escapeHtml(ticket.task_code)}</span>` : ""}
        ${ticket.jira_key ? `<span class="mono plate-ticket__code">${escapeHtml(ticket.jira_key)}</span>` : ""}
      </div>
      ${ticket.objective ? `<div class="plate-ticket__objective">${escapeHtml(ticket.objective)}</div>` : ""}
      <div class="plate-ticket__meta">${[
        ticket.requester ? `par ${escapeHtml(ticket.requester)}` : "",
        ticket.created ? `créée le ${trackingDate(ticket.created)}` : "",
        ticket.closed ? `close le ${trackingDate(ticket.closed)}` : "",
        ticket.labels ? escapeHtml(ticket.labels) : "",
      ].filter(Boolean).join(" · ")}</div>
      ${fdlBarHtml(flow)}
    </li>`;
}

function testHtml(test) {
  return `
    <li class="plate-test">
      <div class="plate-test__head">
        <strong class="mono">${escapeHtml(test.type || "Test")}</strong>
        <span>${trackingDate(test.date)}</span>
        ${test.request ? fdlChipsHtml([test.request], { label: false }) : ""}
        ${test.report ? `<a href="${escapeHtml(test.report)}" target="_blank" rel="noopener">rapport</a>` : ""}
      </div>
      <div class="plate-test__meta">${[test.operator, test.sensor, test.prober, test.temperature, test.description].filter(Boolean).map(escapeHtml).join(" · ")}</div>
    </li>`;
}

/* Le parcours MES, à trois niveaux, qu'on déplie à la demande : la route (PT2_BW_W3S2) ›
   l'étape (SAG_SIN_STRIP, la partie du nom MES avant le point) › ses actions (WET_EKC, BS_CLEAN :
   une ligne MES chacune, avec équipement, recette, dates). Les lignes MES consécutives d'une même
   étape sont regroupées. Une recherche filtre les actions (nom, équipement, recette, porteur,
   lot) et déplie ce qui correspond. */

function stepLabel(name) {
  const text = name || "?";
  const dot = text.indexOf(".");
  return dot > 0 ? { step: text.slice(0, dot), action: text.slice(dot + 1) } : { step: text, action: text };
}

function actionText(s) {
  return [s.step, s.equipment, s.recipe, s.carrier, s.lot, s.lot_out, s.route].filter(Boolean).join(" ").toLowerCase();
}

// [{route, version, steps: [{name, actions: [row…]}]}] - l'ordre des lignes MES
function groupSteps(rows) {
  const routes = [];
  rows.forEach((s) => {
    const { step } = stepLabel(s.step);
    let route = routes[routes.length - 1];
    if (!route || route.route !== s.route || route.version !== s.route_version) {
      route = { route: s.route, version: s.route_version, steps: [] };
      routes.push(route);
    }
    let last = route.steps[route.steps.length - 1];
    if (!last || last.name !== step) {
      last = { name: step, actions: [] };
      route.steps.push(last);
    }
    last.actions.push(s);
  });
  return routes;
}

function actionHtml(s) {
  const open = s.start && !s.end_effective;
  const duration = s.start && s.end_effective ? formatDuration(new Date(s.end_effective.replace(" ", "T")) - new Date(s.start.replace(" ", "T"))) : "";
  return `
    <li class="plate-action${open ? " is-running" : ""}${s.cycle > 1 ? " is-rework" : ""}">
      <span class="plate-action__dot" aria-hidden="true"></span>
      <div class="plate-action__title"><span class="mono">${escapeHtml(stepLabel(s.step).action)}</span>${s.cycle > 1 ? ` <span class="plate-tag plate-tag--warn">reprise ${s.cycle}</span>` : ""}${s.unclosed ? ` <span class="plate-tag plate-tag--mute" title="Jamais clôturée dans la MES, mais suivie d'une autre action">non clôturée</span>` : ""}${open ? ` <span class="plate-tag plate-tag--run">en cours</span>` : ""}</div>
      <div class="plate-action__meta">${[s.equipment, s.recipe, s.carrier ? `porteur ${s.carrier}` : ""].filter(Boolean).map(escapeHtml).join(" · ")}</div>
      <div class="plate-action__time">${trackingDate(s.start)}${s.end_effective ? ` → ${trackingDate(s.end_effective)}` : ""}${duration ? ` · ${duration}` : ""}${s.lot_out && s.lot_out !== s.lot ? ` · lot → ${escapeHtml(s.lot_out)}` : ""}</div>
    </li>`;
}

function stepHtml(step, open) {
  const actions = step.actions;
  const running = actions.some((a) => a.start && !a.end_effective);
  const reworks = actions.filter((a) => a.cycle > 1).length;
  const first = actions[0].start;
  const lastRow = actions[actions.length - 1];
  const last = lastRow.end_effective || lastRow.start;
  const equipments = [...new Set(actions.map((a) => a.equipment).filter(Boolean))];
  const names = [...new Set(actions.map((a) => stepLabel(a.step).action))];
  return `
    <li class="plate-mstep${running ? " is-running" : ""}">
      <details class="plate-mstep__details" ${open ? "open" : ""}>
        <summary class="plate-mstep__summary">
          <span class="plate-mstep__dot" aria-hidden="true"></span>
          <span class="plate-mstep__name mono">${escapeHtml(step.name)}</span>
          <span class="plate-mstep__count">${actions.length} action${actions.length > 1 ? "s" : ""}${names.length > 1 || names[0] !== step.name ? ` · ${escapeHtml(names.slice(0, 3).join(", "))}${names.length > 3 ? "…" : ""}` : ""}</span>
          ${running ? `<span class="plate-tag plate-tag--run">en cours</span>` : ""}${reworks ? ` <span class="plate-tag plate-tag--warn">${reworks} reprise${reworks > 1 ? "s" : ""}</span>` : ""}
          <span class="plate-mstep__when">${trackingDate(first)}${last && last !== first ? ` → ${trackingDate(last)}` : ""}${equipments.length ? ` · ${escapeHtml(equipments.slice(0, 2).join(", "))}${equipments.length > 2 ? "…" : ""}` : ""}</span>
        </summary>
        <ol class="plate-actions">${actions.map(actionHtml).join("")}</ol>
      </details>
    </li>`;
}

function routesHtml(rows, query) {
  const q = (query || "").trim().toLowerCase();
  const routes = groupSteps(q ? rows.filter((s) => actionText(s).includes(q)) : rows);
  if (!routes.length) return `<p class="help" style="margin:8px 0 0;">${q ? "Aucune action ne correspond." : "Aucune étape MES."}</p>`;
  return routes
    .map((route, index) => {
      const all = route.steps.flatMap((s) => s.actions);
      const running = all.some((a) => a.start && !a.end_effective);
      const first = all[0].start;
      const lastRow = all[all.length - 1];
      const last = lastRow.end_effective || lastRow.start;
      const open = q || index === routes.length - 1;
      return `
        <details class="plate-route${running ? " is-running" : ""}" ${open ? "open" : ""}>
          <summary><strong class="mono">${escapeHtml(route.route || "?")}</strong>${route.version ? ` <span class="help" style="display:inline;margin:0;">v${escapeHtml(route.version)}</span>` : ""}<em>${route.steps.length} étape${route.steps.length > 1 ? "s" : ""} · ${all.length} action${all.length > 1 ? "s" : ""} · ${trackingDate(first)}${last ? ` → ${trackingDate(last)}` : ""}</em></summary>
          <ol class="plate-msteps">${route.steps.map((s) => stepHtml(s, Boolean(q) || (running && s.actions.some((a) => a.start && !a.end_effective)))).join("")}</ol>
        </details>`;
    })
    .join("");
}

function stepsHtml(rows) {
  if (!rows.length) return `<p class="help" style="margin:0;">Aucune étape MES.</p>`;
  return `
    <div class="plate-journey__bar">
      <input type="search" class="plate-journey__search js-journey-search" placeholder="Chercher une action, un équipement, une recette, un lot…" aria-label="Chercher dans le parcours MES">
      <span class="help plate-journey__hint" style="margin:0;">Route › étape › actions - dépliez ce qu'il vous faut.</span>
    </div>
    <div class="js-journey-routes">${routesHtml(rows, "")}</div>`;
}

function bindJourneySearch(host, rows) {
  const input = host.querySelector(".js-journey-search");
  const target = host.querySelector(".js-journey-routes");
  if (!input || !target) return;
  let timer = null;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => (target.innerHTML = routesHtml(rows, input.value)), 120);
  });
}

function epitaxyHtml(runs) {
  if (!runs.length) return `<p class="help" style="margin:0;">Aucun run d'épitaxie connu.</p>`;
  return runs
    .map(
      (e) => `
      <div class="plate-epi">
        <div class="plate-epi__head"><strong class="mono">${escapeHtml(e.run || "run MES")}</strong>${e.running ? ` <span class="plate-tag plate-tag--run">en cours</span>` : ""}<span class="plate-tag plate-tag--mute" title="D'où vient cette ligne">${escapeHtml(e.source)}</span></div>
        ${kvHtml([
          ["Réacteur", e.reactor],
          ["Recette", [e.recipe_type, e.recipe_version ? `v${e.recipe_version}` : ""].filter(Boolean).join(" ")],
          ["Recette MES", e.mes_recipe && e.mes_recipe !== e.comments ? e.mes_recipe : null],
          ["Dates", e.start ? `${trackingDate(e.start)}${e.end ? ` → ${trackingDate(e.end)}` : ""}` : null],
          ["FDL", e.request ? fdlChipsHtml([e.request], { label: false }) : null, true],
          ["Tâche", e.task_code],
          ["Plateforme", e.platform],
          ["Commentaire", e.comments],
        ])}
      </div>`
    )
    .join("");
}

function bannersHtml(data) {
  const meta = data.meta;
  const failed = Object.entries(data.phases || {}).filter(([, p]) => !p.ok);
  const out = [];
  if (meta.error) out.push(`<div class="plate-banner plate-banner--bad">Dernière relecture en échec : ${escapeHtml(meta.error)} - données du ${escapeHtml(new Date(meta.fetched_at).toLocaleString("fr-FR"))} gardées.</div>`);
  if (failed.length) out.push(`<div class="plate-banner plate-banner--bad">Lecture incomplète : ${failed.map(([name, p]) => `${escapeHtml(name)} (${escapeHtml(p.error || "?")})`).join(" ; ")}.</div>`);
  if (meta.dormant) out.push(`<div class="plate-banner plate-banner--info">Plaque immobile depuis le ${trackingDate(meta.last_movement)} : plus de relecture automatique au-delà de ${meta.rules.dormant_days} jours sans mouvement - « Rafraîchir » relit les bases quand même.</div>`);
  return out.join("");
}

function trackingHtml(data) {
  const cur = data.current;
  const mes = kvHtml([
    ["Étape", cur ? cur.step : null],
    ["Équipement", cur ? cur.equipment : null],
    ["Recette", cur ? cur.recipe : null],
    [data.status === "en cours" ? "Depuis" : "Dernier mouvement", cur && cur.since ? `${trackingDate(cur.since)}${cur.idle_h && data.status === "en attente" ? ` · ${trackingHours(cur.idle_h)} d'attente` : ""}` : null],
    ["Clôture", data.closed_at ? `${trackingDate(data.closed_at)}${data.last_fdl ? ` (${data.last_fdl.request})` : ""}` : null],
    ["Lot MES", data.lots.length ? data.lots.map((l) => `<span class="mono">${escapeHtml(l)}</span>`).join(", ") : null, true],
    ["Produit", data.product],
    ["Route", data.route],
    ["Parcours", data.n_steps ? `${data.n_steps} étapes${data.n_rework ? `, ${data.n_rework} reprise${data.n_rework > 1 ? "s" : ""}` : ""}${data.n_unclosed ? `, ${data.n_unclosed} non clôturée${data.n_unclosed > 1 ? "s" : ""}` : ""} · ${trackingDate(data.first_start)} → ${trackingDate(data.last_seen)}${data.elapsed_h ? ` (${trackingHours(data.elapsed_h)})` : ""}` : null],
    ["Autres identifiants", data.aliases.length ? data.aliases.map((a) => `<span class="mono">${escapeHtml(a)}</span>`).join(", ") : null, true],
  ]);
  const lotName = data.lot_name
    ? `<span class="mono">${escapeHtml(data.lot_name)}</span>${data.lot_source ? ` <span class="plate-tag plate-tag--mute" title="D'où vient ce nom">${escapeHtml(data.lot_source)}</span>` : ""}${data.lot_alternatives.length ? ` <span class="help" style="display:inline;margin:0;">ou ${data.lot_alternatives.map(escapeHtml).join(", ")}</span>` : ""}`
    : null;
  const fdlCards = data.tickets.length
    ? `<ul class="plate-tickets">${data.tickets.map((t) => ticketHtml(t, data.fdls[t.request])).join("")}</ul>`
    : `<p class="help" style="margin:0;">Aucune FDL ne cite cette plaque ni son lot.</p>`;
  const tests = data.tests.length ? `<ul class="plate-tests">${data.tests.map(testHtml).join("")}</ul>` : `<p class="help" style="margin:0;">Aucun test enregistré.</p>`;
  const record = Object.entries(data.record);
  return `
    ${bannersHtml(data)}
    <div class="plate-life__grid">
      <section class="card plate-life__card">
        <h3 class="plate-life__title">Fabrication <span class="help" style="display:inline;margin:0;">MES</span> ${trackingBadge(data.status)}</h3>
        ${mes}
      </section>
      <section class="card plate-life__card">
        <h3 class="plate-life__title">Épitaxie <span class="help" style="display:inline;margin:0;">Gozer</span></h3>
        ${epitaxyHtml(data.epitaxy)}
        ${data.base_wafer_fdl.length || data.test_fdl.length ? kvHtml([["FDL base wafer", data.base_wafer_fdl.length ? fdlChipsHtml(data.base_wafer_fdl, { label: false }) : null, true], ["FDL test", data.test_fdl.length ? fdlChipsHtml(data.test_fdl, { label: false }) : null, true]]) : ""}
      </section>
      <section class="card plate-life__card plate-life__card--wide">
        <h3 class="plate-life__title">Lot et feuilles de lancement <span class="help" style="display:inline;margin:0;">JIRA</span></h3>
        ${lotName ? `<div class="plate-lot">Lot <strong>${lotName}</strong></div>` : ""}
        ${fdlCards}
      </section>
      <section class="card plate-life__card plate-life__card--wide">
        <h3 class="plate-life__title">Tests <span class="help" style="display:inline;margin:0;">${data.tests.length}</span></h3>
        ${tests}
      </section>
    </div>
    <details class="card plate-life__details js-journey" ${data.status === "en cours" ? "open" : ""}>
      <summary>Parcours MES <span class="help" style="display:inline;margin:0;">${groupSteps(data.steps).reduce((n, r) => n + r.steps.length, 0)} étapes · ${data.n_steps} action${data.n_steps > 1 ? "s" : ""}</span></summary>
      <div class="plate-life__details-body">${stepsHtml(data.steps)}</div>
    </details>
    <details class="card plate-life__details">
      <summary>Fiche wafer Gozer <span class="help" style="display:inline;margin:0;">${record.length} champ${record.length > 1 ? "s" : ""}</span></summary>
      <div class="plate-life__details-body">${record.length ? kvHtml(record) : `<p class="help" style="margin:0;">Aucune fiche wafer dans Gozer.</p>`}</div>
    </details>`;
}

// host : la section de la page ; waferKey : la plaque. Lit, affiche, et branche « Rafraîchir ».
async function initWaferTracking(host, waferKey) {
  const body = host.querySelector(".js-life-body");
  const fresh = host.querySelector(".js-life-fresh");
  const button = host.querySelector(".js-life-refresh");
  let busy = false;

  function show(data) {
    fresh.innerHTML = freshnessHtml(data.meta);
    body.innerHTML = trackingHtml(data);
    bindJourneySearch(body.querySelector(".js-journey"), data.steps);
  }

  async function load(refresh) {
    if (busy) return;
    busy = true;
    button.disabled = true;
    button.classList.add("is-busy");
    if (!refresh) body.innerHTML = `<p class="help plate-life__loading">Lecture des bases de la ligne…</p>`;
    try {
      show(refresh ? await wafersApi.refreshTracking(waferKey) : await wafersApi.tracking(waferKey));
    } catch (err) {
      fresh.innerHTML = "";
      body.innerHTML = `<div class="plate-banner plate-banner--bad">${escapeHtml(err.message || String(err))}</div>`;
    } finally {
      busy = false;
      button.disabled = false;
      button.classList.remove("is-busy");
    }
  }

  button.addEventListener("click", () => load(true));
  await load(false);
}
