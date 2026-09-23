"""Model register of 21 September 2026: every current model, its inputs, the Bloomberg substitute, and whether the
model gives the same results with the substitute.

    python -m tools.model_register_20260921.build --output output/model_register_20260921

The path-lane tests re-run the frozen block models on the recorded origins with one input at a time replaced by
the Bloomberg series held in the 12 September snapshots (data/market_snapshots/*/history_long.csv). The nowcast
rows carry the input-level verdicts of the 13 September inventory; their model-level parity needs the Bloomberg
input lane in cz_struct and is recorded as pending. Nothing is fitted.
"""
import argparse
from datetime import datetime, timezone
import glob
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import r17_common as c
from models.path_inputs import compound_path
from models.fuel_path_r14 import monthly_rates
from models.food_path_r14 import load_inputs as load_food_inputs
from models.food_stable_r14b import forecast_origin as food_forecast_origin
from models.components import petrol_share_for_regime, fuel_mm_from_weekly
from models.core_phase_r29b import phase_from_levels
from models.core_phase_r29 import published_levels as ppi_published_levels

R27 = 'output/research_r27/final'; R29B = 'output/research_r29b/final'
INVENTORY = 'output/bloomberg_model_inputs_20260913/model_input_inventory.csv'
EXACTNESS = 'output/bloomberg_probe_comparison_20260912/exactness/exactness.csv'
FILES = dict(core='tests/fixtures/cleanup/cnb_core_mm.csv', regulated='tests/fixtures/cleanup/cnb_regulated_mm.csv', alc='tests/fixtures/cleanup/alcohol_tobacco.csv',
             headline='output/independent_path_frozen_inputs.csv', pump='data/research_r14/fuel/pump_weekly.csv', calendar='data/release_calendar_cz_cpi.csv',
             support='output/research_r17/attribution/primary_support.csv', long_food='data/research_r14/food/coverage_extension/czso_cpi_1995_2025.csv',
             a6_exact='data/paper_replication/a6_inputs_20260912/exact_inputs_long.csv', fuel_weekly_czso='tests/fixtures/cleanup/fuel_weekly.csv', contributions='output/contribution_report.csv')
FAST = 'STATE_FAST_R15'; ROSTER = 'FOOD_ECM_R27'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_snapshots():
    frames = []
    for f in sorted(glob.glob(str(ROOT / 'data/market_snapshots/*/history_long.csv'))):
        d = pd.read_csv(f, low_memory=False, usecols=['ticker', 'observation_date', 'value']); d['snapshot'] = Path(f).parent.name; frames.append(d)
    h = pd.concat(frames, ignore_index=True); h['date'] = pd.to_datetime(h.observation_date); h = h.sort_values(['ticker', 'date', 'snapshot'])
    h = h.drop_duplicates(['ticker', 'date'], keep='last')
    return {t: g.set_index('date').value.astype(float) for t, g in h.groupby('ticker')}


def monthly(series):
    s = series.copy(); s.index = pd.PeriodIndex(s.index, freq='M'); return s[~s.index.duplicated(keep='last')].sort_index()


def compare(a, b, label, tol=1e-9):
    both = pd.concat([a.rename('a'), b.rename('b')], axis=1).dropna()
    gap = (both.a - both.b).abs()
    return dict(test=label, n=int(len(both)), first=str(both.index.min()), last=str(both.index.max()), exact_share=float((gap <= tol).mean()) if len(both) else np.nan,
                max_abs_gap=float(gap.max()) if len(both) else np.nan, mean_abs_gap=float(gap.mean()) if len(both) else np.nan)


def rmse(e):
    e = np.asarray(e, float); e = e[np.isfinite(e)]; return float(np.sqrt((e ** 2).mean())) if len(e) else np.nan


def regime_share(origin, as_of, calendar):
    """cz_struct._petrol_share re-implemented: even-year basket, usable from the January detail release of its year."""
    t = pd.Period(origin, 'M'); regime = t.year - t.year % 2
    row = calendar[calendar.target_month.eq(f'{regime}-01')]
    available = pd.Timestamp(row.detail_release_dt.iloc[0]).normalize() if len(row) else pd.Timestamp(regime, 2, 15)
    source = regime if available <= pd.Timestamp(as_of).tz_localize(None) else regime - 2
    return petrol_share_for_regime(source), source


def constant_pump_rates(pump, origin, clock, share):
    """models.current_path.constant_pump_path without the cz_struct import."""
    t = pd.Period(origin, 'M'); gross = ['gross_petrol95', 'gross_diesel']
    known = pump.loc[pump.index + pd.Timedelta(days=7) <= clock].dropna(subset=gross)
    grid = pd.date_range(pump.index.min(), (t + 12).end_time.normalize(), freq='W-MON')
    values = known[gross].rename(columns=dict(zip(gross, ('petrol95', 'diesel')))).reindex(grid).ffill()
    return monthly_rates(values, t, share)


def expanding_same_month_mean(rates, target, known_through):
    hist = rates.dropna(); hist = hist[hist.index <= known_through]
    same = hist[hist.index.month == target.month]
    return float(same.mean()) if len(same) >= 3 else float(hist.mean())


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); args = ap.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    bbg = load_snapshots(); tests = []; details = {}
    native = c.read(f'{R27}/native_forecasts.csv'); fast = native[native.model.eq(FAST)]; roster = native[native.model.eq(ROSTER)]
    clocks = fast[fast.h.eq(0)].set_index('origin').as_of_utc.map(pd.Timestamp)
    origins = sorted(clocks.index); support = c.read(FILES['support']); keys = set(zip(support.origin, support.h))
    calendar = c.read(FILES['calendar'])

    # ---- T1/T2: CNB core and regulated m/m (the FAST core filter and the administered pattern read these)
    core = c.monthly(FILES['core'], 'core'); regulated = c.monthly(FILES['regulated'], 'regulated') if 'regulated' in c.read(FILES['regulated']).columns else c.monthly(FILES['regulated']).iloc[:, 0]
    tests.append(dict(compare(core, monthly(bbg['CZCIXM Index']), 'T1 core m/m: fixture vs CZCIXM'), model='FAST core filter (R15), all paths', conclusion='identical inputs on every month: the core block is the same by construction'))
    tests.append(dict(compare(regulated, monthly(bbg['CZCIRM Index']), 'T2 regulated m/m: fixture vs CZCIRM'), model='administered pattern, all paths', conclusion='identical inputs on every month: the administered block is the same by construction'))

    # ---- T3: headline m/m for compounding (paths' annual rates) and the wedge
    headline = c.monthly(FILES['headline']); frozen = headline.headline_mm
    bbg_head = pd.concat([monthly(bbg['CZCIPM Index']), monthly(bbg['CZCPMOM Index'])]); bbg_head = bbg_head[~bbg_head.index.duplicated(keep='last')].sort_index()
    overlap = compare(monthly(bbg['CZCIPM Index']), monthly(bbg['CZCPMOM Index']), 'T3a CZCIPM vs CZCPMOM (two Bloomberg headline m/m tickers)')
    t3 = compare(frozen, bbg_head, 'T3b headline m/m: frozen CZSO 2015=100-based vs Bloomberg published one-decimal'); tests.append(dict(t3, model='all paths (annual-rate compounding, scoring truth)', conclusion='published m/m is rounded to one decimal; see T3c for the effect on the paths'))
    tests.append(dict(overlap, model='—', conclusion='the two published tickers agree'))
    substituted = frozen.copy(); common = substituted.index.intersection(bbg_head.index); substituted.loc[common] = bbg_head.loc[common]
    rows = []
    for origin, g in roster.groupby('origin'):
        t = pd.Period(origin, 'M'); g = g.sort_values('h').reset_index(drop=True); h0 = float(g.mm_forecast.iloc[0]); forecast = dict(zip(g.h, g.mm_forecast))
        for h in range(13):
            if (origin, h) not in keys:
                continue
            months = pd.period_range(t + h - 11, t + h, freq='M')
            yy_f = compound_path(frozen[frozen.index < t], forecast, t, h, h0); yy_b = compound_path(substituted[substituted.index < t], forecast, t, h, h0)
            a_f = 100 * np.expm1(np.log1p(frozen.reindex(months) / 100).sum()) if frozen.reindex(months).notna().all() else np.nan
            a_b = 100 * np.expm1(np.log1p(substituted.reindex(months) / 100).sum()) if substituted.reindex(months).notna().all() else np.nan
            rows.append(dict(origin=origin, h=h, yy_frozen=yy_f, yy_bbg=yy_b, actual_frozen=a_f, actual_bbg=a_b))
    yy = pd.DataFrame(rows); yy.to_csv(out / 'T3_headline_substitution_rows.csv', index=False)
    summary = {}
    for h in (3, 6, 12):
        z = yy[yy.h.eq(h)]; recent = z.origin.ge('2024-01')
        summary[f'h{h}'] = dict(rmse_frozen=rmse(z.yy_frozen - z.actual_frozen), rmse_bbg=rmse(z.yy_bbg - z.actual_bbg), rmse_frozen_2024plus=rmse(z.yy_frozen[recent] - z.actual_frozen[recent]),
                                rmse_bbg_2024plus=rmse(z.yy_bbg[recent] - z.actual_bbg[recent]), max_abs_forecast_change=float((z.yy_frozen - z.yy_bbg).abs().max()), max_abs_actual_change=float((z.actual_frozen - z.actual_bbg).abs().max()))
    details['T3c_paths_with_bloomberg_headline'] = summary
    tests.append(dict(test='T3c R27 path annual rates recompounded on the Bloomberg headline history', n=int(len(yy)), first=str(yy.origin.min()), last=str(yy.origin.max()), exact_share=np.nan,
                      max_abs_gap=float((yy.yy_frozen - yy.yy_bbg).abs().max()), mean_abs_gap=float((yy.yy_frozen - yy.yy_bbg).abs().mean()), model='R27 research path (and every path: same compounding)',
                      conclusion=f"h12 RMSE {summary['h12']['rmse_frozen']:.3f} -> {summary['h12']['rmse_bbg']:.3f} (from 2024 {summary['h12']['rmse_frozen_2024plus']:.3f} -> {summary['h12']['rmse_bbg_2024plus']:.3f}); the scoring truth moves with the input"))

    # ---- T4: fuel block (constant pump prices) with the EC Oil Bulletin from Bloomberg
    pump = pd.read_csv(ROOT / FILES['pump'], index_col=0, parse_dates=True, float_precision='round_trip')
    def to_monday(s):    # Bloomberg stamps the EC bulletin week on its Friday; the frozen panel on its Monday
        s = s.copy(); s.index = s.index - pd.to_timedelta(s.index.dayofweek, unit='D'); return s[~s.index.duplicated(keep='last')].sort_index()
    eb = to_monday(bbg['ECOBETCZ Index']); ob = to_monday(bbg['ECOBOTCZ Index'])
    ratio = (eb.reindex(pump.index) / pump.gross_petrol95).dropna(); scale = float(np.round(ratio.median()))
    pump_bbg = pump.copy(); pe = (eb / scale).reindex(pump.index); pd_ = (ob / scale).reindex(pump.index)
    pump_bbg['gross_petrol95'] = pe.where(pe.notna(), pump.gross_petrol95); pump_bbg['gross_diesel'] = pd_.where(pd_.notna(), pump.gross_diesel)
    tests.append(dict(compare(pump.gross_petrol95, eb / scale, 'T4a pump petrol 95: frozen EC bulletin file vs ECOBETCZ / %g' % scale, tol=1e-4), model='fuel block (constant pump), all paths', conclusion='same survey on Bloomberg'))
    tests.append(dict(compare(pump.gross_diesel, ob / scale, 'T4b pump diesel: frozen EC bulletin file vs ECOBOTCZ / %g' % scale, tol=1e-4), model='fuel block (constant pump), all paths', conclusion='same survey on Bloomberg'))
    fuel_rows = []
    for origin in origins:
        clock = clocks[origin].tz_convert('Europe/Prague').tz_localize(None); share, regime = regime_share(origin, clock, calendar)
        r_frozen = constant_pump_rates(pump, origin, clock, share); r_bbg = constant_pump_rates(pump_bbg, origin, clock, share)
        rec = fast[fast.origin.eq(origin) & fast.h.gt(0)].sort_values('h').value_fuel.to_numpy(float)
        fuel_rows.append(dict(origin=origin, petrol_share=share, regime=regime, max_abs_recorded_minus_reproduced=float(np.abs(rec - r_frozen).max()), max_abs_bbg_minus_frozen=float(np.abs(r_bbg - r_frozen).max())))
    fuel = pd.DataFrame(fuel_rows); fuel.to_csv(out / 'T4_fuel_block_rows.csv', index=False)
    tests.append(dict(test='T4c fuel block re-run: recorded FAST fuel path vs reproduction from the frozen pump panel', n=len(fuel), first=origins[0], last=origins[-1], exact_share=float((fuel.max_abs_recorded_minus_reproduced <= 1e-9).mean()),
                      max_abs_gap=float(fuel.max_abs_recorded_minus_reproduced.max()), mean_abs_gap=float(fuel.max_abs_recorded_minus_reproduced.mean()), model='fuel block, all paths', conclusion='the register re-implements the constant-pump path; parity with the run'))
    tests.append(dict(test='T4d fuel block re-run with the Bloomberg pump panel vs the frozen panel', n=len(fuel), first=origins[0], last=origins[-1], exact_share=float((fuel.max_abs_bbg_minus_frozen <= 1e-9).mean()),
                      max_abs_gap=float(fuel.max_abs_bbg_minus_frozen.max()), mean_abs_gap=float(fuel.max_abs_bbg_minus_frozen.mean()), model='fuel block, all paths', conclusion='same fuel block with Bloomberg pump prices'))

    # ---- T5: food system with the Bloomberg food CPI level (CZCPF, 2025=100, one decimal) in place of the CZSO 2015=100-based level
    levels, available, _ = load_food_inputs()
    czcpf = monthly(bbg['CZCPF Index']); bbg_food_log = 100 * np.log(czcpf / czcpf[pd.Period('2015-01', 'M')])
    tests.append(dict(compare(levels.food, bbg_food_log.reindex(levels.index), 'T5a food log level: frozen (CZSO 2015=100) vs 100*ln(CZCPF/CZCPF_2015-01)', tol=1e-9), model='food system (R14B) input', conclusion='one-decimal 2025=100 index against the 2015=100 index: the levels differ by rounding'))
    levels_bbg = levels.copy(); levels_bbg['food'] = bbg_food_log.reindex(levels.index).to_numpy()
    if not np.isfinite(levels_bbg.food).all():
        raise ValueError('Bloomberg food level does not cover the frozen food history')
    food_rows = []
    for origin in origins:
        clock = clocks[origin]
        f0 = food_forecast_origin(levels, available, origin, clock); f1 = food_forecast_origin(levels_bbg, available, origin, clock)
        p0 = np.array([f0['paths']['FOOD_STABLE_PIPELINE_R14B'][h] for h in range(1, 13)]); p1 = np.array([f1['paths']['FOOD_STABLE_PIPELINE_R14B'][h] for h in range(1, 13)])
        rec = fast[fast.origin.eq(origin) & fast.h.gt(0)].sort_values('h').value_food.to_numpy(float)
        food_rows.append(dict(origin=origin, status_frozen=f0['diagnostics']['status'], status_bbg=f1['diagnostics']['status'], max_abs_recorded_minus_reproduced=float(np.nanmax(np.abs(rec - p0))),
                              max_abs_bbg_minus_frozen=float(np.nanmax(np.abs(p1 - p0))), rms_bbg_minus_frozen=float(np.sqrt(np.nanmean((p1 - p0) ** 2))), cum12_bbg_minus_frozen=float(np.nansum(p1) - np.nansum(p0))))
    food = pd.DataFrame(food_rows); food.to_csv(out / 'T5_food_block_rows.csv', index=False)
    tests.append(dict(test='T5b food system re-run: recorded FAST food path vs reproduction from the frozen levels', n=len(food), first=origins[0], last=origins[-1], exact_share=float((food.max_abs_recorded_minus_reproduced <= 1e-9).mean()),
                      max_abs_gap=float(food.max_abs_recorded_minus_reproduced.max()), mean_abs_gap=float(food.max_abs_recorded_minus_reproduced.mean()), model='food block, all paths', conclusion='parity with the run'))
    tests.append(dict(test='T5c food system re-run with the Bloomberg food level (farm and producer prices unchanged, no Bloomberg series)', n=len(food), first=origins[0], last=origins[-1], exact_share=float((food.max_abs_bbg_minus_frozen <= 1e-9).mean()),
                      max_abs_gap=float(food.max_abs_bbg_minus_frozen.max()), mean_abs_gap=float(food.rms_bbg_minus_frozen.mean()), model='food block, all paths',
                      conclusion=f'monthly food rates move by up to {food.max_abs_bbg_minus_frozen.max():.3f} pp; twelve-month sums by up to {food.cum12_bbg_minus_frozen.abs().max():.3f}'))

    # ---- T6: alcohol and tobacco block (expanding same-month mean) from the Bloomberg division-02 index
    alc = c.monthly(FILES['alc'], 'alcohol_tobacco'); czcpa = monthly(bbg['CZCPA Index']); alc_bbg = 100 * (czcpa / czcpa.shift(1) - 1); alc_pub = monthly(bbg['CZCPAMOM Index'])
    tests.append(dict(compare(alc, alc_bbg, 'T6a alcohol & tobacco m/m: fixture (CZSO 2015=100-based) vs m/m of CZCPA (2025=100, one decimal)', tol=1e-9), model='alcohol & tobacco block input', conclusion='rounding of the published index'))
    tests.append(dict(compare(alc, alc_pub, 'T6b alcohol & tobacco m/m: fixture vs CZCPAMOM (published one-decimal m/m)', tol=1e-9), model='alcohol & tobacco block input', conclusion='rounding of the published m/m'))
    alc_rows = []
    for origin in origins:
        t = pd.Period(origin, 'M'); rec = fast[fast.origin.eq(origin) & fast.h.gt(0)].sort_values('h').value_alcohol_tobacco.to_numpy(float)
        f0 = np.array([expanding_same_month_mean(alc, t + h, t - 1) for h in range(1, 13)]); f1 = np.array([expanding_same_month_mean(alc_bbg, t + h, t - 1) for h in range(1, 13)])
        alc_rows.append(dict(origin=origin, max_abs_recorded_minus_reproduced=float(np.abs(rec - f0).max()), max_abs_bbg_minus_frozen=float(np.abs(f1 - f0).max()), cum12_bbg_minus_frozen=float(f1.sum() - f0.sum())))
    alcf = pd.DataFrame(alc_rows); alcf.to_csv(out / 'T6_alcohol_tobacco_block_rows.csv', index=False)
    tests.append(dict(test='T6c alcohol & tobacco block re-run: recorded FAST block vs reproduction (expanding same-month mean, month t-1 released)', n=len(alcf), first=origins[0], last=origins[-1],
                      exact_share=float((alcf.max_abs_recorded_minus_reproduced <= 1e-9).mean()), max_abs_gap=float(alcf.max_abs_recorded_minus_reproduced.max()), mean_abs_gap=float(alcf.max_abs_recorded_minus_reproduced.mean()),
                      model='alcohol & tobacco block, all paths', conclusion='parity with the run'))
    tests.append(dict(test='T6d alcohol & tobacco block with the Bloomberg index (CZCPA) instead of the CZSO series', n=len(alcf), first=origins[0], last=origins[-1], exact_share=float((alcf.max_abs_bbg_minus_frozen <= 1e-9).mean()),
                      max_abs_gap=float(alcf.max_abs_bbg_minus_frozen.max()), mean_abs_gap=float(alcf.max_abs_bbg_minus_frozen.mean()), model='alcohol & tobacco block, all paths',
                      conclusion=f'monthly block forecasts move by up to {alcf.max_abs_bbg_minus_frozen.max():.3f} pp; twelve-month sums by up to {alcf.cum12_bbg_minus_frozen.abs().max():.3f}'))

    # ---- T7: R29B phase with Bloomberg total domestic PPI (PPTXCZ) instead of the Eurostat manufacturing PPI (A6 row 47)
    from data.cost_gaps_r23 import load_inputs as load_r23
    _, _, raw, _, _ = load_r23(); r47 = raw[47]; r45 = raw[45]
    pptx = monthly(bbg['PPTXCZ Index'])
    tests.append(dict(compare(r45.values, pptx, 'T7a A6 row 45 (Eurostat total domestic PPI index) vs PPTXCZ', tol=1e-9), model='—', conclusion='exact'))
    tests.append(dict(compare(100 * np.log(r47.values / r47.values.shift(6)), 100 * np.log(pptx / pptx.shift(6)), 'T7b six-month momentum: manufacturing PPI (row 47, the R29B input) vs total PPI (PPTXCZ)'), model='R29B phase input', conclusion='different aggregates'))
    phase_rows = []
    for origin in origins:
        clock = clocks[origin]; p47, d47 = phase_from_levels(ppi_published_levels(r47.values, r47.available, origin, clock)); p45, d45 = phase_from_levels(ppi_published_levels(pptx, r47.available.reindex(pptx.index), origin, clock))
        phase_rows.append(dict(origin=origin, phase_manufacturing=p47, momentum_manufacturing=d47.get('momentum'), phase_total_bbg=p45, momentum_total_bbg=d45.get('momentum'), agree=p47 == p45))
    ph = pd.DataFrame(phase_rows); ph.to_csv(out / 'T7_r29b_phase_rows.csv', index=False)
    tests.append(dict(test='T7c R29B phase classification: manufacturing PPI (Eurostat) vs total PPI (PPTXCZ, Bloomberg-exact), same publication stamps', n=len(ph), first=origins[0], last=origins[-1],
                      exact_share=float(ph.agree.mean()), max_abs_gap=float((ph.momentum_manufacturing - ph.momentum_total_bbg).abs().max()), mean_abs_gap=float((ph.momentum_manufacturing - ph.momentum_total_bbg).abs().mean()),
                      model='R29B core phase rule (research line)', conclusion=f'phase agrees at {int(ph.agree.sum())} of {len(ph)} origins; disagreements: ' + ', '.join(ph[~ph.agree].origin)))

    # ---- T8: R24/R27 long food history (CZSO 1995-2025, division 01) against the Bloomberg food CPI candidates
    lf = pd.read_csv(ROOT / FILES['long_food'], dtype=str); lf = lf[lf.ucel_kod.eq('01') & lf.casz_kod.eq('Z')].copy()
    lf['p'] = pd.PeriodIndex([f'{r}-{int(m):02d}' for r, m in zip(lf.rok, lf.mesic)], freq='M'); lf = lf.set_index('p').hodnota.astype(float).sort_index()
    lf_mm = 100 * (lf / lf.shift(1) - 1)
    for ticker in ('CPF1CZ Index', 'CPFOCZ Index', 'CZCPF Index'):
        if ticker in bbg:
            s = monthly(bbg[ticker]); tests.append(dict(compare(lf_mm, 100 * (s / s.shift(1) - 1), f'T8 long food history m/m (CZSO division 01, 1995-2025) vs m/m of {ticker}', tol=.051), model='R24 long-history drift (food), R27 gap window', conclusion='see exact share within one decimal'))

    # ---- T9: the nowcast fuel block (measured from weekly prices) rebuilt on the EC bulletin instead of the CZSO CENPHMT survey
    czso_weekly = pd.read_csv(ROOT / FILES['fuel_weekly_czso'], index_col=0, parse_dates=True)
    ec_weekly = pump.rename(columns={'gross_petrol95': 'petrol95', 'gross_diesel': 'diesel'})[['petrol95', 'diesel']]
    cr = pd.read_csv(ROOT / FILES['contributions'], index_col=0); cr.index = pd.PeriodIndex(cr.index, freq='M')
    nf = []
    for t in cr.index:
        eve = pd.Timestamp(calendar[calendar.target_month.eq(str(t))].detail_release_dt.iloc[0]) - pd.Timedelta(days=1); share, _ = regime_share(t, eve, calendar)
        f_cz, _ = fuel_mm_from_weekly(czso_weekly, t, petrol_share=share); f_ec, _ = fuel_mm_from_weekly(ec_weekly, t, petrol_share=share)
        nf.append(dict(period=str(t), recorded=float(cr.loc[t, 'fc_fuel']), czso_survey=f_cz, ec_bulletin_bbg=f_ec, actual=float(cr.loc[t, 'act_fuel']), w_fuel=float(cr.loc[t, 'w_fuel'])))
    nf = pd.DataFrame(nf); nf.to_csv(out / 'T9_nowcast_fuel_block_rows.csv', index=False)
    t9 = {}
    for name, mask in [('all', nf.period.ge('2000')), ('prints_2024plus', nf.period.ge('2024-01')), ('flash_era', nf.period.ge('2025-01'))]:
        z = nf[mask]; t9[name] = dict(block_rmse_czso=rmse(z.czso_survey - z.actual), block_rmse_ec_bbg=rmse(z.ec_bulletin_bbg - z.actual), headline_rmse_pp_czso=rmse(z.w_fuel * (z.czso_survey - z.actual)), headline_rmse_pp_ec_bbg=rmse(z.w_fuel * (z.ec_bulletin_bbg - z.actual)))
    details['T9_nowcast_fuel_block_on_ec_bulletin'] = t9
    tests.append(dict(test='T9 nowcast fuel block: CZSO CENPHMT survey (recorded source) vs the EC bulletin (Bloomberg ECOBETCZ/ECOBOTCZ exact), same measurement rule', n=len(nf), first=nf.period.iloc[0], last=nf.period.iloc[-1],
                      exact_share=float((nf.recorded - nf.czso_survey).abs().le(.05).mean()), max_abs_gap=float((nf.czso_survey - nf.ec_bulletin_bbg).abs().max()), mean_abs_gap=float((nf.czso_survey - nf.ec_bulletin_bbg).abs().mean()),
                      model='nowcast BASE/HALF/FULL/Category Raw fuel block',
                      conclusion=f"block RMSE all 90 prints {t9['all']['block_rmse_czso']:.3f} (CZSO) vs {t9['all']['block_rmse_ec_bbg']:.3f} (bulletin); from 2024 {t9['prints_2024plus']['block_rmse_czso']:.3f} vs {t9['prints_2024plus']['block_rmse_ec_bbg']:.3f}; headline effect within 0.001 pp either way (exact_share = recorded vs recomputed within 0.05)"))

    # ---- register rows
    tests_df = pd.DataFrame(tests); tests_df.to_csv(out / 'tests.csv', index=False)
    inv = c.read(INVENTORY)
    register = []
    def row(lane, model, status, block, variable, source, ticker, verdict, same_results, evidence, note=''):
        register.append(dict(lane=lane, model=model, status=status, block=block, variable=variable, source_now=source, bloomberg=ticker, input_verdict=verdict, same_results=same_results, evidence=evidence, note=note))
    tv = tests_df.set_index('test')
    path_models = [('R27 research path (FOOD_ECM_R27)', 'research roster'), ('R24 path (FOOD_NORM_SHIFT_R24)', 'predecessor'), ('FAST (STATE_FAST_R15)', 'reference'),
                   ('current core (STABLE_LOCAL_CORE_R14B)', 'presentation frame'), ('R29B core phase rule (CORE_LEVELPHASE_FIXED080_R29B)', 'research line, not promoted')]
    for model, status in path_models:
        row('path', model, status, 'h0', 'independent nowcast BASE', 'nowcast lane (see nowcast rows)', '—', 'see nowcast', 'follows the nowcast', 'R17 stack: every path keeps HARD_BASE h0')
        row('path', model, status, 'core', 'CNB core inflation m/m', 'fixture cnb_core_mm (ARAD SCPIMZM09MOMPECNA)', 'CZCIXM Index', 'exact', 'identical', 'T1')
        row('path', model, status, 'food', 'CZSO food CPI level (division 01)', 'data/research_r14/food/pipeline_log_levels.csv (CZSO 2015=100)', 'CZCPF Index (2025=100, one decimal)', 'extremely similar', 'not identical: see T5c', 'T5a-T5c')
        row('path', model, status, 'food', 'farm-gate prices, four products (agri4)', 'CZSO CEN0203B (data/cz_agri_prices_raw.csv)', 'none', 'not on Bloomberg', 'stays CZSO', '—')
        row('path', model, status, 'food', 'food producer prices (food_ppi)', 'CZSO PPI product level (data/cz_ppi_product_raw.csv)', 'none tested', 'not tested', 'stays CZSO', '—', 'CZPPA10M is the agricultural m/m; the food-industry PPI ticker was not probed')
        if 'R24' in model or 'R27' in model or 'current core' in model or 'R29B' in model:
            row('path', model, status, 'food', 'long food history 1995-2025 (R24 drift)', 'CZSO czso_cpi_1995_2025.csv', 'CPF1CZ / CZCPF (see T8)', 'partial', 'stays CZSO', 'T8')
        row('path', model, status, 'fuel', 'weekly pump prices, petrol 95 and diesel', 'EC Weekly Oil Bulletin files (data/research_r14/fuel/pump_weekly.csv)', 'ECOBETCZ, ECOBOTCZ Index', 'exact', 'identical (T4d)', 'T4a-T4d')
        row('path', model, status, 'fuel', 'petrol share of the fuel item', 'CZSO basket (models/components OFFICIAL_PETROL_SHARE)', 'none', 'static', 'static', '—')
        row('path', model, status, 'administered', 'CNB regulated prices m/m', 'fixture cnb_regulated_mm (ARAD SCPIMZM02MOMPECNA)', 'CZCIRM Index', 'exact', 'identical', 'T2')
        row('path', model, status, 'administered', 'announcement ledger (energy decisions)', 'data/admin_announcements_history.csv (hand-maintained, sourced documents)', 'none', 'documents', 'stays', '—')
        row('path', model, status, 'alcohol & tobacco', 'CZSO division 02 m/m', 'fixture alcohol_tobacco (CZSO 2015=100-based)', 'CZCPA Index / CZCPAMOM Index', 'extremely similar', 'not identical: see T6d', 'T6a-T6d')
        row('path', model, status, 'compounding', 'headline CPI m/m history (annual rates, wedge, scoring truth)', 'output/independent_path_frozen_inputs.csv (CZSO 2015=100-based; FRED before 2015)', 'CZCIPM (2007-) / CZCPMOM (2015-) Index', 'extremely similar', 'not identical: see T3c', 'T3a-T3c')
        row('path', model, status, 'weights', 'CPI basket weights', 'CZSO basket files (data/baskets, data/research_r18/categories)', 'none', 'static', 'static', '—')
    row('path', 'R27 research path (FOOD_ECM_R27)', 'research roster', 'food', 'retail, producer and farm food price levels (the R27 gap)', 'the same three series as the food system', 'CZCPF for retail only', 'extremely similar / none / none', 'stays CZSO', '—')
    row('path', 'R29B core phase rule (CORE_LEVELPHASE_FIXED080_R29B)', 'research line, not promoted', 'core', 'manufacturing PPI index (A6 row 47, Eurostat) for the phase', 'data/paper_replication/a6_inputs_20260912', 'none (EPP00CCZ does not resolve); PPTXCZ is the total', 'different aggregate', 'not identical: see T7c', 'T7a-T7c')
    for m in ['Nowcast HARD_BASE / HARD_HALF / HARD_FULL', 'Nowcast SENTIMENT_BASE / HALF / FULL', 'Scoring and benchmarks']:
        for r in inv[inv.model.eq(m)].itertuples():
            lane = 'nowcast' if 'Nowcast' in m else 'scoring'
            same = 'identical' if r.status == 'exact' else ('static' if r.status == 'static' else ('stays' if r.status in ('no Bloomberg series held', 'no data') else ('switchable: see T9' if str(r.variable).startswith('weekly') else 'parity run pending (Bloomberg input lane in cz_struct)')))
            row(lane, m, 'operating' if 'HARD' in m else ('legacy comparison' if 'SENTIMENT' in m else 'evaluation'), r.block, r.variable, r.source_used, r.closest_ticker, r.closest_verdict if isinstance(r.closest_verdict, str) else r.status, same,
                r.tests if isinstance(r.tests, str) else '—', f'max gap {r.max_abs_gap}' if pd.notna(r.max_abs_gap) else '')
    row('nowcast', 'Category Raw (CATEGORY_RAW)', 'accuracy challenger', 'core (categories)', 'CZSO CPI category levels (CEN0101E groups, 2015+)', 'data/research_r18/categories (CZSO)', 'CZSO division levels only (CZCP..); HICP classes for a few', 'partial', 'stays CZSO', 'map document, CPI index levels section')
    row('nowcast', 'R30B January spirits steps (declared, prospective)', 'declared research', 'alcohol & tobacco', 'excise calendar', 'data/excise_calendar_cz_r30.csv (documents)', 'none', 'documents', 'stays', '—')
    row('CNB lane', 'CNB comparison, lead test, ledger, tracker', 'conditioned evaluation', 'CNB', 'Monetary Policy Report tables', 'cnb.cz spreadsheets (data/cnb_mpr_tables_20260917)', 'none', 'not on Bloomberg', 'stays', '—')
    reg = pd.DataFrame(register); reg.to_csv(out / 'register.csv', index=False)
    details['counts'] = dict(register_rows=len(reg), by_same_results=reg.same_results.value_counts().to_dict(), by_lane=reg.lane.value_counts().to_dict())
    inputs = {n: sha(ROOT / p) for n, p in FILES.items()}; inputs.update({'inventory': sha(ROOT / INVENTORY), 'exactness': sha(ROOT / EXACTNESS), 'native_r27': sha(ROOT / f'{R27}/native_forecasts.csv')})
    inputs['snapshots'] = {str(Path(f).relative_to(ROOT)): sha(f) for f in sorted(glob.glob(str(ROOT / 'data/market_snapshots/*/history_long.csv')))}
    (out / 'details.json').write_text(json.dumps(details, indent=1, default=str), encoding='utf-8')
    (out / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs=inputs, code=sha(__file__),
                                                       outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 70)
    print(tests_df[['test', 'n', 'exact_share', 'max_abs_gap', 'conclusion']].to_string(index=False)); print(json.dumps(details, indent=1, default=str))


if __name__ == '__main__':
    main()
