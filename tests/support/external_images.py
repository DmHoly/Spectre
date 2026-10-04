"""Images externes (plugin external_images) : de vraies images sur le disque, et le parcours des
dossiers autorisés. Les images qu'une mesure du cahier référence se lisent par l'entrée qui les porte
(voir :mod:`support.notebook`). ``browse`` renvoie la réponse telle quelle (pour en vérifier un
refus)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .http import PNG_1PX


def png_files(directory: Path, *names: str) -> list[str]:
    """De vraies images PNG écrites dans ``directory`` - leurs chemins absolus."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in names or ("tem-1.png", "tem-2.png"):
        (directory / name).write_bytes(PNG_1PX)
        paths.append(str(directory / name))
    return paths


def browse(client: Any, slug: str, directory: str) -> Any:
    """GET /external-images?directory= (la réponse)."""
    return client.get(f"/api/microprojects/{slug}/external-images", params={"directory": directory})
