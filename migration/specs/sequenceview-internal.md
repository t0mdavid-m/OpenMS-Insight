# Spec: `SequenceView(internal_fragments=True)` — Internal Fragment Map parity

Status: implementable. Analysis-only document; no runtime code is changed by this file.

This spec adds **internal-fragment** support to OpenMS-Insight's existing `SequenceView`
component (`openms_insight/components/sequenceview.py` + `js-component/.../sequence/SequenceView.vue`),
reproducing FLASHApp's **Internal Fragment Map**.

The non-negotiable, highest-risk item is **porting the internal-fragment math**
(`getInternalFragmentDataFromSeq` and its helper `getInternalFragmentMassesWithSeq`)
**out of FLASHApp's Python and into `sequenceview.py`**. In the oracle this math runs in
`FLASHApp/src/render/sequence.py` (Python, enumerates theoretical internal-fragment masses)
and the **matching against observed masses runs in the Vue** (`InternalFragmentMap.vue`,
`filterMatchingMasses`). The port keeps the same split: **Python enumerates theoretical
internal fragments; Vue matches them against the selected scan's observed masses** — exactly
mirroring how the terminal `SequenceView` already works (Python emits `fragment_masses_*`,
Vue matches in `matchFragmentsTheoretical`).

## Oracles (read-only; reproduce, never edit)

- `/home/user/openms-streamlit-vue-component/src/components/sequence/InternalFragmentMap.vue`
  — visual layout, legend, settings, matching loop.
- `/home/user/openms-streamlit-vue-component/src/types/internal-fragment-data.ts`
  — the exact field names of the per-proteoform internal-fragment payload.
- `/home/user/FLASHApp/src/render/sequence.py`
  — `getInternalFragmentDataFromSeq`, `getInternalFragmentMassesWithSeq`,
    `getFragmentMassesWithSeq`, `remove_ambigious`, `isMatchWithTolerance`, `aa_masses`,
    `H20`, `NH3`. **This is the math to port.**
- `/home/user/FLASHApp/src/render/update.py`
  — `render_internal_fragment_data` / `update_data` / `filter_data`: how the map is
    populated per selected proteoform (`internal_fragment_data[pid]`) and how it is
    paired with the selected scan's observed masses (`per_scan_data[...]['MonoMass']`).
- `/home/user/FLASHApp/src/render/sequence_data_store.py`
  — parquet schema + `load_entry` pushdown (the per-proteoform terminal payload).

## Insight context (extend, do not rewrite)

- `openms_insight/components/sequenceview.py` — self-contained component (does **not**
  extend `core/base.py:BaseComponent`; it has its own cache dir, `.cache_config.json`,
  `sequences.parquet`, `peaks.parquet`). Key methods: `_get_sequence_for_state`,
  `_get_peaks_for_state`, `_prepare_vue_data`, `_get_component_args`, `_get_cache_config`,
  `_load_from_cache`, `calculate_fragment_masses_pyopenms`, `parse_openms_sequence`.
- `js-component/src/components/sequence/SequenceView.vue` — the Vue to extend
  (`matchFragmentsTheoretical`, `markAminoAcidPosition`, `initializeSequenceObjects`).
- `js-component/src/types/sequence-data.ts` — `SequenceData` interface to extend.
- `js-component/src/types/component.ts` — `SequenceViewComponentArgs` to extend.
- `js-component/src/App.vue` — `componentType === 'SequenceView'` dispatch (unchanged).
- `tests/test_sequenceview.py`, `tests/conftest.py` (`sample_sequence_data`,
  `sample_peaks_data`).

---

## 1. Behaviors to preserve from `InternalFragmentMap.vue`

The oracle is a **dense stacked-block map**: a single header row of the amino-acid letters,
followed by three stacked groups of horizontal "bars", one bar per **matched** internal
fragment, colored by internal-ion family. There is no per-residue marker glyph and no
fragment table — it is purely a coverage-bar visualization.

### 1.1 Visual layout (must reproduce)

- Title `Internal Fragment Map` (centered `<h4>`).
- A legend row with three swatches + labels, **in this order**: `by/cz`, `bz`, `cy`.
- A settings cog (`v-menu`) exposing four controls (1.4).
- A bordered `v-sheet` containing `#internal-fragment-part`:
  1. **Header row**: one square cell per amino acid showing the letter
     (`.fragment-segment.sequence-text`, `aspect-ratio: 1`).
  2. Then **three groups in DOM order `by`, then `cy`, then `bz`** (note: legend order is
     by/cz, bz, cy but DOM render order is by, cy, bz — preserve the DOM order so screenshots
     match). Each group is a vertical stack of rows; each row corresponds to one matched
     internal fragment and contains one cell per amino acid.
- Cell height is driven by sequence length: `height = (94 / sequence.length).toFixed(2) + 'vw'`
  (square cells; the whole map scales to ~94vw wide). Preserve this so long proteoforms stay
  on one virtual row.

### 1.2 What each cell/bar means

For a matched internal fragment with `start` (0-based N-terminal bound index) and `end`
(1-based exclusive-style C-terminal bound, as produced by the math — see §3), a residue cell
at `aaIndex` is **filled** iff:

```
inFragment = (aaIndex > start) && (aaIndex <= end)
```

(This is `fragmentClasses()` in the oracle — note the **strict** `>` on the left and `<=` on
the right; the fragment spans residues `start+1 .. end` inclusive in 0-based cell terms.)
Filled cells get the family color; non-filled cells are transparent (`.not-in-fragment`).
Every cell carries `border: 1px solid white`.

### 1.3 Coloring (exact hex)

| Family (DOM key) | Legend label | Fill color | matches oracle `.<x>-fragment` |
|---|---|---|---|
| `by` | `by/cz` | `#f0a441` | `.by-fragment` |
| `cy` | `cy` | `#12871d` | `.cy-fragment` |
| `bz` | `bz` | `#7831cc` | `.bz-fragment` |

`by` and `cz` collapse into the **same** family/track/color (`by`), because the math
(§3) computes `by` and `cz` with the **same shift** and the oracle only emits/draws three
families: `by`, `bz`, `cy`.

### 1.4 Settings (preserve all four; same defaults)

1. **Fragments display style** — switch `fragmentDisplayOverlay` (default `false`).
   - `false` ("Stacked"): each fragment row is `position: static`, rows stack vertically
     (`fragmentTypeOverlayStyle.position = 'static'`, container `height: auto`).
   - `true` ("Overlay fragments from the same type"): rows become `position: absolute` and
     overlap into a single row of height = cell height; filled cells use the
     `-overlayed` class which applies `opacity: var(--frag-block-opacity-value)`.
2. **Opacity of each fragment** — slider `fragOpacity` (default `0.2`, min `0.01`, max `1`,
   step `0.01`), wired to `--frag-block-opacity-value`; only meaningful in overlay mode.
3. **Fragment mass tolerance** — value `fragmentMassTolerance` (default `10`) + unit
   switch `fragmentMassToleranceUnit` (`'ppm'` | `'Da'`, default `'ppm'`). NOTE the oracle's
   matching (`filterMatchingMasses`) **only implements ppm** (it always computes
   `massDiffPpm` and compares to `fragmentMassTolerance`); the `Da` toggle exists in the UI
   but the comparison is ppm-only. **Parity = keep ppm-only matching.** (A `Da` branch may be
   added as an Insight improvement but is NOT required for parity; if added, gate it so the
   default `ppm` path is byte-identical.)
4. `SvgScreenshot` button over `#internal-fragment-part`.

### 1.5 Hover / interaction / selection

- The oracle InternalFragmentMap has **no hover tooltips, no click handlers, no
  cross-component selection** on the bars. Cells are pure visual fills. **Preserve: the
  internal map is display-only** (no `selectionStore` writes, no annotations emitted from the
  internal map). This differs from the terminal `SequenceView`, which is interactive.
- Eligibility gate (must reproduce): a family renders **no** bars when the selected scan is
  ineligible. Oracle: in `byData/cyData/bzData`, if `selectedScanInfo === undefined` →
  `[]`; and `if ((observedMass === 0) && (!displayTnT)) return []` where
  `observedMass = selectedScanInfo.PrecursorMass` and `displayTnT` is true when the
  proteoform entry has a `computed_mass` (FLASHTnT mode). I.e. for plain-FD MS2 with
  `PrecursorMass === 0` and no proteoform, show nothing. In Insight terms the equivalent is:
  no selected spectrum / empty observed masses → no bars (see §4.4).

### 1.6 Selected-proteoform / selected-scan pairing (oracle data flow)

- The theoretical internal fragments are **per proteoform**: oracle
  `internalFragmentData = streamlitData.internalFragmentData[selectedProteinIndex]`
  (`render_internal_fragment_data(sequence)` keyed by `pid` in `update.py`).
- The observed masses are **per selected scan**:
  `observed_masses = selectedScanInfo.MonoMass` (the deconvolved monoisotopic mass list).
- Matching is the Vue's `filterMatchingMasses` (§3.5). In Insight the same two inputs map to
  the existing `SequenceView` filters/peaks: the proteoform → `sequence` filter, the scan →
  `spectrum`/`identification` filter feeding `peaks_data.mass`. **Reuse the existing
  `_get_sequence_for_state` / `_get_peaks_for_state` plumbing**; do not add a parallel data
  path.

---

## 2. Python API

### 2.1 The flag: `internal_fragments` is **config (cache-invalidating)**

Add a constructor kwarg `internal_fragments: bool = False` to `SequenceView.__init__`.
It is **config**, not render-time, because:
- It changes what gets precomputed/serialized (the per-proteoform internal-fragment arrays
  are derived from the sequence; see §2.4 on where they live), and
- It changes `_get_cache_config()` (so flipping it invalidates the cache, consistent with
  how `deconvolved` is handled).

It must also be threaded into `_get_cache_config()`, `_load_from_cache()`, and the
`has_config` gate in `__init__` (so passing `internal_fragments=True` without
`sequence_data` correctly raises, like the other config args).

### 2.2 Constructor signature (additions only)

```python
def __init__(
    self,
    cache_id: str,
    sequence_data=None,
    sequence_data_path=None,
    peaks_data=None,
    peaks_data_path=None,
    filters=None,
    interactivity=None,
    deconvolved=False,
    annotation_config=None,
    cache_path=".",
    title=None,
    height=400,
    # NEW:
    internal_fragments: bool = False,
    internal_fragment_config: Optional[Dict[str, Any]] = None,
    **kwargs,
):
```

`internal_fragment_config` (all optional; defaults chosen to match the oracle):

| key | default | meaning | oracle source |
|---|---|---|---|
| `min_length` | `5` | minimum internal-fragment residue length | `if j < i+5-1: continue` |
| `ion_types` | `["by", "bz", "cy"]` | which internal families to enumerate | `for ion_type in ['by','bz','cy']` |
| `tolerance` | `10.0` | default match tolerance value (Vue init) | `fragmentMassTolerance: 10` |
| `tolerance_ppm` | `True` | ppm (True) vs Da (False) default | `fragmentMassToleranceUnit: 'ppm'` |
| `remove_terminal_collisions` | `True` | drop internal masses that collide with a terminal a/b/c/x/y/z mass within `terminal_collision_ppm` | `tmp code` block in `getInternalFragmentMassesWithSeq` |
| `terminal_collision_ppm` | `10.0` | ppm window for the collision filter | `isMatchWithTolerance(..., 10.0)` |

Rationale for surfacing `remove_terminal_collisions`: the oracle hard-codes a "remove any
internal fragment whose theoretical mass matches a terminal by/cz mass within 10 ppm"
filter and even tags it `# TODO: Should be adressed in component`. To get **bit-identical**
parity the default MUST be `True` with `terminal_collision_ppm = 10.0`. We surface it as a
flag so Phase 2 can flip the default once the behavior is reviewed, without changing parity
defaults now.

### 2.3 Input schema (unchanged from existing `SequenceView`)

No new user input columns. Internal fragments are **derived from the same `sequence` string**
already required by `SequenceView` (`sequences.parquet: sequence, precursor_charge`, plus any
filter columns). Observed masses come from the same `peaks.parquet: peak_id, mass`. This is
the whole point: the math moves into Python and consumes existing inputs.

> If/when the FLASHApp proteoform payload (`proteoform_start/end`, `computed_mass`,
> `modifications` from `sequence_data_store.py`) is wired into Insight's `SequenceView`,
> the internal-fragment math is already written to accept an optional `modifications` list
> (§3) and a `[start:end]` proteoform slice (the oracle slices `sequence.slice(start, end+1)`
> before building the map). For Phase-1 parity on the plain-sequence path, `modifications`
> defaults to `None` and the full sequence is used.

---

## 3. THE FRAGMENT-MATH PORT (highest risk)

Port `getInternalFragmentDataFromSeq` + `getInternalFragmentMassesWithSeq` from
`FLASHApp/src/render/sequence.py` into **`sequenceview.py`** as pure module-level functions
(no `streamlit`, no `session_state`). Below is the exact oracle algorithm, then the Python to
add, then derived golden numbers.

### 3.1 Oracle constants (copy verbatim)

```python
H20 = 18.010564683
NH3 = 17.0265491015
# aa_masses: the 20 + U + X(0) + Z(0) table from sequence.py (monoisotopic residue masses)
```

Internal-ion **shift** by family (oracle line, verbatim logic):

```
shift = -H20            if res_type in ('by','cz')
        -H20 - NH3      if res_type == 'bz'
        -H20 + NH3      otherwise   # 'cy'
```

Each emitted mass is `internal_residue_sum + 18.010564683 + shift`. Net effect:

| family | net add to residue sum | numeric |
|---|---|---|
| `by` / `cz` | `+H2O + (-H2O)` = `0` | `+0.000000` |
| `bz` | `+H2O + (-H2O-NH3)` = `-NH3` | `-17.026549` |
| `cy` | `+H2O + (-H2O+NH3)` = `+NH3` | `+17.026549` |

(The `+18.0105...` is written separately from `H20` in the oracle; they are equal to 9 d.p.
Keep both literals to stay byte-identical with the oracle arithmetic ordering.)

### 3.2 Enumeration (the exact double loop)

For a sequence of length `L`, family `res_type`, optional `modifications`
(`list[(start1based, end1based, mass)]`), optional `terminal_masses` (sorted):

```
masses, start_indices, end_indices = [], [], []
for i in range(L):                 # N-terminal bound, 0-based
    if i == 0: continue            # first position cannot start an internal fragment
    if i == L-1: break             # last position cannot start one (and ends the i-loop)
    mass = 0.0
    for j in range(L):             # C-terminal bound, 0-based
        if j >= i:                 # accumulate residues from i..j inclusive
            mass += aa_masses[seq[j]]
        if j < i + min_length - 1: # enforce length >= min_length (oracle: i+5-1)
            continue
        possible_masses = [mass]
        if modifications is not None:
            for (s, e, m) in modifications:
                if (s >= i+1) and (e <= j+1):          # mod fully inside [i+1, j+1]
                    possible_masses[0] += m            # always applied
                elif (s >= i+1) or (e <= j+1):         # mod partially overlaps
                    possible_masses.append(mass + m)   # ambiguous: emit BOTH variants
        for mm in possible_masses:
            if terminal_masses is not None and remove_terminal_collisions \
               and _is_match_with_tolerance(terminal_masses, mm, terminal_collision_ppm):
                continue                                # drop internal/terminal collision
            masses.append(mm + 18.010564683 + shift)
            start_indices.append(i)                     # 0-based N bound
            end_indices.append(j+1)                     # 1-based C bound (exclusive-style)
return masses, start_indices, end_indices
```

`terminal_masses` is built exactly as the oracle's `tmp code`:
`byp + bys + czp + czs` from `getFragmentMassesWithSeq(protein, 'by')` and `'cz'` (prefix +
suffix neutral masses for charge 0), then `sort()`. In Insight, compute these from
`calculate_fragment_masses_pyopenms(sequence)` (it already produces `fragment_masses_b/c/x/y/z`
and `a`); the oracle's `by`+`cz` terminal set == flatten of `b, y, c, z` neutral masses. Use
those four families' neutral masses, sorted, as `terminal_masses`. (Equivalent to oracle's
`byp+bys+czp+czs`: `byp≈b`, `bys≈y`, `czp≈c`, `czs≈z`.)

`_is_match_with_tolerance(A_sorted, t, ppm)` — port `isMatchWithTolerance` verbatim (binary
search, `tolerance = t*ppm/1e6`, returns True if any `|A[mid]-t| <= tolerance`).

### 3.3 Edge cases (call out explicitly — these are the parity traps)

1. **Min length 5**: `if j < i + min_length - 1: continue`. With `min_length=5`, the smallest
   emitted fragment spans 5 residues (`j-i+1 == 5`). Off-by-one here is the #1 risk.
2. **End index reaches the C-terminus**: the `j`-loop runs to `L-1`, so `end = j+1` can equal
   `L` and the fragment **includes the last residue**. Only the *start* is barred from the
   last position (`if i == L-1: break`). Do not clamp `end` to `L-1`.
3. **First/last start barred**: `i==0` skipped; `i==L-1` breaks. So `start` ∈ `[1, L-2]`.
4. **`start`/`end` index conventions are asymmetric on purpose**: `start` is **0-based**,
   `end` is **1-based**. The Vue fill rule `aaIndex > start && aaIndex <= end` depends on this
   exact convention. Emit them exactly as the oracle does (`i` and `j+1`).
5. **Ambiguous modifications emit TWO masses**: when a mod only partially overlaps the
   internal window (`(s>=i+1) or (e<=j+1)` but not fully contained), the oracle appends a
   second candidate `mass + m` while keeping the unmodified `mass`. Both become separate
   emitted entries (same `start`/`end`, different mass) → both can independently match. Fully
   contained mods are added unconditionally to the single candidate. (Mirror of the terminal
   `getFragmentDataFromSeq` ambiguous-mod logic, but with internal-window bounds.)
6. **Terminal collision filter is per-candidate**: applied inside the `for mm in possible_masses`
   loop, so an ambiguous pair can have one variant dropped and the other kept.
7. **`by` and `cz` are one family**: `getInternalFragmentDataFromSeq` iterates
   `['by','bz','cy']` only, commenting `# by cz are the same`. Emit exactly three families.
8. **Unknown residues**: oracle `aa_masses` maps `X`/`Z` → `0` (and includes `U`). Keep this
   table verbatim so masses match; do **not** fall back to pyOpenMS for the internal residue
   sum (the oracle uses its own `aa_masses` dict, not pyOpenMS, for internal fragments).

### 3.4 Python to add to `sequenceview.py`

```python
# --- internal fragment math (ported from FLASHApp/src/render/sequence.py) ---
H2O_INTERNAL = 18.010564683
NH3_INTERNAL = 17.0265491015

INTERNAL_AA_MASSES = {  # verbatim from sequence.py aa_masses
    "A":71.037114,"R":156.101111,"N":114.042927,"D":115.026943,"C":103.009185,
    "E":129.042593,"Q":128.058578,"G":57.021464,"H":137.058912,"I":113.084064,
    "L":113.084064,"K":128.094963,"M":131.040485,"F":147.068414,"P":97.052764,
    "S":87.032028,"T":101.047679,"U":150.953633405,"W":186.079313,"Y":163.063329,
    "V":99.068414,"X":0,"Z":0,
}

def _internal_shift(res_type: str) -> float:
    if res_type in ("by", "cz"):
        return -H2O_INTERNAL
    if res_type == "bz":
        return -H2O_INTERNAL - NH3_INTERNAL
    return -H2O_INTERNAL + NH3_INTERNAL  # "cy"

def _is_match_with_tolerance(sorted_masses, target, ppm):
    tol = target * ppm / 1e6
    lo, hi = 0, len(sorted_masses) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if abs(sorted_masses[mid] - target) <= tol:
            return True
        elif sorted_masses[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return False

def compute_internal_fragment_masses(
    residues, res_type, *, min_length=5, modifications=None,
    terminal_masses=None, terminal_collision_ppm=10.0,
):
    shift = _internal_shift(res_type)
    masses, starts, ends = [], [], []
    L = len(residues)
    for i in range(L):
        if i == 0:
            continue
        if i == L - 1:
            break
        mass = 0.0
        for j in range(L):
            if j >= i:
                mass += INTERNAL_AA_MASSES[residues[j]]
            if j < i + min_length - 1:
                continue
            candidates = [mass]
            if modifications is not None:
                for (s, e, m) in modifications:
                    if (s >= i + 1) and (e <= j + 1):
                        candidates[0] += m
                    elif (s >= i + 1) or (e <= j + 1):
                        candidates.append(mass + m)
            for mm in candidates:
                if terminal_masses is not None and _is_match_with_tolerance(
                    terminal_masses, mm, terminal_collision_ppm
                ):
                    continue
                masses.append(mm + 18.010564683 + shift)
                starts.append(i)
                ends.append(j + 1)
    return masses, starts, ends

def compute_internal_fragment_data(
    residues, *, ion_types=("by", "bz", "cy"), min_length=5,
    modifications=None, terminal_masses=None,
    remove_terminal_collisions=True, terminal_collision_ppm=10.0,
):
    term = terminal_masses if remove_terminal_collisions else None
    out = {}
    for it in ion_types:
        m, s, e = compute_internal_fragment_masses(
            residues, it, min_length=min_length, modifications=modifications,
            terminal_masses=term, terminal_collision_ppm=terminal_collision_ppm,
        )
        out[f"fragment_masses_{it}"] = m
        out[f"start_indices_{it}"] = s
        out[f"end_indices_{it}"] = e
    return out
```

The `terminal_masses` for the collision filter are built from the existing
`calculate_fragment_masses_pyopenms(sequence_str)` result: flatten the per-position lists for
families `b, c, x, y` (oracle uses by+cz prefix/suffix == b,y,c,z neutral masses), sort
ascending. (Use a helper `_terminal_collision_masses(fragment_masses) -> sorted list`.)

### 3.5 The Vue matcher (kept in Vue, ported into the unified component — see §5)

Oracle `filterMatchingMasses(observed, theo, starts, ends, target)`: for each theoretical
internal mass, scan observed masses; if `abs((observed-theo)/theo*1e6) <= tolerance`, push
`{mass: theo, start, end}` and **break** (first match wins per fragment). This is the
ppm-only matcher; reproduce exactly. (No charge-state expansion — observed values are already
deconvolved neutral masses, matching how the internal map only ever consumes
`MonoMass`.)

### 3.6 Derived **golden** numbers (for the numeric test in §6)

Input: `residues = list("PEPTIDEK")` (L=8), `min_length=5`, `modifications=None`,
`remove_terminal_collisions=False` (isolate the enumeration math from the collision filter).
Computed by faithfully executing the ported algorithm:

`fragment_masses_by` (net `+0`), with `(start, end, residues)`:

| start | end | residues | mass (by) |
|---|---|---|---|
| 1 | 6 | EPTID | 555.254043 |
| 1 | 7 | EPTIDE | 684.296636 |
| 1 | 8 | EPTIDEK | 812.391599 |
| 2 | 7 | PTIDE | 555.254043 |
| 2 | 8 | PTIDEK | 683.349006 |
| 3 | 8 | TIDEK | 586.296242 |

`fragment_masses_bz` = `by_mass - NH3` (i.e. each by-mass `- 17.026549`):
`538.227494, 667.270087, 795.365050, 538.227494, 666.322457, 569.269693`
(same `start_indices`/`end_indices` as `by`).

`fragment_masses_cy` = `by_mass + NH3` (each by-mass `+ 17.026549`):
`572.280592, 701.323185, 829.418148, 572.280592, 700.375555, 603.322791`.

`start_indices_*` = `[1,1,1,2,2,3]`, `end_indices_*` = `[6,7,8,7,8,8]` for all three families.

Pin these exact values (abs tol `1e-4`). They encode all the parity traps: min-length-5 start
(`EPTID`), end reaching the C-terminus (`end=8`, includes `K`), `start∈[1,6]`, and the three
family shifts.

> A second golden case should pin the **ambiguous-modification fork** and the **terminal
> collision drop**: e.g. `modifications=[(2, 4, 79.966331)]` (a phospho ambiguous over
> residues 2..4, 1-based) on `PEPTIDEK` and assert that windows partially overlapping
> `[2,4]` emit **two** entries (unmodified + `+79.966331`) at the same `(start,end)`, while a
> window fully containing `[2,4]` emits a **single** shifted entry. Derive the exact numbers
> by running the ported function once and freezing the output (the spec's algorithm is the
> source of truth).

---

## 4. `_prepare_vue_data` additions + `_get_component_args` keys

### 4.1 `_prepare_vue_data(state)` additions

After the existing terminal `fragment_masses = calculate_fragment_masses_pyopenms(...)`,
when `self._internal_fragments` is True, compute and attach the internal-fragment payload to
`sequence_data` (so it rides the same `sequenceData` object the Vue already consumes):

```python
if self._internal_fragments:
    terminal_masses = _terminal_collision_masses(fragment_masses)  # sorted b,c,x,y neutrals
    internal = compute_internal_fragment_data(
        residues,
        ion_types=self._internal_fragment_config["ion_types"],
        min_length=self._internal_fragment_config["min_length"],
        modifications=None,  # Phase-1 plain path; wire proteoform mods later
        terminal_masses=terminal_masses,
        remove_terminal_collisions=self._internal_fragment_config["remove_terminal_collisions"],
        terminal_collision_ppm=self._internal_fragment_config["terminal_collision_ppm"],
    )
    sequence_data.update(internal)  # adds fragment_masses_by/bz/cy + start_/end_ indices
    sequence_data["internal_fragments"] = True
    sequence_data["internal_fragment_tolerance"] = self._internal_fragment_config["tolerance"]
    sequence_data["internal_fragment_tolerance_ppm"] = self._internal_fragment_config["tolerance_ppm"]
```

Exact keys added to the `sequenceData` payload (one set, matching
`internal-fragment-data.ts`):

```
fragment_masses_by : number[]      start_indices_by : number[]   end_indices_by : number[]
fragment_masses_bz : number[]      start_indices_bz : number[]   end_indices_bz : number[]
fragment_masses_cy : number[]      start_indices_cy : number[]   end_indices_cy : number[]
internal_fragments : bool
internal_fragment_tolerance : number
internal_fragment_tolerance_ppm : bool
```

`observedMasses` / `peakIds` are already emitted by the existing `_prepare_vue_data`; the
internal matcher reuses `observedMasses` as the per-scan `MonoMass` analogue. **No new
top-level keys are required for matching** — only the `sequenceData.*` internal arrays above.
The change-detection hash should incorporate the internal payload length so a flag/config
change re-renders:

```python
hash_input = f"{sequence_str}:{peaks_df.height}:{precursor_charge}:{int(self._internal_fragments)}"
```

> Naming note: the internal arrays are **flat `number[]`** (one entry per matched/enumerated
> fragment), NOT the per-position `number[][]` used by terminal `fragment_masses_a..z`.
> Keep them distinct keys (`_by/_bz/_cy`) so they never collide with terminal families.

### 4.2 `_get_component_args()` keys

Add, only when internal mode is on (so existing callers/screenshots are unaffected):

```python
if self._internal_fragments:
    args["internalFragments"] = True
    args["internalFragmentConfig"] = {
        "tolerance": self._internal_fragment_config["tolerance"],
        "tolerancePpm": self._internal_fragment_config["tolerance_ppm"],
    }
```

`componentType` stays `"SequenceView"` (the same Vue component renders both the terminal map
and, when `args.internalFragments` is true, the internal map sub-view — see §5). `height`,
`deconvolved`, `title`, `interactivity` unchanged.

### 4.3 `_get_cache_config()` / `_load_from_cache()`

Add `internal_fragments` and `internal_fragment_config` to the dict returned by
`_get_cache_config()` and restore them in `_load_from_cache()` (mirroring `deconvolved` /
`annotation_config`). Initialize defaults in the creation branch of `__init__`:

```python
self._internal_fragments = internal_fragments
self._internal_fragment_config = {
    "min_length": 5, "ion_types": ["by", "bz", "cy"],
    "tolerance": 10.0, "tolerance_ppm": True,
    "remove_terminal_collisions": True, "terminal_collision_ppm": 10.0,
}
if internal_fragment_config:
    self._internal_fragment_config.update(internal_fragment_config)
```

Also add `internal_fragments`/`internal_fragment_config` to the `has_config` predicate in
`__init__` so reconstruction-mode validation stays correct.

---

## 5. Vue plan

Strategy: **one new sub-component** `InternalFragmentMap.vue` under
`js-component/src/components/sequence/`, rendered by the existing `SequenceView.vue` **below**
the terminal map when `args.internalFragments === true`. This keeps `App.vue` dispatch
(`componentType: 'SequenceView'`) unchanged and reuses the same data payload, while keeping
the dense bar-map markup isolated (it shares nothing with `AminoAcidCell`).

### 5.1 New file: `js-component/src/components/sequence/InternalFragmentMap.vue`

Port the oracle `InternalFragmentMap.vue` markup/CSS verbatim with these adaptations to
Insight's data plumbing (the oracle reads FLASHApp-specific stores; Insight reads
`allDataForDrawing`):

- Props: `{ sequence: string[], internalData: InternalFragmentData,
  observedMasses: number[], tolerance: number, toleranceIsPpm: boolean }`
  (passed down from `SequenceView.vue`). No direct store access for data → testable, decoupled.
- Keep `data()`: `fragmentDisplayOverlay=false, fragOpacity=0.2, fragOpacityMin=0.01,
  fragOpacityMax=1`, and local `fragmentMassTolerance`/`fragmentMassToleranceUnit` seeded from
  props (defaults `10`/`'ppm'`).
- `byData/cyData/bzData` computeds → call the ported `filterMatchingMasses(observedMasses,
  internalData.fragment_masses_<fam>, internalData.start_indices_<fam>,
  internalData.end_indices_<fam>, target)` exactly (§3.5). Eligibility gate: return `[]` when
  `observedMasses.length === 0`. (This is the Insight equivalent of the oracle's
  `PrecursorMass===0 && !displayTnT` guard — empty observed list ⇒ no bars.)
- Keep `fragmentClasses(aaIndex, start, end, className)` verbatim
  (`aaIndex > start && aaIndex <= end`).
- Keep all CSS classes/colors verbatim: `.by-fragment{#f0a441}`, `.cy-fragment{#12871d}`,
  `.bz-fragment{#7831cc}`, `-overlayed` opacity, `.not-in-fragment{transparent}`, legend
  swatches, `.sequence-text{font-size:8px}`, `.fragment-segment{aspect-ratio:1}`.
- Keep `fragmentStyle` height formula `(94 / sequence.length).toFixed(2)+'vw'` and the
  `--frag-block-opacity-value` wiring; keep DOM group order **by, cy, bz**.
- Keep `SvgScreenshot` over `#internal-fragment-part` (Insight has an `ui/SvgScreenshot.vue`
  equivalent; if absent, render the screenshot button as a no-op stub for parity layout —
  note it as a follow-up rather than blocking).
- Display-only: **no** `selectionStore` writes, **no** `setAnnotations`.

### 5.2 `SequenceView.vue` changes (extend, minimal)

- `import InternalFragmentMap from './InternalFragmentMap.vue'` and register it.
- Add computeds:
  - `internalFragments(): boolean` → `this.args.internalFragments === true`.
  - `internalData(): InternalFragmentData | undefined` → assembled from
    `this.sequenceData` fields (`fragment_masses_by/bz/cy`, `start_indices_*`,
    `end_indices_*`); return `undefined` if `!this.sequenceData?.internal_fragments`.
- In `<template>`, after the existing terminal fragment table block, add:
  ```html
  <InternalFragmentMap
    v-if="internalFragments && internalData"
    :sequence="sequence"
    :internal-data="internalData"
    :observed-masses="observedMasses"
    :tolerance="sequenceData?.internal_fragment_tolerance ?? 10"
    :tolerance-is-ppm="sequenceData?.internal_fragment_tolerance_ppm ?? true"
  />
  ```
- No change to `matchFragments`, annotations, or selection routing — internal map is additive
  and display-only.

### 5.3 `types/sequence-data.ts` additions

Add the internal fields to `SequenceData` (all optional) and add the `InternalFragmentData`
type (mirror the oracle `internal-fragment-data.ts`, restricted to by/bz/cy):

```ts
export interface InternalFragmentData {
  fragment_masses_by: number[]; start_indices_by: number[]; end_indices_by: number[]
  fragment_masses_bz: number[]; start_indices_bz: number[]; end_indices_bz: number[]
  fragment_masses_cy: number[]; start_indices_cy: number[]; end_indices_cy: number[]
}

// add to interface SequenceData:
//   internal_fragments?: boolean
//   internal_fragment_tolerance?: number
//   internal_fragment_tolerance_ppm?: boolean
//   fragment_masses_by?: number[]; start_indices_by?: number[]; end_indices_by?: number[]
//   fragment_masses_bz?: number[]; start_indices_bz?: number[]; end_indices_bz?: number[]
//   fragment_masses_cy?: number[]; start_indices_cy?: number[]; end_indices_cy?: number[]
```

### 5.4 `types/component.ts` additions

Extend `SequenceViewComponentArgs`:

```ts
/** When true, render the internal-fragment map below the terminal sequence map. */
internalFragments?: boolean
/** Default tolerance/unit for the internal-fragment matcher. */
internalFragmentConfig?: { tolerance?: number; tolerancePpm?: boolean }
```

### 5.5 Dispatch / args changes

`App.vue`: **no change** (still `case 'SequenceView': return SequenceView`). The internal map
is a child of `SequenceView`, gated by `args.internalFragments`. `streamlit-data.ts` requires
no change — the internal arrays arrive inside the existing `sequenceData` payload, which is
already merged into `dataForDrawing`.

---

## 6. Tests

### 6.1 NUMERIC GOLDEN test (pins the ported math) — `tests/test_sequenceview_internal.py`

```python
import math
from openms_insight.components.sequenceview import (
    compute_internal_fragment_data, compute_internal_fragment_masses,
)

NH3 = 17.0265491015

def test_internal_fragment_golden_PEPTIDEK_no_mods_no_collision():
    residues = list("PEPTIDEK")
    data = compute_internal_fragment_data(
        residues, ion_types=("by", "bz", "cy"), min_length=5,
        modifications=None, remove_terminal_collisions=False,
    )
    # start/end indices identical across families
    for fam in ("by", "bz", "cy"):
        assert data[f"start_indices_{fam}"] == [1, 1, 1, 2, 2, 3]
        assert data[f"end_indices_{fam}"]   == [6, 7, 8, 7, 8, 8]

    expected_by = [555.254043, 684.296636, 812.391599,
                   555.254043, 683.349006, 586.296242]
    for got, exp in zip(data["fragment_masses_by"], expected_by):
        assert math.isclose(got, exp, abs_tol=1e-4)
    # bz = by - NH3 ; cy = by + NH3 (family-shift invariant)
    for by, bz, cy in zip(data["fragment_masses_by"],
                          data["fragment_masses_bz"],
                          data["fragment_masses_cy"]):
        assert math.isclose(bz, by - NH3, abs_tol=1e-6)
        assert math.isclose(cy, by + NH3, abs_tol=1e-6)

def test_internal_min_length_enforced():
    # Smallest fragment spans exactly 5 residues; none shorter appears.
    residues = list("PEPTIDEK")
    _m, s, e = compute_internal_fragment_masses(
        residues, "by", min_length=5, terminal_masses=None)
    assert all((end - start) >= 5 for start, end in zip(s, e))  # end is 1-based, start 0-based
    # first/last start positions barred
    assert min(s) >= 1 and max(s) <= len(residues) - 2

def test_internal_end_can_reach_cterminus():
    residues = list("PEPTIDEK")
    _m, _s, e = compute_internal_fragment_masses(residues, "by", terminal_masses=None)
    assert max(e) == len(residues)  # includes the last residue (K)
```

### 6.2 Ambiguous-modification fork test (derive-then-freeze)

```python
def test_internal_ambiguous_modification_forks():
    residues = list("PEPTIDEK")
    mods = [(2, 4, 79.966331)]  # 1-based start/end inclusive (phospho), ambiguous
    _m, s, e = compute_internal_fragment_masses(
        residues, "by", min_length=5, modifications=mods, terminal_masses=None)
    # Some (start,end) windows appear twice (unmodified + +79.966331 variant)
    from collections import Counter
    pairs = Counter(zip(s, e))
    assert any(c == 2 for c in pairs.values()), "ambiguous mod must fork into two masses"
```
(Freeze the exact mass list once by running the implementation; assert it for full pinning.)

### 6.3 Terminal-collision filter test

```python
def test_internal_terminal_collision_drops_entries():
    residues = list("PEPTIDEK")
    base = compute_internal_fragment_data(residues, remove_terminal_collisions=False)
    # Provide a terminal mass list that exactly equals one emitted internal 'by' mass
    target = base["fragment_masses_by"][0]
    filtered = compute_internal_fragment_masses(
        residues, "by", terminal_masses=[target - 18.010564683],  # pre-shift residue sum
        terminal_collision_ppm=10.0)
    # the colliding entry is removed
    assert len(filtered[0]) < len(base["fragment_masses_by"])
```
(Compute the exact pre-shift residue-sum used by the collision test from the algorithm; the
filter compares the *pre-`+H2O+shift`* candidate `mm` against `terminal_masses`.)

### 6.4 Contract tests (component wiring) — extend `test_sequenceview.py`

- `test_internal_flag_adds_keys_to_vue_data`: build `SequenceView(..., internal_fragments=True)`
  on `sample_sequence_data`/`sample_peaks_data`; call `_prepare_vue_data({"spectrum": <scan>})`;
  assert `sequenceData["internal_fragments"] is True` and that all nine
  `fragment_masses_by/bz/cy` + `start_indices_*` + `end_indices_*` keys are present and are
  flat lists.
- `test_internal_flag_off_no_keys`: default `internal_fragments=False` → none of the nine
  internal keys present (no regression to existing payload).
- `test_internal_component_args`: `_get_component_args()` has `internalFragments == True` and
  `internalFragmentConfig.tolerance == 10.0` when on; **absent** when off.
- `test_internal_cache_roundtrip`: construct with `internal_fragments=True`, then reconstruct
  from cache (no data) and assert `_internal_fragments is True` and config restored
  (exercises `_get_cache_config`/`_load_from_cache`).
- `test_internal_config_requires_data`: `SequenceView(cache_id=..., internal_fragments=True)`
  with no `sequence_data` raises `ValueError` (the `has_config` gate).
- `test_internal_empty_sequence_safe`: empty sequence (filter None) → internal arrays are all
  `[]`, no exception.

### 6.5 Vue parity gate

`npm run build` must pass; the structural parity probe (`migration/parity_diff.py`) should
include `InternalFragmentMap.vue` presence + the three family colors + the `fragmentClasses`
fill predicate (string-level) so accidental color/predicate drift is caught.

---

## 7. Concrete file-by-file change list

**Python (`openms_insight/components/sequenceview.py`)**
1. Add module constants `H2O_INTERNAL`, `NH3_INTERNAL`, `INTERNAL_AA_MASSES` (verbatim from
   `sequence.py`).
2. Add functions `_internal_shift`, `_is_match_with_tolerance`,
   `compute_internal_fragment_masses`, `compute_internal_fragment_data`,
   `_terminal_collision_masses(fragment_masses) -> list[float]` (flatten b,c,x,y neutral
   masses, sorted).
3. `__init__`: add `internal_fragments=False`, `internal_fragment_config=None`; set
   `self._internal_fragments`, `self._internal_fragment_config` (with defaults merge);
   include both in the `has_config` predicate.
4. `_get_cache_config`: add `internal_fragments`, `internal_fragment_config`.
5. `_load_from_cache`: restore `self._internal_fragments`, `self._internal_fragment_config`.
6. `_prepare_vue_data`: when on, compute internal payload, `sequence_data.update(...)`, set
   `internal_fragments`/`internal_fragment_tolerance`/`_ppm`; fold `internal_fragments` into
   the `data_hash` input.
7. `_get_component_args`: when on, add `internalFragments` + `internalFragmentConfig`.

**Vue (`js-component/src/components/sequence/`)**
8. **New** `InternalFragmentMap.vue` — ported oracle markup/CSS, prop-driven, display-only,
   `filterMatchingMasses` ppm matcher, eligibility gate on empty `observedMasses`.
9. `SequenceView.vue` — import/register `InternalFragmentMap`; add `internalFragments` /
   `internalData` computeds; render `<InternalFragmentMap v-if=...>` below the fragment table.

**Types**
10. `js-component/src/types/sequence-data.ts` — add `InternalFragmentData` type + optional
    internal fields on `SequenceData`.
11. `js-component/src/types/component.ts` — add `internalFragments?` and
    `internalFragmentConfig?` to `SequenceViewComponentArgs`.

**Tests**
12. **New** `tests/test_sequenceview_internal.py` — golden math (§6.1), min-length/end/start
    edge cases, ambiguous-mod fork (§6.2), terminal-collision drop (§6.3).
13. `tests/test_sequenceview.py` — contract tests (§6.4): payload keys on/off, component args,
    cache roundtrip, config-requires-data, empty-sequence safety.
14. (Optional) `migration/parity_diff.py` — add `InternalFragmentMap` structural probe (§6.5).

**Unchanged (call out so reviewers don't expect edits):** `App.vue` dispatch,
`stores/streamlit-data.ts`, `core/base.py`, `core/registry.py`. FLASHApp oracle files are
read-only and untouched.

---

## 8. Parity checklist (acceptance)

- [ ] Three families only: `by` (`#f0a441`, label `by/cz`), `bz` (`#7831cc`), `cy`
      (`#12871d`); DOM render order by, cy, bz; legend order by/cz, bz, cy.
- [ ] Fill predicate `aaIndex > start && aaIndex <= end` byte-identical.
- [ ] Cell height `(94/len).toFixed(2)+'vw'`; stacked/overlay modes + opacity slider
      (default 0.2) preserved.
- [ ] ppm-only matcher, first-match-wins per fragment; tolerance default 10 ppm.
- [ ] Math: min-length 5, `start∈[1,L-2]` (0-based), `end∈[..,L]` (1-based, includes
      C-terminus), `by`/`cz` collapsed, `bz=by-NH3`, `cy=by+NH3`.
- [ ] Ambiguous mods fork into two candidates at the same `(start,end)`; fully-contained mods
      add once.
- [ ] Terminal-collision filter on by default (10 ppm) for parity.
- [ ] Internal map is display-only (no selection/annotations).
- [ ] Golden numeric test green; `npm run build` green; existing `SequenceView` tests
      unaffected when `internal_fragments=False`.
