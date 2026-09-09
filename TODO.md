# TODO

Actions restantes convenues au fil des échanges, par ordre approximatif de priorité. Une fois
faite, déplacer la ligne dans la section « Fait » du bas (ou simplement la retirer).

## Couche Management — Phase 2 (analytique)

La Phase 1 (thèmes, hiérarchie, navigation, `/pilotage` avec compteurs + leaderboard) est livrée.
Reste :

- [ ] **Définir les indicateurs clés société** à suivre dans le temps : lesquelles des mesures
      d'objectif (`Objective.metric`) ou de preuve (`Evidence.metric_value`) comptent comme un
      indicateur stratégique, sur quel µprojet/thème, avec quelle cible. Préalable obligatoire aux
      deux points suivants - sans ça il n'y a rien à tracer.
- [ ] **Courbes de tendance** sur `/pilotage` : évolution dans le temps des indicateurs clés
      choisis ci-dessus (par thème et/ou société entière).
- [ ] **« Hero perfs »** : mettre en avant les meilleures valeurs atteintes à date pour chaque
      indicateur clé (quel µprojet/expérience, quelle valeur, quand).
- [ ] Leaderboard : bascule optionnelle « par thème » / « par µprojet » (actuellement thèmes
      uniquement, décision prise pour la Phase 1).

## Polish navigation / rename

- [ ] Fils d'Ariane secondaires incomplets : `refs.html`, `graphe.html`,
      `formulaire-intention.html` n'affichent que « ← Retour au µprojet » (un saut) plutôt que
      `Thèmes / <thème> / <µprojet>` comme la fiche projet et la fiche expérience.
- [ ] Pages de documentation (`docs-guide.html`, `docs-exemples.html`, `docs-architecture.html`) :
      texte encore en « projet » (seul le lien de retour a été aligné) - à relire et mettre à jour
      pour la terminologie « µprojet » + la nouvelle hiérarchie Management.
- [ ] `scripts/seed_demo.py` : les µprojets de démo ne sont rattachés à aucun thème (atterrissent
      dans « Non classé ») - décider s'ils doivent illustrer un des 3 thèmes phares.
## Petites dettes notées en cours de route

- [ ] `DELETE /experiences/{ref}` (suppression d'une étude) : les blobs de pièces jointes
      orphelins ne sont pas nettoyés (inoffensif, dans `data/`, gitignoré, mais pourrait l'être).
- [ ] Brique technologique : pas d'aperçu de structure dédié au-delà du canevas live existant
      (décidé suffisant pour l'instant - revoir si le besoin revient).
- [ ] `library/recettes.yml` / `library/briques.yml` : un seul exemple fourni chacun - à enrichir
      au fil des besoins réels (le fichier explique le format en commentaire).

## Fait (pour mémoire, pas d'action)

- Bibliothèque racine éditable (`library/*.yml` + registry.py, rechargement à chaud) - matériaux
  resserrés nitrures, présets, recettes de gravure sélective.
- Undo/redo dans l'éditeur de structure, briques repliables.
- Hub `/bibliotheque` global (plus par µprojet).
- Statut « en cours »/« brouillon », édition d'une conclusion après coup, réouverture.
- Split (campagne DOE) et suppression d'expérience possibles depuis une évolution/ref, avec
  filiation conservée.
- Couche Management complète (thèmes, admin, `/pilotage`, 3 thèmes phares seedés), renommage
  `projet → µprojet` (URLs/API/UI), nouvelle navigation Thèmes → thème → µprojet → expérience.
- Renommage profond `project → microproject` : table SQLite, colonnes, dossier
  `data/microprojects/<slug>`, modules Python/JS et clé de scope `"microprojet"`. Une installation
  antérieure se migre au démarrage (`_rename_legacy_project_tables` / `_rename_legacy_project_dir`
  dans `spectre/core/db.py`, couverts par `tests/test_legacy_project_rename_migration.py`).
