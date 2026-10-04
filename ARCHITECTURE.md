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
| `json_store.py` | Collections JSON `{"items": [...]}` d'éléments à `id`, lues et écrites sous un verrou par chemin, de façon atomique ; un élément illisible est écarté à la lecture et gardé tel quel à l'écriture (`ItemStore`, `read_json`, `write_json`, `path_lock`) - les bibliothèques de `process_library` |
| `mail.py` | `send_email(to, subject, body)` : SMTP si `SPECTRE_SMTP_HOST`, sinon journalisation **sans le corps** hors `SPECTRE_EMAIL_DEBUG=1` |
| `pages.py` | Service des pages HTML d'un plugin, avec la barre du haut commune à la place du marqueur `<!-- spectre:topbar -->` (fil d'Ariane déclaré dans le marqueur : `crumb-id`, `crumb-text`) : marque, navigation construite à partir des `NavEntry` de tous les plugins (une entrée peut être réservée à certaines pages : `NavEntry.pages`), place de la session |
| `http.py` | Petits helpers HTTP : `created(response, location)`, conversion `ETag` / `If-Match` |
| `static/` | Front du noyau : `api.js` (client HTTP : JSON, `upload(FormData)`, `blob`, `If-Match`, redirection 401, erreurs 422 lisibles), `ui.js` (`escapeHtml`, `initials`, dates, durées, `routeParams(pattern)`), `timeline.js` (axe des mois et hachures des frises : lots, thématique), `shell.js` (barre du haut : navigation active), `kernel.css` (tokens et composants de la charte), `img/`, `vendor/` (d3, codemirror) |

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
    enabled: Callable[[], bool] = lambda: True   # ex. kpis_demo : SPECTRE_DEMO_DATA=1
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
| 2 | `teams` | Équipes et leurs membres (`manager` ou `member`), page Équipes. Fournit `service.managed_team_ids(user_id)`. Ce qu'une équipe possède est dit par `areas` | accounts | `teams`, `team_members` |
| 3 | `search` | `GET /api/search`, qui agrège les fournisseurs déclarés par les autres plugins (`register_provider`) | accounts | — |
| 4 | `library` | Bibliothèque racine YAML de l'instance (matériaux, recettes, présets, briques, textes d'UI), chargeur générique avec cache mtime, registre `LibraryFile` alimenté par les plugins propriétaires, édition réservée à l'admin | accounts | `data_dir/library/*.yml` (copiés depuis `library/defaults/` au premier démarrage, et les `*.yml` d'un `<dépôt>/library` d'avant par-dessus) |
| 5 | `areas` | Projets corporate (*management areas*), leur équipe, thématiques, objectifs. Pages accueil, projet et thématique. Fournit `service.can_manage(user, area)` et `managed_area_ids(user)` | accounts, teams | `management_areas` (dont `team_id`, `ON DELETE SET NULL`), `thematics`, `area_objectives` |
| 6 | `microprojects` | µprojets (CRUD, numéro, rattachement à un projet ou une thématique, recherche), membres, rôles, invitations. Fournit la règle d'accès (`service.access`, `effective_role`, `check_role`) et `deps.require_role` | accounts, areas, search | `microprojects`, `memberships`, `invitations` |
| 7 | `attachments` | Fichiers téléversés d'un µprojet (blob + sidecar), types, tailles, service des octets | microprojects | `data/microprojects/<slug>/attachments/` |
| 8 | `structures` | Pont StructureForge : matériaux, recettes, simulation, aperçu de campagne DOE, rendu SVG, **types de structure** (`process`, `campaign`, `images`) exposés par `kinds.py`. Pages du constructeur | accounts, library, attachments | — |
| 9 | `process_library` | Structures enregistrées, présets d'étape, briques technologiques (portées `builtin` / `shared` / `microproject`). Pages bibliothèque, présets, briques | structures, microprojects, library | JSON par portée |
| 10 | `experiments` | Pistes d'étude et versions (dépôt Follow d'un µprojet) : création, évolution, statut, conclusion, étiquettes, entités physiques, fusion, suppression, diff, filiation, refs, statistiques et frise transverses. Seul point d'écriture vers Follow (`service.amend`) | microprojects, structures, attachments | `data/microprojects/<slug>/follow/` (dont `retired_lines.json`, les noms des pistes supprimées) |
| 11 | `evidence` | Preuves d'une étude, liens, images, annotations | experiments, attachments | métadonnées Follow |
| 12 | `intent_forms` | Formulaires d'intention (portées) et formulaire actif d'un µprojet | experiments, microprojects | JSON + `follow/commit_form.yml` |
| 13 | `wafers` | Index des plaques suivies, clé `wafer_key`, passeport d'une plaque, recherche par lasermark et par FDL, politique de visibilité | experiments, search | cache mémoire |
| 14 | `lots` | Lots de fabrication, leurs wafers et leurs thématiques visées, Gantt ; ce qu'une lecture compose (expériences, thématiques, retard) dans `views.py` | wafers, areas, experiments, search | `lots`, `lot_wafers`, `lot_thematics` |
| 15 | `links` | Liens entre µprojets et entre entités physiques | microprojects, experiments | `microproject_links`, `entity_links` ; mis de côté par les migrations, plus lus : `entity_links_unresolved`, `microproject_links_duplicates` |
| 16 | `atlas` | Vue graphe d'un projet corporate | areas, microprojects, experiments, links | — |
| 17 | `characterization` | Types de données de caractérisation (PRISM, ou démo via le Protocol `DataSource`) : catalogue, requêtes, graphiques documentaires. Seul module qui importe `prism` | accounts | cache PRISM sous `data_dir/prism` (`PRISM_DATA_DIR`, fixé par `service.current_source()` s'il ne l'est pas) |
| 18 | `notebook` | Cahier de données d'une étude : instantanés et vues DataViz | characterization, experiments | `snapshots/`, métadonnées Follow |
| 19 | `external_images` | Galerie d'images externes référencées (TEM, scans) d'une étude, limitée aux racines autorisées | experiments | métadonnées Follow |
| 20 | `kpis` | Registre de KPI (`register`) et séries mensuelles d'un projet corporate | areas, experiments | — |
| 21 | `kpis_demo` | Séries et fiche d'étude fictives. **Actif seulement si `SPECTRE_DEMO_DATA=1`** | kpis, structures | — |
| 22 | `docs` | Pages de documentation (contenu inchangé) | — | — |

**Les tables d'un autre plugin.** Un plugin possède ses tables : il est seul à y écrire. Il peut
en revanche les **lire par jointure SQL** chez les plugins dont il dépend, pour une liste qui en
affiche un champ (`lots` lit `thematics`, `links` joint `microprojects`, `microprojects` lit
`management_areas`, les auteurs sont joints sur `users`). Une seule exception va contre le DAG :
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
µprojet existant depuis la page d'un projet (il s'appuie sur `?scope=all`). En revanche, un `owner`
d'un µprojet le déplace vers n'importe quel projet (`PATCH /api/microprojects/{mp}` `{area}`),
celui d'une autre équipe compris : il en perd alors la gestion d'équipe, et les managers de
l'équipe d'arrivée la gagnent. Côté µprojet, `microprojects.service.access(user, microproject)` rend
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
| `ExperiencePage.registerPanel({key, mount(el, ctx)})` (voir § 6) | `experiments/static/page.js` | les panneaux de la fiche elle-même, puis evidence (`evidence-panel.js`), external_images (`gallery.js`), lots (`lot-picker.js`), notebook (`notebook.js`) |

**Clés de type de structure figées.** `ProcessLot` et `StructureImage` surchargent
`registry_key()` pour renvoyer leur chaîne historique (`spectre.core.structures.…`). Follow
persiste cette clé dans `structure_type` et l'utilise dans le hachage de l'id, si bien qu'un
déplacement de classe ne doit jamais la changer.

## 4. Conventions REST

- **Langue** : anglais pour l'API, les plugins et le code ; les URL de pages vues par les
  utilisateurs restent en **français**.
- **Ressources** au pluriel, en kebab-case, sans verbe. Une action métier devient une
  sous-ressource : `PUT .../conclusion`, `POST .../merges`.
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
  `{data_type_key}`, `{chart_key}`, `{file_key}`) ; deux autres formes : `{token}` (le jeton d'une
  invitation, seul identifiant que connaît son destinataire) et `{index}` (la position d'une image
  dans un jeu). Pas de convertisseur `:path` sous `/api` (une seule page en a un : la redirection
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
- Les plugins qui écrivent dans une étude sans en être le propriétaire (evidence, notebook,
  external_images) exposent leurs sous-ressources sous `.../experiments/{exp}/` et passent par
  `amend()` : `If-Match` comme les autres (412 `stale_version`), et une écriture renvoie **la
  ressource écrite** (la preuve, la vue du cahier, le jeu d'images), pas l'étude, avec en `ETag` la
  version créée - c'est ce que la fiche enverra en `If-Match` à l'écriture suivante. Leurs lectures
  acceptent `?version=`, sur le modèle de `process?version=`, pour qu'une version passée ouverte en
  lecture seule montre ses propres données. Le détail d'une étude ne porte plus que
  `evidence_count`. Les clés des métadonnées Follow (`evidence_links`, `image_annotations`,
  `data_notebook`, `data_items`) ne changent pas : les études existantes restent lisibles.
- Toutes les lectures des autres plugins désignent la piste : l'index des plaques (wafers, donc la
  recherche et les lots) donne `experiment.id` = la piste ; l'atlas nomme chaque étude par
  `experiment_id` (et `version_id`, sa pointe) ; un lien d'entité désigne
  `{microproject, experiment_id, entity_index}`.
- Deux écritures traversent encore une frontière de plugin sans import, faute de dépendance dans
  ce sens : une fusion (`experiments.service`) reporte et purge les métadonnées de preuve par id
  (evidence dépend d'experiments, pas l'inverse) ; supprimer une piste ne purge pas ses liens
  d'entités (experiments ne dépend pas de links) - ils restent listés et supprimables, l'atlas ne
  les dessine plus, et le nom de la piste n'est **jamais redonné** (`follow/retired_lines.json`,
  `repository.retire_line`) : un lien désigne la piste par son nom, il passerait sinon à une étude
  sans rapport. Supprimer un µprojet, lui, purge ses liens (`ON DELETE CASCADE`).
- Le nom d'une piste : tiré du titre (`epitaxie-a-20-nm`, accents retirés, suffixe `-2`... si pris),
  ou `branch` à la création - un seul segment sans `/`, ni `.`/`..`, ni la forme d'un id de version,
  libre parmi les pistes, les refs **et** les pistes supprimées (sinon 409 `branch_name_taken`).
- Une piste créée depuis une version (`from_version`, `version_id` facultatif : la pointe par
  défaut) en reprend, faute de mieux dans la requête, les objectifs, le contexte et l'entité suivie -
  pas les preuves, les étiquettes ni la conclusion : c'est une nouvelle étude.
- Le nom d'une ref (`refs.py`) : non vide, sans `/`, ni `.`/`..`, ni la forme d'un id de version
  (`repository.VERSION_ID_RE`, repris par `service.VERSION_ID_RE` ; Follow cherche un nom avant un
  id, une telle ref masquerait la version) - sinon 422 `invalid_ref_name` -, libre parmi les refs et
  les pistes (409 `ref_name_taken`). Une ref est propre au µprojet ; la renommer ou la retirer ne
  touche pas la version.
- `scripts/repair_hypotheses.py` (à blanc par défaut, `--apply` pour écrire) reporte sur la pointe de
  chaque piste qui l'a perdue la dernière hypothèse non vide de son historique (bug B1).

### Identité d'une étape

Chaque étape d'un procédé a un id stable, `st_<8 hex>` (`structures.simulation.STEP_ID_RE`),
conservé aux évolutions : c'est par lui qu'un facteur de campagne (et, plus tard, une donnée du
cahier) désigne une étape, et non plus par sa position.

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
| `GET /api/management` | `GET /api/areas?team=` (équipe inconnue → 404 ; chaque projet expose `is_system`, `team {slug, name}`, `can_manage`, `can_delete` (= `can_manage` et pas système), `horizon_months` calculé par le serveur) |
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
| `POST /api/microprojets` | `POST /api/microprojects` `{name, description, area, thematic}` → 201 + `Location` (projet ou thématique inconnus → 422, comme le `PATCH` ; un nom qui donnerait le slug « new » ou « nouvelle » reçoit un suffixe) |
| `GET /api/microprojets/{slug}` | `GET /api/microprojects/{mp}` ; tout µprojet renvoyé porte `role` (effectif), `role_source` (`membership`, `team_manager` ou `admin`), `can_edit` et `can_manage` (§ 3, règle d'autorisation) |
| *(nouveau)* | `PATCH /api/microprojects/{mp}` `{name, description, area, thematic}` |
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
| `POST /api/microprojets/{slug}/images` | `POST /api/microprojects/{mp}/attachments` (multipart, `purpose=evidence`) → 201 `{id, url, …}` |
| `POST /api/microprojets/{slug}/structures/images` | idem avec `purpose=structure` |
| `GET /api/microprojets/{slug}/pieces-jointes/{id}` | `GET /api/microprojects/{mp}/attachments/{attachment_id}/content` |
| *(nouveau)* | `GET /api/microprojects/{mp}/attachments/{attachment_id}` (métadonnées) |
| `POST/DELETE …/experiences/{ref}/pieces-jointes[/{id}]` | **supprimées** (aucun appelant front : on passe par attachments puis evidence), avec les fonctions transitoires de `attachments.store` qui les servaient |

### structures · library

| Avant | Après |
|---|---|
| `GET /api/microprojets/{slug}/materials` | `GET /api/materials` |
| `GET /api/microprojets/{slug}/recettes` | `GET /api/recipes` → `{deposition: [...], etch: [...]}` (exception à « les autres sont un tableau » : le constructeur lit les recettes par sorte d'étape) |
| `POST /api/microprojets/{slug}/structures/simulate` | `POST /api/simulations` → 200 (calcul, rien n'est stocké) ; la réponse porte `step_ids`, l'id de chaque étape (§ 4, identité d'une étape) |
| `POST /api/microprojets/{slug}/structures/variantes` | `POST /api/campaign-previews` → 200 (plafond `MAX_CAMPAIGN_ENTITIES`, 422 au-delà) ; chaque facteur désigne son étape par `step_id` (`"substrate"` pour le substrat ; id inconnu → 422, `step_index` refusé) |
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
| `…/structures-sauvegardees[/{name}]` | `/api/saved-structures[/{structure_id}]` (même schéma) ; `derived_from` : un nom, ou l'origine `{microproject, experiment_id, version_id, ref}` d'une ref publiée depuis la page d'évolution (une étiquette, gardée telle qu'envoyée) |
| `…/briques-technologiques[/{name}]` | `/api/tech-bricks[/{brick_id}]` (même schéma) |

### experiments

| Avant | Après |
|---|---|
| `GET /api/microprojets/{slug}/experiences?status=&offset=&limit=` | `GET /api/microprojects/{mp}/experiments?status=all\|running\|concluded&q=&offset=&limit=` → `{items, total}` (`q` : titre, intention, étiquettes, nom de piste ; chaque élément : `id` = la piste, `version_id` = sa pointe) |
| `POST …/experiences` | `POST /api/microprojects/{mp}/experiments` `{…, structure: {kind: "process", …}}` → 201 |
| `POST …/experiences/image` | idem, avec `structure: {kind: "images", images: [...]}` |
| `POST …/experiences/campagne` | idem, avec `structure: {kind: "campaign", …, plan}` ; `from_version` pour partir d'une version existante ; les facteurs du plan désignent leur étape par `step_id`, comme l'aperçu. Les étapes envoyées (lancement, évolution, fourche) peuvent porter leur `id` |
| `GET …/experiences/{ref}` | `GET /api/microprojects/{mp}/experiments/{exp}` (dernière version, `ETag`) ; le détail porte `id` (la piste), `version_id`, `is_tip`, `children` `[{experiment_id, version_id, title, is_tip}]` et `continued_at` (première suite structurelle) |
| `GET …/experiences/{ref}/timeline` | `GET …/experiments/{exp}/versions` → tableau, de la première version à la pointe : `{version_id, experiment_id, title, intent, created_at, author, is_tip, version, change_level}` (la frise des structures : `change_level != "none"`) |
| *(nouveau)* | `GET …/experiments/{exp}/versions/{version_id}` (une version de l'histoire de la piste, `ETag`) |
| `POST …/{ref}/evoluer` | `POST …/experiments/{exp}/versions` `{structure: {kind: "process", …}, …}` + `If-Match` → 201 + `Location` vers la version ; **200 sans `Location`** si rien n'a changé (§ 4) ; une campagne y est refusée (422 `campaign_is_a_new_line`) : elle se lance avec `from_version` |
| `POST …/{ref}/evoluer-image` | idem, avec `structure: {kind: "images", …}` |
| `POST …/{ref}/dessin` | `PUT …/experiments/{exp}/structure-images` |
| `POST …/{ref}/conclure` | `PUT …/experiments/{exp}/conclusion` |
| `POST …/{ref}/statut` | `PUT …/experiments/{exp}/status` `{status, hold_reason}` |
| `POST …/{ref}/etiquettes` | `PUT …/experiments/{exp}/tags` `{tags}` |
| `POST …/{ref}/entites` | `PUT …/experiments/{exp}/entities` `{entities}` |
| `POST …/{ref}/combiner` | `POST …/experiments/{exp}/merges` `{other_experiment_id}` → 201 + `Location` vers la version (titre et intention restent ceux de la piste ; les preuves des deux côtés sont reportées, dédoublonnées par id, et les métadonnées qui désignent une preuve absente purgées) |
| `GET …/{ref}/process` | `GET …/experiments/{exp}/process?version=` (chaque étape porte son `id`) |
| `GET …/{ref}/diff`, `GET …/{ref}/diff-externe` | `GET …/experiments/{exp}/structure-diff?version=&against_version=&against_experiment=&against_microproject=` → `{target: {experiment_id, version_id, title, microproject} \| null, entries, summary?}` ; sans cible, la **version de structure précédente** (pas le parent immédiat : une étiquette ne rend pas le diff « identique ») ; `against_microproject` exige `against_experiment` et un accès à l'autre µprojet (403) |
| `GET …/{ref}/matrice` | `GET …/experiments/{exp}/variants?version=` |
| `DELETE …/experiences/{ref}` | `DELETE …/experiments/{exp}` (+ `If-Match`) → 204 (supprime la piste jusqu'au point de fourche ; 409 `has_descendants` si une autre piste part de l'une de ses versions - la piste n'est jamais seulement raccourcie) |
| `POST …/{ref}/ref` | `POST /api/microprojects/{mp}/refs` `{experiment_id, version_id?, name?}` → 201 + `Location` `.../refs/{ref_name}` (encodé : `ref%20v1.1.0`) et la ref telle que la liste la montre, plus `name` (`name` vide : « ref vX.Y.Z » ; nom invalide → 422, nom pris → 409 ; § 4) |
| *(nouveau)* | `GET /api/microprojects/{mp}/refs/{ref_name}` (viewer) → l'entrée de la liste plus `name` ; inconnue → 404 `ref_not_found` |
| *(nouveau)* | `PATCH …/refs/{ref_name}` `{name}` (editor) → renomme, la version reste ; 409 `ref_name_taken`, 422 nom vide ou invalide ; même nom ou `name` absent → 200 sans effet |
| *(nouveau)* | `DELETE …/refs/{ref_name}` (editor) → 204, la version reste |
| *(nouveau)* | `GET /api/microprojects/{mp}/structure-history?all_versions=` (viewer) → `{lanes, nodes, edges}` pour la page d'évolution (`experiments.lineage.structure_history`) : pistes dans l'ordre de leur début puis du nom (une nouvelle piste vient en dernier) ; nœuds `{version_id, experiment_id, lane, version, label, change_level, title, created_at, author, is_tip, is_merge, refs, structure_kind, has_process}` (`label` : « vX.Y.Z ») - par défaut les versions structurelles, celles qui portent une ref, les fusions et le début de chaque piste, toutes avec `all_versions=true` ; arêtes `{parent, child, kind}` (`parent`, `fork` ou `merge`), à travers les versions masquées |
| `GET …/refs`, `GET …/refs/graphe` | `GET /api/microprojects/{mp}/refs` → `{refs: [{version_id, experiment_id, names, title, status, decision, version, created_at}], edges: [{from, to}]}` (ids de version) |
| `GET /api/microprojets/{slug}/filiation` | `GET /api/microprojects/{mp}/lineage` (les nœuds portent `version_id` et `experiment_id` - et `id`, égal à `version_id`, que citent les `edges` ; plus de badge de lot : le front le compose avec `GET /api/lots?wafer=`) |
| `GET /api/microprojets/{slug}/graphe.html` | **supprimée**, ainsi que la page `/microprojets/{slug}/graphe` |
| *(dans les listes de µprojets)* | `GET /api/experiment-stats?microproject=&area=` → `[{microproject, running, concluded, abandoned, wafers, role_source}]` |
| *(dans la thématique)* | `GET /api/experiment-timeline?area=&thematic=` (champs masqués pour les non-membres) |
| *(nouveau)* | `GET /api/microprojects/{mp}/experiment-versions/{version_id}` → `{experiment_id, version_id}` (résolution des anciens liens) |

### evidence · notebook · external_images

| Avant | Après |
|---|---|
| *(dans le détail : `evidence`, `evidence_links`, `attachments`)* | `GET …/experiments/{exp}/evidence?version=` → tableau ; chaque preuve porte les champs de Follow plus `kind`, `objective`, `interpretation`, `graph_config`, `annotations` (stockées sous `image_annotations`), `links` et `images: [{id, url, filename, content_type, size, caption}]` ; le détail ne garde que `evidence_count` |
| `POST …/{ref}/preuves` | `POST …/experiments/{exp}/evidence` → 201 + `Location` + la preuve (`ETag` : la version créée) ; le type `graph`, qui allait chercher une URL arbitraire, est refusé à la création (422) et `graph_config` n'est plus reçu ; la fiche montre les anciennes en lecture - titre, axes, requête - sans rien aller chercher ; une image téléversée dans un autre µprojet → 422 |
| *(nouveau)* | `GET …/experiments/{exp}/evidence/{evidence_id}?version=` (la cible du `Location`) |
| `POST …/{ref}/preuves/{id}/annotations` | `PUT …/experiments/{exp}/evidence/{evidence_id}/annotations` → 200, la preuve (les mêmes annotations ne créent pas de version ; image étrangère à la preuve → 422) |
| `GET /api/microprojets/{slug}/donnees/sources` | `GET /api/characterization/data-types?by_wafer=true&status=implemented` |
| `POST …/donnees/instantanes` | `POST /api/microprojects/{mp}/snapshots` `{hook, wafers, refresh}` → 201 + `Location` (la clé `hook` est celle que stockent instantanés et vues) |
| `GET …/donnees/instantanes/{id}` | `GET /api/microprojects/{mp}/snapshots/{snapshot_id}` (immuable : `Cache-Control: private, max-age=31536000, immutable`) |
| *(dans le détail : `data_notebook`)* | `GET …/experiments/{exp}/notebook-entries?version=` → tableau |
| `POST …/{ref}/cahier` | `POST …/experiments/{exp}/notebook-entries` → 201 + la vue (`ETag` : la version créée), **sans `Location`** : une vue n'a pas de route propre, elle se lit dans la liste |
| `PUT …/{ref}/cahier/{entry_id}` (+ `move`) | `PATCH …/experiments/{exp}/notebook-entries/{entry_id}` (`position` entier, ramené dans les bornes ; sans effet → pas de version) |
| `DELETE …/{ref}/cahier/{entry_id}` | `DELETE …` → 204 |
| *(dans le détail : `data_items`)* | `GET …/experiments/{exp}/image-sets?version=` → tableau ; chaque image `{index, name, path, status, url}`, `status` ∈ `ok`, `missing`, `unsupported`, `forbidden` |
| `POST …/{ref}/data` | `POST …/experiments/{exp}/image-sets` → 201 + le jeu (`ETag`), **sans `Location`** (pas de route propre, comme une vue du cahier) |
| `PATCH …/{ref}/data/{id}/epingle` | `PATCH …/experiments/{exp}/image-sets/{set_id}` `{pinned_index}` (sans effet → pas de version) |
| `DELETE …/{ref}/data/{id}` | `DELETE …/experiments/{exp}/image-sets/{set_id}` → 204 |
| `GET /api/microprojets/{slug}/data/image?chemin=` | `GET …/experiments/{exp}/image-sets/{set_id}/images/{index}?version=` (chemin lu dans les métadonnées, jamais reçu du client ; borné aux racines lui aussi : un ancien jeu qui pointe ailleurs répond 403) |
| `GET /api/microprojets/{slug}/data/parcourir?dossier=` | `GET /api/microprojects/{mp}/external-images?directory=` (editor) → `[{name, path, size, displayable}]` ; limité à `SPECTRE_EXTERNAL_IMAGE_ROOTS` (racines connues telles qu'écrites et résolues : un nom court Windows passe), désactivé sans cette variable (503 `browsing_disabled` ; les chemins locaux restent acceptés à la création, les chemins UNC non) ; les TIFF sont listés, non affichables |

Codes de la galerie : hors des racines → 403 `outside_roots` (contrôle lexical avant tout accès disque, revérifié après résolution des liens) ; dossier ou image absents → 404 `directory_not_found` / `image_missing` ; TIFF, fichier qui n'est pas une image, introuvable ou chemin relatif → 422 `unsupported_format`, `not_an_image`, `file_not_found`, `relative_path`.

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
| `GET /api/plaques/{lasermark}` | `GET /api/wafers/{wafer_key}` (le lasermark tel qu'écrit marche aussi ; sans les lots : `GET /api/lots?wafer=` ; une plaque inconnue → 200 sans occurrence, comme avant) ; chaque occurrence : `lasermark` et `experiment: {microproject, member, status, updated_at, id?, title?}` |
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
| experiments | `/microprojets/{slug}/experiences/{experiment_id}` (`?version=` pour une version passée, en lecture seule ; un ancien id de version est résolu puis redirigé en 302 par le `page_router`, sans `?version=` si c'est la pointe, vers `/connexion` hors session, vers le µprojet si la version est introuvable), `/microprojets/{slug}/evolution` (nouvelle : « Évolution des structures », diagramme des pistes, versions et refs ; liée depuis la page µprojet et la fiche), `/microprojets/{slug}/refs` (302 vers `/evolution`) |
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
  `ExperiencePage`, `DataViz`…) ; ses autres déclarations restent locales, dans une IIFE ou un
  objet. **Écarts, tels qu'ils sont** (les regrouper sous un objet par plugin est un chantier à
  part) :
  - les **contrôleurs de page** (un par page : `lots.js`, `area.js`, `atlas.js`…) et le
    **constructeur** (`structures/static/builder/*.js`, une seule page découpée en fichiers qui
    partagent `state`, `slug`, `showError`) déclarent au premier niveau : ces noms ne sortent pas
    de leur page ;
  - le noyau expose ses helpers sans préfixe : `api`, `apiErrorMessage` (`api.js`), `escapeHtml`,
    `initials`, `formatDate`, `timeAgo`, `formatDuration`, `elapsedLabel`, `routeParams` (`ui.js`),
    `timeline*` (`timeline.js`) ;
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
    `lots/lot-picker.js` (`mountLotAssign`), `library/library-files.js`, `accounts/session.js`. Une
    page qui en utilise une la charge elle-même ; un nom nouveau ne doit pas en recouvrir un de
    cette liste ;
  - `notebook.js` et `external_images/gallery.js` gardent un état de premier niveau (`notebookCtx`,
    `galleryCtx`, `galleryMounts`…) mais ne lisent que le `ctx` reçu (voir plus bas).
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
  formulaire d'intention), `tags-refs.js`, `structure-view.js` (structure, couches, campagne,
  comparaison, images de la structure), `plates.js` (plaques suivies), `versions.js` (frise,
  historique, pistes filles, liens), `conclusion.js`, `advanced.js` (fusion, suppression),
  `report.js`. Ceux des autres plugins suivent : `evidence/static/evidence-panel.js`,
  `external_images/static/gallery.js`, `lots/static/lot-picker.js`, `notebook/static/notebook.js`.
- `ctx` est un objet explicite, le même d'un rechargement à l'autre : `microprojectSlug`,
  `experimentId`, `versionId`, `isTip` (la pointe, ouverte sans `?version=`), `role`, `canEdit`
  (éditeur sur la pointe), `detail`, `reload()`, `showError(err, box?)` ; s'y ajoutent, pour ne pas
  recharger chacun la même chose, `microproject`, `versions`, `process`, `variants()` (la matrice
  d'une campagne, un appel par chargement), `write(call, box?)` et `setDataCount(key, n)`, par
  lequel un panneau de l'onglet « Données » qui lit sa propre ressource (cahier, galerie) déclare
  son compte. Aucun module ne lit de globale de la page.
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
- Le vocabulaire d'une étude (types d'étape et leurs paramètres, décisions, résultats d'un objectif)
  est dans `experiments/static/vocabulary.js` (global `ExperimentVocabulary`), chargé par la fiche
  et l'atlas.
- Écarts : `lot-picker.js` sert aussi au graphe de filiation, où `ExperiencePage` n'existe pas ; il
  ne s'enregistre donc que `if (typeof ExperiencePage !== "undefined")`. `notebook.js` garde des
  déclarations de premier niveau (état du cahier, rendu d'une vue) mais ne lit que le `ctx` reçu.
  Chaque panneau de l'onglet « Données » lit sa propre sous-ressource, pour la version affichée
  (`?version=`) ; le repère de l'onglet
  additionne `detail.evidence_count` et ce que déclarent les panneaux (`ctx.setDataCount`).

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
