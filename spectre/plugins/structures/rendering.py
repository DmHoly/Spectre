"""SVG of a structure, always drawn by StructureForge (``structureforge.presentation.svg.frame_to_svg``,
through :func:`frame_svg`): the simulated frames the builder previews, and a committed structure
redrawn from its stored, already-flattened layers.

The **layer labels** (:class:`~spectre.plugins.structures.simulation.LayerLabel`) are Spectre's own:
:func:`labelled_svg` sets StructureForge's drawing in a wider SVG, the labels of the chosen steps
stacked on its right - each one's text, its values below, a thin line to the layer its step
created. The labelled steps of one brick (:class:`~spectre.plugins.structures.simulation.ProcessBrick`,
at least :data:`~spectre.plugins.structures.simulation.MIN_GROUPED_LABELS` of them) share a single
label instead: the brick's name, one line per step, and a bracket over the layers they created.
The provenance of the layers (which step created which layer) always comes from the
server's simulation (``simulation.SimulationResult.layer_origins``, or what a study recorded of
it), never from matching materials. The result is a self-contained SVG: colours are the page's
tokens with their value as fallback, so it reads the same in a screenshot or in the report.
"""

from __future__ import annotations

import html
import itertools
import re
from dataclasses import dataclass
from typing import Any

from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from structureforge.adapters.follow_adapter import ProcessStructure
from structureforge.core.materials import MaterialLibrary
from structureforge.core.units import Length
from structureforge.presentation.svg import frame_to_svg
from structureforge.process.simulate import Frame
from structureforge.process.steps import ProcessStep

from .simulation import (
    GRADED_NITRIDE_RE,
    LABEL_COMPOSITION,
    LABEL_DECLARED_PREFIX,
    LABEL_THICKNESS,
    SUBSTRATE_ORIGIN,
    DeclaredParam,
    LayerLabel,
    ProcessBrick,
    grouped_labels,
)


_PATH_TAG_RE = re.compile(r"<path ")


def format_number(value: float) -> str:
    """A number as people write it: ``20`` (not ``20.0``), and scientific notation for very
    large/small magnitudes - ``1e17``, ``3.16e17`` (a doping level), never
    ``100000000000000000``."""
    if value == 0:
        return "0"
    if abs(value) >= 1e5 or abs(value) < 1e-3:
        mantissa, exponent = f"{value:.2e}".split("e")  # 3 chiffres significatifs : "3.16e+17"
        return f"{mantissa.rstrip('0').rstrip('.')}e{int(exponent)}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6g}"


def _tag_layer_indices(svg: str) -> str:
    """Insert ``data-layer-index="{k}"`` into the k-th ``<path `` tag of ``svg`` (0-based, in
    order of appearance) - ``frame_to_svg`` (external, unmodifiable) draws exactly one path per
    layer with a non-empty ``rings()``, in ``frame.layers`` order, so index ``k`` here lines up
    with ``frames_payload``'s own ``"layers"`` list (same filter, same order). The labels of
    :func:`labelled_svg` draw no ``<path>``.
    """
    counter = itertools.count()
    return _PATH_TAG_RE.sub(lambda _m: f'<path data-layer-index="{next(counter)}" ', svg)


def frame_svg(frame: Frame, material_colors: dict[str, str]) -> str:
    """``frame_to_svg`` with every material name and colour escaped: StructureForge writes them as
    they are, the name in a ``<title>`` and the colour in an attribute, and a page shows the SVG
    through ``innerHTML`` - so a material named with HTML in the editable library would run in
    every page that draws it."""
    escaped = Frame(
        step_index=frame.step_index,
        step_kind=frame.step_kind,
        step_name=frame.step_name,
        layers=[_RenderableLayer(html.escape(layer.material), layer.rings()) for layer in frame.layers],
        domain_width_nm=frame.domain_width_nm,
    )
    return frame_to_svg(escaped, {html.escape(name): html.escape(color) for name, color in material_colors.items()})


# -- les étiquettes de couches ---------------------------------------------------------------------


@dataclass(frozen=True)
class LayerAnnotation:
    """What one label draws: its text, its values (one line each, already written out), and the
    positions in ``frame.layers`` of the layers its step created (the line points at the largest).
    ``grouped``: the label of a brick - its name, one line per labelled step, and a bracket over all
    their layers instead of a line to one of them, its lines written from the highest layer down
    (``line_layers``: the layers of each line's step)."""

    title: str
    lines: tuple[str, ...]
    layers: tuple[int, ...]
    grouped: bool = False
    line_layers: tuple[tuple[int, ...], ...] = ()


def length_text(nm: float) -> str:
    """A length in a readable unit, with the value as entered (:func:`format_number`, not rounded
    to 3 digits): ``80 nm``, ``1.5 µm``, ``1.234 µm``, ``1.005 µm``."""
    return f"{format_number(nm / 1000)} µm" if abs(nm) >= 1000 else f"{format_number(nm)} nm"


def _value_text(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    return format_number(float(value))


def _declared_value(name: str, params: list[DeclaredParam]) -> str | None:
    """The value of the declared parameter ``name`` with its unit (its own field, or the ``unit=``
    of its obtention for a parameter recorded before it) - ``None`` without a value."""
    param = next((p for p in params if p.name == name), None)
    if param is None or param.value in (None, ""):
        return None
    unit = param.unit_text()
    return f"{_value_text(param.value)}{' ' + unit if unit else ''}"


def label_title(step: ProcessStep, label: LayerLabel) -> str:
    """The text of ``step``'s label: its own, or else the step's material, or else its name."""
    material = getattr(step, "material", None) or getattr(step, "resist_material", None)
    return label.text or (material if isinstance(material, str) else None) or step.name


def label_values(step: ProcessStep, declared: list[DeclaredParam], label: LayerLabel) -> list[tuple[str, str]]:
    """``(name, value)`` of each value of ``step``'s label, in the chosen order (``name`` empty for
    a thickness or a composition, the parameter's name for a declared one) - a value the step
    doesn't have (no thickness, not a graded nitride, a declared parameter since removed) is left
    out."""
    values: list[tuple[str, str]] = []
    for key in label.values:
        if key == LABEL_THICKNESS:
            thickness = getattr(step, "thickness", None)
            if isinstance(thickness, Length):
                values.append(("", length_text(thickness.to_nm())))
        elif key == LABEL_COMPOSITION:
            match = GRADED_NITRIDE_RE.match(str(getattr(step, "material", "") or ""))
            if match:
                values.append(("", f"{match.group(1)} {round(float(match.group(2)) * 100)} %"))
        elif key.startswith(LABEL_DECLARED_PREFIX):
            name = key[len(LABEL_DECLARED_PREFIX) :]
            value = _declared_value(name, declared)
            if value:
                values.append((name, value))
    return values


def label_text(step: ProcessStep, declared: list[DeclaredParam], label: LayerLabel) -> tuple[str, tuple[str, ...]]:
    """The text of ``step``'s own label and its value lines (« 150 nm », « dopage Mg : 2e19 cm-3 »)."""
    lines = tuple(f"{name} : {value}" if name else value for name, value in label_values(step, declared, label))
    return label_title(step, label), lines


def grouped_line(step: ProcessStep, declared: list[DeclaredParam], label: LayerLabel) -> str:
    """One step's line in the label of its brick: its text, then its values on the same line
    (« p-GaN : 120 nm · dopage Mg 3e18 cm⁻³ »)."""
    values = [f"{name} {value}" if name else value for name, value in label_values(step, declared, label)]
    title = label_title(step, label)
    return f"{title} : {' · '.join(values)}" if values else title


def annotations_for(
    steps: list[ProcessStep],
    declared: dict[int, list[DeclaredParam]],
    labels: dict[int, LayerLabel],
    origins: list[int | None],
    bricks: list[ProcessBrick] | None = None,
) -> list[LayerAnnotation]:
    """The labels of a drawing whose layers were created by the steps ``origins`` names (one
    position per layer of ``frame.layers``, :data:`SUBSTRATE_ORIGIN` or ``None`` for the
    substrate) - one per labelled step that has a layer in it, in the order of the steps. The
    labelled steps of one brick (``bricks``, see :func:`~.simulation.grouped_labels`) share the
    brick's label instead, one line per step that has a layer in the drawing."""
    labelled = {index: label for index, label in labels.items() if 0 <= index < len(steps)}
    groups = grouped_labels(bricks or [], labelled)
    in_group = {index for _brick, members in groups for index in members}

    def layers_of(indexes: set[int]) -> tuple[int, ...]:
        return tuple(k for k, origin in enumerate(origins) if origin in indexes and origin != SUBSTRATE_ORIGIN)

    ordered: list[tuple[int, LayerAnnotation]] = []
    for index in sorted(labelled):
        layers = layers_of({index})
        if index in in_group or not layers:
            continue
        title, lines = label_text(steps[index], declared.get(index, []), labelled[index])
        ordered.append((index, LayerAnnotation(title, lines, layers)))
    for brick, members in groups:
        present = [index for index in members if layers_of({index})]
        if not present:
            continue
        lines = tuple(grouped_line(steps[index], declared.get(index, []), labelled[index]) for index in present)
        line_layers = tuple(layers_of({index}) for index in present)
        ordered.append((present[0], LayerAnnotation(brick.name, lines, layers_of(set(present)), grouped=True, line_layers=line_layers)))
    return [annotation for _index, annotation in sorted(ordered, key=lambda item: item[0])]


# Mise en page (unités de l'SVG, à l'échelle 1 à l'écran) : la structure tient dans un carré de
# STRUCTURE_BOX, les étiquettes à sa droite, au-delà d'une marge où passent les traits.
STRUCTURE_BOX = 400.0
PAD = 14.0
LEADER_GAP = 44.0
TITLE_SIZE = 16.0
VALUE_SIZE = 14.0
LINE_HEIGHT = 1.3
BLOCK_GAP = 10.0
# l'accolade d'une brique : à droite du dessin, dans la marge des traits
BRACKET_GAP = 6.0
BRACKET_DEPTH = 6.0
BRACKET_TIP = 6.0
BRACKET_MIN_HEIGHT = 8.0
MAX_TITLE_CHARS = 40
MAX_LINE_CHARS = 48
MAX_GROUPED_LINE_CHARS = 64
_TEXT = "var(--text, #1b2440)"
_TEXT_SOFT = "var(--text-soft, #4a5470)"
_SURFACE = "var(--surface, #ffffff)"
_FONT = "var(--font-ui, 'DM Sans', 'Helvetica Neue', Arial, sans-serif)"
_VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"')


def _shape(rings: list[dict]) -> Any:
    polygons = [Polygon(ring["exterior"], ring.get("holes") or []).buffer(0) for ring in rings if len(ring.get("exterior") or []) >= 3]
    return unary_union(polygons) if polygons else None


def _anchor(rings: list[dict]) -> tuple[float, float] | None:
    """A point inside the layer, towards its right edge (the labels are on the right) - on the
    horizontal line through a point surely inside it."""
    shape = _shape(rings)
    if shape is None or shape.is_empty:
        return None
    inside = shape.representative_point()
    min_x, _min_y, max_x, _max_y = shape.bounds
    crossing = shape.intersection(LineString([(min_x - 1, inside.y), (max_x + 1, inside.y)]))
    segments = [g for g in getattr(crossing, "geoms", [crossing]) if g.geom_type == "LineString" and not g.is_empty]
    if not segments:
        return inside.x, inside.y
    right = max(segments, key=lambda g: g.bounds[2])
    seg_min, seg_max = right.bounds[0], right.bounds[2]
    inset = min((seg_max - seg_min) / 2, 0.06 * (max_x - min_x))
    return seg_max - inset, inside.y


# La largeur d'un texte, estimée (le serveur ne mesure pas le texte) et par excès : la chasse de
# chaque caractère, en fraction de la taille de police, arrondie au dixième supérieur du plus large
# de DM Sans et de ses polices de repli (Helvetica Neue, Arial), en gras (600) comme en normal -
# mesurée dans le navigateur. Un texte ne sort jamais du SVG : « WWWW… » mesure 1 em par lettre en
# DM Sans 600, trois fois un « i ».
_CHAR_WIDTHS = {
    **dict.fromkeys("il .,'|", 0.3),
    **dict.fromkeys("Ifjt:;!·()[]°⁻¹²³", 0.4),
    **dict.fromkeys("rz/", 0.5),
    **dict.fromkeys("mw&#_", 0.9),
    **dict.fromkeys("MW—…%@", 1.1),
}


def _top_of(frame: Frame, layers: tuple[int, ...]) -> float:
    """Le haut (en y de la géométrie, vers le haut) des couches ``layers`` de ``frame``."""
    ys = [point[1] for k in layers if k < len(frame.layers) for ring in frame.layers[k].rings() for point in ring.get("exterior") or []]
    return max(ys) if ys else float("-inf")


def _char_width(char: str) -> float:
    return _CHAR_WIDTHS.get(char) or (0.8 if char.isupper() else 0.7)


def _text_width(text: str, size: float) -> float:
    return sum(_char_width(char) for char in text) * size


def _ellipsis(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _place(desired: list[float], heights: list[float], top: float, bottom: float) -> list[float]:
    """The top of each block (``desired`` in increasing order), stacked without overlap: each one
    pushed below the previous, the stack pulled back up if it runs past ``bottom``, but never above
    ``top`` (a stack taller than the drawing runs past its bottom)."""
    tops: list[float] = []
    for want, height in zip(desired, heights):
        floor = top if not tops else tops[-1] + heights[len(tops) - 1] + BLOCK_GAP
        tops.append(max(want, floor))
    limit = bottom
    for k in range(len(tops) - 1, -1, -1):
        tops[k] = min(tops[k], limit - heights[k])
        limit = tops[k] - BLOCK_GAP
    floor = top
    for k, height in enumerate(heights):
        tops[k] = max(tops[k], floor)
        floor = tops[k] + height + BLOCK_GAP
    return tops


def labelled_svg(frame: Frame, material_colors: dict[str, str], annotations: list[LayerAnnotation], *, tag_layers: bool = False) -> str:
    """StructureForge's drawing of ``frame`` (:func:`frame_svg`), with ``annotations`` stacked on
    its right - unchanged when there is none. The drawing becomes a nested ``<svg>`` fitted in a
    :data:`STRUCTURE_BOX` square; the outer one carries ``data-bare-viewbox``, the view without the
    labels (a page hides ``.sp-layer-labels`` and switches to it). Every text is escaped."""
    base = frame_svg(frame, material_colors)
    if tag_layers:
        base = _tag_layer_indices(base)
    if not annotations:
        return base
    view = _VIEWBOX_RE.search(base)
    inner = base[base.index(">") + 1 : base.rindex("</svg>")]
    vx, vy, vw, vh = (float(v) for v in view.group(1).split()) if view else (0.0, 0.0, 1.0, 1.0)
    scale = STRUCTURE_BOX / max(vw, vh)
    sw, sh = vw * scale, vh * scale

    def to_svg(x: float, y: float) -> tuple[float, float]:
        # le dessin est retourné (y vers le haut) : un point (x, y) de la géométrie est en (x, -y)
        return PAD + (x - vx) * scale, PAD + (-y - vy) * scale

    bracket_x = PAD + sw + BRACKET_GAP
    blocks = []
    for annotation in annotations:
        rings_by_layer = [frame.layers[k].rings() for k in annotation.layers if k < len(frame.layers)]
        candidates = [(rings, _shape(rings)) for rings in rings_by_layer]
        candidates = [(rings, shape) for rings, shape in candidates if shape is not None and not shape.is_empty]
        if not candidates:
            continue
        bracket = None
        if annotation.grouped:
            # une accolade sur toute la hauteur des couches de la brique (jamais plus fine qu'un trait lisible)
            _min_x, min_y, _max_x, max_y = unary_union([shape for _rings, shape in candidates]).bounds
            top, bottom = to_svg(0, max_y)[1], to_svg(0, min_y)[1]
            middle = (top + bottom) / 2
            half = max((bottom - top) / 2, BRACKET_MIN_HEIGHT / 2)
            bracket = (middle - half, middle + half)
            anchor = (bracket_x + BRACKET_DEPTH + BRACKET_TIP, middle)
        else:
            point = _anchor(max(candidates, key=lambda c: c[1].area)[0])
            if point is None:
                continue
            anchor = to_svg(*point)
        title = _ellipsis(annotation.title, MAX_TITLE_CHARS)
        lines = list(annotation.lines)
        if annotation.grouped and len(annotation.line_layers) == len(lines):
            # les lignes d'une brique dans l'ordre de ses couches sur le dessin, de la plus haute à la plus basse
            lines = [line for _top, line in sorted(zip((_top_of(frame, layers) for layers in annotation.line_layers), lines), key=lambda item: -item[0])]
        lines = [_ellipsis(line, MAX_GROUPED_LINE_CHARS if annotation.grouped else MAX_LINE_CHARS) for line in lines]
        height = TITLE_SIZE * LINE_HEIGHT + len(lines) * VALUE_SIZE * LINE_HEIGHT
        width = max([_text_width(title, TITLE_SIZE)] + [_text_width(line, VALUE_SIZE) for line in lines])
        blocks.append({"anchor": anchor, "bracket": bracket, "title": title, "lines": lines, "height": height, "width": width})
    if not blocks:
        return base
    blocks.sort(key=lambda b: b["anchor"][1])
    tops = _place(
        [b["anchor"][1] - TITLE_SIZE * LINE_HEIGHT / 2 for b in blocks], [b["height"] for b in blocks], PAD, PAD + sh
    )
    column_x = PAD + sw + LEADER_GAP
    # la colonne est aussi large que la plus large des étiquettes (estimée par excès) : rien ne déborde
    column_w = max(90.0, max(b["width"] for b in blocks))
    width = column_x + column_w + PAD
    height = max(PAD + sh + PAD, tops[-1] + blocks[-1]["height"] + PAD)
    bare = f"0 0 {_n(PAD + sw + PAD)} {_n(PAD + sh + PAD)}"

    parts = []
    for block, block_top in zip(blocks, tops):
        ax, ay = block["anchor"]
        ty = block_top + TITLE_SIZE * LINE_HEIGHT / 2
        if block["bracket"] is not None:
            y1, y2 = block["bracket"]
            tip = bracket_x + BRACKET_DEPTH
            mark = (
                f'<path class="sp-layer-bracket" data-y1="{_n(y1)}" data-y2="{_n(y2)}" '
                f'd="M{_n(bracket_x)},{_n(y1)} H{_n(tip)} V{_n(y2)} H{_n(bracket_x)} M{_n(tip)},{_n(ay)} H{_n(ax)}" '
                f'fill="none" stroke-width="1.4" stroke-linejoin="round" style="stroke:{_TEXT_SOFT}"/>'
                f'<polyline points="{_n(ax)},{_n(ay)} {_n(column_x - 6)},{_n(ty)}" fill="none" stroke-width="1.2" style="stroke:{_TEXT_SOFT}"/>'
            )
        else:
            points = f"{_n(ax)},{_n(ay)} {_n(PAD + sw + 8)},{_n(ay)} {_n(column_x - 6)},{_n(ty)}"
            mark = (
                f'<polyline points="{points}" fill="none" stroke-width="1.2" style="stroke:{_TEXT_SOFT}"/>'
                f'<circle cx="{_n(ax)}" cy="{_n(ay)}" r="3.2" stroke-width="1.4" style="fill:{_TEXT};stroke:{_SURFACE}"/>'
            )
        texts = [
            f'<text x="{_n(column_x)}" y="{_n(block_top + TITLE_SIZE)}" font-size="{_n(TITLE_SIZE)}" font-weight="600" style="fill:{_TEXT}">{html.escape(block["title"])}</text>'
        ]
        for k, line in enumerate(block["lines"]):
            baseline = block_top + TITLE_SIZE * LINE_HEIGHT + (k + 1) * VALUE_SIZE * LINE_HEIGHT - VALUE_SIZE * (LINE_HEIGHT - 1)
            texts.append(
                f'<text x="{_n(column_x)}" y="{_n(baseline)}" font-size="{_n(VALUE_SIZE)}" style="fill:{_TEXT_SOFT}">{html.escape(line)}</text>'
            )
        grouped = ' data-grouped="true"' if block["bracket"] is not None else ""
        parts.append(
            f'<g class="sp-layer-label" data-top="{_n(block_top)}" data-height="{_n(block["height"])}"{grouped}>' + mark + "".join(texts) + "</g>"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(width)} {_n(height)}" width="{_n(width)}" height="{_n(height)}" '
        f'class="sp-labelled-structure" data-bare-viewbox="{bare}">'
        f'<svg x="{_n(PAD)}" y="{_n(PAD)}" width="{_n(sw)}" height="{_n(sh)}" viewBox="{view.group(1) if view else "0 0 1 1"}">{inner}</svg>'
        f'<g class="sp-layer-labels" style="font-family:{_FONT}">{"".join(parts)}</g>'
        "</svg>"
    )


def _n(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def frames_payload(
    frames: list[Frame],
    materials: MaterialLibrary,
    origins: list[list[int]] | None = None,
    steps: list[ProcessStep] | None = None,
    declared: dict[int, list[DeclaredParam]] | None = None,
    labels: dict[int, LayerLabel] | None = None,
    bricks: list[ProcessBrick] | None = None,
) -> dict[str, Any]:
    """Each frame as the builder shows it: its SVG (layers tagged ``data-layer-index``, the labels
    of ``labels`` drawn on the layers they name, grouped by ``bricks``), its materials and its
    layers - each with the position of the step that created it (``step_index``, ``-1`` for the
    substrate), from the simulation's own provenance (``origins``)."""
    material_colors = {m.name: m.color for m in materials}
    payload = []
    for k, frame in enumerate(frames):
        frame_origins = origins[k] if origins is not None else [None] * len(frame.layers)
        annotations = annotations_for(steps or [], declared or {}, labels or {}, frame_origins, bricks) if labels else []
        payload.append(
            {
                "step_index": frame.step_index,
                "step_kind": frame.step_kind,
                "step_name": frame.step_name,
                "svg": labelled_svg(frame, material_colors, annotations, tag_layers=True),
                # only the materials this particular frame actually shows - material_colors below
                # is the whole library (40+ entries), which would make a poor legend on its own.
                "materials": sorted({layer.material for layer in frame.layers}),
                # same order/filter as the SVG's paths (see _tag_layer_indices) - index k here is
                # the layer behind the k-th <path data-layer-index="k">.
                "layers": [
                    {
                        "material": layer.material,
                        "step_index": origin,
                        "provenance": layer.provenance.model_dump(mode="json") if layer.provenance else None,
                    }
                    for layer, origin in zip(frame.layers, frame_origins)
                    if layer.rings()
                ],
            }
        )
    return {"frames": payload, "material_colors": material_colors}


class _RenderableLayer:
    """Duck-types as the ``structureforge.geometry.engine.Layer`` that
    ``structureforge.presentation.svg.frame_to_svg`` expects (a ``material`` attribute plus a
    ``rings()`` method) - built from the *already-flattened* ``LayerSpec`` a committed
    ``ProcessStructure`` stores (``rings`` there is a plain field, not a method).
    """

    __slots__ = ("material", "_rings")

    def __init__(self, material: str, rings: list[dict]) -> None:
        self.material = material
        self._rings = rings

    def rings(self) -> list[dict]:
        return self._rings


def svg_for_process_structure(
    process_structure: ProcessStructure, material_colors: dict[str, str], annotations: list[LayerAnnotation] | None = None
) -> str:
    """A committed structure, redrawn from its stored layers - with its labels, if any (their
    ``layers`` are positions in ``process_structure.layers``)."""
    frame = Frame(
        step_index=0,
        step_kind="structure",
        step_name="structure",
        layers=[_RenderableLayer(layer.material, layer.rings) for layer in process_structure.layers],
        domain_width_nm=process_structure.domain_width_nm,
    )
    return labelled_svg(frame, material_colors, annotations or [])
