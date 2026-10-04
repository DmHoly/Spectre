"""Les données d'une étude d'avant le cahier unique, converties **à la lecture** en entrées du cahier
(:mod:`.service`) - aucune version n'est réécrite : une version garde ses anciennes clés, et le cahier
converti n'est enregistré qu'à la première écriture dans le cahier (qui retire alors ces clés de la
version qu'elle crée).

- une **vue** de l'ancien cahier (``metadata["data_notebook"]``) devient une entrée ``prism`` d'une
  seule mesure, non située (``step_id`` nul), qui garde son id, sa note, son objectif et sa place
  dans le rapport ;
- une **preuve** Follow (``Experiment.evidence``) et ce que Spectre rangeait pour elle
  (``metadata["evidence_extra"]`` : objectif, interprétation, réglages d'un ancien graphique,
  annotations des images ; ``metadata["evidence_links"]`` ; les images de ``metadata["attachments"]``
  qui portent son ``evidence_id``) devient une entrée ``manual`` d'une seule mesure, **qui garde son
  id** - les verdicts de la conclusion (``evidence_ids``) la citent toujours. Son ``step_index``
  devient l'id de l'étape (:func:`spectre.plugins.experiments.service.step_id_at`), lu sur la version
  qui a ajouté la preuve : la position qu'elle désignait alors.

Rien n'est perdu : la description fait le titre (et la note, si elle dépasse la longueur d'un
titre) ; une mesure chiffrée unique fait la valeur, plusieurs (ou une valeur non numérique, une
incertitude...) un tableau ; les liens web restent des liens, un chemin réseau ou disque (un lien
n'est qu'en ``http`` ou ``https``) passe dans le texte de la mesure, comme la référence (``source``)
quand elle n'est pas l'un des liens, la description d'un ancien graphique, la somme de contrôle et
une étape que le procédé de la version d'alors n'avait pas.
"""

from __future__ import annotations

import math
from typing import Any

import follow

from ..experiments import service as experiments

TITLE_LENGTH = 200


def convert(repo: follow.Repository, version: follow.Experiment) -> list[dict[str, Any]]:
    """Les entrées du cahier que donnent les données d'avant de ``version`` (lue dans ``repo``), au
    format enregistré : les vues de l'ancien cahier, puis les preuves, chacune dans son ordre."""
    entries = [_from_view(view) for view in version.metadata.get(experiments.LEGACY_NOTEBOOK_KEY) or [] if _has_id(view)]
    if not version.evidence:
        return entries
    introduced = _introducing_versions(repo, version, {evidence.id for evidence in version.evidence})
    extras = version.metadata.get("evidence_extra") or {}
    links = version.metadata.get("evidence_links") or {}
    files = [a for a in version.metadata.get(experiments.ATTACHMENTS_KEY) or [] if isinstance(a, dict) and a.get("id")]
    for evidence in version.evidence:
        entries.append(
            _from_evidence(
                repo,
                evidence,
                introduced.get(evidence.id, version),
                extras.get(evidence.id) or {},
                list(links.get(evidence.id) or []),
                [a for a in files if a.get("evidence_id") == evidence.id],
            )
        )
    return entries


def _has_id(item: Any) -> bool:
    return isinstance(item, dict) and isinstance(item.get("id"), str) and bool(item["id"])


def _introducing_versions(repo: follow.Repository, version: follow.Experiment, ids: set[str]) -> dict[str, follow.Experiment]:
    """Pour chaque preuve de ``ids``, la plus ancienne version de l'ascendance de ``version`` (tous
    ses parents, une fusion comprise) qui la porte : celle qui l'a ajoutée."""
    ancestry: dict[str, follow.Experiment] = {}
    pending = [version]
    while pending:
        current = pending.pop()
        if current.id in ancestry:
            continue
        ancestry[current.id] = current
        for parent_id in current.parents:
            if parent_id not in ancestry:
                try:
                    pending.append(repo.get(parent_id))
                except (KeyError, follow.FollowError):
                    continue
    first: dict[str, follow.Experiment] = {}
    for ancestor in sorted(ancestry.values(), key=lambda v: v.created_at.timestamp()):
        for evidence in ancestor.evidence:
            if evidence.id in ids:
                first.setdefault(evidence.id, ancestor)
    return first


def _from_view(view: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": view["id"],
        "kind": "prism",
        "title": view.get("title") or "Vue",
        "note": view.get("note"),
        "objective": view.get("objective"),
        "interpretation": None,
        "wafers": [],
        "measurements": [
            {
                "step_id": None,
                "snapshot_id": view.get("snapshot_id"),
                "component": view.get("component"),
                "options": view.get("options") or {},
                "snapshot": {
                    "hook": view.get("hook"),
                    "hook_title": view.get("hook_title"),
                    "wafers": view.get("wafers") or [],
                    "source": view.get("source"),
                    "fetched_at": view.get("fetched_at"),
                    "row_count": view.get("row_count"),
                },
            }
        ],
        "in_report": view.get("in_report") is not False,
        "created_at": view.get("created_at"),
        "created_by": view.get("created_by"),
        "updated_at": view.get("updated_at") or view.get("created_at"),
        "updated_by": view.get("updated_by") or view.get("created_by"),
    }


def _is_web(link: str) -> bool:
    return link.lower().startswith(("http://", "https://"))


def _metrics(metrics: dict[str, follow.Quantity]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """``(valeur, tableau)`` : une seule mesure chiffrée, sans incertitude ni note, fait la valeur ;
    toute autre combinaison, un tableau d'une ligne par mesure."""
    if not metrics:
        return None, None
    if len(metrics) == 1:
        [(name, quantity)] = metrics.items()
        number = quantity.value
        if isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number) and quantity.uncertainty is None and not quantity.note:
            return {"number": number, "unit": quantity.unit, "name": name}, None
    with_uncertainty = any(q.uncertainty is not None for q in metrics.values())
    with_note = any(q.note for q in metrics.values())
    columns = ["Mesure", "Valeur", "Unité"] + (["Incertitude"] if with_uncertainty else []) + (["Note"] if with_note else [])
    rows = [
        [name, quantity.value, quantity.unit] + ([quantity.uncertainty] if with_uncertainty else []) + ([quantity.note] if with_note else [])
        for name, quantity in metrics.items()
    ]
    return None, {"columns": columns, "rows": rows}


def _graph_lines(config: dict[str, Any] | None) -> list[str]:
    """Une ancienne preuve « graphique » : sa description (on n'en crée plus, rien n'est relu)."""
    if not config:
        return []
    axes = " / ".join(str(config[key]) for key in ("x_label", "y_label") if config.get(key))
    details = [str(config["title"])] if config.get("title") else []
    details += [f"axes : {axes}"] if axes else []
    details += [f"requête : {config['query']}"] if config.get("query") else []
    return ["Graphique (description seule)" + (" - " + " ; ".join(details) if details else "")]


def _from_evidence(
    repo: follow.Repository,
    evidence: follow.Evidence,
    introduced: follow.Experiment,
    extra: dict[str, Any],
    links: list[str],
    files: list[dict[str, Any]],
) -> dict[str, Any]:
    description = (evidence.description or "").strip() or "Preuve"
    title = description if len(description) <= TITLE_LENGTH else description[: TITLE_LENGTH - 1].rstrip() + "…"
    links = [link for link in (str(link).strip() for link in links) if link]
    source = (evidence.source or "").strip()

    text: list[str] = []
    if source and source not in links:
        text.append(f"Référence : {source}")
    text += [f"Chemin : {link}" for link in links if not _is_web(link)]
    text += _graph_lines(extra.get("graph_config"))
    if evidence.checksum:
        text.append(f"Somme de contrôle : {evidence.checksum}")

    attachments = [
        {
            "id": a["id"],
            "caption": a.get("caption"),
            "filename": a.get("filename"),
            "content_type": a.get("content_type"),
            "size": a.get("size"),
        }
        for a in files
    ]
    images = [a["id"] for a in attachments if (a.get("content_type") or "image/").startswith("image/")]
    annotations = [
        {
            "attachment_id": annotation.get("attachment_id") or (images[0] if images else None),
            "type": annotation.get("type"),
            "x": annotation.get("x"),
            "y": annotation.get("y"),
            "x2": annotation.get("x2"),
            "y2": annotation.get("y2"),
            "label": annotation.get("label"),
        }
        for annotation in extra.get("image_annotations") or []
        if isinstance(annotation, dict)
    ]
    value, table = _metrics(dict(evidence.metrics))
    step_id = experiments.step_id_at(repo, introduced, evidence.step_index) if evidence.step_index is not None else None
    if evidence.step_index is not None and step_id is None:
        text.append(f"Étape n° {evidence.step_index + 1} du procédé d'alors (introuvable)")
    created_at = (evidence.collected_at or introduced.created_at).isoformat()
    return {
        "id": evidence.id,
        "kind": "manual",
        "title": title,
        "note": description if title != description else None,
        "objective": extra.get("objective"),
        "interpretation": extra.get("interpretation"),
        "wafers": [],
        "measurements": [
            {
                "step_id": step_id,
                "value": value,
                "text": "\n".join(text) or None,
                "table": table,
                "attachments": attachments,
                "links": [{"label": None, "url": link} for link in links if _is_web(link)],
                "annotations": annotations,
            }
        ],
        "in_report": True,
        "created_at": created_at,
        "created_by": introduced.author,
        "updated_at": created_at,
        "updated_by": introduced.author,
    }
