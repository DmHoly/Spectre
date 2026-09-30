/* Bloc KPI réutilisable : une tendance mensuelle par onglet, un onglet par KPI.

   Usage (dépend de d3, common.js pour escapeHtml, api.js) :

     KpiTrendBlock.mount(document.getElementById("trends"), {
       kpisUrl: "/api/management/native-pt2/tendances",           // -> { kpis: [{key, label, status, variants...}] }
       seriesUrl: (key, months, variant) => `/api/.../tendances/${key}?mois=${months}&variante=${variant}`,
       ranges: [6, 12, 24],       // boutons de période, en mois
       defaultRange: 12,
       storageKey: "trends:native-pt2",   // mémorise l'onglet/période/variante choisis (confort, facultatif)
       onPointClick: (point, series) => {}, // clic sur un point porteur d'une étude (`point.study`)
     });

   `kpis` peut aussi être passé directement (tableau) à la place de `kpisUrl`. Chaque onglet charge
   sa série à la demande et la garde en cache : un KPI lent (requête PRISM) ne retarde ni la page ni
   les autres onglets. Une série répond au format :
     { status: "live"|"placeholder"|"error", unit, better: "up"|"down"|null, description, source,
       message, target, periods: ["2026-01", ...], points: [{period, value}] }
   Un KPI "placeholder" s'affiche comme un aperçu (courbe fantôme, clairement signalée) avec sa
   future source de données ; un KPI "demo" se trace normalement mais porte partout la mention
   « données fictives ». Un KPI à `variants` (ex : expériences en cours / wafers engagés) affiche
   une bascule au-dessus de la courbe. Un point porteur d'une étude (`study`, `label`) est marqué
   d'un jalon cliquable (et listé sous la courbe) qui appelle `onPointClick`. Voir
   spectre/core/trends.py pour ajouter un KPI côté serveur. */

(function () {
  const MONTHS_FR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  let uid = 0;

  function monthLabel(period, withYear) {
    const [y, m] = period.split("-").map(Number);
    return withYear ? `${MONTHS_FR[m - 1]} ${String(y).slice(2)}` : MONTHS_FR[m - 1];
  }

  function formatValue(v, unit) {
    if (v === null || v === undefined || Number.isNaN(v)) return "—";
    const abs = Math.abs(v);
    const digits = abs >= 100 || Number.isInteger(v) ? 0 : abs >= 10 ? 1 : 2;
    const txt = v.toLocaleString("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: 0 });
    return unit === "%" ? `${txt} %` : txt;
  }

  function readStore(key) {
    if (!key) return {};
    try {
      return JSON.parse(localStorage.getItem(key) || "{}") || {};
    } catch (_) {
      return {};
    }
  }
  function writeStore(key, value) {
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (_) {
      /* stockage indisponible (navigation privée...) : on s'en passe */
    }
  }

  const ICON_UP = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 15 6-6 6 6"/></svg>`;
  const ICON_DOWN = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>`;
  const ICON_FLAT = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14"/></svg>`;

  function mount(root, options) {
    const opts = Object.assign({ ranges: [6, 12, 24], defaultRange: 12, title: "Tendances" }, options);
    const id = `kpi-block-${++uid}`;
    const stored = readStore(opts.storageKey);
    const state = {
      kpis: [],
      active: stored.active || null,
      months: opts.ranges.includes(stored.months) ? stored.months : opts.defaultRange,
      variants: stored.variants && typeof stored.variants === "object" ? stored.variants : {}, // kpi -> variante choisie
      cache: new Map(), // `${key}:${months}:${variant}` -> promesse de série
      series: null,
      showTable: false,
    };

    root.classList.add("kpi-block");
    root.innerHTML = `
      <div class="kpi-block__head">
        <div>
          <div class="section-title">${escapeHtml(opts.eyebrow || "Indicateurs")}</div>
          <h2 class="kpi-block__title">${escapeHtml(opts.title)}</h2>
        </div>
        <div class="kpi-block__ranges" role="group" aria-label="Période affichée">
          ${opts.ranges
            .map((m) => `<button type="button" class="kpi-block__range" data-months="${m}" aria-pressed="false">${m} mois</button>`)
            .join("")}
        </div>
      </div>
      <div class="tabs kpi-block__tabs" role="tablist" aria-label="${escapeHtml(opts.title)}"></div>
      <div class="kpi-block__panel" role="tabpanel" id="${id}-panel" tabindex="0">
        <div class="skeleton" style="height:220px;"></div>
      </div>`;

    const tablist = root.querySelector(".kpi-block__tabs");
    const panel = root.querySelector(".kpi-block__panel");

    function save() {
      writeStore(opts.storageKey, { active: state.active, months: state.months, variants: state.variants });
    }

    // La variante affichée pour un KPI : celle choisie la dernière fois, sinon la première.
    function variantOf(key) {
      const kpi = state.kpis.find((k) => k.key === key);
      const variants = (kpi && kpi.variants) || [];
      if (!variants.length) return null;
      return variants.some((v) => v.key === state.variants[key]) ? state.variants[key] : variants[0].key;
    }

    function renderTabs() {
      tablist.innerHTML = state.kpis
        .map((k) => {
          const selected = k.key === state.active;
          const soon =
            k.status === "placeholder"
              ? `<span class="kpi-block__soon">à venir</span>`
              : k.status === "demo"
                ? `<span class="kpi-block__soon kpi-block__soon--demo">démo</span>`
                : "";
          return `<button type="button" role="tab" class="tab${selected ? " active" : ""}" id="${id}-tab-${escapeHtml(k.key)}"
            data-key="${escapeHtml(k.key)}" aria-selected="${selected}" aria-controls="${id}-panel" tabindex="${selected ? 0 : -1}">${escapeHtml(k.label)}${soon}</button>`;
        })
        .join("");
      panel.setAttribute("aria-labelledby", `${id}-tab-${state.active}`);
      root.querySelectorAll(".kpi-block__range").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.months) === state.months)));
    }

    function fetchSeries(key, months, variant) {
      const cacheKey = `${key}:${months}:${variant || ""}`;
      if (!state.cache.has(cacheKey)) {
        const p = api.get(opts.seriesUrl(key, months, variant)).catch((err) => {
          state.cache.delete(cacheKey); // on retentera au prochain affichage
          throw err;
        });
        state.cache.set(cacheKey, p);
      }
      return state.cache.get(cacheKey);
    }

    async function select(key, focus) {
      state.active = key;
      save();
      renderTabs();
      if (focus) tablist.querySelector(`[data-key="${CSS.escape(key)}"]`).focus();
      panel.setAttribute("aria-busy", "true");
      const months = state.months;
      const variant = variantOf(key);
      try {
        const series = await fetchSeries(key, months, variant);
        if (state.active !== key || state.months !== months || variantOf(key) !== variant) return; // un autre choix entre-temps
        state.series = series;
        renderPanel();
      } catch (err) {
        if (state.active !== key) return;
        state.series = null;
        panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
      } finally {
        panel.removeAttribute("aria-busy");
      }
    }

    // --- panneau : résumé + graphique + pied -----------------------------------------------

    function isDrawn(s) {
      return s.status === "live" || s.status === "demo";
    }

    function variantToggleHtml(s) {
      const variants = s.variants || [];
      if (variants.length < 2) return "";
      return `
        <div class="view-toggle kpi-block__variants" role="group" aria-label="Mesure affichée">
          ${variants
            .map(
              (v) =>
                `<button type="button" class="view-toggle__btn${v.key === s.variant ? " active" : ""}" data-variant="${escapeHtml(v.key)}" aria-pressed="${v.key === s.variant}">${escapeHtml(v.label)}</button>`
            )
            .join("")}
        </div>`;
    }

    function milestonesHtml(s) {
      const studies = s.points.filter((p) => p.study);
      if (!studies.length) return "";
      return `
        <div class="kpi-block__milestones">
          <span class="kpi-block__milestones-title">Études jalons</span>
          ${studies
            .map(
              (p) =>
                `<button type="button" class="kpi-block__milestone" data-study="${escapeHtml(p.study)}"><span class="kpi-block__milestone-mark" aria-hidden="true"></span><span class="kpi-block__milestone-when">${monthLabel(p.period, true)}</span>${escapeHtml(p.label || "")}<span class="kpi-block__milestone-value">${formatValue(p.value, s.unit)}</span></button>`
            )
            .join("")}
        </div>`;
    }

    function summaryHtml(s) {
      const pts = s.points.filter((p) => p.value !== null && p.value !== undefined);
      if (!isDrawn(s) || !pts.length) return "";
      const last = pts[pts.length - 1];
      const prev = pts.length > 1 ? pts[pts.length - 2] : null;
      let delta = "";
      if (prev) {
        const diff = last.value - prev.value;
        const dir = diff > 0 ? "up" : diff < 0 ? "down" : "flat";
        const tone = dir === "flat" || !s.better ? "neutral" : dir === s.better ? "good" : "bad";
        const icon = dir === "up" ? ICON_UP : dir === "down" ? ICON_DOWN : ICON_FLAT;
        const sign = diff > 0 ? "+" : "";
        delta = `<span class="kpi-block__delta kpi-block__delta--${tone}">${icon}${sign}${formatValue(diff, "")}${s.unit === "%" ? " pt" : ""} <span class="kpi-block__delta-ref">vs ${monthLabel(prev.period, true)}</span></span>`;
      }
      const demo = s.status === "demo" ? `<span class="kpi-block__demo" title="${escapeHtml(s.message || "")}">Démo · données fictives</span>` : "";
      return `
        <div class="kpi-block__summary">
          <div class="kpi-block__value">${formatValue(last.value, s.unit)}${s.unit && s.unit !== "%" ? `<span class="kpi-block__unit">${escapeHtml(s.unit)}</span>` : ""}</div>
          <div class="kpi-block__value-meta">${monthLabel(last.period, true)} ${delta} ${demo}</div>
        </div>`;
    }

    function tableHtml(s) {
      const byPeriod = new Map(s.points.map((p) => [p.period, p.value]));
      return `
        <table class="kpi-block__table">
          <thead><tr><th scope="col">Mois</th><th scope="col">${escapeHtml(s.variant_label || s.label)}${s.unit ? ` (${escapeHtml(s.unit)})` : ""}</th></tr></thead>
          <tbody>${s.periods.map((p) => `<tr><td>${monthLabel(p, true)}</td><td>${formatValue(byPeriod.get(p), s.unit)}</td></tr>`).join("")}</tbody>
        </table>`;
    }

    function renderPanel() {
      const s = state.series;
      if (!s) return;
      const placeholder = !isDrawn(s);
      const overlay = placeholder
        ? `<div class="kpi-block__overlay">
            <div class="kpi-block__overlay-title">${s.status === "error" ? "Données indisponibles" : "Aperçu — données à brancher"}</div>
            <div class="kpi-block__overlay-text">${escapeHtml(s.message || "")}${s.source ? ` Source prévue : <span class="kpi-block__mono">${escapeHtml(s.source)}</span>.` : ""}</div>
          </div>`
        : "";
      panel.innerHTML = `
        <div class="kpi-block__panel-head">${summaryHtml(s)}${variantToggleHtml(s)}</div>
        <div class="kpi-block__chart${placeholder ? " kpi-block__chart--ghost" : ""}">
          <svg role="img" aria-label="${escapeHtml(`${s.variant_label || s.label} par mois${placeholder ? " (aperçu, pas de données)" : ""}`)}"></svg>
          <div class="kpi-block__tooltip" hidden></div>
          ${overlay}
        </div>
        ${placeholder ? "" : milestonesHtml(s)}
        <div class="kpi-block__foot">
          <span>${escapeHtml(s.description || "")}${!placeholder && s.source ? ` · <span class="kpi-block__mono">${escapeHtml(s.source)}</span>` : ""}${s.status === "demo" && s.message ? ` · <strong>${escapeHtml(s.message)}</strong>` : ""}</span>
          ${placeholder ? "" : `<button type="button" class="kpi-block__table-toggle" aria-expanded="${state.showTable}">${state.showTable ? "Masquer les données" : "Voir les données"}</button>`}
        </div>
        ${!placeholder && state.showTable ? tableHtml(s) : ""}`;
      drawChart();
    }

    // Courbe fantôme déterministe pour un KPI pas encore branché : juste une forme, jamais des chiffres.
    function ghostPoints(periods) {
      return periods.map((period, i) => ({ period, value: 50 + 18 * Math.sin(i / 1.7) + i * 2.2 }));
    }

    function drawChart() {
      const s = state.series;
      const wrap = panel.querySelector(".kpi-block__chart");
      const svgEl = wrap && wrap.querySelector("svg");
      if (!svgEl || typeof d3 === "undefined") return;
      const placeholder = !isDrawn(s);
      const width = Math.max(wrap.clientWidth, 260);
      const height = 220;
      const margin = { top: 14, right: 16, bottom: 26, left: placeholder ? 28 : 44 };
      const svg = d3.select(svgEl).attr("viewBox", `0 0 ${width} ${height}`).attr("width", width).attr("height", height);
      svg.selectAll("*").remove();

      const byPeriod = new Map(s.points.map((p) => [p.period, p]));
      const data = placeholder
        ? ghostPoints(s.periods)
        : s.periods.map((period) => {
            const point = byPeriod.get(period);
            return { period, value: point ? point.value : null, study: point ? point.study : null, label: point ? point.label : null };
          });
      // chaque mois « appartient » à la dernière étude jalon conclue avant lui (ce qui a établi ce niveau)
      let governing = null;
      data.forEach((d) => {
        if (d.study) governing = { study: d.study, label: d.label, period: d.period };
        d.governing = governing;
      });
      const clickable = typeof opts.onPointClick === "function";
      const x = d3.scalePoint().domain(s.periods).range([margin.left, width - margin.right]).padding(0.1);
      const values = data.map((d) => d.value).filter((v) => v !== null);
      if (s.target !== null && s.target !== undefined) values.push(s.target);
      const [lo, hi] = values.length ? d3.extent(values) : [0, 1];
      const y = d3
        .scaleLinear()
        .domain([Math.min(0, lo), hi === lo ? hi + 1 : hi])
        .nice(4)
        .range([height - margin.bottom, margin.top]);

      // grille + axes, en retrait
      // Un comptage (que des entiers) n'a pas de graduation « 0,2 ».
      const integral = values.every(Number.isInteger);
      if (integral && y.domain()[1] < 4) y.domain([y.domain()[0], 4]);
      const yTicks = y.ticks(4).filter((t) => !integral || Number.isInteger(t));
      svg
        .append("g")
        .attr("class", "kpi-chart__grid")
        .selectAll("line")
        .data(yTicks)
        .join("line")
        .attr("x1", margin.left)
        .attr("x2", width - margin.right)
        .attr("y1", (d) => y(d))
        .attr("y2", (d) => y(d));
      if (!placeholder) {
        svg
          .append("g")
          .attr("class", "kpi-chart__axis")
          .selectAll("text")
          .data(yTicks)
          .join("text")
          .attr("x", margin.left - 8)
          .attr("y", (d) => y(d))
          .attr("dy", "0.32em")
          .attr("text-anchor", "end")
          .text((d) => d.toLocaleString("fr-FR"));
      }
      const every = Math.ceil(s.periods.length / Math.max(2, Math.floor((width - margin.left - margin.right) / 58)));
      svg
        .append("g")
        .attr("class", "kpi-chart__axis")
        .selectAll("text")
        .data(s.periods.filter((_, i) => i % every === 0 || i === s.periods.length - 1))
        .join("text")
        .attr("x", (d) => x(d))
        .attr("y", height - 6)
        .attr("text-anchor", "middle")
        .text((d, i) => monthLabel(d, i === 0 || d.endsWith("-01")));

      // objectif (ligne de référence)
      if (!placeholder && s.target !== null && s.target !== undefined) {
        svg.append("line").attr("class", "kpi-chart__target").attr("x1", margin.left).attr("x2", width - margin.right).attr("y1", y(s.target)).attr("y2", y(s.target));
        svg.append("text").attr("class", "kpi-chart__target-label").attr("x", width - margin.right).attr("y", y(s.target) - 6).attr("text-anchor", "end").text(`objectif ${formatValue(s.target, s.unit)}`);
      }

      const defined = (d) => d.value !== null && d.value !== undefined;
      const area = d3.area().defined(defined).x((d) => x(d.period)).y0(y(y.domain()[0])).y1((d) => y(d.value)).curve(d3.curveMonotoneX);
      const line = d3.line().defined(defined).x((d) => x(d.period)).y((d) => y(d.value)).curve(d3.curveMonotoneX);
      svg.append("path").datum(data).attr("class", "kpi-chart__area").attr("d", area);
      svg.append("path").datum(data).attr("class", "kpi-chart__line").attr("d", line);
      if (placeholder) return;

      const present = data.filter(defined);
      const last = present[present.length - 1];
      if (last) svg.append("circle").attr("class", "kpi-chart__dot").attr("cx", x(last.period)).attr("cy", y(last.value)).attr("r", 4.5);

      const openStudy = (d) => {
        if (clickable && d && d.study) opts.onPointClick({ period: d.period, value: d.value, study: d.study, label: d.label }, s);
      };

      // survol : réticule + infobulle, cible = toute la zone de tracé
      const tooltip = wrap.querySelector(".kpi-block__tooltip");
      const cross = svg.append("line").attr("class", "kpi-chart__cross").attr("y1", margin.top).attr("y2", height - margin.bottom).style("display", "none");
      const focus = svg.append("circle").attr("class", "kpi-chart__dot").attr("r", 4.5).style("display", "none");
      const hide = () => {
        cross.style("display", "none");
        focus.style("display", "none");
        tooltip.hidden = true;
      };
      svg
        .append("rect")
        .attr("x", margin.left)
        .attr("y", margin.top)
        .attr("width", width - margin.left - margin.right)
        .attr("height", height - margin.top - margin.bottom)
        .attr("fill", "transparent")
        .on("pointermove", (event) => {
          const [mx] = d3.pointer(event);
          const nearest = d3.least(data, (d) => Math.abs(x(d.period) - mx));
          if (!nearest) return hide();
          const cx = x(nearest.period);
          cross.attr("x1", cx).attr("x2", cx).style("display", null);
          if (defined(nearest)) focus.attr("cx", cx).attr("cy", y(nearest.value)).style("display", null);
          else focus.style("display", "none");
          const study = nearest.governing;
          const studyLine = study
            ? `<div class="kpi-block__tooltip-study">${nearest.study ? "Jalon" : "Depuis"} : ${escapeHtml(study.label || "")}${clickable ? `<span class="kpi-block__tooltip-hint">Cliquer pour la fiche</span>` : ""}</div>`
            : "";
          tooltip.innerHTML = `<div class="kpi-block__tooltip-period">${monthLabel(nearest.period, true)}</div><div class="kpi-block__tooltip-value">${formatValue(nearest.value, s.unit)}${s.unit && s.unit !== "%" && defined(nearest) ? ` ${escapeHtml(s.unit)}` : ""}</div>${studyLine}`;
          tooltip.hidden = false;
          const left = Math.min(Math.max(cx - tooltip.offsetWidth / 2, 0), width - tooltip.offsetWidth);
          tooltip.style.left = `${left}px`;
          tooltip.style.top = `${Math.max(defined(nearest) ? y(nearest.value) - tooltip.offsetHeight - 12 : margin.top, 0)}px`;
        })
        .on("pointerleave", hide)
        .on("click", (event) => {
          const [mx] = d3.pointer(event);
          const nearest = d3.least(data, (d) => Math.abs(x(d.period) - mx));
          if (nearest && nearest.governing) openStudy(nearest.governing);
        })
        .style("cursor", clickable && data.some((d) => d.study) ? "pointer" : null);

      // jalons : un losange or par étude, au-dessus de la zone de survol (clic direct, clavier)
      svg
        .append("g")
        .selectAll("path")
        .data(data.filter((d) => d.study && defined(d)))
        .join("path")
        .attr("class", "kpi-chart__milestone")
        .attr("d", d3.symbol(d3.symbolDiamond, 90))
        .attr("transform", (d) => `translate(${x(d.period)},${y(d.value)})`)
        .attr("tabindex", clickable ? 0 : null)
        .attr("role", clickable ? "button" : null)
        .attr("aria-label", (d) => `${d.label || "Étude"} - ${monthLabel(d.period, true)} : ${formatValue(d.value, s.unit)}`)
        .on("click", (event, d) => openStudy(d))
        .on("keydown", (event, d) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            openStudy(d);
          }
        })
        .append("title")
        .text((d) => `${d.label || "Étude"} - ${formatValue(d.value, s.unit)}`);
    }

    // --- interactions ---------------------------------------------------------------------

    tablist.addEventListener("click", (event) => {
      const tab = event.target.closest("[role=tab]");
      if (tab && tab.dataset.key !== state.active) select(tab.dataset.key, false);
    });
    tablist.addEventListener("keydown", (event) => {
      const keys = state.kpis.map((k) => k.key);
      let i = keys.indexOf(state.active);
      if (event.key === "ArrowRight") i = (i + 1) % keys.length;
      else if (event.key === "ArrowLeft") i = (i - 1 + keys.length) % keys.length;
      else if (event.key === "Home") i = 0;
      else if (event.key === "End") i = keys.length - 1;
      else return;
      event.preventDefault();
      select(keys[i], true);
    });
    root.querySelector(".kpi-block__ranges").addEventListener("click", (event) => {
      const btn = event.target.closest("[data-months]");
      if (!btn || Number(btn.dataset.months) === state.months) return;
      state.months = Number(btn.dataset.months);
      save();
      select(state.active, false);
    });
    panel.addEventListener("click", (event) => {
      const variantBtn = event.target.closest("[data-variant]");
      if (variantBtn) {
        if (variantBtn.dataset.variant === variantOf(state.active)) return;
        state.variants[state.active] = variantBtn.dataset.variant;
        save();
        select(state.active, false);
        return;
      }
      const milestone = event.target.closest("[data-study]");
      if (milestone && typeof opts.onPointClick === "function" && state.series) {
        const point = state.series.points.find((p) => p.study === milestone.dataset.study);
        if (point) opts.onPointClick(point, state.series);
        return;
      }
      if (!event.target.closest(".kpi-block__table-toggle")) return;
      state.showTable = !state.showTable;
      renderPanel();
    });
    if (typeof ResizeObserver !== "undefined") {
      let lastWidth = 0;
      new ResizeObserver(() => {
        const w = panel.clientWidth;
        if (Math.abs(w - lastWidth) > 4 && state.series) {
          lastWidth = w;
          drawChart();
        }
      }).observe(panel);
    }

    // --- démarrage ------------------------------------------------------------------------

    (async () => {
      try {
        state.kpis = opts.kpis || (await api.get(opts.kpisUrl)).kpis;
      } catch (err) {
        panel.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div>`;
        return;
      }
      if (!state.kpis.length) {
        panel.innerHTML = `<div class="empty-state">Aucun indicateur défini.</div>`;
        return;
      }
      if (!state.kpis.some((k) => k.key === state.active)) state.active = state.kpis[0].key;
      select(state.active, false);
    })();

    return {
      refresh() {
        state.cache.clear();
        if (state.active) select(state.active, false);
      },
    };
  }

  window.KpiTrendBlock = { mount };
})();
