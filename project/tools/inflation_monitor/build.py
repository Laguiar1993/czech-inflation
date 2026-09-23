"""M1: Czech Inflation Monitor — contribution engine, base-effect ledger, pipeline and CNB strips, one-page note.

    python -m tools.inflation_monitor.build --output output/inflation_monitor_20260922

Reads the CZSO group panel (37 COICOP-2018 groups, 2026 basket weights), the Bloomberg snapshots, the R31B lane path
at its latest origin and the CNB rounds replay data; writes the tables, monitor_data.json, note.md, monitor.html
(from template.html) and a hash manifest. Every number on the page comes from these files.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.model_register_20260921.build import load_snapshots, monthly

HERE = Path(__file__).resolve().parent
CATS = ROOT / 'data/research_r18/categories'
INPUTS = dict(levels=CATS / 'monthly_levels.csv', weights=CATS / 'basket_weights_long.csv', metadata=CATS / 'series_metadata.csv', broad=ROOT / 'data/core_split/broad_yoy.csv',
              food_levels=ROOT / 'data/bloomberg_inputs_20260922_foodppi/path/food_log_levels.csv', path_rows=ROOT / 'output/bloomberg_lane_20260922_foodppi/path/path_rows.csv',
              replay=ROOT / 'output/cnb_rounds_v3/replay_data.json', survey=ROOT / 'data/czcpmom_survey_history_extended.csv', forecasts=ROOT / 'output/independent_nowcast_forecasts.csv')
TICKERS = ['CZCPYOY Index', 'CZCPMOM Index', 'CZCIPM Index', 'CZCIXM Index', 'CZCIRM Index', 'CZCPF Index', 'EPP0BCCZ Index', 'CZEIIMOM Index', 'CZPPA10M Index']
NORM_YEARS = [2015, 2016, 2017, 2018, 2019, 2024, 2025]
SHOCK = (pd.Period('2021-01', 'M'), pd.Period('2023-12', 'M'))
BLOCKS = {
    'food': dict(label='Food & non-alcoholic beverages', short='Food', groups=['food', 'nonalcoholic_beverages']),
    'alcohol_tobacco': dict(label='Alcohol & tobacco', short='Alcohol & tobacco', groups=['alcoholic_beverages', 'tobacco']),
    'energy': dict(label='Household energy', short='Energy', groups=['household_energy']),
    'vehicle_operation': dict(label='Vehicle operation incl. fuel', short='Fuel & vehicle op.', groups=['vehicle_operation']),
    'rents': dict(label='Rents (imputed & actual)', short='Rents', groups=['imputed_rent', 'actual_rent']),
    'catering': dict(label='Catering & accommodation', short='Catering', groups=['catering', 'accommodation']),
    'other_services': dict(label='Other services & mixed', short='Other services', groups=['housing_maintenance', 'water_housing_services', 'household_goods_services', 'health', 'passenger_transport', 'transport_postal_services', 'ict_services', 'recreation_services', 'cultural_services', 'package_holidays', 'education', 'insurance_financial_services', 'personal_social_misc']),
    'core_goods': dict(label='Core goods', short='Core goods', groups=['clothing', 'footwear', 'furniture', 'household_textiles', 'household_appliances', 'tableware_utensils', 'house_garden_tools', 'vehicle_purchases', 'ict_equipment', 'recreation_durables', 'other_recreation_goods', 'garden_pets_goods', 'musical_instruments_media', 'books_stationery']),
}
PIPELINE_PAIRS = [('farm_prices', 'food_cpi'), ('food_ppi', 'food_cpi'), ('domestic_ppi', 'core_goods'), ('domestic_ppi', 'core'), ('import_prices', 'core_goods'), ('domestic_ppi', 'services')]
PIPELINE_LABELS = dict(farm_prices='Farm-gate prices (CZSO basket)', food_ppi='Food-products PPI (CZPPA10M, cumulated)', domestic_ppi='Domestic PPI B+C (EPP0BCCZ)', import_prices='Import prices (CZEIIMOM, cumulated)',
                       food_cpi='Food CPI (CZCPF)', core_goods='Core goods (block)', core='CNB core (CZCIXM)', services='Services (block: other services + catering)')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_periods(path, **kw):
    d = pd.read_csv(path, index_col=0, float_precision='round_trip', **kw); d.index = pd.PeriodIndex(d.index, freq='M'); return d


def seasonal_norm(mm, years=NORM_YEARS):
    """Median m/m of each calendar month over the norm years, as a Series indexed 1..12."""
    z = mm[mm.index.year.isin(years)]; return z.groupby(z.index.month).median()


def momentum_3m_ann(mm, norm):
    """4 x sum over the last three months of (m/m - norm of the calendar month) + the twelve monthly norms."""
    excess = mm - pd.Series([norm.get(p.month, np.nan) for p in mm.index], index=mm.index)
    return 4 * excess.rolling(3).sum() + float(norm.reindex(range(1, 13)).sum())


def yy_from_mm(mm):
    return 100 * np.expm1(np.log1p(mm / 100).rolling(12).sum())


def xcorr(x, y, lags, start=None, end=None, exclude=None):
    out = {}
    for k in lags:
        z = pd.concat([x.shift(k).rename('x'), y.rename('y')], axis=1).dropna()
        if start is not None:
            z = z.loc[start:end]
        if exclude is not None:
            z = z[~z.index.to_series().between(exclude[0], exclude[1])]
        out[k] = float(z.x.corr(z.y)) if len(z) > 24 else np.nan
    return pd.Series(out)


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    bbg = load_snapshots(); s = {t: monthly(bbg[t]) for t in TICKERS}
    head_yy = s['CZCPYOY Index']; head_mm = pd.concat([s['CZCIPM Index'], s['CZCPMOM Index']]); head_mm = head_mm[~head_mm.index.duplicated(keep='last')].sort_index()
    core_yy = yy_from_mm(s['CZCIXM Index']); reg_yy = yy_from_mm(s['CZCIRM Index']); food_cpi_yy = 100 * (s['CZCPF Index'] / s['CZCPF Index'].shift(12) - 1)
    broad = read_periods(INPUTS['broad'])
    # ---- groups and blocks ----------------------------------------------------------------------------------
    lv = read_periods(INPUTS['levels']); meta = pd.read_csv(INPUTS['metadata']).set_index('column')
    w = pd.read_csv(INPUTS['weights']); w = w[(w.effective_year == 2026) & w.mapped_series.notna()].set_index('mapped_series').weight_permille
    assigned = [g for b in BLOCKS.values() for g in b['groups']]
    if sorted(assigned) != sorted(lv.columns) or len(assigned) != len(set(assigned)):
        raise ValueError('blocks must partition the 37 groups exactly')
    if abs(w.reindex(assigned).sum() - 1000) > 1e-6:
        raise ValueError('2026 weights of the 37 groups must sum to 1000')
    g_yy = 100 * (lv / lv.shift(12) - 1); g_mm = 100 * (lv / lv.shift(1) - 1)
    g_norm = {g: seasonal_norm(g_mm[g]) for g in lv.columns}
    g_mom = pd.DataFrame({g: momentum_3m_ann(g_mm[g], g_norm[g]) for g in lv.columns})
    g_contrib = g_yy.mul(w.reindex(g_yy.columns) / 1000, axis=1)
    blocks = {}; rows = []
    for key, b in BLOCKS.items():
        ww = w.reindex(b['groups']); share = ww / ww.sum()
        b_yy = (g_yy[b['groups']] * share).sum(axis=1); b_mm = (g_mm[b['groups']] * share).sum(axis=1)
        b_norm = pd.Series({mth: float(sum(g_norm[g].get(mth, np.nan) * share[g] for g in b['groups'])) for mth in range(1, 13)})
        blocks[key] = dict(label=b['label'], short=b['short'], groups=b['groups'], weight_permille=float(ww.sum()), group_weights={g: float(ww[g]) for g in b['groups']})
        frame = pd.DataFrame(dict(block=key, yy=b_yy, mm=b_mm, contribution=g_contrib[b['groups']].sum(axis=1), d3_yy=b_yy - b_yy.shift(3), momentum_3m_ann=momentum_3m_ann(b_mm, b_norm)))
        rows.append(frame)
    contrib = pd.concat(rows).rename_axis('month').reset_index(); contrib['month'] = contrib.month.astype(str)
    contrib = contrib[contrib.month >= '2016-01']; contrib.to_csv(out / 'contributions.csv', index=False)
    wide = contrib.pivot(index='month', columns='block', values='contribution'); wide.index = pd.PeriodIndex(wide.index, freq='M')
    residual = head_yy.reindex(wide.index) - wide.sum(axis=1)
    latest = lv.index.max(); latest_s = str(latest)
    groups_latest = pd.DataFrame(dict(group=lv.columns, coicop=[meta.loc[g, 'coicop2018_code'] for g in lv.columns], label_cs=[meta.loc[g, 'label_cs'] for g in lv.columns],
                                      block=[next(k for k, b in BLOCKS.items() if g in b['groups']) for g in lv.columns], weight_permille=w.reindex(lv.columns).to_numpy(),
                                      yy=g_yy.loc[latest].to_numpy(), yy_year_ago=g_yy.loc[latest - 12].to_numpy(), contribution=g_contrib.loc[latest].to_numpy(), d3_yy=(g_yy.loc[latest] - g_yy.loc[latest - 3]).to_numpy(), momentum_3m_ann=g_mom.loc[latest].to_numpy()))
    groups_latest = groups_latest.sort_values('contribution', ascending=False); groups_latest.to_csv(out / 'groups_latest.csv', index=False)
    # ---- base-effect ledger ---------------------------------------------------------------------------------
    norm = seasonal_norm(head_mm); last_known = head_mm.index.max()
    path = pd.read_csv(INPUTS['path_rows']); origin = path.origin.max(); pr = path[path.origin.eq(origin)].set_index('h'); model_mm = {pd.Period(origin, 'M') + int(h): float(v) for h, v in pr.mm_lane.items() if h >= 1}
    ledger = []; log_hist = np.log1p(head_mm / 100)
    def implied(assume):
        series = log_hist.copy()
        for t, v in assume.items():
            series.loc[t] = np.log1p(v / 100)
        series = series.sort_index(); return 100 * np.expm1(series.rolling(12).sum())
    assume_norm = {}; assume_model = {}
    for i in range(1, 13):
        t = last_known + i; drop = float(head_mm.get(t - 12, np.nan)); nm = float(norm.get(t.month, np.nan))
        known = float(head_mm.get(t, np.nan)); model = known if np.isfinite(known) else model_mm.get(t, np.nan); model_source = 'published' if np.isfinite(known) else ('roster path' if t in model_mm else 'seasonal norm (beyond the path)')
        if not np.isfinite(model):
            model = nm
        assume_norm[t] = nm; assume_model[t] = model
        ledger.append(dict(month=str(t), dropping_out=drop, seasonal_norm=nm, model_mm=model, model_source=model_source, base_effect=nm - drop, momentum=model - nm, change_under_model=model - drop))
    yy_norm = implied(assume_norm); yy_model = implied(assume_model)
    for r in ledger:
        t = pd.Period(r['month'], 'M'); r['implied_yy_norm'] = float(yy_norm.loc[t]); r['implied_yy_model'] = float(yy_model.loc[t])
        r['flag'] = 'base effect' if abs(r['change_under_model']) >= .2 and abs(r['base_effect']) >= .7 * abs(r['change_under_model']) else ('momentum' if abs(r['change_under_model']) >= .2 else '')
    ledger = pd.DataFrame(ledger); ledger.to_csv(out / 'base_effects.csv', index=False)
    # ---- pipeline ------------------------------------------------------------------------------------------
    dom = s['EPP0BCCZ Index']; imp = (100 * np.log1p(s['CZEIIMOM Index'] / 100)).cumsum(); fppi = (100 * np.log1p(s['CZPPA10M Index'] / 100)).cumsum(); fl = read_periods(INPUTS['food_levels'])
    X = dict(domestic_ppi=100 * (dom / dom.shift(12) - 1), import_prices=imp - imp.shift(12), food_ppi=fppi - fppi.shift(12), farm_prices=fl.agri4 - fl.agri4.shift(12))
    serv_keys = ['other_services', 'catering']; serv_w = sum(blocks[k]['weight_permille'] for k in serv_keys)
    byy = contrib.pivot(index='month', columns='block', values='yy'); byy.index = pd.PeriodIndex(byy.index, freq='M')
    Y = dict(food_cpi=food_cpi_yy, core_goods=byy.core_goods, core=core_yy, services=sum(byy[k] * blocks[k]['weight_permille'] for k in serv_keys) / serv_w)
    ll = []
    for xn, yn in PIPELINE_PAIRS:
        for sample, kw in [('2015-2026', dict(start='2015-01', end=str(latest))), ('excluding 2021-2023', dict(start='2015-01', end=str(latest), exclude=SHOCK))]:
            c = xcorr(X[xn], Y[yn], range(0, 13), **kw)
            ll.append(dict(x=xn, y=yn, x_label=PIPELINE_LABELS[xn], y_label=PIPELINE_LABELS[yn], sample=sample, best_lag=int(c.idxmax()) if c.notna().any() else None, best_corr=float(c.max()) if c.notna().any() else None, corr_lag0=c.get(0), corr_lag3=c.get(3), corr_lag6=c.get(6), corr_lag12=c.get(12)))
    leadlag = pd.DataFrame(ll); leadlag.to_csv(out / 'pipeline_leadlag.csv', index=False)
    readings = {k: dict(label=PIPELINE_LABELS[k], yy=float(v.dropna().iloc[-1]), month=str(v.dropna().index[-1]), yy_3m_ago=float(v.dropna().iloc[-4]), yy_year_ago=float(v.dropna().iloc[-13])) for k, v in X.items()}
    # ---- CNB strip and prints -----------------------------------------------------------------------------
    replay = json.loads(INPUTS['replay'].read_text(encoding='utf-8')); report = replay['reportsByClock']['report'][-1]
    roster_monthly = {m: v for m, v in report['paths'][replay['roster_id']]}
    def qmean(q):
        y, qq = int(q[:4]), int(q[-1]); months = [f'{y}-{mth:02d}' for mth in range(3 * qq - 2, 3 * qq + 1)]; vals = [roster_monthly.get(mm) for mm in months]
        return float(np.mean(vals)) if all(v is not None for v in vals) else None
    cnb_strip = [dict(quarter=r['quarter'], cnb=r['value'], roster=qmean(r['quarter'])) for r in report['cnb'][:6]]
    realised_q = {}
    for p, v in head_yy.items():
        q = f'{p.year}Q{(p.month - 1) // 3 + 1}'; realised_q.setdefault(q, []).append(float(v))
    for r in cnb_strip:
        r['realised_months'] = realised_q.get(r['quarter'], [])
    survey = pd.read_csv(INPUTS['survey']); fc = pd.read_csv(INPUTS['forecasts'], index_col='period')
    prints = []
    for _, r in survey.tail(3).iterrows():
        prints.append(dict(month=r.target_month, release=str(r.release_dt)[:10], actual=float(r.actual), consensus=float(r.survey_median), base_recorded=float(fc.HARD_BASE.get(r.target_month, np.nan)) if r.target_month in fc.index else None, era=r.era))
    # ---- headline numbers -------------------------------------------------------------------------------------
    latest_head = head_yy.index.max()
    def series_tail(x, n=36):
        z = x.dropna().tail(n); return [[str(p), float(v)] for p, v in z.items()]
    numbers = dict(headline_yy=float(head_yy.loc[latest_head]), headline_month=str(latest_head), headline_yy_prev=float(head_yy.loc[latest_head - 1]), core_yy=float(core_yy.loc[latest]), core_yy_year_ago=float(core_yy.loc[latest - 12]), regulated_yy=float(reg_yy.loc[latest]),
                   services_yy=float(broad.services.loc[latest]), goods_yy=float(broad.goods.loc[latest]), food_yy=float(food_cpi_yy.loc[latest]), groups_month=latest_s,
                   peak=dict(month=str(head_yy.loc['2021':].idxmax()), headline=float(head_yy.loc['2021':].max()), core=float(core_yy.loc['2021':].max()), core_month=str(core_yy.loc['2021':].idxmax())))
    latest_blocks = contrib[contrib.month.eq(latest_s)].set_index('block')
    top = latest_blocks.sort_values('contribution', ascending=False)
    hist_months = [str(p) for p in wide.index[-36:]]
    data = dict(title='Czech Inflation Monitor', built=datetime.now(timezone.utc).strftime('%Y-%m-%d'), groups_month=latest_s, headline_month=str(latest_head), numbers=numbers, blocks=blocks,
                latest=[dict(block=k, label=blocks[k]['label'], short=blocks[k]['short'], weight=blocks[k]['weight_permille'], yy=float(r.yy), contribution=float(r.contribution), d3_yy=float(r.d3_yy), momentum=float(r.momentum_3m_ann),
                             contribution_year_ago=float(wide.loc[latest - 12, k]), yy_year_ago=float(byy.loc[latest - 12, k])) for k, r in top.iterrows()],
                residual=dict(latest=float(residual.loc[latest]), note='published headline y/y minus the sum of the eight fixed-weight contributions'),
                history=dict(months=hist_months, contributions={k: [float(wide.loc[pd.Period(m, 'M'), k]) for m in hist_months] for k in BLOCKS}, residual=[float(residual.loc[pd.Period(m, 'M')]) for m in hist_months], headline=[float(head_yy.loc[pd.Period(m, 'M')]) for m in hist_months],
                             core=[float(core_yy.loc[pd.Period(m, 'M')]) for m in hist_months], services=[float(broad.services.loc[pd.Period(m, 'M')]) for m in hist_months], goods=[float(broad.goods.loc[pd.Period(m, 'M')]) for m in hist_months]),
                disinflation=dict(from_month=numbers['peak']['month'], to_month=latest_s, changes={k: float(wide.loc[latest, k] - wide.loc[pd.Period(numbers['peak']['month'], 'M'), k]) for k in BLOCKS}),
                groups_latest=groups_latest.round(4).to_dict('records'), ledger=ledger.round(4).to_dict('records'), ledger_meta=dict(last_known=str(last_known), path_origin=origin, norm_years=NORM_YEARS, norm_by_month={int(k): float(v) for k, v in norm.items()}),
                pipeline=dict(readings=readings, leadlag=leadlag.round(3).to_dict('records')), cnb=dict(report_date=report['report_date'], report_label=f"{report['season']} {report['year']} report", origin=report['origin'], strip=cnb_strip), prints=prints)
    (out / 'monitor_data.json').write_text(json.dumps(data, indent=1, allow_nan=False), encoding='utf-8')
    (out / 'blocks.json').write_text(json.dumps(blocks, indent=1), encoding='utf-8')
    (out / 'note.md').write_text(note(data), encoding='utf-8')
    html = (HERE / 'template.html').read_text(encoding='utf-8').replace('__DATA__', json.dumps(data, allow_nan=False)); (out / 'monitor.html').write_text(html, encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs={k: sha(p) for k, p in INPUTS.items()}, snapshots={p.parent.name: sha(p) for p in sorted((ROOT / 'data/market_snapshots').glob('*/history_long.csv'))},
                                                       code=sha(__file__), template=sha(HERE / 'template.html'), outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    print(note(data))


def note(d):
    n = d['numbers']; top = d['latest']; ups = [b for b in top if b['contribution'] > 0][:4]; downs = sorted([b for b in top if b['contribution'] < 0], key=lambda b: b['contribution'])[:3]
    fmt = lambda b: f"{b['label'].lower()} {b['contribution']:+.2f} pp ({b['yy']:.1f}% y/y)"
    led = d['ledger']; l6 = led[:6]; base_flags = [r['month'] for r in led if r['flag'] == 'base effect']
    dis = d['disinflation']; falls = sorted(dis['changes'].items(), key=lambda kv: kv[1])[:4]
    rd = d['pipeline']['readings']; cnb = d['cnb']
    lines = [f"# Czech Inflation Monitor — {d['built']}", '',
             f"**Headline {n['headline_yy']:.1f}% y/y ({d['headline_month']}, flash), core {n['core_yy']:.1f}% ({d['groups_month']}; {n['core_yy_year_ago']:.1f}% a year ago), regulated {n['regulated_yy']:.1f}%. CZSO services {n['services_yy']:.1f}%, goods {n['goods_yy']:.1f}%, food {n['food_yy']:.1f}%.** Peak: headline {n['peak']['headline']:.1f}% and core {n['peak']['core']:.1f}% in {n['peak']['month']}.", '',
             f"**What holds headline up ({d['groups_month']}, contributions with 2026 weights):** " + '; '.join(fmt(b) for b in ups) + '.',
             f"**What holds it down:** " + '; '.join(fmt(b) for b in downs) + f". Residual of the fixed-weight sum against the published y/y: {d['residual']['latest']:+.2f} pp.", '',
             f"**Since the peak ({dis['from_month']} → {dis['to_month']}):** the largest falls in contribution are " + ', '.join(f"{d['blocks'][k]['label'].lower()} {v:+.1f} pp" for k, v in falls) + '.', '',
             f"**Base effects (next six months, last known m/m {d['ledger_meta']['last_known']}; published months used where known, the roster path's m/m after):** with normal seasonal m/m headline y/y would read " + ', '.join(f"{r['month']} {r['implied_yy_norm']:.1f}" for r in l6) + f"; with the roster path " + ', '.join(f"{r['month']} {r['implied_yy_model']:.1f}" for r in l6) + '. ' + (f"Months whose move is mostly drop-out arithmetic: {', '.join(base_flags)}." if base_flags else 'No month in the next twelve is mostly drop-out arithmetic.'), '',
             f"**Pipeline (y/y):** farm prices {rd['farm_prices']['yy']:+.1f}%, food PPI {rd['food_ppi']['yy']:+.1f}%, domestic PPI {rd['domestic_ppi']['yy']:+.1f}%, import prices {rd['import_prices']['yy']:+.1f}%. Farm and food-PPI lead food CPI by 1–3 months in every sample; PPI → core goods only inside the 2021–23 shock (see the lead-lag table).", '',
             f"**CNB ({cnb['report_label']}, {cnb['report_date']}) vs roster path (origin {cnb['origin']}), quarterly y/y:** " + '; '.join(f"{r['quarter']} CNB {r['cnb']:.1f} / roster {r['roster']:.1f}" if r['roster'] is not None else f"{r['quarter']} CNB {r['cnb']:.1f} / roster —" for r in cnb['strip'][:4]) + '.', '',
             '**Last prints (m/m):** ' + '; '.join(f"{p['month']} actual {p['actual']:.1f}, consensus {p['consensus']:.1f}" + (f", BASE {p['base_recorded']:.2f}" if p['base_recorded'] is not None else ', BASE not recorded (live lane pending)') for p in d['prints']) + '.', '',
             'Method: contributions = 2026 basket weight × group y/y (fixed weights; the residual is shown, not absorbed); the roster-path column differs from the rounds page because the published July and August prints replace the values the path had for them; momentum = annualised three-month excess over the calendar-month median m/m of 2015–2019 and 2024–2025, plus the annual norm; base effect = norm minus the m/m dropping out; core and regulated y/y compounded from the CNB monthly series.']
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); args = ap.parse_args()
    build(args.output if args.output.is_absolute() else ROOT / args.output)


if __name__ == '__main__':
    main()
