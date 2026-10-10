/* Paramètres > Utilisation : le tableau de bord de l'usage de Spectre (usageApi.report). Les filtres
   (période, regroupement, équipe, module, administrateurs) sont tous en haut et gardés dans
   l'adresse de la page, qui se partage ; le serveur calcule tout, la page ne fait que montrer :
   tuiles de la période (comparées à la période d'avant, de même durée), utilisateurs actifs,
   carte de chaleur, activité empilée des modules, tableaux des modules, des comptes et des
   fonctionnalités. Un compte s'ouvre dans un panneau : le même rapport, filtré sur lui. */

(function () {
  // L'ordre fixe des teintes des modules (validé daltonisme, adjacent) ; « Autres » en gris.
  const SERIES = ["var(--usage-series-1)", "var(--usage-series-2)", "var(--usage-series-3)", "var(--usage-series-4)",
    "var(--usage-series-5)", "var(--usage-series-6)", "var(--usage-series-7)"];
  const OTHER = "var(--usage-series-other)";
  const ACTIVE = "var(--usage-series-1)";
  const FREQUENCIES = {
    daily: { label: "Assidu", hint: "3 jours actifs par semaine ou plus", badge: "badge-concluded" },
    weekly: { label: "Régulier", hint: "1 à 3 jours actifs par semaine", badge: "badge-running" },
    occasional: { label: "Occasionnel", hint: "moins d'un jour actif par semaine", badge: "badge-hold" },
    inactive: { label: "Inactif", hint: "aucune activité sur la période", badge: "badge-draft" },
  };
  const PRESET_GRANULARITY = { 7: "day", 30: "day", 90: "week", 365: "month" };
  const fmt = UsageCharts.formatNumber;

  const errorBox = document.getElementById("error");
  const state = {
    period: "30",
    start: "",
    end: "",
    granularity: "day",
    team: "",
    plugin: "",
    includeAdmins: true,
    metric: "page_views",
    routes: "page",
    userQuery: "",
    report: null,
  };
  let pluginOptionsFilled = false;
  let resizeTimer = null;

  // -- dates ------------------------------------------------------------------------------

  function isoDay(date) {
    const pad = (n) => String(n).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }
  function presetRange(days) {
    const end = new Date();
    const start = new Date(end);
    start.setDate(end.getDate() - (Number(days) - 1));
    return { start: isoDay(start), end: isoDay(end) };
  }
  function shortDate(iso) {
    return iso ? UsageCharts.bucketLabel(iso, "day") + " " + iso.slice(0, 4) : "-";
  }
  function relativeDay(iso) {
    if (!iso) return "jamais";
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const [y, m, d] = iso.split("-").map(Number);
    const days = Math.round((today - new Date(y, m - 1, d)) / 86400000);
    if (days <= 0) return "aujourd'hui";
    if (days === 1) return "hier";
    if (days < 31) return `il y a ${days} j`;
    return shortDate(iso);
  }

  // -- adresse de la page <-> filtres --------------------------------------------------------

  function readUrl() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("periode")) state.period = params.get("periode");
    state.start = params.get("du") || "";
    state.end = params.get("au") || "";
    if (state.period === "custom" && !(state.start && state.end)) state.period = "30";
    state.granularity = params.get("par") || PRESET_GRANULARITY[state.period] || "day";
    state.team = params.get("equipe") || "";
    state.plugin = params.get("module") || "";
    state.includeAdmins = params.get("admins") !== "0";
  }
  function writeUrl() {
    const params = new URLSearchParams();
    if (state.period !== "30") params.set("periode", state.period);
    if (state.period === "custom") {
      params.set("du", state.start);
      params.set("au", state.end);
    }
    if (state.granularity !== (PRESET_GRANULARITY[state.period] || "day")) params.set("par", state.granularity);
    if (state.team) params.set("equipe", state.team);
    if (state.plugin) params.set("module", state.plugin);
    if (!state.includeAdmins) params.set("admins", "0");
    const query = params.toString();
    history.replaceState(null, "", window.location.pathname + (query ? `?${query}` : ""));
  }

  function range() {
    return state.period === "custom" ? { start: state.start, end: state.end } : presetRange(state.period);
  }
  function query(extra = {}) {
    const { start, end } = range();
    return {
      start, end, granularity: state.granularity, team: state.team || null, plugin: state.plugin || null,
      include_admins: state.includeAdmins ? null : false, ...extra,
    };
  }

  function syncControls() {
    pressed("[data-period]", (b) => b.dataset.period === state.period);
    pressed("[data-granularity]", (b) => b.dataset.granularity === state.granularity);
    pressed("[data-metric]", (b) => b.dataset.metric === state.metric);
    pressed("[data-routes]", (b) => b.dataset.routes === state.routes);
    const custom = state.period === "custom";
    document.getElementById("custom-dates").hidden = !custom;
    const { start, end } = range();
    document.getElementById("start").value = start;
    document.getElementById("end").value = end;
    document.getElementById("team").value = state.team;
    document.getElementById("plugin").value = state.plugin;
    document.getElementById("include-admins").checked = state.includeAdmins;
  }
  function pressed(selector, isOn) {
    document.querySelectorAll(selector).forEach((button) => {
      const on = isOn(button);
      button.classList.toggle("active", on);
      button.setAttribute("aria-pressed", String(on));
    });
  }

  // -- chargement ---------------------------------------------------------------------------

  let loadSeq = 0;
  async function load() {
    const seq = ++loadSeq;
    errorBox.style.display = "none";
    document.getElementById("kpis").setAttribute("aria-busy", "true");
    writeUrl();
    try {
      const report = await usageApi.report(query());
      if (seq !== loadSeq) return;
      state.report = report;
      fillPluginOptions(report);
      render();
    } catch (err) {
      if (seq !== loadSeq) return;
      if (err.status === 403) {
        document.getElementById("content").hidden = true;
        document.getElementById("denied").hidden = false;
        return;
      }
      errorBox.textContent = err.message || String(err);
      errorBox.style.display = "";
    } finally {
      document.getElementById("kpis").setAttribute("aria-busy", "false");
    }
  }

  function fillPluginOptions(report) {
    if (pluginOptionsFilled) return;
    const select = document.getElementById("plugin");
    const sorted = report.catalog.slice().sort((a, b) => a.title.localeCompare(b.title, "fr"));
    select.innerHTML = `<option value="">Tous les modules</option>` +
      sorted.map((p) => `<option value="${escapeHtml(p.name)}">${escapeHtml(p.title)}</option>`).join("");
    select.value = state.plugin;
    pluginOptionsFilled = true;
  }

  async function loadTeams() {
    if (typeof teamsApi === "undefined") return;
    try {
      const teams = await teamsApi.list();
      const select = document.getElementById("team");
      select.insertAdjacentHTML("beforeend", teams.map((t) => `<option value="${escapeHtml(t.slug)}">${escapeHtml(t.name)}</option>`).join(""));
      select.value = state.team;
    } catch (_err) {
      /* sans équipes : le filtre reste « Toutes les équipes » */
    }
  }

  // -- rendu ----------------------------------------------------------------------------------

  function render() {
    const report = state.report;
    if (!report) return;
    const since = document.getElementById("tracking-since");
    since.textContent = report.tracking_since
      ? `Mesuré depuis le ${shortDate(report.tracking_since)}.`
      : "Aucune activité mesurée pour l'instant : les compteurs se remplissent au fil des visites.";
    renderKpis(report);
    renderActive(report);
    renderHeatmap(report);
    renderModulesChart(report);
    renderModulesTable(report);
    renderUsers(report);
    renderRoutes(report);
  }

  function delta(current, previous, { percent = false } = {}) {
    if (previous === null || previous === undefined) return "";
    const diff = current - previous;
    if (!previous && !current) return `<span class="usage-delta">= période précédente</span>`;
    let text;
    if (percent) text = `${diff >= 0 ? "+" : "−"}${Math.abs(Math.round(diff * 100))} pt`;
    else if (!previous) text = "nouveau";
    else text = `${diff >= 0 ? "+" : "−"}${Math.abs(Math.round((diff / previous) * 100))} %`;
    const dir = diff > 0 ? "up" : diff < 0 ? "down" : "flat";
    const arrow = { up: "↑", down: "↓", flat: "=" }[dir];
    return `<span class="usage-delta usage-delta--${dir}"><span aria-hidden="true">${arrow}</span> ${text}<span class="visually-hidden"> par rapport à la période précédente</span></span>`;
  }

  function tile(value, label, sub, deltaHtml, title = "") {
    return `<div class="card usage-kpi"${title ? ` title="${escapeHtml(title)}"` : ""}>
      <div class="kpi__value">${value}</div>
      <div class="kpi__label">${escapeHtml(label)}</div>
      <div class="usage-kpi__foot">${sub ? `<span>${sub}</span>` : ""}${deltaHtml}</div>
    </div>`;
  }

  function renderKpis(report) {
    const t = report.totals;
    const p = report.previous;
    const pct = (v) => `${Math.round(v * 100)} %`;
    document.getElementById("kpis").innerHTML = [
      tile(fmt(t.active_users), "Utilisateurs actifs", `sur ${fmt(t.registered_users)} comptes`, delta(t.active_users, p.active_users),
        "Comptes qui ont fait au moins une requête sur la période"),
      tile(pct(t.adoption_rate), "Taux d'adoption", t.new_users ? `${fmt(t.new_users)} nouveau${t.new_users > 1 ? "x" : ""} compte${t.new_users > 1 ? "s" : ""}` : "",
        delta(t.adoption_rate, p.adoption_rate, { percent: true }), "Comptes actifs / comptes inscrits à la fin de la période"),
      tile(String(t.avg_daily_active).replace(".", ","), "Actifs par jour ouvré", `pic : ${fmt(t.peak_daily_active)}`, delta(t.avg_daily_active, p.avg_daily_active),
        "Moyenne des comptes actifs chaque jour du lundi au vendredi"),
      tile(fmt(t.page_views), "Pages vues", "", delta(t.page_views, p.page_views)),
      tile(fmt(t.writes), "Écritures", `${fmt(t.reads)} lectures`, delta(t.writes, p.writes),
        "Créations, modifications et suppressions (toute requête de l'API autre qu'une lecture)"),
      tile(`${fmt(t.plugins_used)}<span class="usage-kpi__of"> / ${fmt(t.plugins_total)}</span>`, "Modules utilisés",
        t.server_errors ? `<span class="usage-errors">${fmt(t.server_errors)} erreur${t.server_errors > 1 ? "s" : ""} serveur</span>` : "", ""),
    ].join("");
  }

  function renderActive(report) {
    const { series, period } = report;
    document.getElementById("active-sub").textContent =
      `Comptes distincts par ${{ day: "jour", week: "semaine", month: "mois" }[period.granularity]}`;
    UsageCharts.columns(document.getElementById("active-chart"), {
      buckets: series.map((s) => s.bucket),
      granularity: period.granularity,
      series: [{ label: "Utilisateurs actifs", color: ACTIVE, values: series.map((s) => s.active_users) }],
      ariaLabel: "Utilisateurs actifs par période",
    });
    document.getElementById("active-table").innerHTML = `<table class="usage-table usage-table--compact">
      <thead><tr><th scope="col">Période</th><th scope="col" class="num">Actifs</th><th scope="col" class="num">Pages vues</th><th scope="col" class="num">Lectures</th><th scope="col" class="num">Écritures</th></tr></thead>
      <tbody>${series.map((s) => `<tr><td>${escapeHtml(UsageCharts.bucketLabel(s.bucket, period.granularity, true))}</td>
        <td class="num">${fmt(s.active_users)}</td><td class="num">${fmt(s.page_views)}</td><td class="num">${fmt(s.reads)}</td><td class="num">${fmt(s.writes)}</td></tr>`).join("")}</tbody>
    </table>`;
  }

  function renderHeatmap(report) {
    const container = document.getElementById("heatmap");
    if (!report.heatmap.length) {
      container.innerHTML = `<p class="usage-empty">Aucune activité sur la période.</p>`;
      return;
    }
    const chart = document.createElement("div");
    container.innerHTML = "";
    container.appendChild(chart);
    UsageCharts.heatmap(chart, report.heatmap);
    container.insertAdjacentHTML("beforeend", UsageCharts.heatLegendHtml());
  }

  // Les 7 modules les plus actifs de la période (sur la mesure choisie), les autres regroupés ;
  // la couleur suit le module (son rang dans le tableau de la période), pas sa place dans la pile.
  function renderModulesChart(report) {
    const metric = state.metric;
    const buckets = report.series.map((s) => s.bucket);
    const index = new Map(buckets.map((b, i) => [b, i]));
    const totals = new Map();
    report.plugin_series.forEach((row) => totals.set(row.plugin, (totals.get(row.plugin) || 0) + row[metric]));
    const ranked = [...totals.entries()].filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([name]) => name);
    const top = ranked.slice(0, SERIES.length);
    const titles = new Map(report.plugins.map((p) => [p.name, p.title]));
    const series = top.map((name, i) => ({ name, label: titles.get(name) || name, color: SERIES[i], values: new Array(buckets.length).fill(0) }));
    const other = { name: "_other", label: "Autres", color: OTHER, values: new Array(buckets.length).fill(0) };
    report.plugin_series.forEach((row) => {
      const target = series.find((s) => s.name === row.plugin) || other;
      target.values[index.get(row.bucket)] += row[metric];
    });
    if (ranked.length > SERIES.length) series.push(other);

    const legend = document.getElementById("modules-legend");
    const chart = document.getElementById("modules-chart");
    if (!series.length) {
      legend.innerHTML = "";
      chart.innerHTML = `<p class="usage-empty">Rien à montrer pour cette mesure sur la période.</p>`;
      return;
    }
    legend.innerHTML = series.map((s) => `<span class="usage-legend__item"><span class="usage-legend__key" style="background:${s.color}"></span>${escapeHtml(s.label)}</span>`).join("");
    UsageCharts.columns(chart, {
      buckets, granularity: report.period.granularity, series, height: 260,
      ariaLabel: "Activité par module et par période",
    });
  }

  function trendHtml(plugin) {
    if (!plugin.previous_hits && !plugin.hits) return `<span class="usage-faint">-</span>`;
    return delta(plugin.hits, plugin.previous_hits);
  }

  function renderModulesTable(report) {
    const rows = report.plugins.map((p) => {
      const unused = !p.users;
      const status = !p.active
        ? `<span class="usage-tag">Désactivé</span>`
        : unused ? `<span class="usage-tag usage-tag--warn">${p.last_used ? "Pas sur la période" : "Jamais utilisé"}</span>` : "";
      return `<tr class="usage-row-link${unused ? " is-quiet" : ""}" data-plugin="${escapeHtml(p.name)}" tabindex="0" aria-label="Filtrer le rapport sur ${escapeHtml(p.title)}">
        <th scope="row"><span class="usage-module">${settingsIcon(p.icon, 16)}<span>${escapeHtml(p.title)}</span><span class="usage-module__name mono">${escapeHtml(p.name)}</span></span> ${status}</th>
        <td class="num">${fmt(p.users)}</td>
        <td class="usage-adoption">${UsageCharts.meterHtml(p.adoption_rate, `${Math.round(p.adoption_rate * 100)} % des actifs`)}<span class="mono">${Math.round(p.adoption_rate * 100)} %</span></td>
        <td class="num">${fmt(p.page_views)}</td>
        <td class="num">${fmt(p.reads)}</td>
        <td class="num">${fmt(p.writes)}</td>
        <td class="num">${trendHtml(p)}</td>
        <td class="usage-when">${escapeHtml(relativeDay(p.last_used))}</td>
      </tr>`;
    }).join("");
    document.getElementById("modules-table").innerHTML = `
      <thead><tr>
        <th scope="col">Module</th><th scope="col" class="num">Utilisateurs</th><th scope="col">Adoption</th>
        <th scope="col" class="num">Pages vues</th><th scope="col" class="num">Lectures</th><th scope="col" class="num">Écritures</th>
        <th scope="col" class="num" title="Requêtes, comparées à la période précédente">Tendance</th><th scope="col">Dernière utilisation</th>
      </tr></thead>
      <tbody>${rows}</tbody>`;
  }

  function teamsText(user) {
    return user.teams.length ? user.teams.join(", ") : "";
  }

  function userName(user) {
    return user.deleted ? `Compte supprimé n° ${user.id}` : user.name || user.email;
  }

  function frequencyBadge(key) {
    const f = FREQUENCIES[key];
    return `<span class="badge ${f.badge}" title="${escapeHtml(f.hint)}"><span class="dot"></span>${f.label}</span>`;
  }

  function renderUsers(report) {
    const users = report.users;
    const counts = { daily: 0, weekly: 0, occasional: 0, inactive: 0 };
    users.forEach((u) => { counts[u.frequency] += 1; });
    const total = users.length || 1;
    document.getElementById("frequency-bar").innerHTML = users.length
      ? `<div class="usage-split" role="img" aria-label="${Object.entries(counts).map(([k, v]) => `${FREQUENCIES[k].label} : ${v}`).join(", ")}">
          ${Object.entries(counts).filter(([, v]) => v).map(([k, v]) => `<span class="usage-split__part usage-split__part--${k}" style="flex:${v}" title="${FREQUENCIES[k].label} : ${v}"></span>`).join("")}
        </div>
        <div class="usage-split__legend">${Object.entries(counts).map(([k, v]) => `<span class="usage-legend__item"><span class="usage-legend__key usage-split__part--${k}"></span>${FREQUENCIES[k].label} <strong class="mono">${v}</strong> <span class="usage-faint">(${Math.round((v / total) * 100)} %)</span></span>`).join("")}</div>`
      : "";

    const q = state.userQuery.trim().toLowerCase();
    const titles = new Map(report.plugins.map((p) => [p.name, p.title]));
    const shown = users.filter((u) => !q || [u.name, u.email, ...u.teams].some((v) => (v || "").toLowerCase().includes(q)));
    const rows = shown.map((u) => `<tr class="usage-row-link${u.frequency === "inactive" ? " is-quiet" : ""}" data-user="${u.id}" tabindex="0" aria-label="Détail de ${escapeHtml(userName(u))}">
        <th scope="row"><span class="usage-person"><span class="avatar" aria-hidden="true">${escapeHtml(initials(userName(u)))}</span>
          <span><span class="usage-person__name">${escapeHtml(userName(u))}${u.is_admin ? ` <span class="usage-tag">admin</span>` : ""}</span>
          <span class="usage-person__meta">${escapeHtml([u.email, teamsText(u)].filter(Boolean).join(" · "))}</span></span></span></th>
        <td>${frequencyBadge(u.frequency)}</td>
        <td class="num">${fmt(u.active_days)}</td>
        <td class="num">${fmt(u.page_views)}</td>
        <td class="num">${fmt(u.writes)}</td>
        <td>${u.top_plugins.map((t) => `<span class="usage-chip">${escapeHtml(titles.get(t.plugin) || t.plugin)}</span>`).join("") || `<span class="usage-faint">-</span>`}</td>
        <td class="usage-when">${escapeHtml(relativeDay(u.last_seen))}</td>
      </tr>`).join("");
    document.getElementById("users-table").innerHTML = `
      <thead><tr>
        <th scope="col">Compte</th><th scope="col">Rythme</th><th scope="col" class="num">Jours actifs</th>
        <th scope="col" class="num">Pages vues</th><th scope="col" class="num">Écritures</th><th scope="col">Modules favoris</th><th scope="col">Dernière activité</th>
      </tr></thead>
      <tbody>${rows || `<tr><td colspan="7" class="usage-empty">Aucun compte ne correspond.</td></tr>`}</tbody>`;
  }

  const METHOD_LABELS = { GET: "lecture", POST: "création", PUT: "remplacement", PATCH: "modification", DELETE: "suppression" };

  function routesRowsHtml(routes, titles, limit) {
    return routes.slice(0, limit).map((r) => {
      const page = r.kind === "page";
      const name = page ? (r.title || r.route) : r.route;
      const method = page ? `<span class="usage-method usage-method--page">PAGE</span>` : `<span class="usage-method usage-method--${r.method.toLowerCase()}" title="${METHOD_LABELS[r.method] || ""}">${escapeHtml(r.method)}</span>`;
      const errors = r.server_errors
        ? `<span class="usage-errors">${fmt(r.server_errors)}</span>`
        : r.client_errors ? `<span class="usage-faint" title="Refus (4xx) : droits, saisie, introuvable">${fmt(r.client_errors)}</span>` : `<span class="usage-faint">0</span>`;
      return `<tr>
        <td>${method}</td>
        <th scope="row"><span class="usage-route">${escapeHtml(name)}</span>${page && r.title ? `<span class="usage-route__path mono">${escapeHtml(r.route)}</span>` : ""}</th>
        <td>${escapeHtml(titles.get(r.plugin) || r.plugin)}</td>
        <td class="num">${fmt(r.users)}</td>
        <td class="num">${fmt(r.hits)}</td>
        <td class="num mono">${r.avg_ms.toLocaleString("fr-FR")} ms</td>
        <td class="num mono usage-faint">${Math.round(r.max_ms).toLocaleString("fr-FR")} ms</td>
        <td class="num" title="Erreurs serveur (5xx) en rouge, sinon refus (4xx)">${errors}</td>
      </tr>`;
    }).join("");
  }

  function renderRoutes(report) {
    const titles = new Map(report.plugins.map((p) => [p.name, p.title]));
    const routes = report.routes.filter((r) =>
      state.routes === "all" ? true : state.routes === "page" ? r.kind === "page" : r.kind === "api" && r.method !== "GET" && r.method !== "HEAD");
    document.getElementById("routes-table").innerHTML = `
      <thead><tr>
        <th scope="col">Genre</th><th scope="col">Page ou route</th><th scope="col">Module</th>
        <th scope="col" class="num">Utilisateurs</th><th scope="col" class="num">Requêtes</th>
        <th scope="col" class="num">Temps moyen</th><th scope="col" class="num">Max</th><th scope="col" class="num">Erreurs</th>
      </tr></thead>
      <tbody>${routesRowsHtml(routes, titles, 50) || `<tr><td colspan="8" class="usage-empty">Rien sur la période.</td></tr>`}</tbody>`;
  }

  // -- le détail d'un compte -----------------------------------------------------------------

  async function openUser(userId) {
    const report = state.report;
    const user = report && report.users.find((u) => u.id === userId);
    if (!user) return;
    const dialog = document.getElementById("user-dialog");
    document.getElementById("user-title").textContent = userName(user);
    document.getElementById("user-meta").textContent = [user.email, teamsText(user), user.created_at ? `inscrit le ${shortDate(user.created_at.slice(0, 10))}` : ""]
      .filter(Boolean).join(" · ");
    const detail = document.getElementById("user-detail");
    detail.innerHTML = `<div class="skeleton" style="height:220px"></div>`;
    dialog.showModal();
    try {
      const mine = await usageApi.report(query({ user_id: userId, team: null }));
      const titles = new Map(mine.plugins.map((p) => [p.name, p.title]));
      const used = mine.plugins.filter((p) => p.hits);
      const maxHits = Math.max(1, ...used.map((p) => p.page_views + p.writes));
      detail.innerHTML = `
        <div class="usage-drawer__kpis">
          ${frequencyBadge(user.frequency)}
          <span><strong class="mono">${fmt(user.active_days)}</strong> jour${user.active_days > 1 ? "s" : ""} actif${user.active_days > 1 ? "s" : ""}</span>
          <span><strong class="mono">${fmt(mine.totals.page_views)}</strong> pages vues</span>
          <span><strong class="mono">${fmt(mine.totals.writes)}</strong> écritures</span>
          <span class="usage-faint">première visite : ${escapeHtml(user.first_seen ? shortDate(user.first_seen) : "jamais")}</span>
        </div>
        <h3 class="section-title">Activité</h3>
        <div id="user-chart" class="usage-chart"></div>
        <h3 class="section-title">Modules</h3>
        ${used.length ? `<div class="usage-table-wrap"><table class="usage-table usage-table--compact"><thead><tr><th scope="col">Module</th><th scope="col">Pages + écritures</th><th scope="col" class="num">Lectures</th><th scope="col">Dernière</th></tr></thead><tbody>
          ${used.sort((a, b) => (b.page_views + b.writes) - (a.page_views + a.writes) || b.reads - a.reads).map((p) => `<tr>
            <th scope="row"><span class="usage-module">${settingsIcon(p.icon, 16)}<span>${escapeHtml(p.title)}</span></span></th>
            <td class="usage-adoption">${UsageCharts.meterHtml((p.page_views + p.writes) / maxHits, "")}<span class="mono">${fmt(p.page_views)} + ${fmt(p.writes)}</span></td>
            <td class="num">${fmt(p.reads)}</td><td class="usage-when">${escapeHtml(relativeDay(p.last_used))}</td></tr>`).join("")}
          </tbody></table></div>` : `<p class="usage-empty">Aucune activité sur la période.</p>`}
        <h3 class="section-title">Pages et actions les plus fréquentes</h3>
        ${mine.routes.length ? `<div class="usage-table-wrap"><table class="usage-table usage-table--compact"><tbody>${routesRowsHtml(mine.routes, titles, 12)}</tbody></table></div>` : `<p class="usage-empty">-</p>`}`;
      UsageCharts.columns(document.getElementById("user-chart"), {
        buckets: mine.series.map((s) => s.bucket),
        granularity: mine.period.granularity,
        series: [
          { label: "Pages vues", color: "var(--usage-series-1)", values: mine.series.map((s) => s.page_views) },
          { label: "Écritures", color: "var(--usage-series-2)", values: mine.series.map((s) => s.writes) },
        ],
        height: 180,
        ariaLabel: "Pages vues et écritures du compte par période",
      });
      document.getElementById("user-chart").insertAdjacentHTML("afterbegin",
        `<div class="usage-legend"><span class="usage-legend__item"><span class="usage-legend__key" style="background:var(--usage-series-1)"></span>Pages vues</span><span class="usage-legend__item"><span class="usage-legend__key" style="background:var(--usage-series-2)"></span>Écritures</span></div>`);
    } catch (err) {
      detail.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
    }
  }

  // -- export CSV ------------------------------------------------------------------------------

  function downloadCsv(name, header, rows) {
    const cell = (v) => {
      const text = v === null || v === undefined ? "" : String(v);
      return /[";\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    const csv = "﻿" + [header, ...rows].map((r) => r.map(cell).join(";")).join("\r\n");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const { start, end } = range();
    link.download = `spectre-${name}-${start}_${end}.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function exportModules() {
    const r = state.report;
    if (!r) return;
    downloadCsv("modules", ["module", "titre", "actif", "utilisateurs", "adoption_%", "pages_vues", "lectures", "ecritures", "requetes", "requetes_periode_precedente", "derniere_utilisation"],
      r.plugins.map((p) => [p.name, p.title, p.active ? "oui" : "non", p.users, Math.round(p.adoption_rate * 100), p.page_views, p.reads, p.writes, p.hits, p.previous_hits, p.last_used || ""]));
  }
  function exportUsers() {
    const r = state.report;
    if (!r) return;
    downloadCsv("utilisateurs", ["compte", "e-mail", "equipes", "admin", "rythme", "jours_actifs", "pages_vues", "lectures", "ecritures", "modules_favoris", "premiere_visite", "derniere_activite"],
      r.users.map((u) => [userName(u), u.email || "", u.teams.join(", "), u.is_admin ? "oui" : "non", FREQUENCIES[u.frequency].label, u.active_days, u.page_views, u.reads, u.writes,
        u.top_plugins.map((t) => t.plugin).join(", "), u.first_seen || "", u.last_seen || ""]));
  }

  // -- événements ------------------------------------------------------------------------------

  function onRowActivate(tableId, handler) {
    const table = document.getElementById(tableId);
    table.addEventListener("click", (event) => {
      const row = event.target.closest("tr.usage-row-link");
      if (row) handler(row);
    });
    table.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const row = event.target.closest("tr.usage-row-link");
      if (!row) return;
      event.preventDefault();
      handler(row);
    });
  }

  function bind() {
    document.querySelectorAll("[data-period]").forEach((button) => button.addEventListener("click", () => {
      const period = button.dataset.period;
      if (period === "custom") {
        const current = range();
        state.start = current.start;
        state.end = current.end;
      } else {
        state.granularity = PRESET_GRANULARITY[period];
      }
      state.period = period;
      syncControls();
      load();
    }));
    document.querySelectorAll("[data-granularity]").forEach((button) => button.addEventListener("click", () => {
      state.granularity = button.dataset.granularity;
      syncControls();
      load();
    }));
    ["start", "end"].forEach((id) => document.getElementById(id).addEventListener("change", (event) => {
      if (!event.target.value) return;
      state[id] = event.target.value;
      load();
    }));
    document.getElementById("team").addEventListener("change", (event) => { state.team = event.target.value; load(); });
    document.getElementById("plugin").addEventListener("change", (event) => { state.plugin = event.target.value; load(); });
    document.getElementById("include-admins").addEventListener("change", (event) => { state.includeAdmins = event.target.checked; load(); });
    document.querySelectorAll("[data-metric]").forEach((button) => button.addEventListener("click", () => {
      state.metric = button.dataset.metric;
      syncControls();
      if (state.report) renderModulesChart(state.report);
    }));
    document.querySelectorAll("[data-routes]").forEach((button) => button.addEventListener("click", () => {
      state.routes = button.dataset.routes;
      syncControls();
      if (state.report) renderRoutes(state.report);
    }));
    document.getElementById("user-search").addEventListener("input", (event) => {
      state.userQuery = event.target.value;
      if (state.report) renderUsers(state.report);
    });
    onRowActivate("modules-table", (row) => {
      state.plugin = state.plugin === row.dataset.plugin ? "" : row.dataset.plugin;
      syncControls();
      load();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    onRowActivate("users-table", (row) => openUser(Number(row.dataset.user)));
    document.getElementById("export-modules").addEventListener("click", exportModules);
    document.getElementById("export-users").addEventListener("click", exportUsers);
    const dialog = document.getElementById("user-dialog");
    document.getElementById("user-close").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
    dialog.addEventListener("close", UsageCharts.hideTip);
    window.addEventListener("resize", () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (!state.report) return;
        renderActive(state.report);
        renderHeatmap(state.report);
        renderModulesChart(state.report);
      }, 150);
    });
    window.addEventListener("scroll", UsageCharts.hideTip, { passive: true });
  }

  readUrl();
  syncControls();
  bind();
  loadTeams();
  load();
})();
