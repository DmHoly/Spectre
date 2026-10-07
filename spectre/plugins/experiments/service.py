"""Le domaine d'une étude : une **piste** (une branche Follow, son ``experiment_id``) et ses
**versions** (des commits immuables, ``version_id``).

Toute écriture sur une piste passe par :func:`amend`, sous le verrou du µprojet
(:func:`spectre.plugins.experiments.repository.writing`) : elle part de la pointe de la piste,
refuse une version attendue périmée (``expected_version``, l'``If-Match`` du front : jamais de
fourche implicite), reporte **tout** le parent, applique le changement et ne commite que s'il y a
une différence. Les écritures légères (statut, conclusion, étiquettes, entités, images de la
structure, et celles des plugins qui écrivent dans une étude : le cahier) sont des ``change``
passés à :func:`amend` ; une évolution (:func:`evolve`) aussi, formulaire d'intention revalidé.
Bifurquer, c'est créer une nouvelle piste à partir d'une version (:func:`create` avec
``from_version``) ; combiner deux études aussi : une nouvelle piste à deux parents (:func:`create`
avec ``merge_of``) ; partir de plaques existantes aussi : une nouvelle piste qui reprend la
structure de l'étude qui les suit (:func:`create` avec ``wafer_origin``).
"""

from __future__ import annotations

import copy
import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable, NamedTuple

import follow
from structureforge.adapters import follow_adapter
from structureforge.adapters.follow_adapter import ProcessStructure

from ...kernel.errors import Conflict, InvalidInput, NotFound, PreconditionFailed
from ..structures import campaigns, kinds, simulation
from ..structures.schemas import CampaignPayload, ImagesPayload, StructureImageInput
from . import refs, versioning
from .entities import (
    EntityTrackingInput,
    blank_entity,
    clean_entity_entries,
    compact,
    has_tracked_physical_entity,
    named_entities,
    refuse_duplicate_wafers,
    set_study_fdl,
)
from .repository import (
    HOLD_KEY,
    RUNNING_STATUSES,
    VERSION_ID_RE,
    delete_line,
    display_status,
    get_repository,
    retire_line,
    retired_lines,
    writing,
)
from .schemas import ConclusionRequest, CreateExperimentRequest, EvolveRequest, FromVersion, ObjectiveInput, WaferOrigin

CONTEXT_METADATA_KEY = "context"

# La version de référence dont part une étude (``{reference, version}``, plugin references - qui
# dépend d'experiments, pas l'inverse : ici, la forme seulement). Posée au lancement, reportée par
# amend() comme toute métadonnée, gardée par une fourche et par une combinaison (celle de la
# première étude) quand la requête n'en donne pas.
REFERENCE_ORIGIN_KEY = "reference_origin"

# L'étude dont viennent les plaques d'une étude partie de plaques existantes (``{microproject,
# experiment_id, version_id, variant}`` : son µprojet, sa piste, la version dont la structure a été
# reprise et, pour une campagne, la variante que portaient les plaques). Posée au lancement, reportée
# par amend() ; une fourche ou une combinaison ne la reprennent pas (leur filiation dit d'où elles
# viennent). Dans le même µprojet, la nouvelle piste descend aussi de cette version.
WAFER_ORIGIN_KEY = "wafer_origin"
# les plaques d'une étude simple déclarées comme répétitions exactes de la structure de référence
REPEATS_KEY = "repeats"
# La plaque de référence d'une campagne : la place (l'index de la variante, dans physical_tracking)
# qui répète la structure de référence, ou None quand le split n'en a pas. Une campagne d'avant ce
# choix n'a pas la clé : sa première variante était la référence (reference_place_of).
REFERENCE_PLACE_KEY = "reference_place"
# Sans plaque de référence dans le split, celle à laquelle on se compare : ``{experiment_id,
# version_id, sample_id}`` - une étude du µprojet (celle dont la campagne part, par défaut dans le
# constructeur) et, au choix, une de ses plaques. Facultative.
COMPARISON_KEY = "comparison_reference"

# Le cahier de données d'une étude (plugin notebook, qui dépend d'experiments et non l'inverse) : ses
# entrées sont rangées dans les métadonnées, sous NOTEBOOK_KEY, chacune avec son ``id``. Les données
# d'avant le cahier unique restent lisibles, sans qu'aucune version soit réécrite : les vues de
# l'ancien cahier (LEGACY_NOTEBOOK_KEY), les preuves Follow (``Experiment.evidence``) et ce que les
# métadonnées rangeaient par id de preuve (LEGACY_EVIDENCE_KEYED_METADATA ; les images d'une preuve,
# dans ATTACHMENTS_KEY, portent son ``evidence_id``), et les jeux de l'ancienne galerie d'images
# externes (LEGACY_IMAGE_SETS_KEY). Le plugin notebook les convertit à la lecture et les remplace au
# premier changement du cahier ; experiments n'en connaît que les ids - pour les compter (le détail)
# et les citer (la conclusion).
NOTEBOOK_KEY = "notebook_entries"
LEGACY_NOTEBOOK_KEY = "data_notebook"
LEGACY_IMAGE_SETS_KEY = "data_items"
LEGACY_EVIDENCE_KEYED_METADATA = ("evidence_links", "evidence_extra")
ATTACHMENTS_KEY = "attachments"
_LINEAGE_FIELDS = {"id", "created_at", "author", "parents", "references"}
_LINEAGE_ROLES = ("baseline", "merge_source")


# -- lecture ---------------------------------------------------------------------------------------


def tip_of(repo: follow.Repository, experiment_id: str) -> follow.Experiment:
    """La dernière version de la piste ``experiment_id``."""
    tip_id = repo.branches.get(experiment_id)
    if tip_id is None:
        raise NotFound(f"Expérience « {experiment_id} » introuvable.", code="experiment_not_found")
    return repo.get(tip_id)


def history_of(repo: follow.Repository, experiment_id: str) -> list[follow.Experiment]:
    """Les versions de la piste, de la première à la pointe (celles d'avant sa fourche comprises)."""
    return list(reversed(repo.log(tip_of(repo, experiment_id).id)))


def version_of(repo: follow.Repository, experiment_id: str, version_id: str | None) -> follow.Experiment:
    """La version ``version_id`` de la piste (sa pointe quand ``version_id`` est vide)."""
    if not version_id:
        return tip_of(repo, experiment_id)
    for version in repo.log(tip_of(repo, experiment_id).id):
        if version.id == version_id:
            return version
    raise NotFound(f"Version « {version_id} » introuvable sur cette piste.", code="version_not_found")


def experiment_of_version(repo: follow.Repository, version_id: str) -> str:
    """La piste d'une version (un ancien lien vers un id de version) : celle sur laquelle elle a été
    enregistrée, ou à défaut une piste dont l'histoire la contient."""
    versions = {version.id: version for version in repo}
    version = versions.get(version_id)
    if version is not None:
        candidates = [version.branch, *sorted(repo.branches)]
        for name in candidates:
            if name in repo.branches and any(v.id == version_id for v in repo.log(repo.branches[name])):
                return name
    raise NotFound(f"Version « {version_id} » introuvable.", code="version_not_found")


def continued_at(repo: follow.Repository, version: follow.Experiment) -> datetime | None:
    """Quand le travail a repris après ``version`` : le début de sa première suite structurelle -
    une version dérivée qui change la structure, ou une autre piste qui en part. ``None`` sinon."""
    starts = [
        child.created_at
        for child in repo
        if version.id in child.parents
        and (child.branch != version.branch or versioning.changes_structure(version.metadata, child.metadata))
    ]
    return min(starts) if starts else None


def structural_baseline(repo: follow.Repository, version: follow.Experiment) -> follow.Experiment | None:
    """La version de structure qui précède ``version`` : la comparaison par défaut du diff. Une
    étiquette, une preuve ou un statut ne changent pas la structure - le diff d'une telle version
    se fait donc avec la structure d'avant, pas avec son parent immédiat."""
    structural = versioning.structural_versions(list(reversed(repo.log(version.id))))
    return structural[-2] if len(structural) >= 2 else None


def _ids(items: Any) -> list[str]:
    return [item["id"] for item in items or [] if isinstance(item, dict) and isinstance(item.get("id"), str)]


def notebook_entry_ids(version: follow.Experiment) -> list[str]:
    """Les ids des entrées du cahier de ``version``, sans doublon : celles enregistrées sous :data:`NOTEBOOK_KEY`, puis les données d'avant que le plugin
    notebook convertit à la lecture - les vues de l'ancien cahier, les preuves Follow, puis les jeux
    de l'ancienne galerie d'images externes (une preuve ou un jeu converti garde son id)."""
    ids: list[str] = []
    for entry_id in [
        *_ids(version.metadata.get(NOTEBOOK_KEY)),
        *_ids(version.metadata.get(LEGACY_NOTEBOOK_KEY)),
        *(evidence.id for evidence in version.evidence),
        *_ids(version.metadata.get(LEGACY_IMAGE_SETS_KEY)),
    ]:
        if entry_id not in ids:
            ids.append(entry_id)
    return ids


class StructureState(NamedTuple):
    """Ce que le diff compare d'une version : sa structure (type et données Follow), ses métadonnées
    et les ids de ses étapes - lus dans son dépôt (:func:`state_of`), ou gardés à part (l'instantané
    d'une version de référence, plugin references)."""

    structure_type: str
    structure: Any
    metadata: dict[str, Any]
    step_ids: list[str]


def state_of(repo: follow.Repository, version: follow.Experiment) -> StructureState:
    """Ce que le diff compare de ``version``, lue dans ``repo`` (ses ids d'étape : :func:`step_ids_of`)."""
    return StructureState(version.structure_type, version.structure, version.metadata, step_ids_of(repo, version))


def structure_diff(before_repo: follow.Repository, before: follow.Experiment, after_repo: follow.Repository, after: follow.Experiment) -> dict[str, Any]:
    """Le diff de ``before`` à ``after``, chacune lue dans son dépôt (``before_repo``,
    ``after_repo``) - voir :func:`compare_states`."""
    return compare_states(state_of(before_repo, before), state_of(after_repo, after))


def compare_states(before: StructureState, after: StructureState) -> dict[str, Any]:
    """``{entries, label_changes, param_changes, step_changes}`` : Follow's leaf-by-leaf diff from
    ``before``'s structure to ``after``'s - or, when one of them is given as pictures,
    ``{entries: [], summary}`` in plain French (position by position, a reordering would read as
    "everything changed") - and, apart, what changed to the layer labels and to their grouping by
    brick (:func:`kinds.describe_label_changes`), to the declared parameters
    (:func:`kinds.describe_param_changes`) and to the step names (:func:`kinds.describe_step_changes`),
    which the geometry does not carry - a renamed step alone is a patch, never an empty diff. The
    steps are matched by id, by position between two versions that share none."""
    compared = (before.metadata, after.metadata, before.step_ids, after.step_ids)
    apart = {
        "label_changes": kinds.describe_label_changes(*compared),
        "param_changes": kinds.describe_param_changes(*compared),
        "step_changes": kinds.describe_step_changes(*compared),
    }
    summary = kinds.describe_image_changes(before.structure_type, before.structure, after.structure_type, after.structure)
    if summary is not None:
        return {"entries": [], "summary": summary, **apart}
    return {**follow.diff_structures(before.structure, after.structure).model_dump(mode="json"), **apart}


def structure_change_level(before_metadata: dict[str, Any] | None, after_metadata: dict[str, Any]) -> str:
    """Le niveau du changement de structure des métadonnées ``before_metadata`` à ``after_metadata``
    (:mod:`.versioning` : ``initial`` sans ``before_metadata``, ``major``, ``minor``, ``patch`` -
    étiquettes, nom d'étape, unité ajoutée seule -, ``none``)."""
    after = versioning.structure_signature(after_metadata)
    if after is None:
        return "none"
    before = versioning.structure_signature(before_metadata) if before_metadata is not None else None
    return versioning.classify_process_change(before, after)


# -- l'identité des étapes -------------------------------------------------------------------------
#
# Chaque étape du procédé d'une version porte un id stable (``st_<8 hex>``, voir
# ``structures.simulation.settle_step_ids``), rangé sous ``process_step_ids`` dans les métadonnées,
# dans l'ordre des étapes de ``structureforge_process`` - à part du procédé : ni le versionnage
# (``versioning.structure_signature``) ni StructureForge ne le voient. Une version n'est jamais
# réécrite : celle qui a été enregistrée sans ids (avant eux) en reçoit à la lecture
# (:func:`step_ids_of`) - ceux de son premier parent tant que la suite des types d'étapes est la
# même (la règle des écritures, :func:`_settled_step_ids`), sinon dérivés de son id et de la
# position : toujours les mêmes pour elle, et les mêmes d'une ancienne version à la suivante. Toute
# version écrite ensuite les enregistre (:func:`amend` reporte ceux du parent, une évolution, une
# fourche ou une campagne les règle avec :meth:`_PreparedStructure.step_metadata`).


def _derived_step_ids(version_id: str, count: int) -> list[str]:
    """Les ids d'une version enregistrée sans eux : tirés de son id et de la position de l'étape,
    distincts entre eux - les mêmes à chaque lecture."""
    ids: list[str] = []
    for index in range(count):
        salt = 0
        while True:
            seed = f"{version_id}:{index}" + (f":{salt}" if salt else "")
            candidate = "st_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
            if candidate not in ids:
                break
            salt += 1
        ids.append(candidate)
    return ids


def _step_kinds(version: follow.Experiment) -> list[Any] | None:
    """La suite des types d'étapes du procédé de ``version`` (``None`` sans procédé éditable)."""
    process = version.metadata.get("structureforge_process")
    if not isinstance(process, dict):
        return None
    return [step.get("kind") if isinstance(step, dict) else None for step in process.get("steps") or []]


def _stored_step_ids(version: follow.Experiment, count: int) -> list[str] | None:
    """Les ids que ``version`` a enregistrés pour ses ``count`` étapes - ``None`` s'il n'y en a pas
    (ou s'ils sont mal formés, en double, ou pas un par étape)."""
    stored = version.metadata.get(simulation.STEP_IDS_METADATA_KEY)
    if (
        isinstance(stored, list)
        and len(stored) == count
        and len(set(stored)) == count
        and all(isinstance(step_id, str) and simulation.STEP_ID_RE.fullmatch(step_id) for step_id in stored)
    ):
        return list(stored)
    return None


def _first_parent(repo: follow.Repository, version: follow.Experiment) -> follow.Experiment | None:
    if not version.parents:
        return None
    try:
        return repo.get(version.parents[0])
    except (KeyError, follow.FollowError):
        return None


def step_ids_of(repo: follow.Repository, version: follow.Experiment) -> list[str]:
    """L'id de chaque étape du procédé de ``version`` (lue dans ``repo``), dans l'ordre (vide sans
    procédé éditable) : ceux qu'elle a enregistrés ; à défaut, ceux de son premier parent (lus de la
    même façon) tant que la suite des types d'étapes est la même - la règle d'une écriture sans ids
    (:func:`_settled_step_ids`) ; sinon, ou pour une racine, ceux dérivés de son id
    (:func:`_derived_step_ids`). Une lecture seule, toujours la même pour une version."""
    kinds = _step_kinds(version)
    if kinds is None:
        return []
    current = version
    while True:
        stored = _stored_step_ids(current, len(kinds))
        if stored is not None:
            return stored
        parent = _first_parent(repo, current)
        if parent is None or _step_kinds(parent) != kinds:
            return _derived_step_ids(current.id, len(kinds))
        current = parent


def step_id_at(repo: follow.Repository, version: follow.Experiment, index: int) -> str | None:
    """L'id de l'étape à la position ``index`` (à partir de 0) du procédé de ``version`` - ce que
    devient un ancien ``step_index`` (celui d'une preuve, ou d'un facteur d'une campagne enregistrée
    avant les ids d'étape : ``-1`` y désigne le substrat, ``campaigns.SUBSTRATE_STEP_ID``). ``None``
    hors du procédé."""
    ids = step_ids_of(repo, version)
    return ids[index] if 0 <= index < len(ids) else None


def editable_process(repo: follow.Repository, version: follow.Experiment, *, variant: int | None = None) -> dict[str, Any] | None:
    """Le procédé éditable de ``version`` (substrat, étapes, paramètres déclarés), chaque étape
    portant son ``id`` (:func:`step_ids_of`), les étiquettes de couches (``layer_labels``, par
    position d'étape comme les paramètres déclarés ; ``{}`` sans étiquette) et les briques dont les
    étapes font partie (``bricks``, par positions d'étape ; ``[]`` sans brique) - ``None`` sans
    procédé éditable (une structure en images). ``variant`` : celui d'une variante d'une campagne
    (son index), les valeurs de ses facteurs appliquées - ce qu'a vu la plaque de cette variante ;
    :class:`InvalidInput` hors d'une campagne (``not_a_campaign``)."""
    ids = step_ids_of(repo, version)
    if variant is None:
        return editable_process_from(version.metadata, ids)
    if version.structure_type != kinds.ProcessLot.registry_key():
        raise InvalidInput("Cette expérience n'est pas une campagne à plusieurs variantes.", code="not_a_campaign")
    metadata = {**version.metadata, "structureforge_process": kinds.variant_process(version.metadata, ids, variant)}
    return editable_process_from(metadata, ids)


def editable_process_from(metadata: dict[str, Any], ids: list[str]) -> dict[str, Any] | None:
    """:func:`editable_process` des métadonnées d'une version (``metadata``) dont les étapes portent
    ``ids`` - aussi pour un instantané gardé hors du dépôt (une version de référence)."""
    process = metadata.get("structureforge_process")
    if process is None:
        return None
    payload = copy.deepcopy(process)
    payload["steps"] = [{"id": step_id, **step} for step_id, step in zip(ids, payload.get("steps") or [])]
    labels = metadata.get(simulation.LAYER_LABELS_METADATA_KEY)
    position = {step_id: i for i, step_id in enumerate(ids)}
    payload["layer_labels"] = {
        str(position[step_id]): copy.deepcopy(label) for step_id, label in (labels if isinstance(labels, dict) else {}).items() if step_id in position
    }
    payload["bricks"] = simulation.bricks_json(simulation.bricks_from_metadata(metadata.get(simulation.BRICKS_METADATA_KEY), ids))
    return payload


def _metadata_with_step_ids(repo: follow.Repository, version: follow.Experiment) -> dict[str, Any]:
    """Les métadonnées de ``version``, ses ids d'étape écrits (ceux qu'on lit s'ils ne l'étaient pas,
    :func:`step_ids_of`) - ce qu'une version suivante reporte : ses étapes gardent ainsi les ids
    qu'on lisait sur celle-ci."""
    metadata = copy.deepcopy(version.metadata)
    if isinstance(metadata.get("structureforge_process"), dict):
        metadata[simulation.STEP_IDS_METADATA_KEY] = step_ids_of(repo, version)
    return metadata


def _settled_step_ids(
    requested: list[str | None], process: dict[str, Any], parent: follow.Experiment | None, parent_ids: list[str]
) -> list[str]:
    """Les ids des étapes d'un nouveau procédé (``process``) qui part de ``parent`` (dont les étapes
    portent ``parent_ids``, :func:`step_ids_of`) : ceux que le client renvoie (les ids reçus,
    conservés), un neuf pour une nouvelle étape, et pour une étape dupliquée ou un id mal formé
    (:func:`simulation.settle_step_ids`). Un client qui n'envoie aucun id (un script, une page
    d'avant) garde ceux du parent, par position, tant que la suite des types d'étapes n'a pas
    changé - sinon, de nouveaux ids."""
    if parent is not None and not any(requested) and _step_kinds(parent) == [step.get("kind") for step in process["steps"]]:
        return list(parent_ids)
    return simulation.settle_step_ids(requested)


# -- écriture --------------------------------------------------------------------------------------


Change = Callable[[follow.ExperimentBuilder, follow.Experiment], None]


def amend(
    slug: str,
    experiment_id: str,
    *,
    author: str,
    expected_version: str | None = None,
    change: Change,
    revalidate_form: bool = False,
) -> follow.Experiment:
    """Le seul chemin d'écriture sur une piste existante. Sous le verrou du µprojet : la pointe de
    ``experiment_id`` (:class:`NotFound` sinon) ; :class:`PreconditionFailed` si
    ``expected_version`` est donnée et n'est plus la pointe ; un builder qui reporte **tout** le
    parent (titre, intention, hypothèse, objectifs, étapes, références, métadonnées - tous les
    champs propres à Spectre -, réponses au formulaire, preuves, étiquettes, conclusion) ;
    ``change(builder, parent)`` ; puis le commit, seulement si quelque chose a changé - sinon la
    pointe est renvoyée telle quelle, sans nouvelle version.

    Les réponses au formulaire d'intention sont reportées, pas saisies : le formulaire n'est pas
    revalidé (un formulaire activé après coup ne bloque donc pas l'étude), sauf pour une évolution
    (``revalidate_form``), qui le repose.
    """
    with writing(slug) as repo:
        parent = tip_of(repo, experiment_id)
        if expected_version and expected_version != parent.id:
            raise PreconditionFailed(
                "Cette étude a changé depuis que vous l'avez ouverte - rechargez la page pour voir sa dernière version.",
                code="stale_version",
            )
        if not revalidate_form:
            repo.commit_form = None
        builder = repo.derive(
            parent.id, title=parent.title, intent=parent.intent, new_branch=experiment_id, author=author, hypothesis=parent.hypothesis
        )
        carried = _metadata_with_step_ids(repo, parent)
        builder.metadata = copy.deepcopy(carried)
        builder.form_answers = copy.deepcopy(parent.form_answers)
        builder.evidence = list(parent.evidence)
        builder.tags = list(parent.tags)
        builder.conclusion = parent.conclusion
        change(builder, parent)
        if _unchanged(builder, parent, carried):
            return parent
        try:
            return _commit(builder, "Impossible d'enregistrer cette modification")
        except follow.NothingToCommitError:
            return parent


def _content(experiment: follow.Experiment) -> dict:
    return experiment.model_dump(mode="json", exclude=_LINEAGE_FIELDS)


def _own_references(experiment: follow.Experiment) -> list[dict]:
    return [r.model_dump(mode="json") for r in experiment.references if r.role not in _LINEAGE_ROLES]


def _unchanged(builder: follow.ExperimentBuilder, parent: follow.Experiment, carried: dict[str, Any]) -> bool:
    """Le builder ne dit rien de plus que ``parent`` (hors filiation, auteur et date), dont les
    métadonnées reportées sont ``carried`` (:func:`_metadata_with_step_ids`). Les ids d'étape que
    ``parent`` n'avait pas écrits comptent ainsi comme écrits : les recevoir, sans rien changer
    d'autre, ne fait pas une version."""
    candidate = follow.Experiment(
        id="pending",
        parents=builder.parents,
        branch=builder.branch,
        title=builder.title,
        intent=builder.intent,
        hypothesis=builder.hypothesis,
        structure_type=type(builder.structure).registry_key(),
        structure=builder.structure.model_dump(mode="json"),
        references=builder.references,
        objectives=builder.objectives,
        steps=builder.steps,
        evidence=builder.evidence,
        conclusion=builder.conclusion,
        tags=builder.tags,
        metadata=builder.metadata,
        form_answers=builder.form_answers,
    )
    expected = parent.model_copy(update={"metadata": carried})
    return _content(candidate) == _content(expected) and _own_references(candidate) == _own_references(parent)


def _commit(builder: follow.ExperimentBuilder, failure: str) -> follow.Experiment:
    """``builder.commit()``, les erreurs de Follow traduites en erreurs du domaine."""
    try:
        return builder.commit()
    except follow.FormValidationError as exc:
        raise InvalidInput(
            "Réponses au formulaire d'intention invalides : " + " ; ".join(exc.errors), code="invalid_intent_form"
        ) from exc
    except follow.NothingToCommitError:
        raise
    except follow.ExperimentNotFoundError as exc:
        raise NotFound(f"{failure} : une version de référence est introuvable.", code="version_not_found") from exc
    except follow.FollowError as exc:
        raise Conflict(f"{failure} - rechargez la page et réessayez.", code="commit_refused") from exc


def _slugify_branch(title: str) -> str:
    """Le nom d'une piste tiré de son titre - il en fait l'adresse : « Épitaxie à 20 nm » ->
    ``epitaxie-a-20-nm``."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.strip().lower()).strip("-")
    return slug or "experience"


def unique_branch(taken: set[str], title: str) -> str:
    base = _slugify_branch(title)
    branch = base
    suffix = 2
    while branch in taken:
        branch = f"{base}-{suffix}"
        suffix += 1
    return branch


def _new_branch_name(slug: str, repo: follow.Repository, requested: str | None, title: str) -> str:
    """Le nom de la nouvelle piste : celui demandé (un seul segment d'URL, libre), ou tiré du titre.
    Pris : les pistes, les refs, et les pistes supprimées (:func:`~.repository.retired_lines` - un
    lien vers l'ancienne piste ne doit pas passer à une étude sans rapport)."""
    taken = set(repo.branches) | set(repo.tags) | retired_lines(slug)
    name = (requested or "").strip()
    if not name:
        return unique_branch(taken, title)
    if "/" in name or name in (".", "..") or VERSION_ID_RE.fullmatch(name):
        raise InvalidInput("Le nom de la piste ne peut pas contenir « / » (ni avoir la forme d'un id de version).", code="invalid_branch_name")
    if name in taken:
        raise Conflict(
            f"Le nom « {name} » est déjà pris par une autre piste, une ref ou une piste supprimée.", code="branch_name_taken"
        )
    return name


def apply_context(metadata: dict, context: str | None) -> None:
    """Set (or clear, when blank) the experiment's short context description in its metadata -
    Follow's Experiment has title/intent/hypothesis but nothing for « remettre en contexte ».
    ``None`` leaves whatever the metadata already carries."""
    if context is None:
        return
    value = context.strip()[:2000]
    if value:
        metadata[CONTEXT_METADATA_KEY] = value
    else:
        metadata.pop(CONTEXT_METADATA_KEY, None)


def _require_title_and_intent(body: Any) -> None:
    if not body.title.strip() or not body.intent.strip():
        raise InvalidInput("Le titre et l'intention sont obligatoires.", code="title_and_intent_required")


def split_objectives(inputs: list[ObjectiveInput]) -> tuple[list[follow.Objective], dict[str, str]]:
    """``follow.Objective`` has no "how will we check this" field (only ``rationale``, the *why*) -
    ``verification_method`` is Spectre-specific, so it's kept out of the ``Objective`` itself and
    returned separately, to be stashed under ``Experiment.metadata["objective_verification"]``
    (keyed by objective name)."""
    objectives: list[follow.Objective] = []
    verification: dict[str, str] = {}
    for o in inputs:
        objectives.append(follow.Objective(**o.model_dump(exclude_none=True, exclude={"verification_method"})))
        if o.verification_method:
            verification[o.name] = o.verification_method
    return objectives, verification


def _set_objectives(builder: follow.ExperimentBuilder, inputs: list[ObjectiveInput]) -> None:
    objectives, verification = split_objectives(inputs)
    builder.objectives = objectives
    if verification:
        builder.metadata["objective_verification"] = verification
    else:
        builder.metadata.pop("objective_verification", None)


class _PreparedStructure:
    """A structure payload turned into what a commit needs, outside the lock (the simulation is the
    slow part): the Follow structure, its protocol steps and the Spectre metadata that describes it
    - but its steps' ids, settled against the version it starts from (:meth:`step_metadata`).

    ``start`` is the version a campaign starts from (and the repository it was read in), given when
    its steps come without ids: its factors then name their step by the ids the steps will keep
    from it (:func:`_settled_step_ids`), as a fork without ids would."""

    def __init__(self, slug: str, payload: Any, start: tuple[follow.Repository, follow.Experiment] | None = None) -> None:
        self.kind = payload.kind
        self.metadata: dict[str, Any] = {}
        self.campaign_size = 0
        self.requested_step_ids: list[str | None] = []
        self.plan: campaigns.VariantPlan | None = None
        self.factor_indexes: list[int] = []
        self.labels: dict[int, simulation.LayerLabel] = {}
        self.bricks: list[simulation.ProcessBrick] = []
        # par entité, la position de l'étape qui a créé chaque couche de la structure (-1 : le substrat)
        self.layer_origins: list[list[int]] = []
        if isinstance(payload, ImagesPayload):
            self.structure = kinds.structure_image_from_input(slug, payload.images)
            self.steps: list = []
            self.metadata[kinds.IMAGE_REVISION_KEY] = kinds.new_image_revision()
            return
        declared = simulation.declared_params_by_index(payload.declared_params)
        self.labels = simulation.layer_labels_by_index(payload.layer_labels, len(payload.steps))
        self.bricks = simulation.checked_bricks(payload.bricks, len(payload.steps))
        self.steps = follow_adapter.to_steps(payload.steps)
        self.requested_step_ids = payload.step_ids
        recipes = payload.recipes or None
        origins = simulation.preset_origins_by_index(payload.preset_origins, len(payload.steps))
        self.metadata["structureforge_process"] = simulation.process_metadata(payload.substrate, payload.steps, declared, recipes, origins)
        if isinstance(payload, CampaignPayload):
            factor_ids: list[str | None] = list(payload.step_ids)
            if start is not None and not any(factor_ids):
                reader, source = start
                factor_ids = list(_settled_step_ids(factor_ids, self.metadata["structureforge_process"], source, step_ids_of(reader, source)))
            result = campaigns.generate_campaign_variants(
                payload.substrate, payload.steps, payload.plan, declared, factor_ids, self.labels, self.bricks, recipes
            )
            self.structure = kinds.ProcessLot(entries=result.entries)
            self.campaign_size = len(result.entries)
            self.layer_origins = result.layer_origins
            self.plan = payload.plan
            self.factor_indexes = result.factor_indexes
            self.metadata.update(
                {
                    "campaign_labels": result.labels,
                    "campaign_factor_labels": result.factor_labels,
                    "campaign_factor_values": result.factor_values,
                    # how each factor's values were laid out ("log" for a doping sweep over decades...)
                    "campaign_factor_scales": [factor.scale for factor in payload.plan.factors],
                }
            )
            return
        simulated = simulation.simulate_process(payload.substrate, payload.steps, recipes=recipes)
        self.structure = follow_adapter.to_structure(simulated.geometry)
        self.layer_origins = [simulated.layer_origins[-1]]

    def step_metadata(self, parent: follow.Experiment | None, parent_ids: list[str]) -> dict[str, Any]:
        """What the new version records of its steps' ids, settled against ``parent`` (the version
        it continues or forks from, ``None`` for a brand-new line), whose steps carry
        ``parent_ids`` (:func:`step_ids_of`) - see :func:`_settled_step_ids` -
        and, for a campaign, its plan, whose factors name their step by that final id; with layer
        labels, the labels and the step that created each layer of each entity, by those ids too
        (nothing without labels: a version without them keeps its former shape); with bricks, the
        steps each one groups, by those ids (nothing without bricks either). Nothing for pictures."""
        if self.kind == "images":
            return {}
        step_ids = _settled_step_ids(self.requested_step_ids, self.metadata["structureforge_process"], parent, parent_ids)
        recorded: dict[str, Any] = {simulation.STEP_IDS_METADATA_KEY: step_ids}
        if self.plan is not None:
            recorded["campaign_plan"] = campaigns.plan_metadata(self.plan, self.factor_indexes, step_ids)
        if self.labels:
            recorded[simulation.LAYER_LABELS_METADATA_KEY] = {
                step_ids[i]: label.model_dump(mode="json") for i, label in sorted(self.labels.items())
            }
            recorded[simulation.LAYER_STEPS_METADATA_KEY] = [
                [None if origin == simulation.SUBSTRATE_ORIGIN else step_ids[origin] for origin in origins] for origins in self.layer_origins
            ]
        if self.bricks:
            recorded[simulation.BRICKS_METADATA_KEY] = simulation.bricks_metadata(self.bricks, step_ids)
        return recorded


def create(slug: str, body: CreateExperimentRequest, *, author: str) -> follow.Experiment:
    """Une nouvelle piste : à partir de rien, d'une version existante (``from_version`` : la
    filiation est gardée - référence « baseline », diff, graphe), de plaques existantes
    (``wafer_origin`` : :func:`resolve_wafer_origin`), ou de deux études combinées (``merge_of`` :
    :func:`combine`). Une piste partie d'une version en reprend, faute de mieux dans la requête, les
    objectifs et le contexte - pas ses plaques (la requête nomme les siennes), le cahier de données,
    les étiquettes ni la conclusion : c'est une nouvelle étude. Une piste partie de plaques ne reprend de l'étude qui les
    suit que la référence dont celle-ci part : ses plaques sont celles que nomme la requête. Titre et
    intention obligatoires ; les plaques, non (leurs places restent à associer, depuis la FDL de
    l'étude - ``fdl``) ; le formulaire d'intention du µprojet s'applique ; la toute première étude
    d'un µprojet devient sa première ref."""
    _require_title_and_intent(body)
    if body.merge_of is not None:
        return combine(slug, body, author=author)
    entities = clean_entity_entries(body.entities)
    origin = body.wafer_origin
    if origin and not named_entities(entities):
        raise InvalidInput("Nommez les plaques dont part l'étude.", code="entity_required")
    # l'étude des plaques, lue dans son µprojet quand c'en est un autre (sinon sous le verrou, plus bas)
    elsewhere = resolve_wafer_origin(get_repository(origin.microproject), origin, entities) if origin and origin.microproject != slug else None
    start = None
    start_ref = body.from_version or (FromVersion(experiment_id=origin.experiment_id, version_id=origin.version_id) if origin else None)
    if start_ref and isinstance(body.structure, CampaignPayload) and not any(body.structure.step_ids):
        reader = get_repository(origin.microproject if origin else slug)
        start = (reader, _source_of(reader, start_ref))
    prepared = _PreparedStructure(slug, body.structure, start)
    _check_reference_place(body, prepared)
    with writing(slug) as repo:
        source = _source_of(repo, body.from_version) if body.from_version else None
        found = elsewhere or (resolve_wafer_origin(repo, origin, entities) if origin else None)
        if found is not None and origin.microproject == slug:
            source = found[0]  # dans le même µprojet, la nouvelle piste descend de l'étude des plaques
        branch = _new_branch_name(slug, repo, body.branch, body.title)
        common = dict(title=body.title.strip(), intent=body.intent.strip(), author=author, hypothesis=body.hypothesis or None)
        if source is not None:
            forked = origin is None  # une fourche reprend de sa source ce que la requête ne donne pas
            builder = repo.derive(
                source.id,
                new_branch=branch,
                structure=prepared.structure,
                carry_steps=False,
                carry_objectives=forked and not body.objectives,
                **common,
            )
            builder.steps = prepared.steps
            if forked:
                carried = [CONTEXT_METADATA_KEY] + ([] if body.objectives else ["objective_verification"])
                # ses plaques, non : une nouvelle piste nomme les siennes - les mêmes (cochées, ou
                # partie de plaques : wafer_origin) ou de nouvelles ; aucune n'est reprise en silence
                builder.metadata.update({key: copy.deepcopy(source.metadata[key]) for key in carried if key in source.metadata})
        else:
            builder = repo.new(branch=branch, structure=prepared.structure, steps=prepared.steps, **common)
        if body.objectives:
            _set_objectives(builder, body.objectives)
        builder.metadata.update(prepared.metadata)
        builder.metadata.update(prepared.step_metadata(source, step_ids_of(repo, source) if source is not None else []))
        builder.metadata["physical_tracking"] = _launch_tracking(prepared.kind, prepared.campaign_size, entities)
        # des réplicats déclarés comme répétitions exactes de la référence (étude simple, plusieurs plaques)
        if body.repeats and prepared.kind != "campaign" and len(builder.metadata["physical_tracking"]) > 1:
            builder.metadata[REPEATS_KEY] = True
        else:
            builder.metadata.pop(REPEATS_KEY, None)
        _set_reference_place(builder.metadata, body, prepared)
        set_study_fdl(builder.metadata, body.fdl)
        apply_context(builder.metadata, body.context)
        if found is not None:
            version, variant = found
            builder.metadata[WAFER_ORIGIN_KEY] = {
                "microproject": origin.microproject,
                "experiment_id": origin.experiment_id,
                "version_id": version.id,
                "variant": variant,
            }
        _set_reference_origin(builder.metadata, body, source or (found[0] if found else None))
        builder.form_answers = dict(body.form_answers)
        experiment = _commit(builder, "Impossible de lancer cette expérience")
        if len(repo) == 1:
            refs.create_ref(repo, experiment.id)
        return experiment


def _check_reference_place(body: CreateExperimentRequest, prepared: _PreparedStructure) -> None:
    """La plaque de référence d'une campagne doit être une de ses variantes (``reference_place_out_of_range``)."""
    place = body.reference_place
    if prepared.kind == "campaign" and place is not None and not 0 <= place < prepared.campaign_size:
        raise InvalidInput(
            f"La plaque de référence n° {place + 1} n'existe pas : la campagne a {prepared.campaign_size} variante(s).",
            code="reference_place_out_of_range",
        )


def _set_reference_place(metadata: dict[str, Any], body: CreateExperimentRequest, prepared: _PreparedStructure) -> None:
    """La plaque de référence d'une campagne (:data:`REFERENCE_PLACE_KEY`), telle que la requête la
    donne - ``None`` gardé tel quel : le split n'en a pas, avec alors, au choix, la plaque de
    comparaison (:data:`COMPARISON_KEY`). Une requête qui ne dit rien laisse la clé absente (la
    première variante, comme avant ce choix) ; rien de tout cela hors d'une campagne."""
    metadata.pop(REFERENCE_PLACE_KEY, None)
    metadata.pop(COMPARISON_KEY, None)
    if prepared.kind != "campaign" or "reference_place" not in body.model_fields_set:
        return
    metadata[REFERENCE_PLACE_KEY] = body.reference_place
    if body.reference_place is None and body.comparison_reference is not None:
        metadata[COMPARISON_KEY] = body.comparison_reference.model_dump()


def reference_place_of(version: follow.Experiment) -> int | None:
    """La place de la plaque de référence d'une campagne : celle enregistrée (``None`` : pas de
    référence dans le split), la première pour une campagne d'avant ce choix ; ``None`` pour tout
    ce qui n'est pas une campagne."""
    if version.structure_type != kinds.ProcessLot.registry_key():
        return None
    if REFERENCE_PLACE_KEY not in version.metadata:
        return 0
    place = version.metadata[REFERENCE_PLACE_KEY]
    return place if isinstance(place, int) and not isinstance(place, bool) else None


def comparison_reference_of(version: follow.Experiment) -> dict[str, Any] | None:
    """La plaque de comparaison d'une campagne sans référence dans son split (``{experiment_id,
    version_id, sample_id}``), telle qu'enregistrée - ``None`` sinon."""
    if reference_place_of(version) is not None:
        return None
    cited = version.metadata.get(COMPARISON_KEY)
    if not (isinstance(cited, dict) and isinstance(cited.get("experiment_id"), str)):
        return None
    return {
        "experiment_id": cited["experiment_id"],
        "version_id": cited.get("version_id") if isinstance(cited.get("version_id"), str) else None,
        "sample_id": cited.get("sample_id") if isinstance(cited.get("sample_id"), str) else None,
    }


def _set_reference_origin(metadata: dict[str, Any], body: CreateExperimentRequest, source: follow.Experiment | None) -> None:
    """La version de référence dont part la nouvelle piste : celle de la requête, sinon celle de
    ``source`` (la version dont elle part : une fourche, ou la première étude d'une combinaison)."""
    if body.reference_origin is not None:
        metadata[REFERENCE_ORIGIN_KEY] = body.reference_origin.model_dump()
    elif source is not None and reference_origin_of(source) is not None:
        metadata[REFERENCE_ORIGIN_KEY] = reference_origin_of(source)


def reference_origin_of(version: follow.Experiment) -> dict[str, str] | None:
    """La version de référence dont part l'étude (``{reference, version}``), telle qu'enregistrée -
    ``None`` sans origine, ou pour une origine illisible."""
    origin = version.metadata.get(REFERENCE_ORIGIN_KEY)
    if isinstance(origin, dict) and isinstance(origin.get("reference"), str) and isinstance(origin.get("version"), str):
        return {"reference": origin["reference"], "version": origin["version"]}
    return None


def _source_of(repo: follow.Repository, origin: FromVersion) -> follow.Experiment:
    try:
        return version_of(repo, origin.experiment_id, origin.version_id)
    except NotFound as exc:
        raise NotFound(f"Version de départ introuvable : {exc}", code="source_not_found") from exc


def wafer_origin_of(version: follow.Experiment) -> dict[str, Any] | None:
    """L'étude dont viennent les plaques de l'étude (``{microproject, experiment_id, version_id,
    variant}``), telle qu'enregistrée - ``None`` pour une étude qui n'est pas partie de plaques."""
    origin = version.metadata.get(WAFER_ORIGIN_KEY)
    if isinstance(origin, dict) and all(isinstance(origin.get(key), str) for key in ("microproject", "experiment_id", "version_id")):
        variant = origin.get("variant")
        return {
            "microproject": origin["microproject"],
            "experiment_id": origin["experiment_id"],
            "version_id": origin["version_id"],
            "variant": variant if isinstance(variant, int) else None,
        }
    return None


def resolve_wafer_origin(repo: follow.Repository, origin: WaferOrigin, entities: list[dict[str, Any]]) -> tuple[follow.Experiment, int | None]:
    """La version dont partent les plaques d'une nouvelle piste (``origin``, lue dans ``repo``, le
    dépôt de son µprojet) et, pour une campagne, la variante qu'elles portent. Chaque plaque nommée
    dans ``entities`` doit y être suivie (``wafer_not_in_origin``), et toutes avoir la même
    structure : une seule variante d'une campagne (``wafers_different_structures``) - les
    réplicats d'une étude simple partagent la sienne."""
    version = _source_of(repo, FromVersion(experiment_id=origin.experiment_id, version_id=origin.version_id))
    position = {
        compact(entry["sample_id"]): index
        for index, entry in enumerate(version.metadata.get("physical_tracking", []))
        if entry.get("sample_id")
    }
    named = named_entities(entities)
    missing = [entry["sample_id"] for entry in named if compact(entry["sample_id"]) not in position]
    if missing:
        raise InvalidInput(f"L'étude de départ ne suit pas : {', '.join(missing)}.", code="wafer_not_in_origin")
    if version.structure_type != kinds.ProcessLot.registry_key():
        return version, None
    variants = sorted({position[compact(entry["sample_id"])] for entry in named})
    if len(variants) > 1:
        labels = version.metadata.get("campaign_labels") or []
        names = ", ".join(f"« {labels[i]} »" if i < len(labels) else f"n° {i + 1}" for i in variants)
        raise InvalidInput(
            f"Ces plaques portent des variantes différentes de la campagne ({names}) : leurs structures diffèrent. "
            "Partez de plaques d'une même structure.",
            code="wafers_different_structures",
        )
    return version, variants[0] if variants else None


def _launch_tracking(kind: str, campaign_size: int, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The physical tracking of a new line of study whose structure is of ``kind`` (``process``,
    ``campaign`` of ``campaign_size`` variants, or ``images``), never the same sample twice: exactly
    one slot per variant of a campaign (the samples given fill the first ones - a named one beyond
    the last variant is refused), the slots of a simple study (its replicates, as many as given, at
    least one). A slot may stay blank: the wafers actually launched are associated later, from the
    FDL of the study - a study is concluded only once one of them is named (:func:`conclude`)."""
    refuse_duplicate_wafers(entities)
    if kind == "campaign":
        if named_entities(entities[campaign_size:]):
            raise InvalidInput(
                f"{len(named_entities(entities))} plaques pour {campaign_size} variante(s) : une plaque par variante au plus.",
                code="too_many_entities",
            )
        padding = [blank_entity() for _ in range(max(0, campaign_size - len(entities)))]
        return (entities + padding)[:campaign_size]
    return entities or [blank_entity()]


# Ce qui, dans les métadonnées d'une version, décrit sa structure (le procédé du constructeur, les ids
# de ses étapes, une campagne, la révision d'une structure en images) : ce qu'une combinaison reprend
# de sa première étude, avec la structure elle-même.
_STRUCTURE_METADATA_KEYS = (*kinds.DRAWN_STRUCTURE_METADATA_KEYS, kinds.IMAGE_REVISION_KEY)


def _structure_kind(structure_type: str) -> str:
    kind = kinds.KINDS.get(structure_type)
    return "images" if kind is kinds.IMAGES else "campaign" if kind is kinds.CAMPAIGN else "process"


def combine(slug: str, body: CreateExperimentRequest, *, author: str) -> follow.Experiment:
    """Combiner deux études du µprojet (``body.merge_of`` : deux versions, la pointe de chaque piste
    par défaut) : une **nouvelle piste** C dont elles sont les deux parents (« baseline » pour la
    première, « merge_source » pour la seconde : la filiation et l'évolution des structures montrent
    les deux). Sa structure est la structure combinée, selon la règle de Follow sans résolution de
    conflit : celle de la première étude (structure, protocole, et ce que ses métadonnées disent de
    la structure, ids d'étape compris) ; les deux doivent être deux versions différentes, chacune de
    sa piste (pas d'avant sa fourche), et du même type de structure. C a ses
    propres titre, intention, hypothèse et plaque (obligatoires comme pour un lancement) ; objectifs
    et contexte, faute de mieux dans la requête, viennent de la première étude. Son cahier démarre
    vide, sans étiquettes ni conclusion : les données restent sur A et B, attachées à leurs plaques.
    A et B ne bougent pas (aucune version ne s'y ajoute).

    Follow sait faire un commit à deux parents sur une nouvelle branche :
    ``Repository.merge(a, b, branch=<nouvelle piste>)`` - la voie retenue."""
    first, second = body.merge_of or []
    entities = clean_entity_entries(body.entities)
    with writing(slug) as repo:
        a, b = _source_of(repo, first), _source_of(repo, second)
        if first.experiment_id == second.experiment_id or a.id == b.id:
            raise InvalidInput("Choisissez deux études différentes à combiner.", code="same_experiment")
        # l'histoire d'une piste partie d'une version contient celles d'avant sa fourche, qui ne sont
        # pas à elle : combiner avec l'une d'elles l'attribuerait à la mauvaise piste
        for origin, version in ((first, a), (second, b)):
            if version.branch != origin.experiment_id:
                raise InvalidInput(
                    f"Cette version précède la piste « {origin.experiment_id} » : choisissez une de ses propres versions.",
                    code="version_before_line",
                )
        if a.structure_type != b.structure_type:
            raise InvalidInput(
                "Ces deux expériences ne peuvent pas être combinées (par exemple une expérience simple et une campagne).",
                code="different_structure_kinds",
            )
        branch = _new_branch_name(slug, repo, body.branch, body.title)
        builder = repo.merge(
            a.id, b.id, branch=branch, title=body.title.strip(), intent=body.intent.strip(), author=author, hypothesis=body.hypothesis or None
        )
        structure = _metadata_with_step_ids(repo, a)
        builder.metadata = {key: structure[key] for key in _STRUCTURE_METADATA_KEYS if key in structure}
        # deux campagnes : la plaque de référence (ou de comparaison) de la première, avec sa structure
        builder.metadata.update({key: copy.deepcopy(a.metadata[key]) for key in (REFERENCE_PLACE_KEY, COMPARISON_KEY) if key in a.metadata})
        if body.objectives:
            _set_objectives(builder, body.objectives)
        elif "objective_verification" in a.metadata:
            builder.metadata["objective_verification"] = copy.deepcopy(a.metadata["objective_verification"])
        if CONTEXT_METADATA_KEY in a.metadata:
            builder.metadata[CONTEXT_METADATA_KEY] = a.metadata[CONTEXT_METADATA_KEY]
        apply_context(builder.metadata, body.context)
        _set_reference_origin(builder.metadata, body, a)
        builder.metadata["physical_tracking"] = _launch_tracking(
            _structure_kind(a.structure_type), kinds.entity_count(a.structure_type, a.structure), entities
        )
        set_study_fdl(builder.metadata, body.fdl)
        builder.form_answers = dict(body.form_answers)
        return _commit(builder, "Impossible de combiner ces deux études")


def evolve(slug: str, experiment_id: str, body: EvolveRequest, *, author: str, expected_version: str | None) -> follow.Experiment:
    """Une nouvelle version de la piste, sur sa pointe : une nouvelle structure (procédé du
    constructeur ou images) et l'intention reposée (titre, intention, hypothèse, objectifs,
    réponses au formulaire - revalidées). Le reste est reporté, l'entité suivie comprise. Éditer la
    fiche sans toucher à la structure garde le statut et la conclusion ; une structure qui change
    ouvre une nouvelle itération, non conclue."""
    if isinstance(body.structure, CampaignPayload):
        raise InvalidInput(
            "Une campagne se lance comme une nouvelle piste, à partir de cette version.", code="campaign_is_a_new_line"
        )
    _require_title_and_intent(body)
    prepared = _PreparedStructure(slug, body.structure)
    entities = clean_entity_entries(body.entities)
    refuse_duplicate_wafers(entities)

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        # amend a reporté les ids des étapes du parent, tels qu'on les lit (step_ids_of)
        parent_ids = list(builder.metadata.get(simulation.STEP_IDS_METADATA_KEY) or [])
        builder.title = body.title.strip()
        builder.intent = body.intent.strip()
        if "hypothesis" in body.model_fields_set:
            builder.hypothesis = body.hypothesis or None
        builder.metadata.pop(HOLD_KEY, None)
        if body.objectives:
            _set_objectives(builder, body.objectives)
        apply_context(builder.metadata, body.context)
        if body.fdl is not None:
            set_study_fdl(builder.metadata, body.fdl)
        builder.form_answers = dict(body.form_answers)
        builder.structure = prepared.structure
        builder.steps = prepared.steps
        # une évolution n'est jamais une campagne (refusée plus haut) : plus de plaque de référence
        # parmi des variantes
        builder.metadata.pop(REFERENCE_PLACE_KEY, None)
        builder.metadata.pop(COMPARISON_KEY, None)
        if prepared.kind == "images":
            # les mêmes images (leurs annotations n'y comptent pas) : la même structure
            same = kinds.is_image_structure(parent.structure_type) and bool(parent.metadata.get(kinds.IMAGE_REVISION_KEY)) and (
                kinds.without_annotations(prepared.structure.model_dump()["images"])
                == kinds.without_annotations(kinds.structure_images(parent.structure_type, parent.structure))
            )
            for key in kinds.DRAWN_STRUCTURE_METADATA_KEYS:
                builder.metadata.pop(key, None)
            if not same:
                builder.metadata[kinds.IMAGE_REVISION_KEY] = prepared.metadata[kinds.IMAGE_REVISION_KEY]
            # les plaques données, sinon celles de la version précédente : ses réplicats (places à
            # associer comprises), ou la plaque de la première variante d'une campagne (des images ne
            # disent pas les variantes) - une place à associer s'il n'y en a aucune
            inherited = clean_entity_entries([EntityTrackingInput(**e) for e in parent.metadata.get("physical_tracking", [])])
            if parent.structure_type == kinds.ProcessLot.registry_key():
                inherited = named_entities(inherited)[:1]
            builder.metadata["physical_tracking"] = named_entities(entities) or inherited or [blank_entity()]
        else:
            process = prepared.metadata["structureforge_process"]
            # les étiquettes de couches et les briques ne changent pas la structure, ni l'unité ajoutée
            # à un paramètre déclaré : la conclusion reste
            same = parent.structure_type == ProcessStructure.registry_key() and versioning.same_settings(
                parent.metadata.get("structureforge_process"), process
            )
            # continuing an image-mode experiment in the builder: its structure is drawn from now on
            builder.metadata.pop(kinds.IMAGE_REVISION_KEY, None)
            builder.metadata["structureforge_process"] = process
            # les étiquettes et les briques sont celles de cette évolution (aucune : il n'y en a plus)
            builder.metadata.pop(simulation.LAYER_LABELS_METADATA_KEY, None)
            builder.metadata.pop(simulation.LAYER_STEPS_METADATA_KEY, None)
            builder.metadata.pop(simulation.BRICKS_METADATA_KEY, None)
            builder.metadata.update(prepared.step_metadata(parent, parent_ids))
            if entities:
                builder.metadata["physical_tracking"] = entities
            elif not builder.metadata.get("physical_tracking"):
                builder.metadata["physical_tracking"] = [blank_entity()]
        if not same:
            builder.conclusion = follow.Conclusion()

    return amend(slug, experiment_id, author=author, expected_version=expected_version, change=change, revalidate_form=True)


def set_status(
    slug: str, experiment_id: str, *, status: str, hold_reason: str | None, author: str, expected_version: str | None
) -> follow.Experiment:
    """Brouillon, en cours, en pause (avec sa raison), ou la reprise d'une étude en pause ou conclue
    (sa conclusion reste comme point de départ de la nouvelle). Le statut déjà affiché : rien."""

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        if display_status(parent) == status:
            return
        if status == "hold":
            if parent.conclusion.status not in RUNNING_STATUSES:
                raise InvalidInput("Seule une étude en brouillon ou en cours peut être mise en pause.", code="cannot_hold")
            reason = (hold_reason or "").strip()[:300] or None
            builder.metadata[HOLD_KEY] = {"since": datetime.now(timezone.utc).isoformat(), "by": author, "reason": reason}
        else:
            builder.metadata.pop(HOLD_KEY, None)
            builder.conclusion = parent.conclusion.model_copy(update={"status": status, "decided_at": None})

    return amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)


def conclude(slug: str, experiment_id: str, body: ConclusionRequest, *, author: str, expected_version: str | None) -> follow.Experiment:
    """Conclure (ou abandonner) l'étude : verdict par objectif, synthèse, décision, suite. Le verdict
    d'un objectif peut citer des entrées du cahier (``evidence_ids``, le champ de Follow : les ids
    d'entrées, ceux des anciennes preuves compris) - toutes du cahier de la pointe. Une conclusion
    identique à celle en place ne crée pas de version (sa date reste)."""

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        if not has_tracked_physical_entity(parent.metadata):
            raise InvalidInput(
                "Impossible de conclure : aucune plaque réelle n'est encore associée à cette expérience - "
                "associez-en au moins une (carte « Plaques », depuis la FDL de l'étude).",
                code="entity_required",
            )
        known = set(notebook_entry_ids(parent))
        cited = [entry_id for result in body.objective_results for entry_id in result.evidence_ids if entry_id not in known]
        if cited:
            raise InvalidInput(f"Entrée du cahier introuvable : {', '.join(cited)}.", code="notebook_entry_not_found")
        builder.metadata.pop(HOLD_KEY, None)
        conclusion = follow.Conclusion(
            status=body.status,
            decision=body.decision,
            summary=body.summary,
            next_steps=body.next_steps,
            objective_results=[follow.ObjectiveResult(**result.model_dump()) for result in body.objective_results],
            decided_at=datetime.now(timezone.utc),
        )
        if conclusion.model_copy(update={"decided_at": parent.conclusion.decided_at}) == parent.conclusion:
            conclusion = parent.conclusion
        builder.conclusion = conclusion

    return amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)


def set_tags(slug: str, experiment_id: str, tags: list[str], *, author: str, expected_version: str | None) -> follow.Experiment:
    cleaned: list[str] = []
    for tag in tags:
        tag = tag.strip()
        if tag and tag not in cleaned:
            cleaned.append(tag)

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        builder.tags = cleaned

    return amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)


def set_entities(
    slug: str,
    experiment_id: str,
    entities: list[EntityTrackingInput],
    *,
    author: str,
    expected_version: str | None,
    fdl: list[str] | None = None,
) -> follow.Experiment:
    """L'identifiant physique et l'emplacement de chaque échantillon suivi - un par variante d'une
    campagne, autant de réplicats qu'on veut pour une étude simple (au moins une entrée ; une entrée
    vide est une place encore à associer à une vraie plaque, et garde sa position : les liens
    d'entité désignent une plaque par sa position). Jamais deux fois la même plaque. ``fdl`` : les
    FDL de l'étude (``None`` les garde)."""
    cleaned = clean_entity_entries(entities)
    refuse_duplicate_wafers(cleaned)

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        tracked = list(cleaned)
        if parent.structure_type == kinds.ProcessLot.registry_key():
            expected = kinds.entity_count(parent.structure_type, parent.structure)
            if len(tracked) != expected:
                raise InvalidInput(
                    f"Il faut exactement {expected} entrée(s) (une par variante de cette campagne).", code="entity_count"
                )
        else:
            if not tracked:
                raise InvalidInput("Il faut au moins une entrée (la plaque suivie).", code="entity_count")
        builder.metadata["physical_tracking"] = tracked
        if fdl is not None:
            set_study_fdl(builder.metadata, fdl)

    return amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)


def replace_structure_images(
    slug: str, experiment_id: str, images: list[StructureImageInput], *, author: str, expected_version: str | None
) -> follow.Experiment:
    """Les images d'une structure donnée en images - tout le jeu, dans l'ordre de lecture : un dessin
    plus propre, la coupe TEM une fois faite, une légende, les annotations d'une image... Même
    révision de structure : pas de nouvelle version de structure. Une structure dessinée change par
    une évolution."""
    image = kinds.structure_image_from_input(slug, images)

    def change(builder: follow.ExperimentBuilder, parent: follow.Experiment) -> None:
        if not kinds.is_image_structure(parent.structure_type):
            raise InvalidInput(
                "Cette structure est dessinée dans le constructeur : modifiez-la avec « Enregistrer une évolution ».",
                code="drawn_structure",
            )
        builder.structure = image

    return amend(slug, experiment_id, author=author, expected_version=expected_version, change=change)


def delete(slug: str, experiment_id: str, *, expected_version: str | None) -> list[str]:
    """Supprimer la piste, jusqu'à son point de fourche (:func:`delete_line`) ; son nom n'est plus
    jamais redonné (:func:`retire_line`)."""
    with writing(slug) as repo:
        tip = tip_of(repo, experiment_id)
        if expected_version and expected_version != tip.id:
            raise PreconditionFailed(
                "Cette étude a changé depuis que vous l'avez ouverte - rechargez la page.", code="stale_version"
            )
        # le nom d'abord : une piste supprimée ne doit jamais rester sans son nom retiré
        retire_line(slug, experiment_id)
        return delete_line(repo, experiment_id)


def create_ref(slug: str, experiment_id: str, version_id: str | None, name: str | None) -> dict[str, Any]:
    """Marquer une version (la pointe de la piste par défaut) comme ref - voir :mod:`.refs`."""
    with writing(slug) as repo:
        target = version_of(repo, experiment_id, version_id)
        return refs.create_ref(repo, target.id, name=name)


def rename_ref(slug: str, name: str, new_name: str) -> dict[str, Any]:
    """Renommer une ref ; sa version ne change pas."""
    with writing(slug) as repo:
        return refs.rename_ref(repo, name, new_name)


def delete_ref(slug: str, name: str) -> None:
    """Retirer une ref ; la version, elle, reste."""
    with writing(slug) as repo:
        refs.delete_ref(repo, name)
