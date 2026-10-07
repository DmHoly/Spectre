"""Les rattachements d'un µprojet : une étude **flottante** (partie de rien - sa première version
n'a pas de parent) qu'on accroche après coup, depuis l'arbre, sous une version d'une autre étude -
quand on l'a lancée en racine par erreur alors qu'elle continuait cette autre étude.

Le lien est explicite et réversible : il vit ici, dans la base, et non dans le dépôt Follow -
l'histoire des versions n'est pas réécrite. L'arbre le dessine autrement qu'une filiation (trait
propre, qui l'a posé et quand) ; détacher l'étude la rend à nouveau flottante. Un rattachement dont
l'une des deux études n'existe plus est ignoré.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import follow

from ...kernel.db import get_conn
from ...kernel.errors import InvalidInput, NotFound
from . import service
from .repository import get_repository


@dataclass(frozen=True)
class Attachment:
    experiment_id: str
    parent_experiment_id: str
    parent_version_id: str
    author: str
    created_at: str

    def payload(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "parent": {"experiment_id": self.parent_experiment_id, "version_id": self.parent_version_id},
            "author": self.author,
            "created_at": self.created_at,
        }


def _from_row(row: sqlite3.Row) -> Attachment:
    return Attachment(
        experiment_id=row["experiment_id"],
        parent_experiment_id=row["parent_experiment_id"],
        parent_version_id=row["parent_version_id"],
        author=row["author"],
        created_at=row["created_at"],
    )


def list_attachments(microproject_id: int) -> list[Attachment]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM experiment_attachments WHERE microproject_id = ? ORDER BY created_at", (microproject_id,)
        ).fetchall()
    return [_from_row(row) for row in rows]


def line_root(repo: follow.Repository, experiment_id: str) -> follow.Experiment:
    """La première version de l'histoire de la piste (en remontant les premiers parents)."""
    return service.history_of(repo, experiment_id)[0]


def is_floating(repo: follow.Repository, experiment_id: str) -> bool:
    """La piste est partie de rien : la première version de son histoire est la sienne."""
    return line_root(repo, experiment_id).branch == experiment_id


def _descendants(repo: follow.Repository, root_id: str, attached: list[tuple[str, str]]) -> set[str]:
    """Les versions qui descendent de ``root_id`` (elle comprise), par la filiation du dépôt et par
    les rattachements ``attached`` (``(version parente, racine rattachée)``)."""
    children: dict[str, list[str]] = {}
    for version in repo:
        for parent in version.parents:
            children.setdefault(parent, []).append(version.id)
    for parent, child in attached:
        children.setdefault(parent, []).append(child)
    seen = {root_id}
    frontier = [root_id]
    while frontier:
        for child in children.get(frontier.pop(), []):
            if child not in seen:
                seen.add(child)
                frontier.append(child)
    return seen


def attach(microproject_id: int, slug: str, experiment_id: str, parent_experiment_id: str, parent_version_id: str | None, *, user_id: int, author: str) -> Attachment:
    """Rattache la piste flottante ``experiment_id`` sous une version (la pointe sans
    ``parent_version_id``) d'une autre piste du µprojet - remplace un rattachement précédent."""
    repo = get_repository(slug)
    root = line_root(repo, experiment_id)
    if root.branch != experiment_id:
        raise InvalidInput("Seule une expérience partie de rien (sans expérience de départ) se rattache.", code="not_floating")
    try:
        parent = service.version_of(repo, parent_experiment_id, parent_version_id)
    except NotFound as exc:
        raise NotFound(f"Expérience de rattachement introuvable : {exc}", code="source_not_found") from exc
    others = [a for a in list_attachments(microproject_id) if a.experiment_id != experiment_id]
    others_edges = []
    for other in others:
        if other.experiment_id in repo.branches:
            others_edges.append((other.parent_version_id, line_root(repo, other.experiment_id).id))
    if parent.id in _descendants(repo, root.id, others_edges):
        raise InvalidInput("Impossible de rattacher une expérience à elle-même ou à ce qui en découle.", code="attachment_cycle")
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO experiment_attachments (microproject_id, experiment_id, parent_experiment_id, parent_version_id, created_by, author, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (microproject_id, experiment_id) DO UPDATE SET
                 parent_experiment_id = excluded.parent_experiment_id, parent_version_id = excluded.parent_version_id,
                 created_by = excluded.created_by, author = excluded.author, created_at = excluded.created_at""",
            (microproject_id, experiment_id, parent.branch, parent.id, user_id, author, now),
        )
    return Attachment(experiment_id, parent.branch, parent.id, author, now)


def detach(microproject_id: int, experiment_id: str) -> None:
    with get_conn() as conn:
        removed = conn.execute(
            "DELETE FROM experiment_attachments WHERE microproject_id = ? AND experiment_id = ?", (microproject_id, experiment_id)
        ).rowcount
    if not removed:
        raise NotFound("Cette expérience n'est rattachée à aucune autre.", code="attachment_not_found")


def graph_attachments(repo: follow.Repository, microproject_id: int) -> list[dict[str, Any]]:
    """Les rattachements à dessiner (:func:`lineage.lineage_graph`) : ``{root, parent, author,
    created_at}`` en ids de version - ceux dont les deux études existent encore, et dont la piste est
    toujours flottante."""
    present = {version.id for version in repo}
    drawn = []
    for attachment in list_attachments(microproject_id):
        if attachment.experiment_id not in repo.branches or attachment.parent_version_id not in present:
            continue
        root = line_root(repo, attachment.experiment_id)
        if root.branch != attachment.experiment_id:
            continue
        drawn.append({"root": root.id, "parent": attachment.parent_version_id, "author": attachment.author, "created_at": attachment.created_at})
    return drawn
