"""``GET /api/simulation-runs/{run_id}``: where a simulation of the structure builder is at
(:func:`.service.progress`). The simulation itself is ``structures``'s (``POST /api/simulations?run=``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..accounts.deps import current_user
from . import service

router = APIRouter(prefix="/api", tags=["simulation_progress"], dependencies=[Depends(current_user)])


@router.get("/simulation-runs/{run_id}")
def get_simulation_run(run_id: str) -> dict:
    return service.progress(run_id)
