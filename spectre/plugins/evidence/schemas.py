"""Les corps reçus par les routes des preuves."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EvidenceImageInput(BaseModel):
    image_id: str  # un fichier téléversé d'abord (POST .../attachments, purpose=evidence)
    caption: str | None = None


class EvidenceInput(BaseModel):
    description: str
    source: str = ""
    # un dossier, une présentation PowerPoint, une page SharePoint... - chemins réseau comme URL
    links: list[str] = []
    images: list[EvidenceImageInput] = []
    metric_name: str | None = None
    metric_value: float | None = None
    metric_unit: str | None = None
    step_index: int | None = None
    # « graph » n'est plus proposé à la création : il allait chercher une URL arbitraire
    kind: Literal["standard", "image"] = "standard"
    objective: str | None = None
    interpretation: str | None = None


class AnnotationInput(BaseModel):
    attachment_id: str
    type: Literal["arrow", "box"]
    x: float
    y: float
    x2: float | None = None
    y2: float | None = None
    label: str | None = None


class AnnotationsRequest(BaseModel):
    annotations: list[AnnotationInput]
