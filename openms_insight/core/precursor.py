"""The precursor of a fragment spectrum, marked on its m/z axis.

LinePlot and MirrorPlot take ``precursor_mz`` and ``precursor_charge``: a
dashed line through the spectrum at the precursor's m/z with "precursor 2+"
at its top, drawn whether or not a peak is there, so unfragmented precursor
and its neutral losses are easy to tell apart from fragment ions. In a
MirrorPlot the mark is on the top (measured) half only. It is part of the
image download.

The precursor belongs to the spectrum shown, which a page knows when it draws
the plot, so these are render-time arguments kept on the component and never
part of its cache configuration: setting them never rebuilds a cache.
"""

import math
from typing import Any


def validate_precursor(mz: Any, charge: Any) -> tuple[float | None, int]:
    """Check ``precursor_mz`` and ``precursor_charge`` and return them.

    ``mz`` is None (no mark) or a positive finite number; ``charge`` is None or
    a non-negative int, 0 or None meaning the charge is unknown.
    """
    if mz is not None:
        if isinstance(mz, bool) or not isinstance(mz, (int, float)):
            raise ValueError(f"precursor_mz must be a number or None, got {mz!r}")
        if not math.isfinite(mz) or mz <= 0:
            raise ValueError(f"precursor_mz must be a positive m/z, got {mz!r}")
        mz = float(mz)
    if charge is None:
        charge = 0
    elif isinstance(charge, bool) or not isinstance(charge, int) or charge < 0:
        raise ValueError(
            f"precursor_charge must be a non-negative int or None, got {charge!r}"
        )
    return mz, int(charge)


def precursor_args(mz: float | None, charge: int) -> dict[str, Any]:
    """Component args for the view: ``precursor`` is None when nothing is marked."""
    return {"precursor": None if mz is None else {"mz": mz, "charge": charge}}
