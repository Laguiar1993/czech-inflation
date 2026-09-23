"""Base rates for the CNB lead test.

A model's record of calls means little without knowing what a forecast with no model would
have scored under the same rules. Four such rows are built for every report and clock, in the
schema that `tools.research_r23.lead.lead_pairs` reads:

CONST_2       annual inflation of 2% in every unknown month
RW_YY         the latest known annual rate carried forward
PREV_CNB      the previous report's CNB forecast for the same quarter (a bet on reversal)
CNB_MOMENTUM  the current CNB forecast plus its latest revision (a bet on continuation)

The last two use CNB forecasts. They are evaluation references only and never model inputs.
"""
import numpy as np
import pandas as pd

MODELS = ['CONST_2', 'RW_YY', 'PREV_CNB', 'CNB_MOMENTUM']


def _quarter_months(quarter):
    q = pd.Period(quarter, 'Q')
    return pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M')


def _quarter_mean(quarter, origin, constant, actual):
    values = [actual.get(m, np.nan) if m < origin else constant for m in _quarter_months(quarter)]
    return float(np.mean(values)) if np.isfinite(values).all() else np.nan


def baseline_projections(cnb, clocks, actual_yy):
    forecasts = cnb[cnb.is_forecast.astype(str).str.lower().eq('true')]
    lookup = forecasts.set_index(['report_date', 'quarter']).value
    if lookup.index.duplicated().any():
        raise ValueError('Duplicate CNB report/quarter forecast')
    dates = sorted(cnb.report_date.unique()); previous = dict(zip(dates[1:], dates))
    rows = []
    for c in clocks.itertuples():
        if not isinstance(c.origin, str):
            continue
        origin = pd.Period(c.origin, 'M'); last_known = float(actual_yy.get(origin - 1, np.nan))
        for r in forecasts[forecasts.report_date.eq(c.report_date)].itertuples():
            months = actual_yy.reindex(_quarter_months(r.quarter)).to_numpy(float)
            realised = float(months.mean()) if np.isfinite(months).all() else np.nan
            earlier = float(lookup.get((previous.get(c.report_date), r.quarter), np.nan))
            values = {'CONST_2': _quarter_mean(r.quarter, origin, 2., actual_yy),
                      'RW_YY': _quarter_mean(r.quarter, origin, last_known, actual_yy),
                      'PREV_CNB': earlier, 'CNB_MOMENTUM': float(r.value) + (float(r.value) - earlier)}
            for model in MODELS:
                rows.append(dict(model=model, clock=c.clock, report_date=c.report_date, quarter=r.quarter,
                                 origin=c.origin, forecast=values[model], realised=realised))
    return pd.DataFrame(rows)


def report_clusters(rows):
    """Episodes are not independent: count the distinct reports behind gains and losses."""
    out = []
    for model, g in rows.groupby('model'):
        out.append(dict(model=model, episodes=len(g), reports=g.report_date.nunique(),
                        gain_reports=g[g.material_gain.astype(bool)].report_date.nunique(),
                        loss_reports=g[g.material_loss.astype(bool)].report_date.nunique(),
                        success_reports=g[g.joint_success.astype(bool)].report_date.nunique()))
    return pd.DataFrame(out)
