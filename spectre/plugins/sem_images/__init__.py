"""Les images MEB du G4 (ME-MEB101) d'une plaque, sur sa page : retrouvées sur le partage par PRISM (hook
``meb_g4`` : par les FDL de la plaque, ou par l'index des dossiers que PRISM tient à jour - le partage n'en a pas),
rangées par acquisition (FDL, procédé, étape) et affichées sans rien copier - les TIF sont rendus à la volée
(vignettes, visionneuse avec échelle, trames des détecteurs, métadonnées du défaut revu)."""

from ...kernel.plugin import Plugin
from .api import router

PLUGIN = Plugin(
    name="sem_images",
    depends_on=("accounts", "wafers"),
    router=router,
    title="Images MEB du G4",
    description="Les images MEB du G4 d'une plaque, retrouvées par ses FDL sur le partage et affichées sans copie sur sa page.",
    icon="image",
)
