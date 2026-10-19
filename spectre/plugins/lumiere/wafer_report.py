"""Le modèle « Fiche plaque » : le rapport Lumière d'une plaque, construit avec ce que Spectre sait d'elle.

Slide par slide : le titre ; son **contexte** (les études qui la suivent, ses notes, ses FDL, son lot, ses runs) ;
sa **frise des mesures** (``wafers.timeline`` : fabrication, mesures MES, tests, données, étapes JIRA faites) ;
sa **vie en ligne** (le bloc de suivi de Lumière, ``WaferTrackingBlock``, nourri des mêmes tables que la page de la
plaque : MES, Gozer, FDL JIRA, tests - et, si ce bloc échoue, un tableau du parcours MES) ; ses **données** : pour
chaque type de données PRISM par plaque qui a des positions (eqe, pl...), une ``WaferMaps`` de ses colonnes
scalaires et des ``SummaryBoxPlots`` ; ses **images MEB du G4**, par acquisition, en vignettes incorporées (le
rapport reste un seul fichier) ; le sommaire. Ce qui manque (pas de données, partage non monté) est dit sur la
slide, jamais une erreur du rapport."""

from __future__ import annotations

import base64
import html
import logging
from typing import Any

import pandas as pd

from ...kernel.errors import DomainError
from ..accounts.service import User
from ..characterization import service as characterization
from ..sem_images import render as sem_render
from ..sem_images import service as sem_images
from ..wafer_data import blocks as wafer_data_blocks
from ..wafers import notes, records, timeline, tracking
from ..wafers import service as wafers
from . import engine

log = logging.getLogger(__name__)

MAX_HOOKS = 4  # types de données dessinés (les premiers du catalogue qui ont des lignes)
MAX_MAP_COLUMNS = 8
MAX_IMAGES = 24  # vignettes du G4 incorporées (≈25 Ko chacune)

esc = html.escape


# --- le contexte ---------------------------------------------------------------------------------------


def _facts(passport: dict[str, Any], plate_notes: dict[str, Any] | None, life: dict[str, Any] | None) -> str:
    rows = [
        ("Lasermark", passport["lasermark"]),
        ("Runs d'épitaxie", ", ".join(passport.get("run_names") or []) or None),
        ("FDL", ", ".join(dict.fromkeys([*(passport.get("fdl") or []), *(passport.get("line_fdl") or [])])) or None),
        ("Lot", passport.get("lot_name") or (life or {}).get("lot")),
        ("Dernier emplacement connu", passport.get("last_location")),
        ("µprojets", ", ".join(m.get("code") or m.get("name") or "" for m in passport.get("microprojects") or []) or None),
        ("Statut en ligne", (life or {}).get("status")),
    ]
    cells = "".join(f"<tr><th>{esc(k)}</th><td>{esc(str(v))}</td></tr>" for k, v in rows if v)
    table = f'<table class="spectre-facts">{cells}</table>'
    studies = passport.get("occurrences") or []
    if studies:
        items = []
        for o in studies:
            exp = o.get("experiment") or {}
            title = exp.get("title") or exp.get("id") or "étude"
            mp = (exp.get("microproject") or {}).get("code") or (exp.get("microproject") or {}).get("name") or ""
            bits = [esc(str(title)), esc(str(exp.get("status") or ""))]
            if mp:
                bits.insert(0, f"<strong>{esc(str(mp))}</strong>")
            if o.get("variant"):
                bits.append(f"variante {esc(str(o['variant']))}")
            if o.get("location"):
                bits.append(f"rangée : {esc(str(o['location']))}")
            items.append(f"<li>{' · '.join(b for b in bits if b)}</li>")
        table += f"<h3>Études qui la suivent</h3><ul>{''.join(items)}</ul>"
    else:
        table += "<p><em>Aucune étude ne suit cette plaque.</em></p>"
    if plate_notes:
        parts = [(label, plate_notes.get(key)) for key, label in (("context", "Contexte"), ("hypothesis", "Hypothèse"), ("learnings", "Ce qu'on a compris"))]
        written = [f"<h4>{esc(label)}</h4><p>{esc(str(text))}</p>" for label, text in parts if text]
        if written:
            table += "<h3>Notes</h3>" + "".join(written)
    return table


# --- la vie en ligne -----------------------------------------------------------------------------------


def _lower(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).lower() for c in df.columns]
    return df


def _tracking_block(lumiere: Any, lasermark: str) -> Any:
    """Le bloc de suivi de Lumière, nourri des tables que la source de Spectre lit pour la plaque (les mêmes hooks
    PRISM, ou la démo)."""
    from lumiere_report.blocks.wafer_tracking.tracker import WaferTrackingData

    frames = tracking.current_source().fetch(lasermark)
    data = WaferTrackingData(
        lms=[lasermark.strip().upper()],
        mes=_lower(frames.mes),
        info=_lower(frames.epitaxy),
        wafer=frames.record,
        jira_wafer=_lower(frames.fdl_by_wafer),
        jira_lot=_lower(frames.fdl_by_lot),
        tests=_lower(frames.tests),
        fdl_steps=_lower(frames.fdl_steps),
        phases=dict(frames.phases),
        aliases={k.upper(): v.upper() for k, v in frames.aliases.items()},
    )
    return lumiere.WaferTrackingBlock(data, title=f"Suivi de {lasermark}")


def _life_table(life: dict[str, Any]) -> str:
    """Le parcours MES en tableau, quand le bloc Lumière n'a pas pu se faire."""
    rows = "".join(
        f"<tr><td>{esc(str(s.get('route') or ''))}</td><td>{esc(str(s.get('step') or ''))}{' · mesure' if s.get('measurement') else ''}</td>"
        f"<td>{esc(str(s.get('equipment') or ''))}</td><td>{esc(str(s.get('start') or ''))}</td><td>{esc(str(s.get('end_effective') or ''))}</td></tr>"
        for s in life.get("steps") or []
    )
    head = "<tr><th>Route</th><th>Action MES</th><th>Équipement</th><th>Début</th><th>Fin</th></tr>"
    return f'<table class="spectre-table">{head}{rows}</table>' if rows else "<p><em>Aucune étape MES.</em></p>"


# --- les données ---------------------------------------------------------------------------------------


def _frame(result: Any) -> pd.DataFrame:
    return pd.DataFrame(result.rows, columns=result.columns)


def _wafer_column(columns: list[str]) -> str | None:
    return next((c for c in columns if c.lower() in wafer_data_blocks.WAFER_COLUMNS), None)


def _scalar_columns(entry: wafer_data_blocks.CatalogHook, df: pd.DataFrame) -> list[str]:
    """Les colonnes scalaires numériques du type : d'après le catalogue typé, confirmées sur les lignes."""
    found = []
    for c in entry.columns:
        name = c["name"]
        if name not in df.columns or name in (entry.x, entry.y) or not wafer_data_blocks.col_types.fits(c["type"], "number"):
            continue
        series = df[name]
        if series.map(lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)).mean() > 0.8:
            found.append(name)
    return found


def _data_slides(lumiere: Any, lasermark: str) -> list[Any]:
    slides = []
    for entry in wafer_data_blocks.catalog():
        if len(slides) >= MAX_HOOKS or not (entry.x and entry.y):
            continue
        try:
            result = characterization.query(entry.hook, {"wafer_names": [lasermark]})
        except DomainError as exc:
            log.info("rapport de %s : %s non lu (%s)", lasermark, entry.hook, exc)
            continue
        if not result.rows:
            continue
        df = _frame(result)
        wafer_col = _wafer_column(result.columns) or "wafername"
        scalars = _scalar_columns(entry, df)
        if not scalars:
            continue
        keep = [wafer_col, entry.x, entry.y, *scalars[:MAX_MAP_COLUMNS]]
        df = df[[c for c in keep if c in df.columns]].copy()
        for c in scalars[:MAX_MAP_COLUMNS]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        slide = lumiere.Slide(f"{entry.title} - cartes")
        slide.add(lumiere.WaferMaps(df, x_col=entry.x, y_col=entry.y, wafer_col=wafer_col, colormap_cols=scalars[:MAX_MAP_COLUMNS], title=entry.title, subtitle=f"{len(df)} points · source {result.source}"))
        slides.append(slide)
        boxes = lumiere.Slide(f"{entry.title} - distributions")
        metrics = {s: (s, (entry.column(s) or {}).get("unit", "")) for s in scalars[:6]}
        boxes.add(lumiere.SummaryBoxPlots(df, group_col=wafer_col, metrics=metrics, title=entry.title, subtitle="Une boîte par colonne scalaire"))
        slides.append(boxes)
    return slides


# --- les images du G4 ----------------------------------------------------------------------------------


def _sem_gallery(user: User, lasermark: str, fdls: list[str]) -> str:
    try:
        listing = sem_images.listing(lasermark, fdls)
    except DomainError as exc:
        return f"<p><em>Images MEB non lues : {esc(str(exc))}</em></p>"
    groups = listing.get("groups") or []
    if not groups:
        return "<p><em>Aucune image du G4 trouvée pour cette plaque.</em></p>"
    budget = MAX_IMAGES
    parts = []
    for group in groups:
        if budget <= 0:
            break
        thumbs = []
        for image in group["images"]:
            if budget <= 0:
                break
            path = listing_path(lasermark, image["path"])
            if not path:
                continue
            try:
                body, _ = sem_render.thumbnail(path, 0)
            except Exception as exc:  # un TIF illisible ne fait pas tomber le rapport
                log.info("vignette %s : %s", path, exc)
                continue
            src = "data:image/jpeg;base64," + base64.b64encode(body).decode("ascii")
            caption = f"die {image['die']}" if image.get("die") is not None else image["name"]
            thumbs.append(f'<figure><img src="{src}" alt="{esc(image["name"])}" loading="lazy"><figcaption>{esc(caption)}</figcaption></figure>')
            budget -= 1
        title = " · ".join(str(v) for v in (group.get("step"), group.get("fdl"), group.get("process"), group.get("area_label")) if v)
        parts.append(f"<h3>{esc(title)} <small>{group['count']} image{'s' if group['count'] > 1 else ''}</small></h3><div class=\"spectre-gallery\">{''.join(thumbs)}</div>")
    total = listing.get("count") or 0
    if total > MAX_IMAGES:
        parts.append(f"<p><em>{MAX_IMAGES} vignettes sur {total} images : les autres sont sur la page de la plaque.</em></p>")
    return "".join(parts)


def listing_path(lasermark: str, relative: str) -> str | None:
    """Le fichier d'une image de la liste (sans relire : la liste vient d'être faite)."""
    try:
        return sem_images.image_path(lasermark, relative, lambda: [])
    except DomainError:
        return None


# --- le rapport ----------------------------------------------------------------------------------------

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
</style>"""


def build(user: User, lasermark: str) -> Any:
    """Le ``ReportBuilder`` (mode slide) de la plaque ``lasermark``, pour ``user`` (ce qu'il voit)."""
    lumiere = engine.load()
    key = wafers.wafer_key(lasermark)
    line = tracking.line_facts([key]).get(key)
    passport = wafers.passport(lasermark, wafers.occurrences(user, keys=[lasermark]), records.get(lasermark), line)
    name = passport["lasermark"]
    try:
        life = tracking.read(lasermark)  # la fiche de la vie en ligne (statut, étapes MES, FDL, tests) et sa fraîcheur
    except DomainError as exc:
        log.info("rapport de %s : vie en ligne non lue (%s)", name, exc)
        life = None

    report = lumiere.ReportBuilder(title=f"Plaque {name}", subtitle="Fiche plaque - Spectre", author=user.name or user.email, mode="slide")
    slides: list[Any] = [lumiere.TitleSlide()]

    context = lumiere.Slide("Contexte")
    context.add(engine.html_block(CSS + _facts(passport, notes.get(lasermark), life), title="Contexte", subtitle="études, notes, identifiants"))
    slides.append(context)

    frieze = lumiere.Slide("Frise des mesures")
    try:
        found = timeline.events(user, name)
        counts = {k: sum(1 for e in found if e["kind"] == k) for k in timeline.KINDS}
        said = " · ".join(f"{n} {timeline.KINDS[k].lower()}" for k, n in counts.items() if n)
        frieze.add(engine.html_block(CSS + timeline.svg(found, title=f"Frise de {name}"), title="Frise des mesures", subtitle=said or "aucun événement daté"))
    except Exception as exc:  # noqa: BLE001 - la frise ne fait pas échouer le rapport
        log.info("rapport de %s : frise non dessinée (%s)", name, exc)
        frieze.add(engine.html_block(CSS + "<p><em>Frise indisponible.</em></p>", title="Frise des mesures"))
    slides.append(frieze)

    online = lumiere.Slide("Vie en ligne")
    try:
        online.add(_tracking_block(lumiere, name))
    except Exception as exc:  # le bloc Lumière n'a pas pu se nourrir : le parcours en tableau
        log.info("rapport de %s : bloc de suivi Lumière indisponible (%s)", name, exc)
        online.add(engine.html_block(CSS + (_life_table(life) if life else "<p><em>Vie en ligne non lue.</em></p>"), title="Vie en ligne", subtitle="MES"))
    slides.append(online)

    data_slides = _data_slides(lumiere, name)
    if data_slides:
        slides.extend(data_slides)
    else:
        empty = lumiere.Slide("Données")
        empty.add(engine.html_block(CSS + "<p><em>Aucune donnée de caractérisation par position pour cette plaque.</em></p>", title="Données"))
        slides.append(empty)

    fdls = list(dict.fromkeys([*(passport.get("line_fdl") or []), *(passport.get("fdl") or [])]))
    sem = lumiere.Slide("Images MEB - G4")
    sem.add(engine.html_block(CSS + _sem_gallery(user, name, fdls), title="Images MEB - G4", subtitle="vignettes incorporées"))
    slides.append(sem)

    slides.append(lumiere.SummarySlide())
    report.add(lumiere.SlideView(slides))
    return report
