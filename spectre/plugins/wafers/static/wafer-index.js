/* L'index des plaques (wafer-index.html, /plaques) : toutes celles que Spectre connaît, un champ de
   recherche, un tri. La recherche part au serveur (wafersApi.list) : par lasermark (q) et par FDL
   (fdl), les deux à la fois - un « 1234 » est une FDL, un « W12 » un lasermark, le serveur ne rend
   que celles qui correspondent à l'un ou à l'autre, le lasermark exact d'abord. Une plaque d'un
   µprojet dont on n'est pas membre s'y montre sans FDL ni emplacement (règle de visibilité du plugin). */

const PAGE_SIZE = 100;
const state = { wafers: [], sort: "lasermark", shown: PAGE_SIZE, query: "", token: 0 };

const rowsEl = document.getElementById("wafer-rows");
const tableEl = document.getElementById("wafer-table");
const countEl = document.getElementById("wafer-count");
const emptyEl = document.getElementById("wafer-empty");
const moreEl = document.getElementById("wafer-more");
const errorEl = document.getElementById("error");

function showError(err) {
  errorEl.textContent = err.message || String(err);
  errorEl.style.display = "block";
}

function debounce(fn, ms = 250) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// Les plaques dont le lasermark ou une FDL correspond : les deux recherches ensemble, une plaque une
// fois (le lasermark d'abord, puis la FDL). Sans texte, toutes les plaques.
async function search(query) {
  const text = query.trim();
  if (!text) return wafersApi.list({});
  const [byLasermark, byFdl] = await Promise.all([wafersApi.list({ q: text }), wafersApi.list({ fdl: text })]);
  const seen = new Set(byLasermark.map((w) => w.key));
  return [...byLasermark, ...byFdl.filter((w) => !seen.has(w.key))];
}

function sorted(wafers) {
  const list = [...wafers];
  if (state.sort === "recent") {
    list.sort((a, b) => String(b.latest.experiment.updated_at).localeCompare(String(a.latest.experiment.updated_at)));
  } else if (!state.query.trim()) {
    list.sort((a, b) => a.lasermark.localeCompare(b.lasermark, "fr", { numeric: true }));
  } // une recherche garde l'ordre du serveur : la plaque exacte, puis celles qui commencent par ce texte
  return list;
}

function microprojectsHtml(wafer) {
  return wafer.microprojects
    .map((m) => `<a class="fiche-code" href="/microprojets/${encodeURIComponent(m.slug)}" title="${escapeHtml(m.name)}">${escapeHtml(m.code || m.name)}</a>`)
    .join(" ");
}

function rowHtml(wafer) {
  const latest = wafer.latest.experiment;
  const title = latest.member ? `<span class="wafer-index__study" title="${escapeHtml(latest.title)}">${escapeHtml(latest.title)}</span>` : "";
  return `
    <tr>
      <td><a class="wafer-index__lasermark mono" href="${plateUrl(wafer.lasermark)}">${escapeHtml(wafer.lasermark)}</a></td>
      <td>${microprojectsHtml(wafer)}</td>
      <td class="mono">${wafer.count}</td>
      <td>${fdlChipsHtml(wafer.fdl, { label: false }) || '<span class="help">—</span>'}</td>
      <td>${wafer.locations.length ? escapeHtml(wafer.locations[0]) : '<span class="help">—</span>'}</td>
      <td>
        <div class="wafer-index__latest">${statusBadgeHtml(latest.status)}${title}</div>
        <div class="help wafer-index__date">${escapeHtml(formatDate(latest.updated_at))}</div>
      </td>
    </tr>`;
}

function render() {
  const list = sorted(state.wafers);
  const visible = list.slice(0, state.shown);
  rowsEl.innerHTML = visible.map(rowHtml).join("");
  tableEl.setAttribute("aria-busy", "false");
  tableEl.hidden = !list.length;
  moreEl.hidden = list.length <= state.shown;
  countEl.textContent = `${list.length} plaque${list.length > 1 ? "s" : ""}`;
  emptyEl.hidden = list.length > 0;
  if (!list.length) {
    emptyEl.textContent = state.query.trim()
      ? `Aucune plaque ne correspond à « ${state.query.trim()} ». Une plaque est connue dès qu'une étude la suit : son lasermark se renseigne dans la carte « Plaques & entités physiques » d'une fiche, ou au lancement d'une expérience.`
      : "Aucune plaque n'est encore suivie par une étude.";
  }
}

async function load() {
  const token = ++state.token;
  try {
    const wafers = await search(state.query);
    if (token !== state.token) return; // une recherche plus récente est partie entre-temps
    errorEl.style.display = "none";
    state.wafers = wafers;
    state.shown = PAGE_SIZE;
    render();
  } catch (err) {
    if (token === state.token) showError(err);
  }
}

document.getElementById("wafer-search").addEventListener(
  "input",
  debounce((event) => {
    state.query = event.target.value;
    load();
  })
);

document.querySelectorAll("[data-sort]").forEach((button) => {
  button.addEventListener("click", () => {
    state.sort = button.dataset.sort;
    document.querySelectorAll("[data-sort]").forEach((b) => {
      const active = b === button;
      b.classList.toggle("active", active);
      b.setAttribute("aria-pressed", String(active));
    });
    render();
  });
});

document.getElementById("wafer-more-btn").addEventListener("click", () => {
  state.shown += PAGE_SIZE;
  render();
});

load();
