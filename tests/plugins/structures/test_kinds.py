"""Les types de structure (spectre.plugins.structures.kinds) : chacun trouvé par la clé que Follow a
persistée, et les charges utiles d'une structure (spectre.plugins.structures.schemas), distinguées
par ``kind``."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError
from structureforge.adapters.follow_adapter import ProcessStructure, to_structure

from spectre.plugins.structures import kinds
from spectre.plugins.structures.schemas import CampaignPayload, ImagesPayload, ProcessPayload, StructurePayload
from spectre.plugins.structures.simulation import run_simulation
from support.structures import campaign_plan, steps, substrate


def _process_structure() -> dict:
    process = ProcessPayload.model_validate({"kind": "process", "substrate": substrate(), "steps": steps()})
    geometry, _frames, _materials = run_simulation(process.substrate, process.steps)
    return to_structure(geometry).model_dump(mode="json")


def test_kinds_are_found_by_their_frozen_registry_key():
    assert kinds.KINDS == {
        ProcessStructure.registry_key(): kinds.PROCESS,
        "spectre.core.structures.ProcessLot": kinds.CAMPAIGN,
        "spectre.core.structures.StructureImage": kinds.IMAGES,
    }


def test_each_kind_draws_and_counts_its_entities(data_dir):
    process = _process_structure()
    assert kinds.entity_count(kinds.PROCESS.key, process) == 1
    assert "<svg" in kinds.render_structure_svg(kinds.PROCESS.key, process)

    lot = {"entries": [process, process, process]}
    assert kinds.entity_count(kinds.CAMPAIGN.key, lot) == 3
    assert kinds.render_structure_svg(kinds.CAMPAIGN.key, lot) == kinds.render_structure_svg(kinds.PROCESS.key, process)
    assert kinds.render_structure_svg(kinds.CAMPAIGN.key, {"entries": []}) is None

    images = {"images": [{"image_id": "att_" + "0" * 20, "kind": "coupe", "caption": None}]}
    assert kinds.entity_count(kinds.IMAGES.key, images) == 1
    assert kinds.render_structure_svg(kinds.IMAGES.key, images) is None
    assert kinds.is_image_structure(kinds.IMAGES.key) and not kinds.is_image_structure(kinds.PROCESS.key)

    # un type inconnu : rien à dessiner, une entité
    assert kinds.render_structure_svg("ailleurs.Structure", {}) is None
    assert kinds.entity_count("ailleurs.Structure", {}) == 1


def test_a_structure_payload_is_told_apart_by_its_kind():
    adapter = TypeAdapter(StructurePayload)
    process = adapter.validate_python({"kind": "process", "substrate": substrate(), "steps": steps()})
    assert isinstance(process, ProcessPayload) and process.declared_params == {}
    images = adapter.validate_python({"kind": "images", "images": [{"image_id": "att_" + "1" * 20}]})
    assert isinstance(images, ImagesPayload) and images.images[0].kind == "schema"
    campaign = adapter.validate_python({"kind": "campaign", "substrate": substrate(), "steps": steps(), "plan": campaign_plan([10, 20])})
    assert isinstance(campaign, CampaignPayload) and campaign.plan.factors[0].values == [10, 20]

    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "sketch", "images": []})
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "campaign", "substrate": substrate(), "steps": steps()})  # sans plan
