"""Reviewer's own loaders for the R27 review. Nothing here imports the R27 model, runner or evaluator.

Everything is read straight from the CSV inputs and the exported run files so that every number in the
probes is an independent re-derivation, not a re-run of the code under review.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
FOOD = ROOT / 'data/research_r14/food'
R27 = ROOT / 'output/research_r27/final'
R24 = ROOT / 'output/research_r24/final'
EVAL = R27 / 'evaluation'
ACTUAL = ROOT / 'output/research_r14b/attribution/actual_component_targets.csv'
SUPPORT = ROOT / 'output/research_r17/attribution/primary_support.csv'
HEADLINE = ROOT / 'output/independent_path_frozen_inputs.csv'
CALENDAR = ROOT / 'data/release_calendar_cz_cpi.csv'
BASELINE = 'FOOD_NORM_SHIFT_R24'
FAST = 'STATE_FAST_R15'
CANDIDATE = 'FOOD_ECM_R27'
PPI_CANDIDATE = 'FOOD_ECM_PPI_R27'
FIXED = {'FOOD_ECM_A002_R27': -.02, 'FOOD_ECM_A005_R27': -.05, 'FOOD_ECM_A010_R27': -.10, 'FOOD_ECM_A015_R27': -.15}
PRAGUE = 'Europe/Prague'
ERAS = ['full', 'origins_2019_2021', 'origins_2022_2023', 'origins_2024plus']
WINDOW, MIN_WINDOW = 96, 36


def to_log(percent):
    return 100 * np.log1p(np.asarray(percent, float) / 100)


def to_percent(log_points):
    return 100 * np.expm1(np.asarray(log_points, float) / 100)


def load_levels():
    x = pd.read_csv(FOOD / 'pipeline_log_levels.csv', index_col=0, float_precision='round_trip')
    x.index = pd.PeriodIndex(x.index, freq='M')
    return x


def load_available():
    """Publication stamps as tz-aware UTC timestamps (the file mixes +01:00 and +02:00 offsets)."""
    x = pd.read_csv(FOOD / 'pipeline_available_from.csv', index_col=0)
    x.index = pd.PeriodIndex(x.index, freq='M')
    return x.apply(lambda col: pd.to_datetime(col, utc=True))


def load_calendar():
    cal = pd.read_csv(CALENDAR)
    cal.index = pd.PeriodIndex(cal.target_month, freq='M')
    return cal


def load_native(run=R27):
    return pd.read_csv(run / 'native_forecasts.csv', low_memory=False, float_precision='round_trip')


def load_forecasts(run=R27):
    return pd.read_csv(run / 'forecasts.csv', float_precision='round_trip')


def load_actual():
    a = pd.read_csv(ACTUAL, index_col=0, float_precision='round_trip')
    a.index = pd.PeriodIndex(a.index, freq='M')
    return a


def load_support():
    s = pd.read_csv(SUPPORT)
    return set(zip(s.origin, s.h))


def load_headline():
    h = pd.read_csv(HEADLINE, index_col=0, float_precision='round_trip').headline_mm
    h.index = pd.PeriodIndex(h.index, freq='M')
    return h


def load_audit():
    return pd.read_csv(R27 / 'ecm_audit.csv', float_precision='round_trip')


def clocks(native=None):
    n = load_native() if native is None else native
    n = n[(n.model == BASELINE) & (n.h == 0)]
    return {o: pd.Timestamp(c) for o, c in zip(n.origin, n.as_of_utc)}


def era_of(origin):
    o = str(origin)
    return 'origins_2019_2021' if o <= '2021-12' else 'origins_2022_2023' if o <= '2023-12' else 'origins_2024plus'


def era_mask(origins, name):
    o = pd.Series(list(map(str, origins)))
    if name == 'full':
        return np.ones(len(o), bool)
    return o.map(era_of).eq(name).to_numpy()


def rmse(e):
    e = np.asarray(e, float)
    return float(np.sqrt(np.mean(e ** 2))) if len(e) else np.nan


def food_log_paths(native, models):
    """{model: DataFrame origin x h (1..12) of food monthly log rates} from value_food in native rows."""
    out = {}
    for m in models:
        g = native[(native.model == m) & (native.h.between(1, 12))]
        p = g.pivot(index='origin', columns='h', values='value_food').sort_index()
        out[m] = pd.DataFrame(to_log(p.to_numpy()), index=p.index, columns=p.columns)
    return out


def actual_food_log(actual):
    return pd.Series(to_log(actual.food.to_numpy()), index=actual.index)


def cumulative_table(log_paths, actual_log, support, horizons=(3, 6, 12)):
    """Rows (origin, H) on the primary support with the cumulative log change of every model and the truth."""
    rows = []
    origins = sorted(set.intersection(*[set(p.index) for p in log_paths.values()]))
    for o in origins:
        t = pd.Period(o, 'M')
        for H in horizons:
            if (o, H) not in support:
                continue
            months = pd.period_range(t + 1, t + H, freq='M')
            truth = actual_log.reindex(months)
            row = dict(origin=o, H=H, actual=float(truth.sum()) if truth.notna().all() else np.nan)
            for m, p in log_paths.items():
                v = p.loc[o, list(range(1, H + 1))].to_numpy(float)
                row[m] = float(v.sum()) if np.isfinite(v).all() else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def score_table(table, models, horizons=(3, 6, 12)):
    rows = []
    for H in horizons:
        g = table[table.H == H].dropna(subset=[*models, 'actual'])
        for era in ERAS:
            s = g[era_mask(g.origin, era)]
            for m in models:
                e = s[m] - s.actual
                rows.append(dict(H=H, sample=era, name=m, n=len(s), rmse=rmse(e), bias=float(e.mean()) if len(s) else np.nan))
    return pd.DataFrame(rows)


def circular_block_bootstrap(d, block=12, draws=2000, seed=1509):
    """Reviewer's own copy of the declared scheme: circular blocks, n from ceil(n/block) starts, mean per draw."""
    d = np.asarray(d, float); n = len(d)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(draws, int(np.ceil(n / block))))
    index = ((starts[:, :, None] + np.arange(block)) % n).reshape(draws, -1)[:, :n]
    means = d[index].mean(axis=1)
    return dict(n=n, mean=float(d.mean()), ci_low=float(np.quantile(means, .025)), ci_high=float(np.quantile(means, .975)),
                p_improve=float(np.mean(means < 0)))


def compound_yy(history, h0, path_pct, origin, h):
    """Exact twelve-month rate from history (percent m/m) before the origin, the h0 nowcast and the h1..h forecasts."""
    t = pd.Period(origin, 'M')
    vals = []
    for m in pd.period_range(t + h - 11, t + h, freq='M'):
        if m < t:
            vals.append(history.get(m, np.nan))
        elif m == t:
            vals.append(h0)
        else:
            vals.append(path_pct.get(m.ordinal - t.ordinal, np.nan))
    vals = np.asarray(vals, float)
    if len(vals) != 12 or not np.isfinite(vals).all():
        return np.nan
    return float(100 * np.expm1(np.log1p(vals / 100).sum()))


# ---- the reviewer's own re-implementation of the declared R27 mechanics (spec section "Candidates") ----

def published_before(levels, available, origin, clock):
    t = pd.Period(origin, 'M'); clock = pd.Timestamp(clock)
    assert clock.tzinfo is not None
    y = levels[levels.index < t].copy()
    for col in y.columns:
        ok = available[col].reindex(y.index).le(clock)
        y.loc[~ok.fillna(False).to_numpy(), col] = np.nan
    return y


def month_centre(series):
    means = series.groupby(series.index.month).transform('mean')
    return series - means


def own_gap(published, last, regressors=('food_ppi', 'agri4'), trend=True, window=WINDOW, min_window=MIN_WINDOW, centre=True):
    """Residual of food on [1, trend, regressors] over the window ending at `last`, centred by calendar month."""
    cols = ['food', *regressors]
    frame = published.loc[:last, cols].dropna().iloc[-window:]
    if len(frame) < min_window:
        return None, {}
    n = len(frame)
    x = [np.ones(n)]
    if trend:
        x.append(np.arange(n, dtype=float))
    for r in regressors:
        x.append(frame[r].to_numpy(float))
    X = np.column_stack(x); y = frame.food.to_numpy(float)
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = pd.Series(y - X @ beta, index=frame.index)
    gap = month_centre(resid) if centre else resid
    info = dict(n=n, beta=beta, window_start=str(frame.index[0]), window_end=str(frame.index[-1]))
    return gap, info


def own_speed(published, gap, clip=(-.25, 0.)):
    rates = published.food.diff().reindex(gap.index).dropna()
    centred = month_centre(rates)
    pairs = pd.concat([centred.rename('rate'), gap.shift(1).rename('gap')], axis=1).dropna()
    raw = float(pairs.rate @ pairs.gap) / float(pairs.gap @ pairs.gap)
    return float(np.clip(raw, *clip)) if clip is not None else raw, raw, len(pairs)


def own_correction(alpha, gap_last, last, origin, horizons=range(1, 7)):
    t = pd.Period(origin, 'M'); L = pd.Period(last, 'M')
    out = {h: 0. for h in range(1, 13)}
    for h in horizons:
        steps = (t + h - 1).ordinal - L.ordinal
        out[h] = float(alpha * gap_last * (1 + alpha) ** steps)
    return out
