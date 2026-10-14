"""Comparer des structures : les lignes du tableau, lues par leurs sources, et le tableau qui les
compare (:mod:`.table`).

Une ligne se désigne par un **jeton** ``<source>:<corps>``, dans l'ordre voulu (la base d'abord,
par défaut) - ce que porte l'adresse de la page ``/comparateur?item=…`` :

- ``study:<µprojet>/<piste>[@<version>][~<place>]`` : une étude (sa pointe sans version) ; une
  campagne donne une ligne par variante (celle de la plaque de référence d'abord), ``~n`` la seule
  variante ``n`` ; une étude sans structure, une ligne par plaque de son split déclaré, ``~n`` la
  seule ligne ``n`` ;
- ``wafer:<lasermark>`` : la structure qu'a vue une plaque - celle de la dernière étude de vos
  µprojets qui la suit (sa variante pour une campagne) ; source déclarée par le plugin ``wafers`` ;
- ``reference:<slug>[@<numéro>]`` : une version de référence (la dernière sans numéro) ; source
  déclarée par le plugin ``references``.

Les sources sont un registre (:func:`register_source`), comme les fournisseurs de la recherche :
``study`` est ici (le comparateur dépend d'experiments), ``wafer`` et ``reference`` chez les plugins
qui possèdent leurs données (ils dépendent du comparateur). Un jeton mal formé est un 422 ; une ligne
introuvable ou interdite reste dans le tableau avec son erreur, les autres se comparent.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote

import follow

from ...kernel import plugin_states
from ...kernel.errors import DomainError, Forbidden, InvalidInput, NotFound
from ..accounts.service import User
from ..experiments import service as experiments
from ..experiments.repository import branch_tips, get_repository
from ..microprojects import service as microprojects
from ..microprojects.service import Microproject
from ..structures import kinds
from . import table
from .table import Compared

MAX_ITEMS = 30
MAX_ROWS = 60
INVALID_ITEM = "invalid_comparison_item"


@dataclass(frozen=True)
class ItemSource:
    """Une sorte de ligne : ``prefix`` (``study``, ``wafer``, ``reference``), ``resolve`` - les
    lignes d'un jeton (son corps, sans le préfixe), vues par ce lecteur : plusieurs pour une
    campagne -, ``search`` - ce qu'elle propose pour une saisie, ``[{item, source, label,
    sublabel}]`` -, et ``plugin``, celui qui la déclare : éteint, ses jetons ne se lisent plus."""

    prefix: str
    resolve: Callable[[User, str], list[Compared]]
    search: Callable[[User, str, int], list[dict[str, Any]]] | None = None
    plugin: str = ""
    order: int = 100


_SOURCES: dict[str, ItemSource] = {}


def register_source(source: ItemSource) -> None:
    _SOURCES[source.prefix] = source


def _active(source: ItemSource) -> bool:
    return not source.plugin or plugin_states.is_enabled(source.plugin)


def invalid_item(item: str) -> InvalidInput:
    return InvalidInput(f"« {item} » ne désigne ni une plaque, ni une étude, ni une référence.", code=INVALID_ITEM)


def _unreadable(item: str, source: str, error: str) -> Compared:
    return Compared(item, source, item.partition(":")[2] or item, error=error)


def rows_for(user: User, items: list[str]) -> list[Compared]:
    """Les lignes des jetons ``items``, dans leur ordre (une campagne en donne plusieurs)."""
    if not items:
        raise InvalidInput("Choisissez au moins une plaque ou une structure à comparer.", code="no_comparison_items")
    if len(items) > MAX_ITEMS:
        raise InvalidInput(f"{MAX_ITEMS} éléments au plus dans une comparaison.", code="too_many_comparison_items")
    rows: list[Compared] = []
    for item in items:
        prefix, _sep, body = item.partition(":")
        source = _SOURCES.get(prefix)
        if source is None or not body.strip():
            raise invalid_item(item)
        if not _active(source):
            rows.append(_unreadable(item, prefix, "Ce module est désactivé."))
            continue
        try:
            rows.extend(source.resolve(user, body.strip()))
        except DomainError as exc:
            if exc.code == INVALID_ITEM:
                raise
            rows.append(_unreadable(item, prefix, str(exc)))
    if len(rows) > MAX_ROWS:
        raise InvalidInput(f"{MAX_ROWS} lignes au plus dans une comparaison (une campagne en compte une par variante).", code="too_many_comparison_items")
    return rows


def compare(user: User, items: list[str], baseline: int = 0) -> dict[str, Any]:
    """Le tableau de la comparaison des jetons ``items``, à la ligne ``baseline`` (la première par
    défaut) - :func:`table.build`."""
    return compare_rows(rows_for(user, items), baseline)


def compare_rows(rows: list[Compared], baseline: int = 0) -> dict[str, Any]:
    """Le tableau de lignes déjà lues (:func:`rows_for`, :func:`study_rows`) - pour qui compare
    beaucoup de structures sans les relire."""
    return table.build(rows, baseline)


def comparable(first: Compared, second: Compared) -> bool:
    """Si deux lignes ont des colonnes en commun (:func:`table.comparable`)."""
    return table.comparable(first, second)


def differences(result: dict[str, Any], row: int) -> list[dict[str, Any]]:
    """Ce qui distingue la ligne ``row`` d'un tableau de sa base (:func:`table.differences`)."""
    return table.differences(result, row)


def _folded(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").casefold()


def candidates(user: User, q: str, sources: list[str] | None = None, limit: int = 8) -> list[dict[str, Any]]:
    """Ce qu'on peut ajouter à une comparaison pour la saisie ``q`` : ``[{item, source, label,
    sublabel}]``, source par source (``sources`` : celles-là seulement)."""
    q = q.strip()
    if not q:
        return []
    unknown = sorted(set(sources or ()) - _SOURCES.keys())
    if unknown:
        raise InvalidInput(f"Source inconnue : {', '.join(unknown)} (connues : {', '.join(sorted(_SOURCES))}).")
    selected = sorted(
        (s for s in _SOURCES.values() if s.search and _active(s) and (not sources or s.prefix in sources)),
        key=lambda s: (s.order, s.prefix),
    )
    return [found for source in selected for found in (source.search(user, q, limit) if source.search else [])]


# -- les études ------------------------------------------------------------------------------------

_STUDY_RE = re.compile(r"^(?P<mp>[^/@~\s]+)/(?P<exp>[^/@~\s]+)(?:@(?P<version>[^/@~\s]+))?(?:~(?P<place>\d{1,3}))?$")


def study_item(slug: str, experiment_id: str, version_id: str | None = None, place: int | None = None) -> str:
    """Le jeton d'une étude (sa pointe sans ``version_id``), d'une de ses variantes avec ``place``."""
    return f"study:{slug}/{experiment_id}" + (f"@{version_id}" if version_id else "") + (f"~{place}" if place is not None else "")


def readable_microproject(user: User, slug: str) -> Microproject:
    """Le µprojet ``slug``, où ``user`` a un rôle (404 inconnu, 403 sinon)."""
    microproject = microprojects.get_by_slug(slug)
    if microprojects.effective_role(user, microproject) is None:
        raise Forbidden("Vous n'avez pas accès à ce µprojet.")
    return microproject


def fiche_url(slug: str, experiment_id: str, version: follow.Experiment, tip: follow.Experiment) -> str:
    page = f"/microprojets/{quote(slug, safe='')}/experiences/{quote(experiment_id, safe='')}"
    return page if version.id == tip.id else f"{page}?version={quote(version.id, safe='')}"


def _tracked(metadata: dict[str, Any]) -> list[str | None]:
    return [entry.get("sample_id") if isinstance(entry, dict) else None for entry in metadata.get("physical_tracking") or []]


def study_rows(user: User, slug: str, experiment_id: str, version_id: str | None = None, place: int | None = None) -> list[Compared]:
    """Les lignes d'une étude, vue par ``user`` : sa version ``version_id`` (sa pointe sinon) ; une
    campagne, une par variante - la plaque de référence d'abord - ou la seule variante ``place`` ;
    une étude sans structure, une par plaque de son split - ou la seule ligne ``place`` ; une étude
    simple, une seule (``place`` n'y change rien : ses réplicats ont la même structure)."""
    microproject = readable_microproject(user, slug)
    repo = get_repository(microproject.slug)
    tip = experiments.tip_of(repo, experiment_id)
    version = experiments.version_of(repo, experiment_id, version_id)
    ids = experiments.step_ids_of(repo, version)
    number = experiments.version_number(repo, version)
    metadata = version.metadata
    kind = kinds.structure_kind_name(version.structure_type)
    url = fiche_url(microproject.slug, experiment_id, version, tip)
    common = {"source": "study", "url": url, "structure_kind": kind, "metadata": metadata, "step_ids": ids}
    version_label = f"v{number}"
    tracked = _tracked(metadata)

    if kind == "campaign":
        labels = metadata.get("campaign_labels") or []
        count = max(len(metadata.get("campaign_factor_values") or []), len(labels))
        reference = experiments.reference_place_of(version)
        if place is not None:
            if not 0 <= place < count:
                raise NotFound(f"Cette campagne n'a pas de variante n° {place + 1}.", code="unknown_variant")
            places = [place]
        else:
            places = sorted(range(count), key=lambda i: (i != reference, i))
        rows = []
        for i in places:
            sample = tracked[i] if i < len(tracked) else None
            try:
                process = kinds.variant_process(metadata, ids, i)
                detail = labels[i] if i < len(labels) else ""
            except InvalidInput:  # une campagne d'avant les plans : son procédé commun seulement
                process = metadata.get("structureforge_process")
                detail = "procédé commun (variante non enregistrée)"
            rows.append(
                Compared(
                    study_item(microproject.slug, experiment_id, version.id, i),
                    label=sample or f"Variante {i + 1}",
                    version=version_label,
                    sublabel=" · ".join(part for part in (version.title, detail) if part),
                    context=microproject.name,
                    process=process if isinstance(process, dict) else None,
                    wafers=[sample] if sample else [],
                    badge="RÉF" if i == reference else None,
                    **common,
                )
            )
        return rows

    if kind == "declared":
        declared = kinds.declared_structure_payload(microproject.slug, version.structure_type, version.structure) or {"factors": [], "wafers": []}
        lines = declared["wafers"]
        if place is not None and not 0 <= place < len(lines):
            raise NotFound(f"Ce split n'a pas de ligne n° {place + 1}.", code="unknown_variant")
        rows = []
        for i in [place] if place is not None else range(len(lines)):
            sample = tracked[i] if i < len(tracked) else None
            rows.append(
                Compared(
                    study_item(microproject.slug, experiment_id, version.id, i),
                    label=sample or lines[i]["name"],
                    version=version_label,
                    sublabel=" · ".join(part for part in (version.title, lines[i]["name"] if sample else "") if part),
                    context=microproject.name,
                    declared=(list(declared["factors"]), list(lines[i]["values"])),
                    wafers=[sample] if sample else [],
                    **common,
                )
            )
        return rows

    process = metadata.get("structureforge_process")
    note = None
    if kind == "images":
        note = "Structure donnée en images : rien à comparer paramètre par paramètre."
    elif not isinstance(process, dict):
        note = "Cette étude n'a pas de procédé enregistré."
    return [
        Compared(
            study_item(microproject.slug, experiment_id, version.id),
            label=version.title,
            version=version_label,
            context=microproject.name,
            process=process if isinstance(process, dict) and kind != "images" else None,
            wafers=[sample for sample in tracked if sample],
            note=note,
            **common,
        )
    ]


def _resolve_study(user: User, body: str) -> list[Compared]:
    found = _STUDY_RE.fullmatch(body)
    if found is None:
        raise invalid_item(f"study:{body}")
    place = int(found["place"]) if found["place"] is not None else None
    return study_rows(user, found["mp"], found["exp"], found["version"], place)


def _search_studies(user: User, q: str, limit: int) -> list[dict[str, Any]]:
    """Les études (la pointe de chaque piste) de vos µprojets dont le titre ou le nom de piste
    contient ``q`` (sans casse ni accents), la plus récente d'abord."""
    needle = _folded(q)
    selected = microprojects.list_all()
    access = microprojects.accesses(user, selected)
    found: list[tuple[str, dict[str, Any]]] = []
    for microproject in selected:
        if access.get(microproject.id) is None or access[microproject.id].role is None:
            continue
        for tip in branch_tips(get_repository(microproject.slug)):
            if needle not in _folded(tip.title or "") and needle not in _folded(tip.branch or ""):
                continue
            kind = kinds.structure_kind_name(tip.structure_type)
            count = len(tip.metadata.get("campaign_labels") or []) if kind in ("campaign", "declared") else 0
            detail = f"campagne · {count} variantes" if kind == "campaign" else f"split déclaré · {count} plaques" if kind == "declared" else "en images" if kind == "images" else ""
            found.append(
                (
                    tip.created_at.isoformat(),
                    {
                        "item": study_item(microproject.slug, tip.branch),
                        "source": "study",
                        "label": tip.title or tip.branch,
                        "sublabel": " · ".join(part for part in (microproject.name, detail) if part),
                    },
                )
            )
    found.sort(key=lambda entry: entry[0], reverse=True)
    return [candidate for _date, candidate in found[:limit]]


register_source(ItemSource("study", _resolve_study, _search_studies, order=20))
