# Migration review rollup — OpenMS-Insight (Phases 1 & 2)

> Auto-context for the convergence loop. The live rollup matrix + the
> `CONSECUTIVE CLEAN ROUNDS: k / 3` counter are printed by
> `python migration/run_review.py report --phase N`.

## Status

| Phase | Description | Converged? |
|------:|-------------|:----------:|
| 1 | Parity — port every FLASHApp visualization onto Insight | ✅ **CONVERGED** (11 rounds; rounds 9–11 clean + gate green) |
| 2 | Simplification & generalization of the public surface | ✅ **CONVERGED** (15 rounds; rounds 13–15 clean + gate green) |

### Phase 2 — CONVERGED

All 8 API units pass 3 consecutive fix-free 3-critic (simplicity / feature-parity /
reusability) rounds (13, 14, 15) with a green gate. Delivered: `base.py` render-config
split (S4 — presentation params render-time, not cache-invalidating); cross-component
naming convergence (`category_column`/`category_colors`, `trace_mode`, `tag_identifier`);
`LinePlot.density()/.tagger()` factories (minimal default signature); heatmap `downsample`
enum; docs for the 7-component surface + reusable generic interfaces; dead-code + docstring
sweeps. **3 genuine cache/correctness bugs fixed** (heatmap `reversescale` + `category_colors`
lost on reconstruction; MirrorPlot per-side annotations broken on the cache-hit path) plus a
regression the loop caught and fixed (`downsample_2d` `descending` TypeError), and
`low_values_on_top` now honored across all 10 downsample paths.

### Phase 1 — CONVERGED

All 23 parity units pass 3 consecutive fix-free full re-reviews (rounds 9, 10, 11),
each with a green machine gate (pytest 530/1-skip + `npm run build` + parity_diff +
vitest). New code delivered: `Plot3D` component; `LinePlot` `tagger`/`density` modes +
generic per-peak charge-annotation API; `Table` `fixed`/`placeholder` formatters;
`SequenceView` `internal_fragments` (ported `by/bz/cy` math) + per-residue coverage +
truncated/undetermined terminals; 5 ported Vue sources. 18 findings found & fixed across
rounds 1–8 (incl. tagger Level-1 content/zoom, heatmap categorical click routing, table
server-side go-to selection, charge-annotation geometry, internal-frag bug-for-bug parity).

Convergence target: **≥3 consecutive clean rounds** (every unit clean + machine gate green).

## Baseline (Phase 0)

- Dev env prepared: editable install (`pip install -e ".[dev]"`) OK; `npm ci` OK;
  Vue bundle built and copied to `openms_insight/js-component/dist`.
- Machine gate green on the untouched `main` code: **pytest 398 passed**, `npm run build` OK.
- Unit registry: see `units.yaml` (Phase 1 = 23 parity units, Phase 2 = 8 API units).

## How findings are tracked

Findings get stable ids `PHASE-UNIT-NNN` with `status: open|fixed|wontfix`, recorded in
`review-log/phase-{1,2}.jsonl`. Any new finding resets the consecutive-clean counter to 0.
