"""The progress of a simulation, as the builder's loading bar reads it - noted by
:mod:`spectre.plugins.structures.simulation` while it runs, under the identifier the page gave it."""

from __future__ import annotations

from typing import Any

from ...kernel.errors import NotFound
from ..structures import simulation


def progress(run_id: str) -> dict[str, Any]:
    """``state`` (``running``, ``done`` or ``failed``), ``total`` steps, ``done`` so far - ``resumed``
    of them taken from a state kept by an earlier simulation, so not computed this time - the step
    running now (``step``: its ``index`` from 0 and ``name``, ``None`` between two steps or when
    over) and the seconds ``elapsed``. :class:`NotFound` for a simulation that has not started yet
    or whose trace is already forgotten."""
    run = simulation.run_progress(run_id) if simulation.RUN_ID_RE.fullmatch(run_id) else None
    if run is None:
        raise NotFound("Simulation inconnue : elle n'est pas encore partie, ou son suivi est déjà oublié.", code="simulation_run_not_found")
    step = {"index": run.step_index, "name": run.step_name} if run.step_index is not None else None
    return {
        "state": run.state,
        "total": run.total,
        "done": run.done,
        "resumed": run.resumed,
        "step": step,
        "elapsed": round(run.elapsed, 2),
    }
