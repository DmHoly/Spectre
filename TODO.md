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
- [ ] **Situer chaque donnée dans le procédé, sur plusieurs étapes.**
      - À l'ajout comme à la lecture d'une donnée, on affiche un **stepper** du procédé : une bulle
        par étape, avec en **rouge** les étapes où la mesure est faite.
      - Une même mesure peut être faite à **plusieurs moments** du procédé. Une entrée porte donc
        une **liste d'étapes** (`steps: [step_id, …]`), pas une étape unique. Dans la boîte d'ajout,
        on coche les bulles.
      - Dans la vue du procédé (`experiments/static/structure-view.js`), chaque étape affiche un
        badge avec le nombre de données qui la concernent. Un clic filtre le cahier sur cette étape.
- [ ] **Préalable : une identité stable pour chaque étape.** Aujourd'hui une étape est désignée par
      sa position : insérer une étape à l'évolution suivante décalerait tous les rattachements.
      - Il faut un `step_id` dans les métadonnées du procédé, attribué au lancement et conservé
        aux évolutions.
      - Les facteurs DOE doivent le référencer aussi (la revue l'a relevé : `REVIEW.md`, front du
        constructeur).
      - Une migration attribue les `step_id` aux procédés existants, et les `step_index` des
        anciennes preuves sont convertis.
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
de plus.

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

## Polish navigation / rename

- [ ] Fils d'Ariane secondaires incomplets : `refs.html` et `intent-forms.html` n'affichent que
      « ← Retour au µprojet » (un saut) plutôt que `Thèmes / <thème> / <µprojet>` comme la fiche
      projet et la fiche expérience.
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
