# TODO

Actions restantes convenues au fil des échanges, par ordre approximatif de priorité. Une fois
faite, déplacer la ligne dans la section « Fait » du bas (ou simplement la retirer).

## Prochaines évolutions (après le passage en plugins)

Demandées le 2026-10-03. Chacune suit le contrat d'`ARCHITECTURE.md` : un plugin propriétaire, des
routes REST en anglais, le front par son `client.js`. Les points 1 (équipes), 2 (page d'évolution
et refs) et 3 (un seul cahier de données, rattaché aux étapes du procédé, et son préalable,
l'identité des étapes) sont livrés : voir « Fait ».

### 4. Documentation intégrée (en tout dernier)

Volontairement à faire **après** les points 1 à 3, pour ne pas réécrire la documentation une fois
de plus. `ARCHITECTURE.md` et le README sont à jour des points 1 à 3 ;
les pages `/docs` non : `docs/guide.html` décrit encore l'ancienne page « Refs » et
`docs/architecture.html` l'ancien `require_role`.

- [ ] **Réécrire les pages de documentation intégrées.** Il s'agit des pages `/docs`, `/docs/guide`,
      `/docs/exemples` et `/docs/architecture` (`spectre/plugins/docs/pages/`).
      Aujourd'hui, elles décrivent l'application d'avant le refactor :
      - l'ancienne terminologie (« projet » au lieu de « µprojet ») ;
      - les anciennes routes (`/api/auth/*`, `/api/microprojets/…`, `spectre/api/static/`) ;
      - l'ancienne architecture.

      Elles doivent refléter l'état final :
      - les plugins et leur nomenclature ;
      - la piste et ses versions, et les refs avec leur page d'évolution ;
      - les équipes et les rôles ;
      - le cahier unique et le stepper ;
      - les conventions REST.

      La page « architecture » renverra à `ARCHITECTURE.md` plutôt que d'en recopier le contenu.
- [ ] **Refaire les captures d'écran** (`spectre/plugins/docs/static/img/`) une fois l'interface
      stabilisée.

## Couche Management — Phase 2 (analytique)

La Phase 1 (thèmes, hiérarchie, navigation) est livrée ; la page `/pilotage` (compteurs +
leaderboard) a été retirée - la page d'un projet corporate porte désormais ses objectifs classés et
un bloc de tendances à onglets (`spectre/plugins/kpis/service.py`, `plugins/kpis/static/kpi-trend.js`). Reste :

- [ ] **Définir les indicateurs clés société** à suivre dans le temps : lesquelles des mesures
      d'objectif (`Objective.metric`) ou du cahier (valeur d'une entrée manuelle, `value.name`) comptent comme un
      indicateur stratégique, sur quel µprojet/thème, avec quelle cible. Préalable obligatoire aux
      deux points suivants - sans ça il n'y a rien à tracer.
- [ ] **Brancher les KPI de tendance** (EQE, PL, défectivité, rendement - aujourd'hui des
      aperçus « à venir ») : écrire leur `provider` et l'enregistrer par `kpis.service.register`, typiquement un
      hook PRISM sur les wafers suivis par les µprojets du projet.
- [ ] **« Hero perfs »** : mettre en avant les meilleures valeurs atteintes à date pour chaque
      indicateur clé (quel µprojet/expérience, quelle valeur, quand).

## Suivi de lots — Phase 2 (données réelles)

La Phase 1 (déclarative) est livrée : `/lots` (Gantt), `/lots/{code}`, recherche, badge de lot sur les
nœuds d'un µprojet, lot rappelé sur la page d'une plaque (plugin `lots`). Un
lot = priorité (P10, P20...), début, fin prévisionnelle, fin déclarée, wafers - pas de parcours
d'étapes (jugé trop lourd à saisir). Reste :

- [ ] **Brancher les champs sur la base de production** via des datahooks PRISM : priorité, début,
      fin prévisionnelle et fin réelle, liste des wafers d'un lot. Le refactor a préparé le terrain :
      `lots.source` (`declaratif` ou `prism`, les champs d'un lot PRISM sont en lecture seule) et
      `PATCH /api/lots/{lot_id}` avec précondition. Reste à écrire la synchro (`lots.sync`) et son
      adaptateur PRISM.

## Polish navigation / rename

- [ ] Fil d'Ariane secondaire incomplet : `intent-forms.html` n'affiche que
      « ← Retour au µprojet » (un saut) plutôt que `Thèmes / <thème> / <µprojet>` comme la fiche
      projet et la fiche expérience.
- [ ] `scripts/seed_demo.py` : les µprojets de démo ne sont rattachés à aucun thème (atterrissent
      dans « Non classé ») - décider s'ils doivent illustrer un des 3 thèmes phares. Le seed ne crée
      pas non plus d'équipe : il faudrait une équipe de démo, avec Léa en manager, pour montrer les
      droits d'équipe sans manipulation.
- [ ] Le dialogue « Modifier le projet » (page d'un projet corporate) déborde en largeur sur écran
      étroit, comme le faisait « Nouvelle équipe » avant sa correction.

## Petites dettes notées en cours de route

- [ ] `DELETE /api/microprojects/{mp}/experiments/{exp}` (suppression d'une piste) : les blobs de
      pièces jointes orphelins ne sont pas nettoyés (inoffensif, dans `data/`, gitignoré, mais pourrait l'être).
- [ ] Brique technologique : pas d'aperçu de structure dédié au-delà du canevas live existant
      (décidé suffisant pour l'instant - revoir si le besoin revient).
- [ ] `recettes.yml` / `briques.yml` (`spectre/plugins/library/defaults/`, copiés dans `data/library/`) : un seul exemple fourni chacun - à enrichir
      au fil des besoins réels (le fichier explique le format en commentaire).

## Fait (pour mémoire, pas d'action)

- **Un seul cahier de données, côté interface** (2026-10-04, point 3). Le panneau « Données » de la
  fiche n'a plus que le cahier (et la galerie d'images externes) : chaque entrée montre son type,
  ses plaques, son objectif, son interprétation, le **stepper** du procédé (`notebook/static/stepper.js`,
  les étapes mesurées en rouge, une bulle « étape retirée ») et ses mesures côte à côte, une par
  étape ; les entrées d'autres plaques sont repliées dans « Autres plaques ». La boîte d'ajout et
  d'édition (`entry-dialog.js`) : PRISM (un instantané par étape cochée, une vue commune) ou à la
  main (valeur, texte, tableau collé d'Excel, images collées ou déposées, fichiers, liens), plaques
  mesurées, bulles à cocher ; les annotations des images se posent sur la fiche. La vue du procédé
  porte un badge par étape (`?summary=steps`) qui filtre le cahier ; la conclusion cite des entrées
  (`evidence_ids`) ; le rapport reprend tout le cahier. Décisions appliquées (2026-10-04) : la donnée
  suit la plaque mesurée, une seule entrée par mesure avec une valeur par étape, pas de mesures
  prévues dans le constructeur, pas de conversion d'une entrée manuelle en PRISM.
- **Un seul cahier de données, côté serveur** (2026-10-04, point 3). Le plugin `evidence` a disparu :
  `notebook` porte toutes les données d'une étude (`.../notebook-entries`, `kind: prism | manual`,
  une seule forme : plaques mesurées `wafers`, une mesure par étape `measurements[].step_id`), avec
  la règle « la donnée suit la plaque » (`applies`) et l'étape retirée (`step_retired`). **Pas de
  migration** : les vues de l'ancien cahier et les preuves (Follow + `metadata`) sont converties à
  la lecture, sans perte, les preuves gardant leur id (la conclusion les cite toujours) et leur
  `step_index` devenu un id d'étape ; la première écriture dans le cahier enregistre le cahier
  converti. Spectre n'écrit plus de preuve Follow. Détail dans `ARCHITECTURE.md` § 4 et § 5.
- **Équipes, managers et administrateurs** (2026-10-04, ex-point 1). Plugin `teams` (tables `teams`,
  `team_members`, pages `/equipes`, `/equipes/{slug}`), `management_areas.team_id`. Une seule
  règle : `areas.service.can_manage` pour un projet, `microprojects.service.access` pour un
  µprojet (admin et manager de l'équipe : owner), dont dérivent `require_role` et toutes les
  autorisations des autres plugins. Décisions appliquées : plusieurs équipes par compte, « Non
  classé » sans équipe, rien de rattaché à la migration, pas de SSO. Écarts retenus : la lecture des
  équipes est ouverte à tout compte connecté ; rattacher un projet à une équipe, ou un µprojet
  existant depuis la page d'un projet, reste à l'admin (un `owner` peut, lui, déplacer son µprojet,
  dans les limites du placement ci-dessous).
- **Placement d'un µprojet dans un projet d'équipe** (décidé et fait le 2026-10-04). Le créer ou l'y
  déplacer (`POST /api/microprojects`, `PATCH /api/microprojects/{mp}` `{area}`) : membres de
  l'équipe (tout rôle) et admin ; un projet sans équipe et « Non classé » restent ouverts à tous ;
  sinon 403 `placement_forbidden`. Règle `areas.service.can_place_microproject` (exposée par chaque
  projet), vérifiée par `microprojects.service.check_placement` ; les pages projet et thématique
  n'offrent « + Nouveau µprojet » qu'aux comptes autorisés.
- **Page « Évolution des structures »** (2026-10-04, ex-point 2). `/microprojets/{slug}/evolution`
  (l'ancienne `/refs` y redirige), servie par `GET .../structure-history` ; refs adressables
  (`GET`/`PATCH`/`DELETE .../refs/{ref_name}`, `Location` à la création) ; publication d'une ref
  dans la bibliothèque partagée (`derived_from` = son origine). Par défaut, le diagramme montre
  aussi les fusions et le début de chaque piste ; publier n'est offert qu'aux editors, sur une
  version qui porte une ref.
- **Identité stable des étapes** (2026-10-04, préalable du point 3). Ids `st_<8 hex>` sous
  `process_step_ids`, conservés aux évolutions ; facteurs de campagne par `step_id` ; **pas de
  migration** : les ids des anciennes versions se lisent avec la règle d'une écriture sans ids (ceux
  du premier parent tant que les types d'étapes ne changent pas, sinon dérivés de la version) ;
  recevoir des ids ne crée pas de version. Détail dans `ARCHITECTURE.md` § 4.

- Table `lot_steps` de la toute première version des lots supprimée par la migration
  `lots/0002_drop_lot_steps` (la base d'avant est sauvegardée dans `data/backups/` au démarrage qui migre).

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
