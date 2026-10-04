# Spectre

Spectre suit les expériences de procédé d'une équipe, de la définition de la structure jusqu'à la
conclusion. Chaque expérience a une **fiche d'identité** : intention, structure, plaques suivies,
cahier de données et conclusion. Ce que Spectre apporte : des comptes, des µprojets avec des droits
par membre, une couche de pilotage (projets corporate, thématiques, objectifs) et une interface web
unique.

L'application relie trois bibliothèques et n'en réécrit pas la logique :

- **[StructureForge](https://github.com/dmholy/structureforge)** construit et simule un empilement
  de couches (substrat, dépôt, gravure, planarisation, lithographie).
- **[Follow](https://github.com/dmholy/follow)** versionne chaque expérience : versions immuables,
  pistes, fourches, fusions, diff, étiquettes.
- **[PRISM](https://gitlab-it.aledia.com/sda/tools/soft/prism)** (`prism-aledia-datahook`) est le
  dictionnaire des données de caractérisation (EQE, PL, NCEL...) : requêtes, formules KPI, cache.
  Il est partagé avec les autres projets Aledia et alimente la page **Data** et le cahier de
  données des fiches.

## Hiérarchie métier

```
Projet corporate          Native (PT2), VLC (microlink), Nova (PT1)... et ses objectifs de la période
  └─ thématique           un axe technique du projet (dopage PGaN, double EBL...)
       └─ µprojet         une chaîne d'expériences, numérotée d'après son projet (Nat_0004, lien court /p/Nat_0004)
            └─ expérience     une piste versionnée : brouillon → en cours → conclue
                 └─ entité physique   une plaque suivie (lasermark, emplacement, FDL)
                      └─ structure       le procédé simulé par StructureForge, ou une suite d'images
                           └─ étape          une opération (dépôt, gravure...), regroupable en brique technologique
```

- **Piste et versions.** Une expérience est une **piste** (une branche Follow, nommée d'après son
  titre : `epitaxie-a-20-nm`). Chaque écriture crée une **version** immuable (`exp_<hex>`) ; la
  piste désigne toujours sa dernière version. Partir d'une version existante crée une nouvelle
  piste (fourche explicite). **Combiner** deux études (« Actions avancées » de la fiche, puis
  « Combiner… ») crée une nouvelle étude, issue des deux (le graphe de filiation et l'évolution des
  structures montrent ses deux parents), avec la structure de la première, son titre (proposé
  « A + B »), son intention, son hypothèse et une nouvelle plaque ; son cahier démarre vide et les
  deux études ne bougent pas.
- **Numéro de version.** Chaque version porte un numéro `X.Y.Z` calculé depuis la structure
  (`experiments/versioning.py`) : majeur si le substrat ou la suite d'étapes change, mineur si un
  paramètre d'étape change, correctif si seul un nom d'étape, l'unité ajoutée à un paramètre
  déclaré ou une étiquette de couche change ; regrouper des étapes en brique ne change pas la
  version (au plus un correctif, quand cela regroupe des étiquettes).
- **Ref.** Une ref est un repère local d'un µprojet (une étiquette Follow nommée, « ref vX.Y.Z »
  par défaut). Celles qui existent restent affichées, et un editor peut les renommer ou les
  retirer (la version, elle, reste) ; on n'en pose plus de nouvelles depuis les pages : un point de
  départ partagé est une référence (ci-dessous).
- **Références de structure.** Une référence (« epitaxie-standard ») est un objet de toute
  l'application, pas d'un µprojet : ses versions, numérotées `MAJEUR.MINEUR` par le serveur, sont
  publiées depuis les études de n'importe quel µprojet (« Publier comme référence » : tout editor du
  µprojet source), chacune comparée à la version de référence dont elle dérive - un changement
  majeur donne le majeur suivant, un réglage, une étiquette ou une unité seule le mineur suivant,
  une structure identique est refusée ; deux dérivations d'une même version reçoivent 1.1 et 1.2.
  Chaque version garde un instantané de la structure (procédé, paramètres déclarés et leur unité,
  étiquettes, briques), qui se dessine et se reprend même si l'étude source disparaît, et dit d'où
  elle vient (qui, quand, quel µprojet, quelle piste et version : seulement le nom du µprojet pour
  qui n'en est pas membre). Une étude lancée depuis une référence retient la version dont elle part
  (`reference_origin`, reportée à ses versions suivantes et à ses fourches) : la référence en compte
  les usages. Renommer, décrire ou retirer une référence revient à son créateur ou à un admin. Les
  refs locales nommées à la main avant les références (la même « epitaxie-standard » dans deux
  µprojets) y ont été regroupées par nom, sans toucher aux dépôts Follow.
  Côté pages : **Références** dans la barre du haut (`/references`, aussi depuis la Bibliothèque)
  liste les références, la plus récemment mise à jour d'abord (dernière version, date, µprojet
  source, usages, recherche, « Nouvelle référence ») ; `/references/{slug}` montre l'évolution
  d'une référence avec le diagramme de la page d'évolution des structures, en versions de
  référence seules (1.0, 1.1, 2.0 ; branches parallèles en colonnes, rattachements déduits en
  pointillés) et, pour une version, sa structure étiquetée, son auteur, sa note, sa source, ses
  usages, la comparaison à une autre version et « Partir de cette version ». « Publier comme
  référence » (fiche, page d'évolution) propose la référence dont vient l'étude, ou une autre, ou
  une nouvelle, et affiche le numéro calculé. **Nouvelle expérience** (page µprojet, accueil)
  ouvre d'abord « Partir d'une référence » (recherche, dernière version proposée, autre version,
  aperçu) ; partir d'une structure vierge, d'une image ou de la bibliothèque reste en second. La
  fiche dit « Issue de la référence X 1.1 », et la page d'un µprojet tout juste créé propose d'y
  lancer la première expérience depuis une référence.
- **Évolution des structures.** La page `/microprojets/{slug}/evolution` (bouton « Évolution des
  structures » de la page µprojet et de la fiche) dessine les pistes en colonnes, façon git : un
  nœud `vX.Y.Z` par version structurelle (majeure, mineure), les fourches, les combinaisons et les refs
  en badges, les versions publiées comme référence en badges « R nom 1.1 », avec une bascule
  « Toutes les versions ». Sur un nœud : publier comme référence, renommer ou retirer une ref
  locale, comparer à une autre version, suivre une ref (ce qui en descend), partir de cette
  version. L'ancienne adresse `/microprojets/{slug}/refs` y redirige.
- **Étapes.** Chaque étape d'un procédé a un identifiant stable, conservé quand on insère, déplace
  ou supprime d'autres étapes à une évolution : une campagne DOE désigne ses étapes par cet
  identifiant, et non plus par leur position.
- **Étiquettes de couches.** Dans le constructeur, une étape qui crée une couche peut être
  « affichée sur la structure » : son nom (« p-GaN », le matériau par défaut) et, dessous, son
  épaisseur, sa composition ou ses paramètres déclarés (un dopage), écrits à droite du dessin et
  reliés à la couche - pour qu'une capture d'écran porte l'essentiel. Seules les étapes choisies en
  portent une ; elles sont enregistrées avec la version (sans compter comme un changement de
  structure) et avec les structures et briques de la bibliothèque, et se retrouvent sur la fiche
  (bouton « Étiquettes : masquer / afficher »), la page d'évolution et le rapport.
  Les étapes étiquetées d'une même brique n'ont qu'une étiquette, celle de la brique : son nom,
  une ligne par étape (« p-GaN : 120 nm · dopage Mg 3e18 cm⁻³ ») et une accolade sur leurs
  couches. Un paramètre déclaré a son unité (cm⁻³, %, °C...), écrite sur l'étiquette. Le diff
  d'une version dit, à part de la structure, ce qui change aux étiquettes.
- **Briques d'un procédé.** Une brique insérée dans le constructeur (ou formée d'étapes
  choisies) reste un groupe d'étapes, enregistré avec la version, les structures et briques de
  la bibliothèque, et retrouvé à la réouverture (évolution, fourche, modèle).
- **Cahier de données.** Toutes les données d'une expérience sont dans un seul cahier (onglet
  « Données » de la fiche) : des entrées PRISM (un instantané par étape et une vue DataViz) ou
  saisies à la main (valeur, texte, tableau collé d'Excel, images annotées, fichiers, images
  externes - TEM, scans référencés sur le serveur sans être copiés, choisies dans un dossier
  autorisé et légendées -, liens). Les jeux de l'ancienne galerie « Images de mesure » y sont des
  entrées comme les autres. Une
  entrée nomme les plaques mesurées et les étapes du procédé où la mesure a été faite, choisies sur
  un **stepper** ; la vue du procédé affiche un badge par étape mesurée. **La donnée suit la
  plaque** : si la piste ne suit plus ces plaques, l'entrée reste, repliée dans « Autres plaques ».
  La conclusion cite des entrées du cahier. Les anciennes preuves et les jeux de l'ancienne galerie
  « Images de mesure » s'y lisent comme des entrées saisies à la main, sans migration.
- **Annotations des images.** Toute image que Spectre montre s'annote : une image téléversée ou
  externe d'une mesure du cahier, une image d'une structure en images. Des flèches et des cadres,
  numérotés sur l'image et légendés dans une liste dessous, posés sur la fiche par un éditeur ;
  ils restent à leur place quelle que soit la taille de l'image et suivent leur image quand on
  réordonne. Les vignettes (graphe, atlas, planche du constructeur, aperçus du cahier) et le rapport
  les montrent. Annoter une structure en images n'en change pas la version de structure.
- **Droits.** Trois niveaux :
  - **administrateur** : tout ; il est propriétaire de tous les µprojets, même sans en être membre ;
  - **manager d'une équipe** : gère les projets corporate rattachés à son équipe (les renommer, les
    supprimer, leurs thématiques et objectifs), peut en créer dans son équipe, et il est propriétaire
    des µprojets de ces projets ;
  - **membre d'un µprojet** : son rôle, `viewer`, `editor` ou `owner`.

  Un compte peut être dans plusieurs équipes, manager dans certaines seulement. Un µprojet suit
  l'équipe de son projet corporate ; un µprojet non rattaché tombe dans « Non classé », qui n'a pas
  d'équipe (seuls l'administrateur et ses membres y ont accès). Projets et thématiques restent
  visibles par tout compte connecté. Le badge de rôle dit d'où vient un droit : « Propriétaire
  (manager) », « Propriétaire (admin) ». Créer un µprojet dans le projet d'une équipe, ou l'y
  déplacer, est réservé aux membres de cette équipe (managers compris) et à l'administrateur ; un
  projet sans équipe et « Non classé » restent ouverts à tous.

## Démarrer en local

### Windows

Prérequis : [Python 3.11+](https://www.python.org/downloads/) (cocher « Add python.exe to PATH ») et
[Git](https://git-scm.com/download/win). L'installation télécharge StructureForge et Follow depuis
GitHub, et PRISM depuis gitlab-it.aledia.com : il faut être sur le réseau Aledia.

1. Cloner le dépôt : `git clone https://github.com/DmHoly/Spectre.git` puis `cd Spectre`.
2. **`install.bat`** crée `.venv` et y installe Spectre en mode éditable avec ses dépendances de
   développement (`pip install -e ".[dev]"`). Il signale si `%USERPROFILE%\.prism\connections.yml`
   manque.
3. **`start.bat`** lance le serveur dans une nouvelle fenêtre (`spectre --port 8000`) et ouvre
   `http://127.0.0.1:8000/`. Les données vont dans `data\` du dépôt, sauf si `SPECTRE_DATA_DIR` est
   déjà défini. Fermer la fenêtre (ou `Ctrl+C`) arrête le serveur.
4. **`update.bat`** met à jour : il se place sur `main`, fait `git pull origin main --ff-only`,
   réinstalle les dépendances, puis force la réinstallation de StructureForge, Follow et PRISM
   (sans cela, `pip` garde la version déjà installée d'une dépendance `git+https`). Attention : sur
   une autre branche, il bascule sur `main`.

### macOS / Linux

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
spectre --port 8000          # http://127.0.0.1:8000/
```

`spectre` (ou `spectre start`) accepte `--host` (défaut `127.0.0.1`), `--port` (défaut `8000`) et
`--reload`. L'application est construite par `spectre.kernel.app:create_app` en mode factory
d'uvicorn.

### Docker

```bash
docker compose up -d --build     # http://localhost:8000/
```

L'image (`Dockerfile`, `python:3.11-slim`) installe le paquet avec pip, ce qui demande un accès
sortant vers GitHub et gitlab-it.aledia.com. Elle tourne en utilisateur non privilégié, écoute sur
`0.0.0.0:8000` et écrit sous `/data` (`SPECTRE_DATA_DIR=/data`, `PRISM_DATA_DIR=/data/prism`).
`docker-compose.yml` monte un volume nommé `spectre-data` sur `/data`, définit `SPECTRE_BASE_URL`
et laisse les variables SMTP en commentaire. Sans compose :

```bash
docker build -t spectre .
docker run -d -p 8000:8000 -v spectre-data:/data --name spectre spectre
```

PRISM se configure au lancement, pas dans l'image : monter un `connections.yml`, pointer
`PRISM_CONNECTIONS_FILE` dessus et passer les identifiants par variables d'environnement.

Il n'y a pas d'intégration continue : lancer les tests et construire l'image avant de déployer
reste manuel.

## Configuration

Variables lues par le code de Spectre :

| Variable | Rôle | Défaut |
|---|---|---|
| `SPECTRE_DATA_DIR` | Dossier des données : `spectre.db`, `microprojects/<slug>/` (dépôt Follow, pièces jointes, instantanés), `library/`, cache PRISM | `./data` (résolu depuis le dossier courant) |
| `SPECTRE_LIBRARY_DIR` | Dossier de la bibliothèque YAML éditable | `<SPECTRE_DATA_DIR>/library` |
| `SPECTRE_EXTERNAL_IMAGE_ROOTS` | Racines autorisées pour les images externes (TEM, scans) d'une fiche, séparées par `;` sous Windows et `:` ailleurs. Sans elle, le parcours de dossiers est désactivé (503) et seuls les chemins locaux sont acceptés, pas les chemins réseau | (aucune) |
| `SPECTRE_DEMO_DATA` | `1` : données de caractérisation synthétiques à la place de PRISM, et activation du plugin `kpis_demo` (séries de KPI fictives) | (désactivé) |
| `SPECTRE_BASE_URL` | URL publique utilisée dans les liens des e-mails (invitation, mot de passe oublié) | (vide : liens relatifs) |
| `SPECTRE_COOKIE_SECURE` | `1`/`true`/`yes`/`on` force l'attribut `Secure` du cookie de session, toute autre valeur le retire | `Secure` si `SPECTRE_BASE_URL` commence par `https://` |
| `SPECTRE_SMTP_HOST` | Serveur SMTP. Absent : aucun e-mail n'est envoyé, seuls le destinataire et l'objet sont journalisés | (aucun) |
| `SPECTRE_SMTP_PORT` | Port SMTP (connexion en STARTTLS) | `587` |
| `SPECTRE_SMTP_USER` / `SPECTRE_SMTP_PASSWORD` | Identifiants SMTP | (aucun) |
| `SPECTRE_SMTP_FROM` | Expéditeur | `SPECTRE_SMTP_USER`, sinon `spectre@localhost` |
| `SPECTRE_EMAIL_DEBUG` | `1` : sans SMTP, journalise aussi le corps des e-mails, donc leurs liens. Poste de développement uniquement | (désactivé) |
| `PRISM_DATA_DIR` | Cache disque de PRISM. Le plugin characterization le fixe à son premier accès à PRISM s'il n'est pas défini | `<SPECTRE_DATA_DIR>/prism` |

Variables lues par PRISM lui-même (voir sa documentation) :

| Variable | Rôle | Défaut |
|---|---|---|
| `PRISM_CONFIG_DIR` | Dossier de `connections.yml` et `credentials.ini` | `~/.prism` |
| `PRISM_CONNECTIONS_FILE` | Fichier de profils de connexion | `<PRISM_CONFIG_DIR>/connections.yml` |
| `PRISM_USER` / `PRISM_PASSWORD` | Compte de lecture commun à tous les profils | (aucun) |
| `PRISM_<PROFIL>_USER` / `PRISM_<PROFIL>_PASSWORD` | Compte propre à un profil (prioritaire) | (aucun) |
| `PRISM_HOOKS_DIR` | Jeu de hooks à utiliser à la place de celui du paquet | hooks du paquet installé |

## Données de caractérisation (PRISM)

La page **Data** (`/donnees`) et l'onglet « Données » des fiches interrogent les bases via PRISM.
La configuration se fait une fois par poste, **hors du dépôt** (aucun secret n'y est commité) :

1. copier le modèle `config/connections.example.yml` du dépôt PRISM en `~/.prism/connections.yml`
   (`%USERPROFILE%\.prism\connections.yml` sous Windows) : hôtes et bases, sans mot de passe ;
2. créer `~/.prism/credentials.ini` avec le compte de lecture :
   ```ini
   [DEFAULT]
   user = ...
   password = ...
   ```
   ou définir `PRISM_USER` / `PRISM_PASSWORD`. Les anciens noms (`[DB_CREDENTIALS]`,
   `DB_LUMIERE_USER` / `DB_LUMIERE_PASSWORD`) restent acceptés ;
3. vérifier, sans connexion à une base : `prism doctor`.

Sans cette configuration, Spectre fonctionne ; seule une requête de données répond 503
(« configuration de connexion PRISM incomplète »). Une base injoignable ou une requête en échec
répond 502. Les requêtes et formules KPI se corrigent dans le dépôt PRISM, pas dans Spectre.

**Mode démo.** `SPECTRE_DEMO_DATA=1` remplace PRISM par une source synthétique, signalée comme
telle, et active les KPI fictifs des pages de projet. C'est utile pour une instance de démonstration
sans accès aux bases.

## Administration

- **Premier administrateur.** Le tout premier compte inscrit devient administrateur
  (`users.is_admin`). Un administrateur gère les projets corporate, thématiques et objectifs, et
  modifie la bibliothèque YAML.
- **Équipes.** La page `/equipes` liste les équipes ; tout compte connecté la lit. Un
  administrateur crée les équipes, y ajoute un premier manager, puis rattache chaque projet
  corporate à son équipe (champ « Équipe » du dialogue « Modifier » de la page du projet). Un manager ajoute ensuite les
  membres de son équipe et en nomme d'autres managers ; une équipe garde toujours au moins un
  manager. À la mise à jour, rien n'est rattaché : les droits ne changent pas tant qu'un
  administrateur n'a pas créé d'équipes.
- **Promouvoir ou rétrograder** un compte :
  ```bash
  spectre admin quelquun@exemple.com            # promouvoir
  spectre admin quelquun@exemple.com --revoke   # rétrograder
  ```
- **Migrations.** Au démarrage, `create_app()` applique les migrations de chaque plugin qui ne
  figurent pas encore dans la table `schema_migrations(plugin, migration_id, applied_at)`, dans
  l'ordre des plugins puis de leurs migrations, une transaction par migration. Rien à lancer à la
  main ; une installation antérieure au renommage `projet → µprojet` se migre aussi
  automatiquement. `spectre admin` applique les migrations avant d'agir. Avant la première
  migration en attente, la base et les fichiers que les migrations réécrivent sont copiés dans
  `<SPECTRE_DATA_DIR>/backups/<horodatage>/` : l'ancien code ne lit pas une base migrée, revenir
  à une version précédente, c'est arrêter Spectre et remettre cette copie en place.
- **Bibliothèque YAML.** Matériaux, recettes, présets d'étape, briques technologiques et textes de
  la section intention sont des fichiers YAML dans `<SPECTRE_DATA_DIR>/library` (ou
  `SPECTRE_LIBRARY_DIR`). Au premier démarrage, ce dossier est créé depuis
  `spectre/plugins/library/defaults/` (format décrit dans son `README.md`) ; s'il existe encore un
  dossier `library/` à la racine du dépôt (ancien emplacement), ses `*.yml` priment. Un
  administrateur édite ces fichiers depuis `/bibliotheque` ; un YAML invalide est refusé (422), et
  les modifications sont prises en compte sans redémarrage.

## Scripts

Les deux scripts lisent `--data-dir`, sinon `SPECTRE_DATA_DIR`, sinon `./data`.

- **`python scripts/seed_demo.py [--data-dir DOSSIER]`** crée le compte de démonstration
  `demo@spectre.local` / `demo1234`, deux coéquipiers (`lea@spectre.local`, `marc@spectre.local`,
  même mot de passe) et deux µprojets remplis sur des nanofils GaN pour LED (puits quantique simple ;
  puits multiples avec et sans EBL), avec fourches, combinaison et refs. Tout passe par les routes HTTP ;
  seules les dates de création sont recalées ensuite pour étaler l'historique sur un an. Le script
  **écrit directement** (pas de mode à blanc) et suppose un dossier de données neuf : relancé sur
  un dossier déjà semé, l'inscription des comptes échoue. Les µprojets de démo ne sont rattachés à
  aucun projet corporate.
- **`python scripts/repair_hypotheses.py [--data-dir DOSSIER] [--microproject SLUG] [--apply]`**
  reporte sur la pointe de chaque piste qui l'a perdue la dernière hypothèse non vide de son
  historique (bug B1 de `REVIEW.md`). **À blanc par défaut** : il affiche ce qu'il ferait ;
  `--apply` écrit, par `experiments.service.amend()`. Arrêter le serveur avant `--apply`.

## Architecture en un écran

Un **noyau** sans métier (`spectre/kernel/`) et des **plugins** (`spectre/plugins/<plugin>/`).
Le noyau fournit la base SQLite et l'exécuteur de migrations, le manifeste `Plugin`, les erreurs
du domaine et leur traduction en codes HTTP, les verrous, l'e-mail, le service des pages avec la
barre du haut commune, et son front (`/static/kernel/` : `api.js`, `ui.js`, `shell.js`,
`kernel.css`, `vendor/`). Chaque plugin possède ses routes (`api.py`), son domaine (`service.py`),
ses tables (`migrations.py`), ses pages (`pages/`) et son front (`static/`, servi sous
`/static/<plugin>/`).

| Plugin | Responsabilité | API | Pages |
|---|---|---|---|
| `accounts` | Comptes, sessions, mot de passe, profil, rôle admin | `/api/users`, `/api/sessions`, `/api/password-resets` | `/connexion`, `/inscription`, `/mot-de-passe-oublie`, `/reinitialiser`, `/profil` |
| `teams` | Équipes, managers et membres | `/api/teams` | `/equipes`, `/equipes/{slug}` |
| `search` | Recherche de la barre du haut, agrège les fournisseurs des autres plugins | `/api/search` | — |
| `library` | Bibliothèque YAML de l'instance, édition admin, textes d'interface | `/api/library/files`, `/api/ui-texts` | — |
| `areas` | Projets corporate et leur équipe, thématiques, objectifs | `/api/areas`, `/api/thematics` | `/`, `/management/{slug}`, `/management/{slug}/thematiques/{thematique_slug}` |
| `microprojects` | µprojets, numéro, rattachement, membres, rôles, invitations, règle d'accès (admin, manager, membre) | `/api/microprojects`, `/api/invitations` | `/microprojets/{slug}`, `/p/{code}` |
| `attachments` | Fichiers téléversés d'un µprojet | `/api/microprojects/{mp}/attachments` | — |
| `structures` | Pont StructureForge : matériaux, recettes, simulation, aperçu DOE, types de structure | `/api/materials`, `/api/recipes`, `/api/simulations`, `/api/campaign-previews` | constructeur et structure en images (`/microprojets/{slug}/structures/...`, `.../evoluer`, `.../evoluer-image`) |
| `process_library` | Structures enregistrées, présets d'étape, briques technologiques | `/api/saved-structures`, `/api/step-presets`, `/api/tech-bricks` | `/bibliotheque`, `/microprojets/{slug}/presets-etapes`, `/microprojets/{slug}/briques-technologiques` |
| `experiments` | Pistes et versions Follow : création, évolution, statut, conclusion, étiquettes, entités, combinaison de deux études, diff, filiation, refs, statistiques | `/api/microprojects/{mp}/experiments`, `.../lineage`, `.../refs`, `.../structure-history`, `/api/experiment-stats`, `/api/experiment-timeline` | `/microprojets/{slug}/experiences/{experiment_id}`, `/microprojets/{slug}/evolution` |
| `references` | Références de structure de toute l'application : versions `MAJEUR.MINEUR` publiées depuis les études, instantanés, évolution, usages, regroupement des refs locales d'avant | `/api/references`, `/api/reference-versions` | `/references`, `/references/{slug}` |
| `intent_forms` | Formulaires d'intention et formulaire actif d'un µprojet | `/api/intent-forms`, `/api/microprojects/{mp}/active-intent-form` | `/microprojets/{slug}/formulaire-intention` |
| `wafers` | Index des plaques suivies, recherche par lasermark et FDL, visibilité | `/api/wafers` | `/plaques/{lasermark}` |
| `lots` | Lots de fabrication, wafers, thématiques visées, Gantt | `/api/lots`, `/api/lot-priorities` | `/lots`, `/lots/{code}` |
| `links` | Liens entre µprojets et entre entités physiques | `/api/microproject-links`, `/api/entity-links` | — |
| `atlas` | Vue graphe d'un projet corporate | `/api/areas/{area_slug}/atlas` | `/management/{slug}/atlas` |
| `characterization` | Adaptateur PRISM (ou source démo) : catalogue, requêtes, graphiques | `/api/characterization` | `/donnees`, `/donnees/{key}` |
| `external_images` | Politique des images externes (racines autorisées, formats) et parcours des dossiers ; les images sont un contenu du cahier | `/api/microprojects/{mp}/external-images` (et `.../roots`) | — |
| `notebook` | Cahier de données d'une étude, le seul : entrées PRISM (instantanés et vues DataViz) et manuelles (valeurs, textes, tableaux, fichiers, images externes, liens - les anciennes preuves et les anciens jeux d'images), rattachées aux plaques mesurées et aux étapes du procédé | `/api/microprojects/{mp}/snapshots`, `.../experiments/{exp}/notebook-entries` (et `.../{entry_id}/external-images/{index}`) | — (panneau de la fiche) |
| `kpis` | Registre de KPI et séries mensuelles d'un projet corporate | `/api/areas/{area_slug}/kpis` | — |
| `kpis_demo` | Séries et fiche d'étude fictives, actif seulement si `SPECTRE_DEMO_DATA=1` | `/api/areas/{area_slug}/kpis/{kpi_key}/studies` | — |
| `docs` | Documentation dans l'application | — | `/docs`, `/docs/guide`, `/docs/exemples`, `/docs/architecture` |

Règles principales :

- **Dépendances en DAG.** Chaque plugin déclare `depends_on` et n'importe que ces plugins, et
  seulement leurs modules publics (`service`, `models`, `deps`, `schemas`), jamais leur `api`. Le
  noyau n'importe aucun plugin. `PLUGINS` (`spectre/plugins/__init__.py`) est dans l'ordre
  topologique, vérifié au démarrage.
- **Le domaine ignore HTTP.** `service.py` lève les exceptions de `spectre.kernel.errors` ; le noyau
  les traduit en codes HTTP à un seul endroit.
- **Le front passe par `client.js`.** Pages en HTML/CSS/JS vanilla, sans bundler. Chaque plugin
  expose un global `<plugin>Api` (camelCase) dans `static/client.js`, seul endroit où s'écrivent
  ses URL d'API.
- **Pas de HTML sous `/api`.** L'API est en anglais ; les URL de pages restent en français.

Le contrat complet (modules du noyau, points d'extension, conventions, table des routes, front de
la fiche) est dans [`ARCHITECTURE.md`](ARCHITECTURE.md). Les constats et les raisons des choix sont
dans [`REVIEW.md`](REVIEW.md).

### Ajouter un plugin

1. Créer le paquet `spectre/plugins/<nom>/` avec `api.py` (un `APIRouter` sous `/api`),
   `service.py` (sans FastAPI), `schemas.py` si besoin, `pages/` et `static/`.
2. Écrire le manifeste dans `__init__.py` : `PLUGIN = Plugin(name="<nom>", depends_on=(...),
   router=router, pages=(Page(...),), nav=(NavEntry(...),), migrations=MIGRATIONS)`. Le nom est le
   même que le dossier, que `/static/<nom>/` et que `tests/plugins/<nom>/`.
3. L'ajouter à `PLUGINS` dans `spectre/plugins/__init__.py`, **après** chacun des plugins dont il
   dépend.
4. Déclarer ses tables dans `migrations.py` : `MIGRATIONS = (Migration("0001_initial", SQL), ...)`.
   Une migration appliquée ne se modifie plus ; un changement s'ajoute en nouvelle migration
   (`kernel.db.rebuild_table()` pour un changement non additif).
5. Écrire `static/client.js` avec le global `<nom>Api`, une fonction par appel ; les pages
   chargent `/static/kernel/api.js`, `ui.js`, `shell.js`, puis les `client.js` utilisés, puis leur
   contrôleur, et portent le marqueur `<!-- spectre:topbar -->`.
6. Tests : `tests/plugins/<nom>/` pour les tests HTTP, `tests/support/<nom>.py` pour les helpers.
7. Lancer les contrats (`pytest tests/contracts tests/kernel`) : ils vérifient l'ordre de
   `PLUGINS`, les imports, les routes appelées par le front, les fichiers statiques et le 401
   anonyme. Une route publique ou un appel à URL dynamique s'y déclarent explicitement.

## API

Résumé des conventions (détail : `ARCHITECTURE.md` § 4) :

- Ressources en anglais, au pluriel, en kebab-case ; une action métier est une sous-ressource
  (`PUT .../conclusion`, `PUT .../status`). JSON en `snake_case` ; collections paginées en
  `{"items": [...], "total": n}`.
- Une expérience est désignée par sa piste : `GET /api/microprojects/{mp}/experiments/{experiment_id}`
  renvoie la dernière version avec `ETag: "<version_id>"`. Toute écriture sur une piste accepte
  `If-Match: "<version_id>"` ; si la piste a avancé, la réponse est **412** et rien n'est écrit.
  Bifurquer, c'est `POST .../experiments` avec `from_version`. Une modification sans effet renvoie
  200 sans créer de version.
- Codes : 201 + `Location` à la création, 204 à la suppression, 401 seulement sans session, 403
  droit insuffisant, 404 introuvable, 409 conflit ou doublon, 412 `If-Match` périmé, 413 fichier
  trop gros, 422 saisie invalide (identifiants de connexion refusés compris), 502/503 pour PRISM.
  Erreurs au format `{"detail": "<message en français>", "code": "<code>"}`.

La liste des routes, avec leur correspondance aux anciennes, est dans `ARCHITECTURE.md` § 5.
Swagger UI et ReDoc sont désactivés (`docs_url=None`, `redoc_url=None`) ; `/docs` est la
documentation de l'application. Le schéma brut reste servi par FastAPI sur `/openapi.json`.

## Tests

```bash
pip install -e ".[dev]"
pytest                                   # ou : pytest -q -p no:warnings
pytest --cov --cov-report=term-missing   # couverture (pytest-cov)
```

| Dossier | Contenu |
|---|---|
| `tests/plugins/<plugin>/` | Tests HTTP de chaque plugin |
| `tests/support/` | Helpers et fabriques ; chaque helper encapsule une route |
| `tests/contracts/` | Contrats : chaque appel du front vise une route existante (méthode et chemin), chaque `client.js` déclare un seul global `<plugin>Api` et aucune URL `/api/` n'est écrite hors des clients, chaque fichier statique nommé est servi, le graphe d'imports respecte le DAG, toute route non publique répond 401 sans session, les clés de registre Follow des structures restent figées |
| `tests/kernel/` | Noyau : migrations, erreurs, verrous, e-mail, écriture atomique, service des pages et ordre des plugins |
| `tests/integration/` | Parcours qui traversent plusieurs plugins |

`tests/conftest.py` isole `SPECTRE_DATA_DIR`, `PRISM_DATA_DIR`, `SPECTRE_LIBRARY_DIR`, le SMTP et le
mode démo : aucun test ne touche les données ou la configuration du poste. Les contrats activent
`SPECTRE_DEMO_DATA=1` pour couvrir aussi `kpis_demo`.

Les tests JavaScript (`tests_js/`) exécutent les vrais fichiers du constructeur de structure
(`spectre/plugins/structures/static/builder/`) avec le test runner intégré de
[Node.js](https://nodejs.org/) 18+, sans dépendance à installer. Seule la logique pure (registre des
types d'étape, génération de code, résumés) est couverte ; le reste dépend du DOM.

```bash
node --test
node --test --experimental-test-coverage
```

## Feuille de route

Les évolutions prévues et les dettes notées sont dans [`TODO.md`](TODO.md), notamment :

- la réécriture de la documentation intégrée (`/docs`), en dernier.
