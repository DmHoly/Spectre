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
from pydantic import BaseModel, ConfigDict, Field, model_validator
from structureforge.adapters.follow_adapter import ProcessStructure

from ...kernel.errors import InvalidInput
from ..attachments.store import content_url, uploaded_image
from .rendering import svg_for_process_structure
from .schemas import StructureImageInput
from .simulation import STEP_IDS_METADATA_KEY, material_names_in_layers, materials_library


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
    is, and an optional caption."""

    model_config = ConfigDict(extra="forbid")

    image_id: str
    kind: Literal["schema", "coupe", "autre"] = "schema"
    caption: str | None = None


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
    "campaign_labels",
    "campaign_factor_labels",
    "campaign_factor_values",
    "campaign_factor_scales",
    "campaign_plan",
)


class StructureKind(Protocol):
    """A kind of structure, found in :data:`KINDS` by the registry key Follow persisted for it."""

    key: str

    def render_svg(self, data: dict[str, Any]) -> str | None:
        """The SVG of a committed structure of this kind - ``None`` when there is nothing to draw."""

    def entity_count(self, data: dict[str, Any]) -> int:
        """How many physical entities a structure of this kind tracks."""


class _ProcessKind:
    key = ProcessStructure.registry_key()

    def render_svg(self, data: dict[str, Any]) -> str | None:
        return _process_svg(ProcessStructure.model_validate(data))

    def entity_count(self, data: dict[str, Any]) -> int:
        return 1


class _CampaignKind:
    """A campaign renders its first entry, the representative case the constant/varying split
    already covers in full; it tracks one entity per variant."""

    key = PROCESS_LOT_KEY

    def render_svg(self, data: dict[str, Any]) -> str | None:
        lot = ProcessLot.model_validate(data)
        return _process_svg(lot.entries[0]) if lot.entries else None

    def entity_count(self, data: dict[str, Any]) -> int:
        return len(ProcessLot.model_validate(data).entries)


class _ImagesKind:
    """Pictures: nothing for StructureForge to draw, one entity."""

    key = STRUCTURE_IMAGE_KEY

    def render_svg(self, data: dict[str, Any]) -> str | None:
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
    """:func:`structure_images` tel que l'API le renvoie : chaque image porte l'``url`` de ses
    octets - le front ne la construit pas."""
    images = structure_images(structure_type, structure_data)
    if images is None:
        return None
    return [{**image, "url": content_url(slug, image["image_id"])} for image in images]


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
    return lines


def new_image_revision() -> str:
    return secrets.token_hex(6)


def _process_svg(process_structure: ProcessStructure) -> str:
    materials = materials_library(*material_names_in_layers(process_structure.layers))
    return svg_for_process_structure(process_structure, {m.name: m.color for m in materials})


def render_structure_svg(structure_type: str, structure_data: dict[str, Any]) -> str | None:
    """SVG for an already-committed experiment's current structure, redrawn by StructureForge from
    its stored, already-flattened layers - ``None`` for a structure type with nothing to draw (the
    fiche just skips the diagram then)."""
    kind = KINDS.get(structure_type)
    return kind.render_svg(structure_data) if kind else None


def render_lot_svgs(lot: ProcessLot) -> list[str]:
    """One SVG per entity in a committed campaign - the "atlas": every variant drawn side by
    side, not just the reference one ``render_structure_svg`` shows on its own.
    """
    names = {name for entry in lot.entries for name in material_names_in_layers(entry.layers)}
    material_colors = {m.name: m.color for m in materials_library(*names)}
    return [svg_for_process_structure(entry, material_colors) for entry in lot.entries]


def entity_count(structure_type: str, structure_data: dict[str, Any]) -> int:
    """How many physical entities a structure tracks: one per variant of a campaign, one otherwise."""
    kind = KINDS.get(structure_type)
    return kind.entity_count(structure_data) if kind else 1


def structure_image_from_input(slug: str, items: list[StructureImageInput]) -> StructureImage:
    """The :class:`StructureImage` a request points at - only once every picture really is an
    uploaded image of *this* microproject (each id is checked against the files on disk, never
    turned into a path from anything else)."""
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
        pictures.append(StructureImageItem(image_id=item.image_id, kind=item.kind, caption=caption))
    return StructureImage(images=pictures)
