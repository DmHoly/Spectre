"""Fabriques de structures (plugin structures) : un dict par type d'étape, la même forme que
structure-builder.js envoie (voir spectre/plugins/structures/static/builder/step-kinds.js) - comme
les fabriques de scripts/seed_demo.py."""

from __future__ import annotations

from typing import Any

from .attachments import upload_file
from .http import assert_ok


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


def fixed_step_id(n: int) -> str:
    """Le n-ième id d'étape des tests (``st_00000001``...) - un id bien formé, comme ceux que le
    serveur donne (le constructeur renvoie ceux qu'il a reçus)."""
    return f"st_{n:08x}"


def identified(process_steps: list[dict]) -> list[dict]:
    """``process_steps``, chaque étape portant son id (``fixed_step_id(1)``, ``(2)``... dans l'ordre)."""
    return [{"id": fixed_step_id(i + 1), **step} for i, step in enumerate(process_steps)]


def steps(thickness_nm: float = 20) -> list[dict]:
    """Le procédé par défaut des tests : une seule couche d'oxyde (id ``fixed_step_id(1)``)."""
    return identified([deposition(thickness_nm=thickness_nm)])


def campaign_plan(values: list, *, step_id: str = fixed_step_id(1), field: str = "thickness", **factor: Any) -> dict:
    """Un plan de campagne à un seul facteur - par défaut l'épaisseur de la première étape
    (``step_id`` : l'id de l'étape, ``"substrate"`` pour le substrat)."""
    return {"factors": [{"step_id": step_id, "field": field, "values": list(values), **factor}]}


def layer_label(text: str = "", *values: str) -> dict:
    """L'étiquette de couche d'une étape : son texte (vide : le matériau) et les valeurs écrites
    dessous (``"thickness"``, ``"composition"``, ``"declared:<nom>"``)."""
    return {"text": text, "values": list(values)}


def label_texts(svg: str) -> list[str]:
    """Les textes des étiquettes de couches d'un SVG, dans l'ordre où elles sont dessinées."""
    import re

    labels = re.search(r'<g class="sp-layer-labels"[^>]*>(.*)</g></svg>$', svg, re.S)
    return re.findall(r"<text[^>]*>([^<]*)</text>", labels.group(1)) if labels else []


def simulate(client: Any, body: dict) -> Any:
    """POST /api/simulations, tel quel (la réponse, pour en vérifier un refus)."""
    return client.post("/api/simulations", json=body)


def preview_campaign(client: Any, body: dict) -> Any:
    """POST /api/campaign-previews, tel quel (la réponse, pour en vérifier un refus)."""
    return client.post("/api/campaign-previews", json=body)


def list_materials(client: Any) -> list[dict]:
    return assert_ok(client.get("/api/materials"))


def list_recipes(client: Any) -> dict:
    return assert_ok(client.get("/api/recipes"))


def upload_structure_image(client: Any, slug: str, name: str = "schema.png") -> str:
    """Envoie une image de structure (POST .../attachments, purpose=structure) - renvoie son id."""
    return upload_file(client, slug, "structure", name)["id"]
