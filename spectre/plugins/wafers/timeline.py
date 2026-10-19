"""La frise d'une plaque : tout ce qui lui est arrivé, daté, sur un seul axe de temps - les actions MES de
fabrication (des segments), les **mesures** MES (``is_measurement``), les tests PRISM (``wafer_tests``), les étapes
JIRA faites, et les **données** qui existent pour elle (déclarées par d'autres plugins : les jours de mesure de
chaque type de données PRISM par wafer_data, les acquisitions MEB du G4 par sem_images - :func:`register_source`).
On voit ainsi *quand* la plaque a été caractérisée entre deux étapes de fabrication (SOCLE-DATA.md §4.7).

:func:`events` assemble la liste ; :func:`svg` la dessine, en SVG autonome (couleurs écrites, pas de variable
CSS : le même dessin sert la page de la plaque et le rapport Lumière). Sur la page, chaque marque porte
``data-detail="timeline" data-index``, et ``ref`` dit quoi ouvrir (l'action MES, l'étape JIRA, le test)."""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from ..accounts.service import User
from . import tracking
from .tracking_model import step_category

log = logging.getLogger(__name__)

KINDS = {
    "fab": "Fabrication (MES)",
    "measure": "Mesures (MES)",
    "test": "Tests",
    "data": "Données",
    "jira": "Étapes JIRA faites",
}
# couleurs de la charte, écrites (le SVG vit aussi hors de Spectre, dans un rapport)
COLORS = {"fab": "#c7cde0", "fab_running": "#2f7d5b", "measure": "#1a2f6a", "test": "#2e7d5b", "data": "#b9731a", "jira": "#646e8c", "axis": "#9aa3bd", "text": "#1d2233", "muted": "#646e8c", "grid": "#e3e6ef"}

# (utilisateur, lasermark) -> événements ``{kind: "data", at, end?, label, detail, source, ref}``
EventSource = Callable[[User, str], list[dict[str, Any]]]
_SOURCES: dict[str, EventSource] = {}


def register_source(name: str, source: EventSource) -> None:
    """Un plugin déclare ce qu'il sait dater pour une plaque (ses données) ; ``name`` le désigne (``source``)."""
    _SOURCES[name] = source


def parse_date(value: Any) -> datetime | None:
    """Une date telle que les fiches l'écrivent (``2026-09-02 04:48``, ISO avec ou sans fuseau, un jour) ->
    datetime naïf (le fuseau est ignoré : tout est lu en heure locale de la ligne)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"(Z|[+-]\d{2}:?\d{2})$", "", text.replace("T", " "))
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: 26 if fmt.endswith("%f") else len(text)], fmt)
        except ValueError:
            continue
    return None


def _event(kind: str, at: Any, label: str, *, end: Any = None, detail: str = "", source: str = "", ref: dict[str, Any] | None = None, precision: str = "minute") -> dict[str, Any] | None:
    start = parse_date(at)
    if start is None:
        return None
    stop = parse_date(end)
    return {
        "kind": kind,
        "at": start.strftime("%Y-%m-%d %H:%M"),
        "end": stop.strftime("%Y-%m-%d %H:%M") if stop else None,
        "precision": precision,
        "label": label,
        "detail": detail,
        "source": source,
        "ref": ref or {},
    }


def tracking_events(fiche: dict[str, Any]) -> list[dict[str, Any]]:
    """Les événements de la vie en ligne (la fiche de :func:`tracking.read`) : actions MES (fabrication ou mesure),
    tests, étapes JIRA faites."""
    out: list[dict[str, Any]] = []
    for index, step in enumerate(fiche.get("steps") or []):
        name = step.get("step") or "?"
        kind = "measure" if step.get("measurement") else "fab"
        detail = " · ".join(str(v) for v in (step.get("equipment"), step.get("recipe"), step.get("route")) if v)
        running = bool(step.get("start") and not step.get("end_effective"))
        ev = _event(kind, step.get("start"), name, end=step.get("end_effective"), detail=detail, source="MES", ref={"detail": "action", "index": index, "running": running})
        if ev:
            out.append(ev)
    for index, test in enumerate(fiche.get("tests") or []):
        label = test.get("type") or "Test"
        detail = " · ".join(str(v) for v in (test.get("sensor"), test.get("operator"), test.get("request")) if v)
        ev = _event("test", test.get("date"), label, end=test.get("end"), detail=detail, source="PRISM wafer_tests", ref={"detail": "test", "index": index})
        if ev:
            out.append(ev)
    for request, flow in (fiche.get("fdls") or {}).items():
        for index, step in enumerate(flow.get("steps") or []):
            if step.get("category") != "done" or not step.get("closed"):
                continue
            ev = _event("jira", step["closed"], step.get("stage") or step.get("key") or "étape", detail=f"FDL {request}" + (f" · {step['assignee']}" if step.get("assignee") else ""), source="JIRA", ref={"detail": "fdl-step", "request": request, "index": index})
            if ev:
                out.append(ev)
    return out


def events(user: User, lasermark: str) -> list[dict[str, Any]]:
    """Tous les événements datés de la plaque, du plus ancien au plus récent : la vie en ligne, puis ce que les
    sources déclarées savent (une source en échec est ignorée et journalisée : la frise se dessine quand même)."""
    try:
        fiche = tracking.read(lasermark)
    except Exception as exc:  # noqa: BLE001 - la vie en ligne indisponible : la frise des autres sources
        log.info("frise de %s : vie en ligne non lue (%s)", lasermark, exc)
        fiche = {}
    found = tracking_events(fiche)
    for name, source in _SOURCES.items():
        try:
            for raw in source(user, lasermark):
                ev = _event(
                    raw.get("kind") or "data", raw.get("at"), str(raw.get("label") or name), end=raw.get("end"), detail=str(raw.get("detail") or ""),
                    source=str(raw.get("source") or name), ref=raw.get("ref"), precision=str(raw.get("precision") or "day"),
                )
                if ev:
                    found.append(ev)
        except Exception as exc:  # noqa: BLE001
            log.info("frise de %s : source %s en échec (%s)", lasermark, name, exc)
    found.sort(key=lambda e: (e["at"], e["kind"]))
    for i, ev in enumerate(found):
        ev["index"] = i
    return found


# --- le dessin ------------------------------------------------------------------------------------------

LANES = ("fab", "measure", "test", "data", "jira")
LANE_H = 26
LEFT = 118
RIGHT = 16
TOP = 10
AXIS_H = 34
LEGEND_H = 22


def _x(at: datetime, start: datetime, span: float, width: float) -> float:
    return LEFT + (at - start).total_seconds() / span * width


def _ticks(start: datetime, end: datetime) -> list[tuple[datetime, str]]:
    """Des repères lisibles : des jours, des semaines ou des mois selon la durée."""
    days = max((end - start).days, 1)
    ticks: list[tuple[datetime, str]] = []
    if days <= 14:
        t = start.replace(hour=0, minute=0, second=0, microsecond=0)
        while t <= end:
            if t >= start:
                ticks.append((t, t.strftime("%d %b")))
            t += timedelta(days=1)
    elif days <= 120:
        t = start.replace(hour=0, minute=0, second=0, microsecond=0)
        t -= timedelta(days=t.weekday())
        while t <= end:
            if t >= start:
                ticks.append((t, t.strftime("%d %b")))
            t += timedelta(days=7)
    else:
        t = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        while t <= end:
            if t >= start:
                ticks.append((t, t.strftime("%b %Y")))
            t = (t.replace(day=28) + timedelta(days=4)).replace(day=1)
    return ticks[:24]


def svg(found: list[dict[str, Any]], *, width: int = 960, title: str = "") -> str:
    """La frise en SVG : une ligne par genre, les actions de fabrication en segments, le reste en marques
    cliquables (``data-detail="timeline" data-index``), l'axe du temps en bas et une légende."""
    esc = html.escape
    dated = [(parse_date(e["at"]), parse_date(e.get("end")), e) for e in found]
    dated = [(a, b, e) for a, b, e in dated if a is not None]
    height = TOP + LANE_H * len(LANES) + AXIS_H + LEGEND_H
    if not dated:
        return (
            f'<svg class="plate-timeline__svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 60" width="100%" role="img" aria-label="Frise vide">'
            f'<text x="{width / 2}" y="34" text-anchor="middle" font-size="13" fill="{COLORS["muted"]}" font-family="DM Sans, system-ui, sans-serif">Aucun événement daté pour cette plaque.</text></svg>'
        )
    start = min(a for a, _, _ in dated)
    end = max(max(a, b or a) for a, b, _ in dated)
    if end <= start:
        end = start + timedelta(days=1)
    pad = (end - start) * 0.03
    start, end = start - pad, end + pad
    span = (end - start).total_seconds()
    plot_w = width - LEFT - RIGHT
    parts = [
        f'<svg class="plate-timeline__svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="{esc(title or "Frise de la plaque")}" font-family="DM Sans, system-ui, sans-serif">'
    ]
    # les lignes
    for i, lane in enumerate(LANES):
        y = TOP + i * LANE_H
        parts.append(f'<rect x="{LEFT}" y="{y}" width="{plot_w}" height="{LANE_H}" fill="{"#f6f7fb" if i % 2 else "#ffffff"}"/>')
        parts.append(f'<text x="{LEFT - 8}" y="{y + LANE_H / 2 + 4}" text-anchor="end" font-size="11.5" fill="{COLORS["text"]}">{esc(KINDS[lane])}</text>')
    axis_y = TOP + LANE_H * len(LANES)
    for t, label in _ticks(start, end):
        x = _x(t, start, span, plot_w)
        parts.append(f'<line x1="{x:.1f}" y1="{TOP}" x2="{x:.1f}" y2="{axis_y}" stroke="{COLORS["grid"]}" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{axis_y + 16}" text-anchor="middle" font-size="10.5" fill="{COLORS["muted"]}">{esc(label)}</text>')
    parts.append(f'<line x1="{LEFT}" y1="{axis_y}" x2="{LEFT + plot_w}" y2="{axis_y}" stroke="{COLORS["axis"]}" stroke-width="1"/>')
    # les événements
    for a, b, e in dated:
        lane = LANES.index(e["kind"]) if e["kind"] in LANES else LANES.index("data")
        y = TOP + lane * LANE_H + LANE_H / 2
        x = _x(a, start, span, plot_w)
        tip = esc(f"{e['label']} · {e['at']}" + (f" → {e['end']}" if e.get("end") else "") + (f"\n{e['detail']}" if e.get("detail") else "") + (f"\n{e['source']}" if e.get("source") else ""))
        attrs = f'class="plate-timeline__event plate-timeline__event--{e["kind"]}" data-detail="timeline" data-index="{e.get("index", 0)}" role="button" tabindex="0"'
        if e["kind"] == "fab":
            x2 = _x(b, start, span, plot_w) if b else x + 2
            running = (e.get("ref") or {}).get("running")
            fill = COLORS["fab_running"] if running else COLORS["fab"]
            parts.append(f'<g {attrs}><title>{tip}</title><rect x="{x:.1f}" y="{y - 7:.1f}" width="{max(x2 - x, 2.5):.1f}" height="14" rx="2" fill="{fill}"/></g>')
        elif e["kind"] == "measure":
            parts.append(f'<g {attrs}><title>{tip}</title><path d="M{x:.1f} {y - 8:.1f} l7 8 -7 8 -7 -8 z" fill="{COLORS["measure"]}"/></g>')
        elif e["kind"] == "test":
            parts.append(f'<g {attrs}><title>{tip}</title><circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{COLORS["test"]}"/></g>')
        elif e["kind"] == "jira":
            parts.append(f'<g {attrs}><title>{tip}</title><path d="M{x:.1f} {y - 7:.1f} l6.5 12 h-13 z" fill="{COLORS["jira"]}"/></g>')
        else:
            parts.append(f'<g {attrs}><title>{tip}</title><rect x="{x - 5.5:.1f}" y="{y - 5.5:.1f}" width="11" height="11" rx="1.5" fill="{COLORS["data"]}"/></g>')
    # la légende
    ly = axis_y + AXIS_H + 8
    lx = LEFT
    legend = (("fab", "fabrication"), ("measure", "mesure MES"), ("test", "test"), ("data", "données"), ("jira", "étape JIRA faite"))
    for kind, label in legend:
        parts.append(f'<rect x="{lx}" y="{ly - 8}" width="10" height="10" rx="2" fill="{COLORS[kind]}"/>')
        parts.append(f'<text x="{lx + 15}" y="{ly + 1}" font-size="10.5" fill="{COLORS["muted"]}">{esc(label)}</text>')
        lx += 15 + 7 * len(label) + 26
    parts.append("</svg>")
    return "".join(parts)


def frieze(user: User, lasermark: str) -> dict[str, Any]:
    """Ce que la route rend : les événements et leur dessin."""
    found = events(user, lasermark)
    counts: dict[str, int] = {}
    for e in found:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return {"lasermark": lasermark, "events": found, "counts": counts, "svg": svg(found, title=f"Frise de {lasermark}")}
