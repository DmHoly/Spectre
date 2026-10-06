"""Le manifeste d'un plugin : ce qu'il apporte à l'application (routes, pages, entrées de la barre
du haut, migrations) et les plugins dont il dépend. Des dataclasses figées et une liste écrite à la
main (``spectre.plugins.PLUGINS``) plutôt qu'une découverte dynamique : moins de 25 plugins, tous
internes et livrés ensemble (voir ``REVIEW.md`` § 5).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from fastapi import APIRouter


@dataclass(frozen=True)
class Page:
    """Une page HTML du plugin : ``file`` est cherché dans ``plugins/<plugin>/pages/``."""

    path: str  # "/lots/{code}"
    file: str  # "lot.html"


@dataclass(frozen=True)
class NavEntry:
    """Une entrée de la barre du haut. ``match`` : l'expression régulière (sur le chemin de la
    page) qui la marque comme section courante ; à défaut, son ``href`` exact. ``pages`` : les
    gabarits de route (``Page.path``) des seules pages qui l'affichent - toutes si vide. ``id`` :
    l'id du lien, pour une page qui en complète l'adresse (le lien « Atlas » d'un projet)."""

    label: str
    href: str
    order: int = 100
    match: str | None = None
    pages: tuple[str, ...] = ()
    id: str | None = None
    admin: bool = False  # montrée aux seuls administrateurs (accounts/static/session.js la révèle)


@dataclass(frozen=True)
class Migration:
    """Une étape du schéma d'un plugin, appliquée une seule fois (``spectre.kernel.db.run_migrations``).
    ``apply`` : un script SQL, ou une fonction qui reçoit la connexion - dans la transaction de la
    migration, donc sans ``commit()`` ni ``executescript()``. ``files`` : pour une migration qui
    réécrit ou supprime des fichiers hors de la base, ceux qu'elle touchera (chemins existants sous
    ``data_dir()``), sauvegardés avec la base avant la première migration en attente."""

    id: str
    apply: str | Callable[[sqlite3.Connection], None]
    files: Callable[[], Iterable[Path]] | None = None


def _always() -> bool:
    return True


@dataclass(frozen=True)
class Plugin:
    name: str  # identique en Python, sous /static/<name>/ et dans les tests
    depends_on: tuple[str, ...] = ()
    router: APIRouter | None = None  # routes /api de ce plugin
    page_router: APIRouter | None = None  # routes de pages spéciales (redirections), avant ses pages
    pages: tuple[Page, ...] = ()
    nav: tuple[NavEntry, ...] = ()
    migrations: tuple[Migration, ...] = ()
    enabled: Callable[[], bool] = _always  # disponible sur cette instance (ex. kpis_demo : SPECTRE_DEMO_DATA=1)
    # Ce que la page Paramètres > Plugins en montre (spectre.kernel.plugin_states) : un nom lisible,
    # une phrase sur ce qu'il apporte et une icône (clé de settings/static/icons.js).
    title: str = ""
    description: str = ""
    icon: str = "puzzle"
    # Du noyau de l'application : ne se désactive pas, ni aucun plugin dont il dépend.
    required: bool = False


class PluginOrderError(ValueError):
    pass


def check_dependencies(plugins: Iterable[Plugin]) -> None:
    """Vérifie que chaque plugin n'est listé qu'une fois et que chacun de ses ``depends_on`` est
    placé avant lui - la liste est alors dans un ordre topologique, celui des migrations et de
    l'inclusion des routes."""
    seen: set[str] = set()
    for plugin in plugins:
        if plugin.name in seen:
            raise PluginOrderError(f"plugin {plugin.name!r} listé deux fois")
        for dependency in plugin.depends_on:
            if dependency not in seen:
                raise PluginOrderError(
                    f"le plugin {plugin.name!r} dépend de {dependency!r}, qui doit être listé avant lui"
                )
        seen.add(plugin.name)
