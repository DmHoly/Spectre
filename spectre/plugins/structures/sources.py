"""Les structures nommées qu'on peut retrouver et dessiner hors d'une étude : une version de
référence (plugin references), une structure de la bibliothèque des procédés (plugin
process_library)... Chaque plugin qui en possède déclare ici comment la lire (:func:`register`), et
qui veut en montrer une - la structure attachée à une plaque sans µprojet (plugin wafers) - la lit
par :func:`resolve`, sans dépendre de ces plugins ni savoir lesquels sont actifs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ...kernel import plugin_states
from ...kernel.errors import InvalidInput


@dataclass(frozen=True)
class Resolved:
    """Une structure retrouvée : sa version (``None`` si elle n'en a pas), son nom tel qu'on
    l'affiche, et son dessin (``None`` sans dessin)."""

    version: str | None
    label: str
    svg: str | None


@dataclass(frozen=True)
class StructureSource:
    kind: str  # "reference", "saved"
    plugin: str  # le plugin qui la sert : la source se tait quand il est désactivé
    resolve: Callable[[Any, str, str | None], Resolved]  # (utilisateur, id, version) -> Resolved


_SOURCES: dict[str, StructureSource] = {}


def register(source: StructureSource) -> None:
    _SOURCES[source.kind] = source


def resolve(kind: str, user: Any, source_id: str, version: str | None = None) -> Resolved:
    """La structure ``source_id`` (``version``, la dernière sinon) de la source ``kind`` - 422 pour
    une source inconnue ou dont le plugin est désactivé ; les erreurs de la source passent telles
    quelles (404 introuvable...)."""
    source = _SOURCES.get(kind)
    if source is None or not plugin_states.is_enabled(source.plugin):
        raise InvalidInput(f"Source de structure indisponible : « {kind} ».", code="invalid_structure_kind")
    return source.resolve(user, source_id, version)
