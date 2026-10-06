"""DOE campaigns: varying one or more parameters of a process across the full cross of their
values (:class:`VariantPlan`), each combination re-simulated - the preview before launch and the
variants a :class:`~spectre.plugins.structures.kinds.ProcessLot` commits.
"""

from __future__ import annotations

import itertools
import math
from enum import Enum
from typing import Any

from follow.core.errors import BatchShapeError
from follow.doe.batch import BatchVariation, analyze_batch
from pydantic import BaseModel, ValidationError
from structureforge.adapters.follow_adapter import ProcessStructure, to_structure
from structureforge.core.materials import aluminum_gan, indium_gan
from structureforge.core.units import Length
from structureforge.process.steps import ProcessStep

from .rendering import annotations_for, format_number, labelled_svg
from .simulation import GRADED_NITRIDE_RE, DeclaredParam, LayerLabel, ProcessBrick, ProcessRecipes, SimulationFailedError, SubstrateSpec, simulate_process


CAMPAIGN_FIELD_LABELS = {
    "thickness": "Épaisseur",
    "depth": "Profondeur",
    "target_level": "Niveau cible",
    "domain_width": "Largeur du domaine",
    "material": "Matériau",
    "material_c": "Matériau plan C",
    "material_m": "Matériau plan M",
    "material_sp": "Matériau semipolaire",
    "resist_material": "Résine",
    "stop_material": "Matériau d'arrêt",
    "recipe": "Recette",
    "orientation": "Orientation",
    "rate_c": "Vitesse plan C",
    "rate_m": "Vitesse plan M",
    "rate_sp": "Vitesse semipolaire",
    "semi_polar_angle_deg": "Angle semipolaire",
    "angle_deg": "Angle",
    "openings.pitch": "Pas du réseau",
    "openings.diameter": "Diamètre d'ouverture",
}

# Plafond d'entités d'une campagne : chaque variante est re-simulée (près d'une seconde chacune) à
# chaque aperçu et au lancement - vérifié avant toute simulation.
MAX_CAMPAIGN_ENTITIES = 30

SUBSTRATE_STEP_ID = "substrate"  # un facteur sur cet « id » fait varier le substrat plutôt qu'une étape
SUBSTRATE_STEP_INDEX = -1  # sa position, pour le calcul (et dans les plans d'avant les ids d'étape)
DECLARED_FIELD_PREFIX = "declared:"  # "declared:dopage" : un paramètre déclaré (DeclaredParam) de l'étape
FRACTION_FIELD_SUFFIX = ".fraction"  # "material.fraction" : le taux d'In/Al (%) d'un nitrure à composition


class VariantFactor(BaseModel):
    """One parameter to vary, on the step whose id is ``step_id`` (or the substrate, at
    :data:`SUBSTRATE_STEP_ID`), across ``values``. ``field`` names *any* parameter of that step:

    - one of its own fields - a ``Length`` (``thickness``, ``depth``...: values in that field's own
      unit), a plain number (``rate_m``, ``angle_deg``...), or a name/choice (``material``,
      ``recipe``, ``orientation``...: values are strings);
    - ``"<material field>.fraction"`` - the indium/aluminium rate (%) of a graded nitride
      (``In0.20Ga0.80N``...);
    - ``"openings.pitch"`` / ``"openings.diameter"`` - a lithography's periodic array (nm),
      regenerated around the same centre;
    - ``"declared:<name>"`` - a :class:`DeclaredParam` of the step (a doping level, say), which
      doesn't change the simulated geometry but is recorded per variant.

    ``scale`` only records how the values were laid out (``"log"`` = geometric spacing, e.g. a
    doping sweep over decades) so they can be shown back the same way; ``label`` overrides the
    factor's generated human label.

    The step is named by its id (see :func:`spectre.plugins.structures.simulation.settle_step_ids`),
    never by its position: a plan recorded before step ids (``campaign_plan`` of an older campaign)
    carries ``step_index`` instead - its id is ``experiments.service.step_id_at(repo, version, index)``,
    and ``-1`` is the substrate.
    """

    step_id: str
    field: str
    values: list[float | str]
    scale: str = "linear"  # "linear" | "log" | "list"
    label: str | None = None


class VariantPlan(BaseModel):
    """A DOE campaign plan: one or more factors, fully crossed - every combination of every
    factor's values becomes one entity (5 thicknesses x 3 angles = 15 entities), the same "full
    factorial" ``follow.doe.design.full_factorial`` offers for a plain ``Structure`` field, applied
    here to a process's *steps* instead (which ``follow.doe.design`` never varies directly). A full
    factorial is always statistically identifiable - every factor is crossed with every other by
    construction - so there is nothing to warn about, unlike a hand-rolled "diagonal" sweep.
    """

    factors: list[VariantFactor]


class CampaignVariants(BaseModel):
    """The result of :func:`generate_campaign_variants` in a shape both the preview endpoint and
    the launch-a-campaign endpoint can use directly.
    """

    entries: list[ProcessStructure]
    svgs: list[str]
    variation: BatchVariation
    labels: list[str]  # one combined, human label per entity - e.g. "10 · 20" for 2 factors
    factor_labels: list[str]  # one label per factor - e.g. "Épaisseur — Oxyde initial"
    factor_values: list[list[float | str]]  # per entity, the raw value of each factor, same order
    factor_indexes: list[int]  # the position of each factor's step (SUBSTRATE_STEP_INDEX: the substrate)
    # per entity, the position of the step that created each of its layers (-1: the substrate)
    layer_origins: list[list[int]]


def _format_value_label(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return format_number(float(value))
    return str(value)


def _numeric(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise SimulationFailedError(f"{field!r} attend des valeurs numériques (reçu {value!r})") from exc


def _variable_fields(step: ProcessStep) -> list[str]:
    return [
        name
        for name in type(step).model_fields
        if name not in ("kind", "name", "description") and isinstance(getattr(step, name, None), (Length, int, float, str, Enum))
    ]


def _openings_with(openings: list[tuple[float, float]], domain_nm: float, *, pitch: float | None = None, diameter: float | None = None) -> list[tuple[float, float]]:
    """Regenerate a lithography's periodic openings with a new pitch or diameter (nm), keeping
    their count and the centre of the array - the same "pitch + diameter" generator the builder
    offers (``generatePeriodicOpenings`` in form-widgets.js), applied to an existing array."""
    ordered = sorted(openings)
    if not ordered:
        raise SimulationFailedError("cette lithographie n'a aucune ouverture à faire varier")
    # une ouverture coupée par un bord du domaine est plus étroite que les autres : son vrai centre
    # se déduit du bord resté intact, avec la largeur des ouvertures entières
    full = max(b - a for a, b in ordered)
    centers = []
    for a, b in ordered:
        if b - a < full - 1e-6 and a <= 1e-6:
            centers.append(b - full / 2)
        elif b - a < full - 1e-6 and b >= domain_nm - 1e-6:
            centers.append(a + full / 2)
        else:
            centers.append((a + b) / 2)
    width = diameter if diameter is not None else full
    if width <= 0:
        raise SimulationFailedError("le diamètre d'ouverture doit être positif")
    if pitch is not None:
        if len(ordered) < 2:
            raise SimulationFailedError("il faut au moins deux ouvertures pour faire varier le pas du réseau")
        middle = (centers[0] + centers[-1]) / 2
        centers = [middle + (i - (len(ordered) - 1) / 2) * pitch for i in range(len(ordered))]
    spacing = min((b - a for a, b in zip(centers, centers[1:])), default=None)
    if spacing is not None and width >= spacing:
        raise SimulationFailedError(f"ouvertures de {format_number(width)} nm plus larges que le pas ({format_number(spacing)} nm) : elles se chevaucheraient")
    result = []
    for center in centers:
        a, b = max(0.0, center - width / 2), min(domain_nm, center + width / 2)
        if b > a:
            result.append((round(a, 3), round(b, 3)))
    if not result:
        raise SimulationFailedError("aucune ouverture ne tombe dans le domaine simulé")
    return result


def _step_with_value(step: ProcessStep, field: str, value: Any, domain_nm: float) -> ProcessStep:
    """``step`` with the parameter ``field`` (see :class:`VariantFactor`) set to ``value`` -
    rebuilt through the step's own model so a bad value (a name where a number is expected, an
    unknown orientation...) is refused here, before any simulation, rather than half-applied."""
    data = step.model_dump()
    if field in ("openings.pitch", "openings.diameter"):
        if not isinstance(getattr(step, "openings", None), list):
            raise SimulationFailedError(f"{field!r} ne s'applique qu'à une lithographie")
        number = _numeric(value, field)
        key = "pitch" if field == "openings.pitch" else "diameter"
        data["openings"] = _openings_with(step.openings, domain_nm, **{key: number})
    elif field.endswith(FRACTION_FIELD_SUFFIX):
        base = field[: -len(FRACTION_FIELD_SUFFIX)]
        match = GRADED_NITRIDE_RE.match(str(getattr(step, base, "") or ""))
        if not match:
            raise SimulationFailedError(f"{base!r} n'est pas un nitrure à composition (InGaN/AlGaN à un taux donné) sur cette étape")
        fraction = min(1.0, max(0.0, round(_numeric(value, field) / 100, 2)))
        data[base] = (indium_gan if match.group(1) == "In" else aluminum_gan)(fraction).name
    else:
        if field not in type(step).model_fields or field in ("kind", "name", "description"):
            raise SimulationFailedError(
                f"{field!r} n'est pas un paramètre modifiable de cette étape (paramètres disponibles : {_variable_fields(step)!r})"
            )
        current = getattr(step, field)
        if isinstance(current, Length):
            data[field] = Length(value=_numeric(value, field), unit=current.unit)
        elif isinstance(current, (int, float)) and not isinstance(current, bool):
            data[field] = _numeric(value, field)
        else:
            data[field] = value
    try:
        return type(step).model_validate(data)
    except ValidationError as exc:
        raise SimulationFailedError(f"valeur {value!r} invalide pour {field!r} : {exc.errors()[0].get('msg', exc)}") from exc


def _substrate_with_value(substrate: SubstrateSpec, field: str, value: Any) -> SubstrateSpec:
    if field in ("thickness", "domain_width"):
        current: Length = getattr(substrate, field)
        return substrate.model_copy(update={field: Length(value=_numeric(value, field), unit=current.unit)})
    if field == "material":
        if not isinstance(value, str):
            raise SimulationFailedError(f"'material' attend un nom de matériau (reçu {value!r})")
        return substrate.model_copy(update={"material": value})
    raise SimulationFailedError(f"{field!r} n'est pas un paramètre du substrat (thickness, domain_width, material)")


def _declared_with_value(declared: dict[int, list[DeclaredParam]], step_index: int, name: str, value: Any) -> dict[int, list[DeclaredParam]]:
    params = list(declared.get(step_index, []))
    existing = next((i for i, p in enumerate(params) if p.name == name), None)
    if existing is None:
        params.append(DeclaredParam(name=name, value=value))
    else:
        params[existing] = params[existing].model_copy(update={"value": value})
    return {**declared, step_index: params}


def factor_step_indexes(plan: VariantPlan, step_ids: list[str | None]) -> list[int]:
    """The position of each factor's step among ``step_ids`` (the ids the steps came with, in
    order), :data:`SUBSTRATE_STEP_INDEX` for the substrate - an id no step carries is refused."""
    indexes = []
    for factor in plan.factors:
        if factor.step_id == SUBSTRATE_STEP_ID:
            indexes.append(SUBSTRATE_STEP_INDEX)
        elif factor.step_id in step_ids:
            indexes.append(step_ids.index(factor.step_id))
        else:
            raise SimulationFailedError("étape sélectionnée invalide (aucune étape ne porte cet id)")
    return indexes


def plan_metadata(plan: VariantPlan, indexes: list[int], step_ids: list[str]) -> dict[str, Any]:
    """The plan as a campaign records it (``campaign_plan``): each factor names the final id of its
    step (``step_ids``, once settled - see :func:`factor_step_indexes` for ``indexes``), or the
    substrate."""
    dumped = plan.model_dump(mode="json")
    for factor, index in zip(dumped["factors"], indexes):
        factor["step_id"] = SUBSTRATE_STEP_ID if index == SUBSTRATE_STEP_INDEX else step_ids[index]
    return dumped


def _factor_label(factor: VariantFactor, index: int, steps: list[ProcessStep]) -> str:
    if factor.label:
        return factor.label
    target = "Substrat" if index == SUBSTRATE_STEP_INDEX else steps[index].name
    if factor.field.startswith(DECLARED_FIELD_PREFIX):
        field_label = factor.field[len(DECLARED_FIELD_PREFIX) :]
    elif factor.field.endswith(FRACTION_FIELD_SUFFIX):
        field_label = "Taux (%)"
    else:
        field_label = CAMPAIGN_FIELD_LABELS.get(factor.field, factor.field)
    return f"{field_label} — {target}"


def apply_combination(
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    declared: dict[int, list[DeclaredParam]],
    plan: VariantPlan,
    indexes: list[int],
    combo: list[Any],
) -> tuple[SubstrateSpec, list[ProcessStep], dict[int, list[DeclaredParam]]]:
    """The substrate, steps and declared parameters of one variant: each factor of ``plan`` (on the
    step at its position in ``indexes``) set to its value in ``combo`` - everything else as given."""
    varied_substrate = substrate
    varied_steps = list(steps)
    varied_declared = declared
    for factor, index, value in zip(plan.factors, indexes, combo):
        if index == SUBSTRATE_STEP_INDEX:
            varied_substrate = _substrate_with_value(varied_substrate, factor.field, value)
        elif factor.field.startswith(DECLARED_FIELD_PREFIX):
            varied_declared = _declared_with_value(varied_declared, index, factor.field[len(DECLARED_FIELD_PREFIX) :], value)
        else:
            domain_nm = varied_substrate.domain_width.to_nm()
            varied_steps[index] = _step_with_value(varied_steps[index], factor.field, value, domain_nm)
    return varied_substrate, varied_steps, varied_declared


def generate_campaign_variants(
    substrate: SubstrateSpec,
    steps: list[ProcessStep],
    plan: VariantPlan,
    declared_params: dict[int, list[DeclaredParam]] | None = None,
    step_ids: list[str | None] | None = None,
    layer_labels: dict[int, LayerLabel] | None = None,
    bricks: list[ProcessBrick] | None = None,
    recipes: ProcessRecipes | None = None,
) -> CampaignVariants:
    """Re-simulate ``steps`` once per combination in the full cross of every factor's values,
    varying each factor's parameter for that combination - everything else (substrate, every
    other step, every other field) held constant. Returns one flattened ``ProcessStructure``
    and one preview SVG per combination, plus Follow's own constant/varying split
    (``follow.doe.batch.analyze_batch``) so the "matrice de split" is available before anyone
    commits to the campaign, not only after. A factor on a declared parameter leaves the geometry
    untouched - its value per variant lives in ``factor_values``, like every other factor's.
    The factors name their step by id, among ``step_ids`` (the ids the steps came with, in order).
    Each variant's SVG carries the labels of ``layer_labels`` (by step position), with its own values.
    ``recipes``: the process's own (a factor on ``recipe`` may pick one of them).
    """
    if not plan.factors:
        raise SimulationFailedError("il faut au moins un paramètre à faire varier")
    indexes = factor_step_indexes(plan, list(step_ids or []))
    for factor in plan.factors:
        if not factor.values:
            raise SimulationFailedError("il faut au moins une valeur pour chaque paramètre")
        if not factor.field:
            raise SimulationFailedError("il faut choisir un paramètre à faire varier")
    for factor, index in zip(plan.factors, indexes):
        if index == SUBSTRATE_STEP_INDEX and factor.field.startswith(DECLARED_FIELD_PREFIX):
            raise SimulationFailedError("le substrat n'a pas de paramètres déclarés")
    combinations = math.prod(len(factor.values) for factor in plan.factors)
    if combinations > MAX_CAMPAIGN_ENTITIES:
        raise SimulationFailedError(
            f"{combinations} variantes : {MAX_CAMPAIGN_ENTITIES} au maximum par campagne (chacune est simulée) - réduisez le nombre de valeurs."
        )

    factor_labels = [_factor_label(factor, index, steps) for factor, index in zip(plan.factors, indexes)]
    base_declared = declared_params or {}

    entries: list[ProcessStructure] = []
    svgs: list[str] = []
    labels: list[str] = []
    factor_values: list[list[float | str]] = []
    layer_origins: list[list[int]] = []
    for combo in itertools.product(*(factor.values for factor in plan.factors)):
        varied_substrate, varied_steps, varied_declared = apply_combination(substrate, steps, base_declared, plan, indexes, list(combo))
        result = simulate_process(varied_substrate, varied_steps, varied_declared or None, recipes)
        entries.append(to_structure(result.geometry))
        material_colors = {m.name: m.color for m in result.materials}
        # chaque variante écrit ses propres valeurs sur ses étiquettes
        annotations = annotations_for(varied_steps, varied_declared, layer_labels or {}, result.layer_origins[-1], bricks) if layer_labels else []
        svgs.append(labelled_svg(result.frames[-1], material_colors, annotations))
        labels.append(" · ".join(_format_value_label(v) for v in combo))
        factor_values.append(list(combo))
        layer_origins.append(result.layer_origins[-1])

    variation = analyze_variants(entries)
    return CampaignVariants(
        entries=entries,
        svgs=svgs,
        variation=variation,
        labels=labels,
        factor_labels=factor_labels,
        factor_values=factor_values,
        factor_indexes=indexes,
        layer_origins=layer_origins,
    )


def _layer_extents(entry: ProcessStructure) -> dict[str, Any]:
    """A variant reduced to what can always be compared: each layer's material and bounding box."""
    layers = []
    for layer in entry.layers:
        points = [point for ring in layer.rings for point in ring.get("exterior", [])]
        xs = [p[0] for p in points] or [0.0]
        ys = [p[1] for p in points] or [0.0]
        layers.append(
            {
                "material": layer.material,
                "x_min": round(min(xs), 3),
                "x_max": round(max(xs), 3),
                "y_min": round(min(ys), 3),
                "y_max": round(max(ys), 3),
            }
        )
    return {"domain_width_nm": entry.domain_width_nm, "layers": layers}


def analyze_variants(entries: list[ProcessStructure]) -> BatchVariation:
    """Follow's constant/varying split (``follow.doe.batch.analyze_batch``) of a campaign's
    variants - which compares them point by point, so it refuses variants whose outlines don't
    have the same number of points (a facet growth rate, a material or a pitch that changes the
    polygons). Then each layer is compared by its extent instead (material + bounding box), and if
    even the layer count differs, only the entity count is reported: the factors the campaign was
    launched with (``campaign_factor_labels``/``values``) still say exactly what varies.
    """
    try:
        return analyze_batch(entries)
    except BatchShapeError:
        pass
    try:
        return analyze_batch([_layer_extents(entry) for entry in entries])
    except BatchShapeError:
        return BatchVariation(entity_count=len(entries))
