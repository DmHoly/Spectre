/* Charge la copie éditable (library/intention.yml) de la section « Objectifs et intention » et
   remplace le texte codé en dur dans structure-builder.html par celle-ci. Échec silencieux : en
   cas d'erreur réseau on garde le texte français déjà présent dans le HTML. */

function applyIntentionCopy(cfg) {
  const setText = (id, value) => {
    if (value == null) return;
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };
  const setPlaceholder = (id, value) => {
    if (value == null) return;
    const el = document.getElementById(id);
    if (el) el.placeholder = value;
  };

  setText("intention-section-title", cfg.section_title);
  setText("intention-section-subtitle", cfg.section_subtitle);

  setText("title-label", cfg.title_label);
  setPlaceholder("exp-title", cfg.title_placeholder);
  setText("intent-label", cfg.intent_label);
  setPlaceholder("exp-intent", cfg.intent_placeholder);
  setText("hypothesis-label", cfg.hypothesis_label);
  setPlaceholder("exp-hypothesis", cfg.hypothesis_placeholder);

  setText("entity-field-label", cfg.entity_field_label);
  setPlaceholder("exp-entity-sample-id", cfg.entity_id_placeholder);
  setText("entity-location-label", cfg.entity_location_label);
  setPlaceholder("exp-entity-location", cfg.entity_location_placeholder);
  setText("entity-field-hint", cfg.entity_field_hint);

  setText("objectives-title", cfg.objectives_title);
  setText("objective-name-label", cfg.objective_name_label);
  setPlaceholder("obj-name", cfg.objective_name_placeholder);
  setText("objective-rationale-label", cfg.objective_rationale_label);
  setPlaceholder("obj-rationale", cfg.objective_rationale_placeholder);
  setText("objective-metric-label", cfg.objective_metric_label);
  setPlaceholder("obj-metric", cfg.objective_metric_placeholder);
  setText("objective-direction-label", cfg.objective_direction_label);
  setText("objective-target-label", cfg.objective_target_label);
  setText("objective-verification-label", cfg.objective_verification_label);
  setPlaceholder("obj-verification", cfg.objective_verification_placeholder);
  setText("objective-submit-btn", cfg.objective_submit_label);

  if (Array.isArray(cfg.objective_directions) && cfg.objective_directions.length) {
    window.OBJECTIVE_DIRECTIONS = cfg.objective_directions;
    const select = document.getElementById("obj-direction");
    if (select) {
      const current = select.value;
      select.innerHTML = cfg.objective_directions
        .map((d) => `<option value="${escapeHtml(d.value)}">${escapeHtml(d.label)}</option>`)
        .join("");
      if (cfg.objective_directions.some((d) => d.value === current)) select.value = current;
    }
    if (typeof renderObjectives === "function" && typeof state !== "undefined" && state.objectives) {
      renderObjectives();
    }
  }
}

(async function loadIntentionCopy() {
  try {
    const cfg = await api.get(`/api/microprojets/${slug}/structures/intention-form`);
    applyIntentionCopy(cfg || {});
  } catch (err) {
    console.warn("Copie de la section « Objectifs et intention » : non chargée, texte par défaut conservé.", err);
  }
})();
