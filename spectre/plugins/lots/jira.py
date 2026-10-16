"""Les lots que la ligne connaît : le nom de lot « métier » qu'écrivent les FDL JIRA
(``jira_nom_lots`` : QMDE06, QT112...). Un lot existe dans Spectre dès qu'on le sait, pour que ses
plaques en portent le badge.

Deux chemins :

- **la détection** : chaque fois que la vie d'une plaque est lue en ligne (plugin wafers,
  :func:`tracking.on_tracking_read`), son nom de lot JIRA (``lot_name``, quand il vient de JIRA et pas
  de la MES) fait exister le lot et y range la plaque (:func:`detect`) ;
- **l'import** : la liste de tous les lots cités par les FDL (hook PRISM ``jira_lots``,
  :func:`available`), et pour l'un d'eux, toutes ses plaques (``jira_lot_wafers``) - le lot est créé,
  ses plaques y entrent et chacune reçoit sa fiche de plaque (:func:`import_lot`).

Les noms bruts de ``jira_nom_lots`` sont libres (« QMDE 06 », « qmde06, QMDE07 ») : ils sont lus
comme le fait la vie d'une plaque (:func:`tracking.lot_names`) - un même lot peut venir de
plusieurs écritures, toutes gardées (``raw``) pour relire ses plaques exactement.

Les sources, choisies à un seul endroit (:func:`current_source`) : PRISM, ou la démo
(``SPECTRE_DEMO_DATA=1``) - des lots QMDE01... aux plaques inventées.
"""

from __future__ import annotations

import logging
import os
import random
from datetime import datetime, timedelta
from typing import Any, Protocol

import pandas as pd

from ...kernel import plugin_states
from ...kernel.errors import InvalidInput, NotFound
from ..accounts.service import User
from ..wafers import records, tracking
from ..wafers import service as wafer_index
from . import service as lots

logger = logging.getLogger(__name__)


lot_names = tracking.lot_names


def _date(value: Any) -> str | None:
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    try:
        return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def group_lots(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Le hook ``jira_lots`` (une ligne par valeur brute de ``jira_nom_lots`` : ``n_fdl``,
    ``first_created``, ``last_created``) regroupé par nom de lot : ``{name, raw, n_fdl, first,
    last}``, les plus récents d'abord."""
    found: dict[str, dict[str, Any]] = {}
    if df is not None and len(df):
        for row in df.to_dict("records"):
            raw = str(row.get("jira_nom_lots") or "").strip()
            for name in lot_names(raw):
                entry = found.setdefault(name, {"name": name, "raw": [], "n_fdl": 0, "first": None, "last": None})
                if raw not in entry["raw"]:
                    entry["raw"].append(raw)
                entry["n_fdl"] += int(row.get("n_fdl") or 0)
                first, last = _date(row.get("first_created")), _date(row.get("last_created"))
                if first and (entry["first"] is None or first < entry["first"]):
                    entry["first"] = first
                if last and (entry["last"] is None or last > entry["last"]):
                    entry["last"] = last
    return sorted(found.values(), key=lambda e: (e["last"] or "", e["name"]), reverse=True)


def lot_wafers(df: pd.DataFrame, name: str) -> list[dict[str, Any]]:
    """Le hook ``jira_lot_wafers`` (une ligne par FDL et plaque citée) : les plaques du lot ``name``
    - ``{lasermark, fdl}`` -, dans l'ordre des FDL puis du ticket, chacune une fois."""
    out: dict[str, dict[str, Any]] = {}
    if df is not None and len(df):
        for row in df.to_dict("records"):
            if name not in lot_names(str(row.get("jira_nom_lots") or "")):
                continue
            mark = " ".join(str(row.get("wafer") or "").split())
            if mark and mark.upper() not in out:
                out[mark.upper()] = {"lasermark": mark, "fdl": str(row.get("Request_Number") or "") or None}
    return list(out.values())


class JiraLotSource(Protocol):
    name: str

    def lots(self) -> list[dict[str, Any]]: ...

    def wafers(self, lot: dict[str, Any]) -> list[dict[str, Any]]: ...


class PrismSource:
    name = "prism"

    @staticmethod
    def _run(hook: str, params: dict[str, Any]) -> pd.DataFrame:
        return tracking.run_line_hook(hook, params)  # l'adaptateur PRISM du plugin wafers

    def lots(self) -> list[dict[str, Any]]:
        return group_lots(self._run("jira_lots", {}))

    def wafers(self, lot: dict[str, Any]) -> list[dict[str, Any]]:
        return lot_wafers(self._run("jira_lot_wafers", {"nom_lots": lot["raw"]}), lot["name"])


class DemoSource:
    """Douze lots QMDE inventés, toujours les mêmes, de 4 à 12 plaques ``QMDEnn-Wkk``."""

    name = "demo"

    def __init__(self) -> None:
        now = datetime(2026, 10, 1)
        rows, wafers = [], []
        for n in range(1, 13):
            name = f"QMDE{n:02d}"
            raw = f"QMDE {n:02d}" if n % 3 == 0 else name
            rng = random.Random(n)
            first = now - timedelta(days=10 * (13 - n))
            rows.append({"jira_nom_lots": raw, "n_fdl": rng.randint(1, 4), "first_created": first, "last_created": first + timedelta(days=rng.randint(1, 20))})
            for slot in sorted(rng.sample(range(1, 26), rng.randint(4, 12))):
                wafers.append({"Request_Number": f"FDL-{700 + n}", "jira_nom_lots": raw, "wafer": f"{name}-W{slot:02d}"})
        self._lots = pd.DataFrame(rows)
        self._wafers = pd.DataFrame(wafers)

    def lots(self) -> list[dict[str, Any]]:
        return group_lots(self._lots)

    def wafers(self, lot: dict[str, Any]) -> list[dict[str, Any]]:
        return lot_wafers(self._wafers[self._wafers["jira_nom_lots"].isin(lot["raw"])], lot["name"])


_PRISM = PrismSource()
_DEMO = DemoSource()


def current_source() -> JiraLotSource:
    return _DEMO if os.environ.get("SPECTRE_DEMO_DATA") == "1" else _PRISM


def _spectre_lot(name: str) -> dict[str, Any] | None:
    lot = lots.find_by_code(name)
    if lot is None:
        return None
    return {"id": lot.id, "code": lot.code, "source": lot.source, "wafers": len(lots.wafers_of([lot.id]).get(lot.id, []))}


def available(q: str = "") -> dict[str, Any]:
    """Les lots cités par les FDL JIRA (filtrés par ``q``), chacun avec ``spectre`` : le lot
    Spectre du même nom, s'il existe."""
    source = current_source()
    wanted = "".join(q.split()).upper()
    items = [lot for lot in source.lots() if not wanted or wanted in lot["name"].replace(" ", "").upper()]
    return {"source": source.name, "items": [{**lot, "spectre": _spectre_lot(lot["name"])} for lot in items]}


def import_lot(user: User, name: str) -> dict[str, Any]:
    """Importe le lot JIRA ``name`` : le lot (créé ou complété), ses plaques et leurs fiches de
    plaque. Rend ``{lot, created, added, wafers, records_created, base_error}``."""
    source = current_source()
    wanted = " ".join((name or "").split()).upper()
    found = next((lot for lot in source.lots() if lot["name"].upper() == wanted), None)
    if found is None:
        raise NotFound(f"Aucune FDL JIRA ne cite le lot « {name} ».", code="jira_lot_not_found")
    if not lots.is_valid_code(found["name"]):
        raise InvalidInput(f"« {found['name']} » ne peut pas devenir le code d'un lot Spectre.", code="invalid_lot_code")
    wafers = source.wafers(found)
    marks = [w["lasermark"] for w in wafers]
    lot, created, added = lots.upsert_from_line(
        found["name"], marks, title=f"Lot {found['name']}", description="Lot importé des FDL JIRA (jira_nom_lots).", started_on=found.get("first"), created_by=user.id
    )
    made, error = 0, None
    for start in range(0, len(marks), records.MAX_LOOKUP):
        result = records.create(user, marks[start : start + records.MAX_LOOKUP])
        made += sum(1 for item in result["items"] if item["created"])
        error = error or result["base_error"]
    return {"lot": {"id": lot.id, "code": lot.code}, "created": created, "added": added, "wafers": len(marks), "records_created": made, "base_error": error}


def detect(key: str, lasermark: str, payload: dict[str, Any]) -> None:
    """La plaque vient d'être lue en ligne : son lot JIRA existe désormais dans Spectre, et elle y
    est (un nom venu de la MES seulement n'est pas un lot JIRA : ignoré)."""
    if not plugin_states.is_enabled("lots"):
        return
    name = payload.get("lot_name")
    if not name or payload.get("lot_source") != "JIRA" or not lots.is_valid_code(name):
        return
    lots.upsert_from_line(name, [lasermark], title=f"Lot {name}", description="Lot détecté dans les FDL JIRA (jira_nom_lots) de ses plaques.")


tracking.on_tracking_read(detect)


def _lot_names() -> dict[str, list[str]]:
    return lots.lot_codes_by_wafer() if plugin_states.is_enabled("lots") else {}


# chercher une plaque par le nom de son lot (/plaques, barre du haut)
wafer_index.register_lot_names(_lot_names)
