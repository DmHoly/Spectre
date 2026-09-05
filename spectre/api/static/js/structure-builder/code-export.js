/* -- "Voir le code" : sérialise le substrat + les étapes courantes en script StructureForge
   autonome, indépendant de Spectre - mêmes classes/champs que structureforge.process.steps.
   `pyStr`/`pyLength`/`pyDict` sont aussi utilisés par les `pyCode()` de step-kinds.js. */

const LENGTH_TO_NM = { A: 0.1, nm: 1, um: 1000, mm: 1_000_000 };

function toNm(length) {
  return length.value * (LENGTH_TO_NM[length.unit] || 1);
}

function pyStr(value) {
  return JSON.stringify(String(value));
}

function pyLength(length) {
  return `Length(value=${length.value}, unit=${pyStr(length.unit)})`;
}

function pyDict(obj) {
  const entries = Object.entries(obj || {});
  if (entries.length === 0) return "{}";
  return `{${entries.map(([k, v]) => `${pyStr(k)}: ${v}`).join(", ")}}`;
}

function pyList(values) {
  return `[${(values || []).map((v) => pyStr(v)).join(", ")}]`;
}

function generateStructureForgeCode() {
  const substrate = substrateSpec();
  const usedKinds = [...new Set(state.steps.map((s) => s.kind))];
  const importNames = new Set(["Geometry", "Length", "default_library", "default_recipes", "save_svg", "simulate"]);
  usedKinds.forEach((k) => importNames.add(PY_STEP_CLASS[k] || k));
  if (usedKinds.includes("epitaxial_growth")) importNames.add("GrowthOrientation");
  const stepsLines = state.steps.length ? state.steps.map((s) => `    ${pyStepCode(s)},`).join("\n") : "    # aucune étape pour l'instant";
  return `from structureforge import (
    ${[...importNames].sort().join(",\n    ")},
)

materials = default_library()
recipes = default_recipes()
geometry = Geometry.substrate(
    ${pyStr(substrate.material)},
    domain_width_nm=${toNm(substrate.domain_width)},
    thickness_nm=${toNm(substrate.thickness)},
)

steps = [
${stepsLines}
]

frames = simulate(geometry, steps, materials, recipes)
material_colors = {m.name: m.color for m in materials}
save_svg("structure.svg", frames[-1], material_colors)
`;
}

document.getElementById("show-code-btn").addEventListener("click", () => {
  document.getElementById("code-modal-pre").textContent = generateStructureForgeCode();
  document.getElementById("code-modal").showModal();
});
document.getElementById("code-modal-close-btn").addEventListener("click", () => {
  document.getElementById("code-modal").close();
});
document.getElementById("code-modal-copy-btn").addEventListener("click", async () => {
  const btn = document.getElementById("code-modal-copy-btn");
  try {
    await navigator.clipboard.writeText(document.getElementById("code-modal-pre").textContent);
    const original = btn.textContent;
    btn.textContent = "Copié !";
    setTimeout(() => (btn.textContent = original), 1500);
  } catch (err) {
    showError(new Error("Impossible de copier automatiquement - sélectionnez le code et copiez-le manuellement."));
  }
});
