"""Request bodies of an experience's launch and evolution - by the structure builder, with pictures,
or as a whole DOE campaign."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from structureforge.process.steps import ProcessStep

from ..structures.schemas import CampaignPreviewRequest, StructureImageInput
from ..structures.simulation import DeclaredParam, SubstrateSpec
from .entities import EntityTrackingInput


class ObjectiveInput(BaseModel):
    name: str
    metric: str
    direction: str = "observe"
    target: float | None = None
    tolerance: float | None = None
    rationale: str | None = None  # pourquoi cet objectif compte
    verification_method: str | None = None  # comment on prévoit de le vérifier


class LaunchExperienceRequest(BaseModel):
    substrate: SubstrateSpec
    steps: list[ProcessStep]
    title: str
    intent: str
    hypothesis: str | None = None
    # a short description that puts the experience back in context (shown at the top of the fiche) -
    # None on an evolution keeps the previous version's (see apply_context)
    context: str | None = None
    objectives: list[ObjectiveInput] = []
    # required on a brand-new launch (see launch_experience) ; optional when evolving, where
    # it's only needed to fix forward an experience whose lineage never got one (see evolve_experience).
    entities: list[EntityTrackingInput] = []
    new_branch: str | None = None  # only meaningful when evolving: fork instead of continuing
    # the steps' declared parameters (see simulation.DeclaredParam), keyed by step index - kept in
    # the committed process metadata (simulation.process_metadata) so an evolution gets them back
    declared_params: dict[str, list[DeclaredParam]] = {}
    # answers to the microproject's active commit form (spectre.plugins.intent_forms), if one is
    # configured - re-asked on every real launch/evolution, unlike metadata/tags/evidence which
    # lightweight evolutions (conclure/preuves/etiquettes...) simply carry forward unchanged.
    form_answers: dict[str, Any] = {}


class LaunchImageExperienceRequest(BaseModel):
    """A launch (or an evolution, see ``evolve_experience_with_image``) whose structure is given as
    pictures instead of a simulated process - otherwise the same intention fields as
    :class:`LaunchExperienceRequest`."""

    images: list[StructureImageInput]
    title: str
    intent: str
    hypothesis: str | None = None
    # a short description that puts the experience back in context (shown at the top of the fiche) -
    # None on an evolution keeps the previous version's (see apply_context)
    context: str | None = None
    objectives: list[ObjectiveInput] = []
    entities: list[EntityTrackingInput] = []
    new_branch: str | None = None  # evolution only: fork instead of continuing
    form_answers: dict[str, Any] = {}


class LaunchCampaignRequest(CampaignPreviewRequest):
    title: str
    intent: str
    hypothesis: str | None = None
    # a short description that puts the experience back in context (shown at the top of the fiche) -
    # None on an evolution keeps the previous version's (see apply_context)
    context: str | None = None
    objectives: list[ObjectiveInput] = []
    entities: list[EntityTrackingInput] = []  # at least one (the reference sample) is required
    form_answers: dict[str, Any] = {}
    # when the campaign is built from an existing version (« partir d'une ref » / « continuer ») it
    # branches off that commit so the lineage/baseline link is kept, exactly like an évolution -
    # instead of starting a disconnected new branch.
    from_ref: str | None = None
    new_branch: str | None = None  # only meaningful with from_ref: name the forked branch
