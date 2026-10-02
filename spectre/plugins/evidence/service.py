"""Les champs d'une preuve propres à Spectre, et la preuve telle que l'API la montre."""

from __future__ import annotations

import copy
from typing import Any

import follow

# Les champs de preuve propres à Spectre (type de preuve, objectif servi, interprétation, réglages du
# graphe, annotations d'image) : rangés dans Experiment.metadata[EVIDENCE_EXTRA_KEY][evidence_id]
# plutôt que sur follow.Evidence, dont les champs dépendent de la version de Follow installée (une
# version qui ne les déclare pas les ignore sans rien dire) - la même raison que pour
# metadata["evidence_links"]. Chaque évolution légère recopie metadata, donc ils suivent les preuves.
EVIDENCE_EXTRA_KEY = "evidence_extra"
EVIDENCE_EXTRA_DEFAULTS: dict[str, Any] = {
    "kind": "standard",
    "objective": None,
    "interpretation": None,
    "graph_config": None,
    "image_annotations": [],
}


def native_evidence_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Those of ``fields`` the installed ``follow.Evidence`` declares itself - passed to it too, so
    a Follow that carries them natively keeps them in sync with the metadata copy."""
    return {name: value for name, value in fields.items() if name in follow.Evidence.model_fields}


def evidence_payload(evidence: Any, extras: dict[str, dict[str, Any]]) -> dict:
    """One preuve as the API shows it: Follow's own fields, plus Spectre's (see
    :data:`EVIDENCE_EXTRA_KEY`) - read from the preuve itself when the installed Follow declares
    the field and it was actually set there, otherwise from ``extras`` (the experience's
    ``metadata[EVIDENCE_EXTRA_KEY]``), otherwise their default."""
    payload = evidence.model_dump(mode="json")
    stored = extras.get(evidence.id, {})
    for name, default in EVIDENCE_EXTRA_DEFAULTS.items():
        if name in follow.Evidence.model_fields and name in evidence.model_fields_set:
            continue
        payload[name] = stored.get(name, copy.deepcopy(default))
    return payload
