"""Le cahier de données d'une étude : des vues sur les données de caractérisation de ses plaques,
chacune avec ses observations - le cahier de labo de l'étude, repris tel quel dans son rapport.

Une vue = un instantané (:mod:`.snapshots`) + un composant de visualisation (``component``, une clé
du registre ``DataViz`` côté page, ``notebook/static/dataviz/``) + ses réglages (``options``, libres :
c'est le composant qui les lit) + des observations (``note``) et, au besoin, l'objectif qu'elle sert.
Le serveur ne connaît pas les composants : ajouter une visualisation ne demande que d'écrire son
fichier JS.

Les vues sont rangées dans les métadonnées de l'étude (:data:`NOTEBOOK_KEY`) ; chaque changement est
une écriture sur la piste (:func:`spectre.plugins.experiments.service.amend`, ``If-Match`` compris) -
la traçabilité d'un cahier de labo, pour rien.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any

import follow

from ...kernel.errors import InvalidInput, NotFound
from ..experiments import service as experiments
from ..experiments.repository import get_repository
from . import snapshots
from .schemas import EntryInput, EntryUpdate

NOTEBOOK_KEY = "data_notebook"
MAX_ENTRIES = 60
MAX_OPTIONS_SIZE = 20000
_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,48}$")


def entries(slug: str, experiment_id: str, version_id: str | None = None) -> list[dict]:
    """Les vues du cahier d'une version de la piste (sa pointe par défaut), dans l'ordre."""
    version = experiments.version_of(get_repository(slug), experiment_id, version_id)
    return list(version.metadata.get(NOTEBOOK_KEY, []))


def _clean_text(value: str | None, limit: int) -> str | None:
    return (value or "").strip()[:limit] or None


def _title(value: str | None) -> str:
    title = _clean_text(value, 200)
    if not title:
        raise InvalidInput("Donnez un titre à cette vue.")
    return title


def _component(value: str) -> str:
    if not _COMPONENT_RE.fullmatch(value or ""):
        raise InvalidInput("Composant de visualisation invalide.")
    return value


def _options(options: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(options, ensure_ascii=False)) > MAX_OPTIONS_SIZE:
        raise InvalidInput("Réglages de la vue trop volumineux.")
    return options


def _objective(value: str | None, parent: follow.Experiment) -> str | None:
    objective = _clean_text(value, 200)
    if objective and not any(o.name == objective for o in parent.objectives):
        raise InvalidInput(f"Objectif « {objective} » introuvable sur cette expérience.")
    return objective


def _snapshot_summary(slug: str, snapshot_id: str) -> dict[str, Any]:
    try:
        dataset = snapshots.load(slug, snapshot_id)
    except NotFound as exc:
        raise InvalidInput("Instantané de données introuvable - rechargez les données.", code="snapshot_not_found") from exc
    return {
        "snapshot_id": snapshot_id,
        "hook": dataset.get("hook"),
        "hook_title": dataset.get("hook_title"),
        "wafers": dataset.get("wafers", []),
        "source": dataset.get("source"),
        "fetched_at": dataset.get("fetched_at"),
        "row_count": len(dataset.get("rows", [])),
    }


def _index(notebook: list[dict], entry_id: str) -> int:
    for i, entry in enumerate(notebook):
        if entry.get("id") == entry_id:
            return i
    raise NotFound("Vue introuvable dans le cahier de cette étude.", code="notebook_entry_not_found")


def add_entry(slug: str, experiment_id: str, body: EntryInput, *, author: str, expected_version: str | None) -> tuple[dict, follow.Experiment]:
    """Ajoute une vue en fin de cahier - renvoie la vue et la nouvelle pointe."""
    title = _title(body.title)
    component = _component(body.component)
    options = _options(body.options)
    snapshot = _snapshot_summary(slug, body.snapshot_id)
    now = datetime.now(timezone.utc).isoformat()
    entry: dict[str, Any] = {}

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        notebook = list(parent.metadata.get(NOTEBOOK_KEY, []))
        if len(notebook) >= MAX_ENTRIES:
            raise InvalidInput(f"{MAX_ENTRIES} vues au maximum par cahier.")
        entry.update(
            id=f"nb_{secrets.token_hex(6)}",
            title=title,
            **snapshot,
            component=component,
            options=options,
            note=_clean_text(body.note, 20000),
            objective=_objective(body.objective, parent),
            in_report=body.in_report,
            created_by=author,
            created_at=now,
            updated_by=author,
            updated_at=now,
        )
        builder.metadata[NOTEBOOK_KEY] = [*notebook, entry]

    tip = experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
    return entry, tip


def update_entry(
    slug: str, experiment_id: str, entry_id: str, body: EntryUpdate, *, author: str, expected_version: str | None
) -> tuple[dict, follow.Experiment]:
    """Modifie les champs envoyés d'une vue (``position`` : sa place dans le cahier, ramenée dans les
    bornes). Une modification sans effet ne crée pas de version."""
    changes = body.model_dump(exclude_unset=True)
    position = changes.pop("position", None)
    fields: dict[str, Any] = {}
    if "title" in changes:
        fields["title"] = _title(changes["title"])
    if changes.get("snapshot_id"):
        fields.update(_snapshot_summary(slug, changes["snapshot_id"]))
    if changes.get("component") is not None:
        fields["component"] = _component(changes["component"])
    if changes.get("options") is not None:
        fields["options"] = _options(changes["options"])
    if "note" in changes:
        fields["note"] = _clean_text(changes["note"], 20000)
    if changes.get("in_report") is not None:
        fields["in_report"] = changes["in_report"]
    result: dict[str, Any] = {}

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        notebook = [dict(e) for e in parent.metadata.get(NOTEBOOK_KEY, [])]
        index = _index(notebook, entry_id)
        entry = notebook[index]
        updated = {**entry, **fields}
        if "objective" in changes:
            updated["objective"] = _objective(changes["objective"], parent)
        if updated != entry:
            updated.update(updated_by=author, updated_at=datetime.now(timezone.utc).isoformat())
        notebook[index] = updated
        if position is not None:
            notebook.insert(max(0, min(len(notebook) - 1, position)), notebook.pop(index))
        builder.metadata[NOTEBOOK_KEY] = notebook
        result.update(updated)

    tip = experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
    return result, tip


def remove_entry(slug: str, experiment_id: str, entry_id: str, *, author: str, expected_version: str | None) -> follow.Experiment:
    """Retire une vue du cahier (elle reste dans l'historique de l'étude)."""

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        notebook = list(parent.metadata.get(NOTEBOOK_KEY, []))
        notebook.pop(_index(notebook, entry_id))
        builder.metadata[NOTEBOOK_KEY] = notebook

    return experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
