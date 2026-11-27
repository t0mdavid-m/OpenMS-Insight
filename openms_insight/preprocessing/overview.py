"""A small raster of a whole heatmap, for the overview shown while it is zoomed.

Each cell holds the highest intensity of the points in it, scaled to 1..255
between the weakest and the strongest cell (0: no point), so the browser can draw it on a canvas without the points.
"""

from __future__ import annotations

import base64
from typing import Any

import numpy as np
import polars as pl

#: Cells across and down; the overview is drawn at this size in pixels.
OVERVIEW_WIDTH = 160
OVERVIEW_HEIGHT = 100


def overview_raster(
    data: pl.DataFrame,
    x_column: str,
    y_column: str,
    intensity_column: str | None = None,
    log_scale: bool = True,
    extent: tuple[list[float], list[float]] | None = None,
    width: int = OVERVIEW_WIDTH,
    height: int = OVERVIEW_HEIGHT,
) -> dict[str, Any] | None:
    """Rasterize ``data`` to ``width`` x ``height`` cells.

    Args:
        data: The points, with numeric x and y columns.
        x_column: Column on the x axis.
        y_column: Column on the y axis.
        intensity_column: Column whose highest value colors a cell (None:
            every cell holding a point is drawn at full strength).
        log_scale: Scale intensities by log10, as the plot does.
        extent: ``([x_lo, x_hi], [y_lo, y_hi])`` the raster covers (default:
            the range of the points).
        width: Cells across.
        height: Cells down.

    Returns:
        ``{"x": [lo, hi], "y": [lo, hi], "width", "height", "cells"}`` with the
        cells as base64 of ``width * height`` bytes, row by row from the lowest
        y up; None when no point has finite coordinates.
    """
    if data.is_empty():
        return None
    x = data[x_column].cast(pl.Float64).to_numpy()
    y = data[y_column].cast(pl.Float64).to_numpy()
    if intensity_column and intensity_column in data.columns:
        z = data[intensity_column].cast(pl.Float64).fill_null(0.0).to_numpy()
    else:
        z = np.ones(len(x))
    keep = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x, y, z = x[keep], y[keep], z[keep]
    if not len(x):
        return None
    if extent is None:
        x_lo, x_hi = float(x.min()), float(x.max())
        y_lo, y_hi = float(y.min()), float(y.max())
    else:
        (x_lo, x_hi), (y_lo, y_hi) = extent
    # A single value spreads over a cell, not a line
    if x_hi <= x_lo:
        x_lo, x_hi = x_lo - 0.5, x_lo + 0.5
    if y_hi <= y_lo:
        y_lo, y_hi = y_lo - 0.5, y_lo + 0.5
    ix = np.clip(((x - x_lo) / (x_hi - x_lo) * width).astype(np.int64), 0, width - 1)
    iy = np.clip(((y - y_lo) / (y_hi - y_lo) * height).astype(np.int64), 0, height - 1)
    # As the plot colors: log10 of the intensity (0 for none), else the value
    if log_scale:
        values = np.where(z > 0, np.log10(np.where(z > 0, z, 1.0)), 0.0)
    else:
        values = z
    grid = np.full(width * height, -np.inf)
    np.maximum.at(grid, iy * width + ix, values)
    filled = np.isfinite(grid)
    cells = np.zeros(width * height, dtype=np.uint8)
    # Filled cells span 1..255 from the weakest to the strongest cell
    lo, hi = grid[filled].min(), grid[filled].max()
    scaled = (grid[filled] - lo) / (hi - lo) if hi > lo else np.ones(int(filled.sum()))
    cells[filled] = (1 + np.round(scaled * 254)).astype(np.uint8)
    return {
        "x": [x_lo, x_hi],
        "y": [y_lo, y_hi],
        "width": width,
        "height": height,
        "cells": base64.b64encode(cells.tobytes()).decode("ascii"),
    }
