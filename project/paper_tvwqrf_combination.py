"""Exploratory check E1 of PAPER_TVWQRF_SPEC_2026-09-12.md: combine the bridge and TVW-QRF paths.

For each origin and horizon, the combined monthly forecast is
``weight * INDEPENDENT_BRIDGE + (1 - weight) * TVW3``. The bridge's monthly path
is taken as stored on Board A; TVW3 comes from a real-time run, mapped by
``paper_tvwqrf_path.load_paths``.

The combined paths are scored on Board A only, using the board's functions with
h0 = HARD_BASE, the block bootstrap against the bridge and the declared checks.
Months where the bridge has no forecast stay missing, so the paired samples match
the bridge's own. The check was declared exploratory, so its result cannot make
a path challenger.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

import paper_tvwqrf_path as scorer

MODEL = "TVW3"


def bridge_paths(board: Path = scorer.BOARD_A) -> pd.DataFrame:
    frame = pd.read_csv(board, dtype={"origin": str, "target": str}, float_precision="round_trip")
    frame = frame[frame.model.eq(scorer.BASE)]
    return frame[["origin", "h", "mm_forecast"]].rename(columns={"mm_forecast": "bridge_mm"})


def combine_paths(bridge: pd.DataFrame, paths: pd.DataFrame, weight: float, label: str) -> pd.DataFrame:
    """Weighted monthly paths on the bridge's (origin, h) keys; a month missing on either side stays missing."""
    if not 0.0 <= weight <= 1.0:
        raise ValueError("weight must lie in [0, 1]")
    model = paths.assign(origin=paths.origin.astype(str))[["origin", "h", "mm_forecast"]]
    merged = bridge.merge(model, on=["origin", "h"], how="left")
    merged["mm_forecast"] = weight * merged.bridge_mm + (1.0 - weight) * merged.mm_forecast
    merged["origin"] = pd.PeriodIndex(merged.origin, freq="M")
    merged["target"] = merged.origin + merged.h
    merged["model"] = f"COMBO{round(100 * weight):02d}_BRIDGE_{MODEL}_{label}"
    return merged[["origin", "h", "target", "model", "mm_forecast"]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, help="LABEL=FOLDER of a real-time run")
    parser.add_argument("--weight", type=float, default=0.5, help="weight on INDEPENDENT_BRIDGE")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    headline = scorer.headline_series()
    bridge = bridge_paths()
    runs = dict(item.split("=", 1) for item in args.run)
    combined = []
    for label, folder in runs.items():
        paths = scorer.load_paths(Path(folder), label)
        combined.append(combine_paths(bridge, paths[paths.model.eq(f"TVWQRF_{MODEL}_{label}")], args.weight, label))
    paths = pd.concat(combined, ignore_index=True)
    a = scorer.board_a(paths, headline)
    for name, frame in a.items():
        frame.to_csv(output / f"board_a_{name}.csv", index=False)
    decisions = [scorer.decision(a["summary"], a["bootstrap"], m) for m in sorted(paths.model.unique())]
    (output / "decision.json").write_text(json.dumps(decisions, indent=2), encoding="utf-8")
    manifest = {"tool": "paper_tvwqrf_combination", "check": "E1 (exploratory)", "weight_on_bridge": args.weight,
                "created_at": datetime.now(timezone.utc).isoformat(), "runs": runs,
                "inputs": {str(p): scorer._sha(p) for p in (scorer.BOARD_A, scorer.BRIDGE, scorer.NOWCAST, scorer.HEADLINE, scorer.CNB)},
                "run_manifests": {label: scorer._sha(Path(folder) / "manifest.json") for label, folder in runs.items()},
                "tool_sha256": scorer._sha(Path(__file__)), "scorer_sha256": scorer._sha(Path(scorer.__file__))}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    view = a["summary"][a["summary"].scope.eq("all_common") & a["summary"]["sample"].eq("full")]
    print(view.pivot_table(index="model", columns="h", values="yy_rmse")[[1, 3, 6, 9, 12]].round(3).to_string())
    for d in decisions:
        print(d["model"], "passes the declared checks" if d["path_challenger"] else "fails the declared checks", d["checks"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
