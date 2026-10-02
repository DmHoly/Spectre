"""What every route that writes an experience shares, whichever plugin it belongs to: naming the
piste a new version lands on, the intention fields of a launch, and turning Follow's errors into
the answer the page shows.
"""

from __future__ import annotations

import re
from typing import Any

import follow
from fastapi import HTTPException

from . import refs
from .schemas import ObjectiveInput

CONTEXT_METADATA_KEY = "context"


def _slugify_branch(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "experience"


def unique_branch(repo: "follow.Repository", title: str) -> str:
    base = _slugify_branch(title)
    branch = base
    suffix = 2
    while branch in repo.branches:
        branch = f"{base}-{suffix}"
        suffix += 1
    return branch


def require_branch_name(name: str | None) -> str | None:
    """A piste name typed by the user (``new_branch``) - refused with a "/" in it, which would not
    fit in the single ``{ref}`` path segment every experience route uses (see
    :mod:`spectre.plugins.experiments.api`)."""
    if name and "/" in name:
        raise HTTPException(status_code=422, detail="Le nom de la piste ne peut pas contenir « / ».")
    return name


def derive_branch(repo: "follow.Repository", parent: Any, requested: str | None) -> str | None:
    """Which branch to derive onto. An explicit fork request wins; otherwise continue the
    parent's own branch as long as it's still the tip. If someone else already evolved past this
    exact version (its branch has moved on), silently continue on a fresh branch instead of
    letting Follow's own branch-collision error - raw, in English, full of git vocabulary -
    reach a non-technical user.
    """
    if requested:
        return require_branch_name(requested)
    if repo.branches.get(parent.branch) == parent.id:
        return None
    return unique_branch(repo, parent.title)


def form_validation_error(exc: "follow.FormValidationError") -> HTTPException:
    """A commit form's own errors are already a list of specific, user-facing messages ("operator
    (Opérateur) est obligatoire") - meant, per its own docstring, to eventually drive a form UI
    that shows every invalid field at once rather than one at a time. Surfaced as a structured
    422 rather than folded into the generic FollowError->400 translation.
    """
    return HTTPException(status_code=422, detail={"message": "Réponses au formulaire d'intention invalides.", "errors": exc.errors})


def not_found(exc: follow.ExperimentNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc.args[0]) if exc.args else "expérience introuvable")


def ref_the_first_experience(repo: "follow.Repository", experiment: "follow.Experiment") -> None:
    """A brand-new microproject has no ref yet to start from - so its very first experience becomes
    one automatically (the default "ref vX.Y.Z" name), rather than leaving every microproject stuck
    with nothing to feature in "Partir d'une ref" until someone remembers to tag one by hand.
    """
    if len(repo) == 1:
        refs.create_ref(repo, experiment.id)


def apply_context(metadata: dict, context: str | None) -> None:
    """Set (or clear, when blank) the experience's short context description in its metadata -
    Follow's Experiment has title/intent/hypothesis but nothing for « remettre en contexte ». ``None``
    leaves whatever the metadata already carries (an evolution keeps the previous version's)."""
    if context is None:
        return
    value = context.strip()[:2000]
    if value:
        metadata[CONTEXT_METADATA_KEY] = value
    else:
        metadata.pop(CONTEXT_METADATA_KEY, None)


def require_title_and_intent(title: str, intent: str) -> None:
    if not title.strip() or not intent.strip():
        raise HTTPException(status_code=422, detail="Le titre et l'intention sont obligatoires.")


def first_tracked_entity(entities: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    """An image-mode experience follows exactly one sample - the first one actually named."""
    named = [e for e in entities if e["sample_id"]]
    return named[:1]


def split_objectives(inputs: list[ObjectiveInput]) -> tuple[list["follow.Objective"], dict[str, str]]:
    """``follow.Objective`` has no "how will we check this" field (only ``rationale``, the *why*)
    - ``verification_method`` is Spectre-specific, so it's kept out of the ``Objective`` itself and
    returned separately, to be stashed under ``Experiment.metadata["objective_verification"]``
    (keyed by objective name) the same way ``structureforge_process`` already rides along there.
    """
    objectives: list[follow.Objective] = []
    verification: dict[str, str] = {}
    for o in inputs:
        data = o.model_dump(exclude_none=True, exclude={"verification_method"})
        objectives.append(follow.Objective(**data))
        if o.verification_method:
            verification[o.name] = o.verification_method
    return objectives, verification
