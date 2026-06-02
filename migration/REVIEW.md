# Migration review rollup — OpenMS-Insight (Phases 1 & 2)

> Auto-context for the convergence loop. The live rollup matrix + the
> `CONSECUTIVE CLEAN ROUNDS: k / 3` counter are printed by
> `python migration/run_review.py report --phase N`.

## Status

| Phase | Description | Converged? |
|------:|-------------|:----------:|
| 1 | Parity — port every FLASHApp visualization onto Insight | ⏳ not started |
| 2 | Simplification & generalization of the public surface | ⏳ not started |

Convergence target: **≥3 consecutive clean rounds** (every unit clean + machine gate green).

## Baseline (Phase 0)

- Dev env prepared: editable install (`pip install -e ".[dev]"`) OK; `npm ci` OK;
  Vue bundle built and copied to `openms_insight/js-component/dist`.
- Machine gate green on the untouched `main` code: **pytest 398 passed**, `npm run build` OK.
- Unit registry: see `units.yaml` (Phase 1 = 23 parity units, Phase 2 = 8 API units).

## How findings are tracked

Findings get stable ids `PHASE-UNIT-NNN` with `status: open|fixed|wontfix`, recorded in
`review-log/phase-{1,2}.jsonl`. Any new finding resets the consecutive-clean counter to 0.
