"""R30: scheduled excise steps in the alcohol-and-tobacco nowcast block.

The recorded block forecast is an expanding same-calendar-month mean. The candidate replaces the mean's embedded
average excise step with the statutory step of the year in force: forecast = M(m) - Sbar(m) + S(m), where S(m) is
the calendar's contribution to the block's monthly rate and Sbar(m) the mean of S over the same past months the
expanding mean averaged. Only published tax decisions enter. See docs/implementation/R30_EXCISE_STEPS_NOWCAST_SPEC_2026-09-20.md.
"""
import numpy as np
import pandas as pd

THETA = .45                      # declared excise share of the retail price of spirits
THETA_GRID = (.35, .55)
FIRST_SERIES_MONTH = pd.Period('2015-02', 'M')     # the block's m/m series starts here (index 2015 = 100 from January 2015)
BLOCK_CODE, TOBACCO_CODES, SPIRITS_CODE = 2.0, (2.2, 2.3), 2.11


def load_calendar(path):
    cal = pd.read_csv(path, dtype=str)
    cal['effective_month'] = pd.PeriodIndex(cal.effective_month, freq='M')
    cal['landing'] = [pd.PeriodIndex(s.split('|'), freq='M') for s in cal.landing_months]
    cal['statutory_step_pct'] = cal.statutory_step_pct.astype(float)
    cal['available_from'] = pd.to_datetime(cal.available_from)
    return cal


def weight_shares(weights_long):
    """Per basket year: tobacco and spirits weights as shares of the block (division 02)."""
    w = weights_long.copy(); w['code'] = w.basket_code.astype(float); out = {}
    for year, g in w.groupby('effective_year'):
        block = g[g.code.eq(BLOCK_CODE)].weight_permille.iloc[0]
        tob = g[g.code.isin(TOBACCO_CODES)].weight_permille.iloc[0]; spir = g[g.code.eq(SPIRITS_CODE)].weight_permille.iloc[0]
        out[int(year)] = dict(tobacco=float(tob / block), spirits=float(spir / block))
    return out


def shares_for(month, shares):
    """The basket in force: the latest effective year at or before the month's year."""
    years = [y for y in shares if y <= month.year]
    if not years:
        raise ValueError(f'No basket weights for {month}')
    return shares[max(years)]


def contribution(month, cal, shares, theta=THETA, timing='thirds', clock=None, include=None):
    """S(m): the calendar's contribution to the block's monthly rate in `month`, in percent of the block.

    `timing` 'thirds' spreads a cigarette step equally over its landing months; 'first' puts it all in the first.
    Rows not yet available at `clock` (when given) are excluded; `include` filters by provenance.
    """
    month = pd.Period(month, 'M'); total = 0.
    for row in cal.itertuples():
        if include is not None and row.provenance not in include:
            continue
        if clock is not None and row.available_from > pd.Timestamp(clock):
            continue
        w = shares_for(month, shares)
        if row.product == 'cigarettes':
            landing = list(row.landing)
            if month not in landing:
                continue
            share = (1. / len(landing)) if timing == 'thirds' else (1. if month == landing[0] else 0.)
            total += w['tobacco'] * row.statutory_step_pct * share
        elif row.product == 'spirits':
            if month != row.effective_month:
                continue
            total += w['spirits'] * row.statutory_step_pct * theta
        else:
            raise ValueError('Unknown product ' + str(row.product))
    return float(total)


def past_mean(month, cal, shares, **kw):
    """Sbar(m): mean of S over the same calendar month in every earlier year of the block series (released by the clock)."""
    month = pd.Period(month, 'M'); values = []
    for year in range(FIRST_SERIES_MONTH.year, month.year):
        past = pd.Period(f'{year}-{month.month:02d}', 'M')
        if past < FIRST_SERIES_MONTH:
            continue
        values.append(contribution(past, cal, shares, **kw))
    return float(np.mean(values)) if values else 0.


def candidate_block(month, recorded_mean, cal, shares, **kw):
    """The candidate's block forecast: recorded same-month mean minus its embedded average step plus this year's step."""
    return float(recorded_mean) - past_mean(month, cal, shares, **kw) + contribution(month, cal, shares, **kw)
