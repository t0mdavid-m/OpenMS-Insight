#!/usr/bin/env python3
"""
Parity-diff harness — a machine-gate step for the migration (run by run_review.py).

It runs a set of lightweight "probes". Each probe returns a JSON-able value that is
snapshotted against a baseline in migration/baselines/<name>.json:

  * first run (or --update) writes the baseline and the probe passes;
  * later runs FAIL the gate on any drift, until the baseline is intentionally
    refreshed with `python migration/parity_diff.py --update`.

Phase 1 fan-out agents register one probe per parity unit (e.g. golden
`_get_component_args()` + a sampled `_prepare_vue_data()` shape vs. its oracle).
Until a unit has its own probe it is covered by the agent review fan-out + pytest;
the seed probes below assert structural invariants that must always hold.

Exit code: 0 if all probes pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASELINE = ROOT / "baselines"
PROBES: dict = {}


def probe(name: str):
    def deco(fn):
        PROBES[name] = fn
        return fn
    return deco


# --------------------------------------------------------- seed structural probes
@probe("public_api")
def _public_api():
    """Public export surface + component_type uniqueness (anti-regression snapshot)."""
    import openms_insight as oi

    exported = sorted(getattr(oi, "__all__", []) or [n for n in dir(oi) if not n.startswith("_")])
    types = {}
    for name in exported:
        ct = getattr(getattr(oi, name, None), "_component_type", None)
        if ct:
            types[name] = ct
    vals = list(types.values())
    assert len(vals) == len(set(vals)), f"duplicate _component_type among {types}"
    assert all(vals), f"empty _component_type among {types}"
    return {"exported": exported, "component_types": types}


@probe("base_contract")
def _base_contract():
    """The BaseComponent contract methods every component/mode must keep."""
    from openms_insight.core.base import BaseComponent

    required = [
        "_prepare_vue_data", "_get_component_args", "get_filters_mapping",
        "get_interactivity_mapping", "get_state_dependencies", "__call__",
    ]
    missing = [m for m in required if not hasattr(BaseComponent, m)]
    assert not missing, f"BaseComponent missing contract methods: {missing}"
    return {"required_methods": required}


# ----------------------------------------------------------------------- runner
def run(update: bool) -> int:
    BASELINE.mkdir(exist_ok=True)
    failed = []
    for name, fn in sorted(PROBES.items()):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - report, do not crash the gate
            print(f"[parity-diff] {name}: ERROR {type(exc).__name__}: {exc}")
            failed.append(name)
            continue
        payload = json.dumps(result, sort_keys=True, indent=2, default=str)
        bpath = BASELINE / f"{name}.json"
        if update or not bpath.exists():
            bpath.write_text(payload)
            print(f"[parity-diff] {name}: baseline {'updated' if update else 'created'}")
        elif bpath.read_text() == payload:
            print(f"[parity-diff] {name}: OK")
        else:
            print(f"[parity-diff] {name}: DRIFT vs baseline (refresh with --update if intended)")
            failed.append(name)
    print(f"\n[parity-diff] {len(PROBES) - len(failed)}/{len(PROBES)} probes passing")
    return 1 if failed else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="structural parity-diff harness")
    ap.add_argument("--update", action="store_true", help="(re)write all baselines")
    args = ap.parse_args()
    sys.exit(run(args.update))


if __name__ == "__main__":
    main()
