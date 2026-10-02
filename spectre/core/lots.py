"""Suivi de lots : un lot de fabrication, c'est une liste de wafers (par lasermark - le ``sample_id``
de ``Experiment.metadata["physical_tracking"]``, voir :mod:`spectre.core.plates`) avec sa priorité
(P10, P20... - la plus petite passe d'abord), son début, sa fin prévisionnelle et sa fin déclarée.

Tout est **déclaratif** pour l'instant (``source = "declaratif"``) : les dates, la priorité et les
wafers sont saisis à la main ; des datahooks PRISM (base de production) les alimenteront ensuite.
Pas de parcours d'étapes : trop lourd à tenir à la main.

Ce module ne stocke **ni expériences ni µprojets** : les expériences d'un lot sont toutes celles qui
suivent un de ses wafers - dès qu'un wafer entre dans un lot, ses expériences y sont rattachées, même
terminées avant (une épitaxie finie, puis un lot de fabrication lancé pour en avoir la mesure
électro-optique) ; ses thématiques sont celles de leurs µprojets, plus celles déclarées « visées » à
la main, utiles avant qu'une expérience n'existe - voir :mod:`spectre.api.lots`. Un lot
est visible de tout utilisateur connecté, comme les projets corporate ; chacun peut en créer et le
mettre à jour.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date

from .db import get_conn
from .plates import compact

STATUSES = ("planned", "wip", "hold", "done", "cancelled")
ACTIVE_STATUSES = {"planned", "wip", "hold"}  # pas encore sorti (ni annulé)
PRIORITIES = ("P10", "P20", "P30", "P40", "P50")  # suggestions - toute valeur courte est acceptée
MAX_WAFERS = 200

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-.]{0,39}$")  # il sert d'adresse : /lots/{code}
_PRIORITY_RE = re.compile(r"^[A-Za-z0-9 _\-]{0,10}$")


class LotNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Lot:
    id: int
    code: str
    title: str
    description: str
    priority: str  # « P10 » (la plus urgente) ... ; '' = pas encore donnée
    status: str
    started_on: str | None  # début (YYYY-MM-DD)
    forecast_exit_on: str | None  # fin prévisionnelle
    exited_on: str | None  # fin déclarée - le lot est alors « sorti »
    hold_reason: str
    source: str
    created_by: int | None
    created_at: str
    updated_at: str


def _lot_from_row(row: sqlite3.Row) -> Lot:
    return Lot(
        id=row["id"],
        code=row["code"],
        title=row["title"],
        description=row["description"],
        priority=row["priority"],
        status=row["status"],
        started_on=row["started_on"],
        forecast_exit_on=row["forecast_exit_on"],
        exited_on=row["exited_on"],
        hold_reason=row["hold_reason"],
        source=row["source"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def priority_rank(priority: str) -> tuple[int, str]:
    """Pour trier : P10 avant P20 avant P100 ; sans priorité, à la fin."""
    match = re.search(r"\d+", priority or "")
    return (int(match.group()) if match else 10**6, (priority or "").upper())


def _check_date(value: str | None, label: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"{label} : date invalide « {value} » (attendu AAAA-MM-JJ)") from exc


def _check_code(code: str) -> str:
    code = " ".join((code or "").split())
    if not _CODE_RE.match(code):
        raise ValueError("le code du lot doit faire 1 à 40 caractères (lettres, chiffres, espace, - _ .)")
    return code


def _check_priority(priority: str | None) -> str:
    priority = " ".join((priority or "").split()).upper()
    if not _PRIORITY_RE.match(priority):
        raise ValueError("la priorité est un code court (ex : P10), 10 caractères au plus")
    return priority


def _check_dates(started: str | None, forecast: str | None, exited: str | None) -> None:
    if started and forecast and forecast < started:
        raise ValueError("la fin prévisionnelle est avant le début du lot")
    if started and exited and exited < started:
        raise ValueError("la fin déclarée est avant le début du lot")


def parse_lasermarks(text: str | list[str]) -> list[str]:
    """Des lasermarks collés tels quels (une colonne Excel, « W12-A3, W12-A4 »...) - dans l'ordre,
    sans doublon (même règle de comparaison que l'index des plaques)."""
    items = text if isinstance(text, list) else re.split(r"[\s,;]+", text or "")
    seen: set[str] = set()
    result = []
    for item in items:
        item = (item or "").strip()
        key = compact(item)
        if key and key not in seen:
            seen.add(key)
            result.append(item[:60])
    return result


def _touch(conn: sqlite3.Connection, lot_id: int) -> None:
    conn.execute("UPDATE lots SET updated_at = datetime('now') WHERE id = ?", (lot_id,))


def _next_code(conn: sqlite3.Connection) -> str:
    n = conn.execute("SELECT COUNT(*) AS n FROM lots").fetchone()["n"] + 1
    while conn.execute("SELECT 1 FROM lots WHERE code = ? COLLATE NOCASE", (f"LOT-{n:04d}",)).fetchone():
        n += 1
    return f"LOT-{n:04d}"


# --- lecture --------------------------------------------------------------------------------


def list_all(statuses: set[str] | None = None) -> list[Lot]:
    """Les lots par priorité (P10 d'abord), puis par fin prévisionnelle (ou seulement ceux de
    ``statuses``)."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM lots").fetchall()
    lots = [_lot_from_row(row) for row in rows if statuses is None or row["status"] in statuses]
    return sorted(lots, key=lambda lot: (priority_rank(lot.priority), lot.forecast_exit_on or "9999", lot.code))


def get_by_code(code: str) -> Lot:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM lots WHERE code = ? COLLATE NOCASE", ((code or "").strip(),)).fetchone()
    if row is None:
        raise LotNotFoundError(code)
    return _lot_from_row(row)


def get_by_id(lot_id: int) -> Lot:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()
    if row is None:
        raise LotNotFoundError(str(lot_id))
    return _lot_from_row(row)


def list_wafers(lot_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT lasermark FROM lot_wafers WHERE lot_id = ? ORDER BY position", (lot_id,)).fetchall()
    return [row["lasermark"] for row in rows]


def declared_thematic_ids(lot_id: int) -> list[int]:
    with get_conn() as conn:
        rows = conn.execute("SELECT thematic_id FROM lot_thematics WHERE lot_id = ? ORDER BY thematic_id", (lot_id,)).fetchall()
    return [row["thematic_id"] for row in rows]


def lots_by_wafer() -> dict[str, list[dict]]:
    """Lasermark comparé (:func:`spectre.core.plates.compact`) -> les lots qui le contiennent
    (``{"code", "title", "status", "priority"}``, le plus récent d'abord) - pour marquer
    d'un badge les expériences d'un µprojet qui suivent un wafer d'un lot."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT lot_wafers.lasermark_key, lots.code, lots.title, lots.status, lots.priority "
            "FROM lot_wafers JOIN lots ON lots.id = lot_wafers.lot_id ORDER BY lots.created_at DESC, lots.id DESC"
        ).fetchall()
    index: dict[str, list[dict]] = {}
    for row in rows:
        index.setdefault(row["lasermark_key"], []).append(
            {
                "code": row["code"],
                "title": row["title"],
                "status": row["status"],
                "priority": row["priority"],
            }
        )
    return index


def lots_for_lasermarks(lasermarks, index: dict[str, list[dict]] | None = None) -> list[dict]:
    """Les lots (sans doublon) qui contiennent au moins un de ces wafers - ceux d'une expérience
    qui suit ces wafers, quelle que soit sa date."""
    index = lots_by_wafer() if index is None else index
    seen: set[str] = set()
    found = []
    for lasermark in lasermarks:
        for lot in index.get(compact(lasermark), []):
            if lot["code"] in seen:
                continue
            seen.add(lot["code"])
            found.append(lot)
    return found


def search(query: str, *, limit: int = 6) -> list[dict]:
    """Les lots dont le code ou l'intitulé correspond à ``query`` (le code exact d'abord), puis ceux
    qui contiennent un wafer dont le lasermark correspond - ``wafer`` dit lequel."""
    wanted = compact(query)
    words = (query or "").lower().split()
    if len(wanted) < 2:
        return []
    with get_conn() as conn:
        lots = [_lot_from_row(row) for row in conn.execute("SELECT * FROM lots").fetchall()]
        wafer_rows = conn.execute("SELECT lot_id, lasermark, lasermark_key FROM lot_wafers").fetchall()
    scored: dict[int, tuple] = {}
    for lot in lots:
        code = compact(lot.code)
        if code == wanted:
            rank = 0
        elif code.startswith(wanted):
            rank = 1
        elif wanted in code or (words and all(w in f"{lot.code} {lot.title}".lower() for w in words)):
            rank = 2
        else:
            continue
        scored[lot.id] = (rank, None)
    for row in wafer_rows:
        key = row["lasermark_key"]
        if row["lot_id"] in scored or not (key == wanted or key.startswith(wanted)):
            continue
        scored[row["lot_id"]] = (3 if key == wanted else 4, row["lasermark"])
    by_id = {lot.id: lot for lot in lots}
    ordered = sorted(scored.items(), key=lambda item: (item[1][0], by_id[item[0]].status not in ACTIVE_STATUSES, by_id[item[0]].code))
    return [{"lot": by_id[lot_id], "wafer": wafer} for lot_id, (_rank, wafer) in ordered[:limit]]


# --- écriture -------------------------------------------------------------------------------


def _write_wafers(conn: sqlite3.Connection, lot_id: int, lasermarks: list[str]) -> None:
    existing = {row["lasermark_key"] for row in conn.execute("SELECT lasermark_key FROM lot_wafers WHERE lot_id = ?", (lot_id,))}
    position = conn.execute("SELECT COALESCE(MAX(position) + 1, 0) AS p FROM lot_wafers WHERE lot_id = ?", (lot_id,)).fetchone()["p"]
    added = [lm for lm in parse_lasermarks(lasermarks) if compact(lm) not in existing]
    if len(existing) + len(added) > MAX_WAFERS:
        raise ValueError(f"{MAX_WAFERS} wafers au maximum par lot")
    for lasermark in added:
        conn.execute(
            "INSERT INTO lot_wafers (lot_id, lasermark, lasermark_key, position) VALUES (?, ?, ?, ?)",
            (lot_id, lasermark, compact(lasermark), position),
        )
        position += 1


def _write_thematics(conn: sqlite3.Connection, lot_id: int, thematic_ids: list[int]) -> None:
    conn.execute("DELETE FROM lot_thematics WHERE lot_id = ?", (lot_id,))
    for thematic_id in dict.fromkeys(thematic_ids):
        if conn.execute("SELECT 1 FROM thematics WHERE id = ?", (thematic_id,)).fetchone() is None:
            raise ValueError("thématique introuvable")
        conn.execute("INSERT INTO lot_thematics (lot_id, thematic_id) VALUES (?, ?)", (lot_id, thematic_id))


def create(
    *,
    code: str | None,
    title: str = "",
    description: str = "",
    priority: str = "",
    started_on: str | None = None,
    forecast_exit_on: str | None = None,
    wafers: list[str] | None = None,
    thematic_ids: list[int] | None = None,
    created_by: int,
) -> Lot:
    """Un nouveau lot - code auto (LOT-0001...) s'il est laissé vide ; « en cours » dès qu'il a un
    début passé, « en préparation » sinon."""
    started = _check_date(started_on, "début")
    forecast = _check_date(forecast_exit_on, "fin prévisionnelle")
    _check_dates(started, forecast, None)
    status = "wip" if started and started <= date.today().isoformat() else "planned"
    with get_conn() as conn:
        code = _check_code(code) if (code or "").strip() else _next_code(conn)
        if conn.execute("SELECT 1 FROM lots WHERE code = ? COLLATE NOCASE", (code,)).fetchone():
            raise ValueError(f"le lot « {code} » existe déjà")
        cursor = conn.execute(
            "INSERT INTO lots (code, title, description, priority, status, started_on, forecast_exit_on, created_by) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (code, title.strip()[:160], description.strip(), _check_priority(priority), status, started, forecast, created_by),
        )
        lot_id = cursor.lastrowid
        _write_wafers(conn, lot_id, wafers or [])
        _write_thematics(conn, lot_id, thematic_ids or [])
    return get_by_id(lot_id)


def update(
    lot_id: int,
    *,
    code: str,
    title: str,
    description: str,
    priority: str,
    status: str,
    started_on: str | None,
    forecast_exit_on: str | None,
    exited_on: str | None,
    hold_reason: str = "",
) -> Lot:
    """Les informations du lot. Une fin déclarée le rend « sorti » ; « sorti » sans date prend
    aujourd'hui ; tout autre statut efface la fin déclarée (le lot est rouvert)."""
    if status not in STATUSES:
        raise ValueError(f"statut inconnu : {status!r}")
    started = _check_date(started_on, "début")
    forecast = _check_date(forecast_exit_on, "fin prévisionnelle")
    exited = _check_date(exited_on, "fin déclarée")
    _check_dates(started, forecast, exited)  # les dates saisies ; un début ajouté ci-dessous peut dépasser la prévision (retard)
    if exited and status != "cancelled":
        status = "done"
    if status == "done" and not exited:
        exited = date.today().isoformat()
    if status not in ("done", "cancelled"):
        exited = None
    if status in ("wip", "hold") and not started:
        started = date.today().isoformat()
    with get_conn() as conn:
        code = _check_code(code)
        clash = conn.execute("SELECT id FROM lots WHERE code = ? COLLATE NOCASE AND id != ?", (code, lot_id)).fetchone()
        if clash:
            raise ValueError(f"le lot « {code} » existe déjà")
        conn.execute(
            "UPDATE lots SET code = ?, title = ?, description = ?, priority = ?, status = ?, started_on = ?, "
            "forecast_exit_on = ?, exited_on = ?, hold_reason = ?, updated_at = datetime('now') WHERE id = ?",
            (
                code,
                title.strip()[:160],
                description.strip(),
                _check_priority(priority),
                status,
                started,
                forecast,
                exited,
                hold_reason.strip()[:300] if status == "hold" else "",
                lot_id,
            ),
        )
    return get_by_id(lot_id)


def add_wafers(lot_id: int, lasermarks: str | list[str]) -> None:
    with get_conn() as conn:
        _write_wafers(conn, lot_id, parse_lasermarks(lasermarks))
        _touch(conn, lot_id)


def remove_wafer(lot_id: int, lasermark: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM lot_wafers WHERE lot_id = ? AND lasermark_key = ?", (lot_id, compact(lasermark)))
        _touch(conn, lot_id)


def set_thematics(lot_id: int, thematic_ids: list[int]) -> None:
    with get_conn() as conn:
        _write_thematics(conn, lot_id, thematic_ids)
        _touch(conn, lot_id)


def delete(lot_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM lots WHERE id = ?", (lot_id,))
