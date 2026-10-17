"""Les analyses de plaques : une question posée à quelques plaques, quelle que soit l'étude qui les suit -
une plaque de référence et celles qu'on lui compare -, et ce qu'on en a conclu. L'analyse ne garde que
son cadre (titre, question, plaques, conclusion, KPI comparés et blocs libres) : structures, contexte et données se relisent à chaque
ouverture chez les plugins qui les possèdent, et ce que chaque plaque a appris s'écrit dans ses notes
(plugin wafers), qui la suivent sur sa page.

Comme les notes d'une plaque, une analyse se lit et s'écrit par tout compte connecté (qui et quand sont
gardés) ; la supprimer revient à son auteur ou à un administrateur.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from ...kernel.db import get_conn
from ...kernel.errors import Forbidden, InvalidInput, NotFound
from ..accounts.service import User
from ..kpi_tracking import service as kpi_tracking
from ..wafer_data import blocks as wafer_blocks
from ..wafers.service import wafer_key

MAX_TITLE = 160
MAX_TEXT = 8000
MAX_LASERMARK = 80
# Les plaques d'une analyse se montrent côte à côte : au-delà, ni les structures ni les boîtes ne se lisent.
MAX_WAFERS = 16
MAX_KPIS = 12  # une boîte à moustaches chacun
MAX_BLOCKS = 12  # les blocs libres : une figure par plaque chacun
BETTER = ("high", "low")  # le sens d'un écart à la référence qui est un progrès


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _title(value: str | None) -> str:
    title = " ".join((value or "").split())[:MAX_TITLE]
    if not title:
        raise InvalidInput("Donnez un titre à l'analyse.", code="missing_title")
    return title


def _text(value: str | None) -> str:
    return (value or "").strip()[:MAX_TEXT]


def _wafers(lasermarks: Iterable[str]) -> list[tuple[str, str]]:
    """``(clé, lasermark)`` de chaque plaque, dans l'ordre donné, sans doublon (deux écritures d'une même
    plaque n'en font qu'une) ; la première est la référence."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in lasermarks:
        lasermark = " ".join(str(raw or "").split())[:MAX_LASERMARK]
        key = wafer_key(lasermark)
        if key and key not in seen:
            seen.add(key)
            found.append((key, lasermark))
    if not found:
        raise InvalidInput("Choisissez au moins la plaque de référence.", code="no_wafers")
    if len(found) > MAX_WAFERS:
        raise InvalidInput(f"Une analyse compare {MAX_WAFERS} plaques au plus.", code="too_many_wafers")
    return found


def kpi_title(kpi: dict[str, Any]) -> str:
    """Le nom d'un KPI de l'analyse : celui qu'on lui a donné, sinon sa colonne suivie de ses filtres."""
    if kpi["label"]:
        return kpi["label"]
    filters = " · ".join(kpi_tracking.describe_filter(f) for f in kpi["filters"])
    return f"{kpi['column']} ({filters})" if filters else kpi["column"]


def column_catalog() -> dict[str, dict[str, Any]]:
    """Toute donnée de PRISM qu'une analyse peut comparer comme un KPI, par ``hook:colonne`` : ``{entry, type,
    sure}``. Les colonnes de KPI des types de données par plaque d'abord, puis leurs colonnes brutes et celles que la
    fiche data (wafer_data) a vues dans les vraies lignes - avec leur type (``sure`` : choisi ou observé). ``entry`` est un :class:`kpi_tracking.CatalogKpi` (filtres, unité, titre du type)."""
    found: dict[str, dict[str, Any]] = {k.key: {"entry": k, "type": None, "sure": False} for k in kpi_tracking.catalog(all_columns=True)}
    for hook in wafer_blocks.catalog():
        for column in hook.columns:
            key = f"{hook.hook}:{column['name']}"
            if key not in found:
                if column["name"].lower() in kpi_tracking.NOT_A_KPI:
                    continue
                entry = kpi_tracking.CatalogKpi(hook.hook, column["name"], hook.title, column["unit"], column["description"], hook.names, kpi=False)
                found[key] = {"entry": entry, "type": None, "sure": False}
            found[key].update(type=column["type"], sure=column["sure"])
    return found


def clean_kpis(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les KPI de l'analyse, vérifiés : une colonne d'un type de données PRISM par plaque (:func:`column_catalog`,
    422 ``unknown_kpi`` ; ``not_a_number`` pour une colonne brute qu'on sait n'être pas un scalaire), ses filtres au
    vocabulaire des KPI suivis (:func:`kpi_tracking.clean_filters`), un nom libre, un sens de progrès ; un même KPI
    aux mêmes filtres n'entre qu'une fois."""
    if len(values) > MAX_KPIS:
        raise InvalidInput(f"Une analyse compare {MAX_KPIS} KPI au plus.", code="too_many_kpis")
    catalogue = column_catalog() if values else {}
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values:
        hook, column = str(raw.get("hook") or ""), str(raw.get("column") or "")
        found = catalogue.get(f"{hook}:{column}")
        if found is None:
            raise InvalidInput(f"« {column} » n'est pas une colonne de « {hook} » dans le catalogue PRISM.", code="unknown_kpi")
        if found["sure"] and found["type"] != "number" and not found["entry"].kpi:
            raise InvalidInput(f"« {column} » n'est pas un scalaire : montrez-la dans un bloc libre (courbes, images…).", code="not_a_number")
        filters = kpi_tracking.clean_filters(found["entry"], raw.get("filters"))
        signature = json.dumps([hook, column, filters], sort_keys=True)
        if signature in seen:
            continue
        seen.add(signature)
        better = raw.get("better")
        cleaned.append(
            {
                "hook": hook,
                "column": column,
                "label": " ".join(str(raw.get("label") or "").split())[: kpi_tracking.MAX_LABEL],
                "filters": filters,
                "better": better if better in BETTER else None,
            }
        )
    return cleaned


def clean_blocks(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les blocs libres de l'analyse - comme ceux de la fiche data d'un projet (:mod:`wafer_data.blocks`, mêmes
    genres, mêmes vérifications : 422 ``unknown_hook``, ``wrong_column_type``...) mais choisis ici, sur n'importe
    quel type de données PRISM par plaque."""
    if len(values) > MAX_BLOCKS:
        raise InvalidInput(f"Une analyse montre {MAX_BLOCKS} blocs libres au plus.", code="too_many_blocks")
    cleaned = []
    for raw in values:
        kind = str(raw.get("kind") or "")
        hook, config = wafer_blocks.clean_config(kind, str(raw.get("hook") or ""), raw.get("config"))
        label = " ".join(str(raw.get("label") or "").split())[: wafer_blocks.MAX_LABEL]
        cleaned.append({"kind": kind, "hook": hook, "config": config, "label": label})
    return cleaned


def _blocks(raw: str) -> list[dict[str, Any]]:
    """Les blocs libres gardés, avec leur nom (celui qu'on leur a donné, sinon ce qu'ils montrent) et leur genre."""
    return [
        {
            **b,
            "title": wafer_blocks.Block(i, wafer_blocks.FREE_AREA, b["kind"], b["hook"], b["config"], b["label"], i, "").title,
            "kind_label": wafer_blocks.KINDS.get(b["kind"], b["kind"]),
        }
        for i, b in enumerate(json.loads(raw or "[]"))
    ]


def _members(conn: Any, ids: list[int]) -> dict[int, list[dict[str, str]]]:
    members: dict[int, list[dict[str, str]]] = {i: [] for i in ids}
    if not ids:
        return members
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT analysis_id, wafer_key, lasermark FROM wafer_analysis_wafers WHERE analysis_id IN ({marks}) ORDER BY analysis_id, position",
        ids,
    ).fetchall()
    for row in rows:
        members[row["analysis_id"]].append({"key": row["wafer_key"], "lasermark": row["lasermark"]})
    return members


def _payload(row: Any, wafers: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "question": row["question"],
        "conclusion": row["conclusion"],
        "kpis": [{**kpi, "title": kpi_title(kpi)} for kpi in json.loads(row["kpis"])],
        "blocks": _blocks(row["blocks"]),
        "reference": wafers[0] if wafers else None,
        "wafers": wafers,  # la référence d'abord
        "created_by": row["created_by"],
        "created_by_id": row["created_by_id"],
        "created_at": row["created_at"],
        "updated_by": row["updated_by"],
        "updated_by_id": row["updated_by_id"],
        "updated_at": row["updated_at"],
    }


def _write_wafers(conn: Any, analysis_id: int, wafers: list[tuple[str, str]]) -> None:
    conn.execute("DELETE FROM wafer_analysis_wafers WHERE analysis_id = ?", (analysis_id,))
    conn.executemany(
        "INSERT INTO wafer_analysis_wafers (analysis_id, wafer_key, lasermark, position) VALUES (?, ?, ?, ?)",
        [(analysis_id, key, lasermark, position) for position, (key, lasermark) in enumerate(wafers)],
    )


def get(analysis_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM wafer_analyses WHERE id = ?", (analysis_id,)).fetchone()
        if row is None:
            raise NotFound("Cette analyse n'existe pas (ou plus).", code="analysis_not_found")
        return _payload(row, _members(conn, [analysis_id])[analysis_id])


def list_all(wafer: str | None = None) -> list[dict[str, Any]]:
    """Toutes les analyses, la plus récemment modifiée d'abord - ou celles où paraît la plaque ``wafer``
    (un lasermark ou une clé)."""
    with get_conn() as conn:
        if wafer is not None:
            rows = conn.execute(
                """SELECT a.* FROM wafer_analyses a JOIN wafer_analysis_wafers w ON w.analysis_id = a.id
                   WHERE w.wafer_key = ? ORDER BY a.updated_at DESC, a.id DESC""",
                (wafer_key(wafer),),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM wafer_analyses ORDER BY updated_at DESC, id DESC").fetchall()
        members = _members(conn, [row["id"] for row in rows])
    return [_payload(row, members[row["id"]]) for row in rows]


def create(user: User, title: str, lasermarks: Iterable[str], question: str | None = None) -> dict[str, Any]:
    clean_title, wafers = _title(title), _wafers(lasermarks)
    now = _now()
    with get_conn() as conn:
        cursor = conn.execute(
            """INSERT INTO wafer_analyses (title, question, conclusion, created_by, created_by_id, created_at, updated_by, updated_by_id, updated_at)
               VALUES (?, ?, '', ?, ?, ?, ?, ?, ?)""",
            (clean_title, _text(question), user.name, user.id, now, user.name, user.id, now),
        )
        analysis_id = int(cursor.lastrowid)
        _write_wafers(conn, analysis_id, wafers)
    return get(analysis_id)


def update(user: User, analysis_id: int, values: dict[str, Any]) -> dict[str, Any]:
    """Change ce que ``values`` donne : ``title``, ``question``, ``conclusion``, ``wafers`` (toutes les plaques,
    dans l'ordre : la première est la référence), ``kpis`` (tous les KPI comparés, dans l'ordre) et ``blocks``
    (tous les blocs libres, dans l'ordre)."""
    get(analysis_id)  # 404 avant toute validation
    fields: dict[str, str] = {}
    if "title" in values:
        fields["title"] = _title(values["title"])
    for name in ("question", "conclusion"):
        if name in values:
            fields[name] = _text(values[name])
    if values.get("kpis") is not None:
        fields["kpis"] = json.dumps(clean_kpis(values["kpis"]))
    if values.get("blocks") is not None:
        fields["blocks"] = json.dumps(clean_blocks(values["blocks"]), ensure_ascii=False)
    wafers = _wafers(values["wafers"]) if values.get("wafers") is not None else None
    with get_conn() as conn:
        fields.update(updated_by=user.name, updated_by_id=user.id, updated_at=_now())
        assignments = ", ".join(f"{name} = ?" for name in fields)
        conn.execute(f"UPDATE wafer_analyses SET {assignments} WHERE id = ?", (*fields.values(), analysis_id))
        if wafers is not None:
            _write_wafers(conn, analysis_id, wafers)
    return get(analysis_id)


def delete(user: User, analysis_id: int) -> None:
    analysis = get(analysis_id)
    if not user.is_admin and analysis["created_by_id"] != user.id:
        raise Forbidden("Seul l'auteur de l'analyse, ou un administrateur, peut la supprimer.", code="not_analysis_author")
    with get_conn() as conn:
        conn.execute("DELETE FROM wafer_analyses WHERE id = ?", (analysis_id,))
