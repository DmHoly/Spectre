# Spectre

Suivi d'expériences de procédé, de la définition de la structure jusqu'à la conclusion.

Spectre est l'application métier qui relie deux bibliothèques :

- **[StructureForge](https://github.com/dmholy/structureforge)** : construire et simuler la
  structure d'un empilement de couches (substrat, dépôt, gravure, planarisation, lithographie).
- **[Follow](https://github.com/dmholy/follow)** : suivre l'évolution d'une expérience dans le
  temps (versions successives, comparaisons, conclusions), sans jamais l'exposer avec du
  vocabulaire technique.

Spectre lui-même n'ajoute que ce qui manque aux deux bibliothèques pour devenir une application
d'équipe : des comptes utilisateurs, plusieurs µprojets avec des droits de modification, une couche
de pilotage stratégique par-dessus, et une interface unique et simple - une **fiche d'identité**
par expérience.

## Hiérarchie

```
Thème (Management)         grand thème piloté par la société - Datacom (VLC), Nova (PT1), Native (PT2)...
  └─ µprojet                 un sujet adressé sous ce thème (ex-« projet »)
       └─ expérience          une étude versionnée (Follow) : brouillon → en cours → conclue
            └─ entité physique   un wafer réel suivi (identifiant + emplacement)
                 └─ structure       le procédé simulé (StructureForge) porté par ce wafer
                      └─ étape          une opération du procédé (dépôt, gravure...), regroupable en
                                        brique technologique réutilisable ; ses paramètres process
                                        se sauvegardent en préset d'étape
```

- **Thèmes** (`spectre.core.management`) : visibles par tout utilisateur connecté (vue société
  transverse) ; seul un compte **administrateur** (`users.is_admin`) crée/renomme/supprime un thème
  ou y rattache un µprojet - voir `spectre admin` plus bas. Page d'accueil (`/`), un thème
  (`/management/{slug}`), vue globale chiffrée (`/pilotage`).
- **µprojets** gardent leurs droits par membre (`viewer`/`editor`/`owner`) exactement comme avant -
  la couche Management n'y change rien, elle ne fait que les regrouper.
- **Bibliothèque** (`/bibliotheque`) : structures/présets/briques réutilisables entre µprojets, plus
  la bibliothèque de matériaux/recettes de l'installation, éditable dans `library/*.yml` à la racine
  du dépôt (voir `library/README.md`) - inutile de redémarrer, rechargée à chaud.

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

### Administrateur (couche Management)

Le tout premier compte inscrit devient automatiquement administrateur - seul rôle habilité à
créer/renommer/supprimer un thème ou y rattacher un µprojet (tout le monde peut les consulter).
Pour en promouvoir un autre :

```bash
spectre admin quelquun@exemple.com          # promouvoir
spectre admin quelquun@exemple.com --revoke # rétrograder
```

### Compte de démonstration

```bash
python scripts/seed_demo.py
```

Crée un compte (`demo@spectre.local` / `demo1234`) avec deux projets déjà remplis, comme si
l'équipe utilisait Spectre depuis un an - tous les deux sur des nanofils GaN épitaxiés pour LED,
pour rester dans un seul domaine métier : **Nanofils GaN - puits quantique simple** (épitaxie de
référence, gravure, croissance sélective, un seul puits quantique InGaN visant le bleu, un
changement de substrat de base saphir/SiC, et une déclinaison rouge/vert/bleu du taux d'indium de
la zone active) et **Nanofils GaN - puits quantiques multiples (MQW)** - un projet séparé - qui
reprend la même base épitaxiale mais compare plusieurs puits quantiques avec et sans couche
bloqueuse d'électrons (EBL), puis affine le dopage P en aval. Les deux montrent l'éventail complet
des flux de filiation, pas seulement des évolutions linéaires : embranchements (déclinaisons de
couleur, substrat SiC, avec/sans EBL), fusion de deux pistes indépendantes en une seule expérience
(`/combiner`, visible dans le graphe du projet comme un losange), et des refs
(`spectre.core.refs`) posées sur les points de départ vraiment réutilisés (l'épitaxie standard, la
structure de référence...) plutôt que sur chaque version. Tout passe par les vraies routes HTTP,
donc les données sont garanties valides ; seules les dates de création sont recalées après coup
pour étaler l'historique sur l'année (voir le script pour le détail). Lancer sur un répertoire de
données neuf (`--data-dir` sinon `SPECTRE_DATA_DIR`/`./data`) - relancer sur un répertoire déjà
semé recréerait les mêmes comptes et échouerait sur l'inscription.

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

- `spectre/core/` - accès aux données (comptes, sessions, µprojets, droits, thèmes de management)
  et le pont vers StructureForge/Follow. Aucune logique de simulation, de diff ou de versioning
  n'est réécrite ici : elle est importée depuis les deux bibliothèques.
  - `management.py` : les thèmes de pilotage stratégique (au-dessus des µprojets).
  - `registry.py` : la bibliothèque racine éditable (`library/*.yml` - matériaux, présets,
    briques, recettes), rechargée à chaud.
- `spectre/api/` - l'application FastAPI (routes JSON + pages HTML/CSS/JS vanilla, une page par
  écran). Un µprojet s'appelle `microproject` partout en interne (table SQLite `microprojects`,
  dossier `data/microprojects/<slug>`, modules `spectre/core/microprojects.py` et
  `spectre/api/microprojects.py`) ; le français « µprojet » est réservé à ce que voit
  l'utilisateur - les URLs (`/microprojets/...`, `/api/microprojets/...`), les libellés, et la clé
  de scope `"microprojet"` des payloads à trois niveaux. Les anciennes URLs `/projets/...`
  redirigent (308) vers `/microprojets/...`, et une installation antérieure au renommage se migre
  toute seule au démarrage - tables, colonnes et dossier `data/projects/` compris (voir
  `_rename_legacy_project_tables` dans `spectre/core/db.py`).
- `library/` - la bibliothèque racine (matériaux/présets/briques/recettes), voir son propre
  `README.md`.

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
| `spectre/api/microprojects.py` | 87 % |
| `spectre/api/structures.py` | 95 % |
| `spectre/cli.py` | 0 % *(point d'entrée `spectre --port`, non exercé par les tests HTTP)* |
| `spectre/core/accounts.py` | 97 % |
| `spectre/core/db.py` | 100 % |
| `spectre/core/email.py` | 48 % *(l'envoi SMTP réel n'est pas simulé en test)* |
| `spectre/core/keyed_store.py` | 100 % |
| `spectre/core/permissions.py` | 100 % |
| `spectre/core/microprojects.py` | 97 % |
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
