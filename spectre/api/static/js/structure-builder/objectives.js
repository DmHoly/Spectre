/* Objectifs et intention de l'expérience (mode expérience uniquement). */

// Rempli par intention-copy.js une fois la config `library/intention.yml` chargée (liste de
// {value, label, color}) - repli sur un jeu par défaut tant qu'elle n'est pas encore arrivée.
window.OBJECTIVE_DIRECTIONS = window.OBJECTIVE_DIRECTIONS || [
  { value: "observe", label: "Observer", color: "#2f6fb0" },
  { value: "maximize", label: "Maximiser", color: "#2f8f5b" },
  { value: "minimize", label: "Minimiser", color: "#b5842a" },
  { value: "target", label: "Cible précise", color: "#7b4fa3" },
];

function objectiveDirectionInfo(value) {
  return window.OBJECTIVE_DIRECTIONS.find((d) => d.value === value) || { value, label: value, color: "#6c757d" };
}

function renderObjectives() {
  const list = document.getElementById("objectives-list");
  list.innerHTML = state.objectives
    .map((o, i) => {
      const dir = objectiveDirectionInfo(o.direction);
      return `
      <div class="objective-card" style="border-left-color:${dir.color};">
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:600;">${escapeHtml(o.name)}</div>
          <div style="font-size:12px;color:var(--text-faint);margin-top:3px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
            <span class="objective-direction-badge" style="background:${dir.color}1a;color:${dir.color};">${escapeHtml(dir.label)}</span>
            <span>${escapeHtml(o.metric)}${o.target != null ? " · cible " + o.target : ""}</span>
          </div>
          ${o.rationale ? `<div style="font-size:12px;color:var(--text-soft);margin-top:4px;">${escapeHtml(o.rationale)}</div>` : ""}
          ${o.verification_method ? `<div style="font-size:11.5px;color:var(--text-faint);margin-top:2px;">Vérification : ${escapeHtml(o.verification_method)}</div>` : ""}
        </div>
        <button class="step-remove" data-index="${i}" type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 5l14 14M5 19L19 5"/></svg>
        </button>
      </div>`;
    })
    .join("");
  list.querySelectorAll(".step-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.objectives.splice(parseInt(btn.dataset.index, 10), 1);
      renderObjectives();
    });
  });
}

document.getElementById("objective-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const name = document.getElementById("obj-name").value.trim();
  const metric = document.getElementById("obj-metric").value.trim();
  if (!name || !metric) return;
  const targetRaw = document.getElementById("obj-target").value;
  state.objectives.push({
    name,
    metric,
    direction: document.getElementById("obj-direction").value,
    target: targetRaw ? parseFloat(targetRaw) : null,
    rationale: document.getElementById("obj-rationale").value.trim() || null,
    verification_method: document.getElementById("obj-verification").value.trim() || null,
  });
  document.getElementById("objective-form").reset();
  renderObjectives();
});
