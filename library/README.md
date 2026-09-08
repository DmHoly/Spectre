# Bibliothèque racine (`library/`)

Le vocabulaire **par défaut** de cette instance Spectre, en fichiers YAML éditables plutôt qu'en
dur dans le code :

| Fichier | Alimente | Modèle Python |
|---|---|---|
| `materiaux.yml` | le sélecteur de matériaux du constructeur de structure (+ couleurs du rendu) | `structureforge.core.materials.Material` |
| `presets.yml` | les présets d'étape (scope « préset ») | `spectre.core.step_presets.StepPreset` |
| `briques.yml` | les briques technologiques (scope « préset ») | `spectre.core.tech_bricks.TechBrick` |
| `recettes.yml` | des recettes de dépôt / gravure en plus de celles de StructureForge (fusion par nom) | `structureforge.core.recipes.DepositionRecipe` / `EtchRecipe` |

Chargés par [`spectre/core/registry.py`](../spectre/core/registry.py).

## Faire évoluer

1. Éditez le fichier.
2. Rafraîchissez la page — **pas besoin de redémarrer le serveur** (rechargement à chaud sur
   changement de `mtime`).
3. Un fichier absent, vide ou invalide → jeu intégré de repli, avec un avertissement dans les logs
   du serveur (`Bibliothèque racine : … invalide`). Votre modification n'est alors *pas* prise en
   compte — vérifiez les logs.

## Portée

- Ces trois collections sont le **scope « préset »** du système à trois niveaux
  *intégré / partagé / projet*. Le partagé (`data/*_partages.json`) et le projet
  (`data/projects/<slug>/*.json`) restent modifiables depuis l'app et ne sont pas touchés ici.
- **Matériaux** : le sélecteur ne montre que cette liste, mais la simulation résout toujours
  n'importe quel matériau connu de StructureForge (~46) — retirer une entrée n'empêche pas une
  structure existante de se simuler. Une entrée peut *ajouter* un matériau absent de StructureForge
  (GZO, AlCu) ou en *redéfinir* la couleur.
- **Recettes** de dépôt/gravure : StructureForge en fournit un jeu de base ; `recettes.yml` en
  ajoute (ou en redéfinit). Une **gravure sélective** (« ne grave que l'Al2O3 ») est une recette,
  pas un préset — la sélectivité (`selectivity_by_material` / `_by_category` / `default_factor`)
  vit sur la recette, un préset/une étape ne fait que nommer une recette. Exemple livré :
  « Gravure sélective Al2O3 » dans `recettes.yml`, exposée comme préset dans `presets.yml`.

## Emplacement

`<racine du dépôt>/library`, ou le chemin dans `$SPECTRE_LIBRARY_DIR` s'il est défini.
