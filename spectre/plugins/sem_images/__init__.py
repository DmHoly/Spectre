"""Les images MEB du G4 (ME-MEB101) d'une plaque, sur sa page : retrouvées sur le partage par PRISM (hook
``meb_g4`` : par les FDL de la plaque, ou par l'index des dossiers que PRISM tient à jour - le partage n'en a pas),
rangées par acquisition (FDL, procédé, étape) et affichées sans rien copier - les TIF sont rendus à la volée
(vignettes, visionneuse avec échelle, trames des détecteurs, métadonnées du défaut revu). La section vit dans l'onglet
« Data » de la page ; les blocs « images » de la fiche data (wafer_data) lus dans ``meb_g4`` passent par ce rendu."""

from ...kernel.plugin import Plugin
from ..wafer_data import service as wafer_data
from . import service, source
from .api import router

# Les blocs « images » de la fiche data et des analyses lus dans le type de données meb_g4 sont servis par ce plugin
# (vignette JPEG, PNG entier d'un TIF), pas par les images externes.
wafer_data.register_image_server(source.HOOK, service.image_urls)

PLUGIN = Plugin(
    name="sem_images",
    depends_on=("accounts", "wafers", "wafer_data"),
    router=router,
    title="Images MEB du G4",
    description="Les images MEB du G4 d'une plaque, retrouvées par ses FDL sur le partage et affichées sans copie dans l'onglet Data de sa page et dans les blocs d'images de la fiche data.",
    icon="image",
)
