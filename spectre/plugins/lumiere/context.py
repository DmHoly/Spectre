"""Le contexte d'un rapport : ce que Spectre sait de la chose décrite, lu une fois et partagé par tous les blocs
d'un même rapport (:class:`WaferContext` : une plaque). Chaque lecture est paresseuse et mémorisée ; une lecture
en échec rend « rien » et se journalise : un bloc dit alors ce qui manque, le rapport sort quand même."""

from __future__ import annotations

import logging
from functools import cached_property
from typing import Any

from ...kernel.errors import DomainError
from ..accounts.service import User
from ..characterization import service as characterization
from ..sem_images import service as sem_images
from ..wafer_data import blocks as wafer_data_blocks
from ..wafers import notes, records, timeline, tracking
from ..wafers import service as wafers

log = logging.getLogger(__name__)


class WaferContext:
    """Une plaque, pour les blocs d'un rapport : son passeport, sa vie en ligne, ses notes, sa frise, ses données
    par type (``data(hook)``), ses images MEB."""

    kind = "wafer"

    def __init__(self, user: User, lasermark: str):
        self.user = user
        self.lasermark = lasermark.strip()
        self._data: dict[str, Any] = {}

    @cached_property
    def key(self) -> str:
        return wafers.wafer_key(self.lasermark)

    @cached_property
    def line(self) -> dict[str, Any] | None:
        return tracking.line_facts([self.key]).get(self.key)

    @cached_property
    def passport(self) -> dict[str, Any]:
        return wafers.passport(self.lasermark, wafers.occurrences(self.user, keys=[self.lasermark]), records.get(self.lasermark), self.line)

    @property
    def name(self) -> str:
        return self.passport["lasermark"]

    @property
    def title(self) -> str:
        return f"Plaque {self.name}"

    @cached_property
    def life(self) -> dict[str, Any] | None:
        try:
            return tracking.read(self.lasermark)
        except DomainError as exc:
            log.info("rapport de %s : vie en ligne non lue (%s)", self.lasermark, exc)
            return None

    @cached_property
    def notes(self) -> dict[str, Any] | None:
        return notes.get(self.lasermark)

    @cached_property
    def fdls(self) -> list[str]:
        return list(dict.fromkeys([*(self.passport.get("line_fdl") or []), *(self.passport.get("fdl") or [])]))

    @cached_property
    def events(self) -> list[dict[str, Any]]:
        return timeline.events(self.user, self.name)

    @cached_property
    def catalog(self) -> list[wafer_data_blocks.CatalogHook]:
        return wafer_data_blocks.catalog()

    def hook(self, key: str) -> wafer_data_blocks.CatalogHook | None:
        return next((h for h in self.catalog if h.hook == key), None)

    def data(self, hook: str) -> Any | None:
        """Le résultat (colonnes, lignes, source) d'un type de données PRISM pour la plaque ; ``None`` s'il ne se
        lit pas."""
        if hook not in self._data:
            try:
                self._data[hook] = characterization.query(hook, {"wafer_names": [self.name]})
            except DomainError as exc:
                log.info("rapport de %s : %s non lu (%s)", self.name, hook, exc)
                self._data[hook] = None
        return self._data[hook]

    @cached_property
    def sem_listing(self) -> dict[str, Any] | str:
        """La liste des images MEB du G4 (``groups``), ou le message qui dit pourquoi il n'y en a pas."""
        try:
            return sem_images.listing(self.name, self.fdls)
        except DomainError as exc:
            return str(exc)


def make(user: User, kind: str, key: str) -> WaferContext:
    if kind == "wafer":
        return WaferContext(user, key)
    raise ValueError(kind)
