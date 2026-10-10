/* Les graphiques du tableau d'utilisation, en SVG dessiné à la main (global UsageCharts) :
   colonnes (une série), colonnes empilées (plusieurs modules), carte de chaleur jour x heure et
   barres horizontales. Barres de 24px au plus, bout arrondi de 4px, base carrée ; 2px de fond
   entre deux segments ; grille en filets ; texte aux couleurs de texte, jamais à celle d'une série.
   Une seule infobulle (#usage-tip) pour tous, au survol d'une bande entière (cible plus grande
   que la marque) et au focus clavier. Chaque graphique se redessine à la largeur de sa carte. */

const UsageCharts = (function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const NUMBER = new Intl.NumberFormat("fr-FR");
  const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];
  const WEEKDAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];

  function formatNumber(value) {
    return NUMBER.format(value || 0);
  }

  function parseDay(iso) {
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d);
  }

  // « 12 oct. », « sem. du 12 oct. », « oct. 2026 »
  function bucketLabel(iso, granularity, long = false) {
    const day = parseDay(iso);
    if (granularity === "month") return `${MONTHS[day.getMonth()]} ${day.getFullYear()}`;
    const short = `${day.getDate()} ${MONTHS[day.getMonth()]}`;
    if (granularity === "week") return long ? `Semaine du ${short} ${day.getFullYear()}` : short;
    return long ? `${WEEKDAYS[(day.getDay() + 6) % 7]} ${short} ${day.getFullYear()}` : short;
  }

  // Des graduations rondes : 0, 5, 10... (au plus ~5)
  function niceTicks(max) {
    if (max <= 0) return [0, 1];
    const raw = max / 4;
    const power = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = Math.max(1, [1, 2, 5, 10].map((f) => f * power).find((s) => s >= raw));
    const top = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = 0; v <= top + step / 1000; v += step) ticks.push(v);
    return ticks;
  }

  function el(name, attrs = {}, parent = null) {
    const node = document.createElementNS(SVG_NS, name);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (parent) parent.appendChild(node);
    return node;
  }

  // Une colonne au bout arrondi (4px), base carrée sur y0
  function columnPath(x, y, width, height) {
    if (height <= 0) return "";
    const r = Math.min(4, width / 2, height);
    return `M${x},${y + height}V${y + r}Q${x},${y} ${x + r},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}V${y + height}Z`;
  }

  // -- infobulle ---------------------------------------------------------------------------

  const tip = () => document.getElementById("usage-tip");

  function showTip(html, clientX, clientY) {
    const node = tip();
    if (!node) return;
    node.innerHTML = html;
    node.hidden = false;
    const { width, height } = node.getBoundingClientRect();
    let left = clientX + 14;
    let top = clientY - height - 12;
    if (left + width > window.innerWidth - 8) left = clientX - width - 14;
    if (top < 8) top = clientY + 16;
    node.style.left = `${Math.max(8, left)}px`;
    node.style.top = `${top}px`;
  }
  function hideTip() {
    const node = tip();
    if (node) node.hidden = true;
  }
  function tipRow(swatch, label, value) {
    const key = swatch ? `<span class="usage-tip__key" style="background:${swatch}"></span>` : "";
    return `<div class="usage-tip__row">${key}<span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
  }

  // Une bande survolable (souris, clavier) qui montre l'infobulle de sa colonne
  function hoverBand(svg, x, width, height, html, onFocusMark) {
    const band = el("rect", { x, y: 0, width, height, class: "usage-band", tabindex: "0", fill: "transparent" }, svg);
    band.addEventListener("mousemove", (event) => { onFocusMark(true); showTip(html, event.clientX, event.clientY); });
    band.addEventListener("mouseleave", () => { onFocusMark(false); hideTip(); });
    band.addEventListener("focus", () => {
      const box = band.getBoundingClientRect();
      onFocusMark(true);
      showTip(html, box.left + box.width / 2, box.top + 40);
    });
    band.addEventListener("blur", () => { onFocusMark(false); hideTip(); });
    return band;
  }

  // -- colonnes (une ou plusieurs séries empilées) -----------------------------------------

  /* opts : {buckets: [iso], granularity, series: [{label, color, values: []}], height, unit}
     Une série : pas de légende (le titre de la carte la nomme). */
  function columns(container, opts) {
    const series = opts.series;
    const n = opts.buckets.length;
    const width = Math.max(container.clientWidth, 280);
    const height = opts.height || 220;
    const margin = { top: 12, right: 8, bottom: 26, left: 40 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    const totals = opts.buckets.map((_, i) => series.reduce((sum, s) => sum + (s.values[i] || 0), 0));
    const ticks = niceTicks(Math.max(...totals, 0));
    const max = ticks[ticks.length - 1] || 1;
    const band = plotW / Math.max(n, 1);
    const barW = Math.max(2, Math.min(24, band * 0.62));
    const y = (v) => margin.top + plotH - (v / max) * plotH;

    container.innerHTML = "";
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": opts.ariaLabel || "" }, container);

    ticks.forEach((tick) => {
      el("line", { x1: margin.left, x2: width - margin.right, y1: y(tick), y2: y(tick), class: tick === 0 ? "usage-axis" : "usage-grid" }, svg);
      const label = el("text", { x: margin.left - 8, y: y(tick) + 4, class: "usage-tick", "text-anchor": "end" }, svg);
      label.textContent = formatNumber(tick);
    });

    // libellés de l'axe des x sans chevauchement : un sur k
    const labelEvery = Math.max(1, Math.ceil(70 / band));
    opts.buckets.forEach((bucket, i) => {
      const cx = margin.left + band * i + band / 2;
      if (i % labelEvery === 0) {
        const label = el("text", { x: cx, y: height - 8, class: "usage-tick", "text-anchor": "middle" }, svg);
        label.textContent = bucketLabel(bucket, opts.granularity);
      }
      const group = el("g", { class: "usage-col" }, svg);
      let base = 0;
      series.forEach((s, si) => {
        const value = s.values[i] || 0;
        if (!value) return;
        const top = y(base + value);
        let h = y(base) - top;
        const isTop = series.slice(si + 1).every((other) => !(other.values[i] || 0));
        // 2px de fond entre deux segments empilés
        if (base > 0) h -= 2;
        if (h > 0) {
          const x = cx - barW / 2;
          const shape = isTop ? el("path", { d: columnPath(x, top, barW, h) }, group) : el("rect", { x, y: top, width: barW, height: h }, group);
          shape.setAttribute("fill", s.color);
        }
        base += value;
      });
      const rows = series.length > 1
        ? series.filter((s) => s.values[i]).slice().reverse().map((s) => tipRow(s.color, s.label, formatNumber(s.values[i]))).join("")
          + tipRow(null, "Total", formatNumber(totals[i]))
        : tipRow(null, series[0].label, formatNumber(totals[i]));
      const html = `<div class="usage-tip__title">${escapeHtml(bucketLabel(bucket, opts.granularity, true))}</div>${rows}`;
      hoverBand(svg, margin.left + band * i, band, margin.top + plotH, html, (on) => group.classList.toggle("is-hot", on));
    });
    return svg;
  }

  // -- carte de chaleur jour x heure -------------------------------------------------------

  // cells : [{weekday (0 = lundi), hour, hits}]
  function heatmap(container, cells) {
    const grid = Array.from({ length: 7 }, () => new Array(24).fill(0));
    cells.forEach((cell) => { grid[cell.weekday][cell.hour] = cell.hits; });
    const max = Math.max(1, ...cells.map((cell) => cell.hits));
    const width = Math.max(container.clientWidth, 280);
    const left = 34;
    const top = 4;
    const gap = 2;
    const cellW = (width - left - 4) / 24;
    const cellH = Math.min(22, Math.max(14, cellW));
    const height = top + 7 * cellH + 22;

    container.innerHTML = "";
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": "Requêtes par jour de la semaine et par heure" }, container);
    WEEKDAYS.forEach((day, d) => {
      const label = el("text", { x: left - 8, y: top + d * cellH + cellH / 2 + 4, class: "usage-tick", "text-anchor": "end" }, svg);
      label.textContent = day;
      for (let h = 0; h < 24; h += 1) {
        const value = grid[d][h];
        // une seule teinte, du fond clair au navy : la part du maximum
        const share = value ? 12 + Math.round((value / max) * 88) : 0;
        const rect = el("rect", {
          x: left + h * cellW, y: top + d * cellH, width: Math.max(1, cellW - gap), height: cellH - gap, rx: 3,
          fill: value ? `color-mix(in srgb, var(--navy-500) ${share}%, var(--surface))` : "var(--viz-empty)",
          class: "usage-cell", tabindex: "-1",
        }, svg);
        const html = `<div class="usage-tip__title">${WEEKDAYS[d]} · ${h} h - ${h + 1} h</div>${tipRow(null, "Requêtes", formatNumber(value))}`;
        rect.addEventListener("mousemove", (event) => showTip(html, event.clientX, event.clientY));
        rect.addEventListener("mouseleave", hideTip);
      }
    });
    [0, 6, 12, 18].forEach((h) => {
      const label = el("text", { x: left + h * cellW, y: height - 6, class: "usage-tick" }, svg);
      label.textContent = `${h} h`;
    });
    return svg;
  }

  function heatLegendHtml() {
    const steps = [12, 34, 56, 78, 100]
      .map((share) => `<span class="usage-heat-legend__step" style="background:color-mix(in srgb, var(--navy-500) ${share}%, var(--surface))"></span>`)
      .join("");
    return `<div class="usage-heat-legend"><span>moins</span>${steps}<span>plus</span></div>`;
  }

  // -- barre horizontale dans une cellule de tableau ---------------------------------------

  function meterHtml(share, label) {
    const pct = Math.max(0, Math.min(100, share * 100));
    return `<div class="usage-meter" role="img" aria-label="${escapeHtml(label)}"><span class="usage-meter__fill" style="width:${pct.toFixed(1)}%"></span></div>`;
  }

  return { columns, heatmap, heatLegendHtml, meterHtml, bucketLabel, formatNumber, hideTip, showTip, tipRow };
})();
