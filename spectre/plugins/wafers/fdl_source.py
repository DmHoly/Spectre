"""Les plaques d'une FDL : celles qui ont réellement été lancées sous cette feuille de lancement,
lues « en base » pour qu'une étude associe chacune de ses places (une par variante d'une campagne,
ses réplicats sinon) à une vraie plaque, à la main, depuis un menu déroulant.

Le contrat (``FdlSource``) est celui de toutes les sources ; :func:`current_source` est le seul
endroit qui choisit :

- **la démo** (``SPECTRE_DEMO_DATA=1``, comme la caractérisation) : chaque numéro ``FDL-n`` contient
  des plaques inventées, toujours les mêmes pour le même numéro - de quoi essayer l'association ;
- **PRISM** sinon, en lecture seule : le hook ``fdl_wafers`` (catégorie « Traçabilité ») rend les
  lasermarks que le ticket Gozer de la FDL cite, dans l'ordre du ticket - la ligne connaît déjà les
  plaques de chaque FDL, Spectre ne porte aucune requête ;
- **la base locale** : les lasermarks d'une FDL collés à la main (``PUT /api/fdls/{fdl}/wafers``),
  la seule source qu'on écrit. Elle reste le repli, **automatique**, pour une FDL que Gozer ne
  connaît pas (``known`` faux côté PRISM : une FDL pas encore créée, une clé qui n'en est pas une) :
  c'est ce cas, et lui seul, que la saisie à la main couvre, et l'utilisateur n'a rien à régler
  pour y arriver. Une base de la ligne qui ne répond pas n'y bascule pas (502) : une liste saisie
  hier ne doit pas passer pour la vérité de Gozer. ``SPECTRE_FDL_SOURCE=local`` se passe de PRISM
  tout à fait (un poste sans ``~/.prism/connections.yml``, les tests) ; sans configuration PRISM,
  c'est une 503 qui le dit, comme pour la vie d'une plaque.
"""

from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from ...kernel.db import get_conn
from ...kernel.db import data_dir
from ...kernel.errors import Conflict, InvalidInput, Unavailable, UpstreamError
from ..experiments.entities import MAX_TRACKED_ENTITIES, compact, normalize_fdl


@dataclass(frozen=True)
class FdlWafer:
    """Une plaque d'une FDL : son lasermark et, quand la source la connaît, sa place dans le lot."""

    lasermark: str
    slot: int | None = None

    def payload(self) -> dict[str, Any]:
        return {"lasermark": self.lasermark, "slot": self.slot}


class FdlSource(Protocol):
    name: str  # "demo", "local", "prism"
    editable: bool  # ses plaques se saisissent à la main

    def wafers(self, fdl: str) -> list[FdlWafer] | None:
        """Les plaques de ``fdl`` (déjà normalisée), dans l'ordre du lot - ``None`` pour une FDL
        que la source ne connaît pas."""
        ...


def content(source: FdlSource, fdl: str, wafers: list[FdlWafer] | None) -> dict[str, Any]:
    """Ce que dit ``source`` de ``fdl`` : ``{fdl, source, editable, known, wafers}``."""
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


class PrismSource:
    """Les plaques citées par le ticket Gozer de la FDL : le hook PRISM ``fdl_wafers`` (une ligne par
    plaque, ``Request_Number`` / ``wafer`` / ``rank``). ``None`` quand Gozer ne cite aucune plaque
    pour ce numéro."""

    name = "prism"
    editable = False

    @staticmethod
    def _run(hook: str, params: dict[str, Any]) -> Any:
        import prism

        return prism.run_hook(hook, **params)

    def wafers(self, fdl: str) -> list[FdlWafer] | None:
        import prism

        try:
            df = self._run("fdl_wafers", {"fdl_numbers": [fdl]})
        except prism.ConfigError as exc:
            raise Unavailable(f"configuration de connexion PRISM incomplète : {exc}") from exc
        except prism.PrismError as exc:
            raise UpstreamError(f"la base de la ligne ne répond pas : {exc}") from exc
        found: list[FdlWafer] = []
        seen: set[str] = set()
        rows = [] if df is None or len(df) == 0 else df.sort_values("rank").to_dict("records")
        for row in rows:
            if str(row.get("Request_Number") or "").strip().upper() != fdl.upper():
                continue
            mark = " ".join(str(row.get("wafer") or "").split())
            if mark and compact(mark) not in seen:
                seen.add(compact(mark))
                found.append(FdlWafer(mark, len(found) + 1))
        return found or None


_LOCAL = LocalSource()
_DEMO = DemoSource()
_PRISM = PrismSource()


def current_source() -> FdlSource:
    if os.environ.get("SPECTRE_DEMO_DATA") == "1":
        return _DEMO
    if os.environ.get("SPECTRE_FDL_SOURCE", "prism") == "local":
        return _LOCAL
    # Le cache disque de PRISM vit avec les données de Spectre (comme pour la caractérisation).
    os.environ.setdefault("PRISM_DATA_DIR", str(data_dir() / "prism"))
    return _PRISM


def resolve(fdl: str) -> tuple[FdlSource, list[FdlWafer] | None]:
    """La source qui fait foi pour ``fdl`` et ses plaques : la source courante, ou la base locale
    quand PRISM ne connaît pas la FDL (voir le module)."""
    source = current_source()
    wafers = source.wafers(fdl)
    if wafers is None and source is _PRISM:
        return _LOCAL, _LOCAL.wafers(fdl)
    return source, wafers


def fdl_key(text: str) -> str:
    """Une FDL telle qu'écrite dans l'adresse, normalisée comme partout (« 1234 » -> FDL-1234)."""
    fdl = normalize_fdl(text)
    if not fdl:
        raise InvalidInput("Numéro de FDL manquant.", code="fdl_required")
    return fdl


def read(text: str) -> dict[str, Any]:
    fdl = fdl_key(text)
    source, wafers = resolve(fdl)
    return content(source, fdl, wafers)


def write(text: str, lasermarks: list[str], *, author: str) -> dict[str, Any]:
    """Les plaques d'une FDL saisies à la main - seulement dans la base locale : une source qui
    connaît la ligne (la démo, PRISM) fait foi."""
    fdl = fdl_key(text)
    source, _ = resolve(fdl)
    if not isinstance(source, LocalSource):
        raise Conflict("Les plaques de cette FDL viennent de la base de la ligne : elles ne se saisissent pas ici.", code="fdl_source_read_only")
    source.set_wafers(fdl, lasermarks, author=author)
    return content(source, fdl, source.wafers(fdl))
