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
   `experiments.lineage`, `experiments.entities`, `experiments.insights`, `structures.kinds`,
   `structures.campaigns`, `structures.simulation` et `structures.rendering`. La liste est tenue par
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
| `plugin.py` | `Plugin`, `Page`, `NavEntry`, `Migration` (dataclasses figées ; `Migration.files` : les fichiers hors base qu'une migration réécrit ou supprime), et `check_dependencies(plugins)`, qui vérifie l'ordre topologique au démarrage |
| `app.py` | `create_app(plugins=PLUGINS)` : migrations, `include_router` de chaque plugin, routes de pages, montage de `/static/<plugin>/` et `/static/kernel/`, exception handlers, middleware `Cache-Control: no-cache` |
| `db.py` | `data_dir()`, `connect()`, `get_conn()`, exécuteur de migrations versionnées (table `schema_migrations(plugin, migration_id, applied_at)`), `rebuild_table()` pour les changements non additifs (CHECK, NOT NULL), qui garde le compteur d'`AUTOINCREMENT` de la table (un id supprimé n'est jamais redonné). Avant la première migration en attente d'une installation existante, la base (API de sauvegarde de sqlite3) et les fichiers déclarés par les migrations (`Migration.files`, copiés juste avant chacune) sont sauvegardés dans `data_dir/backups/<horodatage>/` : une migration peut supprimer ou réécrire ce que l'ancien code lit, et l'ancien code ne lit pas une base migrée - revenir en arrière, c'est restaurer cette copie |
| `errors.py` | `DomainError` → `Unauthorized` (401, `unauthorized` : pas de session, levée par `accounts.deps.current_user`), `NotFound` (404), `Forbidden` (403), `Conflict` (409), `PreconditionFailed` (412), `InvalidInput` (422), `UpstreamError` (502), `Unavailable` (503) ; un handler unique renvoie `{"detail": str, "code": str}`. Un plugin peut sous-classer `DomainError` pour un statut qui lui est propre (`attachments.store.TooLarge` : 413, `too_large`), le même handler s'en charge |
| `locks.py` | `keyed_lock(namespace, key)` : un `threading.Lock` par clé (le serveur tourne en un seul processus) |
| `fs.py` | `replace(src, dst)` : le `os.replace` de toute écriture atomique (fichier temporaire du même dossier, puis remplacement), réessayé quelques fois, à intervalles croissants, sur `PermissionError` - sous Windows, un antivirus ou un lecteur tient la cible un instant (de même pour le dossier de bibliothèque assemblé puis renommé, `library.service`) ; `write_text(path, text)` : l'écriture atomique complète (temporaire unique, `fsync`, `replace`), celle des dépôts Follow (`experiments.repository`) |
| `annotations.py` | La forme des annotations d'une image, la même pour toute image que Spectre montre : `ImageAnnotation` (`{type: "arrow" \| "box", x, y, x2, y2, label}`, en % de l'image, champs en plus refusés) et `clean_annotations(raw, limit=100)` (positions dans l'image : des nombres finis entre 0 et 100 ; libellé de 200 caractères au plus ; 422 `invalid_annotation`). Le noyau ne sait pas à quelle image une annotation appartient : le cahier la range dans la mesure par une clé d'image, une structure en images sur l'image elle-même. Au noyau plutôt qu'à `attachments` : une image externe n'est pas une pièce jointe, et `notebook` et `structures` s'en servent tous deux |
| `json_store.py` | Collections JSON `{"items": [...]}` d'éléments à `id`, lues et écrites sous un verrou par chemin, de façon atomique ; un élément illisible est écarté à la lecture et gardé tel quel à l'écriture (`ItemStore`, `read_json`, `write_json`, `path_lock`) - les bibliothèques de `process_library` |
| `mail.py` | `send_email(to, subject, body)` : SMTP si `SPECTRE_SMTP_HOST`, sinon journalisation **sans le corps** hors `SPECTRE_EMAIL_DEBUG=1` |
| `pages.py` | Service des pages HTML d'un plugin, avec la barre du haut commune à la place du marqueur `<!-- spectre:topbar -->` (fil d'Ariane déclaré dans le marqueur : `crumb-id`, `crumb-text`) : marque, navigation construite à partir des `NavEntry` des plugins actifs, relue à chaque requête (une entrée peut être réservée à certaines pages : `NavEntry.pages`, ou aux administrateurs : `NavEntry.admin`, rendue cachée et révélée par `accounts/static/session.js` ; une entrée à icône, `NavEntry.icon`, devient un bouton à côté de la session : la roue crantée des Paramètres), place de la session. Retire d'une page les `<script>` et `<link>` des statiques des plugins éteints et les nomme sur `<html data-plugins-off="...">` ; la page d'un plugin éteint est un 404 « Module désactivé » |
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
```

Le `page_router` d'un plugin est inclus **avant** ses pages : une redirection peut viser un gabarit
plus étroit qu'une page du même plugin. Deux cas, tous deux dans `experiments` : un ancien id de
version sous la page d'une étude (`/microprojets/{slug}/experiences/{version_id:experiment_version}`,
convertisseur d'URL Starlette `exp_<16 hex>` déclaré par `experiments.api`, forme qu'aucun nom de
piste ne peut prendre), et l'ancienne page des refs (`/microprojets/{slug}/refs`, 302 vers
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
| 3 | `teams` | Équipes et leurs membres (`manager` ou `member`), page Équipes. Fournit `service.managed_team_ids(user_id)`. Ce qu'une équipe possède est dit par `areas` | accounts | `teams`, `team_members` |
| 4 | `search` | `GET /api/search`, qui agrège les fournisseurs déclarés par les autres plugins (`register_provider`) | accounts | — |
| 5 | `library` | Bibliothèque racine YAML de l'instance (matériaux, recettes, présets, briques, textes d'UI), chargeur générique avec cache mtime, registre `LibraryFile` alimenté par les plugins propriétaires, édition réservée à l'admin | accounts | `data_dir/library/*.yml` (copiés depuis `library/defaults/` au premier démarrage, et les `*.yml` d'un `<dépôt>/library` d'avant par-dessus) |
| 6 | `areas` | Projets corporate (*management areas*), leur équipe, thématiques, objectifs. Pages accueil, projet et thématique. Fournit `service.can_manage(user, area)`, `managed_area_ids(user)` et `can_place_microproject(user, area)` | accounts, teams | `management_areas` (dont `team_id`, `ON DELETE SET NULL`), `thematics`, `area_objectives` |
| 7 | `microprojects` | µprojets (CRUD, numéro, rattachement à un projet ou une thématique, recherche), membres, rôles, invitations. Fournit la règle d'accès (`service.access`, `effective_role`, `check_role`) et `deps.require_role` | accounts, areas, search | `microprojects`, `memberships`, `invitations` |
| 8 | `attachments` | Fichiers téléversés d'un µprojet (blob + sidecar), types, tailles, service des octets | microprojects | `data/microprojects/<slug>/attachments/` |
| 9 | `structures` | Pont StructureForge : matériaux, recettes, simulation, aperçu de campagne DOE, rendu SVG, **types de structure** (`process`, `campaign`, `images`) exposés par `kinds.py`. Pages du constructeur | accounts, library, attachments | — |
| 10 | `process_library` | Structures enregistrées, présets d'étape, briques technologiques (portées `builtin` / `shared` / `microproject`). Pages bibliothèque, présets, briques | structures, microprojects, library | JSON par portée |
| 11 | `experiments` | Pistes d'étude et versions (dépôt Follow d'un µprojet) : création, évolution, statut, conclusion, étiquettes, entités physiques, combinaison de deux études (une nouvelle piste à deux parents), suppression, diff, filiation, refs, statistiques et frise transverses. Seul point d'écriture vers Follow (`service.amend`) | microprojects, structures, attachments | `data/microprojects/<slug>/follow/` (dont `retired_lines.json`, les noms des pistes supprimées) |
| 12 | `references` | Références de structure de toute l'application : versions `MAJEUR.MINEUR` publiées depuis les études des µprojets (numéro calculé, instantané de la structure), leur évolution, leurs usages (les études parties d'une version, lues dans `reference_origin`), le regroupement des refs locales d'avant dont le nom est porté dans au moins deux µprojets (`local_refs.py`) | experiments, microprojects, structures | `structure_references`, `reference_versions`, `reference_import_scans`, `reference_import_rules`, `retired_reference_slugs`, `dismissed_local_refs` |
| 13 | `intent_forms` | Formulaires d'intention (portées) et formulaire actif d'un µprojet | experiments, microprojects | JSON + `follow/commit_form.yml` |
| 14 | `wafers` | Index des plaques suivies, clé `wafer_key`, passeport d'une plaque, recherche par lasermark et par FDL, politique de visibilité, plaques de chaque FDL (`fdl_source` : démo, base locale, PRISM à venir) | experiments, search | cache mémoire, `fdl_wafers` |
| 15 | `lots` | Lots de fabrication, leurs wafers et leurs thématiques visées, Gantt ; ce qu'une lecture compose (expériences, thématiques, retard) dans `views.py` | wafers, areas, experiments, search | `lots`, `lot_wafers`, `lot_thematics` |
| 16 | `links` | Liens entre µprojets et entre entités physiques | microprojects, experiments | `microproject_links`, `entity_links` ; mis de côté par les migrations, plus lus : `entity_links_unresolved`, `microproject_links_duplicates` |
| 17 | `atlas` | Vue graphe d'un projet corporate | areas, microprojects, experiments, links | — |
| 18 | `characterization` | Types de données de caractérisation (PRISM, ou démo via le Protocol `DataSource`) : catalogue, requêtes, graphiques documentaires. Seul module qui importe `prism` | accounts | cache PRISM sous `data_dir/prism` (`PRISM_DATA_DIR`, fixé par `service.current_source()` s'il ne l'est pas) |
| 19 | `external_images` | Politique des images externes référencées (TEM, scans) : racines autorisées, formats affichables, lecture bornée ; parcours des dossiers autorisés | microprojects | — |
| 20 | `notebook` | Cahier de données d'une étude, le seul : entrées PRISM (instantanés et vues DataViz) et manuelles (valeurs, textes, tableaux, fichiers, images externes, liens), rattachées aux plaques et aux étapes ; sert les images externes d'une entrée par identifiant ; lit les vues, les preuves et les jeux d'images d'avant (`legacy.py`) | characterization, experiments, attachments, external_images | `snapshots/`, métadonnées Follow (`notebook_entries`) |
| 21 | `kpis` | Registre de KPI (`register`) et séries mensuelles d'un projet corporate | areas, experiments | — |
| 22 | `kpis_demo` | Séries et fiche d'étude fictives. **Actif seulement si `SPECTRE_DEMO_DATA=1`** | kpis, structures | — |
| 23 | `docs` | Pages de documentation (contenu inchangé) | — | — |

### Activer et désactiver un plugin

Un administrateur active ou désactive un plugin depuis **Paramètres > Plugins** (`/parametres/plugins`,
plugin `settings`), **à chaud** : rien à redémarrer. La règle est au noyau (`kernel.plugin_states`) :

- **Noyau** : les plugins `required` - `accounts`, `settings`, `microprojects`, `experiments`,
  `wafers`, `process_library` - et tout plugin dont l'un d'eux dépend (`teams`, `search`, `library`,
  `areas`, `attachments`, `structures`) ne se désactivent pas (409 `plugin_required`). `wafers` et
  `process_library` en sont parce que le constructeur et la fiche d'étude s'en servent partout
  (champ FDL, liens de plaque, structures enregistrées, présets).
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
  concerne : bloc KPI d'un projet (`kpis`), lien Atlas (`atlas`), départ depuis une référence,
  « Publier comme référence » et versions publiées (`references`), badges et affectation de lots
  (`lots`), « Données en base » (`characterization`), onglet Données et citations de la conclusion
  (`notebook`), formulaire d'intention du constructeur (`intent_forms`). Côté serveur, sans
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

- **admin** (`users.is_admin`) : tout. Il est `owner` de tout µprojet, même sans en être membre ;
- **manager d'une équipe** (`team_members.role = manager`) : gère les projets corporate rattachés à
  son équipe (`management_areas.team_id`), leurs thématiques et leurs objectifs, peut créer un
  projet dans l'une de ses équipes, et il est `owner` des µprojets de ces projets (un µprojet hérite
  de l'équipe de son projet ; « Non classé » n'a pas d'équipe) ;
- **membre** : le rôle de son adhésion au µprojet (`viewer` < `editor` < `owner`).

Un compte peut appartenir à plusieurs équipes et n'être manager que dans certaines.

Côté projet, `areas.service.can_manage(user, area)` (admin, ou manager de l'équipe du projet) est
la règle de toute écriture d'un projet, d'une thématique ou d'un objectif. Rattacher un projet à
une équipe reste à l'admin (renvoyer l'équipe déjà en place est sans effet), comme rattacher un
µprojet existant depuis la page d'un projet (il s'appuie sur `?scope=all`). **Placer un µprojet**
dans un projet - le créer (`POST /api/microprojects`) ou l'y déplacer (`PATCH
/api/microprojects/{mp}` `{area}`, réservé par ailleurs à l'`owner`) - suit
`areas.service.can_place_microproject(user, area)` : dans le projet d'une équipe, ses membres (tout
rôle, managers compris, donc qui le gère) et un admin ; un projet sans équipe et « Non classé »
restent ouverts à tous. Le refus est un 403 `placement_forbidden`, levé à un seul endroit,
`microprojects.service.check_placement` ; la règle vit dans `areas`, sous `microprojects`, parce
que chaque projet l'expose (`can_place_microproject`) et qu'`areas` ne peut pas importer
`microprojects`. Changer de thématique dans le même projet n'est pas un placement ; sortir un
µprojet du projet d'une équipe reste permis à son `owner`. Les pages projet et thématique
n'offrent « + Nouveau µprojet » que si `can_place_microproject` est vrai, comme « Rattacher un
µprojet existant » (page projet, admin seulement).

Côté µprojet, `microprojects.service.access(user, microproject)` rend
un `Access(role, source, membership)` : `role` est le rôle effectif, `source` dit d'où il vient,
dans cet ordre de priorité : owner par adhésion (`membership`), puis `team_manager`, puis `admin`,
puis le rôle de l'adhésion. `effective_role`, `has_role`, `check_role`, `accesses` (une liste en
deux requêtes) et `deps.require_role` en dérivent ; aucun autre plugin ne lit la table
`memberships` pour autoriser (`role_for` et `list_for_user` restent des lecteurs bruts). « Mes
µprojets » (`list_mine`) : ceux dont on est membre et ceux des équipes qu'on manage, pas tous
ceux qu'un admin peut ouvrir. Hors µprojets, trois contrôles gardent leur propre règle, qui ne
dépend pas d'un rôle : la suppression d'un lot (créateur ou admin) et les éléments partagés de
`process_library` et d'`intent_forms` (auteur ou admin).

À la migration (`teams/0001_initial`, `areas/0003_team`), rien n'est rattaché : les droits d'une
base existante ne changent qu'une fois les équipes créées et les projets rattachés par un admin.

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
| `StructureKind` (Protocol : `key`, `render_svg`, `entity_count` ; `KINDS` indexé par les clés figées). Le corps reçu est lu par l'union `structures.schemas.StructurePayload`, discriminée par `kind` | `structures/kinds.py` | process, campaign, images |
| `DataSource` (Protocol : `list_types`, `describe`, `query`, `chart`), choisie à un seul endroit (`characterization.service.current_source()`, `SPECTRE_DEMO_DATA`) | `characterization/source.py` | PRISM (`prism_source.py`), démo (`demo.py`) |
| `register_provider(SearchProvider)` | `search` | microprojects, wafers (lasermark, FDL), lots |
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
déplacement de classe ne doit jamais la changer.

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
  de page qui porte encore un ancien id de version est résolue par
  `GET /api/microprojects/{microproject_slug}/experiment-versions/{version_id}`.

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
- Les seuls accès aux internes privés de Follow sont dans `repository` : `delete_line(repo,
  experiment_id)` (suppression d'une piste), `rename_tag` et `remove_tag` (renommer ou retirer une
  ref ; Follow n'en offre pas le moyen). Le dépôt est ouvert sur le stockage JSON de Follow
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
  campagne (une évolution, jamais une campagne, retire les deux clés) ; une combinaison reprend celles
  de sa première étude. Le détail rend `reference_place` (`null` hors campagne) et
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
- Le nom d'une ref (`refs.py`) : non vide, sans `/`, ni `.`/`..`, ni la forme d'un id de version
  (`repository.VERSION_ID_RE`, repris par `service.VERSION_ID_RE` ; Follow cherche un nom avant un
  id, une telle ref masquerait la version) - sinon 422 `invalid_ref_name` -, libre parmi les refs et
  les pistes (409 `ref_name_taken`). Une ref est propre au µprojet ; la renommer ou la retirer ne
  touche pas la version.
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
  niveau **correctif** (`patch`), comme renommer une étape, et garde la conclusion (elles ne
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
- **Diff** : `GET .../structure-diff` rend, à part des changements de structure, `label_changes`
  (`kinds.describe_label_changes`) : par étape (`step_id`, `change` : `added`, `removed` ou
  `modified` avec `text {before, after}`, `values_added`, `values_removed` - les noms lisibles :
  « épaisseur », « composition », le nom du paramètre), puis par brique (`group_id`, `change` :
  `grouped`, `ungrouped`, `renamed`, `regrouped`), chacun avec `subject` et `line`, la phrase
  (« p-GaN — ajout : dopage Mg »). Les étapes s'apparient par id (`service.step_ids_of`) quand les
  deux versions en ont en commun (une piste, une fourche), sinon **par position**, comme le diff de
  structure (deux études lancées à part, ou reprises d'un modèle, que le constructeur copie sans
  ids) ; une brique est son nom et ses étapes étiquetées, comme pour le versionnage, jamais son
  `group_id` (dissocier puis regrouper les mêmes étapes ne change rien). Il rend aussi
  `param_changes` (`kinds.describe_param_changes`) : les paramètres déclarés, que la géométrie
  comparée ne porte pas, par étape (appariées de même) et par nom - `change` `added`, `removed` ou
  `modified` (`value`, `unit` `{before, after}` ou `null`, `obtention_changed`), avec `step_id`,
  `subject` (le nom de l'étape), `param` et `line` (« p-GaN — dopage Mg : unité « cm⁻³ » ajoutée ») ;
  une unité passée de l'obtention au champ, la même, n'y est pas. Et `step_changes`
  (`kinds.describe_step_changes`) : les étapes renommées (appariées de même ; un nom d'étape n'est
  ni dans la géométrie ni dans les étiquettes, et c'est un correctif), `{step_id, subject, change:
  "renamed", name: {before, after}, line}` (« étape « n-GaN » renommée « n-GaN dopé » ») - une
  étape ajoutée ou retirée, elle, change la structure. La fiche, sa comparaison, la page
  d'évolution et celle d'une référence les écrivent sur une ligne « Étapes : … », « Paramètres :
  … » puis « Étiquettes : … », et la fiche ne dit plus « identique à la version précédente » quand
  seuls des noms d'étape, des paramètres déclarés ou des étiquettes changent.

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
  étiquetées) - au plus un correctif.
- **Bibliothèques** : une structure enregistrée et une brique les gardent par positions
  (`bricks`) ; une brique insérée dans un procédé y devient un seul groupe (les briques ne
  s'imbriquent pas), de `source` l'id de la brique insérée. Le nom d'une brique de bibliothèque,
  que reprend ce groupe, a la même limite (`POST`, `PATCH /api/tech-bricks`, 422 au-delà ; les
  champs du constructeur ont `maxlength`) ; celui d'une brique enregistrée avant la limite est
  coupé à l'envoi (`bricksPayload`), et le mode brique demande de le raccourcir pour l'enregistrer.

### Unité des paramètres déclarés

Un paramètre déclaré (`simulation.DeclaredParam`) a un champ `unit` facultatif (20 caractères au
plus), que le constructeur propose (« cm⁻³ », « % », « °C », « nm », « sccm », « W », « min »…) et
que l'étiquette écrit ; sans unité, il s'enregistre sans la clé (la forme d'avant). L'ancienne
astuce, `unit=` dans l'obtention, reste lue. Les paramètres déclarés font partie de la structure
(un réglage : niveau mineur), mais **une unité ajoutée ou retirée seule** - ou passée de
l'obtention au champ - ne fait qu'écrire la valeur : niveau **correctif**, conclusion gardée
(`versioning.same_settings`) ; une unité remplacée par une autre change la valeur : niveau
**mineur**.
- **Provenance des couches** : toujours celle du serveur. `simulation.simulate_process` simule une
  étape à la fois (mêmes images, mêmes erreurs que `simulate` de StructureForge, qui ne dit l'étape
  d'une couche que pour une croissance, et sans sa position) et suit les couches de la géométrie :
  une couche garde son objet tant qu'elle existe, une étape ajoute les siennes, un retournement les
  recrée dans l'ordre inverse. `layer_origins[k][j]` : la position de l'étape qui a créé la
  `j`-ième couche de l'image `k` (`-1` : le substrat). Jamais d'alignement de matériaux côté client.
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
| `GET /api/teams` | les équipes ; chacune porte `member_count`, `managers`, `my_role`, `can_edit` (renommer, supprimer : admin) et `can_manage` (gérer les membres) |
| `POST /api/teams` `{name}` (admin) | → 201 + `Location` |
| `GET /api/teams/{team_slug}` | une équipe |
| `PATCH /api/teams/{team_slug}` (admin) | renommer |
| `DELETE /api/teams/{team_slug}` (admin) | → 204 ; ses projets restent, sans équipe |
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
| `GET /api/management` | `GET /api/areas?team=` (équipe inconnue → 404 ; chaque projet expose `is_system`, `team {slug, name}`, `can_manage`, `can_delete` (= `can_manage` et pas système), `can_place_microproject` (y créer ou y déplacer un µprojet, § 3), `horizon_months` calculé par le serveur) |
| `POST /api/management` | `POST /api/areas` `{…, team}` → 201 (admin, avec ou sans équipe, ou manager pour l'une de ses équipes ; équipe inconnue → 422 `unknown_team`) |
| `GET /api/management/{slug}` | `GET /api/areas/{area_slug}` (projet, thématiques, objectifs) |
| `PUT /api/management/{slug}` | `PATCH /api/areas/{area_slug}` (`can_manage` ; `{team}` : admin seulement, sans effet si c'est l'équipe déjà en place, 409 sur « Non classé ») |
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
| `GET /api/microprojets` | `GET /api/microprojects` (les miens : membre, ou manager de l'équipe du µprojet) ; `?scope=all` (admin, sinon 403) ; `?area=&thematic=` (inconnu → 404, `thematic` sans `area` → 422). Le payload d'un µprojet nomme son rattachement `area` / `thematic`, comme le `PATCH`, et ne porte plus de compteurs : le front les lit dans `GET /api/experiment-stats` |
| `GET /api/microprojets/recherche?q=` | `GET /api/microprojects?q=&limit=` (toute la société, champs réduits `{slug, code, name, area}` ; `?q=` et `?code=` ne se combinent avec aucun autre filtre → 422) |
| `GET /api/microprojets/tous` | `GET /api/microprojects?scope=all` |
| `GET /api/microprojets/code/{code}` | `GET /api/microprojects?code=` → `[]` ou un élément, mêmes champs réduits |
| `POST /api/microprojets` | `POST /api/microprojects` `{name, description, area, thematic}` → 201 + `Location` (projet ou thématique inconnus → 422, comme le `PATCH` ; projet d'une équipe dont on n'est ni membre ni admin → 403 `placement_forbidden`, comme le `PATCH` `{area}` ; un nom qui donnerait le slug « new » ou « nouvelle » reçoit un suffixe) |
| `GET /api/microprojets/{slug}` | `GET /api/microprojects/{mp}` ; tout µprojet renvoyé porte `role` (effectif), `role_source` (`membership`, `team_manager` ou `admin`), `can_edit` et `can_manage` (§ 3, règle d'autorisation) |
| *(nouveau)* | `PATCH /api/microprojects/{mp}` `{name, description, area, thematic}` (`owner` ; changer de projet vers celui d'une équipe dont on n'est ni membre ni admin → 403 `placement_forbidden`, § 3 ; renommer ou changer de thématique dans le même projet n'est pas vérifié) |
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
| `…/briques-technologiques[/{name}]` | `/api/tech-bricks[/{brick_id}]` (même schéma) |

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
| `POST …/{ref}/evoluer` | `POST …/experiments/{exp}/versions` `{structure: {kind: "process", …}, …}` + `If-Match` → 201 + `Location` vers la version ; **200 sans `Location`** si rien n'a changé (§ 4) ; une campagne y est refusée (422 `campaign_is_a_new_line`) : elle se lance avec `from_version` |
| `POST …/{ref}/evoluer-image` | idem, avec `structure: {kind: "images", …}` |
| `POST …/{ref}/dessin` | `PUT …/experiments/{exp}/structure-images` (toute la planche, dans l'ordre : `{image_id, kind, caption, annotations}` ; écriture légère, même révision de structure - c'est aussi par elle que se posent les annotations d'une image) |
| `POST …/{ref}/conclure` | `PUT …/experiments/{exp}/conclusion` (le verdict d'un objectif peut citer des entrées du cahier : `evidence_ids`, des ids d'entrées de la pointe, sinon 422 `notebook_entry_not_found`) |
| `POST …/{ref}/statut` | `PUT …/experiments/{exp}/status` `{status, hold_reason}` |
| `POST …/{ref}/etiquettes` | `PUT …/experiments/{exp}/tags` `{tags}` |
| `POST …/{ref}/entites` | `PUT …/experiments/{exp}/entities` `{entities}` (une par variante d'une campagne, 422 `entity_count` sinon ; au moins une pour une étude simple, ses réplicats ; 422 `duplicate_wafer`) |
| `POST …/{ref}/combiner` | `POST /api/microprojects/{mp}/experiments` `{merge_of: [{experiment_id, version_id?}, {experiment_id, version_id?}], title, intent, hypothesis, entities, objectives?, context?, branch?}` → 201 + `Location` vers la **nouvelle piste** (§ 4 : deux parents, la structure de la première, cahier vide ; les deux études ne changent pas). Exactement deux études, sans `structure` ni `from_version` (422) ; une version inconnue → 404 `source_not_found` ; deux fois la même piste ou la même version → 422 `same_experiment` ; une version d'avant la fourche de la piste désignée → 422 `version_before_line` ; une étude d'un autre µprojet n'y existe pas (404), et un champ de plus dans `merge_of` (`microproject`...) est refusé (422). `POST …/experiments/{exp}/merges` **supprimée** |
| `GET …/{ref}/process` | `GET …/experiments/{exp}/process?version=&variant=` (`variant` : le procédé d'une variante d'une campagne, § 4 ; chaque étape porte son `id` ; `layer_labels` : les étiquettes de couches par position d'étape, § 4 ; `bricks` : les briques du procédé par positions d'étape, § 4) |
| `GET …/{ref}/diff`, `GET …/{ref}/diff-externe` | `GET …/experiments/{exp}/structure-diff?version=&against_version=&against_experiment=&against_microproject=` → `{target: {experiment_id, version_id, title, microproject} \| null, entries, summary?, label_changes, param_changes, step_changes}` (avec une cible, à part : les étiquettes de couches et leur regroupement par brique, `label_changes`, les paramètres déclarés, `param_changes`, et les étapes renommées, `step_changes` ; étapes appariées par id, par position entre deux versions sans id commun, § 4) ; sans cible, la **version de structure précédente** (pas le parent immédiat : une étiquette ne rend pas le diff « identique ») ; `against_microproject` exige `against_experiment` et un accès à l'autre µprojet (403) |
| `GET …/{ref}/matrice` | `GET …/experiments/{exp}/variants?version=` |
| `DELETE …/experiences/{ref}` | `DELETE …/experiments/{exp}` (+ `If-Match`) → 204 (supprime la piste jusqu'au point de fourche ; 409 `has_descendants` si une autre piste part de l'une de ses versions - la piste n'est jamais seulement raccourcie) |
| `POST …/{ref}/ref` | `POST /api/microprojects/{mp}/refs` `{experiment_id, version_id?, name?}` → 201 + `Location` `.../refs/{ref_name}` (encodé : `ref%20v1.1.0`) et la ref telle que la liste la montre, plus `name` (`name` vide : « ref vX.Y.Z » ; nom invalide → 422, nom pris → 409 ; § 4) |
| *(nouveau)* | `GET /api/microprojects/{mp}/refs/{ref_name}` (viewer) → l'entrée de la liste plus `name` ; inconnue → 404 `ref_not_found` |
| *(nouveau)* | `PATCH …/refs/{ref_name}` `{name}` (editor) → renomme, la version reste ; 409 `ref_name_taken`, 422 nom vide ou invalide ; même nom ou `name` absent → 200 sans effet |
| *(nouveau)* | `DELETE …/refs/{ref_name}` (editor) → 204, la version reste |
| *(nouveau)* | `GET /api/microprojects/{mp}/structure-history?all_versions=&include_versions=` (viewer ; `include_versions`, répété : des ids de version à montrer en plus - les versions publiées comme référence, que la page lit dans `GET /api/reference-versions` ; un id inconnu est ignoré) → `{lanes, nodes, edges}` pour la page d'évolution (`experiments.lineage.structure_history`) : pistes dans l'ordre de leur début puis du nom (une nouvelle piste vient en dernier) ; nœuds `{version_id, experiment_id, lane, version, label, change_level, title, created_at, author, is_tip, is_merge, refs, structure_kind, has_process}` (`label` : « vX.Y.Z ») - par défaut les versions structurelles, celles qui portent une ref, les fusions (combinaisons comprises) et le début de chaque piste, toutes avec `all_versions=true` ; arêtes `{parent, child, kind}` (`parent`, `fork` ou `merge` : vers une combinaison, depuis chacun de ses deux parents ; vers une fusion d'avant, depuis son second parent), à travers les versions masquées |
| `GET …/refs`, `GET …/refs/graphe` | `GET /api/microprojects/{mp}/refs` → `{refs: [{version_id, experiment_id, names, title, status, decision, version, created_at}], edges: [{from, to}]}` (ids de version) |
| `GET /api/microprojets/{slug}/filiation` | `GET /api/microprojects/{mp}/lineage` (les nœuds portent `version_id` et `experiment_id` - et `id`, égal à `version_id`, que citent les `edges` ; plus de badge de lot : le front le compose avec `GET /api/lots?wafer=`). Vers une version à deux parents (une combinaison), une arête depuis le nœud de chacune des deux études : une pointe est toujours un nœud, et deux pistes parties d'un même point sans changer sa structure n'y sont pas confondues avec ce point |
| `GET /api/microprojets/{slug}/graphe.html` | **supprimée**, ainsi que la page `/microprojets/{slug}/graphe` |
| *(dans les listes de µprojets)* | `GET /api/experiment-stats?microproject=&area=` → `[{microproject, running, concluded, abandoned, wafers, role_source}]` |
| *(dans la thématique)* | `GET /api/experiment-timeline?area=&thematic=` (champs masqués pour les non-membres) |
| *(nouveau)* | `GET /api/microprojects/{mp}/experiment-versions/{version_id}` → `{experiment_id, version_id}` (résolution des anciens liens) |

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
    path, caption, status, url}]}`. À l'écriture, `attachments` accepte des ids ou
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
| `GET /api/microprojets/{slug}/data/parcourir?dossier=` | `GET /api/microprojects/{mp}/external-images?directory=` (editor) → `[{name, path, size, displayable}]` ; limité à `SPECTRE_EXTERNAL_IMAGE_ROOTS` (racines connues telles qu'écrites et résolues : un nom court Windows passe), désactivé sans cette variable (503 `browsing_disabled` ; les chemins locaux restent acceptés à la création, les chemins UNC non) ; les TIFF sont listés, non affichables ; seules les images d'un dossier sont listées, pas ses sous-dossiers |
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
crée une. Plugin `references` : `service.py` (le domaine), `local_refs.py` (le regroupement des refs
locales d'avant).

| Route | Effet |
|---|---|
| `GET /api/references?q=` | toutes les références, la plus récemment mise à jour d'abord (une version publiée la met à jour) : `{slug, name, description, created_by, created_at, updated_by, updated_at, latest_version: {number, label, change_level, published_by, published_at, source, note} \| null, version_count, usage_count, can_edit}` ; `q` : nom, slug, description, sans casse ni accents |
| `POST /api/references` `{name, description}` | → 201 + `Location` `/api/references/{reference_slug}` + la référence, sans version ; nom vide ou sans lettre ni chiffre → 422 `invalid_reference_name`, nom déjà pris (comparé sans casse, ni accents, ni ponctuation) → 409 `reference_name_taken` |
| `GET /api/references/{reference_slug}` | une référence (404 `reference_not_found`) |
| `PATCH /api/references/{reference_slug}` `{name, description}` | son créateur ou un admin (403) ; le **slug ne change pas** (une étude cite sa référence par lui) ; sans effet → 200, rien d'écrit |
| `DELETE /api/references/{reference_slug}` | → 204 ; son créateur ou un admin (403) ; une référence qui a des versions, un admin seulement (409 `reference_has_versions` pour son créateur) - ses versions partent avec elle, les études qui en étaient parties gardent une origine désormais inconnue : son slug n'est **jamais redonné** (`retired_reference_slugs` ; une nouvelle référence du même nom reçoit `-2`), celui d'une référence sans version (aucune étude n'a pu en partir) se libère ; les étiquettes importées dans ses versions ne sont plus regroupées (`dismissed_local_refs`) : le retrait est définitif |
| `GET /api/references/{reference_slug}/versions` | `{reference, lanes, nodes, edges}` : l'évolution de la référence. `nodes`, dans l'ordre de publication : `{number, major, minor, label, change_level, parent, parent_inferred, imported, note, published_by, published_at, source, usage_count, usages, lane}` ; une version prend la colonne (`lane`) de son parent si elle en est le premier enfant, sinon une nouvelle ; `lanes` : `{index, start, head}` ; `edges` : `{parent, child, kind: "parent" \| "branch", inferred}` |
| `POST /api/references/{reference_slug}/versions` `{microproject, experiment_id, version_id?, note?, parent?}` | publie une version d'étude (la pointe de la piste par défaut) : rôle `editor` sur le µprojet source (403 ; µprojet inconnu → 422 `unknown_microproject`, piste ou version inconnue → 404) ; une structure dessinée seulement (des images, une campagne → 422 `reference_needs_process`) ; son parent : `parent` (« 1.1 », inconnu → 422 `unknown_parent_version`), sinon la dernière version de cette référence publiée depuis ce µprojet dont la version publiée descend (republier une étude qui a évolué continue sa suite : 1.1 puis 1.2), sinon la version dont part la piste source (`reference_origin`), sinon la dernière publiée ; identique à son parent → 409 `reference_version_identical` ; une version Follow déjà publiée dans cette référence → 409 `reference_version_already_published` ; → 201 + `Location` `.../versions/{version_number}` + la version |
| `GET /api/references/{reference_slug}/versions/{version_number}` | une version (404 `reference_version_not_found`) : son nœud, plus `reference {slug, name}`, `structure_svg` (l'instantané dessiné par le serveur, étiquettes comprises) et `process` (son procédé éditable, la forme de `GET .../experiments/{exp}/process` : étapes avec leur id, `layer_labels` et `bricks` par positions) - ce que le constructeur charge pour lancer une étude depuis elle |
| `GET /api/references/{reference_slug}/versions/{version_number}/structure-diff?against=` | la version comparée à `against` (une autre version de la référence), à sa version parente par défaut : `{target: {number} \| null, entries, summary?, label_changes, param_changes, step_changes}` - le diff des études (`experiments.service.compare_states`), lu dans les deux instantanés ; sans parent ni `against` : `{target: null, entries: []}` |
| `GET /api/reference-versions?microproject=` | les versions de référence publiées depuis ce µprojet (viewer : 403 sinon ; inconnu → 404) : `[{reference: {slug, name}, number, label: "R nom 1.1", experiment_id, version_id, local_tag, change_level, published_at}]`, pour les badges de sa page d'évolution |

- **Numéro** (`service.next_number`) : la version est comparée à sa version parente par le
  versionnage des études (`experiments.service.structure_change_level`). La première est 1.0 ; un
  changement **majeur** (substrat, suite d'étapes) ouvre le majeur suivant **le plus grand pris** (un
  majeur quand 2.0 existe : 3.0) ; un **mineur** ou un **correctif** (étiquettes, nom d'étape, unité
  ajoutée seule) prend le mineur suivant le plus grand pris sous le majeur du parent (deux dérivations
  de 1.0 : 1.1 puis 1.2) ; aucun changement → 409. Les écritures des références passent une à une
  (`keyed_lock("references", "write")`), et `(reference_id, number_major, number_minor)` est unique :
  deux publications simultanées n'ont jamais le même numéro. `change_level` garde le niveau
  (`initial`, `major`, `minor`, `patch` ; `none` pour un import seulement).
- **Instantané** (`service.snapshot_of`, colonne `snapshot`) : la structure dessinée
  (`structure_type`, `structure` de Follow), les métadonnées qui la décrivent (`structureforge_process`
  - substrat, étapes, paramètres déclarés avec leur unité -, `process_step_ids` tels qu'on les lit,
  `process_layer_labels`, `process_layer_steps`, `process_bricks`) et le titre de l'étude. Une version
  se dessine, se reprend et se compare sans son étude : elle reste utilisable si l'étude change de
  droits ou disparaît. Aucun objet Follow n'est écrit.
- **Source et masquage** : `source` = `{microproject: {slug, code, name}, experiment_id, version_id,
  title, local_tag, linked: true}` pour un membre du µprojet source (un admin l'est de tous),
  `{microproject: {name}, linked: false}` pour les autres, `{microproject: {name, deleted: true},
  linked: false}` si le µprojet a été supprimé (son nom à la publication). Les usages suivent la même
  règle : `{microproject, experiment_id, title, status, updated_at, linked: true}` ou
  `{microproject: {name}, linked: false}`.
- **Usages** : les études parties d'une version - la pointe de chaque piste dont `reference_origin`
  désigne `(slug, numéro)`, lue dans le dépôt en cache de chaque µprojet (une lecture par µprojet et
  par réponse) ; une fourche ou une combinaison qui a gardé l'origine compte aussi. Une origine
  inconnue n'est comptée nulle part.
- **Les refs locales d'avant** (`local_refs.import_local_refs`, appelée par chaque fonction du
  service avant tout le reste ; règle décidée le 2026-10-05) : seuls les noms de refs portés dans
  **au moins deux µprojets** (`SHARED_BY`) deviennent des références. Les étiquettes Follow de tous
  les µprojets sont relues et regroupées par nom normalisé (`service.normalized_name` : sans casse,
  ni accents, ni ponctuation), sauf les noms automatiques « ref vX.Y.Z » (suffixés ou non) et les
  étiquettes d'une structure qui n'est pas un procédé dessiné ; un nom qui n'est porté (sur un
  procédé dessiné) que dans un µprojet reste un repère local, montré sur sa page d'évolution, qu'un
  éditeur publie à la main s'il le veut (« Publier comme référence »). Le partage se décide sur
  l'ensemble des µprojets : un nom qui n'était que dans A et qui apparaît dans B importe, à la
  lecture des références qui suit, les étiquettes de A et de B (A et B déjà lus ou non). Chaque nom partagé a sa
  référence (celle qui a déjà reçu des étiquettes de ce nom, même renommée ; sinon une référence du
  même nom existante ; sinon une nouvelle : le nom de sa plus ancienne étiquette, créateur : celui du
  µprojet de la première version), chaque étiquette une version (`local_tag`, `published_by` vide,
  `published_at` : la date de la version étiquetée), dans l'ordre des dates ; son parent est la
  dernière version de la référence dont la version étiquetée descend dans le même dépôt, sinon la
  précédente (`parent_inferred` : un rattachement déduit) ; une version identique à son parent (la
  même structure étiquetée dans deux µprojets, comme « epitaxie-standard » dans la démo) reçoit le
  mineur suivant, `change_level` `none` ; une étiquette déjà importée (même µprojet, même nom) ou
  dont la version Follow est déjà une version de la référence (publiée à la main) ne l'est pas deux
  fois. Les étiquettes d'une référence qu'un admin a retirée (`service.delete_reference` :
  `dismissed_local_refs`, par µprojet et nom) ne sont plus regroupées ni comptées pour le partage :
  le retrait est définitif (elles restent des repères locaux, publiables à la main ; un nom repris
  par deux autres µprojets fait une nouvelle référence, slug suffixé). Les étiquettes restent en
  place, aucun fichier Follow n'est réécrit.
  Le regroupement passe quand l'empreinte des étiquettes nommées d'un µprojet (`_fingerprint` :
  noms et versions, lus dans le `refs.json` du dépôt en cache) diffère de celle de sa dernière
  lecture (`reference_import_scans.tags_fingerprint`, migration `0004_dismissed_local_refs`) ou
  qu'il n'a pas encore été lu - une ref posée, retirée ou déplacée dans un µprojet déjà lu est donc
  regroupée à la lecture suivante -, et une fois pour la règle (`reference_import_rules`,
  migration `0003_import_rules`) : sur une installation où l'ancienne règle (chaque ref nommée
  devenait une référence) a tourné, il retire d'abord les références qu'elle a créées depuis un seul
  µprojet - toutes leurs versions importées, aucune publiée à la main, aucune dont le µprojet a
  été supprimé (son instantané est la seule copie qui reste), aucune étude, quelle qu'en
  soit la version, qui cite leur slug (`reference_origin`), et que personne n'a touchées (ni
  renommées ni décrites : écart, une référence retouchée à la main est gardée) -, sans réserver
  leur slug (aucune étude n'en est partie), puis relit tous les µprojets. Idempotent ; sans
  étiquette changée ni règle à passer, la lecture des `refs.json` en cache et une requête.

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

### Pages (URL françaises, inchangées sauf mention)

| Plugin | Pages |
|---|---|
| accounts | `/connexion`, `/inscription`, `/mot-de-passe-oublie`, `/reinitialiser`, `/profil` |
| teams | `/equipes`, `/equipes/{slug}` (nouvelles) |
| areas | `/`, `/management/{slug}`, `/management/{slug}/thematiques/{thematique_slug}` |
| atlas | `/management/{slug}/atlas` |
| microprojects | `/microprojets/{slug}`, `/p/{code}` (redirection, **après** contrôle de session), `/projets/{rest:path}` (redirection héritée, 308) |
| experiments | `/microprojets/{slug}/experiences/{experiment_id}` (`?version=` pour une version passée, en lecture seule ; un ancien id de version est résolu puis redirigé en 302 par le `page_router`, sans `?version=` si c'est la pointe, vers `/connexion` hors session, vers le µprojet si la version est introuvable), `/microprojets/{slug}/evolution` (nouvelle : « Évolution des structures », diagramme des pistes, versions, refs locales et versions de référence ; liée depuis la page µprojet et la fiche), `/microprojets/{slug}/refs` (302 vers `/evolution`) |
| references | `/references` (la liste des références de toute l'application ; entrée « Références » de la barre du haut), `/references/{slug}` (l'évolution d'une référence, `?version=1.1` : la version choisie) |
| structures | `/microprojets/{slug}/structures/nouvelle`, `/structures/image`, `/experiences/{experiment_id}/evoluer`, `/experiences/{experiment_id}/evoluer-image` (`?version=` : partir d'une version passée, sur une nouvelle piste), `/structures/bibliotheque/nouvelle`, `/structures/bibliotheque/{structure_id}`, `/briques-technologiques/bibliotheque/nouvelle`, `/briques-technologiques/bibliotheque/{brick_id}` |
| process_library | `/bibliotheque`, `/microprojets/{slug}/presets-etapes`, `/microprojets/{slug}/briques-technologiques` |
| intent_forms | `/microprojets/{slug}/formulaire-intention` |
| wafers | `/plaques/{lasermark}` |
| lots | `/lots`, `/lots/{code}` |
| characterization | `/donnees`, `/donnees/{key}` |
| docs | `/docs`, `/docs/guide`, `/docs/exemples`, `/docs/architecture` |

Supprimée : `/microprojets/{slug}/graphe`.

## 6. Front

- Scripts classiques (`<script src>`), sans bundler ni framework. Un `client.js`, un registre ou
  un module partagé récent n'expose qu'un global nommé d'après son plugin (`lotsApi`,
  `ExperiencePage`, `DataViz`, `EvolutionGraph`, `ReferencePublishDialog`, `ReferenceStartPicker`…) ; ses autres déclarations restent locales, dans une IIFE ou un
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
  `svg.sp-labelled-structure` à sa `data-bare-viewbox`), `plates.js` (plaques suivies), `conclusion.js`,
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
  d'ajout et d'édition : type, plaques, stepper à cocher, une mesure par bulle, tableau collé en TSV,
  images par `mountImageDrop` avec `purpose: "notebook"`, images externes - choisies dans un
  dossier autorisé (`externalImagesApi.roots`, puis `browse`) ou par leur chemin, légendées,
  réordonnées (la première est la principale), retirées ; une image déjà sur la mesure s'aperçoit
  par son `url`, une nouvelle une fois enregistrée -, fichiers, liens) et `stepper.js`
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
- **Les références, côté pages** (plugin references, TODO « Références de structure ») :
  - `experiments/static/evolution-graph.js` (global `EvolutionGraph`) : le diagramme façon git -
    colonnes, rangées, arêtes, formes des nœuds par niveau de changement, légende, liste des
    rangées au clavier (`bindListbox`), corps d'une comparaison (`diffBodyHtml`). Il ne connaît ni
    les pistes ni les références : la page d'évolution d'un µprojet (`evolution.js`, versions
    Follow) et la page d'une référence (`references/static/reference.js`, versions 1.0, 1.1, 2.0 :
    colonnes de branches, rattachements déduits en pointillés, `evo-edge--inferred`) lui donnent
    leurs nœuds rangés et écrivent leurs rangées et leur panneau. Il reste dans experiments, d'où
    il vient et que references charge déjà (le navigateur compose).
  - `references/static/publish-dialog.js` (global `ReferencePublishDialog`) : « Publier comme
    référence », ouvert par la fiche (`tags-refs.js`, à la place de « + ref », sur une structure
    dessinée seulement) et la page d'évolution (à la place de « Promouvoir en ref » et de « Publier
    dans la bibliothèque »). La référence proposée : l'origine de l'étude (`reference_origin`),
    sinon la dernière référence où a été publiée une version dont elle descend (la page
    d'évolution donne ces ancêtres, lus dans ses arêtes ; la fiche, sur la pointe, prend la même
    piste) ; le parent proposé : la dernière version de cette référence publiée depuis la piste,
    sinon la version d'origine (la règle du serveur). Une référence créée dans la boîte puis
    refusée (409 identique, droits) est retirée aussitôt. Le numéro calculé s'affiche après la publication.
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
    (badges « R nom 1.1 », anneau or comme une ref) ; les refs locales restent montrées en
    repères, renommer et retirer gardés, mais ne se posent plus (`experimentsApi.createRef` retiré
    du client ; la route reste).
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
