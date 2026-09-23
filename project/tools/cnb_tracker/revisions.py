"""CNB revision tracker: news since the previous cutoff as a predictor of the next forecast revision.

A separate, conditioned lane. It uses CNB forecasts as inputs and therefore never feeds the
independent forecast. Specification: docs/implementation/CNB_TRACKER_SPEC_2026-09-17.md.

    python -m tools.cnb_tracker.revisions --tables data/cnb_mpr_tables_20260917 --lead output/research_r24/final/evaluation --output output/cnb_tracker_20260917/revisions
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from tools.cnb_tracker.component_gaps import cnb_weight

MODELS = {'T0_ZERO': [], 'T1_CPI': ['cpi_news'], 'T2_CPI_FX_OIL': ['cpi_news', 'fx_news', 'brent_news'],
          'T3_BLOCKS_FX_OIL': ['core_news', 'noncore_news', 'fx_news', 'brent_news']}
HORIZONS = (0, 1, 2, 3)
MATERIAL = .15
FX = 'data/cnb_daily_eur_fixings_20260912/eurczk_daily.csv'
CANDIDATES = 'data/paper_replication/a6_inputs_20260912/candidate_inputs_long.csv'
BRENT = 'bbg__brent_front_reference__month_mean'
INPUTS = ['output/independent_path_frozen_inputs.csv', 'tests/fixtures/cleanup/cnb_core_mm.csv', 'data/release_calendar_cz_cpi.csv', FX, CANDIDATES]


def annual(monthly_rate):
    return 100 * np.expm1(np.log1p(monthly_rate / 100).rolling(12, min_periods=12).sum())


def quarter_mean(monthly, quarter, available=None, clock=None):
    """Quarter average; with `available` and `clock`, only months released by the clock (NaN unless all three are)."""
    q = pd.Period(quarter, 'Q'); months = pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M'); values = monthly.reindex(months)
    if available is not None:
        values = values.where((available.reindex(months) <= clock).to_numpy())
    return float(values.mean()) if values.notna().all() else np.nan


def load_public():
    headline = c.monthly(INPUTS[0], 'headline_mm'); core = c.monthly(INPUTS[1], 'core')
    released = c.publication_dates(pd.period_range('2015-01', core.index.max(), freq='M'))
    fx = pd.read_csv(ROOT / FX, parse_dates=['date']).set_index('date').eurczk
    cand = pd.read_csv(ROOT / CANDIDATES, dtype={'period': str}); b = cand[cand.column.eq(BRENT)]
    brent = pd.Series(b.value.to_numpy(float), index=pd.PeriodIndex(b.period, freq='M')).sort_index()
    return dict(cpi=annual(headline), core=annual(core), released=released, fx=fx, brent=brent)


def cnb_frame(cnb_long):
    q = cnb_long[cnb_long.frequency.eq('Q') & cnb_long.indicator.notna()]
    if q.duplicated(['report_date', 'indicator', 'period']).any():
        raise ValueError('Duplicate CNB indicator cells')
    values = q.set_index(['report_date', 'indicator', 'period']).value
    weights = q[q.indicator.eq('core')].drop_duplicates('report_date').set_index('report_date').row_label.map(cnb_weight)
    reports = cnb_long.drop_duplicates('report_date')[['report_date', 'cutoff_date']].sort_values('report_date').reset_index(drop=True)
    return values, weights, reports


def news_at(values, weights, public, report, cutoff_next, partial=False):
    """News against report `report`, using only what was public by `cutoff_next`."""
    q_k = pd.Period(report, 'Q'); q_next = q_k + 1; clock = pd.Timestamp(cutoff_next) + pd.Timedelta(hours=23, minutes=59)
    got = {}
    for name in ('cpi', 'core'):
        months = pd.period_range(q_k.asfreq('M', 'start'), q_k.asfreq('M', 'end'), freq='M')
        seen = public[name].reindex(months).where((public['released'].reindex(months) <= clock).to_numpy())
        got[name] = float(seen.mean()) if (seen.notna().all() or (partial and seen.notna().any())) else np.nan
        got[name + '_months'] = int(seen.notna().sum())
    cpi_news = got['cpi'] - float(values.get((report, 'cpi', str(q_k)), np.nan))
    core_news = float(weights.get(report, np.nan)) * (got['core'] - float(values.get((report, 'core', str(q_k)), np.nan)))
    fixings = public['fx'].loc[:pd.Timestamp(cutoff_next)].iloc[-10:]
    month = pd.Period(cutoff_next, 'M') - 1
    return dict(cpi_news=cpi_news, core_news=core_news, noncore_news=cpi_news - core_news,
                fx_news=float(100 * np.log(fixings.mean() / values.get((report, 'czk_eur', str(q_next)), np.nan))) if len(fixings) == 10 else np.nan,
                brent_news=float(100 * np.log(public['brent'].get(month, np.nan) / values.get((report, 'brent', str(q_next)), np.nan))),
                months_of_quarter_released=got['cpi_months'], fx_window_end=str(fixings.index[-1].date()) if len(fixings) else None, brent_month=str(month))


def build_panel(cnb_long, public):
    values, weights, reports = cnb_frame(cnb_long); rows = []
    for k in range(len(reports) - 1):
        now, nxt = reports.iloc[k], reports.iloc[k + 1]; q_next = pd.Period(nxt.report_date, 'Q')
        if q_next != pd.Period(now.report_date, 'Q') + 1:
            raise ValueError('Reports are expected one calendar quarter apart')
        news = news_at(values, weights, public, now.report_date, nxt.cutoff_date)
        if news['months_of_quarter_released'] != 3:
            raise AssertionError(f'The quarter of report {now.report_date} was not fully released by the next cutoff')
        for j in HORIZONS:
            target = str(q_next + j)
            rows.append(dict(pair=k, report=now.report_date, next_report=nxt.report_date, next_cutoff=nxt.cutoff_date, j=j, target=target,
                             revision=float(values.get((nxt.report_date, 'cpi', target), np.nan) - values.get((now.report_date, 'cpi', target), np.nan)), **news))
    return pd.DataFrame(rows)


def fit(x, y):
    return np.linalg.lstsq(x, y, rcond=None)[0] if x.shape[1] else np.zeros(0)


def predictions(panel):
    out = []
    for j in HORIZONS:
        data = panel[panel.j.eq(j)].sort_values('pair').reset_index(drop=True)
        for model, columns in MODELS.items():
            x = data[columns].to_numpy(float); y = data.revision.to_numpy(float)
            for scheme in ('leave_one_out', 'expanding'):
                for i in range(len(data)):
                    train = np.arange(len(data)) != i if scheme == 'leave_one_out' else np.arange(len(data)) < i
                    if scheme == 'expanding' and i < 8:
                        continue
                    beta = fit(x[train], y[train])
                    out.append(dict(scheme=scheme, model=model, j=j, pair=int(data.pair[i]), report=data.report[i], target=data.target[i],
                                    predicted=float(x[i] @ beta) if len(beta) else 0., actual=float(y[i])))
    return pd.DataFrame(out)


def scores(pred):
    rows = []
    for (scheme, model, j), g in pred.groupby(['scheme', 'model', 'j']):
        big = g[g.actual.abs().ge(MATERIAL) & g.predicted.ne(0)]
        rows.append(dict(scheme=scheme, model=model, j=j, n=len(g), rmse=float(np.sqrt(((g.predicted - g.actual) ** 2).mean())),
                         zero_rmse=float(np.sqrt((g.actual ** 2).mean())), correlation=float(g.predicted.corr(g.actual)) if g.predicted.std() > 0 else np.nan,
                         material_n=len(big), sign_hit_rate=float((np.sign(big.predicted) == np.sign(big.actual)).mean()) if len(big) else np.nan))
    table = pd.DataFrame(rows); table['rmse_vs_zero_pct'] = 100 * (table.rmse / table.zero_rmse - 1)
    return table


def coefficients(panel):
    rows = []
    for j in HORIZONS:
        data = panel[panel.j.eq(j)]
        for model, columns in MODELS.items():
            if not columns:
                continue
            x = data[columns].to_numpy(float); y = data.revision.to_numpy(float); beta = fit(x, y); resid = y - x @ beta
            cov = resid @ resid / (len(y) - len(beta)) * np.linalg.inv(x.T @ x)
            for name, b, se in zip(columns, beta, np.sqrt(np.diag(cov))):
                rows.append(dict(model=model, j=j, regressor=name, coefficient=float(b), standard_error=float(se), t=float(b / se), n=len(y),
                                 r2_uncentred=float(1 - resid @ resid / (y @ y))))
    return pd.DataFrame(rows)


def compare_with_path(pred, lead_dir, models=('STATE_FAST_R15', 'FOOD_NORM_SHIFT_R24', 'CONST_2')):
    """Same report/target rows, material revisions only: whose sign matched the next revision?"""
    lead = pd.read_csv(Path(lead_dir) / 'cnb_lead_pairs.csv'); lead = lead[lead.clock.eq('report') & lead.threshold.eq(.3) & lead.revision_eligible]
    rows = []
    for scheme in ('leave_one_out', 'expanding'):
        t = pred[pred.scheme.eq(scheme) & pred.model.eq('T2_CPI_FX_OIL') & pred.j.isin([2, 3])]
        for name in models:
            z = lead[lead.model.eq(name)].merge(t[['report', 'target', 'predicted', 'actual']], left_on=['report_date', 'quarter'], right_on=['report', 'target'])
            z = z[z.actual.abs().ge(MATERIAL)]
            rows.append(dict(scheme=scheme, path_model=name, n=len(z), path_gap_sign_hit=float((np.sign(z.deviation) == np.sign(z.actual)).mean()) if len(z) else np.nan,
                             tracker_sign_hit=float((np.sign(z.predicted) == np.sign(z.actual)).mean()) if len(z) else np.nan,
                             both_agree_n=int((np.sign(z.deviation) == np.sign(z.predicted)).sum()),
                             hit_when_both_agree=float((np.sign(z.predicted) == np.sign(z.actual))[np.sign(z.deviation) == np.sign(z.predicted)].mean()) if len(z) else np.nan))
    return pd.DataFrame(rows)


def live_reading(cnb_long, public, panel):
    values, weights, reports = cnb_frame(cnb_long); last = reports.iloc[-1]; today = public['fx'].index.max()
    news = news_at(values, weights, public, last.report_date, today.date().isoformat(), partial=True); q_next = pd.Period(last.report_date, 'Q') + 1; out = []
    for j in HORIZONS:
        data = panel[panel.j.eq(j)]; columns = MODELS['T2_CPI_FX_OIL']; beta = fit(data[columns].to_numpy(float), data.revision.to_numpy(float))
        x = np.array([news[k] for k in columns], float)
        out.append(dict(target=str(q_next + j), cnb_current=float(values.get((last.report_date, 'cpi', str(q_next + j)), np.nan)),
                        predicted_revision=float(x @ beta) if np.isfinite(x).all() else None))
    return dict(against_report=last.report_date, data_through=str(today.date()), news=news, partial=news['months_of_quarter_released'] < 3, readings=out,
                warning='Frozen repository data only. Partial-quarter news is not the quantity the coefficients were estimated on. Side product; no promotion claim.')


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--tables', type=Path, required=True); ap.add_argument('--lead', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True); args = ap.parse_args(); out = args.output; out.mkdir(parents=True, exist_ok=False)
    cnb_long = pd.read_csv(args.tables / 'cnb_mpr_indicators_long.csv'); public = load_public()
    panel = build_panel(cnb_long, public); panel.to_csv(out / 'panel.csv', index=False)
    pred = predictions(panel); pred.to_csv(out / 'predictions.csv', index=False)
    scores(pred).to_csv(out / 'scores.csv', index=False); coefficients(panel).to_csv(out / 'coefficients.csv', index=False)
    compare_with_path(pred, args.lead).to_csv(out / 'comparison_with_path.csv', index=False)
    (out / 'live_reading.json').write_text(json.dumps(live_reading(cnb_long, public, panel), indent=2, default=str), encoding='utf-8')
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps(dict(
        specification='docs/implementation/CNB_TRACKER_SPEC_2026-09-17.md', lane='conditioned: uses CNB forecasts; never an input to the independent forecast',
        inputs={**{k: sha(ROOT / k) for k in INPUTS}, 'tables': sha(args.tables / 'cnb_mpr_indicators_long.csv'), 'lead_pairs': sha(args.lead / 'cnb_lead_pairs.csv'),
                'tools/cnb_tracker/revisions.py': sha(__file__)},
        outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=2), encoding='utf-8')
    print('Completed CNB revision tracker', out, flush=True)


if __name__ == '__main__':
    main()
