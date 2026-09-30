/* Lecture/écriture du formulaire de substrat - utilisé par le rendu (simulation.js), l'export de
   code (code-export.js) et le chargement d'un procédé existant (experience-launch.js, library-mode.js). */

function setSubstrateFields(substrate) {
  ensureSelectValue("substrate-material", substrate.material);
  document.getElementById("substrate-width").value = substrate.domain_width.value;
  ensureSelectValue("substrate-width-unit", substrate.domain_width.unit, "");
  document.getElementById("substrate-thickness").value = substrate.thickness.value;
  ensureSelectValue("substrate-thickness-unit", substrate.thickness.unit, "");
}

function substrateSpec() {
  return {
    material: document.getElementById("substrate-material").value,
    domain_width: lengthValue("substrate-width"),
    thickness: lengthValue("substrate-thickness"),
  };
}
