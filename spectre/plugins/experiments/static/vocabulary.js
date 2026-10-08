/* Le vocabulaire d'une étude, en libellés français : types d'étape du procédé (et leurs paramètres),
   décisions d'une conclusion, résultats d'un objectif. Une seule copie, pour la fiche d'expérience,
   les panneaux qui s'y greffent (cahier) et l'atlas. */

const ExperimentVocabulary = {
  stepKinds: {
    deposition: "Dépôt",
    etch: "Gravure",
    lithography: "Lithographie",
    resist_strip: "Retrait de résine",
    planarization: "Planarisation",
    chemical: "Étape chimique",
    faceted_growth: "Croissance facettée",
    facet_envelope: "Rattrapage des plans",
    epitaxial_growth: "Croissance épitaxiale",
    flip: "Retournement",
  },

  stepFields: {
    material: "Matériau",
    recipe: "Recette",
    angle_deg: "Angle",
    thickness: "Épaisseur",
    depth: "Profondeur",
    resist_material: "Résine",
    openings: "Ouvertures",
    target_level: "Niveau cible",
    stop_material: "S'arrête sur",
    orientation: "Orientation",
    rate_c: "Vitesse relative (plan C)",
    rate_m: "Vitesse relative (plan M)",
    rate_sp: "Vitesse relative (semipolaire)",
    rate_sp_inv: "Vitesse relative (semipolaire inversée)",
    semi_polar_angle_deg: "Angle semipolaire",
    seed_materials: "Matériaux d'amorçage (SAG)",
  },

  // Conclusion.decision - dans l'ordre du formulaire de conclusion
  decisions: {
    promote: "Retenir comme référence",
    branch: "Explorer une variante",
    replicate: "Reproduire pour confirmer",
    abandon: "Abandonner la piste",
    inconclusive: "Non concluant",
  },

  // ObjectiveResult.status - dans l'ordre du formulaire de conclusion
  objectiveStatuses: {
    met: "Atteint",
    not_met: "Non atteint",
    partially_met: "Partiellement atteint",
    inconclusive: "Non concluant",
  },

  // « Dépôt — Couche GaN » : une étape du procédé ({kind, name}).
  stepLabel(step) {
    return `${this.stepKinds[step.kind] || step.kind} — ${step.name}`;
  },
};
