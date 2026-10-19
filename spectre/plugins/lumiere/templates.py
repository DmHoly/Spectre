"""Les modèles de rapport : une liste de **slides**, chacune une slide spéciale (titre, section, sommaire) ou une
**grille** (``nrows`` × ``ncols``) dont chaque cellule porte un bloc du catalogue (:mod:`.blocks`) avec ses options.
Un modèle déclare son **contexte** (``wafer`` : une plaque) : c'est ce qui dit où il apparaît et quels blocs il peut
poser. Spectre en livre un (:data:`BUILTIN`, non modifiable - il se copie) ; les autres vivent dans la table
``lumiere_templates``, visibles de tous, modifiés par leur auteur ou un administrateur (un modèle ne donne accès
à rien : la génération vérifie les droits du contexte).

La forme d'une slide, telle que l'éditeur l'envoie et que la table la garde :

    {"kind": "title"}                                   {"kind": "section", "title": "...", "subtitle": "..."}
    {"kind": "summary"}
    {"kind": "grid", "title": "...", "nrows": 1, "ncols": 2, "row_heights": ["1fr"], "col_widths": ["1fr", "1fr"],
     "cells": [{"r": 0, "c": 0, "rowspan": 1, "colspan": 1, "block": {"type": "data.maps", "options": {...}}}]}

:func:`build` en fait un ``ReportBuilder`` Lumière pour un contexte ; :func:`preview` rend une seule slide."""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ...kernel.db import get_conn
from ...kernel.errors import Forbidden, InvalidInput, NotFound
from ..accounts.service import User
from . import blocks as block_types
from . import context as contexts
from . import engine

CONTEXTS = {"wafer": "une plaque"}
SLIDE_KINDS = ("title", "section", "summary", "grid")
MAX_SLIDES = 40
MAX_GRID = 3
MAX_NAME = 80
MAX_DESCRIPTION = 500
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,59}$")


@dataclass(frozen=True)
class Template:
    key: str
    name: str
    description: str
    context: str
    slides: tuple[dict[str, Any], ...]
    builtin: bool = False
    owner_id: int | None = None
    owner_name: str = ""
    updated_at: str = ""

    @property
    def outline(self) -> list[str]:
        """Ce que le rapport contient, slide par slide, en mots."""
        names = {"title": "Titre", "section": "Section", "summary": "Sommaire"}
        out = []
        for slide in self.slides:
            if slide["kind"] != "grid":
                out.append(slide.get("title") or names[slide["kind"]])
            else:
                out.append(slide.get("title") or ", ".join(block_types.BLOCKS[c["block"]["type"]].label for c in slide["cells"] if c["block"]["type"] in block_types.BLOCKS) or "Slide")
        return out

    def payload(self) -> dict[str, Any]:
        return {
            "key": self.key, "name": self.name, "description": self.description, "context": self.context,
            "slides": list(self.slides), "outline": self.outline, "builtin": self.builtin,
            "owner_id": self.owner_id, "owner_name": self.owner_name, "updated_at": self.updated_at,
        }


def grid(title: str, cells: list[tuple[int, int, str, dict[str, Any]]], nrows: int = 1, ncols: int = 1, **extra: Any) -> dict[str, Any]:
    return {"kind": "grid", "title": title, "nrows": nrows, "ncols": ncols, **extra, "cells": [{"r": r, "c": c, "rowspan": 1, "colspan": 1, "block": {"type": t, "options": o}} for r, c, t, o in cells]}


BUILTIN: dict[str, Template] = {
    "fiche-plaque": Template(
        key="fiche-plaque",
        name="Fiche plaque",
        description="Tout ce que Spectre sait d'une plaque, en slides : son contexte (études, notes), sa frise des mesures, sa vie en ligne (MES, FDL JIRA, tests), ses données de caractérisation (cartes et distributions), ses images MEB du G4.",
        context="wafer",
        builtin=True,
        slides=(
            {"kind": "title"},
            grid("Contexte", [(0, 0, "context.facts", {"studies": True, "notes": True})]),
            grid("Frise des mesures", [(0, 0, "wafer.timeline", {})]),
            grid("Vie en ligne", [(0, 0, "wafer.tracking", {})]),
            grid("EQE - cartes et distributions", [(0, 0, "data.maps", {"hook": "eqe", "max_columns": 8}), (0, 1, "data.boxes", {"hook": "eqe", "max_columns": 6})], ncols=2, col_widths=["1.4fr", "1fr"]),
            grid("PL - cartes", [(0, 0, "data.maps", {"hook": "pl", "max_columns": 8})]),
            grid("Images MEB - G4", [(0, 0, "sem.gallery", {"max": 24, "step": ""})]),
            {"kind": "summary"},
        ),
    ),
}


# --- la vérification d'un modèle ----------------------------------------------------------------------------


def _fractions(values: Any, n: int, label: str) -> list[str]:
    if not values:
        return ["1fr"] * n
    if not isinstance(values, list) or len(values) != n:
        raise InvalidInput(f"{label} : {n} valeur(s) attendue(s).", code="invalid_grid")
    out = []
    for v in values:
        text = str(v).strip()
        if not re.fullmatch(r"\d+(\.\d+)?fr", text):
            raise InvalidInput(f"{label} : « {text} » n'est pas une fraction (1fr, 1.5fr).", code="invalid_grid")
        out.append(text)
    return out


def clean_slides(raw: Any, context: str) -> list[dict[str, Any]]:
    """Les slides d'un modèle, vérifiées : genres connus, grilles bornées, cellules dans la grille et sans
    chevauchement, blocs du catalogue pour ce contexte avec leurs options nettoyées (422 sinon)."""
    if not isinstance(raw, list) or not raw:
        raise InvalidInput("Un modèle a au moins une slide.", code="no_slides")
    if len(raw) > MAX_SLIDES:
        raise InvalidInput(f"Un modèle fait {MAX_SLIDES} slides au plus.", code="too_many_slides")
    out: list[dict[str, Any]] = []
    for i, slide in enumerate(raw, start=1):
        if not isinstance(slide, dict) or slide.get("kind") not in SLIDE_KINDS:
            raise InvalidInput(f"Slide {i} : genre inconnu.", code="invalid_slide")
        kind = slide["kind"]
        title = " ".join(str(slide.get("title") or "").split())[:MAX_NAME]
        if kind in ("title", "summary"):
            out.append({"kind": kind})
            continue
        if kind == "section":
            if not title:
                raise InvalidInput(f"Slide {i} : une section a un titre.", code="invalid_slide")
            out.append({"kind": "section", "title": title, "subtitle": " ".join(str(slide.get("subtitle") or "").split())[:MAX_NAME]})
            continue
        try:
            nrows, ncols = int(slide.get("nrows") or 1), int(slide.get("ncols") or 1)
        except (TypeError, ValueError):
            raise InvalidInput(f"Slide {i} : grille invalide.", code="invalid_grid") from None
        if not (1 <= nrows <= MAX_GRID and 1 <= ncols <= MAX_GRID):
            raise InvalidInput(f"Slide {i} : une grille fait de 1×1 à {MAX_GRID}×{MAX_GRID}.", code="invalid_grid")
        cells_raw = slide.get("cells") or []
        if not isinstance(cells_raw, list):
            raise InvalidInput(f"Slide {i} : cellules invalides.", code="invalid_grid")
        taken: set[tuple[int, int]] = set()
        cells = []
        for cell in cells_raw:
            if not isinstance(cell, dict) or not isinstance(cell.get("block"), dict):
                raise InvalidInput(f"Slide {i} : une cellule porte un bloc.", code="invalid_cell")
            try:
                r, c = int(cell.get("r", 0)), int(cell.get("c", 0))
                rs, cs = max(1, int(cell.get("rowspan") or 1)), max(1, int(cell.get("colspan") or 1))
            except (TypeError, ValueError):
                raise InvalidInput(f"Slide {i} : cellule invalide.", code="invalid_cell") from None
            if not (0 <= r < nrows and 0 <= c < ncols and r + rs <= nrows and c + cs <= ncols):
                raise InvalidInput(f"Slide {i} : une cellule sort de la grille {nrows}×{ncols}.", code="invalid_cell")
            spots = {(r + dr, c + dc) for dr in range(rs) for dc in range(cs)}
            if spots & taken:
                raise InvalidInput(f"Slide {i} : deux blocs occupent la même cellule.", code="invalid_cell")
            taken |= spots
            block = block_types.get(str(cell["block"].get("type") or ""))
            if context not in block.contexts:
                raise InvalidInput(f"Slide {i} : le bloc « {block.label} » ne s'applique pas à {CONTEXTS.get(context, context)}.", code="block_wrong_context")
            cells.append({"r": r, "c": c, "rowspan": rs, "colspan": cs, "block": {"type": block.key, "options": block.clean_options(cell["block"].get("options"))}})
        cells.sort(key=lambda x: (x["r"], x["c"]))
        out.append({
            "kind": "grid", "title": title or f"Slide {i}", "nrows": nrows, "ncols": ncols,
            "row_heights": _fractions(slide.get("row_heights"), nrows, "Hauteurs des lignes"),
            "col_widths": _fractions(slide.get("col_widths"), ncols, "Largeurs des colonnes"),
            "cells": cells,
        })
    return out


def _clean_name(value: Any) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise InvalidInput("Donnez un nom au modèle.", code="missing_name")
    if len(name) > MAX_NAME:
        raise InvalidInput(f"Un nom fait {MAX_NAME} caractères au plus.", code="name_too_long")
    return name


def _slug(name: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return (text or "modele")[:50]


# Les modèles livrés passent par la même vérification que les autres : leurs slides ont la forme complète.
BUILTIN = {key: dataclasses.replace(t, slides=tuple(clean_slides(list(t.slides), t.context))) for key, t in BUILTIN.items()}


# --- la table -----------------------------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_row(row: Any) -> Template:
    return Template(
        key=row["key"], name=row["name"], description=row["description"], context=row["context"],
        slides=tuple(json.loads(row["slides"])), builtin=False, owner_id=row["owner_id"], owner_name=row["owner_name"] or "", updated_at=row["updated_at"],
    )


_SELECT = "SELECT t.*, u.name AS owner_name FROM lumiere_templates t LEFT JOIN users u ON u.id = t.owner_id"


def for_context(context: str | None = None) -> list[Template]:
    """Les modèles livrés puis les modèles enregistrés (les plus récents d'abord), d'un contexte ou de tous."""
    found = [t for t in BUILTIN.values() if context is None or t.context == context]
    with get_conn() as conn:
        rows = conn.execute(_SELECT + (" WHERE t.context = ?" if context else "") + " ORDER BY t.updated_at DESC", (context,) if context else ()).fetchall()
    return found + [_from_row(r) for r in rows]


def get(key: str) -> Template:
    if key in BUILTIN:
        return BUILTIN[key]
    with get_conn() as conn:
        row = conn.execute(_SELECT + " WHERE t.key = ?", (key,)).fetchone()
    if row is None:
        raise NotFound(f"Modèle de rapport inconnu : {key!r}.", code="unknown_template")
    return _from_row(row)


def _editable(user: User, template: Template) -> Template:
    if template.builtin:
        raise Forbidden("Un modèle livré avec Spectre ne se modifie pas : copiez-le.", code="builtin_template")
    if template.owner_id != user.id and not user.is_admin:
        raise Forbidden("Ce modèle n'est pas le vôtre.", code="not_template_owner")
    return template


def create(user: User, body: dict[str, Any]) -> Template:
    """Un nouveau modèle : ``name``, ``description``, ``context`` et ``slides`` - ou ``copy_of`` (la clé d'un
    modèle dont on part, livré ou non), dont les slides remplacent celles qu'on n'a pas données."""
    source = get(str(body["copy_of"])) if body.get("copy_of") else None
    context = str(body.get("context") or (source.context if source else "wafer"))
    if context not in CONTEXTS:
        raise InvalidInput(f"Contexte inconnu : {context!r}.", code="unknown_context")
    name = _clean_name(body.get("name") or (f"{source.name} (copie)" if source else ""))
    description = " ".join(str(body.get("description") or (source.description if source else "")).split())[:MAX_DESCRIPTION]
    slides = clean_slides(body.get("slides") if body.get("slides") is not None else (list(source.slides) if source else [{"kind": "title"}, {"kind": "summary"}]), context)
    base = _slug(name)
    with get_conn() as conn:
        key, n = base, 2
        while key in BUILTIN or conn.execute("SELECT 1 FROM lumiere_templates WHERE key = ?", (key,)).fetchone():
            key, n = f"{base}-{n}", n + 1
        now = _now()
        conn.execute(
            "INSERT INTO lumiere_templates (key, name, description, context, slides, owner_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (key, name, description, context, json.dumps(slides, ensure_ascii=False), user.id, now, now),
        )
    return get(key)


def update(user: User, key: str, body: dict[str, Any]) -> Template:
    template = _editable(user, get(key))
    name = _clean_name(body["name"]) if "name" in body else template.name
    description = " ".join(str(body["description"] or "").split())[:MAX_DESCRIPTION] if "description" in body else template.description
    slides = clean_slides(body["slides"], template.context) if "slides" in body else list(template.slides)
    with get_conn() as conn:
        conn.execute("UPDATE lumiere_templates SET name = ?, description = ?, slides = ?, updated_at = ? WHERE key = ?", (name, description, json.dumps(slides, ensure_ascii=False), _now(), key))
    return get(key)


def delete(user: User, key: str) -> None:
    _editable(user, get(key))
    with get_conn() as conn:
        conn.execute("DELETE FROM lumiere_templates WHERE key = ?", (key,))


# --- le rendu ------------------------------------------------------------------------------------------------


def _slide(lumiere: Any, ctx: Any, slide: dict[str, Any]) -> Any:
    kind = slide["kind"]
    if kind == "title":
        return lumiere.TitleSlide()
    if kind == "summary":
        return lumiere.SummarySlide()
    if kind == "section":
        return lumiere.SectionSlide(slide["title"], slide.get("subtitle") or "")
    made = lumiere.Slide(slide["title"], nrows=slide["nrows"], ncols=slide["ncols"], row_heights=list(slide.get("row_heights") or []) or None, col_widths=list(slide.get("col_widths") or []) or None)
    for cell in slide["cells"]:
        block = block_types.get(cell["block"]["type"])
        try:
            rendered = block.render(ctx, block.clean_options(cell["block"].get("options")), lumiere)
        except Exception as exc:  # noqa: BLE001 - un bloc qui casse ne fait pas tomber le rapport : il le dit
            rendered = engine.html_block(f"<p><em>Bloc « {block_types.esc(block.label)} » : {block_types.esc(str(exc))}</em></p>", title=block.label)
        if slide["nrows"] == 1 and slide["ncols"] == 1:
            made.add(rendered)
        else:
            made[cell["r"], cell["c"]].add(rendered, rowspan=cell.get("rowspan", 1), colspan=cell.get("colspan", 1))
    return made


def build(user: User, template: Template, context_key: str, *, only: int | None = None) -> Any:
    """Le ``ReportBuilder`` (mode slide) d'un modèle pour un contexte ; ``only`` : une seule slide (l'aperçu)."""
    lumiere = engine.load()
    ctx = contexts.make(user, template.context, context_key)
    report = lumiere.ReportBuilder(title=ctx.title, subtitle=f"{template.name} - Spectre", author=user.name or user.email, mode="slide")
    chosen = list(template.slides) if only is None else [template.slides[only]]
    report.add(lumiere.SlideView([_slide(lumiere, ctx, s) for s in chosen]))
    return report


def preview(user: User, context: str, slides: Any, index: int, context_key: str) -> str:
    """Le HTML d'une seule slide (``index``) d'un modèle en cours d'édition, rendu sur ``context_key``."""
    cleaned = clean_slides(slides, context)
    if not 0 <= index < len(cleaned):
        raise InvalidInput("Cette slide n'existe pas.", code="no_such_slide")
    draft = Template(key="apercu", name="Aperçu", description="", context=context, slides=tuple(cleaned))
    return build(user, draft, context_key, only=index).render()
