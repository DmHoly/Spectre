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

import html
import itertools
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union
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
    ``offset``); ``offset``: how far its text was moved by hand from its automatic place."""

    title: str
    lines: tuple[str, ...]
    layers: tuple[int, ...]
    grouped: bool = False
    line_layers: tuple[tuple[int, ...], ...] = ()
    interface: bool = False
    after: tuple[int, ...] = ()
    step: int | None = None
    offset: tuple[float, float] | None = None


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
) -> list[LayerAnnotation]:
    """The labels of a drawing whose layers were created by the steps ``origins`` names (one
    position per layer of ``frame.layers``, :data:`SUBSTRATE_ORIGIN` or ``None`` for the
    substrate) - one per labelled step that has a layer in it, in the order of the steps. The
    labelled steps of one brick (``bricks``, see :func:`~.simulation.grouped_labels`) share the
    brick's label instead, one line per step that has a layer in the drawing. A labelled step that
    creates no layer (:data:`~.simulation.INTERFACE_STEP_KINDS`) is an interface mark of its own,
    never grouped: between the layers made before it (the substrate among them) and those made
    after it."""
    marks = {index: label for index, label in labels.items() if 0 <= index < len(steps) and steps[index].kind in INTERFACE_STEP_KINDS}
    labelled = {index: label for index, label in labels.items() if 0 <= index < len(steps) and index not in marks}
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
        ordered.append((index, LayerAnnotation(title, lines, before, interface=True, after=after, step=index, offset=marks[index].offset)))
    for index in sorted(labelled):
        layers = layers_of({index})
        if index in in_group or not layers:
            continue
        title, lines = label_text(steps[index], declared.get(index, []), labelled[index])
        ordered.append((index, LayerAnnotation(title, lines, layers, step=index, offset=labelled[index].offset)))
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


def _union(frame: Frame, layers: tuple[int, ...]) -> Any:
    shapes = [shape for k in layers if k < len(frame.layers) for shape in [_shape(frame.layers[k].rings())] if shape is not None and not shape.is_empty]
    return unary_union(shapes) if shapes else None


# où chercher la surface d'une marque d'interface, en fraction de la largeur : à droite d'abord, du
# côté des étiquettes
_INTERFACE_SAMPLES = (0.92, 0.85, 0.75, 0.65, 0.5, 0.35, 0.2, 0.08)


def _interface_anchor(frame: Frame, before: tuple[int, ...], after: tuple[int, ...]) -> tuple[float, float] | None:
    """A point on the surface a step that made no layer left behind: the top of the layers made
    before it (``before``), where a layer made after it (``after``) lies on it - the interface -,
    else where that surface is bare; towards the right edge, like the labels."""
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
        top = crossing.bounds[3]
        if above is None or above.distance(Point(x, top)) <= tolerance:
            return x, top
        bare = bare or (x, top)
    return bare


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
    marks_at: list[tuple[float, float]] = []
    for annotation in annotations:
        bracket = None
        rings_by_layer = [frame.layers[k].rings() for k in annotation.layers if k < len(frame.layers)]
        candidates = [(rings, _shape(rings)) for rings in rings_by_layer]
        candidates = [(rings, shape) for rings, shape in candidates if shape is not None and not shape.is_empty]
        if not candidates:
            continue
        if annotation.interface:
            point = _interface_anchor(frame, annotation.layers, annotation.after)
            if point is None:
                continue
            anchor = to_svg(*point)
            # deux étapes sur la même interface (une gravure puis un nettoyage) : côte à côte
            while any(abs(anchor[0] - x) < INTERFACE_TICK and abs(anchor[1] - y) < INTERFACE_TICK for x, y in marks_at):
                anchor = (anchor[0] - 2.4 * INTERFACE_TICK, anchor[1])
            marks_at.append(anchor)
        elif annotation.grouped:
            # une accolade sur toute la hauteur des couches de la brique (jamais plus fine qu'un trait lisible)
            _min_x, min_y, _max_x, max_y = unary_union([shape for _rings, shape in candidates]).bounds
            top, bottom = to_svg(0, max_y)[1], to_svg(0, min_y)[1]
            middle = (top + bottom) / 2
            half = max((bottom - top) / 2, BRACKET_MIN_HEIGHT / 2)
            bracket = (middle - half, middle + half)
            anchor = (bracket_x, middle)  # x : au bout de l'accolade, selon sa colonne (plus bas)
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
            }
        )
    if not blocks:
        return base
    columns = _bracket_columns([b["bracket"] for b in blocks])
    for block, column in zip(blocks, columns):
        if column is not None:
            block["bracket_x"] = bracket_x + column * BRACKET_COLUMN
            block["anchor"] = (block["bracket_x"] + BRACKET_DEPTH + BRACKET_TIP, block["anchor"][1])
    extra = max([c for c in columns if c is not None], default=0) * BRACKET_COLUMN
    # le coude des traits : au-delà de la dernière colonne d'accolades, qu'ils croisent à angle droit
    elbow = bracket_x + extra + BRACKET_DEPTH + BRACKET_TIP if any(c is not None for c in columns) else PAD + sw + 8
    blocks.sort(key=lambda b: b["anchor"][1])
    tops = _place(
        [b["anchor"][1] - TITLE_SIZE * LINE_HEIGHT / 2 for b in blocks], [b["height"] for b in blocks], PAD, PAD + sh
    )
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
    width, height = max_x - min_x, max_y - min_y
    bare = f"0 0 {_n(PAD + sw + PAD)} {_n(PAD + sh + PAD)}"

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
            mark = (
                f'<polyline points="{points}" class="sp-layer-leader" fill="none" stroke-width="1.2" stroke-dasharray="4 3" style="stroke:{_TEXT_SOFT}"/>'
                f'<path d="M{_n(ax - INTERFACE_TICK)},{_n(ay)} H{_n(ax + INTERFACE_TICK)}" stroke-width="2" stroke-linecap="round" style="stroke:{_TEXT}"/>'
                f'<path d="M{_n(ax)},{_n(ay - r)} L{_n(ax + r)},{_n(ay)} L{_n(ax)},{_n(ay + r)} L{_n(ax - r)},{_n(ay)} Z" stroke-width="1.4" style="fill:{_SURFACE};stroke:{_TEXT}"/>'
            )
        else:
            mark = (
                f'<polyline points="{points}" class="sp-layer-leader" fill="none" stroke-width="1.2" style="stroke:{_TEXT_SOFT}"/>'
                f'<circle cx="{_n(ax)}" cy="{_n(ay)}" r="3.2" stroke-width="1.4" style="fill:{_TEXT};stroke:{_SURFACE}"/>'
            )
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
        # data-anchor, data-elbow, data-width : de quoi redessiner le trait pendant qu'on déplace le
        # texte à la souris (constructeur, label-drag.js)
        parts.append(
            f'<g class="sp-layer-label" data-top="{_n(block_top)}" data-height="{_n(block["height"])}"{grouped}{step}{moved} '
            f'data-anchor="{_n(ax)} {_n(ay)}" data-elbow="{_n(elbow)}" data-width="{_n(block["width"])}">'
            + mark
            + f'<g class="sp-layer-label__text">{"".join(texts)}</g>'
            + "</g>"
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_n(min_x)} {_n(min_y)} {_n(width)} {_n(height)}" width="{_n(width)}" height="{_n(height)}" '
        f'class="sp-labelled-structure" data-bare-viewbox="{bare}">'
        f'<svg x="{_n(PAD)}" y="{_n(PAD)}" width="{_n(sw)}" height="{_n(sh)}" viewBox="{view.group(1) if view else "0 0 1 1"}">{inner}</svg>'
        f'<g class="sp-layer-labels" style="font-family:{_FONT}">{"".join(parts)}</g>'
        "</svg>"
    )


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
