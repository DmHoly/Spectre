"""Outils de fichiers du noyau.

- :func:`replace` : ``os.replace`` qui tient bon sous Windows. Le remplacement atomique d'un
  fichier y échoue en ``PermissionError`` tant qu'un autre processus (antivirus, indexeur, un
  lecteur qui vient d'ouvrir l'ancienne version) garde un handle sur la cible ; ce handle se
  libère en quelques millisecondes, on réessaie donc un peu avant d'abandonner. Toute écriture
  atomique de Spectre (fichier temporaire du même dossier, puis remplacement) passe par lui.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

REPLACE_ATTEMPTS = 5
REPLACE_DELAY_SECONDS = 0.03


def replace(src: str | Path, dst: str | Path) -> None:
    """``os.replace(src, dst)``, réessayé jusqu'à :data:`REPLACE_ATTEMPTS` fois sur
    ``PermissionError`` (cible tenue un instant par un autre processus sous Windows) ; la dernière
    erreur remonte telle quelle."""
    for attempt in range(1, REPLACE_ATTEMPTS + 1):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == REPLACE_ATTEMPTS:
                raise
            time.sleep(REPLACE_DELAY_SECONDS)
