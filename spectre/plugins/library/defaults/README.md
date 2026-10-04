# Bibliothèque racine — fichiers livrés

Le vocabulaire **par défaut** d'une instance Spectre, en fichiers YAML éditables plutôt qu'en
dur dans le code. Ce dossier contient les fichiers **livrés** : au premier démarrage, ils sont
copiés dans le dossier de la bibliothèque de l'instance, qui est ensuite le seul lu et modifié.

| Fichier | Clé (`/api/library/files/{clé}`) | Alimente | Déclaré par |
|---|---|---|---|
| `materiaux.yml` | `materials` | le sélecteur de matériaux du constructeur de structure (+ couleurs du rendu) | `spectre/plugins/structures/library_files.py` |
| `recettes.yml` | `recipes` | des recettes de dépôt / gravure en plus de celles de StructureForge (fusion par nom) | `spectre/plugins/structures/library_files.py` |
| `presets.yml` | `step-presets` | les présets d'étape intégrés (portée `builtin`) | `spectre/plugins/process_library/library_files.py` |
| `briques.yml` | `tech-bricks` | les briques technologiques intégrées (portée `builtin`) | `spectre/plugins/process_library/library_files.py` |
| `intention.yml` | `intention` | les libellés, placeholders et aides de la section « Objectifs et intention » du constructeur (`GET /api/ui-texts/intention`) | `spectre/plugins/library/service.py` |

Chargés par [`spectre/plugins/library/service.py`](../service.py), qui ne connaît aucun de ces
types : chaque plugin propriétaire déclare son fichier (`register_library_file`) avec la fonction
qui en interprète le contenu et son jeu intégré de repli.

## Emplacement

- `$SPECTRE_LIBRARY_DIR` s'il est défini, sinon `<dossier des données>/library` (en Docker :
  `/data/library`, sur le volume des données).
- Absent, ce dossier est créé à la première lecture en copiant les `*.yml` d'ici. Il appartient
  ensuite à l'instance : une mise à jour du code (`git pull`, nouvelle image) ne l'écrase pas, et
  une édition ne touche pas au dépôt. Pour repartir des fichiers livrés, supprimez le fichier
  voulu de ce dossier : il retombe sur le jeu intégré du code, ou recopiez-le d'ici.

## Faire évoluer

1. Éditez le fichier : depuis la page `/bibliotheque` (réservé aux administrateurs ; le contenu est
   validé avant d'être écrit, un fichier invalide est refusé avec le message de l'erreur), ou à la
   main dans le dossier de l'instance.
2. Rafraîchissez la page — **pas besoin de redémarrer le serveur** (rechargement à chaud quand le
   fichier change).
3. Un fichier édité à la main absent, vide ou invalide → jeu intégré de repli, avec un
   avertissement dans les logs du serveur (`Bibliothèque racine : … invalide`). Votre modification
   n'est alors *pas* prise en compte — vérifiez les logs.

- **Intention** : contrairement aux autres fichiers (des listes sous une clé), `intention.yml` est
  un objet unique à plat - un fichier partiel (qui ne redéfinit que quelques libellés) est fusionné
  par-dessus le jeu intégré, clé par clé.

## Portée

- Les présets et les briques d'ici sont la portée **`builtin`** des bibliothèques
  *intégré / partagé / µprojet*. Les éléments partagés (`<données>/*_partage(e)s.json`) et ceux
  d'un µprojet (`<données>/microprojects/<slug>/*.json`) se gèrent depuis l'application et ne sont
  pas touchés ici.
- **Matériaux** : le sélecteur ne montre que cette liste, mais la simulation résout toujours
  n'importe quel matériau connu de StructureForge (~46) — retirer une entrée n'empêche pas une
  structure existante de se simuler. Une entrée peut *ajouter* un matériau absent de StructureForge
  (GZO, AlCu) ou en *redéfinir* la couleur.
- **Recettes** de dépôt/gravure : StructureForge en fournit un jeu de base ; `recettes.yml` en
  ajoute (ou en redéfinit). Une **gravure sélective** (« ne grave que l'Al2O3 ») est une recette,
  pas un préset — la sélectivité (`selectivity_by_material` / `_by_category` / `default_factor`)
  vit sur la recette, un préset/une étape ne fait que nommer une recette (qui doit exister : un
  préset vers une recette inconnue est refusé). Exemple livré : « Gravure sélective Al2O3 » dans
  `recettes.yml`, exposée comme préset dans `presets.yml`.
