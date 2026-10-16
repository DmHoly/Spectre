# Architecture de Spectre — noyau et plugins

Ce document est le **contrat** de l'architecture. Toute nouvelle fonctionnalité s'y conforme, et
toute exception y est écrite. Le *pourquoi* de chaque choix (constats, coûts, garde-fous) est dans
[`REVIEW.md`](REVIEW.md).

## 1. Principes

1. **Un plugin = une raison de changer.** Il possède son code back, son code front, ses pages,
   ses tables et ses tests, sous **le même nom** partout :

   | Côté | Emplacement | Exemple (`lots`) |
   |---|---|---|
   | Python | `spectre/plugins/<plugin>/` | `spectre/plugins/lots/service.py` |
   | API | `/api/<ressource>` (anglais, pluriel, kebab-case) | `/api/lots/{lot_id}` |
   | Front (JS, CSS) | `spectre/plugins/<plugin>/static/`, servi sous `/static/<plugin>/` | `/static/lots/client.js` |
   | Pages HTML | `spectre/plugins/<plugin>/pages/` | `pages/lot.html` → `/lots/{code}` |
   | Client JS | `static/<plugin>/client.js`, global `<plugin>Api` (camelCase) | `lotsApi.get(id)` |
   | Tests | `tests/plugins/<plugin>/`, helpers `tests/support/<plugin>.py` | `tests/plugins/lots/test_api.py` |

2. **Le front passe par l'API Spectre, et par elle seule.** Une page n'appelle jamais une URL
   `/api/...` à la main : elle passe par les fonctions du `client.js` du plugin propriétaire. Pas
   de chemin disque, de HTML ou de règle métier fabriqués côté client quand le serveur les connaît
   déjà. Le test `tests/contracts/test_frontend_routes.py` fait échouer tout appel front vers une
   route inexistante (méthode et chemin).
3. **Les dépendances forment un DAG explicite.** Un plugin n'importe que les plugins listés dans son
   `depends_on`, et seulement leurs modules publics, jamais leur `api` : `service` (ou `store`),
   `models`, `deps`, `schemas`, plus les modules de domaine que trois plugins offrent en propre -
   `accounts.security` (cookie de session, hachage des jetons), `experiments.repository`,
   `experiments.lineage`, `experiments.entities`, `experiments.insights`, `experiments.plans`,
   `experiments.versioning` (la règle X.Y, que les briques suivent), `structures.kinds`,
   `structures.campaigns`, `structures.simulation`, `structures.rendering` et
   `process_library.tech_bricks` (la forme d'une brique, lue par la promotion). La liste est tenue par
   `tests/contracts/test_plugin_imports.py` (`PUBLIC_MODULES`, `PUBLIC_EXTRA`). Le noyau n'importe
   aucun plugin.
4. **Le domaine ne connaît pas HTTP.** `service.py`, `store.py` et `models.py` n'importent pas
   FastAPI et lèvent des exceptions de `spectre.kernel.errors`. `api.py` ne fait que lire la
   requête, appeler le service et sérialiser. Les codes HTTP sont posés à un seul endroit, par
   les exception handlers du noyau.
5. **YAGNI d'abord.** Une abstraction (Protocol, registre) n'existe que s'il y a **au moins deux
   implémentations réelles**. Les plugins sont listés statiquement : ni découverte dynamique, ni
   entry points, ni bus d'événements.

## 2. Le noyau (`spectre/kernel/`)

Le noyau ne connaît **aucune** fonctionnalité métier. Il fournit :

| Module | Rôle |
|---|---|
| `plugin.py` | `Plugin`, `Page`, `NavEntry`, `Migration` (dataclasses figées ; `Migration.files` : les fichiers hors base qu'une migration réécrit ou supprime), `RequestTrace` (ce que voit un observateur de requêtes, `Plugin.observe`) et `check_dependencies(plugins)`, qui vérifie l'ordre topologique au démarrage |
| `app.py` | `create_app(plugins=PLUGINS)` : migrations, `include_router` de chaque plugin, routes de pages, montage de `/static/<plugin>/` et `/static/kernel/`, exception handlers, middleware `Cache-Control: no-cache`, et le middleware des observateurs de requêtes : chaque route d'un plugin marque sa requête de son plugin et de son genre (`api` ou `page`, une dépendance posée par `create_app`), et après la réponse chaque `Plugin.observe` d'un plugin actif reçoit une `RequestTrace` (plugin, genre, méthode, gabarit de la route, statut, durée, cookies) - une exception de l'observateur est journalisée, jamais renvoyée |
| `db.py` | `data_dir()`, `connect()`, `get_conn()`, exécuteur de migrations versionnées (table `schema_migrations(plugin, migration_id, applied_at)`), `rebuild_table()` pour les changements non additifs (CHECK, NOT NULL), qui garde le compteur d'`AUTOINCREMENT` de la table (un id supprimé n'est jamais redonné). Avant la première migration en attente d'une installation existante, la base (API de sauvegarde de sqlite3) et les fichiers déclarés par les migrations (`Migration.files`, copiés juste avant chacune) sont sauvegardés dans `data_dir/backups/<horodatage>/` : une migration peut supprimer ou réécrire ce que l'ancien code lit, et l'ancien code ne lit pas une base migrée - revenir en arrière, c'est restaurer cette copie |
| `errors.py` | `DomainError` → `Unauthorized` (401, `unauthorized` : pas de session, levée par `accounts.deps.current_user`), `NotFound` (404), `Forbidden` (403), `Conflict` (409), `PreconditionFailed` (412), `InvalidInput` (422), `UpstreamError` (502), `Unavailable` (503) ; un handler unique renvoie `{"detail": str, "code": str}`. Un plugin peut sous-classer `DomainError` pour un statut qui lui est propre (`attachments.store.TooLarge` : 413, `too_large`), le même handler s'en charge |
| `locks.py` | `keyed_lock(namespace, key)` : un `threading.Lock` par clé (le serveur tourne en un seul processus) |
| `fs.py` | `replace(src, dst)` : le `os.replace` de toute écriture atomique (fichier temporaire du même dossier, puis remplacement), réessayé quelques fois, à intervalles croissants, sur `PermissionError` - sous Windows, un antivirus ou un lecteur tient la cible un instant (de même pour le dossier de bibliothèque assemblé puis renommé, `library.service`) ; `write_text(path, text)` : l'écriture atomique complète (temporaire unique, `fsync`, `replace`), celle des dépôts Follow (`experiments.repository`) |
| `annotations.py` | La forme des annotations d'une image, la même pour toute image que Spectre montre : `ImageAnnotation` (`{type: "arrow" \| "box", x, y, x2, y2, label}`, en % de l'image, champs en plus refusés) et `clean_annotations(raw, limit=100)` (positions dans l'image : des nombres finis entre 0 et 100 ; libellé de 200 caractères au plus ; 422 `invalid_annotation`). Le noyau ne sait pas à quelle image une annotation appartient : le cahier la range dans la mesure par une clé d'image, une structure en images sur l'image elle-même. Au noyau plutôt qu'à `attachments` : une image externe n'est pas une pièce jointe, et `notebook` et `structures` s'en servent tous deux |
| `json_store.py` | Collections JSON `{"items": [...]}` d'éléments à `id`, lues et écrites sous un verrou par chemin, de façon atomique ; un élément illisible est écarté à la lecture et gardé tel quel à l'écriture (`ItemStore`, `read_json`, `write_json`, `path_lock`) - les bibliothèques de `process_library` |
| `mail.py` | `send_email(to, subject, body)` : SMTP si `SPECTRE_SMTP_HOST`, sinon journalisation **sans le corps** hors `SPECTRE_EMAIL_DEBUG=1` |
| `pages.py` | Service des pages HTML d'un plugin, avec la barre du haut commune à la place du marqueur `<!-- spectre:topbar -->` (fil d'Ariane déclaré dans le marqueur : `crumb-id`, `crumb-text`) : marque, navigation construite à partir des `NavEntry` des plugins actifs, relue à chaque requête (une entrée peut être réservée à certaines pages : `NavEntry.pages`, ou aux administrateurs : `NavEntry.admin`, rendue cachée et révélée par `accounts/static/session.js` ; une entrée à icône, `NavEntry.icon`, devient un bouton à côté de la session : la roue crantée des Paramètres, le comparateur, la documentation ; une entrée qui nomme un groupe, `NavEntry.group`, est rangée dans son menu déroulant, `NAV_GROUPS` : « Structure » = bibliothèque + références, « Gestion » = lots + planning + équipes ; `NavEntry.glyph` : le pictogramme devant le libellé, « µ » des Projets), place de la session. Retire d'une page les `<script>` et `<link>` des statiques des plugins éteints et les nomme sur `<html data-plugins-off="...">` ; la page d'un plugin éteint est un 404 « Module désactivé » |
| `plugin_states.py` | L'activation des plugins, réglée à chaud par un administrateur (§ 3, *Activer et désactiver un plugin*) : `PluginStates` (`is_enabled`, `blocked_by`, `all_dependents`, `set_enabled`, `core`), installé par `create_app` (`app.state.plugin_states`) ; `is_enabled(name)` pour un plugin qui en sert d'autres (`search`, `experiments.repository`). Sa table `plugin_states(plugin, enabled, updated_at, updated_by)` est, avec `schema_migrations`, la seule table du noyau |
| `database.py` | La base vue par un administrateur (plugin `settings`, Paramètres > Base de données) : `write_backup(target)`, le ZIP de tout `data_dir()` (la base copiée par l'API de sauvegarde de sqlite3, puis tous les fichiers sauf `backups/`, et un `manifest.json`) - restaurer, c'est arrêter Spectre et dézipper à la place du dossier ; `tables()`, `rows(table, q, sort, descending, offset, limit)` (lignes désignées par leur `rowid`, recherche dans toutes les colonnes, clés étrangères des colonnes), `update_row` et `delete_row` (clés étrangères actives : cascade du schéma, ou 409 `integrity_error`). Colonnes secrètes (mot de passe, sel, jeton, empreinte) masquées et jamais écrites ; `schema_migrations` et `plugin_states` en lecture seule ; chaque écriture journalisée avec son auteur. Les données hors SQL (études : dépôts Follow) ne sont pas des tables : la page les liste et les supprime par l'API d'`experiments` |
| `http.py` | Petits helpers HTTP : `created(response, location)`, conversion `ETag` / `If-Match` |
| `static/` | Front du noyau : `api.js` (client HTTP : JSON, `upload(FormData)`, `blob`, `If-Match`, redirection 401, erreurs 422 lisibles ; `withQuery` répète un paramètre donné en tableau, `?id=a&id=b`), `ui.js` (`escapeHtml`, `initials`, dates, durées, `routeParams(pattern)`, `pluginEnabled(name)`), `timeline.js` (axe des mois et hachures des frises : lots, thématique), `annotations.js` (global `ImageAnnotations` : les annotations d'une image dessinées et numérotées, leur liste et leurs outils - § 6), `shell.js` (barre du haut : navigation active), `kernel.css` (tokens et composants de la charte), `img/`, `vendor/` (d3, codemirror) |

```python
@dataclass(frozen=True)
class Plugin:
    name: str                              # identique en Python, sous /static/<name>/ et dans les tests
    depends_on: tuple[str, ...] = ()
    router: APIRouter | None = None        # routes /api de ce plugin
    page_router: APIRouter | None = None   # routes de pages spéciales (redirections), incluses avant ses pages
    pages: tuple[Page, ...] = ()           # Page("/lots/{code}", "lot.html")
    nav: tuple[NavEntry, ...] = ()         # entrées de la barre du haut
    migrations: tuple[Migration, ...] = ()
    enabled: Callable[[], bool] = lambda: True   # disponible sur l'instance, lu au démarrage (kpis_demo : SPECTRE_DEMO_DATA=1)
    title: str = ""                        # ce que montre Paramètres > Plugins : un nom lisible,
    description: str = ""                  # une phrase sur ce qu'il apporte,
    icon: str = "puzzle"                   # une clé de settings/static/icons.js
    required: bool = False                 # du noyau : ne se désactive pas, ni ce dont il dépend
    observe: Callable[[RequestTrace], None] | None = None  # appelé après chaque requête d'une route de plugin (usage)
```

Le `page_router` d'un plugin est inclus **avant** ses pages : une redirection peut viser un gabarit
plus étroit qu'une page du même plugin. Deux cas, tous deux dans `experiments` : un ancien id de
version sous la page d'une étude (`/microprojets/{slug}/experiences/{version_id:experiment_version}`,
convertisseur d'URL Starlette `exp_<16 hex>` déclaré par `experiments.api`, forme qu'aucun nom de
piste ne peut prendre), et l'ancienne page des refs locales (`/microprojets/{slug}/refs`, 302 vers
`/microprojets/{slug}/evolution`).

Les plugins sont listés **dans l'ordre topologique** dans `spectre/plugins/__init__.py`
(`PLUGINS = (...)`). L'application est construite par `create_app()`, en mode factory pour
uvicorn (`spectre.kernel.app:create_app`). Aucun `app` n'est créé à l'import d'un module.

## 3. Les plugins

Les plugins sont listés dans l'ordre topologique. Chaque plugin ne dépend que des plugins
placés au-dessus de lui.

| # | Plugin | Responsabilité | Dépend de | Tables / stockage |
|---|---|---|---|---|
| 1 | `accounts` | Comptes, sessions, mot de passe, profil, rôle admin global. Fournit `deps.current_user` et `deps.require_admin` | — | `users`, `sessions`, `password_resets` |
| 2 | `settings` | Paramètres de l'application, réservés aux administrateurs : page `/parametres` à menu latéral, une section par couche réglable, ouverte par une roue crantée dans la barre du haut. Les plugins (`GET /api/plugins`, `PATCH /api/plugins/{plugin_name}` `{enabled}`), dont la règle est au noyau (`kernel.plugin_states`) ; la base de données (`GET /api/database`, `GET /api/database/backup` : le ZIP, `GET /api/database/tables`, `GET .../tables/{table_name}/rows`, `PATCH` et `DELETE .../rows/{row_id}`, routeur annexe `database_api.py`), dont la mécanique est au noyau (`kernel.database`) | accounts | — (au noyau) |
| 3 | `teams` | Équipes - nom, badge (couleur `#rrggbb`, libellé court) - et leurs membres (`manager` ou `member`), page Équipes. Fournit `service.managed_team_ids(user_id)`, `roles_of(user_id)` et `Team.ref()` (le badge tel que l'API le sert). Ce qu'une équipe possède est dit par `areas` et `microprojects` | accounts | `teams` (dont `color`, `badge`), `team_members` |
| 4 | `search` | `GET /api/search`, qui agrège les fournisseurs déclarés par les autres plugins (`register_provider`) | accounts | — |
| 5 | `library` | Bibliothèque racine YAML de l'instance (matériaux, recettes, présets, briques, textes d'UI), chargeur générique avec cache mtime, registre `LibraryFile` alimenté par les plugins propriétaires, édition réservée à l'admin | accounts | `data_dir/library/*.yml` (copiés depuis `library/defaults/` au premier démarrage, et les `*.yml` d'un `<dépôt>/library` d'avant par-dessus) |
| 6 | `areas` | Projets corporate (*management areas*), les équipes qui y travaillent, leurs thématiques (chacune à une équipe, avec les équipes invitées) et objectifs. Pages accueil, projet et thématique. Fournit `service.can_manage(user, area)`, `managed_area_ids(user)`, `can_place_microproject(user, area)`, `can_manage_thematic`, `visible_thematic_ids(user)` et `thematic_ids_of_teams` | accounts, teams | `management_areas`, `area_teams`, `thematics` (dont `team_id`, `ON DELETE SET NULL`), `thematic_teams`, `area_objectives` |
| 7 | `microprojects` | µprojets (CRUD, numéro, rattachement à un projet ou une thématique, recherche), membres, rôles, invitations. Fournit la règle d'accès (`service.access`, `effective_role`, `check_role`) et `deps.require_role` | accounts, areas, search | `microprojects`, `memberships`, `invitations` |
| 8 | `attachments` | Fichiers téléversés d'un µprojet (blob + sidecar), types, tailles, service des octets | microprojects | `data/microprojects/<slug>/attachments/` |
| 9 | `structures` | Pont StructureForge : matériaux, recettes, simulation, aperçu de campagne DOE, rendu SVG, **types de structure** (`process`, `campaign`, `images`) exposés par `kinds.py`. Pages du constructeur | accounts, library, attachments | — |
| 10 | `experiments` | Pistes d'étude et versions (dépôt Follow d'un µprojet) : création, évolution, statut, conclusion, étiquettes, entités physiques, combinaison de deux études (une nouvelle piste à deux parents), suppression, diff, filiation, refs, statistiques et frise transverses. Seul point d'écriture vers Follow (`service.amend`) | microprojects, structures, attachments | `data/microprojects/<slug>/follow/` (dont `retired_lines.json`, les noms des pistes supprimées) |
| 11 | `comparator` | Comparateur de structures : le tableau d'une liste de plaques, d'études et de versions de référence (`GET /api/comparisons`), une ligne par plaque ou structure, une colonne par paramètre regroupée par étape, chaque cellule comparée à la ligne de base (modifié, paramètre ajouté, couche en plus, étape déplacée, couche absente : `table.py`, pur) ; registre des sources de lignes (`register_source`) - les études ici, les plaques et les références chez leurs plugins ; page `/comparateur`, composant `Comparator` des pages qui comparent des structures. Ne stocke rien | experiments, microprojects, structures | — |
| 12 | `process_library` | Structures enregistrées, présets d'étape, briques technologiques (portées `builtin` / `shared` / `microproject`) ; une brique est **versionnée** X.Y (ses versions gardées avec elle, `tech_bricks.py`) et peut être une **brique de référence** (promue par le plugin promotion). Pages bibliothèque, présets, briques d'un µprojet, briques de référence (`/briques`), fiche d'une brique (`/briques/{id}`) | structures, microprojects, library, experiments (où servent les briques, la règle de numérotation) | JSON par portée |
| 13 | `references` | Références de structure de toute l'application : versions `MAJEUR.MINEUR` publiées depuis les études des µprojets (numéro calculé, instantané de la structure), leur évolution, leurs usages (les études parties d'une version, lues dans `reference_origin`), la source « référence » du comparateur (`comparison_source.py`), les refs locales d'avant regroupées une fois par migration (`local_refs.py`) | experiments, microprojects, structures, comparator | `structure_references`, `reference_versions`, `retired_reference_slugs` |
| 14 | `promotion` | Promouvoir une structure comme référence : le seul chemin pour choisir une nouvelle référence ou une nouvelle version (une étude, la variante d'un split, une version passée). Page `/promotion` (formulaire, vérifications, journal) ouverte par le bouton « Promouvoir comme référence » de chaque fiche, variante, conclusion « Retenir comme référence », page d'évolution et page de référence (`static/link.js`, `PromotionLink`). **Registre de règles** (`rules.py`, `register_rule`) : chaque règle rend `ok` / `warn` / `block` ; une règle de plus ne change ni le formulaire, ni l'API. Écrit les versions par `references.service.plan_publication` / `record_publication`. La même page (`?brique=`) promeut une **brique de référence** avec ses propres règles (`brick_rules.py`) | experiments, microprojects, structures, references, process_library | `promotions` (le journal : source, référence, numéro, pourquoi, verdicts des règles du jour) |
| 15 | `intent_forms` | Formulaires d'intention (portées) et formulaire actif d'un µprojet | experiments, microprojects | JSON + `follow/commit_form.yml` |
| 16 | `wafers` | Index des plaques suivies, clé `wafer_key`, passeport d'une plaque, recherche par lasermark et par FDL, politique de visibilité, plaques de chaque FDL (`fdl_source` : PRISM - hook `fdl_wafers`, les lasermarks cités par le ticket Gozer, en lecture seule - avec la base locale `fdl_wafers`, saisie à la main, en repli pour une FDL que Gozer ne connaît pas ; `SPECTRE_FDL_SOURCE=local` pour s'en passer, démo avec `SPECTRE_DEMO_DATA=1`) ; la source « plaque » du comparateur (`comparison_source.py`) ; la vie d'une plaque en ligne (`GET /api/wafers/{wafer_key}/tracking`, `POST .../tracking/refresh`) : les tables lues par la source (`tracking_source` : les hooks PRISM de la catégorie « Traçabilité » - MES, épitaxie et fiche Gozer, FDL par plaque et par lot, tests, étapes de FDL - ou la démo), assemblées en une fiche (`tracking_model` : statut en cours / en attente / clos / introuvable, étape courante, parcours MES, épitaxie, FDL et leur avancement, tests) et gardées avec leur date de lecture (`tracking` : relues d'elles-mêmes après 24 h, plus jamais pour une plaque immobile depuis 30 jours, toujours sur le bouton ; une relecture en échec garde la fiche et le dit). Avec `characterization.prism_source`, les modules qui importent `prism` (`tracking_source`, `fdl_source`). Les **fiches de plaque** (`records` : une plaque enregistrée pour elle-même, avant toute étude - le monde d'avant Spectre) : `GET /api/wafers/lookup?lasermark=…` cherche des plaques, plusieurs à la fois, dans Spectre puis dans la base par `TrackingSource.lookup` (hooks `wafer_record` et `wafer_mes_history`, une lecture chacun, résumées par `tracking_model.lookup_summaries` ; la démo ignore les lasermarks en `ZZ`) ; `POST /api/wafer-records` crée les fiches avec ce que la base en disait (source `prism` / `demo`, `manual` quand elle ne la connaît pas ou n'a pas répondu), `DELETE /api/wafer-records/{wafer_key}` les retire (auteur ou admin) ; l'index et le passeport les connaissent (`count` 0, `latest` `None`, `record`) ; sur la page d'une plaque, « Rattacher à une étude » (`attach.js`) réécrit les entités d'une étude existante par `experiments` | experiments, search, comparator | cache mémoire, `fdl_wafers`, `wafer_tracking`, `wafer_records` |
| 17 | `twins` | Plaques jumelles : parmi toutes les plaques suivies que le lecteur peut lire, celles dont la structure est celle d'une ligne du comparateur - exactement, ou à 1 à 5 variations près (`GET /api/wafer-twins?item=&max_variations=`). Une variation est une différence que le tableau colorerait (paramètre modifié ou ajouté, couche en plus ou absente, étape déplacée : `comparator.table.differences`, même décompte que le résumé du comparateur). Chaque plaque est lue par la structure de sa dernière étude (`wafers.service.latest_members`), une structure partagée n'est lue et comparée qu'une fois ; une structure sans les colonnes de la base est écartée. Panneau `Twins` monté par la page `/comparateur` (le comparateur n'en dépend pas : il vérifie `pluginEnabled("twins")`). Ne stocke rien | experiments, comparator, wafers | — |
| 18 | `lots` | Lots de fabrication, leurs wafers et leurs thématiques visées, Gantt ; ce qu'une lecture compose (expériences, thématiques, retard) dans `views.py` | wafers, areas, experiments, search | `lots`, `lot_wafers`, `lot_thematics` |
| 19 | `planning` | Planning d'une équipe, pour ses managers (et les admins) : les plaques de ses études par thématique ▸ µprojet ▸ épi, les lots qui les portent (en cours, sortis, prévus) et les expériences prévues de ses µprojets (`GET /api/team-plannings`, `GET /api/team-plannings/{team_slug}` ; 403 `planning_forbidden` hors managers ; les sujets d'une équipe sont ses µprojets, `microprojects.team_id`), page `/planning` à frise par semaine. Ne stocke rien : un lot prévu est un lot `planned` du plugin lots, créé et rempli par ses routes depuis la page ; lit `experiments.plans` | teams, areas, microprojects, structures, experiments, wafers, lots | — |
| 20 | `links` | Liens entre µprojets et entre entités physiques | microprojects, experiments | `microproject_links`, `entity_links` ; mis de côté par les migrations, plus lus : `entity_links_unresolved`, `microproject_links_duplicates` |
| 21 | `atlas` | Vue graphe d'un projet corporate | areas, microprojects, experiments, links | — |
| 22 | `characterization` | Types de données de caractérisation (PRISM, ou démo via le Protocol `DataSource`) : catalogue, requêtes, graphiques documentaires. Importe `prism` (`prism_source`, comme `wafers.tracking_source`) | accounts | cache PRISM sous `data_dir/prism` (`PRISM_DATA_DIR`, fixé par `service.current_source()` s'il ne l'est pas) |
| 23 | `prism` | La gestion de PRISM, réservée aux administrateurs : page à menu latéral (comme les Paramètres), une section par sujet - aujourd'hui le catalogue des données de caractérisation (`/prism/donnees`, hooks, colonnes, testeur en direct) ; l'ancien `/donnees` y renvoie (302, requête gardée). Pas d'API : tout vient de `characterization`. Son entrée (admin) est rangée dans le menu « Data » de la barre du haut, avec « Plaques » | accounts, settings, characterization | — |
| 24 | `external_images` | Politique des images externes référencées (TEM, scans) : racines autorisées, formats affichables, lecture bornée ; parcours des dossiers autorisés | microprojects | — |
| 25 | `notebook` | Cahier de données d'une étude, le seul : entrées PRISM (instantanés et vues DataViz) et manuelles (valeurs, textes, tableaux, fichiers, images externes, liens), rattachées aux plaques et aux étapes ; sert les images externes d'une entrée par identifiant ; lit les vues, les preuves et les jeux d'images d'avant (`legacy.py`) | characterization, experiments, attachments, external_images | `snapshots/`, métadonnées Follow (`notebook_entries`) |
| 26 | `kpis` | Registre de KPI (`register`) et séries mensuelles d'un projet corporate | areas, experiments | — |
| 27 | `kpis_demo` | Séries et fiche d'étude fictives. **Actif seulement si `SPECTRE_DEMO_DATA=1`** | kpis, structures | — |
| 28 | `usage` | Mesure de l'utilisation, pour les administrateurs : son observateur de requêtes (`recorder.observe`) compte chaque requête d'un compte connecté - le compte, l'heure locale, le plugin, le genre et le gabarit de la route, rien d'autre - en mémoire, écrits en base toutes les 15 s et avant toute lecture ; ni les requêtes anonymes ni les siennes. Le rapport d'une période (`service.report`) : adoption, comptes actifs par jour ouvré, modules, pages et routes, carte de chaleur, rythme de chaque compte, comparés à la période d'avant. Page Paramètres > Utilisation (section du menu de `settings`, cachée quand `usage` est éteint) | accounts, settings, teams | `usage_counts` (un compteur par heure, compte, plugin, genre, méthode et route ; sans clé étrangère : l'histoire d'un compte supprimé reste) |
| 29 | `simulation_progress` | La barre de chargement du constructeur de structures : l'étape en cours et le temps écoulé d'une simulation de plusieurs secondes (`GET /api/simulation-runs/{run_id}`). Le calcul reste à `structures` : la page donne un identifiant à sa simulation (`POST /api/simulations?run=`), `simulation.simulate_process` note sous lui chaque étape terminée (`run_progress`, en mémoire, les 64 dernières ; une étape reprise d'un état gardé compte faite d'emblée), le plugin le lit. Le front (`simulation-progress.js`) sonde toutes les 250 ms et monte la barre dans la zone de dessin - rien à l'écran avant la première réponse « en cours » ; éteint (`pluginEnabled`), le constructeur simule comme avant, sans barre. Ne stocke rien | accounts, structures | — |
| 30 | `step_report` | Les commentaires d'étape et le rapport pas à pas du constructeur de structures. Un commentaire (texte libre, 4000 caractères) se range sous l'id de l'étape et le µprojet qui la porte (`GET /api/microprojects/{slug}/step-comments`, `?step_id=` répétable ; `PUT .../{step_id}`, texte vide : retiré ; lire demande le rôle `viewer`, écrire `editor`) - l'id d'étape est stable d'une version de l'étude à la suivante, le commentaire la suit donc ; il n'entre dans aucune version ni dans leur comparaison. Dans une structure de la bibliothèque (qui ne garde pas les ids d'étape), le commentaire vit sur l'étape côté page et s'enregistre avec la structure (`step_comments`, par rang d'étape, un champ de `process_library` comme `declared_params` : vides écartés, 4000 caractères au plus) ; une expérience partie d'une telle structure en reprend les commentaires sous les ids de ses étapes. Pas de commentaire dans une brique ni un préset. Le front (`step-report.js`) ajoute le champ « Commentaire » à l'inspecteur d'étape, un point doré aux puces commentées, et le bouton « rapport » de la barre d'édition, qui télécharge un diaporama HTML d'un seul fichier (`report-core.js` lit les paramètres de chaque étape sur l'étape elle-même et compose les données ; `report-html.js`, pur : le dessin de chaque étape, ses paramètres - ceux du formulaire et les paramètres déclarés, marqués -, son commentaire, la légende des matériaux, un stepper ; s'imprime une diapositive par page), fabriqué côté page de ce que le constructeur a à l'écran. La fiche d'une étude a le même rapport (bouton « Rapport pas à pas » au-dessus de la structure, `study-report.js`) : le procédé de la version affichée, simulé pour avoir le dessin de chaque étape, avec les commentaires de ses étapes ; rien pour une structure en images ni une expérience sans structure. Le constructeur n'appelle le plugin que par `syncStepReport()` ; éteint, plus de champ ni de bouton | accounts, microprojects, structures | `step_comments` (microprojet, id d'étape, texte, auteur, date) |
| 31 | `materials` | Éditer les matériaux de l'instance depuis une page (`/materiaux`, entrée « Matériaux » du menu Structure) : le document de `materiaux.yml` - la liste du sélecteur du constructeur (nom, catégorie, couleur, description, densité, indice) et les **dégradés de couleur** de l'InGaN et de l'AlGaN selon le taux (points `{x, color}`, mélange linéaire, `generic_x` : le taux du nom nu « InGaN ») - `GET /api/material-library` (tout compte, avec `can_edit`), `PUT /api/material-library` (administrateur : validé, réécrit par `library.service.save` qui le fait relire par l'interprète de `structures.library_files`, l'en-tête de commentaires du fichier gardé). Le document porte la `revision` du fichier lu : un enregistrement qui en cite une autre est refusé (409 `library_file_changed`) plutôt que d'écraser une édition faite entre-temps. Le sens du fichier reste à `structures` (`library_files.Gradient`, `gradient(famille)`), dont `simulation` tire la couleur d'un `In0.20Ga0.80N` ; rien n'est stocké ici | accounts, library, structures | — |
| 32 | `kpi_tracking` | Les KPI qu'un **projet corporate** suit et leurs boîtes à moustaches. Le choix (`service.add_tracked`, `/api/areas/{area_slug}/kpi-tracking/kpis`) : une colonne de KPI d'un type de données PRISM par plaque (`hook` + `column`), prise au `catalog()` - les `kpi_columns` des fiches des types implémentés dont le seul paramètre est `wafer_names`, « A / B » en deux KPI, sans identifiant ni position (`wafername`, `X`, `Y`) ; 422 `unknown_kpi` hors catalogue, 409 `kpi_already_tracked`, 30 au plus ; tous les µprojets du projet le partagent. **Filtres** (`filters`, `clean_filters`) : une liste de `{column, op, value}` par KPI suivi, cumulés ET - `gt/gte/lt/lte` (nombre), `eq/ne` (nombre, booléen ou texte sans casse, selon la cellule), `contains`, `in` (liste) ; une cellule non comparable (vide, courbe) écarte la ligne, jamais devinée ; la même colonne se suit plusieurs fois avec des filtres différents (409 `kpi_already_tracked` pour les mêmes), `PATCH .../kpis/{id}` `{label?, filters?}`. **Dates** : si le type de données a une colonne de date (« PL date », « Test_Date » : la première dont le nom dit « date »), une plaque mesurée à plusieurs jours a une boîte par jour (`group.date`). **Valeurs à choisir** : `GET .../values?hook=&column=` (gérer le projet) lit la colonne sur les plaques du projet (la requête PRISM par plaque, en cache) et rend ses valeurs distinctes (`kind` text/bool/number/empty, `{value, count}` les plus fréquentes d'abord, 200 au plus, étendue d'une colonne numérique) : le formulaire de filtre propose alors une liste (une valeur pour `=`/`≠`, plusieurs pour « dans la liste »), la saisie libre restant pour `contient` et `>`... **Axe du temps** : chaque boîte porte `sort_date` (son jour de mesure, `dated`, sinon le jour où la plus ancienne étude a commencé à suivre la plaque) et les boîtes sont rendues dans l'ordre chronologique ; `time-window.js` (inspiré du sélecteur de période de quick_report) pose au-dessus du dessin une fenêtre à poignées sur l'histogramme des boîtes, ouverte par défaut sur le dernier mois des données (toute l'étendue s'il n'y a rien), « Tout » pour l'historique entier, partagée par les onglets du projet ; le dessin défile à l'horizontale plutôt que de rétrécir. Les filtres sur une autre fiche que celle du KPI (EQE filtré par la longueur d'onde dominante du PL) ne sont pas possibles. Le calcul (`service.distributions`, `GET .../distributions`) est à la demande, jamais stocké : les plaques sont celles des `physical_tracking` de la pointe de chaque piste de **tous les µprojets du projet** (une plaque suivie par deux études n'y est qu'une fois, avec ses µprojets et ses études), chaque type de données est interrogé une fois pour toutes (par paquets du plafond de `characterization`, via `characterization.service.query`, donc le cache par plaque de PRISM), et par KPI et plaque on garde quartiles, moustaches à 1,5 × IQR et valeurs aberrantes sur les lignes (dispositifs) de la plaque. Un type en échec n'ôte rien aux autres KPI : `status` `error` + message sur les siens. Lecture ouverte à tout compte connecté (comme `kpis`) mais le titre d'une étude n'est donné qu'à qui lit son µprojet (`null` sinon) ; choisir ses KPI et `?refresh=true` (ignorer le cache PRISM) demandent de gérer le projet (`areas.require_manage`). Le front : l'entrée « KPI » du menu Data (`/kpi`, un sélecteur de projet gardé dans `?projet=`, `kpi-config.js`) règle le choix ; sur la page d'un projet, `distribution-tab.js` ajoute au bloc « Évolution des KPI » (`kpis/static/kpi-trend.js`, KPI à `render`) un onglet par KPI suivi - boîte par plaque colorée par µprojet (`boxplot.js`, pur) - à la place des aperçus « à venir » de `kpis` ; un clic sur une boîte ouvre le récapitulatif de la plaque (`wafer-modal.js` : run, lot, FDL, µprojets, structure vue, contexte/intention/conclusion via `PlateContext`, études qui la suivent, lien vers `/plaques/{lasermark}`) ; sans KPI suivi, un onglet renvoie à `/kpi` | accounts, areas, microprojects, experiments, wafers, characterization | `area_tracked_kpis` (projet, hook, colonne, filtres JSON, nom affiché, rang ; unique sur projet + hook + colonne + filtres) |
| 33 | `docs` | Pages de documentation (contenu inchangé) | — | — |

### Activer et désactiver un plugin

Un administrateur active ou désactive un plugin depuis **Paramètres > Plugins** (`/parametres/plugins`,
plugin `settings`), **à chaud** : rien à redémarrer. La règle est au noyau (`kernel.plugin_states`) :

- **Noyau** : les plugins `required` - `accounts`, `settings`, `microprojects`, `experiments`,
  `comparator`, `wafers`, `process_library` - et tout plugin dont l'un d'eux dépend (`teams`, `search`, `library`,
  `areas`, `attachments`, `structures`) ne se désactivent pas (409 `plugin_required`). `wafers` et
  `process_library` en sont parce que le constructeur et la fiche d'étude s'en servent partout
  (champ FDL, liens de plaque, structures enregistrées, présets) ; `comparator`, parce que toute
  comparaison de structures passe par lui (évolution d'un µprojet, d'une référence, fiche, plaque).
- **Actif** = disponible (`Plugin.enabled()`, lu au démarrage : un plugin indisponible n'a pas de
  routes ; 409 `plugin_unavailable` pour l'activer), activé (le choix enregistré, actif par défaut)
  et tous ses prérequis actifs. Désactiver un plugin **éteint ceux qui en dépendent** sans toucher à
  leur choix (`blocked_by` : ce qui les éteint) ; le réactiver les rallume. La page demande
  confirmation en nommant les modules qui s'éteindront avec lui.
- **Éteint**, un plugin reste installé (migrations appliquées, tables et fichiers gardés, statiques
  servis) mais : ses routes `/api` et ses redirections répondent 404 `plugin_disabled` (une
  dépendance posée par `create_app` sur son routeur - avant l'authentification : une route éteinte
  n'existe plus, pour personne), ses pages un 404 « Module désactivé », ses entrées quittent la
  barre du haut, ses `<script>` / `<link>` sont retirés des pages des autres plugins (ses panneaux
  ne se montent plus), et la recherche n'interroge plus ses fournisseurs (`SearchProvider.plugin`).
- **Le front d'un plugin du noyau** qui se sert d'un plugin optionnel le vérifie avec
  `pluginEnabled(name)` (`kernel/static/ui.js`) avant d'en appeler les globaux, et cache ce qui le
  concerne : bloc KPI d'un projet (`kpis`), lien Atlas (`atlas`), départ depuis une référence et
  versions publiées (`references`), « Promouvoir comme référence » (`promotion`), badges et affectation de lots
  (`lots`), « Données en base » (`characterization`), onglet Données et citations de la conclusion
  (`notebook`), formulaire d'intention du constructeur (`intent_forms`), barre de chargement de sa simulation (`simulation_progress`), plaques jumelles du comparateur (`twins`). Côté serveur, sans
  `intent_forms` le formulaire d'un µprojet n'est pas exigé (`experiments.repository.writing`) : ses
  questions ne peuvent plus être posées.

**Les tables d'un autre plugin.** Un plugin possède ses tables : il est seul à y écrire. Il peut
en revanche les **lire par jointure SQL** chez les plugins dont il dépend, pour une liste qui en
affiche un champ (`lots` lit `thematics`, `links` joint `microprojects`, `microprojects` lit
`management_areas`, `references` lit les ids de `microprojects` pour savoir lesquels n'ont pas
encore été lus, les auteurs sont joints sur `users`). Une seule exception va contre le DAG :
`areas`, placé avant `microprojects` (qui dépend de lui), touche la table `microprojects` -
l'objectif validé par un µprojet (`area_objectives.validated_by_microproject_id`, lu par jointure
avec son code recopié de `microprojects.service.format_code`), et le repli des µprojets quand on
supprime un projet (vers « Non classé », sans thématique) ou une thématique (`thematic_id` remis à
`NULL`). La faire passer par `microprojects` demanderait une dépendance dans l'autre sens.

### Une seule règle d'autorisation

Trois niveaux de droits, et une seule fonction qui les combine par ressource :

- **admin** (`users.is_admin`) : tout. Il est `owner` de tout µprojet, même sans en être membre, et voit
  toutes les thématiques ;
- **manager d'une équipe** (`team_members.role = manager`) : gère les projets corporate où son
  équipe travaille (`area_teams`) et leurs objectifs, les thématiques de son équipe, peut créer un
  projet dans l'une de ses équipes, et il est `owner` des µprojets de son équipe
  (`microprojects.team_id`) ;
- **membre** : le rôle de son adhésion au µprojet (`viewer` < `editor` < `owner`).

Un compte peut appartenir à plusieurs équipes et n'être manager que dans certaines.

**Plusieurs équipes travaillent dans un même projet corporate** (`area_teams`, rattachées par un
admin ou par le manager de l'équipe, retirées de même - 409 `team_has_content` tant qu'elles y possèdent
quelque chose). Chaque **thématique** appartient à une équipe (`thematics.team_id`) et chaque **µprojet**
aussi (`microprojects.team_id`) : celle de sa thématique, sinon l'une des équipes du projet
(`microprojects.service.resolve_team`, 422 `team_required` quand plusieurs conviennent, `team_mismatch`
si l'équipe demandée n'est pas celle de la thématique). Sans équipe (`NULL` : les données d'avant, « Non
classé », une équipe supprimée), une thématique est **ouverte** : tout le monde la voit, et le
manager du projet l'écrit.

**Visibilité.** Le projet corporate (nom, objectifs) reste visible de tous. Une thématique ne l'est que de
son équipe, des équipes **invitées** dedans (`thematic_teams` : toute l'équipe, en lecture seule) et des
comptes membres d'un de ses µprojets (`areas.service.visible_thematic_ids`) ; pour les autres elle n'existe
pas (404, absente des listes, 422 si on la nomme pour y placer un µprojet). Les µprojets d'une thématique
suivent : `microprojects.service.visible` (les recherches, `experiment-stats`, `experiment-timeline`) ne
nomme que ceux où l'on a un rôle et les µprojets ouverts (sans équipe, hors thématique cachée).

Côté projet, `areas.service.can_manage(user, area)` (admin, ou manager d'une équipe du projet) est
la règle d'écriture du projet et de ses objectifs ; pour une thématique, `can_manage_thematic` (admin,
ou manager de l'équipe qui la possède - une thématique ouverte retombe sur `can_manage`) : modifier,
supprimer, inviter une équipe (`POST /api/areas/{area}/thematics/{thematic}/teams`). Créer une
thématique : `thematic_owner` choisit l'équipe (celle qu'on manage dans le projet ; `team` si plusieurs).
**Placer un µprojet** dans un projet - le créer (`POST /api/microprojects`) ou l'y déplacer (`PATCH
/api/microprojects/{mp}` `{area, thematic, team}`, réservé par ailleurs à l'`owner`) - suit
`resolve_team` : dans une thématique d'équipe, ses membres et un admin ; hors thématique, un membre d'une
équipe du projet ; un projet sans équipe et « Non classé » restent ouverts à tous. Le refus est un 403
`placement_forbidden`. `areas.service.can_place_microproject` (projet) et `can_place_in_thematic` en sont
les formes que chaque ressource expose (`can_place_microproject`) : `areas` ne peut pas importer
`microprojects`. Un µprojet garde son équipe quand il change de projet ; il en prend une autre en entrant
dans la thématique d'une autre équipe. Les pages projet et thématique n'offrent « + Nouveau µprojet »
que si `can_place_microproject` est vrai, comme « Rattacher un µprojet existant » (page projet, admin
seulement).

Côté µprojet, `microprojects.service.access(user, microproject)` rend
un `Access(role, source, membership)` : `role` est le rôle effectif, `source` dit d'où il vient,
dans cet ordre de priorité : owner par adhésion (`membership`), puis `team_manager` (manager de l'équipe du
µprojet), puis `admin`, puis le rôle de l'adhésion, puis **la lecture que donne la thématique** - `viewer`
pour un membre de l'équipe du µprojet (`team`), d'une équipe invitée dans sa thématique (`thematic_team`) ou
d'un autre µprojet de la thématique (`thematic_guest` : ajouté à un µprojet, on voit la thématique et on
lit les autres, on n'écrit que dans le sien). `effective_role`, `has_role`, `check_role`, `accesses` (une
liste en quelques requêtes) et `deps.require_role` en dérivent ; aucun autre plugin ne lit la table
`memberships` pour autoriser (`role_for` reste un lecteur brut). « Mes µprojets » (`list_mine`) : ceux dont
on est membre et ceux de ses équipes ; `?scope=readable` : tous ceux où l'on a un rôle ; pas tous ceux qu'un
admin peut ouvrir. Hors µprojets, trois contrôles gardent leur propre règle, qui ne
dépend pas d'un rôle : la suppression d'un lot (créateur ou admin) et les éléments partagés de
`process_library` et d'`intent_forms` (auteur ou admin).

À la migration (`teams/0002_badge`, `areas/0004_teams_per_area`, `microprojects/0005_team`), l'équipe unique
d'un projet devient sa première équipe (`area_teams`), elle possède ses thématiques et ses µprojets ;
un projet sans équipe garde des thématiques ouvertes. Une base d'avant les équipes n'est rattachée
à rien : ses droits ne changent qu'une fois les équipes créées et rattachées aux projets.

Une **page** appartient au plugin de sa ressource principale. Son script peut utiliser les
`client.js` d'autres plugins : le navigateur est la racine de composition. Une agrégation qui
traverse plusieurs µprojets côté serveur vit dans le plugin le plus haut qui en possède les
données. Par exemple, la frise d'une thématique est servie par `experiments`, qui dépend déjà
de `microprojects` et de `areas`.

### Modules d'un plugin

```
spectre/plugins/<plugin>/
  __init__.py     # PLUGIN = Plugin(...)  — le manifeste, rien d'autre
  api.py          # APIRouter : HTTP uniquement
  <sujet>_api.py  # routeur annexe inclus par api.py, HTTP lui aussi (microprojects/invitations_api.py,
                  # experiments/insights_api.py) ; un autre plugin ne l'importe pas plus que api.py
  schemas.py      # modèles Pydantic des requêtes et réponses
  service.py      # domaine (ou store.py + models.py) — sans FastAPI
  migrations.py   # MIGRATIONS = (Migration("0001_initial", ...), ...)
  deps.py         # dépendances FastAPI offertes aux autres plugins (accounts, microprojects seulement)
  pages/          # HTML
  static/         # client.js, contrôleurs de page, widgets, <plugin>.css
```

### Points d'extension (abstractions justifiées)

| Extension | Où | Implémentations réelles |
|---|---|---|
| `StructureKind` (Protocol : `key`, `render_svg`, `entity_count` ; `KINDS` indexé par les clés figées). Le corps reçu est lu par l'union `structures.schemas.StructurePayload`, discriminée par `kind` | `structures/kinds.py` | process, campaign, images, declared (sans structure) |
| `DataSource` (Protocol : `list_types`, `describe`, `query`, `chart`), choisie à un seul endroit (`characterization.service.current_source()`, `SPECTRE_DEMO_DATA`) | `characterization/source.py` | PRISM (`prism_source.py`), démo (`demo.py`) |
| `register_provider(SearchProvider)` | `search` | microprojects, wafers (lasermark, FDL), lots |
| `register_source(ItemSource)` : le préfixe d'un jeton de ligne (`study`, `wafer`, `reference`), `resolve` (les lignes d'un jeton, vues par le lecteur), `search` (les suggestions d'une saisie), `plugin` (éteint : ses jetons ne se lisent plus) | `comparator` | études (comparator), plaques (wafers), versions de référence (references) |
| `register_library_file(LibraryFile)` : clé en kebab-case anglais (le nom du fichier YAML reste le nom historique), `parse` (mapping YAML → contenu, `ValueError` si invalide : sert à valider avant l'écriture et à charger) et `fallback` (contenu quand le fichier est absent ou invalide) | `library` | structures (matériaux, recettes), process_library (présets, briques), library (textes de la section intention, servis par `GET /api/ui-texts/intention`) |
| `register(KpiDefinition)` | `kpis` | activité, wafers, démo EQE |
| `DataViz.register(component)` | `notebook/static/dataviz/core.js` | table, carte de wafer, distribution, nuage de points, courbes… |
| `ExperiencePage.registerPanel({key, mount(el, ctx)})` (voir § 6) | `experiments/static/page.js` | les panneaux de la fiche elle-même, puis lots (`lot-picker.js`), notebook (`notebook.js`) |
| `ctx.setNotebook(summary)` / `ExperiencePage.onNotebook(fn)`, `ctx.filterNotebook(stepId)` / `ExperiencePage.onNotebookFilter(fn)` (voir § 6) | `experiments/static/page.js` | le cahier (notebook) déclare ses entrées et leur nombre par étape ; la vue du procédé (`structure-view.js`, badges) et la conclusion (`conclusion.js`, citations) s'en servent ; un badge filtre le cahier |

**Annotations d'une structure en images.** Chaque image de `StructureImage` porte un champ
facultatif `annotations` (la forme de `kernel.annotations`) : une image enregistrée avant se relit
sans, et une image sans annotation s'enregistre sans la clé (l'objet garde la forme d'avant). Le
détail d'une étude renvoie toujours `annotations` (une liste) sur chaque image de
`structure_images`. Des annotations ne changent pas la structure : `PUT .../structure-images` garde la
révision, et une évolution qui ne change que des annotations (mêmes images, mêmes types et
légendes) la garde aussi (`kinds.without_annotations`) ; le résumé du diff dit « Image n :
annotations modifiées ».

**Clés de type de structure figées.** `ProcessLot` et `StructureImage` surchargent
`registry_key()` pour renvoyer leur chaîne historique (`spectre.core.structures.…`). Follow
persiste cette clé dans `structure_type` et l'utilise dans le hachage de l'id, si bien qu'un
déplacement de classe ne doit jamais la changer. `DeclaredStructure` a la sienne, figée dès sa
création : `spectre.structures.DeclaredStructure`.

**Expérience sans structure (`DeclaredStructure`, kind `declared`).** Pas de structure complète :
une `description` libre, des `images` facultatives (la forme de `StructureImage`, 0 à 12) et le split
déclaré - `factors` (les colonnes : ce qu'on change) et `wafers` (`[{label, values}]`, une ligne par
plaque, au moins une, une valeur texte par colonne). Rien à simuler ni d'étapes (`steps = []`, pas
de `structureforge_process`, les mesures du cahier se rattachent à la plaque ou à l'étude). Comme une
campagne, une place de `physical_tracking` par ligne (`entity_count`), à sa position, et
`PUT …/physical-tracking` en exige exactement autant ; `campaign_labels` reçoit le nom de chaque ligne
(`label`, sinon ses valeurs, sinon « Plaque n » - `kinds.declared_wafer_label`) pour la liste des
plaques et le cahier. Les versions se distinguent par la révision des images
(`structure_image_revision`) : une évolution qui garde description, images (sans leurs annotations)
et tableau garde la révision et la conclusion ; sinon nouvelle révision (changement majeur). Le
détail porte `structure_kind` et `declared_structure` (`{description, images (avec url), factors,
wafers: [{label, values, name}]}`). Partie dans le constructeur, une telle étude garde ses plaques
nommées comme réplicats. Page : `structures/pages/declared-structure.html` (+ `declared-structure.js`).

## 4. Conventions REST

- **Langue** : anglais pour l'API, les plugins et le code ; les URL de pages vues par les
  utilisateurs restent en **français**.
- **Ressources** au pluriel, en kebab-case, sans verbe. Une action métier devient une
  sous-ressource : `PUT .../conclusion`, `PUT .../status`.
- **Méthodes** : `GET` lit, `POST` crée dans une collection, `PUT` remplace (ensemble ou
  singleton), `PATCH` modifie partiellement (`exclude_unset`), `DELETE` supprime.
- **Codes** :

  | Situation | Code |
  |---|---|
  | Création | `201` + `Location` + la ressource |
  | Lecture ou modification | `200` + la ressource |
  | Suppression | `204` sans corps |
  | Pas de session | `401` (réservé à ce cas) |
  | Droit insuffisant | `403` |
  | Introuvable | `404` |
  | Conflit d'état ou doublon | `409` |
  | `If-Match` périmé | `412` |
  | Fichier téléversé trop gros | `413` |
  | Saisie invalide (y compris des identifiants de connexion refusés) | `422` |

  Une modification sans effet renvoie `200` et ne crée pas de version.
- **Recherche et filtres** : par query params sur la collection (`?q=`, `?status=`, `?code=`).
  Aucun segment littéral ne partage le niveau d'un identifiant.
- **Identifiants** : un seul segment, opaque, sans `/`. Paramètres nommés `{<ressource>_id}`,
  `{<ressource>_slug}`, ou `{<ressource>_key}` pour une clé naturelle (`{wafer_key}`, `{kpi_key}`,
  `{data_type_key}`, `{chart_key}`, `{file_key}`) ; trois autres formes : `{token}` (le jeton d'une
  invitation, seul identifiant que connaît son destinataire), `{index}` (la position d'une image
  externe dans une entrée du cahier) et `{version_number}` (le numéro « 1.1 » d'une version de
  référence, sa clé dans la référence). Pas de convertisseur `:path` sous `/api` (une seule page en a un : la redirection
  héritée `/projets/{rest:path}`).
- **JSON** : clés en `snake_case` anglais. Collections paginées : `{"items": [...], "total": n}` ;
  les autres sont un tableau. Les ressources binaires exposent leur `url` : le front ne la
  construit pas.
- **Erreurs** : `{"detail": "<message en français>", "code": "<code>"}`. Les 422 de validation
  gardent le format FastAPI, que `api.js` met en forme.
- **Pas de HTML** servi sous `/api`.

### Identité d'une expérience

- `experiment_id` = la **piste** (le nom de branche Follow, slug d'un seul segment).
  `GET .../experiments/{experiment_id}` renvoie toujours la **dernière version** de la piste, avec
  l'en-tête `ETag: "<version_id>"`.
- `version_id` = une version immuable (`exp_<hex>`), lisible sous
  `.../experiments/{experiment_id}/versions/{version_id}`.
- Toute écriture sur une piste accepte `If-Match: "<version_id>"`. Si la piste a avancé, la
  réponse est `412` et rien n'est écrit. Le front envoie toujours ce qu'il a affiché. **Aucune
  fourche implicite** : bifurquer, c'est `POST .../experiments` avec `from_version`.
- Les écritures d'une piste sont sérialisées par µprojet (`kernel.locks`) et passent toutes par
  `experiments.service.amend()`. Cette fonction reporte **tout** le parent (titre, intention,
  hypothèse, métadonnées, réponses au formulaire, preuves, étiquettes, conclusion), puis applique
  le changement et ne commite que s'il y a une différence.
- Les liens vers une étude (atlas, entités, pages) désignent la piste et non une version. Une URL
  de page qui porte encore un ancien id de version est redirigée vers la page de sa piste (le
  `page_router` d'`experiments`).

**Mise en œuvre** (`experiments/repository.py`, `experiments/service.py`) :

- Lecture : `get_repository(slug)` sert un `follow.Repository` par µprojet depuis un cache, rechargé
  quand la signature du dépôt change (`refs.json` et `objects/`, comme l'index des plaques) ou après
  une écriture (compteur de génération). L'instance est partagée : on n'y écrit jamais.
- Écriture : `with writing(slug) as repo:` prend `keyed_lock("experiments", slug)`, recharge le
  dépôt **dans** le verrou et invalide le cache à la sortie. `amend()` y désactive la revalidation du
  formulaire d'intention (`repo.commit_form = None` : les réponses sont reportées, pas saisies) ;
  une évolution (`POST .../versions`) le revalide. Les erreurs de Follow deviennent des
  `kernel.errors` ; un formulaire refusé est un 422 `invalid_intent_form` dont le `detail` énumère
  les réponses en défaut.
- Le seul accès aux internes privés de Follow est dans `repository` : `delete_line(repo,
  experiment_id)` (suppression d'une piste ; Follow n'en offre pas le moyen). Le dépôt est ouvert sur le stockage JSON de Follow
  (même format sur disque), dont les écritures passent par `kernel.fs.write_text` : un `refs.json`
  tenu un instant par un lecteur, sous Windows, ne fait plus échouer un commit.
- Le plugin qui écrit dans une étude sans en être le propriétaire (notebook) expose ses
  sous-ressources sous `.../experiments/{exp}/` et passe par `amend()` : `If-Match` comme les autres
  (412 `stale_version`), et une écriture renvoie **la ressource écrite** (l'entrée du cahier), pas
  l'étude, avec en `ETag` la version créée - c'est ce que la fiche enverra en `If-Match` à
  l'écriture suivante. Ses lectures acceptent `?version=`, sur le modèle de `process?version=`,
  pour qu'une version passée ouverte en lecture seule montre ses propres données. Le détail d'une
  étude ne porte que `notebook_count` (toutes les entrées du cahier de la version, autres plaques
  comprises, anciens jeux d'images compris).
- **Le cahier unique et les données d'avant.** Les entrées du cahier sont rangées sous
  `notebook_entries` (`experiments.service.NOTEBOOK_KEY`). Avant le cahier unique, les données d'une
  étude étaient les vues de l'ancien cahier (`data_notebook`) et les preuves Follow
  (`Experiment.evidence`, plus `evidence_extra` - type, objectif, interprétation, graphique,
  `image_annotations` -, `evidence_links` et les images de `attachments` qui portent leur
  `evidence_id`). Elles ne sont **jamais réécrites** : `notebook.legacy` les convertit à la lecture
  (une vue → une entrée `prism` non située ; une preuve → une entrée `manual` **qui garde son id**,
  son `step_index` traduit par `step_id_at` sur la version qui l'a ajoutée, ses liens relus selon
  la règle d'aujourd'hui : espaces encodés, un lien qu'elle refuse passe dans le texte), et la
  première écriture dans le cahier enregistre le cahier converti dans la version qu'elle crée, sans les anciennes clés
  ni la liste `evidence` de Follow. Une écriture sans effet n'enregistre rien ; une autre écriture
  (étiquette, statut...) reporte l'ancien format tel quel.
- **Les jeux de l'ancienne galerie d'images externes** (`data_items`,
  `experiments.service.LEGACY_IMAGE_SETS_KEY` : `{id, title, note, entity_index, image_paths,
  pinned_index}`) suivent la même règle : `notebook.legacy` convertit chacun, à la lecture, en une
  entrée `manual` **qui garde son id** (la conclusion peut la citer), titrée du nom du jeu (« Images
  de mesure » sans nom), sa note conservée, d'une seule mesure non située qui porte ses images
  externes, l'image épinglée en premier ; un jeu rattaché à une variante d'une campagne vaut pour la
  plaque de cette variante dans la version lue (`wafers`), et sans plaque à cette variante, pour
  toute la piste, la variante rappelée dans le texte. Ses images ne sont pas revérifiées à la
  conversion : leur `status` dit ce qui ne se montre plus. La première écriture dans le cahier
  l'enregistre au nouveau format et retire `data_items` de la version qu'elle crée.
- **Les preuves Follow natives.** Spectre n'en écrit plus : le cahier est la seule source. La
  conclusion de Follow garde son champ `ObjectiveResult.evidence_ids`, qui cite désormais des ids
  d'entrées du cahier (Follow ne les vérifie pas ; `PUT .../conclusion` les vérifie, 422
  `notebook_entry_not_found`) - comme une preuve convertie garde son id, une conclusion d'avant cite
  toujours la bonne entrée. Retirer une entrée la retire des verdicts qui la citaient.
- Toutes les lectures des autres plugins désignent la piste : l'index des plaques (wafers, donc la
  recherche et les lots) donne `experiment.id` = la piste ; l'atlas nomme chaque étude par
  `experiment_id` (et `version_id`, sa pointe) ; un lien d'entité désigne
  `{microproject, experiment_id, entity_index}`.
- notebook dépend d'experiments, pas l'inverse : experiments ne connaît que les ids des entrées du
  cahier (`notebook_entry_ids`), pour les compter et les citer. Une écriture traverse encore une
  frontière de plugin sans import, faute de dépendance dans ce sens : supprimer une piste ne purge
  pas ses liens d'entités (experiments ne dépend pas de links) - ils restent listés et supprimables,
  l'atlas ne les dessine plus, et le nom de la piste n'est **jamais redonné**
  (`follow/retired_lines.json`, `repository.retire_line`) : un lien désigne la piste par son nom, il
  passerait sinon à une étude sans rapport. Supprimer un µprojet, lui, purge ses liens (`ON DELETE
  CASCADE`).
- Le nom d'une piste : tiré du titre (`epitaxie-a-20-nm`, accents retirés, suffixe `-2`... si pris),
  ou `branch` à la création - un seul segment sans `/`, ni `.`/`..`, ni la forme d'un id de version,
  libre parmi les pistes, les refs **et** les pistes supprimées (sinon 409 `branch_name_taken`).
- Une piste créée depuis une version (`from_version`, `version_id` facultatif : la pointe par
  défaut) en reprend, faute de mieux dans la requête, les objectifs et le contexte - pas ses plaques
  (la requête nomme les siennes, les mêmes, de nouvelles, ou aucune encore - décision du 2026-10-07),
  ni ses FDL, le cahier de données, les étiquettes ni la conclusion : c'est une nouvelle étude.
- **Plaques à associer, FDL de l'étude** (décision du 2026-10-07) : nommer les plaques est optionnel
  au lancement, à l'évolution et à la combinaison - une place (une par variante d'une campagne, une
  par plaque prévue d'une étude simple, au moins une) reste `{sample_id: null}` jusqu'à ce qu'on
  l'associe à une vraie plaque ; une étude ne se **conclut** qu'avec au moins une place associée
  (422 `entity_required`). Partir de plaques (`wafer_origin`) les nomme toujours. L'étude porte ses
  FDL (`metadata["fdl"]`, normalisées, `fdl` au lancement, à l'évolution - `null` les garde - et
  dans `PUT .../entities`, renvoyées dans `fdl` du détail) ; les plaques qu'elles contiennent se
  lisent dans le plugin wafers (`GET /api/fdls/{fdl}`, § wafers) et chaque place s'y associe à la
  main, par un menu déroulant (constructeur, écran 3 ; carte « Plaques » de la fiche).
- **Les expériences prévisionnelles** (`experiments.plans`, table `experiment_plans`, migration
  `experiments/0001_plans`) : prévues depuis l'arbre du µprojet, avant d'en savoir la structure, le
  split ou les vraies plaques - un titre, une intention, la version dont elles partent (aucune pour
  une racine ; la version choisie reste même si la piste avance) et ce qu'elles continuent :
  **les mêmes plaques** (`same_wafers`, des lasermarks suivis par cette version, d'une seule variante
  pour une campagne - la règle de `resolve_wafer_origin`, vérifiée dès la prévision) ou **de
  nouvelles plaques** (`new_wafers`, `wafer_count` estimé, 1 à 200). Ce n'est pas encore une étude :
  elles vivent dans la base, pas dans le dépôt Follow. `GET .../lineage` les rend (`plans`, chacune
  avec `parent_node`, le nœud qui montre sa version de départ - `lineage_graph(anchors=)`).
  Lancées (`POST .../experiments` avec `plan_id`), elles sont supprimées : l'étude ne garde que ses
  plaques réelles (le prévisionnel est oublié). L'éditeur les lance par `?prevision=<id>` : mêmes
  plaques → départ de plaques existantes (`wafer_origin`) ; nouvelles plaques → nouvelle piste depuis
  la version (`from_version`, jamais une modification sur place) ; racine → structure vierge.
  « Continuer » depuis l'arbre passe toujours par là ; la modification sur place d'une étude reste
  « Éditer la fiche ».
  Une prévision peut partir d'une autre (`parent_plan_id`, migration `experiments/0003_chained_plans`,
  qui reconstruit la table sans le CHECK sur le mode) : mêmes plaques parmi celles que la mère nomme
  (aucune si elle n'en nomme pas - à cocher une fois lancée), ou nouvelles plaques. Elle ne se lance
  qu'après la mère ; `consume_plan` accroche les filles à l'étude lancée (`parent_version_id`).
  `delete_plan` ne supprime pas les filles : `parent_plan_id` remis à NULL, `detached_from` = le titre
  de la mère - détachées, elles se rattachent par `PATCH` avec `parent` ou `parent_plan_id`
  (`plan_cycle` refusé), plaques revérifiées ; une détachée sur les mêmes plaques les garde en attente.
- Dans le graphe, une étude partie d'une autre **sans changer la structure** (des tests sur les mêmes
  plaques...) est accrochée à celle dont elle part, et non au dernier changement de structure
  (`lineage_graph`, `hung_from`).
- **L'origine de référence** (`reference_origin`, `experiments.service.REFERENCE_ORIGIN_KEY`) : la
  version de référence dont part une étude, `{reference, version}` (un slug et un numéro « 1.1 »),
  donnée au lancement (`POST .../experiments`) et rangée dans les métadonnées. experiments ne connaît
  pas le plugin references (il en dépend, pas l'inverse) : il n'en vérifie que la forme
  (`schemas.ReferenceOrigin`, 422 sinon), et une origine qui désigne une référence ou une version
  inconnue s'enregistre et se lit telle quelle. `amend()` la reporte comme toute métadonnée (statut,
  étiquettes, évolution) ; une fourche garde celle de sa version de départ et une combinaison celle
  de sa première étude, sauf si la requête en donne une. Le détail d'une étude la rend
  (`reference_origin`, `null` sans origine).
- **Les plaques suivies** (`physical_tracking`, `experiments.entities`) : une par variante d'une
  campagne (une place chacune, vide tant qu'elle n'est pas nommée) ; autant qu'on veut pour une
  étude simple (procédé ou images) - ses **réplicats**, des plaques passées par la même structure
  (décision du 2026-10-05, l'ancienne règle « une plaque par étude simple » est levée). Jamais deux
  fois la même plaque dans une version (422 `duplicate_wafer`, lasermark comparé sans casse ni
  séparateurs) ; au lancement, les lignes vides d'une étude simple tombent et une plaque nommée au-delà
  de la dernière variante d'une campagne est refusée (422 `too_many_entities`) ; `PUT .../entities`
  garde la place d'une ligne vidée au milieu (les liens d'entité désignent une plaque par sa
  position) et retire les vides de fin. Une évolution en images garde les réplicats de la version
  précédente (la plaque de la première variante pour une campagne).
- **La plaque de référence d'une campagne** (`REFERENCE_PLACE_KEY`, décision du 2026-10-07) : la
  place (index de variante) dont la plaque répète la structure de référence, donnée au lancement
  (`reference_place`, 422 `reference_place_out_of_range` hors des variantes) ; `null` gardé tel quel :
  le split n'a pas de référence, et cite alors, au choix, la plaque d'une étude proche
  (`comparison_reference: {experiment_id, version_id?, sample_id?}`, `COMPARISON_KEY`, seulement
  citée, rien n'est vérifié). Une requête sans `reference_place` laisse la clé absente : la première
  variante, comme pour les campagnes d'avant ce choix (`service.reference_place_of`). Rien hors d'une
  campagne (une évolution vers une autre structure retire les deux clés ; une évolution d'une campagne
  qui n'en dit rien garde les siennes) ; une combinaison reprend celles de sa première étude. Le détail rend `reference_place` (`null` hors campagne) et
  `comparison_reference`, `GET .../variants` `reference_index` (le « RÉF » du carrousel). Le
  constructeur coche d'office la variante qui garde les valeurs de la structure de départ.
- **Partir de plaques existantes** (`POST .../experiments` avec `wafer_origin: {microproject,
  experiment_id, version_id?}`, `service.resolve_wafer_origin`) : l'étude qui suit les plaques (sa pointe
  par défaut), dans ce µprojet ou dans un autre dont l'appelant est membre (404 µprojet inconnu, 403
  sinon) ; les plaques sont les `entities`, chacune suivie par cette version (422
  `wafer_not_in_origin`), toutes de la même structure : une seule variante d'une campagne (422
  `wafers_different_structures`), les réplicats d'une étude simple. Dans le même µprojet, la
  nouvelle piste **descend** de cette version (`repo.derive`, comme une fourche, mais sans en
  reprendre objectifs, contexte ni plaques) ; d'un autre µprojet, elle naît sans parent (pas de
  filiation d'un dépôt à l'autre). Dans les deux cas l'origine est rangée dans les métadonnées
  (`WAFER_ORIGIN_KEY` : `{microproject, experiment_id, version_id, variant}`, `variant` l'index de la
  variante pour une campagne), reportée par `amend()`, pas par une fourche ni une combinaison, et
  rendue par le détail (`wafer_origin`, `null` sinon) ; la référence dont part l'étude d'origine
  (`reference_origin`) est reprise. Exclusif de `from_version` et de `merge_of` (422). La structure
  envoyée est libre (on continue le procédé) ; ses ids d'étape sont gardés (`_settled_step_ids`,
  avec ou sans parent). Le procédé d'une variante : `GET .../process?variant=` (`kinds.variant_process`,
  les valeurs de ses facteurs appliquées au procédé commun ; 422 `not_a_campaign`, `unknown_variant`,
  `no_variant_process` pour une campagne d'avant les plans).
- **Combiner deux études crée une nouvelle étude** (`POST .../experiments` avec `merge_of`,
  `service.combine`) : deux versions du µprojet (la pointe de chaque piste par défaut), de deux
  pistes différentes, et deux versions différentes (422 `same_experiment` : deux fois la même piste
  ou la même version), chacune une version **de sa piste** et non d'avant sa fourche (422
  `version_before_line` : l'histoire d'une piste partie d'une version contient celles d'avant), et du
  même type de structure (422 `different_structure_kinds`), deviennent les deux parents d'une **nouvelle piste** C, construite
  par `follow.Repository.merge(a, b, branch=<C>)` : Follow sait faire un commit à deux parents sur
  une nouvelle branche (références `baseline` vers A, `merge_source` vers B). Sa structure est la
  structure combinée selon la règle de Follow sans résolution de conflit, celle d'avant : celle de A
  (structure, protocole, et les métadonnées qui la décrivent : procédé, ids d'étape, campagne,
  révision d'une structure en images). C a ses titre, intention et hypothèse (titre et intention
  obligatoires comme pour un lancement), sa plaque et ses FDL (optionnelles) ; objectifs et contexte viennent de A faute de mieux dans la requête ; son
  cahier démarre vide, sans étiquettes ni conclusion. A et B ne bougent pas : aucune version ne s'y
  ajoute. Son numéro de version suit la règle d'une nouvelle piste (l'histoire de son premier
  parent, A : celui de A tant que la structure ne change pas). Les fusions d'avant (une version de A
  à deux parents) restent lisibles telles quelles. Les pages disent « combinaison » des deux : le
  losange du graphe de filiation et de l'évolution des structures, « issue de vX (piste n) et vY
  (piste m) » sur l'évolution, « Combinaison de » pour les deux liens de la fiche.
- **Une seule sorte de ref** (2026-10-11) : les références de structure (plugin `references`),
  déclarées à la main. Les refs locales d'un µprojet (des étiquettes Follow : `refs.py`, la
  « ref v1.0.0 » posée au premier lancement, les routes `…/refs`) sont retirées ; les étiquettes
  déjà dans les dépôts y restent, invisibles, réservent leur nom de piste (`_new_branch_name`) et
  ont été regroupées en références une fois, à la mise à jour, quand leur nom était partagé
  (`references/local_refs.py`, migration `0005_local_refs_imported_once`).
- **Numéro de version `X.Y`** (`versioning.py`, 2026-10-11 : il n'y a plus de Z) : majeur (X) -
  le substrat, ou une étape (une couche ajoutée, retirée, déplacée ou remplacée : la suite des
  types d'étapes, et, entre deux versions qui partagent un id d'étape, `process_step_ids`, un id
  qui change de place ou qui va et vient - `versioning.step_ids_in`) ; mineur (Y)
  - un réglage d'étape, un paramètre déclaré (ajouté, retiré, sa valeur, son obtention, son unité
  remplacée) ou, pour une campagne, son plan (`campaign_plan` : un facteur, son étape, son
  paramètre, ses valeurs - pas son libellé ni son échelle) ; `patch` - une retouche (nom d'étape,
  unité écrite seule, étiquettes de couches et leur regroupement, une variante d'un split corrigée
  à la main ou remise au calcul - `campaign_variant_overrides`) : niveau gardé, pour l'historique et
  la conclusion, mais pas de nouveau numéro.
- `scripts/repair_hypotheses.py` (à blanc par défaut, `--apply` pour écrire) reporte sur la pointe de
  chaque piste qui l'a perdue la dernière hypothèse non vide de son historique (bug B1).

### Identité d'une étape

Chaque étape d'un procédé a un id stable, `st_<8 hex>` (`structures.simulation.STEP_ID_RE`),
conservé aux évolutions : c'est par lui qu'un facteur de campagne et une mesure du cahier
désignent une étape, et non plus par sa position.

- **Stockage** : à part du procédé, sous la clé de métadonnées `process_step_ids` (dans l'ordre des
  étapes). Le versionnage et StructureForge ne la voient pas ; `service.editable_process` ajoute
  l'`id` à chaque étape de `GET .../process`.
- **Anciennes versions** : leurs objets Follow ne sont jamais réécrits, donc **pas de migration**.
  Leurs ids se lisent (`experiments.service.step_ids_of`) avec la règle d'une écriture sans ids :
  ceux du premier parent tant que la suite des types d'étapes est la même, sinon (ou pour une
  racine) dérivés de l'id de la version et de la position. Ils sont toujours les mêmes pour une
  version, et une même étape garde le même id d'une ancienne version à la suivante : un ancien
  `step_index` (`step_id_at`) donne un id que porte encore la dernière version, tant que les types
  d'étapes n'ont pas changé entre les deux. Toute version écrite ensuite enregistre les siens, y
  compris une écriture légère, qui reprend ceux du parent.
- **Attribution** (`simulation.settle_step_ids`, `service._settled_step_ids`) : une étape renvoyée
  avec son id le garde ; une étape sans id, ou dont l'id est mal formé ou en double, en reçoit un
  neuf ; un client qui n'envoie aucun id garde ceux du parent, par position, tant que la suite des
  types d'étapes ne change pas. Il en va de même pour une campagne lancée depuis une version : sans
  ids, ses facteurs visent les étapes par les ids de la version de départ. Le serveur accepte tout id bien formé : le constructeur renvoie
  ceux que `POST /api/simulations` lui a donnés (`step_ids`).
- **Recevoir des ids ne crée pas de version** : une écriture qui n'ajouterait que les ids du parent
  est sans effet (200, rien n'est écrit).
- `experiments.service.step_id_at(version, index)` traduit une ancienne position (`step_index`) en
  id ; `-1` désigne le substrat dans un ancien plan de campagne. Une campagne existante garde son
  `campaign_plan` en `step_index`, toujours lisible.
- Les bibliothèques (structures enregistrées, briques, présets) n'ont pas d'ids : leurs étapes sont
  des modèles, recopiées comme nouvelles étapes (`ProcessStep` ignore le champ `id`).

### Étiquettes de couches

Une étape choisie (par défaut aucune) peut porter une **étiquette** dessinée à droite de la
structure et reliée par un trait à la couche qu'elle a créée : un texte (« p-GaN » ; vide, le nom
du matériau) et, dessous, des valeurs de l'étape - `thickness` (dans une unité lisible, la valeur saisie sans arrondi : `150 nm`,
`2.5 µm`, `1.234 µm`), `composition` (le taux d'In ou d'Al d'un nitrure à composition : `In 20 %`) et
`declared:<nom>` (un paramètre déclaré, avec son unité : son champ `unit`, ou pour un paramètre
enregistré avant ce champ, la clé `unit` de son obtention, toujours lue).
Modèle `structures.simulation.LayerLabel` (`{text, values}`, 40 caractères et 6 valeurs au plus ; une
valeur d'un autre type → 422 ; une valeur que l'étape n'a pas n'est pas écrite).

- **Requêtes** (simulation, aperçu de campagne, lancement, évolution, fourche, campagne, structures
  enregistrées, briques) : `layer_labels`, par **position** d'étape comme `declared_params` (une
  position hors du procédé, ou qui n'est pas un entier écrit en chiffres ASCII - `²`, `٣` - → 422
  `invalid_layer_label`).
- **Étude** : par **id d'étape**, sous la clé de métadonnées `process_layer_labels`, à part du
  procédé comme `process_step_ids` ; avec elles, `process_layer_steps` : l'id de l'étape qui a créé
  chaque couche de la structure enregistrée (`null` : le substrat), une liste par entité (une par
  variante d'une campagne). Une version sans étiquette n'enregistre ni l'une ni l'autre (elle garde
  la forme d'avant ; les anciennes versions n'en ont pas, sans migration). `GET .../process` les
  rend par position (`layer_labels`, `{}` sans étiquette). Une écriture légère les reporte ; une
  évolution remplace celles du parent (aucune : il n'y en a plus) ; une combinaison prend celles de
  sa première étude ; une structure en images les retire (`kinds.DRAWN_STRUCTURE_METADATA_KEYS`).
- **Versionnage** : `versioning.structure_signature` les ajoute au procédé comparé, avec leur
  regroupement par brique (`label_groups`, ci-dessous) ; ne changer qu'elles est une version de
  niveau **retouche** (`patch`, sans nouveau numéro), comme renommer une étape, et garde la conclusion (elles ne
  changent pas la structure).
- **Regroupées par brique** : quand au moins deux étapes étiquetées (`MIN_GROUPED_LABELS`)
  appartiennent à une même brique (ci-dessous), le dessin n'a qu'une étiquette pour elles : le nom
  de la brique en titre, puis une ligne par étape (« p-GaN : 120 nm · dopage Mg 3e18 cm⁻³ »), de la
  couche la plus haute à la plus basse, et une accolade (`.sp-layer-bracket`, à droite du dessin)
  sur toute la hauteur des couches que ces étapes ont créées - pas celles des autres étapes de la
  brique. Une étape étiquetée hors brique, ou seule étiquetée de sa brique, garde son étiquette.
  Des accolades dont les hauteurs se recouvrent (sur un nanofil, les coquilles enveloppent le
  cœur) ont chacune leur **colonne** (`rendering._bracket_columns` : la plus courte au plus près du
  dessin, celle qui en contient une autre à sa droite ; deux briques empilées, qui se touchent,
  partagent la leur) ; la colonne des étiquettes recule d'autant, et chaque trait fait son coude
  au-delà de la dernière colonne, qu'il croise à angle droit (`data-x` : le trait vertical d'une
  accolade).
- **Largeur** : estimée par excès, caractère par caractère (`rendering._CHAR_WIDTHS` : la plus
  large de DM Sans, Helvetica Neue et Arial, en 400 comme en 600, mesurée dans le navigateur), et
  la colonne des étiquettes est aussi large que la plus large : aucune ne sort du SVG (40 « W »
  mesurent 641,6 unités en DM Sans 600 ; l'ancienne estimation, 0,58 em par lettre et une colonne
  plafonnée à 320, en laissait 307 dehors). Hors de l'ASCII, une lettre accentuée compte comme sa
  lettre de base, tout autre caractère 1,2 em (« Œ » mesure 1,114 em, « 中 » 1 em) et un émoji ou
  un pictogramme 1,6 em (« 🔬 » : 1,373 em) - l'ancienne règle (0,7 ou 0,8 em) en laissait
  sortir 180 unités. Un titre est coupé à 40 caractères, une ligne à 48 (64 pour la ligne d'une
  étape dans l'étiquette d'une brique).
- **Retouches dites à part** (`kinds.describe_label_changes` et `kinds.describe_step_changes`, ce que le
  comparateur écrit des retouches d'une version, `comparator.table`) : `label_changes`, par étape
  (`step_id`, `change` : `added`, `removed` ou
  `modified` avec `text {before, after}`, `values_added`, `values_removed` - les noms lisibles :
  « épaisseur », « composition », le nom du paramètre), puis par brique (`group_id`, `change` :
  `grouped`, `ungrouped`, `renamed`, `regrouped`), chacun avec `subject` et `line`, la phrase
  (« p-GaN — ajout : dopage Mg »). Les étapes s'apparient par id (`service.step_ids_of`) quand les
  deux versions en ont en commun (une piste, une fourche), sinon **par position** (deux études
  lancées à part, ou reprises d'un modèle, que le constructeur copie sans ids) ; une brique est son
  nom et ses étapes étiquetées, comme pour le versionnage, jamais son `group_id` (dissocier puis
  regrouper les mêmes étapes ne change rien). Et `step_changes` : les étapes renommées (appariées
  de même ; un nom d'étape n'est ni dans la géométrie ni dans les étiquettes, et c'est une
  retouche), `{step_id, subject, change: "renamed", name: {before, after}, line}` (« étape
  « n-GaN » renommée « n-GaN dopé » ») - une étape ajoutée ou retirée, elle, change la structure.
  Les paramètres déclarés, eux, sont des colonnes du comparateur. L'ancien diff géométrique
  page ne l'appelait depuis le comparateur.

### Briques d'un procédé

Une brique technologique insérée dans le constructeur (ou formée d'étapes choisies, « Grouper en
brique ») reste un **groupe d'étapes consécutives** de la structure : son identifiant de groupe
(celui du constructeur, gardé d'une version à l'autre), son nom et la brique de bibliothèque d'où
elle vient (`source`, son id). Modèle `structures.simulation.ProcessBrick` (`{group_id, name,
source, step_indexes}`, champs en plus refusés ; un nom de 120 caractères au plus,
`BRICK_NAME_MAX_LENGTH`).

- **Requêtes** (simulation, aperçu de campagne, lancement, évolution, fourche, campagne,
  structures enregistrées, briques) : `bricks`, par **positions** d'étape comme les étiquettes ;
  des étapes du procédé, consécutives et dans l'ordre, aucune dans deux briques, un groupe une
  seule fois (sinon 422 `invalid_brick`).
- **Étude** : par **ids d'étape**, sous la clé de métadonnées `process_bricks`
  (`[{group_id, name, source, step_ids}]`), à part du procédé ; une version sans brique ne
  l'enregistre pas (la forme d'avant). `GET .../process` les rend par positions (`bricks`, `[]`
  sans brique), et le constructeur les rattache aux étapes au chargement (évolution, fourche,
  modèle, structure ou brique de bibliothèque). Une écriture légère les reporte ; une évolution
  remplace celles du parent ; une combinaison prend celles de sa première étude ; une structure
  en images les retire (`kinds.DRAWN_STRUCTURE_METADATA_KEYS`).
- **Versionnage** : seules, elles ne changent pas la version (`none`) ; elles ne comptent que par
  les étiquettes qu'elles regroupent (`label_groups` : le nom de la brique et ses étapes
  étiquetées) - au plus une retouche.
- **Bibliothèques** : une structure enregistrée et une brique les gardent par positions
  (`bricks`) ; une brique insérée dans un procédé y devient un seul groupe (les briques ne
  s'imbriquent pas), de `source` l'id de la brique insérée. Le nom d'une brique de bibliothèque,
  que reprend ce groupe, a la même limite (`POST`, `PATCH /api/tech-bricks`, 422 au-delà ; les
  champs du constructeur ont `maxlength`) ; celui d'une brique enregistrée avant la limite est
  coupé à l'envoi (`bricksPayload`), et le mode brique demande de le raccourcir pour l'enregistrer.

### Briques de départ et copie tracée

Les macro-étapes d'avant (un rôle gabarit SAG / épitaxie / procédé sur une brique, un assemblage à
trois emplacements, une page par µprojet) ont été retirées le 2026-10-15 : elles faisaient doublon
avec les briques. Une structure se compose de briques quelconques, dans l'ordre qu'on veut ; ce
qu'un gabarit SAG apportait tient à une seule chose, qui reste :

- **Brique de départ** : toute brique peut garder un `substrate` (avec son réseau de fils,
  ci-dessous) - case « Brique de départ » du mode brique, « Garder le substrat » de « Grouper en
  brique » quand la sélection part de la première étape. Posée dans une **structure vide**, elle
  apporte son substrat ; ailleurs, seules ses étapes s'appliquent, par-dessus ce qui existe. Une
  brique sans substrat ne l'écrit pas dans sa forme. `briques.yml` accepte `substrate` et
  `lattice_openings`. Un gabarit SAG d'avant est devenu une brique de départ (migration
  `0004_drop_macro_step_roles` : `role` et `preview_on` retirés des briques, `role` retiré des briques
  internes d'une brique et d'une structure enregistrée) ; les `process_bricks` d'une version d'étude
  qui portent encore un `role` sont lus en l'ignorant (`ProcessBrick`), jamais réécrits.
- **Où sert une brique** : `GET /api/tech-brick-usages?microproject=` (`process_library/usages.py`)
  rend, par id de brique visible, les études dont la version courante (la pointe de chaque piste) a
  une copie de la brique (`process_bricks`, `source`), avec la version copiée ; tous les µprojets
  sont lus (une brique partagée sert partout), mais d'une étude d'un µprojet dont on n'est pas
  membre, seul le nom du µprojet (comme les usages d'une référence). D'où la dépendance de
  `process_library` à `experiments`, listé avant lui.
- **Copie tracée** (`brick-origin.js`) : une brique de bibliothèque a une `version`, qui monte quand
  son contenu change (`tech_bricks.BRICK_CONTENT_FIELDS` : étapes, paramètres, étiquettes, recettes,
  ancrages, substrat ; pas son nom ni ses notes - `revised_brick`). Sa copie dans une structure
  garde la version d'alors (`ProcessBrick.version`, dans `process_bricks` d'une étude ; absente, la
  forme d'avant) : une trace, jamais un lien. L'inspecteur d'une brique dit si elle est conforme,
  modifiée depuis, si la brique a changé (vN) ou si elle a disparu. Il propose « Réappliquer la
  brique » (même groupe, même place ; une brique de départ en tête reprend son substrat, le nombre
  de fils vus gardé), « Mettre à jour la brique » (une nouvelle version, que la copie suit ; une
  brique de départ en tête reprend le substrat de la structure) et « Détacher ». Les ouvertures
  d'une lithographie ancrée et le nombre de fils vus ne comptent pas dans la comparaison ; le
  substrat d'une brique de départ compte quand elle est en tête.

### Versions X.Y des briques, briques de référence, structures-briques

Décidé le 2026-10-15 : « un système de versionnement des briques - pousser une brique comme brique
de référence et suivre son évolution - et une structure complète utilisable comme brique du
constructeur ».

- **Versions** (`tech_bricks.py`) : le contenu d'une brique (`BRICK_CONTENT_FIELDS`) est numéroté
  `MAJEUR.MINEUR` par la règle des études (`experiments.versioning.classify_process_change`,
  `brick_change_level`) : une étape ajoutée, retirée ou déplacée, ou le substrat changé, ouvre
  X+1.0 ; un paramètre (déclaré compris, les recettes propres, un ancrage au réseau) donne X.Y+1 ;
  un nom d'étape, une étiquette, une trace de préset est une **retouche** qui garde le numéro (le
  contenu gardé de la version courante suit). Chaque version est gardée avec la brique
  (`versions`, :class:`BrickVersion` : `number`, `created_at`, `created_by`, `note`, `level`,
  `content`) ; une brique d'avant les numéros (compteur entier `N`) se lit `N.0`, sa version
  courante devenant sa première version gardée - de même pour la copie d'une étude
  (`ProcessBrick.version`, `"1.2"` ; un entier d'avant se lit `N.0`). `GET /api/tech-bricks/{id}`
  rend chaque version avec son contenu et, en mots, **ce qui change** depuis la précédente
  (`changes`, `brick_changes` : substrat, étape ajoutée / retirée / remplacée / renommée, champ
  modifié « « n-GaN » : thickness 200 nm → 300 nm », paramètres déclarés, recettes, ancrages,
  étiquettes) ; la liste rend les versions sans leur contenu. `PATCH` accepte `note` : le pourquoi
  de la version que le changement fait. `revised_brick` est le `revise` de la collection, qui
  reçoit désormais `user_id` et `note` (`service.update_item`).
- **Brique de référence** (`TechBrick.reference`, :class:`BrickReference` : `promoted_by`,
  `promoted_at`, `note`) : une brique partagée que tout le monde reprend. La promouvoir passe par le
  plugin promotion (`POST /api/promotions/bricks`, § promotion) : une brique de µprojet passe en
  partagée, **même id** (les copies qu'en ont les structures la retrouvent), son auteur devient qui
  la promeut (`service.set_brick_reference`). `DELETE /api/tech-bricks/{id}/reference` la retire des
  références (qui peut la modifier) : elle reste partagée, avec ses versions. Une brique de
  référence **ne change pas sans note** : un `PATCH` qui fait une version majeure ou mineure sans
  `note` est refusé (422 `brick_note_required`) ; une retouche passe. `GET /api/tech-bricks?reference=true`
  les liste.
- **Pages** : `/briques` (`bricks.js`, entrée « Briques de réf. » du menu Structure) liste les briques
  de référence (version courante, dernière mise à jour, qui l'a promue, usages) ; `/briques/{id}`
  (`brick.js`) est la fiche de toute brique : sa référence (qui, quand, pourquoi), ses **versions**
  de la plus récente à la première (numéro, niveau, date, auteur, note, ce qui change), son aperçu
  simulé (sur son substrat de brique de départ, sinon un substrat d'aperçu), **où elle sert** (les
  études et la version copiée, « M sur une version antérieure »), ses étapes ; « Ouvrir dans le
  constructeur » (mode brique, sous le µprojet de la brique ou le µprojet de travail mémorisé par
  le hub, `?retour=brique`), « Promouvoir comme brique de référence » (`PromotionLink.url({brick})`),
  « Retirer des références ». La page des briques d'un µprojet et le hub lient chaque brique à sa
  fiche (badge « Réf. »). **Constructeur** : le flow écrit « Réf. » (or sur navy inversé,
  `sb-brick__tag--ref`) sur une brique de référence ; l'inspecteur dit « Brique de référence
  « X » · v1.2 · fiche » ; « Mettre à jour la brique » demande la note d'une brique de référence
  (`window.prompt`) ; le mode brique montre la version courante et un champ « Pourquoi cette
  version ? », exigé d'une brique de référence.
- **Une structure complète comme brique** (`palette.js`) : sans rien créer, la liste des briques du
  constructeur propose aussi, sous leur nom, **chaque structure de la bibliothèque** (intégrée,
  partagée, du µprojet) et **la dernière version de chaque référence** (sections « Structures de la
  bibliothèque », « Références (dernière version) »). Insérée, elle copie ses étapes en un seul
  groupe (ses briques internes aplaties : les briques ne s'imbriquent pas), nommé comme elle, de
  source `structure:<id>` ou `reference:<slug>@<numéro>` (`ProcessBrick.source`) et, dans une
  structure vide, apporte son substrat (comme une brique de départ). Une version de référence n'est
  lue qu'au moment de l'insérer (`referencesApi.version`, gardée dans `state.referenceBricks` ;
  celles copiées dans une structure chargée sont lues en arrière-plan, `prefetchReferenceBricks`).
  Sa copie garde le numéro de la version copiée (`brick_version`) ; celle d'une structure, aucune
  version (la structure est un instantané écrasable : la copie se compare par son contenu). Le flow
  écrit « Réf. » sur une version de référence, « Struct. » sur une structure ; l'inspecteur dit
  « Version de référence « X 1.2 » · évolution » ou « Structure de la bibliothèque « X » », conforme,
  modifiée, « la source a changé depuis (1.3) » (une autre version de la référence depuis) ou
  introuvable ; « Réappliquer » reprend la dernière version. `GET /api/tech-brick-usages` rend aussi,
  par `structure:<id>` de structure visible, les études qui en ont une copie ; le hub l'écrit
  (« utilisée dans N études ») sur ses structures et ses briques.

### Réseau de fils

Le substrat peut porter un réseau de fils, `substrate.lattice = {pitch, wires}` (`simulation.Lattice` :
un pas en nm, de 1 à `MAX_LATTICE_WIRES` = 50 fils ; absent, la forme d'avant). Le domaine fait alors
`wires × pitch` de large, chaque fil au centre de sa maille. Une lithographie **ancrée au réseau**
porte, sur l'étape même, `lattice_opening` (`simulation.LatticeOpening`, une clé qu'un `ProcessStep`
ignore), d'un des modes de `LATTICE_OPENING_SIZES` :

- `{diameter}` (mode `wires`, écrit sans son mode) : un trou par fil, centré dans sa maille ;
- `{mode: "between", width}` : une ouverture entre deux fils voisins, une demi-ouverture à chaque
  bord du domaine (le réseau se répète) ;
- `{mode: "pixel", margin}` : une seule ouverture sur tout le pixel, moins la marge de chaque côté.

Une ouverture qui ne tient pas est refusée (422) : un diamètre ou une largeur qui atteint le pas, une
marge qui couvre le pixel. Une brique de départ qui porte un réseau ne dit plus des nm absolus : la
même épi se voit sur 1 fil, puis le procédé sur un pixel de N fils.

- **Résolution** : dès la lecture d'une requête (`schemas.ProcessInput`, `simulation.resolve_lattice`),
  la largeur du domaine et les ouvertures des lithographies ancrées sont recalculées. La suite
  (simulation, campagne, lancement, Follow) ne voit qu'un procédé ordinaire. Un procédé enregistré
  garde ses ouvertures résolues à côté de leur ancrage, et reste lisible tel quel. Sans réseau, une
  lithographie ancrée garde ses ouvertures.
- **Le nombre de fils est une vue** : `versioning.structure_signature` et `same_settings` comparent
  le procédé sans `wires`, sans la largeur du domaine et sans les ouvertures des lithographies
  ancrées (`simulation.view_neutral_process`). Passer d'un fil à six ne fait pas de version et garde
  la conclusion ; un autre pas est majeur, un autre diamètre mineur.
- **Campagnes** : sur une lithographie ancrée, `openings.pitch` fait varier le pas du réseau (le
  domaine suit), et `openings.diameter`, `openings.width` ou `openings.margin` la taille de son
  ancrage, celle de son mode (une autre est refusée, 422) (`campaigns.apply_combination`,
  `combination_anchors`). La variante d'une campagne lancée garde son ancrage. `domain_width` sur le
  substrat est refusé quand il a un réseau (422).
- **Bibliothèques** : une structure enregistrée et une brique rangent les ancrages par position
  d'étape (`lattice_openings`, comme `preset_origins`). Un procédé d'étude publié tel quel (ancrage
  sur l'étape) y est converti (`process_library.api._InlineLatticeAnchors`). Une combinaison au
  marché garde l'ancrage des étapes reprises.
- **Constructeur** (`substrate.js`) : une case « Réseau de fils » dans le substrat (pas, fils
  simulés ; la largeur est alors figée), un réglage « − N fils + » au-dessus du dessin. Dans la
  lithographie, le choix « Ouvertures : sur chaque fil / entre les fils / pixel entier / libres », et « Ancrer ces ouvertures sur un
  réseau de fils » pour des ouvertures régulières (le pas, le diamètre et le nombre en sont déduits).

### Unité des paramètres déclarés

Un paramètre déclaré (`simulation.DeclaredParam`) a un champ `unit` facultatif (20 caractères au
plus), que le constructeur propose (« cm⁻³ », « % », « °C », « nm », « sccm », « W », « min »…) et
que l'étiquette écrit ; sans unité, il s'enregistre sans la clé (la forme d'avant). L'ancienne
astuce, `unit=` dans l'obtention, reste lue. Les paramètres déclarés font partie de la structure
(un réglage : niveau mineur), mais **une unité ajoutée ou retirée seule** - ou passée de
l'obtention au champ - ne fait qu'écrire la valeur : niveau **retouche** (même numéro), conclusion gardée
(`versioning.same_settings`) ; une unité remplacée par une autre change la valeur : niveau
**mineur**.
- **Provenance des couches** : toujours celle du serveur. `simulation.simulate_process` simule une
  étape à la fois (mêmes images, mêmes erreurs que `simulate` de StructureForge, qui ne dit l'étape
  d'une couche que pour une croissance, et sans sa position) et suit les couches de la géométrie :
  une couche garde son objet tant qu'elle existe, une étape ajoute les siennes, un retournement les
  recrée dans l'ordre inverse. `layer_origins[k][j]` : la position de l'étape qui a créé la
  `j`-ième couche de l'image `k` (`-1` : le substrat). Jamais d'alignement de matériaux côté client.
- **Reprise d'une simulation** : chaque état atteint (les couches après une étape, leur provenance,
  l'image) est gardé en mémoire du serveur - les `simulation.MAX_CHECKPOINTS` derniers servis - et
  sur disque (`cache/simulations/` du dossier de données, `simulation.DISK_CHECKPOINTS_MAX_BYTES`
  au plus, les moins récemment servis effacés d'abord ; jamais dans la sauvegarde de la base, tout
  s'y recalcule), sous une clé qui résume le moteur (les sources de StructureForge en service),
  substrat, bibliothèques (matériaux racine, recettes du procédé et de la bibliothèque) et étapes
  jusque-là. Une simulation repart du plus long début déjà calculé : une étiquette, une brique ou
  un paramètre déclaré ne relancent rien, une retouche de l'étape k ne recalcule qu'elle et la
  suite, les variantes d'une campagne partagent les étapes d'avant leurs facteurs, une structure
  enregistrée se rouvre sans calcul même après un redémarrage. Mêmes images qu'une simulation
  complète. Côté constructeur, une seule simulation à la fois : une retouche pendant qu'elle tourne
  en relance une à son retour, avec l'état d'alors.
- **Pixel de N fils par sa maille** (`simulation.periodic_prefix`) : les bords du domaine sont des
  miroirs pour StructureForge, donc la maille d'un fil est déjà le réseau infini, et un pixel de N
  fils simulé d'un bloc coûte bien plus que N fois un fil (8 fils : 9 à 10 fois, mesuré). Tant que
  le procédé ne voit le réseau que par ses mailles (lithographies ancrées en mode fils ou
  entre-fils, dépôts conformes ou verticaux, gravures isotropes ou verticales, croissances non
  semi-polaires, planarisation, retournement...), la maille est simulée (le cache de la vue « 1
  fil ») puis répétée N fois, état par état ; la première étape qui voit le pixel entier (ouverture
  sur tout le pixel, ouvertures en nm absolus, faisceau incliné, croissance semi-polaire) et la
  suite se simulent sur le pixel, d'un bloc, depuis l'état répété. Les appelants passent les
  ancrages (`lattice_anchors`) ; sans eux, le pixel se simule d'un bloc, comme avant.
- **Rendu** (`structures.rendering.labelled_svg`) : le dessin de StructureForge devient un `<svg>`
  imbriqué, ajusté dans un carré de 400 unités, les étiquettes empilées à droite sans chevauchement
  (poussées sous la précédente, remontées si la pile dépasse le dessin), le trait partant d'un point
  de la couche vers son bord droit (la plus grande, si l'étape en a créé plusieurs). Textes échappés,
  couleurs et police en jetons de la charte avec leur valeur en repli (`var(--text, #1b2440)`) : le
  SVG reste autonome (capture, rapport). Sans étiquette, le SVG est celui d'avant. L'élément porte
  `data-bare-viewbox`, la vue sans les étiquettes (`.sp-layer-labels`). Une campagne écrit, sur
  chaque variante, ses propres valeurs (`campaigns.apply_combination`, relu depuis le plan et les
  valeurs de la variante).

## 5. Table de correspondance des routes

Rupture nette : les anciennes routes disparaissent sans alias. `{mp}` vaut
`{microproject_slug}` et `{exp}` vaut `{experiment_id}` (la piste).

### accounts

| Avant | Après |
|---|---|
| `POST /api/auth/register` | `POST /api/users` → 201 + session |
| `POST /api/auth/login` | `POST /api/sessions` → 201 `{user, expires_at}` + `Location` `/api/sessions/current` ; identifiants refusés → 422 `invalid_credentials` (401 reste réservé à l'absence de session) |
| *(nouveau : cible du `Location`)* | `GET /api/sessions/current` → `{user, expires_at}` de la session de l'appelant (401 sans session) |
| `POST /api/auth/logout` | `DELETE /api/sessions/current` → 204 |
| `GET /api/auth/me` | `GET /api/users/me` |
| `PUT /api/auth/me` | `PATCH /api/users/me` |
| `POST /api/auth/mot-de-passe` | `PUT /api/users/me/password` → 204 (mot de passe actuel faux → 422, jamais 401) |
| `POST /api/auth/mot-de-passe-oublie` | `POST /api/password-resets` → 202 |
| `POST /api/auth/reinitialiser` | `POST /api/password-resets/completions` `{token, password}` → 204 |
| `GET /api/auth/invitation/{token}` | `GET /api/invitations/{token}` (plugin microprojects, public ; `account_exists` pour proposer la connexion plutôt que l'inscription) |
| *(register avec invitation)* | `POST /api/invitations/{token}/acceptance` (connecté, même e-mail, sinon 403 `email_mismatch`) → 201 `{microproject: {slug, name}, role}` + `Location` vers l'adhésion `/api/microprojects/{mp}/members/{user_id}` ; `role` est le plus élevé du rôle déjà détenu et du rôle invité (une invitation ne rétrograde jamais) ; ajouter directement un membre supprime ses invitations en attente |

### teams

Toutes nouvelles. La lecture est ouverte à tout compte connecté (comme celle des projets) ; les
écritures sur l'équipe sont à l'admin, celles sur ses membres à l'admin ou à un manager de
l'équipe.

| Route | Effet |
|---|---|
| `GET /api/teams` | les équipes ; chacune porte son badge (`color`, `badge`, `short`), `member_count`, `managers`, `my_role`, `can_edit` (supprimer : admin) et `can_manage` (renommer, badge, membres : admin ou manager) |
| `POST /api/teams` `{name, color, badge}` (admin) | → 201 + `Location` ; couleur `#rrggbb` (422 `invalid_color`), badge de 4 caractères au plus (422 `invalid_badge`) |
| `GET /api/teams/{team_slug}` | une équipe |
| `PATCH /api/teams/{team_slug}` `{name, color, badge}` (admin ou manager de l'équipe) | nom et badge |
| `DELETE /api/teams/{team_slug}` (admin) | → 204 ; ses thématiques et µprojets restent, sans équipe (ouverts) |
| `GET /api/teams/{team_slug}/members[/{user_id}]` | les membres, ou un membre |
| `POST /api/teams/{team_slug}/members` `{email, role}` | → 201 + `Location` ; 404 `no_account`, 409 `already_member` |
| `PATCH` / `DELETE /api/teams/{team_slug}/members/{user_id}` | `{role}` / → 204 ; 409 `last_manager` si l'équipe resterait sans manager |

### search

| Avant | Après |
|---|---|
| `GET /api/microprojets/recherche`, `/api/plaques/recherche`, `/api/microprojets/recherche-fdl`, `/api/lots/recherche` (4 appels par frappe) | `GET /api/search?q=&types=` → `[{type, label, detail, badge, url}]` (types `microproject`, `lot`, `wafer`, `fdl` ; un type inconnu → 422 ; l'`url` est une page, donnée par le fournisseur) |

### areas · kpis · kpis_demo

| Avant | Après |
|---|---|
| `GET /api/management` | `GET /api/areas?team=` (équipe inconnue → 404 ; chaque projet expose `is_system`, `teams [{slug, name, color, short}]`, `attachable_teams`, `manageable_teams`, `placement_teams`, `can_manage`, `can_delete` (= `can_manage` et pas système), `can_place_microproject` (y créer ou y déplacer un µprojet, § 3), `horizon_months` calculé par le serveur) |
| `POST /api/management` | `POST /api/areas` `{…, team}` (l'équipe qui y travaille d'abord) → 201 (admin, avec ou sans équipe, ou manager pour l'une de ses équipes ; équipe inconnue → 422 `unknown_team`) |
| `GET /api/management/{slug}` | `GET /api/areas/{area_slug}` (projet, thématiques, objectifs) |
| `PUT /api/management/{slug}` | `PATCH /api/areas/{area_slug}` (`can_manage`) ; `POST /api/areas/{area_slug}/teams` `{team}` et `DELETE …/teams/{team_slug}` (admin ou manager de l'équipe ; 409 sur « Non classé », 409 `team_has_content` au retrait) ; `POST …/thematics/{thematic}/teams` `{team}` et `DELETE …/teams/{team_slug}` (inviter une équipe, en lecture seule ; 409 `owner_team`) |
| `DELETE /api/management/{slug}` | `DELETE /api/areas/{area_slug}` → 204 (409 pour un projet système) |
| `POST /api/management/{slug}/microprojets` | `PATCH /api/microprojects/{mp}` `{area, thematic}` |
| `POST /api/management/{slug}/thematiques` | `POST /api/areas/{area_slug}/thematics` → 201 |
| `GET /api/management/{slug}/thematiques/{t}` | `GET /api/areas/{area_slug}/thematics/{thematic_slug}` ; la frise : `GET /api/experiment-timeline?area=&thematic=` |
| `PUT /api/management/{slug}/thematiques/{t}` | `PATCH /api/areas/{area_slug}/thematics/{thematic_slug}` |
| `DELETE /api/management/{slug}/thematiques/{t}` | `DELETE …` → 204 |
| *(nouveau)* | `GET /api/thematics?area=` : liste à plat `{id, slug, name, area}` (remplace `/api/lots/thematiques`) |
| `POST /api/management/{slug}/objectifs` | `POST /api/areas/{area_slug}/objectives` → 201 |
| `PUT /api/management/{slug}/objectifs` (réordonner) | **supprimée** (aucun appelant) |
| *(nouveau : cible du `Location`)* | `GET /api/areas/{area_slug}/objectives/{objective_id}` (404 si l'objectif n'est pas celui de ce projet) |
| `PUT /api/management/{slug}/objectifs/{id}` | `PATCH /api/areas/{area_slug}/objectives/{objective_id}` |
| `DELETE /api/management/{slug}/objectifs/{id}` | `DELETE …` → 204 |
| `GET /api/management/{slug}/tendances` | `GET /api/areas/{area_slug}/kpis` |
| `GET /api/management/{slug}/tendances/{kpi}?mois=&variante=` | `GET /api/areas/{area_slug}/kpis/{kpi_key}?months=&variant=` |
| `GET …/tendances/{kpi}/etudes/{study_id}` | `GET /api/areas/{area_slug}/kpis/{kpi_key}/studies/{study_id}` (kpis_demo) |
| `GET /api/atlas?theme=` | `GET /api/areas/{area_slug}/atlas` (plugin atlas) → `{area, microprojects: [{…, experiments, edges}], microproject_links, entity_links}` : chaque étude porte `experiment_id` (la piste) et `version_id` (sa pointe), les `edges` d'un µprojet relient des pistes, les liens sont ceux des listes du plugin links ; le front relit ensuite les seuls liens (`GET /api/microproject-links`, `/api/entity-links`) après une création ou un retrait |

### microprojects

| Avant | Après |
|---|---|
| `GET /api/microprojets` | `GET /api/microprojects` (les miens : membre, ou de mon équipe) ; `?scope=readable` (tous ceux où j'ai un rôle) ; `?scope=all` (admin, sinon 403) ; `?area=&thematic=` (inconnu → 404, `thematic` sans `area` → 422). Le payload d'un µprojet nomme son rattachement `area` / `thematic`, comme le `PATCH`, et ne porte plus de compteurs : le front les lit dans `GET /api/experiment-stats` |
| `GET /api/microprojets/recherche?q=` | `GET /api/microprojects?q=&limit=` (toute la société, champs réduits `{slug, code, name, area}` ; `?q=` et `?code=` ne se combinent avec aucun autre filtre → 422) |
| `GET /api/microprojets/tous` | `GET /api/microprojects?scope=all` |
| `GET /api/microprojets/code/{code}` | `GET /api/microprojects?code=` → `[]` ou un élément, mêmes champs réduits |
| `POST /api/microprojets` | `POST /api/microprojects` `{name, description, area, thematic, team}` → 201 + `Location` (projet ou thématique inconnus → 422, comme le `PATCH` ; projet d'une équipe dont on n'est ni membre ni admin → 403 `placement_forbidden`, comme le `PATCH` `{area}` ; un nom qui donnerait le slug « new » ou « nouvelle » reçoit un suffixe) |
| `GET /api/microprojets/{slug}` | `GET /api/microprojects/{mp}` ; tout µprojet renvoyé porte `role` (effectif), `role_source` (`membership`, `team_manager`, `admin`, `team`, `thematic_team` ou `thematic_guest`), `team` (son badge), `can_edit` et `can_manage` (§ 3, règle d'autorisation) |
| *(nouveau)* | `PATCH /api/microprojects/{mp}` `{name, description, area, thematic, team}` (`owner` ; changer de projet vers celui d'une équipe dont on n'est ni membre ni admin → 403 `placement_forbidden`, § 3 ; renommer ou changer de thématique dans le même projet n'est pas vérifié) |
| `DELETE /api/microprojets/{slug}` | `DELETE /api/microprojects/{mp}?confirm_name=` → 204 (garde côté serveur : mauvais nom → 422 `confirm_name_mismatch`) |
| `GET …/members` | `GET /api/microprojects/{mp}/members` |
| `POST …/members` (upsert + invitation) | `POST /api/microprojects/{mp}/members` `{email, role}` → 201 + `Location` `/api/microprojects/{mp}/members/{user_id}` (409 déjà membre ; 404 `no_account`) |
| *(nouveau : cible du `Location`)* | `GET /api/microprojects/{mp}/members/{user_id}` (viewer) → `{id, name, email, role, is_creator}` ; 404 si ce compte n'est pas membre |
| *(changement de rôle par POST)* | `PATCH /api/microprojects/{mp}/members/{user_id}` `{role}` (409 `last_owner` / `creator_protected`, vérifiés sous verrou) |
| `DELETE …/members/{user_id}` | `DELETE …` → 204 (409 pour le créateur ou le dernier owner) |
| `GET …/invitations` | `GET /api/microprojects/{mp}/invitations` (en attente, non expirées, **sans le jeton**) |
| *(implicite dans POST members)* | `POST /api/microprojects/{mp}/invitations` `{email, role}` → 201, **sans `Location`** (une invitation n'a pas de route propre) ; réinviter une adresse remplace son invitation en attente, inviter un membre → 409 ; jeton stocké haché (SHA-256), les liens déjà envoyés restent valides |
| `DELETE …/invitations/{token}` | `DELETE /api/microprojects/{mp}/invitations/{invitation_id}` → 204 |
| `GET …/entites/historique` | `GET /api/wafers?microproject={mp}` (plugin wafers ; 403 hors membre, 404 inconnu) |
| `GET /api/microprojets/recherche-fdl` | `GET /api/wafers?fdl=` (plugin wafers) |

### attachments

| Avant | Après |
|---|---|
| `POST /api/microprojets/{slug}/images` | `POST /api/microprojects/{mp}/attachments` (multipart, `purpose=notebook`) → 201 `{id, url, …}` : une image (PNG, JPEG, GIF, WebP) ou un document d'une liste fermée (PDF, CSV, TSV, TXT, XLS, XLSX, DOCX, PPTX ; un document porte l'extension de son type - un `outil.exe` annoncé `application/pdf` → 422 - et un type annoncé vague se lit sur l'extension), 10 Mo au plus (413) ; un document se sert en téléchargement (`Content-Disposition: attachment`, `nosniff`). L'usage `evidence` d'avant n'est plus accepté au téléversement, ses fichiers restent lisibles |
| `POST /api/microprojets/{slug}/structures/images` | idem avec `purpose=structure` |
| `GET /api/microprojets/{slug}/pieces-jointes/{id}` | `GET /api/microprojects/{mp}/attachments/{attachment_id}/content` |
| *(nouveau)* | `GET /api/microprojects/{mp}/attachments/{attachment_id}` (métadonnées) |
| `POST/DELETE …/experiences/{ref}/pieces-jointes[/{id}]` | **supprimées** (aucun appelant front : on passe par attachments puis le cahier), avec les fonctions transitoires de `attachments.store` qui les servaient |

### structures · library

| Avant | Après |
|---|---|
| `GET /api/microprojets/{slug}/materials` | `GET /api/materials` |
| `GET /api/microprojets/{slug}/recettes` | `GET /api/recipes` → `{deposition: [...], etch: [...]}` (exception à « les autres sont un tableau » : le constructeur lit les recettes par sorte d'étape) |
| `POST /api/microprojets/{slug}/structures/simulate` | `POST /api/simulations` → 200 (calcul, rien n'est stocké) ; la réponse porte `step_ids`, l'id de chaque étape (§ 4, identité d'une étape), et chaque couche d'une image, `step_index`, la position de l'étape qui l'a créée (`-1` : le substrat) ; `layer_labels` (§ 4, étiquettes de couches) : les SVG portent les étiquettes, regroupées par `bricks` (§ 4, briques d'un procédé) |
| `POST /api/microprojets/{slug}/structures/variantes` | `POST /api/campaign-previews` → 200 (plafond `MAX_CAMPAIGN_ENTITIES`, 422 au-delà) ; chaque facteur désigne son étape par `step_id` (`"substrate"` pour le substrat ; id inconnu → 422, `step_index` refusé) ; `layer_labels` : chaque variante écrit ses propres valeurs ; `bricks` les regroupe |
| `GET /api/microprojets/{slug}/structures/intention-form` | `GET /api/ui-texts/intention` (plugin library) |
| `GET /api/bibliotheque/fichiers` | `GET /api/library/files` |
| `GET /api/bibliotheque/fichiers/{key}` | `GET /api/library/files/{file_key}` |
| `PUT /api/bibliotheque/fichiers/{key}` | `PUT /api/library/files/{file_key}` (admin ; 422 si le YAML est invalide) |

### process_library

Chaque collection est **à plat** : chaque élément porte `id` (opaque ; `builtin-<empreinte du nom>`
pour un élément intégré), `name`, `scope` (`builtin` / `shared` / `microproject`), `microproject`,
`created_by` et `updated_by` (`{id, name}`, ou `null` pour un élément intégré ou antérieur à cette
trace) et `can_edit`, calculé par le serveur. Le nom n'est qu'un champ, unique par portée (et par
µprojet) : on renomme avec un `PATCH`, et un renommage vers un nom déjà pris renvoie 409.

Lecture : un élément d'un µprojet dont on n'est pas membre répond 404 ; `?microproject=` d'un tel
µprojet répond 403 ; `scope=microproject` sans µprojet répond 422.

Droits d'écriture :
- `builtin` : lecture seule (on le modifie par les fichiers YAML de `library`) ;
- `shared` : création ouverte à tout compte connecté, modification et suppression par l'auteur
  ou un admin ;
- `microproject` : rôle `editor` sur ce µprojet.

| Avant | Après |
|---|---|
| `GET /api/microprojets/{slug}/presets-etapes` | `GET /api/step-presets?microproject={mp}` (intégrés + partagés + ceux du µprojet) |
| `POST …/presets-etapes` | `POST /api/step-presets` `{scope, microproject?, …}` → 201 |
| *(nouveau)* | `GET /api/step-presets/{preset_id}` (la cible du `Location`) |
| `PUT …/presets-etapes/{name}?partagee=` | `PATCH /api/step-presets/{preset_id}` (la portée est modifiable) |
| `DELETE …/presets-etapes/{name}?partagee=` | `DELETE /api/step-presets/{preset_id}` → 204 |
| `…/structures-sauvegardees[/{name}]` | `/api/saved-structures[/{structure_id}]` (même schéma) ; `derived_from` : un nom, ou l'origine `{microproject, experiment_id, version_id, ref}` d'une ref publiée depuis la page d'évolution avant les références (une étiquette, gardée telle qu'envoyée ; la page n'en publie plus : on publie une référence) |
| `…/briques-technologiques[/{name}]` | `/api/tech-bricks[/{brick_id}]` (même schéma) ; `GET /api/tech-bricks?reference=true\|false` : les briques de référence seulement (ou sans elles) ; chaque brique porte `version` (« 1.2 »), `versions` (`[{number, level, created_at, created_by, note}]`, avec `content` et `changes` sur `GET /api/tech-bricks/{brick_id}` seulement) et, promue, `reference` (`{promoted_by, promoted_at, note}`) ; `PATCH` accepte `note` (le pourquoi de la version que le changement fait ; 422 `brick_note_required` pour une brique de référence sans note) |
| *(nouveau)* | `DELETE /api/tech-bricks/{brick_id}/reference` → la brique, retirée des briques de référence (qui peut la modifier) ; la promouvoir : `POST /api/promotions/bricks` (§ promotion) |
| *(nouveau)* | `GET /api/tech-brick-usages?microproject=` → par id de brique visible, et par `structure:<id>` de structure visible, les études dont la version courante en a une copie, avec la version copiée |

Une structure enregistrée et une brique gardent, comme `declared_params`, leurs étiquettes de couches
par position d'étape (`layer_labels`, § 4 ; une position hors des étapes → 422) et l'appartenance
de leurs étapes aux briques (`bricks`, § 4 ; 422 `invalid_brick`).

### experiments

| Avant | Après |
|---|---|
| `GET /api/microprojets/{slug}/experiences?status=&offset=&limit=` | `GET /api/microprojects/{mp}/experiments?status=all\|running\|concluded&q=&offset=&limit=` → `{items, total}` (`q` : titre, intention, étiquettes, nom de piste ; chaque élément : `id` = la piste, `version_id` = sa pointe) |
| `POST …/experiences` | `POST /api/microprojects/{mp}/experiments` `{…, structure: {kind: "process", …}, reference_origin?: {reference, version}, wafer_origin?: {microproject, experiment_id, version_id?}}` → 201 (`reference_origin` : la version de référence dont part l'étude, § 4 ; sa forme seule est vérifiée, 422 sinon ; `wafer_origin` : partir de plaques existantes, les `entities`, § 4) |
| `POST …/experiences/image` | idem, avec `structure: {kind: "images", images: [...]}` |
| `POST …/experiences/campagne` | idem, avec `structure: {kind: "campaign", …, plan}` ; `from_version` pour partir d'une version existante ; les facteurs du plan désignent leur étape par `step_id`, comme l'aperçu. `reference_place` (index de variante, `null` : pas de référence dans le split) et `comparison_reference` (§ 4). Les étapes envoyées (lancement, évolution, fourche) peuvent porter leur `id` |
| `GET …/experiences/{ref}` | `GET /api/microprojects/{mp}/experiments/{exp}` (dernière version, `ETag`) ; le détail porte `id` (la piste), `version_id`, `is_tip`, `children` `[{experiment_id, version_id, title, is_tip}]`, `continued_at` (première suite structurelle), `reference_origin` (`{reference, version}` ou `null`) et `wafer_origin` (`{microproject, experiment_id, version_id, variant}` ou `null`) |
| `GET …/experiences/{ref}/timeline` | `GET …/experiments/{exp}/versions` → tableau, de la première version à la pointe : `{version_id, experiment_id, title, intent, created_at, author, is_tip, version, change_level}` (la frise des structures : `change_level != "none"`) |
| *(nouveau)* | `GET …/experiments/{exp}/versions/{version_id}` (une version de l'histoire de la piste, `ETag`) |
| *(nouveau)* | `GET /api/microprojects/{mp}/experiment-plans` → `{items}` ; `POST` `{title, intent, parent?: {experiment_id, version_id?}, mode: same_wafers\|new_wafers, wafers?, wafer_count?}` → 201 + `Location` (editor ; 422 `title_required`, `parent_required`, `entity_required`, `wafer_count_required`, `wafer_not_in_origin`, `wafers_different_structures` ; 404 `source_not_found`) ; `GET`/`PATCH` `{title?, intent?, mode?, wafers?, wafer_count?}`/`DELETE …/experiment-plans/{id}` (404 `plan_not_found`) - les expériences prévisionnelles (§ 4) ; `POST …/experiments` accepte `plan_id` |
| `POST …/{ref}/evoluer` | `POST …/experiments/{exp}/versions` `{structure: {kind: "process", …}, …}` + `If-Match` → 201 + `Location` vers la version ; **200 sans `Location`** si rien n'a changé (§ 4). Avec `structure: {kind: "campaign", plan, …}` et `reference_place?`, `comparison_reference?` : un **split modifié sur sa piste** (2026-10-15) - le lot recalculé comme au lancement, numéroté X.Y (un plan qui change : mineur), les plaques reportées par place (celles données, sinon celles en place, une place de plus à associer, une de moins effacée ; 422 `too_many_entities`), la plaque témoin toujours dernière, la plaque de référence telle que donnée (sinon gardée), FDL et cahier reportés ; les retouches de variantes tombent. Une campagne ne devient pas une étude simple par cette voie (422 `campaign_needs_split`) : une nouvelle piste, avec `from_version` |
| *(nouveau)* | `PUT …/experiments/{exp}/variant-overrides/{n}` `{substrate, steps, declared_params?, …}` (le procédé du constructeur) + `If-Match` → la piste à jour : **une variante corrigée à la main** (`campaign_variant_overrides[n] = {process, step_ids}`, sa structure simulée remplacée dans le lot, niveau `patch`) - `kinds.variant_process` rend la retouche, donc le carrousel (`GET …/variants` `overridden: [n…]`), `GET …/process?variant=`, la promotion, le comparateur et les jumelles lisent la variante corrigée ; `DELETE …/variant-overrides/{n}` la recalcule depuis le procédé commun et le plan (la pointe telle quelle sans retouche) ; 422 `not_a_campaign`, `unknown_variant` |
| `POST …/{ref}/evoluer-image` | idem, avec `structure: {kind: "images", …}` |
| *(nouveau)* | idem, avec `structure: {kind: "declared", description, images, factors, wafers: [{label, values}]}` (sans structure) - le lancement aussi (`POST …/experiments`) ; 422 `declared_no_wafer`, `declared_factor_unnamed`, `declared_factor_duplicate`, `declared_values_mismatch`, `too_many_entities` |
| `POST …/{ref}/dessin` | `PUT …/experiments/{exp}/structure-images` (toute la planche, dans l'ordre : `{image_id, kind, caption, annotations}` ; écriture légère, même révision de structure - c'est aussi par elle que se posent les annotations d'une image) |
| `POST …/{ref}/conclure` | `PUT …/experiments/{exp}/conclusion` (le verdict d'un objectif peut citer des entrées du cahier : `evidence_ids`, des ids d'entrées de la pointe, sinon 422 `notebook_entry_not_found`) |
| `POST …/{ref}/statut` | `PUT …/experiments/{exp}/status` `{status, hold_reason}` |
| `POST …/{ref}/etiquettes` | `PUT …/experiments/{exp}/tags` `{tags}` |
| `POST …/{ref}/entites` | `PUT …/experiments/{exp}/entities` `{entities}` (une par variante d'une campagne, 422 `entity_count` sinon ; au moins une pour une étude simple, ses réplicats ; 422 `duplicate_wafer`) |
| `POST …/{ref}/combiner` | `POST /api/microprojects/{mp}/experiments` `{merge_of: [{experiment_id, version_id?}, {experiment_id, version_id?}], title, intent, hypothesis, entities, objectives?, context?, branch?}` → 201 + `Location` vers la **nouvelle piste** (§ 4 : deux parents, la structure de la première, cahier vide ; les deux études ne changent pas). Exactement deux études, sans `structure` ni `from_version` (422) ; une version inconnue → 404 `source_not_found` ; deux fois la même piste ou la même version → 422 `same_experiment` ; une version d'avant la fourche de la piste désignée → 422 `version_before_line` ; une étude d'un autre µprojet n'y existe pas (404), et un champ de plus dans `merge_of` (`microproject`...) est refusé (422). `POST …/experiments/{exp}/merges` **supprimée** |
| `GET …/{ref}/process` | `GET …/experiments/{exp}/process?version=&variant=` (`variant` : le procédé d'une variante d'une campagne, § 4 ; chaque étape porte son `id` ; `layer_labels` : les étiquettes de couches par position d'étape, § 4 ; `bricks` : les briques du procédé par positions d'étape, § 4) |
| `GET …/{ref}/matrice` | `GET …/experiments/{exp}/variants?version=` (`overridden` : les variantes retouchées) ; le détail d'une campagne porte `campaign_plan` (`{factors: [{step_id, field, values, scale, label}]}`, ce que le constructeur rouvre en mode évolution) et `variant_overrides` (les index retouchés) |
| `DELETE …/experiences/{ref}` | `DELETE …/experiments/{exp}` (+ `If-Match`) → 204 (supprime la piste jusqu'au point de fourche ; 409 `has_descendants` si une autre piste part de l'une de ses versions - la piste n'est jamais seulement raccourcie) |
| `POST …/{ref}/ref`, `…/refs[/{ref_name}]`, `…/refs/graphe` | **supprimées** (2026-10-11) : les références (plugin `references`) sont les seules refs |
| *(nouveau)* | `GET /api/microprojects/{mp}/structure-history?all_versions=&include_versions=` (viewer ; `include_versions`, répété : des ids de version à montrer en plus - les versions publiées comme référence, que la page lit dans `GET /api/reference-versions` ; un id inconnu est ignoré) → `{lanes, nodes, edges}` pour la page d'évolution (`experiments.lineage.structure_history`) : pistes dans l'ordre de leur début puis du nom (une nouvelle piste vient en dernier) ; nœuds `{version_id, experiment_id, lane, version, label, change_level, title, created_at, author, is_tip, is_merge, structure_kind, has_process}` (`label` : « vX.Y ») - par défaut les versions structurelles, les fusions (combinaisons comprises) et le début de chaque piste, toutes avec `all_versions=true` ; arêtes `{parent, child, kind}` (`parent`, `fork` ou `merge` : vers une combinaison, depuis chacun de ses deux parents ; vers une fusion d'avant, depuis son second parent), à travers les versions masquées |
| `GET /api/microprojets/{slug}/filiation` | `GET /api/microprojects/{mp}/lineage` (les nœuds portent `version_id` et `experiment_id` - et `id`, égal à `version_id`, que citent les `edges` ; plus de badge de lot : le front le compose avec `GET /api/lots?wafer=`). Vers une version à deux parents (une combinaison), une arête depuis le nœud de chacune des deux études : une pointe est toujours un nœud, et deux pistes parties d'un même point sans changer sa structure n'y sont pas confondues avec ce point |
| `GET /api/microprojets/{slug}/graphe.html` | **supprimée**, ainsi que la page `/microprojets/{slug}/graphe` |
| *(dans les listes de µprojets)* | `GET /api/experiment-stats?microproject=&area=` → `[{microproject, running, concluded, abandoned, wafers, role_source}]` |
| *(dans la thématique)* | `GET /api/experiment-timeline?area=&thematic=` (champs masqués pour les non-membres) |

### notebook · external_images

Le plugin `evidence` a disparu (TODO § 3) : ses preuves sont les entrées manuelles du cahier.

| Avant | Après |
|---|---|
| `GET …/experiments/{exp}/evidence[/{evidence_id}]`, `POST …/evidence`, `PUT …/evidence/{evidence_id}/annotations` (plugin evidence) | **supprimées** : `…/notebook-entries` (`kind: "manual"` ; les annotations sont celles d'une mesure, modifiées par un `PATCH` de ses `measurements`) |
| `GET /api/microprojets/{slug}/donnees/sources` | `GET /api/characterization/data-types?by_wafer=true&status=implemented` |
| `POST …/donnees/instantanes` | `POST /api/microprojects/{mp}/snapshots` `{hook, wafers, refresh}` → 201 + `Location` (la clé `hook` est celle que stockent instantanés et vues) |
| `GET …/donnees/instantanes/{id}` | `GET /api/microprojects/{mp}/snapshots/{snapshot_id}` (immuable : `Cache-Control: private, max-age=31536000, immutable`) |
| *(dans le détail : `data_notebook`, `evidence`)* | `GET …/experiments/{exp}/notebook-entries?version=&step=&wafer=&kind=` → tableau (`ETag` : la version lue) ; `?summary=steps` → `{step_id: n}`, le nombre d'entrées qui s'appliquent à la version et ont une mesure à chaque étape (les badges du procédé) |
| `POST …/{ref}/cahier` | `POST …/experiments/{exp}/notebook-entries` → 201 + `Location` `…/notebook-entries/{entry_id}` + l'entrée (`ETag` : la version créée) |
| *(nouveau : cible du `Location`)* | `GET …/experiments/{exp}/notebook-entries/{entry_id}?version=` |
| `PUT …/{ref}/cahier/{entry_id}` (+ `move`) | `PATCH …/experiments/{exp}/notebook-entries/{entry_id}` (`exclude_unset` ; `measurements` les remplace toutes ; `position` entier, ramené dans les bornes ; sans effet → pas de version) |
| `DELETE …/{ref}/cahier/{entry_id}` | `DELETE …` → 204 (`ETag` : la version créée ; les verdicts de la conclusion ne la citent plus) |

Une entrée du cahier, une seule forme pour ses deux types :
`{id, kind: "prism" | "manual", title, note, objective, interpretation, wafers, measurements,
in_report, created_at, created_by, updated_at, updated_by}`, plus, à la lecture, `applies`.

- `wafers` : les plaques mesurées (clés de wafer : lasermark sans casse ni séparateur) ; vide, toute
  la piste. À l'écriture, une plaque citée doit être suivie par la version (422 `unknown_wafer`),
  sauf si l'entrée la portait déjà. **La donnée suit la plaque** : `applies` vaut `true` si `wafers`
  est vide ou si l'une de ses plaques est suivie par la version lue (`physical_tracking`) ; sinon
  l'entrée reste au cahier, à ranger parmi les « autres plaques ».
- `measurements` : une mesure par étape au plus (`step_id`, un id de `GET …/process` de la version,
  422 `unknown_step` sinon ; ou `null`, non située, une fois au plus), 30 au plus. Une même mesure
  faite à plusieurs étapes est une seule entrée. À la lecture, `step_retired` marque une mesure dont
  l'étape n'est plus dans le procédé de la version (l'entrée qui la porte peut la garder).
  - `prism` (une au moins) : `{step_id, snapshot_id, component, options}`, plus `snapshot` (résumé
    de l'instantané : `hook`, `hook_title`, `wafers`, `source`, `fetched_at`, `row_count`) ;
  - `manual` (zéro ou plus ; une mesure vide marque l'étape où elle a été faite) : `{step_id, value:
    {number, unit, name} | null, text, table: {columns, rows} | null, attachments: [{id, caption,
    filename, content_type, size, url}], links: [{label, url}], annotations: [{attachment_id |
    external_image, type: "arrow" | "box", x, y, x2, y2, label}], external_images: [{index, name,
    path, caption, status, url}], image_folder}` (`external_images` et `image_folder` absents quand
    vides ; `image_folder` : le dossier d'où on a épinglé les images, sous les racines et présent à
    l'écriture - 403 `outside_roots`, 422 `directory_not_found`, 503 sans racines -, ou déjà sur
    l'entrée, gardé tel quel même s'il a disparu). À l'écriture, `attachments` accepte des ids ou
    `{id, caption}` (des fichiers `purpose=notebook` de ce µprojet, 12 au plus) ; `links` n'accepte
    que `http`/`https` (10 au plus, 422 `invalid_link`) ; un tableau a de 1 à 50 colonnes, 1000
    lignes au plus, une cellule par colonne (texte de 500 caractères au plus, nombre fini, booléen
    ou vide ; 422 `invalid_table`) ; une annotation (la forme du noyau, `kernel.annotations`, 100
    au plus par mesure) désigne une image de la mesure par une clé qui ne bouge pas quand on
    réordonne ses images : un fichier image (`attachment_id`) ou une image externe
    (`external_image` : son chemin, unique dans la mesure) - l'un ou l'autre, sinon 422 ; une image
    retirée de la mesure part avec ses annotations (la page ne les renvoie plus).
- `objective` : un objectif de la version (422 sinon) - le lien d'une donnée à un objectif.

| Avant | Après |
|---|---|
| *(dans le détail : `data_items`)*, `POST …/{ref}/data`, `PATCH …/{ref}/data/{id}/epingle`, `DELETE …/{ref}/data/{id}` | **supprimées**, avec les routes `…/experiments/{exp}/image-sets` qui les avaient remplacées : les images externes sont un contenu d'une mesure manuelle du cahier (`external_images`, écrites par `POST`/`PATCH …/notebook-entries`), et les anciens jeux se lisent comme des entrées du cahier (§ 4) |
| `GET /api/microprojets/{slug}/data/image?chemin=` | `GET …/experiments/{exp}/notebook-entries/{entry_id}/external-images/{index}?version=` (viewer ; `index` : le rang de l'image dans l'entrée, ses mesures dans l'ordre ; le chemin est lu dans le cahier de la version, jamais reçu du client, et revérifié à chaque lecture : une image d'avant qui pointe hors des racines répond 403) ; c'est l'`url` que porte chaque image, qui nomme toujours la version lue (`?version=`, la pointe comprise) : le rang d'une image change quand on réordonne ou retire les images d'une mesure, une adresse ne désigne ainsi qu'une seule image et le navigateur peut la garder en cache |
| `GET /api/microprojets/{slug}/data/parcourir?dossier=` | `GET /api/microprojects/{mp}/external-images?directory=` (editor) → `[{name, path, size, displayable, url}]` (`url` : l'aperçu de l'image, ci-dessous) ; limité à `SPECTRE_EXTERNAL_IMAGE_ROOTS` (racines connues telles qu'écrites et résolues : un nom court Windows passe), désactivé sans cette variable (503 `browsing_disabled` ; les chemins locaux restent acceptés à la création, les chemins UNC non) ; les TIFF sont listés, non affichables ; seules les images d'un dossier sont listées, pas ses sous-dossiers |
| *(nouveau)* | `GET /api/microprojects/{mp}/external-images/file?path=` (editor) : les octets d'une image d'un dossier parcouru, pour la voir avant de l'épingler (le carrousel de l'éditeur du cahier) ; sous les racines seulement, 503 `browsing_disabled` sans elles (jamais un fichier local quelconque), formats affichables, 404 si absente |
| *(nouveau)* | `GET /api/microprojects/{mp}/external-images/roots` (editor) → `[chemin]` : les dossiers autorisés tels qu'écrits dans `SPECTRE_EXTERNAL_IMAGE_ROOTS` (absolus, sans doublon, sans toucher au disque), d'où partir pour choisir des images ; `[]` : le parcours est désactivé |

Une image externe d'une mesure : `{path, caption}` à l'écriture (100 au plus par mesure, sans
doublon) ; chaque chemin doit être absolu, sous une racine de `SPECTRE_EXTERNAL_IMAGE_ROOTS`, dans un
format que le navigateur affiche, et présent sur le disque (`external_images.service.checked_image`)
- sauf s'il est déjà sur l'entrée (une image d'un ancien jeu, déplacée depuis, reste). À la lecture,
`status` ∈ `ok`, `missing`, `unsupported`, `forbidden`, et l'`url` de ses octets. Une mesure sans image
externe n'enregistre pas la clé (elle se lit `[]`) ; une mesure PRISM n'en a pas.

Codes des images externes : hors des racines → 403 `outside_roots` (contrôle lexical avant tout accès disque, revérifié après résolution des liens) ; dossier ou image absents → 404 `directory_not_found` / `image_missing` ; rang hors de l'entrée → 404 `image_not_found` ; TIFF, fichier qui n'est pas une image, introuvable, chemin relatif ou chemin contenant un caractère NUL → 422 `unsupported_format` (le message dit d'exporter en PNG ou JPEG), `not_an_image`, `file_not_found`, `relative_path`, `invalid_path`.

Le plugin external_images se réduit à cette politique (`service` : `configured_roots`, `roots`, `checked_image`,
`image_status`, `readable_file`, `browse`) et au parcours des dossiers ; notebook en dépend. Garder un
plugin plutôt que l'absorber dans notebook : l'accès au disque du serveur (racines, chemins réseau,
formats) est une raison de changer à part, sensible, que le cahier n'a pas à porter ; le DAG reste
propre (external_images ne dépend que de microprojects, placé avant notebook).

### references

Toutes nouvelles (TODO, « Références de structure »). Une **référence** est un objet de toute
l'application ; tout compte connecté lit les références, leurs versions et leurs instantanés, et en
crée une. Plugin `references` : `service.py` (le domaine), `local_refs.py` (les refs locales d'avant, regroupées une fois par la migration `0005`).

| Route | Effet |
|---|---|
| `GET /api/references?q=` | toutes les références, la plus récemment mise à jour d'abord (une version publiée la met à jour) : `{slug, name, description, created_by, created_at, updated_by, updated_at, latest_version: {number, label, change_level, published_by, published_at, source, note} \| null, version_count, usage_count, can_edit}` ; `q` : nom, slug, description, sans casse ni accents |
| `POST /api/references` `{name, description}` | → 201 + `Location` `/api/references/{reference_slug}` + la référence, sans version ; nom vide ou sans lettre ni chiffre → 422 `invalid_reference_name`, nom déjà pris (comparé sans casse, ni accents, ni ponctuation) → 409 `reference_name_taken` |
| `GET /api/references/{reference_slug}` | une référence (404 `reference_not_found`) |
| `PATCH /api/references/{reference_slug}` `{name, description}` | son créateur ou un admin (403) ; le **slug ne change pas** (une étude cite sa référence par lui) ; sans effet → 200, rien d'écrit |
| `DELETE /api/references/{reference_slug}` | → 204 ; son créateur ou un admin (403) ; une référence qui a des versions, un admin seulement (409 `reference_has_versions` pour son créateur) - ses versions partent avec elle, les études qui en étaient parties gardent une origine désormais inconnue : son slug n'est **jamais redonné** (`retired_reference_slugs` ; une nouvelle référence du même nom reçoit `-2`), celui d'une référence sans version (aucune étude n'a pu en partir) se libère |
| `GET /api/references/{reference_slug}/versions` | `{reference, lanes, nodes, edges}` : l'évolution de la référence. `nodes`, dans l'ordre de publication : `{number, major, minor, label, change_level, parent, parent_inferred, imported, note, published_by, published_at, source, usage_count, usages, lane}` ; une version prend la colonne (`lane`) de son parent si elle en est le premier enfant, sinon une nouvelle ; `lanes` : `{index, start, head}` ; `edges` : `{parent, child, kind: "parent" \| "branch", inferred}` |
| ~~`POST /api/references/{reference_slug}/versions`~~ | **supprimée** (2026-10-11) : publier une version passe par le plugin promotion (`POST /api/promotions`), seul chemin pour choisir une référence, avec ses règles |
| `GET /api/references/{reference_slug}/versions/{version_number}` | une version (404 `reference_version_not_found`) : son nœud, plus `reference {slug, name}`, `structure_svg` (l'instantané dessiné par le serveur, étiquettes comprises) et `process` (son procédé éditable, la forme de `GET .../experiments/{exp}/process` : étapes avec leur id, `layer_labels` et `bricks` par positions) - ce que le constructeur charge pour lancer une étude depuis elle |
| `GET /api/reference-versions?microproject=` | les versions de référence publiées depuis ce µprojet (viewer : 403 sinon ; inconnu → 404) : `[{reference: {slug, name}, number, label: "R nom 1.1", experiment_id, version_id, variant, local_tag, change_level, published_at}]`, pour les badges de sa page d'évolution et le bloc « Référence » de la fiche |

- **Numéro** (`service.next_number`) : la version est comparée à sa version parente par le
  versionnage des études (`experiments.service.structure_change_level`). La première est 1.0 ; un
  changement **majeur** (substrat, suite d'étapes) ouvre le majeur suivant **le plus grand pris** (un
  majeur quand 2.0 existe : 3.0) ; un **mineur** ou une **retouche** (étiquettes, nom d'étape, unité
  ajoutée seule) prend le mineur suivant le plus grand pris sous le majeur du parent (deux dérivations
  de 1.0 : 1.1 puis 1.2) ; aucun changement → 409. Les écritures des références passent une à une
  (`keyed_lock("references", "write")`), et `(reference_id, number_major, number_minor)` est unique :
  deux publications simultanées n'ont jamais le même numéro. `change_level` garde le niveau
  (`initial`, `major`, `minor`, `patch` ; `none` pour un import seulement).
- **Instantané** (`service.snapshot_of`, colonne `snapshot`) : la structure dessinée
  (`structure_type`, `structure` de Follow), les métadonnées qui la décrivent (`structureforge_process`
  - substrat, étapes, paramètres déclarés avec leur unité -, `process_step_ids` tels qu'on les lit,
  `process_layer_labels`, `process_layer_steps`, `process_bricks`) et le titre de l'étude. Pour une
  campagne (un split), celui de la variante promue (colonne `variant`, migration `0006`) : sa structure
  simulée et son procédé, les valeurs de ses facteurs appliquées (`kinds.variant_process`) - une étude
  simple, d'où l'on peut lancer une étude. Une version
  se dessine, se reprend et se compare sans son étude : elle reste utilisable si l'étude change de
  droits ou disparaît. Aucun objet Follow n'est écrit.
- **Source et masquage** : `source` = `{microproject: {slug, code, name}, experiment_id, version_id,
  title, variant, local_tag, linked: true}` pour un membre du µprojet source (un admin l'est de tous),
  `{microproject: {name}, linked: false}` pour les autres, `{microproject: {name, deleted: true},
  linked: false}` si le µprojet a été supprimé (son nom à la publication). Les usages suivent la même
  règle : `{microproject, experiment_id, title, status, updated_at, linked: true}` ou
  `{microproject: {name}, linked: false}`.
- **Usages** : les études parties d'une version - la pointe de chaque piste dont `reference_origin`
  désigne `(slug, numéro)`, lue dans le dépôt en cache de chaque µprojet (une lecture par µprojet et
  par réponse) ; une fourche ou une combinaison qui a gardé l'origine compte aussi. Une origine
  inconnue n'est comptée nulle part.
- **Les refs locales d'avant** (`local_refs.import_shared_local_refs`, appelée une fois par la
  migration `0005_local_refs_imported_once`, qui supprime ensuite les tables `reference_import_scans`,
  `reference_import_rules` et `dismissed_local_refs` qui suivaient le regroupement) : seuls les noms
  de refs portés dans **au moins deux µprojets** (`SHARED_BY`, règle du 2026-10-05) sont devenus des
  références. Les étiquettes Follow de tous les µprojets sont lues et regroupées par nom normalisé
  (`service.normalized_name` : sans casse, ni accents, ni ponctuation), sauf les noms automatiques
  « ref vX.Y.Z » (suffixés ou non), les étiquettes d'une structure qui n'est pas un procédé dessiné
  et celles dont un admin avait retiré la référence (`dismissed_local_refs`, lue une dernière fois).
  Chaque nom partagé a sa référence (celle qui a déjà reçu des étiquettes de ce nom, même renommée ;
  sinon une référence du même nom existante ; sinon une nouvelle : le nom de sa plus ancienne
  étiquette, créateur : celui du µprojet de la première version), chaque étiquette une version
  (`local_tag`, `published_by` vide, `published_at` : la date de la version étiquetée), dans l'ordre
  des dates ; son parent est la dernière version de la référence dont la version étiquetée descend
  dans le même dépôt, sinon la précédente (`parent_inferred` : un rattachement déduit) ; une version
  identique à son parent (la même structure étiquetée dans deux µprojets) reçoit le mineur suivant,
  `change_level` `none` ; une étiquette déjà importée ou dont la version Follow est déjà une version
  de la référence ne l'est pas deux fois. Sur une installation où l'ancienne règle (chaque ref nommée
  devenait une référence) avait tourné sans que celle du 2026-10-05 passe, la migration retire
  d'abord les références créées depuis un seul µprojet que personne n'a touchées (toutes leurs
  versions importées, aucune publiée à la main, aucune d'un µprojet supprimé, aucune étude qui cite
  leur slug), sans réserver leur slug. Les étiquettes restent en place, aucun fichier Follow n'est
  réécrit ; un nom qui n'était porté que par un µprojet reste un repère local, qu'un éditeur publie
  à la main. Plus rien ne pose d'étiquette Follow depuis les refs déclarées (2026-10-11) : une
  étiquette qui apparaîtrait après (un dépôt copié d'ailleurs) n'est plus regroupée.

### promotion

Nouvelles (2026-10-11). **Choisir une référence** - une nouvelle référence, ou une nouvelle version
d'une référence - passe par un seul formulaire, la page `/promotion`, que chaque endroit où l'on
voit une structure ouvre déjà rempli (`PromotionLink.url` : `?microprojet=&etude=&version=&variante=
&reference=&retour=`) : en tête de la fiche d'une étude, au-dessus de sa structure (la variante que
montre le carrousel d'un split), dans la conclusion (décider « Retenir comme référence » ouvre le
formulaire une fois la conclusion enregistrée ; tant que rien n'est promu, l'en-tête de la fiche le
rappelle), sur la page d'évolution d'un µprojet, la liste des références (« Promouvoir une
structure ») et la page d'une référence (« Promouvoir une nouvelle version »), plus l'entrée
« Promouvoir une réf. » de la barre du haut. Le bouton est **toujours montré** : ce que la structure
permet ou non, ce sont les règles du formulaire qui le disent. Une référence ne se crée plus vide :
elle naît avec sa première version.

| Route | Effet |
|---|---|
| `POST /api/promotions/preview` `{microproject, experiment_id, version_id?, variant?, reference? \| new_reference? {name, description}, parent?, note}` | ce que donnerait la promotion, rien n'est écrit : `{source: {microproject, experiment_id, version_id, title, status, decision, structure_kind, variants: [{index, label}], variant, structure_svg}, suggestion: {reference, name, parent, why} \| null, target: {reference \| null, new_name}, parents, base, level, level_text, number, rules: [{rule, label, level, message, code}], can_promote}` ; sans `reference` ni `new_reference`, la référence proposée (celle dont part l'étude, à la suite de la dernière version publiée depuis la piste ; sinon la dernière où a été publiée une version dont elle descend) ; lecteur du µprojet (403 sinon) |
| `POST /api/promotions` (même corps) | → 201 + `Location` `/api/references/{slug}/versions/{number}` + la version (`GET` d'une version) ; refusée avec le statut et le code de la **première règle qui bloque** ; sinon, dans une transaction sous le verrou des références : la nouvelle référence (si `new_reference`), la version (`references.service.record_publication`), l'entrée du journal ; µprojet inconnu → 422 `unknown_microproject`, piste, version ou référence inconnue → 404, `parent` inconnu → 422 `unknown_parent_version` |
| `GET /api/promotions?microproject=&experiment_id=&limit=` | le journal, les plus récentes d'abord : `{reference: {slug, name, exists}, number, created_reference, source, note, warnings, promoted_by, promoted_at}` ; `source` masquée comme celle d'une version de référence |
| `GET /api/promotion-sources` | les µprojets où l'on peut promouvoir (éditeur) : `[{slug, name}]` |
| `POST /api/promotions/bricks/preview` `{brick_id, note}` | ce que donnerait la promotion d'une brique comme **brique de référence**, rien n'est écrit : `{brick, rules: [{rule, label, level, message, code}], can_promote}` (`brick_rules.py`) |
| `POST /api/promotions/bricks` (même corps) | → 201 + `Location` `/api/tech-bricks/{id}` + la brique (partagée, `reference` posée) ; refusée avec le statut et le code de la première règle qui bloque : droit de promouvoir (403 `forbidden`, `builtin_brick`), brique utilisable (422 `brick_empty`), pas déjà une référence (409 `brick_already_reference`), nom libre parmi les briques partagées (409 `brick_name_taken`), justification (avertissement). Pas d'entrée au journal des promotions de structures : la brique porte elle-même qui l'a promue, quand et pourquoi |

- **Les règles** (`rules.py`) : un registre, comme les sources du comparateur. Une règle
  (`Rule(id, label, check, order)`) reçoit le `Candidate` (qui promeut, la publication planifiée par
  `references.service.plan_publication` : source, instantané, référence visée, version parente,
  numéro, version déjà publiée depuis la même source ; le nom d'une nouvelle référence ; le pourquoi)
  et rend `ok`, `warn` (on peut promouvoir, en le sachant), `block` (statut et code de l'erreur) ou
  `None` (sans objet). Celles de base : droit de promouvoir (`editor`, 403), variante du split
  (`variant_required`), structure utilisable comme point de départ (`reference_needs_process`,
  `unknown_variant`, `no_variant_process`), référence visée (`invalid_reference_name`,
  `reference_name_taken`), différente de sa version parente (`reference_version_identical`), pas déjà
  promue (`reference_version_already_published`), étude conclue (avertissement : pas conclue, ou la
  conclusion n'a pas retenu cette structure), justification (avertissement). **Choisir une référence
  suivra un jour d'autres règles** : une règle de plus est une fonction de plus, enregistrée ici ou par
  un autre plugin (`from ..promotion.rules import Rule, register_rule`) - le formulaire la montre,
  l'API l'applique, le journal la garde.
- **Une variante de split** est promue comme une étude simple : son instantané est sa structure
  simulée et son procédé (`references.service.snapshot_of(..., variant)`), la version garde son index
  (`reference_versions.variant`) ; chaque variante d'une même version Follow peut devenir une version
  de référence.
- **Le journal** (`promotions`) garde les noms du jour (référence, µprojet, titre de l'étude), le
  pourquoi et les verdicts des règles passées, pour relire sous quelles règles on a choisi.

### intent_forms

Même forme et mêmes droits d'écriture que les collections de process_library (portées `shared` et
`microproject`, sans élément intégré), plus `created_at`, `updated_at` et `form`. Le `PATCH`
n'accepte que `name` et `yaml` : la portée d'une entrée est fixée à sa création.

Le formulaire actif est une **copie** : son origine `{form_id, name}` est écrite en commentaire
sur la première ligne de `commit_form.yml` (Follow ignore les commentaires). Modifier ou supprimer
l'entrée ne touche pas la copie ; `outdated` vaut `true` quand les questions de l'entrée diffèrent
de la copie (un simple renommage ne compte pas, une entrée supprimée non plus).

| Avant | Après |
|---|---|
| `GET /api/microprojets/{slug}/formulaires-intention` | `GET /api/intent-forms?microproject={mp}` (à plat, avec `scope`) |
| *(nouveau)* | `GET /api/intent-forms/{form_id}` (la cible du `Location`) |
| `POST …` | `POST /api/intent-forms` → 201 |
| `PUT …/{name}` | `PATCH /api/intent-forms/{form_id}` |
| `DELETE …/{name}?partagee=` | `DELETE /api/intent-forms/{form_id}` → 204 |
| `GET …/formulaire-actif` | `GET /api/microprojects/{mp}/active-intent-form` → `{form, origin, outdated}`, ou 204 sans corps si aucun (un singleton absent est un état normal, pas une erreur : un 404 s'afficherait en rouge dans la console à chaque page qui le lit) — lu depuis `commit_form.yml`, la seule vérité |
| `POST …/formulaire-actif` `{name}` / `{name: null}` | `PUT …/active-intent-form` `{intent_form_id}` / `DELETE` → 204 |

### wafers · lots · links

| Avant | Après |
|---|---|
| `GET /api/plaques/recherche?q=` | `GET /api/wafers?q=` (aussi `fdl=` et `microproject=` ; chaque élément porte `key`) |
| `GET /api/plaques/{lasermark}` | `GET /api/wafers/{wafer_key}` (le lasermark tel qu'écrit marche aussi ; sans les lots : `GET /api/lots?wafer=` ; une plaque inconnue → 200 sans occurrence, comme avant) ; chaque occurrence : `lasermark`, `entity_index` et `experiment: {microproject, member, status, updated_at, tracked_since, id?, version_id?, title?, campaign?}` (`tracked_since` : la première version de la piste qui suit la plaque ; les champs en `?` pour les membres seulement) |
| `GET /api/lots?statut=actifs\|sortis\|annules\|tous` | `GET /api/lots?status=planned,wip,hold,done,cancelled&q=&wafer=&code=&view=summary` → tableau ; clés en anglais (`experiments`, `thematics`, `via_experiments`) et `is_active` calculé par le serveur |
| `GET /api/lots/recherche`, `/selection` | `GET /api/lots?q=…`, `GET /api/lots?view=summary&status=…` |
| `GET /api/lots/thematiques` | `GET /api/thematics` (plugin areas) |
| `POST /api/lots` | `POST /api/lots` → 201 + `Location` + `ETag` (409 `lot_code_taken`, course comprise) |
| *(datalists codées en dur)* | `GET /api/lot-priorities` → les priorités proposées à la saisie (P10…P50 ; toute valeur courte reste acceptée). Nouvelle route : la liste des lots est devenue un tableau, les suggestions n'avaient plus d'autre source |
| `GET/PUT/DELETE /api/lots/{code}` | `GET` / `PATCH` / `DELETE /api/lots/{lot_id}` (204) ; le code devient un champ filtrable. `PATCH` : `exclude_unset`, `If-Match` = `updated_at` (`ETag`, ISO UTC ; 412 `stale_version`), sans effet → rien d'écrit ; les règles de statut d'un lot déclaratif sont une fonction pure (`declared_state`) ; un lot `prism` refuse priorité, dates et wafers (409 `lot_read_only_source`) |
| `POST /api/lots/{code}/wafers` | `POST /api/lots/{lot_id}/wafers` `{lasermarks}` → 201, 200 si rien n'est ajouté ; **sans `Location`** (un wafer d'un lot n'a pas de route propre) |
| `DELETE /api/lots/{code}/wafers/{lasermark}` | `DELETE /api/lots/{lot_id}/wafers/{wafer_key}` → 204 (404 si absent) |
| `PUT /api/lots/{code}/thematiques` | `PUT /api/lots/{lot_id}/thematics` `{thematic_ids}` |
| `POST /api/liens-projets` | `POST /api/microproject-links` `{a, b, note}` (slugs) → 201 `{id, a: {slug, name}, b, note, created_at}`, **sans `Location`** (un lien se lit dans la liste) ; doublon dans un sens ou l'autre → 409 `already_linked` ; µprojet lié à lui-même → 422 `self_link`, inconnu → 422 `unknown_microproject` ; rôle editor des deux côtés |
| `DELETE /api/liens-projets/{id}` | `DELETE /api/microproject-links/{link_id}` → 204 (editor d'un côté au moins) |
| *(nouveau)* | `GET /api/microproject-links?microproject=&area=` (un lien n'est listé qu'aux membres de ses deux µprojets ; retenu dès qu'un de ses bouts correspond au filtre ; `?microproject=` inconnu → 404, hors membre → 403 ; `?area=` inconnu → 404) |
| `POST /api/liens-entites` | `POST /api/entity-links` `{a: {microproject, experiment_id, entity_index}, b: {…}, note}` → 201, sans `Location` (désigne la piste : piste inconnue → 422 `unknown_experiment`, index hors de la pointe → 422 `unknown_entity`, même entité des deux côtés → 422 `self_link`) ; les lignes existantes sont migrées vers la piste, les irrésolubles gardées dans `entity_links_unresolved` et journalisées |
| `DELETE /api/liens-entites/{id}` | `DELETE /api/entity-links/{link_id}` → 204 |
| *(nouveau)* | `GET /api/entity-links?microproject=&area=` (mêmes règles) |

Les plaques d'une FDL (`wafers.fdl_source`) : `GET /api/fdls/{fdl}` → `{fdl, source, editable,
known, wafers: [{lasermark, slot}]}` (le numéro tel qu'écrit, normalisé ; `known` faux pour une FDL
que la source ne connaît pas) et `PUT /api/fdls/{fdl}/wafers` `{lasermarks}` (dans l'ordre du lot,
chacune une fois ; aucune efface la FDL) - seulement quand la source est la base locale, 409
`fdl_source_read_only` sinon. Une seule fonction choisit la source (`fdl_source.current_source`) :
la démo avec `SPECTRE_DEMO_DATA=1` (des plaques inventées, toujours les mêmes pour un même
`FDL-n`, lecture seule), la base locale sinon (table `fdl_wafers`, migration `wafers/0001_fdl_wafers`,
saisie à la main) ; **PRISM** la remplacera, en lecture seule, derrière le même contrat (`FdlSource`).
Côté front, `wafers/fdl.js` : `mountStudyFdl` (le champ des FDL de l'étude et ce que la base dit de
chacune, avec la saisie de ses lasermarks), `fdlWaferChoices`, `fdlWaferSelectHtml` (le menu d'une
place : « à associer », les plaques par FDL, une déjà prise grisée), `withFdl`.

Visibilité des plaques : une seule règle (`wafers.service`), partagée par les lots. Tout compte
connecté voit qu'un autre µprojet suit une plaque (µprojet, statut, dates) ; titre, lien,
emplacement, FDL et variante restent aux membres, et la recherche par FDL ne lit que les FDL des
µprojets dont on est membre. Avant, la page et la recherche des plaques ne montraient que ses
propres µprojets quand les lots montraient déjà les autres, masqués : les deux suivent désormais la
règle des lots. Une entité suivie sans lasermark (un emplacement seul) n'a pas de `wafer_key` et
n'est plus proposée à l'autocomplétion.

### characterization

| Avant | Après |
|---|---|
| `GET /api/donnees/hooks` | `GET /api/characterization/data-types?category=&status=&by_wafer=` |
| `GET /api/donnees/categories` | `GET /api/characterization/categories` |
| `GET /api/donnees/hooks/{key}` | `GET /api/characterization/data-types/{data_type_key}` |
| `POST /api/donnees/hooks/{key}/executer` | `POST /api/characterization/data-types/{data_type_key}/queries` `{parameters, refresh}` → 200 (plafond de wafers commun) |
| `GET /api/donnees/hooks/{key}/graphiques/{chart}` | `GET /api/characterization/data-types/{data_type_key}/charts/{chart_key}` |

Codes, pour les deux sources : type inconnu (ou que la démo ne sait pas servir) 404 ; type à venir
422 `not_implemented` ; paramètres invalides ou plus de `MAX_WAFERS` plaques 422 ; configuration
PRISM absente 503 ; connexion, requête ou fiche `hook.yml` invalide 502 (une fiche invalide est
écartée du catalogue et journalisée, sans faire tomber `/categories`).

### comparator

Toutes nouvelles (2026-10-11). Rien n'est enregistré : une comparaison se relit à chaque fois, et
son adresse la partage (`/comparateur?item=…&item=…&base=n`). Plugin `comparator` : `table.py` (le
tableau, pur), `service.py` (les jetons, le registre des sources, la source « étude »).

| Route | Effet |
|---|---|
| `GET /api/comparisons?item=&item=…&baseline=` | le tableau des lignes désignées par leurs jetons, dans l'ordre (30 au plus ; 60 lignes au plus une fois les campagnes détaillées), comparées à la ligne `baseline` (0 par défaut) : `{baseline, rows, groups, summary}`. Jetons : `study:<µprojet>/<piste>[@<version>][~<place>]` (une campagne : une ligne par variante, la plaque de référence d'abord, `~n` la seule variante `n` ; un split déclaré : une ligne par plaque), `wafer:<lasermark>` (la dernière étude de vos µprojets qui suit la plaque, sa variante), `reference:<slug>[@<numéro>]` (la dernière version sans numéro). Chaque ligne rendue porte son jeton exact (`item`), `label`, `version`, `sublabel`, `context`, `url`, `wafers`, `badge` (« RÉF »), `baseline`, `cells` (une par colonne : `{text, status, title, changed?}`, `None` sans rien à comparer), `note` (une structure en images), `error` (une ligne introuvable ou interdite garde sa place : µprojet sans rôle, plaque suivie ailleurs seulement, version inconnue), `notes` (les retouches face à la base : étapes renommées, étiquettes) et `summary`. `groups` : le substrat, puis une entrée par étape (`{key, label, kind, kind_label, position, status, differs, columns: [{key, label, status, differs}]}`) ; un split déclaré a le sien. Jeton mal formé → 422 `invalid_comparison_item` ; aucun → 422 `no_comparison_items` ; trop → 422 `too_many_comparison_items` |
| `GET /api/comparison-candidates?q=&source=` | ce qu'on peut ajouter pour une saisie, source par source (plaques, études, versions de référence ; `source` : celles-là seulement) : `[{item, source, label, sublabel}]` ; une plaque n'est proposée qu'à un membre d'un µprojet qui la suit |

- **Le code couleur** (statut d'une cellule face à la base) : `changed` rouge (la valeur change, un
  paramètre retiré compris), `added_param` violet (une colonne que l'étape de la base n'a pas : un
  paramètre ajouté), `added_layer` vert (une étape que la base n'a pas), `moved` orange (l'étape est
  ailleurs dans l'ordre ; `changed` dit si sa valeur change aussi), `absent` (la base a l'étape, pas
  cette ligne), `same`, `empty` (ni l'une ni l'autre), `na` (une ligne d'une autre sorte : split
  déclaré face à un procédé). `differs` d'une colonne ou d'une étape : la page peut ne montrer que
  les différences.
- **Les colonnes** : celles des champs de chaque étape (matériau, recette, épaisseur, vitesses...),
  ses paramètres déclarés (valeur et unité), le mode et la taille d'une lithographie ancrée au réseau
  (ses ouvertures, qui suivent le nombre de fils vus, non), les ouvertures d'une lithographie dessinée
  (nombre et largeur), les paramètres d'une étape chimique ; le substrat : matériau, épaisseur, largeur
  du domaine ou pas du réseau. Une colonne vide partout tombe ; une étape sans paramètre garde une
  colonne « Présente ». Les longueurs se comparent en nm (`0.15 µm` = `150 nm`) ; une recette propre au
  procédé se compare avec sa définition.
- **L'appariement des étapes** (`table._align`) : par id quand deux lignes en partagent (versions
  d'une piste, variantes, fourche, version de référence et étude publiée) ; sinon par type et
  matériau (ou recette), dans l'ordre - plus longue sous-suite commune pondérée. Appariée par id hors
  de cet ordre, ou restée seule avec sa jumelle (même type, même matériau) : déplacée. Restée seule :
  ajoutée après la dernière étape appariée qui la précède. La base des étapes est la ligne `baseline`
  si elle a un procédé, sinon la première qui en a un (de même pour un split déclaré).
- **Le front** : `comparator/static/comparator-table.js` (global `Comparator` : `mount(el, result,
  {tools, onBaseline, onRemove, onMove})` - la légende au-dessus, la case « Seulement les
  différences » (préférence de ce navigateur), le tableau à en-têtes et première colonne collants,
  défilant dans sa carte, les retouches dessous ; `summaryText`, `studyItem`, `waferItem`,
  `referenceItem`, `pageUrl`). Il sert à la page `/comparateur` (recherche à suggestions, lignes à
  monter, descendre, retirer ou prendre comme base, lien à copier ; bouton à icône de la barre du
  haut), sous le diagramme des pages d'évolution d'un µprojet et d'une référence (deux versions, la
  première choisie en base ; le panneau n'en garde que le résumé et « Voir le tableau »), et en liens
  depuis la fiche d'une étude (« Comparer », « Comparer les plaques » d'une campagne) et la page d'une
  plaque (« Comparer sa structure »).

### usage

Toutes nouvelles, réservées aux administrateurs (403 sinon).

| Route | Effet |
|---|---|
| `GET /api/usage?start=&end=&granularity=&team=&user_id=&plugin=&include_admins=` | le rapport d'une période (30 derniers jours par défaut, `day`, `week` ou `month`, trois ans au plus et 400 jours au plus par jour : 422 `invalid_period`, `invalid_granularity`) : `period` (et la période d'avant, de même durée), `tracking_since`, `catalog` (les plugins mesurés), `totals` et `previous` (comptes inscrits et actifs, taux d'adoption, actifs par jour ouvré, pic, pages vues, lectures - les `GET` de l'API -, écritures - les autres méthodes -, modules utilisés, erreurs), `series` et `plugin_series` (par période du graphique, vides comprises), `plugins` (tous, jamais utilisés compris : utilisateurs, part des actifs, mesures, requêtes de la période d'avant, dernière utilisation), `heatmap` (jour de la semaine x heure), `routes` (les 200 plus sollicitées, le titre de la page pour une page, temps moyen et max, erreurs), `users` (les comptes du périmètre, inactifs compris : jours actifs, mesures, rythme `daily` / `weekly` / `occasional` / `inactive`, trois modules favoris, première et dernière activité). `team` (slug, 404 inconnu) : ses membres ; `plugin` (404 inconnu) : un seul module ; `include_admins=false` : sans les administrateurs |

### Pages (URL françaises, inchangées sauf mention)

| Plugin | Pages |
|---|---|
| accounts | `/connexion`, `/inscription`, `/mot-de-passe-oublie`, `/reinitialiser`, `/profil` |
| teams | `/equipes`, `/equipes/{slug}` (nouvelles) |
| areas | `/`, `/management/{slug}`, `/management/{slug}/thematiques/{thematique_slug}` |
| atlas | `/management/{slug}/atlas` |
| microprojects | `/microprojets/{slug}`, `/p/{code}` (redirection, **après** contrôle de session), `/projets/{rest:path}` (redirection héritée, 308) |
| experiments | `/microprojets/{slug}/experiences/{experiment_id}` (`?version=` pour une version passée, en lecture seule ; un ancien id de version est résolu puis redirigé en 302 par le `page_router`, sans `?version=` si c'est la pointe, vers `/connexion` hors session, vers le µprojet si la version est introuvable), `/microprojets/{slug}/evolution` (nouvelle : « Évolution des structures », diagramme des pistes, versions et versions de référence ; liée depuis la page µprojet et la fiche), `/microprojets/{slug}/refs` (302 vers `/evolution`) |
| references | `/references` (la liste des références de toute l'application ; entrée « Références » de la barre du haut), `/references/{slug}` (l'évolution d'une référence, `?version=1.1` : la version choisie) |
| promotion | `/promotion` (nouvelle : promouvoir une structure comme référence, `?microprojet=&etude=&version=&variante=&reference=&retour=` ; entrée « Promouvoir une réf. » de la barre du haut ; `?brique=<id>&retour=` : promouvoir une brique comme brique de référence, `promotion-brick.js`) |
| comparator | `/comparateur` (nouvelle : `?item=` répété, `&base=n` ; bouton à icône de la barre du haut, à côté de la session) |
| structures | `/microprojets/{slug}/structures/nouvelle`, `/structures/image`, `/structures/sans-structure`, `/experiences/{experiment_id}/evoluer`, `/experiences/{experiment_id}/evoluer-image`, `/experiences/{experiment_id}/evoluer-sans-structure` (`?version=` : partir d'une version passée, sur une nouvelle piste), `/structures/bibliotheque/nouvelle`, `/structures/bibliotheque/{structure_id}`, `/briques-technologiques/bibliotheque/nouvelle`, `/briques-technologiques/bibliotheque/{brick_id}` |
| process_library | `/bibliotheque`, `/microprojets/{slug}/presets-etapes`, `/microprojets/{slug}/briques-technologiques`, `/briques` (les briques de référence ; entrée « Briques de réf. » du menu Structure), `/briques/{brick_id}` (la fiche d'une brique : versions, où elle sert) |
| intent_forms | `/microprojets/{slug}/formulaire-intention` |
| wafers | `/plaques` (l'index : toutes les plaques connues et leur recherche ; entrée « Plaques » du menu Data), `/plaques/{lasermark}` |
| lots | `/lots`, `/lots/{code}` |
| prism | `/prism` (302 vers sa première section), `/prism/donnees`, `/prism/donnees/{key}` (`?wafers=` : requête lancée sur ces plaques) ; `/donnees` et `/donnees/{key}` y renvoient (302) |
| settings | `/parametres` (302 vers sa première section), `/parametres/plugins`, `/parametres/base-de-donnees` |
| usage | `/parametres/utilisation` (une section des Paramètres) |
| docs | `/docs`, `/docs/guide`, `/docs/exemples`, `/docs/architecture` |

Supprimée : `/microprojets/{slug}/graphe`.

## 6. Front

- Scripts classiques (`<script src>`), sans bundler ni framework. Un `client.js`, un registre ou
  un module partagé récent n'expose qu'un global nommé d'après son plugin (`lotsApi`,
  `ExperiencePage`, `DataViz`, `EvolutionGraph`, `ReferencePublishDialog`, `ReferenceStartPicker`, `Comparator`…) ; ses autres déclarations restent locales, dans une IIFE ou un
  objet. **Écarts, tels qu'ils sont** (les regrouper sous un objet par plugin est un chantier à
  part) :
  - les **contrôleurs de page** (un par page : `lots.js`, `area.js`, `atlas.js`…) et le
    **constructeur** (`structures/static/builder/*.js`, une seule page découpée en fichiers qui
    partagent `state`, `slug`, `showError`) déclarent au premier niveau : ces noms ne sortent pas
    de leur page ;
  - le noyau expose ses helpers sans préfixe : `api`, `apiErrorMessage` (`api.js`), `escapeHtml`,
    `initials`, `formatDate`, `timeAgo`, `formatDuration`, `elapsedLabel`, `routeParams` (`ui.js`),
    `timeline*` (`timeline.js`), `ImageAnnotations` (`annotations.js`) ;
  - des **bibliothèques de widgets** partagées entre plugins exposent plusieurs fonctions de
    premier niveau : `wafers/fdl.js` (`normalizeFdl`, `fdlChipsHtml`, `fdlsOfTracking`,
    `mountFdlField`, `plateUrl`, `waferKey`, `waferSuggestions`), `experiments/lineage-graph.js`
    (`lineage*`), `experiments/lineage-view.js` (`mountLineage`), `experiments/status.js`
    (`statusBadgeHtml`, `experimentOutcome`, libellés), `microprojects/roles.js` (`roleLabel(role, source?)`, qui
    affiche « Propriétaire (manager) » ou « Propriétaire (admin) » selon `role_source`,
    `ownerChipHtml`), `attachments/image-drop.js` (`mountImageDrop`, contrôles d'images),
    `structures/structure-images.js`, `structures/campaign-carousel.js`,
    `characterization/wafer-data-links.js`, `intent_forms/intent-form-section.js`,
    `areas/totals.js` (`experimentTotals`), `areas/area-art.js`, `lots/lots-gantt.js`,
    `lots/lot-picker.js` (`mountLotAssign`), `notebook/stepper.js` (`mountStepper`, le stepper du
    procédé), `library/library-files.js`, `accounts/session.js`. Une
    page qui en utilise une la charge elle-même ; un nom nouveau ne doit pas en recouvrir un de
    cette liste ;
- Ordre de chargement d'une page :
  1. noyau : `/static/kernel/api.js`, `ui.js`, `shell.js` ;
  2. session et recherche : `/static/accounts/session.js`, `/static/search/client.js`,
     `/static/search/topbar-search.js` ;
  3. les `client.js` des plugins utilisés ;
  4. le contrôleur de la page.
- Un module réutilisé par plusieurs pages reçoit son contexte en paramètre
  (`mount(el, {microprojectSlug, canEdit, onChange})`) et ne lit jamais une globale de la page
  hôte.
- Les paramètres de chemin d'une page se lisent avec `routeParams("/microprojets/{slug}/...")`
  (dans `ui.js`), jamais par position dans `location.pathname`.
- CSS : `kernel.css` (tokens et composants de la charte, voir `design-system/spectre/MASTER.md`),
  plus `/static/<plugin>/<plugin>.css` chargé par les pages qui en affichent les composants.

### La fiche d'une expérience

- `experiments/static/page.js` (global `ExperiencePage`) amorce la fiche : il charge l'étude (la
  pointe, ou `?version=`), le µprojet, la frise (`versions`) et le procédé, puis monte chaque panneau
  enregistré par `ExperiencePage.registerPanel({key, mount(el, ctx)})` dans l'élément
  `[data-panel="<key>"]` de la page, dans l'ordre de chargement des scripts (un panneau sans élément
  est ignoré). Les modules de la fiche sont eux-mêmes des panneaux, un fichier chacun, sans global :
  `header.js` (bandeau, verdict, statut et pause), `objectives.js` (objectifs, réponses au
  formulaire d'intention), `tags-refs.js`, `structure-view.js` (structure, couches, feuille de split - une
  ligne par plaque -, étapes du procédé, images de la structure ; le bouton « Étiquettes : masquer / afficher » des
  étiquettes de couches, préférence de ce navigateur, affichées par défaut : il passe chaque
  `svg.sp-labelled-structure` à sa `data-bare-viewbox` ; sur un split, le carrousel
  `structures/static/campaign-carousel.js` porte « Corriger cette variante » - le constructeur sur
  `…/evoluer?variante=n`, écran structure seul, « Enregistrer la correction » → `PUT …/variant-overrides/{n}` -,
  marque une variante « retouchée » et propose « Revenir à la variante calculée » ; « Modifier la
  structure » sur un split rouvre le constructeur avec le procédé de base et le plan reconstitué
  (`campaign_plan` → `state.variationFactors`, case « Réf. », plaques à leur place), qui s'enregistre
  depuis l'écran 3 sur la même piste), `plates.js` (plaques suivies), `conclusion.js`,
  `advanced.js` (la boîte « Combiner deux études » : l'autre étude, cherchée parmi celles du
  µprojet, le titre proposé « A + B », l'intention, l'hypothèse et la nouvelle plaque - lasermark,
  emplacement, FDL, comme au lancement -, puis la fiche de la nouvelle étude ; suppression), `report.js`. Ceux des autres plugins suivent :
  `lots/static/lot-picker.js`, `notebook/static/notebook.js`.
- **Les annotations d'une image** : un seul composant, `kernel/static/annotations.js` (global
  `ImageAnnotations`), dans le noyau parce qu'il ne connaît aucun plugin ni aucune pièce jointe - il
  reçoit une `<img>` et des formes, et rend la liste à enregistrer. Lecture seule sans rien monter :
  une `<img>` marquée `ImageAnnotations.attr(annotations)` voit ses annotations dessinées à son
  chargement (vignettes du graphe et de l'atlas, planche du constructeur `image-drop.js`, aperçus de
  la boîte du cahier). `ImageAnnotations.mount(host, {img, annotations, editable, onSave, name})` :
  les annotations numérotées, leur liste (les libellés) et, pour un éditeur, les outils (flèche,
  cadre au cliquer-glisser, libellé modifiable, retrait, « Enregistrer » / « Annuler ») - le cahier
  (`notebook.js`, chaque image d'une mesure) et la planche d'une structure en images
  (`structure-view.js`, `PUT .../structure-images`) s'en servent. Le dessin est un SVG posé sur
  l'image, au repère aux proportions de l'image (`preserveAspectRatio` « meet » : il épouse aussi une
  image en `object-fit: contain`) ; l'image s'enveloppe dans `.annot-frame` (`kernel.css`), ou l'hôte
  pose le dessin par une règle (`.img-tile__frame > .annot-layer`). Le rapport garde dessin et
  libellés (les outils et les champs portent `data-report-hide`).
- `ctx` est un objet explicite, le même d'un rechargement à l'autre : `microprojectSlug`,
  `experimentId`, `versionId`, `isTip` (la pointe, ouverte sans `?version=`), `role`, `canEdit`
  (éditeur sur la pointe), `detail`, `reload()`, `showError(err, box?)` ; s'y ajoutent, pour ne pas
  recharger chacun la même chose, `microproject`, `versions`, `process`, `variants()` (la matrice
  d'une campagne, un appel par chargement) et `write(call, box?)`. Aucun module ne lit de globale
  de la page.
- **Le cahier vu par la fiche.** notebook dépend d'experiments, pas l'inverse : la fiche ne lit pas
  le cahier. Son panneau (`notebook.js`) le lit (`notebookApi.entries`, et `notebookApi.stepCounts`,
  `?summary=steps`) et le déclare par `ctx.setNotebook({entries: [{id, title, kind, objective,
  applies}], stepCounts})` - `ctx.notebook`, `null` à chaque chargement jusque-là. Les panneaux de la
  fiche qui s'en servent s'abonnent au chargement de leur script, par
  `ExperiencePage.onNotebook(fn)` : la vue du procédé (`structure-view.js`) en fait un badge par
  étape, la conclusion (`conclusion.js`) la liste des entrées qu'un verdict peut citer
  (`evidence_ids`) et leurs titres. Un clic sur un badge appelle `ctx.filterNotebook(stepId)`, qui
  ouvre l'onglet « Données » et prévient le cahier (`ExperiencePage.onNotebookFilter(fn)`) : il masque
  les entrées sans mesure à cette étape, à l'écran seulement.
- **Le cahier, côté page** (`notebook/static/`) : `notebook.js` (le panneau : chaque entrée avec son
  stepper statique et ses mesures côte à côte, les entrées d'autres plaques repliées, les
  annotations de chaque image, téléversée ou externe (`ImageAnnotations`), les images externes d'une mesure - leur chemin affiché, et ce qui empêche
  de montrer une image -, le filtre), `entry-dialog.js` (global `NotebookEntryDialog`, la boîte
  d'ajout et d'édition, sur un seul écran : titre et type (saisie libre ou PRISM), la donnée - en
  saisie libre une description (le `text` de la mesure), un dossier d'images (son chemin, ses images
  dans un carrousel - `externalImagesApi.browse` et l'`url` d'aperçu de chaque image -, celles qu'on
  épingle deviennent les `external_images` de la mesure, légendées, réordonnées, et le dossier son
  `image_folder`, rouvert à la modification ; sans racines, une image par son chemin), images par
  `mountImageDrop` avec `purpose: "notebook"`, tableau collé en TSV, fichiers, liens ; la valeur
  chiffrée n'a plus de champ, sauf sur une mesure d'avant qui en a une -, le commentaire (`note`,
  et l'`interpretation` d'une entrée d'avant tant qu'elle en a une), puis « Options » replié
  (ouvert pour PRISM, résumé sur son titre) : plaques, stepper à cocher - une mesure par bulle -,
  objectif, rapport) et `stepper.js`
  (`mountStepper(el, {steps, measured, retired, selectable, onChange})`). Le rapport les reprend
  tels qu'affichés : `data-report-show` y montre ce que l'écran masque ou replie (entrées hors du
  filtre, « Autres plaques »).
- `mount` est rappelé, sur le même élément, à chaque `ctx.reload()` : il remplit l'élément de
  nouveau ; ce qu'un module branche une fois pour toutes (modales, champs fixes de la page), il le
  branche au chargement de son script.
- Écritures : `ctx.write(call)` envoie `ctx.versionId` en `If-Match` (chaque fonction d'écriture
  des clients reçoit la version affichée) ; réussie, la fiche se relit sur place (même adresse,
  dernière version, onglet gardé) ; un `412` ferme les modales et affiche le bandeau « La fiche a été
  modifiée entre-temps » avec « Recharger », la saisie restant en place ; un autre refus s'affiche
  tel quel (le `409 has_descendants` d'une suppression, par exemple : le client ne recalcule pas les
  préconditions du serveur).
- Une version passée (`?version=` d'une version qui n'est pas la pointe) se lit seule : aucun
  contrôle d'édition, un bandeau « Version du … - voir la version actuelle » et, pour un éditeur,
  « Partir de cette version », qui ouvre l'éditeur sur `?version=` : il enregistre une nouvelle piste
  (`POST /experiments` avec `from_version`). Un `?version=` qui désigne la pointe (lien d'une ref,
  par exemple) ouvre la fiche actuelle et le paramètre est retiré de l'adresse (`replaceState`) ;
  les liens construits par la fiche l'omettent déjà grâce à `is_tip` (frise, `children`).
- **Les étiquettes de couches, côté pages.** Le constructeur (`structures/static/builder/layer-label.js`)
  ajoute à l'inspecteur d'une étape qui crée une couche (dépôt, croissances, lithographie) la section
  « Afficher sur la structure » : la case, le texte (prérempli du matériau, l'épaisseur cochée), les
  valeurs possibles (épaisseur, composition d'un nitrure à composition, paramètres déclarés de
  l'étape) ; l'étiquette vit sur l'étape (`step.layerLabel`), part par position
  (`layerLabelsPayload`) et revient au chargement (`attachLayerLabels`) - procédé d'une étude,
  structure enregistrée, brique (insérée ou éditée). L'aperçu est le SVG du serveur ; le lien
  couche ↔ étape du dessin (sélection, survol) lit lui aussi le `step_index` du serveur. La page
  d'évolution montre, dans son panneau, la structure de la version choisie (agrandie dans une boîte
  au clic) ; pour une structure en images, sa première image avec ses annotations
  (`structureBoardHtml` compact, en lecture seule ; un clic l'ouvre). Les vignettes de l'écran « Variations » restent sans étiquettes (trop petites).
  Une étiquette se place à la main : glisser son texte dans l'aperçu (`layer-label.js`, le trait
  redessiné en direct à partir de `data-anchor`/`data-elbow`/`data-width` du `<g class="sp-layer-label"
  data-step>`) écrit `layerLabel.offset` (`[dx, dy]`, unités du dessin, depuis la place automatique ;
  celle d'une brique sur sa première étape étiquetée) ; double-clic ou « Remettre à sa place » l'efface.
  Côté serveur, `LayerLabel.offset` (borné à ±`MAX_LABEL_OFFSET`, absent de l'enregistrement quand il
  est nul) est appliqué par `rendering.labelled_svg` après l'empilement automatique, le cadre
  (`viewBox`, qui peut alors commencer en négatif) agrandi pour le contenir ; le versionnage et les
  différences d'étiquettes l'ignorent (un déplacement seul : version `none`), et un préset d'étape ne
  le garde pas (`presetContentOf`).
  Son point d'accroche aussi : le glisser (le groupe `.sp-layer-anchor` - le rond, ou le tiret et le
  losange d'une marque d'interface -, attrapé par un cercle invisible `.sp-layer-anchor__hit`,
  `pointer-events="none"` dans le SVG et rallumé par `structures.css` dans le seul constructeur, de
  rayon constant à l'écran : `r` divisé par `--sb-zoom`, que `applyZoom` écrit) écrit
  `layerLabel.anchor` (`[fx, fy]`, fractions de `data-anchor-box`, le cadre de ce qu'il désigne : les
  couches de l'étape, celles d'avant elle pour une marque d'interface). Un point visible l'emporte
  sur la zone d'un autre (`labelAnchorAt`, par `elementsFromPoint` : dans un empilement de couches
  fines, la zone d'une étiquette plus bas couvre les points d'au-dessus), sinon le plus proche ; un
  clic sans déplacement sur le point sélectionne l'étape, à côté (dans la zone seule) c'est un clic sur
  la couche dessous (`clickLayer`, simulation.js) ; un double-clic sur le point l'efface. Côté
  serveur, `LayerLabel.anchor` (dans [0, 1]) se lit dans le cadre de ce qu'il désigne **sur la
  structure finale**, quelle que soit l'image (`frames_payload` le passe à chaque image :
  `LayerAnnotation.anchor_bounds`) - posé sur l'image d'une étape, il tombe au même endroit sur la
  structure finale, celle qu'enregistre une étude ; avant un retournement, il n'est ni suivi ni
  déplaçable (`labelled_svg(anchors=False)`, pas de `data-anchor-box`). Puis il est posé par
  `rendering._placed_anchor` (gardé s'il est sur la couche, sinon le point d'elle le plus proche,
  rentré du rayon du point là seulement où elle est assez épaisse - jamais vers une partie épaisse
  lointaine) ou `_placed_interface_anchor` (le point le plus proche de la surface, sans ce qui longe
  les côtés et le fond du dessin entier - pas le fond des couches d'avant : après un retournement,
  l'interface est dessous) ; les textes s'empilent toujours d'après le point automatique (poser le
  point ne déplace aucun texte), `data-anchor-placed` le signale. Une accolade de brique n'en a pas.
  `simulation.LABEL_PLACE_KEYS` (`offset`, `anchor`) et `label_without_place` : ce que versionnage,
  différences d'étiquettes et signatures d'étapes d'une combinaison au marché (`composition.py`) ne
  comptent pas.
- **Les références, côté pages** (plugin references, TODO « Références de structure ») :
  - `experiments/static/evolution-graph.js` (global `EvolutionGraph`) : le diagramme façon git -
    colonnes, rangées, arêtes, formes des nœuds par niveau de changement, légende, liste des
    rangées au clavier (`bindListbox`) ; la comparaison de deux versions est le tableau du
    comparateur (`Comparator`, § comparator), sous le diagramme des deux pages. Il ne connaît ni
    les pistes ni les références : la page d'évolution d'un µprojet (`evolution.js`, versions
    Follow) et la page d'une référence (`references/static/reference.js`, versions 1.0, 1.1, 2.0 :
    colonnes de branches, rattachements déduits en pointillés, `evo-edge--inferred`) lui donnent
    leurs nœuds rangés et écrivent leurs rangées et leur panneau. Il reste dans experiments, d'où
    il vient et que references charge déjà (le navigateur compose).
  - `promotion/static/link.js` (global `PromotionLink`) : le bouton « Promouvoir comme référence »,
    le même partout (fiche, variante d'un split, conclusion, page d'évolution, liste et page d'une
    référence), un lien vers le formulaire `/promotion` déjà rempli (§ promotion). Il a remplacé la
    boîte « Publier comme référence » (`references/static/publish-dialog.js`, retirée le
    2026-10-11), que la fiche ne montrait que sur une structure dessinée - jamais sur un split.
  - `references/static/start-picker.js` (global `ReferenceStartPicker`) : « Partir d'une
    référence », le premier choix de « Nouvelle expérience » (page µprojet, accueil ; et la page
    d'un µprojet ouverte avec `?premiere-experience=1`, ce que font les pages d'un projet et d'une
    thématique après sa création) et de « Partir de cette version » (page d'une référence) : la
    recherche (`?q=` du serveur), la dernière version proposée, une autre au choix, l'aperçu
    (`structure_svg`), le µprojet où lancer (éditeur) s'il n'est pas donné ; « Partir d'une structure
    vierge » en lien secondaire (sur la page µprojet : l'ancienne boîte - dessin, image,
    bibliothèque, étude existante). Il ouvre le constructeur sur
    `/microprojets/{slug}/structures/nouvelle?reference=<slug>&version=<n>`, qui charge `process`
    de la version **en gardant les ids d'étape** (l'étude descend de cette version : une version
    publiée ensuite s'y compare étape par étape) et envoie `reference_origin` au lancement - la
    version qu'il a bien chargée seulement (`referenceOrigin`, posé au chargement réussi ; une
    référence retirée ou inconnue n'en laisse aucune). Avec `onWafers` (la page µprojet), un second
    lien « Partir de plaques existantes ».
  - `wafers/static/start-picker.js` (global `WaferStartPicker`) : « Partir de plaques existantes »,
    ouvert depuis la boîte précédente et depuis la boîte « sans référence » de la page µprojet. Les
    plaques du µprojet, ou cherchées par lasermark ou FDL dans tous les µprojets, se cochent ; leurs
    passeports (`GET /api/wafers/{key}`) donnent les études qui les suivent toutes (dans un µprojet
    dont on est membre ; une campagne seulement si elles y portent la même variante), la plus
    récemment rejointe d'abord (`tracked_since`), une autre au choix ; sinon la boîte dit pourquoi
    (structures différentes, variantes différentes, plaque illisible hors membre) et ne lance rien
    - le serveur décide de toute façon. Il ouvre le constructeur sur
    `/microprojets/{slug}/structures/nouvelle?plaque=…&depuis-mp=…&depuis-etude=…&depuis-version=…`,
    qui charge le procédé de l'étude (celui de la variante, `?variant=`) en gardant les ids d'étape,
    met les plaques dans le tableau de l'écran « Variations » (lasermarks fixés, emplacement et FDL
    repris et modifiables) et envoie `wafer_origin` - l'étude qu'il a bien chargée seulement
    (`waferOrigin`). Une structure en images part du substrat. Sans variation, le tableau a une ligne
    par plaque (des réplicats, « + Ajouter une plaque » hors départ de plaques) ; avec un plan, une
    par variante, et des plaques reprises en trop bloquent le lancement. La fiche dit « Plaques
    reprises de X » (`tags-refs.js`, titre lu chez l'étude d'origine, le µprojet s'il est autre) ;
    sa carte « Plaques » ajoute des réplicats à une étude simple. Une évolution d'une piste à
    plusieurs plaques (constructeur, page en images) les garde toutes : le champ unique s'efface
    devant leur liste.
  - La fiche affiche « Issue de la référence X 1.1 » (lien vers sa page ; « référence inconnue »
    si `GET .../versions` répond 404 ou n'a pas ce numéro). La page d'évolution d'un µprojet lit
    `GET /api/reference-versions` puis `structure-history` avec ces versions en `include_versions`
    (badges « R nom 1.1 », anneau or) ; les refs locales n'y sont plus (2026-10-11).
  - `/bibliotheque` a une carte « Références de structure » qui renvoie vers `/references`.
- Le vocabulaire d'une étude (types d'étape et leurs paramètres, décisions, résultats d'un objectif)
  est dans `experiments/static/vocabulary.js` (global `ExperimentVocabulary`), chargé par la fiche
  et l'atlas.
- Écarts : `lot-picker.js` sert aussi au graphe de filiation, où `ExperiencePage` n'existe pas ; il
  ne s'enregistre donc que `if (typeof ExperiencePage !== "undefined")`. Le cahier, seul panneau de
  l'onglet « Données », lit sa propre sous-ressource, pour la version affichée (`?version=`) ; le
  repère de l'onglet est `detail.notebook_count`.

## 7. Tests

| Dossier | Contenu |
|---|---|
| `tests/plugins/<plugin>/` | tests HTTP du plugin |
| `tests/support/<plugin>.py` | helpers et fabriques ; chaque helper encapsule une route |
| `tests/contracts/` | appels front ↔ routes, 401 anonyme sur toute route non publique |
| `tests/kernel/` | noyau, migrations |
| `tests/integration/` | parcours qui traversent plusieurs plugins |

`conftest.py` isole `SPECTRE_DATA_DIR`, `PRISM_DATA_DIR`, `SPECTRE_LIBRARY_DIR`, le SMTP et le mode
démo. L'application des contrats (`tests/contracts/conftest.py`) active les plugins optionnels
(`SPECTRE_DEMO_DATA=1`) pour vérifier aussi leurs routes, leurs fichiers et leur 401.
