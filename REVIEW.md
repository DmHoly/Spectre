# Revue de code de Spectre — SOLID, REST, découpage en plugins

*Revue du 2 octobre 2026, sur `03f4646` (« ajout du systeme de lot »), avant refactor.*

**Méthode.** Douze relecteurs ont couvert chacun un périmètre :
- noyau ; comptes ;
- µprojets ; expériences, côté back et côté front ;
- structures, côté back et côté front ;
- management ; données PRISM ; plaques et lots ;
- tests ; graphe de dépendances.

Chaque constat coûteux a ensuite été soumis à un second relecteur chargé de le **réfuter**, en
relisant le code et, souvent, en écrivant une sonde `TestClient` jetable. Un seul constat a été
réfuté entièrement. Une centaine ont été nuancés, et leur formulation corrigée est celle retenue
ici. Les numéros de ligne renvoient à `03f4646`. Le contrat d'architecture qui en découle est dans
[`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## 1. Diagnostic

Le code est **localement propre** : fonctions courtes, docstrings utiles, stdlib plutôt que
dépendances (PBKDF2, smtplib, un client HTTP de 56 lignes), pas d'ORM ni de framework front. Le
problème n'est pas la qualité des fonctions. C'est la **direction des dépendances** et
l'**identité des données** :

- **L'infrastructure dépend du métier.** `core/db.py` porte les 14 tables de 7 fonctionnalités et
  leurs données de départ. `api/app.py` connaît chaque écran. `common.js` contient les widgets de
  6 fonctionnalités et il est chargé par 24 pages.
- **Des routeurs servent de bibliothèques à d'autres routeurs.** `api/experiments.py` (1 695 lignes)
  exporte `lineage_graph`, `_derive_branch` et `_not_found` vers `lots`, `management` et
  `notebook`. Il importe lui-même 12 symboles, dont des privés, de `api/structures.py`.
- **Le chemin d'écriture d'une expérience est recopié 13 fois.** Le motif dériver → recopier
  6 champs → commiter → traduire les erreurs a divergé d'une copie à l'autre, et il a **déjà
  détruit des données**.
- **L'identité d'une étude est l'id de sa dernière version.** Chaque étiquette ou preuve change
  donc l'URL, casse les liens et fige les marque-pages.
- **L'API est faite de verbes français** (`/evoluer`, `/conclure`, `/statut`, `/epingle`,
  `/executer`, `/parcourir`), servis sous un `{ref:path}` glouton qui rend l'ordre d'inclusion des
  routeurs significatif.

Ces cinq points se renforcent : impossible d'extraire un plugin sans toucher au noyau, au routeur
des expériences et à `common.js` en même temps. Le refactor commence donc par inverser ces
dépendances, et non par renommer des URL.

---

## 2. Principes mobilisés

Seules les violations au coût **réel** sont développées. Les bénignes sont listées en une ligne.

### S — Responsabilité unique (le plus coûteux)

| Où | Raisons de changer réunies | Coût concret |
|---|---|---|
| `api/experiments.py` (1 695 l., 29 routes) | Présentation de la fiche, algorithme de filiation, rendu Plotly, évolutions, cycle de vie, preuves, étiquettes, entités, blobs, galerie DATA, refs, fusion, suppression | Toute nouvelle mutation recopie le passe-plat. La filiation, algorithme de domaine, vit dans un routeur importé par trois autres |
| `core/microprojects.py` (557 l.) | CRUD et numéros, membres, invitations avec rédaction et envoi d'e-mail, plan disque, fabriques des stores de 4 autres modules, activation du formulaire Follow, statuts d'expérience | 19 modules en dépendent. Tout plugin qui a besoin d'un store ou d'un statut vient le modifier |
| `api/structures.py` | Catalogues, 3 CRUD de bibliothèque, simulation, uploads, **et 3 routes de création d'expérience** | La logique de lancement est copiée 5 fois. Le titre obligatoire n'est contrôlé que dans 2 des 5 chemins |
| `core/db.py` | DDL de 7 fonctionnalités, migrations ad hoc, renommages hérités, données de départ, promotion d'admin | Aucun plugin ne possède ses tables. Les migrations ne savent qu'ajouter une colonne |
| `api/management.py` | Le routeur fait l'agrégation : stats par µprojet, frise, règle de visibilité | 2 à 3 rechargements complets de chaque dépôt Follow par µprojet et par page. Quatre définitions divergentes de « wafer » |
| `common.js` (702 l.) et `experience.js` (2 143 l.) | Statuts, FDL, PRISM, recherche fédérée, auth et navigation ; une vingtaine de responsabilités pour la fiche | Un renommage d'URL de n'importe quel plugin touche le « commun ». La fiche partage son état avec deux autres scripts par globales implicites |

Bénin : `core/structures.py` (7 sections bien découpées, un seul auteur ; seuls le DOE et le suivi
physique méritent de sortir), `core/lots.update()` (à scinder avant la synchro PRISM, cf. § 3),
`style.css` (5 254 l., aucun coût d'exécution).

### O — Ouvert/fermé

- **Dispatch sur le type de structure par comparaison de chaînes**, à 14 endroits dans 2 fichiers
  (`structure_type == ProcessLot.registry_key()`). Le nombre d'entités d'une campagne est recopié
  3 fois (`experiments.py:1049`, `1140`, `1381`). Un 4ᵉ type de structure oblige à retrouver et
  modifier chacun de ces sites, et un oubli donne un résultat faux sans aucune erreur. **Ici
  l'abstraction paie** : un Protocol `StructureKind` réduit à `key`, `render_svg` et
  `entity_count`, avec 3 implémentations réelles.
- **Ordre d'inclusion des routeurs significatif** (`app.py:55`). Un `GET`/`DELETE` déclaré sous
  `{ref:path}` par un routeur inclus après `experiments` est avalé en silence. C'est incompatible
  avec des plugins enregistrés indépendamment. Corrigé à la source par des identifiants d'un seul
  segment.
- **La recherche de la barre du haut code en dur 4 types et 4 endpoints** (`common.js:483-555`).
  Chaque type cherchable coûte 6 à 7 modifications et 4 requêtes par frappe.
- Bénin : `_scoped_store_getters` (le noyau µprojet connaît ses 4 bibliothèques), registre front
  `STEP_KIND_DEFS` sans repli (un type inconnu fait planter le constructeur).
- **Bons modèles existants, à généraliser** : `trends.register` et `DataViz.register` sont de
  vrais points d'extension. Ajouter un KPI ou une vue ne touche ni l'API ni le noyau.

### L — Substitution (deux cas, bénins)

- « Non classé » est un `ManagementArea` qui n'est pas substituable aux autres. Il est repéré par
  le slug magique `non-classe`, testé six fois côté front et traité à part côté back (pas de
  préfixe, pas de suppression), alors qu'on peut toujours lui ajouter thématiques et objectifs.
  Correctif : exposer `is_system`/`can_delete` et refuser côté back.
- La source de démonstration ne respecte pas le contrat de la source PRISM qu'elle remplace : elle
  liste des types qu'elle ne sait pas servir et répond 422 là où PRISM répond 404.

### I — Ségrégation des interfaces

- **`common.js` impose ses 6 domaines à toutes les pages**, docs et profil compris. Une
  redéclaration globale dans un autre script casse toute la page (SyntaxError).
- **Contrats implicites par globales** : `intent-form.js`, `objectives.js` et `intention-copy.js`
  exigent que la page hôte définisse `slug`, `state` et `showError`. `data-notebook.js` et
  `experience-data.js` lisent les globales d'`experience.js`. `microprojet-graphe.js` lit le
  `currentRole` déclaré en ligne dans `projet.html`. Renommer une variable casse un autre fichier,
  au clic et non au chargement.
- **`_detail` sert de charge utile fourre-tout** : chaque plugin rattaché à une expérience
  (cahier, galerie, pièces jointes) doit modifier le cœur pour y glisser sa clé.
- Bénin : la réponse « trois paniers » `{presets, partagees, microprojet}` des bibliothèques
  oblige 8 clients à la réaplatir.

### D — Inversion des dépendances

- **`core/permissions.py` importe `api.deps` et lève `HTTPException`.** Le coût d'exécution est
  faible. Mais c'est la dépendance que tous les plugins importeront : elle doit être rangée avant
  le découpage.
- **La suppression d'expérience écrit dans les attributs privés de Follow**
  (`repo._objects`, `_tags`, `_branches`, `_store.write_refs`, `experiments.py:1681-1693`). Le
  cache des plaques, lui, repose sur la disposition disque de Follow. **Les dépendances
  structureforge, follow et prism ne sont pas épinglées** (`@main`, `@master`, ou pas de ref du
  tout pour follow). C'est la cause des 3 tests rouges. La bonne inversion n'est pas un Protocol
  Spectre : il n'y a qu'une implémentation. C'est une méthode publique `Repository.delete_line()`
  dans Follow, que l'équipe maintient, et des SHA épinglés.
- **Deux adaptateurs PRISM** (`api/datahook.py`, `core/datasets.py`) qui divergent déjà (gestion
  d'erreur, plafond de wafers, `json_safe`). Ici, un Protocol `DataSource` (PRISM, démo) se
  justifie.

### Au-delà de SOLID : REST

- 131 routes. Les chemins sont faits de verbes français. Le préfixe `/api/microprojets` est
  partagé par 6 routeurs. Le HTML Plotly est servi sous `/api`.
- Des segments littéraux (`/tous`, `/recherche`, `/selection`, `/code/{code}`) partagent le niveau
  des identifiants : un µprojet nommé « Tous » ou un lot nommé « selection » devient
  inaccessible.
- Les mutations renvoient toute la collection, ou la vue du parent, au lieu de la ressource. Pas
  de `Location`. Les `DELETE` répondent 200 avec un corps. 422 sert pour des conflits, 401 pour
  un mot de passe métier faux.
- Les ressources globales (présets, briques et structures partagés) sont adressées sous un
  µprojet arbitraire, la portée étant choisie par un booléen `?partagee=`.
- Quatre noms pour le même concept : projet corporate = `management` = « projet » = « theme ».
  Une plaque s'appelle plaque, plate, wafer, sample_id, lasermark ou entity selon le fichier.

La cible est détaillée dans [`ARCHITECTURE.md` § 4-5](ARCHITECTURE.md#4-conventions-rest).

---

## 3. Bugs et failles vérifiés

Tous ont été confirmés par lecture du code, et la plupart par une sonde exécutée. Ils sont
classés par gravité.

### Sécurité

| # | Faille | Où |
|---|---|---|
| S1 | **N'importe quel compte connecté lit toute image du disque du serveur et liste n'importe quel dossier.** Il lui suffit de créer son propre µprojet : `?chemin=` et `?dossier=` absolus, sans racine autorisée. Sous Windows, un chemin UNC déclenche une authentification SMB sortante | `experiments.py:1507-1537` |
| S2 | Redirection ouverte et exécution de `javascript:` via `/connexion?suite=` | `connexion.html:60-70` |
| S3 | XSS stockée : `payload.recipe` d'un préset est injecté sans échappement, et tout éditeur peut publier un préset partagé | `presets.js:80-92` |
| S4 | La bibliothèque partagée est modifiable et supprimable par n'importe quel éditeur de n'importe quel µprojet, sans trace ni confirmation | `structures.py:305-464`, `intent_forms.py` |
| S5 | Inscription ouverte sans vérification d'adresse, et `add_member` ajoute directement un compte existant : squat d'adresse. Les invitations servent aussi de relais de phishing (texte libre envoyé depuis le SMTP de l'entreprise) | `accounts.py:41`, `microprojects.py:296-321` |
| S6 | Sans SMTP (configuration Docker livrée), les liens de réinitialisation et d'invitation sont écrits en clair dans les journaux | `email.py:30` |
| S7 | Bénins : jetons de session stockés en clair, cookie sans `Secure`, `/p/{code}` résout un µprojet sans session, `<title>` du SVG non échappé | divers |

### Perte de données et comportements faux

| # | Bug | Où |
|---|---|---|
| B1 | **L'hypothèse est effacée par 11 des 12 évolutions légères** (étiquette, preuve, statut, conclusion, entités, galerie…). 26 hypothèses perdues dans les données locales | `experiments.py:761, 833, 961…` |
| B2 | **Le type, l'objectif, l'interprétation et les annotations des preuves sont perdus en silence** avec le Follow installé (3 tests rouges) | `experiments.py:862, 1276` |
| B3 | `/combiner` perd toutes les preuves de la version fusionnée | `experiments.py:913` |
| B4 | **Écritures concurrentes** : dépôt rechargé à chaque requête, sans verrou, et `refs.json` gagné par le dernier écrivain, d'où une pointe de branche perdue. Une page périmée crée une fourche silencieuse | `microprojects.py:481`, `experiments.py:83` |
| B5 | Activer ou changer le formulaire d'intention **bloque toute action** sur les études existantes (422 opaque). Le pointeur du formulaire actif et `commit_form.yml` se désynchronisent | `intent_forms.py`, `microprojects.py:461` |
| B6 | Renommer un élément de bibliothèque vers un nom existant **écrase l'autre** sans erreur. Un nom contenant « / » devient inatteignable | `keyed_store.py:58-67` |
| B7 | Les liens d'entités de l'atlas **disparaissent** à la première modification de l'une des deux études (lien vers un id de version) | `links.py:119`, `atlas.js:471` |
| B8 | Une version périmée s'affiche comme « version actuelle ». Le diff annonce « identique » dès qu'on ajoute une étiquette | `experiments.py:491, 509` |
| B9 | Un owner peut rétrograder le créateur, et un µprojet peut se retrouver sans owner. Une deuxième invitation d'une personne sans compte est morte | `microprojects.py:298`, `auth.py:76` |
| B10 | Un mot de passe actuel incorrect renvoie 401, et le front déconnecte l'utilisateur | `auth.py:135` |
| B11 | En Docker, la bibliothèque YAML est absente et l'éditeur répond 500. En local, une édition admin bloque `update.bat` | `registry.py:53` |
| B12 | Un admin révoqué est re-promu au redémarrage. Une campagne DOE n'a pas de plafond (50 variantes = 36 s, re-simulées à chaque aperçu) | `db.py:356`, `structures.py:676` |

### Performance

`get_repository` relit et revalide tout le dépôt Follow **à chaque appel**, sans cache. La fiche
d'expérience déclenche une dizaine de requêtes, et chacune recharge le dépôt. La page thématique
charge chaque dépôt trois fois par µprojet. `GET /api/lots` parcourt les dépôts de tous les
µprojets qui partagent un wafer.

### Filet de tests

307 tests HTTP, un bon choix. Mais :
- 949 URL sont écrites en dur et les fabriques sont dupliquées (24 copies de `_substrate`) ;
- 24 assertions `== 404` passent aussi quand la route n'existe plus (le 404 du routeur) ;
- les routes les plus exposées (`/data/*`, `/api/bibliotheque`) n'ont aucun test ;
- aucun contrat ne relie les appels du front aux routes ;
- la base n'est pas verte (3 échecs déterministes, 1 intermittent sous Windows).

---

## 4. Ce qui cassera en premier

**Le maillon faible : le chemin d'écriture d'une expérience.** Chaque action sur une fiche (preuve,
étiquette, statut, entité, cahier, galerie, conclusion) est un commit Follow complet. Le contexte
aggrave les choses :
- le dépôt est **rechargé entièrement depuis le disque à chaque requête** ;
- il n'y a **ni verrou ni précondition** ;
- l'identité exposée est **l'id de la version** ;
- le passe-plat est recopié dans 13 handlers.

**Le scénario.** Ce n'est pas une hypothèse : le maillon a **déjà** cédé de trois façons.
1. Perte silencieuse de champs (B1, B2, B3).
2. Identité instable : liens d'atlas qui s'évanouissent, ancienne version présentée comme
   courante, fourches fantômes (B7, B8).
3. Coût qui croît avec l'historique.

Le prochain usage réellement collaboratif le fera céder franchement. Deux ingénieurs annotent la
même campagne pendant une revue de lot, ou le cahier de données sert de vrai cahier de labo
pendant quelques semaines. Deux écritures simultanées font perdre une pointe de branche (le
dernier `refs.json` gagne). Une page ouverte depuis la veille crée une piste « titre-2 » dans le
graphe. Chaque note recharge un dépôt de plus en plus gros. Le découpage en plugins aggraverait
tout cela si on le faisait d'abord : chaque plugin (evidence, notebook, galerie, lots) aurait
recopié sa propre version du passe-plat.

**Le coût.**
- **Avant le découpage : environ 1 semaine.**
  - Une fonction `experiments.service.amend()`, unique, sous verrou par µprojet, qui reporte tout
    le parent et ne commite que s'il y a une différence.
  - Un cache du dépôt invalidé par signature.
  - L'identité « piste » avec `If-Match`, qui renvoie 412 au lieu de fourcher.
  - La migration des `entity_links` vers la piste.
  - Un script qui restaure les hypothèses depuis l'historique.
- **Après le découpage : le double**, plus la réconciliation des pistes fantômes déjà créées.

C'est pour cela que ce chantier est le cœur du plugin `experiments` et passe avant les plugins qui
écrivent dans une étude.

*Second point de rupture, plus probable à court terme mais moins profond :* les dépendances non
épinglées. Le prochain `update.bat` ou `docker build` peut changer le comportement de toutes les
installations à la fois, sans aucun commit Spectre. Les 3 tests rouges en sont la preuve. Le
correctif prend une heure : épingler des SHA, et ajouter `follow` en dépendance directe. C'est une
décision de mise en production : je la recommande, je ne l'ai pas prise à ta place.

---

## 5. Garde-fou anti-sur-ingénierie : où SOLID ne vaut pas le coût

| Tentation | Pourquoi non | Version directe retenue |
|---|---|---|
| Protocol `ExperimentRepository` au-dessus de Follow | Une seule implémentation, aucune variation prévue, et Follow fournit déjà son abstraction de stockage | Des fonctions concrètes (`amend`, `delete_line`) qui prennent un `follow.Repository`. Les accès privés sont isolés dans un seul module |
| Protocol `Mailer` avec injection | Une implémentation réelle. Le repli « journaliser » sert au poste de dev | `kernel.mail.send_email` et une fixture `outbox` qui fait un `monkeypatch` |
| `UserRepository`/`SessionStore`, JWT, authlib | Une base SQLite, pas de SSO décidé | Fonctions de module derrière `current_user`. Si le SSO arrive, on remplace le corps de `current_user` |
| Découverte dynamique de plugins (entry points), ABC `Plugin` avec cycle de vie, bus d'événements | Moins de 25 plugins, tous internes, livrés ensemble | Une dataclass `Plugin` figée et une liste `PLUGINS` écrite à la main, vérifiée au démarrage |
| Fabrique générique de routeurs CRUD pour les bibliothèques | Les ressources diffèrent sur les permissions, les modèles et l'activation. L'OpenAPI deviendrait opaque | Des routes explicites de 5 lignes, qui délèguent à un service commun |
| Registre d'« enrichisseurs » de nœuds de filiation | Les lots sont le seul enrichissement | La filiation ne renvoie que les wafers. Le front compose les badges via `lotsApi` |
| Protocol `LotSource` pour la future synchro PRISM | Un seul stockage (SQLite). PRISM n'est qu'un producteur | `lots.sync(records, source="prism")` et un petit adaptateur |
| Migrer les 21 scripts du constructeur en modules ES | Coût et risque élevés, aucun bénéfice pour le découpage. Le constructeur est une seule page | Scripts classiques, un global par plugin, contexte passé en paramètre aux modules partagés |
| Générer 100 % des formulaires d'étape depuis le schéma StructureForge | Croissance facettée, planarisation et lithographie ont une UX propre | Schéma pour les défauts et les libellés, formulaires écrits à la main, repli générique pour un type inconnu |
| Route pour antidater (seed de démo) | Un trou d'intégrité de l'historique en production, pour un script | Garder l'écriture directe du seed, mais la faire échouer bruyamment |
| Protocol au-dessus de la simulation StructureForge | Un moteur, maison | Fonctions concrètes du plugin `structures` |

**Là où l'abstraction paie**, avec au moins deux implémentations réelles et plusieurs sites
d'appel : `StructureKind` (3 types), `DataSource` (PRISM et démo), le registre de recherche
(4 fournisseurs), le registre de KPI, le registre DataViz et les panneaux de la fiche
d'expérience.

**Le code à supprimer plutôt qu'à abstraire**, faute de consommateur :
- la vue Plotly `graphe.html` ;
- `POST/DELETE …/pieces-jointes` ;
- `PUT …/objectifs` (réordonnancement) ;
- `totals` et `conclusion_rate` ;
- le champ `attachments` de l'atlas ;
- `get_current_user_optional` ;
- `list_microproject_links` ;
- le type de preuve `graph` (il allait chercher une URL arbitraire).

---

## 6. Ce qui en découle

Les décisions prises :
- API en anglais, pages en français, rupture nette ;
- identité d'une expérience = sa **piste** ;
- bibliothèque partagée modifiable par son **auteur ou un admin** ;
- suppression de la vue Plotly ;
- démo KPI isolée.

Le contrat est dans [`ARCHITECTURE.md`](ARCHITECTURE.md) : noyau sans métier, 21 plugins nommés de
la même façon en Python, sous `/api` et sous `/static`, et table de correspondance des 131 routes.

---

## 7. État après le refactor (4 octobre 2026)

Branche `refactor/plugins` : 43 commits depuis `03f4646`. Elle a été menée par étapes, chacune
gardant la suite verte puis relue par un agent chargé de la réfuter :
1. filet de sécurité ;
2. déplacement structurel ;
3. front par plugin ;
4. trois vagues REST ;
5. finitions.

**Résultat.** 769 tests verts, sans xfail. S'y ajoutent les tests de contrat :
- appels du front ↔ routes ;
- aucune chaîne `/api/` hors des `client.js` ;
- 401 anonyme sur toute route non publique ;
- graphe d'imports entre plugins, sans aucune exception transitoire ;
- assets servis.

### Constats de ce rapport : ce qui est réglé

| Constat | État |
|---|---|
| S — `api/experiments.py`, `core/microprojects.py`, `api/structures.py`, `core/db.py`, `common.js`, `experience.js` | Réglé : répartis en plugins. `experiments` a une seule fonction d'écriture (`amend`) et la fiche est découpée en modules et panneaux |
| O — dispatch par chaîne sur le type de structure, ordre des routeurs, recherche codée en dur | Réglé : `StructureKind` (3 types), identifiants d'un seul segment, `GET /api/search` avec registre de fournisseurs |
| L — « Non classé », source démo | Réglé : `is_system`/`can_delete` ; `DataSource` respecté par les deux sources |
| I — globales implicites, `_detail` fourre-tout | Réglé en grande partie : contexte explicite (`ctx`, `mount(el, ctx)`), chaque plugin lit sa sous-ressource. Il reste des fonctions globales partagées entre plugins côté front, documentées dans ARCHITECTURE.md § 6 |
| D — `core/permissions` → `api`, adaptateurs PRISM doublés | Réglé : dépendances dans `accounts.deps`/`microprojects.deps`, un seul adaptateur PRISM derrière `DataSource`. Les accès privés à Follow sont isolés dans `experiments.repository.delete_line` |
| REST | Réglé : 131 routes renommées en ressources anglaises (rupture nette). Codes, `Location` qui se lit, 204, `If-Match`/412 ; plus de HTML sous `/api` |
| S1 lecture de fichiers arbitraires | Réglé : images servies par identifiant, racines `SPECTRE_EXTERNAL_IMAGE_ROOTS`, parcours réservé aux éditeurs |
| S2 redirection ouverte, S3 XSS de préset, SVG non échappés | Réglé, testé dans le navigateur |
| S4 bibliothèque partagée modifiable par tous | Réglé : auteur ou admin, `created_by`/`updated_by`, confirmation avant suppression |
| S6 jetons dans les journaux, S7 jetons en clair, cookie, `/p/{code}` anonyme | Réglé |
| B1 hypothèse effacée, B2 champs de preuve perdus, B3 fusion sans preuves | Réglé et testé pour chaque écriture. `scripts/repair_hypotheses.py` (à blanc par défaut) restaure les hypothèses déjà perdues : 12 sur la copie de `data/` |
| B4 écritures concurrentes, fourches silencieuses | Réglé : verrou par µprojet, cache du dépôt, `If-Match` → 412, aucune fourche implicite (vérifié sous charge et dans le navigateur) |
| B5 formulaire d'intention bloquant, B6 renommage qui écrase, B7 liens d'atlas qui disparaissent, B8 version périmée « actuelle » | Réglé |
| B9 owner rétrogradable, invitations mortes, B10 401 sur mot de passe faux, B11 bibliothèque en Docker, B12 admin re-promu, DOE sans plafond | Réglé |
| Performance : dépôt relu à chaque requête | Réglé : cache invalidé par signature ; les stats et la frise chargent chaque dépôt une seule fois |
| Filet de tests | Réglé : helpers par plugin, 404 du handler distingué de celui du routeur, contrats ; écritures atomiques réessayées sous Windows |

### Ce qui reste ouvert

**Décisions produit ou sécurité :**
- Inscription libre sans vérification d'adresse, et ajout direct d'un compte existant comme membre
  (S5). Une liste blanche de domaines (`SPECTRE_ALLOWED_EMAIL_DOMAINS`) serait la réponse minimale.
- `/openapi.json` est lisible sans session : il décrit les routes, pas les données.

**Dette assumée, documentée dans ARCHITECTURE.md :**
- Les dépendances structureforge, follow et prism ne sont pas épinglées (§ 4 ci-dessus) : à
  épingler avant une mise en production.
- Le cahier de données vit encore dans les métadonnées versionnées de l'étude. C'est désormais
  sûr (verrou, `If-Match`), mais chaque note crée une version : à sortir dans un stockage propre
  si le cahier devient un vrai cahier de labo.
- Côté front, des règles métier sont encore recopiées : `waferKey`, `normalizeFdl`, limites
  d'images, définition du WIP. Il reste aussi quelques fonctions globales partagées entre plugins.
- Les liens d'entités d'une piste supprimée restent listés. Le nom d'une piste supprimée n'est
  jamais réattribué, donc ils ne pointent jamais vers une autre étude.
- `areas` met à jour la table `microprojects` lors d'une suppression : c'est l'exception écrite
  dans ARCHITECTURE.md § 3.

**Autres points :**
- Les pages de documentation intégrées (`/docs`) citent encore les anciennes routes ; leur
  contenu est laissé en l'état, à reprendre.
- `tests_js` ne tourne pas sur ce poste, faute de Node.

**Incident pendant le refactor.** Le 3 octobre à 23 h 33, la nouvelle version a été démarrée sur
le dossier `data/` réel du dépôt, par un processus non identifié. Les migrations s'y sont
appliquées.
- Aucune donnée d'expérience n'a été touchée : les dépôts Follow sont intacts, de même que les
  comptes, les µprojets et les lots.
- Seules les 5 lignes de la table abandonnée `lot_steps` sont perdues.
- Ce `data/` ne peut plus être ouvert par `main`.

Depuis, toute migration commence par une sauvegarde dans `data/backups/<horodatage>/`.
