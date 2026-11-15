"""The "Relative intensity" switch of LinePlot.

A button in the plot's toolbar shows the intensities as a percentage of the
spectrum's highest peak, and switches back to absolute values.
``relative_intensity=True`` starts in relative mode. Like ``keep_zoom`` it is
a render-time argument, never part of the cache configuration.
"""

from typing import Any


def validate_relative_intensity(relative_intensity: Any) -> bool:
    """Check ``relative_intensity`` is a bool and return it."""
    if not isinstance(relative_intensity, bool):
        raise ValueError(
            f"relative_intensity must be True or False, got {relative_intensity!r}"
        )
    return relative_intensity


def relative_intensity_args(relative_intensity: bool) -> dict[str, Any]:
    """The Vue argument: whether the intensities start relative."""
    return {"relativeIntensity": relative_intensity}
