"""Où servent les briques technologiques : les études dont la version courante (la pointe de chaque
piste) contient une copie d'une brique de bibliothèque - un groupe d'étapes dont la ``source`` est
son id (``process_bricks``, voir :class:`spectre.plugins.structures.simulation.ProcessBrick`) - avec
la version de la brique que porte cette copie. Comme les usages d'une référence : tous les µprojets
sont lus (une brique partagée sert partout), mais un compte ne voit d'une étude d'un µprojet dont il
n'est pas membre que le nom de ce µprojet."""

from __future__ import annotations

from typing import Any

from ..accounts.service import User
from ..experiments.repository import branch_tips, display_status, get_repository
from ..microprojects import service as microprojects
from ..structures.simulation import BRICKS_METADATA_KEY
from . import service
from .service import TECH_BRICKS


def tech_brick_usages(user: User, microproject_slug: str | None) -> dict[str, list[dict[str, Any]]]:
    """Par id de brique visible (intégrées, partagées, celles de ``microproject_slug``), les études
    qui en ont une copie, la plus récente d'abord - une liste vide pour une brique qui ne sert nulle
    part. Une étude : ``{microproject, linked, version}`` ; pour un membre de son µprojet, aussi
    ``experiment_id``, ``title``, ``status`` et ``updated_at``. ``version`` : celle de la brique
    quand on l'a copiée (``None`` pour une copie d'avant les versions)."""
    visible = {entry.item.id for entry in service.list_items(TECH_BRICKS, user, microproject_slug=microproject_slug)}
    found: dict[str, list[tuple[Any, Any, int | None]]] = {brick_id: [] for brick_id in visible}
    everything = microprojects.list_all()
    access = microprojects.accesses(user, everything)
    for mp in everything:
        for tip in branch_tips(get_repository(mp.slug)):
            raw = tip.metadata.get(BRICKS_METADATA_KEY)
            seen: set[str] = set()
            for item in raw if isinstance(raw, list) else []:
                source = item.get("source") if isinstance(item, dict) else None
                if source in found and source not in seen:
                    seen.add(source)
                    version = item.get("version")
                    found[source].append((mp, tip, version if isinstance(version, int) else None))
    result: dict[str, list[dict[str, Any]]] = {}
    for brick_id, uses in found.items():
        uses.sort(key=lambda use: use[1].created_at, reverse=True)
        result[brick_id] = [_usage(mp, tip, version, access.get(mp.id)) for mp, tip, version in uses]
    return result


def _usage(mp: Any, tip: Any, version: int | None, access: Any) -> dict[str, Any]:
    if access is None or access.role is None:
        return {"microproject": {"name": mp.name}, "linked": False, "version": version}
    return {
        "microproject": {"slug": mp.slug, "code": mp.code, "name": mp.name},
        "experiment_id": tip.branch,
        "title": tip.title,
        "status": display_status(tip),
        "updated_at": tip.created_at.isoformat(),
        "linked": True,
        "version": version,
    }
