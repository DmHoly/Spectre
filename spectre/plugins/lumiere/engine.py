"""Le moteur Lumière (``lumiere_report``), importé paresseusement : l'import charge tous les blocs (quelques
secondes) et exige PRISM, on ne le paie qu'au premier rapport. Seul module du plugin à importer ``lumiere_report``
directement ; les modèles (:mod:`.templates`) reçoivent le module par :func:`load`."""

from __future__ import annotations

import html
import importlib
import importlib.util
from functools import lru_cache
from typing import Any

from ...kernel.errors import Unavailable


def available() -> bool:
    """Lumière est-il installé dans cet environnement ? (le plugin n'existe pas sinon)"""
    return importlib.util.find_spec("lumiere_report") is not None


@lru_cache(maxsize=1)
def load() -> Any:
    """Le module ``lumiere_report`` (ReportBuilder, Slide, blocs...)."""
    try:
        return importlib.import_module("lumiere_report")
    except ImportError as exc:  # installé mais cassé (PRISM manquant...)
        raise Unavailable(f"Le moteur de rapports Lumière ne se charge pas : {exc}", code="lumiere_broken") from exc


@lru_cache(maxsize=1)
def _html_block_class() -> type:
    lumiere = load()

    class HtmlBlock(lumiere.Block):
        """Un bloc de HTML déjà rendu (ce que Spectre sait produire lui-même : un tableau, une galerie, un texte)
        posé sur une slide Lumière - le « HtmlSection » de SOCLE-DATA.md §4.4."""

        needs_plotly = False
        needs_marked = False
        serializable = False

        def __init__(self, content: str, title: str = "", subtitle: str = ""):
            self.content = content
            self.title = title
            self.subtitle = subtitle

        def render(self, store=None) -> str:  # noqa: ARG002 - la signature de Block
            head = ""
            if self.title:
                sub = f'<span class="rb-section-sub">— {html.escape(self.subtitle)}</span>' if self.subtitle else ""
                head = f'<div class="rb-section"><div class="rb-section-bar"></div><h2 class="rb-section-title">{html.escape(self.title)}</h2>{sub}</div>'
            return f'<div class="spectre-html">{head}{self.content}</div>'

    return HtmlBlock


def html_block(content: str, title: str = "", subtitle: str = "") -> Any:
    """Un bloc Lumière qui rend ``content`` tel quel (déjà échappé par l'appelant)."""
    return _html_block_class()(content, title, subtitle)
