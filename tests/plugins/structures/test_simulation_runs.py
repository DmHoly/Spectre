"""Le suivi d'une simulation : sous l'identifiant que lui donne la requête, chaque étape terminée est
notée - ce que la barre de chargement du constructeur (plugin ``simulation_progress``) lit. Sans
identifiant, rien n'est noté ; ce qui est calculé ne change pas."""

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


def _steps(raw: list[dict]) -> list[ProcessStep]:
    return TypeAdapter(list[ProcessStep]).validate_python(raw)


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    monkeypatch.setattr(simulation, "_checkpoints", OrderedDict())
    monkeypatch.setattr(simulation, "_runs", OrderedDict())


def test_a_followed_simulation_ends_done_with_every_step_counted():
    simulation.simulate_process(SPEC, _steps(STEPS), run_id="run-0000-aaaa")
    run = simulation.run_progress("run-0000-aaaa")
    assert (run.state, run.total, run.done, run.resumed) == ("done", 3, 3, 0)
    assert (run.step_index, run.step_name) == (None, None)
    assert run.ended is not None and run.elapsed >= 0


def test_each_step_is_noted_as_it_starts_with_the_ones_before_it_done(monkeypatch):
    seen: list[tuple[int, int | None, str | None]] = []
    real = simulation.simulate

    def watching(geometry, steps, materials, recipes):
        run = simulation.run_progress("run-0000-bbbb")
        seen.append((run.done, run.step_index, run.step_name))
        return real(geometry, steps, materials, recipes)

    monkeypatch.setattr(simulation, "simulate", watching)
    simulation.simulate_process(SPEC, _steps(STEPS), run_id="run-0000-bbbb")
    # le substrat d'abord (aucune étape faite), puis une étape à la fois, celles d'avant comptées faites
    assert seen == [(0, None, None), (0, 0, "Oxyde"), (1, 1, "Gravure"), (2, 2, "Nitrure")]


def test_steps_kept_by_an_earlier_simulation_count_as_resumed():
    simulation.simulate_process(SPEC, _steps(STEPS))
    edited = [STEPS[0], STEPS[1], deposition("Nitrure", "Si3N4", thickness_nm=25)]
    simulation.simulate_process(SPEC, _steps(edited), run_id="run-0000-cccc")
    run = simulation.run_progress("run-0000-cccc")
    assert (run.state, run.total, run.done, run.resumed) == ("done", 3, 3, 2)


def test_a_simulation_that_fails_is_noted_failed():
    broken = [STEPS[0], deposition("Absurde", "Unobtainium", thickness_nm=10)]
    with pytest.raises(simulation.SimulationFailedError):
        simulation.simulate_process(SPEC, _steps(broken), run_id="run-0000-dddd")
    run = simulation.run_progress("run-0000-dddd")
    assert (run.state, run.done, run.total) == ("failed", 1, 2)


def test_a_simulation_without_an_id_leaves_no_trace():
    simulation.simulate_process(SPEC, _steps(STEPS))
    assert not simulation._runs


def test_only_the_last_runs_are_kept(monkeypatch):
    monkeypatch.setattr(simulation, "MAX_TRACKED_RUNS", 2)
    for name in ("run-0000-eeee", "run-0000-ffff", "run-0000-gggg"):
        simulation.simulate_process(SPEC, _steps(STEPS[:1]), run_id=name)
    assert simulation.run_progress("run-0000-eeee") is None
    assert simulation.run_progress("run-0000-gggg").state == "done"


def test_an_unknown_run_has_no_progress():
    assert simulation.run_progress("run-0000-hhhh") is None
