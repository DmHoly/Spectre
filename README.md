# Spectre

Suivi d'expériences de procédé, de la définition de la structure jusqu'à la conclusion.

Spectre est l'application métier qui relie deux bibliothèques :

- **[StructureForge](https://github.com/dmholy/structureforge)** : construire et simuler la
  structure d'un empilement de couches (substrat, dépôt, gravure, planarisation, lithographie).
- **[Follow](https://github.com/dmholy/follow)** : suivre l'évolution d'une expérience dans le
  temps (versions successives, comparaisons, conclusions), sans jamais l'exposer avec du
  vocabulaire technique.

Spectre lui-même n'ajoute que ce qui manque aux deux bibliothèques pour devenir une application
d'équipe : des comptes utilisateurs, plusieurs projets avec des droits de modification, et une
interface unique et simple - une **fiche d'identité** par expérience.

## Démarrer en local

```bash
pip install -e ".[dev]"
spectre --port 8000
#   http://127.0.0.1:8000/
```

Les données (comptes, projets, dépôts d'expériences, recettes) sont écrites sous `./data` par
défaut - voir `SPECTRE_DATA_DIR` pour changer cet emplacement.

## Organisation

- `spectre/core/` - accès aux données (comptes, sessions, projets, droits) et le pont vers
  StructureForge/Follow. Aucune logique de simulation, de diff ou de versioning n'est réécrite
  ici : elle est importée depuis les deux bibliothèques.
- `spectre/api/` - l'application FastAPI (routes JSON + pages HTML/CSS/JS vanilla, une page par
  écran).

## Tests

```bash
pytest
```
