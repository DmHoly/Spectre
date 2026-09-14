"""Utilitaires partagés par les modules de graphique (voir ``charts/__init__.py``)."""

from __future__ import annotations

import io

import matplotlib

matplotlib.use("Agg")  # jamais d'affichage interactif ni de backend GUI depuis un process serveur

from matplotlib.figure import Figure


def empty_figure(message: str) -> Figure:
    """Une figure "vide" propre (pas de données à tracer) plutôt qu'une exception ou un graphe
    trompeur - affichée telle quelle par la page wiki quand la sélection ne contient rien à montrer.
    """
    fig = Figure(figsize=(6, 3.2))
    ax = fig.add_subplot(111)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=11, color="#8a8f86", wrap=True)
    ax.axis("off")
    return fig


def render_png(fig: Figure) -> bytes:
    """Sérialise une figure matplotlib en PNG (les fonctions de graphique ne connaissent que
    matplotlib - le choix de format d'export et sa résolution restent un détail de l'API)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=144, bbox_inches="tight")
    return buf.getvalue()
