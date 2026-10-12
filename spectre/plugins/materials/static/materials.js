/* Page /materiaux : l'éditeur de la bibliothèque de matériaux (materiaux.yml). Le serveur donne un
   document (materialsApi.library) - les matériaux du sélecteur et les dégradés de couleur de l'InGaN et
   de l'AlGaN - que la page modifie en brouillon, puis renvoie en entier (materialsApi.saveLibrary) : il
   le valide, le réécrit dans le fichier et le relit. Rien n'est écrit avant « Enregistrer » ; « Annuler »
   revient au document lu. Un administrateur seul modifie (les autres lisent) ; si le fichier a changé
   depuis la lecture, l'enregistrement est refusé (409) plutôt que d'écraser l'autre modification. */

(function () {
  const FAMILIES = [
    { key: "InGaN", symbol: "In", title: "InGaN", formula: "In<sub>x</sub>Ga<sub>1-x</sub>N", hint: "x = taux d'indium" },
    { key: "AlGaN", symbol: "Al", title: "AlGaN", formula: "Al<sub>y</sub>Ga<sub>1-y</sub>N", hint: "y = taux d'aluminium" },
  ];
  const SAMPLE_RATES = [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1];
  const HEX = /^#[0-9a-fA-F]{6}$/;
  const NEW_MATERIAL_COLOR = "#9e9e9e";

  const el = (id) => document.getElementById(id);
  const errorBox = el("error");
  const state = { doc: null, draft: null, filter: "", saving: false, nextId: 1 };

  const icons = {
    up: '<path d="m6 15 6-6 6 6"/>',
    down: '<path d="m6 9 6 6 6-6"/>',
    trash: '<path d="M4 7h16"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M6 7l1 13h10l1-13"/><path d="M9 7V4h6v3"/>',
  };
  const icon = (name) =>
    `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name]}</svg>`;

  // -- couleurs ---------------------------------------------------------------------------------

  function rgb(hex) {
    return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  }
  function toHex(channels) {
    return "#" + channels.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("");
  }
  // le même mélange que le serveur (structures.library_files.Gradient.color_at) : linéaire canal par canal
  function colorAt(stops, x) {
    const sorted = sortedStops(stops).filter((s) => HEX.test(s.color));
    if (!sorted.length) return NEW_MATERIAL_COLOR;
    if (x <= sorted[0].x) return sorted[0].color;
    const last = sorted[sorted.length - 1];
    if (x >= last.x) return last.color;
    for (let i = 0; i < sorted.length - 1; i++) {
      const a = sorted[i];
      const b = sorted[i + 1];
      if (x >= a.x && x <= b.x) {
        const t = b.x > a.x ? (x - a.x) / (b.x - a.x) : 0;
        const ca = rgb(a.color);
        const cb = rgb(b.color);
        return toHex(ca.map((c, k) => c + (cb[k] - c) * t));
      }
    }
    return last.color;
  }
  function sortedStops(stops) {
    return [...stops].sort((a, b) => a.x - b.x);
  }
  const percent = (x) => Math.round(x * 10000) / 100;
  const rate = (percentValue) => Number((percentValue / 100).toFixed(4));
  function compositionName(symbol, x) {
    return `${symbol}${x.toFixed(2)}Ga${(1 - x).toFixed(2)}N`;
  }

  // -- le brouillon -----------------------------------------------------------------------------

  const clone = (value) => JSON.parse(JSON.stringify(value));

  function toDraft(doc) {
    const draft = { materials: clone(doc.materials), gradients: clone(doc.gradients) };
    draft.materials.forEach((m) => (m._id = state.nextId++));
    return draft;
  }
  // le document tel que le serveur le reçoit : sans les identifiants de ligne, les vides à null
  function toDocument(draft) {
    return {
      revision: state.doc.revision,
      materials: draft.materials.map(({ _id, ...m }) => ({ ...m, notes: m.notes || null })),
      gradients: clone(draft.gradients),
    };
  }
  const comparable = (draft) => JSON.stringify({ m: draft.materials.map(({ _id, ...m }) => ({ ...m, notes: m.notes || null })), g: draft.gradients });
  function pristine() {
    return comparable(toDraftForCompare(state.doc));
  }
  function toDraftForCompare(doc) {
    return { materials: doc.materials, gradients: doc.gradients };
  }
  const isDirty = () => !!state.draft && comparable(state.draft) !== pristine();
  const canEdit = () => !!state.doc && state.doc.can_edit;

  // -- messages ---------------------------------------------------------------------------------

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }
  const clearError = () => (errorBox.hidden = true);

  // -- les dégradés -----------------------------------------------------------------------------

  function gradientCss(stops) {
    const sorted = sortedStops(stops).filter((s) => HEX.test(s.color));
    if (!sorted.length) return "none";
    if (sorted.length === 1) return sorted[0].color;
    return `linear-gradient(to right, ${sorted.map((s) => `${s.color} ${percent(s.x)}%`).join(", ")})`;
  }

  function stopRowHtml(family, stop, index) {
    const disabled = canEdit() ? "" : " disabled";
    const only = state.draft.gradients[family].stops.length <= 2;
    return `
      <li class="mat-stop" data-family="${family}" data-index="${index}">
        <label class="mat-stop__x">
          <span class="visually-hidden">Taux du point ${index + 1} (%)</span>
          <input class="field" type="number" min="0" max="100" step="0.5" value="${percent(stop.x)}" data-stop="x"${disabled}>
          <span class="mat-unit">%</span>
        </label>
        <input type="color" class="mat-color" value="${escapeHtml(stop.color)}" data-stop="picker" aria-label="Couleur du point ${index + 1}"${disabled}>
        <input class="field mat-hex" value="${escapeHtml(stop.color)}" maxlength="7" spellcheck="false" data-stop="hex" aria-label="Couleur du point ${index + 1} en hexadécimal"${disabled}>
        ${canEdit() ? `<button type="button" class="mat-icon-btn" data-act="del-stop" aria-label="Retirer le point ${index + 1}"${only ? " disabled" : ""} title="${only ? "Un dégradé garde au moins deux points" : "Retirer ce point"}">${icon("trash")}</button>` : ""}
      </li>`;
  }

  function gradientCardHtml(family) {
    const gradient = state.draft.gradients[family.key];
    const disabled = canEdit() ? "" : " disabled";
    return `
      <article class="card card-pad mat-gradient" data-family="${family.key}" aria-labelledby="g-${family.key}">
        <header class="mat-gradient__head">
          <h2 id="g-${family.key}">${family.title}</h2>
          <span class="mat-formula">${family.formula} · ${family.hint}</span>
        </header>
        <div class="mat-bar" role="img" aria-label="Dégradé de couleur de l'${family.key} selon le taux, de 0 à 100 %" data-bar>
          <div class="mat-bar__fill" data-fill></div>
          <div class="mat-bar__marks" data-marks></div>
        </div>
        <div class="mat-bar__axis" aria-hidden="true"><span>0 %<br><small>GaN pur</small></span><span>50 %</span><span>100 %</span></div>
        <ul class="mat-chips" data-chips aria-label="Aperçu de compositions"></ul>
        <div class="section-title mat-sub">Points du dégradé</div>
        <ul class="mat-stops" data-stops>${gradient.stops.map((stop, i) => stopRowHtml(family.key, stop, i)).join("")}</ul>
        <div class="mat-gradient__foot">
          <label class="mat-generic">
            <span>Couleur du nom nu « ${family.key} » : taux</span>
            <input class="field" type="number" min="0" max="100" step="0.5" value="${percent(gradient.generic_x)}" data-generic${disabled}>
            <span class="mat-unit">%</span>
          </label>
          ${canEdit() ? `<div class="mat-gradient__actions">
            <button type="button" class="btn btn-line" data-act="add-stop">+ Ajouter un point</button>
            <button type="button" class="btn btn-line" data-act="reset-gradient">Dégradé livré</button>
          </div>` : ""}
        </div>
      </article>`;
  }

  // l'aperçu (barre, repères, pastilles) suit le brouillon à chaque frappe, sans refaire les champs
  function paintGradient(familyKey) {
    const card = document.querySelector(`.mat-gradient[data-family="${familyKey}"]`);
    if (!card) return;
    const family = FAMILIES.find((f) => f.key === familyKey);
    const gradient = state.draft.gradients[familyKey];
    card.querySelector("[data-fill]").style.background = gradientCss(gradient.stops);
    card.querySelector("[data-marks]").innerHTML = gradient.stops
      .filter((s) => HEX.test(s.color))
      .map((s) => `<span class="mat-bar__mark" style="left:${percent(s.x)}%;background:${s.color}" title="${percent(s.x)} %"></span>`)
      .join("");
    card.querySelector("[data-chips]").innerHTML = SAMPLE_RATES.map((x) => {
      const color = colorAt(gradient.stops, x);
      const name = compositionName(family.symbol, x);
      return `<li class="mat-chip" title="${name} · ${color}"><span class="mat-chip__swatch" style="background:${color}"></span><span>${percent(x)} %</span></li>`;
    }).join("");
  }

  function renderGradients() {
    el("gradients").innerHTML = FAMILIES.map(gradientCardHtml).join("");
    el("gradients").removeAttribute("aria-busy");
    FAMILIES.forEach((family) => paintGradient(family.key));
  }

  function stopsOf(familyKey) {
    return state.draft.gradients[familyKey].stops;
  }

  el("gradients").addEventListener("input", (event) => {
    if (!canEdit()) return;
    const target = event.target;
    const card = target.closest(".mat-gradient");
    if (!card) return;
    const familyKey = card.dataset.family;
    if (target.matches("[data-generic]")) {
      const value = parseFloat(target.value);
      if (!Number.isNaN(value)) state.draft.gradients[familyKey].generic_x = rate(Math.min(Math.max(value, 0), 100));
    } else {
      const row = target.closest(".mat-stop");
      if (!row) return;
      const stop = stopsOf(familyKey)[Number(row.dataset.index)];
      const kind = target.dataset.stop;
      if (kind === "x") {
        const value = parseFloat(target.value);
        if (!Number.isNaN(value)) stop.x = rate(Math.min(Math.max(value, 0), 100));
      } else if (kind === "picker") {
        stop.color = target.value;
        row.querySelector('[data-stop="hex"]').value = target.value;
      } else if (kind === "hex") {
        const text = target.value.trim();
        target.setAttribute("aria-invalid", HEX.test(text) ? "false" : "true");
        if (!HEX.test(text)) return;
        stop.color = text.toLowerCase();
        row.querySelector('[data-stop="picker"]').value = stop.color;
      }
    }
    paintGradient(familyKey);
    refreshSaveBar();
  });

  el("gradients").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-act]");
    if (!button || !canEdit()) return;
    const card = button.closest(".mat-gradient");
    const familyKey = card.dataset.family;
    const gradient = state.draft.gradients[familyKey];
    if (button.dataset.act === "add-stop") {
      // au milieu du plus grand écart entre deux points, dans la couleur que le dégradé y a déjà
      const sorted = sortedStops(gradient.stops);
      let best = { gap: -1, x: 0.5 };
      for (let i = 0; i < sorted.length - 1; i++) {
        const gap = sorted[i + 1].x - sorted[i].x;
        if (gap > best.gap) best = { gap, x: (sorted[i].x + sorted[i + 1].x) / 2 };
      }
      const x = rate(percent(best.x));
      gradient.stops.push({ x, color: colorAt(gradient.stops, x) });
    } else if (button.dataset.act === "del-stop") {
      if (gradient.stops.length <= 2) return;
      gradient.stops.splice(Number(button.closest(".mat-stop").dataset.index), 1);
    } else if (button.dataset.act === "reset-gradient") {
      gradient.stops = clone(state.doc.defaults[familyKey].stops);
      gradient.generic_x = state.doc.defaults[familyKey].generic_x;
    }
    const list = card.querySelector("[data-stops]");
    list.innerHTML = gradient.stops.map((stop, i) => stopRowHtml(familyKey, stop, i)).join("");
    card.querySelector("[data-generic]").value = percent(gradient.generic_x);
    paintGradient(familyKey);
    refreshSaveBar();
  });

  // -- les matériaux ----------------------------------------------------------------------------

  function categoryOptions(selected) {
    return state.doc.categories
      .map((c) => `<option value="${escapeHtml(c.value)}"${c.value === selected ? " selected" : ""}>${escapeHtml(c.label)}</option>`)
      .join("");
  }

  function numberValue(value) {
    return value === null || value === undefined ? "" : value;
  }

  function materialRowHtml(material, position, total) {
    const disabled = canEdit() ? "" : " disabled";
    const reorder = canEdit() && !state.filter;
    return `
      <tr data-id="${material._id}">
        <td>
          <div class="mat-colorcell">
            <input type="color" class="mat-color" value="${escapeHtml(material.color)}" data-f="picker" aria-label="Couleur de ${escapeHtml(material.name || "ce matériau")}"${disabled}>
            <input class="field mat-hex" value="${escapeHtml(material.color)}" maxlength="7" spellcheck="false" data-f="hex" aria-label="Couleur de ${escapeHtml(material.name || "ce matériau")} en hexadécimal"${disabled}>
          </div>
        </td>
        <td><input class="field" value="${escapeHtml(material.name)}" maxlength="64" data-f="name" aria-label="Nom"${disabled}></td>
        <td><select class="field" data-f="category" aria-label="Catégorie de ${escapeHtml(material.name || "ce matériau")}"${disabled}>${categoryOptions(material.category)}</select></td>
        <td><input class="field" value="${escapeHtml(material.notes || "")}" maxlength="500" data-f="notes" placeholder="Infobulle, usage…" aria-label="Description de ${escapeHtml(material.name || "ce matériau")}"${disabled}></td>
        <td class="mat-num"><input class="field" type="number" min="0" step="any" value="${numberValue(material.density_g_cm3)}" data-f="density_g_cm3" aria-label="Densité de ${escapeHtml(material.name || "ce matériau")}"${disabled}></td>
        <td class="mat-num"><input class="field" type="number" min="0" step="any" value="${numberValue(material.refractive_index)}" data-f="refractive_index" aria-label="Indice de réfraction de ${escapeHtml(material.name || "ce matériau")}"${disabled}></td>
        <td class="mat-actions">
          ${reorder ? `<button type="button" class="mat-icon-btn" data-act="up" aria-label="Monter ${escapeHtml(material.name)}"${position === 0 ? " disabled" : ""}>${icon("up")}</button>
          <button type="button" class="mat-icon-btn" data-act="down" aria-label="Descendre ${escapeHtml(material.name)}"${position === total - 1 ? " disabled" : ""}>${icon("down")}</button>` : ""}
          ${canEdit() ? `<button type="button" class="mat-icon-btn mat-icon-btn--danger" data-act="delete" aria-label="Retirer ${escapeHtml(material.name)}">${icon("trash")}</button>` : ""}
        </td>
      </tr>`;
  }

  function matches(material) {
    const needle = state.filter.trim().toLowerCase();
    if (!needle) return true;
    return [material.name, material.notes, material.category].some((text) => (text || "").toLowerCase().includes(needle));
  }

  function renderMaterials() {
    const all = state.draft.materials;
    const visible = all.filter(matches);
    el("materials-body").innerHTML = visible.length
      ? visible.map((material) => materialRowHtml(material, all.indexOf(material), all.length)).join("")
      : `<tr><td colspan="7" class="mat-empty">${all.length ? "Aucun matériau ne correspond au filtre." : "Aucun matériau : ajoutez-en un."}</td></tr>`;
    renderKnownOptions();
  }

  function renderKnownOptions() {
    const listed = new Set(state.draft.materials.map((m) => m.name.toLowerCase()));
    const select = el("add-known");
    const labels = Object.fromEntries(state.doc.categories.map((c) => [c.value, c.label]));
    select.innerHTML =
      '<option value="">Ajouter depuis StructureForge…</option>' +
      state.doc.available
        .filter((m) => !listed.has(m.name.toLowerCase()))
        .map((m) => `<option value="${escapeHtml(m.name)}">${escapeHtml(m.name)} — ${escapeHtml(labels[m.category] || m.category)}</option>`)
        .join("");
  }

  const materialOf = (row) => state.draft.materials.find((m) => String(m._id) === row.dataset.id);

  el("materials-body").addEventListener("input", (event) => {
    if (!canEdit()) return;
    const target = event.target;
    const row = target.closest("tr[data-id]");
    const field = target.dataset.f;
    if (!row || !field) return;
    const material = materialOf(row);
    if (field === "picker") {
      material.color = target.value;
      row.querySelector('[data-f="hex"]').value = target.value;
    } else if (field === "hex") {
      const text = target.value.trim();
      target.setAttribute("aria-invalid", HEX.test(text) ? "false" : "true");
      if (!HEX.test(text)) return;
      material.color = text.toLowerCase();
      row.querySelector('[data-f="picker"]').value = material.color;
    } else if (field === "density_g_cm3" || field === "refractive_index") {
      material[field] = target.value === "" ? null : Number(target.value);
    } else {
      material[field] = target.value;
    }
    if (field === "name") renderKnownOptions();
    refreshSaveBar();
  });

  el("materials-body").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-act]");
    if (!button || !canEdit()) return;
    const materials = state.draft.materials;
    const material = materialOf(button.closest("tr"));
    const index = materials.indexOf(material);
    if (button.dataset.act === "delete") {
      materials.splice(index, 1);
    } else if (button.dataset.act === "up" && index > 0) {
      [materials[index - 1], materials[index]] = [materials[index], materials[index - 1]];
    } else if (button.dataset.act === "down" && index < materials.length - 1) {
      [materials[index + 1], materials[index]] = [materials[index], materials[index + 1]];
    }
    renderMaterials();
    refreshSaveBar();
    const again = el("materials-body").querySelector(`tr[data-id="${material._id}"] button[data-act="${button.dataset.act}"]`);
    if (again && !again.disabled) again.focus();
  });

  function appendMaterial(material) {
    state.filter = "";
    el("filter").value = "";
    const added = { notes: null, density_g_cm3: null, refractive_index: null, ...clone(material), _id: state.nextId++ };
    state.draft.materials.push(added);
    renderMaterials();
    refreshSaveBar();
    const row = el("materials-body").querySelector(`tr[data-id="${added._id}"]`);
    row.scrollIntoView({ block: "center", behavior: "smooth" });
    row.querySelector('[data-f="name"]').focus();
  }

  el("add-material").addEventListener("click", () => appendMaterial({ name: "", category: "other", color: NEW_MATERIAL_COLOR }));
  el("add-known").addEventListener("change", (event) => {
    const known = state.doc.available.find((m) => m.name === event.target.value);
    event.target.value = "";
    if (known) appendMaterial(known);
  });
  el("filter").addEventListener("input", (event) => {
    state.filter = event.target.value;
    renderMaterials();
  });

  // -- enregistrer ------------------------------------------------------------------------------

  const saveBar = el("savebar");
  let savedTimer = null;

  function refreshSaveBar() {
    if (!canEdit() || state.saving) return;
    const dirty = isDirty();
    if (dirty) {
      window.clearTimeout(savedTimer);
      saveBar.dataset.state = "dirty";
      el("savebar-text").textContent = "Modifications non enregistrées.";
    }
    saveBar.hidden = !dirty && saveBar.dataset.state !== "saved";
  }

  function flashSaved() {
    saveBar.dataset.state = "saved";
    saveBar.hidden = false;
    el("savebar-text").textContent = "Enregistré ✓ - c'est pris en compte partout, sans redémarrage.";
    window.clearTimeout(savedTimer);
    savedTimer = window.setTimeout(() => {
      saveBar.dataset.state = "";
      refreshSaveBar();
    }, 3000);
  }

  function load(doc) {
    state.doc = doc;
    state.draft = toDraft(doc);
    el("readonly").hidden = doc.can_edit;
    el("materials-toolbar").hidden = false;
    el("add-material").hidden = el("add-known").parentElement.hidden = !doc.can_edit;
    const problem = el("problem");
    problem.hidden = !doc.problem;
    if (doc.problem) {
      problem.textContent = `Le fichier materiaux.yml est invalide (${doc.problem}) : l'application utilise le jeu intégré, affiché ici. L'enregistrer remplace le fichier par ce que vous voyez.`;
    }
    renderGradients();
    renderMaterials();
    refreshSaveBar();
  }

  el("save").addEventListener("click", async () => {
    clearError();
    state.saving = true;
    el("save").disabled = true;
    try {
      load(await materialsApi.saveLibrary(toDocument(state.draft)));
      state.saving = false;
      flashSaved();
    } catch (err) {
      state.saving = false;
      showError(err.status === 409 ? `${err.message}\n(Vos modifications restent à l'écran : copiez-les au besoin avant de recharger.)` : err.message || String(err));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      state.saving = false;
      el("save").disabled = false;
    }
  });

  el("discard").addEventListener("click", () => {
    clearError();
    load(state.doc);
  });

  window.addEventListener("beforeunload", (event) => {
    if (isDirty()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  materialsApi
    .library()
    .then(load)
    .catch((err) => showError(err.message || String(err)));
})();
