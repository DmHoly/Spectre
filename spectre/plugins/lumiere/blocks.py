"""Les blocs qu'un modèle de rapport pose sur ses slides : chacun a une clé, un libellé, les contextes où il a un
sens, ses **options** (:class:`OptionSpec` : le formulaire de l'éditeur s'en déduit) et sa fonction de rendu
``render(ctx, options, lumiere) -> Block`` - un bloc Lumière (WaferMaps, WaferTrackingBlock...) ou du HTML que
Spectre produit lui-même (:func:`engine.html_block`). Ce que Lumière saura faire de lui-même un jour (ses
composants, SOCLE-DATA.md §2) remplacera ce catalogue bloc par bloc."""

from __future__ import annotations

import base64
import html
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from ...kernel.errors import InvalidInput
from ..sem_images import render as sem_render
from ..sem_images import service as sem_images
from ..wafer_data import blocks as wafer_data_blocks
from ..wafers import timeline, tracking
from . import engine
from .context import WaferContext

log = logging.getLogger(__name__)
esc = html.escape

MAX_TEXT = 8000
MAX_IMAGES = 60

CSS = """
<style>
.spectre-html{font-size:14px;line-height:1.45}
.spectre-facts{border-collapse:collapse;margin:8px 0 14px}
.spectre-facts th{text-align:left;padding:4px 14px 4px 0;color:#646e8c;font-weight:500;white-space:nowrap}
.spectre-facts td{padding:4px 0}
.spectre-table{border-collapse:collapse;width:100%;font-size:12.5px}
.spectre-table th,.spectre-table td{border-bottom:1px solid #e3e6ef;padding:4px 8px;text-align:left}
.spectre-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:6px 0 16px}
.spectre-gallery figure{margin:0}
.spectre-gallery img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px;background:#111}
.spectre-gallery figcaption{font-size:11.5px;color:#646e8c;margin-top:3px}
.spectre-html h3{font-size:15px;margin:14px 0 6px}
.spectre-html h3 small{color:#646e8c;font-weight:400}
.spectre-html h4{font-size:13px;margin:10px 0 2px;color:#646e8c}
.spectre-md p{margin:0 0 8px}
</style>"""


@dataclass(frozen=True)
class OptionSpec:
    key: str
    label: str
    kind: str  # text | textarea | number | bool | choice
    default: Any = None
    help: str = ""
    choices: str | tuple[tuple[str, str], ...] = ()  # fixes, ou le nom d'un fournisseur dynamique (CHOICES)
    min: int | None = None
    max: int | None = None

    def payload(self, ctx_kind: str) -> dict[str, Any]:
        choices = CHOICES[self.choices](ctx_kind) if isinstance(self.choices, str) else [{"value": v, "label": l} for v, l in self.choices]
        return {"key": self.key, "label": self.label, "kind": self.kind, "default": self.default, "help": self.help, "choices": choices, "min": self.min, "max": self.max}


@dataclass(frozen=True)
class BlockType:
    key: str
    label: str
    description: str
    contexts: tuple[str, ...]
    render: Callable[[Any, dict[str, Any], Any], Any]
    options: tuple[OptionSpec, ...] = ()
    group: str = "Plaque"
    needs: str = ""  # ce qu'il faut pour qu'il montre quelque chose

    def payload(self, ctx_kind: str) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "description": self.description, "group": self.group, "needs": self.needs, "options": [o.payload(ctx_kind) for o in self.options]}

    def clean_options(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        """Les options telles que le modèle les garde : vérifiées, réduites à celles du bloc (422 sinon)."""
        raw = dict(raw or {})
        out: dict[str, Any] = {}
        for spec in self.options:
            value = raw.get(spec.key, spec.default)
            if spec.kind in ("text", "textarea", "choice"):
                text = "" if value is None else str(value)
                if len(text) > MAX_TEXT:
                    raise InvalidInput(f"« {spec.label} » fait {MAX_TEXT} caractères au plus.", code="option_too_long")
                if spec.kind == "choice" and isinstance(spec.choices, tuple) and spec.choices and text not in {v for v, _ in spec.choices}:
                    raise InvalidInput(f"« {spec.label} » : valeur inconnue ({text!r}).", code="invalid_option")
                out[spec.key] = text
            elif spec.kind == "number":
                try:
                    number = int(value if value not in (None, "") else spec.default or 0)
                except (TypeError, ValueError):
                    raise InvalidInput(f"« {spec.label} » doit être un nombre.", code="invalid_option") from None
                if spec.min is not None:
                    number = max(spec.min, number)
                if spec.max is not None:
                    number = min(spec.max, number)
                out[spec.key] = number
            elif spec.kind == "bool":
                out[spec.key] = bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "oui", "on")
        return out


# --- les choix dynamiques ----------------------------------------------------------------------------


def _hooks(predicate: Callable[[wafer_data_blocks.CatalogHook], bool]) -> list[dict[str, str]]:
    return [{"value": h.hook, "label": h.title} for h in wafer_data_blocks.catalog() if predicate(h)]


CHOICES: dict[str, Callable[[str], list[dict[str, str]]]] = {
    "positional_hooks": lambda kind: _hooks(lambda h: bool(h.x and h.y)),
    "hooks": lambda kind: _hooks(lambda h: True),
}


# --- les blocs -------------------------------------------------------------------------------------------


def _text(ctx: Any, options: dict[str, Any], lumiere: Any) -> Any:
    return lumiere.Text(options.get("content") or "")


def _facts(ctx: WaferContext, options: dict[str, Any], lumiere: Any) -> Any:
    passport, life, plate_notes = ctx.passport, ctx.life, ctx.notes
    rows = [
        ("Lasermark", passport["lasermark"]),
        ("Runs d'épitaxie", ", ".join(passport.get("run_names") or []) or None),
        ("FDL", ", ".join(ctx.fdls) or None),
        ("Lot", passport.get("lot_name") or (life or {}).get("lot")),
        ("Dernier emplacement connu", passport.get("last_location")),
        ("µprojets", ", ".join(m.get("code") or m.get("name") or "" for m in passport.get("microprojects") or []) or None),
        ("Statut en ligne", (life or {}).get("status")),
    ]
    out = f'<table class="spectre-facts">{"".join(f"<tr><th>{esc(k)}</th><td>{esc(str(v))}</td></tr>" for k, v in rows if v)}</table>'
    studies = passport.get("occurrences") or []
    if options.get("studies", True):
        if studies:
            items = []
            for o in studies:
                exp = o.get("experiment") or {}
                mp = (exp.get("microproject") or {}).get("code") or (exp.get("microproject") or {}).get("name") or ""
                bits = [f"<strong>{esc(str(mp))}</strong>" if mp else "", esc(str(exp.get("title") or exp.get("id") or "étude")), esc(str(exp.get("status") or ""))]
                if o.get("variant"):
                    bits.append(f"variante {esc(str(o['variant']))}")
                if o.get("location"):
                    bits.append(f"rangée : {esc(str(o['location']))}")
                items.append(f"<li>{' · '.join(b for b in bits if b)}</li>")
            out += f"<h3>Études qui la suivent</h3><ul>{''.join(items)}</ul>"
        else:
            out += "<p><em>Aucune étude ne suit cette plaque.</em></p>"
    if options.get("notes", True) and plate_notes:
        written = [f"<h4>{esc(label)}</h4><p>{esc(str(plate_notes[key]))}</p>" for key, label in (("context", "Contexte"), ("hypothesis", "Hypothèse"), ("learnings", "Ce qu'on a compris")) if plate_notes.get(key)]
        if written:
            out += "<h3>Notes</h3>" + "".join(written)
    return engine.html_block(CSS + out, title="Contexte", subtitle="études, notes, identifiants")


def _timeline(ctx: WaferContext, options: dict[str, Any], lumiere: Any) -> Any:
    found = ctx.events
    counts = {k: sum(1 for e in found if e["kind"] == k) for k in timeline.KINDS}
    said = " · ".join(f"{n} {timeline.KINDS[k].lower()}" for k, n in counts.items() if n)
    return engine.html_block(CSS + timeline.svg(found, title=f"Frise de {ctx.name}"), title="Frise des mesures", subtitle=said or "aucun événement daté")


def _lower(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    return df


def _life_table(life: dict[str, Any] | None) -> str:
    if not life:
        return "<p><em>Vie en ligne non lue.</em></p>"
    rows = "".join(
        f"<tr><td>{esc(str(s.get('route') or ''))}</td><td>{esc(str(s.get('step') or ''))}{' · mesure' if s.get('measurement') else ''}</td>"
        f"<td>{esc(str(s.get('equipment') or ''))}</td><td>{esc(str(s.get('start') or ''))}</td><td>{esc(str(s.get('end_effective') or ''))}</td></tr>"
        for s in life.get("steps") or []
    )
    return f'<table class="spectre-table"><tr><th>Route</th><th>Action MES</th><th>Équipement</th><th>Début</th><th>Fin</th></tr>{rows}</table>' if rows else "<p><em>Aucune étape MES.</em></p>"


def _tracking(ctx: WaferContext, options: dict[str, Any], lumiere: Any) -> Any:
    """Le bloc de suivi de Lumière, nourri des tables que la source de Spectre lit (mêmes hooks PRISM, ou la
    démo) ; si ça échoue, le parcours MES en tableau."""
    try:
        from lumiere_report.blocks.wafer_tracking.tracker import WaferTrackingData

        frames = tracking.current_source().fetch(ctx.name)
        data = WaferTrackingData(
            lms=[ctx.name.upper()], mes=_lower(frames.mes), info=_lower(frames.epitaxy), wafer=frames.record,
            jira_wafer=_lower(frames.fdl_by_wafer), jira_lot=_lower(frames.fdl_by_lot), tests=_lower(frames.tests),
            fdl_steps=_lower(frames.fdl_steps), phases=dict(frames.phases), aliases={k.upper(): v.upper() for k, v in frames.aliases.items()},
        )
        return lumiere.WaferTrackingBlock(data, title=f"Suivi de {ctx.name}")
    except Exception as exc:  # noqa: BLE001 - le bloc Lumière n'a pas pu se nourrir
        log.info("rapport de %s : bloc de suivi Lumière indisponible (%s)", ctx.name, exc)
        return engine.html_block(CSS + _life_table(ctx.life), title="Vie en ligne", subtitle="MES")


def _frame(ctx: WaferContext, hook: str) -> tuple[Any, pd.DataFrame, str, list[str]] | str:
    """(type du catalogue, lignes scalaires, colonne plaque, colonnes scalaires) d'un type pour la plaque, ou le
    message qui dit ce qui manque."""
    entry = ctx.hook(hook)
    if entry is None:
        return f"Type de données inconnu : {hook!r}."
    result = ctx.data(hook)
    if result is None:
        return f"{entry.title} : non lu."
    if not result.rows:
        return f"{entry.title} : aucune ligne pour cette plaque."
    df = pd.DataFrame(result.rows, columns=result.columns)
    wafer_col = next((c for c in result.columns if c.lower() in wafer_data_blocks.WAFER_COLUMNS), None) or "wafername"
    scalars = []
    for c in entry.columns:
        name = c["name"]
        if name not in df.columns or name in (entry.x, entry.y) or not wafer_data_blocks.col_types.fits(c["type"], "number"):
            continue
        if df[name].map(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)).mean() > 0.8:
            scalars.append(name)
    if not scalars:
        return f"{entry.title} : aucune colonne scalaire à dessiner."
    return entry, df, wafer_col, scalars


def _maps(ctx: WaferContext, options: dict[str, Any], lumiere: Any) -> Any:
    found = _frame(ctx, options["hook"])
    if isinstance(found, str):
        return engine.html_block(CSS + f"<p><em>{esc(found)}</em></p>", title="Cartographies")
    entry, df, wafer_col, scalars = found
    if not (entry.x and entry.y):
        return engine.html_block(CSS + f"<p><em>{esc(entry.title)} : pas de positions (X, Y).</em></p>", title="Cartographies")
    cols = scalars[: options["max_columns"]]
    keep = [c for c in [wafer_col, entry.x, entry.y, *cols] if c in df.columns]
    df = df[keep].copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    result = ctx.data(options["hook"])
    return lumiere.WaferMaps(df, x_col=entry.x, y_col=entry.y, wafer_col=wafer_col, colormap_cols=cols, title=entry.title, subtitle=f"{len(df)} points · source {result.source}")


def _boxes(ctx: WaferContext, options: dict[str, Any], lumiere: Any) -> Any:
    found = _frame(ctx, options["hook"])
    if isinstance(found, str):
        return engine.html_block(CSS + f"<p><em>{esc(found)}</em></p>", title="Distributions")
    entry, df, wafer_col, scalars = found
    cols = scalars[: options["max_columns"]]
    df = df[[c for c in [wafer_col, *cols] if c in df.columns]].copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    metrics = {s: (s, (entry.column(s) or {}).get("unit", "")) for s in cols}
    return lumiere.SummaryBoxPlots(df, group_col=wafer_col, metrics=metrics, title=entry.title, subtitle="Une boîte par colonne scalaire")


def _gallery(ctx: WaferContext, options: dict[str, Any], lumiere: Any) -> Any:
    listing = ctx.sem_listing
    title = "Images MEB - G4"
    if isinstance(listing, str):
        return engine.html_block(CSS + f"<p><em>Images MEB non lues : {esc(listing)}</em></p>", title=title)
    groups = listing.get("groups") or []
    wanted = (options.get("step") or "").strip().upper()
    if wanted:
        groups = [g for g in groups if wanted in str(g.get("step") or "").upper()]
    if not groups:
        return engine.html_block(CSS + "<p><em>Aucune image du G4 trouvée pour cette plaque" + (f" à l'étape « {esc(wanted)} »" if wanted else "") + ".</em></p>", title=title)
    budget = options["max"]
    parts = []
    for group in groups:
        if budget <= 0:
            break
        thumbs = []
        for image in group["images"]:
            if budget <= 0:
                break
            try:
                path = sem_images.image_path(ctx.name, image["path"], lambda: [])
                body, _ = sem_render.thumbnail(path, 0)
            except Exception as exc:  # noqa: BLE001 - un TIF illisible ne fait pas tomber le rapport
                log.info("vignette %s : %s", image["path"], exc)
                continue
            src = "data:image/jpeg;base64," + base64.b64encode(body).decode("ascii")
            caption = f"die {image['die']}" if image.get("die") is not None else image["name"]
            thumbs.append(f'<figure><img src="{src}" alt="{esc(image["name"])}" loading="lazy"><figcaption>{esc(caption)}</figcaption></figure>')
            budget -= 1
        head = " · ".join(str(v) for v in (group.get("step"), group.get("fdl"), group.get("process"), group.get("area_label")) if v)
        parts.append(f"<h3>{esc(head)} <small>{group['count']} image{'s' if group['count'] > 1 else ''}</small></h3><div class=\"spectre-gallery\">{''.join(thumbs)}</div>")
    total = sum(g["count"] for g in groups)
    if total > options["max"]:
        parts.append(f"<p><em>{options['max']} vignettes sur {total} images : les autres sont sur la page de la plaque.</em></p>")
    return engine.html_block(CSS + "".join(parts), title=title, subtitle="vignettes incorporées")


BLOCKS: dict[str, BlockType] = {
    b.key: b
    for b in (
        BlockType("text", "Texte", "Un texte libre, en Markdown (titres, listes, gras).", ("wafer",), _text, (OptionSpec("content", "Texte", "textarea", "", "Markdown : **gras**, listes, titres ##."),), group="Texte"),
        BlockType("context.facts", "Contexte de la plaque", "Identifiants (lasermark, runs, FDL, lot), statut en ligne, études qui la suivent, notes.", ("wafer",), _facts, (OptionSpec("studies", "Les études qui la suivent", "bool", True), OptionSpec("notes", "Ses notes", "bool", True))),
        BlockType("wafer.timeline", "Frise des mesures", "Fabrication et mesures MES, tests, données, étapes JIRA faites, sur un seul axe.", ("wafer",), _timeline),
        BlockType("wafer.tracking", "Vie en ligne (suivi Lumière)", "Le bloc de suivi de plaques de Lumière : MES, Gozer, FDL JIRA, tests, Gantt.", ("wafer",), _tracking),
        BlockType("data.maps", "Cartographies", "Les cartes (X, Y) des colonnes scalaires d'un type de données PRISM, dans l'explorateur de cartes de Lumière.", ("wafer",), _maps,
                  (OptionSpec("hook", "Type de données", "choice", "eqe", choices="positional_hooks"), OptionSpec("max_columns", "Colonnes au plus", "number", 8, min=1, max=16)), group="Données", needs="un type à positions (X, Y)"),
        BlockType("data.boxes", "Distributions", "Une boîte à moustaches par colonne scalaire d'un type de données PRISM.", ("wafer",), _boxes,
                  (OptionSpec("hook", "Type de données", "choice", "eqe", choices="hooks"), OptionSpec("max_columns", "Colonnes au plus", "number", 6, min=1, max=12)), group="Données"),
        BlockType("sem.gallery", "Images MEB - G4", "Les vignettes des images du G4 de la plaque, par acquisition, incorporées au rapport.", ("wafer",), _gallery,
                  (OptionSpec("max", "Vignettes au plus", "number", 24, min=1, max=MAX_IMAGES), OptionSpec("step", "Étape (filtre)", "text", "", "Ne garder que les acquisitions dont l'étape contient ce texte (ARC_POST_STRIP…)")), group="Images"),
    )
}


def for_context(kind: str) -> list[BlockType]:
    return [b for b in BLOCKS.values() if kind in b.contexts]


def get(key: str) -> BlockType:
    found = BLOCKS.get(key)
    if found is None:
        raise InvalidInput(f"Bloc inconnu : {key!r}.", code="unknown_block")
    return found
