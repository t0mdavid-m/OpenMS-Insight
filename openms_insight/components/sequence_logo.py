"""Sequence logo: the residues of aligned sequences, position by position."""

from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.image_format import image_format_args, validate_image_format
from ..core.multi_select import filter_selection
from ..core.registry import register_component
from ..core.sequence_logo import (
    UNITS,
    default_colors,
    logo_frame,
    max_height,
    normalize_alphabet,
    normalize_background,
)
from ..preprocessing.filtering import compute_dataframe_hash

#: What a click on a letter can set: its position (0-based), the position's
#: label, or the residue.
CLICK_FIELDS = ("position", "label", "residue")


@register_component("sequence_logo")
class SequenceLogo(BaseComponent):
    """
    Sequence logo of aligned sequences of equal length.

    Each position is a stack of the residues found there, each letter as high
    as its share of the position times the position's information content in
    bits against a background (``units="bits"``), or as its frequency
    (``units="probability"``). The most frequent residue is on top. Typical
    uses: the residues around cleavage sites (P4..P4'), motifs around
    modification sites, conserved positions of peptides or tags.

    Data has one row per sequence (``sequence_column``), optionally weighted
    (``weight_column``, e.g. a spectral count). Characters outside the
    alphabet (gaps ``-``, ``X``) are not counted. ``filters`` narrow the rows
    to a selection (another logo per protease, sample or group), and
    ``interactivity`` maps identifiers to ``"position"``, ``"label"`` or
    ``"residue"``: clicking a letter sets them, and the clicked position is
    highlighted while its identifier holds it.

    Example:
        logo = SequenceLogo(
            cache_id="cleavage_logo",
            data=sites,  # one row per cleavage site: window "AKLR|GVEA" as "AKLRGVEA"
            sequence_column="window",
            position_labels=["P4", "P3", "P2", "P1", "P1'", "P2'", "P3'", "P4'"],
            filters={"protease": "protease"},
            interactivity={"logo_residue": "residue"},
            title="Cleavage sites",
        )
        logo(key="logo", state_manager=state_manager, height=300)
    """

    _component_type: str = "sequence_logo"

    def __init__(
        self,
        cache_id: str,
        data: pl.LazyFrame | None = None,
        data_path: str | None = None,
        filters: dict[str, str] | None = None,
        filter_defaults: dict[str, Any] | None = None,
        interactivity: dict[str, str] | None = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        sequence_column: str = "sequence",
        weight_column: str | None = None,
        alphabet: str | None = "protein",
        background: str | dict[str, float] | None = "uniform",
        units: str = "bits",
        position_labels: list[str] | None = None,
        first_position: int = 1,
        colors: dict[str, str] | None = None,
        title: str | None = None,
        y_label: str | None = None,
        image_format: str | None = None,
        **kwargs,
    ):
        """
        Initialize the SequenceLogo component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame, one row per aligned sequence.
            data_path: Path to a parquet file with the data.
            filters: Mapping of identifier names to column names; the logo is
                computed from the rows matching the selections.
            filter_defaults: Default values for filters when state is None.
            interactivity: Mapping of identifier names to ``"position"``
                (0-based), ``"label"`` or ``"residue"``, set by a click on a
                letter.
            cache_path: Base path for cache storage.
            regenerate_cache: Rebuild the cache even if a matching one exists.
            sequence_column: Column with the sequences.
            weight_column: Column weighting each sequence (default: 1 each).
            alphabet: ``"protein"`` (the 20 amino acids), ``"dna"``, ``"rna"``
                or the residues as a string.
            background: ``"uniform"`` over the alphabet, or the frequency of
                each residue (e.g. of the proteome searched), normalised to 1.
                Only used with ``units="bits"``.
            units: ``"bits"`` (information content) or ``"probability"``.
            position_labels: Name of each position on the x axis (default:
                ``first_position``, ``first_position + 1``, ...).
            first_position: Number of the first position when there are no
                labels.
            colors: Colour per residue, over the defaults (amino acids by
                chemistry, nucleotides A/C/G/T).
            title: Title above the logo.
            y_label: Y-axis label (default: "Bits" or "Probability").
            image_format: Format of the image download: 'svg', 'png', 'jpeg'
                or 'webp'. None follows ``openms_insight.set_image_format()``.
                Render-time only.
            **kwargs: Additional configuration options.
        """
        if units not in UNITS:
            raise ValueError(f"units must be one of {UNITS}, got {units!r}")
        self._sequence_column = sequence_column
        self._weight_column = weight_column
        self._alphabet = normalize_alphabet(alphabet)
        self._background = normalize_background(background, self._alphabet)
        self._units = units
        self._position_labels = (
            [str(label) for label in position_labels] if position_labels else None
        )
        self._first_position = int(first_position)
        self._colors = {**default_colors(self._alphabet), **dict(colors or {})}
        self._title = title
        self._y_label = y_label
        self._image_format = validate_image_format(image_format, allow_none=True)
        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            sequence_column=sequence_column,
            weight_column=weight_column,
            alphabet=self._alphabet,
            background=self._background,
            units=units,
            position_labels=self._position_labels,
            first_position=first_position,
            colors=self._colors,
            title=title,
            y_label=y_label,
            **kwargs,
        )

    def _validate_mappings(self) -> None:
        """Filters name data columns; interactivity names the logo's own fields."""
        for identifier, field in self._interactivity.items():
            if field not in CLICK_FIELDS:
                raise ValueError(
                    f"interactivity of '{identifier}' must be one of {CLICK_FIELDS}, "
                    f"got {field!r}"
                )
        if self._raw_data is None:
            return
        names = self._raw_data.collect_schema().names()
        needed = {"sequence_column": self._sequence_column}
        if self._weight_column:
            needed["weight_column"] = self._weight_column
        for identifier, column in self._filters.items():
            needed[f"filter '{identifier}'"] = column
        for what, column in needed.items():
            if column not in names:
                raise ValueError(
                    f"Column '{column}' ({what}) not found in data. "
                    f"Available columns: {names}"
                )

    def _get_cache_config(self) -> dict[str, Any]:
        return {
            "sequence_column": self._sequence_column,
            "weight_column": self._weight_column,
            "alphabet": self._alphabet,
            "background": self._background,
            "units": self._units,
            "position_labels": self._position_labels,
            "first_position": self._first_position,
            "colors": self._colors,
            "title": self._title,
            "y_label": self._y_label,
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        self._sequence_column = config.get("sequence_column", "sequence")
        self._weight_column = config.get("weight_column")
        self._alphabet = config.get("alphabet", normalize_alphabet(None))
        self._background = config.get("background") or normalize_background(
            None, self._alphabet
        )
        self._units = config.get("units", "bits")
        self._position_labels = config.get("position_labels")
        self._first_position = config.get("first_position", 1)
        self._colors = config.get("colors") or default_colors(self._alphabet)
        self._title = config.get("title")
        self._y_label = config.get("y_label")
        if not hasattr(self, "_image_format"):
            self._image_format = None

    def _preprocess(self) -> None:
        """Keep the columns the logo is computed from."""
        if self._raw_data is None:
            raise ValueError("No data provided and no cache exists")
        columns = [self._sequence_column]
        if self._weight_column:
            columns.append(self._weight_column)
        columns.extend(c for c in self._filters.values() if c not in columns)
        self._preprocessed_data["data"] = self._raw_data.select(columns)

    def _get_vue_component_name(self) -> str:
        return "SequenceLogo"

    def _get_data_key(self) -> str:
        return "logoData"

    def logo_data(self, state: dict[str, Any] | None = None) -> pl.DataFrame:
        """The letters of the logo for ``state``: position (0-based), its
        label, residue, count, frequency and height."""
        state = state or {}
        data = self._preprocessed_data.get("data")
        if data is None:
            data = self._raw_data
        if isinstance(data, pl.DataFrame):
            data = data.lazy()
        for identifier, column in self._filters.items():
            value = state.get(identifier)
            if value is None and self._filter_defaults:
                value = self._filter_defaults.get(identifier)
            if value is None:
                data = data.head(0)
                break
            data = filter_selection(data, column, value)
        frame = logo_frame(
            data,
            self._sequence_column,
            self._alphabet,
            self._background,
            self._units,
            self._weight_column,
        )
        return frame.with_columns(
            pl.col("position")
            .map_elements(self._label, return_dtype=pl.Utf8)
            .alias("label")
        ).select("position", "label", "residue", "count", "frequency", "height")

    def _label(self, position: int) -> str:
        labels = self._position_labels
        if labels and 0 <= position < len(labels):
            return labels[position]
        return str(self._first_position + position)

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        frame = self.logo_data(state)
        return {"logoData": frame.to_pandas(), "_hash": compute_dataframe_hash(frame)}

    def _get_component_args(self) -> dict[str, Any]:
        length = len(self._position_labels) if self._position_labels else None
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "colors": self._colors,
            "units": self._units,
            "yMax": max_height(self._units, self._alphabet),
            "yLabel": self._y_label
            or ("Bits" if self._units == "bits" else "Probability"),
            "positionLabels": self._position_labels,
            "firstPosition": self._first_position,
            "length": length,
            "interactivity": self._interactivity or {},
        }
        if self._title:
            args["title"] = self._title
        args.update(image_format_args(self._image_format))
        return args
