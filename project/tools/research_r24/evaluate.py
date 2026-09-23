"""R24 scoring: the food block first, then the assembled path with the standard diagnostics.

    python -m tools.research_r24.evaluate --root output/research_r24/final
"""
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from tools.path_diagnostics import standard

LABELS = {'FOOD_ZERO_DRIFT_R24': 'Food: zero drift (control)', 'FOOD_ROBUST_WINDOW_R24': 'Food: robust window drift',
          'FOOD_NORM_SHIFT_R24': 'Food: long-history drift', 'FOOD_NORM_REFIT_R24': 'Food: long-history drift, refit'}
METHOD = [
    'R24: four declared food-drift candidates on the saved FAST path, original 90 origins and 969 primary keys. Only the food block of h1-12 changes; h0, core, fuel, administered prices, alcohol and tobacco, the wedge and all weights are untouched. Historical research, not a live or untouched holdout record.',
    'The frozen food system centres monthly rates on calendar-month means of a window of at most 96 months, so its forecasts decay to a centre that carries the window average drift, including the 2022 surge. Every candidate keeps the seasonal shape and the decaying deviation and replaces only that drift.',
    'Drift estimates use published observations only: zero (control); the median of overlapping twelve-month changes inside the training window; the same median over food history from 1996 (CZSO division 01 before February 2015, the model series after). The refit candidate re-estimates the system around the long-history centre.',
    'A lower drift would have under-predicted the 2021-22 surge even more. Every drift choice is a bet on regime and one inflation cycle cannot settle it; results are shown for origins 2019-21, 2022-23 and from 2024 as well as in full.',
    'No survey, CNB forecast or future realised driver enters the independent predictions. Current-vintage histories and assumed publication rules remain limitations. The block scores that motivated this round were seen before it was declared.',
    'Lead tables flag abs(model-CNB)>=0.30pp (0.50 sensitivity) against the immediately next CNB report for the same still-future quarter, with base-rate rows (constant 2%, random-walk annual rate, previous CNB, CNB momentum) passed through the same rules.',
    'Defaults show FAST with the long-history drift candidate; no promotion is implied. Every control and candidate remains selectable.']


def food_block_scores(out):
    """Food cumulative log change against realised, zero change and seasonal-naive, by era."""
    b = pd.read_csv(out / 'block_benchmarks.csv'); b = b[b.block.eq('food')].copy()
    reference = b[b.model.eq(c.FAST)].set_index(['H', 'sample']).model_rmse
    b['rmse_vs_baseline_pct'] = [100 * (r.model_rmse / reference.get((r.H, r.sample), np.nan) - 1) for r in b.itertuples()]
    return b.drop(columns='block')


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--root', type=Path, required=True); args = ap.parse_args()
    out, _ = standard.standard_evaluation(args.root, 'R24', LABELS, METHOD, defaults={c.FAST, 'FOOD_NORM_SHIFT_R24'})
    food_block_scores(out).to_csv(out / 'food_block_scores.csv', index=False)
    standard.close_manifest(out, extra_code=[Path(__file__)])
    print('Completed R24 evaluation', out, flush=True)


if __name__ == '__main__':
    main()
