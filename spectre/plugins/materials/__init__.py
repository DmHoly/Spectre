"""Éditer les matériaux de l'instance depuis une page (``/materiaux``) : la liste du sélecteur du
constructeur - nom, catégorie, couleur, description - et les dégradés de couleur de l'InGaN et de
l'AlGaN selon leur taux, qui s'écrivent dans ``materiaux.yml`` de la bibliothèque racine."""

from ...kernel.plugin import NavEntry, Page, Plugin
from .api import router

MATERIALS_GLYPH = '<path d="M12 3 4 7.5v9L12 21l8-4.5v-9L12 3Z"/><path d="m4 7.5 8 4.5 8-4.5"/><path d="M12 12v9"/>'

PLUGIN = Plugin(
    name="materials",
    depends_on=("accounts", "library", "structures"),
    router=router,
    pages=(Page("/materiaux", "materials.html"),),
    nav=(NavEntry("Matériaux", "/materiaux", order=22, match=r"^/materiaux", group="structure", glyph=MATERIALS_GLYPH),),
    title="Matériaux",
    description="Édite les matériaux du constructeur (couleur, catégorie, description...) et les dégradés de couleur de l'InGaN et de l'AlGaN, depuis une page plutôt que dans le fichier YAML.",
    icon="layers",
)
