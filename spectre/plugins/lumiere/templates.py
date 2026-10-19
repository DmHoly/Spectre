"""Les modèles de rapport : un modèle a une clé, un nom, le **contexte** qu'il attend (``wafer`` : une plaque) et
une fonction qui construit le rapport Lumière (``build(user, key) -> ReportBuilder``). Aujourd'hui un seul,
codé ici ; la page de composition slide par slide (SOCLE-DATA.md §4.6, R2) les rendra éditables."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ...kernel.errors import NotFound
from ..accounts.service import User
from . import wafer_report

CONTEXTS = {"wafer": "une plaque"}


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    description: str
    context: str  # une clé de CONTEXTS
    build: Callable[[User, str], Any]  # -> lumiere_report.ReportBuilder
    slides: tuple[str, ...]  # ce que le rapport contient, pour le dire avant de le générer

    def payload(self) -> dict[str, Any]:
        return {"key": self.key, "name": self.name, "description": self.description, "context": self.context, "slides": list(self.slides)}


TEMPLATES: dict[str, Template] = {
    "fiche-plaque": Template(
        key="fiche-plaque",
        name="Fiche plaque",
        description="Tout ce que Spectre sait d'une plaque, en slides : son contexte (études, notes), sa vie en ligne (MES, FDL JIRA, tests), ses données de caractérisation par type (cartes et distributions), ses images MEB du G4.",
        context="wafer",
        build=wafer_report.build,
        slides=("Titre", "Contexte", "Vie en ligne", "Données par type (cartes, boîtes)", "Images MEB - G4", "Sommaire"),
    ),
}


def for_context(context: str | None = None) -> list[Template]:
    return [t for t in TEMPLATES.values() if context is None or t.context == context]


def get(key: str) -> Template:
    found = TEMPLATES.get(key)
    if found is None:
        raise NotFound(f"Modèle de rapport inconnu : {key!r}.", code="unknown_template")
    return found
