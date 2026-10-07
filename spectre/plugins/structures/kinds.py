"""The kinds of structure an experiment can carry: StructureForge's own single ``ProcessStructure``,
a DOE campaign's variants (:class:`ProcessLot`) and pictures given instead of a drawn process
(:class:`StructureImage`). Each is a :class:`StructureKind` of :data:`KINDS`, keyed by the registry
key Follow persists in ``structure_type`` - what every view asks of a structure (its SVG, how many
physical entities it tracks) goes through it rather than through a comparison of that key.
"""

from __future__ import annotations

import secrets
from typing import Any, Literal, Protocol

import follow
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    model_serializer,
    model_validator,
)
from structureforge.adapters.follow_adapter import ProcessStructure
from structureforge.process.steps import ProcessStep

from ...kernel.annotations import ImageAnnotation, clean_annotations
from ...kernel.errors import InvalidInput
from ..attachments.store import content_url, uploaded_image
from . import campaigns
from .rendering import LayerAnnotation, annotations_for, svg_for_process_structure, value_text
from .schemas import StructureImageInput
from .simulation import (
    BRICKS_METADATA_KEY,
    LABEL_COMPOSITION,
    LABEL_DECLARED_PREFIX,
    LABEL_DEPTH,
    LABEL_THICKNESS,
    LAYER_LABELS_METADATA_KEY,
    LAYER_STEPS_METADATA_KEY,
    MIN_GROUPED_LABELS,
    STEP_IDS_METADATA_KEY,
    DeclaredParam,
    LayerLabel,
    PresetOrigin,
    SubstrateSpec,
    bricks_from_metadata,
    declared_params_by_index,
    material_names_in_layers,
    materials_library,
    preset_origins_by_index,
    process_metadata,
    process_recipes,
    split_declared_unit,
)


# Clés de registre Follow de nos deux types de structure, figées sur leur valeur historique. Par
# défaut Follow dérive la clé du module et du nom de la classe (``Structure.registry_key``), la
# persiste dans ``structure_type`` de chaque expérience et la hache dans son id ; c'est aussi sous
# cette clé que ``Structure.__init_subclass__`` enregistre la classe. Déplacer ces classes (vers un
# plugin, par exemple) changerait donc la clé et rendrait illisibles les dépôts existants - d'où la
# chaîne écrite en dur, à ne jamais modifier.
PROCESS_LOT_KEY = "spectre.core.structures.ProcessLot"
STRUCTURE_IMAGE_KEY = "spectre.core.structures.StructureImage"


class ProcessLot(follow.Structure):
    """A Follow ``Structure`` holding several ``ProcessStructure`` variants (a DOE campaign's
    wafers, say) - the one Spectre-level type needed so Follow's generic batch/DOE tooling
    (``follow.doe.batch.analyze_batch``, ``follow.doe.design``) can work on structures built by
    StructureForge, which only ever models one geometry at a time. See
    :mod:`spectre.plugins.structures.campaigns` for where variants are generated.
    """

    entries: list[ProcessStructure]

    @classmethod
    def registry_key(cls) -> str:
        return PROCESS_LOT_KEY


class StructureImageItem(BaseModel):
    """One picture of a :class:`StructureImage`: which uploaded image (a file of the microproject's
    attachments, see :func:`spectre.plugins.attachments.store.attachments_dir`), what kind of picture it
    is, an optional caption, and the arrows and boxes drawn on it (:mod:`spectre.kernel.annotations`).

    ``annotations`` came later: a picture stored before reads without it, and a picture without any
    is stored without the key - the same object as before, so its content (and the id Follow hashes
    from it) does not change for nothing."""

    model_config = ConfigDict(extra="forbid")

    image_id: str
    kind: Literal["schema", "coupe", "autre"] = "schema"
    caption: str | None = None
    annotations: list[ImageAnnotation] = []

    @model_serializer(mode="wrap")
    def _without_empty_annotations(self, handler: Any) -> dict[str, Any]:
        data = handler(self)
        if not data.get("annotations"):
            data.pop("annotations", None)
        return data


MAX_STRUCTURE_IMAGES = 12


class StructureImage(follow.Structure):
    """A structure given as pictures instead of being drawn step by step in the builder - a
    schematic pasted from PowerPoint, TEM/SEM cross-sections, a photo... several of them when one
    alone doesn't tell the whole story (the schematic + an overview cross-section + a close-up),
    in the order they should be read. Spectre knows nothing of the layers (no simulation, no
    per-step provenance, no campaign split). Changing the pictures is a lightweight evolution of
    the same experience (see ``spectre.plugins.experiments.api::replace_structure_drawing``); an actual
    change of structure is an evolution with new pictures (``evoluer-image``) - told apart for
    versioning by :data:`IMAGE_REVISION_KEY`, not by the pictures themselves.
    """

    images: list[StructureImageItem] = Field(min_length=1, max_length=MAX_STRUCTURE_IMAGES)

    @classmethod
    def registry_key(cls) -> str:
        return STRUCTURE_IMAGE_KEY

    @model_validator(mode="before")
    @classmethod
    def _single_image_shape(cls, data: Any) -> Any:
        # the very first version of this mode held one flat picture ({image_id, kind, caption})
        if isinstance(data, dict) and "image_id" in data and "images" not in data:
            return {"images": [data]}
        return data


# Metadata key holding the "which structure is this" token of an image-mode experience: set anew
# on a real launch/evolution, carried unchanged by every lightweight evolution - replacing the
# picture included (same structure, better drawing). That token, not the image, is what
# :mod:`spectre.plugins.experiments.versioning` compares, since two pictures say nothing about what changed.
IMAGE_REVISION_KEY = "structure_image_revision"

# What a drawn structure leaves in Experiment.metadata that no longer describes an image-mode
# experience evolved from it (the StructureForge process, a campaign's split) - dropped when
# continuing with an image, the same way the builder's evolution drops IMAGE_REVISION_KEY.
DRAWN_STRUCTURE_METADATA_KEYS = (
    "structureforge_process",
    STEP_IDS_METADATA_KEY,
    LAYER_LABELS_METADATA_KEY,
    LAYER_STEPS_METADATA_KEY,
    BRICKS_METADATA_KEY,
    "campaign_labels",
    "campaign_factor_labels",
    "campaign_factor_values",
    "campaign_factor_scales",
    "campaign_plan",
)


class StructureKind(Protocol):
    """A kind of structure, found in :data:`KINDS` by the registry key Follow persisted for it."""

    key: str

    def render_svg(self, data: dict[str, Any], metadata: dict[str, Any] | None = None) -> str | None:
        """The SVG of a committed structure of this kind, with the layer labels its version's
        ``metadata`` records - ``None`` when there is nothing to draw."""

    def entity_count(self, data: dict[str, Any]) -> int:
        """How many distinct structures a structure of this kind holds - one tracked entity slot
        each for a campaign (one per variant); a simple structure's one is shared by any number of
        replicate wafers."""


class _ProcessKind:
    key = ProcessStructure.registry_key()

    def render_svg(self, data: dict[str, Any], metadata: dict[str, Any] | None = None) -> str | None:
        return _process_svg(ProcessStructure.model_validate(data), layer_annotations(metadata or {}, 0))

    def entity_count(self, data: dict[str, Any]) -> int:
        return 1


class _CampaignKind:
    """A campaign renders its first entry, the representative case the constant/varying split
    already covers in full; it tracks one entity per variant."""

    key = PROCESS_LOT_KEY

    def render_svg(self, data: dict[str, Any], metadata: dict[str, Any] | None = None) -> str | None:
        lot = ProcessLot.model_validate(data)
        return _process_svg(lot.entries[0], layer_annotations(metadata or {}, 0)) if lot.entries else None

    def entity_count(self, data: dict[str, Any]) -> int:
        return len(ProcessLot.model_validate(data).entries)


class _ImagesKind:
    """Pictures: nothing for StructureForge to draw, one entity."""

    key = STRUCTURE_IMAGE_KEY

    def render_svg(self, data: dict[str, Any], metadata: dict[str, Any] | None = None) -> str | None:
        return None

    def entity_count(self, data: dict[str, Any]) -> int:
        return 1


PROCESS: StructureKind = _ProcessKind()
CAMPAIGN: StructureKind = _CampaignKind()
IMAGES: StructureKind = _ImagesKind()
KINDS: dict[str, StructureKind] = {kind.key: kind for kind in (PROCESS, CAMPAIGN, IMAGES)}


def is_image_structure(structure_type: str) -> bool:
    return KINDS.get(structure_type) is IMAGES


def structure_images(structure_type: str, structure_data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """The pictures of an image-mode experience as plain dicts, in reading order (whatever shape
    they were stored in) - ``None`` for a drawn structure."""
    if not is_image_structure(structure_type):
        return None
    return [item.model_dump() for item in StructureImage.model_validate(structure_data).images]


def structure_images_payload(slug: str, structure_type: str, structure_data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """:func:`structure_images` tel que l'API le renvoie : chaque image porte ses ``annotations``
    (une liste, vide si elle n'en a pas) et l'``url`` de ses octets - le front ne la construit pas."""
    images = structure_images(structure_type, structure_data)
    if images is None:
        return None
    return [{**image, "annotations": image.get("annotations", []), "url": content_url(slug, image["image_id"])} for image in images]


def without_annotations(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Des images d'une structure sans leurs annotations : ce qui dit si la structure a changé (une
    flèche posée sur une coupe ne la change pas)."""
    return [{key: value for key, value in image.items() if key != "annotations"} for image in images]


def describe_image_changes(
    before_type: str, before_data: dict[str, Any], after_type: str, after_data: dict[str, Any]
) -> list[str] | None:
    """What changed between two structures when at least one of them is given as pictures, in
    plain French - Follow's own diff compares lists position by position, so a reordering or one
    added picture would read as "everything changed". ``None`` when neither side is pictures (the
    generic diff applies then)."""
    before = structure_images(before_type, before_data)
    after = structure_images(after_type, after_data)
    if before is None and after is None:
        return None
    if before is None:
        return ["Structure donnée en images (la version précédente était dessinée dans le constructeur)"]
    if after is None:
        return ["Structure redessinée dans le constructeur (la version précédente était donnée en images)"]

    kind_label = {"schema": "Schéma", "coupe": "Coupe TEM / MEB", "autre": "Autre"}
    before_ids = [img["image_id"] for img in before]
    after_ids = [img["image_id"] for img in after]
    lines: list[str] = []
    # la même place, une autre image : un remplacement plutôt qu'un ajout + un retrait
    replaced = {
        i for i, image_id in enumerate(after_ids)
        if image_id not in before_ids and i < len(before_ids) and before_ids[i] not in after_ids
    }
    lines += [f"Image {i + 1} remplacée" for i in sorted(replaced)]
    added = [i for i, image_id in enumerate(after_ids) if image_id not in before_ids and i not in replaced]
    removed = [i for i, image_id in enumerate(before_ids) if image_id not in after_ids and i not in replaced]
    if added:
        lines.append(f"{len(added)} image{'s' if len(added) > 1 else ''} ajoutée{'s' if len(added) > 1 else ''}")
    if removed:
        lines.append(f"{len(removed)} image{'s' if len(removed) > 1 else ''} retirée{'s' if len(removed) > 1 else ''}")
    kept = [image_id for image_id in after_ids if image_id in before_ids]
    if kept != [image_id for image_id in before_ids if image_id in after_ids]:
        lines.append("Ordre des images modifié")
    previous = {img["image_id"]: img for img in before}
    for i, img in enumerate(after):
        old = previous.get(img["image_id"])
        if old is None:
            continue
        if old["kind"] != img["kind"]:
            lines.append(f"Image {i + 1} : {kind_label[old['kind']]} → {kind_label[img['kind']]}")
        if old["caption"] != img["caption"]:
            lines.append(f"Image {i + 1} : légende {'modifiée' if img['caption'] else 'retirée'}")
        if old.get("annotations", []) != img.get("annotations", []):
            lines.append(f"Image {i + 1} : annotations modifiées")
    return lines


def new_image_revision() -> str:
    return secrets.token_hex(6)


def _process_svg(process_structure: ProcessStructure, annotations: list[LayerAnnotation]) -> str:
    materials = materials_library(*material_names_in_layers(process_structure.layers))
    return svg_for_process_structure(process_structure, {m.name: m.color for m in materials}, annotations)


_STEP_LIST: TypeAdapter[list[ProcessStep]] = TypeAdapter(list[ProcessStep])
_LABELS: TypeAdapter[dict[str, LayerLabel]] = TypeAdapter(dict[str, LayerLabel])
_DECLARED: TypeAdapter[dict[str, list[DeclaredParam]]] = TypeAdapter(dict[str, list[DeclaredParam]])
_ORIGINS: TypeAdapter[dict[str, PresetOrigin]] = TypeAdapter(dict[str, PresetOrigin])


def layer_annotations(metadata: dict[str, Any], entry_index: int) -> list[LayerAnnotation]:
    """The labels of entity ``entry_index`` of a committed structure, from what its version's
    ``metadata`` records: the labels by step id, the step that created each layer of each entity,
    the process (and, for a campaign, the plan and the values of this variant: each variant writes
    its own), and the bricks its steps belong to (their labels grouped). Nothing for a version
    without labels (every version from before them), nor for one whose record does not read: the
    drawing stays, unlabelled."""
    raw_labels = metadata.get(LAYER_LABELS_METADATA_KEY)
    layer_steps = metadata.get(LAYER_STEPS_METADATA_KEY)
    process = metadata.get("structureforge_process")
    step_ids = metadata.get(STEP_IDS_METADATA_KEY)
    if not (raw_labels and isinstance(layer_steps, list) and isinstance(process, dict) and isinstance(step_ids, list)):
        return []
    if not 0 <= entry_index < len(layer_steps) or not isinstance(layer_steps[entry_index], list):
        return []
    try:
        labels = _LABELS.validate_python(raw_labels)
        steps = _STEP_LIST.validate_python(process.get("steps") or [])
        declared = declared_params_by_index(_DECLARED.validate_python(process.get("declared_params") or {}))
        plan = metadata.get("campaign_plan")
        values = metadata.get("campaign_factor_values") or []
        if isinstance(plan, dict) and entry_index < len(values):
            variant_plan = campaigns.VariantPlan.model_validate(plan)
            indexes = campaigns.factor_step_indexes(variant_plan, list(step_ids))
            substrate = SubstrateSpec.model_validate(process["substrate"])
            _substrate, steps, declared = campaigns.apply_combination(substrate, steps, declared, variant_plan, indexes, values[entry_index])
    except (ValidationError, InvalidInput, KeyError, TypeError, ValueError):
        return []
    position = {step_id: i for i, step_id in enumerate(step_ids)}
    by_index = {position[step_id]: label for step_id, label in labels.items() if step_id in position}
    origins = [position.get(step_id) if step_id is not None else None for step_id in layer_steps[entry_index]]
    bricks = bricks_from_metadata(metadata.get(BRICKS_METADATA_KEY), list(step_ids))
    return annotations_for(steps, declared, by_index, origins, bricks)


def variant_process(metadata: dict[str, Any], step_ids: list[str], entry_index: int) -> dict[str, Any]:
    """The re-editable process (``structureforge_process``) of variant ``entry_index`` of a
    committed campaign, from what its version's ``metadata`` records: the process every variant
    shares, each factor of the plan (naming its step among ``step_ids``) set to this variant's
    value - what the wafer of that variant went through. :class:`InvalidInput` for a variant the
    campaign does not have, or a campaign recorded without its plan (before plans were kept)."""
    process = metadata.get("structureforge_process")
    plan = metadata.get("campaign_plan")
    values = metadata.get("campaign_factor_values") or []
    if not 0 <= entry_index < len(values):
        raise InvalidInput(f"Cette campagne n'a pas de variante n° {entry_index + 1}.", code="unknown_variant")
    if not (isinstance(process, dict) and isinstance(plan, dict)):
        raise InvalidInput("Le procédé de cette variante n'a pas été enregistré (campagne d'avant les plans).", code="no_variant_process")
    try:
        variant_plan = campaigns.VariantPlan.model_validate(plan)
        substrate = SubstrateSpec.model_validate(process["substrate"])
        steps = _STEP_LIST.validate_python(process.get("steps") or [])
        declared = declared_params_by_index(_DECLARED.validate_python(process.get("declared_params") or {}))
        indexes = campaigns.factor_step_indexes(variant_plan, list(step_ids))
        substrate, steps, declared = campaigns.apply_combination(substrate, steps, declared, variant_plan, indexes, values[entry_index])
        recipes = process_recipes(process.get("recipes"))
        origins = preset_origins_by_index(_ORIGINS.validate_python(process.get("preset_origins") or {}), len(steps))
    except (ValidationError, InvalidInput, KeyError, TypeError, ValueError) as exc:
        raise InvalidInput("Le procédé de cette variante ne se relit pas.", code="no_variant_process") from exc
    return process_metadata(substrate, steps, declared, recipes, origins)


# -- ce qui change aux étiquettes et aux paramètres déclarés d'une version à l'autre ---------------
#
# Deux versions d'une même piste (ou d'une fourche) partagent les ids de leurs étapes : on les
# apparie par id, une étape insérée ne décale rien. Deux études lancées à part (ou reprises d'un
# modèle, que le constructeur copie sans ids) n'en partagent aucun : on les apparie alors par
# position, comme le diff de structure (couche par couche). Une brique est ce que le versionnage en
# voit (``versioning._label_groups``) : son nom et ses étapes étiquetées, jamais son identifiant de
# groupe - dissocier puis regrouper les mêmes étapes sous le même nom ne change rien.

_VALUE_NAMES = {LABEL_THICKNESS: "épaisseur", LABEL_COMPOSITION: "composition", LABEL_DEPTH: "profondeur"}


def _value_name(key: str) -> str:
    """Le nom lisible d'une valeur d'étiquette : « épaisseur », « composition », ou le nom du paramètre déclaré."""
    if key.startswith(LABEL_DECLARED_PREFIX):
        return key[len(LABEL_DECLARED_PREFIX) :]
    return _VALUE_NAMES.get(key, key)


def _process_steps(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    process = metadata.get("structureforge_process")
    raw_steps = process.get("steps") if isinstance(process, dict) else None
    return [step if isinstance(step, dict) else {} for step in raw_steps or []]


def _own_step_ids(metadata: dict[str, Any], given: list[str] | None) -> list[str]:
    """L'id de chaque étape de la version : ``given`` (ceux que le service lit, ceux d'une ancienne
    version compris), sinon ceux qu'elle a enregistrés ; à défaut, un repère de position qu'aucune
    autre version ne porte (elle s'apparie alors par position)."""
    count = len(_process_steps(metadata))
    ids = given if given is not None else metadata.get(STEP_IDS_METADATA_KEY)
    ids = [sid for sid in ids if isinstance(sid, str)] if isinstance(ids, list) else []
    return ids if len(ids) == count else [f"#{i}" for i in range(count)]


def _aligned_step_ids(before_ids: list[str], after_ids: list[str]) -> list[str]:
    """Les ids sous lesquels comparer les étapes de ``before`` à celles d'``after`` : les leurs quand
    les deux versions ont une étape en commun, sinon ceux d'``after`` à la même position (une étape de
    ``before`` au-delà de la dernière d'``after`` garde le sien)."""
    if set(before_ids) & set(after_ids):
        return list(before_ids)
    return [after_ids[i] if i < len(after_ids) else sid for i, sid in enumerate(before_ids)]


def _step_name(step: dict[str, Any], position: int) -> str:
    return str(step.get("name") or step.get("material") or step.get("resist_material") or f"étape {position + 1}")


class _Record:
    """Ce qu'une version dit de ses étiquettes et de ses paramètres déclarés, sous les ids ``ids``
    (ceux de ses étapes ``own``, dans l'ordre, éventuellement alignés sur l'autre version) : ses
    étiquettes, le nom de chaque étape étiquetée (le texte, sinon le matériau, sinon le nom de
    l'étape), le nom de chaque étape, ses paramètres déclarés (par étape et par nom) et ses briques
    dont les étiquettes n'en font qu'une (``{group_id, name, step_ids}``)."""

    def __init__(self, metadata: dict[str, Any], own: list[str], ids: list[str]):
        steps = _process_steps(metadata)
        rename = dict(zip(own, ids))
        raw = metadata.get(LAYER_LABELS_METADATA_KEY)
        raw = raw if isinstance(raw, dict) else {}
        self.order = list(ids)
        self.step_names = {sid: _step_name(step, i) for i, (sid, step) in enumerate(zip(ids, steps))}
        # sans leur place (offset) : une étiquette seulement déplacée n'a pas changé
        self.labels = {rename[sid]: {k: v for k, v in label.items() if k != "offset"} for sid, label in raw.items() if sid in rename and isinstance(label, dict)}
        self.label_names: dict[str, str] = {}
        for sid, step in zip(ids, steps):
            if sid in self.labels:
                material = step.get("material") or step.get("resist_material")
                self.label_names[sid] = str(self.labels[sid].get("text") or material or step.get("name") or sid)
        self.groups: list[dict[str, Any]] = []
        for brick in bricks_from_metadata(metadata.get(BRICKS_METADATA_KEY), own):
            members = tuple(ids[i] for i in brick.step_indexes if ids[i] in self.labels)
            if len(members) >= MIN_GROUPED_LABELS:
                self.groups.append({"group_id": brick.group_id, "name": brick.name, "step_ids": members})
        process = metadata.get("structureforge_process")
        declared = process.get("declared_params") if isinstance(process, dict) else None
        self.params: dict[str, dict[str, dict[str, Any]]] = {}
        for key, params in (declared if isinstance(declared, dict) else {}).items():
            index = int(key) if isinstance(key, str) and key.isdigit() else -1
            if 0 <= index < len(ids) and isinstance(params, list):
                self.params[ids[index]] = {str(p["name"]): p for p in params if isinstance(p, dict) and p.get("name")}


def _records(before: dict[str, Any], after: dict[str, Any], before_ids: list[str] | None, after_ids: list[str] | None) -> tuple[_Record, _Record]:
    own_before, own_after = _own_step_ids(before, before_ids), _own_step_ids(after, after_ids)
    return _Record(before, own_before, _aligned_step_ids(own_before, own_after)), _Record(after, own_after, own_after)


def _ordered(old: _Record, new: _Record, keys: set[str]) -> list[str]:
    """``keys`` (des ids d'étape) dans l'ordre des étapes d'``new``, puis de celles d'``old`` qui n'y sont plus."""

    def position(sid: str) -> tuple[int, int]:
        return (0, new.order.index(sid)) if sid in new.order else (1, old.order.index(sid) if sid in old.order else 0)

    return sorted(keys, key=position)


def _match_groups(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any] | None, dict[str, Any]]], list[dict[str, Any]]]:
    """Chaque brique d'``new`` avec celle d'``old`` qui lui répond - le même nom et les mêmes étapes,
    sinon les mêmes étapes (renommée), sinon le même nom (regroupée autrement), sinon aucune - et
    les briques d'``old`` restées seules."""
    pending = list(old)
    matched: list[dict[str, Any] | None] = [None] * len(new)
    for same in (
        lambda a, b: a["name"] == b["name"] and a["step_ids"] == b["step_ids"],
        lambda a, b: a["step_ids"] == b["step_ids"],
        lambda a, b: a["name"] == b["name"],
    ):
        for k, group in enumerate(new):
            if matched[k] is None:
                found = next((g for g in pending if same(g, group)), None)
                if found is not None:
                    pending.remove(found)
                    matched[k] = found
    return list(zip(matched, new)), pending


def describe_label_changes(
    before: dict[str, Any], after: dict[str, Any], before_ids: list[str] | None = None, after_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Ce qui change aux étiquettes de couches de la version de métadonnées ``before`` à celle de
    ``after`` (``before_ids``, ``after_ids`` : les ids de leurs étapes, lus par le service ; à
    défaut, ceux qu'elles ont enregistrés), à part des changements de structure : par étape
    (``step_id``, celui d'``after`` ; ``change`` : ``added``, ``removed`` ou ``modified``, avec
    ``text`` ``{before, after}`` quand le texte change et les valeurs ajoutées et retirées, par leur
    nom lisible) puis par brique (``group_id`` ; ``change`` : ``grouped`` - ses étiquettes n'en font
    plus qu'une -, ``ungrouped``, ``renamed`` ou ``regrouped`` - pas les mêmes étapes). Chaque
    changement porte ``subject`` (l'étape ou la brique, telle que l'étiquette la nomme) et ``line``,
    la phrase qui le dit."""
    old, new = _records(before, after, before_ids, after_ids)
    changes: list[dict[str, Any]] = []
    for sid in _ordered(old, new, set(old.labels) | set(new.labels)):
        was, now = old.labels.get(sid), new.labels.get(sid)
        if was == now:
            continue
        subject = new.label_names.get(sid) or old.label_names.get(sid) or sid
        if was is None or now is None:
            change = "added" if was is None else "removed"
            line = f"{subject} — étiquette {'ajoutée' if was is None else 'retirée'}"
            changes.append({"step_id": sid, "subject": subject, "change": change, "line": line})
            continue
        old_values, new_values = list(was.get("values") or []), list(now.get("values") or [])
        added = [_value_name(v) for v in new_values if v not in old_values]
        removed = [_value_name(v) for v in old_values if v not in new_values]
        parts = []
        text = None
        if (was.get("text") or "") != (now.get("text") or ""):
            text = {"before": was.get("text") or "", "after": now.get("text") or ""}
            parts.append(f"texte « {old.label_names.get(sid, '')} » → « {subject} »")
        if added:
            parts.append(f"ajout : {', '.join(added)}")
        if removed:
            parts.append(f"retrait : {', '.join(removed)}")
        if not parts:
            parts.append("ordre des valeurs modifié")
        changes.append(
            {"step_id": sid, "subject": subject, "change": "modified", "text": text, "values_added": added, "values_removed": removed, "line": f"{subject} — {' ; '.join(parts)}"}
        )
    pairs, ungrouped = _match_groups(old.groups, new.groups)
    for was, now in pairs:
        subject = now["name"]
        if was is None:
            change, line = "grouped", f"brique {subject} — étiquettes regroupées"
        elif was["step_ids"] == now["step_ids"] and was["name"] == now["name"]:
            continue
        elif was["name"] != now["name"]:
            change, line = "renamed", f"brique « {was['name']} » renommée « {subject} »"
        else:
            change, line = "regrouped", f"brique {subject} — regroupement modifié"
        changes.append({"group_id": now["group_id"], "subject": subject, "change": change, "line": line})
    for was in ungrouped:
        changes.append({"group_id": was["group_id"], "subject": was["name"], "change": "ungrouped", "line": f"brique {was['name']} — étiquettes séparées"})
    return changes


def describe_param_changes(
    before: dict[str, Any], after: dict[str, Any], before_ids: list[str] | None = None, after_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Ce qui change aux paramètres déclarés (:class:`~.simulation.DeclaredParam` : dopage,
    précurseur...) de la version de métadonnées ``before`` à celle de ``after`` - ils ne sont pas
    dans la géométrie que compare le diff de structure. Par étape (appariées comme pour les
    étiquettes) et par paramètre : ``change`` ``added``, ``removed`` ou ``modified`` (avec ``value``
    et ``unit`` ``{before, after}``, ``None`` quand ils ne changent pas, et ``obtention_changed``) -
    une unité passée de l'obtention au champ ``unit``, la même, ne change rien. Chacun porte
    ``step_id``, ``subject`` (le nom de l'étape), ``param`` et ``line``, la phrase qui le dit."""
    old, new = _records(before, after, before_ids, after_ids)
    changes: list[dict[str, Any]] = []
    for sid in _ordered(old, new, set(old.params) | set(new.params)):
        subject = new.step_names.get(sid) or old.step_names.get(sid) or sid
        was_params, now_params = old.params.get(sid, {}), new.params.get(sid, {})
        for name in [*now_params, *(n for n in was_params if n not in now_params)]:
            was, now = was_params.get(name), now_params.get(name)
            base = {"step_id": sid, "subject": subject, "param": name}
            if was is None or now is None:
                param = now if was is None else was
                _rest, unit_text = split_declared_unit(param)
                shown = f"{value_text(param.get('value'))}{' ' + unit_text if unit_text else ''}"
                verb = "ajouté" if was is None else "retiré"
                changes.append({**base, "change": "added" if was is None else "removed", "line": f"{subject} — {name} {verb} ({shown})"})
                continue
            (old_rest, old_unit), (new_rest, new_unit) = split_declared_unit(was), split_declared_unit(now)
            parts = []
            value = unit = None
            if old_rest.get("value") != new_rest.get("value"):
                value = {"before": old_rest.get("value"), "after": new_rest.get("value")}
                parts.append(f"{value_text(value['before'])} → {value_text(value['after'])}")
            if old_unit != new_unit:
                unit = {"before": old_unit, "after": new_unit}
                if not old_unit:
                    parts.append(f"unité « {new_unit} » ajoutée")
                elif not new_unit:
                    parts.append(f"unité « {old_unit} » retirée")
                else:
                    parts.append(f"unité « {old_unit} » → « {new_unit} »")
            obtention_changed = old_rest.get("obtention") != new_rest.get("obtention")
            if obtention_changed:
                parts.append("obtention modifiée")
            if parts:
                line = f"{subject} — {name} : {' ; '.join(parts)}"
                changes.append({**base, "change": "modified", "value": value, "unit": unit, "obtention_changed": obtention_changed, "line": line})
    return changes


def describe_step_changes(
    before: dict[str, Any], after: dict[str, Any], before_ids: list[str] | None = None, after_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Les étapes renommées de la version de métadonnées ``before`` à celle de ``after`` (appariées
    comme pour les étiquettes) - un correctif pour le versionnage, que ni la géométrie comparée par
    le diff de structure ni les étiquettes ne portent. Chacune : ``step_id`` (celui d'``after``),
    ``subject`` (son nom lisible d'après), ``change`` ``renamed``, ``name`` ``{before, after}`` (le
    champ ``name`` de l'étape, ``""`` sans nom) et ``line``, la phrase qui le dit. Une étape ajoutée
    ou retirée change la structure : le diff de structure la dit."""
    old, new = _records(before, after, before_ids, after_ids)
    old_steps = dict(zip(old.order, _process_steps(before)))
    changes: list[dict[str, Any]] = []
    for position, (sid, step) in enumerate(zip(new.order, _process_steps(after))):
        was = old_steps.get(sid)
        if was is None or (was.get("name") or "") == (step.get("name") or ""):
            continue
        shown_before, shown_after = old.step_names[sid], new.step_names[sid]
        line = f"étape « {shown_before} » renommée « {shown_after} »" if shown_before != shown_after else f"étape {position + 1} — nom « {was.get('name') or ''} » → « {step.get('name') or ''} »"
        changes.append(
            {"step_id": sid, "subject": shown_after, "change": "renamed", "name": {"before": was.get("name") or "", "after": step.get("name") or ""}, "line": line}
        )
    return changes


def render_structure_svg(structure_type: str, structure_data: dict[str, Any], metadata: dict[str, Any] | None = None) -> str | None:
    """SVG for an already-committed experiment's current structure, redrawn by StructureForge from
    its stored, already-flattened layers, with the layer labels its ``metadata`` records - ``None``
    for a structure type with nothing to draw (the fiche just skips the diagram then)."""
    kind = KINDS.get(structure_type)
    return kind.render_svg(structure_data, metadata) if kind else None


def render_lot_svgs(lot: ProcessLot, metadata: dict[str, Any] | None = None) -> list[str]:
    """One SVG per entity in a committed campaign - the "atlas": every variant drawn side by
    side, not just the reference one ``render_structure_svg`` shows on its own - each with its
    own values on its labels.
    """
    names = {name for entry in lot.entries for name in material_names_in_layers(entry.layers)}
    material_colors = {m.name: m.color for m in materials_library(*names)}
    return [
        svg_for_process_structure(entry, material_colors, layer_annotations(metadata or {}, i)) for i, entry in enumerate(lot.entries)
    ]


def entity_count(structure_type: str, structure_data: dict[str, Any]) -> int:
    """How many distinct structures a structure holds: one per variant of a campaign (a tracked
    entity slot each), one otherwise (shared by the study's replicate wafers)."""
    kind = KINDS.get(structure_type)
    return kind.entity_count(structure_data) if kind else 1


def structure_image_from_input(slug: str, items: list[StructureImageInput]) -> StructureImage:
    """The :class:`StructureImage` a request points at - only once every picture really is an
    uploaded image of *this* microproject (each id is checked against the files on disk, never
    turned into a path from anything else) and its annotations are well formed."""
    if not items:
        raise InvalidInput("Collez ou choisissez au moins une image de la structure.")
    if len(items) > MAX_STRUCTURE_IMAGES:
        raise InvalidInput(f"{MAX_STRUCTURE_IMAGES} images au maximum.")
    if len({item.image_id for item in items}) != len(items):
        raise InvalidInput("La même image figure deux fois.")
    pictures = []
    for item in items:
        uploaded_image(slug, item.image_id)
        caption = (item.caption or "").strip()[:200] or None
        annotations = clean_annotations(item.annotations)
        pictures.append(StructureImageItem(image_id=item.image_id, kind=item.kind, caption=caption, annotations=annotations))
    return StructureImage(images=pictures)
