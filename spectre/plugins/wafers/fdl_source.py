"""Les plaques d'une FDL : celles qui ont réellement été lancées sous cette feuille de lancement,
lues « en base » pour qu'une étude associe chacune de ses places (une par variante d'une campagne,
ses réplicats sinon) à une vraie plaque, à la main, depuis un menu déroulant.

Le contrat (``FdlSource``) est celui de toutes les sources ; :func:`current_source` est le seul
endroit qui choisit :

- **la démo** (``SPECTRE_DEMO_DATA=1``, comme la caractérisation) : chaque numéro ``FDL-n`` contient
  des plaques inventées, toujours les mêmes pour le même numéro - de quoi essayer l'association ;
- **la base locale** sinon : les lasermarks d'une FDL, collés à la main (``PUT
  /api/fdls/{fdl}/wafers``) en attendant la vraie source - la seule qu'on écrit ;
- **PRISM** viendra ici, en lecture seule, à la place de la base locale : la ligne connaît déjà
  les plaques de chaque FDL.
"""

from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from ...kernel.db import get_conn
from ...kernel.errors import Conflict, InvalidInput
from ..experiments.entities import MAX_TRACKED_ENTITIES, compact, normalize_fdl


@dataclass(frozen=True)
class FdlWafer:
    """Une plaque d'une FDL : son lasermark et, quand la source la connaît, sa place dans le lot."""

    lasermark: str
    slot: int | None = None

    def payload(self) -> dict[str, Any]:
        return {"lasermark": self.lasermark, "slot": self.slot}


class FdlSource(Protocol):
    name: str  # "demo", "local" - "prism" à venir
    editable: bool  # ses plaques se saisissent à la main

    def wafers(self, fdl: str) -> list[FdlWafer] | None:
        """Les plaques de ``fdl`` (déjà normalisée), dans l'ordre du lot - ``None`` pour une FDL
        que la source ne connaît pas."""
        ...


def content(source: FdlSource, fdl: str) -> dict[str, Any]:
    """Ce que dit ``source`` de ``fdl`` : ``{fdl, source, editable, known, wafers}``."""
    wafers = source.wafers(fdl)
    return {
        "fdl": fdl,
        "source": source.name,
        "editable": source.editable,
        "known": wafers is not None,
        "wafers": [wafer.payload() for wafer in wafers or []],
    }


class LocalSource:
    """Les plaques d'une FDL telles qu'on les a collées dans Spectre (table ``fdl_wafers``)."""

    name = "local"
    editable = True

    def wafers(self, fdl: str) -> list[FdlWafer] | None:
        with get_conn() as conn:
            rows = conn.execute("SELECT lasermark, position FROM fdl_wafers WHERE fdl = ? ORDER BY position", (fdl,)).fetchall()
        return [FdlWafer(row["lasermark"], row["position"] + 1) for row in rows] or None

    def set_wafers(self, fdl: str, lasermarks: list[str], *, author: str) -> None:
        """Remplace les plaques de ``fdl`` : chacune une fois (comparées sans casse ni séparateurs),
        dans l'ordre donné - aucune efface la FDL."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in lasermarks:
            mark = " ".join((raw or "").split())[:80]
            if mark and compact(mark) not in seen:
                seen.add(compact(mark))
                cleaned.append(mark)
        if len(cleaned) > MAX_TRACKED_ENTITIES:
            raise InvalidInput(f"Au plus {MAX_TRACKED_ENTITIES} plaques par FDL.", code="too_many_wafers")
        now = datetime.now(timezone.utc).isoformat()
        with get_conn() as conn:
            conn.execute("DELETE FROM fdl_wafers WHERE fdl = ?", (fdl,))
            conn.executemany(
                "INSERT INTO fdl_wafers (fdl, position, lasermark, author, updated_at) VALUES (?, ?, ?, ?, ?)",
                [(fdl, i, mark, author, now) for i, mark in enumerate(cleaned)],
            )


class DemoSource:
    """Des plaques inventées pour chaque ``FDL-n`` : un lot de 25 places dont une partie a été lancée,
    toujours la même pour le même numéro. Une autre clé JIRA n'est pas une FDL connue."""

    name = "demo"
    editable = False

    def wafers(self, fdl: str) -> list[FdlWafer] | None:
        match = re.fullmatch(r"FDL-(\d+)", fdl)
        if not match:
            return None
        number = int(match.group(1))
        rng = random.Random(number)
        slots = sorted(rng.sample(range(1, 26), rng.randint(4, 12)))
        return [FdlWafer(f"D{number}-W{slot:02d}", slot) for slot in slots]


_LOCAL = LocalSource()
_DEMO = DemoSource()


def current_source() -> FdlSource:
    return _DEMO if os.environ.get("SPECTRE_DEMO_DATA") == "1" else _LOCAL


def fdl_key(text: str) -> str:
    """Une FDL telle qu'écrite dans l'adresse, normalisée comme partout (« 1234 » -> FDL-1234)."""
    fdl = normalize_fdl(text)
    if not fdl:
        raise InvalidInput("Numéro de FDL manquant.", code="fdl_required")
    return fdl


def read(text: str) -> dict[str, Any]:
    return content(current_source(), fdl_key(text))


def write(text: str, lasermarks: list[str], *, author: str) -> dict[str, Any]:
    """Les plaques d'une FDL saisies à la main - seulement dans la base locale : une source qui
    connaît la ligne (la démo, PRISM) fait foi."""
    fdl = fdl_key(text)
    source = current_source()
    if not isinstance(source, LocalSource):
        raise Conflict("Les plaques de cette FDL viennent de la base de la ligne : elles ne se saisissent pas ici.", code="fdl_source_read_only")
    source.set_wafers(fdl, lasermarks, author=author)
    return content(source, fdl)
