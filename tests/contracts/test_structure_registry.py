"""Les clés de registre Follow de ProcessLot et StructureImage sont figées : Follow les persiste dans
``structure_type`` de chaque expérience (et les hache dans son id), puis s'en sert pour retrouver la
classe au rechargement. Déplacer ces classes - vers un plugin - ne doit rendre illisible aucun dépôt
existant."""

from __future__ import annotations

import json

import follow
from follow.core import structure as follow_structure
from structureforge.adapters.follow_adapter import ProcessStructure

from spectre.plugins.experiments.repository import follow_repo_path, get_repository
from spectre.plugins.structures.kinds import PROCESS_LOT_KEY, STRUCTURE_IMAGE_KEY, ProcessLot, StructureImage

from support.experiments import launch_campaign
from support.microprojects import signup_with_microproject


def test_the_registry_keys_are_the_historical_strings():
    assert PROCESS_LOT_KEY == "spectre.core.structures.ProcessLot"
    assert STRUCTURE_IMAGE_KEY == "spectre.core.structures.StructureImage"
    assert ProcessLot.registry_key() == PROCESS_LOT_KEY
    assert StructureImage.registry_key() == STRUCTURE_IMAGE_KEY
    assert follow.Structure.resolve(PROCESS_LOT_KEY) is ProcessLot
    assert follow.Structure.resolve(STRUCTURE_IMAGE_KEY) is StructureImage


def test_a_stored_campaign_reloads_through_a_class_defined_elsewhere(client, monkeypatch):
    slug = signup_with_microproject(client, "registry@example.com")
    campaign = launch_campaign(client, slug)

    stored = json.loads((follow_repo_path(slug) / "objects" / f"{campaign['id']}.json").read_text(encoding="utf-8"))
    assert stored["structure_type"] == PROCESS_LOT_KEY

    # the same structure, as a plugin would define it from another module: registered under the
    # same frozen key (the original is put back after the test)
    monkeypatch.setitem(follow_structure._REGISTRY, PROCESS_LOT_KEY, ProcessLot)

    class MovedProcessLot(follow.Structure):
        entries: list[ProcessStructure]

        @classmethod
        def registry_key(cls) -> str:
            return PROCESS_LOT_KEY

    assert MovedProcessLot.__module__ != ProcessLot.__module__
    repo = get_repository(slug)
    reloaded = repo.load_structure(repo.get(campaign["id"]))
    assert isinstance(reloaded, MovedProcessLot) and len(reloaded.entries) == 3
