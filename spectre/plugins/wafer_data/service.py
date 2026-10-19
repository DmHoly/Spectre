"""La fiche data d'une plaque : les blocs des projets corporate de ses µprojets, calculés sur elle.

Une plaque rattachée à un µprojet (une étude la suit) l'est à son projet corporate ; l'onglet « Data » de
sa page montre, pour chacun de ces projets, les blocs qu'il a configurés (:mod:`.blocks`). Une plaque sans
µprojet n'a pas de fiche data.

Ce qu'un bloc a calculé sur une plaque se garde, résumé (:mod:`.store`) ; on le relit tel quel, sauf :

- jamais calculé (ou oublié par le budget) : calculé, sur le cache par plaque de PRISM ;
- calculé **sans mesure** (``empty``) il y a plus de :data:`RETRY_EMPTY` : recalculé en retapant la base -
  une plaque pas encore mesurée l'est peut-être depuis (le cache de PRISM, lui, garde un vide pour toujours) ;
- des images d'un modèle de chemin listées il y a plus de :data:`RETRY_EMPTY` : relistées (un fichier a pu arriver) ;
- les images d'un type de données qu'un autre plugin sert (:func:`register_image_server` : les TIF du G4, rendus en
  vignette et en PNG par sem_images) ne passent pas par les images externes ;
- ``refresh`` (le bouton « Rafraîchir ») : tout est recalculé en retapant la base.

Chaque type de données n'est interrogé qu'une fois pour tous les blocs qui le lisent, d'un projet à l'autre ;
chaque lecture garde au passage le profil de ses colonnes (:func:`.columns.profile`) - ce qui type les colonnes
du catalogue d'après les vraies lignes. :func:`probe` lit un type sur des plaques du projet pour ça seulement.
Un type en échec (base injoignable) ne prive pas des autres : ses blocs portent l'erreur, rien n'est gardé.
:func:`compute_area` calcule d'avance les fiches de toutes les plaques d'un projet, par paquets - de quoi
situer chaque valeur parmi toutes les plaques du projet.
"""

from __future__ import annotations

from collections.abc import Callable

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
from . import columns as col_types
from . import store
from .blocks import Block, CatalogHook
from .digest import COMPUTE, WAFER_COLUMNS, round4

PROBE_WAFERS = 3

# D'autres plugins servent eux-mêmes les images de certains types de données - les TIF du G4 (hook ``meb_g4``),
# rendus en vignette et en PNG par sem_images - au lieu des images externes, qui servent les fichiers tels quels.
# Un tel plugin déclare, par type de données, la fonction qui donne (vignette, image entière) d'un chemin
# absolu pour une plaque, ou ``None`` quand elle ne le sert pas (hors de sa racine, plugin désactivé).
ImageUrls = Callable[[str, str], tuple[str, str] | None]
_IMAGE_SERVERS: dict[str, ImageUrls] = {}


def register_image_server(hook: str, urls: ImageUrls) -> None:
    _IMAGE_SERVERS[hook] = urls


def image_server(hook: str) -> ImageUrls | None:
    return _IMAGE_SERVERS.get(hook)

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
    if found["status"] == "empty" or block.from_pattern:
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
    source, columns, by_wafer, sample = "", [], {}, []
    for start in range(0, len(lasermarks), BATCH):
        result = characterization.query(hook, {characterization.WAFER_PARAMETER: lasermarks[start : start + BATCH]}, refresh=refresh)
        source, columns = result.source, result.columns
        sample.extend(result.rows[: col_types.SAMPLE_ROWS - len(sample)])
        for key, rows in _rows_by_wafer(result.columns, result.rows).items():
            by_wafer.setdefault(key, []).extend(rows)
    try:
        store.observe(hook, col_types.profile(columns, sample))
    except Exception:  # le profil n'est qu'un indice pour le catalogue : jamais au prix de la fiche
        log.exception("fiche data : profil des colonnes de %s non gardé", hook)
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


def _served(status: str, payload: dict[str, Any], hook: str = "") -> tuple[str, str]:
    """Les images d'une colonne : celles qu'on ne servira pas (hors des dossiers autorisés) sont comptées ;
    si aucune ne l'est, le bloc est en erreur (rien n'est gardé : la règle peut changer). Un type de données dont un
    autre plugin sert les images (:func:`register_image_server`) n'est pas soumis aux dossiers autorisés."""
    if status != "ok":
        return status, ""
    if image_server(hook) is not None:
        payload["blocked"] = 0
        return status, ""
    blocked = sum(1 for image in payload["images"] if not external_images.allowed(image["path"]))
    payload["blocked"] = blocked
    if blocked and blocked == len(payload["images"]):
        folder = payload["images"][0]["path"].replace("\\", "/").rpartition("/")[0]
        return "error", f"Ces images sont hors des dossiers autorisés pour les images externes (SPECTRE_EXTERNAL_IMAGE_ROOTS) : {folder}"
    return status, ""


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
        if block.from_pattern:
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
            if block.kind == "images":
                status, message = _served(status, payload, block.hook)
                if status == "error":
                    results[(key, block.sig)] = {"status": "error", "payload": None, "computed_at": None, "message": message}
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


def gather(wafers: list[tuple[str, str]], every: list[Block], *, refresh: bool = False) -> tuple[dict[str, dict[str, dict[str, Any]]], set[str]]:
    """Ce que les blocs ``every`` ont calculé sur chaque plaque ``(clé, nom)`` - relu du magasin, ou calculé
    (voir le docstring du module) : ``{clé: {signature: {status, payload, computed_at, message}}}`` et les
    sources lues."""
    unique = {b.sig: b for b in every}
    stored = {key: store.read(key, list(unique)) for key, _ in wafers}
    pending, retry = [], set()
    for key, name in wafers:
        for sig, block in unique.items():
            found = stored[key].get(sig)
            if refresh or _stale(found, block):
                pending.append((key, name, block))
                if (found or {}).get("status") == "empty":
                    retry.add((key, sig))
    patterned = [key for key, _, block in pending if block.from_pattern]
    line = tracking.line_facts(list(dict.fromkeys(patterned))) if patterned else {}
    computed, sources = compute(pending, refresh=refresh, line=line, retry=retry) if pending else ({}, set())
    for (key, sig), result in computed.items():
        stored[key][sig] = result
    for found in (f for per_wafer in stored.values() for f in per_wafer.values()):
        if found.get("payload") and found["payload"].get("source"):
            sources.add(found["payload"]["source"])
    return stored, sources


def source_of(sources: set[str]) -> str | None:
    return sorted(sources)[0] if len(sources) == 1 else ("mixed" if sources else None)


def free_block(index: int, kind: str, hook: str, config: dict[str, Any], label: str = "") -> Block:
    """Un bloc hors de tout projet (celui d'une analyse de plaques, plugin meta_analysis) : ``index`` lui tient
    lieu d'identifiant. Sa signature ne dépend que de ce qu'il lit - deux analyses qui lisent la même chose
    partagent leurs résumés - et une valeur ne s'y situe parmi aucune population."""
    return Block(index, blocks_mod.FREE_AREA, kind, hook, config, label, index, "")


def stored_image(block: Block, wafer_key: str, index: int):
    """Le fichier de la i-ème image d'un bloc sur une plaque, tel que gardé dans son résumé - jamais un chemin venu
    de la requête -, revérifié sous les dossiers autorisés à chaque lecture."""
    if block.kind != "images":
        raise NotFound("Ce bloc ne montre pas d'images.")
    found = store.read(wafer_key, [block.sig]).get(block.sig)
    images = (found or {}).get("payload", {}).get("images", [])
    if not 0 <= index < len(images):
        raise NotFound("Image inconnue.")
    return external_images.readable_file(images[index]["path"])


def block_payload(
    block: Block, found: dict[str, Any] | None, *, wafer: str, entries: dict[str, CatalogHook], image_url: Any = None
) -> dict[str, Any]:
    """Un bloc calculé sur une plaque, tel que la page le dessine ; ``image_url(i)`` : l'adresse de sa i-ème
    image (par défaut, celle de la fiche data de la plaque)."""
    payload = (found or {}).get("payload")
    status = found["status"] if found else "pending"
    entry = entries.get(block.hook)
    out = {
        "id": block.id,
        "kind": block.kind,
        "kind_label": blocks_mod.KINDS[block.kind],
        "title": block.title,
        "label": block.label,
        "hook": block.hook,
        "hook_title": entry.title if entry else block.hook,
        "unit": block.unit(entry),
        "units": {key: (entry.column(name) or {}).get("unit", "") for key in ("x", "y") if entry and (name := block.config.get(key))},
        "config": block.config,
        "status": status,
        "message": (found or {}).get("message", ""),
        "computed_at": (found or {}).get("computed_at"),
        "data": payload,
    }
    if block.kind == "images" and payload:
        url = image_url or (lambda i: f"/api/wafers/{wafer}/data/images/{block.id}/{i}")
        sem = _served_urls(block.hook, wafer, payload.get("images", []))
        out["data"] = {
            **{k: v for k, v in payload.items() if k != "images"},
            "images": [
                {
                    "name": image["name"],
                    "url": sem[i][0] if sem and sem[i] else url(i),
                    **({"full": sem[i][1]} if sem and sem[i] else {}),
                    "meta": image.get("meta", {}),
                    "g": image.get("g", 0),
                }
                for i, image in enumerate(payload.get("images", []))
            ],
        }
    if block.kind == "value" and payload and status == "ok" and block.area_id != blocks_mod.FREE_AREA:
        out["population"] = store.population(block.sig, payload["value"])
    return out


def _served_urls(hook: str, wafer: str, images: list[dict[str, Any]]) -> list[tuple[str, str] | None] | None:
    """Les (vignette, image entière) des images d'un type de données qu'un autre plugin sert
    (:func:`register_image_server`) ; ``None`` sans un tel plugin, ou pour une image qu'il ne sert pas (l'adresse
    ordinaire, qui dira alors que l'image n'est pas servie)."""
    urls = image_server(hook)
    if urls is None:
        return None
    try:
        return [urls(wafer, image["path"]) for image in images]
    except DomainError as exc:
        log.info("images %s de %s non servies : %s", hook, wafer, exc)
        return None


def sheet(user: User, lasermark: str, *, refresh: bool = False) -> dict[str, Any]:
    """La fiche data d'une plaque - voir le docstring du module."""
    key = wafers.wafer_key(lasermark)
    name, found_areas = wafer_areas(user, lasermark)
    by_area = blocks_mod.blocks_by_area([area.id for area, _ in found_areas])
    every = [block for area, _ in found_areas for block in by_area.get(area.id, [])]
    gathered, sources = gather([(key, name)], every, refresh=refresh)
    stored = gathered[key]
    entries = {h.hook: h for h in blocks_mod.catalog()} if every else {}
    return {
        "wafer": {"key": key, "lasermark": name},
        "source": source_of(sources),
        "areas": [
            {
                "area": {"slug": area.slug, "name": area.name},
                "can_manage": areas.can_manage(user, area),
                "microprojects": refs,
                "blocks": [block_payload(b, stored.get(b.sig), wafer=key, entries=entries) for b in by_area.get(area.id, [])],
            }
            for area, refs in found_areas
        ],
    }


def image_file(user: User, lasermark: str, block_id: int, index: int):
    """Le fichier d'une image d'un bloc de la fiche d'une plaque (voir :func:`stored_image`)."""
    _, found_areas = wafer_areas(user, lasermark)
    block = next((b for area, _ in found_areas for b in blocks_mod.blocks_by_area([area.id]).get(area.id, []) if b.id == block_id), None)
    if block is None or block.kind != "images":
        raise NotFound("Bloc d'images inconnu pour cette plaque.")
    return stored_image(block, wafers.wafer_key(lasermark), index)


# --- le calcul d'avance d'un projet -----------------------------------------------------------------


def compute_area(area: ManagementArea, user: User, *, offset: int = 0, refresh: bool = False) -> dict[str, Any]:
    """Calcule les fiches d'un paquet de plaques du projet (:data:`BATCH`, à partir de ``offset``) : celles qui
    manquent, ou toutes avec ``refresh``. La page enchaîne les paquets (``next_offset``) en montrant l'avancée."""
    all_wafers = list(tracked_wafers(area, user).items())
    chunk = all_wafers[offset : offset + BATCH]
    area_blocks = [b for b in blocks_mod.list_blocks(area) if not b.from_pattern]
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
        "source": source_of(sources),
    }


# --- les colonnes d'un type de données ----------------------------------------------------------------


def probe(area: ManagementArea | None, user: User, hook: str, *, lasermark: str | None = None) -> CatalogHook:
    """Lit ``hook`` sur une plaque donnée ou sur quelques plaques du projet (:data:`PROBE_WAFERS`, celles
    que suivent ses µprojets ; sans projet, la plaque est requise) pour en observer les vraies colonnes et leurs types ; rend l'entrée du catalogue
    à jour. Passe par le cache de PRISM : une plaque déjà lue ne retape pas la base."""
    if blocks_mod.catalog_entry(hook) is None:
        raise NotFound(f"« {hook} » n'est pas un type de données PRISM par plaque.")
    if lasermark:
        names = [lasermark.strip()]
    elif area is not None:
        names = [w["wafer"] for w in tracked_wafers(area, user).values()][:PROBE_WAFERS]
    else:
        names = []
    if not names:
        raise InvalidInput("Aucune plaque suivie dans ce projet : indiquez une plaque sur laquelle lire les colonnes.", code="no_wafer_to_probe")
    _query(hook, names, False)
    return blocks_mod.catalog_entry(hook)
