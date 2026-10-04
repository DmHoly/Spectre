# TODO

Actions restantes convenues au fil des échanges, par ordre approximatif de priorité. Une fois
faite, déplacer la ligne dans la section « Fait » du bas (ou simplement la retirer).

## Prochaines évolutions (après le passage en plugins)

Demandées le 2026-10-03. Chacune suit le contrat d'`ARCHITECTURE.md` : un plugin propriétaire, des
routes REST en anglais, le front par son `client.js`. Les points 1 (équipes) et 2 (page d'évolution
et refs) sont livrés, comme le préalable du point 3 (identité des étapes) : voir « Fait ».

### 3. Un seul cahier de données, rattaché aux étapes du procédé

Demandé le 2026-10-04. Ce point remplace l'ancien « résultats rattachés à une étape ».

- [ ] **Fondre les preuves dans le cahier.** Aujourd'hui, les données d'une étude sont réparties
      entre deux modules : les **preuves** (plugin `evidence`) et le **cahier** (plugin `notebook`).
      On regroupe tout dans le cahier. Ce qu'on appelait une preuve devient un type d'entrée du
      cahier : la **donnée chargée à la main**. Elle couvre tout ce que PRISM ne peut pas prévoir :
      - image, capture d'écran, fichier ;
      - valeur mesurée, texte, tableau collé (analysé en TSV) ;
      - lien vers un dossier ou une présentation.

      C'est la donnée très R&D : une mesure faite une seule fois, qui ne vaut pas un connecteur,
      ou dont le format n'est pas fixé. On ne peut pas la normaliser, mais on veut la garder.
      Le cahier aura donc deux types d'entrée :
      - **PRISM** : instantané d'un type de données de `characterization` et sa vue DataViz,
        comme aujourd'hui ;
      - **manuelle** : l'ex-preuve, qui garde son lien à un objectif et son interprétation.
- [ ] **Conséquences sur l'architecture.**
      - Le plugin `evidence` disparaît et son contenu passe dans `notebook` : panneau, routes
        `.../notebook-entries` avec `kind: prism | manual`, client et tests.
      - Une migration convertit les preuves existantes (preuves Follow, plus les champs Spectre de
        `metadata`) en entrées manuelles du cahier, sans perte. Les images restent dans
        `attachments`.
      - Il faut aussi suivre ce que la fusion touche ailleurs :
        - le compteur de l'onglet « Données » ;
        - le rapport ;
        - la conclusion, qui cite les preuves ;
        - la fusion d'études (`experiments.service._merge_evidence`) ;
        - le lien preuve ↔ objectif.
      - Mettre à jour ARCHITECTURE.md (§ 3 et § 5) et le README.
- [ ] **Convertir les `step_index` des anciennes preuves** en ids d'étape, avec
      `experiments.service.step_id_at(repo, version, index)` (l'identité des étapes est livrée,
      voir « Fait » ; il n'y a pas de migration des procédés, leurs ids se lisent de parent en
      parent, si bien qu'une étape garde le même id dans les anciennes versions d'une piste).
- [ ] **Situer chaque donnée dans le procédé, sur plusieurs étapes.**
      - À l'ajout comme à la lecture d'une donnée, on affiche un **stepper** du procédé : une bulle
        par étape, avec en **rouge** les étapes où la mesure est faite.
      - Une même mesure peut être faite à **plusieurs moments** du procédé. Une entrée porte donc
        une **liste d'étapes** (`steps: [step_id, …]`, les ids `st_<8 hex>` de `process_step_ids`),
        pas une étape unique. Dans la boîte d'ajout, on coche les bulles.
      - Dans la vue du procédé (`experiments/static/structure-view.js`), chaque étape affiche un
        badge avec le nombre de données qui la concernent. Un clic filtre le cahier sur cette étape.
- [ ] **À trancher :**
      - une donnée rattachée à une étape suit-elle cette étape aux versions suivantes si elle n'a
        pas changé ? Et si l'étape est supprimée à une évolution, que devient le rattachement ?
      - pour une même mesure faite à plusieurs étapes, une seule entrée avec une valeur par étape
        (pour comparer avant et après), ou une entrée par moment, reliées entre elles ?
      - faut-il un « point de contrôle attendu », déclaré à la conception dans le constructeur,
        en plus de la « donnée obtenue » ? Le stepper montrerait alors en gris les mesures prévues
        et en rouge celles qui sont faites.
      - côté PRISM : connecteur quand il existe, sinon entrée manuelle. Peut-on convertir plus tard
        une entrée manuelle en entrée PRISM, quand le connecteur apparaît ?

### 4. Documentation intégrée (en tout dernier)

Volontairement à faire **après** les points 1 à 3, pour ne pas réécrire la documentation une fois
de plus. `ARCHITECTURE.md` et le README sont à jour des points 1 et 2 et de l'identité des étapes ;
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
      d'objectif (`Objective.metric`) ou de preuve (`Evidence.metric_value`) comptent comme un
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
- [ ] **À décider : déplacer un µprojet vers le projet d'une autre équipe.** Tout `owner` effectif
      d'un µprojet (propriétaire, manager de son équipe, admin) le déplace vers n'importe quel
      projet (`PATCH /api/microprojects/{mp}` `{area}`, `microprojects.service.update`), celui d'une
      autre équipe compris : l'équipe d'arrivée en devient `owner` sans l'avoir demandé, celle de
      départ en perd la gestion. Pas une escalade (celui qui déplace ne gagne rien, et tout compte
      crée déjà un µprojet dans n'importe quel projet). Si on veut l'empêcher : exiger, quand `area`
      change, que l'appelant gère le projet d'arrivée (`areas.service.can_manage`) ou soit admin.

## Petites dettes notées en cours de route

- [ ] `DELETE /api/microprojects/{mp}/experiments/{exp}` (suppression d'une piste) : les blobs de
      pièces jointes orphelins ne sont pas nettoyés (inoffensif, dans `data/`, gitignoré, mais pourrait l'être).
- [ ] Brique technologique : pas d'aperçu de structure dédié au-delà du canevas live existant
      (décidé suffisant pour l'instant - revoir si le besoin revient).
- [ ] `recettes.yml` / `briques.yml` (`spectre/plugins/library/defaults/`, copiés dans `data/library/`) : un seul exemple fourni chacun - à enrichir
      au fil des besoins réels (le fichier explique le format en commentaire).

## Fait (pour mémoire, pas d'action)

- **Équipes, managers et administrateurs** (2026-10-04, ex-point 1). Plugin `teams` (tables `teams`,
  `team_members`, pages `/equipes`, `/equipes/{slug}`), `management_areas.team_id`. Une seule
  règle : `areas.service.can_manage` pour un projet, `microprojects.service.access` pour un
  µprojet (admin et manager de l'équipe : owner), dont dérivent `require_role` et toutes les
  autorisations des autres plugins. Décisions appliquées : plusieurs équipes par compte, « Non
  classé » sans équipe, rien de rattaché à la migration, pas de SSO. Écarts retenus : la lecture des
  équipes est ouverte à tout compte connecté ; rattacher un projet à une équipe, ou un µprojet
  existant depuis la page d'un projet, reste à l'admin (un `owner` peut, lui, déplacer son µprojet :
  voir la question ouverte ci-dessus).
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
