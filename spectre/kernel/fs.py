"""Outils de fichiers du noyau.

- :func:`replace` : ``os.replace`` qui tient bon sous Windows. Le remplacement atomique d'un
  fichier y échoue en ``PermissionError`` tant qu'un autre processus (antivirus, indexeur, un
  lecteur qui vient d'ouvrir l'ancienne version) garde un handle sur la cible ; ce handle se
  libère en quelques millisecondes, on réessaie donc un peu avant d'abandonner. Toute écriture
  atomique de Spectre (fichier temporaire du même dossier, puis remplacement) passe par lui.
- :func:`write_text` : l'écriture atomique complète d'un texte (fichier temporaire unique du même
  dossier, ``fsync``, puis :func:`replace`) - celle du dépôt Follow d'un µprojet, entre autres.
"""

from __future__ import annotations

import os
import tempfile
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
            time.sleep(REPLACE_DELAY_SECONDS * attempt)  # 30, 60, 90, 120 ms


def write_text(path: str | Path, text: str) -> None:
    """Remplace ``path`` par ``text`` (UTF-8) de façon atomique : un lecteur voit l'ancien fichier ou
    le nouveau, jamais un fichier à moitié écrit, et le temporaire ne reste jamais sur disque."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())  # les octets sur disque avant que le nom ne les désigne
        replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
