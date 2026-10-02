/* « Ajouter au lot », depuis un µprojet - le panneau d'un nœud du graphe (lineage-view.js) et la
   carte « Plaques » de la fiche d'une expérience (experiment.js) : met un ou plusieurs wafers de
   l'expérience (ses lasermarks) dans un lot - en cours ou déjà sorti, à tout moment, autant de fois
   qu'on veut - ou dans un nouveau lot créé sur place. Voir /lots et spectre.api.lots (GET /selection,
   POST /{code}/wafers, POST ""). Dépend de common.js. */

let lotAssignCount = 0;

// Dès que son wafer entre dans le lot, l'expérience y est rattachée (même terminée). `onChange(code)`
// après chaque ajout.
function mountLotAssign(container, { lasermarks = [], onChange } = {}) {
  const key = (text) => (text || "").replace(/[\s_\-./#:]/g, "").toUpperCase(); // = spectre.core.plates.compact
  const marks = [];
  for (const mark of lasermarks) {
    if (mark && !marks.some((m) => key(m) === key(mark))) marks.push(mark);
  }
  if (!marks.length) {
    container.innerHTML = `<p class="help">Renseignez d'abord le lasermark de la plaque (suivi physique) pour la mettre dans un lot.</p>`;
    return;
  }
  const id = `lot-assign-${(lotAssignCount += 1)}`;
  let lots = [];

  const label = (l) => `${l.priority ? `${l.priority} · ` : ""}${l.code}${l.title ? ` — ${l.title}` : ""}`;
  const holds = (l, mark) => l.wafers.some((w) => key(w) === key(mark));
  const findLot = (code) => lots.find((l) => key(l.code) === key(code));
  const chosen = () =>
    marks.length === 1 ? marks : [...container.querySelectorAll(`input[name="${id}-wafer"]:checked`)].map((i) => i.value);

  function current() {
    const rows = marks
      .map((mark) => {
        const found = lots.filter((l) => holds(l, mark));
        return found.length
          ? `<li><span class="lot-assign__mark">${escapeHtml(mark)}</span> ${found.map((l) => `<a class="lineage-lot-chip" href="/lots/${encodeURIComponent(l.code)}">${escapeHtml(l.code)}</a>`).join(" ")}</li>`
          : "";
      })
      .join("");
    return rows ? `<ul class="lot-assign__current" aria-label="Wafers déjà dans un lot">${rows}</ul>` : "";
  }

  // les lots en cours (P10 d'abord), puis ceux déjà sortis - un lot qui contient déjà tous les wafers
  // cochés est grisé (rien à y ajouter)
  function options() {
    const wanted = chosen();
    const option = (l) => {
      const all = wanted.length && wanted.every((m) => holds(l, m));
      return `<option value="${escapeHtml(l.code)}"${all ? " disabled" : ""}>${escapeHtml(label(l))}${all ? " (déjà dedans)" : ""}</option>`;
    };
    const active = lots.filter((l) => l.status !== "done");
    const done = lots.filter((l) => l.status === "done");
    return `${active.length ? `<optgroup label="En cours">${active.map(option).join("")}</optgroup>` : ""}${
      done.length ? `<optgroup label="Sortis">${done.map(option).join("")}</optgroup>` : ""
    }<option value="__new">+ Nouveau lot…</option>`;
  }

  // Le lot présélectionné : celui qu'on préfère (le dernier utilisé, le choix en cours) s'il peut encore
  // recevoir les wafers cochés, sinon le premier lot qui le peut - « Nouveau lot » seulement s'il n'y en
  // a aucun (avant, on y basculait sans le dire, et taper le code d'un lot existant tentait de le recréer).
  function pick(select, preferred) {
    const usable = [...select.options].filter((o) => !o.disabled);
    for (const wanted of preferred) {
      if (wanted && usable.some((o) => o.value === wanted)) {
        select.value = wanted;
        return;
      }
    }
    const firstLot = usable.find((o) => o.value !== "__new");
    select.value = firstLot ? firstLot.value : "__new";
  }

  function render(message = "", isError = false, preferred = null) {
    const previous = container.querySelector(`#${id}-lot`);
    const keep = previous ? previous.value : "";
    container.innerHTML = `
      <form class="lot-assign" novalidate>
        ${current()}
        ${
          marks.length > 1
            ? `<fieldset class="lot-assign__wafers"><legend>Wafers à ajouter</legend>${marks
                .map((m) => `<label><input type="checkbox" name="${id}-wafer" value="${escapeHtml(m)}" checked> ${escapeHtml(m)}</label>`)
                .join("")}</fieldset>`
            : `<div class="lot-assign__single">Wafer <span class="lot-assign__mark">${escapeHtml(marks[0])}</span></div>`
        }
        <label for="${id}-lot">Ajouter au lot</label>
        <div class="lot-assign__row">
          <select class="field" id="${id}-lot">${options()}</select>
          <button type="submit" class="btn btn-line btn-sm">Ajouter</button>
        </div>
        <div class="lot-assign__new" hidden>
          <input class="field" id="${id}-code" maxlength="40" placeholder="Code du nouveau lot (vide = auto)" aria-label="Code du nouveau lot">
          <input class="field" id="${id}-priority" maxlength="10" list="${id}-priorities" placeholder="Priorité" aria-label="Priorité du nouveau lot">
          <input class="field" id="${id}-forecast" type="date" aria-label="Fin prévisionnelle du nouveau lot" title="Fin prévisionnelle">
          <datalist id="${id}-priorities"><option value="P10"><option value="P20"><option value="P30"><option value="P40"><option value="P50"></datalist>
        </div>
        <div class="lot-assign__msg${isError ? " is-error" : ""}" role="status">${message}</div>
      </form>`;
    pick(container.querySelector(`#${id}-lot`), [preferred, keep === "__new" ? null : keep]);
    syncNew();
  }

  function syncNew() {
    const isNew = container.querySelector(`#${id}-lot`).value === "__new";
    container.querySelector(".lot-assign__new").hidden = !isNew;
  }

  async function load(message, isError, preferred) {
    try {
      lots = await api.get("/api/lots/selection");
      render(message, isError, preferred);
    } catch (err) {
      container.innerHTML = `<p class="help">Lots indisponibles : ${escapeHtml(err.message || String(err))}</p>`;
    }
  }

  container.addEventListener("change", (event) => {
    if (event.target.name === `${id}-wafer`) {
      const sel = container.querySelector(`#${id}-lot`);
      const keep = sel.value;
      sel.innerHTML = options();
      pick(sel, [keep]);
    }
    if (event.target.id === `${id}-lot` || event.target.name === `${id}-wafer`) syncNew();
  });

  container.addEventListener("submit", async (event) => {
    event.preventDefault();
    const wafers = chosen();
    if (!wafers.length) return render("Cochez au moins un wafer.", true);
    let target = container.querySelector(`#${id}-lot`).value;
    const typedCode = container.querySelector(`#${id}-code`).value.trim();
    let note = "";
    if (target === "__new" && typedCode) {
      // le code d'un lot qui existe déjà : on y ajoute les wafers plutôt que de tenter de le recréer
      const existing = findLot(typedCode);
      if (existing) {
        target = existing.code;
        note = " (lot existant)";
      } else {
        try {
          target = (await api.get(`/api/lots/${encodeURIComponent(typedCode)}`)).code; // annulé : absent de la liste
          note = " (lot existant)";
        } catch (err) {
          /* introuvable : on le crée */
        }
      }
    }
    const button = container.querySelector('button[type="submit"]');
    button.disabled = true;
    try {
      const lot =
        target === "__new"
          ? await api.post("/api/lots", {
              code: typedCode || null,
              priority: container.querySelector(`#${id}-priority`).value,
              forecast_exit_on: container.querySelector(`#${id}-forecast`).value || null,
              wafers,
            })
          : await api.post(`/api/lots/${encodeURIComponent(target)}/wafers`, { lasermarks: wafers });
      await load(
        `${escapeHtml(wafers.join(", "))} ${wafers.length > 1 ? "ajoutés" : "ajouté"} au lot <a href="/lots/${encodeURIComponent(lot.code)}">${escapeHtml(lot.code)}</a>${note} - l'expérience y est rattachée.`,
        false,
        lot.code
      );
      if (onChange) onChange(lot.code);
    } catch (err) {
      button.disabled = false;
      const msg = container.querySelector(".lot-assign__msg");
      msg.className = "lot-assign__msg is-error";
      msg.textContent = err.message || String(err);
    }
  });

  container.innerHTML = `<p class="help">Chargement des lots…</p>`;
  load();
}
