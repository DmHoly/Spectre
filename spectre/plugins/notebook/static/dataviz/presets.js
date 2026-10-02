/* Préréglages par type de données : les façons habituelles de regarder chaque type, proposées en
   premier quand on ajoute une vue au cahier. Une entrée = un composant (voir les autres fichiers de
   ce dossier) + ses réglages + un titre de départ. Un préréglage dont une colonne manque au jeu de
   données chargé n'est simplement pas proposé (DataViz.presetsFor).

   Pour ajouter la vue qu'utilise une équipe : une ligne ici si un composant existant suffit, sinon
   un nouveau fichier composant (voir core.js) puis une ligne ici. */

DataViz.addPresets("eqe", [
  { title: "EQE vs densité de courant", component: "eqe-curves", options: { maxPerWafer: 40, median: true, mark25: true } },
  { title: "Carte wafer · EQE max", component: "wafer-map", options: { value: "max_EQE", hideZero: true } },
  { title: "EQE max par plaque", component: "distribution", options: { value: "max_EQE", points: true, hideZero: true } },
  { title: "Synthèse par plaque", component: "wafer-summary", options: { columns: ["max_EQE", "J_at_MaxEQE", "EQE_25A_cm2", "yield_per_wafer"], hideZero: true } },
  { title: "Courbes I-V", component: "curves", options: { x: "V", y: "I", logy: true, maxPerWafer: 40, median: true } },
  { title: "Carte wafer · J à l'EQE max", component: "wafer-map", options: { value: "J_at_MaxEQE", log: true, hideZero: true } },
]);

DataViz.addPresets("pl", [
  { title: "Carte wafer · longueur d'onde dominante", component: "wafer-map", options: { value: "Dominant WL(nm)" } },
  { title: "Carte wafer · PL intégrée", component: "wafer-map", options: { value: "Integrated PL (a.u.)" } },
  { title: "Pic PL par plaque", component: "distribution", options: { value: "Peak WL (nm)", points: true } },
  { title: "Synthèse par plaque", component: "wafer-summary", options: { columns: ["Peak WL (nm)", "Dominant WL(nm)", "Integrated PL (a.u.)", "FWHM (nm)"] } },
  { title: "PL intégrée vs longueur d'onde", component: "scatter", options: { x: "Peak WL (nm)", y: "Integrated PL (a.u.)" } },
]);

DataViz.addPresets("ncel", [
  { title: "Carte wafer · émission NCEL", component: "wafer-map", options: { value: "na_emission_max" } },
  { title: "Émission NCEL par plaque", component: "distribution", options: { value: "na_emission_max", points: true } },
  { title: "Synthèse par plaque", component: "wafer-summary", options: { columns: ["na_emission_max", "na_current_a"] } },
]);

DataViz.addPresets("waferlist", [{ title: "Liste des wafers", component: "table", options: {} }]);
