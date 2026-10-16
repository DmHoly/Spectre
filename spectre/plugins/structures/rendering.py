"""SVG of a structure, always drawn by StructureForge (``structureforge.presentation.svg.frame_to_svg``,
through :func:`frame_svg`): the simulated frames the builder previews, and a committed structure
redrawn from its stored, already-flattened layers.

The **layer labels** (:class:`~spectre.plugins.structures.simulation.LayerLabel`) are Spectre's own:
:func:`labelled_svg` sets StructureForge's drawing in a wider SVG, the labels of the chosen steps
stacked on its right - each one's text, its values below, a thin line to the layer its step
created. The labelled steps of one brick (:class:`~spectre.plugins.structures.simulation.ProcessBrick`,
at least :data:`~spectre.plugins.structures.simulation.MIN_GROUPED_LABELS` of them) share a single
label instead: the brick's name, one line per step, and a bracket over the layers they created.
A labelled step that creates no layer (a clean, an etch, an etch back:
:data:`~spectre.plugins.structures.simulation.INTERFACE_STEP_KINDS`) is drawn as an **interface
mark** - a dashed line to the surface as it was when the step took place, between the layers made
before it and those made after.
The provenance of the layers (which step created which layer) always comes from the
server's simulation (``simulation.SimulationResult.layer_origins``, or what a study recorded of
it), never from matching materials. The result is a self-contained SVG: colours are the page's
tokens with their value as fallback, so it reads the same in a screenshot or in the report.
"""

from __future__ import annotations

import hashlib
import html
import itertools
import re
import threading
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union
from structureforge.adapters.follow_adapter import ProcessStructure
from structureforge.core.materials import MaterialLibrary
from structureforge.core.units import Length
from structureforge.presentation.svg import frame_to_svg
from structureforge.process.simulate import Frame
from structureforge.process.steps import ProcessStep

from .simulation import (
    GRADED_NITRIDE_RE,
    INTERFACE_STEP_KINDS,
    LABEL_COMPOSITION,
    LABEL_DECLARED_PREFIX,
    LABEL_DEPTH,
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
    (``line_layers``: the layers of each line's step). ``interface``: the mark of a step that
    created no layer - ``layers`` are then the layers made before it, ``after`` those made after
    it, and the line points at the surface between the two. ``step``: the position of the step
    whose label this is (a brick's: its first labelled step's, which keeps the brick's
    ``offset``); ``offset``: how far its text was moved by hand from its automatic place;
    ``anchor``: where its point was put by hand, in fractions of the frame of what it points at
    (:attr:`~.simulation.LayerLabel.anchor` - never for a brick, whose bracket is its point);
    ``anchor_bounds``: that frame (``(min_x, min_y, max_x, max_y)`` in the geometry) when it is not
    this drawing's own - the final structure's, for every frame of a simulation
    (:func:`frames_payload`), so that a point put on one frame lands at the same place on all.
    ``flipped``: an interface mark whose step was followed by an odd number of flips before this
    drawing - its surface is then the underside of the layers made before it."""

    title: str
    lines: tuple[str, ...]
    layers: tuple[int, ...]
    grouped: bool = False
    line_layers: tuple[tuple[int, ...], ...] = ()
    interface: bool = False
    after: tuple[int, ...] = ()
    step: int | None = None
    offset: tuple[float, float] | None = None
    anchor: tuple[float, float] | None = None
    anchor_bounds: tuple[float, float, float, float] | None = None
    flipped: bool = False


def length_text(nm: float) -> str:
    """A length in a readable unit, with the value as entered (:func:`format_number`, not rounded
    to 3 digits): ``80 nm``, ``1.5 µm``, ``1.234 µm``, ``1.005 µm``."""
    return f"{format_number(nm / 1000)} µm" if abs(nm) >= 1000 else f"{format_number(nm)} nm"


def value_text(value: Any) -> str:
    """Une valeur de paramètre déclaré telle qu'une étiquette l'écrit (un nombre comme saisi)."""
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
    return f"{value_text(param.value)}{' ' + unit if unit else ''}"


def label_title(step: ProcessStep, label: LayerLabel) -> str:
    """The text of ``step``'s label: its own, or else the step's material, or else its name (always
    its name for an interface mark: the material of a resist strip is not what it made)."""
    if step.kind in INTERFACE_STEP_KINDS:
        return label.text or step.name
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
        elif key == LABEL_DEPTH:
            depth = getattr(step, "depth", None)
            if isinstance(depth, Length):
                values.append(("", length_text(depth.to_nm())))
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
    through: int | None = None,
) -> list[LayerAnnotation]:
    """The labels of a drawing whose layers were created by the steps ``origins`` names (one
    position per layer of ``frame.layers``, :data:`SUBSTRATE_ORIGIN` or ``None`` for the
    substrate) - one per labelled step that has a layer in it, in the order of the steps. The
    labelled steps of one brick (``bricks``, see :func:`~.simulation.grouped_labels`) share the
    brick's label instead, one line per step that has a layer in the drawing. A labelled step that
    creates no layer (:data:`~.simulation.INTERFACE_STEP_KINDS`) is an interface mark of its own,
    never grouped: between the layers made before it (the substrate among them) and those made
    after it. ``through``: how many steps the drawing has seen (the final structure's: all of them) -
    an interface mark turned over by the flips between its step and the drawing is ``flipped``."""
    through = len(steps) if through is None else through
    # une étape seulement cotée (LayerLabel.shown faux) n'a pas d'étiquette : ses cotes, à part
    labels = {index: label for index, label in labels.items() if label.shown}
    # une marque ne paraît qu'une fois son étape passée (une couche, elle, n'est là qu'après la sienne)
    marks = {index: label for index, label in labels.items() if 0 <= index < min(len(steps), through) and steps[index].kind in INTERFACE_STEP_KINDS}
    labelled = {index: label for index, label in labels.items() if 0 <= index < len(steps) and steps[index].kind not in INTERFACE_STEP_KINDS}
    groups = grouped_labels(bricks or [], labelled)
    in_group = {index for _brick, members in groups for index in members}

    def layers_of(indexes: set[int]) -> tuple[int, ...]:
        return tuple(k for k, origin in enumerate(origins) if origin in indexes and origin != SUBSTRATE_ORIGIN)

    def substrate(origin: int | None) -> bool:
        return origin is None or origin == SUBSTRATE_ORIGIN

    ordered: list[tuple[int, LayerAnnotation]] = []
    for index in sorted(marks):
        before = tuple(k for k, origin in enumerate(origins) if substrate(origin) or origin < index)
        after = tuple(k for k, origin in enumerate(origins) if not substrate(origin) and origin > index)
        if not before:
            continue
        title, lines = label_text(steps[index], declared.get(index, []), marks[index])
        flipped = sum(1 for step in steps[index + 1 : through] if step.kind == "flip") % 2 == 1
        mark = LayerAnnotation(
            title, lines, before, interface=True, after=after, step=index, offset=marks[index].offset, anchor=marks[index].anchor, flipped=flipped
        )
        ordered.append((index, mark))
    for index in sorted(labelled):
        layers = layers_of({index})
        if index in in_group or not layers:
            continue
        title, lines = label_text(steps[index], declared.get(index, []), labelled[index])
        ordered.append((index, LayerAnnotation(title, lines, layers, step=index, offset=labelled[index].offset, anchor=labelled[index].anchor)))
    for brick, members in groups:
        present = [index for index in members if layers_of({index})]
        if not present:
            continue
        lines = tuple(grouped_line(steps[index], declared.get(index, []), labelled[index]) for index in present)
        line_layers = tuple(layers_of({index}) for index in present)
        first = present[0]
        annotation = LayerAnnotation(
            brick.name, lines, layers_of(set(present)), grouped=True, line_layers=line_layers, step=first, offset=labelled[first].offset
        )
        ordered.append((first, annotation))
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
# des accolades dont les hauteurs se recouvrent (les coquilles d'un nanofil enveloppent son cœur) :
# chacune dans sa colonne, la plus courte au plus près du dessin
BRACKET_COLUMN = BRACKET_DEPTH + 4.0
# la marque d'une étape sans couche : un tiret de part et d'autre du point, un losange dessus
INTERFACE_TICK = 9.0
INTERFACE_DIAMOND = 3.8
# le point d'une étiquette sur sa couche, et la zone où l'attraper pour le déplacer (constructeur :
# un cercle invisible, inerte ailleurs - pointer-events="none", rallumé par la feuille de style)
ANCHOR_DOT = 3.2
ANCHOR_HIT = 10.0
MAX_TITLE_CHARS = 40
MAX_LINE_CHARS = 48
MAX_GROUPED_LINE_CHARS = 64
_TEXT = "var(--text, #1b2440)"
_TEXT_SOFT = "var(--text-soft, #4a5470)"
_SURFACE = "var(--surface, #ffffff)"
_FONT = "var(--font-ui, 'DM Sans', 'Helvetica Neue', Arial, sans-serif)"
_VIEWBOX_RE = re.compile(r'viewBox="([^"]+)"')


def _valid(polygon: Any) -> Any:
    # ``buffer(0)`` ne répare qu'un contour invalide - sur un contour valide il ne change rien, mais
    # coûte cher (des secondes sur les couches d'un réseau de fils, à chaque image) : on l'évite
    return polygon if polygon.is_valid else polygon.buffer(0)


def _shape(rings: list[dict]) -> Any:
    polygons = [_valid(Polygon(ring["exterior"], ring.get("holes") or [])) for ring in rings if len(ring.get("exterior") or []) >= 3]
    return unary_union(polygons) if polygons else None


def _layer_shape(layer: Any) -> Any:
    """La forme d'une couche (``None`` si vide) : le polygone du moteur lui-même quand il est là (une
    image simulée), sinon refaite de ses contours (une structure enregistrée, :class:`_RenderableLayer`)."""
    polygon = getattr(layer, "polygon", None)
    shape = _valid(polygon) if isinstance(polygon, BaseGeometry) else _shape(layer.rings())
    return None if shape is None or shape.is_empty else shape


def _anchor(shape: Any) -> tuple[float, float] | None:
    """A point inside the layer, towards its right edge (the labels are on the right) - on the
    horizontal line through a point surely inside it."""
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


# la grille (en nm) sur laquelle s'unissent les couches : le moteur laisse un bruit flottant entre
# deux couches qui se touchent (le bas d'un dépôt à 1e-18 au lieu de 0) qui, sans elle, garde leur
# interface dans le contour de l'union - une marque d'interface s'y poserait comme sur une surface
_UNION_GRID = 1e-6


def _union(frame: Frame, layers: tuple[int, ...]) -> Any:
    shapes = [shape for k in layers if k < len(frame.layers) for shape in [_layer_shape(frame.layers[k])] if shape is not None]
    return shapely.union_all(shapes, grid_size=_UNION_GRID) if shapes else None


# où chercher la surface d'une marque d'interface, en fraction de la largeur : à droite d'abord, du
# côté des étiquettes
_INTERFACE_SAMPLES = (0.92, 0.85, 0.75, 0.65, 0.5, 0.35, 0.2, 0.08)


def _interface_anchor(frame: Frame, before: tuple[int, ...], after: tuple[int, ...], flipped: bool = False) -> tuple[float, float] | None:
    """A point on the surface a step that made no layer left behind: the top of the layers made
    before it (``before``) - their underside once the wafer has been turned over since (``flipped``) -,
    where a layer made after it (``after``) lies on it - the interface -, else where that surface is
    bare; towards the right edge, like the labels."""
    below = _union(frame, before)
    if below is None:
        return None
    above = _union(frame, after)
    min_x, min_y, max_x, max_y = below.bounds
    tolerance = 0.01 * max(max_x - min_x, max_y - min_y, 1e-9)
    bare = None
    for fraction in _INTERFACE_SAMPLES:
        x = min_x + fraction * (max_x - min_x)
        crossing = below.intersection(LineString([(x, min_y - 1), (x, max_y + 1)]))
        if crossing.is_empty:
            continue
        surface = crossing.bounds[1] if flipped else crossing.bounds[3]
        if above is None or above.distance(Point(x, surface)) <= tolerance:
            return x, surface
        bare = bare or (x, surface)
    return bare


def _at_fractions(bounds: tuple[float, float, float, float], fractions: tuple[float, float]) -> Point:
    """Le point du cadre ``bounds`` (``(min_x, min_y, max_x, max_y)`` de la géométrie) à ``fractions``
    - de gauche à droite et de haut en bas (le haut de la géométrie : son plus grand y)."""
    min_x, min_y, max_x, max_y = bounds
    fx, fy = fractions
    return Point(min_x + fx * (max_x - min_x), max_y - fy * (max_y - min_y))


def _placed_anchor(shape: Any, point: Point, inset: float) -> tuple[float, float]:
    """Le point d'accroche posé à la main (:attr:`~.simulation.LayerLabel.anchor`) en ``point`` sur
    ``shape``, les couches de l'étape : là où il a été posé s'il est sur elles ; sinon (posé à côté,
    ou la couche a changé depuis) le point d'elles le plus proche, rentré de ``inset`` (le rayon du
    point) là où elles sont assez épaisses pour qu'il y tienne entier - jamais vers une partie
    épaisse lointaine : posé à côté d'un flanc fin, il reste sur ce flanc."""
    if shape.covers(point):
        return point.x, point.y
    near = nearest_points(shape, point)[0]
    inner = shape.buffer(-inset)
    if not inner.is_empty:
        inside = nearest_points(inner, near)[0]
        # assez épaisse ici : à ``inset`` du bord (un peu plus dans un coin, au plus inset * √2)
        if inside.distance(near) <= 1.5 * inset:
            near = inside
    return near.x, near.y


def _frame_bounds(frame: Frame) -> tuple[float, float, float, float]:
    """Le cadre (``(min_x, min_y, max_x, max_y)``) de toutes les couches de ``frame``."""
    points = [point for layer in frame.layers for ring in layer.rings() for point in ring.get("exterior") or []]
    xs, ys = [point[0] for point in points], [point[1] for point in points]
    return (min(xs), min(ys), max(xs), max(ys)) if points else (0.0, 0.0, 0.0, 0.0)


def _surface(below: Any, frame_bounds: tuple[float, float, float, float]) -> Any:
    """La surface de ``below`` (les couches d'avant une étape sans couche) : son contour sans ce qui
    longe les côtés et le fond du dessin (``frame_bounds``, le cadre de toutes ses couches) - les bords
    du domaine simulé et le dessous de l'empilement, où aucune étape n'a lieu. Le fond du dessin, pas
    celui de ``below`` : après un retournement, l'interface d'une étape d'avant est sous elles."""
    min_x, min_y, max_x, max_y = frame_bounds
    tolerance = 0.01 * max(max_x - min_x, max_y - min_y, 1e-9)
    edges = unary_union(
        [LineString([(min_x, min_y), (min_x, max_y)]), LineString([(max_x, min_y), (max_x, max_y)]), LineString([(min_x, min_y), (max_x, min_y)])]
    ).buffer(tolerance)
    surface = below.boundary.difference(edges)
    return below.boundary if surface.is_empty else surface


def _placed_interface_anchor(below: Any, point: Point, frame_bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    """Le point d'une marque d'interface posé à la main en ``point`` : le point de la surface de
    ``below`` (les couches d'avant l'étape, :func:`_surface`) le plus proche - sur le dessus comme sur
    un flanc."""
    nearest = nearest_points(_surface(below, frame_bounds), point)[0]
    return nearest.x, nearest.y


# La largeur d'un texte, estimée (le serveur ne mesure pas le texte) et par excès : la chasse de
# chaque caractère, en fraction de la taille de police, arrondie au dixième supérieur du plus large
# de DM Sans et de ses polices de repli (Helvetica Neue, Arial), en gras (600) comme en normal -
# mesurée dans le navigateur. « WWWW… » mesure 1 em par lettre en DM Sans 600, trois fois un « i ».
# Hors de l'ASCII, une lettre accentuée a la chasse de sa lettre de base ; tout autre caractère est
# compté large (Œ, Æ, l'idéogramme d'une police de repli : :data:`_WIDE`) et un émoji ou un
# pictogramme plus encore (:data:`_EMOJI`) - par excès toujours : aucun texte ne sort du SVG.
_CHAR_WIDTHS = {
    **dict.fromkeys("il .,'|", 0.3),
    **dict.fromkeys("Ifjt:;!·()[]°⁻¹²³", 0.4),
    **dict.fromkeys("rz/", 0.5),
    **dict.fromkeys("mw&#_", 0.9),
    **dict.fromkeys("MW—…%@", 1.1),
}
_WIDE = 1.2
_EMOJI = 1.6


def _top_of(frame: Frame, layers: tuple[int, ...]) -> float:
    """Le haut (en y de la géométrie, vers le haut) des couches ``layers`` de ``frame``."""
    ys = [point[1] for k in layers if k < len(frame.layers) for ring in frame.layers[k].rings() for point in ring.get("exterior") or []]
    return max(ys) if ys else float("-inf")


def _char_width(char: str) -> float:
    known = _CHAR_WIDTHS.get(char)
    if known:
        return known
    if char.isascii():
        return 0.8 if char.isupper() else 0.7
    base = unicodedata.normalize("NFD", char)[0]
    if base != char and base.isascii():
        return _char_width(base)
    if ord(char) > 0xFFFF or unicodedata.category(char) == "So":
        return _EMOJI
    return _WIDE


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


def _bracket_columns(brackets: list[tuple[float, float] | None]) -> list[int | None]:
    """La colonne de chaque accolade (``(y1, y2)`` ; ``None`` pour un bloc sans accolade) : la plus
    proche du dessin où elle ne recouvre aucune accolade déjà placée (deux briques empilées se
    touchent : même colonne), les plus courtes placées d'abord - une accolade qui en contient une
    autre passe à sa droite."""
    columns: list[int | None] = [None] * len(brackets)
    taken: list[list[tuple[float, float]]] = []
    order = sorted((i for i, b in enumerate(brackets) if b is not None), key=lambda i: (brackets[i][1] - brackets[i][0], brackets[i][0]))
    for i in order:
        y1, y2 = brackets[i]
        column = next(
            (c for c, spans in enumerate(taken) if all(y2 <= a + 0.5 or y1 >= b - 0.5 for a, b in spans)), len(taken)
        )
        if column == len(taken):
            taken.append([])
        taken[column].append((y1, y2))
        columns[i] = column
    return columns


def labelled_svg(
    frame: Frame,
    material_colors: dict[str, str],
    annotations: list[LayerAnnotation],
    *,
    tag_layers: bool = False,
    anchors: bool = True,
    measures: list[MeasureLine] | tuple[MeasureLine, ...] = (),
) -> str:
    """StructureForge's drawing of ``frame`` (:func:`frame_svg`), with ``annotations`` stacked on
    its right - unchanged when there is none. The drawing becomes a nested ``<svg>`` fitted in a
    :data:`STRUCTURE_BOX` square; the outer one carries ``data-bare-viewbox``, the view without the
    labels (a page hides ``.sp-layer-labels`` and switches to it). Every text is escaped.
    ``anchors=False``: the points put by hand are not honoured, nor can any be put (no
    ``data-anchor-box``) - a frame before a flip, which the final structure's frame of reference
    (:attr:`LayerAnnotation.anchor_bounds`) does not fit. ``measures``: the dimension lines drawn
    over the structure (:func:`measure_line`), kept when a page hides the labels."""
    base = frame_svg(frame, material_colors)
    if tag_layers:
        base = _tag_layer_indices(base)
    if not annotations and not measures:
        return base
    view = _VIEWBOX_RE.search(base)
    inner = base[base.index(">") + 1 : base.rindex("</svg>")]
    vx, vy, vw, vh = (float(v) for v in view.group(1).split()) if view else (0.0, 0.0, 1.0, 1.0)
    scale = STRUCTURE_BOX / max(vw, vh)
    sw, sh = vw * scale, vh * scale

    def to_svg(x: float, y: float) -> tuple[float, float]:
        # le dessin est retourné (y vers le haut) : un point (x, y) de la géométrie est en (x, -y)
        return PAD + (x - vx) * scale, PAD + (-y - vy) * scale

    def svg_box(bounds: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        min_x, min_y, max_x, max_y = bounds
        return (*to_svg(min_x, max_y), *to_svg(max_x, min_y))

    bracket_x = PAD + sw + BRACKET_GAP
    blocks = []
    marks_at: list[tuple[float, float]] = []
    for annotation in annotations:
        bracket = None
        candidates = [shape for k in annotation.layers if k < len(frame.layers) for shape in [_layer_shape(frame.layers[k])] if shape is not None]
        if not candidates:
            continue
        # ce que désigne le point d'accroche (les couches de l'étape ; d'une marque d'interface, celles
        # d'avant elle) et le cadre où il se pose à la main (LayerLabel.anchor, en fractions de ce
        # cadre : celui de la structure finale, sinon le sien) - une accolade n'en a pas ; auto_y : la
        # hauteur de son point automatique, d'après laquelle les textes s'empilent - poser le point ne
        # déplace aucun texte
        designated = None if annotation.grouped else _union(frame, annotation.layers)
        reference = (annotation.anchor_bounds or designated.bounds) if anchors and designated is not None else None
        placed = _at_fractions(reference, annotation.anchor) if reference is not None and annotation.anchor else None
        if annotation.interface:
            point = _interface_anchor(frame, annotation.layers, annotation.after, annotation.flipped)
            if point is None or designated is None:
                continue
            anchor = to_svg(*point)
            auto_y = anchor[1]
            if placed is not None:
                anchor = to_svg(*_placed_interface_anchor(designated, placed, _frame_bounds(frame)))
            else:
                # deux étapes sur la même interface (une gravure puis un nettoyage) : côte à côte
                while any(abs(anchor[0] - x) < INTERFACE_TICK and abs(anchor[1] - y) < INTERFACE_TICK for x, y in marks_at):
                    anchor = (anchor[0] - 2.4 * INTERFACE_TICK, anchor[1])
            marks_at.append(anchor)
        elif annotation.grouped:
            # une accolade sur toute la hauteur des couches de la brique (jamais plus fine qu'un trait lisible)
            _min_x, min_y, _max_x, max_y = unary_union(candidates).bounds
            top, bottom = to_svg(0, max_y)[1], to_svg(0, min_y)[1]
            middle = (top + bottom) / 2
            half = max((bottom - top) / 2, BRACKET_MIN_HEIGHT / 2)
            bracket = (middle - half, middle + half)
            anchor = (bracket_x, middle)  # x : au bout de l'accolade, selon sa colonne (plus bas)
            auto_y = middle
        else:
            point = _anchor(max(candidates, key=lambda shape: shape.area))
            if point is None:
                continue
            anchor = to_svg(*point)
            auto_y = anchor[1]
            if placed is not None and designated is not None:
                anchor = to_svg(*_placed_anchor(designated, placed, ANCHOR_DOT / scale))
        title = _ellipsis(annotation.title, MAX_TITLE_CHARS)
        lines = list(annotation.lines)
        if annotation.grouped and len(annotation.line_layers) == len(lines):
            # les lignes d'une brique dans l'ordre de ses couches sur le dessin, de la plus haute à la plus basse
            lines = [line for _top, line in sorted(zip((_top_of(frame, layers) for layers in annotation.line_layers), lines), key=lambda item: -item[0])]
        lines = [_ellipsis(line, MAX_GROUPED_LINE_CHARS if annotation.grouped else MAX_LINE_CHARS) for line in lines]
        height = TITLE_SIZE * LINE_HEIGHT + len(lines) * VALUE_SIZE * LINE_HEIGHT
        width = max([_text_width(title, TITLE_SIZE)] + [_text_width(line, VALUE_SIZE) for line in lines])
        blocks.append(
            {
                "anchor": anchor,
                "bracket": bracket,
                "title": title,
                "lines": lines,
                "height": height,
                "width": width,
                "interface": annotation.interface,
                "step": annotation.step,
                "offset": annotation.offset or (0.0, 0.0),
                "auto_y": auto_y,
                "box": svg_box(reference) if reference is not None else None,
                "placed": annotation.anchor if placed is not None else None,
            }
        )
    measure_parts, measure_boxes = _measure_marks(measures, to_svg)
    if not blocks and not measure_parts:
        return base
    bare = f"0 0 {_n(PAD + sw + PAD)} {_n(PAD + sh + PAD)}"
    if not blocks:
        min_x = min([0.0] + [box[0] - PAD for box in measure_boxes])
        min_y = min([0.0] + [box[1] - PAD for box in measure_boxes])
        max_x = max([PAD + sw + PAD] + [box[2] + PAD for box in measure_boxes])
        max_y = max([PAD + sh + PAD] + [box[3] + PAD for box in measure_boxes])
        return _outer_svg(min_x, min_y, max_x - min_x, max_y - min_y, bare, sw, sh, view, inner, [], measure_parts)
    columns = _bracket_columns([b["bracket"] for b in blocks])
    for block, column in zip(blocks, columns):
        if column is not None:
            block["bracket_x"] = bracket_x + column * BRACKET_COLUMN
            block["anchor"] = (block["bracket_x"] + BRACKET_DEPTH + BRACKET_TIP, block["anchor"][1])
    extra = max([c for c in columns if c is not None], default=0) * BRACKET_COLUMN
    # le coude des traits : au-delà de la dernière colonne d'accolades, qu'ils croisent à angle droit
    elbow = bracket_x + extra + BRACKET_DEPTH + BRACKET_TIP if any(c is not None for c in columns) else PAD + sw + 8
    blocks.sort(key=lambda b: b["auto_y"])
    tops = _place([b["auto_y"] - TITLE_SIZE * LINE_HEIGHT / 2 for b in blocks], [b["height"] for b in blocks], PAD, PAD + sh)
    column_x = PAD + sw + LEADER_GAP + extra
    # la colonne est aussi large que la plus large des étiquettes (estimée par excès) : rien ne déborde
    column_w = max(90.0, max(b["width"] for b in blocks))
    # une étiquette déplacée à la main (LayerLabel.offset) : son texte quitte la colonne, le trait le
    # suit ; le cadre s'agrandit pour la contenir, de tous les côtés
    tops = [top + block["offset"][1] for top, block in zip(tops, blocks)]
    lefts = [column_x + block["offset"][0] for block in blocks]
    min_x = min([0.0] + [x - 6 - PAD for x in lefts])
    min_y = min([0.0] + [top - PAD for top in tops])
    max_x = max([column_x + column_w + PAD] + [x + b["width"] + PAD for x, b in zip(lefts, blocks)])
    max_y = max([PAD + sh + PAD] + [top + b["height"] + PAD for top, b in zip(tops, blocks)])
    min_x = min([min_x] + [box[0] - PAD for box in measure_boxes])
    min_y = min([min_y] + [box[1] - PAD for box in measure_boxes])
    max_x = max([max_x] + [box[2] + PAD for box in measure_boxes])
    max_y = max([max_y] + [box[3] + PAD for box in measure_boxes])
    width, height = max_x - min_x, max_y - min_y

    parts = []
    for block, block_top, text_x in zip(blocks, tops, lefts):
        ax, ay = block["anchor"]
        ty = block_top + TITLE_SIZE * LINE_HEIGHT / 2
        points = _leader_points(ax, ay, elbow, text_x, ty, block["width"])
        if block["bracket"] is not None:
            y1, y2 = block["bracket"]
            bx = block["bracket_x"]
            tip = bx + BRACKET_DEPTH
            mark = (
                f'<path class="sp-layer-bracket" data-y1="{_n(y1)}" data-y2="{_n(y2)}" data-x="{_n(tip)}" '
                f'd="M{_n(bx)},{_n(y1)} H{_n(tip)} V{_n(y2)} H{_n(bx)} M{_n(tip)},{_n(ay)} H{_n(ax)}" '
                f'fill="none" stroke-width="1.4" stroke-linejoin="round" style="stroke:{_TEXT_SOFT}"/>'
                f'<polyline points="{points}" class="sp-layer-leader" fill="none" stroke-width="1.2" style="stroke:{_TEXT_SOFT}"/>'
            )
        elif block["interface"]:
            # une marque d'interface : un trait pointillé, un tiret posé sur la surface et un losange
            r = INTERFACE_DIAMOND
            tick = f'<path d="M{_n(ax - INTERFACE_TICK)},{_n(ay)} H{_n(ax + INTERFACE_TICK)}" stroke-width="2" stroke-linecap="round" style="stroke:{_TEXT}"/>'
            diamond = (
                f'<path d="M{_n(ax)},{_n(ay - r)} L{_n(ax + r)},{_n(ay)} L{_n(ax)},{_n(ay + r)} L{_n(ax - r)},{_n(ay)} Z" '
                f'stroke-width="1.4" style="fill:{_SURFACE};stroke:{_TEXT}"/>'
            )
            mark = (
                f'<polyline points="{points}" class="sp-layer-leader" fill="none" stroke-width="1.2" stroke-dasharray="4 3" style="stroke:{_TEXT_SOFT}"/>'
                + _anchor_mark(ax, ay, tick + diamond)
            )
        else:
            dot = f'<circle cx="{_n(ax)}" cy="{_n(ay)}" r="{_n(ANCHOR_DOT)}" stroke-width="1.4" style="fill:{_TEXT};stroke:{_SURFACE}"/>'
            mark = f'<polyline points="{points}" class="sp-layer-leader" fill="none" stroke-width="1.2" style="stroke:{_TEXT_SOFT}"/>' + _anchor_mark(ax, ay, dot)
        texts = [
            f'<text x="{_n(text_x)}" y="{_n(block_top + TITLE_SIZE)}" font-size="{_n(TITLE_SIZE)}" font-weight="600" style="fill:{_TEXT}">{html.escape(block["title"])}</text>'
        ]
        for k, line in enumerate(block["lines"]):
            baseline = block_top + TITLE_SIZE * LINE_HEIGHT + (k + 1) * VALUE_SIZE * LINE_HEIGHT - VALUE_SIZE * (LINE_HEIGHT - 1)
            texts.append(
                f'<text x="{_n(text_x)}" y="{_n(baseline)}" font-size="{_n(VALUE_SIZE)}" style="fill:{_TEXT_SOFT}">{html.escape(line)}</text>'
            )
        grouped = ' data-grouped="true"' if block["bracket"] is not None else ' data-interface="true"' if block["interface"] else ""
        step = f' data-step="{block["step"]}"' if block["step"] is not None else ""
        dx, dy = block["offset"]
        moved = f' data-offset="{_n(dx)} {_n(dy)}"' if (dx or dy) else ""
        # data-anchor-box : le cadre où poser le point à la main (data-anchor-placed : où il l'a été,
        # en fractions de ce cadre) - une accolade n'en a pas
        if block["box"] is not None:
            moved += f' data-anchor-box="{" ".join(_n(v) for v in block["box"])}"'
        if block["placed"]:
            moved += f' data-anchor-placed="{" ".join(f"{v:g}" for v in block["placed"])}"'
        # data-anchor, data-elbow, data-width : de quoi redessiner le trait pendant qu'on déplace le
        # texte ou le point à la souris (constructeur, layer-label.js)
        parts.append(
            f'<g class="sp-layer-label" data-top="{_n(block_top)}" data-height="{_n(block["height"])}"{grouped}{step}{moved} '
            f'data-anchor="{_n(ax)} {_n(ay)}" data-elbow="{_n(elbow)}" data-width="{_n(block["width"])}">'
            + mark
            + f'<g class="sp-layer-label__text">{"".join(texts)}</g>'
            + "</g>"
        )
    return _outer_svg(min_x, min_y, width, height, bare, sw, sh, view, inner, parts, measure_parts)


def _outer_svg(
    min_x: float, min_y: float, width: float, height: float, bare: str, sw: float, sh: float, view: Any, inner: str, parts: list[str], measure_parts: list[str]
) -> str:
    """Le dessin de StructureForge (``inner``, dans un carré ``sw`` × ``sh``) et ce que Spectre y
    ajoute : ses cotes par-dessus, ses étiquettes à droite (``.sp-layer-labels``, qu'une page peut
    cacher : ``data-bare-viewbox``)."""
    measures = f'<g class="sp-measures" style="font-family:{_FONT}">{"".join(measure_parts)}</g>' if measure_parts else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_n(min_x)} {_n(min_y)} {_n(width)} {_n(height)}" width="{_n(width)}" height="{_n(height)}" '
        f'class="sp-labelled-structure" data-bare-viewbox="{bare}">'
        f'<svg x="{_n(PAD)}" y="{_n(PAD)}" width="{_n(sw)}" height="{_n(sh)}" viewBox="{view.group(1) if view else "0 0 1 1"}">{inner}</svg>'
        + measures
        + f'<g class="sp-layer-labels" style="font-family:{_FONT}">{"".join(parts)}</g>'
        "</svg>"
    )


# -- les cotes ---------------------------------------------------------------------------------------
#
# Une cote (:class:`~.simulation.Measure`) mesure ce qui est sous un point de l'image d'une étape :
# la traversée verticale (une épaisseur) ou horizontale (une largeur) de la couche sous le point - ou
# de toute la matière d'un seul tenant autour de lui. Le moteur donne les contours ; la mesure est
# celle du dessin, au dixième de nm.

MEASURE_TICK = 5.0  # la demi-longueur des traits d'extrémité (unités du dessin)
MEASURE_ARROW = 5.0
MEASURE_TEXT_GAP = 5.0


@dataclass(frozen=True)
class MeasureLine:
    """Une cote calculée : son segment ``(x1, y1)``-``(x2, y2)`` dans la géométrie (nm, y vers le
    haut), sa longueur (nm), le matériau mesuré, et d'où elle vient - l'étape (``step``) et sa
    place parmi les cotes de l'étape (``index``)."""

    direction: str
    x1: float
    y1: float
    x2: float
    y2: float
    length: float
    material: str
    step: int | None = None
    index: int = 0
    # une cote suivie (Measure.also) : l'étape de l'image où elle est reprise, et sa longueur sur
    # l'image de sa propre étape - l'écart s'écrit à côté
    at: int | None = None
    reference: float | None = None


def _segments(geometry: Any) -> list[Any]:
    lines = [g for g in getattr(geometry, "geoms", [geometry]) if g.geom_type in ("LineString", "MultiLineString") and not g.is_empty]
    if not lines:
        return []
    merged = shapely.line_merge(unary_union(lines))
    return [g for g in getattr(merged, "geoms", [merged]) if g.geom_type == "LineString" and not g.is_empty]


def _measured(
    frame: Frame, point: Point, direction: str, scope: str, among: set[int] | None = None
) -> tuple[tuple[float, float, float, float, float], int, Any] | None:
    """La traversée de ``frame`` par ``point`` : ``((x1, y1, x2, y2, longueur), la couche mesurée,
    sa forme)`` - la couche sous le point (la plus haute ; à défaut la plus proche), ou, ``among``
    donné, la plus proche du point parmi ces couches-là ; avec, ``scope`` ``"material"``, toute la
    matière d'un seul tenant de son matériau autour d'elle. ``None`` : rien à mesurer."""
    shapes = [(k, layer, shape) for k, layer in enumerate(frame.layers) for shape in [_layer_shape(layer)] if shape is not None]
    if not shapes:
        return None
    if among is not None:
        chosen = [item for item in shapes if item[0] in among]
        if not chosen:
            return None
        k, layer, shape = min(chosen, key=lambda item: item[2].distance(point))
    else:
        under = [item for item in shapes if item[2].covers(point)]
        k, layer, shape = under[-1] if under else min(shapes, key=lambda item: item[2].distance(point))
    own = shape
    if scope == "material":
        same = [other for _j, other_layer, other in shapes if other_layer.material == layer.material]
        union = shapely.union_all(same, grid_size=_UNION_GRID)
        parts = [g for g in getattr(union, "geoms", [union]) if not g.is_empty]
        shape = min(parts, key=lambda part: part.distance(own)) if parts else shape
    min_x, min_y, max_x, max_y = shape.bounds
    if direction == "thickness":
        x = min(max(point.x, min_x), max_x)
        across = LineString([(x, min_y - 1), (x, max_y + 1)])
    else:
        y = min(max(point.y, min_y), max_y)
        across = LineString([(min_x - 1, y), (max_x + 1, y)])
    segments = _segments(shape.intersection(across))
    if among is not None:
        # la traversée de la couche suivie (pas celle d'une autre partie de sa matière)
        segments = [g for g in segments if g.intersects(own.buffer(1e-3))] or segments
    if not segments:
        return None
    segment = min(segments, key=lambda g: g.distance(point))
    (x1, y1), (x2, y2) = segment.coords[0], segment.coords[-1]
    if (direction == "thickness" and y1 < y2) or (direction == "width" and x1 > x2):
        (x1, y1), (x2, y2) = (x2, y2), (x1, y1)  # du haut vers le bas, de gauche à droite
    return (x1, y1, x2, y2, round(segment.length, 1)), k, own


def measure_line(frame: Frame, measure: Any, step: int | None = None, index: int = 0) -> MeasureLine | None:
    """La cote ``measure`` (:class:`~.simulation.Measure`) sur ``frame`` : la couche sous son point
    (la plus haute dans l'empilement ; à défaut, la plus proche), ou toute la matière d'un seul tenant
    de son matériau (``scope`` ``"material"``), traversée à la verticale du point (une épaisseur) ou à
    son horizontale (une largeur) - le morceau de la traversée qui passe par le point. ``None`` : rien
    à mesurer (une image vide)."""
    found = _measured(frame, Point(measure.point), measure.direction, measure.scope)
    if found is None:
        return None
    (x1, y1, x2, y2, length), k, _shape = found
    return MeasureLine(measure.direction, x1, y1, x2, y2, length, frame.layers[k].material, step, index)


def followed_measure_line(
    frames: list[Frame], origins: list[list[int | None]], steps: list[ProcessStep], measure: Any, step: int, index: int, at: int
) -> MeasureLine | None:
    """La cote ``measure`` de l'étape ``step``, reprise sur l'image de l'étape ``at`` (plus loin) :
    la couche qu'elle mesure sur l'image de son étape (celle de la même étape d'origine, ``origins``),
    traversée au même endroit - même x ; à la même hauteur dans la couche, comptée depuis son dessous
    (depuis son dessus si la plaque a été retournée entre-temps). ``reference`` : sa longueur sur
    l'image de son étape. ``None`` : la couche n'y est plus (gravée), ou rien à mesurer."""
    if not 0 <= step < at < len(frames) - 1:
        return None
    first = _measured(frames[step + 1], Point(measure.point), measure.direction, measure.scope)
    if first is None:
        return None
    (_x1, _y1, _x2, _y2, reference), k0, shape0 = first
    origin, material = origins[step + 1][k0], frames[step + 1].layers[k0].material
    frame = frames[at + 1]
    among = {k for k, (layer, o) in enumerate(zip(frame.layers, origins[at + 1])) if o == origin and layer.material == material}
    shapes = [shape for k in among for shape in [_layer_shape(frame.layers[k])] if shape is not None]
    if not shapes:
        return None
    _bx, b0_min, _bx2, b0_max = shape0.bounds
    _cx, b1_min, _cx2, b1_max = unary_union(shapes).bounds
    x, y = measure.point
    height = b0_max - b0_min
    fraction = min(1.0, max(0.0, (y - b0_min) / height)) if height > 0 else 0.5
    flipped = sum(1 for later in steps[step + 1 : at + 1] if later.kind == "flip") % 2 == 1
    mapped = b1_max - fraction * (b1_max - b1_min) if flipped else b1_min + fraction * (b1_max - b1_min)
    found = _measured(frame, Point(x, mapped), measure.direction, measure.scope, among)
    if found is None:
        return None
    (x1, y1, x2, y2, length), k, _shape = found
    return MeasureLine(measure.direction, x1, y1, x2, y2, length, frame.layers[k].material, step, index, at=at, reference=reference)


def _length_with_change(line: MeasureLine) -> str:
    """La longueur d'une cote ; d'une cote suivie, avec son écart à sa valeur d'origine."""
    text = length_text(line.length)
    if line.reference is None:
        return text
    change = round(line.length - line.reference, 1)
    if abs(change) < 0.05:
        return f"{text} (=)"
    return f"{text} ({'+' if change > 0 else '−'}{length_text(abs(change))})"


def measure_lines(frame: Frame, label: Any, step: int | None) -> tuple[MeasureLine, ...]:
    """Les cotes d'une étiquette (:attr:`~.simulation.LayerLabel.measures`) sur ``frame``, l'image
    de son étape."""
    lines = (measure_line(frame, measure, step, k) for k, measure in enumerate(getattr(label, "measures", None) or []))
    return tuple(line for line in lines if line is not None)


def _measure_marks(measures: Any, to_svg: Callable[[float, float], tuple[float, float]]) -> tuple[list[str], list[tuple[float, float, float, float]]]:
    """Le dessin des cotes (des flèches entre deux traits d'extrémité, la longueur à côté, sur un
    halo pour se lire sur toutes les couches) et le cadre de chacune (unités du dessin), que le
    dessin agrandi contient."""
    parts: list[str] = []
    boxes: list[tuple[float, float, float, float]] = []
    for line in measures:
        (ax, ay), (bx, by) = to_svg(line.x1, line.y1), to_svg(line.x2, line.y2)
        text = _length_with_change(line)
        text_w = _text_width(text, VALUE_SIZE)
        if line.direction == "thickness":
            tick = f"M{_n(ax - MEASURE_TICK)},{_n(ay)} H{_n(ax + MEASURE_TICK)} M{_n(bx - MEASURE_TICK)},{_n(by)} H{_n(bx + MEASURE_TICK)}"
            size = min(MEASURE_ARROW, abs(by - ay) / 2)
            arrows = (
                f"M{_n(ax)},{_n(ay)} l{_n(-size / 2)},{_n(size)} h{_n(size)} Z "
                f"M{_n(bx)},{_n(by)} l{_n(-size / 2)},{_n(-size)} h{_n(size)} Z"
            )
            tx, ty, anchor = ax + MEASURE_TICK + MEASURE_TEXT_GAP, (ay + by) / 2 + VALUE_SIZE / 3, "start"
            box = (min(ax, bx) - MEASURE_TICK, min(ay, by), tx + text_w, max(ay, by))
        else:
            tick = f"M{_n(ax)},{_n(ay - MEASURE_TICK)} V{_n(ay + MEASURE_TICK)} M{_n(bx)},{_n(by - MEASURE_TICK)} V{_n(by + MEASURE_TICK)}"
            size = min(MEASURE_ARROW, abs(bx - ax) / 2)
            arrows = (
                f"M{_n(ax)},{_n(ay)} l{_n(size)},{_n(-size / 2)} v{_n(size)} Z "
                f"M{_n(bx)},{_n(by)} l{_n(-size)},{_n(-size / 2)} v{_n(size)} Z"
            )
            tx, ty, anchor = (ax + bx) / 2, ay - MEASURE_TICK - MEASURE_TEXT_GAP, "middle"
            box = (min(tx - text_w / 2, ax), ty - VALUE_SIZE, max(tx + text_w / 2, bx), ay + MEASURE_TICK)
        step = f' data-step="{line.step}"' if line.step is not None else ""
        # une cote suivie : l'étape de l'image où elle est reprise, et sa longueur d'origine
        followed = f' data-at="{line.at}"' if line.at is not None else ""
        reference = f' data-reference="{_n(line.reference)}"' if line.reference is not None else ""
        segment = f"M{_n(ax)},{_n(ay)} L{_n(bx)},{_n(by)} {tick}"
        parts.append(
            f'<g class="sp-measure" data-direction="{line.direction}"{step} data-measure="{line.index}"{followed} data-length="{_n(line.length)}" '
            f'data-material="{html.escape(line.material)}"{reference}>'
            f'<path d="{segment}" fill="none" stroke-width="3.4" stroke-linecap="round" style="stroke:{_SURFACE}"/>'
            f'<path d="{segment}" fill="none" stroke-width="1.3" stroke-linecap="round" style="stroke:{_TEXT}"/>'
            f'<path d="{arrows}" style="fill:{_TEXT}"/>'
            f'<text x="{_n(tx)}" y="{_n(ty)}" text-anchor="{anchor}" font-size="{_n(VALUE_SIZE)}" font-weight="600" '
            f'stroke-width="3.5" stroke-linejoin="round" paint-order="stroke" style="fill:{_TEXT};stroke:{_SURFACE}">{html.escape(text)}</text>'
            "</g>"
        )
        boxes.append(box)
    return parts, boxes


def _anchor_mark(ax: float, ay: float, marker: str) -> str:
    """Le point d'accroche d'une étiquette (``marker`` : un rond sur la couche, un tiret et un losange
    sur l'interface), dans un groupe que le constructeur fait glisser - avec, dessous, la zone où
    l'attraper (:data:`ANCHOR_HIT`), invisible et inerte hors du constructeur."""
    hit = f'<circle class="sp-layer-anchor__hit" cx="{_n(ax)}" cy="{_n(ay)}" r="{_n(ANCHOR_HIT)}" fill="none" pointer-events="none"/>'
    return f'<g class="sp-layer-anchor">{hit}{marker}</g>'


def _leader_points(ax: float, ay: float, elbow: float, tx: float, ty: float, width: float) -> str:
    """The points of the line from a label's anchor ``(ax, ay)`` to its text (left edge ``tx``,
    first line at ``ty``): through the elbow when the text is past it (its automatic place), else
    straight to the nearest side of the text - its right edge when it was moved left of the anchor."""
    if tx - 6 >= elbow:
        return f"{_n(ax)},{_n(ay)} {_n(elbow)},{_n(ay)} {_n(tx - 6)},{_n(ty)}"
    end = tx + width + 6 if tx + width + 6 < ax else tx - 6
    return f"{_n(ax)},{_n(ay)} {_n(end)},{_n(ty)}"


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
    frame_keys: tuple[str, ...] | list[str] | None = None,
    step_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Each frame as the builder shows it: its SVG (layers tagged ``data-layer-index``, the labels
    of ``labels`` drawn on the layers they name, grouped by ``bricks``), its materials and its
    layers - each with the position of the step that created it (``step_index``, ``-1`` for the
    substrate), from the simulation's own provenance (``origins``). A point put by hand
    (:attr:`~.simulation.LayerLabel.anchor`) is in the final structure's frame of reference on every
    frame (:attr:`LayerAnnotation.anchor_bounds`), and neither honoured nor movable before a flip.
    ``frame_keys``: the key of each frame's simulated state (:attr:`~.simulation.SimulationResult.frame_keys`)
    - with them, a frame drawn the same way as before (same state, same labels) is not drawn again
    (:func:`_cached_svg`). ``step_ids``: the id of each step, which a measure followed at later steps
    names them by (:attr:`~.simulation.Measure.also`)."""
    material_colors = {m.name: m.color for m in materials}

    def origins_of(k: int) -> list[int | None]:
        return origins[k] if origins is not None else [None] * len(frames[k].layers)

    # le point d'accroche posé à la main l'est dans le cadre de ce qu'il désigne sur la structure
    # finale, quelle que soit l'image où on le pose : il tombe au même endroit sur toutes - sauf
    # avant un retournement, où il n'est ni suivi ni déplaçable (anchors=False)
    final: dict[int, tuple[float, float, float, float]] = {}
    if labels and frames:
        for annotation in annotations_for(steps or [], declared or {}, labels, origins_of(len(frames) - 1), bricks):
            designated = None if annotation.grouped else _union(frames[-1], annotation.layers)
            if designated is not None and annotation.step is not None:
                final[annotation.step] = designated.bounds
    payload = []
    for k, frame in enumerate(frames):
        frame_origins = origins_of(k)
        annotations = annotations_for(steps or [], declared or {}, labels or {}, frame_origins, bricks, through=k) if labels else []
        annotations = [replace(a, anchor_bounds=final.get(a.step)) if a.step is not None else a for a in annotations]
        flipped_later = any(later.step_kind == "flip" for later in frames[k + 1 :])
        # les cotes d'une étape ne paraissent que sur son image (frames[k] : après l'étape k - 1)
        measured = (labels or {}).get(k - 1) if k > 0 else None
        measures = measure_lines(frame, measured, k - 1) if measured is not None and measured.measures else ()
        # et celles d'étapes d'avant, suivies jusqu'à celle-ci (Measure.also)
        here = step_ids[k - 1] if step_ids and 0 < k <= len(step_ids) else None
        if here is not None and origins is not None and steps:
            followed = (
                followed_measure_line(frames, origins, steps, measure, i, m, k - 1)
                for i, label in sorted((labels or {}).items())
                if i < k - 1
                for m, measure in enumerate(label.measures)
                if here in measure.also
            )
            measures = (*measures, *(line for line in followed if line is not None))
        payload.append(
            {
                "step_index": frame.step_index,
                "step_kind": frame.step_kind,
                "step_name": frame.step_name,
                "svg": _cached_svg(
                    frame_keys[k] if frame_keys and k < len(frame_keys) else None,
                    (frame.step_name, annotations, measures, not flipped_later, sorted(material_colors.items())),
                    lambda: labelled_svg(frame, material_colors, annotations, tag_layers=True, anchors=not flipped_later, measures=measures),
                ),
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


# Le dessin d'une image, gardé sous la clé de son état simulé et ce qui s'y dessine (ses étiquettes,
# les couleurs) : déplacer une étiquette ne redessine que les images où elle paraît - le dessin des
# étiquettes (unions de couches, surfaces) coûte bien plus que la reprise de la simulation, gardée.
MAX_CACHED_SVGS = 512
_svg_cache: OrderedDict[str, str] = OrderedDict()
_svg_cache_lock = threading.Lock()


def _cached_svg(state_key: str | None, drawn: Any, draw: Callable[[], str]) -> str:
    if state_key is None:
        return draw()
    key = hashlib.sha256(f"{state_key}|{drawn!r}".encode()).hexdigest()
    with _svg_cache_lock:
        svg = _svg_cache.get(key)
        if svg is not None:
            _svg_cache.move_to_end(key)
            return svg
    svg = draw()
    with _svg_cache_lock:
        _svg_cache[key] = svg
        while len(_svg_cache) > MAX_CACHED_SVGS:
            _svg_cache.popitem(last=False)
    return svg


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
