"""API des types de données de caractérisation (voir :mod:`.service`) : le catalogue, la fiche
d'un type, une requête pour voir ce qu'elle renvoie, et ses graphiques documentaires en PNG. Page
associée : /donnees (``pages/data-types.html``)."""

from __future__ import annotations

from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel

from ..accounts.deps import current_user
from . import service
from .source import DataType

PREFIX = "/api/characterization"

router = APIRouter(prefix=PREFIX, tags=["characterization"], dependencies=[Depends(current_user)])


def _chart_url(key: str, chart_key: str) -> str:
    return f"{PREFIX}/data-types/{quote(key, safe='')}/charts/{quote(chart_key, safe='')}"


def _detail(data_type: DataType) -> dict[str, Any]:
    return {
        **data_type.summary(),
        "parameters": list(data_type.parameters),
        "cacheable": data_type.cacheable,
        "postprocessing": list(data_type.postprocessing),
        "raw_columns": list(data_type.raw_columns),
        "kpi_columns": list(data_type.kpi_columns),
        "example_rows": list(data_type.example_rows),
        "charts": [{**c, "url": _chart_url(data_type.key, c["key"])} for c in data_type.charts],
    }


@router.get("/data-types")
def list_data_types(
    category: str | None = None,
    status: Literal["implemented", "planned"] | None = None,
    by_wafer: bool | None = None,
) -> list[dict[str, Any]]:
    return [t.summary() for t in service.list_types(category=category, status=status, by_wafer=by_wafer)]


@router.get("/categories")
def list_categories() -> list[dict[str, Any]]:
    return [{"name": name, "data_types": [t.summary() for t in types]} for name, types in service.categories()]


@router.get("/data-types/{data_type_key}")
def get_data_type(data_type_key: str) -> dict[str, Any]:
    return _detail(service.describe(data_type_key))


class QueryRequest(BaseModel):
    # Un paramètre est toujours une liste de chaînes à ce jour (wafer_names...) : chaque type
    # déclare son propre jeu de paramètres.
    parameters: dict[str, list[str]] = {}
    # Ignore le cache par plaque et retape la base (une mesure refaite depuis).
    refresh: bool = False


@router.post("/data-types/{data_type_key}/queries")
def run_query(data_type_key: str, body: QueryRequest) -> dict[str, Any]:
    result = service.query(data_type_key, body.parameters, refresh=body.refresh)
    return {
        "source": result.source,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": len(result.rows),
        "wafers": result.wafers,
        "from_cache": result.from_cache,
        "fetched": result.fetched,
    }


@router.get("/data-types/{data_type_key}/charts/{chart_key}")
def get_chart(data_type_key: str, chart_key: str) -> Response:
    return Response(content=service.chart(data_type_key, chart_key), media_type="image/png")
