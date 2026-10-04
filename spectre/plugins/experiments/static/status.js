/* Statut et issue d'une expérience : le badge (statusBadgeHtml) et la clé d'issue (experimentOutcome),
   la même partout - fiche, graphe de filiation, frise d'une thématique, lots, plaques. */

const STATUS_LABELS = {
  draft: { label: "Brouillon", cls: "badge-draft" },
  running: { label: "En cours", cls: "badge-running" },
  hold: { label: "En pause", cls: "badge-hold" }, // statut propre à Spectre (metadata « hold »)
  continued: { label: "Continuée", cls: "badge-continued" }, // brouillon repris par une version suivante
  concluded: { label: "Conclue", cls: "badge-concluded" },
  abandoned: { label: "Abandonnée", cls: "badge-abandoned" },
};

// Conclusion.status alone ("concluded") doesn't say what kind of conclusion it was -
// Conclusion.decision (posé par /conclure : promote/branch/replicate/abandon/inconclusive)
// already carries that nuance, just not shown anywhere before. Reusing the existing .badge-*
// classes (each already fixes the right colour/teinte pair) rather than inventing new ones -
// only the label changes. "concluded" with no decision (older data, or never set) keeps the
// generic "Conclue" from STATUS_LABELS above.
// « À poursuivre » a sa propre couleur (violet) : en bleu, on la confondait avec « En cours » ; une
// conclusion « Abandonner la piste » est une piste abandonnée, pas une « Conclue » verte.
const CONCLUDED_DECISION_LABELS = {
  promote: { label: "Concluante", cls: "badge-concluded" },
  inconclusive: { label: "Non concluante", cls: "badge-abandoned" },
  branch: { label: "À poursuivre", cls: "badge-continue" },
  replicate: { label: "À poursuivre", cls: "badge-continue" },
  abandon: { label: "Abandonnée", cls: "badge-abandoned" },
};

// L'issue d'une expérience en une clé (draft, continued, running, hold, promote, concluded, continue,
// inconclusive, abandoned) : la même partout - badge (statusBadgeHtml), nœud du graphe et frise (lineage-graph.js).
const OUTCOME_BY_DECISION = { promote: "promote", inconclusive: "inconclusive", branch: "continue", replicate: "continue", abandon: "abandoned" };

function experimentOutcome(status, decision) {
  if (status === "concluded") return OUTCOME_BY_DECISION[decision] || "concluded";
  return STATUS_LABELS[status] ? status : "draft";
}

// `decision` is optional (Conclusion.decision, only meaningful when status === "concluded") -
// every call site should pass it when it has it (an experiment's ``conclusion.decision`` or a
// node payload's ``decision``) so "Concluante"/"Non concluante"/"À poursuivre" show up instead of
// the generic "Conclue" wherever a status badge appears.
function statusBadgeHtml(status, decision) {
  const info = (status === "concluded" && CONCLUDED_DECISION_LABELS[decision]) || STATUS_LABELS[status] || STATUS_LABELS.draft;
  return `<span class="badge ${info.cls}"><span class="dot"></span>${info.label}</span>`;
}
