"""Independent, offline R22 chronology and numerical reconstruction probes."""
from pathlib import Path
import sys
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data.research_transmission_r22 import load_inputs, log_change, quarterly_pressure
from models.transmission_r22 import run_origin, mask_panel, FAMILIES
import r17_common as c


def manual_path(diag, pre, origin):
    cols = diag['columns']; k = len(cols)
    beta = np.array(diag['coefficients'])
    state = np.array(diag['state_at_internal_h0'])
    output = []
    for h in range(1, 13):
        first = beta[0] + state @ beta[1:]
        state = np.r_[first, state[:-k]]
        core = cols.index('core')
        lograte = (first[core] * pre['sigma']['core'] + pre['center']['core']
                   + pre['seasonal']['core'][(origin + h).month])
        output.append(100 * np.expm1(lograte / 100))
    return output


def main():
    panel, available, quarters, meta, hashes = load_inputs()
    origins = c.read('output/research_r17/path/native_forecasts.csv').query("model == 'STATE_FAST_R15' and h == 0")
    report = {'input_samples': {col: dict(first=str(panel[col].first_valid_index()),
                last=str(panel[col].last_valid_index()), nonfinite=int((~np.isfinite(panel[col])).sum())) for col in panel},
              'chronology': [], 'checks': []}
    families = {key: value for key, value in FAMILIES.items() if key != 'JOINT_RF_R22'}
    for pos in (0, 30, 60, 89):
        row = origins.iloc[pos]; t = pd.Period(row.origin, 'M')
        fit = run_origin(panel, available, t, row.as_of_utc, families)
        summary = dict(origin=str(t), asof=row.as_of_utc, status=fit['status'], n_train=fit['n_train'])
        if fit['status'] != 'estimated':
            report['chronology'].append(summary); continue
        masked = mask_panel(panel, available, t, row.as_of_utc)
        poisoned = panel.copy()
        hidden = pd.DataFrame(True, index=panel.index, columns=panel.columns)
        hidden.loc[masked.index] = masked.isna()
        poisoned[hidden] = 1e10
        counterfactual = run_origin(poisoned, available, t, row.as_of_utc, families)
        dates = []
        for name in families:
            np.testing.assert_allclose(fit['paths'][name], counterfactual['paths'][name], rtol=0, atol=0)
            d = fit['fits'][name]
            np.testing.assert_allclose(fit['paths'][name], manual_path(d, fit['preprocessing'], t), rtol=1e-12, atol=1e-12)
            dates.append(d['train_dates'])
            assert d['radius'] <= .980000001
            assert pd.Period(d['train_dates'][-1], 'M') < t
            cols = d['columns']; k = len(cols)
            h0 = np.array(d['state_at_internal_h0'])[:k]
            for col in d['known_h0']:
                expected = ((masked.loc[t, col] - fit['preprocessing']['seasonal'][col][t.month]
                             - fit['preprocessing']['center'][col]) / fit['preprocessing']['sigma'][col])
                np.testing.assert_allclose(h0[cols.index(col)], expected, rtol=0, atol=1e-12)
        assert all(d == dates[0] for d in dates)
        summary.update(anchor=fit['fits']['JOINT_LINEAR_R22']['anchor'],
                       known_h0=fit['fits']['JOINT_LINEAR_R22']['known_h0'],
                       raw_radius=fit['fits']['JOINT_LINEAR_R22']['raw_radius'],
                       n_distinct_ulc_quarters=int(quarters.loc[pd.PeriodIndex(dates[0], freq='M')].nunique()),
                       max_abs_core_forecast=float(max(abs(np.array(x)).max() for x in fit['paths'].values())))
        report['chronology'].append(summary)
    report['checks'].append('Four real origins: exact hidden-input poison invariance; common training dates; independently reconstructed h1..h12 paths; bounded radii; exact macro h0 observations.')

    # Delay the older endpoint, not the new one: quarter growth must remain hidden.
    qindex = pd.period_range('2017Q1', periods=8, freq='Q')
    v = pd.Series(np.arange(100., 108.), index=qindex)
    a = pd.Series(qindex.to_timestamp(how='end').normalize() + pd.Timedelta(days=75), index=qindex)
    a.iloc[0] = pd.Timestamp('2025-01-01')
    rate, dates, provenance = quarterly_pressure(v, a)
    for month in ('2018-03', '2018-04', '2018-05'):
        assert dates.loc[month] == pd.Timestamp('2025-01-01')
        assert provenance.loc[month] == '2018Q1'
    v.iloc[4] = np.nan
    rate2, dates2, _ = quarterly_pressure(v, a)
    assert rate2.loc['2018-03':'2018-05'].isna().all()
    assert dates2.loc['2018-03':'2018-05'].isna().all()
    report['checks'].append('Quarterly pressure uses maximum old/new endpoint date and fails closed on missing quarterly values.')
    out = Path(__file__).with_name('audit_results.json')
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
