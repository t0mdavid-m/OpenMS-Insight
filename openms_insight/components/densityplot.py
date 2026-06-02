"""DensityPlot component — dual KDE (target vs decoy) score distribution plot.

Port of FLASHApp's ``FDRPlotly`` ("Score Distribution Plot" / "FDR Plot"). Static,
informational plot with no cross-component linking. Computes a 200-point Gaussian
KDE for a target series and a decoy series and renders them as two named
``lines+markers`` scatter traces (Target green / Decoy red).

The KDE preprocessing reproduces FLASHApp's ``fdr_density_distribution`` exactly for
both workflows:

- FLASHDeconv (``deconv.py``): targets are rows with ``TargetDecoyType == 0``,
  decoys are rows with ``TargetDecoyType > 0``; the score column is ``Qscore``.
- FLASHTnT (``tnt.py``): rows are pre-filtered to ``ProteoformLevelQvalue > 0``;
  targets are accessions NOT starting with ``DECOY_``, decoys are accessions
  starting with ``DECOY_``; the score column is ``ProteoformLevelQvalue``.

On BOTH paths the x-axis label is the literal ``"QScore"`` and the series names are
``"Target QScores"`` / ``"Decoy QScores"`` (FLASHApp parity — see STRATEGY §6.3).
"""

from typing import Any, Dict, List, Optional

import numpy as np
import polars as pl

from ..core.base import BaseComponent
from ..core.registry import register_component

# Number of grid points for the KDE — fixed by FLASHApp parity (np.linspace(min,max,200)).
KDE_GRID_POINTS = 200


@register_component("densityplot")
class DensityPlot(BaseComponent):
    """
    Static dual-KDE density plot (target vs decoy score distributions).

    Two construction modes:

    1. **Raw mode** (recommended — centralizes the 200-point KDE): pass ``data`` (a
       LazyFrame of identification/deconvolution rows) plus ``mode`` (``"deconv"`` or
       ``"tnt"``). ``_preprocess`` splits target/decoy by the workflow rule and
       computes the KDE for each.

    2. **Precomputed mode**: pass ``density_target`` and/or ``density_decoy``
       LazyFrames that already contain ``x``/``y`` columns (200 rows each, sorted by
       ``x`` ascending). This mirrors FLASHApp's cached ``density_target`` /
       ``density_decoy`` payloads.

    The component is static: no ``filters``, no ``interactivity``,
    ``get_state_dependencies() == []``. Selecting scans/masses elsewhere never
    recomputes or alters this plot.

    Example (raw, Deconv):
        density = DensityPlot(
            cache_id="exp1_fdr",
            data=fdr_rows,            # has TargetDecoyType + Qscore columns
            mode="deconv",
            title="FDR Plot",
        )
        density(state_manager=state)

    Example (raw, TnT):
        density = DensityPlot(
            cache_id="exp1_id_fdr",
            data=protein_rows,       # has accession + ProteoformLevelQvalue
            mode="tnt",
            title="FDR Plot",
        )

    Example (precomputed):
        density = DensityPlot(
            cache_id="exp1_fdr",
            density_target=target_xy,   # columns x, y
            density_decoy=decoy_xy,     # columns x, y (may be empty)
            title="FDR Plot",
        )
    """

    _component_type: str = "densityplot"

    # FLASHApp literals — preserved on BOTH Deconv and TnT paths.
    DEFAULT_X_LABEL = "QScore"
    DEFAULT_Y_LABEL = "Density"
    DEFAULT_TARGET_NAME = "Target QScores"
    DEFAULT_DECOY_NAME = "Decoy QScores"
    DEFAULT_TARGET_COLOR = "green"
    DEFAULT_DECOY_COLOR = "red"

    def __init__(
        self,
        cache_id: str,
        # Raw mode
        data: Optional[pl.LazyFrame] = None,
        data_path: Optional[str] = None,
        mode: Optional[str] = None,
        score_column: Optional[str] = None,
        td_type_column: str = "TargetDecoyType",
        accession_column: str = "accession",
        # Precomputed mode
        density_target: Optional[pl.LazyFrame] = None,
        density_decoy: Optional[pl.LazyFrame] = None,
        # Cache
        cache_path: str = ".",
        regenerate_cache: bool = False,
        # Schema of the {x,y} frames
        x_column: str = "x",
        y_column: str = "y",
        # Labels / visuals
        title: Optional[str] = "FDR Plot",
        x_label: Optional[str] = None,
        y_label: Optional[str] = None,
        target_name: Optional[str] = None,
        decoy_name: Optional[str] = None,
        target_color: Optional[str] = None,
        decoy_color: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize the DensityPlot component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
                Use a distinct cache_id per experiment so caches don't collide.
            data: LazyFrame of raw rows (raw mode). Mutually exclusive with
                density_target/density_decoy and with data_path.
            data_path: Path to a parquet file with raw rows (raw mode, subprocess).
            mode: Workflow grouping — ``"deconv"`` (TargetDecoyType + Qscore) or
                ``"tnt"`` (DECOY_ accession + ProteoformLevelQvalue>0). Required in
                raw mode.
            score_column: Score column to run the KDE over. Defaults to ``Qscore``
                for deconv and ``ProteoformLevelQvalue`` for tnt.
            td_type_column: Target/decoy type column for deconv (default
                ``TargetDecoyType``; target==0, decoy>0).
            accession_column: Accession column for tnt (default ``accession``;
                decoy rows start with ``DECOY_``).
            density_target: Precomputed target {x,y} LazyFrame (precomputed mode).
            density_decoy: Precomputed decoy {x,y} LazyFrame (precomputed mode; may
                be empty / 0 rows).
            cache_path: Base path for cache storage. Default "." (current dir).
            regenerate_cache: If True, regenerate cache even if valid cache exists.
            x_column: Column name for x values in the {x,y} frames (default "x").
            y_column: Column name for y (density) values (default "y").
            title: Plot title (bold HTML in Vue). Default "FDR Plot".
            x_label: X-axis label. Default literal "QScore".
            y_label: Y-axis label. Default "Density".
            target_name: Target trace legend name. Default "Target QScores".
            decoy_name: Decoy trace legend name. Default "Decoy QScores".
            target_color: Target line/marker color. Default "green".
            decoy_color: Decoy line/marker color. Default "red".
            **kwargs: Additional configuration options.
        """
        # DensityPlot is static — strip any filter/interactivity kwargs that a
        # subprocess re-instantiation might forward, so super().__init__ never
        # receives them twice and the component stays cross-link free.
        kwargs.pop("filters", None)
        kwargs.pop("filter_defaults", None)
        kwargs.pop("interactivity", None)

        self._mode = mode
        self._score_column = score_column
        self._td_type_column = td_type_column
        self._accession_column = accession_column

        self._x_column = x_column
        self._y_column = y_column

        self._title = title
        self._x_label = x_label or self.DEFAULT_X_LABEL
        self._y_label = y_label or self.DEFAULT_Y_LABEL
        self._target_name = target_name or self.DEFAULT_TARGET_NAME
        self._decoy_name = decoy_name or self.DEFAULT_DECOY_NAME
        self._target_color = target_color or self.DEFAULT_TARGET_COLOR
        self._decoy_color = decoy_color or self.DEFAULT_DECOY_COLOR

        # Precomputed-mode inputs (held until _preprocess).
        self._precomputed_target = density_target
        self._precomputed_decoy = density_decoy
        self._is_precomputed = density_target is not None or density_decoy is not None

        if self._is_precomputed and (data is not None or data_path is not None):
            raise ValueError(
                "Provide either raw data (data=/data_path=) or precomputed "
                "density_target/density_decoy, not both."
            )
        if (
            not self._is_precomputed
            and data is None
            and data_path is None
            and (regenerate_cache or mode is not None)
        ):
            raise ValueError(
                "Raw mode requires data= or data_path= together with mode=."
            )

        # In precomputed mode the base class still needs a `data` sentinel to enter
        # creation mode. Use the target frame (fall back to decoy) so has_data=True.
        base_data = data
        if self._is_precomputed:
            base_data = density_target if density_target is not None else density_decoy

        super().__init__(
            cache_id=cache_id,
            data=base_data,
            data_path=data_path,
            filters=None,
            filter_defaults=None,
            interactivity=None,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            mode=mode,
            score_column=score_column,
            td_type_column=td_type_column,
            accession_column=accession_column,
            x_column=x_column,
            y_column=y_column,
            title=title,
            x_label=x_label,
            y_label=y_label,
            target_name=target_name,
            decoy_name=decoy_name,
            target_color=target_color,
            decoy_color=decoy_color,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    # KDE                                                                #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _compute_kde(scores: np.ndarray) -> pl.DataFrame:
        """Compute a 200-point Gaussian KDE over ``scores``.

        Reproduces FLASHApp's ``fdr_density_distribution`` exactly:
        ``x = np.linspace(min, max, 200)``; ``y = gaussian_kde(scores)(x)``.

        Empty input (or input that cannot form a KDE, e.g. <2 points / zero
        variance) yields an empty ``{x, y}`` frame (0 rows) rather than raising —
        this guards the empty-decoy (and empty-target) edge case.
        """
        from scipy.stats import gaussian_kde

        scores = np.asarray(scores, dtype=float)
        scores = scores[~np.isnan(scores)]

        if scores.size == 0:
            return pl.DataFrame(
                {"x": [], "y": []},
                schema={"x": pl.Float64, "y": pl.Float64},
            )

        x = np.linspace(float(scores.min()), float(scores.max()), KDE_GRID_POINTS)
        try:
            kde = gaussian_kde(scores)
            y = kde(x)
        except (np.linalg.LinAlgError, ValueError):
            # Degenerate input (single unique value / singular covariance):
            # cannot build a KDE — return an empty frame rather than error.
            return pl.DataFrame(
                {"x": [], "y": []},
                schema={"x": pl.Float64, "y": pl.Float64},
            )

        return pl.DataFrame({"x": x, "y": np.asarray(y, dtype=float)})

    def _split_scores(self) -> tuple[np.ndarray, np.ndarray]:
        """Split raw data into (target_scores, decoy_scores) per workflow mode."""
        df = self._raw_data.collect()

        if self._mode == "deconv":
            score_col = self._score_column or "Qscore"
            td_col = self._td_type_column
            target = (
                df.filter(pl.col(td_col) == 0)
                .get_column(score_col)
                .drop_nulls()
                .to_numpy()
            )
            decoy = (
                df.filter(pl.col(td_col) > 0)
                .get_column(score_col)
                .drop_nulls()
                .to_numpy()
            )
            return target, decoy

        if self._mode == "tnt":
            score_col = self._score_column or "ProteoformLevelQvalue"
            acc_col = self._accession_column
            # Pre-filter ProteoformLevelQvalue > 0 (the actual score column).
            df = df.filter(pl.col(score_col) > 0)
            is_decoy = pl.col(acc_col).str.starts_with("DECOY_")
            target = df.filter(~is_decoy).get_column(score_col).drop_nulls().to_numpy()
            decoy = df.filter(is_decoy).get_column(score_col).drop_nulls().to_numpy()
            return target, decoy

        raise ValueError(
            f"Unknown mode '{self._mode}'. Use 'deconv' or 'tnt', or pass "
            f"precomputed density_target/density_decoy."
        )

    @staticmethod
    def _normalize_xy(
        frame: Optional[pl.LazyFrame], x_col: str, y_col: str
    ) -> pl.DataFrame:
        """Collect a precomputed frame and project/rename to canonical x,y columns."""
        if frame is None:
            return pl.DataFrame(
                {"x": [], "y": []}, schema={"x": pl.Float64, "y": pl.Float64}
            )
        df = frame.collect() if isinstance(frame, pl.LazyFrame) else frame
        if df.height == 0:
            return pl.DataFrame(
                {"x": [], "y": []}, schema={"x": pl.Float64, "y": pl.Float64}
            )
        return df.select(
            pl.col(x_col).cast(pl.Float64).alias("x"),
            pl.col(y_col).cast(pl.Float64).alias("y"),
        )

    # ------------------------------------------------------------------ #
    # BaseComponent hooks                                                #
    # ------------------------------------------------------------------ #
    def _validate_mappings(self) -> None:
        """Static component — only validate that required columns exist."""
        if self._raw_data is None:
            return  # Reconstruction from cache

        if self._is_precomputed:
            for frame, label in (
                (self._precomputed_target, "density_target"),
                (self._precomputed_decoy, "density_decoy"),
            ):
                if frame is None:
                    continue
                names = frame.collect_schema().names()
                for col in (self._x_column, self._y_column):
                    if col not in names:
                        raise ValueError(
                            f"{label} is missing column '{col}'. "
                            f"Available columns: {names}"
                        )
            return

        # Raw mode: validate the grouping/score columns exist.
        names = self._raw_data.collect_schema().names()
        if self._mode == "deconv":
            required = [self._score_column or "Qscore", self._td_type_column]
        elif self._mode == "tnt":
            required = [
                self._score_column or "ProteoformLevelQvalue",
                self._accession_column,
            ]
        else:
            raise ValueError(f"Unknown mode '{self._mode}'. Use 'deconv' or 'tnt'.")
        missing = [c for c in required if c not in names]
        if missing:
            raise ValueError(
                f"Missing required columns for mode '{self._mode}': {missing}. "
                f"Available columns: {names}"
            )

    def _preprocess(self) -> None:
        """Compute (or normalize) the two {x,y} density frames and cache them."""
        if self._is_precomputed:
            target_df = self._normalize_xy(
                self._precomputed_target, self._x_column, self._y_column
            )
            decoy_df = self._normalize_xy(
                self._precomputed_decoy, self._x_column, self._y_column
            )
        else:
            target_scores, decoy_scores = self._split_scores()
            target_df = self._compute_kde(target_scores)
            decoy_df = self._compute_kde(decoy_scores)

        # Release any held precomputed frames.
        self._precomputed_target = None
        self._precomputed_decoy = None

        self._preprocessed_data["densityTarget"] = target_df
        self._preprocessed_data["densityDecoy"] = decoy_df

    def _get_vue_component_name(self) -> str:
        return "PlotlyDensity"

    def _get_data_key(self) -> str:
        return "densityTarget"

    def get_state_dependencies(self) -> List[str]:
        """Static plot — no state dependencies. Never recomputes on selections."""
        return []

    def get_filters_mapping(self) -> Dict[str, str]:
        return {}

    def get_interactivity_mapping(self) -> Dict[str, str]:
        return {}

    def _get_cache_config(self) -> Dict[str, Any]:
        return {
            "mode": self._mode,
            "score_column": self._score_column,
            "td_type_column": self._td_type_column,
            "accession_column": self._accession_column,
            "x_column": self._x_column,
            "y_column": self._y_column,
            "title": self._title,
            "x_label": self._x_label,
            "y_label": self._y_label,
            "target_name": self._target_name,
            "decoy_name": self._decoy_name,
            "target_color": self._target_color,
            "decoy_color": self._decoy_color,
        }

    def _restore_cache_config(self, config: Dict[str, Any]) -> None:
        self._mode = config.get("mode")
        self._score_column = config.get("score_column")
        self._td_type_column = config.get("td_type_column", "TargetDecoyType")
        self._accession_column = config.get("accession_column", "accession")
        self._x_column = config.get("x_column", "x")
        self._y_column = config.get("y_column", "y")
        self._title = config.get("title", "FDR Plot")
        self._x_label = config.get("x_label", self.DEFAULT_X_LABEL)
        self._y_label = config.get("y_label", self.DEFAULT_Y_LABEL)
        self._target_name = config.get("target_name", self.DEFAULT_TARGET_NAME)
        self._decoy_name = config.get("decoy_name", self.DEFAULT_DECOY_NAME)
        self._target_color = config.get("target_color", self.DEFAULT_TARGET_COLOR)
        self._decoy_color = config.get("decoy_color", self.DEFAULT_DECOY_COLOR)
        # Precomputed inputs are consumed during preprocessing; reset.
        self._precomputed_target = None
        self._precomputed_decoy = None
        self._is_precomputed = False

    def _prepare_vue_data(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Return both density frames. State is ignored — this plot is static."""
        from ..preprocessing.filtering import compute_dataframe_hash

        target = self._preprocessed_data.get("densityTarget")
        decoy = self._preprocessed_data.get("densityDecoy")

        if isinstance(target, pl.LazyFrame):
            target = target.collect()
        if isinstance(decoy, pl.LazyFrame):
            decoy = decoy.collect()
        if target is None:
            target = pl.DataFrame(
                {"x": [], "y": []}, schema={"x": pl.Float64, "y": pl.Float64}
            )
        if decoy is None:
            decoy = pl.DataFrame(
                {"x": [], "y": []}, schema={"x": pl.Float64, "y": pl.Float64}
            )

        data_hash = f"{compute_dataframe_hash(target)}_{compute_dataframe_hash(decoy)}"

        return {
            "densityTarget": target.to_pandas(),
            "densityDecoy": decoy.to_pandas(),
            "_hash": data_hash,
        }

    def _get_component_args(self) -> Dict[str, Any]:
        return {
            "componentType": self._get_vue_component_name(),
            "title": self._title or "",
            "xLabel": self._x_label,
            "yLabel": self._y_label,
            "xColumn": self._x_column,
            "yColumn": self._y_column,
            "targetName": self._target_name,
            "decoyName": self._decoy_name,
            "targetColor": self._target_color,
            "decoyColor": self._decoy_color,
            # Static plot — no interactivity.
            "interactivity": {},
        }
