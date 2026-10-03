# TODO

Actions restantes convenues au fil des échanges, par ordre approximatif de priorité. Une fois
faite, déplacer la ligne dans la section « Fait » du bas (ou simplement la retirer).

## Prochaines évolutions (après le passage en plugins)

Demandées le 2026-10-03, à démarrer une fois la branche `refactor/plugins` fusionnée. Chacune suit
le contrat d'`ARCHITECTURE.md` : un plugin propriétaire, des routes REST en anglais, le front par
son `client.js`.

### 1. Équipes, managers et administrateurs

- [ ] **Trois niveaux de droits.**
      - **admin** : accès à tout. C'est l'actuel `users.is_admin`. Il doit aussi passer outre les
        rôles de µprojet, ce que `require_role` ne fait pas aujourd'hui.
      - **manager** : tous les droits sur ce qui appartient à **son équipe**, dont créer, renommer
        et supprimer les thèmes (projets corporate), les thématiques et les objectifs, et
        administrer les µprojets de l'équipe (membres, rattachement).
      - **membre** : les rôles de µprojet actuels (viewer, editor, owner).
- [ ] **Nouveau plugin `teams`.**
      - Tables `teams` et `team_members(team_id, user_id, role: manager|member)`.
      - Routes `/api/teams`, `/api/teams/{team_slug}/members`.
      - Page « Équipes ».
      - Le rattachement d'un thème (`areas.team_id`) et d'un µprojet à une équipe se fait par
        `PATCH` sur la ressource concernée.
- [ ] **Une seule règle d'autorisation.** Partir de `accounts.deps.require_admin` et
      `microprojects.deps.require_role` et en faire une fonction de politique unique (ex.
      `can_manage(user, area | microproject)`) appelée par ces deux dépendances, au lieu de
      contrôles dispersés.
      **Pas de moteur de règles générique : YAGNI.**
- [ ] **À trancher avant de commencer :**
      - un utilisateur peut-il être dans plusieurs équipes ?
      - un thème ou un µprojet appartient-il à une seule équipe ?
      - un manager voit-il les µprojets de son équipe sans en être membre ?
      - quelle équipe par défaut pour l'existant, à la migration ?
      - faut-il anticiper le SSO (voir `REVIEW.md` § 2, identité) ?

### 2. Page dédiée à l'évolution des structures et aux refs

- [ ] **Constat.** On peut déjà promouvoir une version en ref (`POST /api/microprojects/{mp}/refs`,
      bouton « + ref » de la fiche), et chaque version porte un numéro majeur.mineur.correctif
      (`experiments/versioning.py`). Mais rien ne le met en valeur : la page `/microprojets/{slug}/refs`
      n'est liée depuis aucun écran.
- [ ] **Page dédiée** dans le plugin `experiments` (ou un plugin `refs` s'il grossit), liée depuis la
      page µprojet et depuis la fiche. Elle montre un **diagramme façon git** de l'évolution des
      structures :
      - une colonne par piste ;
      - un nœud par version structurelle, étiqueté `vX.Y.Z`, avec les changements majeurs et mineurs
        distingués ;
      - les fourches, les fusions et les refs en badges.

      D3 est déjà embarqué, et `lineage-graph.js` sait dessiner la filiation.
- [ ] **Actions sur la page :**
      - « Promouvoir en ref » sur n'importe quel nœud ;
      - comparer deux nœuds (`GET .../structure-diff`) ;
      - partir d'une ref (fourche explicite, `POST .../experiments` avec `from_version`) ;
      - suivre l'évolution d'une ref donnée, c'est-à-dire tout ce qui en descend.
- [ ] **API.** Enrichir `GET /api/microprojects/{mp}/lineage` (ou une ressource
      `.../structure-history`) avec le numéro de version, le niveau de changement et les refs posées
      sur chaque nœud, pour que la page ne recalcule rien côté client.
- [ ] **À trancher :**
      - une ref reste-t-elle propre au µprojet, ou peut-elle être publiée dans la bibliothèque
        partagée (structures enregistrées de `process_library`) ?
      - peut-on renommer ou retirer une ref ?

### 3. Résultats de données rattachés à une étape du procédé

- [ ] **Besoin.** Sur un procédé de 10 étapes, dire « à cette étape, on vérifie tel point » et y
      rattacher le résultat. Trois sources possibles :
      - un **connecteur PRISM** quand il existe : instantané d'un type de données du plugin
        `characterization`, comme le cahier ;
      - un **lien vers la donnée** (dossier, fichier, URL) ;
      - un **copier-coller** : tableau collé, analysé en TSV, texte ou image. Le collage d'images
        existe déjà dans `attachments/static/image-drop.js`.
- [ ] **Ce qui existe déjà.** Une preuve Follow porte déjà un `step_index`, et le plugin `evidence`
      gère liens et images. Il faut :
      - étendre la preuve, ou ajouter une ressource `.../experiments/{exp}/step-results`, avec
        `step` et `source: prism | link | paste` ;
      - afficher, dans la vue du procédé (`experiments/static/structure-view.js`), un badge de
        résultats par étape et une action « Rattacher un résultat ».
- [ ] **Préalable : une identité stable pour chaque étape.** Aujourd'hui une étape est désignée par
      sa position, si bien qu'insérer une étape à l'évolution suivante décale tous les rattachements.
      La revue l'a relevé (`REVIEW.md`, front du constructeur : l'identité positionnelle des étapes
      gêne déjà le DOE). Il faut donc un `step_id` dans les métadonnées du procédé, et que les
      facteurs DOE le référencent aussi.
- [ ] **À trancher :**
      - un résultat rattaché suit-il l'étape aux versions suivantes si elle n'a pas changé ?
      - faut-il « point de contrôle attendu » (déclaré à la conception) en plus de « résultat
        obtenu » ?

## Couche Management — Phase 2 (analytique)

La Phase 1 (thèmes, hiérarchie, navigation) est livrée ; la page `/pilotage` (compteurs +
leaderboard) a été retirée - la page d'un projet corporate porte désormais ses objectifs classés et
un bloc de tendances à onglets (`spectre/core/trends.py`, `plugins/kpis/static/kpi-trend.js`). Reste :

- [ ] **Définir les indicateurs clés société** à suivre dans le temps : lesquelles des mesures
      d'objectif (`Objective.metric`) ou de preuve (`Evidence.metric_value`) comptent comme un
      indicateur stratégique, sur quel µprojet/thème, avec quelle cible. Préalable obligatoire aux
      deux points suivants - sans ça il n'y a rien à tracer.
- [ ] **Brancher les KPI de tendance** (EQE, PL, défectivité, rendement - aujourd'hui des
      aperçus « à venir ») : écrire leur `provider` dans `spectre/core/trends.py`, typiquement un
      hook PRISM sur les wafers suivis par les µprojets du projet.
- [ ] **« Hero perfs »** : mettre en avant les meilleures valeurs atteintes à date pour chaque
      indicateur clé (quel µprojet/expérience, quelle valeur, quand).

## Suivi de lots — Phase 2 (données réelles)

La Phase 1 (déclarative) est livrée : `/lots` (Gantt), `/lots/{code}`, recherche, badge de lot sur les
nœuds d'un µprojet, lot rappelé sur la page d'une plaque (`spectre/core/lots.py`, `api/lots.py`). Un
lot = priorité (P10, P20...), début, fin prévisionnelle, fin déclarée, wafers - pas de parcours
d'étapes (jugé trop lourd à saisir). Reste :

- [ ] **Brancher les champs sur la base de production** via des datahooks PRISM : priorité, début,
      fin prévisionnelle et fin réelle, liste des wafers d'un lot. `lots.source` vaut `declaratif`
      aujourd'hui - prévoir la valeur pour un lot alimenté par hook et ce qui reste saisissable à
      la main (thématiques visées, notes).
- [ ] La table `lot_steps` créée par la toute première version (parcours, abandonné) peut rester
      dans une base existante : plus lue, à supprimer à l'occasion (`DROP TABLE lot_steps`).

## Polish navigation / rename

- [ ] Fils d'Ariane secondaires incomplets : `refs.html`, `graphe.html`,
      `intent-forms.html` n'affichent que « ← Retour au µprojet » (un saut) plutôt que
      `Thèmes / <thème> / <µprojet>` comme la fiche projet et la fiche expérience.
- [ ] Pages de documentation (`guide.html`, `examples.html`, `architecture.html`) :
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
