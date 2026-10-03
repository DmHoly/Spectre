"""Transverse readings of the experiments, across µprojets: each µprojet's counts
(``GET /api/experiment-stats``) and a thématique's frise (``GET /api/experiment-timeline``) - for
the home, project and thématique pages.

Company-wide visibility: any signed-in user sees which µprojets exist, their counts and the dates
and outcomes of their experiments; what an experiment *is* (its id, its title, why it's on hold)
only reaches the µprojet's members (:func:`redact_for_viewer`). Each Follow repository is loaded
once per request.
"""

from __future__ import annotations

from typing import Any, Iterable

from ...kernel.errors import NotFound
from ..accounts.service import User
from ..areas import service as areas
from ..microprojects import service as microprojects
from ..microprojects.service import Microproject
from .entities import compact
from .lineage import lineage_graph
from .repository import RUNNING_STATUSES, branch_tips, get_repository

# What anyone sees of an experiment on a frise, and what only the µprojet's members see.
PUBLIC_NODE_FIELDS = ("started_at", "ended_at", "continued_at", "status", "decision", "is_merge", "is_tip")
MEMBER_NODE_FIELDS = ("id", "experiment_id", "version_id", "title")


def tracked_wafers(experiments: Iterable[Any]) -> set[str]:
    """The wafers these experiments track, one per wafer key - the lasermark compared without case
    nor separators (:func:`spectre.plugins.experiments.entities.compact`): the same wafer followed by
    two studies, or typed « w12-a3 » here and « W12 A3 » there, counts once."""
    return {
        compact(entry["sample_id"])
        for experiment in experiments
        for entry in experiment.metadata.get("physical_tracking", [])
        if entry.get("sample_id")
    }


def experiment_counts(repo: Any) -> dict:
    """``{running, concluded, abandoned, wafers}`` over the µprojet's lines of study (one per
    branch, its current tip): in progress (draft or running, paused ones included), concluded,
    abandoned, and the distinct wafers they track."""
    tips = branch_tips(repo)
    statuses = [tip.conclusion.status for tip in tips]
    return {
        "running": sum(1 for status in statuses if status in RUNNING_STATUSES),
        "concluded": statuses.count("concluded"),
        "abandoned": statuses.count("abandoned"),
        "wafers": len(tracked_wafers(tips)),
    }


def redact_for_viewer(node: dict, member: bool) -> dict:
    """One node of a µprojet's lineage (:func:`lineage_graph`) as a viewer may see it: its dates and
    outcome for anyone, plus what the experiment is for the µprojet's members."""
    point = {key: node[key] for key in PUBLIC_NODE_FIELDS}
    hold = node.get("hold")
    point["hold"] = {"since": hold["since"], **({"reason": hold["reason"]} if member else {})} if hold else None
    if member:
        point.update({key: node[key] for key in MEMBER_NODE_FIELDS if key in node})
    return point


def _utc_iso(value: str | None) -> str | None:
    """SQLite's ``datetime('now')`` (« 2026-03-01 09:30:00 », UTC, no zone) as ISO 8601 with its
    zone, so a browser doesn't read it as local time."""
    return f"{value.replace(' ', 'T')}Z" if value else None


class _Summaries:
    """The µprojet half of each row - who it is, where it sits, its owners and the viewer's role -
    with the projects, thématiques, roles and owners read once for the whole request."""

    def __init__(self, user: User, selected: list[Microproject]) -> None:
        self._areas = {area.id: area for area in areas.list_all()}
        self._thematics = {thematic.id: thematic for thematic in areas.list_thematics()}
        self._roles = {microproject.id: role for microproject, role in microprojects.list_for_user(user.id)}
        self._owners = microprojects.owners_by_microproject([m.id for m in selected])

    def __call__(self, microproject: Microproject) -> dict:
        area = self._areas.get(microproject.management_area_id)
        thematic = self._thematics.get(microproject.thematic_id)
        return {
            "slug": microproject.slug,
            "code": microproject.code,
            "name": microproject.name,
            "description": microproject.description,
            "created_at": _utc_iso(microproject.created_at),
            "area": {"slug": area.slug, "name": area.name} if area else None,
            "thematic": {"slug": thematic.slug, "name": thematic.name} if thematic else None,
            "role": self._roles.get(microproject.id),
            "owners": self._owners[microproject.id],
        }


def _select(*, microproject_slug: str | None = None, area_slug: str | None = None, thematic_slug: str | None = None) -> list[Microproject]:
    """The µprojets the filters designate - a filter naming nothing that exists is a 404."""
    selected = microprojects.list_all()
    if microproject_slug:
        try:
            selected = [microprojects.get_by_slug(microproject_slug)]
        except microprojects.MicroprojectNotFoundError as exc:
            raise NotFound(f"µprojet {microproject_slug!r} introuvable") from exc
    if area_slug:
        area = areas.get_by_slug(area_slug)
        thematic = areas.get_thematic(area.id, thematic_slug) if thematic_slug else None
        selected = [
            m for m in selected if m.management_area_id == area.id and (thematic is None or m.thematic_id == thematic.id)
        ]
    return selected


def stats(user: User, *, microproject_slug: str | None = None, area_slug: str | None = None) -> list[dict]:
    """``[{microproject, running, concluded, abandoned, wafers}]`` for every µprojet (of one project
    with ``area_slug``, or just one with ``microproject_slug``)."""
    selected = _select(microproject_slug=microproject_slug, area_slug=area_slug)
    summary = _Summaries(user, selected)
    return [{"microproject": summary(m), **experiment_counts(get_repository(m.slug))} for m in selected]


def timeline(user: User, *, area_slug: str, thematic_slug: str | None = None) -> list[dict]:
    """``[{microproject, nodes}]``: each µprojet of the project (or of one of its thématiques), oldest
    first, with its experiments laid out in time - the nodes of its lineage graph, redacted for
    whoever isn't a member (:func:`redact_for_viewer`), by start date."""
    selected = sorted(_select(area_slug=area_slug, thematic_slug=thematic_slug), key=lambda m: m.created_at or "")
    summary = _Summaries(user, selected)
    rows = []
    for microproject in selected:
        row = summary(microproject)
        nodes = lineage_graph(get_repository(microproject.slug))["nodes"]
        member = row["role"] is not None
        rows.append(
            {"microproject": row, "nodes": sorted((redact_for_viewer(n, member) for n in nodes), key=lambda n: n["started_at"])}
        )
    return rows
