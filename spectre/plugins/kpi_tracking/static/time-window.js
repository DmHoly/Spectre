/* La fenêtre de temps d'un onglet de KPI (global `KpiTimeWindow`) : une piste dont la densité des mesures dessine
   l'histogramme, une zone verte qu'on déplace ou qu'on étire par ses deux poignées, le libellé de la période et
   « Tout ». Inspirée du sélecteur de période du bloc « KPI Explorer » de quick_report. Les instants sont des
   millisecondes UTC ; les jours des mesures (« AAAA-MM-JJ ») se lisent avec `dayMs`.

     const slider = KpiTimeWindow.mount(host, {
       min, max,              // l'étendue de la piste (ms)
       from, to,              // la fenêtre choisie (ms)
       days: [ms, ...],       // un instant par boîte, pour l'histogramme
       onChange(from, to) {}, // à chaque déplacement
     });
     slider.update({ days })  // un autre jeu de boîtes (même étendue)

   Dépend de escapeHtml (kernel/ui.js). */

const KpiTimeWindow = (function () {
  const DAY = 864e5;
  const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

  function dayMs(day) {
    return Date.parse(`${day}T00:00:00Z`);
  }

  function fmt(ms) {
    const d = new Date(ms);
    return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  }

  // La fenêtre qu'on ouvre : le dernier mois des données, ou toute l'étendue s'il ne s'y trouve rien (`days`).
  function defaultWindow(min, max, days) {
    const start = new Date(max);
    start.setUTCMonth(start.getUTCMonth() - 1);
    const from = Math.max(min, start.getTime());
    return days.some((d) => d >= from && d <= max) ? { from, to: max } : { from: min, to: max };
  }

  function mount(host, options) {
    const { min, max, onChange } = options;
    const span = max - min;
    let days = options.days || [];
    let p0 = (options.from - min) / span;
    let p1 = (options.to - min) / span;

    host.innerHTML = `<div class="kt-window">
      <div class="kt-window__head">
        <span class="section-title">Fenêtre</span>
        <span class="kt-window__label"></span>
        <button type="button" class="btn btn-line kt-window__all">Tout</button>
      </div>
      <div class="kt-window__track">
        <canvas class="kt-window__canvas" aria-hidden="true"></canvas>
        <div class="kt-window__fill"></div>
        <button type="button" class="kt-window__handle" data-handle="L" role="slider" aria-label="Début de la période"></button>
        <button type="button" class="kt-window__handle" data-handle="R" role="slider" aria-label="Fin de la période"></button>
      </div>
      <div class="kt-window__ticks" aria-hidden="true"></div>
    </div>`;
    const track = host.querySelector(".kt-window__track");
    const fill = host.querySelector(".kt-window__fill");
    const label = host.querySelector(".kt-window__label");
    const canvas = host.querySelector(".kt-window__canvas");
    const handles = { L: host.querySelector('[data-handle="L"]'), R: host.querySelector('[data-handle="R"]') };

    function ms(p) {
      return min + p * span;
    }

    function draw() {
      fill.style.left = `${p0 * 100}%`;
      fill.style.width = `${(p1 - p0) * 100}%`;
      handles.L.style.left = `${p0 * 100}%`;
      handles.R.style.left = `${p1 * 100}%`;
      handles.L.setAttribute("aria-valuetext", fmt(ms(p0)));
      handles.R.setAttribute("aria-valuetext", fmt(ms(p1)));
      const whole = p0 <= 0.001 && p1 >= 0.999;
      label.textContent = whole ? `Tout l'historique · ${fmt(min)} – ${fmt(max)}` : `${fmt(ms(p0))} – ${fmt(ms(p1))}`;
    }

    function drawTicks() {
      const first = new Date(min);
      let cursor = Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + (first.getUTCDate() > 1 ? 1 : 0), 1);
      const starts = [];
      while (cursor <= max) {
        starts.push(cursor);
        const d = new Date(cursor);
        cursor = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
      }
      const step = Math.max(1, Math.ceil(starts.length / 10)); // pas plus d'une dizaine de repères
      host.querySelector(".kt-window__ticks").innerHTML = starts
        .filter((_, i) => i % step === 0)
        .map((t) => {
          const d = new Date(t);
          const text = d.getUTCMonth() === 0 || step > 1 ? `${MONTHS[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}` : MONTHS[d.getUTCMonth()];
          return `<span class="kt-window__tick" style="left:${((t - min) / span) * 100}%">${escapeHtml(text)}</span>`;
        })
        .join("");
    }

    function drawHistogram() {
      const ratio = window.devicePixelRatio || 1;
      const width = Math.max(1, Math.round(track.clientWidth * ratio));
      const height = Math.max(1, Math.round(track.clientHeight * ratio));
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, width, height);
      const bucketMs = Math.max(DAY, span / 52);
      const count = Math.max(1, Math.ceil(span / bucketMs));
      const counts = new Array(count).fill(0);
      for (const t of days) counts[Math.max(0, Math.min(count - 1, Math.floor((t - min) / bucketMs)))]++;
      const top = Math.max(...counts, 1);
      ctx.fillStyle = getComputedStyle(host).getPropertyValue("--accent").trim() || "#1a2f6a";
      ctx.globalAlpha = 0.55;
      const bar = width / count;
      counts.forEach((n, i) => {
        if (!n) return;
        const h = Math.max(2 * ratio, (n / top) * (height - 4 * ratio));
        ctx.fillRect(i * bar + 0.5, height - h, Math.max(1, bar - 1), h);
      });
    }

    let drag = null;
    function down(kind, event) {
      drag = { kind, x: event.clientX, p0, p1 };
      event.preventDefault();
      event.stopPropagation();
    }
    function move(event) {
      if (!drag) return;
      const dx = (event.clientX - drag.x) / track.getBoundingClientRect().width;
      if (drag.kind === "L") p0 = Math.max(0, Math.min(drag.p1 - 0.01, drag.p0 + dx));
      else if (drag.kind === "R") p1 = Math.max(drag.p0 + 0.01, Math.min(1, drag.p1 + dx));
      else {
        const width = drag.p1 - drag.p0;
        p0 = Math.max(0, Math.min(1 - width, drag.p0 + dx));
        p1 = p0 + width;
      }
      draw();
      onChange(ms(p0), ms(p1));
    }
    function up() {
      drag = null;
    }
    handles.L.addEventListener("pointerdown", (e) => down("L", e));
    handles.R.addEventListener("pointerdown", (e) => down("R", e));
    fill.addEventListener("pointerdown", (e) => down("F", e));
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", up);
    track.addEventListener("pointerdown", (event) => {
      if (event.target !== track && event.target !== canvas) return;
      const rect = track.getBoundingClientRect();
      const p = (event.clientX - rect.left) / rect.width;
      if (Math.abs(p - p0) < Math.abs(p - p1)) p0 = Math.max(0, Math.min(p1 - 0.01, p));
      else p1 = Math.max(p0 + 0.01, Math.min(1, p));
      draw();
      onChange(ms(p0), ms(p1));
    });
    // au clavier : les flèches déplacent une poignée d'un jour
    for (const [kind, handle] of Object.entries(handles)) {
      handle.addEventListener("keydown", (event) => {
        const step = ((event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0) * DAY) / span;
        if (!step) return;
        event.preventDefault();
        if (kind === "L") p0 = Math.max(0, Math.min(p1 - 0.01, p0 + step));
        else p1 = Math.max(p0 + 0.01, Math.min(1, p1 + step));
        draw();
        onChange(ms(p0), ms(p1));
      });
    }
    host.querySelector(".kt-window__all").addEventListener("click", () => {
      p0 = 0;
      p1 = 1;
      draw();
      onChange(min, max);
    });
    let observed = 0;
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(() => {
        if (Math.abs(track.clientWidth - observed) > 4) {
          observed = track.clientWidth;
          drawHistogram();
        }
      }).observe(track);
    }

    draw();
    drawTicks();
    drawHistogram();
    return {
      update(next) {
        days = next.days || days;
        drawHistogram();
      },
    };
  }

  return { mount, dayMs, fmt, defaultWindow };
})();
