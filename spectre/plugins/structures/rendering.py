"""SVG of a structure, always drawn by StructureForge (``structureforge.presentation.svg.frame_to_svg``):
the simulated frames the builder previews, and a committed structure redrawn from its stored,
already-flattened layers.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from structureforge.adapters.follow_adapter import ProcessStructure
from structureforge.core.materials import MaterialLibrary
from structureforge.presentation.svg import frame_to_svg
from structureforge.process.simulate import Frame


_PATH_TAG_RE = re.compile(r"<path ")


def _tag_layer_indices(svg: str) -> str:
    """Insert ``data-layer-index="{k}"`` into the k-th ``<path `` tag of ``svg`` (0-based, in
    order of appearance) - ``frame_to_svg`` (external, unmodifiable) draws exactly one path per
    layer with a non-empty ``rings()``, in ``frame.layers`` order, so index ``k`` here lines up
    with ``frames_payload``'s own ``"layers"`` list (same filter, same order).
    """
    counter = itertools.count()
    return _PATH_TAG_RE.sub(lambda _m: f'<path data-layer-index="{next(counter)}" ', svg)


def frames_payload(frames: list[Frame], materials: MaterialLibrary) -> dict[str, Any]:
    material_colors = {m.name: m.color for m in materials}
    return {
        "frames": [
            {
                "step_index": frame.step_index,
                "step_kind": frame.step_kind,
                "step_name": frame.step_name,
                "svg": _tag_layer_indices(frame_to_svg(frame, material_colors)),
                # only the materials this particular frame actually shows - material_colors below
                # is the whole library (40+ entries), which would make a poor legend on its own.
                "materials": sorted({layer.material for layer in frame.layers}),
                # same order/filter as the SVG's paths (see _tag_layer_indices) - index k here is
                # the layer behind the k-th <path data-layer-index="k">.
                "layers": [
                    {
                        "material": layer.material,
                        "provenance": layer.provenance.model_dump(mode="json") if layer.provenance else None,
                    }
                    for layer in frame.layers
                    if layer.rings()
                ],
            }
            for frame in frames
        ],
        "material_colors": material_colors,
    }


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


def svg_for_process_structure(process_structure: ProcessStructure, material_colors: dict[str, str]) -> str:
    frame = Frame(
        step_index=0,
        step_kind="structure",
        step_name="structure",
        layers=[_RenderableLayer(layer.material, layer.rings) for layer in process_structure.layers],
        domain_width_nm=process_structure.domain_width_nm,
    )
    return frame_to_svg(frame, material_colors)
