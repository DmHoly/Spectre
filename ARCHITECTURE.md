# Architecture de Spectre — le contrat

Ce document est le **contrat** de l'architecture : court, et tenu à jour avant le code. Toute
nouvelle fonctionnalité s'y conforme, toute exception y est écrite nommément. Le détail technique
(noyau, autorisation, conventions REST, identités, routes, front, tests) est dans
[`ARCHITECTURE-REFERENCE.md`](ARCHITECTURE-REFERENCE.md) ; le *pourquoi* des choix dans
[`REVIEW.md`](REVIEW.md).

Spectre sert à **relier les expériences et capitaliser sur leurs conclusions** : une intention, des
objectifs, une structure, des plaques, des mesures, une conclusion. Tout le reste est optionnel.

## 1. Les trois étages

```
  Bibliothèques      StructureForge · Follow · client PRISM · Lumière · numpy, pandas…
                     (ne connaissent pas Spectre ; importées par les plugins qui en ont besoin)

  Noyau              spectre/kernel/ — immuable, sans métier, n'importe aucun plugin

  Plugins            Core ─▶ Extensions ─▶ Feuilles  (DAG strict, voir § 3)
```

1. **Une bibliothèque ne dépend de personne.** Lumière est une bibliothèque au même titre que
   StructureForge ou le client PRISM : un système de rapports et de dataviz, sans aucune
   connaissance de Spectre.
2. **Le noyau est immuable.** Il fournit l'infrastructure (plugins, base, migrations, erreurs, pages,
   activation, statiques), les **comptes, sessions et droits** (`accounts`, trop central pour être un
   plugin dont tout dépend) et les **fichiers téléversés** (`attachments` : une fonction de base de
   l'application), et rien d'autre de métier. Il n'importe aucun plugin ; seul `create_app` lit la liste
   `PLUGINS`. **Toute modification du noyau est justifiée** : le commit dit quel besoin ne pouvait pas
   être servi par un plugin, et `REVIEW.md` en garde la trace. Un refactor qui touche le noyau sans
   cette justification est refusé.
3. **Les plugins portent tout le métier**, rangés en trois couches d'importance décroissante.

## 2. Données et dataviz : deux guichets

- **Toute donnée mesurée entre par PRISM**, et la bibliothèque PRISM n'est appelée que par le plugin
  `prism_plugin` (le suffixe distingue le plugin de la bibliothèque).
  Il répond à une seule question : « les lignes du hook X pour ces plaques ». Il possède le
  catalogue des hooks, le typage des colonnes, les filtres et les statistiques de base. Aucun autre
  plugin n'appelle PRISM, ne lit `N:\`, le MES ou JIRA : un besoin de donnée nouveau est un hook
  PRISM nouveau, puis une colonne de plus au guichet. Les images hors Spectre (MEB du G4) sont
  une donnée comme une autre : « les images de telle plaque », et PRISM fournit les liens.
- **Tout rapport et toute dataviz de donnée mesurée sortent de Lumière**, et Lumière n'est appelée
  que par le plugin `lumiere_plugin`. Il répond à une seule question : « tel type de rapport (ou de
  figure) pour ces plaques ». Il va chercher la donnée chez `prism_plugin`. Aucun autre plugin n'importe Lumière ni
  ne dessine une mesure.
- **Spectre dessine ses propres objets.** Ce que l'utilisateur a saisi dans Spectre (un planning,
  une structure, une filiation, des compteurs d'usage) est une donnée de Spectre : le plugin qui la
  possède peut la représenter lui-même. La frontière est la nature de la donnée, pas l'outil.
- **Exception nommée.** La tendance KPI des pages de projet corporate (`kpis`) est tracée par
  Spectre, mais ses valeurs viennent de `prism_plugin`.

Ces deux guichets sont **Core** : ils sont des plugins parce qu'ils ont des routes, un catalogue et
une page d'administration, et Core parce que les Extensions reposent dessus. C'est un compromis
assumé : un système de données et un système de dataviz dans le socle.

## 3. Les plugins : trois couches

| Couche | Désactivable | Peut dépendre de | Peut être une dépendance de | Comment on la fait évoluer |
|---|---|---|---|---|
| **Core** | non | noyau, autres Core | tous | peu ou pas : on l'enrichit de l'extérieur |
| **Extension** | oui | noyau, Core **seulement** | Feuilles | librement, c'est son rôle |
| **Feuille** | oui | noyau, Core, Extensions | personne | librement |

**L'usage Core** est ce qui doit marcher quand tout le reste est éteint : comptes, équipes,
projets corporate et thématiques, µprojets, constructeur et structures, études (intention,
objectifs, plans, filiation, conclusion), plaques et leur fiche, références, recherche,
bibliothèque YAML, donnée PRISM et rapports Lumière ; comptes et pièces jointes sont au noyau.

| Couche | Plugins |
|---|---|
| **Noyau** | `accounts` (comptes, sessions, droits) et `attachments` (fichiers téléversés) y entrent |
| **Core** | rangé par niveaux : un Core de niveau *n* ne dépend que du noyau et de Core de niveau inférieur. Niveau 0 : `settings`, `teams`, `search`, `library` · 1 : `areas`, `prism_plugin`, `structures` · 2 : `microprojects`, `lumiere_plugin` · 3 : `experiments` · 4 : `wafers`, `references`. L'ordre est figé : ajouter une dépendance qui remonte un niveau est une décision écrite ici |
| **Extensions** | `comparator`, `process_library`, `lots`, `links`, `notebook`, `kpis`, `kpi_tracking`, `wafer_data` |
| **Feuilles** | `promotion`, `twins`, `planning`, `meta_analysis`, `sem_images`, `step_report`, `simulation_progress`, `intent_forms`, `materials`, `atlas`, `usage`, `kpis_demo`, `docs`, `external_images` |

Le diagramme interactif de ces couches, avec les dépendances d'aujourd'hui et celles de la cible, est
[`ARBRE.html`](ARBRE.html) (régénéré par `scripts/build_arbre.py`). Son onglet « Déploiement » montre où
Spectre tourne : un conteneur Docker, un dossier à la racine du serveur (`docker-compose.yml`, `.env` pour
les secrets et comptes de service, un fichier de configuration s'il en faut un, le dossier des données), la base
`testcarac` (PostgreSQL, INF49) que PRISM attaque en direct, GOZER (INF10) et les bases sherlock, MES, mycroft,
defectivity lues à travers ses schémas liés (`schema_gozer`, `schema_sherlock`…), et les disques O, N, W, P.

La couche d'un plugin est déclarée dans son manifeste (`Plugin.required` pour Core) et le noyau
la fait respecter (`kernel.plugin_states` : un Core ne se désactive pas ; éteindre une Extension
éteint ses dépendants). Le test `tests/contracts/test_plugin_imports.py` vérifie les imports.

### Règles

1. **DAG strict, explicite, sans cycle.** Un plugin n'importe que les plugins de son `depends_on`,
   et seulement leurs modules publics (jamais `api`). Le noyau vérifie l'ordre topologique au
   démarrage.
2. **Pas de plugin central hors Core.** Une Extension ne dépend **que** du noyau et du Core, jamais
   d'une autre Extension ; une Feuille peut dépendre d'Extensions. La chaîne la plus longue est donc
   Feuille → Extension → Core. Une Extension dont on voudrait dépendre depuis une autre Extension est
   un signal : soit elle devient Core (décision écrite ici), soit ce qu'on lui emprunte descend dans
   un Core existant.
3. **Désactiver ne dégrade pas l'usage Core.** Tout plugin hors Core s'éteint sans modifier
   l'expérience Core : le front d'un Core vérifie `pluginEnabled(name)` avant de montrer ce qu'un
   optionnel apporte, et le cache sinon. Un Core n'a jamais de dépendance, même optionnelle, dans
   son `depends_on` vers un plugin hors Core.
4. **Enrichir plutôt que modifier.** Un plugin peut enrichir un autre plugin (panneau, bouton,
   source, fournisseur) par ses points d'extension, en déclarant la dépendance. L'arbitrage entre
   modifier l'existant et créer un plugin : **un fichier et quelques fonctions, on modifie ;
   au-delà, on crée un plugin.** Un bouton dans une interface, un onglet, un panneau se découpent
   en plugin. Pour un Core la barre est plus basse encore : on ne le modifie que pour un point
   d'extension ou une correction.
5. **Un plugin possède ses tables** et seul y écrit ; il lit celles de ses dépendances par
   jointure. Exception nommée : `areas` écrit dans `microprojects` (objectif validé, repli des
   µprojets à la suppression), parce que la dépendance inverse serait un cycle.
6. **Le front passe par l'API Spectre, et par elle seule**, via le `client.js` du plugin
   propriétaire. Le domaine ne connaît pas HTTP. Une abstraction n'existe qu'avec deux
   implémentations réelles. Pas de découverte dynamique, pas de bus d'événements.
7. **Un plugin = une raison de changer**, sous le même nom partout (Python, `/api/<ressource>`,
   `/static/<plugin>/`, `pages/`, `tests/plugins/<plugin>/`).

### Points d'extension

Les registres par lesquels un plugin en enrichit un autre (chaque ligne a au moins deux
implémentations réelles) : `StructureKind` (`structures`), `DataSource` (`prism_plugin` : PRISM, démo),
`register_provider` (`search`), `register_source` (`comparator`), `register_library_file`
(`library`), `register(KpiDefinition)` (`kpis`), `ExperiencePage.registerPanel` et les crochets du
cahier (`experiments`), les modules de dataviz de Lumière (`lumiere_plugin`). Le détail est dans la
référence, § 3.

## 4. Écarts à résorber

L'arbre ci-dessus est la cible. Ce que le code fait encore autrement, et ce qu'on en fait :

| Écart | Cible |
|---|---|
| `accounts` est un plugin dont tous les autres dépendent | Entre dans le noyau : ses tables, ses `deps` et `security` deviennent du noyau ; plus aucun `depends_on` ne le nomme |
| `attachments` est un plugin qui dépend de `microprojects` (un dossier par µprojet) | Entre dans le noyau : téléverser un fichier est une fonction de base ; le dossier d'un fichier est celui de la ressource qui le porte ; `structures`, `experiments`, `notebook` ne le nomment plus |
| `characterization` porte le `DataSource` et `prism` n'est que sa page d'administration | Un seul plugin `prism_plugin`, Core : le guichet et sa page. `characterization` disparaît |
| Le typage des colonnes, les filtres et les stats sont dans `kpi_tracking` ; `wafer_data`, `sem_images`, `meta_analysis`, `lumiere` les lui empruntent | Descendent dans `prism_plugin`. `wafer_data` ne dépend plus de `kpi_tracking` ; la chaîne `meta_analysis → wafer_data → kpi_tracking` disparaît |
| `lumiere` dépend de 13 plugins et va chercher leurs données | Inversé : `lumiere_plugin` est le guichet Core, les plugins qui veulent un rapport le lui demandent. Il ne dépend que de `prism_plugin` |
| `external_images` est une Extension dont `notebook`, `wafer_data` et `lumiere` dépendent | Feuille : plus personne n'en dépend. À terme les images hors Spectre viennent de `prism_plugin`, comme le fait déjà `sem_images` pour le G4 |
| `notebook/static/dataviz/` dessine les figures du cahier | Le cahier devient une implémentation des modules de dataviz de Lumière : un bloc Lumière est un module du cahier |
| `wafers` et `references` dépendent de `comparator` pour s'y enregistrer comme sources | Inversion : `comparator` dépend de `wafers` et `references` et les enregistre lui-même |
| `wafers` importe `structures` (`kinds`, `sources`) sans le nommer dans `depends_on` | Déclaré : une plaque est une entité d'une version d'étude, et sa structure est celle de l'étude ; `wafers` dépend d'`experiments` et de `structures` |
| `kpis` calcule ses définitions sur `spectre.db` | Les KPI de mesure viennent de `prism_plugin` ; les KPI d'activité (nombre d'études, de plaques) sont des données Spectre et restent |
| `comparator` et `process_library` sont `required` | Extensions. Les Core qui s'en servent (constructeur : présets ; fiche d'étude : comparaison) cachent ce qu'ils apportent quand ils sont éteints |
| `experiments` dépend de `structures` | Les deux sont Core : la dépendance est licite, pas de découpage |

Un écart résorbé est retiré de ce tableau dans le même commit.
