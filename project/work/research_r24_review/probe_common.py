"""Reviewer's own loaders and estimators for the R24 review. Nothing here imports R24 or R14B model code.

Everything is computed directly from the CSV inputs so that the comparisons in the probes are independent
re-derivations, not re-runs of the code under review.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FOOD = ROOT / 'data/research_r14/food'
LONG = FOOD / 'coverage_extension/czso_cpi_1995_2025.csv'
R24 = ROOT / 'output/research_r24/final'
EVAL = R24 / 'evaluation'
NATIVE_R21 = ROOT / 'output/research_r21/path_anchor/native_forecasts.csv'
ACTUAL = ROOT / 'output/research_r14b/attribution/actual_component_targets.csv'
HEADLINE = ROOT / 'output/independent_path_frozen_inputs.csv'
FAST = 'STATE_FAST_R15'
CANDIDATES = ['FOOD_ZERO_DRIFT_R24', 'FOOD_ROBUST_WINDOW_R24', 'FOOD_NORM_SHIFT_R24', 'FOOD_NORM_REFIT_R24']
PRAGUE = 'Europe/Prague'


def load_levels():
    x = pd.read_csv(FOOD / 'pipeline_log_levels.csv', index_col=0, float_precision='round_trip')
    x.index = pd.PeriodIndex(x.index, freq='M')
    return x


def load_available():
    """Publication stamps as tz-aware UTC timestamps (the file mixes +01:00 and +02:00 offsets)."""
    x = pd.read_csv(FOOD / 'pipeline_available_from.csv', index_col=0)
    x.index = pd.PeriodIndex(x.index, freq='M')
    return x.apply(lambda col: pd.to_datetime(col, utc=True))


def load_long_index(kind='Z'):
    """CZSO division 01. kind 'Z' = base-year index, 'C' = same month of previous year = 100."""
    raw = pd.read_csv(LONG, dtype=str)
    raw = raw[(raw.ucel_kod == '01') & (raw.casz_kod == kind)]
    ix = pd.PeriodIndex([f'{y}-{int(m):02d}' for y, m in zip(raw.rok, raw.mesic)], freq='M')
    s = pd.Series(raw.hodnota.astype(float).to_numpy(), index=ix).sort_index()
    assert s.index.is_unique
    return s


def own_long_rates(levels, available):
    """Spliced monthly food log changes and their publication stamps, by the specification's words:
    before 2015-02 from the CZSO base-year index, from 2015-02 the model's own changes with recorded stamps,
    earlier months published on the tenth of the following month (09:00 Prague is the reviewer's reading
    of the repository's convention for CPI releases)."""
    idx = load_long_index('Z')
    old = (100 * np.log(idx)).diff().dropna()
    own = levels['food'].diff().dropna()
    first_own = pd.Period('2015-02', 'M')
    assert own.index.min() == first_own
    rates = pd.concat([old[old.index < first_own], own[own.index >= first_own]]).sort_index()
    assert rates.index.equals(pd.period_range(rates.index.min(), rates.index.max(), freq='M'))
    stamps = {}
    for m in rates.index:
        if m >= first_own:
            stamps[m] = available.loc[m, 'food']
        else:
            nxt = m + 1
            stamps[m] = pd.Timestamp(year=nxt.year, month=nxt.month, day=10, hour=9, tz=PRAGUE).tz_convert('UTC')
    return rates, pd.Series(stamps)


def own_released_rates(levels, available, origin, clock):
    """Levels strictly before the origin month, blanked where the stamp is after the clock; first difference."""
    t = pd.Period(origin, 'M'); clock = pd.Timestamp(clock)
    assert clock.tzinfo is not None
    y = levels[levels.index < t].copy()
    for col in y.columns:
        ok = available[col].reindex(y.index).le(clock)
        y.loc[~ok.fillna(False).to_numpy(), col] = np.nan
    return y.diff()


def own_training_dates(rates, lags=6, window=96):
    """Response months whose own row and six lags are complete for all three series; the last `window`."""
    v = rates.to_numpy(float); good = []
    for i in range(lags, len(rates)):
        if np.isfinite(v[i - lags:i + 1]).all():
            good.append(rates.index[i])
    return pd.PeriodIndex(good[-window:], freq='M')


def own_median_drift(rates, stamps, clock, start='1996-01', allowed=None, min_windows=12):
    """Median over complete runs of twelve consecutive usable months of the twelve-month log change, per month."""
    clock = pd.Timestamp(clock); start = pd.Period(start, 'M')
    months = [m for m in rates.index if m >= start and np.isfinite(rates[m]) and stamps[m] <= clock
              and (allowed is None or m in allowed)]
    have = set(months); sums = []
    for m in months:
        win = [m - k for k in range(12)]
        if all(w in have for w in win):
            sums.append(sum(rates[w] for w in win))
    if len(sums) < min_windows:
        return np.nan, len(sums)
    return float(np.median(sums) / 12), len(sums)


def own_drifts(levels, available, long_rates, long_stamps, origin, clock):
    r = own_released_rates(levels, available, origin, clock)
    train = own_training_dates(r)
    food = r.loc[train, 'food']
    by_month = food.groupby(food.index.month).mean().reindex(range(1, 13))
    mu_window = float(by_month.mean())
    mu_robust, n_robust = own_median_drift(long_rates, long_stamps, clock, allowed=set(train))
    mu_long, n_long = own_median_drift(long_rates, long_stamps, clock)
    return dict(origin=str(origin), mu_window=mu_window, mu_robust=mu_robust, mu_long=mu_long, n_train=len(train),
                train_start=str(train.min()), train_end=str(train.max()), n_windows_robust=n_robust, n_windows_long=n_long,
                plain_window_mean=float(food.mean()), calendar_means=by_month.to_numpy())


def clocks():
    n = pd.read_csv(R24 / 'native_forecasts.csv', usecols=['origin', 'h', 'model', 'as_of_utc'])
    n = n[(n.model == FAST) & (n.h == 0)]
    return {o: pd.Timestamp(c) for o, c in zip(n.origin, n.as_of_utc)}


def era(origin):
    o = str(origin)
    return 'origins_2019_2021' if o <= '2021-12' else 'origins_2022_2023' if o <= '2023-12' else 'origins_2024plus'


ERAS = ['full', 'origins_2019_2021', 'origins_2022_2023', 'origins_2024plus']


def era_mask(origins, name):
    o = pd.Series(list(map(str, origins)))
    if name == 'full':
        return np.ones(len(o), bool)
    return o.map(era).eq(name).to_numpy()
