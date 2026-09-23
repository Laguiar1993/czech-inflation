"""R25 scoring: the core block first, then the assembled path with the standard diagnostics.

    python -m tools.research_r25.evaluate --root output/research_r25/final
"""
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from tools.path_diagnostics import standard, gates

LABELS = {'CORE_PANEL_SHRINK_R25': 'Core: panel persistence', 'CORE_PANEL_STATE_R25': 'Core: panel persistence, two regimes',
          'CORE_OWN_SHRINK_R25': 'Core: Czech-only persistence (control)', 'CORE_PANEL_SHRINK_FOODNORM_R25': 'Panel core + long-history food drift'}
METHOD = [
    'R25: the share of the FAST core trend deviation from a robust norm that survives to each three-month band, estimated in real time on an EU HICP-core panel that excludes Czechia, then applied to the saved Czech FAST path. Original 90 origins and 969 primary keys. Historical research, not a live or untouched holdout record.',
    'Every panel country is filtered with the unchanged R15 filter and its own-origin seasonal pattern, exactly like Czech core. Only the persistence weight is borrowed from the panel; no level, forecast or Czech observation comes from it.',
    'The norm is the median of overlapping twelve-month log changes available at the origin. The band weight is a pooled no-intercept regression of realised deviation on forecast deviation, clipped to [0, 1], using only bands published by the Czech clock.',
    'Candidates: one weight per band; two weights split at the real-time median deviation; a Czech-only control; and the single-weight core combined with the separately declared R24 food drift. h0 and the other blocks are untouched.',
    'The HICP aggregate is not the CNB core measure and the frozen panel ends in December 2025. No survey, CNB forecast or future realised driver enters the independent predictions.',
    'Lead tables flag abs(model-CNB)>=0.30pp (0.50 sensitivity) against the immediately next CNB report for the same still-future quarter, with base-rate rows passed through the same rules.',
    'Defaults show FAST with the single-weight panel candidate and the combination; no promotion is implied.']


def needed_applied(frame, models):
    rows = []; fast = frame[frame.model.eq(c.FAST)].set_index(['origin', 'h'])
    for h in (3, 6, 12):
        base = fast.xs(h, level='h'); needed = (base.core_cumulative_log_actual - base.core_cumulative_log_forecast).dropna()
        for model in models:
            own = frame[frame.model.eq(model) & frame.h.eq(h)].set_index('origin')
            applied = (own.core_cumulative_log_forecast - base.core_cumulative_log_forecast).reindex(needed.index)
            for sample, rule in standard.ERAS.items():
                keep = needed.index[rule(needed.index.to_numpy().astype(str))]
                rows.append(dict(model=model, h=h, sample=sample, **gates.needed_vs_applied(needed.loc[keep], applied.loc[keep])))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--root', type=Path, required=True); args = ap.parse_args()
    out, _ = standard.standard_evaluation(args.root, 'R25', LABELS, METHOD, defaults={c.FAST, 'CORE_PANEL_SHRINK_R25', 'CORE_PANEL_SHRINK_FOODNORM_R25'})
    frame = pd.read_csv(out / 'forecast_core_outcomes.csv', low_memory=False)
    needed_applied(frame, list(LABELS)).to_csv(out / 'needed_vs_applied.csv', index=False)
    same = pd.read_csv(out / 'same_support_scoreboard.csv'); core = same[same.metric.eq('core_cumulative_log')].copy()
    reference = core[core.model.eq(c.FAST)].set_index(['h', 'sample']).rmse
    core['rmse_vs_fast_pct'] = [100 * (r.rmse / reference.get((r.h, r.sample), np.nan) - 1) for r in core.itertuples()]
    core.to_csv(out / 'core_block_scores.csv', index=False)
    standard.close_manifest(out, extra_code=[Path(__file__)])
    print('Completed R25 evaluation', out, flush=True)


if __name__ == '__main__':
    main()
