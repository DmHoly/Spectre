"""Les blocs qu'un modèle de rapport pose sur ses slides : chacun a une clé, un libellé, les contextes où il a un
sens, ses **options** (:class:`OptionSpec` : le formulaire de l'éditeur s'en déduit) et sa fonction de rendu
``render(ctx, options, lumiere) -> Block`` - un bloc Lumière (WaferMaps, WaferTrackingBlock...) ou du HTML que
Spectre produit lui-même (:func:`engine.html_block`). Les blocs « de plaques » travaillent sur ``ctx.wafers`` : une
plaque, ou toutes celles d'une analyse, d'une étude, d'un µprojet, d'un lot. Ce que Lumière saura faire de lui-même
un jour (ses composants, SOCLE-DATA.md §2) remplacera ce catalogue bloc par bloc."""

from __future__ import annotations

import base64
import html
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from ...kernel.errors import InvalidInput
from ..sem_images import render as sem_render
from ..sem_images import service as sem_images
from ..wafer_data import blocks as wafer_data_blocks
from ..wafers import timeline, tracking
from . import engine
from .context import CONTEXTS, ReportContext

log = logging.getLogger(__name__)
esc = html.escape

MAX_TEXT = 8000
MAX_IMAGES = 60
MAX_TIMELINES = 8  # frises dessinées dans un contexte à plusieurs plaques
ALL = tuple(CONTEXTS)
MANY = ("analysis", "study", "microproject", "lot")

CSS = """
<style>
.spectre-html{font-size:14px;line-height:1.45}
.spectre-facts{border-collapse:collapse;margin:8px 0 14px}
.spectre-facts th{text-align:left;padding:4px 14px 4px 0;color:#646e8c;font-weight:500;white-space:nowrap;vertical-align:top}
.spectre-facts td{padding:4px 0}
.spectre-table{border-collapse:collapse;width:100%;font-size:12.5px}
.spectre-table th,.spectre-table td{border-bottom:1px solid #e3e6ef;padding:4px 8px;text-align:left;vertical-align:top}
.spectre-table td.num{text-align:right;font-variant-numeric:tabular-nums}
.spectre-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:6px 0 16px}
.spectre-gallery figure{margin:0}
.spectre-gallery img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:6px;background:#111}
.spectre-gallery figcaption{font-size:11.5px;color:#646e8c;margin-top:3px}
.spectre-html h3{font-size:15px;margin:14px 0 6px}
.spectre-html h3 small{color:#646e8c;font-weight:400}
.spectre-html h4{font-size:13px;margin:10px 0 2px;color:#646e8c}
.spectre-structure svg{max-width:100%;height:auto;max-height:520px}
.spectre-better{color:#2e7d5b}.spectre-worse{color:#b9731a}
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
    group: str = "Plaques"
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


def _note(text: str, title: str) -> Any:
    return engine.html_block(CSS + f"<p><em>{esc(text)}</em></p>", title=title)


# --- les blocs -------------------------------------------------------------------------------------------


def _text(ctx: Any, options: dict[str, Any], lumiere: Any) -> Any:
    return lumiere.Text(options.get("content") or "")


def _facts(ctx: ReportContext, options: dict[str, Any], lumiere: Any) -> Any:
    return engine.html_block(CSS + ctx.facts_html(options), title="Contexte", subtitle=CONTEXTS.get(ctx.kind, ctx.kind))


def _timeline(ctx: ReportContext, options: dict[str, Any], lumiere: Any) -> Any:
    if not ctx.wafers:
        return _note("Aucune plaque.", "Frise des mesures")
    parts = []
    for lasermark in ctx.wafers[:MAX_TIMELINES]:
        plate = ctx.plate(lasermark)
        found = plate.events
        counts = {k: sum(1 for e in found if e["kind"] == k) for k in timeline.KINDS}
        said = " · ".join(f"{n} {timeline.KINDS[k].lower()}" for k, n in counts.items() if n)
        head = f"<h3>{esc(lasermark)}{' <small>' + esc(ctx.roles[lasermark]) + '</small>' if ctx.roles.get(lasermark) else ''} <small>{esc(said or 'aucun événement daté')}</small></h3>" if len(ctx.wafers) > 1 else ""
        parts.append(head + timeline.svg(found, title=f"Frise de {lasermark}"))
    if len(ctx.wafers) > MAX_TIMELINES:
        parts.append(f"<p><em>{MAX_TIMELINES} frises sur {len(ctx.wafers)} plaques.</em></p>")
    subtitle = said if len(ctx.wafers) == 1 else f"{min(len(ctx.wafers), MAX_TIMELINES)} plaques"
    return engine.html_block(CSS + "".join(parts), title="Frise des mesures", subtitle=subtitle or "aucun événement daté")


def _lower(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    return df


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    kept = [f for f in frames if not f.empty]
    return pd.concat(kept, ignore_index=True) if kept else (frames[0] if frames else pd.DataFrame())


def _life_table(plates: list[Any]) -> str:
    parts = []
    for plate in plates:
        life = plate.life
        if not life:
            parts.append(f"<h3>{esc(plate.name)}</h3><p><em>Vie en ligne non lue.</em></p>")
            continue
        rows = "".join(
            f"<tr><td>{esc(str(s.get('route') or ''))}</td><td>{esc(str(s.get('step') or ''))}{' · mesure' if s.get('measurement') else ''}</td>"
            f"<td>{esc(str(s.get('equipment') or ''))}</td><td>{esc(str(s.get('start') or ''))}</td><td>{esc(str(s.get('end_effective') or ''))}</td></tr>"
            for s in life.get("steps") or []
        )
        table = f'<table class="spectre-table"><tr><th>Route</th><th>Action MES</th><th>Équipement</th><th>Début</th><th>Fin</th></tr>{rows}</table>' if rows else "<p><em>Aucune étape MES.</em></p>"
        parts.append((f"<h3>{esc(plate.name)}</h3>" if len(plates) > 1 else "") + table)
    return "".join(parts)


def _tracking(ctx: ReportContext, options: dict[str, Any], lumiere: Any) -> Any:
    """Le bloc de suivi de Lumière, nourri des tables que la source de Spectre lit pour chaque plaque (mêmes hooks
    PRISM, ou la démo) ; si ça échoue, le parcours MES en tableau."""
    if not ctx.wafers:
        return _note("Aucune plaque.", "Vie en ligne")
    try:
        from lumiere_report.blocks.wafer_tracking.tracker import WaferTrackingData

        frames = [tracking.current_source().fetch(lm) for lm in ctx.wafers]
        aliases: dict[str, str] = {}
        phases: dict[str, Any] = {}
        for f in frames:
            aliases.update({k.upper(): v.upper() for k, v in f.aliases.items()})
            phases.update(f.phases)
        data = WaferTrackingData(
            lms=[lm.upper() for lm in ctx.wafers],
            mes=_lower(_concat([f.mes for f in frames])), info=_lower(_concat([f.epitaxy for f in frames])), wafer=_concat([f.record for f in frames]),
            jira_wafer=_lower(_concat([f.fdl_by_wafer for f in frames])), jira_lot=_lower(_concat([f.fdl_by_lot for f in frames])),
            tests=_lower(_concat([f.tests for f in frames])), fdl_steps=_lower(_concat([f.fdl_steps for f in frames])), phases=phases, aliases=aliases,
        )
        title = f"Suivi de {ctx.wafers[0]}" if len(ctx.wafers) == 1 else f"Suivi de {len(ctx.wafers)} plaques"
        return lumiere.WaferTrackingBlock(data, title=title)
    except Exception as exc:  # noqa: BLE001 - le bloc Lumière n'a pas pu se nourrir
        log.info("rapport %s %s : bloc de suivi Lumière indisponible (%s)", ctx.kind, ctx.key, exc)
        return engine.html_block(CSS + _life_table([ctx.plate(lm) for lm in ctx.wafers]), title="Vie en ligne", subtitle="MES")


def _frame(ctx: ReportContext, hook: str) -> tuple[Any, pd.DataFrame, str, list[str]] | str:
    """(type du catalogue, lignes, colonne plaque, colonnes scalaires) d'un type pour les plaques du contexte, ou
    le message qui dit ce qui manque."""
    entry = ctx.hook(hook)
    if entry is None:
        return f"Type de données inconnu : {hook!r}."
    if not ctx.wafers:
        return "Aucune plaque."
    result = ctx.data(hook)
    if result is None:
        return f"{entry.title} : non lu."
    if not result.rows:
        return f"{entry.title} : aucune ligne pour {'cette plaque' if len(ctx.wafers) == 1 else 'ces plaques'}."
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


def _maps(ctx: ReportContext, options: dict[str, Any], lumiere: Any) -> Any:
    found = _frame(ctx, options["hook"])
    if isinstance(found, str):
        return _note(found, "Cartographies")
    entry, df, wafer_col, scalars = found
    if not (entry.x and entry.y):
        return _note(f"{entry.title} : pas de positions (X, Y).", "Cartographies")
    cols = scalars[: options["max_columns"]]
    df = df[[c for c in [wafer_col, entry.x, entry.y, *cols] if c in df.columns]].copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    result = ctx.data(options["hook"])
    return lumiere.WaferMaps(df, x_col=entry.x, y_col=entry.y, wafer_col=wafer_col, colormap_cols=cols, title=entry.title, subtitle=f"{len(df)} points · {df[wafer_col].nunique()} plaque(s) · source {result.source}")


def _boxes(ctx: ReportContext, options: dict[str, Any], lumiere: Any) -> Any:
    found = _frame(ctx, options["hook"])
    if isinstance(found, str):
        return _note(found, "Distributions")
    entry, df, wafer_col, scalars = found
    cols = scalars[: options["max_columns"]]
    df = df[[c for c in [wafer_col, *cols] if c in df.columns]].copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    metrics = {s: (s, (entry.column(s) or {}).get("unit", "")) for s in cols}
    return lumiere.SummaryBoxPlots(df, group_col=wafer_col, metrics=metrics, title=entry.title, subtitle="Une boîte par plaque et par colonne scalaire")


def _gallery(ctx: ReportContext, options: dict[str, Any], lumiere: Any) -> Any:
    title = "Images MEB - G4"
    if not ctx.wafers:
        return _note("Aucune plaque.", title)
    wanted = (options.get("step") or "").strip().upper()
    budget = options["max"]
    parts = []
    shown = total = 0
    for lasermark in ctx.wafers:
        if budget <= 0:
            break
        plate = ctx.plate(lasermark)
        listing = plate.sem_listing
        if isinstance(listing, str):
            parts.append(f"<h3>{esc(plate.name)}</h3><p><em>Images MEB non lues : {esc(listing)}</em></p>" if len(ctx.wafers) > 1 else f"<p><em>Images MEB non lues : {esc(listing)}</em></p>")
            continue
        groups = [g for g in listing.get("groups") or [] if not wanted or wanted in str(g.get("step") or "").upper()]
        if not groups:
            parts.append(f"<h3>{esc(plate.name)}</h3><p><em>Aucune image du G4.</em></p>" if len(ctx.wafers) > 1 else "<p><em>Aucune image du G4 trouvée pour cette plaque" + (f" à l'étape « {esc(wanted)} »" if wanted else "") + ".</em></p>")
            continue
        for group in groups:
            total += group["count"]
            if budget <= 0:
                continue
            thumbs = []
            for image in group["images"]:
                if budget <= 0:
                    break
                try:
                    path = sem_images.image_path(plate.name, image["path"], lambda: [])
                    body, _ = sem_render.thumbnail(path, 0)
                except Exception as exc:  # noqa: BLE001 - un TIF illisible ne fait pas tomber le rapport
                    log.info("vignette %s : %s", image["path"], exc)
                    continue
                src = "data:image/jpeg;base64," + base64.b64encode(body).decode("ascii")
                caption = f"die {image['die']}" if image.get("die") is not None else image["name"]
                thumbs.append(f'<figure><img src="{src}" alt="{esc(image["name"])}" loading="lazy"><figcaption>{esc(caption)}</figcaption></figure>')
                budget -= 1
                shown += 1
            head = " · ".join(str(v) for v in ((plate.name if len(ctx.wafers) > 1 else None), group.get("step"), group.get("fdl"), group.get("process"), group.get("area_label")) if v)
            parts.append(f"<h3>{esc(head)} <small>{group['count']} image{'s' if group['count'] > 1 else ''}</small></h3><div class=\"spectre-gallery\">{''.join(thumbs)}</div>")
    if total > shown:
        parts.append(f"<p><em>{shown} vignettes sur {total} images : les autres sont sur la page de chaque plaque.</em></p>")
    return engine.html_block(CSS + "".join(parts), title=title, subtitle="vignettes incorporées")


def _analysis_kpis(ctx: Any, options: dict[str, Any], lumiere: Any) -> Any:
    kpis = ctx.kpis
    if kpis is None:
        return _note("Les KPI de l'analyse n'ont pas pu être calculés (bases non jointes).", "KPI comparés")
    if not kpis["kpis"]:
        return _note("Cette analyse ne compare encore aucun KPI.", "KPI comparés")
    parts = []
    for kpi in kpis["kpis"]:
        unit = f" ({kpi['unit']})" if kpi.get("unit") else ""
        if kpi["status"] != "ok":
            parts.append(f"<h3>{esc(kpi['title'])}{esc(unit)}</h3><p><em>{esc(kpi['message'])}</em></p>")
            continue
        rows = []
        for group in kpi["groups"]:
            stats = group.get("stats") or {}
            delta = group.get("delta") or {}
            verdict = ""
            if delta.get("relative") is not None and kpi.get("better"):
                good = (delta["relative"] > 0) == (kpi["better"] == "high")
                verdict = f'<span class="{"spectre-better" if good else "spectre-worse"}">{"mieux" if good else "moins bien"}</span>'
            rows.append(
                f"<tr><td><strong>{esc(group['wafer'])}</strong>{' · référence' if group is kpi['groups'][0] else ''}</td>"
                f"<td class=\"num\">{_num(stats.get('median'))}</td><td class=\"num\">{_num(stats.get('q1'))} – {_num(stats.get('q3'))}</td><td class=\"num\">{stats.get('n', '') if stats else ''}</td>"
                f"<td class=\"num\">{_num(delta.get('absolute')) if delta else ''}</td><td class=\"num\">{_pct(delta.get('relative')) if delta else ''}</td><td>{verdict}</td>"
                f"<td>{esc(str(group.get('date') or ''))}</td></tr>"
            )
        parts.append(
            f"<h3>{esc(kpi['title'])}{esc(unit)} <small>{esc(kpi.get('hook_title') or '')}</small></h3>"
            f'<table class="spectre-table"><tr><th>Plaque</th><th>Médiane</th><th>Q1 – Q3</th><th>n</th><th>Écart</th><th>Écart %</th><th></th><th>Mesure du</th></tr>{"".join(rows)}</table>'
        )
    return engine.html_block(CSS + "".join(parts), title="KPI comparés", subtitle=f"{len(kpis['kpis'])} KPI · la mesure la plus récente de chaque plaque")


def _num(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.4g}"
    except (TypeError, ValueError):
        return esc(str(value))


def _pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:+.1f} %"
    except (TypeError, ValueError):
        return esc(str(value))


def _structure(ctx: Any, options: dict[str, Any], lumiere: Any) -> Any:
    svg = ctx.structure_svg
    if not svg:
        return _note("Cette étude n'a pas de structure à dessiner (images, ou structure décrite seulement).", "Structure")
    return engine.html_block(CSS + f'<div class="spectre-structure">{svg}</div>', title="Structure", subtitle=f"version actuelle · {esc(getattr(ctx.tip, 'structure_type', ''))}")


def _studies(ctx: Any, options: dict[str, Any], lumiere: Any) -> Any:
    return engine.html_block(CSS + ctx.studies_html(), title="Études du µprojet", subtitle=f"{len(ctx.tips)} piste(s), la plus récente d'abord")


BLOCKS: dict[str, BlockType] = {
    b.key: b
    for b in (
        BlockType("text", "Texte", "Un texte libre, en Markdown (titres, listes, gras).", ALL, _text, (OptionSpec("content", "Texte", "textarea", "", "Markdown : **gras**, listes, titres ##."),), group="Texte"),
        BlockType("context.facts", "Contexte", "Ce qu'est la chose décrite : identifiants, statut, études, notes (plaque) ; question, plaques et conclusion (analyse) ; intention et conclusion (étude) ; études (µprojet) ; dates et plaques (lot).", ALL, _facts,
                  (OptionSpec("studies", "Les études / les plaques en détail", "bool", True), OptionSpec("notes", "Les notes de plaque", "bool", True)), group="Contexte"),
        BlockType("wafer.timeline", "Frise des mesures", "Fabrication et mesures MES, tests, données, étapes JIRA faites, sur un seul axe - une frise par plaque.", ALL, _timeline),
        BlockType("wafer.tracking", "Vie en ligne (suivi Lumière)", "Le bloc de suivi de plaques de Lumière : MES, Gozer, FDL JIRA, tests, Gantt - toutes les plaques du contexte.", ALL, _tracking),
        BlockType("data.maps", "Cartographies", "Les cartes (X, Y) des colonnes scalaires d'un type de données PRISM, plaque par plaque, dans l'explorateur de cartes de Lumière.", ALL, _maps,
                  (OptionSpec("hook", "Type de données", "choice", "eqe", choices="positional_hooks"), OptionSpec("max_columns", "Colonnes au plus", "number", 8, min=1, max=16)), group="Données", needs="un type à positions (X, Y)"),
        BlockType("data.boxes", "Distributions", "Une boîte à moustaches par plaque et par colonne scalaire d'un type de données PRISM : les plaques se comparent d'un coup d'œil.", ALL, _boxes,
                  (OptionSpec("hook", "Type de données", "choice", "eqe", choices="hooks"), OptionSpec("max_columns", "Colonnes au plus", "number", 6, min=1, max=12)), group="Données"),
        BlockType("sem.gallery", "Images MEB - G4", "Les vignettes des images du G4, par plaque et par acquisition, incorporées au rapport.", ALL, _gallery,
                  (OptionSpec("max", "Vignettes au plus", "number", 24, min=1, max=MAX_IMAGES), OptionSpec("step", "Étape (filtre)", "text", "", "Ne garder que les acquisitions dont l'étape contient ce texte (ARC_POST_STRIP…)")), group="Images"),
        BlockType("analysis.kpis", "KPI comparés", "Les KPI de l'analyse : médiane et quartiles de chaque plaque, écart à la référence, mieux / moins bien.", ("analysis",), _analysis_kpis, group="Analyse"),
        BlockType("study.structure", "Structure de l'étude", "Le dessin de la structure de l'étude (sa version actuelle), tel que la fiche le montre.", ("study",), _structure, group="Étude"),
        BlockType("microproject.studies", "Études du µprojet", "Le tableau des études du µprojet : statut, date, plaques, conclusion.", ("microproject",), _studies, group="µprojet"),
    )
}


def for_context(kind: str) -> list[BlockType]:
    return [b for b in BLOCKS.values() if kind in b.contexts]


def get(key: str) -> BlockType:
    found = BLOCKS.get(key)
    if found is None:
        raise InvalidInput(f"Bloc inconnu : {key!r}.", code="unknown_block")
    return found
