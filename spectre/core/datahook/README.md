# datahook — dictionnaire de données externes

Ce dossier connecte Spectre à la base de caractérisation (PostgreSQL) de l'installation : chaque
type de mesure qu'on veut pouvoir récupérer (PL, NCEL, EQE...) est un **hook** — un nom, une
description de ce qu'il renvoie, et la requête SQL qui va le chercher.

## Un hook = un dossier sous `hooks/`

```
hooks/
  pl/
    hook.yml     # titre, description, paramètres attendus, post-traitements
    query.sql    # la requête, paramétrée (%(wafer_names)s, style psycopg2)
  ncel/
    hook.yml
    query.sql
  waferlist/
    hook.yml
    query.sql
```

`hook.yml` :

```yaml
title: "Photoluminescence (PL)"
description: >
  Ce que ces lignes représentent, comment elles sont filtrées - la partie qu'on relit dans six
  mois pour se souvenir pourquoi telle recette est exclue.
parameters:
  - wafer_names        # les paramètres nommés que query.sql attend, dans %(...)s
postprocessing:
  - common:add_median_per_wafer   # module:fonction, résolu dans postprocessing/
```

Utilisation, depuis le code Python de Spectre :

```python
from spectre.core.datahook.hooks import run_hook

df = run_hook("pl", wafer_names=["2753M0Z6MMA7"])
```

`run_hook` charge le hook, exécute sa requête via `connection.run_query` (la seule chose qui parle
réellement à PostgreSQL), puis applique en chaîne chaque fonction de post-traitement listée, dans
l'ordre, chacune recevant le DataFrame renvoyé par la précédente.

## Post-traitement (`postprocessing/`)

Une fonction de post-traitement prend un DataFrame, renvoie un DataFrame. Référencée dans un
`hook.yml` par `module:fonction` (jamais du code arbitraire dans le YAML lui-même) - `module` est
un fichier de `postprocessing/`, `fonction` une des fonctions qu'il expose. `common.py` porte les
utilitaires génériques (ex. `add_median_per_wafer`) ; un post-traitement spécifique à un type de
mesure (calcul de KPI EQE/LIV, par ex.) mérite son propre module plutôt que d'être ajouté à
`common.py`.

## Connexion (`connection.py`)

Identifiants : `DB_LUMIERE_USER`/`DB_LUMIERE_PASSWORD` (variables d'environnement) en priorité,
sinon `config/Credential.ini` (voir `config/Readme.md` - **jamais commité**, voir le `.gitignore`
à la racine du dépôt). Hôte/base/port : `DB_LUMIERE_HOST`/`DB_LUMIERE_NAME`/`DB_LUMIERE_PORT`, sinon
`config/config.ini` (section `[DB]`), sinon les valeurs historiques de cette installation.

## `legacy/`

Le code antérieur à cette réorganisation (scripts de rapport, notebooks, KPI EQE/LIV/couleur,
imagerie SEM/EL, listes de wafers...) est conservé tel quel sous `legacy/` - pas encore reformaté
en hooks. Rien ici n'est câblé au reste de Spectre ; à migrer au fur et à mesure, un hook à la
fois, sur le même modèle que `pl`/`ncel`/`waferlist`.

## Ce qui n'existe pas encore

Le système de "fiches graphique" (un YAML = un graphique standard - box plot médiane vs nom de
wafer, etc. - consommant un ou plusieurs hooks, +/- un bout de code de rendu) n'est pas construit :
seul le dictionnaire de hooks ci-dessus l'est. Prochaine étape.
