"""SVG of a structure, always drawn by StructureForge (``structureforge.presentation.svg.frame_to_svg``,
through :func:`frame_svg`): the simulated frames the builder previews, and a committed structure
redrawn from its stored, already-flattened layers.

The **layer labels** (:class:`~spectre.plugins.structures.simulation.LayerLabel`) are Spectre's own:
:func:`labelled_svg` sets StructureForge's drawing in a wider SVG, the labels of the chosen steps
stacked on its right - each one's text, its values below, a thin line to the layer its step
created. The provenance of the layers (which step created which layer) always comes from the
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
    positions in ``frame.layers`` of the layers its step created (the line points at the largest)."""

    title: str
    lines: tuple[str, ...]
    layers: tuple[int, ...]


def length_text(nm: float) -> str:
    """A length in a readable unit, with the value as entered (:func:`format_number`, not rounded
    to 3 digits): ``80 nm``, ``1.5 µm``, ``1.234 µm``, ``1.005 µm``."""
    return f"{format_number(nm / 1000)} µm" if abs(nm) >= 1000 else f"{format_number(nm)} nm"


def _value_text(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    return format_number(float(value))


def _declared_line(name: str, params: list[DeclaredParam]) -> str | None:
    param = next((p for p in params if p.name == name), None)
    if param is None or param.value in (None, ""):
        return None
    unit = next((str(param.obtention[key]) for key in ("unit", "unité", "unite") if param.obtention.get(key)), "")
    return f"{name} : {_value_text(param.value)}{' ' + unit if unit else ''}"


def label_text(step: ProcessStep, declared: list[DeclaredParam], label: LayerLabel) -> tuple[str, tuple[str, ...]]:
    """The text of ``step``'s label (its own, or else the step's material) and its value lines, in
    the chosen order - a value the step doesn't have (no thickness, not a graded nitride, a
    declared parameter since removed) is left out."""
    material = getattr(step, "material", None) or getattr(step, "resist_material", None)
    title = label.text or (material if isinstance(material, str) else None) or step.name
    lines: list[str] = []
    for key in label.values:
        line = None
        if key == LABEL_THICKNESS:
            thickness = getattr(step, "thickness", None)
            line = length_text(thickness.to_nm()) if isinstance(thickness, Length) else None
        elif key == LABEL_COMPOSITION:
            match = GRADED_NITRIDE_RE.match(str(getattr(step, "material", "") or ""))
            line = f"{match.group(1)} {round(float(match.group(2)) * 100)} %" if match else None
        elif key.startswith(LABEL_DECLARED_PREFIX):
            line = _declared_line(key[len(LABEL_DECLARED_PREFIX) :], declared)
        if line:
            lines.append(line)
    return title, tuple(lines)


def annotations_for(
    steps: list[ProcessStep],
    declared: dict[int, list[DeclaredParam]],
    labels: dict[int, LayerLabel],
    origins: list[int | None],
) -> list[LayerAnnotation]:
    """The labels of a drawing whose layers were created by the steps ``origins`` names (one
    position per layer of ``frame.layers``, :data:`SUBSTRATE_ORIGIN` or ``None`` for the
    substrate) - one per labelled step that has a layer in it, in the order of the steps."""
    annotations = []
    for index in sorted(labels):
        layers = tuple(k for k, origin in enumerate(origins) if origin == index and origin != SUBSTRATE_ORIGIN)
        if not layers or not 0 <= index < len(steps):
            continue
        title, lines = label_text(steps[index], declared.get(index, []), labels[index])
        annotations.append(LayerAnnotation(title, lines, layers))
    return annotations


# Mise en page (unités de l'SVG, à l'échelle 1 à l'écran) : la structure tient dans un carré de
# STRUCTURE_BOX, les étiquettes à sa droite, au-delà d'une marge où passent les traits.
STRUCTURE_BOX = 400.0
PAD = 14.0
LEADER_GAP = 44.0
TITLE_SIZE = 16.0
VALUE_SIZE = 14.0
LINE_HEIGHT = 1.3
BLOCK_GAP = 10.0
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


def _text_width(text: str, size: float) -> float:
    return len(text) * size * 0.58  # une estimation : le serveur ne mesure pas le texte


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

    blocks = []
    for annotation in annotations:
        rings_by_layer = [frame.layers[k].rings() for k in annotation.layers if k < len(frame.layers)]
        candidates = [(rings, _shape(rings)) for rings in rings_by_layer]
        candidates = [(rings, shape) for rings, shape in candidates if shape is not None and not shape.is_empty]
        if not candidates:
            continue
        rings = max(candidates, key=lambda c: c[1].area)[0]
        point = _anchor(rings)
        if point is None:
            continue
        title = _ellipsis(annotation.title, 40)
        lines = [_ellipsis(line, 48) for line in annotation.lines]
        height = TITLE_SIZE * LINE_HEIGHT + len(lines) * VALUE_SIZE * LINE_HEIGHT
        width = max([_text_width(title, TITLE_SIZE)] + [_text_width(line, VALUE_SIZE) for line in lines])
        blocks.append({"anchor": to_svg(*point), "title": title, "lines": lines, "height": height, "width": width})
    if not blocks:
        return base
    blocks.sort(key=lambda b: b["anchor"][1])
    tops = _place(
        [b["anchor"][1] - TITLE_SIZE * LINE_HEIGHT / 2 for b in blocks], [b["height"] for b in blocks], PAD, PAD + sh
    )
    column_x = PAD + sw + LEADER_GAP
    column_w = min(320.0, max(90.0, max(b["width"] for b in blocks)))
    width = column_x + column_w + PAD
    height = max(PAD + sh + PAD, tops[-1] + blocks[-1]["height"] + PAD)
    bare = f"0 0 {_n(PAD + sw + PAD)} {_n(PAD + sh + PAD)}"

    parts = []
    for block, block_top in zip(blocks, tops):
        ax, ay = block["anchor"]
        ty = block_top + TITLE_SIZE * LINE_HEIGHT / 2
        points = f"{_n(ax)},{_n(ay)} {_n(PAD + sw + 8)},{_n(ay)} {_n(column_x - 6)},{_n(ty)}"
        texts = [
            f'<text x="{_n(column_x)}" y="{_n(block_top + TITLE_SIZE)}" font-size="{_n(TITLE_SIZE)}" font-weight="600" style="fill:{_TEXT}">{html.escape(block["title"])}</text>'
        ]
        for k, line in enumerate(block["lines"]):
            baseline = block_top + TITLE_SIZE * LINE_HEIGHT + (k + 1) * VALUE_SIZE * LINE_HEIGHT - VALUE_SIZE * (LINE_HEIGHT - 1)
            texts.append(
                f'<text x="{_n(column_x)}" y="{_n(baseline)}" font-size="{_n(VALUE_SIZE)}" style="fill:{_TEXT_SOFT}">{html.escape(line)}</text>'
            )
        parts.append(
            f'<g class="sp-layer-label" data-top="{_n(block_top)}" data-height="{_n(block["height"])}">'
            f'<polyline points="{points}" fill="none" stroke-width="1.2" style="stroke:{_TEXT_SOFT}"/>'
            f'<circle cx="{_n(ax)}" cy="{_n(ay)}" r="3.2" stroke-width="1.4" style="fill:{_TEXT};stroke:{_SURFACE}"/>'
            + "".join(texts)
            + "</g>"
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
) -> dict[str, Any]:
    """Each frame as the builder shows it: its SVG (layers tagged ``data-layer-index``, the labels
    of ``labels`` drawn on the layers they name), its materials and its layers - each with the
    position of the step that created it (``step_index``, ``-1`` for the substrate), from the
    simulation's own provenance (``origins``)."""
    material_colors = {m.name: m.color for m in materials}
    payload = []
    for k, frame in enumerate(frames):
        frame_origins = origins[k] if origins is not None else [None] * len(frame.layers)
        annotations = annotations_for(steps or [], declared or {}, labels or {}, frame_origins) if labels else []
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
