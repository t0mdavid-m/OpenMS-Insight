"""Sequence coverage map: matched stretches of a reference sequence, per track."""

import hashlib
import json
import math
from typing import Any

import polars as pl

from ..core.base import BaseComponent
from ..core.image_format import image_format_args, validate_image_format
from ..core.registry import register_component

# Fixed count bins shared by every track (upper bound, label, colour): a
# reversed magma palette, light for few matches and dark for many.
DEFAULT_COUNT_BINS: tuple[tuple[float, str, str], ...] = (
    (1, "1", "#fcfdbf"),
    (2, "2", "#fdc78d"),
    (4, "3–4", "#fb8861"),
    (8, "5–8", "#e65163"),
    (16, "9–16", "#b73779"),
    (32, "17–32", "#822581"),
    (64, "33–64", "#4f127b"),
    (128, "65–128", "#1c1044"),
    (math.inf, "129+", "#000004"),
)
EMPTY_COUNT_COLOR = "#e4e7ec"
MODIFICATION_COLOR = "#00a6a6"


def count_color(
    count: float | None,
    bins: tuple[tuple[float, str, str], ...] | list = DEFAULT_COUNT_BINS,
    empty: str = EMPTY_COUNT_COLOR,
) -> str:
    """Colour of a match's count: ``empty`` for none or zero, else its bin's."""
    if count is None or count == 0 or (isinstance(count, float) and math.isnan(count)):
        return empty
    for upper, _, color in bins:
        if upper is None or count <= upper:
            return color
    return bins[-1][2]


def pack_lanes(hits: list[dict[str, Any]]) -> int:
    """Give each hit a ``lane`` so overlapping hits stack; returns the lane count.

    Hits are packed in the order given (sorted by start first, longer first),
    each into the first lane whose last hit ended before it starts.
    """
    ends: list[int] = []
    for hit in hits:
        lane = next((i for i, end in enumerate(ends) if end < hit["start"]), len(ends))
        if lane == len(ends):
            ends.append(hit["end"])
        else:
            ends[lane] = hit["end"]
        hit["lane"] = lane
    return max(1, len(ends))


def covered_positions(hits: list[dict[str, Any]], length: int) -> int:
    """Number of reference positions (1..length) at least one hit covers."""
    covered = [False] * length
    for hit in hits:
        for position in range(max(1, hit["start"]), min(length, hit["end"]) + 1):
            covered[position - 1] = True
    return sum(covered)


def _reference_tokens(reference: str | list[str] | None) -> list[str]:
    if reference is None:
        return []
    if isinstance(reference, str):
        return list(reference)
    return [str(token) for token in reference]


def _to_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    try:
        return list(value)
    except TypeError:
        return [value]


def _plain(value: Any) -> Any:
    """A JSON-friendly copy of a numpy or pandas scalar."""
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _check_block_size(block_size: Any) -> None:
    if block_size is None:
        return
    if (
        isinstance(block_size, bool)
        or not isinstance(block_size, int)
        or not 10 <= block_size <= 200
    ):
        raise ValueError("block_size must be None or an integer from 10 to 200")


@register_component("sequence_coverage")
class SequenceCoverage(BaseComponent):
    """
    Where matches lie on a reference sequence, one track per group of matches.

    Each row of ``data`` is one match: a stretch ``start``..``end`` (1-based,
    inclusive) of the reference, with a label (the matched sequence) and,
    optionally, a count (e.g. its spectrum matches), a track (a condition or
    sample) and modified positions. The view draws the reference in blocks of
    ``block_size`` positions; below each block every track packs its matches
    into lanes, coloured by count on bins shared by all tracks, with a dot at
    each modified position. Each track and the whole reference report how many
    positions are covered. Works for any sequence of tokens: nucleotides,
    amino acids, or modified codes such as ``[m1A]``.

    Clicking a match sets the ``interactivity`` identifiers to its values, and
    the match whose values the state holds is outlined.

    The map fills the width it is given. Its cog menu sets the positions per
    line (fitted to the width by default) and holds the app's own
    ``toolbar_settings`` (see core/settings.py), e.g. how matches are grouped
    into tracks: their values go to selection identifiers the app reads back
    with ``setting_value`` and builds the rows from. The download menu saves
    the map as an image, as a web page of its own, or the drawn matches as a
    tab-separated table.

    Example:
        coverage = SequenceCoverage(
            cache_id="coverage",
            data=matches,
            reference=list("AUGGCUACGU"),
            start_column="start",
            end_column="end",
            label_column="sequence",
            count_column="psms",
            track_column="condition",
            filters={"accession": "accession"},
            interactivity={"oligo": "oligo_id"},
        )
        coverage(key="coverage", state_manager=state_manager)
    """

    _component_type: str = "sequence_coverage"
    #: The cog menu holds the app's ``toolbar_settings`` too.
    _supports_settings: bool = True

    def __init__(
        self,
        cache_id: str,
        data: pl.LazyFrame | None = None,
        data_path: str | None = None,
        reference: str | list[str] | None = None,
        start_column: str = "start",
        end_column: str = "end",
        label_column: str | None = "sequence",
        count_column: str | None = None,
        track_column: str | None = None,
        track_note_column: str | None = None,
        modifications_column: str | None = None,
        modification_labels_column: str | None = None,
        track_order: list[str] | None = None,
        filters: dict[str, str] | None = None,
        filter_defaults: dict[str, Any] | None = None,
        interactivity: dict[str, str] | None = None,
        cache_path: str = ".",
        regenerate_cache: bool = False,
        title: str | None = "Sequence coverage",
        reference_name: str | None = None,
        block_size: int | None = None,
        count_label: str = "Matches",
        count_bins: list[tuple[float, str, str]] | None = None,
        empty_color: str = EMPTY_COUNT_COLOR,
        modification_color: str = MODIFICATION_COLOR,
        notes: list[str] | None = None,
        empty_message: str = "Nothing matched to this sequence.",
        image_format: str | None = None,
        **kwargs,
    ):
        """
        Initialize the SequenceCoverage component.

        Args:
            cache_id: Unique identifier for this component's cache (MANDATORY).
            data: Polars LazyFrame, one row per match.
            data_path: Path to a parquet file with the data.
            reference: The reference sequence: a string (one token per
                character) or a list of tokens. ``set_reference()`` replaces it
                for one render, e.g. when the filters pick another reference.
            start_column: First covered position (1-based).
            end_column: Last covered position (1-based, inclusive).
            label_column: Label of a match, shown in its tooltip.
            count_column: Count of a match (colours it); None colours all
                matches as count 1.
            track_column: Track a match belongs to; None: one track.
            track_note_column: A line shown under a track's name (its first
                value in the track), e.g. how many samples were pooled.
            modifications_column: List column of modified positions (1-based).
            modification_labels_column: List column naming each modification,
                in the order of ``modifications_column``.
            track_order: Order of the tracks (others follow in data order).
            filters: Mapping of identifier names to column names for filtering.
            filter_defaults: Default values for filters when state is None.
            interactivity: Mapping of identifier names to column names set by
                clicking a match.
            cache_path: Base path for cache storage.
            regenerate_cache: Rebuild the cache even if a matching one exists.
            title: Title above the map (None: no title).
            reference_name: Name of the reference (e.g. its accession), shown
                in the title line and the image file name.
            block_size: Positions per line, 10 to 200, the value the
                settings menu starts from; None (default) fits as many
                positions per line as the width allows. The user changes it
                in the settings menu (the cog), render-time only.
            count_label: What a count counts, titling the colour legend.
            count_bins: (upper bound, label, colour) per count bin, ascending;
                default a magma scale from 1 to 129+.
            empty_color: Colour of a match whose count is zero or unknown.
            modification_color: Colour of the modification dots.
            notes: Lines of explanation below the legend.
            empty_message: Shown when no match is left after filtering.
            image_format: Format of the image download: 'svg', 'png', 'jpeg'
                or 'webp'. None (default) follows
                ``openms_insight.set_image_format()``. Render-time only.
            **kwargs: Additional configuration options.
        """
        _check_block_size(block_size)
        self._reference = _reference_tokens(reference)
        self._start_column = start_column
        self._end_column = end_column
        self._label_column = label_column
        self._count_column = count_column
        self._track_column = track_column
        self._track_note_column = track_note_column
        self._modifications_column = modifications_column
        self._modification_labels_column = modification_labels_column
        self._track_order = list(track_order or [])
        self._title = title
        self._reference_name = reference_name
        self._block_size = block_size
        self._count_label = count_label
        self._count_bins = [
            [None if math.isinf(float(u)) else float(u), str(label), str(color)]
            for u, label, color in (count_bins or DEFAULT_COUNT_BINS)
        ]
        self._empty_color = empty_color
        self._modification_color = modification_color
        self._notes = list(notes or [])
        self._empty_message = empty_message
        self._image_format = validate_image_format(image_format, allow_none=True)
        # Reference given for one render (not cached)
        self._render_reference: list[str] | None = None
        self._render_reference_name: str | None = None
        super().__init__(
            cache_id=cache_id,
            data=data,
            data_path=data_path,
            filters=filters,
            filter_defaults=filter_defaults,
            interactivity=interactivity,
            cache_path=cache_path,
            regenerate_cache=regenerate_cache,
            **kwargs,
        )

    # -- columns and cache --------------------------------------------------

    def _match_columns(self) -> list[str]:
        columns = [self._start_column, self._end_column]
        for column in (
            self._label_column,
            self._count_column,
            self._track_column,
            self._track_note_column,
            self._modifications_column,
            self._modification_labels_column,
        ):
            if column:
                columns.append(column)
        columns += list((self._interactivity or {}).values())
        columns += list((self._filters or {}).values())
        return list(dict.fromkeys(columns))

    def _validate_columns(self, schema: pl.Schema) -> None:
        available = set(schema.names())
        missing = [c for c in self._match_columns() if c not in available]
        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. "
                f"Available columns: {sorted(available)}"
            )

    def _get_cache_config(self) -> dict[str, Any]:
        return {
            "reference": self._reference,
            "start_column": self._start_column,
            "end_column": self._end_column,
            "label_column": self._label_column,
            "count_column": self._count_column,
            "track_column": self._track_column,
            "track_note_column": self._track_note_column,
            "modifications_column": self._modifications_column,
            "modification_labels_column": self._modification_labels_column,
            "track_order": self._track_order,
            "title": self._title,
            "reference_name": self._reference_name,
            "block_size": self._block_size,
            "count_label": self._count_label,
            "count_bins": self._count_bins,
            "empty_color": self._empty_color,
            "modification_color": self._modification_color,
            "notes": self._notes,
            "empty_message": self._empty_message,
        }

    def _restore_cache_config(self, config: dict[str, Any]) -> None:
        self._reference = list(config.get("reference") or [])
        self._start_column = config.get("start_column", "start")
        self._end_column = config.get("end_column", "end")
        self._label_column = config.get("label_column", "sequence")
        self._count_column = config.get("count_column")
        self._track_column = config.get("track_column")
        self._track_note_column = config.get("track_note_column")
        self._modifications_column = config.get("modifications_column")
        self._modification_labels_column = config.get("modification_labels_column")
        self._track_order = list(config.get("track_order") or [])
        self._title = config.get("title", "Sequence coverage")
        self._reference_name = config.get("reference_name")
        self._block_size = config.get("block_size")
        self._count_label = config.get("count_label", "Matches")
        self._count_bins = config.get("count_bins") or [
            [None if math.isinf(u) else u, label, color]
            for u, label, color in DEFAULT_COUNT_BINS
        ]
        self._empty_color = config.get("empty_color", EMPTY_COUNT_COLOR)
        self._modification_color = config.get("modification_color", MODIFICATION_COLOR)
        self._notes = list(config.get("notes") or [])
        self._empty_message = config.get(
            "empty_message", "Nothing matched to this sequence."
        )
        self._render_reference = None
        self._render_reference_name = None

    def _preprocess(self) -> None:
        if self._raw_data is None:
            raise ValueError("No data provided and no cache exists")
        self._validate_columns(self._raw_data.collect_schema())
        df = self._raw_data.select(self._match_columns()).collect()
        self._preprocessed_data = {"coverageData": df}

    # -- render ---------------------------------------------------------------

    def set_reference(
        self, reference: str | list[str] | None, name: str | None = None
    ) -> "SequenceCoverage":
        """
        Reference sequence (and its name) for the next render.

        Args:
            reference: A string or list of tokens; None goes back to the
                reference given to the constructor.
            name: Name shown in the title line (None: ``reference_name``).

        Returns:
            Self for method chaining.
        """
        self._render_reference = (
            None if reference is None else _reference_tokens(reference)
        )
        self._render_reference_name = name
        return self

    @property
    def reference(self) -> list[str]:
        """The reference drawn with the next render."""
        if self._render_reference is not None:
            return list(self._render_reference)
        return list(self._reference)

    def _get_render_key(self) -> str | None:
        if self._render_reference is None and self._render_reference_name is None:
            return None
        return hashlib.md5(
            json.dumps([self._render_reference, self._render_reference_name]).encode()
        ).hexdigest()

    def _get_vue_component_name(self) -> str:
        return "SequenceCoverage"

    def _get_data_key(self) -> str:
        return "coverageData"

    def _filtered_matches(self, state: dict[str, Any]) -> tuple[list[dict], str]:
        if self._preprocessed_data is None or not self._preprocessed_data:
            self._load_preprocessed_data()
        data = self._preprocessed_data["coverageData"]
        if isinstance(data, pl.DataFrame):
            data = data.lazy()
        from ..preprocessing.filtering import filter_and_collect_cached

        frame, data_hash = filter_and_collect_cached(
            data,
            self._filters or {},
            state,
            columns=self._match_columns(),
            filter_defaults=self._filter_defaults,
        )
        return frame.to_dict("records"), data_hash

    def build_model(self, state: dict[str, Any]) -> dict[str, Any]:
        """The coverage map for ``state``: reference, tracks, packed hits and coverage.

        Returns a dict with ``reference`` (tokens), ``length``,
        ``covered``/``coverage`` (whole reference) and ``tracks``, each with
        ``name``, ``note``, ``covered``, ``coverage``, ``lanes`` and ``hits``
        (``id``, ``start``, ``end``, ``label``, ``count``, ``color``, ``lane``,
        ``modifications`` and the ``values`` a click sets). Hits outside the
        reference are clipped to it, and dropped when nothing is left.
        """
        reference = self.reference
        length = len(reference)
        rows, data_hash = self._filtered_matches(state)
        interactivity = self._interactivity or {}
        tracks: dict[str, dict[str, Any]] = {}
        for index, row in enumerate(rows):
            start = _plain(row.get(self._start_column))
            end = _plain(row.get(self._end_column))
            if start is None or end is None:
                continue
            start, end = int(start), int(end)
            if end < start:
                start, end = end, start
            if length:
                start, end = max(1, start), min(length, end)
                if start > end:
                    continue
            track = (
                str(_plain(row.get(self._track_column))) if self._track_column else ""
            )
            entry = tracks.setdefault(
                track,
                {
                    "name": track,
                    "note": (
                        _plain(row.get(self._track_note_column))
                        if self._track_note_column
                        else None
                    ),
                    "hits": [],
                },
            )
            count = _plain(row.get(self._count_column)) if self._count_column else 1
            positions = (
                [_plain(p) for p in _to_list(row.get(self._modifications_column))]
                if self._modifications_column
                else []
            )
            labels = (
                [_plain(p) for p in _to_list(row.get(self._modification_labels_column))]
                if self._modification_labels_column
                else []
            )
            modifications = [
                {
                    "position": int(p),
                    "label": str(labels[i])
                    if i < len(labels) and labels[i] is not None
                    else "",
                }
                for i, p in enumerate(positions)
                if p is not None and start <= int(p) <= end
            ]
            entry["hits"].append(
                {
                    "id": index,
                    "start": start,
                    "end": end,
                    "label": (
                        str(_plain(row.get(self._label_column)))
                        if self._label_column
                        else ""
                    ),
                    "count": count,
                    "color": count_color(
                        count, [tuple(b) for b in self._count_bins], self._empty_color
                    ),
                    "modifications": modifications,
                    "values": {
                        identifier: _plain(row.get(column))
                        for identifier, column in interactivity.items()
                    },
                }
            )

        order = [t for t in self._track_order if t in tracks]
        order += [t for t in tracks if t not in order]
        all_hits: list[dict[str, Any]] = []
        track_list = []
        for name in order:
            entry = tracks[name]
            hits = sorted(entry["hits"], key=lambda h: (h["start"], -h["end"]))
            entry["hits"] = hits
            entry["lanes"] = pack_lanes(hits)
            covered = covered_positions(hits, length) if length else 0
            entry["covered"] = covered
            entry["coverage"] = covered / length if length else 0.0
            all_hits += hits
            track_list.append(entry)
        covered = covered_positions(all_hits, length) if length else 0
        return {
            "reference": reference,
            "length": length,
            "covered": covered,
            "coverage": covered / length if length else 0.0,
            "tracks": track_list,
            "_hash": data_hash,
        }

    def _prepare_vue_data(self, state: dict[str, Any]) -> dict[str, Any]:
        model = self.build_model(state)
        data_hash = model.pop("_hash")
        model["name"] = self._render_reference_name or self._reference_name
        return {
            "coverageData": model,
            "_hash": hashlib.md5(
                json.dumps([data_hash, self._get_render_key()]).encode()
            ).hexdigest(),
        }

    def _get_component_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {
            "componentType": self._get_vue_component_name(),
            "title": self._title,
            "blockSize": self._block_size,
            "countLabel": self._count_label,
            "countBins": self._count_bins,
            "emptyColor": self._empty_color,
            "modificationColor": self._modification_color,
            "notes": self._notes,
            "emptyMessage": self._empty_message,
            "interactivity": self._interactivity or {},
            "hasCounts": self._count_column is not None,
        }
        args.update(image_format_args(self._image_format))
        return args

    def __call__(
        self,
        key: str | None = None,
        state_manager: Any | None = None,
        height: int | None = None,
        block_size: int | None = None,
        help: str | None = None,
    ) -> Any:
        """
        Render the coverage map.

        Args:
            key: Optional unique key for this component instance.
            state_manager: StateManager for cross-component linking.
            height: Optional height in pixels (None: as tall as the map).
            block_size: Positions per line for this render (10 to 200).
            help: Help text shown in the component's card.
        """
        if block_size is not None:
            _check_block_size(block_size)
            self._block_size = block_size
        return super().__call__(
            key=key, state_manager=state_manager, height=height, help=help
        )
