"""E. The specification's promotion rule ('What would count'), evaluated strictly as written from the reviewer's
own scores (out_D_food_block_own.csv, out_D_headline_own.csv - run probe_D_scores.py first).

 1. food-block h12 RMSE at or below the baseline on the full sample and on origins from 2024
 2. food-block h3 and h6 RMSE no more than 2% above the baseline on the full sample
 3. assembled headline h12 RMSE at or below FAST on the full sample and on origins from 2024
 4. a smaller absolute food-block h12 bias on origins from 2024
Preference if several pass: NORM_SHIFT, ROBUST_WINDOW, NORM_REFIT. ZERO_DRIFT is never promoted.

Sensitivity (not part of the rule): condition 3 on every matured origin instead of the fixed 969-key support,
and the margins by which each condition passes.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_common as pc

pd.set_option('display.width', 250); pd.set_option('display.max_columns', 60)
food = pd.read_csv(pc.HERE / 'out_D_food_block_own.csv').set_index(['model', 'H', 'sample'])
head = pd.read_csv(pc.HERE / 'out_D_headline_own.csv').set_index(['model', 'h', 'sample'])
F = pc.FAST; rows = []
for m in pc.CANDIDATES:
    g = lambda H, s, col='own_rmse', model=m: float(food.loc[(model, H, s), col])
    y = lambda s, model=m: float(head.loc[(model, 12, s), 'own_rmse'])
    c1 = g(12, 'full') <= g(12, 'full', model=F) and g(12, 'origins_2024plus') <= g(12, 'origins_2024plus', model=F)
    c2 = g(3, 'full') <= 1.02 * g(3, 'full', model=F) and g(6, 'full') <= 1.02 * g(6, 'full', model=F)
    c3 = y('full') <= y('full', F) and y('origins_2024plus') <= y('origins_2024plus', F)
    c4 = abs(g(12, 'origins_2024plus', 'own_bias')) < abs(g(12, 'origins_2024plus', 'own_bias', F))
    rows.append(dict(model=m, c1_food_h12=c1, c2_food_h3_h6=c2, c3_headline_h12=c3, c4_bias_2024=c4, all_four=c1 and c2 and c3 and c4,
                     food_h12_full=f"{g(12, 'full'):.3f} vs {g(12, 'full', model=F):.3f}", food_h12_2024=f"{g(12, 'origins_2024plus'):.3f} vs {g(12, 'origins_2024plus', model=F):.3f}",
                     food_h3_pct=round(100 * (g(3, 'full') / g(3, 'full', model=F) - 1), 2), food_h6_pct=round(100 * (g(6, 'full') / g(6, 'full', model=F) - 1), 2),
                     yy_h12_full=f"{y('full'):.4f} vs {y('full', F):.4f}", yy_h12_2024=f"{y('origins_2024plus'):.4f} vs {y('origins_2024plus', F):.4f}",
                     bias_2024=f"{g(12, 'origins_2024plus', 'own_bias'):+.3f} vs {g(12, 'origins_2024plus', 'own_bias', F):+.3f}"))
out = pd.DataFrame(rows); out.to_csv(pc.HERE / 'out_E_promotion.csv', index=False)
print(out.T.to_string())
passing = [m for m in ['FOOD_NORM_SHIFT_R24', 'FOOD_ROBUST_WINDOW_R24', 'FOOD_NORM_REFIT_R24'] if bool(out.set_index('model').loc[m, 'all_four'])]
print('\nPass all four, in declared preference order:', passing, '-> selected:', passing[0] if passing else None)
print('ZERO_DRIFT (control, never promoted) passes all four:', bool(out.set_index('model').loc['FOOD_ZERO_DRIFT_R24', 'all_four']))

# sensitivity: condition 3 on every matured origin (78 at h12) rather than the fixed support (75)
fc = pd.read_csv(pc.R24 / 'forecasts.csv', low_memory=False, float_precision='round_trip'); fc = fc[fc.h.eq(12) & np.isfinite(fc.yy_actual) & np.isfinite(fc.yy_exante)]
e = fc.assign(e=fc.yy_exante - fc.yy_actual).pivot(index='origin', columns='model', values='e')
print('\nSensitivity, headline h12 on every matured origin (n=%d, %s..%s):' % (len(e), e.index.min(), e.index.max()))
for s in ('full', 'origins_2024plus'):
    z = e[pc.era_mask(e.index, s)]
    print(f'   {s:<18} n={len(z):>2}  FAST {np.sqrt((z[F] ** 2).mean()):.4f}  ' + '  '.join(f'{m[5:-4]} {np.sqrt((z[m] ** 2).mean()):.4f}' for m in pc.CANDIDATES))
