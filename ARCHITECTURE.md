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
   `depends_on`, et seulement leurs modules publics (`service`, `models`, `deps`, `schemas`), jamais
   leur `api`. Le noyau n'importe aucun plugin.
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
| `plugin.py` | `Plugin`, `Page`, `NavEntry`, `Migration` (dataclasses figées), et `check_dependencies(plugins)`, qui vérifie l'ordre topologique au démarrage |
| `app.py` | `create_app(plugins=PLUGINS)` : migrations, `include_router` de chaque plugin, routes de pages, montage de `/static/<plugin>/` et `/static/kernel/`, exception handlers, middleware `Cache-Control: no-cache` |
| `db.py` | `data_dir()`, `connect()`, `get_conn()`, exécuteur de migrations versionnées (table `schema_migrations(plugin, migration_id, applied_at)`), `rebuild_table()` pour les changements non additifs (CHECK, NOT NULL) |
| `errors.py` | `DomainError` → `NotFound` (404), `Forbidden` (403), `Conflict` (409), `PreconditionFailed` (412), `InvalidInput` (422), `UpstreamError` (502), `Unavailable` (503) ; un handler unique renvoie `{"detail": str, "code": str}`. Un plugin peut sous-classer `DomainError` pour un statut qui lui est propre (`attachments.store.TooLarge` : 413, `too_large`), le même handler s'en charge |
| `locks.py` | `keyed_lock(namespace, key)` : un `threading.Lock` par clé (le serveur tourne en un seul processus) |
| `mail.py` | `send_email(to, subject, body)` : SMTP si `SPECTRE_SMTP_HOST`, sinon journalisation **sans le corps** hors `SPECTRE_EMAIL_DEBUG=1` |
| `pages.py` | Service des pages HTML d'un plugin, avec la barre du haut commune à la place du marqueur `<!-- spectre:topbar -->` (fil d'Ariane déclaré dans le marqueur : `crumb-id`, `crumb-text`) : marque, navigation construite à partir des `NavEntry` de tous les plugins (une entrée peut être réservée à certaines pages : `NavEntry.pages`), place de la session |
| `http.py` | Petits helpers HTTP : `created(response, location)`, conversion `ETag` / `If-Match` |
| `static/` | Front du noyau : `api.js` (client HTTP : JSON, `upload(FormData)`, `blob`, `If-Match`, redirection 401, erreurs 422 lisibles), `ui.js` (`escapeHtml`, `initials`, dates, durées, `routeParams(pattern)`), `shell.js` (barre du haut : navigation active), `kernel.css` (tokens et composants de la charte), `img/`, `vendor/` (d3, codemirror) |

```python
@dataclass(frozen=True)
class Plugin:
    name: str                              # identique en Python, sous /static/<name>/ et dans les tests
    depends_on: tuple[str, ...] = ()
    router: APIRouter | None = None        # routes /api de ce plugin
    page_router: APIRouter | None = None   # routes de pages spéciales (redirections)
    pages: tuple[Page, ...] = ()           # Page("/lots/{code}", "lot.html")
    nav: tuple[NavEntry, ...] = ()         # entrées de la barre du haut
    migrations: tuple[Migration, ...] = ()
    enabled: Callable[[], bool] = lambda: True   # ex. kpis_demo : SPECTRE_DEMO_DATA=1
```

Les plugins sont listés **dans l'ordre topologique** dans `spectre/plugins/__init__.py`
(`PLUGINS = (...)`). L'application est construite par `create_app()`, en mode factory pour
uvicorn (`spectre.kernel.app:create_app`). Aucun `app` n'est créé à l'import d'un module.

## 3. Les plugins

Les plugins sont listés dans l'ordre topologique. Chaque plugin ne dépend que des plugins
placés au-dessus de lui.

| # | Plugin | Responsabilité | Dépend de | Tables / stockage |
|---|---|---|---|---|
| 1 | `accounts` | Comptes, sessions, mot de passe, profil, rôle admin global. Fournit `deps.current_user` et `deps.require_admin` | — | `users`, `sessions`, `password_resets` |
| 2 | `search` | `GET /api/search`, qui agrège les fournisseurs déclarés par les autres plugins (`register_provider`) | accounts | — |
| 3 | `library` | Bibliothèque racine YAML de l'instance (matériaux, recettes, présets, briques, textes d'UI), chargeur générique avec cache mtime, registre `LibraryFile` alimenté par les plugins propriétaires, édition réservée à l'admin | accounts | `data_dir/library/*.yml` (copiés depuis `library/defaults/` au premier démarrage, et les `*.yml` d'un `<dépôt>/library` d'avant par-dessus) |
| 4 | `areas` | Projets corporate (*management areas*), thématiques, objectifs. Pages accueil, projet et thématique | accounts | `management_areas`, `thematics`, `area_objectives` |
| 5 | `microprojects` | µprojets (CRUD, numéro, rattachement à un projet ou une thématique, recherche), membres, rôles, invitations. Fournit `deps.require_role` | accounts, areas, search | `microprojects`, `memberships`, `invitations` |
| 6 | `attachments` | Fichiers téléversés d'un µprojet (blob + sidecar), types, tailles, service des octets | microprojects | `data/microprojects/<slug>/attachments/` |
| 7 | `structures` | Pont StructureForge : matériaux, recettes, simulation, aperçu de campagne DOE, rendu SVG, **types de structure** (`process`, `campaign`, `images`) exposés par `kinds.py`. Pages du constructeur | accounts, library, attachments | — |
| 8 | `process_library` | Structures enregistrées, présets d'étape, briques technologiques (portées `builtin` / `shared` / `microproject`). Pages bibliothèque, présets, briques | structures, microprojects, library | JSON par portée |
| 9 | `experiments` | Pistes d'étude et versions (dépôt Follow d'un µprojet) : création, évolution, statut, conclusion, étiquettes, entités physiques, fusion, suppression, diff, filiation, refs, statistiques et frise transverses. Seul point d'écriture vers Follow (`service.amend`) | microprojects, structures, attachments | `data/microprojects/<slug>/follow/` |
| 10 | `evidence` | Preuves d'une étude, liens, images, annotations | experiments, attachments | métadonnées Follow |
| 11 | `intent_forms` | Formulaires d'intention (portées) et formulaire actif d'un µprojet | experiments, microprojects | JSON + `follow/commit_form.yml` |
| 12 | `wafers` | Index des plaques suivies, clé `wafer_key`, passeport d'une plaque, recherche par lasermark et par FDL, politique de visibilité | experiments, search | cache mémoire |
| 13 | `lots` | Lots de fabrication, leurs wafers et leurs thématiques visées, Gantt | wafers, areas, experiments, search | `lots`, `lot_wafers`, `lot_thematics` |
| 14 | `links` | Liens entre µprojets et entre entités physiques | microprojects, experiments | `microproject_links`, `entity_links` |
| 15 | `atlas` | Vue graphe d'un projet corporate | areas, microprojects, experiments, links | — |
| 16 | `characterization` | Types de données de caractérisation (PRISM, ou démo via le Protocol `DataSource`) : catalogue, requêtes, graphiques documentaires. Seul module qui importe `prism` | accounts | cache PRISM sous `data_dir/prism` |
| 17 | `notebook` | Cahier de données d'une étude : instantanés et vues DataViz | characterization, experiments | `snapshots/`, métadonnées Follow |
| 18 | `external_images` | Galerie d'images externes référencées (TEM, scans) d'une étude, limitée aux racines autorisées | experiments | métadonnées Follow |
| 19 | `kpis` | Registre de KPI (`register`) et séries mensuelles d'un projet corporate | areas, experiments | — |
| 20 | `kpis_demo` | Séries et fiche d'étude fictives. **Actif seulement si `SPECTRE_DEMO_DATA=1`** | kpis, structures | — |
| 21 | `docs` | Pages de documentation (contenu inchangé) | — | — |

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
| `ExperiencePage.registerPanel({key, mount(ctx)})` | `experiments/static/page.js` | evidence, notebook, external_images, lots |

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
- **Identifiants** : un seul segment, opaque, sans `/`. Paramètres nommés `{<ressource>_id}` ou
  `{<ressource>_slug}`. Pas de convertisseur `:path`.
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
  `GET /api/microprojects/{slug}/experiment-versions/{version_id}`.

## 5. Table de correspondance des routes

Rupture nette : les anciennes routes disparaissent sans alias. `{mp}` vaut
`{microproject_slug}` et `{exp}` vaut `{experiment_id}` (la piste).

### accounts

| Avant | Après |
|---|---|
| `POST /api/auth/register` | `POST /api/users` → 201 + session |
| `POST /api/auth/login` | `POST /api/sessions` → 201 `{user, expires_at}` ; identifiants refusés → 422 `invalid_credentials` (401 reste réservé à l'absence de session) |
| `POST /api/auth/logout` | `DELETE /api/sessions/current` → 204 |
| `GET /api/auth/me` | `GET /api/users/me` |
| `PUT /api/auth/me` | `PATCH /api/users/me` |
| `POST /api/auth/mot-de-passe` | `PUT /api/users/me/password` → 204 (mot de passe actuel faux → 422, jamais 401) |
| `POST /api/auth/mot-de-passe-oublie` | `POST /api/password-resets` → 202 |
| `POST /api/auth/reinitialiser` | `POST /api/password-resets/completions` `{token, password}` → 204 |
| `GET /api/auth/invitation/{token}` | `GET /api/invitations/{token}` (plugin microprojects, public ; `account_exists` pour proposer la connexion plutôt que l'inscription) |
| *(register avec invitation)* | `POST /api/invitations/{token}/acceptance` (connecté, même e-mail, sinon 403 `email_mismatch`) → 201 `{microproject: {slug, name}, role}` + `Location` vers l'adhésion `/api/microprojects/{mp}/members/{user_id}` ; `role` est le plus élevé du rôle déjà détenu et du rôle invité (une invitation ne rétrograde jamais) ; ajouter directement un membre supprime ses invitations en attente |

### search

| Avant | Après |
|---|---|
| `GET /api/microprojets/recherche`, `/api/plaques/recherche`, `/api/microprojets/recherche-fdl`, `/api/lots/recherche` (4 appels par frappe) | `GET /api/search?q=&types=` → `[{type, label, detail, badge, url}]` |

### areas · kpis · kpis_demo

| Avant | Après |
|---|---|
| `GET /api/management` | `GET /api/areas` (chaque projet expose `is_system`, `can_delete`, `horizon_months` calculé par le serveur) |
| `POST /api/management` | `POST /api/areas` → 201 |
| `GET /api/management/{slug}` | `GET /api/areas/{area_slug}` (projet, thématiques, objectifs) |
| `PUT /api/management/{slug}` | `PATCH /api/areas/{area_slug}` |
| `DELETE /api/management/{slug}` | `DELETE /api/areas/{area_slug}` → 204 (409 pour un projet système) |
| `POST /api/management/{slug}/microprojets` | `PATCH /api/microprojects/{mp}` `{area, thematic}` |
| `POST /api/management/{slug}/thematiques` | `POST /api/areas/{area_slug}/thematics` → 201 |
| `GET /api/management/{slug}/thematiques/{t}` | `GET /api/areas/{area_slug}/thematics/{thematic_slug}` ; la frise : `GET /api/experiment-timeline?area=&thematic=` |
| `PUT /api/management/{slug}/thematiques/{t}` | `PATCH /api/areas/{area_slug}/thematics/{thematic_slug}` |
| `DELETE /api/management/{slug}/thematiques/{t}` | `DELETE …` → 204 |
| *(nouveau)* | `GET /api/thematics?area=` : liste à plat `{id, slug, name, area}` (remplace `/api/lots/thematiques`) |
| `POST /api/management/{slug}/objectifs` | `POST /api/areas/{area_slug}/objectives` → 201 |
| `PUT /api/management/{slug}/objectifs` (réordonner) | **supprimée** (aucun appelant) |
| `PUT /api/management/{slug}/objectifs/{id}` | `PATCH /api/areas/{area_slug}/objectives/{objective_id}` |
| `DELETE /api/management/{slug}/objectifs/{id}` | `DELETE …` → 204 |
| `GET /api/management/{slug}/tendances` | `GET /api/areas/{area_slug}/kpis` |
| `GET /api/management/{slug}/tendances/{kpi}?mois=&variante=` | `GET /api/areas/{area_slug}/kpis/{kpi_key}?months=&variant=` |
| `GET …/tendances/{kpi}/etudes/{study_id}` | `GET /api/areas/{area_slug}/kpis/{kpi_key}/studies/{study_id}` (kpis_demo) |
| `GET /api/atlas?theme=` | `GET /api/areas/{area_slug}/atlas` (plugin atlas) |

### microprojects

| Avant | Après |
|---|---|
| `GET /api/microprojets` | `GET /api/microprojects` (les miens) ; `?scope=all` (admin) ; `?area=&thematic=` |
| `GET /api/microprojets/recherche?q=` | `GET /api/microprojects?q=&limit=` (toute la société, champs réduits) |
| `GET /api/microprojets/tous` | `GET /api/microprojects?scope=all` |
| `GET /api/microprojets/code/{code}` | `GET /api/microprojects?code=` |
| `POST /api/microprojets` | `POST /api/microprojects` → 201 |
| `GET /api/microprojets/{slug}` | `GET /api/microprojects/{mp}` |
| *(nouveau)* | `PATCH /api/microprojects/{mp}` `{name, description, area, thematic}` |
| `DELETE /api/microprojets/{slug}` | `DELETE /api/microprojects/{mp}` → 204 |
| `GET …/members` | `GET /api/microprojects/{mp}/members` |
| `POST …/members` (upsert + invitation) | `POST /api/microprojects/{mp}/members` `{email, role}` → 201 (409 déjà membre ; 404 `no_account`) |
| *(changement de rôle par POST)* | `PATCH /api/microprojects/{mp}/members/{user_id}` `{role}` (409 si plus aucun owner) |
| `DELETE …/members/{user_id}` | `DELETE …` → 204 (409 pour le créateur ou le dernier owner) |
| `GET …/invitations` | `GET /api/microprojects/{mp}/invitations` (en attente, non expirées, **sans le jeton**) |
| *(implicite dans POST members)* | `POST /api/microprojects/{mp}/invitations` `{email, role}` → 201 |
| `DELETE …/invitations/{token}` | `DELETE /api/microprojects/{mp}/invitations/{invitation_id}` → 204 |
| `GET …/entites/historique` | `GET /api/wafers?microproject={mp}` (plugin wafers) |
| `GET /api/microprojets/recherche-fdl` | `GET /api/wafers?fdl=` (plugin wafers) |

### attachments

| Avant | Après |
|---|---|
| `POST /api/microprojets/{slug}/images` | `POST /api/microprojects/{mp}/attachments` (multipart, `purpose=evidence`) → 201 `{id, url, …}` |
| `POST /api/microprojets/{slug}/structures/images` | idem avec `purpose=structure` |
| `GET /api/microprojets/{slug}/pieces-jointes/{id}` | `GET /api/microprojects/{mp}/attachments/{attachment_id}/content` |
| *(nouveau)* | `GET /api/microprojects/{mp}/attachments/{attachment_id}` (métadonnées) |
| `POST/DELETE …/experiences/{ref}/pieces-jointes[/{id}]` | **supprimées** (aucun appelant front : on passe par attachments puis evidence) |

### structures · library

| Avant | Après |
|---|---|
| `GET /api/microprojets/{slug}/materials` | `GET /api/materials` |
| `GET /api/microprojets/{slug}/recettes` | `GET /api/recipes` → `{deposition: [...], etch: [...]}` (exception à « les autres sont un tableau » : le constructeur lit les recettes par sorte d'étape) |
| `POST /api/microprojets/{slug}/structures/simulate` | `POST /api/simulations` → 200 (calcul, rien n'est stocké) |
| `POST /api/microprojets/{slug}/structures/variantes` | `POST /api/campaign-previews` → 200 (plafond `MAX_CAMPAIGN_ENTITIES`, 422 au-delà) |
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
| `PUT …/presets-etapes/{name}?partagee=` | `PATCH /api/step-presets/{preset_id}` (la portée est modifiable) |
| `DELETE …/presets-etapes/{name}?partagee=` | `DELETE /api/step-presets/{preset_id}` → 204 |
| `…/structures-sauvegardees[/{name}]` | `/api/saved-structures[/{structure_id}]` (même schéma) |
| `…/briques-technologiques[/{name}]` | `/api/tech-bricks[/{brick_id}]` (même schéma) |

### experiments

| Avant | Après |
|---|---|
| `GET /api/microprojets/{slug}/experiences?status=&offset=&limit=` | `GET /api/microprojects/{mp}/experiments?status=all\|running\|concluded&q=&offset=&limit=` → `{items, total}` |
| `POST …/experiences` | `POST /api/microprojects/{mp}/experiments` `{…, structure: {kind: "process", …}}` → 201 |
| `POST …/experiences/image` | idem, avec `structure: {kind: "images", images: [...]}` |
| `POST …/experiences/campagne` | idem, avec `structure: {kind: "campaign", …, plan}` ; `from_version` pour partir d'une version existante |
| `GET …/experiences/{ref}` | `GET /api/microprojects/{mp}/experiments/{exp}` (dernière version, `ETag`) |
| `GET …/experiences/{ref}/timeline` | `GET …/experiments/{exp}/versions` |
| *(nouveau)* | `GET …/experiments/{exp}/versions/{version_id}` |
| `POST …/{ref}/evoluer` | `POST …/experiments/{exp}/versions` `{structure: {kind: "process", …}, …}` + `If-Match` → 201 |
| `POST …/{ref}/evoluer-image` | idem, avec `structure: {kind: "images", …}` |
| `POST …/{ref}/dessin` | `PUT …/experiments/{exp}/structure-images` |
| `POST …/{ref}/conclure` | `PUT …/experiments/{exp}/conclusion` |
| `POST …/{ref}/statut` | `PUT …/experiments/{exp}/status` `{status, hold_reason}` |
| `POST …/{ref}/etiquettes` | `PUT …/experiments/{exp}/tags` `{tags}` |
| `POST …/{ref}/entites` | `PUT …/experiments/{exp}/entities` `{entities}` |
| `POST …/{ref}/combiner` | `POST …/experiments/{exp}/merges` `{other_experiment_id}` → 201 |
| `GET …/{ref}/process` | `GET …/experiments/{exp}/process?version=` |
| `GET …/{ref}/diff`, `GET …/{ref}/diff-externe` | `GET …/experiments/{exp}/structure-diff?version=&against_version=&against_experiment=&against_microproject=` |
| `GET …/{ref}/matrice` | `GET …/experiments/{exp}/variants` |
| `DELETE …/experiences/{ref}` | `DELETE …/experiments/{exp}` → 204 (supprime la piste jusqu'au point de fourche ; 409 si quelque chose en découle) |
| `POST …/{ref}/ref` | `POST /api/microprojects/{mp}/refs` `{experiment_id, version_id?, name}` → 201 |
| `GET …/refs`, `GET …/refs/graphe` | `GET /api/microprojects/{mp}/refs` → `{refs, edges}` |
| `GET /api/microprojets/{slug}/filiation` | `GET /api/microprojects/{mp}/lineage` (les nœuds portent `version_id` et `experiment_id` ; plus de badge de lot, que le front compose via `lotsApi`) |
| `GET /api/microprojets/{slug}/graphe.html` | **supprimée**, ainsi que la page `/microprojets/{slug}/graphe` |
| *(dans les listes de µprojets)* | `GET /api/experiment-stats?microproject=&area=` → `[{microproject, running, concluded, abandoned, wafers}]` |
| *(dans la thématique)* | `GET /api/experiment-timeline?area=&thematic=` (champs masqués pour les non-membres) |
| *(nouveau)* | `GET /api/microprojects/{mp}/experiment-versions/{version_id}` → `{experiment_id, version_id}` (résolution des anciens liens) |

### evidence · notebook · external_images

| Avant | Après |
|---|---|
| *(dans le détail)* | `GET …/experiments/{exp}/evidence` |
| `POST …/{ref}/preuves` | `POST …/experiments/{exp}/evidence` → 201 (le type `graph`, qui allait chercher une URL arbitraire, n'est plus proposé à la création) |
| `POST …/{ref}/preuves/{id}/annotations` | `PUT …/experiments/{exp}/evidence/{evidence_id}/annotations` |
| `GET /api/microprojets/{slug}/donnees/sources` | `GET /api/characterization/data-types?by_wafer=true&status=implemented` |
| `POST …/donnees/instantanes` | `POST /api/microprojects/{mp}/snapshots` → 201 |
| `GET …/donnees/instantanes/{id}` | `GET /api/microprojects/{mp}/snapshots/{snapshot_id}` |
| *(dans le détail)* | `GET …/experiments/{exp}/notebook-entries` |
| `POST …/{ref}/cahier` | `POST …/experiments/{exp}/notebook-entries` → 201 |
| `PUT …/{ref}/cahier/{entry_id}` (+ `move`) | `PATCH …/experiments/{exp}/notebook-entries/{entry_id}` (`position` entier) |
| `DELETE …/{ref}/cahier/{entry_id}` | `DELETE …` → 204 |
| *(dans le détail)* | `GET …/experiments/{exp}/image-sets` |
| `POST …/{ref}/data` | `POST …/experiments/{exp}/image-sets` → 201 |
| `PATCH …/{ref}/data/{id}/epingle` | `PATCH …/experiments/{exp}/image-sets/{set_id}` `{pinned_index}` |
| `DELETE …/{ref}/data/{id}` | `DELETE …/experiments/{exp}/image-sets/{set_id}` → 204 |
| `GET /api/microprojets/{slug}/data/image?chemin=` | `GET …/experiments/{exp}/image-sets/{set_id}/images/{index}` (chemin résolu côté serveur, jamais reçu du client) |
| `GET /api/microprojets/{slug}/data/parcourir?dossier=` | `GET /api/microprojects/{mp}/external-images?directory=` (editor ; limité à `SPECTRE_EXTERNAL_IMAGE_ROOTS`, désactivé si la variable n'est pas définie) |

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
| `POST …` | `POST /api/intent-forms` → 201 |
| `PUT …/{name}` | `PATCH /api/intent-forms/{form_id}` |
| `DELETE …/{name}?partagee=` | `DELETE /api/intent-forms/{form_id}` → 204 |
| `GET …/formulaire-actif` | `GET /api/microprojects/{mp}/active-intent-form` → `{form, origin, outdated}` (404 `no_active_intent_form` si aucun) — lu depuis `commit_form.yml`, la seule vérité |
| `POST …/formulaire-actif` `{name}` / `{name: null}` | `PUT …/active-intent-form` `{intent_form_id}` / `DELETE` → 204 |

### wafers · lots · links

| Avant | Après |
|---|---|
| `GET /api/plaques/recherche?q=` | `GET /api/wafers?q=` |
| `GET /api/plaques/{lasermark}` | `GET /api/wafers/{wafer_key}` (sans les lots : `GET /api/lots?wafer=`) |
| `GET /api/lots?statut=actifs\|sortis\|annules\|tous` | `GET /api/lots?status=planned,wip,hold,done,cancelled&q=&wafer=&code=&view=summary` |
| `GET /api/lots/recherche`, `/selection` | `GET /api/lots?q=…`, `GET /api/lots?view=summary&status=…` |
| `GET /api/lots/thematiques` | `GET /api/thematics` (plugin areas) |
| `POST /api/lots` | `POST /api/lots` → 201 (409 code déjà pris) |
| `GET/PUT/DELETE /api/lots/{code}` | `GET` / `PATCH` / `DELETE /api/lots/{lot_id}` (204) ; le code devient un champ filtrable |
| `POST /api/lots/{code}/wafers` | `POST /api/lots/{lot_id}/wafers` `{lasermarks}` → 201 |
| `DELETE /api/lots/{code}/wafers/{lasermark}` | `DELETE /api/lots/{lot_id}/wafers/{wafer_key}` → 204 (404 si absent) |
| `PUT /api/lots/{code}/thematiques` | `PUT /api/lots/{lot_id}/thematics` `{thematic_ids}` |
| `POST /api/liens-projets` | `POST /api/microproject-links` → 201 (409 doublon) |
| `DELETE /api/liens-projets/{id}` | `DELETE /api/microproject-links/{link_id}` → 204 |
| *(nouveau)* | `GET /api/microproject-links?microproject=&area=` |
| `POST /api/liens-entites` | `POST /api/entity-links` `{a: {microproject, experiment_id, entity_index}, b: {…}, note}` → 201 (désigne la piste ; les lignes existantes sont migrées) |
| `DELETE /api/liens-entites/{id}` | `DELETE /api/entity-links/{link_id}` → 204 |
| *(nouveau)* | `GET /api/entity-links?microproject=&area=` |

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
| areas | `/`, `/management/{slug}`, `/management/{slug}/thematiques/{thematique_slug}` |
| atlas | `/management/{slug}/atlas` |
| microprojects | `/microprojets/{slug}`, `/p/{code}` (redirection, **après** contrôle de session), `/projets/{rest}` (redirection héritée) |
| experiments | `/microprojets/{slug}/experiences/{experiment_id}` (`?version=` pour une version passée ; un ancien id de version est résolu puis redirigé), `/microprojets/{slug}/refs` |
| structures | `/microprojets/{slug}/structures/nouvelle`, `/structures/image`, `/experiences/{experiment_id}/evoluer`, `/experiences/{experiment_id}/evoluer-image`, `/structures/bibliotheque/nouvelle`, `/structures/bibliotheque/{structure_id}`, `/briques-technologiques/bibliotheque/nouvelle`, `/briques-technologiques/bibliotheque/{brick_id}` |
| process_library | `/bibliotheque`, `/microprojets/{slug}/presets-etapes`, `/microprojets/{slug}/briques-technologiques` |
| intent_forms | `/microprojets/{slug}/formulaire-intention` |
| wafers | `/plaques/{lasermark}` |
| lots | `/lots`, `/lots/{code}` |
| characterization | `/donnees`, `/donnees/{key}` |
| docs | `/docs`, `/docs/guide`, `/docs/exemples`, `/docs/architecture` |

Supprimée : `/microprojets/{slug}/graphe`.

## 6. Front

- Scripts classiques (`<script src>`), sans bundler ni framework. Chaque fichier n'expose qu'un
  global nommé d'après son plugin (`lotsApi`, `ExperiencePage`, `DataViz`…). Les autres
  déclarations restent locales, dans une IIFE ou un objet.
- Ordre de chargement d'une page :
  1. noyau : `/static/kernel/api.js`, `ui.js`, `shell.js` ;
  2. session et recherche : `/static/accounts/session.js`, `/static/search/topbar-search.js` ;
  3. les `client.js` des plugins utilisés ;
  4. le contrôleur de la page.
- Un module réutilisé par plusieurs pages reçoit son contexte en paramètre
  (`mount(el, {microprojectSlug, canEdit, onChange})`) et ne lit jamais une globale de la page
  hôte.
- Les paramètres de chemin d'une page se lisent avec `routeParams("/microprojets/{slug}/...")`
  (dans `ui.js`), jamais par position dans `location.pathname`.
- CSS : `kernel.css` (tokens et composants de la charte, voir `design-system/spectre/MASTER.md`),
  plus `/static/<plugin>/<plugin>.css` chargé par les pages qui en affichent les composants.

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
