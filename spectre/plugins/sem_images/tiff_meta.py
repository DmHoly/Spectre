"""Ce qu'un TIF du G4 (SEMVision) dit de lui-même, lu dans ses balises texte - sans lire l'image :

- ``ImageDescription`` (270) : champ de vue en µm (``Field-Of-View``), position sur le wafer (``Wafer-Location``),
  tension (``Vacc``), inclinaison ;
- ``NewAdditionalInformation`` (34737) : les attributs du défaut revu (``waferID``, ``defectID``, ``lotID``,
  ``class``, ``dieLocX/Y``, ``die: 2,0``) et la date d'acquisition (``mDate``, en secondes Unix).

Ces balises sont un YAML maison (indentation de deux espaces, listes ``[0]: ...``) : :func:`parse_block` les lit
en dictionnaires imbriqués, sans dépendance. Un TIF qui n'a pas ces balises (autre microscope) rend simplement
moins de champs.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

IMAGE_DESCRIPTION = 270
NEW_ADDITIONAL_INFORMATION = 34737


def parse_block(text: str) -> dict[str, Any]:
    """``clé: valeur`` indentés -> dictionnaires imbriqués (une clé sans valeur ouvre un niveau)."""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in (text or "").splitlines():
        if not raw.strip() or ":" not in raw:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        key, _, value = raw.strip().partition(":")
        key, value = key.strip().strip('"'), value.strip().strip('"')
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1] if stack else root
        if value:
            parent[key] = value
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
    return root


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pair(node: Any) -> tuple[float | None, float | None]:
    if not isinstance(node, dict):
        return None, None
    return _number(node.get("mX")), _number(node.get("mY"))


def attributes(info: dict[str, Any]) -> dict[str, str]:
    """La liste ``mImageAttributesList`` (``"waferID: "``, ``27CYH1G6MMB2``, ..., ``"die: 2,0"``) en dictionnaire."""
    node = info.get("NewAdditionalInformation", {}).get("mImageAttributesList", {})
    items = [node[k] for k in sorted((k for k in node if re.fullmatch(r"\[\d+\]", k)), key=lambda k: int(k[1:-1]))]
    found: dict[str, str] = {}
    pending: str | None = None
    for item in items:
        text = str(item).strip()
        if pending is not None:
            found[pending] = text
            pending = None
        elif text.endswith(":"):
            pending = text[:-1].strip()
        elif ":" in text:
            key, _, value = text.partition(":")
            found[key.strip()] = value.strip()
    return found


def describe(tags: dict[int, Any], size: tuple[int, int], frames: int) -> dict[str, Any]:
    """Les métadonnées utiles d'un TIF à partir de ses balises (``{numéro: valeur}``), de sa taille en pixels et de
    son nombre de trames (une par détecteur)."""
    description = parse_block(str(tags.get(IMAGE_DESCRIPTION) or "")).get("ImageDescription", {})
    extra = parse_block(str(tags.get(NEW_ADDITIONAL_INFORMATION) or ""))
    attrs = attributes(extra)
    fov_x, fov_y = _pair(description.get("Field-Of-View"))
    loc_x, loc_y = _pair(description.get("Wafer-Location"))
    params = description.get("Image-Parameters", {}) if isinstance(description.get("Image-Parameters"), dict) else {}
    width, height = size
    acquired = _number(extra.get("NewAdditionalInformation", {}).get("mDate"))
    die = attrs.get("die")
    return {
        "width": width,
        "height": height,
        "frames": frames,
        "fov_um": [fov_x, fov_y] if fov_x else None,
        "pixel_um": (fov_x / width) if fov_x and width else None,
        "location_um": [loc_x, loc_y] if loc_x is not None and loc_y is not None else None,
        "die_location_um": [_number(attrs.get("dieLocX")), _number(attrs.get("dieLocY"))] if "dieLocX" in attrs else None,
        "die_index": die.replace(" ", "") if die else None,
        "defect_id": attrs.get("defectID"),
        "defect_class": attrs.get("class"),
        "wafer_id": attrs.get("waferID"),
        "lot_id": attrs.get("lotID"),
        "kv": (_number(params.get("Vacc")) or 0) / 1000 or None,
        "tilt": _number(params.get("Tilt")),
        "image_type": description.get("Image-Type"),
        "acquired": datetime.fromtimestamp(acquired, tz=timezone.utc).isoformat(timespec="seconds") if acquired else None,
    }
