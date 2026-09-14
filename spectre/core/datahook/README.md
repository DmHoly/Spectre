# datahook — dictionnaire de données externes

Ce dossier connecte Spectre à la base de caractérisation (PostgreSQL) de l'installation : chaque
type de mesure qu'on veut pouvoir récupérer (PL, NCEL, EQE...) est un **hook** — un nom, une
description de ce qu'il renvoie, la requête SQL qui va le chercher, et (optionnel) un post-traitement
qui en tire des KPI. Le tout est exposé côté web par la page wiki `/donnees`.

## Vue d'ensemble du dossier

```
datahook/
  connection.py      # parle réellement à PostgreSQL (identifiants, run_query)
  hooks.py            # charge un hook.yml, exécute la requête, enchaîne le post-traitement
  cache.py            # cache disque JSON par (hook, wafer)
  postprocessing/      # les fonctions référencées depuis un hook.yml (module:fonction)
    common.py
    pl.py, ncel.py, eqe.py
  hooks/               # un sous-dossier = un hook = une clé
    pl/hook.yml + query.sql
    ncel/hook.yml + query.sql
    eqe/hook.yml + query.sql
    waferlist/hook.yml + query.sql
    tem/ fib/ meb_g4/ sem101/ el/ el_pattern/ pdpl/ cathodo/
        defect_images/ defect_counting/   # placeholders (status: planned, pas de query.sql)
  config/
    Credential.ini, config.ini            # jamais commités (voir .gitignore + config/Readme.md)
    Credential_example.ini                # le template, lui est suivi par git
  legacy/              # ancien code, pas encore migré en hooks — voir plus bas
  data/                # anciennes données figées (ex. historical/liv.parquet), pas liées au cache
```

Le cache disque (par wafer/hook) vit sous `<SPECTRE_DATA_DIR>/datahook_cache/`, pas ici — voir
`cache.py` et la section Cache plus bas.

## 1. Un hook = un dossier sous `hooks/`

```
hooks/pl/
  hook.yml     # titre, description, paramètres, post-traitements, + tout ce qu'il faut pour le wiki
  query.sql    # la requête, paramétrée (%(wafer_names)s, style psycopg2)
```

Un hook **implémenté** (`status: implemented`, la valeur par défaut) a les deux fichiers. Un hook
**planned** n'a qu'un `hook.yml` minimal — c'est une fiche documentaire pure, il n'est pas exécutable
(voir plus bas "Ajouter un hook").

### `hook.yml` — référence complète des champs

```yaml
# --- exécution -----------------------------------------------------------
title: "Photoluminescence (PL)"
description: >
  Ce que ces lignes représentent, comment elles sont filtrées - la partie qu'on relit dans six
  mois pour se souvenir pourquoi telle recette est exclue.
status: implemented          # implemented (défaut) | planned
parameters:
  - wafer_names               # noms attendus par query.sql, dans %(...)s
postprocessing:
  - common:add_median_per_wafer   # module:fonction, résolu dans postprocessing/ — appliquées EN CHAÎNE, dans l'ordre
cache_key_column: wafername   # colonne du résultat (post-traité) qui identifie le wafer d'une ligne
                               # -> active le cache disque par wafer pour ce hook (omis = pas de cache)

# --- page wiki (/donnees) --------------------------------------------------
category: "Post EPI"           # regroupement affiché sur la page hub (/donnees)
raw_columns:                   # Niveau 1 : colonnes telles que renvoyées par query.sql
  - name: "wafer_name"
    description: "Nom du wafer tel qu'enregistré en base."
    example: "16J5A426MMD4"
kpi_columns:                    # Niveau 2 : colonnes calculées/recalculées par le post-traitement
  - name: "max_EQE"
    description: "EQE maximal atteint sur tout le balayage de ce device."
    source: "eqe:apply_eqe_kpi" # quelle fonction de post-traitement la produit
    example: 0.0177
example_rows:                   # petit échantillon écrit à la main, illustre la fiche sans requêter
  - wafername: "16J5A426MMD4"
    max_EQE: 0.0177
representative_column: "max_EQE"  # colonne mise en avant sur le graphique de la fiche

charts:                          # graphiques pédagogiques custom - voir section 6
  - key: iv_extraction
    title: "Facteur d'idéalité & résistance série (I-V)"
    description: "Ce que montre ce graphique et comment le lire."
    function: "eqe:iv_curve_with_extraction"   # module:fonction, résolu dans charts/
    example:                     # une ligne de données à la main, vecteurs complets inclus
      Led_Name: "MONO2-1.55x1.55-5852-R"
      V: [0.0, 0.5, 1.0, "..."]
      I: [1e-9, 1.5e-4, 7e-4, "..."]
```

Tout ce bloc "page wiki" est optionnel *techniquement* (des listes vides restent valides), mais c'est
lui qui remplit `/donnees/<clé>` — un hook sans `raw_columns`/`kpi_columns`/`example_rows` affiche une
fiche vide avec juste le titre et la description.

### Utilisation depuis le code Python

```python
from spectre.core.datahook.hooks import run_hook

df = run_hook("pl", wafer_names=["2753M0Z6MMA7"])
```

`run_hook` : charge le hook (`load_hook`), refuse tout de suite si `status == "planned"` (pas de
requête à lancer), vérifie que les `parameters` attendus sont fournis, exécute `query.sql` via
`connection.run_query` (le seul endroit qui parle réellement à PostgreSQL), puis applique en chaîne
chaque fonction de `postprocessing`, dans l'ordre, chacune recevant le DataFrame renvoyé par la
précédente.

## 2. Post-traitement (`postprocessing/`)

Une fonction de post-traitement prend un DataFrame, renvoie un DataFrame. Référencée dans un
`hook.yml` par `module:fonction` (jamais du code arbitraire dans le YAML lui-même — `_resolve_
postprocessing_function` dans `hooks.py` ne résout QUE des modules sous `spectre.core.datahook.
postprocessing`) : `module` est un fichier de `postprocessing/`, `fonction` une des fonctions qu'il
expose.

- `common.py` : utilitaires génériques réutilisables par plusieurs hooks (ex. `add_median_per_wafer`).
- `pl.py`, `ncel.py`, `eqe.py` : un module par type de mesure, pour tout post-traitement spécifique
  (calcul de KPI, filtrage, ré-échantillonnage). Un post-traitement propre à une mesure mérite son
  propre module plutôt que d'être ajouté à `common.py`.

Exemple (`eqe/hook.yml`) : `postprocessing: [eqe:apply_eqe_kpi, eqe:downsample_spectra]` — le calcul
des KPI (max EQE, point de fonctionnement, couleur...) tourne d'abord sur les vecteurs complets, le
sous-échantillonnage des spectres (n=100 points) vient après, pour ne pas perdre de précision sur les
KPI scalaires avant de les calculer.

## 3. Connexion (`connection.py`)

Identifiants, par ordre de priorité :
1. Variables d'environnement `DB_LUMIERE_USER`/`DB_LUMIERE_PASSWORD`/`DB_LUMIERE_HOST`/
   `DB_LUMIERE_NAME`/`DB_LUMIERE_PORT`
2. `config/Credential.ini` (section `[DB_CREDENTIALS]`) + `config/config.ini` (section `[DB]`) —
   voir `config/Readme.md`. **Ces deux fichiers ne sont jamais commités** (`.gitignore` à la racine
   du dépôt) ; seul `config/Credential_example.ini` (le template, sans vraies valeurs) est suivi.
3. Valeurs historiques de cette installation (`host=INF49`, `database=testcarac`, `port=5432`).

Si tu ajoutes ou modifies un fichier sous `config/`, vérifie toujours avec `git status` /
`git add -n` que `Credential.ini`/`config.ini` restent bien ignorés avant tout commit.

## 4. Cache disque (`cache.py`)

Pour éviter de retaper la base à chaque affichage, `run_hook_cached(key, wafer_names, refresh=False)`
met le résultat en cache **par wafer**, sur disque, en JSON à plat :

```
<SPECTRE_DATA_DIR>/datahook_cache/<hook_key>/<wafer_name>.json
```

- Ne s'applique qu'aux hooks qui déclarent `cache_key_column` dans leur `hook.yml`. Les autres (ex.
  `waferlist`, qui ne prend même pas `wafer_names`) retombent sur `run_hook` tel quel, sans cache.
- Un wafer déjà vu (par cet appel ou un précédent) est relu instantanément depuis son fichier ; seuls
  les wafers manquants (ou tous, si `refresh=True`) déclenchent une vraie requête, et sont réécrits en
  cache aussitôt après.
- C'est ce que la page `/donnees/<clé>` utilise via la case "Forcer le rafraîchissement" côté
  "Tester en direct".
- Le dossier de cache tombe sous le `.gitignore` général de `data/` — rien à faire de spécial.

## 5. Graphiques pédagogiques (`charts/`)

Certains hooks ont besoin de plus qu'un tableau de colonnes pour être compris : par exemple,
*comment* on lit le facteur d'idéalité ou la résistance série sur une courbe I-V ne se voit que sur
un dessin annoté. Ces graphiques vivent sous `charts/` — un module par hook, une fonction Python
`(df: pd.DataFrame) -> matplotlib.figure.Figure` par graphique — référencée depuis `hook.yml` par
`module:fonction` (même principe et même restriction que `postprocessing:`).

**Important : la fiche wiki documente, elle ne calcule pas à l'affichage.** Un graphique se dessine
toujours sur un exemple **figé**, écrit à la main dans `hook.yml` sous `charts[].example` (comme
`example_rows`, mais avec les vecteurs complets dont un graphique a besoin, ex. `V`/`I` d'un
device réel plutôt qu'un simple scalaire) — jamais sur une vraie requête. Charger la page
`/donnees/<clé>` ne touche donc jamais la base, même pour ses graphiques ; "Tester en direct" reste
le seul endroit qui interroge réellement PostgreSQL.

Ajouter un graphique à un hook :
1. Écrire la fonction dans `charts/<hook>.py` (ou un module existant) : elle reçoit un DataFrame
   d'une seule ligne (construit depuis `example`), renvoie une `Figure` matplotlib.
2. Déclarer `charts: [{key, title, description, function, example}]` dans le `hook.yml` du hook -
   `example` porte les colonnes dont la fonction a besoin, valeurs écrites à la main (idéalement
   recopiées depuis un vrai exemple, tronquées si le vecteur est long).
3. L'API (`GET /api/donnees/hooks/{key}/graphiques/{chart_key}`) et la page wiki l'affichent sans
   rien coder de plus.

## 6. La page wiki (`/donnees`)

Tout le contenu de `/donnees` (hub par catégorie) et `/donnees/<clé>` (fiche par hook) vient
directement du `hook.yml` — rien à toucher côté code pour documenter un hook ou en ajouter un nouveau :

- **Hub** (`/donnees`) : une carte par `category`, la liste des hooks qu'elle contient en "chips" —
  cliquable et menant à la fiche si `status: implemented`, grisé "à venir" si `status: planned`.
- **Fiche** (`/donnees/<clé>`) :
  - **Niveau 1 — Données brutes** : table depuis `raw_columns` (ce que `query.sql` renvoie tel quel).
  - **Niveau 2 — KPI calculés** : table depuis `kpi_columns`, avec une colonne "Source" (`source`, le
    `module:fonction` qui la produit).
  - Table d'exemple depuis `example_rows`.
  - Un petit bar chart D3 (une barre par ligne d'`example_rows`, hauteur = `representative_column`).
  - "Tester en direct" (lance vraiment `run_hook_cached` contre la base) — affiché **uniquement** si
    `status: implemented`.
- Code : `spectre/api/datahook.py` (endpoints `/api/donnees/...`) et
  `spectre/api/static/js/donnees.js` (rendu). Aucun des deux n'a besoin d'être modifié pour un
  nouveau hook — seul son `hook.yml` compte.

## Ajouter un nouveau hook

1. `hooks/<clé>/hook.yml` — au minimum `title`, `description`. Choisis `status: planned` tant que la
   requête n'est pas prête (aucun `query.sql` requis dans ce cas — le hook apparaît sur `/donnees`
   comme fiche documentaire, non exécutable).
2. Quand la requête existe : passe `status: implemented`, ajoute `hooks/<clé>/query.sql` (paramètres
   nommés `%(nom)s`, résolus depuis `parameters`), et remplis `raw_columns`/`kpi_columns`/
   `example_rows`/`representative_column` pour que la fiche wiki soit utile.
3. S'il faut calculer des KPI : ajoute une fonction dans `postprocessing/<clé>.py` (ou réutilise
   `common.py` si c'est vraiment générique), référence-la dans `postprocessing:` du `hook.yml`.
4. Si le résultat peut être mis en cache par wafer : ajoute `cache_key_column: <colonne>`.
5. Ajoute des tests dans `tests/test_datahook.py` (jamais contre la vraie base — tout y est mocké).

Les 10 hooks actuellement `planned` (`pdpl`, `cathodo`, `el`, `el_pattern`, `tem`, `fib`, `meb_g4`,
`sem101`, `defect_images`, `defect_counting`) sont des placeholders à migrer un par un sur ce modèle,
en s'appuyant sur le code correspondant dans `legacy/` (voir plus bas).

## `legacy/`

Le code antérieur à cette réorganisation (scripts de rapport, notebooks, KPI EQE/LIV/couleur,
imagerie SEM/EL, listes de wafers...) est conservé tel quel sous `legacy/` — pas encore reformaté en
hooks, rien ici n'est câblé au reste de Spectre. `pl`, `ncel`, `eqe`/`waferlist` ont déjà été migrés
depuis ce code (voir leurs `hook.yml`/`postprocessing/*.py` pour la correspondance exacte avec les
fichiers `legacy/` d'origine) ; les hooks `planned` restants pointent vers le fichier `legacy/`
correspondant dans leur `description`, à migrer au fur et à mesure sur ce même modèle.

## Ce qui n'existe pas encore

Le système de "fiches graphique" (un YAML = un graphique standard — box plot médiane vs nom de
wafer, etc. — consommant un ou plusieurs hooks) n'est pas construit : seuls le dictionnaire de hooks
et la page wiki (graphique simple, un par fiche) le sont. Prochaine étape naturelle si besoin.
