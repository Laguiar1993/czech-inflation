"""B2. Poison test of `candidates_at` at every origin.

Variant P1: every agri/ppi/food LEVEL whose own publication stamp is after the origin's clock is replaced by a
            distinct huge number (so differences are huge too, never a harmless zero); the long history is
            rebuilt from the poisoned levels with the code under review.
Variant P2: clean levels, but every spliced long-history RATE stamped after the clock is set to 1e9.
Variant P3: P1 plus a poisoned copy of the CZSO file in which every division-01 base-index value from 2015-02
            onwards is 1e9 (tests that the CZSO file can only ever supply months before 2015-02).
Variant T : truncation instead of poison - rows at or after the origin month are dropped and unpublished
            cells are NaN, i.e. the function only ever sees what existed at the clock.

Pass = drifts, baseline log rates, all four candidate log-rate paths and simple-rate paths are bit-identical
(==, not allclose) to the clean call, and equal to the frozen run's fits.jsonl.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import probe_common as pc
from models.food_path_r14 import load_inputs
from models.food_drift_r24 import long_food_rates, candidates_at, LONG_HISTORY

SCRATCH = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE
levels, available, _ = load_inputs()
stamps = pc.load_available()
long_rates, long_published = long_food_rates(levels, available, ROOT / LONG_HISTORY)
clk = pc.clocks()
frozen = {json.loads(line)['origin']: json.loads(line) for line in (pc.R24 / 'fits.jsonl').read_text(encoding='utf-8').splitlines()}

# poisoned CZSO copy (P3)
raw = pd.read_csv(ROOT / LONG_HISTORY, dtype=str)
late = raw.ucel_kod.eq('01') & raw.casz_kod.eq('Z') & ((raw.rok.astype(int) > 2015) | ((raw.rok.astype(int) == 2015) & (raw.mesic.astype(int) >= 2)))
poisoned_csv = SCRATCH / 'czso_poisoned_from_2015_02.csv'
raw.assign(hodnota=raw.hodnota.where(~late, '1000000000')).to_csv(poisoned_csv, index=False)
print('CZSO rows poisoned (division 01, base index, 2015-02..2025-12):', int(late.sum()))
p3_rates, p3_published = long_food_rates(levels, available, poisoned_csv)
print('Long history built from the poisoned CZSO copy is identical to the clean one:', bool(p3_rates.equals(long_rates) and p3_published.equals(long_published)))


def same(a, b):
    ok = a['status'] == b['status'] and a['drifts'] == b['drifts'] and a['baseline_log_rates'] == b['baseline_log_rates']
    ok = ok and a['log_rates'] == b['log_rates'] and a['paths'] == b['paths'] and a['baseline_path'] == b['baseline_path'] and a['refit'] == b['refit']
    return bool(ok)


rows = []
for origin in sorted(clk):
    clock = clk[origin]; t = pd.Period(origin, 'M')
    clean = candidates_at(levels, available, long_rates, long_published, origin, clock)
    # P1
    lp = levels.copy(); n_poison = 0
    for col in lp.columns:
        bad = (stamps[col] > clock).to_numpy() | (lp.index >= t)
        lp.loc[bad, col] = 1e9 * (2 + np.arange(bad.sum()))
        n_poison += int(bad.sum())
    r1, s1 = long_food_rates(lp, available, ROOT / LONG_HISTORY)
    p1 = candidates_at(lp, available, r1, s1, origin, clock)
    # P2
    r2 = long_rates.copy(); bad2 = (long_published > clock).to_numpy(); r2[bad2] = 1e9
    p2 = candidates_at(levels, available, r2, long_published, origin, clock)
    # P3
    r3, s3 = long_food_rates(lp, available, poisoned_csv)
    p3 = candidates_at(lp, available, r3, s3, origin, clock)
    # T
    lt = levels[levels.index < t].copy()
    for col in lt.columns:
        lt.loc[(stamps[col].reindex(lt.index) > clock).to_numpy(), col] = np.nan
    at = available[available.index < t]
    rt, st = long_food_rates(lt, at, ROOT / LONG_HISTORY)
    tt = candidates_at(lt, at, rt, st, origin, clock)
    fr = frozen[origin]
    matches_frozen = clean['drifts'] == fr['drifts'] and clean['log_rates'] == fr['log_rates'] and clean['baseline_log_rates'] == fr['baseline_log_rates']
    rows.append(dict(origin=origin, clock=str(clock), poisoned_level_cells=n_poison, poisoned_long_rates=int(bad2.sum()),
                     P1_levels_identical=same(clean, p1), P2_long_rates_identical=same(clean, p2), P3_czso_identical=same(clean, p3),
                     T_truncated_identical=same(clean, tt), clean_equals_frozen_run=bool(matches_frozen)))
out = pd.DataFrame(rows); out.to_csv(HERE / 'out_B2_poison.csv', index=False)
pd.set_option('display.width', 250)
print(out[out.origin.isin(['2019-02', '2021-12', '2022-06', '2024-06', '2026-07'])].to_string(index=False))
print('\nAll origins:', len(out))
for col in ['P1_levels_identical', 'P2_long_rates_identical', 'P3_czso_identical', 'T_truncated_identical', 'clean_equals_frozen_run']:
    print(f'  {col}: {int(out[col].sum())}/{len(out)}')
poisoned_csv.unlink()
