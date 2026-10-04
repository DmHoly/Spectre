# TODO

Actions restantes convenues au fil des échanges, par ordre approximatif de priorité. Une fois
faite, déplacer la ligne dans la section « Fait » du bas (ou simplement la retirer).

## Prochaines évolutions (après le passage en plugins)

Demandées le 2026-10-03. Chacune suit le contrat d'`ARCHITECTURE.md` : un plugin propriétaire, des
routes REST en anglais, le front par son `client.js`. Les points 1 (équipes), 2 (page d'évolution
et refs), 3 (un seul cahier de données, rattaché aux étapes du procédé, et son préalable,
l'identité des étapes) et 3 bis (ses suites : images externes dans le cahier, combinaison en une
nouvelle étude) sont livrés, serveur et interface, ainsi que tout le 3 ter (annotations sur toute
image, étiquettes de couches) : voir
« Fait ».

### 3 ter. Images et structure

Demandé le 2026-10-04 : « toute image devrait avoir ses annotations possibles » ; et, le même
jour, « pouvoir mettre des valeurs clés à côté de la structure : au niveau de la couche, sur le
côté, le nom (ex. p-GaN) et en dessous un paramètre (épaisseur, dopage ou les deux), pour qu'une
capture d'écran porte les infos importantes ».

- [x] **Annoter toute image** : fait, voir « Fait » (« Annotations sur toute image »).
- [x] **Étiquettes de couches** : seules les couches choisies (aucune par défaut), réglées dans le
      constructeur par étape, enregistrées avec la version sans compter comme un changement de
      structure ; sur la fiche (bouton masquer / afficher), la page d'évolution et le rapport.
      Fait : voir « Fait ».

Suites décidées le 2026-10-04 (relecture des étiquettes) :

- [x] **Appartenance aux briques enregistrée** (préalable) : le constructeur envoyait
      `brick_group_id` / `brick_name` avec les étapes, le serveur les perdait à chaque sauvegarde.
      Fait : voir « Fait » (« Briques d'un procédé »).
- [x] **Étiquettes regroupées par brique** : une étiquette pour les étapes étiquetées d'une même
      brique (son nom, une ligne par étape, une accolade sur leurs couches), partout où les
      étiquettes s'affichent. Fait : voir « Fait ».
- [x] **Unité des paramètres déclarés** : un vrai champ `unit`, l'ancienne astuce de l'obtention
      toujours lue ; niveau de version d'une unité seule choisi et documenté. Fait : voir « Fait ».
- [x] **Diff des étiquettes** : `structure-diff` dit, à part, ce qui change aux étiquettes et à leur
      regroupement ; la fiche l'écrit au lieu de « identique à la version précédente ». Fait :
      voir « Fait ».
- [x] **Étiquettes très longues** : mesurées dans le navigateur, elles sortaient du SVG ; corrigé.
      Fait : voir « Fait ».

Relecture du lot 5 (2026-10-04) :

- [x] **Accolades superposées** : sur un nanofil, les hauteurs des briques se recouvrent et leurs
      accolades se dessinaient au même endroit. Fait : voir « Fait » (« Relecture du lot 5 »).
- [x] **Diff entre deux études indépendantes** : étiquettes appariées par id d'étape et briques par
      `group_id`, deux études identiques lancées à part se disaient tout différent. Fait.
- [x] **Dissocier puis regrouper les mêmes étapes** : un faux « regroupées ; séparées ». Fait.
- [x] **Unité ajoutée seule** : un correctif que la fiche disait « identique ». Fait.
- [x] **Nom d'une brique de bibliothèque** : sans limite, il faisait refuser (422) toute simulation
      où la brique était insérée. Fait.
- [x] **Largeur des caractères hors ASCII** : « Œ », « 中 », un émoji sortaient du SVG. Fait.

### 3 quater. Références de structure

Demandé le 2026-10-04 : « une structure de ref, c'est pour l'utiliser dans différents projets et
pouvoir la tracer au fur et à mesure ; une page à l'échelle de toute l'application pour tracer
l'évolution des références et voir leur dernière mise à jour ; la même vue que l'évolution des
structures mais en version références, pour tous les projets : on choisit la référence et on voit
son évolution, uniquement les versions de référence ; quand on démarre une expérience ou un projet
on part souvent d'une référence, rarement d'une structure vierge ».

Décisions (font foi) :

- Une **référence** est un objet **global** de l'application, avec des versions qui peuvent venir
  de µprojets différents. « Promouvoir en ref » devient « Publier comme référence » : on choisit la
  référence (proposée d'office : celle dont vient l'étude) ou on en crée une. Les refs locales
  existantes du même nom (ex. epitaxie-standard) sont **regroupées** en une référence ; les refs à
  nom automatique (« ref vX.Y.Z ») restent de simples repères locaux.
- Numérotation **MAJEUR.MINEUR calculée** : la nouvelle version est comparée à la version de
  référence dont elle dérive (majeur → X+1.0 ; mineur ou correctif → X.Y+1 ; identique → 409),
  numéros uniques même entre branches parallèles (deux dérivations d'une même version → 1.1 et
  1.2 ; un majeur quand 2.0 existe → 3.0).
- Publier une version : tout **éditeur** du µprojet source ; renommer, décrire, retirer une
  référence : son créateur ou un admin. Tout est tracé (qui, quand, depuis quel µprojet, étude,
  version).
- Démarrage : « Nouvelle expérience » ouvre **d'abord** le choix d'une référence (dernière version
  proposée, recherche, choix de version) ; partir d'une structure vierge reste possible mais
  secondaire. L'étude **retient** la version de référence dont elle part (suivi des usages). Même
  proposition après la création d'un µprojet.

- [x] **Serveur** : plugin `references` (après experiments), routes `/api/references`,
      `/api/references/{slug}/versions[/{number}[/structure-diff]]`, `/api/reference-versions`,
      `reference_origin` au lancement d'une étude, regroupement des refs locales, badges de la page
      d'évolution (`include_versions`). Fait : voir « Fait » (« Références de structure »).
- [x] **Page des références** (toute l'application, entrée « Références » de la barre du haut) :
      la liste (`/references`) et l'évolution d'une référence (`/references/{slug}`), le panneau
      d'une version, renommer / décrire / retirer, `referencesApi`. Fait : voir « Fait »
      (« Références de structure, pages »).
- [x] **Publier comme référence** (page d'évolution d'un µprojet, fiche) à la place de « Promouvoir
      en ref » et de « Publier dans la bibliothèque ».
- [x] **Badges « R nom 1.1 »** sur les nœuds de la page d'évolution d'un µprojet.
- [x] **Nouvelle expérience depuis une référence** (page µprojet, accueil, après la création d'un
      µprojet, « Partir de cette version » d'une référence) ; l'origine sur la fiche.

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

- **Références de structure, pages** (2026-10-04, point 3 quater ; `ARCHITECTURE.md` § 5
  « Pages », § 6 « Les références, côté pages »).
  - `/references` : nom, description, dernière version, date de la dernière mise à jour, µprojet
    source, nombre de versions et d'usages, la plus récemment mise à jour d'abord ; recherche
    (`?q=` du serveur, gardée dans l'adresse) ; « Nouvelle référence » ; « Nouvelle expérience
    depuis une référence ». Entrée « Références » de la barre du haut, carte dans `/bibliotheque`.
  - `/references/{slug}` : le diagramme de la page d'évolution des structures, **sans le dupliquer**
    - son dessin est sorti d'`evolution.js` dans `experiments/static/evolution-graph.js`
    (`EvolutionGraph`), que les deux pages utilisent ; versions de référence seules, majeur
    (plein) et mineur (anneau) distingués, correctif et import identique aussi, une colonne par
    branche parallèle, µprojet source sur chaque rangée, nombre d'usages, rattachement déduit en
    pointillés et écrit sur la rangée ; le panneau : structure étiquetée (SVG serveur, agrandie au
    clic), auteur (ou « repère importé »), date, note, source (lien vers l'étude pour un membre,
    sinon le seul nom du µprojet et la raison), parente, usages repliables (« 3 études en sont
    parties »), comparer avec une autre version ou avec sa parente, « Partir de cette version » ;
    renommer / décrire / retirer pour son créateur ou un admin (`can_edit`).
  - « Publier comme référence » (`ReferencePublishDialog`) sur la fiche et la page d'évolution :
    référence proposée (l'origine de l'étude, sinon celle où une version dont elle descend a été
    publiée), une autre ou une nouvelle, le parent proposé (« automatique » au choix), la note ;
    le numéro calculé est affiché ; une référence créée dans la boîte puis refusée est retirée.
    Écart : une campagne ou une structure en images n'a pas le bouton (le serveur la refuse).
  - Badges « R nom 1.1 » (navy, distincts de l'or des refs locales) et anneau or sur les nœuds de
    la page d'évolution, via `include_versions` (`api.withQuery` répète un paramètre donné en
    tableau). Les refs locales restent affichées (« Refs locales »), renommer / retirer / suivre
    gardés ; on n'en pose plus (`experimentsApi.createRef` retiré du client, la route reste).
  - « Nouvelle expérience » (page µprojet ; accueil, écart : bouton ajouté, l'accueil n'en avait
    pas) ouvre d'abord « Partir d'une référence » (`ReferenceStartPicker` : recherche, dernière
    version proposée, autre version, aperçu, µprojet à choisir s'il n'est pas donné) ; « Partir
    d'une structure vierge » ouvre l'ancienne boîte (dessin, image, bibliothèque, étude existante),
    qui offre de revenir aux références. Après la création d'un µprojet, sa page s'ouvre sur
    `?premiere-experience=1` et propose la même boîte. Le constructeur
    (`structures/nouvelle?reference=&version=`) charge le procédé de la version en gardant ses ids
    d'étape (choix : l'étude en descend, une version publiée ensuite s'y compare par ids) et envoie
    `reference_origin` ; la fiche dit « Issue de la référence X 1.1 » (lien), « référence
    inconnue » sinon.
  - Vérifié dans le navigateur sur la démo : epitaxie-standard regroupée (1.0 du puits simple, 1.1
    du MQW en rattachement déduit) ; publiée depuis l'évolution du puits simple → 2.0 (majeur,
    depuis 1.0) ; une expérience du MQW partie de 1.0, publiée depuis sa fiche → 1.2 (correctif,
    branche depuis 1.0), la page de la référence montre la branche et l'usage ; non-membre du MQW :
    source masquée. Test : `tests/plugins/references/test_pages.py`.

- **Références de structure, serveur** (2026-10-04, point 3 quater ; `ARCHITECTURE.md` § 3,
  § 4 « Identité d'une expérience », § 5 « references »).
  - Plugin `references` (dépend d'experiments, microprojects, structures ; placé juste après
    experiments) : tables `structure_references`, `reference_versions`, `reference_import_scans`.
    Écart : `structure_references` et non `references`, mot réservé de SQL.
  - Numéro calculé (`service.next_number`) avec le versionnage des études ; écritures sérialisées
    et numéro unique par référence (index) ; 409 `reference_version_identical`.
  - Instantané de la structure à la publication (structure dessinée, procédé, paramètres déclarés
    avec unité, ids d'étape, étiquettes, briques) : rendu SVG, procédé éditable et diff sans l'étude.
    Écart : une structure en images ou une campagne ne se publie pas (422
    `reference_needs_process`) - une référence est un point de départ du constructeur ; leurs refs
    locales restent locales.
  - Règles choisies : le slug d'une référence est fixé à la création (une étude la cite par lui ;
    renommer ne change que le nom) ; un nom est unique sans casse, ni accents, ni ponctuation ;
    retirer une référence qui a des versions est réservé à l'admin (409 pour son créateur), ses
    versions partent avec elle ; « dernière version » = la dernière publiée.
  - `reference_origin` : forme vérifiée par experiments seul, reporté par `amend()`, gardé par une
    fourche et (écart, non demandé mais du même ordre) par une combinaison ; usages lus sur la
    pointe de chaque piste.
  - Regroupement des refs locales : à la première lecture des références (pas au démarrage : le
    noyau n'a pas de crochet de démarrage, et la démo sème ses refs après la migration), chaque
    µprojet lu une fois ; une version identique à son parent à l'import (epitaxie-standard des deux
    µprojets de la démo) reçoit le mineur suivant, `change_level` `none`, au lieu d'un 409.
  - Badges de la page d'évolution : `GET /api/reference-versions?microproject=`, et
    `structure-history?include_versions=` pour montrer une version publiée légère (experiments ne
    connaît pas les références).
  - Le front : voir « Références de structure, pages » ci-dessus.

- **Relecture du lot 5** (2026-10-04, point 3 ter ; `ARCHITECTURE.md` § 4, « Étiquettes de
  couches », « Briques d'un procédé »).
  - *Accolades* : une colonne par accolade dont la hauteur recouvre celle d'une autre
    (`rendering._bracket_columns`, la plus courte au plus près du dessin) ; deux briques empilées
    gardent la même ; la colonne des étiquettes recule d'autant et chaque trait fait son coude
    au-delà de la dernière colonne. Écart : un trait qui part d'une couche enveloppée croise
    toujours les accolades qui l'entourent (à angle droit) - inévitable, l'étiquette est à droite.
  - *Diff* : étapes appariées par id (`service.step_ids_of`, celles d'une ancienne version
    comprises) quand les deux versions en partagent, sinon par position, comme le diff de
    structure ; briques comparées par nom et étapes étiquetées, comme le versionnage (renommée :
    mêmes étapes ; regroupement modifié : même nom). `service.structure_diff` prend désormais le
    dépôt de chaque version.
  - *Paramètres déclarés* : `structure-diff` rend aussi `param_changes` (ajouté, retiré, valeur,
    unité, obtention), écrit « Paramètres : … » sur la fiche, sa comparaison et la page
    d'évolution. Écart : pas seulement l'unité - une valeur de dopage changée (un mineur) se disait
    aussi « identique », la géométrie comparée ne portant pas les paramètres déclarés ; une unité
    passée de l'obtention au champ, la même, n'y figure pas (rien de visible ne change).
    `versioning._split_unit` devient `simulation.split_declared_unit`, partagé.
  - *Nom d'une brique* : `simulation.BRICK_NAME_MAX_LENGTH` (120) pour `ProcessBrick` et pour
    `POST` / `PATCH /api/tech-bricks` ; `maxlength` sur les deux champs du constructeur ; le nom
    d'une brique enregistrée avant la limite est coupé à l'envoi (`bricksPayload`) et le mode
    brique demande de le raccourcir. Écart : les structures enregistrées et les pas de procédé
    gardent leur nom sans limite (rien ne le reprend ailleurs).
  - *Largeur des caractères* : hors ASCII, une lettre accentuée compte comme sa lettre de base,
    tout autre caractère 1,2 em, un émoji ou un pictogramme 1,6 em (mesuré : « Œ » 1,114, « 中 » 1,
    « 🔬 » 1,373) ; tests.

- **Briques d'un procédé, étiquettes regroupées, unité, diff des étiquettes** (2026-10-04, suites
  du point 3 ter ; `ARCHITECTURE.md` § 4, « Étiquettes de couches », « Briques d'un procédé »,
  « Unité des paramètres déclarés »).
  - *Briques* : `structures.simulation.ProcessBrick` (`{group_id, name, source, step_indexes}`),
    `bricks` dans toute requête de procédé (positions consécutives, 422 `invalid_brick`) ; une étude
    les range par ids d'étape sous `process_bricks`, `GET .../process` les rend par positions et le
    constructeur les rattache aux étapes au chargement (`attachBricks`, `bricksPayload`,
    `brick_source` : l'id de la brique de bibliothèque insérée ou créée). Gardées par lancement,
    évolution, fourche, campagne, combinaison (celles de la première étude), écritures légères,
    structures et briques de la bibliothèque. Écart : une brique de bibliothèque insérée devient un
    seul groupe, les briques composées ne s'imbriquent pas ; les briques restaurées arrivent
    dépliées (une brique insérée arrive repliée, comme avant).
  - *Versionnage* : seules, les briques ne changent pas la version (`none`) ; elles ne comptent que
    par les étiquettes qu'elles regroupent (`label_groups` dans la signature) - au plus un
    correctif, comme les étiquettes.
  - *Étiquettes regroupées* (`rendering.annotations_for`, `labelled_svg`) : à partir de **deux**
    étapes étiquetées dans la même brique (écart : une seule étape étiquetée garde son étiquette,
    pour ne pas remplacer « p-GaN » par le nom de la brique) ; titre = nom de la brique, une ligne
    par étape (« p-GaN : 120 nm · dopage Mg 3e18 cm⁻³ ») de la couche la plus haute à la plus
    basse, accolade (`.sp-layer-bracket`) sur la hauteur des couches **créées par les étapes
    étiquetées** (pas toute la brique). Constructeur, fiche, carrousel d'une campagne, page
    d'évolution et rapport : tous reçoivent le SVG du serveur. Écart : l'aperçu des variantes à
    l'écran « Variations » n'envoyait déjà pas les étiquettes ; inchangé.
  - *Unité* : `DeclaredParam.unit` (facultatif, 20 caractères, enregistré sans la clé quand il est
    vide), champ « Unité » du constructeur avec suggestions (`datalist`) ; l'astuce `unit=` de
    l'obtention reste lue. Niveau choisi : une unité ajoutée ou retirée seule (ou passée de
    l'obtention au champ) est un **correctif** qui garde la conclusion (`versioning.same_settings`),
    une unité remplacée par une autre un **mineur** (elle change la valeur).
  - *Diff* : `structure-diff` rend `label_changes` (par étape : ajoutée, retirée, modifiée - texte,
    valeurs ajoutées et retirées ; par brique : regroupées, séparées, renommée, regroupement
    modifié), chacun avec sa phrase ; la fiche (et sa comparaison) et la page d'évolution écrivent
    « Étiquettes : … ». Écart : formulation neutre « p-GaN — ajout : dopage Mg » plutôt que
    « dopage ajouté » (le genre d'un paramètre déclaré n'est pas connu).
  - *Étiquettes très longues* : mesuré dans le navigateur, 40 « W » font 641,6 unités en DM Sans
    600 (1 em par lettre) ; l'ancienne estimation (0,58 em, colonne plafonnée à 320) en laissait 307
    hors du SVG. Largeur désormais estimée par excès caractère par caractère (la plus large de DM
    Sans, Helvetica Neue et Arial, en 400 et 600, mesurée) et colonne sans plafond ; test.

- **Étiquettes de couches** (2026-10-04, point 3 ter). Dans l'inspecteur du constructeur, une étape
  qui crée une couche (dépôt, croissances, lithographie) a la section « Afficher sur la structure » :
  une case, le texte (prérempli du matériau, l'épaisseur cochée d'office) et les valeurs écrites
  dessous - épaisseur (unité lisible, valeur saisie sans arrondi : `150 nm`, `2.5 µm`, `1.234 µm`), composition d'un nitrure à composition
  (`In 20 %`), paramètres déclarés de l'étape (`dopage Mg : 7e18 cm-3`) ; une pastille sur la puce
  de l'étape. Le serveur dessine (`structures.rendering.labelled_svg`) : la structure de
  StructureForge à gauche, les étiquettes empilées à droite sans chevauchement, un trait fin vers la
  couche, jetons de couleur avec leur valeur en repli (SVG autonome) ; aperçu du constructeur, fiche
  (avec « Étiquettes : masquer / afficher », préférence du navigateur), carrousel et cartographie
  d'une campagne (chaque variante ses valeurs), page d'évolution (la structure de la version choisie
  dans le panneau, agrandie au clic) et rapport. Enregistrées par id d'étape
  (`process_layer_labels`) avec la provenance des couches (`process_layer_steps`), reprises au
  chargement (évolution, fourche, modèle) et gardées par les structures et briques de la
  bibliothèque (par position, comme les paramètres déclarés ; une ref publiée garde celles de sa
  version). La provenance des couches vient du serveur : la simulation suit les couches de la
  géométrie étape par étape (`simulation.simulate_process`, `step_index` de chaque couche) ;
  l'ancien alignement de matériaux du constructeur (`computeLayerOrigins`) a disparu, la sélection
  et le survol d'une couche lisent la provenance du serveur. Écarts retenus : ne changer que les
  étiquettes fait une version de niveau **correctif** qui **garde la conclusion** (renommer une
  étape la réinitialise toujours) ; une version sans étiquette n'enregistre aucune des deux clés
  (les anciennes versions n'en ont pas, sans migration) ; un paramètre déclaré n'a pas de champ
  unité : elle est lue dans son obtention (`unit=cm-3`) ; une étape qui a créé plusieurs couches
  pointe vers la plus grande ; la largeur du texte est estimée par le serveur (texte tronqué à 40
  caractères, une valeur à 48) ; les vignettes de l'écran « Variations » restent sans étiquettes
  (90 px de large ; la route d'aperçu les accepte) ; la vignette du panneau de la page d'évolution
  est petite (340 px), d'où l'agrandissement ; le graphe de filiation de la page µprojet et l'atlas
  montrent le SVG tel quel ; une campagne relit les valeurs de chaque variante depuis son plan et
  ses valeurs enregistrées. Correction annexe : les paramètres déclarés d'une étape sont rattachés
  à ses couches dans toutes les images de l'aperçu, et non plus seulement dans celle où elles
  apparaissent.

- **Annotations sur toute image** (2026-10-04, point 3 ter). Un seul modèle, dans le noyau
  (`spectre/kernel/annotations.py` : `{type: arrow | box, x, y, x2, y2, label}` en % de l'image,
  `clean_annotations` : une position hors de l'image, hors de 0 à 100, est refusée en 422), et un seul composant de page (`kernel/static/annotations.js`, global
  `ImageAnnotations` : dessin numéroté, liste des libellés, outils d'un éditeur). Le cahier annote
  ses images externes comme ses images téléversées : une annotation d'une mesure désigne son image
  par `attachment_id` ou `external_image` (le chemin, unique dans la mesure : réordonner les images
  ne déplace pas leurs annotations ; l'ancien format se relit tel quel). Une structure en images
  porte `annotations` sur chaque image de `StructureImage` (champ facultatif, absent des anciens
  objets et des images sans annotation ; `registry_key` inchangée), posées sur la fiche par
  `PUT .../structure-images` avec `If-Match` : écriture légère, aucune version de structure, et une
  évolution qui ne change que des annotations n'en crée pas non plus. Les vignettes (graphe,
  atlas, planche du constructeur, aperçus de la boîte du cahier, panneau de la page d'évolution) et
  le rapport les montrent, en
  lecture seule ; un dessin aux proportions de l'image suit son redimensionnement. Écarts retenus :
  le composant est au noyau et non dans `attachments` (une image externe n'est pas une pièce
  jointe, et il ne connaît que l'`<img>` qu'on lui donne) ; les annotations se posent sur la fiche
  (cahier et planche de la structure), pas dans le constructeur ni dans la boîte d'ajout du cahier,
  qui les gardent et les montrent (remplacer une image retire ses annotations ; retirer une image
  externe aussi) ; une image externe que le serveur ne montre plus garde ses annotations rangées,
  sans les montrer ; dessiner demande un pointeur (outils, libellés et retraits se font au clavier,
  Échap annule l'outil en cours) ; sur la fiche, l'image d'une structure en images reste un lien
  vers l'image en grand, mais aucun geste d'annotation (ni le clic qui termine un tracé) ne l'ouvre ; les libellés sont numérotés sur l'image et écrits dans la liste,
  pas sur l'image ; les images documentaires (graphiques d'exemple d'un type de données de
  caractérisation, captures de la documentation) ne s'annotent pas : ce ne sont pas des images
  d'utilisateur. Pas de test JS du composant (`node` absent du poste de développement) : vérifié
  dans le navigateur (cahier : image téléversée et image externe annotées, réordonnées ; structure
  en images annotée ; rapport téléchargé).

- **Images externes et combinaison, côté interface** (2026-10-04, point 3 bis). La galerie « Images
  de mesure » a quitté l'onglet « Données » : tout est dans le cahier (le repère de l'onglet, le
  rapport et la conclusion ne connaissent que ses entrées ; les anciens jeux s'y lisent comme des
  entrées). La boîte d'ajout du cahier (`entry-dialog.js`) choisit les **images externes** d'une
  mesure manuelle : les dossiers autorisés (nouvelle route `GET .../external-images/roots`, editor,
  les racines telles qu'écrites, `[]` : parcours désactivé), les images d'un dossier à cocher (un
  TIFF listé mais non cochable, avec la marche à suivre ; une image déjà dans la mesure, cochée et
  grisée), ou le chemin d'une image ; légende, ordre (la première est la principale, l'ancienne
  épinglée) et retrait ; une image déjà enregistrée s'aperçoit par l'`url` de l'entrée. **Combiner**
  (« Actions avancées » de la fiche, `advanced.js`) ouvre une boîte : l'autre étude (la recherche
  existante), le titre proposé « A + B » (il suit le choix tant qu'on ne l'a pas changé),
  l'intention, l'hypothèse et la nouvelle plaque (lasermark, emplacement, FDL, avec
  l'autocomplétion du µprojet), et l'aide « crée une nouvelle étude issue de ces deux-là ; elles ne
  changent pas ; son cahier démarre vide » ; créée, sa fiche s'ouvre. La filiation, l'évolution
  des structures (« issue de vX (piste n) et vY (piste m) ») et les liens de la fiche (« Combinaison
  de ») montrent les deux parents ; les légendes disent « Combinaison de deux études ». Écarts
  retenus : pas d'annotations sur une image externe (levé depuis : « Annotations sur toute
  image ») ; une nouvelle image externe ne s'aperçoit qu'une fois enregistrée (aucune route ne sert
  un chemin reçu du client, et c'est voulu) ; le parcours liste les images d'un dossier, pas ses
  sous-dossiers (on tape le chemin) ; l'autre étude se combine à sa pointe (le serveur accepte une
  version, la boîte ne la propose pas) ; objectifs et contexte restent ceux de la première étude ;
  pour une campagne, la plaque saisie est celle de la première variante. Deux corrections côté
  serveur, trouvées en vérifiant l'interface : l'`url` d'une image externe nomme toujours la
  version lue (`?version=`, la pointe comprise) - sans elle, réordonner ou retirer des images
  faisait désigner à une même adresse une autre image, que le navigateur pouvait garder en cache ;
  la filiation (`GET .../lineage`) tire l'arête d'une combinaison depuis le nœud de chacune des
  deux études - deux pistes parties d'un même point sans changer sa structure étaient repliées sur
  ce point, et la combinaison n'y montrait qu'un parent.
- **Les images externes deviennent un contenu du cahier** (2026-10-04, point 3 bis, côté serveur).
  Une mesure manuelle porte `external_images: [{path, caption}]`, validées à l'écriture par la
  politique du plugin `external_images` (racines `SPECTRE_EXTERNAL_IMAGE_ROOTS`, chemin réseau hors
  racines refusé sans toucher au disque, formats affichables - TIFF refusé avec la marche à suivre -,
  fichier présent) ; à la lecture, chaque image porte `index`, `name`, `status` et son `url`, servie
  par identifiant : `GET .../notebook-entries/{entry_id}/external-images/{index}` (le chemin lu dans
  le cahier, jamais reçu du client, revérifié à chaque lecture). Les routes `.../image-sets`
  disparaissent ; les anciens jeux (`data_items`) se lisent comme des entrées manuelles qui gardent
  leur id (titre = nom du jeu, note conservée, une mesure non située, l'image épinglée en premier ;
  `wafers` = la plaque de la variante d'une campagne), et la première écriture dans le cahier les
  enregistre au nouveau format. Le panneau séparé de la fiche disparaît. Choix : **le plugin
  `external_images` reste**, réduit à la politique des chemins et au parcours (une raison de changer
  à part : l'accès au disque du serveur), et notebook en dépend (`external_images` passe avant
  `notebook` dans `PLUGINS`, ne dépend plus que de `microprojects`). Écarts retenus : une image déjà
  sur l'entrée n'est pas revérifiée à l'écriture (une image d'un ancien jeu, déplacée depuis, reste) ;
  une mesure sans image externe n'enregistre pas la clé (elle se lit `[]`) ; un jeu d'une variante
  sans plaque vaut pour toute la piste, la variante rappelée dans le texte ; un titre de jeu trop long
  est tronqué, entier dans la note ; 100 images au plus par mesure, sans doublon ; `ctx.setDataCount`
  disparaît de la fiche (le cahier est le seul panneau de l'onglet « Données »).
- **Combiner deux études crée une nouvelle étude** (2026-10-04, point 3 bis, côté serveur).
  `POST .../experiments/{exp}/merges` disparaît : `POST /api/microprojects/{mp}/experiments` avec
  `merge_of` (exactement deux études du µprojet, version facultative : la pointe) et les champs d'un
  lancement → 201 + `Location` vers la nouvelle piste C. C est construite par
  `follow.Repository.merge(a, b, branch=<C>)` (Follow accepte un commit à deux parents sur une
  nouvelle branche) : deux parents (filiation, évolution des structures : arêtes `merge` depuis A et
  B), la structure de A (la règle de combinaison d'avant, sans résolution de conflit), cahier vide,
  ni étiquettes ni conclusion ; A et B inchangés. `_merge_notebook` et tout code de fusion de cahier
  sont retirés. Écarts retenus : l'hypothèse reste facultative, comme à un lancement (titre,
  intention et plaque obligatoires) ; objectifs et contexte viennent de A faute de mieux dans la
  requête, comme pour une piste partie d'une version ; deux versions de la même piste, ou deux fois la même version
  désignée par deux pistes, sont refusées (`same_experiment`) ; une version d'avant la fourche de la
  piste désignée (son histoire la contient, mais elle n'est pas à elle) est refusée en 422
  (`version_before_line`) plutôt que d'attribuer C à la mauvaise piste ; une étude d'un autre µprojet est introuvable (404) et `merge_of` refuse tout
  champ de plus (422) ; le formulaire d'intention du µprojet s'applique ; le numéro de version de C
  continue l'histoire de A (la règle d'une piste partie d'une version) ; les fusions d'avant (une
  version de A à deux parents) restent lisibles, l'arête depuis leur premier parent gardant le type
  `parent`. Le jeu de démo (`seed_demo.py`) combine en une nouvelle étude.

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
  prévues dans le constructeur, pas de conversion d'une entrée manuelle en PRISM. Écarts retenus :
  la galerie « Images de mesure » (external_images) reste dans l'onglet « Données », à côté du
  cahier (depuis, elle en est un contenu : voir plus haut) ; le filtre par étape se fait dans la page (sans `?step=`) pour que le rapport garde tout
  le cahier ; cocher la première bulle d'une entrée non située (une ancienne preuve) y range son
  contenu, décocher la dernière la rend non située ; une mesure à une étape retirée se range à
  droite des autres ; les réglages PRISM passent par « Modifier » (« Actualiser » reste sur la carte
  d'une entrée PRISM à une mesure) ; la conclusion renvoie le champ `observed` d'un verdict au lieu
  de l'effacer ; une virgule décimale d'un tableau collé se lit comme un nombre. Pas de test JS de
  l'analyse du tableau collé (`node` absent du poste de développement).
- **Un seul cahier de données, côté serveur** (2026-10-04, point 3). Le plugin `evidence` a disparu :
  `notebook` porte toutes les données d'une étude (`.../notebook-entries`, `kind: prism | manual`,
  une seule forme : plaques mesurées `wafers`, une mesure par étape `measurements[].step_id`), avec
  la règle « la donnée suit la plaque » (`applies`) et l'étape retirée (`step_retired`). **Pas de
  migration** : les vues de l'ancien cahier et les preuves (Follow + `metadata`) sont converties à
  la lecture, sans perte, les preuves gardant leur id (la conclusion les cite toujours) et leur
  `step_index` devenu un id d'étape ; la première écriture dans le cahier enregistre le cahier
  converti. Spectre n'écrit plus de preuve Follow. Détail dans `ARCHITECTURE.md` § 4 et § 5.
  Écarts retenus, pour ne rien perdre des anciennes preuves : `in_report` est gardé (le rapport
  s'en sert), une valeur porte un `name` (la métrique à laquelle renvoie `Objective.metric`) et une
  pièce jointe est `{id, caption}` (un id seul est accepté) pour garder les légendes.
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
  n'offrent « + Nouveau µprojet » qu'aux comptes autorisés. Écarts retenus : la règle vit dans
  `areas` (chaque projet l'expose et `areas` ne peut pas importer `microprojects`), le refus reste
  levé à un seul endroit ; seul le projet d'arrivée d'un changement de projet est vérifié
  (renommer ou changer de thématique dans le même projet ne l'est pas, et un `owner` peut sortir
  son µprojet du projet d'une équipe) ; `microprojects.service.create` reçoit le compte (`owner: User`) et non plus son id.
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
