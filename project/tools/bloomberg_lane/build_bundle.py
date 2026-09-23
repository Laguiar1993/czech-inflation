"""Build the frozen Bloomberg input bundle for the roster models (R31).

    python -m tools.bloomberg_lane.build_bundle --output data/bloomberg_inputs_20260922

Reads the Bloomberg snapshots under data/market_snapshots/ and writes the models' input frames in their own schemas,
with every column's provenance (ticker, transform, coverage, largest gap against the previous source) and a hash
manifest. Inputs that Bloomberg does not hold are copied from the previous source and marked as such.
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

FIX = ROOT / 'tests/fixtures/cleanup'
FOOD_DIR = ROOT / 'data/research_r14/food'
PATH_HEADLINE = ROOT / 'output/independent_path_frozen_inputs.csv'
PUMP = ROOT / 'data/research_r14/fuel/pump_weekly.csv'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_fixture(name):
    d = pd.read_csv(FIX / name, index_col=0, float_precision='round_trip'); d.index = pd.PeriodIndex(d.index, freq='M'); return d


def substitute(series, source, provenance, column, ticker, transform, tol=1e-9):
    """Replace `series` where `source` has a value; keep the previous value elsewhere; record what happened."""
    out = series.copy(); common = out.dropna().index.intersection(source.dropna().index)
    gap = (out.loc[common] - source.loc[common]).abs()
    kept = out.dropna().index.difference(common)
    provenance[column] = dict(ticker=ticker, transform=transform, months_from_bloomberg=int(len(common)), first=str(common.min()) if len(common) else None, last=str(common.max()) if len(common) else None,
                              months_kept_from_previous_source=int(len(kept)), kept_span=[str(kept.min()), str(kept.max())] if len(kept) else None,
                              exact_share=float((gap <= tol).mean()) if len(common) else None, max_abs_gap=float(gap.max()) if len(common) else None)
    out.loc[common] = source.loc[common]; return out


def to_monday(s):
    s = s.copy(); s.index = s.index - pd.to_timedelta(s.index.dayofweek, unit='D'); return s[~s.index.duplicated(keep='last')].sort_index()


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); args = ap.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    bbg = load_snapshots(); prov = {}
    czcpmom = monthly(bbg['CZCPMOM Index']); czcipm = monthly(bbg['CZCIPM Index']); head_bbg = pd.concat([czcipm[czcipm.index < czcpmom.index.min()], czcpmom]).sort_index()
    czcpfmom = monthly(bbg['CZCPFMOM Index']); czcpamom = monthly(bbg['CZCPAMOM Index']); czcixm = monthly(bbg['CZCIXM Index']); czcirm = monthly(bbg['CZCIRM Index'])
    czeii = monthly(bbg['CZEIIMOM Index']); czppa10 = monthly(bbg['CZPPA10M Index']); czcpf = monthly(bbg['CZCPF Index'])
    fx = bbg['EURCZK CNB Curncy']; fx_month = fx.groupby(fx.index.to_period('M')).mean().round(3); fx_mm = 100 * (fx_month / fx_month.shift(1) - 1)
    yy = pd.concat([monthly(bbg['CZCIPY Index']), monthly(bbg['CZCPYOY Index'])]); yy = yy[~yy.index.duplicated(keep='last')].sort_index()

    # ---- nowcast frames (the cleanup fixture schema)
    headline = read_fixture('target_headline_cpi_mm.csv'); headline['cpi_mm'] = substitute(headline.cpi_mm, czcpmom, prov, 'nowcast/headline.cpi_mm', 'CZCPMOM Index', 'published m/m')
    comp = read_fixture('component_food_fuel_mm.csv'); comp['food'] = substitute(comp.food, czcpfmom, prov, 'nowcast/components.food', 'CZCPFMOM Index', 'published m/m')
    prov['nowcast/components.fuel'] = dict(ticker=None, transform='kept: CZSO fuel item m/m (no exact or rounding-only Bloomberg series)', months_kept_from_previous_source=int(comp.fuel.notna().sum()))
    core = read_fixture('cnb_core_mm.csv'); core['core'] = substitute(core.core, czcixm, prov, 'nowcast/core.core', 'CZCIXM Index', 'published m/m')
    reg = read_fixture('cnb_regulated_mm.csv'); reg.iloc[:, 0] = substitute(reg.iloc[:, 0], czcirm, prov, 'nowcast/regulated', 'CZCIRM Index', 'published m/m')
    alc = read_fixture('alcohol_tobacco.csv'); alc['alcohol_tobacco'] = substitute(alc.alcohol_tobacco, czcpamom, prov, 'nowcast/alcohol.alcohol_tobacco', 'CZCPAMOM Index', 'published m/m')
    x = read_fixture('core_features.csv')
    x['eurczk_mm'] = substitute(x.eurczk_mm, fx_mm, prov, 'nowcast/features.eurczk_mm', 'EURCZK CNB Curncy', 'm/m of the monthly mean of the daily fixing, mean rounded to 3 dp')
    for col, lag in (('core_l1', 1), ('core_l2', 2), ('core_l12', 12)):
        x[col] = substitute(x[col], czcixm.shift(lag, freq='M'), prov, f'nowcast/features.{col}', 'CZCIXM Index', f'published m/m, lag {lag}')
    x['import_l2'] = substitute(x.import_l2, czeii.shift(2, freq='M'), prov, 'nowcast/features.import_l2', 'CZEIIMOM Index', 'published m/m, lag 2')
    state_src = (yy.shift(1, freq='M') > 4).astype(float).where(yy.shift(1, freq='M').notna())
    x['state'] = substitute(x.state, state_src.reindex(x.index), prov, 'nowcast/features.state', 'CZCIPY Index (to 2014), CZCPYOY Index (2015-)', 'published y/y at t-1 > 4')
    x['eurczk_mm_x_state'] = x.eurczk_mm * x.state; x['exp12_x_state'] = x.exp12 * x.state; x['import_l2_x_state'] = x.import_l2 * x.state
    for col in ('exp12', 'exp36', 'household_exp', 'esi', 'services_l1'):
        prov[f'nowcast/features.{col}'] = dict(ticker=None, transform='kept: ' + ('survey column dropped by the HARD policy' if col != 'services_l1' else 'CZSO services proxy (no Bloomberg series)'), months_kept_from_previous_source=int(x[col].notna().sum()))
    f = read_fixture('food_block_features.csv')
    f['food_l1'] = substitute(f.food_l1, czcpfmom.shift(1, freq='M'), prov, 'nowcast/food_features.food_l1', 'CZCPFMOM Index', 'published m/m, lag 1')
    f['food_l12'] = substitute(f.food_l12, czcpfmom.shift(12, freq='M'), prov, 'nowcast/food_features.food_l12', 'CZCPFMOM Index', 'published m/m, lag 12')
    f['food_ppi_l1'] = substitute(f.food_ppi_l1, czppa10.shift(1, freq='M'), prov, 'nowcast/food_features.food_ppi_l1', 'CZPPA10M Index', 'published m/m, lag 1')
    for col in ('agri_l0', 'agri_l1'):
        prov[f'nowcast/food_features.{col}'] = dict(ticker=None, transform='kept: CZSO farm-price basket (not on Bloomberg)', months_kept_from_previous_source=int(f[col].notna().sum()))
    weekly = pd.read_csv(FIX / 'fuel_weekly.csv', index_col=0, float_precision='round_trip'); weekly.index = pd.to_datetime(weekly.index)
    weekly_b = weekly.copy(); eb = to_monday(bbg['ECOBETCZ Index']) / 1000.; ob = to_monday(bbg['ECOBOTCZ Index']) / 1000.
    for col, src in (('petrol95', eb), ('diesel', ob)):
        aligned = src.reindex(weekly.index); common = weekly[col].dropna().index.intersection(aligned.dropna().index); gap = (weekly.loc[common, col] - aligned.loc[common]).abs()
        prov[f'nowcast/weekly_fuel_variant_b.{col}'] = dict(ticker={'petrol95': 'ECOBETCZ Index', 'diesel': 'ECOBOTCZ Index'}[col], transform='EC Weekly Oil Bulletin, CZK/l, Friday stamp mapped to the ISO-week Monday (different survey from CZSO CENPHMT)',
                                                            weeks_from_bloomberg=int(len(common)), exact_share=float((gap <= 1e-9).mean()), max_abs_gap=float(gap.max()))
        weekly_b.loc[common, col] = aligned.loc[common]
    prov['nowcast/weekly_fuel.petrol95'] = prov['nowcast/weekly_fuel.diesel'] = dict(ticker=None, transform='variant A keeps the CZSO CENPHMT Monday survey', weeks_kept_from_previous_source=int(len(weekly)))
    (out / 'nowcast').mkdir()
    for name, frame in [('target_headline_cpi_mm.csv', headline), ('component_food_fuel_mm.csv', comp), ('cnb_core_mm.csv', core), ('cnb_regulated_mm.csv', reg), ('alcohol_tobacco.csv', alc), ('core_features.csv', x), ('food_block_features.csv', f)]:
        frame.to_csv(out / 'nowcast' / name, index_label='period')
    weekly.to_csv(out / 'nowcast' / 'fuel_weekly.csv', index_label='date'); weekly_b.to_csv(out / 'nowcast' / 'fuel_weekly_variant_b.csv', index_label='date')

    # ---- path inputs
    (out / 'path').mkdir()
    ph = pd.read_csv(PATH_HEADLINE, index_col=0, float_precision='round_trip'); ph.index = pd.PeriodIndex(ph.index, freq='M')
    ph['headline_mm'] = substitute(ph.headline_mm, head_bbg, prov, 'path/headline_mm', 'CZCIPM Index (2007-2014), CZCPMOM Index (2015-)', 'published m/m; months before 2007 kept from the frozen file')
    ph.to_csv(out / 'path' / 'headline_history.csv', index_label='period')
    levels = pd.read_csv(FOOD_DIR / 'pipeline_log_levels.csv', index_col=0, float_precision='round_trip'); levels.index = pd.PeriodIndex(levels.index, freq='M')
    food_log = 100 * np.log(czcpf / czcpf[pd.Period('2015-01', 'M')])
    levels['food'] = substitute(levels.food, food_log.reindex(levels.index), prov, 'path/food_levels.food', 'CZCPF Index', '100*ln(level / level at 2015-01), one-decimal 2025=100 index')
    for col in ('agri4', 'food_ppi'):
        prov[f'path/food_levels.{col}'] = dict(ticker=None, transform='kept: CZSO ' + ('farm-price basket' if col == 'agri4' else 'food-products PPI level') + ' (not on Bloomberg)', months_kept_from_previous_source=int(levels[col].notna().sum()))
    if not np.isfinite(levels).all().all():
        raise ValueError('The Bloomberg food level does not cover the frozen food history')
    levels.to_csv(out / 'path' / 'food_log_levels.csv', index_label='period')
    available = pd.read_csv(FOOD_DIR / 'pipeline_available_from.csv', index_col=0); available.to_csv(out / 'path' / 'food_available_from.csv', index_label='period')
    prov['path/food_available_from'] = dict(ticker=None, transform='kept: publication stamps of the three series (release calendar; unchanged by the source)')
    alc_path = read_fixture('alcohol_tobacco.csv'); alc_path['alcohol_tobacco'] = substitute(alc_path.alcohol_tobacco, czcpamom, prov, 'path/alcohol_mm', 'CZCPAMOM Index', 'published m/m'); alc_path.to_csv(out / 'path' / 'alcohol_tobacco_mm.csv', index_label='period')
    pump = pd.read_csv(PUMP, index_col=0, parse_dates=True, float_precision='round_trip'); pump_b = pump.copy()
    for col, src in (('gross_petrol95', eb), ('gross_diesel', ob)):
        aligned = src.reindex(pump.index); common = pump[col].dropna().index.intersection(aligned.dropna().index); gap = (pump.loc[common, col] - aligned.loc[common]).abs()
        prov[f'path/pump_weekly.{col}'] = dict(ticker={'gross_petrol95': 'ECOBETCZ Index', 'gross_diesel': 'ECOBOTCZ Index'}[col], transform='EC Weekly Oil Bulletin, CZK/l, ÷1000, Friday stamp mapped to the ISO-week Monday',
                                                weeks_from_bloomberg=int(len(common)), weeks_kept_from_previous_source=int(pump[col].notna().sum() - len(common)), exact_share=float((gap <= 1e-9).mean()), max_abs_gap=float(gap.max()))
        pump_b.loc[common, col] = aligned.loc[common]
    pump_b.to_csv(out / 'path' / 'pump_weekly.csv', index_label='date')
    prov['path/pump_weekly.net_and_tax_columns'] = dict(ticker=None, transform='kept: net prices, VAT and excise columns of the frozen panel (the constant-pump control reads gross prices only)')
    snapshots = {str(p.relative_to(ROOT)): sha(p) for p in sorted((ROOT / 'data/market_snapshots').glob('*/history_long.csv'))}
    (out / 'provenance.json').write_text(json.dumps(dict(built_at_utc=datetime.now(timezone.utc).isoformat(), snapshots=snapshots, columns=prov), indent=1), encoding='utf-8')
    (out / 'MANIFEST.json').write_text(json.dumps(dict(previous_sources={'tests/fixtures/cleanup': json.loads((FIX / 'MANIFEST.json').read_text()), 'path_headline': sha(PATH_HEADLINE), 'food_levels': sha(FOOD_DIR / 'pipeline_log_levels.csv'), 'pump': sha(PUMP)},
                                                   files={str(p.relative_to(out)).replace('\\', '/'): sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json'}), indent=1), encoding='utf-8')
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ('ticker', 'months_from_bloomberg', 'weeks_from_bloomberg', 'months_kept_from_previous_source', 'exact_share', 'max_abs_gap')} for k, v in prov.items()}, indent=1))


if __name__ == '__main__':
    main()
