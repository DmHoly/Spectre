"""Les annotations d'une image : des flèches et des cadres posés sur une image, chacun avec un libellé
facultatif. Une seule forme pour toute image que Spectre montre - une image du cahier (téléversée ou
externe), une image d'une structure en images -, une seule validation, et un seul composant de page
pour les poser et les dessiner (``kernel/static/annotations.js``).

Les positions sont en **% de l'image** (``x``, ``y`` : le départ d'une flèche ou un coin du cadre ;
``x2``, ``y2`` : l'arrivée ou le coin opposé) : une annotation reste à sa place quelle que soit la
taille à laquelle l'image est affichée (vignette, fiche, rapport).

Le noyau ne sait pas à quelle image une annotation appartient : c'est au plugin qui la range de le
dire (sur l'image elle-même pour une structure, par une clé d'image dans une mesure du cahier).
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from .errors import InvalidInput

MAX_ANNOTATIONS = 100
MAX_LABEL = 200


class ImageAnnotation(BaseModel):
    """Une flèche ou un cadre posé sur une image, en % de l'image."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["arrow", "box"]
    x: float
    y: float
    x2: float | None = None
    y2: float | None = None
    label: str | None = None


def clean_annotations(raw: list[ImageAnnotation], *, limit: int = MAX_ANNOTATIONS) -> list[dict[str, Any]]:
    """Les annotations reçues, telles qu'on les range : ``limit`` au plus, des positions finies, un
    libellé sans espaces autour (``None`` s'il est vide), de ``MAX_LABEL`` caractères au plus. Refus :
    ``InvalidInput`` (``invalid_annotation``)."""
    if len(raw) > limit:
        raise InvalidInput(f"{limit} annotations au maximum.", code="invalid_annotation")
    if not all(number is None or math.isfinite(number) for a in raw for number in (a.x, a.y, a.x2, a.y2)):
        raise InvalidInput("Une annotation a une position qui n'est pas un nombre fini.", code="invalid_annotation")
    return [
        {"type": a.type, "x": a.x, "y": a.y, "x2": a.x2, "y2": a.y2, "label": (a.label or "").strip()[:MAX_LABEL] or None} for a in raw
    ]
