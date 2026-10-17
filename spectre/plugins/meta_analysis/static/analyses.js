/* Page /analyses : la liste des analyses de plaques (la plus récemment modifiée d'abord) et la création d'une
   analyse - ses plaques se cherchent comme dans la barre du haut (WaferPicker : lasermark, run, lot, µprojet, FDL). ?plaque=<lasermark> : seulement celles où paraît cette plaque (le lien de sa page) ;
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

  // -- les plaques de la nouvelle analyse : la première est la référence ---------------------------
  const MAX_WAFERS = 16; // meta_analysis.service.MAX_WAFERS
  const chosen = [];
  const chipsEl = document.getElementById("new-chips");
  const pickerInput = document.getElementById("new-picker");
  const has = (key) => chosen.some((l) => WaferPicker.keyOf(l) === key);

  function renderChosen() {
    chipsEl.innerHTML = chosen
      .map(
        (l, i) => `<li class="ma-chip${i === 0 ? " is-ref" : ""}">${i === 0 ? `<span class="ma-chip__ref">Réf.</span>` : ""}<span class="mono">${escapeHtml(l)}</span>
          ${i ? `<button type="button" class="ma-chip__btn js-make-ref" data-index="${i}" aria-label="Prendre ${escapeHtml(l)} comme référence" title="Prendre comme référence"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 4v16"/><path d="M20 12H9"/><path d="m13 8-4 4 4 4"/></svg></button>` : ""}
          <button type="button" class="ma-chip__btn ma-chip__remove js-remove" data-index="${i}" aria-label="Retirer ${escapeHtml(l)}" title="Retirer"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg></button></li>`
      )
      .join("");
    chipsEl.hidden = !chosen.length;
    pickerInput.disabled = chosen.length >= MAX_WAFERS;
  }

  function add(lasermarks) {
    const fresh = lasermarks.filter((l) => !has(WaferPicker.keyOf(l)));
    const room = MAX_WAFERS - chosen.length;
    chosen.push(...fresh.slice(0, room));
    showError(fresh.length > room ? new Error(`Une analyse compare ${MAX_WAFERS} plaques au plus : ${room} ajoutée${room > 1 ? "s" : ""} sur ${fresh.length}.`) : null);
    renderChosen();
  }

  WaferPicker.mount({ input: pickerInput, listbox: document.getElementById("new-picker-options"), has, onPick: add });
  chipsEl.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const [lasermark] = chosen.splice(Number(button.dataset.index), 1);
    if (button.classList.contains("js-make-ref")) chosen.unshift(lasermark);
    renderChosen();
  });

  function openForm(open) {
    form.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    if (open) (chosen.length ? form.elements.title : pickerInput).focus();
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
        wafers: chosen,
      });
      location.href = `/analyses/${encodeURIComponent(analysis.id)}`;
    } catch (err) {
      showError(err);
      button.disabled = false;
    }
  });

  const ref = (params.get("ref") || "").trim();
  renderChosen();
  if (ref) {
    add([ref, ...splitLasermarks(params.get("plaques"))]);
    openForm(true);
  }
  load();
})();
