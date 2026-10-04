"""Le cahier de données d'une étude : **toutes** ses données mesurées, le cahier de labo de l'étude,
repris dans son rapport. Une entrée a deux types (``kind``), une seule forme :

- ``prism`` : une vue sur un instantané (:mod:`.snapshots`) d'un type de données de caractérisation -
  un composant de visualisation (``component``, une clé du registre ``DataViz`` côté page,
  ``notebook/static/dataviz/``) et ses réglages (``options``, libres : c'est le composant qui les
  lit ; le serveur ne connaît pas les composants) ;
- ``manual`` : ce que PRISM ne peut pas prévoir - une valeur mesurée, un texte, un tableau collé,
  des fichiers (images annotées, documents) et des liens.

``{id, kind, title, note, objective, interpretation, wafers, measurements, in_report, created_at,
created_by, updated_at, updated_by}`` : ``wafers``, les plaques mesurées (clés de wafer ; vide :
toute la piste) ; ``measurements``, une mesure par étape du procédé (``step_id``, ou ``None`` : non
située) - la même mesure faite à plusieurs étapes est **une** entrée, qu'on compare d'une étape à
l'autre.

**La donnée suit la plaque** : lue sur une version, une entrée s'applique (``applies``) si elle vaut
pour toute la piste ou si l'une de ses plaques est suivie par cette version ; sinon elle reste au
cahier, rangée par la page parmi les « autres plaques ». Une mesure dont l'étape n'est plus dans le
procédé de la version est marquée ``step_retired``.

Les entrées sont rangées dans les métadonnées de l'étude
(:data:`spectre.plugins.experiments.service.NOTEBOOK_KEY`), reportées de version en version ; chaque
changement est une écriture sur la piste (:func:`spectre.plugins.experiments.service.amend`,
``If-Match`` compris). Les données d'avant (vues de l'ancien cahier, preuves) sont converties à la
lecture (:mod:`.legacy`) ; la première écriture dans le cahier enregistre le cahier converti et
retire les anciennes clés de la version qu'elle crée - y compris la liste des preuves Follow : une
entrée garde l'id de la preuve dont elle vient, que la conclusion cite toujours.
"""

from __future__ import annotations

import copy
import json
import math
import re
import secrets
from datetime import datetime, timezone
from typing import Any

import follow

from ...kernel.errors import InvalidInput, NotFound
from ..attachments.store import NOTEBOOK_TYPES, content_url, uploaded_file
from ..experiments import service as experiments
from ..experiments.entities import compact as wafer_key
from ..experiments.repository import get_repository
from . import legacy, snapshots
from .schemas import AttachmentRef, EntryInput, EntryUpdate, LinkInput, MeasurementInput, TableInput, is_web_link

MAX_ENTRIES = 200
MAX_MEASUREMENTS = 30
MAX_WAFERS = 50
MAX_TEXT = 20000
MAX_OPTIONS_SIZE = 20000
MAX_LINKS = 10
MAX_ATTACHMENTS = 12
MAX_ANNOTATIONS = 100
MAX_TABLE_COLUMNS = 50
MAX_TABLE_ROWS = 1000
MAX_CELL = 500
MAX_TABLE_SIZE = 200000
_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,48}$")
_PRISM_FIELDS = ("snapshot_id", "component", "options")
_MANUAL_FIELDS = ("value", "text", "table", "attachments", "links", "annotations")


# -- lecture ---------------------------------------------------------------------------------------


def stored_entries(repo: follow.Repository, version: follow.Experiment) -> list[dict[str, Any]]:
    """Le cahier de ``version`` au format enregistré : ses entrées, puis celles que donnent ses
    données d'avant (:func:`.legacy.convert`) et qu'il n'a pas déjà (par id) - l'ordre de
    :func:`spectre.plugins.experiments.service.notebook_entry_ids`."""
    entries = [copy.deepcopy(entry) for entry in version.metadata.get(experiments.NOTEBOOK_KEY) or [] if isinstance(entry, dict) and entry.get("id")]
    known = {entry["id"] for entry in entries}
    for entry in legacy.convert(repo, version):
        if entry["id"] not in known:
            entries.append(entry)
            known.add(entry["id"])
    return entries


def tracked_wafers(version: follow.Experiment) -> set[str]:
    """Les clés des plaques que ``version`` suit (ses entités physiques)."""
    return {wafer_key(entity.get("sample_id")) for entity in version.metadata.get("physical_tracking") or [] if entity.get("sample_id")} - {""}


class _Reading:
    """Ce qu'une lecture du cahier d'une version sait d'elle : ses plaques et ses étapes."""

    def __init__(self, slug: str, repo: follow.Repository, version: follow.Experiment) -> None:
        self.slug = slug
        self.version = version
        self.wafers = tracked_wafers(version)
        self.steps = set(experiments.step_ids_of(repo, version))
        self.entries = stored_entries(repo, version)

    def applies(self, entry: dict[str, Any]) -> bool:
        wafers = entry.get("wafers") or []
        return not wafers or any(wafer in self.wafers for wafer in wafers)

    def view(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Une entrée telle que l'API la montre : ``applies``, ``step_retired`` sur chaque mesure,
        l'``url`` de chaque fichier."""
        shown = copy.deepcopy(entry)
        shown["applies"] = self.applies(entry)
        for measurement in shown.get("measurements") or []:
            step_id = measurement.get("step_id")
            measurement["step_retired"] = step_id is not None and step_id not in self.steps
            for attachment in measurement.get("attachments") or []:
                attachment["url"] = content_url(self.slug, attachment["id"])
        return shown


def _reading(slug: str, experiment_id: str, version_id: str | None) -> _Reading:
    repo = get_repository(slug)
    return _Reading(slug, repo, experiments.version_of(repo, experiment_id, version_id))


def _selected(reading: _Reading, *, step: str | None, wafer: str | None, kind: str | None) -> list[dict[str, Any]]:
    """Les entrées du cahier lu qui passent les filtres : une mesure à l'étape ``step`` ; la plaque
    ``wafer`` (ou toute la piste) ; le type ``kind``."""
    key = wafer_key(wafer) if wafer else None
    return [
        entry
        for entry in reading.entries
        if (kind is None or entry.get("kind") == kind)
        and (step is None or any(m.get("step_id") == step for m in entry.get("measurements") or []))
        and (key is None or not entry.get("wafers") or key in entry["wafers"])
    ]


def entries(
    slug: str, experiment_id: str, version_id: str | None = None, *, step: str | None = None, wafer: str | None = None, kind: str | None = None
) -> tuple[follow.Experiment, list[dict[str, Any]]]:
    """``(version, entrées)`` : le cahier de la version ``version_id`` de la piste (sa pointe par
    défaut), dans l'ordre, filtré."""
    reading = _reading(slug, experiment_id, version_id)
    return reading.version, [reading.view(entry) for entry in _selected(reading, step=step, wafer=wafer, kind=kind)]


def step_counts(
    slug: str, experiment_id: str, version_id: str | None = None, *, step: str | None = None, wafer: str | None = None, kind: str | None = None
) -> tuple[follow.Experiment, dict[str, int]]:
    """``(version, {step_id: n})`` : pour chaque étape, le nombre d'entrées (filtrées, et qui
    s'appliquent à cette version) qui y ont une mesure - les badges du procédé."""
    reading = _reading(slug, experiment_id, version_id)
    counts: dict[str, int] = {}
    for entry in _selected(reading, step=step, wafer=wafer, kind=kind):
        if reading.applies(entry):
            for step_id in {m.get("step_id") for m in entry.get("measurements") or []} - {None}:
                counts[step_id] = counts.get(step_id, 0) + 1
    return reading.version, counts


def _index(notebook: list[dict[str, Any]], entry_id: str) -> int:
    for i, entry in enumerate(notebook):
        if entry.get("id") == entry_id:
            return i
    raise NotFound("Entrée introuvable dans le cahier de cette étude.", code="notebook_entry_not_found")


def get_entry(slug: str, experiment_id: str, entry_id: str, version_id: str | None = None) -> tuple[follow.Experiment, dict[str, Any]]:
    reading = _reading(slug, experiment_id, version_id)
    return reading.version, reading.view(reading.entries[_index(reading.entries, entry_id)])


# -- validation ------------------------------------------------------------------------------------


def _clean_text(value: str | None, limit: int) -> str | None:
    return (value or "").strip()[:limit] or None


def _title(value: str | None) -> str:
    title = _clean_text(value, legacy.TITLE_LENGTH)
    if not title:
        raise InvalidInput("Donnez un titre à cette entrée.", code="title_required")
    return title


def _objective(value: str | None, parent: follow.Experiment) -> str | None:
    objective = _clean_text(value, 200)
    if objective and not any(o.name == objective for o in parent.objectives):
        raise InvalidInput(f"Objectif « {objective} » introuvable sur cette expérience.", code="unknown_objective")
    return objective


def _wafers(raw: list[str], parent: follow.Experiment, kept: list[str]) -> list[str]:
    """Les plaques mesurées : des clés de wafer, sans doublon, chacune suivie par la version (ou déjà
    sur l'entrée : une plaque que la piste ne suit plus reste citée)."""
    tracked = tracked_wafers(parent)
    wafers: list[str] = []
    for value in raw:
        key = wafer_key(value)
        if not key or key in wafers:
            continue
        if key not in tracked and key not in kept:
            raise InvalidInput(f"La plaque « {value} » n'est pas suivie par cette étude.", code="unknown_wafer")
        wafers.append(key)
    if len(wafers) > MAX_WAFERS:
        raise InvalidInput(f"{MAX_WAFERS} plaques au maximum par entrée.")
    return wafers


def _options(options: dict[str, Any] | None) -> dict[str, Any]:
    options = options or {}
    try:
        size = len(json.dumps(options, ensure_ascii=False, allow_nan=False))
    except ValueError as exc:  # Infinity, NaN : ni JSON, ni relisible
        raise InvalidInput("Réglages de la vue invalides (nombre non fini).") from exc
    if size > MAX_OPTIONS_SIZE:
        raise InvalidInput("Réglages de la vue trop volumineux.")
    return options


def _snapshot(slug: str, snapshot_id: str, known: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if snapshot_id in known:
        return copy.deepcopy(known[snapshot_id])
    try:
        return snapshots.summary(snapshots.load(slug, snapshot_id))
    except NotFound as exc:
        raise InvalidInput("Instantané de données introuvable - rechargez les données.", code="snapshot_not_found") from exc


def _table(raw: TableInput) -> dict[str, Any]:
    columns = [(column or "").strip() for column in raw.columns]
    if not 1 <= len(columns) <= MAX_TABLE_COLUMNS:
        raise InvalidInput(f"Un tableau a de 1 à {MAX_TABLE_COLUMNS} colonnes.", code="invalid_table")
    if len(raw.rows) > MAX_TABLE_ROWS:
        raise InvalidInput(f"{MAX_TABLE_ROWS} lignes au maximum par tableau.", code="invalid_table")
    if any(len(row) != len(columns) for row in raw.rows):
        raise InvalidInput("Chaque ligne du tableau doit avoir une cellule par colonne.", code="invalid_table")
    for cell in [*columns, *(cell for row in raw.rows for cell in row)]:
        if isinstance(cell, str) and len(cell) > MAX_CELL:
            raise InvalidInput(f"Une cellule du tableau dépasse {MAX_CELL} caractères.", code="invalid_table")
        if isinstance(cell, float) and not math.isfinite(cell):
            raise InvalidInput("Une cellule du tableau n'est pas un nombre fini.", code="invalid_table")
    table = {"columns": columns, "rows": [list(row) for row in raw.rows]}
    if len(json.dumps(table, ensure_ascii=False)) > MAX_TABLE_SIZE:
        raise InvalidInput("Tableau trop volumineux.", code="invalid_table")
    return table


def _links(raw: list[LinkInput]) -> list[dict[str, Any]]:
    """Des liens web (``http`` ou ``https`` seulement : un chemin réseau va dans le texte), sans
    doublon."""
    links: list[dict[str, Any]] = []
    for link in raw:
        url = link.url.strip()
        if not is_web_link(url):
            raise InvalidInput(f"Lien invalide ({url[:80] or 'vide'}) : une adresse http ou https.", code="invalid_link")
        if all(known["url"] != url for known in links):
            links.append({"label": _clean_text(link.label, 200), "url": url})
    if len(links) > MAX_LINKS:
        raise InvalidInput(f"{MAX_LINKS} liens au maximum par mesure.", code="invalid_link")
    return links


def _attachments(slug: str, raw: list[AttachmentRef], known: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Les fichiers d'une mesure : téléversés dans ce µprojet (images ou documents acceptés par le
    cahier), ou déjà sur l'entrée."""
    if len(raw) > MAX_ATTACHMENTS:
        raise InvalidInput(f"{MAX_ATTACHMENTS} fichiers au maximum par mesure.", code="invalid_attachments")
    if len({ref.id for ref in raw}) != len(raw):
        raise InvalidInput("Le même fichier figure deux fois.", code="invalid_attachments")
    attachments = []
    for ref in raw:
        meta = known.get(ref.id) or uploaded_file(slug, ref.id, NOTEBOOK_TYPES)
        attachments.append(
            {
                "id": ref.id,
                "caption": _clean_text(ref.caption, 200),
                "filename": meta.get("filename"),
                "content_type": meta.get("content_type"),
                "size": meta.get("size"),
            }
        )
    return attachments


def _finite(*numbers: float | None) -> bool:
    return all(number is None or math.isfinite(number) for number in numbers)


def _annotations(raw: list[Any], attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    images = {a["id"] for a in attachments if (a.get("content_type") or "").startswith("image/")}
    if len(raw) > MAX_ANNOTATIONS:
        raise InvalidInput(f"{MAX_ANNOTATIONS} annotations au maximum par mesure.", code="invalid_annotation")
    if not all(_finite(a.x, a.y, a.x2, a.y2) for a in raw):
        raise InvalidInput("Une annotation a une position qui n'est pas un nombre fini.", code="invalid_annotation")
    if any(annotation.attachment_id not in images for annotation in raw):
        raise InvalidInput("Une annotation désigne une image qui n'est pas dans cette mesure.", code="invalid_annotation")
    return [{**annotation.model_dump(), "label": _clean_text(annotation.label, 200)} for annotation in raw]


def _measurements(
    slug: str, kind: str, raw: list[MeasurementInput], *, steps: list[str], previous: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Les mesures d'une entrée de type ``kind``, validées : une par étape du procédé de la version
    (``steps``) au plus, ou non située ; une étape retirée du procédé, un instantané ou un fichier
    sont acceptés tels quels s'ils sont déjà sur l'entrée (``previous``)."""
    if len(raw) > MAX_MEASUREMENTS:
        raise InvalidInput(f"{MAX_MEASUREMENTS} mesures au maximum par entrée.", code="invalid_measurement")
    if kind == "prism" and not raw:
        raise InvalidInput("Une entrée PRISM a au moins une vue.", code="invalid_measurement")
    if len({m.step_id for m in raw}) != len(raw):
        raise InvalidInput("Une seule mesure par étape (et une seule non située).", code="invalid_measurement")
    known_steps = set(steps) | {m.get("step_id") for m in previous}
    known_snapshots = {m["snapshot_id"]: m.get("snapshot") for m in previous if m.get("snapshot_id") and m.get("snapshot")}
    known_files = {a["id"]: a for m in previous for a in m.get("attachments") or []}
    measurements = []
    for measurement in raw:
        if measurement.step_id is not None and measurement.step_id not in known_steps:
            raise InvalidInput("Étape introuvable dans le procédé de cette version.", code="unknown_step")
        manual = [name for name in _MANUAL_FIELDS if getattr(measurement, name) not in (None, [])]
        prism = [name for name in _PRISM_FIELDS if getattr(measurement, name) is not None]
        if kind == "prism":
            if manual or not measurement.snapshot_id or not measurement.component:
                raise InvalidInput("Une mesure PRISM est une vue : un instantané et un composant, rien d'autre.", code="invalid_measurement")
            if not _COMPONENT_RE.fullmatch(measurement.component):
                raise InvalidInput("Composant de visualisation invalide.", code="invalid_measurement")
            measurements.append(
                {
                    "step_id": measurement.step_id,
                    "snapshot_id": measurement.snapshot_id,
                    "component": measurement.component,
                    "options": _options(measurement.options),
                    "snapshot": _snapshot(slug, measurement.snapshot_id, known_snapshots),
                }
            )
            continue
        if prism:
            raise InvalidInput("Une mesure manuelle n'a pas d'instantané : une valeur, un texte, un tableau, des fichiers ou des liens.", code="invalid_measurement")
        value = measurement.value
        if value is not None and not _finite(value.number):
            raise InvalidInput("La valeur mesurée n'est pas un nombre fini.", code="invalid_measurement")
        attachments = _attachments(slug, measurement.attachments, known_files)
        measurements.append(
            {
                "step_id": measurement.step_id,
                "value": {"number": value.number, "unit": _clean_text(value.unit, 40), "name": _clean_text(value.name, 120)} if value else None,
                "text": _clean_text(measurement.text, MAX_TEXT),
                "table": _table(measurement.table) if measurement.table else None,
                "attachments": attachments,
                "links": _links(measurement.links),
                "annotations": _annotations(measurement.annotations, attachments),
            }
        )
    return measurements


# -- écriture --------------------------------------------------------------------------------------


def _store(builder: follow.ExperimentBuilder, notebook: list[dict[str, Any]]) -> None:
    """Enregistre ``notebook`` dans la version en cours, au format actuel, et en retire les données
    d'avant qu'il reprend (vues de l'ancien cahier, preuves Follow et leurs métadonnées, images des
    preuves) - aucune ancienne version n'est touchée."""
    builder.metadata[experiments.NOTEBOOK_KEY] = notebook
    builder.metadata.pop(experiments.LEGACY_NOTEBOOK_KEY, None)
    for key in experiments.LEGACY_EVIDENCE_KEYED_METADATA:
        builder.metadata.pop(key, None)
    if experiments.ATTACHMENTS_KEY in builder.metadata:
        rest = [a for a in builder.metadata[experiments.ATTACHMENTS_KEY] if not (isinstance(a, dict) and a.get("evidence_id"))]
        if rest:
            builder.metadata[experiments.ATTACHMENTS_KEY] = rest
        else:
            builder.metadata.pop(experiments.ATTACHMENTS_KEY)
    builder.evidence = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_entry(slug: str, experiment_id: str, body: EntryInput, *, author: str, expected_version: str | None) -> tuple[follow.Experiment, dict[str, Any]]:
    """Ajoute une entrée en fin de cahier - ``(nouvelle version, l'entrée)``."""
    title = _title(body.title)
    added: dict[str, Any] = {}

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        notebook = stored_entries(builder.repo, parent)
        if len(notebook) >= MAX_ENTRIES:
            raise InvalidInput(f"{MAX_ENTRIES} entrées au maximum par cahier.", code="notebook_full")
        taken = {entry["id"] for entry in notebook}
        entry_id = f"nb_{secrets.token_hex(6)}"
        while entry_id in taken:
            entry_id = f"nb_{secrets.token_hex(6)}"
        now = _now()
        added.update(
            id=entry_id,
            kind=body.kind,
            title=title,
            note=_clean_text(body.note, MAX_TEXT),
            objective=_objective(body.objective, parent),
            interpretation=_clean_text(body.interpretation, MAX_TEXT),
            wafers=_wafers(body.wafers, parent, []),
            measurements=_measurements(slug, body.kind, body.measurements, steps=experiments.step_ids_of(builder.repo, parent), previous=[]),
            in_report=body.in_report,
            created_at=now,
            created_by=author,
            updated_at=now,
            updated_by=author,
        )
        _store(builder, [*notebook, added])

    version = experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
    return version, _Reading(slug, get_repository(slug), version).view(added)


def update_entry(
    slug: str, experiment_id: str, entry_id: str, body: EntryUpdate, *, author: str, expected_version: str | None
) -> tuple[follow.Experiment, dict[str, Any]]:
    """Modifie les champs envoyés d'une entrée (``measurements`` les remplace toutes ; ``position``
    : sa place dans le cahier, ramenée dans les bornes) - ``(version, l'entrée)``. Une modification
    sans effet ne crée pas de version."""
    changes = body.model_dump(exclude_unset=True)
    position = changes.pop("position", None)

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        notebook = stored_entries(builder.repo, parent)
        index = _index(notebook, entry_id)
        entry = notebook[index]
        updated = copy.deepcopy(entry)
        if "title" in changes:
            updated["title"] = _title(changes["title"])
        for name in ("note", "interpretation"):
            if name in changes:
                updated[name] = _clean_text(changes[name], MAX_TEXT)
        if "objective" in changes:
            updated["objective"] = _objective(changes["objective"], parent)
        if body.wafers is not None:
            updated["wafers"] = _wafers(body.wafers, parent, entry.get("wafers") or [])
        if body.measurements is not None:
            steps = experiments.step_ids_of(builder.repo, parent)
            updated["measurements"] = _measurements(slug, entry["kind"], body.measurements, steps=steps, previous=entry.get("measurements") or [])
        if body.in_report is not None:
            updated["in_report"] = body.in_report
        target = index if position is None else max(0, min(len(notebook) - 1, position))
        if updated == entry and target == index:
            return
        if updated != entry:
            updated.update(updated_by=author, updated_at=_now())
        notebook[index] = updated
        notebook.insert(target, notebook.pop(index))
        _store(builder, notebook)

    version = experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
    reading = _Reading(slug, get_repository(slug), version)
    return version, reading.view(reading.entries[_index(reading.entries, entry_id)])


def remove_entry(slug: str, experiment_id: str, entry_id: str, *, author: str, expected_version: str | None) -> follow.Experiment:
    """Retire une entrée du cahier (elle reste dans l'historique de l'étude) ; les verdicts de la
    conclusion qui la citaient ne la citent plus."""

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        notebook = stored_entries(builder.repo, parent)
        notebook.pop(_index(notebook, entry_id))
        _store(builder, notebook)
        results = builder.conclusion.objective_results
        if any(entry_id in result.evidence_ids for result in results):
            cleaned = [result.model_copy(update={"evidence_ids": [i for i in result.evidence_ids if i != entry_id]}) for result in results]
            builder.conclusion = builder.conclusion.model_copy(update={"objective_results": cleaned})

    return experiments.amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)
