/* Page /analyses : la liste des analyses de plaques (la plus récemment modifiée d'abord) et la création d'une
   analyse. ?plaque=<lasermark> : seulement celles où paraît cette plaque (le lien de sa page) ;
   ?ref=<lasermark>&plaques=a,b : ouvre le formulaire prérempli (« Nouvelle analyse » depuis une plaque). */

(() => {
  const params = new URLSearchParams(location.search);
  const wafer = (params.get("plaque") || "").trim();
  const form = document.getElementById("new-analysis");
  const toggle = document.getElementById("new-toggle");
  const errorEl = document.getElementById("error");
  const listEl = document.getElementById("list");

  function showError(err) {
    errorEl.textContent = err ? err.message || String(err) : "";
    errorEl.hidden = !err;
  }

  function splitLasermarks(text) {
    return String(text || "")
      .split(/[\n,;]+/)
      .map((value) => value.trim())
      .filter(Boolean);
  }

  function openForm(open) {
    form.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) form.elements[form.elements.ref.value ? "title" : "ref"].focus();
  }

  function chipsHtml(analysis) {
    return analysis.wafers
      .map(
        (w, i) =>
          `<span class="ma-chip${i === 0 ? " is-ref" : ""}">${i === 0 ? `<span class="ma-chip__ref">Réf.</span>` : ""}<span class="mono">${escapeHtml(w.lasermark)}</span></span>`
      )
      .join("");
  }

  function cardHtml(analysis) {
    return `
      <a class="card ma-item" href="/analyses/${encodeURIComponent(analysis.id)}">
        <div class="ma-item__main">
          <h2 class="ma-item__title">${escapeHtml(analysis.title)}</h2>
          ${analysis.question ? `<p class="ma-item__question">${escapeHtml(analysis.question)}</p>` : ""}
          <div class="ma-chips">${chipsHtml(analysis)}</div>
        </div>
        <div class="ma-item__meta">
          <span>${analysis.wafers.length} plaque${analysis.wafers.length > 1 ? "s" : ""}</span>
          ${analysis.conclusion ? `<span class="ma-item__concluded">Conclusion écrite</span>` : ""}
          <span>${escapeHtml(analysis.updated_by)} · ${escapeHtml(formatDate(analysis.updated_at))}</span>
        </div>
      </a>`;
  }

  async function load() {
    try {
      const analyses = await metaAnalysisApi.list(wafer ? { wafer } : {});
      listEl.innerHTML = analyses.length
        ? analyses.map(cardHtml).join("")
        : `<div class="card card-pad ma-empty"><p>${
            wafer ? `Aucune analyse ne porte encore sur la plaque <strong class="mono">${escapeHtml(wafer)}</strong>.` : "Aucune analyse pour l'instant."
          }</p><p class="help" style="margin:0;">« Nouvelle analyse » : une plaque de référence, celles qu'on lui compare, et la question qu'on leur pose.</p></div>`;
    } catch (err) {
      listEl.innerHTML = "";
      showError(err);
    }
  }

  if (wafer) {
    const filter = document.getElementById("filter");
    filter.innerHTML = `Les analyses où paraît la plaque <a class="mono" href="/plaques/${encodeURIComponent(wafer)}">${escapeHtml(wafer)}</a> · <a href="/analyses">toutes les analyses</a>`;
    filter.hidden = false;
  }

  toggle.addEventListener("click", () => openForm(form.hidden));
  document.getElementById("new-cancel").addEventListener("click", () => openForm(false));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    showError(null);
    const button = form.querySelector("[type=submit]");
    button.disabled = true;
    try {
      const analysis = await metaAnalysisApi.create({
        title: form.elements.title.value,
        question: form.elements.question.value,
        wafers: [form.elements.ref.value.trim(), ...splitLasermarks(form.elements.others.value)],
      });
      location.href = `/analyses/${encodeURIComponent(analysis.id)}`;
    } catch (err) {
      showError(err);
      button.disabled = false;
    }
  });

  const ref = (params.get("ref") || "").trim();
  if (ref) {
    form.elements.ref.value = ref;
    form.elements.others.value = splitLasermarks(params.get("plaques")).join("\n");
    openForm(true);
  }
  load();
})();
