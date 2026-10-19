# Socle data : composants Lumière, hôtes Spectre

*Proposition d'architecture, v3 du 2026-10-19. Rien n'est implémenté.*

*Cette v2 remplace la v1. La v1 liait n'importe quel bloc à n'importe quel type par un moteur de rôles, et affichait les blocs dans des iframes. Ici, c'est le modèle que tu as décrit : des composants écrits pour chaque hook, un catalogue de compatibilité dans Lumière, et Spectre comme cadre.*

*La v2.1 intègre deux relectures critiques : l'une a vérifié chaque référence au code, l'autre a déroulé le parcours gravure → mesure → rafraîchissement de bout en bout.*

*La v3 (2026-10-19) ajoute ce que tu as demandé le 19 : **un seul système de rapports**, Lumière, qui remplace les trois exporteurs éparpillés (analyse, fiche d'étude, et bientôt plaque) ; un **plugin `lumiere`** avec une page où l'on compose un modèle de rapport slide par slide, « comme un mini PowerPoint » ; le **cahier de mesures** rendu comme un rapport Lumière ; et la **frise des mesures** dans le parcours MES et le flux JIRA. Ces ajouts sont au §4.6, §4.7 et dans le plan du §5 ; le reste du document est inchangé.*

## En bref

- **Lumière + PRISM se suffisent.** Ils produisent déjà des rapports seuls ; Spectre n'est jamais requis.
- **Pour chaque hook PRISM, un ou plusieurs composants Lumière.** Un composant, c'est :
  - une recette de données ;
  - un ou plusieurs blocs ;
  - des réglages.

  Chaque composant déclare ses hooks. **Le catalogue de compatibilité hook → composants vit dans Lumière.**
- **Spectre est un cadre.** Ses hôtes sont la fiche plaque, le cahier de manip, l'analyse, le rapport Lumière brut et la tendance.
  - Un hôte stocke `{composant, version, réglages}` et fournit les plaques.
  - Il donne l'accès aux données (sa passerelle PRISM) et un contexte : les événements datés et les URL d'images.
- **Les nouveaux blocs sont « montables »**, c'est-à-dire insérés directement dans les pages Spectre, sans iframe.
- **Dans le cahier, un composant montre les données figées à l'ajout.** Un badge annonce les nouvelles mesures, et **Rafraîchir** prend un nouvel instantané.
- **Chaque date de mesure est reliée au changement qui l'a précédée**, dans le même graphe :
  - Spectre fournit les événements (version de l'étude, étape ajoutée, étape MES) ;
  - Lumière fait la jointure « au plus tard » et ajoute `__etat` ;
  - la boîte « 02 · v1.3 gravure 2 » se place entre « 01 · v1.2 » et « 03 · v1.4 », et la légende renvoie à chaque version.
- **Un seul système de rapports : Lumière** (v3). Un rapport est un *modèle* composé dans la page `/lumiere` (des slides, une grille par slide, un composant par cellule), appliqué à un *contexte* (une plaque, une analyse, une étude, un µprojet, un lot). Le bouton « Rapport » de chaque hôte ouvre la liste des modèles qui conviennent à son contexte et télécharge le HTML autonome que `ReportBuilder` produit. Les exporteurs maison (`meta_analysis/report-html.js`, `experiments/report.js`) disparaissent ; le cahier de mesures devient un modèle Lumière.
- **Les mesures se voient sur la frise de la plaque** (v3) : les actions MES de mesure, les tests PRISM et les sessions de mesure des hooks sont posés sur la même chronologie que les étapes MES et JIRA - dans le parcours MES de la page plaque, et comme composant Lumière `wafer.timeline`.

---

## 1. Le modèle

```
┌──────────────────────────── PRISM ────────────────────────────┐
│ hooks (eqe, pl, el_pattern, meb_g4…) · cache par plaque        │
│ wafer_tests, testled_updated_since : sessions et remesures     │
└───────────────▲───────────────────────────────────────────────┘
                │ runner(hook, params) -> DataFrame
┌───────────────┴──────────── LUMIÈRE (autonome) ───────────────┐
│ sources/     recettes de données, runner injectable            │
│ components/  Component · catalog() · compatible(hook)          │
│              timeline.tag_states() : jointure mesure ↔ événement│
│ blocks/      blocs existants (inchangés) + nouveaux montables  │
│ _mount.py    MountableBlock + window.LUMIERE (JS)              │
│ embed.py     render_fragment() · embed_css() · asset Plotly    │
│ ReportBuilder : rapport HTML autonome (inchangé)               │
└───────────────▲───────────────────────────────────────────────┘
                │ catalogue, fragments, rapports
┌───────────────┴──────────── SPECTRE (cadre) ──────────────────┐
│ datasets   passerelle PRISM unique = le runner de Spectre      │
│            fraîcheur (sessions) · jetons d'image · moteur de   │
│            composants (registre, file de rendu, cache)         │
│ lumiere    adaptateur : seul importeur de lumiere_report       │
│ wafers.timeline   événements datés d'une plaque / d'une étude  │
│ hôtes : cahier · fiche plaque · analyse · rapport brut · tendance│
└───────────────────────────────────────────────────────────────┘
```

**Dépendances.** Lumière ne sait rien de Spectre. Spectre importe Lumière dans un seul module et lui injecte son `runner`, ses événements et son `url_for`. Sans Spectre, un rapport Lumière utilise `prism_runner` et groupe par date de mesure.

---

## 2. Côté Lumière

### 2.1 Le composant

```python
# lumiere_report/components/base.py
class Component(ABC):
    key: str                     # "eqe.box-by-state" : minuscules, chiffres, points, tirets
                                 # (regex du cahier, notebook/service.py:73 — pas de « _ »)
    label: str
    version: int
    hooks: tuple[str, ...]       # ("eqe",) | ("eqe", "el_pattern") -> catalogue de compatibilité
    wafers_min: int = 1
    wafers_max: int | None = None
    time_cols: tuple[str, ...] = ()        # par préférence : ("measured_at", "Test_Date") ; le 1er présent sert
    keep: Literal["scalars", "vectors", "all"] = "scalars"   # ce qu'un hôte figé conserve
    options: dict[str, OptionSpec]         # JSON ; formulaire généré par l'hôte

    def load(self, wafers, runner, options) -> dict[str, pd.DataFrame]: ...
        # données BRUTES, sans contexte : c'est exactement ce qu'un hôte fige
    def enrich(self, frames, options, ctx) -> dict[str, pd.DataFrame]: ...
        # au rendu, jamais stocké : tag_states, url_for, rôles. Une implémentation par défaut est fournie
    def blocks(self, keys: dict[str, str], options, ctx) -> list[Block]: ...   # pur
    def migrate_options(self, options: dict, from_version: int) -> dict: ...

@dataclass
class Context:
    events: pd.DataFrame | None = None         # {wafer|None, at, precision, kind, label, url, rank}
    url_for: Callable[[str], str] | None = None
    roles: Mapping[str, str] | None = None     # plaque -> "ref" | "comparée" (analyse)
    aliases: Mapping[str, str] | None = None   # ancien nom -> clé de plaque (renommages)
    namespace: str = ""                        # "c_<uuid>" : préfixe des clés __DATA_STORE__
```

Le runner a la forme `runner(hook, params) -> DataFrame`. Dans `params`, `refresh` vaut `True` ou une liste de plaques.

Fonctions du catalogue :
- `catalog()` donne `{key: Component}` ;
- `compatible(hook)` donne les composants d'un hook ;
- `get(key)` lève `UnknownComponent`. L'hôte affiche alors « composant inconnu » ; il fait de même pour une version plus récente que celle installée.

**`timeline.tag_states(frame, events, time_col, wafer_col)`** obéit à cinq règles, toutes vérifiées par un test :
1. **Les événements d'étude (`wafer=None`) sont diffusés à toutes les plaques** avant le `merge_asof(by=wafer)`. Sinon pandas les ignore : c'est testé sous pandas 3.0.6.
2. **En précision jour, la mesure vaut `jour + 23:59:59.999`.** Une mesure faite le jour d'une gravure se range donc *après* elle. Aujourd'hui, `Test_Date` vaut minuit et la rangerait avant.
3. **`__etat = f"{rang:02d} · {libellé}"`, unique.** Le rang est l'ordre global des événements de la famille. Deux reprises MES du même nom ne fusionnent donc pas, et un tri alphabétique est un tri chronologique. Une mesure antérieure à tout événement vaut « 00 · état initial ».
4. Les autres colonnes produites sont :
   - `__etat_rang` (entier) ;
   - `__etat_url` ;
   - `__etat_couleur` (hexadécimal, pour les blocs qui ne colorent qu'en hex) ;
   - `__wafer_etat = f"{plaque} · {rang:02d} · {libellé}"`, pour les carrousels triés par ordre alphabétique (`wafer_maps.py:359`).
5. Les unités de temps sont normalisées en `ns` : `merge_asof` refuse `[us]` face à `[ns]`.

**Tests.** Un test de contrat paramétré sur `catalog()`, avec un `fake_runner` par hook (modèle : `wafer_tracking/_mock.py:184`). Il vérifie que :
- `load` ne renvoie que les jeux déclarés ;
- chaque bloc se rend dans un magasin préfixé, sans clé nue `"main"` ;
- les réglages font l'aller-retour en JSON ;
- `migrate_options` est appliqué ;
- `wafers_min/max` sont respectés ;
- `tag_states` gère une séquence gravure/mesure fabriquée, cas du même jour compris.

Lumière publie aussi un **fragment de référence** `{html, store, needs, etats}`. Le test JS de Spectre le lit.

### 2.2 Le contrat « montable » des nouveaux blocs

Il reprend WaferExplorer (`_js_core.py:3036` `whenVisible`, `:2391` `destroy`) :
1. un identifiant uuid ;
2. un CSS limité à une classe racine, avec les variables déclarées sur cette racine ;
3. une bibliothèque JS idempotente (`window.LUMIERE.libs[nom]`) ;
4. une configuration JSON dans la racine ;
5. des données sous une clé préfixée ;
6. un `boot` idempotent, qui ne dessine que lorsque le bloc est visible ;
7. un `destroy` qui libère les écouteurs (`AbortController`) et purge Plotly ;
8. aucune écriture dans `location.hash` ;
9. `ctx.emit("select", {etat, wafer})`.

Le socle de ce contrat est `lumiere_report/_mount.py` (`MountableBlock` et `window.LUMIERE`).

**Les blocs existants servent tels quels**, montés en ligne. L'hôte recrée leurs scripts, charge Plotly avant le montage, donne un uuid à `_id` et envoie un `resize` quand un onglet devient visible.
- **Ils n'émettent aucun clic.** KPIExplorer, par exemple, n'a pas de `plotly_click`. Avec eux, le lien état → version passe par la **légende des états**, que Spectre dessine sous le composant. Le clic sur une boîte demande un nouveau bloc montable (§2.4).
- Leurs écouteurs globaux fuient au démontage, ce qui est acceptable.
- GraphBuilderV2/V3 sont exclus (applications pleine page).

### 2.3 Changements d'infrastructure dans Lumière (aucun bloc touché)

| Changement | Pourquoi | Où |
|---|---|---|
| `runner` injectable | Spectre fournit sa passerelle (cache, démo, erreurs). Le motif existe déjà dans `tracker.py:31`, `cd_data.py:40` et `vlc_data_loader.py:139` | `sources/_runner.py` ; `runner=` dans `load_led_dataset`, `load_pl_dataset`, `load_el_images` |
| `make_json_safe` garde l'ISO à la seconde | Aujourd'hui elle tronque tout `datetime64` en `%Y-%m-%d` (`prism_data.py:78`), alors qu'une ligne lue depuis le cache PRISM garde l'heure. Le comportement change selon la source | `sources/prism_data.py` |
| Imports paresseux | `import lumiere_report` prend ~12 s, exige `prism` (`cd_spc/_images.py:41`) et charge tous les blocs (`_helpers.py:147`) | `__getattr__` PEP 562 dans `__init__.py` et `blocks/__init__.py` |
| Plotly en local | `assets/` n'existe pas, donc tout part du CDN (`_assets.py:21-29`) | `assets/plotly-2.35.2.min.js` + `asset_path("plotly")` |
| CSS intégrable | `_CSS` contient un reset `*`, `:root` et `body{height:100vh}` (`_assets.py:90-123`, `:767-776`), en collision avec `kernel.css` | `_CSS_PAGE` / `_CSS_BLOCKS` ; `embed_css(scope=".lm-embed")` |
| **Paquetage** | Spectre (`pyproject.toml:15`, `prism…@master`) et Lumière (`prism…git`, sans référence) déclaraient PRISM par deux URL directes différentes, et pip renvoyait `ResolutionImpossible` (reproduit). **Fait le 2026-10-19** : Lumière déclare exactement la même URL `…prism.git@master` (non commité dans son dépôt) : une seule installation de PRISM, partagée. Quand PRISM aura un tag, les deux l'épinglent ensemble | `lumiere_report_engine/pyproject.toml` ; Lumière est versionné par tags |
| Nouveaux fichiers | `components/` (avec `embed.py`, dont `add_to_tab` et `render_fragment` sont **nouveaux**), `_mount.py`, `timeline.py` | – |

À signaler séparément, car ce sont des bugs de blocs :
- `cd_spc/_wafer_link.py:141-145` sous pandas 3 (2 tests en échec) ;
- `SyntaxWarning`s à `kpi_explorer_history.py:2054`, `stat_analysis.py:1538/1540` et `lumiere_tour.py:502`.

### 2.4 Premiers composants

| Composant | Hooks | `load` | Blocs | États |
|---|---|---|---|---|
| `eqe.box-by-state` | eqe | `load_led_dataset(runner=…)`, puis on ne garde que les colonnes scalaires (`scalar_columns(df)`). Pas `to_scalar_rows`, qui retire `EQE_max_iqr_outlier` (`history/store.py:41,61`). `keep="scalars"` | v1 : `SummaryBoxPlots(group_col="__etat", metrics={libellé: (col, unité)})`. Le tri alphabétique (`summary.py:136`) est chronologique grâce au préfixe de rang. **Puis `StateBoxPlot`**, un nouveau bloc montable (L1) : une boîte par état et par plaque, couleur par plaque, clic → `select` | x = état |
| `eqe.maps` | eqe | `load_led_dataset(runner=…)` **complet** : vecteurs et `Spectra`, lus par `curve_cols` et `spectra_col` (`wafer_maps.py:99-112`). `keep="all"` | `WaferMaps(wafer_col="__wafer_etat", colormap_cols=[…], filter_cols=["Optical_Sensor"], curve_cols=…, spectra_col="Spectra")` | une carte par plaque × état |
| `el.images` | el_pattern | `load_el_images(runner=…)` avec `full_path` **brut** ; date de session tirée du dossier `EL_Pattern_YYYYMMDD` | `enrich` ajoute `__img_url = ctx.url_for(full_path)`, puis `Imageviewer(image_col="__img_url", meta_cols=["__session"])` | `time_cols=("__session_date",)` |
| `eqe-el.explorer` | eqe + el_pattern | les deux | `WaferExplorerBlock(el_data=…, filter_cols=["Optical_Sensor","__etat"], remeasure_policy="all", deeplink=False)` | filtre ; couleur via `__etat_rang` |

Pourquoi pas KPIExplorer pour les boîtes ? Il **n'affiche par défaut que le dernier mois** (`trInit`, `kpi_explorer_history.py:1140-1145`), le filtre s'applique au box plot (`:1411`) et aucun paramètre ne le change. Une séquence gravure/mesure de plus d'un mois perdrait ses premiers états.

`load_led_dataset` exclut déjà NCEL et ref et pose le drapeau IQR global : la parité avec les rapports Lumière est donc automatique.

---

## 3. Côté PRISM

**Ce qui existe déjà** et suffit pour suivre les remesures au jour près :
- `wafer_tests` renvoie, par plaque, `PK_Test`, `Test_Type`, `Test_Date` et `TestStartDate` (`hooks/wafer_tests/query.sql:1-11`) : ce sont les sessions de mesure.
- `testled_updated_since` renvoie `last_test_date` et `n_testled` : c'est l'empreinte du badge.
- La relecture ciblée existe déjà dans Lumière : `_stale_in_cache`, puis `load_led_dataset(stale, refresh=True)` (`sources/history.py:78-87`, `:144-160`).
- `fetched_at` est déjà écrit dans chaque fichier de cache (`cache.py:150`). Il reste seulement à l'exposer dans `CacheResult`.

**Ce qui est nécessaire pour la précision à la minute (T1) :**
- **eqe v3** : `test_id` (`FK_Test`) et `measured_at` (`TestStartDate`, sinon `Test_Date`) dans les lignes eqe ; `yield_per_wafer` et le drapeau IQR calculés par (plaque, session).
- Aujourd'hui, `Test_Date` est tronqué au jour (`postprocessing/eqe.py:222`). Une gravure à 15 h entre deux mesures à 14 h 41 et 16 h 39 le même jour ne peut donc pas être placée. C'est arrivé sur 16L5C0E6MMB1 le 2026-08-04, et 31 plaques en cache ont un device mesuré deux fois le même jour.
- De plus, `yield_per_wafer` mélange aujourd'hui l'avant et l'après gravure (`eqe.py:229`).

**Utile ensuite :**
- pl en mode historique : aujourd'hui seule la dernière mesure est gardée (`pl.py:33-34`) ;
- el_pattern avec `folder` et `modified` ;
- ncel qui garde `Led_Name` ;
- `run_hook_cached(refresh=[plaques])` ;
- le schéma typé de la v1, désormais hors du chemin critique.

---

## 4. Côté Spectre

### 4.1 `datasets` (plugin cœur, `depends_on=("accounts",)`)

- **`gateway`**. C'est le seul `import prism`, qui remplace les 4 actuels. Il apporte :
  - une bascule démo unique et un `PRISM_DATA_DIR` unique ;
  - un traducteur d'erreurs qui garde les codes actuels (`upstream_error`, `sem_root_missing`…) ;
  - un mémo du catalogue ;
  - un single-flight par (hook, plaque).

  `gateway.runner(user)` est le runner donné à Lumière ; il accepte `refresh=True|[plaques]`.
- **`freshness`**. Il calcule l'empreinte de chaque plaque à partir de `testled_updated_since` et de `wafer_tests`, mémorisée 10 min. Il fournit `new_sessions(wafers, since_fingerprints)`.
- **`images`**. `url_for(path)` renvoie `/api/images/{token}` (HMAC, secret dans `.env`). Ce module réunit les 5 serveurs de fichiers actuels et généralise le rendu Pillow de sem_images (TIF, vignettes). Les jetons sont produits au rendu et ne sont jamais stockés.
- **`keys.compact`**, déplacé depuis `experiments/entities.py:49`.
- **`components`**, le moteur de composants vu par les hôtes :
  - `register_engine(engine)` : c'est `lumiere` qui s'y enregistre ;
  - `available()` lit `plugin_states` **à chaque requête**, si bien qu'éteindre `lumiere` à chaud est pris en compte ;
  - un sémaphore de 2 rendus ;
  - un cache de fragments indexé par (instantanés, composant, version, réglages, version de Lumière, empreinte des événements) ;
  - côté JS, une petite amorce qui affiche « Lumière non disponible » quand les statiques de `lumiere` ont été retirés de la page (`plugin_states.py:4-7`).

  Les hôtes n'importent que `datasets.components`, jamais `lumiere`.

### 4.2 `lumiere` (adaptateur optionnel)

- **Installation.** Un extra `spectre[lumiere]`, épinglé sur un tag de Lumière. Le `Dockerfile` installe l'extra. L'adaptateur vérifie une version minimale de `lumiere_report`. `enabled()` est vrai si l'import est possible.
- **Démarrage.** Lumière est importé en tâche de fond, pour ne pas faire payer ~12 s au premier rendu.
- **Routes.** `GET /api/lumiere/components?hook=` sert le catalogue. Le rendu passe par la route de chaque hôte, qui applique ses propres droits.
- **Réponse.** `{html, store, needs, etats: [{rang, label, url}]}`. C'est une exception écrite à « Pas de HTML sous /api » (`ARCHITECTURE.md:350`), avec le précédent de `structure_svg`.
- **JS `LumiereMount`.** Il :
  - charge Plotly et `embed_css` une seule fois ;
  - recrée les scripts du fragment ;
  - attribue le préfixe `c_<uuid>` ;
  - **met ses requêtes en file et réessaie sur 503** : un cahier de 10 entrées ne doit pas recevoir 8 erreurs ;
  - dessine la légende des états avec leurs liens ;
  - écoute `select` ;
  - démonte proprement.
- **Labo admin.** Un onglet « Composants compatibles » sur `/prism/donnees/{hook}`.

### 4.3 `wafers.timeline` : les événements datés

Ce module va dans `wafers`, qui est requis et dépend déjà d'experiments. Seul `notebook` ajoute `wafers` à son `depends_on`, sans cycle ni changement d'activation ; meta_analysis en dépend déjà.

```python
def events(user, *, study: StudyRef | None, wafers: list[str],
           family: Literal["versions", "mes", "aucun"] = "versions") -> list[Event]
# Event = {wafer|None, at (Paris, naïf), precision, kind, label, url, source}
```

| Famille | Source | Date | Libellé et lien |
|---|---|---|---|
| **versions** (défaut) | `history_of`, puis `compute_branch_versions` (`versioning.py:280`, qui ne donne que `{version, level}`). On garde `initial/major/minor`. Un `patch` n'est gardé que si `overridden_variants()` diffère de la version précédente ; il vaut alors pour la plaque `physical_tracking[i].sample_id` (`comparator/service.py:171`), qui peut manquer. Les `none` (écritures du cahier) sont ignorés | `created_at` (commit), corrigeable | `v{X.Y} · {intent}`. Lien : `fiche_url` ; lien secondaire : comparateur avec la version précédente |
| étapes ajoutées | différence de `step_ids_of` entre deux versions structurelles | date de la version | nom de l'étape |
| **mes** | `tracking.read` : `steps[].end_effective` (minute), `epitaxy[]`, `renames[]` | date fab réelle | étape MES + cycle |

**La lignée d'une plaque.**
- Les événements suivent la plaque d'étude en étude : chaîne `wafer_origin` et études filles `same_wafers` (`plans.py`), y compris dans un autre µprojet.
- Une version que l'utilisateur ne peut pas voir garde sa date, mais elle est libellée « étude non visible » et n'a pas de lien.
- Pour les renommages, l'hôte charge les données sous toute la chaîne de noms (`links.chain`) et passe `ctx.aliases`.

**Pièges.**
- Une date de commit n'est pas une date fab. La date effective d'une version est donc corrigeable dans les réglages de l'hôte (`{version_id: effective_at}`), et chaque événement affiche sa source.
- Une seule famille par graphe.
- Les ancres manuelles du cahier (`measurements[].step_id`, une seule par mesure, `schemas.py:96`) ne valent pas pour une entrée « composant », qui couvre plusieurs sessions après un rafraîchissement. Des ancres par session (`{test_id: step_id}`) viendront plus tard.

### 4.4 Les hôtes

Ils stockent tous la même forme : `{"engine": "lumiere", "component": "eqe.box-by-state", "version": 1, "options": {...}}`.

| Hôte | Stockage | Plaques | Données | Événements | Droits |
|---|---|---|---|---|---|
| **Cahier** | `MeasurementInput` gagne `engine` (`"dataviz"` \| `"lumiere"`), `version` et `snapshots: [{id, taken_at}]` (`schemas.py:89-104`, `service.py:397-403`). Les entrées DataViz restent telles quelles | plaques de l'entrée | **figées** (voir ci-dessous) | versions (ou MES) | éditeur du µprojet |
| **Fiche plaque** | `area_wafer_sheet_blocks`, `kind="component"`. À adapter : `Literal` (`wafer_data/api.py:36`), `blocks.KINDS` (`blocks.py:52`), `clean_config` (`:304`) et l'exclusion du calcul des résumés (`service.py:183`, `COMPUTE[kind]`) | la plaque | en direct | optionnel (MES) | manager du projet |
| **Analyse** | `wafer_analyses.blocks`, mêmes adaptations (`meta_analysis/api.py:43`) | réf. + N plaques, `ctx.roles` | en direct | optionnel | comme aujourd'hui |
| **Rapport brut** | nouvelle page : sélecteur (`meta_analysis/picker.py`) + composants | choisies, **vérifiées côté serveur** contre ce que l'utilisateur voit (`wafers.occurrences(user)`, fiches visibles) | en direct | optionnel | connecté, filtré |
| **Tendance** | page projet, à terme à la place de `KpiTrendBlock` et des onglets kpi_tracking | suivies × période | en direct, ou historique de Lumière (`history/`) | – | manager |

**L'instantané figé du cahier** est un nouveau format, différent de l'actuel :
- l'actuel ne contient qu'un hook ;
- il retire les colonnes 2D (`Spectra`), plafonne les vecteurs à 150 points et coupe à 20 000 lignes (`snapshots.py:33-36,50-71`) ;
- une mesure n'y a qu'un `snapshot_id`.

```json
{"format": "component/1", "component": "eqe.box-by-state", "version": 1, "taken_at": "…",
 "frames": {"eqe": {"columns": [...], "rows": [...]}},
 "sessions": {"16L5C0E6MMB1": {"last_test_date": "…", "n_testled": 45}}}
```

- **On y stocke la sortie brute de `load()`.** `enrich` (états, URL d'images, rôles) se refait à chaque rendu : les jetons et les événements ne sont jamais figés.
- Ce que l'instantané conserve dépend du `keep` du composant. Il n'y a pas de troncature silencieuse : au-delà d'un plafond (par exemple 20 Mo), l'ajout est refusé avec un message.
- Le format reste en JSON, sans nouvelle dépendance (pyarrow est absent du venv).

**Rafraîchir :**
1. À l'ouverture du cahier, `freshness.new_sessions` compare les empreintes stockées à PRISM, puis affiche le badge « 1 nouvelle mesure · 16/10 ».
2. Le bouton relit seulement les plaques remesurées (`refresh=[…]`) et **ajoute** un instantané à `snapshots`. eqe et ncel renvoient tous les tests : le dernier instantané suffit au rendu. Pour pl, tant que le mode historique n'existe pas, le rendu fait l'union des instantanés (dédoublonnée sur les clés).
3. Une nouvelle boîte apparaît pour le nouvel état.
4. Un clic sur la légende, ou sur la boîte avec `StateBoxPlot`, ouvre la version ou le comparateur.

**Rapports.**
- Le rapport d'analyse devient un rapport Lumière (`ReportBuilder`). Le contenu propre à Spectre (SVG de structure, tableau du comparateur, conclusion) y entre par un nouveau bloc `HtmlSection`.
- Le rapport du cahier **garde son exporteur actuel tant qu'il reste des entrées DataViz** : leurs SVG sont rendus par le navigateur (`experiments/report.js:6-7`), et le serveur ne peut pas les reproduire. Il passe à `ReportBuilder` après la conversion DataViz → composants (P8).
- Le diaporama de step_report reste tel quel.

### 4.6 Rapports : un seul chemin, Lumière (v3)

**Le constat.** Aujourd'hui un rapport se récupère de trois façons, chacune avec son propre code :

| Où | Code | Ce qu'il fait |
|---|---|---|
| `/analyses/{id}`, bouton « Rapport » | `meta_analysis/static/report-html.js` (~500 lignes) | un HTML composé **dans le navigateur** à partir de ce que la page montre (SVG natifs, images réduites en `data:`) |
| fiche d'étude, « Télécharger le rapport » | `experiments/static/report.js` | une photographie HTML de la fiche, dans le navigateur aussi |
| `/microprojets/{slug}`, diaporama par étape | `step_report/static/*.js` | le pas-à-pas du procédé, avec les commentaires d'étape |
| page plaque | *rien* | tu veux pouvoir en sortir un aussi |

Ils ne partagent rien, ne savent pas faire de Plotly, et chaque nouvelle donnée (images du G4, cartes, EL) demande de les retoucher tous.

**Le modèle.** Trois objets, et c'est tout :

1. **Un composant Lumière** (§2.1) : la brique autonome qui consomme sa donnée PRISM et l'affiche - wafer map, EL pattern, galerie du G4, boîtes par état, suivi de plaque... Le même composant sert **monté dans une page Spectre** (fiche plaque, analyse, cahier) et **posé sur une slide** d'un rapport.
2. **Un modèle de rapport** (`report_templates`, nouveau dans le plugin `lumiere`) : une liste de slides, chacune avec sa grille (`Slide(nrows, ncols, row_heights, col_widths)`, `navigation.py:172`) et, par cellule, `{component, version, options}` ou un bloc de texte Markdown. Il déclare son **contexte** (`wafer` \| `wafers` \| `analysis` \| `study` \| `microproject` \| `lot`) : c'est ce qui dit où il apparaît.
   ```json
   {"name": "Fiche plaque complète", "context": "wafer", "slides": [
     {"kind": "title"},
     {"title": "Suivi", "nrows": 1, "ncols": 1, "cells": [{"r": 0, "c": 0, "component": "wafer.timeline", "version": 1, "options": {}}]},
     {"title": "EQE", "nrows": 1, "ncols": 2, "cells": [
        {"r": 0, "c": 0, "component": "eqe.maps", "options": {"column": "max_EQE"}},
        {"r": 0, "c": 1, "component": "eqe.box-by-state", "options": {}}]},
     {"title": "MEB G4", "cells": [{"r": 0, "c": 0, "component": "meb.gallery", "options": {"step": "ARC_POST_STRIP"}}]},
     {"kind": "summary"}]}
   ```
3. **Un contexte**, fourni par l'hôte au moment de générer : les plaques (et leurs rôles : référence / comparées), l'étude ou l'analyse (titre, question, conclusion, SVG de structure, tableau du comparateur : par le bloc `HtmlSection`), les événements datés (`wafers.timeline`, §4.3). Les droits sont ceux de l'hôte : on ne génère que sur ce que l'on voit.

**Fait le 2026-10-19 (R2, première version)** : l'éditeur existe sur `/lumiere` (bande de slides, grille 1×1 à 3×3, un bloc par cellule, options déduites du catalogue, aperçu d'une slide sur une plaque d'essai dans un cadre, copie des modèles livrés, modèles enregistrés dans `lumiere_templates`). Le catalogue de blocs est celui de Spectre (`lumiere/blocks.py`) en attendant les composants Lumière (L0) ; pas encore de glisser-déposer ni de fusion de cellules dans l'éditeur (le modèle les accepte : `rowspan`/`colspan`).

**La page `/lumiere`** (menu Data, « Rapports »). Deux volets :
- **Modèles** : la liste, un éditeur **slide par slide** : une bande de vignettes à gauche (ajouter, dupliquer, réordonner, supprimer), la slide en cours au centre avec sa grille (1×1, 1×2, 2×2, 2×1, ou libre), un clic sur une cellule ouvre le catalogue des composants **compatibles avec le contexte** (`catalog()` filtré par hooks et par `wafers_min/max`) et le formulaire de ses `options` (généré depuis `OptionSpec`, comme `block-form.js` aujourd'hui). Un aperçu rend la slide avec les données d'une plaque d'essai (le fragment du §4.2) - c'est le « mini PowerPoint ».
- **Rapports générés** : l'historique (qui, quand, quel modèle, quel contexte), avec le fichier gardé `<data>/lumiere/reports/` et un lien de téléchargement ; une purge par taille comme le cache PRISM.

**Génération.** `POST /api/lumiere/reports {template_id, context: {...}}` → l'adaptateur construit `ReportBuilder(title=…)`, un `SlideView([TitleSlide, Slide…, SummarySlide])`, enregistre les DataFrames de chaque composant (`load()` puis `enrich()` avec les événements et les `url_for`), et `save()`. Les images (EL, G4) sont **incorporées** (`el_mode="embed"`, miniatures) pour que le fichier reste autonome ; au-delà d'un plafond (50 Mo) le rapport est refusé avec le nombre d'images à réduire. Le rendu est long (Plotly, lecture PRISM) : il part en tâche de fond, la page montre l'avancement, le fichier arrive dans « Rapports générés ».

**Où apparaît le bouton « Rapport ».** Un seul composant JS `LumiereReportButton(context)` : il liste les modèles du contexte et lance la génération. Posé sur : la page plaque (contexte `wafer`), une analyse (`analysis`), la fiche d'étude (`study`), le µprojet (`microproject`), un lot (`lot`), et le rapport brut du §4.4 (`wafers`). Sans le plugin `lumiere`, le bouton n'existe pas, et la page garde l'exporteur actuel tant que P6/P8 ne l'ont pas retiré.

**Le cahier de mesures.** Un modèle Lumière livré avec le plugin (`context: "study"`), non supprimable : une slide de titre, une slide `wafer.timeline` (les états), puis **une slide par entrée du cahier** dans l'ordre chronologique, chaque composant rendu depuis l'**instantané figé** de l'entrée (§4.4). Les entrées DataViz restantes y passent par `HtmlSection` avec leur SVG, jusqu'à leur conversion (P8).

**Modèles livrés.** `Fiche plaque` (suivi + données principales du projet + G4), `Analyse` (réf. vs plaques, HtmlSection pour structure et comparateur, blocs libres), `Cahier de mesures`, `Lot` (WaferTrackingBlock + boîtes par plaque). Ils se copient et se modifient ; un modèle livré mis à jour par une version de Spectre ne touche pas les copies.

**Ce que ça remplace** : `report-html.js` (P6), `experiments/report.js` (P8, après la conversion du cahier), et les trois boutons disparates. **Ce que ça ne remplace pas** : le diaporama de step_report (c'est un pas-à-pas de procédé, pas un rapport de données) ; il pourrait devenir un composant `study.steps` plus tard.

### 4.7 La frise des mesures : MES, JIRA, tests, sessions (v3)

**Ce qui est fait le 2026-10-19 (dans ce dépôt, non commité)** : dans le parcours MES de la page plaque, les actions de mesure (`MEASUREMENT_DEV`, `Mesure PL`, `METRO_*`, `INSPECTION`…) portent la marque « mesure » et sont comptées (`tracking_model.is_measurement`, `n_measurements`) ; les étapes JIRA annulées / écartées ne sont plus montrées (comptées à part).

**Fait le 2026-10-19 (F1, première version)** : `wafers.timeline` (événements de la vie en ligne + sources déclarées par `register_source` : les jours de mesure de chaque type daté par wafer_data, les acquisitions du G4 par sem_images), dessiné en SVG autonome par le serveur (`GET /api/wafers/{key}/timeline`), montré en tête du parcours MES (chaque marque ouvre son détail) et en slide « Frise des mesures » du rapport Lumière. Reste : le composant Lumière *montable* (L0), le clic qui ouvre le composant de la session, la précision à la minute (T1).

**Ce qui restait à faire : une seule chronologie.** La page montrait quatre listes séparées : les étapes MES, les FDL JIRA, les tests PRISM (`wafer_tests`) et, ailleurs, les mesures des hooks (eqe, pl, el_pattern, meb_g4). La frise les pose sur **un seul axe de temps**, par plaque :

| Rang | Source | Événement | Date |
|---|---|---|---|
| fabrication | MES `wafer_mes_history` | action de fabrication (non mesure) | `step_start_date` → `_end_eff` |
| **mesure MES** | MES | action marquée mesure | idem |
| **test** | `wafer_tests` | session de test (type, capteur, opérateur) | `TestStartDate` sinon `Test_Date` |
| **données** | `testled_updated_since`, `pl`, `el_pattern`, `meb_g4` | « des données existent pour cet état » : n lignes eqe, une passe EL, une acquisition G4 (`modified` du dossier) | la date de la session, du dossier, du fichier |
| étape JIRA | `fdl_steps` | étape faite (close) ; les annulées jamais | `jira_closure_date` |

Une mesure MES sans test ni données reste un point gris ; un test avec des données devient un point plein **cliquable** : il ouvre le composant correspondant (les boîtes eqe de cette session, la galerie G4 de cette acquisition). C'est la jointure « au plus tard » de `tag_states` (§2.1) lue dans l'autre sens : au lieu de donner un état à chaque mesure, on donne ses mesures à chaque état.

**Où ça vit.**
- `wafers.timeline` (§4.3) gagne la famille **`mesures`** : il rend les événements ci-dessus, en plus des versions et des étapes MES.
- Composant Lumière **`wafer.timeline`** (hooks `wafer_mes_history`, `wafer_tests`, `fdl_steps`, et en option les hooks de données) : la frise horizontale, une ligne par plaque quand il y en a plusieurs, montable (clic → `select {wafer, at, kind}`) et imprimable. C'est lui que le cahier de mesures et la fiche plaque montrent, et c'est le premier bloc des modèles « Fiche plaque » et « Cahier ».
- Dans le **parcours MES** de la page plaque, la frise remplace l'en-tête de chaque route (`routesHtml`) : on voit d'un coup d'œil où les mesures tombent entre les étapes, et la liste détaillée reste dépliable dessous.

**PRISM.** Rien de nouveau pour la précision au jour (tout existe, §3). Pour placer une mesure à la minute entre deux actions MES le même jour, il faut **T1** (`measured_at` dans eqe v3). Pour le G4, la date d'acquisition fiable est dans le `.meta` du dossier (non lu aujourd'hui, voir [sem-images]) ; en attendant, `modified` du TIF.

### 4.5 Ce qui disparaît, progressivement

| Aujourd'hui | Devient |
|---|---|
| 4 `import prism`, 4 bascules démo, 5 `PRISM_DATA_DIR`, 5 traductions d'erreur | `datasets.gateway` |
| DataViz du cahier + `presets.js` | composants ; conversion des anciennes entrées en P8 |
| natifs wafer_data, `kpiBoxplotSvg`, `curvesSvg`, `KpiTrendBlock` | retirés hook par hook, quand un composant couvre le besoin |
| 5 serveurs de fichiers image | `datasets.images` |
| exporteurs HTML d'analyse et de fiche d'étude, « Rapport » de chaque page | modèles de rapport Lumière (§4.6) + `HtmlSection` (analyse en P6, fiche d'étude et cahier en P8) ; un seul bouton `LumiereReportButton` |
| quatre listes (MES, JIRA, tests, données) sur la page plaque | la frise des mesures (§4.7), composant `wafer.timeline` |
| Lumière | aucun bloc existant modifié ; de l'infrastructure et de nouveaux blocs (`StateBoxPlot`, `HtmlSection`) |

**Hors périmètre** : coupes de structure, comparateur et jumelles, usage, frises et Gantt, graphes de filiation, diaporama de step_report.

---

## 5. Plan par phases

| Phase | Dépôt | Contenu | Critère de sortie | Taille |
|---|---|---|---|---|
| **L0 – Infra Lumière** | Lumière | runner injectable, `make_json_safe` à la seconde, imports paresseux, Plotly local, `embed_css`, paquetage (PRISM sans URL, tags), `_mount.py`, `components/` + `catalog()` + test de contrat, `tag_states` (5 règles), fragment de référence. Composants `eqe.box-by-state` (SummaryBoxPlots) et `eqe.maps` | rapport Lumière **autonome** bâti avec 2 composants ; même jour testé | M, 6-8 j |
| **P0 – Filets** | Spectre | tests d'or sur la passerelle ; démo eqe complète (`Idx at Max EQE` manque dans `demo.py:40-43`, et `load_led_dataset` le refuse, `prism_data.py:136`), avec plusieurs sessions ; `FakeComponentEngine` ; marqueur `lumiere` ; `POST …/queries` réservé aux admins | suite verte, avec ou sans Lumière | S, 3 j |
| **P1 – Passerelle** | Spectre | `datasets.gateway`, `freshness`, `keys.compact` ; test AST « un seul `import prism` » | tests d'or identiques | M, 5-7 j |
| **P2 – Adaptateur + labo** | Spectre | extra `spectre[lumiere]` + Dockerfile ; `datasets.components` ; plugin `lumiere` ; `LumiereMount` ; onglet labo | **premier composant visible dans Spectre** ; extinction à chaud → message ; démontage propre | M, 5-7 j |
| **P3a – Cahier, précision jour** | Spectre | `wafers.timeline` (versions, étapes, lignée) ; composant dans une entrée ; instantané `component/1` ; badge ; Rafraîchir ; légende des états. **Ne dépend pas de T1** | gravure → mesure → regravure → mesure sur une étude réelle : une boîte par état, dans l'ordre, chaque état relié à sa version | L, 8-10 j |
| **T1 – PRISM eqe v3** | PRISM | `test_id`, `measured_at`, KPI par session ; `fetched_at` exposé | deux mesures le même jour séparées | S, 3-4 j, en parallèle |
| **L1 – Lumière suit eqe v3** | Lumière | `time_cols` préfère `measured_at` ; bloc montable **`StateBoxPlot`** (clic → `select`) | test du même jour à la minute | S, 3-4 j |
| **P3b – Cahier, précision minute** | Spectre | famille MES ; clic sur une boîte → version | gravure et mesure le même jour, séparées | S, 2-3 j |
| **P4 – Fiche plaque** | Spectre | `kind="component"` (points listés au §4.4) | un manager ajoute un composant | M, 4-5 j |
| **P5 – Images** | Spectre + Lumière | `datasets.images` ; `el.images`, `eqe-el.explorer` | un TIF s'affiche ; une seule route d'image | L, 8-10 j |
| **P6 – Analyse + rapport** | Spectre + Lumière | composants sur réf. + N ; `HtmlSection` ; rapport d'analyse = rapport Lumière | ancien exporteur d'analyse retiré | M, 6-8 j |
| **P7 – Rapport brut + tendance** | Spectre | page rapport brut (droits vérifiés côté serveur) ; hôte tendance | un rapport brut téléchargé | M, 5-7 j |
| **P8 – Retrait** | Spectre | natifs retirés hook par hook ; conversion DataViz → composants ; rapport du cahier sur `ReportBuilder` | configs migrées, code supprimé | S par hook |

**Phases ajoutées par la v3 (rapports et frise) :**

| Phase | Dépôt | Contenu | Critère de sortie | Taille |
|---|---|---|---|---|
| **R0 – Dépendance** | Spectre + Lumière | `lumiere-report-engine @ git+…@<tag>` dans `pyproject.toml` (extra `spectre[lumiere]`), Dockerfile, `install.bat` ; import paresseux en tâche de fond ; test « Lumière s'importe dans le venv de Spectre et voit le même PRISM » | `pip install -e ".[lumiere]"` passe, un seul PRISM | S, 1 j |
| **R1 – Plugin `lumiere`, rapport brut** | Spectre | plugin, table `report_templates`, `POST /api/lumiere/reports` en tâche de fond, « Rapports générés », `LumiereReportButton` sur la page plaque avec un modèle « Fiche plaque » **codé en dur** (WaferTrackingBlock + Imageviewer G4 + boîtes eqe) | un rapport HTML de plaque téléchargé depuis `/plaques/{lm}` | M, 4-5 j (après P2 pour les composants ; avant, avec les blocs Lumière existants directement) |
| **R2 – Éditeur de modèles** | Spectre | page `/lumiere` : bande de slides, grille, catalogue des composants par contexte, formulaire d'options, aperçu sur une plaque d'essai ; modèles livrés copiables | un utilisateur compose un modèle et le bouton « Rapport » le propose | L, 8-10 j |
| **R3 – Les autres hôtes** | Spectre | bouton sur analyse (`HtmlSection` : structure, comparateur, conclusion), fiche d'étude, µprojet, lot ; retrait de `report-html.js` | l'ancien exporteur d'analyse retiré (= P6) | M, 5-6 j |
| **R4 – Cahier de mesures** | Spectre | modèle « Cahier » depuis les instantanés figés (dépend de P3a) ; `experiments/report.js` retiré quand il n'y a plus d'entrée DataViz (= P8) | le cahier d'une étude réelle sort en rapport Lumière | M, 4-5 j |
| **F1 – Frise des mesures** | Spectre + Lumière | famille `mesures` de `wafers.timeline` ; composant `wafer.timeline` ; frise dans le parcours MES ; clic → composant de la session | sur une plaque réelle, chaque mesure se voit entre deux étapes et s'ouvre | M, 5-7 j |

**Chemin le plus court vers ton cas d'usage :** L0 + P0 + P1 + P2 + P3a, soit environ 5 semaines. On a alors le cahier qui suit gravure et remesures au jour près. T1, L1 et P3b ajoutent ensuite la minute et le clic sur les boîtes.

**Ordre que je recommande pour les rapports** : R0 tout de suite (une journée, et ça débloque tout), puis **R1 avant P2** avec les blocs Lumière existants - c'est le rapport de plaque que tu n'as pas aujourd'hui, visible en une semaine ; F1 juste après (la frise est le premier bloc de tous les modèles) ; R2 quand les premiers composants existent (P2), sinon l'éditeur n'a rien à proposer ; R3 et R4 ferment la boucle en retirant l'ancien code.

---

## 6. Ce qui est décidé

1. Les composants et le catalogue de compatibilité vivent dans Lumière ; Lumière + PRISM restent autonomes.
2. Spectre n'est qu'un cadre : interface, hôtes, passerelle, contexte.
3. Les nouveaux blocs respectent le contrat montable ; il n'y a pas d'iframe.
4. Dans le cahier, les données sont figées à l'ajout, avec Rafraîchir et le suivi des remesures.
5. Chaque date de mesure est reliée à l'événement qui la précède, dans le même graphe.
6. (v3) Un seul système de rapports : des modèles Lumière composés slide par slide dans le plugin `lumiere`, un bouton « Rapport » par hôte, les exporteurs maison retirés ; le cahier de mesures en est un.
7. (v3) Lumière est une dépendance de Spectre (extra `spectre[lumiere]`), qui partage l'installation de PRISM.
8. (v3) Les étapes JIRA annulées ne sont pas montrées ; les actions MES de mesure sont marquées ; la frise des mesures les réunit avec les tests et les données.

## 7. Questions ouvertes

| # | Question | Ma recommandation |
|---|---|---|
| 1 | Relier les mesures par défaut aux **versions de l'étude** (date de commit, corrigeable) ou aux **étapes MES** (date fab réelle, mais sans lien avec les étapes Spectre) ? | **Versions** par défaut, MES en option |
| 2 | Pour les boîtes cliquables : un **nouveau bloc** `StateBoxPlot`, ou un paramètre ajouté à KPIExplorer (période par défaut + clic), ce qui modifie un bloc existant ? | **Nouveau bloc** |
| 3 | eqe v3 dans PRISM (`test_id` + horodatage) ? | **Oui** (T1) |
| 4 | Le rapport d'analyse devient-il un rapport Lumière interactif (Plotly incorporé, ~3,6 Mo) ? | **Oui** |
| 5 | Les graphiques natifs restent-ils jusqu'à ce qu'un composant les couvre ? | **Oui** |
| 6 | Plafond de taille d'un instantané figé (`keep="all"` avec `Spectra`) ? | **20 Mo**, refus avec message au-delà |
| 7 | Qui ajoute un composant : les mêmes droits que l'hôte ? | **Oui** |
| 8 | (v3) Qui compose un modèle de rapport : tout utilisateur connecté (ses modèles + les livrés), ou les managers de projet seulement ? | **Tout connecté** : un modèle ne donne accès à rien (la génération vérifie les droits du contexte) ; les modèles livrés sont modifiables par les administrateurs seulement |
| 9 | (v3) Le rapport : un HTML autonome Lumière (Plotly incorporé, images en `data:`), ou aussi un PowerPoint ? | **HTML d'abord** ; un export `.pptx` (python-pptx, une image par cellule) est un plus possible en R2, pas un prérequis |
| 10 | (v3) La génération : synchrone (attente dans la page) ou en tâche de fond avec historique ? | **Tâche de fond** : un rapport de lot lit des dizaines de plaques dans PRISM |
| 11 | (v3) Les tests PRISM (`wafer_tests`) et les données des hooks sur la frise : reliés à l'action MES de mesure la plus proche (même jour) ou laissés en points séparés ? | **Reliés quand même jour**, sinon séparés ; T1 affine à la minute |
| 12 | (v3) Le diaporama de step_report : garder tel quel ou le refaire en composant Lumière `study.steps` ? | **Garder** pour l'instant |
