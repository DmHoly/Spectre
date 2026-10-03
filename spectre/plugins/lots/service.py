"""Suivi de lots : un lot de fabrication, c'est une liste de wafers (par lasermark - le ``sample_id``
de ``Experiment.metadata["physical_tracking"]``, comparé par sa clé, voir
:mod:`spectre.plugins.wafers.service`) avec sa priorité (P10, P20... - la plus petite passe
d'abord), son début, sa fin prévisionnelle et sa fin déclarée.

Un lot a une **source** : ``declaratif``, saisi à la main ici - et c'est le seul cas aujourd'hui -,
ou ``prism``, alimenté par la base de production : sa priorité, ses dates et ses wafers y sont
alors en lecture seule (409). Les règles de statut (:func:`declared_state`) ne s'appliquent qu'à une
saisie déclarative. Pas de parcours d'étapes : trop lourd à tenir à la main.

Ce module ne stocke **ni expériences ni µprojets** : les expériences d'un lot sont toutes celles qui
suivent un de ses wafers - dès qu'un wafer entre dans un lot, ses expériences y sont rattachées, même
terminées avant (une épitaxie finie, puis un lot de fabrication lancé pour en avoir la mesure
électro-optique) ; ses thématiques sont celles de leurs µprojets, plus celles déclarées « visées » à
la main, utiles avant qu'une expérience n'existe - voir :mod:`spectre.plugins.lots.views`. Un lot
est visible de tout utilisateur connecté, comme les projets corporate ; chacun peut en créer et le
mettre à jour.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Iterable

from ...kernel.db import get_conn
from ...kernel.errors import Conflict, Forbidden, InvalidInput, NotFound, PreconditionFailed
from ...kernel.locks import keyed_lock
from ..wafers.service import wafer_key

STATUSES = ("planned", "wip", "hold", "done", "cancelled")
ACTIVE_STATUSES = frozenset({"planned", "wip", "hold"})  # pas encore sorti (ni annulé)
PRIORITIES = ("P10", "P20", "P30", "P40", "P50")  # suggestions - toute valeur courte est acceptée
MAX_WAFERS = 200
SEARCH_LIMIT = 20

# ce qu'un lot alimenté par PRISM ne laisse pas modifier ici
PRISM_FIELDS = frozenset({"priority", "started_on", "forecast_exit_on", "exited_on"})

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _\-.]{0,39}$")  # il se lit dans l'adresse d'une page : /lots/{code}
_PRIORITY_RE = re.compile(r"^[A-Za-z0-9 _\-]{0,10}$")


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
    updated_at: str  # sa version : la précondition If-Match d'une modification

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


@dataclass(frozen=True)
class LotWafer:
    key: str
    lasermark: str  # tel que saisi


def _lot_from_row(row: sqlite3.Row) -> Lot:
    return Lot(**{name: row[name] for name in Lot.__dataclass_fields__})


def _now() -> str:
    """La date d'une écriture, à la microseconde : deux écritures successives d'un lot n'ont jamais
    la même version."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def priority_rank(priority: str) -> tuple[int, str]:
    """Pour trier : P10 avant P20 avant P100 ; sans priorité, à la fin."""
    match = re.search(r"\d+", priority or "")
    return (int(match.group()) if match else 10**6, (priority or "").upper())


def _sort_key(lot: Lot) -> tuple:
    return (priority_rank(lot.priority), lot.forecast_exit_on or "9999", lot.code)


State = tuple[str, str | None, str | None]  # (statut, début, fin déclarée)


def declared_state(current: State, changes: dict, *, today: str) -> State:
    """Les règles de statut d'une saisie déclarative : ``(statut, début, fin déclarée)`` après
    ``changes`` (ce que la saisie modifie de ``current``) - sans rien lire ni écrire. Un statut
    choisi autre que sorti ou annulé rouvre le lot (la fin déclarée s'efface), une fin déclarée
    effacée aussi ; une fin déclarée rend le lot « sorti » (sauf annulé), « sorti » sans date prend
    ``today`` ; en cours ou en pause, il a commencé (``today`` sans début)."""
    status, started_on, exited_on = (changes.get(name, value) for name, value in zip(("status", "started_on", "exited_on"), current))
    if "status" in changes and "exited_on" not in changes and status not in ("done", "cancelled"):
        exited_on = None
    if "exited_on" in changes and exited_on is None and "status" not in changes and status == "done":
        status = "wip" if started_on else "planned"
    if exited_on and status != "cancelled":
        status = "done"
    if status == "done" and not exited_on:
        exited_on = today
    if status not in ("done", "cancelled"):
        exited_on = None
    if status in ("wip", "hold") and not started_on:
        started_on = today
    return status, started_on, exited_on


def _check_date(value: str | None, label: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    try:
        return date.fromisoformat(str(value).strip()[:10]).isoformat()
    except ValueError as exc:
        raise InvalidInput(f"{label} : date invalide « {value} » (attendu AAAA-MM-JJ)") from exc


def _check_code(code: str) -> str:
    code = " ".join((code or "").split())
    if not _CODE_RE.match(code):
        raise InvalidInput("Le code du lot doit faire 1 à 40 caractères (lettres, chiffres, espace, - _ .).")
    return code


def _check_priority(priority: str | None) -> str:
    priority = " ".join((priority or "").split()).upper()
    if not _PRIORITY_RE.match(priority):
        raise InvalidInput("La priorité est un code court (ex : P10), 10 caractères au plus.")
    return priority


def _check_dates(started: str | None, forecast: str | None, exited: str | None) -> None:
    if started and forecast and forecast < started:
        raise InvalidInput("La fin prévisionnelle est avant le début du lot.")
    if started and exited and exited < started:
        raise InvalidInput("La fin déclarée est avant le début du lot.")


def check_statuses(statuses: Iterable[str]) -> set[str]:
    wanted = {status.strip() for status in statuses if status.strip()}
    unknown = sorted(wanted - set(STATUSES))
    if unknown:
        raise InvalidInput(f"Statut de lot inconnu : {', '.join(unknown)} (connus : {', '.join(STATUSES)}).")
    return wanted


def parse_lasermarks(text: str | list[str]) -> list[str]:
    """Des lasermarks collés tels quels (une colonne Excel, « W12-A3, W12-A4 »...) - dans l'ordre,
    sans doublon (même clé que l'index des plaques)."""
    items = text if isinstance(text, list) else re.split(r"[\s,;]+", text or "")
    seen: set[str] = set()
    result = []
    for item in items:
        item = (item or "").strip()
        key = wafer_key(item)
        if key and key not in seen:
            seen.add(key)
            result.append(item[:60])
    return result


def _code_taken(code: str) -> Conflict:
    return Conflict(f"Le lot « {code} » existe déjà.", code="lot_code_taken")


def _read_only(lot: Lot) -> Conflict:
    return Conflict(
        f"Le lot « {lot.code} » est alimenté par la base de production : sa priorité, ses dates et ses wafers ne se modifient pas ici.",
        code="lot_read_only_source",
    )


def _next_code(conn: sqlite3.Connection) -> str:
    n = conn.execute("SELECT COUNT(*) AS n FROM lots").fetchone()["n"] + 1
    while conn.execute("SELECT 1 FROM lots WHERE code = ? COLLATE NOCASE", (f"LOT-{n:04d}",)).fetchone():
        n += 1
    return f"LOT-{n:04d}"


# --- lecture --------------------------------------------------------------------------------


def _placeholders(values: Iterable) -> str:
    return ", ".join("?" for _ in values)


def list_lots(*, statuses: set[str] | None = None, wafer_keys: Iterable[str] | None = None, code: str | None = None) -> list[Lot]:
    """Les lots par priorité (P10 d'abord), puis par fin prévisionnelle - ceux de ``statuses``,
    qui contiennent l'un des wafers ``wafer_keys`` (des clés ou des lasermarks), ou dont le code
    est ``code`` (sans la casse), si ces filtres sont donnés."""
    where, params = [], []
    if statuses:
        where.append(f"status IN ({_placeholders(statuses)})")
        params.extend(sorted(statuses))
    if wafer_keys is not None:
        keys = sorted({wafer_key(key) for key in wafer_keys} - {""})
        if not keys:
            return []
        where.append(f"id IN (SELECT lot_id FROM lot_wafers WHERE lasermark_key IN ({_placeholders(keys)}))")
        params.extend(keys)
    if code is not None:
        where.append("code = ? COLLATE NOCASE")
        params.append(code.strip())
    sql = "SELECT * FROM lots" + (f" WHERE {' AND '.join(where)}" if where else "")
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return sorted((_lot_from_row(row) for row in rows), key=_sort_key)


def search(query: str, *, statuses: set[str] | None = None, limit: int = SEARCH_LIMIT) -> list[tuple[Lot, str | None]]:
    """``(lot, wafer)`` : les lots dont le code correspond à ``query`` (le code exact, puis ceux qui
    commencent par lui, puis ceux qui le contiennent - ou dont le code et l'intitulé contiennent
    chaque mot tapé), puis ceux qui contiennent un wafer dont le lasermark correspond (``wafer`` dit
    lequel) ; les lots pas encore sortis d'abord, à rang égal."""
    key = wafer_key(query)
    if len(key) < 2:
        return []
    words = (query or "").lower().split()
    every_word = " AND ".join("instr(py_lower(code || ' ' || title), ?) > 0" for _ in words)
    status_filter = f"WHERE status IN ({_placeholders(statuses)})" if statuses else ""
    sql = f"""
        SELECT *, MIN(score) AS best FROM (
            SELECT lots.*, NULL AS wafer, CASE
                WHEN compact(code) = ? THEN 0
                WHEN instr(compact(code), ?) = 1 THEN 1
                WHEN instr(compact(code), ?) > 0 OR ({every_word}) THEN 2
            END AS score
            FROM lots
            UNION ALL
            SELECT lots.*, lot_wafers.lasermark, CASE WHEN lot_wafers.lasermark_key = ? THEN 3 ELSE 4 END
            FROM lots JOIN lot_wafers ON lot_wafers.lot_id = lots.id
            WHERE instr(lot_wafers.lasermark_key, ?) = 1
        ) {status_filter}
        GROUP BY id HAVING best IS NOT NULL
        ORDER BY best, status NOT IN ({_placeholders(ACTIVE_STATUSES)}), code COLLATE NOCASE
        LIMIT ?"""
    params = [key, key, key, *words, key, key, *sorted(statuses or ()), *sorted(ACTIVE_STATUSES), limit]
    with get_conn() as conn:
        # la clé d'un code, comme celle d'un lasermark ; et lower() pour tout l'Unicode (« Épitaxie »)
        conn.create_function("compact", 1, wafer_key, deterministic=True)
        conn.create_function("py_lower", 1, lambda text: (text or "").lower(), deterministic=True)
        rows = conn.execute(sql, params).fetchall()
    return [(_lot_from_row(row), row["wafer"]) for row in rows]


def get(lot_id: int) -> Lot:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()
    if row is None:
        raise NotFound(f"Lot {lot_id} introuvable.")
    return _lot_from_row(row)


def wafers_of(lot_ids: Iterable[int]) -> dict[int, list[LotWafer]]:
    """Les wafers de chacun de ces lots, dans l'ordre où ils ont été ajoutés - en une requête."""
    ids = sorted(set(lot_ids))
    found: dict[int, list[LotWafer]] = {lot_id: [] for lot_id in ids}
    if ids:
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT lot_id, lasermark, lasermark_key FROM lot_wafers WHERE lot_id IN ({_placeholders(ids)}) ORDER BY lot_id, position",
                ids,
            ).fetchall()
        for row in rows:
            found[row["lot_id"]].append(LotWafer(row["lasermark_key"], row["lasermark"]))
    return found


def declared_thematic_ids(lot_ids: Iterable[int]) -> dict[int, list[int]]:
    """Les thématiques déclarées « visées » de chacun de ces lots - en une requête."""
    ids = sorted(set(lot_ids))
    found: dict[int, list[int]] = {lot_id: [] for lot_id in ids}
    if ids:
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT lot_id, thematic_id FROM lot_thematics WHERE lot_id IN ({_placeholders(ids)}) ORDER BY lot_id, thematic_id",
                ids,
            ).fetchall()
        for row in rows:
            found[row["lot_id"]].append(row["thematic_id"])
    return found


# --- écriture -------------------------------------------------------------------------------


def _write_wafers(conn: sqlite3.Connection, lot_id: int, lasermarks: list[str]) -> int:
    """Ajoute les wafers qui n'y sont pas encore - renvoie combien."""
    existing = {row["lasermark_key"] for row in conn.execute("SELECT lasermark_key FROM lot_wafers WHERE lot_id = ?", (lot_id,))}
    position = conn.execute("SELECT COALESCE(MAX(position) + 1, 0) AS p FROM lot_wafers WHERE lot_id = ?", (lot_id,)).fetchone()["p"]
    added = [lasermark for lasermark in parse_lasermarks(lasermarks) if wafer_key(lasermark) not in existing]
    if len(existing) + len(added) > MAX_WAFERS:
        raise InvalidInput(f"{MAX_WAFERS} wafers au maximum par lot.")
    for lasermark in added:
        conn.execute(
            "INSERT INTO lot_wafers (lot_id, lasermark, lasermark_key, position) VALUES (?, ?, ?, ?)",
            (lot_id, lasermark, wafer_key(lasermark), position),
        )
        position += 1
    return len(added)


def _write_thematics(conn: sqlite3.Connection, lot_id: int, thematic_ids: list[int]) -> None:
    conn.execute("DELETE FROM lot_thematics WHERE lot_id = ?", (lot_id,))
    for thematic_id in dict.fromkeys(thematic_ids):
        if conn.execute("SELECT 1 FROM thematics WHERE id = ?", (thematic_id,)).fetchone() is None:
            raise InvalidInput(f"Thématique {thematic_id} introuvable.")
        conn.execute("INSERT INTO lot_thematics (lot_id, thematic_id) VALUES (?, ?)", (lot_id, thematic_id))


def _touch(conn: sqlite3.Connection, lot_id: int) -> None:
    conn.execute("UPDATE lots SET updated_at = ? WHERE id = ?", (_now(), lot_id))


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
    """Un nouveau lot déclaratif - code auto (LOT-0001...) s'il est laissé vide ; « en cours » dès
    qu'il a un début passé, « en préparation » sinon. Un code déjà pris (sans la casse) : 409."""
    started = _check_date(started_on, "Début")
    forecast = _check_date(forecast_exit_on, "Fin prévisionnelle")
    _check_dates(started, forecast, None)
    status = "wip" if started and started <= date.today().isoformat() else "planned"
    values = (title.strip()[:160], description.strip(), _check_priority(priority), status, started, forecast, created_by)
    if (code or "").strip():
        code = _check_code(code)
        with get_conn() as conn:
            if conn.execute("SELECT 1 FROM lots WHERE code = ? COLLATE NOCASE", (code,)).fetchone():
                raise _code_taken(code)
            try:
                lot_id = _insert_lot(conn, code, values)
            except sqlite3.IntegrityError as exc:  # créé entre-temps par une autre requête
                raise _code_taken(code) from exc
            _write_wafers(conn, lot_id, wafers or [])
            _write_thematics(conn, lot_id, thematic_ids or [])
        return get(lot_id)
    # Code généré : deux créations simultanées ne doivent pas tirer le même numéro (verrou jusqu'au
    # commit), et un code saisi à la main qui prend ce numéro entre-temps fait passer au suivant -
    # jamais de 409 pour un code que personne n'a tapé.
    with keyed_lock("lots", "next-code"), get_conn() as conn:
        for _ in range(_NEXT_CODE_ATTEMPTS):
            try:
                lot_id = _insert_lot(conn, _next_code(conn), values)
                break
            except sqlite3.IntegrityError:
                continue
        else:
            raise Conflict("Impossible d'attribuer un code au lot : réessayez.", code="lot_code_unavailable")
        _write_wafers(conn, lot_id, wafers or [])
        _write_thematics(conn, lot_id, thematic_ids or [])
    return get(lot_id)


_NEXT_CODE_ATTEMPTS = 20


def _insert_lot(conn: sqlite3.Connection, code: str, values: tuple) -> int:
    """``values`` : titre, description, priorité, statut, début, fin prévisionnelle, auteur."""
    cursor = conn.execute(
        "INSERT INTO lots (code, title, description, priority, status, started_on, forecast_exit_on, created_by, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (code, *values, _now()),
    )
    return cursor.lastrowid


def _check_version(lot: Lot, expected_version: str | None) -> None:
    if expected_version is not None and expected_version != lot.updated_at:
        raise PreconditionFailed(
            f"Le lot « {lot.code} » a été modifié entre-temps : rechargez-le avant de l'enregistrer.", code="stale_version"
        )


def update(lot_id: int, changes: dict, *, expected_version: str | None = None) -> Lot:
    """Modifie les champs de ``changes`` (``code``, ``title``, ``description``, ``priority``,
    ``status``, ``started_on``, ``forecast_exit_on``, ``exited_on``, ``hold_reason``) - les autres
    restent. ``expected_version`` (``If-Match``) : la version affichée, sinon 412 et rien n'est
    écrit. Sans effet, rien n'est écrit (et la version ne change pas)."""
    with keyed_lock("lots", str(lot_id)):
        lot = get(lot_id)
        _check_version(lot, expected_version)
        if lot.source != "declaratif" and PRISM_FIELDS & changes.keys():
            current = {name: getattr(lot, name) for name in PRISM_FIELDS & changes.keys()}
            if any(changes[name] != value for name, value in current.items()):
                raise _read_only(lot)
        if "status" in changes and changes["status"] not in STATUSES:
            raise InvalidInput(f"Statut de lot inconnu : {changes['status']!r} (connus : {', '.join(STATUSES)}).")
        fields = {name: value for name, value in changes.items() if name in Lot.__dataclass_fields__}
        after = replace(lot, **fields)
        started = _check_date(after.started_on, "Début")
        forecast = _check_date(after.forecast_exit_on, "Fin prévisionnelle")
        exited = _check_date(after.exited_on, "Fin déclarée")
        if changes.keys() & {"started_on", "forecast_exit_on", "exited_on"}:
            # les dates saisies ; un début ajouté par les règles de statut peut dépasser la prévision (retard)
            _check_dates(started, forecast, exited)
        status = after.status
        if lot.source == "declaratif":
            given = {"status": status, "started_on": started, "exited_on": exited}
            status, started, exited = declared_state(
                (lot.status, lot.started_on, lot.exited_on),
                {name: value for name, value in given.items() if name in changes},
                today=date.today().isoformat(),
            )
        after = replace(
            after,
            code=_check_code(after.code),
            title=(after.title or "").strip()[:160],
            description=(after.description or "").strip(),
            priority=_check_priority(after.priority),
            status=status,
            started_on=started,
            forecast_exit_on=forecast,
            exited_on=exited,
            hold_reason=(after.hold_reason or "").strip()[:300] if status == "hold" else "",
        )
        if after == lot:
            return lot
        with get_conn() as conn:
            if conn.execute("SELECT 1 FROM lots WHERE code = ? COLLATE NOCASE AND id != ?", (after.code, lot_id)).fetchone():
                raise _code_taken(after.code)
            try:
                conn.execute(
                    "UPDATE lots SET code = ?, title = ?, description = ?, priority = ?, status = ?, started_on = ?, "
                    "forecast_exit_on = ?, exited_on = ?, hold_reason = ?, updated_at = ? WHERE id = ?",
                    (
                        after.code,
                        after.title,
                        after.description,
                        after.priority,
                        after.status,
                        after.started_on,
                        after.forecast_exit_on,
                        after.exited_on,
                        after.hold_reason,
                        _now(),
                        lot_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise _code_taken(after.code) from exc
    return get(lot_id)


def add_wafers(lot_id: int, lasermarks: str | list[str]) -> int:
    """Ajoute ces wafers au lot (ceux qui n'y sont pas encore) - renvoie combien."""
    with keyed_lock("lots", str(lot_id)):
        lot = get(lot_id)
        if lot.source != "declaratif":
            raise _read_only(lot)
        with get_conn() as conn:
            added = _write_wafers(conn, lot_id, parse_lasermarks(lasermarks))
            if added:
                _touch(conn, lot_id)
    return added


def remove_wafer(lot_id: int, wafer: str) -> None:
    """Retire du lot le wafer ``wafer`` (sa clé, ou son lasermark) - 404 s'il n'y est pas."""
    with keyed_lock("lots", str(lot_id)):
        lot = get(lot_id)
        if lot.source != "declaratif":
            raise _read_only(lot)
        with get_conn() as conn:
            removed = conn.execute("DELETE FROM lot_wafers WHERE lot_id = ? AND lasermark_key = ?", (lot_id, wafer_key(wafer))).rowcount
            if not removed:
                raise NotFound(f"Le wafer « {wafer} » n'est pas dans le lot « {lot.code} ».")
            _touch(conn, lot_id)


def set_thematics(lot_id: int, thematic_ids: list[int]) -> None:
    with keyed_lock("lots", str(lot_id)):
        get(lot_id)
        with get_conn() as conn:
            before = [row["thematic_id"] for row in conn.execute("SELECT thematic_id FROM lot_thematics WHERE lot_id = ? ORDER BY thematic_id", (lot_id,))]
            _write_thematics(conn, lot_id, thematic_ids)
            if sorted(dict.fromkeys(thematic_ids)) != before:
                _touch(conn, lot_id)


def can_delete(lot: Lot, user_id: int, is_admin: bool) -> bool:
    return is_admin or lot.created_by == user_id


def delete(lot_id: int, *, user_id: int, is_admin: bool) -> None:
    """Seule la personne qui a créé le lot, ou un admin, le supprime (403 sinon)."""
    lot = get(lot_id)
    if not can_delete(lot, user_id, is_admin):
        raise Forbidden("Seule la personne qui a créé le lot (ou un admin) peut le supprimer.")
    with get_conn() as conn:
        conn.execute("DELETE FROM lots WHERE id = ?", (lot_id,))
