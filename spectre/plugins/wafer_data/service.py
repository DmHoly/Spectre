"""La fiche data d'une plaque : les blocs des projets corporate de ses µprojets, calculés sur elle.

Une plaque rattachée à un µprojet (une étude la suit) l'est à son projet corporate ; l'onglet « Data » de
sa page montre, pour chacun de ces projets, les blocs qu'il a configurés (:mod:`.blocks`). Une plaque sans
µprojet n'a pas de fiche data.

Ce qu'un bloc a calculé sur une plaque se garde, résumé (:mod:`.store`) ; on le relit tel quel, sauf :

- jamais calculé (ou oublié par le budget) : calculé, sur le cache par plaque de PRISM ;
- calculé **sans mesure** (``empty``) il y a plus de :data:`RETRY_EMPTY` : recalculé en retapant la base -
  une plaque pas encore mesurée l'est peut-être depuis (le cache de PRISM, lui, garde un vide pour toujours) ;
- des images listées il y a plus de :data:`RETRY_EMPTY` : relistées (un fichier a pu arriver) ;
- ``refresh`` (le bouton « Rafraîchir ») : tout est recalculé en retapant la base.

Chaque type de données n'est interrogé qu'une fois pour tous les blocs qui le lisent, d'un projet à l'autre.
Un type en échec (base injoignable) ne prive pas des autres : ses blocs portent l'erreur, rien n'est gardé.
:func:`compute_area` calcule d'avance les fiches de toutes les plaques d'un projet, par paquets - de quoi
situer chaque valeur parmi toutes les plaques du projet.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from ...kernel.errors import DomainError, Forbidden, InvalidInput, NotFound, Unavailable
from ..accounts.service import User
from ..areas import service as areas
from ..areas.service import ManagementArea
from ..characterization import service as characterization
from ..experiments.entities import compact
from ..external_images import service as external_images
from ..kpi_tracking.service import tracked_wafers
from ..wafers import service as wafers
from ..wafers import tracking
from . import blocks as blocks_mod
from . import store
from .blocks import Block
from .digest import COMPUTE, WAFER_COLUMNS, round4

log = logging.getLogger(__name__)

RETRY_EMPTY = timedelta(hours=24)
BATCH = characterization.MAX_WAFERS


def _age(computed_at: str) -> timedelta:
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(computed_at)
    except ValueError:
        return RETRY_EMPTY * 2


def _stale(found: dict[str, Any] | None, block: Block) -> bool:
    if found is None:
        return True
    if found["status"] == "empty" or block.kind == "images":
        return _age(found["computed_at"]) > RETRY_EMPTY
    return False


# --- le calcul ------------------------------------------------------------------------------------


def _rows_by_wafer(columns: list[str], rows: list[list[Any]]) -> dict[str, list[list[Any]]]:
    lower = [c.lower() for c in columns]
    at = next((lower.index(name) for name in WAFER_COLUMNS if name in lower), None)
    if at is None:
        raise InvalidInput("la requête ne dit pas à quelle plaque va chaque ligne")
    found: dict[str, list[list[Any]]] = {}
    for row in rows:
        if row[at]:
            found.setdefault(compact(str(row[at])), []).append(row)
    return found


def _query(hook: str, lasermarks: list[str], refresh: bool) -> tuple[str, list[str], dict[str, list[list[Any]]]]:
    source, columns, by_wafer = "", [], {}
    for start in range(0, len(lasermarks), BATCH):
        result = characterization.query(hook, {characterization.WAFER_PARAMETER: lasermarks[start : start + BATCH]}, refresh=refresh)
        source, columns = result.source, result.columns
        for key, rows in _rows_by_wafer(result.columns, result.rows).items():
            by_wafer.setdefault(key, []).extend(rows)
    return source, columns, by_wafer


def _failure(exc: Exception, hook: str) -> str:
    if isinstance(exc, DomainError):
        return str(exc)
    log.exception("fiche data : lecture du type de données %s impossible", hook, exc_info=exc)
    return "Lecture impossible pour le moment : l'erreur a été journalisée sur le serveur."


def _placeholders(lasermark: str, line: dict[str, Any] | None) -> dict[str, str | None]:
    line = line or {}
    return {
        "lasermark": lasermark,
        "lot": line.get("lot_name") or None,
        "run": (line.get("run_names") or [None])[0],
        "fdl": (line.get("fdls") or [None])[0],
    }


def _images(block: Block, lasermark: str, line: dict[str, Any] | None) -> tuple[str, dict[str, Any], str]:
    """Les images d'une plaque d'après le modèle du bloc : (statut, résumé, message)."""
    values = _placeholders(lasermark, line)
    missing = sorted(name for name in re.findall(r"\{([^{}]*)\}", block.config["pattern"]) if not values.get(name))
    if missing:
        return "empty", {"images": [], "missing": missing}, f"On ne connaît pas encore {', '.join('{' + m + '}' for m in missing)} pour cette plaque."
    pattern = block.config["pattern"]
    for name, value in values.items():
        if value:
            pattern = pattern.replace("{" + name + "}", value)
    directory, _, name = pattern.replace("\\", "/").rpartition("/")
    try:
        entries = external_images.browse(directory)
    except Unavailable:
        return "error", {"images": []}, "Les images externes ne sont pas activées sur ce serveur (aucun dossier autorisé)."
    except Forbidden:
        return "error", {"images": []}, "Ce dossier n'est pas parmi les dossiers autorisés pour les images externes."
    except (NotFound, InvalidInput):
        return "empty", {"images": [], "directory": directory}, "Dossier introuvable pour cette plaque."
    matched = [e for e in entries if e["displayable"] and fnmatch.fnmatch(e["name"].lower(), name.lower())]
    images = [{"name": e["name"], "path": e["path"]} for e in matched[: block.config["max"]]]
    return ("ok" if images else "empty"), {"images": images, "directory": directory, "total": len(matched)}, ""


def compute(
    pending: list[tuple[str, str, Block]], *, refresh: bool, line: dict[str, dict[str, Any]], retry: set[tuple[str, str]] = frozenset()
) -> tuple[dict[tuple[str, str], dict[str, Any]], set[str]]:
    """Calcule et garde ``pending`` (``(clé de plaque, lasermark, bloc)``) : chaque type de données une fois pour
    toutes les plaques qui en ont besoin. ``retry`` : les couples (plaque, signature) dont le vide se revérifie en
    retapant la base. Rend ``{(clé, sig): {status, computed_at, payload, message}}`` et les sources lues."""
    results: dict[tuple[str, str], dict[str, Any]] = {}
    sources: set[str] = set()
    by_hook: dict[tuple[str, bool], list[tuple[str, str, Block]]] = {}
    for key, lasermark, block in pending:
        if block.kind == "images":
            status, payload, message = _images(block, lasermark, line.get(key))
            computed_at = store.write(key, block.sig, status, payload) if status != "error" else None
            results[(key, block.sig)] = {"status": status, "payload": payload, "computed_at": computed_at, "message": message}
            continue
        hard = refresh or (key, block.sig) in retry
        by_hook.setdefault((block.hook, hard), []).append((key, lasermark, block))
    for (hook, hard), items in by_hook.items():
        lasermarks = list(dict.fromkeys(lasermark for _, lasermark, _ in items))
        try:
            source, columns, rows = _query(hook, lasermarks, hard)
        except Exception as exc:
            message = _failure(exc, hook)
            for key, _, block in items:
                results[(key, block.sig)] = {"status": "error", "payload": None, "computed_at": None, "message": message}
            continue
        sources.add(source)
        for key, _, block in items:
            try:
                status, payload, scalar = COMPUTE[block.kind](columns, rows.get(key, []), block.config)
            except InvalidInput as exc:
                results[(key, block.sig)] = {"status": "error", "payload": None, "computed_at": None, "message": str(exc)}
                continue
            payload["source"] = source
            computed_at = store.write(key, block.sig, status, payload, scalar=None if scalar is None else round4(scalar))
            results[(key, block.sig)] = {"status": status, "payload": payload, "computed_at": computed_at, "message": ""}
    return results, sources


# --- la fiche d'une plaque ------------------------------------------------------------------------


def wafer_areas(user: User, lasermark: str) -> tuple[str, list[tuple[ManagementArea, list[dict[str, Any]]]]]:
    """Le nom de la plaque tel que ses études l'écrivent, et les projets corporate de ses µprojets - chacun avec
    ces µprojets (``{slug, code, name}``), dans l'ordre où la plaque y est entrée."""
    found = wafers.occurrences(user, keys=[lasermark])
    name = next((o.entry.get("sample_id") for o in found if o.entry.get("sample_id")), None) or lasermark
    by_area: dict[int, list[dict[str, Any]]] = {}
    for occurrence in found:
        mp = occurrence.microproject
        if mp.management_area_id is None:
            continue
        refs = by_area.setdefault(mp.management_area_id, [])
        ref = wafers.microproject_ref(mp)
        if ref not in refs:
            refs.append(ref)
    out = []
    for area_id, refs in by_area.items():
        try:
            area = areas.get_by_id(area_id)
        except NotFound:
            continue
        if not getattr(area, "is_system", False):
            out.append((area, refs))
    return name.strip(), out


def _block_payload(block: Block, found: dict[str, Any] | None, *, wafer: str, hook_titles: dict[str, str]) -> dict[str, Any]:
    payload = (found or {}).get("payload")
    status = found["status"] if found else "pending"
    out = {
        "id": block.id,
        "kind": block.kind,
        "kind_label": blocks_mod.KINDS[block.kind],
        "title": block.title,
        "label": block.label,
        "hook": block.hook,
        "hook_title": hook_titles.get(block.hook, block.hook),
        "unit": block.unit,
        "config": block.config,
        "status": status,
        "message": (found or {}).get("message", ""),
        "computed_at": (found or {}).get("computed_at"),
        "data": payload,
    }
    if block.kind == "images" and payload:
        out["data"] = {
            **{k: v for k, v in payload.items() if k != "images"},
            "images": [
                {"name": image["name"], "url": f"/api/wafers/{wafer}/data/images/{block.id}/{i}"} for i, image in enumerate(payload.get("images", []))
            ],
        }
    if block.kind == "value" and payload and status == "ok":
        out["population"] = store.population(block.sig, payload["value"])
    return out


def sheet(user: User, lasermark: str, *, refresh: bool = False) -> dict[str, Any]:
    """La fiche data d'une plaque - voir le docstring du module."""
    key = wafers.wafer_key(lasermark)
    name, found_areas = wafer_areas(user, lasermark)
    by_area = blocks_mod.blocks_by_area([area.id for area, _ in found_areas])
    every = [block for area, _ in found_areas for block in by_area.get(area.id, [])]
    stored = store.read(key, list({b.sig for b in every}))
    stale = [b for b in every if refresh or _stale(stored.get(b.sig), b)]
    retry = {(key, b.sig) for b in stale if stored.get(b.sig, {}).get("status") == "empty"}
    unique = {b.sig: b for b in stale}
    line = tracking.line_facts([key]) if any(b.kind == "images" for b in unique.values()) else {}
    computed, sources = compute([(key, name, b) for b in unique.values()], refresh=refresh, line=line, retry=retry) if unique else ({}, set())
    for (_, sig), result in computed.items():
        stored[sig] = result
    for found in stored.values():
        if found.get("payload") and found["payload"].get("source"):
            sources.add(found["payload"]["source"])
    hook_titles = {h.hook: h.title for h in blocks_mod.catalog()} if every else {}
    return {
        "wafer": {"key": key, "lasermark": name},
        "source": sorted(sources)[0] if len(sources) == 1 else ("mixed" if sources else None),
        "areas": [
            {
                "area": {"slug": area.slug, "name": area.name},
                "can_manage": areas.can_manage(user, area),
                "microprojects": refs,
                "blocks": [_block_payload(b, stored.get(b.sig), wafer=key, hook_titles=hook_titles) for b in by_area.get(area.id, [])],
            }
            for area, refs in found_areas
        ],
    }


def image_file(user: User, lasermark: str, block_id: int, index: int):
    """Le fichier d'une image d'un bloc, tel que gardé dans son résumé - jamais un chemin venu de la requête -,
    revérifié sous les dossiers autorisés à chaque lecture."""
    key = wafers.wafer_key(lasermark)
    _, found_areas = wafer_areas(user, lasermark)
    block = next((b for area, _ in found_areas for b in blocks_mod.blocks_by_area([area.id]).get(area.id, []) if b.id == block_id), None)
    if block is None or block.kind != "images":
        raise NotFound("Bloc d'images inconnu pour cette plaque.")
    found = store.read(key, [block.sig]).get(block.sig)
    images = (found or {}).get("payload", {}).get("images", [])
    if not 0 <= index < len(images):
        raise NotFound("Image inconnue.")
    return external_images.readable_file(images[index]["path"])


# --- le calcul d'avance d'un projet -----------------------------------------------------------------


def compute_area(area: ManagementArea, user: User, *, offset: int = 0, refresh: bool = False) -> dict[str, Any]:
    """Calcule les fiches d'un paquet de plaques du projet (:data:`BATCH`, à partir de ``offset``) : celles qui
    manquent, ou toutes avec ``refresh``. La page enchaîne les paquets (``next_offset``) en montrant l'avancée."""
    all_wafers = list(tracked_wafers(area, user).items())
    chunk = all_wafers[offset : offset + BATCH]
    area_blocks = [b for b in blocks_mod.list_blocks(area) if b.kind != "images"]
    pending, retry = [], set()
    for key, wafer in chunk:
        stored = store.read(key, [b.sig for b in area_blocks])
        for block in area_blocks:
            if refresh or _stale(stored.get(block.sig), block):
                pending.append((key, wafer["wafer"], block))
                if stored.get(block.sig, {}).get("status") == "empty":
                    retry.add((key, block.sig))
    results, sources = compute(pending, refresh=refresh, line={}, retry=retry) if pending else ({}, set())
    errors = sorted({r["message"] for r in results.values() if r["status"] == "error"})
    done = offset + len(chunk)
    return {
        "total": len(all_wafers),
        "done": done,
        "next_offset": done if done < len(all_wafers) else None,
        "computed": sum(1 for r in results.values() if r["status"] != "error"),
        "errors": errors[:5],
        "source": sorted(sources)[0] if len(sources) == 1 else ("mixed" if sources else None),
    }
