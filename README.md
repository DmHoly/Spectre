# Spectre

Suivi d'expériences de procédé, de la définition de la structure jusqu'à la conclusion.

Spectre est l'application métier qui relie trois bibliothèques :

- **[StructureForge](https://github.com/dmholy/structureforge)** : construire et simuler la
  structure d'un empilement de couches (substrat, dépôt, gravure, planarisation, lithographie).
- **[Follow](https://github.com/dmholy/follow)** : suivre l'évolution d'une expérience dans le
  temps (versions successives, comparaisons, conclusions), sans jamais l'exposer avec du
  vocabulaire technique.
- **[PRISM](https://gitlab-it.aledia.com/sda/tools/soft/prism)** (`prism-aledia-datahook`) : le
  dictionnaire des données de caractérisation (EQE, PL, NCEL...) - requêtes, formules KPI, cache,
  documentation - partagé avec les autres projets Aledia. C'est lui qui alimente la page **Data**.

Spectre lui-même n'ajoute que ce qui manque à ces bibliothèques pour devenir une application
d'équipe : des comptes utilisateurs, plusieurs µprojets avec des droits de modification, une couche
de pilotage stratégique par-dessus, et une interface unique et simple - une **fiche d'identité**
par expérience.

La structure d'une expérience se dessine étape par étape dans le constructeur (simulée par
StructureForge), ou se donne simplement en **images** - un schéma collé depuis PowerPoint, des
coupes TEM, une ou plusieurs dans l'ordre où les lire - modifiables à tout moment
(`spectre.plugins.structures.kinds.StructureImage`, page `/microprojets/<slug>/structures/image`).

Chaque wafer suivi porte ses **FDL** (feuilles de lancement JIRA, `spectre.plugins.wafers.fdl`) - plusieurs
possibles, empilées - retrouvables depuis la barre de recherche ; une preuve peut porter des liens
(dossier, présentation PowerPoint) et des images collées.

## Hiérarchie

```
Projet corporate (Management)   Native (PT2), VLC (microlink), Nova (PT1)... - avec ses objectifs
                                 de la période (ex. 6 prochains mois) : un % (chiffre de bonus,
                                 0-100, simplement noté - ils sont classés par lui), atteint ou non,
                                 et le µprojet qui l'a validé
  └─ thématique                   un axe technique du projet (dopage PGaN, double EBL...)
       └─ µprojet                  une chaîne d'expériences sur cette thématique, numérotée d'après
                                   son projet (Nat_0004, Nov_0001, VLC_0002 - lien court /p/Nat_0004)
            └─ expérience          une étude versionnée (Follow) : brouillon → en cours → conclue
                 └─ entité physique   un wafer réel suivi (identifiant + emplacement)
                      └─ structure       le procédé simulé (StructureForge) porté par ce wafer
                           └─ étape          une opération du procédé (dépôt, gravure...), regroupable en
                                             brique technologique réutilisable ; ses paramètres process
                                             se sauvegardent en préset d'étape
```

- **Thèmes** (plugin `areas`) : visibles par tout utilisateur connecté (vue société
  transverse) ; seul un compte **administrateur** (`users.is_admin`) crée/renomme/supprime un thème
  ou y rattache un µprojet - voir `spectre admin` plus bas. Page d'accueil (`/`), un projet
  (`/management/{slug}` : objectifs classés, tendances des KPI, thématiques et µprojets).
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
   Follow - téléchargées depuis GitHub - et PRISM, depuis gitlab-it.aledia.com : il faut donc être
   sur le réseau Aledia ; ça peut prendre quelques minutes).
3. Double-cliquer **`start.bat`**. Une fenêtre s'ouvre avec les journaux du serveur, et le
   navigateur s'ouvre automatiquement sur `http://127.0.0.1:8000/`.

Pour arrêter le serveur : fermer la fenêtre de journaux (ou `Ctrl+C` dedans). Pour relancer plus
tard, `start.bat` suffit - pas besoin de relancer `install.bat` à chaque fois.

Pour mettre à jour vers la dernière version : double-cliquer **`update.bat`**. Il récupère les
derniers changements de Spectre (`git pull`) et force le rechargement de StructureForge, Follow
(GitHub) et PRISM (GitLab) - les dépôts dont dépend l'application - puisque `pip` garde sinon la
version déjà installée même quand ces dépôts ont changé.

### macOS / Linux

```bash
pip install -e ".[dev]"
spectre --port 8000
#   http://127.0.0.1:8000/
```

### Dans tous les cas

Les données (comptes, projets, dépôts d'expériences, présets d'étape) sont écrites sous `./data`
par défaut - voir `SPECTRE_DATA_DIR` pour changer cet emplacement.

### Données de caractérisation (PRISM)

La page **Data** interroge les bases de caractérisation via PRISM, qui se configure une fois par
poste, **hors du dépôt** (rien de secret n'est jamais commité ici) :

1. copier le modèle
   [`config/connections.example.yml`](https://gitlab-it.aledia.com/sda/tools/soft/prism/-/blob/master/config/connections.example.yml)
   de PRISM en `~/.prism/connections.yml` (`%USERPROFILE%\.prism\connections.yml` sous
   Windows) - hôtes et bases, sans mot de passe ;
2. créer `~/.prism/credentials.ini` avec le compte de lecture :
   ```ini
   [DEFAULT]
   user = ...
   password = ...
   ```
   (ou les variables d'environnement `PRISM_USER` / `PRISM_PASSWORD` ; l'ancienne section
   `[DB_CREDENTIALS]` et `DB_LUMIERE_USER` / `DB_LUMIERE_PASSWORD` restent acceptées) ;
3. vérifier, sans se connecter à rien : `prism doctor`.

Sans cette configuration Spectre fonctionne normalement ; seule l'exécution d'une requête depuis
la page Data renvoie « configuration de connexion incomplète ». Le cache par wafer de PRISM est
rangé sous `<SPECTRE_DATA_DIR>/prism`. Pour ajouter ou corriger une donnée (requête, KPI), c'est
dans le dépôt PRISM que ça se passe, plus dans Spectre.

Le **cahier de données** de chaque fiche (onglet « Données ») passe par la même configuration : il
charge les mesures des plaques de l'expérience via PRISM et les montre avec des composants de
visualisation (`spectre/plugins/notebook/static/dataviz/`, un fichier par composant - voir la documentation
d'architecture pour en ajouter un). Une instance de démonstration sans accès aux bases peut
définir `SPECTRE_DEMO_DATA=1` pour utiliser des données synthétiques, signalées comme telles.

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
(`spectre.plugins.experiments.refs`) posées sur les points de départ vraiment réutilisés (l'épitaxie standard, la
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
GitHub et gitlab-it.aledia.com, `structureforge` et PRISM étant des dépendances `git+https`), tourne en utilisateur non privilégié
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
| `SPECTRE_COOKIE_SECURE` | `1` / `0` : force ou retire l'attribut `Secure` du cookie de session | `1` si `SPECTRE_BASE_URL` est en `https://` |
| `SPECTRE_SMTP_HOST` | Serveur SMTP pour l'envoi réel des e-mails - absent, seuls le destinataire et l'objet de chaque e-mail sont journalisés | (aucun) |
| `SPECTRE_EMAIL_DEBUG` | `1` : sans SMTP, journalise aussi le corps des e-mails (et donc leurs liens) - poste de développement seulement | (aucun) |
| `SPECTRE_SMTP_PORT` | Port SMTP | `587` |
| `SPECTRE_SMTP_USER` / `SPECTRE_SMTP_PASSWORD` | Identifiants SMTP | (aucun) |
| `SPECTRE_SMTP_FROM` | Adresse d'expéditeur | `SPECTRE_SMTP_USER`, sinon `spectre@localhost` |
| `PRISM_CONNECTIONS_FILE` | Fichier de profils de connexion PRISM (à monter dans le conteneur) | `~/.prism/connections.yml` |
| `PRISM_USER` / `PRISM_PASSWORD` | Identifiants des bases de caractérisation (ou `PRISM_<PROFIL>_USER`...) | (aucun) |
| `PRISM_DATA_DIR` | Cache disque de PRISM | `<SPECTRE_DATA_DIR>/prism` |

Il n'y a pas de pipeline d'intégration continue : construire l'image et lancer `pytest` avant de
déployer reste une étape manuelle.

## Organisation

Le contrat d'architecture est [`ARCHITECTURE.md`](ARCHITECTURE.md) (le pourquoi : [`REVIEW.md`](REVIEW.md)).

- `spectre/kernel/` - le noyau, sans métier : base SQLite et migrations versionnées par plugin
  (`db.py`), manifeste d'un plugin (`plugin.py`), erreurs, verrous, e-mail, service des pages et
  construction de l'application (`app.py`, `create_app()` lancé par uvicorn en mode factory) ; son
  front (`static/`, servi sous `/static/kernel/`) : client HTTP (`api.js`), utilitaires d'affichage
  (`ui.js`), barre du haut (`shell.js`), feuille de style de la charte (`kernel.css`), logo et
  bibliothèques embarquées (`vendor/`).
- `spectre/plugins/<plugin>/` - une fonctionnalité par plugin (comptes, projets corporate,
  µprojets, structures, expériences, lots...), chacun avec ses routes (`api.py`), son domaine
  (`service.py`...), ses tables (`migrations.py`), ses pages HTML (`pages/`) et son front JS/CSS
  vanilla (`static/`, servi sous `/static/<plugin>/` : son `client.js` - le global `<plugin>Api`,
  seul endroit où s'écrivent ses URL d'API -, ses contrôleurs de page et sa `<plugin>.css`) ; la
  liste ordonnée est `spectre/plugins/__init__.py`.
  Aucune logique de simulation, de diff ou de versioning n'est réécrite : elle est importée depuis
  StructureForge et Follow. De même, aucune requête ni formule KPI de caractérisation : le plugin
  `characterization` n'est que l'adaptateur de PRISM.
- Les pages sont du HTML/CSS/JS vanilla, une page par écran. Un µprojet s'appelle
  `microproject` partout en interne (table SQLite `microprojects`, dossier
  `data/microprojects/<slug>`, plugin `microprojects`) ; le français « µprojet » est réservé à ce
  que voit l'utilisateur - les URLs (`/microprojets/...`, `/api/microprojets/...`), les libellés, et
  la clé de scope `"microprojet"` des payloads à trois niveaux. Les anciennes URLs `/projets/...`
  redirigent (308) vers `/microprojets/...`, et une installation antérieure au renommage se migre
  toute seule au démarrage - tables, colonnes et dossier `data/projects/` compris (première
  migration du plugin `microprojects`).
- `library/` - la bibliothèque racine (matériaux/présets/briques/recettes), voir son propre
  `README.md`.

## Tests

```bash
pytest
```

Le front-end (`spectre/kernel/static/`, `spectre/plugins/*/static/`) reste des balises `<script>` classiques sans bundler, mais
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

JavaScript (`tests_js/`, `node --test` exécute les vrais fichiers de `spectre/plugins/
structures/static/builder/` - voir `tests_js/helpers/load-structure-builder.js`) : encore partiel, seule
la logique pure du registre `STEP_KIND_DEFS` est couverte pour l'instant, le reste du constructeur
dépend du DOM et n'a que la vérification manuelle (Playwright) faite pendant le développement.

| Module | Couverture (lignes) |
|---|---|
| `step-kinds.js` | 51 % |
| `code-export.js` | 44 % |
| `form-widgets.js` | 16 % *(les widgets eux-mêmes touchent le DOM ; seuls `modeSummary`/`parseOpenings` sont testés)* |
| `context.js`, `substrate.js`, `step-list.js`, `objectives.js`, `campaign.js`, `simulation.js`, `experience-launch.js`, `library-mode.js`, `main.js` | 0 % *(pilotage du DOM/état - pas encore de tests automatisés)* |
