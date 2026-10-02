"""Fabriques de structures (plugin structures) : un dict par type d'étape, la même forme que
structure-builder.js envoie (voir spectre/api/static/js/structure-builder/step-kinds.js) - comme
les fabriques de scripts/seed_demo.py."""

from __future__ import annotations

from typing import Any

from .http import PNG_1PX, assert_created


def length(value: float, unit: str = "nm") -> dict:
    return {"value": value, "unit": unit}


def substrate(material: str = "Si", *, width_nm: float = 200, thickness_nm: float = 50) -> dict:
    return {"material": material, "domain_width": length(width_nm), "thickness": length(thickness_nm)}


def deposition(name: str = "Oxyde", material: str = "SiO2", *, recipe: str = "CVD Conformal", thickness_nm: float = 20) -> dict:
    return {"kind": "deposition", "name": name, "material": material, "recipe": recipe, "thickness": length(thickness_nm)}


def etch(name: str = "Gravure", *, recipe: str = "Anisotropic RIE", depth_nm: float = 10) -> dict:
    return {"kind": "etch", "name": name, "recipe": recipe, "depth": length(depth_nm)}


def lithography(name: str, resist: str = "Photoresist", *, thickness_nm: float, openings: list) -> dict:
    return {"kind": "lithography", "name": name, "resist_material": resist, "thickness": length(thickness_nm), "openings": list(openings)}


def steps(thickness_nm: float = 20) -> list[dict]:
    """Le procédé par défaut des tests : une seule couche d'oxyde."""
    return [deposition(thickness_nm=thickness_nm)]


def campaign_plan(values: list, *, step_index: int = 0, field: str = "thickness", **factor: Any) -> dict:
    """Un plan de campagne à un seul facteur - par défaut l'épaisseur de la première étape."""
    return {"factors": [{"step_index": step_index, "field": field, "values": list(values), **factor}]}


def upload_structure_image(client: Any, slug: str, name: str = "schema.png") -> str:
    """Envoie une image de structure (POST /structures/images) - renvoie son ``image_id``."""
    response = client.post(f"/api/microprojets/{slug}/structures/images", files={"file": (name, PNG_1PX, "image/png")})
    return assert_created(response)["image_id"]
