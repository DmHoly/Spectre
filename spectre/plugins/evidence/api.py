"""Les preuves d'une expérience : en ajouter une (liens, mesure, images collées) et annoter ses
images. Comme tout le reste de la fiche, chaque changement est une écriture légère sur la piste - une
nouvelle version qui reporte tout le reste (:func:`spectre.plugins.experiments.service.amend`).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Literal

import follow
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..accounts.deps import current_user
from ..accounts.service import User
from ..attachments.store import uploaded_image
from ..experiments import service as experiments
from ..microprojects.deps import require_role
from ..microprojects.service import Microproject
from .service import EVIDENCE_EXTRA_KEY, native_evidence_fields

router = APIRouter(prefix="/api/microprojets", tags=["evidence"])


class EvidenceImageInput(BaseModel):
    image_id: str  # returned by POST /images once pasted/dropped in the preuve form
    caption: str | None = None


class EvidenceInput(BaseModel):
    description: str
    source: str = ""
    # a folder, a PowerPoint deck, a SharePoint page... - network paths as well as URLs
    links: list[str] = []
    images: list[EvidenceImageInput] = []
    metric_name: str | None = None
    metric_value: float | None = None
    metric_unit: str | None = None
    step_index: int | None = None
    kind: Literal["standard", "image", "graph"] = "standard"
    objective: str | None = None
    interpretation: str | None = None
    graph_config: dict[str, Any] | None = None


class AnnotationInput(BaseModel):
    attachment_id: str
    type: Literal["arrow", "box"]
    x: float
    y: float
    x2: float | None = None
    y2: float | None = None
    label: str | None = None


class EvidenceAnnotationsRequest(BaseModel):
    annotations: list[AnnotationInput]


MAX_EVIDENCE_IMAGES = 12
MAX_EVIDENCE_LINKS = 10


def _clean_evidence_links(raw: list[str]) -> list[str]:
    """A preuve's links as typed or pasted - one per entry, surrounding quotes dropped (Windows'
    « Copier en tant que chemin d'accès » adds them), blanks and duplicates removed."""
    links: list[str] = []
    for value in raw:
        value = (value or "").strip().strip('"').strip()
        if value and value not in links:
            links.append(value[:1000])
    if len(links) > MAX_EVIDENCE_LINKS:
        raise HTTPException(status_code=422, detail=f"{MAX_EVIDENCE_LINKS} liens au maximum par preuve")
    return links


@router.post("/{slug}/experiences/{ref}/preuves", status_code=201)
def add_evidence(
    ref: str,
    body: EvidenceInput,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Attach a piece of evidence (a link, a measurement, pasted images) to an experiment - a
    lightweight write on its line of study (``ref``), everything else carried over unchanged
    (:func:`spectre.plugins.experiments.service.amend`).
    """
    metric = None
    if body.metric_name:
        if body.metric_value is None:
            raise HTTPException(status_code=422, detail="une valeur est requise pour la mesure nommée")
        metric = {body.metric_name: follow.Quantity(value=body.metric_value, unit=body.metric_unit)}

    links = _clean_evidence_links(body.links)
    if len(body.images) > MAX_EVIDENCE_IMAGES:
        raise HTTPException(status_code=422, detail=f"{MAX_EVIDENCE_IMAGES} images au maximum par preuve")
    if len({img.image_id for img in body.images}) != len(body.images):
        raise HTTPException(status_code=422, detail="La même image figure deux fois.")
    images = [(img, uploaded_image(microproject.slug, img.image_id)) for img in body.images]
    kind = "image" if images and body.kind == "standard" else body.kind
    source = body.source.strip() or (links[0] if links else "")
    evidence_id = secrets.token_hex(6)
    extra = {"kind": kind, "objective": body.objective, "interpretation": body.interpretation, "graph_config": body.graph_config}

    def change(builder: Any, parent: Any) -> None:
        if body.step_index is not None:
            process = parent.metadata.get("structureforge_process")
            steps = process.get("steps", []) if process else []
            if not steps:
                raise HTTPException(
                    status_code=422,
                    detail="cette expérience n'a pas de procédé éditable enregistré : impossible d'associer une étape",
                )
            if not (0 <= body.step_index < len(steps)):
                raise HTTPException(status_code=422, detail="étape sélectionnée invalide")
        if body.objective is not None and not any(o.name == body.objective for o in parent.objectives):
            raise HTTPException(status_code=422, detail=f"objectif {body.objective!r} introuvable sur cette expérience")

        if links:
            builder.metadata["evidence_links"] = {**builder.metadata.get("evidence_links", {}), evidence_id: links}
        builder.metadata[EVIDENCE_EXTRA_KEY] = {**builder.metadata.get(EVIDENCE_EXTRA_KEY, {}), evidence_id: extra}
        if images:
            # the pasted images become the preuve's attachments in this same version
            now = datetime.now(timezone.utc).isoformat()
            builder.metadata["attachments"] = list(builder.metadata.get("attachments", [])) + [
                {
                    "id": img.image_id,
                    "filename": sidecar.get("filename", "image"),
                    "content_type": sidecar.get("content_type"),
                    "size": sidecar.get("size"),
                    "entity_index": None,
                    "evidence_id": evidence_id,
                    "caption": (img.caption or "").strip()[:200] or None,
                    "uploaded_by": user.name,
                    "uploaded_at": now,
                }
                for img, sidecar in images
            ]
        builder.add_evidence(
            id=evidence_id,
            description=body.description,
            source=source,
            metrics=metric or {},
            step_index=body.step_index,
            **native_evidence_fields(extra),
        )

    experiment = experiments.amend(microproject.slug, ref, author=user.name, change=change)
    return {"id": ref, "version_id": experiment.id, "evidence_id": evidence_id}


@router.post("/{slug}/experiences/{ref}/preuves/{evidence_id}/annotations")
def update_evidence_annotations(
    ref: str,
    evidence_id: str,
    body: EvidenceAnnotationsRequest,
    microproject: Microproject = Depends(require_role("editor")),
    user: User = Depends(current_user),
) -> dict:
    """Replace a ``kind="image"`` preuve's annotations (arrows/boxes marking up one of its attached
    images) - a lightweight write like every other one on the evidence (only this preuve's
    ``image_annotations`` changes).
    """
    annotations = {"image_annotations": [a.model_dump() for a in body.annotations]}
    native = native_evidence_fields(annotations)

    def change(builder: Any, parent: Any) -> None:
        if not any(e.id == evidence_id for e in parent.evidence):
            raise HTTPException(status_code=404, detail="preuve introuvable sur cette version")
        attachment_ids = {a.get("id") for a in parent.metadata.get("attachments", []) if a.get("evidence_id") == evidence_id}
        if any(annotation.attachment_id not in attachment_ids for annotation in body.annotations):
            raise HTTPException(status_code=422, detail="pièce jointe introuvable sur cette preuve")
        builder.evidence = [e.model_copy(update=native) if native and e.id == evidence_id else e for e in parent.evidence]
        extras = builder.metadata.setdefault(EVIDENCE_EXTRA_KEY, {})
        extras[evidence_id] = {**extras.get(evidence_id, {}), **annotations}

    experiment = experiments.amend(microproject.slug, ref, author=user.name, change=change)
    return {"id": ref, "version_id": experiment.id}
