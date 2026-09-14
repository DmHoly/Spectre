/* Page "wiki" du dictionnaire de hooks (spectre/core/datahook) :
   - /donnees              -> le hub, une carte par catégorie (Post EPI, Structure...), chaque hook
                              en chip (implémenté = cliquable, "planned" = grisé "à venir").
   - /donnees/<key>         -> la fiche d'un hook : description, colonnes niveau 1 (données brutes,
                              telles que la requête SQL les renvoie) et niveau 2 (KPI calculés par
                              le post-traitement, avec leur source), un graphique représentatif
                              construit sur `example_rows` (écrit à la main dans hook.yml - la fiche
                              se charge sans dépendre de la base), et - seulement si le hook est
                              implémenté - un testeur en direct (mêmes paramètres, exécute
                              vraiment la requête, comme avant).

   Tout vient de hook.yml (voir spectre/core/datahook/hooks.py) via /api/donnees/categories -
   rien de tout ça n'est câblé en dur ici. */

const errorBox = document.getElementById("error");
function showError(err) {
  errorBox.textContent = err.message || String(err);
  errorBox.style.display = "block";
}
function clearError() {
  errorBox.style.display = "none";
}

function currentHookKey() {
  const match = window.location.pathname.match(/^\/donnees\/([^/]+)$/);
  return match ? decodeURIComponent(match[1]) : null;
}

function setBreadcrumb(parts) {
  // parts: [{label, href?}] - le dernier n'est jamais un lien (c'est la page courante).
  document.getElementById("breadcrumb").innerHTML = parts
    .map((p, i) => (i === parts.length - 1 || !p.href ? `<span>${escapeHtml(p.label)}</span>` : `<a href="${p.href}">${escapeHtml(p.label)}</a>`))
    .join(" / ");
}

function cellText(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return `[${value.length} valeurs]`;
  return String(value);
}

// ---------------------------------------------------------------------------------------------
// Hub : une carte par catégorie.
// ---------------------------------------------------------------------------------------------

function hookChipHtml(hook) {
  if (hook.status === "planned") {
    return `<div class="hook-chip hook-chip--planned"><span>${escapeHtml(hook.title)}</span><span class="badge-planned">à venir</span></div>`;
  }
  return `<a class="hook-chip hook-chip--implemented" href="/donnees/${encodeURIComponent(hook.key)}" style="text-decoration:none;color:inherit;">
    <span>${escapeHtml(hook.title)}</span>
    <span style="color:var(--text-faint);font-size:16px;">&rarr;</span>
  </a>`;
}

function categoryCardHtml(category) {
  const implementedCount = category.hooks.filter((h) => h.status === "implemented").length;
  return `
    <div class="card card-pad">
      <div style="font-size:15.5px;font-weight:700;">${escapeHtml(category.name)}</div>
      <div class="help" style="margin-top:2px;">${implementedCount}/${category.hooks.length} implémenté${implementedCount > 1 ? "s" : ""}</div>
      <div class="hook-chip-list">${category.hooks.map(hookChipHtml).join("")}</div>
    </div>`;
}

async function renderHub() {
  setBreadcrumb([{ label: "Data" }]);
  const root = document.getElementById("app-root");
  root.innerHTML = `
    <h1 style="font-size:24px;margin-bottom:6px;">Data</h1>
    <p style="color:var(--text-soft);font-size:14px;margin-bottom:20px;max-width:70ch;">
      Le dictionnaire de données de cette installation (<code>spectre/core/datahook</code>), organisé
      par catégorie. Chaque source documente ses données brutes (niveau 1) et les KPI qu'on en calcule
      (niveau 2), avec un exemple et un graphique - avant même de lancer une vraie requête.
    </p>
    <div id="categories-grid" class="category-grid"><p class="help">Chargement…</p></div>`;

  try {
    const body = await api.get("/api/donnees/categories");
    document.getElementById("categories-grid").innerHTML = body.categories.map(categoryCardHtml).join("");
  } catch (err) {
    showError(err);
  }
}

// ---------------------------------------------------------------------------------------------
// Fiche d'un hook.
// ---------------------------------------------------------------------------------------------

function columnsTableHtml(columns, { withSource }) {
  if (!columns.length) return `<p class="help">Aucune colonne documentée pour l'instant.</p>`;
  return `
    <div class="donnees-table-wrap">
      <table class="donnees-table">
        <thead><tr>
          <th>Colonne</th><th>Description</th>${withSource ? "<th>Source</th>" : ""}<th>Exemple</th>
        </tr></thead>
        <tbody>
          ${columns
            .map(
              (c) => `<tr>
                <td><code>${escapeHtml(c.name)}</code></td>
                <td>${escapeHtml(c.description || "")}</td>
                ${withSource ? `<td>${c.source ? `<code>${escapeHtml(c.source)}</code>` : ""}</td>` : ""}
                <td>${escapeHtml(cellText(c.example))}</td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function exampleRowsTableHtml(rows) {
  if (!rows.length) return `<p class="help">Pas d'exemple pour l'instant.</p>`;
  const columns = Object.keys(rows[0]);
  return `
    <div class="donnees-table-wrap">
      <table class="donnees-table">
        <thead><tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map((row) => `<tr>${columns.map((c) => `<td>${escapeHtml(cellText(row[c]))}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>`;
}

// Un petit bar chart D3 : une barre par ligne d'exemple, hauteur = representative_column - juste
// assez pour donner une idée visuelle de la donnée sur la fiche, pas un système de graphes complet
// (voir le hub /donnees pour la suite prévue : des fiches graphique dédiées, YAML elles aussi).
function renderRepresentativeChart(hook) {
  const host = document.getElementById("wiki-chart");
  if (!host) return;
  const col = hook.representative_column;
  const rows = (hook.example_rows || []).filter((r) => typeof r[col] === "number");
  if (!col || rows.length === 0) {
    host.innerHTML = `<p class="help">Pas de graphique représentatif pour l'instant.</p>`;
    return;
  }
  const width = 560;
  const height = 220;
  const margin = { top: 16, right: 16, bottom: 46, left: 48 };
  const labelKey = "wafername" in rows[0] ? "wafername" : Object.keys(rows[0])[0];
  const labels = rows.map((r, i) => String(r[labelKey] ?? i));

  const svg = d3.select(host).html("").append("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("width", "100%");
  const x = d3
    .scaleBand()
    .domain(labels.map((_, i) => i))
    .range([margin.left, width - margin.right])
    .padding(0.25);
  const y = d3
    .scaleLinear()
    .domain([0, d3.max(rows, (r) => r[col]) * 1.15 || 1])
    .range([height - margin.bottom, margin.top]);

  svg
    .append("g")
    .selectAll("rect")
    .data(rows)
    .join("rect")
    .attr("x", (_, i) => x(i))
    .attr("width", x.bandwidth())
    .attr("y", (r) => y(r[col]))
    .attr("height", (r) => y(0) - y(r[col]))
    .attr("fill", "var(--accent, #0e5f68)");

  svg
    .append("g")
    .attr("transform", `translate(0,${height - margin.bottom})`)
    .selectAll("text")
    .data(labels)
    .join("text")
    .attr("x", (_, i) => x(i) + x.bandwidth() / 2)
    .attr("y", 16)
    .attr("text-anchor", "middle")
    .attr("font-size", "10px")
    .attr("fill", "var(--text-soft, #5c655e)")
    .text((d) => (d.length > 12 ? d.slice(0, 11) + "…" : d));

  svg
    .append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(y).ticks(4))
    .call((g) => g.selectAll("text").attr("font-size", "10px").attr("fill", "var(--text-soft, #5c655e)"))
    .call((g) => g.selectAll("path,line").attr("stroke", "var(--border-soft, #ede9df)"));

  svg
    .append("text")
    .attr("x", margin.left)
    .attr("y", 12)
    .attr("font-size", "11px")
    .attr("font-weight", "700")
    .attr("fill", "var(--text, #1f2420)")
    .text(col);
}

function runnerHtml(hook) {
  const paramsHtml = hook.parameters.length
    ? hook.parameters
        .map(
          (p) => `
      <div style="margin-top:8px;">
        <label style="font-size:11px;">${escapeHtml(p)}</label>
        <input class="field js-hook-param" data-param="${escapeHtml(p)}" placeholder="valeurs séparées par des virgules (ex: W12-A3, W12-A4)">
      </div>`
        )
        .join("")
    : `<div class="help" style="margin-top:8px;">Ce hook ne prend aucun paramètre.</div>`;

  const cacheHtml = hook.cacheable
    ? `<label style="display:flex;align-items:center;gap:6px;margin-top:10px;font-size:12.5px;font-weight:400;">
         <input type="checkbox" id="hook-refresh-checkbox"> Forcer le rafraîchissement (ignorer le cache)
       </label>`
    : "";

  return `
    <form id="hook-run-form">
      ${paramsHtml}
      ${cacheHtml}
      <button class="btn btn-primary" type="submit" style="margin-top:12px;">Lancer la requête</button>
    </form>
    <div id="results-card" style="display:none;margin-top:16px;">
      <div class="section-title" style="margin-bottom:8px;">Résultat</div>
      <div id="results-summary" class="help" style="margin-bottom:10px;"></div>
      <div class="donnees-table-wrap"><table class="donnees-table" id="donnees-results-table"></table></div>
    </div>`;
}

function wireRunner(hook) {
  const form = document.getElementById("hook-run-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    const parameters = {};
    form.querySelectorAll(".js-hook-param").forEach((input) => {
      parameters[input.dataset.param] = input.value
        .split(",")
        .map((v) => v.trim())
        .filter((v) => v.length > 0);
    });
    const refreshCheckbox = document.getElementById("hook-refresh-checkbox");
    const refresh = refreshCheckbox ? refreshCheckbox.checked : false;
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Requête en cours…";
    try {
      const result = await api.post(`/api/donnees/hooks/${encodeURIComponent(hook.key)}/executer`, { parameters, refresh });
      renderRunnerResults(result);
    } catch (err) {
      showError(err);
      document.getElementById("results-card").style.display = "none";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Lancer la requête";
    }
  });
}

function renderRunnerResults(result) {
  document.getElementById("results-card").style.display = "";
  const countLabel = result.row_count === 0 ? "Aucune ligne renvoyée." : `${result.row_count} ligne${result.row_count > 1 ? "s" : ""}.`;
  const cacheLabel =
    result.from_cache !== undefined
      ? ` (${result.from_cache.length} wafer${result.from_cache.length > 1 ? "s" : ""} en cache, ${result.fetched.length} requêté${result.fetched.length > 1 ? "s" : ""})`
      : "";
  document.getElementById("results-summary").textContent = countLabel + cacheLabel;

  const table = document.getElementById("donnees-results-table");
  if (result.row_count === 0) {
    table.innerHTML = "";
    return;
  }
  const head = `<thead><tr>${result.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr></thead>`;
  const body = `<tbody>${result.rows
    .slice(0, 200)
    .map((row) => `<tr>${row.map((v) => `<td>${escapeHtml(cellText(v))}</td>`).join("")}</tr>`)
    .join("")}</tbody>`;
  table.innerHTML = head + body;
}

async function renderHookPage(key) {
  const root = document.getElementById("app-root");
  root.innerHTML = `<p class="help">Chargement…</p>`;
  let hook;
  try {
    hook = await api.get(`/api/donnees/hooks/${encodeURIComponent(key)}`);
  } catch (err) {
    showError(err);
    root.innerHTML = "";
    return;
  }

  setBreadcrumb([{ label: "Data", href: "/donnees" }, { label: hook.category, href: "/donnees" }, { label: hook.title }]);

  const statusBadge =
    hook.status === "planned"
      ? `<span class="badge-planned">à venir</span>`
      : `<span class="badge-level badge-level--kpi">implémenté</span>`;

  root.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap;">
      <h1 style="font-size:22px;">${escapeHtml(hook.title)}</h1>
      ${statusBadge}
    </div>
    <p style="color:var(--text-soft);font-size:13.5px;margin-bottom:20px;max-width:80ch;white-space:pre-line;">${escapeHtml(hook.description)}</p>

    <div class="card card-pad" style="margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
        <span class="badge-level badge-level--raw">Niveau 1</span>
        <div class="section-title" style="margin-bottom:0;">Données brutes</div>
      </div>
      <p class="help" style="margin-bottom:10px;">Ce que la requête renvoie telle quelle, directement issu de la base.</p>
      ${columnsTableHtml(hook.raw_columns, { withSource: false })}
    </div>

    <div class="card card-pad" style="margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">
        <span class="badge-level badge-level--kpi">Niveau 2</span>
        <div class="section-title" style="margin-bottom:0;">KPI calculés</div>
      </div>
      <p class="help" style="margin-bottom:10px;">Ce que le post-traitement calcule ou recalcule à partir des données brutes - chaque colonne indique la fonction qui la produit.</p>
      ${columnsTableHtml(hook.kpi_columns, { withSource: true })}
    </div>

    <div class="card card-pad" style="margin-bottom:16px;">
      <div class="section-title" style="margin-bottom:10px;">Exemple</div>
      ${exampleRowsTableHtml(hook.example_rows || [])}
      <div id="wiki-chart" style="margin-top:14px;"></div>
    </div>

    ${
      hook.status === "implemented"
        ? `<div class="card card-pad"><div class="section-title" style="margin-bottom:10px;">Tester en direct</div>${runnerHtml(hook)}</div>`
        : `<div class="card card-pad"><p class="help">Fiche documentaire uniquement pour l'instant - pas encore de requête à lancer.</p></div>`
    }`;

  renderRepresentativeChart(hook);
  wireRunner(hook);
}

async function init() {
  const key = currentHookKey();
  if (key) {
    await renderHookPage(key);
  } else {
    await renderHub();
  }
}

init();
