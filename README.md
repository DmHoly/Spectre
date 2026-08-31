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

### Windows

Prérequis : [Python 3.11+](https://www.python.org/downloads/) (cocher « Add python.exe to PATH »
à l'installation) et [Git](https://git-scm.com/download/win).

1. Cloner le dépôt puis ouvrir le dossier :
   ```bat
   git clone https://github.com/DmHoly/Spectre.git
   cd Spectre
   ```
2. Double-cliquer **`install.bat`** (ou l'exécuter depuis une invite de commandes). Il crée un
   environnement virtuel `.venv` et installe Spectre avec ses dépendances (StructureForge,
   Follow - téléchargées depuis GitHub, ça peut prendre quelques minutes).
3. Double-cliquer **`start.bat`**. Une fenêtre s'ouvre avec les journaux du serveur, et le
   navigateur s'ouvre automatiquement sur `http://127.0.0.1:8000/`.

Pour arrêter le serveur : fermer la fenêtre de journaux (ou `Ctrl+C` dedans). Pour relancer plus
tard, `start.bat` suffit - pas besoin de relancer `install.bat` à chaque fois (seulement après une
mise à jour du code, pour récupérer d'éventuelles nouvelles dépendances).

### macOS / Linux

```bash
pip install -e ".[dev]"
spectre --port 8000
#   http://127.0.0.1:8000/
```

### Dans tous les cas

Les données (comptes, projets, dépôts d'expériences, recettes) sont écrites sous `./data` par
défaut - voir `SPECTRE_DATA_DIR` pour changer cet emplacement.

## Déploiement

```bash
docker compose up -d --build
#   http://localhost:8000/
```

L'image (voir `Dockerfile`) installe le paquet avec pip (nécessite un accès réseau sortant vers
GitHub, `structureforge` étant une dépendance `git+https`), tourne en utilisateur non privilégié
et écrit ses données sous `/data` - `docker-compose.yml` monte ce chemin en volume nommé pour
qu'elles survivent à un redémarrage du conteneur. Sans `docker compose`, l'équivalent direct :

```bash
docker build -t spectre .
docker run -d -p 8000:8000 -v spectre-data:/data --name spectre spectre
```

Variables d'environnement reconnues :

| Variable | Rôle | Par défaut |
|---|---|---|
| `SPECTRE_DATA_DIR` | Où sont écrites les données (comptes, projets, dépôts Follow, recettes) | `./data` |
| `SPECTRE_BASE_URL` | URL publique utilisée dans les liens des e-mails envoyés (invitation, mot de passe oublié) | (vide) |
| `SPECTRE_SMTP_HOST` | Serveur SMTP pour l'envoi réel des e-mails - absent, les e-mails sont journalisés au lieu d'être envoyés | (aucun) |
| `SPECTRE_SMTP_PORT` | Port SMTP | `587` |
| `SPECTRE_SMTP_USER` / `SPECTRE_SMTP_PASSWORD` | Identifiants SMTP | (aucun) |
| `SPECTRE_SMTP_FROM` | Adresse d'expéditeur | `SPECTRE_SMTP_USER`, sinon `spectre@localhost` |

Il n'y a pas de pipeline d'intégration continue : construire l'image et lancer `pytest` avant de
déployer reste une étape manuelle.

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
