"""Les preuves d'une étude : les lire telles que l'API les montre, en ajouter une (liens, mesure,
images collées), annoter ses images. Comme tout le reste de la fiche, chaque changement est une
écriture légère sur la piste (:func:`spectre.plugins.experiments.service.amend`).

Ce que Spectre range à côté de ``follow.Evidence``, dans les métadonnées de la version et par id de
preuve - ce module est le seul à le lire et à l'écrire (la fusion de deux pistes le reporte sans le
lire : ``experiments.service.EVIDENCE_KEYED_METADATA``) :

- ``metadata["evidence_extra"][id]`` : type, objectif servi, interprétation, réglages d'une ancienne
  preuve « graphique », annotations des images. Rangés là plutôt que sur ``follow.Evidence``, dont
  les champs dépendent de la version de Follow installée (une version qui ne les déclare pas les
  ignore sans rien dire) ;
- ``metadata["evidence_links"][id]`` : les liens de la preuve, pour la même raison ;
- ``metadata["attachments"]`` : les images collées, téléversées d'abord (plugin attachments) puis
  rattachées à la preuve par une entrée qui porte son ``evidence_id``.
"""

from __future__ import annotations

import copy
import secrets
from datetime import datetime, timezone
from typing import Any

import follow

from ...kernel.errors import InvalidInput, NotFound
from ..attachments.store import content_url, uploaded_image
from ..experiments import service as experiments
from ..experiments.repository import get_repository
from .schemas import AnnotationInput, EvidenceInput

EVIDENCE_EXTRA_KEY = "evidence_extra"
EVIDENCE_LINKS_KEY = "evidence_links"
ATTACHMENTS_KEY = "attachments"
EVIDENCE_EXTRA_DEFAULTS: dict[str, Any] = {
    "kind": "standard",
    "objective": None,
    "interpretation": None,
    "graph_config": None,
    "image_annotations": [],
}
MAX_EVIDENCE_IMAGES = 12
MAX_EVIDENCE_LINKS = 10


# -- lecture ---------------------------------------------------------------------------------------


def _native_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Ceux de ``fields`` que le ``follow.Evidence`` installé déclare lui-même : passés aussi à la
    preuve, pour qu'un Follow qui les porte nativement reste d'accord avec la copie des métadonnées."""
    return {name: value for name, value in fields.items() if name in follow.Evidence.model_fields}


def _payload(slug: str, version: follow.Experiment, evidence: follow.Evidence) -> dict:
    """Une preuve telle que l'API la montre : les champs de Follow, ceux de Spectre (lus sur la
    preuve quand le Follow installé les déclare et qu'ils y ont été posés, sinon dans les
    métadonnées, sinon leur défaut), ses liens et ses images avec leur ``url``."""
    payload = evidence.model_dump(mode="json")
    stored = version.metadata.get(EVIDENCE_EXTRA_KEY, {}).get(evidence.id, {})
    for name, default in EVIDENCE_EXTRA_DEFAULTS.items():
        if name in follow.Evidence.model_fields and name in evidence.model_fields_set:
            continue
        payload[name] = stored.get(name, copy.deepcopy(default))
    payload["annotations"] = payload.pop("image_annotations")
    payload["links"] = list(version.metadata.get(EVIDENCE_LINKS_KEY, {}).get(evidence.id, []))
    payload["images"] = [
        {
            "id": attachment["id"],
            "url": content_url(slug, attachment["id"]),
            "filename": attachment.get("filename"),
            "content_type": attachment.get("content_type"),
            "size": attachment.get("size"),
            "caption": attachment.get("caption"),
        }
        for attachment in version.metadata.get(ATTACHMENTS_KEY, [])
        if attachment.get("evidence_id") == evidence.id and (attachment.get("content_type") or "image/").startswith("image/")
    ]
    return payload


def _find(version: follow.Experiment, evidence_id: str) -> follow.Evidence:
    for evidence in version.evidence:
        if evidence.id == evidence_id:
            return evidence
    raise NotFound("Preuve introuvable sur cette version.", code="evidence_not_found")


def list_evidence(slug: str, experiment_id: str, version_id: str | None = None) -> tuple[follow.Experiment, list[dict]]:
    """``(version, preuves)`` : les preuves de la version ``version_id`` de la piste (sa pointe par
    défaut), dans l'ordre où elles ont été ajoutées."""
    version = experiments.version_of(get_repository(slug), experiment_id, version_id)
    return version, [_payload(slug, version, evidence) for evidence in version.evidence]


def get_evidence(slug: str, experiment_id: str, evidence_id: str, version_id: str | None = None) -> tuple[follow.Experiment, dict]:
    version = experiments.version_of(get_repository(slug), experiment_id, version_id)
    return version, _payload(slug, version, _find(version, evidence_id))


# -- écriture --------------------------------------------------------------------------------------


def clean_links(raw: list[str]) -> list[str]:
    """Les liens d'une preuve tels que tapés ou collés : un par entrée, guillemets autour retirés
    (« Copier en tant que chemin d'accès » de Windows en ajoute), vides et doublons écartés."""
    links: list[str] = []
    for value in raw:
        value = (value or "").strip().strip('"').strip()
        if value and value not in links:
            links.append(value[:1000])
    if len(links) > MAX_EVIDENCE_LINKS:
        raise InvalidInput(f"{MAX_EVIDENCE_LINKS} liens au maximum par preuve.")
    return links


def add(slug: str, experiment_id: str, body: EvidenceInput, *, author: str, expected_version: str | None) -> tuple[follow.Experiment, dict]:
    """Ajoute une preuve à la piste - ``(nouvelle version, la preuve)``. Ses images sont des fichiers
    déjà téléversés dans ce µprojet (:class:`InvalidInput` sinon), rattachés dans la même version."""
    metric = None
    if body.metric_name:
        if body.metric_value is None:
            raise InvalidInput("Une valeur est requise pour la mesure nommée.")
        metric = {body.metric_name: follow.Quantity(value=body.metric_value, unit=body.metric_unit)}
    links = clean_links(body.links)
    if len(body.images) > MAX_EVIDENCE_IMAGES:
        raise InvalidInput(f"{MAX_EVIDENCE_IMAGES} images au maximum par preuve.")
    if len({image.image_id for image in body.images}) != len(body.images):
        raise InvalidInput("La même image figure deux fois.")
    images = [(image, uploaded_image(slug, image.image_id)) for image in body.images]
    source = body.source.strip() or (links[0] if links else "")
    evidence_id = secrets.token_hex(6)
    extra = {"kind": "image" if images else body.kind, "objective": body.objective, "interpretation": body.interpretation}

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        if body.step_index is not None:
            process = parent.metadata.get("structureforge_process")
            steps = process.get("steps", []) if process else []
            if not steps:
                raise InvalidInput("Cette expérience n'a pas de procédé éditable enregistré : impossible d'associer une étape.")
            if not 0 <= body.step_index < len(steps):
                raise InvalidInput("Étape sélectionnée invalide.")
        if body.objective is not None and not any(o.name == body.objective for o in parent.objectives):
            raise InvalidInput(f"Objectif « {body.objective} » introuvable sur cette expérience.")

        if links:
            builder.metadata[EVIDENCE_LINKS_KEY] = {**builder.metadata.get(EVIDENCE_LINKS_KEY, {}), evidence_id: links}
        builder.metadata[EVIDENCE_EXTRA_KEY] = {**builder.metadata.get(EVIDENCE_EXTRA_KEY, {}), evidence_id: extra}
        if images:
            now = datetime.now(timezone.utc).isoformat()
            builder.metadata[ATTACHMENTS_KEY] = list(builder.metadata.get(ATTACHMENTS_KEY, [])) + [
                {
                    "id": image.image_id,
                    "filename": sidecar.get("filename", "image"),
                    "content_type": sidecar.get("content_type"),
                    "size": sidecar.get("size"),
                    "entity_index": None,
                    "evidence_id": evidence_id,
                    "caption": (image.caption or "").strip()[:200] or None,
                    "uploaded_by": author,
                    "uploaded_at": now,
                }
                for image, sidecar in images
            ]
        builder.add_evidence(
            id=evidence_id,
            description=body.description,
            source=source,
            metrics=metric or {},
            step_index=body.step_index,
            **_native_fields(extra),
        )

    version = experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
    return version, _payload(slug, version, _find(version, evidence_id))


def set_annotations(
    slug: str, experiment_id: str, evidence_id: str, annotations: list[AnnotationInput], *, author: str, expected_version: str | None
) -> tuple[follow.Experiment, dict]:
    """Remplace les annotations (flèches, cadres) des images d'une preuve - ``(version, la preuve)`` ;
    chacune désigne l'une de ses images (:class:`InvalidInput` sinon). Les mêmes annotations ne
    créent pas de version."""
    stored = {"image_annotations": [annotation.model_dump() for annotation in annotations]}
    native = _native_fields(stored)

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        _find(parent, evidence_id)
        own_images = {a.get("id") for a in parent.metadata.get(ATTACHMENTS_KEY, []) if a.get("evidence_id") == evidence_id}
        if any(annotation.attachment_id not in own_images for annotation in annotations):
            raise InvalidInput("Image introuvable sur cette preuve.")
        builder.evidence = [e.model_copy(update=native) if native and e.id == evidence_id else e for e in parent.evidence]
        extras = builder.metadata.setdefault(EVIDENCE_EXTRA_KEY, {})
        extras[evidence_id] = {**extras.get(evidence_id, {}), **stored}

    version = experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
    return version, _payload(slug, version, _find(version, evidence_id))
