# Migration harness — OpenMS-Insight as FLASHApp's plotting backend

This directory tracks the **parity migration** that makes OpenMS-Insight the single
plotting backend for FLASHApp. It is process/tracking infrastructure — it ships no
runtime behavior and is not imported by the library.

Goal (high-stakes, non-negotiable): **feature parity** with FLASHApp's existing
visualizations, enforced by iterative multi-agent review loops that converge
(**≥3 consecutive clean rounds** per phase).

## Phases (this repo owns 1 & 2)

- **Phase 1 — Parity.** Port every FLASHApp visualization onto Insight's component
  set (`Table, Heatmap, LinePlot, MirrorPlot, VolcanoPlot, SequenceView, Plot3D`),
  adding new components/modes where needed. Each unit is checked against its
  **oracle** = the old code whose behavior must be reproduced.
- **Phase 2 — Simplification & generalization.** Lock a minimal-but-powerful public
  surface; promote broadly-useful concepts into clean generic interfaces.

Phase 3 (FLASHApp page rebuild) is tracked in `FLASHApp/migration/`.

## Oracles (read-only reference — never edited)

- Old Vue components: `/home/user/openms-streamlit-vue-component/src/components/…`
- Old FLASHApp render layer: `/home/user/FLASHApp/src/render/…`
  (`update.py` is the authoritative index→value selection oracle.)

## Files

- `units.yaml` — review-unit registry (id → target → oracle → concern) + per-phase
  machine-gate command definitions and the convergence target.
- `run_review.py` — convergence driver: `record` results, run the `gate`, and
  `report` per-round cleanliness + the consecutive-clean counter (exit 0 iff converged).
- `parity_diff.py` — machine-gate snapshot harness (structural parity probes vs. baselines).
- `review-log/phase-{1,2}.jsonl` — append-only ledger of review + gate records.
- `REVIEW.md` — human-readable rollup.
- `COMPONENT_MAP.md`, `specs/` — produced by Phase 1 agents (map → per-component specs).

## How a round works (driven by the session's `/goal` loop)

1. Fan out one review agent per unit; each diffs the new behavior against its oracle
   and records `clean` or a `finding` via
   `python migration/run_review.py record --phase N --round R --unit U --status …`.
2. Run the machine gate:
   `python migration/run_review.py gate --phase N --round R`
   (pytest + `npm run build` + `parity_diff.py`).
3. Fixers consume open findings; the next round re-verifies **and** re-scans for regressions.
4. `python migration/run_review.py report --phase N` prints the rollup + the
   `CONSECUTIVE CLEAN ROUNDS: k / 3` line the `/goal` evaluator watches for.

A round is **clean** iff every unit is `clean` AND every gate step passed. Any new
finding resets the consecutive-clean counter to 0.
