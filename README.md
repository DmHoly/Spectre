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
tard, `start.bat` suffit - pas besoin de relancer `install.bat` à chaque fois.

Pour mettre à jour vers la dernière version : double-cliquer **`update.bat`**. Il récupère les
derniers changements de Spectre (`git pull`) et force le rechargement de StructureForge et Follow
depuis GitHub - les trois dépôts dont dépend l'application - puisque `pip` garde sinon la version
déjà installée même quand ces dépôts ont changé.

### macOS / Linux

```bash
pip install -e ".[dev]"
spectre --port 8000
#   http://127.0.0.1:8000/
```

### Dans tous les cas

Les données (comptes, projets, dépôts d'expériences, présets d'étape) sont écrites sous `./data`
par défaut - voir `SPECTRE_DATA_DIR` pour changer cet emplacement.

### Compte de démonstration

```bash
python scripts/seed_demo.py
```

Crée un compte (`demo@spectre.local` / `demo1234`) avec deux projets déjà remplis, comme si
l'équipe utilisait Spectre depuis un an : **Gâteau au chocolat** (une recette optimisée au fil de
dizaines d'essais - température, dosages, glaçage - pour montrer que le suivi d'expérience marche
sur n'importe quel procédé, pas seulement en salle blanche) et **Nanofils GaN** (épitaxie,
gravure, croissance sélective, campagnes DOE, retournement pour contact face arrière - plus
proche du métier réel). Les deux montrent l'éventail complet des flux de filiation, pas seulement
des évolutions linéaires : embranchements (une piste vegan et une piste sans-gluten pour le
gâteau, un essai sur substrat SiC pour les nanofils) puis fusion de deux pistes indépendantes en
une seule expérience (`/combiner`, visible dans le graphe du projet comme un losange). Tout passe
par les vraies routes HTTP, donc les données sont garanties valides ; seules les dates de création
sont recalées après coup pour étaler l'historique sur
l'année (voir le script pour le détail). Lancer sur un répertoire de données neuf (`--data-dir`
sinon `SPECTRE_DATA_DIR`/`./data`) - relancer sur un répertoire déjà semé recréerait les mêmes
comptes et échouerait sur l'inscription.

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
| `SPECTRE_DATA_DIR` | Où sont écrites les données (comptes, projets, dépôts Follow, présets d'étape) | `./data` |
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

Le front-end (`spectre/api/static/js/`) reste des balises `<script>` classiques sans bundler, mais
la logique pure du constructeur de structure (génération du code Python, résumés d'étape...) a ses
propres tests unitaires, sans aucune dépendance à installer - juste [Node.js](https://nodejs.org/)
18+ et son test runner intégré :

```bash
node --test
```

### Couverture de code

```bash
pytest --cov --cov-report=term-missing   # Python (pip install -e ".[dev]" installe pytest-cov)
node --test --experimental-test-coverage # JavaScript
```

Python, par module (`spectre/`, 109 tests, 91 % au total à la dernière mesure) :

| Module | Couverture |
|---|---|
| `spectre/__init__.py` | 100 % |
| `spectre/api/app.py` | 100 % |
| `spectre/api/auth.py` | 96 % |
| `spectre/api/deps.py` | 86 % |
| `spectre/api/experiments.py` | 83 % |
| `spectre/api/keyed_resource.py` | 100 % |
| `spectre/api/projects.py` | 87 % |
| `spectre/api/structures.py` | 95 % |
| `spectre/cli.py` | 0 % *(point d'entrée `spectre --port`, non exercé par les tests HTTP)* |
| `spectre/core/accounts.py` | 97 % |
| `spectre/core/db.py` | 100 % |
| `spectre/core/email.py` | 48 % *(l'envoi SMTP réel n'est pas simulé en test)* |
| `spectre/core/keyed_store.py` | 100 % |
| `spectre/core/permissions.py` | 100 % |
| `spectre/core/projects.py` | 97 % |
| `spectre/core/security.py` | 100 % |
| `spectre/core/step_presets.py` | 100 % |
| `spectre/core/structure_library.py` | 100 % |
| `spectre/core/structures.py` | 95 % |

JavaScript (`tests_js/`, `node --test` exécute les vrais fichiers de `spectre/api/static/js/
structure-builder/` - voir `tests_js/helpers/load-structure-builder.js`) : encore partiel, seule
la logique pure du registre `STEP_KIND_DEFS` est couverte pour l'instant, le reste du constructeur
dépend du DOM et n'a que la vérification manuelle (Playwright) faite pendant le développement.

| Module | Couverture (lignes) |
|---|---|
| `step-kinds.js` | 51 % |
| `code-export.js` | 44 % |
| `form-widgets.js` | 16 % *(les widgets eux-mêmes touchent le DOM ; seuls `modeSummary`/`parseOpenings` sont testés)* |
| `context.js`, `substrate.js`, `step-list.js`, `objectives.js`, `campaign.js`, `simulation.js`, `experience-launch.js`, `library-mode.js`, `main.js` | 0 % *(pilotage du DOM/état - pas encore de tests automatisés)* |
