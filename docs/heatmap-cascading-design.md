# Heatmap Cascading Downsampling Design

## Overview

The heatmap component uses **cascading downsampling** to efficiently build multi-resolution levels for large datasets. Instead of building each resolution level from raw data (which reads the full dataset N times), cascading builds smaller levels from larger ones - reading raw data only once.

This document explains the algorithm, proves its correctness, and describes the implementation.

---

## The Problem

Mass spectrometry heatmaps often contain millions of data points. To enable smooth zooming, we pre-compute multiple resolution levels:

| Level | Points | Use Case |
|-------|--------|----------|
| 0 | 20,000 | Initial view (zoomed out) |
| 1 | 80,000 | Medium zoom |
| 2 | 320,000 | High zoom |
| 3 | 1,280,000 | Full resolution |

**Naive approach:** Build each level by downsampling raw data independently.
- Problem: Reads 5M+ points 4 times = 20M+ point reads
- Memory: Must scan full dataset for each level

**Cascading approach:** Build Level 2 from Level 3, Level 1 from Level 2, etc.
- Reads raw data once (for Level 3)
- Each subsequent level reads from the previous (smaller) level

---

## Why Cascading Preserves Accuracy

The downsampling algorithm (`downsample_2d_streaming`) works by:

1. **Spatial binning:** Divide the 2D space into a grid (e.g., 400 x 50 bins)
2. **Per-bin selection:** Keep the TOP N highest-intensity points from each bin
3. **Global limit:** Cap total points at target size

### Key Insight: Idempotent Selection

If we select the top-2 highest-intensity points per bin:

```
Raw data (bin 0,0):  [100, 80, 60, 40, 20]  → select [100, 80]
Raw data (bin 0,1):  [95, 75, 55, 35, 15]   → select [95, 75]
```

Now cascade - select top-1 from the top-2:

```
From Level 1 (bin 0,0): [100, 80] → select [100]
From Level 1 (bin 0,1): [95, 75]  → select [95]
```

**This produces the same result as selecting top-1 from raw data:**

```
Raw data (bin 0,0): [100, 80, 60, 40, 20] → select [100]  ✓ Same!
Raw data (bin 0,1): [95, 75, 55, 35, 15]  → select [95]   ✓ Same!
```

### Mathematical Proof

Let `S_k(D)` = top-k highest-intensity points from dataset D per bin.

**Claim:** `S_j(S_k(D)) = S_j(D)` for all `j ≤ k`

**Proof:**
- `S_k(D)` contains the k highest-intensity points per bin
- `S_j(S_k(D))` selects the j highest from those k points
- Since j ≤ k, the j highest from the top-k are exactly the j highest overall
- Therefore `S_j(S_k(D)) = S_j(D)` ∎

### Critical Requirement: Consistent Bin Boundaries

For cascading to work correctly, **bin boundaries must be identical across all levels**. The implementation computes `x_range` and `y_range` once from raw data and passes them to all downsampling calls:

```python
# Computed once, used for ALL levels
x_range, y_range = get_data_range(raw_data, x_column, y_column)

# Level 3 (from raw)
level_3 = downsample(raw_data, x_range=x_range, y_range=y_range, ...)

# Level 2 (from Level 3) - SAME bin boundaries
level_2 = downsample(level_3, x_range=x_range, y_range=y_range, ...)
```

---

## Implementation

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     _preprocess_streaming()                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Compute x_range, y_range from raw data (once)               │
│                                                                  │
│  2. Compute level sizes: [20000, 80000, 320000]                 │
│                                                                  │
│  3. Save full resolution (Level 3) to disk                      │
│     └─► level_3.parquet                                         │
│                                                                  │
│  4. Cascade: Build each level from the previous                 │
│                                                                  │
│     Level 2 ◄── downsample(scan_parquet("level_3.parquet"))     │
│     └─► level_2.parquet                                         │
│                                                                  │
│     Level 1 ◄── downsample(scan_parquet("level_2.parquet"))     │
│     └─► level_1.parquet                                         │
│                                                                  │
│     Level 0 ◄── downsample(scan_parquet("level_1.parquet"))     │
│     └─► level_0.parquet                                         │
│                                                                  │
│  5. Load all levels as LazyFrame references                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Code Flow

```python
def _preprocess_streaming(self) -> None:
    # Step 1: Get bin boundaries (used for ALL levels)
    x_range, y_range = get_data_range(self._raw_data, ...)

    # Step 2: Compute target sizes
    level_sizes = compute_compression_levels(min_points, total)
    # Example: [20000, 80000, 320000] for 1M points

    # Step 3: Save full resolution first
    full_res_path = cache_dir / f"level_{len(level_sizes)}.parquet"
    self._raw_data.sort([x_col, y_col]).sink_parquet(full_res_path)

    # Step 4: Cascade from largest to smallest
    current_source = pl.scan_parquet(full_res_path)

    for i, target_size in enumerate(reversed(level_sizes)):
        level_idx = len(level_sizes) - 1 - i

        # Downsample from PREVIOUS level (not raw data!)
        level = downsample_2d_streaming(
            current_source,  # ◄── Key: uses previous level
            max_points=target_size,
            x_range=x_range,  # ◄── Consistent boundaries
            y_range=y_range,
        )

        # Save immediately to disk
        level_path = cache_dir / f"level_{level_idx}.parquet"
        level.sink_parquet(level_path)

        # Next iteration reads from this level
        current_source = pl.scan_parquet(level_path)
```

### Memory Efficiency

The streaming implementation never holds more than one level in memory:

1. **sink_parquet():** Streams LazyFrame directly to disk without full materialization
2. **scan_parquet():** Returns a LazyFrame reference (no data loaded)
3. **Immediate saves:** Each level is written to disk before building the next

This enables processing datasets larger than available RAM.

---

## Categorical Filter Handling

When `categorical_filters` is specified (e.g., filtering by ion mobility dimension), the component creates separate level hierarchies per filter value:

```
cache/
├── level_0.parquet          # Global fallback
├── level_1.parquet
├── level_2.parquet
├── cat_level_im_0_0.parquet # im_dimension=0, Level 0
├── cat_level_im_0_1.parquet # im_dimension=0, Level 1
├── cat_level_im_1_0.parquet # im_dimension=1, Level 0
├── cat_level_im_1_1.parquet # im_dimension=1, Level 1
└── ...
```

Each per-value hierarchy uses the same cascading approach, with bin boundaries computed from the filtered subset.

---

## Testing

The `tests/test_heatmap_cascading.py` file verifies cascading correctness:

| Test | Description |
|------|-------------|
| `test_single_cascade_step_equivalence` | One cascade step matches from-scratch |
| `test_multi_step_cascade_equivalence` | Multiple cascades match from-scratch |
| `test_cascade_preserves_highest_intensity_per_bin` | Correct points survive |
| `test_large_data_cascade_equivalence` | Works at scale (50K points) |
| `test_cascade_via_parquet_roundtrip` | Parquet serialization preserves accuracy |

### Example Test

```python
def test_single_cascade_step_equivalence(data):
    x_range, y_range = get_data_range(data, "x", "y")

    # From scratch: raw → 200 points
    from_scratch = downsample(data, max_points=200, x_range=x_range, ...)

    # Cascading: raw → 400 → 200
    intermediate = downsample(data, max_points=400, x_range=x_range, ...)
    cascaded = downsample(intermediate, max_points=200, x_range=x_range, ...)

    # Must produce identical results
    assert set(from_scratch["intensity"]) == set(cascaded["intensity"])
```

---

## Performance Comparison

| Approach | Raw Data Reads | Memory Peak | I/O Operations |
|----------|---------------|-------------|----------------|
| Naive (from-scratch) | N levels | Full dataset | N full scans |
| Cascading | 1 | ~1 level | N incremental writes |

For a 5M point dataset with 4 levels:
- **Naive:** 20M point reads, high memory
- **Cascading:** 5M point reads, bounded memory

---

## Configuration

```python
Heatmap(
    cache_id="peaks",
    data_path="peaks.parquet",
    x_column="retention_time",
    y_column="mz",
    intensity_column="intensity",
    min_points=20000,      # Smallest level target
    x_bins=400,            # Spatial grid resolution
    y_bins=50,
    use_streaming=True,    # Enable cascading (default)
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_points` | 20000 | Target size for smallest (most zoomed out) level |
| `x_bins` | 400 | Horizontal grid resolution for binning |
| `y_bins` | 50 | Vertical grid resolution for binning |
| `use_streaming` | True | Use streaming cascading (recommended) |
