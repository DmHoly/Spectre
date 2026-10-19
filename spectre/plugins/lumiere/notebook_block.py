"""Le cahier de mesures d'une étude dans un rapport Lumière : ses entrées (``notebook.service.entries``), celles
que l'étude reprend dans son rapport (``in_report``), rendues **une slide par entrée** (le bloc se *déplie*,
:func:`expand`) ou toutes sur une slide (:func:`render`). Une entrée PRISM montre son instantané figé : ce qu'il
contient, et les distributions de ses colonnes scalaires par plaque (``SummaryBoxPlots`` de Lumière) ; une entrée
manuelle, sa valeur, son texte, son tableau, ses images (fichiers déposés et images externes, incorporées en
``data:``), ses liens. Les vues DataViz de la page (un composant côté navigateur) ne se reproduisent pas ici :
la slide dit la vue choisie et renvoie à la fiche."""

from __future__ import annotations

import base64
import html
import logging
from typing import Any

import pandas as pd

from ..attachments import store as attachments
from ..experiments import service as experiments
from ..experiments.repository import get_repository
from ..external_images import service as external_images
from ..notebook import service as notebook
from ..wafer_data import blocks as wafer_data_blocks
from . import engine

log = logging.getLogger(__name__)
esc = html.escape

MAX_ENTRIES = 40
MAX_IMAGES = 30
MAX_IMAGE_BYTES = 2_000_000
MAX_TABLE_ROWS = 40
MAX_BOX_COLUMNS = 6
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp")

CSS = """
<style>
.spectre-entry{font-size:14px;line-height:1.45}
.spectre-entry__meta{color:#646e8c;font-size:12.5px;margin:0 0 8px}
.spectre-entry h4{font-size:13px;margin:12px 0 4px;color:#646e8c;text-transform:uppercase;letter-spacing:.04em}
.spectre-entry .spectre-measure{border-left:3px solid #e3e6ef;padding:4px 0 4px 12px;margin:10px 0}
.spectre-entry .spectre-value{font-size:22px;font-weight:600;color:#1a2f6a}
.spectre-entry .spectre-value small{font-size:13px;color:#646e8c;font-weight:400;margin-left:6px}
.spectre-entry table{border-collapse:collapse;font-size:12.5px;margin:6px 0}
.spectre-entry th,.spectre-entry td{border-bottom:1px solid #e3e6ef;padding:3px 8px;text-align:left}
.spectre-entry .spectre-gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin:6px 0}
.spectre-entry .spectre-gallery figure{margin:0}
.spectre-entry .spectre-gallery img{width:100%;border-radius:6px;background:#f6f7fb}
.spectre-entry .spectre-gallery figcaption{font-size:11.5px;color:#646e8c;margin-top:3px}
.spectre-entry ul{margin:4px 0;padding-left:18px}
</style>"""


class _Budget:
    def __init__(self) -> None:
        self.images = MAX_IMAGES


def _image_data(path: Any, content_type: str, budget: _Budget) -> str | None:
    """L'image en ``data:`` si elle est petite et qu'il reste de la place ; ``None`` sinon."""
    try:
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES or budget.images <= 0:
            return None
        budget.images -= 1
        return f"data:{content_type};base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        log.info("cahier : image %s non lue (%s)", path, exc)
        return None


def _step_names(ctx: Any) -> dict[str, str]:
    try:
        process = experiments.editable_process(get_repository(ctx.microproject.slug), ctx.tip) or {}
        return {str(s.get("id")): str(s.get("name") or s.get("id")) for s in process.get("steps") or [] if s.get("id")}
    except Exception as exc:  # noqa: BLE001
        log.info("cahier de %s : étapes non lues (%s)", ctx.key, exc)
        return {}


def _value_html(value: dict[str, Any]) -> str:
    number = value.get("number")
    text = f"{number:.6g}" if isinstance(number, (int, float)) else esc(str(number))
    unit = f"<small>{esc(str(value['unit']))}</small>" if value.get("unit") else ""
    name = f"<div class=\"spectre-entry__meta\">{esc(str(value['name']))}</div>" if value.get("name") else ""
    return f'{name}<div class="spectre-value">{text}{unit}</div>'


def _table_html(table: dict[str, Any]) -> str:
    columns = table.get("columns") or []
    rows = table.get("rows") or []
    head = "".join(f"<th>{esc(str(c))}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{esc('' if v is None else str(v))}</td>" for v in row) + "</tr>" for row in rows[:MAX_TABLE_ROWS])
    more = f"<p class=\"spectre-entry__meta\">{len(rows) - MAX_TABLE_ROWS} lignes de plus dans le cahier.</p>" if len(rows) > MAX_TABLE_ROWS else ""
    return f"<table><tr>{head}</tr>{body}</table>{more}"


def _manual_html(ctx: Any, entry: dict[str, Any], measurement: dict[str, Any], budget: _Budget) -> str:
    parts = []
    if measurement.get("value"):
        parts.append(_value_html(measurement["value"]))
    if measurement.get("text"):
        parts.append(f"<p>{esc(str(measurement['text']))}</p>")
    if measurement.get("table"):
        parts.append(_table_html(measurement["table"]))
    figures = []
    for attachment in measurement.get("attachments") or []:
        try:
            found, path = attachments.get(ctx.microproject.slug, attachment["id"])
        except Exception as exc:  # noqa: BLE001
            figures.append(f"<figure><figcaption>{esc(str(attachment.get('caption') or attachment['id']))} <em>(fichier introuvable : {esc(str(exc))})</em></figcaption></figure>")
            continue
        caption = esc(str(attachment.get("caption") or found.filename))
        if found.content_type in IMAGE_TYPES:
            src = _image_data(path, found.content_type, budget)
            figures.append(f'<figure>{f"<img src={chr(34)}{src}{chr(34)} alt={chr(34)}{caption}{chr(34)} loading={chr(34)}lazy{chr(34)}>" if src else "<em>image non incorporée (trop lourde ou trop d images)</em>"}<figcaption>{caption}</figcaption></figure>')
        else:
            figures.append(f"<figure><figcaption>📎 {caption} <small>({esc(found.content_type)})</small></figcaption></figure>")
    for image in measurement.get("external_images") or []:
        caption = esc(str(image.get("caption") or image.get("name") or image.get("path") or "image"))
        try:
            path = external_images.readable_file(image["path"])
            suffix = str(path.suffix).lower()
            content_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}.get(suffix)
            src = _image_data(path, content_type, budget) if content_type else None
        except Exception as exc:  # noqa: BLE001
            src = None
            caption += f" <em>({esc(str(exc))})</em>"
        figures.append(f'<figure>{f"<img src={chr(34)}{src}{chr(34)} alt={chr(34)}{caption}{chr(34)} loading={chr(34)}lazy{chr(34)}>" if src else "<em>image externe non incorporée</em>"}<figcaption>{caption}</figcaption></figure>')
    if figures:
        parts.append(f'<div class="spectre-gallery">{"".join(figures)}</div>')
    links = measurement.get("links") or []
    if links:
        parts.append("<ul>" + "".join(f'<li><a href="{esc(str(l["url"]))}">{esc(str(l.get("label") or l["url"]))}</a></li>' for l in links) + "</ul>")
    if measurement.get("annotations"):
        parts.append(f"<p class=\"spectre-entry__meta\">{len(measurement['annotations'])} annotation(s) sur ses images (voir la fiche).</p>")
    return "".join(parts) or "<p><em>Mesure vide.</em></p>"


def _snapshot_blocks(ctx: Any, measurement: dict[str, Any], lumiere: Any) -> tuple[str, Any | None]:
    """(résumé HTML, bloc Lumière ou None) d'une mesure PRISM : l'instantané figé et ses distributions."""
    snapshot_id = measurement.get("snapshot_id")
    view = f"vue « {esc(str(measurement.get('component') or '?'))} » dans la fiche"
    if not snapshot_id:
        return f"<p><em>Mesure PRISM sans instantané ({view}).</em></p>", None
    try:
        dataset = notebook.snapshots.load(ctx.microproject.slug, snapshot_id)
    except Exception as exc:  # noqa: BLE001
        return f"<p><em>Instantané {esc(snapshot_id)} introuvable ({esc(str(exc))}).</em></p>", None
    summary = notebook.snapshots.summary(dataset)
    text = (
        f"<p class=\"spectre-entry__meta\">{esc(str(summary.get('hook_title') or summary.get('hook') or ''))} · {summary['row_count']} lignes · "
        f"{len(summary.get('wafers') or [])} plaque(s) · source {esc(str(summary.get('source') or '?'))} · figé le {esc(str(summary.get('fetched_at') or '?')[:16])} · {view}</p>"
    )
    columns, rows = dataset.get("columns") or [], dataset.get("rows") or []
    if not rows:
        return text + "<p><em>Instantané vide.</em></p>", None
    df = pd.DataFrame(rows, columns=columns)
    wafer_col = next((c for c in columns if str(c).lower() in wafer_data_blocks.WAFER_COLUMNS), None)
    scalars = [c for c in columns if c != wafer_col and df[c].map(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)).mean() > 0.8][:MAX_BOX_COLUMNS]
    if not scalars or not wafer_col:
        return text, None
    kept = df[[wafer_col, *scalars]].copy()
    for c in scalars:
        kept[c] = pd.to_numeric(kept[c], errors="coerce")
    block = lumiere.SummaryBoxPlots(kept, group_col=wafer_col, metrics={s: (s, "") for s in scalars}, title=str(summary.get("hook_title") or summary.get("hook") or "Instantané"), subtitle="Une boîte par plaque, l'instantané figé du cahier")
    return text, block


def _entries(ctx: Any, options: dict[str, Any]) -> list[dict[str, Any]]:
    _, found = notebook.entries(ctx.microproject.slug, ctx.tip.branch)
    if not options.get("all_entries"):
        found = [e for e in found if e.get("in_report") is not False]
    return found[:MAX_ENTRIES]


def _entry_html(ctx: Any, entry: dict[str, Any], steps: dict[str, str], budget: _Budget, lumiere: Any, *, with_blocks: bool) -> tuple[str, list[Any]]:
    """(HTML de l'entrée, blocs Lumière à poser après) - les blocs seulement en mode déplié."""
    meta = [
        "entrée PRISM" if entry.get("kind") == "prism" else "entrée manuelle",
        f"plaques : {', '.join(entry['wafers'])}" if entry.get("wafers") else "toute la piste",
        f"par {entry['created_by']}" if entry.get("created_by") else "",
        str(entry.get("created_at") or "")[:10],
    ]
    out = [f'<p class="spectre-entry__meta">{esc(" · ".join(m for m in meta if m))}</p>']
    if entry.get("objective"):
        out.append(f"<h4>Objectif</h4><p>{esc(str(entry['objective']))}</p>")
    if entry.get("note"):
        out.append(f"<p>{esc(str(entry['note']))}</p>")
    blocks: list[Any] = []
    for measurement in entry.get("measurements") or []:
        step = measurement.get("step_id")
        where = f"à l'étape {esc(steps.get(str(step), str(step)))}" if step else "non située"
        if measurement.get("step_retired"):
            where += " (étape retirée du procédé)"
        body = ""
        if entry.get("kind") == "prism":
            body, block = _snapshot_blocks(ctx, measurement, lumiere)
            if block is not None and with_blocks:
                blocks.append(block)
        else:
            body = _manual_html(ctx, entry, measurement, budget)
        out.append(f'<div class="spectre-measure"><h4>Mesure {esc(where)}</h4>{body}</div>')
    if entry.get("interpretation"):
        out.append(f"<h4>Interprétation</h4><p>{esc(str(entry['interpretation']))}</p>")
    return "".join(out), blocks


def expand(ctx: Any, options: dict[str, Any], lumiere: Any) -> list[tuple[str, list[Any]]]:
    """Une slide par entrée du cahier : (titre, blocs)."""
    entries = _entries(ctx, options)
    if not entries:
        return [("Cahier de mesures", [engine.html_block(CSS + "<p><em>Le cahier de cette étude est vide" + ("" if options.get("all_entries") else " (ou rien n'y est repris dans le rapport)") + ".</em></p>", title="Cahier de mesures")])]
    steps = _step_names(ctx)
    budget = _Budget()
    out = []
    for i, entry in enumerate(entries, start=1):
        body, blocks = _entry_html(ctx, entry, steps, budget, lumiere, with_blocks=True)
        head = engine.html_block(CSS + f'<div class="spectre-entry">{body}</div>', title=f"{i}. {entry.get('title') or 'Entrée'}", subtitle="cahier de mesures")
        out.append((entry.get("title") or f"Entrée {i}", [head, *blocks]))
    return out


def render(ctx: Any, options: dict[str, Any], lumiere: Any) -> Any:
    """Tout le cahier sur une slide (sans les distributions des instantanés : la liste seulement)."""
    entries = _entries(ctx, options)
    if not entries:
        return engine.html_block(CSS + "<p><em>Le cahier de cette étude est vide.</em></p>", title="Cahier de mesures")
    steps = _step_names(ctx)
    budget = _Budget()
    parts = []
    for i, entry in enumerate(entries, start=1):
        body, _ = _entry_html(ctx, entry, steps, budget, lumiere, with_blocks=False)
        parts.append(f'<div class="spectre-entry"><h3>{i}. {esc(str(entry.get("title") or "Entrée"))}</h3>{body}</div>')
    return engine.html_block(CSS + "".join(parts), title="Cahier de mesures", subtitle=f"{len(entries)} entrée(s)")
