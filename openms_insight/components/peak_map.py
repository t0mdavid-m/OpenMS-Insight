"""PeakMap component: a heatmap that can also be drawn in 3D."""

import inspect
from typing import Any

from .heatmap import Heatmap

VIEWS = ("2d", "3d")


class PeakMap(Heatmap):
    """
    A Heatmap whose points can also be drawn in 3D, as stems as high as their
    intensity.

    The toolbar switches between the two drawings. Both show the same points:
    the zoom (``zoom_identifier``), the selection (``interactivity``,
    ``highlight``), the filter and the colours of the toolbar's Color button,
    and the layers apply to either, so a zoom or a click in one is there in the
    other. In 3D the points of the zoomed window are drawn; the toolbar zooms
    in or out around the window's centre, or around the selected point.

    It takes every argument of :class:`Heatmap`, and:

    Args:
        view: The drawing shown first, ``"2d"`` (default) or ``"3d"``.
        z_label: Label of the height axis in 3D. Default: ``intensity_label``,
            else "Intensity".

    Example:
        peak_map = PeakMap(
            cache_id="ms1_map",
            data=peaks,
            x_column="rt",
            y_column="mz",
            intensity_column="intensity",
            interactivity={"spectrum": "scan_id"},
            x_label="Retention time (s)",
            y_label="m/z",
        )
        peak_map(state_manager=state_manager)
    """

    _component_type: str = "peak_map"

    _highlight_intensity = True

    def __init__(self, cache_id: str, *args: Any, view: str = "2d", z_label: str | None = None, **kwargs: Any):
        if view not in VIEWS:
            raise ValueError(f"view must be one of {VIEWS}, not {view!r}")
        self._view = view
        self._z_label = z_label
        super().__init__(cache_id, *args, **kwargs)

    def _get_component_args(self) -> dict[str, Any]:
        args = super()._get_component_args()
        args["view3d"] = True
        args["initialView"] = self._view
        if self._z_label:
            args["zLabel"] = self._z_label
        return args


def _signature() -> inspect.Signature:
    """Heatmap's parameters and PeakMap's own, so code that inspects the
    constructor (which options it takes) sees every one of them."""
    heatmap = inspect.signature(Heatmap.__init__)
    params = list(heatmap.parameters.values())
    keyword = [p for p in params if p.kind is inspect.Parameter.VAR_KEYWORD]
    params = [p for p in params if p.kind is not inspect.Parameter.VAR_KEYWORD]
    own = [
        inspect.Parameter("view", inspect.Parameter.KEYWORD_ONLY, default="2d", annotation=str),
        inspect.Parameter("z_label", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=str | None),
    ]
    positional = [p for p in params if p.kind is not inspect.Parameter.KEYWORD_ONLY]
    keyword_only = [p for p in params if p.kind is inspect.Parameter.KEYWORD_ONLY]
    return heatmap.replace(parameters=[*positional, *keyword_only, *own, *keyword])


PeakMap.__init__.__signature__ = _signature()  # type: ignore[attr-defined]
