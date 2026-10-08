"""La reprise d'une simulation : chaque état atteint est gardé, et une simulation repart du plus long
début déjà calculé - mêmes images qu'une simulation complète, sans refaire les étapes d'avant."""

from __future__ import annotations

from collections import OrderedDict

import pytest
from pydantic import TypeAdapter
from structureforge.process.steps import ProcessStep

from spectre.plugins.structures import simulation
from support.structures import deposition, etch, substrate

STEPS = [
    deposition("Oxyde", "SiO2", thickness_nm=30),
    etch("Gravure", depth_nm=10),
    deposition("Nitrure", "Si3N4", thickness_nm=20),
]
SPEC = simulation.SubstrateSpec.model_validate(substrate("Si", width_nm=200, thickness_nm=50))


@pytest.fixture
def simulated(monkeypatch) -> list[list[str]]:
    """Les étapes que StructureForge simule vraiment, appel par appel - sur un cache vide."""
    monkeypatch.setattr(simulation, "_checkpoints", OrderedDict())
    calls: list[list[str]] = []
    real = simulation.simulate

    def counting(geometry, steps, materials, recipes):
        calls.append([step.name for step in steps])
        return real(geometry, steps, materials, recipes)

    monkeypatch.setattr(simulation, "simulate", counting)
    return calls


def _steps(raw: list[dict]) -> list[ProcessStep]:
    return TypeAdapter(list[ProcessStep]).validate_python(raw)


def _shape(result: simulation.SimulationResult) -> tuple:
    frames = [
        (f.step_index, f.step_kind, f.step_name, [(l.material, l.polygon.wkb, l.provenance) for l in f.layers])
        for f in result.frames
    ]
    return frames, result.layer_origins, [(l.material, l.polygon.wkb) for l in result.geometry.layers]


def test_the_same_process_again_simulates_nothing_and_gives_the_same_frames(simulated):
    first = simulation.simulate_process(SPEC, _steps(STEPS))
    assert simulated == [[], ["Oxyde"], ["Gravure"], ["Nitrure"]]
    simulated.clear()
    again = simulation.simulate_process(SPEC, _steps(STEPS))
    assert simulated == []
    assert _shape(again) == _shape(first)


def test_an_edited_step_resimulates_from_it_on_like_a_full_simulation(simulated, monkeypatch):
    simulation.simulate_process(SPEC, _steps(STEPS))
    simulated.clear()
    edited = [STEPS[0], etch("Gravure", depth_nm=15), STEPS[2]]
    resumed = simulation.simulate_process(SPEC, _steps(edited))
    assert simulated == [["Gravure"], ["Nitrure"]]
    monkeypatch.setattr(simulation, "_checkpoints", OrderedDict())
    assert _shape(resumed) == _shape(simulation.simulate_process(SPEC, _steps(edited)))


def test_an_added_step_simulates_only_itself(simulated):
    simulation.simulate_process(SPEC, _steps(STEPS))
    simulated.clear()
    result = simulation.simulate_process(SPEC, _steps([*STEPS, deposition("Encore", "SiO2", thickness_nm=5)]))
    assert simulated == [["Encore"]] and len(result.frames) == len(STEPS) + 2


def test_declared_parameters_never_stick_to_the_kept_states(simulated):
    declared = {0: [simulation.DeclaredParam(name="dopage", value=1e19, unit="cm-3")]}
    with_param = simulation.simulate_process(SPEC, _steps(STEPS), declared)
    assert "dopage" in with_param.frames[-1].layers[1].provenance.parameters
    without = simulation.simulate_process(SPEC, _steps(STEPS))
    assert all(l.provenance is None or "dopage" not in l.provenance.parameters for f in without.frames for l in f.layers)


def test_a_changed_recipe_or_substrate_starts_over(simulated):
    own = simulation.ProcessRecipes.model_validate({"etch": [{"name": "Gravure maison", "mode": "isotropic", "default_factor": 1.0}]})
    steps = _steps([STEPS[0], etch("Gravure", recipe="Gravure maison", depth_nm=10)])
    simulation.simulate_process(SPEC, steps, recipes=own)
    simulated.clear()
    slower = simulation.ProcessRecipes.model_validate({"etch": [{"name": "Gravure maison", "mode": "isotropic", "default_factor": 0.5}]})
    simulation.simulate_process(SPEC, steps, recipes=slower)
    assert simulated == [[], ["Oxyde"], ["Gravure"]]
    simulated.clear()
    wider = simulation.SubstrateSpec.model_validate(substrate("Si", width_nm=300, thickness_nm=50))
    simulation.simulate_process(wider, steps, recipes=own)
    assert simulated == [[], ["Oxyde"], ["Gravure"]]


def test_only_the_latest_states_are_kept(simulated, monkeypatch):
    monkeypatch.setattr(simulation, "MAX_CHECKPOINTS", 3)
    simulation.simulate_process(SPEC, _steps(STEPS))
    assert len(simulation._checkpoints) == 3
    simulated.clear()
    # le départ est le plus ancien : oublié, tout est refait
    simulation.simulate_process(SPEC, _steps(STEPS))
    assert simulated == [[], ["Oxyde"], ["Gravure"], ["Nitrure"]]
