"""Name the driver of a disagreement with CNB: split model-minus-CNB into CNB's own price blocks.

CNB's forecast table carries core inflation, food (including alcohol and tobacco), fuel and
administered prices with their basket weights. For a frozen origin the model's annual rate of
each block is compounded from realised monthly rates before the origin and forecast rates from
h1. Each block's contribution gap is `w_model * model_rate - w_cnb * cnb_rate`. What the blocks
do not explain (the h0 nowcast month, the reconciliation wedge, weight and aggregation
differences) is reported as `unexplained`, never forced into a block.

The h0 month has no block split in the research archive. Historical attribution therefore uses
the realised block rates for that one month (pass `h0_blocks` to supply a recorded nowcast split
in prospective use). This is an accounting of an ex-ante gap, not a forecast, and CNB forecasts
never enter any model here.
"""
import re

import numpy as np
import pandas as pd

BLOCK_MAP = {'core': ['core'], 'food_alc_tobacco': ['food', 'alcohol_tobacco'], 'fuel': ['fuel'], 'administered': ['administered']}
WEIGHT = {'core': 'weight_core', 'food': 'weight_food', 'alcohol_tobacco': 'weight_alc', 'fuel': 'weight_fuel', 'administered': 'weight_administered'}


def cnb_weight(label):
    """Basket weight printed in a CNB row label, as a fraction."""
    found = re.search(r'(\d+(?:[.,]\d+)?)\s*%\s*\*', str(label)) or re.search(r'\((\d+(?:[.,]\d+)?)\s*%\)', str(label))
    return float(found.group(1).replace(',', '.')) / 100 if found else np.nan


def model_block_rates(frame, actual, origin, h0_blocks=None):
    """Monthly rates by CNB block for origin-23..origin+12 and the model's weights."""
    t = pd.Period(origin, 'M'); future = frame[frame.h.gt(0)].set_index('h'); months = pd.period_range(t - 23, t + 12, freq='M')
    weights = {b: float(future[w].mean()) for b, w in WEIGHT.items()}; out = {}
    for block, parts in BLOCK_MAP.items():
        total = sum(weights[p] for p in parts); series = pd.Series(0., index=months)
        for p in parts:
            rate = actual[p].reindex(months).copy()
            rate.loc[rate.index > t] = np.nan
            for h, value in future['value_' + p].items():
                rate.loc[t + int(h)] = value
            if h0_blocks is not None:
                rate.loc[t] = h0_blocks[p]
            series = series + weights[p] / total * rate
        out[block] = series
    return pd.DataFrame(out), {block: sum(weights[p] for p in parts) for block, parts in BLOCK_MAP.items()}


def annual_rates(monthly):
    return 100 * np.expm1(np.log1p(monthly / 100).rolling(12, min_periods=12).sum())


def component_gaps(native, actual, cnb_long, projections, clocks, models, h0_blocks=None):
    """One row per model, clock, report, target quarter and block, plus an `unexplained` row."""
    quarterly = cnb_long[cnb_long.frequency.eq('Q') & cnb_long.indicator.isin(BLOCK_MAP)]
    cnb_rate = quarterly.set_index(['report_date', 'indicator', 'period']).value
    cnb_w = quarterly.drop_duplicates(['report_date', 'indicator']).set_index(['report_date', 'indicator']).row_label.map(cnb_weight)
    origin_of = {(r.clock, r.report_date): r.origin for r in clocks.itertuples() if isinstance(r.origin, str)}; rows = []
    for model in models:
        own = native[native.model.eq(model)]
        for (clock, report), origin in origin_of.items():
            frame = own[own.origin.eq(origin)]
            if frame.empty:
                continue
            monthly, weights = model_block_rates(frame, actual, origin, h0_blocks); yearly = annual_rates(monthly)
            mine = projections[projections.model.eq(model) & projections.clock.eq(clock) & projections.report_date.eq(report)]
            for p in mine.itertuples():
                q = pd.Period(p.quarter, 'Q'); span = pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M')
                headline = p.forecast - cnb_long_value(cnb_long, report, 'cpi', p.quarter); explained = 0.; block_rows = []
                for block in BLOCK_MAP:
                    ours = float(yearly[block].reindex(span).mean()) if yearly[block].reindex(span).notna().all() else np.nan
                    theirs = float(cnb_rate.get((report, block, p.quarter), np.nan)); w_cnb = float(cnb_w.get((report, block), np.nan))
                    gap = weights[block] * ours - w_cnb * theirs; explained += gap
                    block_rows.append(dict(block=block, model_rate=ours, cnb_rate=theirs, model_weight=weights[block], cnb_weight=w_cnb, contribution_gap=gap))
                complete = np.isfinite([headline, explained]).all()
                for b in [*block_rows, dict(block='unexplained', model_rate=np.nan, cnb_rate=np.nan, model_weight=np.nan, cnb_weight=np.nan,
                                           contribution_gap=headline - explained if complete else np.nan)]:
                    rows.append(dict(model=model, clock=clock, report_date=report, origin=origin, quarter=p.quarter, quarters_ahead=p.quarters_ahead,
                                     headline_gap=headline, **b))
    return pd.DataFrame(rows)


def cnb_long_value(cnb_long, report, indicator, quarter):
    hit = cnb_long[cnb_long.report_date.eq(report) & cnb_long.indicator.eq(indicator) & cnb_long.frequency.eq('Q') & cnb_long.period.eq(quarter)]
    return float(hit.value.iloc[0]) if len(hit) else np.nan


def dominant_block(gaps):
    """Per model/clock/report/quarter: the block pushing hardest in the direction of the headline gap."""
    keys = ['model', 'clock', 'report_date', 'quarter']; out = []
    for key, g in gaps.groupby(keys):
        g = g.dropna(subset=['contribution_gap'])
        if g.empty or not np.isfinite(g.headline_gap.iloc[0]):
            continue
        signed = g.set_index('block').contribution_gap * np.sign(g.headline_gap.iloc[0])
        out.append(dict(zip(keys, key), headline_gap=g.headline_gap.iloc[0], dominant_block=signed.idxmax(), dominant_gap=float(signed.max()),
                        **{'gap_' + b: float(v) for b, v in g.set_index('block').contribution_gap.items()}))
    return pd.DataFrame(out)
