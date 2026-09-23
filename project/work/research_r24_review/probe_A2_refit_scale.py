"""A2. The refit candidate: same training dates, same scale, same priors, same contraction rule, and the centre moves
the declared way. Calls the frozen fit_rate_var directly with the baseline centre and with the shifted centre."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import probe_common as pc
from models.food_path_r14 import load_inputs
from models.food_stable_r14b import released_rates, design, fit_rate_var, WINDOW

levels, available, _ = load_inputs(); clk = pc.clocks()
audit = pd.read_csv(pc.R24 / 'drift_audit.csv', float_precision='round_trip').set_index('origin')
stored = pd.read_csv(pc.R24 / 'food_log_rates.csv', float_precision='round_trip')
for origin in ['2019-02', '2021-12', '2022-06', '2024-06', '2026-07']:
    t = pd.Period(origin, 'M'); rates, _ = released_rates(levels, available, t, clk[origin])
    x, y, index = design(rates); dates = index[np.isfinite(x).all(axis=1) & np.isfinite(y).all(axis=1)][-WINDOW:]
    base = fit_rate_var(rates, dates); centre = base['seasonal_means'].copy(); shift = audit.loc[origin, 'mu_long'] - audit.loc[origin, 'mu_window']
    centre[:, 2] += shift; moved = fit_rate_var(rates, dates, shared_means=centre)
    new_food_centre = moved['seasonal_means'][:, 2]
    refit = stored[(stored.origin == origin) & (stored.model == 'FOOD_NORM_REFIT_R24')].set_index('h').log_rate
    target_month_centre = new_food_centre[(t + 12).month - 1]
    print(f'{origin}: training dates identical {base["training_dates"] == moved["training_dates"]} (n={moved["n_train"]}); '
          f'max |sigma refit - sigma baseline| = {np.abs(moved["sigma"] - base["sigma"]).max():.1e}; '
          f'farm/producer centres unchanged {bool((moved["seasonal_means"][:, :2] == base["seasonal_means"][:, :2]).all())}; '
          f'mean of new food centre - mu_long = {new_food_centre.mean() - audit.loc[origin, "mu_long"]:+.1e}; '
          f'contraction {moved["contraction"]:.3f} (baseline {base["contraction"]:.3f}); '
          f'stored refit h12 rate - new centre for that calendar month = {refit[12] - target_month_centre:+.4f} (shift was {shift:+.4f})')
