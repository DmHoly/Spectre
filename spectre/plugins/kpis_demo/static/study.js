/* La fiche (fictive) d'une étude derrière un point d'une tendance de démonstration : un dialogue
   créé au premier appel, ouvert par KpisDemo.openStudy(areaSlug, kpiKey, studyId). La page d'un
   projet ne charge ce fichier (et client.js, kpis_demo.css) qu'au premier clic sur un tel point :
   seules les séries de démonstration en portent, et le plugin n'est actif qu'avec SPECTRE_DEMO_DATA=1.
   Dépend de kernel/static/ui.js (escapeHtml) et d'experiments/static/status.js (statusBadgeHtml). */

const KpisDemo = (function () {
  const DIRECTION_LABELS = { maximize: "Maximiser", minimize: "Minimiser", target: "Cible précise", observe: "Observer" };
  let dialog = null;
  let current = null; // {areaSlug, kpiKey} de la fiche affichée

  // Vue symbolique de l'arbre d'expériences : la ligne principale des études (en haut), les pistes
  // secondaires en dessous ; le chemin jusqu'à l'étude affichée est tracé, la suite estompée.
  function treeSvg(tree) {
    const colW = 118;
    const laneH = 58;
    const pad = 52; // place pour les libellés centrés sous les nœuds des bords
    const cols = Math.max(...tree.nodes.map((n) => n.col)) + 1;
    const lanes = Math.max(...tree.nodes.map((n) => n.lane)) + 1;
    const width = pad * 2 + (cols - 1) * colW;
    const height = pad + (lanes - 1) * laneH + 34;
    const pos = new Map(tree.nodes.map((n) => [n.id, { x: pad + n.col * colW, y: pad + n.lane * laneH, node: n }]));
    const edges = tree.edges
      .map(([from, to]) => {
        const a = pos.get(from);
        const b = pos.get(to);
        const onPath = b.node.state !== "future" && a.node.state !== "future";
        const d = a.y === b.y ? `M${a.x},${a.y} L${b.x},${b.y}` : `M${a.x},${a.y} C${a.x + colW * 0.55},${a.y} ${b.x - colW * 0.55},${b.y} ${b.x},${b.y}`;
        return `<path class="tree-edge${onPath ? " is-path" : ""}" d="${d}"/>`;
      })
      .join("");
    const nodes = tree.nodes
      .map((n) => {
        const { x, y } = pos.get(n.id);
        const status = n.status === "abandoned" ? " is-abandoned" : n.status === "inconclusive" ? " is-inconclusive" : "";
        const study = n.lane === 0 ? ` data-study="${escapeHtml(n.id)}" tabindex="0" role="button" aria-label="Ouvrir l'étude ${escapeHtml(n.title)}"` : "";
        return `<g class="tree-node is-${n.state}${status}" transform="translate(${x},${y})"${study}>
            <title>${escapeHtml(n.title)}</title>
            <circle r="${n.state === "current" ? 10 : 8}"></circle>
            <text y="24" text-anchor="middle">${escapeHtml(n.label)}</text>
          </g>`;
      })
      .join("");
    return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Arbre des expériences de l'étude">${edges}${nodes}</svg>`;
  }

  function studyHtml(study) {
    const r = study.result;
    const delta = r.previous != null ? `<span class="study__result-delta">${r.value - r.previous >= 0 ? "+" : ""}${(r.value - r.previous).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} pt</span> vs étude précédente · ` : "";
    const o = study.objective;
    const [year, month] = study.period.split("-");
    const when = new Date(Number(year), Number(month) - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
    return `
      <div class="study__head">
        <div>
          <div class="study__badges">
            ${study.demo ? `<span class="study__demo">Démo · fiche fictive</span>` : ""}
            <span class="study__where">${escapeHtml(study.project)} › ${escapeHtml(study.microproject)} · conclue en ${escapeHtml(when)}</span>
          </div>
          <h2 class="study__title" id="study-title">${escapeHtml(study.title)}</h2>
          <p class="study__change">${escapeHtml(study.change)}</p>
        </div>
        <button type="button" class="btn btn-line btn-sm" id="study-close">Fermer</button>
      </div>
      <div class="study__grid">
        <div class="study__panel">
          <div class="study__panel-title">Structure</div>
          <div class="study__svg">${study.structure_svg}</div>
          <div class="study__legend">${study.materials.map((m) => `<span><i style="background:${escapeHtml(study.material_colors[m] || "var(--text-faint)")};"></i>${escapeHtml(m)}</span>`).join("")}</div>
          <details class="study__steps"><summary>Procédé (${study.steps.length} étapes)</summary><ol>${study.steps.map((name) => `<li>${escapeHtml(name)}</li>`).join("")}</ol></details>
        </div>
        <div>
          <div class="study__panel">
            <div class="study__panel-title">Résultat</div>
            <div class="study__result">
              <span class="study__result-value">${escapeHtml(r.metric)} ${r.value.toLocaleString("fr-FR")} ${escapeHtml(r.unit)}</span>
            </div>
            <div class="study__result-meta">${delta}objectif ${r.target.toLocaleString("fr-FR")} ${escapeHtml(r.unit)}</div>
          </div>
          <div class="study__panel">
            <div class="study__panel-title">Objectif</div>
            <div class="study__objective-name">${escapeHtml(o.name)}</div>
            <div class="study__meta">${escapeHtml(DIRECTION_LABELS[o.direction] || o.direction)} · cible ${o.target.toLocaleString("fr-FR")} % · <strong>${escapeHtml(o.status)}</strong></div>
            <div class="study__meta">${escapeHtml(o.rationale)}</div>
          </div>
          <div class="study__panel">
            <div class="study__panel-title">Conclusion</div>
            ${statusBadgeHtml("concluded", study.conclusion.decision)}
            <p class="study__conclusion">${escapeHtml(study.conclusion.summary)}</p>
          </div>
        </div>
      </div>
      <div class="study__panel study__tree">
        <div class="study__panel-title">Arbre d'expériences</div>
        ${treeSvg(study.tree)}
        <div class="tree-legend"><span>● étude de la ligne principale (cliquer pour l'ouvrir)</span><span>◌ piste abandonnée ou non concluante</span></div>
      </div>`;
  }

  function ensureDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "study-dialog";
    dialog.setAttribute("aria-labelledby", "study-title");
    dialog.innerHTML = `<div class="study"></div>`;
    document.body.appendChild(dialog);
    const box = dialog.firstElementChild;
    box.addEventListener("click", (event) => {
      if (event.target.closest("#study-close")) return dialog.close();
      const node = event.target.closest("[data-study]");
      if (node) openStudy(current.areaSlug, current.kpiKey, node.dataset.study);
    });
    box.addEventListener("keydown", (event) => {
      const node = event.target.closest && event.target.closest("[data-study]");
      if (node && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        openStudy(current.areaSlug, current.kpiKey, node.dataset.study);
      }
    });
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close(); // clic sur le fond
    });
    return dialog;
  }

  async function openStudy(areaSlug, kpiKey, studyId) {
    if (!kpiKey || !studyId) return;
    const box = ensureDialog().firstElementChild;
    current = { areaSlug, kpiKey };
    if (!dialog.open) {
      box.innerHTML = `<div class="skeleton" style="height:420px;"></div>`;
      dialog.showModal();
    }
    try {
      box.innerHTML = studyHtml(await kpisDemoApi.study(areaSlug, kpiKey, studyId));
      document.getElementById("study-close").focus();
    } catch (err) {
      box.innerHTML = `<div class="error">${escapeHtml(err.message || String(err))}</div><button type="button" class="btn btn-line btn-sm" id="study-close" style="margin-top:12px;">Fermer</button>`;
    }
  }

  return { openStudy };
})();
