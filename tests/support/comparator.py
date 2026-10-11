"""Comparateur de structures (plugin comparator) : le tableau d'une liste de jetons et les
suggestions d'une saisie. Chaque aide encapsule une route et vérifie son code de succès."""

from __future__ import annotations

from typing import Any

from .http import assert_ok


def get_comparison(client: Any, *items: str, baseline: int | None = None) -> Any:
    """GET /api/comparisons, tel quel (la réponse, pour en vérifier un refus)."""
    params: dict[str, Any] = {"item": list(items)}
    if baseline is not None:
        params["baseline"] = baseline
    return client.get("/api/comparisons", params=params)


def compare(client: Any, *items: str, baseline: int | None = None) -> dict:
    return assert_ok(get_comparison(client, *items, baseline=baseline))


def candidates(client: Any, q: str) -> list[dict]:
    return assert_ok(client.get("/api/comparison-candidates", params={"q": q}))


def column(table: dict, group_label: str, column_label: str) -> int:
    """La position (dans les cellules d'une ligne) de la colonne ``column_label`` de l'étape
    ``group_label``."""
    start = 0
    for group in table["groups"]:
        for offset, col in enumerate(group["columns"]):
            if group["label"] == group_label and col["label"] == column_label:
                return start + offset
        start += len(group["columns"])
    raise AssertionError(f"pas de colonne {column_label!r} sous {group_label!r} : {[g['label'] for g in table['groups']]}")


def cell(table: dict, row: int, group_label: str, column_label: str) -> dict:
    return table["rows"][row]["cells"][column(table, group_label, column_label)]


def group(table: dict, label: str) -> dict:
    return next(g for g in table["groups"] if g["label"] == label)
