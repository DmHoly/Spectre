"""Cahier de données d'une expérience : des vues sur les données de caractérisation de ses plaques
(PRISM), chacune avec ses observations / sa conclusion - le cahier de labo de l'étude, repris tel
quel dans son rapport.

- ``GET  /{slug}/donnees/sources`` : les types de données qu'on peut charger (requêtes PRISM implémentées).
- ``POST /{slug}/donnees/instantanes`` : charger un type de données pour des plaques et le figer
  (:mod:`spectre.core.datasets`) ; ``GET .../instantanes/{id}`` le relit.
- ``POST/PUT/DELETE /{slug}/experiences/{ref}/cahier[/{entry_id}]`` : ajouter / modifier / retirer
  une vue. Comme tout le reste de la fiche, chaque changement est une nouvelle version (évolution
  légère) - la traçabilité d'un cahier de labo, pour rien.

Une vue = un instantané + un composant de visualisation (``component``, une clé du registre
``DataViz`` côté page, ``js/dataviz/``) + ses réglages (``options``, libres : c'est le composant qui
les lit) + des observations (``note``) et, au besoin, l'objectif qu'elle sert. Le serveur ne connaît
pas les composants : ajouter une visualisation ne demande que d'écrire son fichier JS.

Routes en ``{ref:path}/cahier`` : ce routeur est inclus avant celui des expériences (voir app.py),
dont le ``GET``/``DELETE /{slug}/experiences/{ref:path}`` avalerait sinon ces adresses.
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Callable

import follow
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core import datasets, microprojects
from ..core.accounts import User
from ..core.microprojects import Microproject
from ..core.permissions import require_role
from .deps import get_current_user
from .experiments import _derive_branch, _not_found
from .structures import _form_validation_error

router = APIRouter(prefix="/api/microprojets", tags=["notebook"])

NOTEBOOK_KEY = "data_notebook"
MAX_ENTRIES = 60
_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,48}$")
_ENTRY_ID_RE = re.compile(r"^nb_[0-9a-f]{12}$")


def _source_error(exc: datasets.DataSourceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


class SnapshotRequest(BaseModel):
    hook: str
    wafers: list[str] = []
    refresh: bool = False


class EntryInput(BaseModel):
    title: str
    snapshot_id: str
    component: str
    options: dict[str, Any] = {}
    note: str | None = None
    objective: str | None = None
    in_report: bool = True


class EntryUpdate(BaseModel):
    title: str | None = None
    snapshot_id: str | None = None
    component: str | None = None
    options: dict[str, Any] | None = None
    note: str | None = None
    objective: str | None = None
    in_report: bool | None = None
    move: int | None = None  # -1 : remonter d'un cran, +1 : descendre


@router.get("/{slug}/donnees/sources")
def notebook_sources(microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    return {"sources": datasets.available_sources(), "demo": datasets.demo_enabled()}


@router.post("/{slug}/donnees/instantanes", status_code=201)
def take_snapshot(body: SnapshotRequest, microproject: Microproject = Depends(require_role("editor"))) -> dict:
    try:
        dataset = datasets.fetch(body.hook, body.wafers, refresh=body.refresh)
    except datasets.DataSourceError as exc:
        raise _source_error(exc) from exc
    snapshot_id = datasets.store(microproject.slug, dataset)
    return {"snapshot_id": snapshot_id, **dataset}


@router.get("/{slug}/donnees/instantanes/{snapshot_id}")
def read_snapshot(snapshot_id: str, microproject: Microproject = Depends(require_role("viewer"))) -> dict:
    try:
        return {"snapshot_id": snapshot_id, **datasets.load(microproject.slug, snapshot_id)}
    except datasets.DataSourceError as exc:
        raise _source_error(exc) from exc


def _clean_text(value: str | None, limit: int) -> str | None:
    value = (value or "").strip()
    return value[:limit] or None


def _check_options(options: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(options, ensure_ascii=False)) > 20000:
        raise HTTPException(status_code=422, detail="réglages de la vue trop volumineux")
    return options


def _check_component(component: str) -> str:
    if not _COMPONENT_RE.fullmatch(component or ""):
        raise HTTPException(status_code=422, detail="composant de visualisation invalide")
    return component


def _check_objective(objective: str | None, parent: Any) -> str | None:
    objective = _clean_text(objective, 200)
    if objective and not any(o.name == objective for o in parent.objectives):
        raise HTTPException(status_code=422, detail=f"objectif « {objective} » introuvable sur cette expérience")
    return objective


def _snapshot_summary(slug: str, snapshot_id: str) -> dict[str, Any]:
    try:
        dataset = datasets.load(slug, snapshot_id)
    except datasets.DataSourceError as exc:
        raise HTTPException(status_code=422, detail="instantané de données introuvable - rechargez les données") from exc
    return {
        "snapshot_id": snapshot_id,
        "hook": dataset.get("hook"),
        "hook_title": dataset.get("hook_title"),
        "wafers": dataset.get("wafers", []),
        "source": dataset.get("source"),
        "fetched_at": dataset.get("fetched_at"),
        "row_count": len(dataset.get("rows", [])),
    }


def _commit(
    microproject: Microproject, ref: str, user: User, mutate: Callable[[list[dict], Any], dict], failure: str
) -> dict:
    """Une évolution légère qui ne change que le cahier (tout le reste reporté tel quel)."""
    repo = microprojects.get_repository(microproject.slug)
    try:
        parent = repo.get(ref)
    except follow.ExperimentNotFoundError as exc:
        raise _not_found(exc) from exc
    entries = [dict(e) for e in parent.metadata.get(NOTEBOOK_KEY, [])]
    result = mutate(entries, parent)
    builder = repo.derive(
        ref,
        title=parent.title,
        intent=parent.intent,
        new_branch=_derive_branch(repo, parent, None),
        author=user.name,
        hypothesis=parent.hypothesis,
    )
    builder.metadata = dict(parent.metadata)
    builder.metadata[NOTEBOOK_KEY] = entries
    builder.form_answers = dict(parent.form_answers)
    builder.evidence = list(parent.evidence)
    builder.tags = list(parent.tags)
    builder.conclusion = parent.conclusion
    try:
        experiment = builder.commit()
    except follow.FormValidationError as exc:
        raise _form_validation_error(exc) from exc
    except follow.FollowError as exc:
        raise HTTPException(status_code=400, detail=f"{failure} - rechargez la page et réessayez.") from exc
    return {"id": experiment.id, **result}


def _find(entries: list[dict], entry_id: str) -> int:
    for i, entry in enumerate(entries):
        if entry.get("id") == entry_id:
            return i
    raise HTTPException(status_code=404, detail="vue introuvable dans le cahier de cette version")


@router.post("/{slug}/experiences/{ref:path}/cahier", status_code=201)
def add_entry(
    ref: str,
    body: EntryInput,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    title = _clean_text(body.title, 200)
    if not title:
        raise HTTPException(status_code=422, detail="donnez un titre à cette vue")
    snapshot = _snapshot_summary(microproject.slug, body.snapshot_id)

    def mutate(entries: list[dict], parent: Any) -> dict:
        if len(entries) >= MAX_ENTRIES:
            raise HTTPException(status_code=422, detail=f"{MAX_ENTRIES} vues au maximum par cahier")
        now = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": f"nb_{secrets.token_hex(6)}",
            "title": title,
            **snapshot,
            "component": _check_component(body.component),
            "options": _check_options(body.options),
            "note": _clean_text(body.note, 20000),
            "objective": _check_objective(body.objective, parent),
            "in_report": body.in_report,
            "created_by": user.name,
            "created_at": now,
            "updated_by": user.name,
            "updated_at": now,
        }
        entries.append(entry)
        return {"entry_id": entry["id"]}

    return _commit(microproject, ref, user, mutate, "Impossible d'ajouter cette vue")


@router.put("/{slug}/experiences/{ref:path}/cahier/{entry_id}")
def update_entry(
    ref: str,
    entry_id: str,
    body: EntryUpdate,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    if not _ENTRY_ID_RE.fullmatch(entry_id):
        raise HTTPException(status_code=404, detail="vue introuvable")
    snapshot = _snapshot_summary(microproject.slug, body.snapshot_id) if body.snapshot_id else None

    def mutate(entries: list[dict], parent: Any) -> dict:
        index = _find(entries, entry_id)
        entry = entries[index]
        if body.title is not None:
            title = _clean_text(body.title, 200)
            if not title:
                raise HTTPException(status_code=422, detail="donnez un titre à cette vue")
            entry["title"] = title
        if snapshot:
            entry.update(snapshot)
        if body.component is not None:
            entry["component"] = _check_component(body.component)
        if body.options is not None:
            entry["options"] = _check_options(body.options)
        if body.note is not None:
            entry["note"] = _clean_text(body.note, 20000)
        if body.objective is not None:
            entry["objective"] = _check_objective(body.objective, parent)
        if body.in_report is not None:
            entry["in_report"] = body.in_report
        entry["updated_by"] = user.name
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        if body.move:
            target = max(0, min(len(entries) - 1, index + (1 if body.move > 0 else -1)))
            entries.insert(target, entries.pop(index))
        return {"entry_id": entry_id}

    return _commit(microproject, ref, user, mutate, "Impossible d'enregistrer cette vue")


@router.delete("/{slug}/experiences/{ref:path}/cahier/{entry_id}")
def remove_entry(
    ref: str,
    entry_id: str,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(get_current_user),
) -> dict:
    def mutate(entries: list[dict], parent: Any) -> dict:
        entries.pop(_find(entries, entry_id))
        return {}

    return _commit(microproject, ref, user, mutate, "Impossible de retirer cette vue")
