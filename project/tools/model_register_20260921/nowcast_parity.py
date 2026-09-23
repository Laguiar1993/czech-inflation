"""Nowcast parity on Bloomberg inputs: BASE, HALF and FULL re-run at the 90 recorded release-eve clocks from the frozen
fixture frames, then from the same frames with every input that Bloomberg holds replaced by the Bloomberg series.

    python -m tools.model_register_20260921.nowcast_parity --output output/model_register_20260921_nowcast

Replaced (model's own transform): headline m/m (CZCPMOM), food m/m and its lags (CZCPFMOM), CNB core and regulated m/m
(CZCIXM, CZCIRM), alcohol and tobacco m/m (CZCPAMOM), import prices lag 2 (CZEIIMOM), EUR/CZK m/m (monthly mean of the
CNB fixing, EURCZK CNB Curncy), the regime state (published y/y, CZCPYOY and CZCIPY), the food-products PPI lag 1
(CZPPA10M), the weekly pump prices (ECOBETCZ, ECOBOTCZ). Kept from CZSO: the fuel item m/m (weights and wedge), the
services proxy, farm prices; survey columns are dropped by the HARD policy anyway. The live loaders (DuckDB, requests)
are stubbed: this runtime holds no database, and the fixtures are the recorded inputs.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import types

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
for name in ('duckdb', 'requests'):      # the nowcast modules import the live loaders at module level; none is called here
    if name not in sys.modules:
        stub = types.ModuleType(name); stub.__getattr__ = lambda attr, _n=name: (_ for _ in ()).throw(RuntimeError(f'{_n} stub: live loaders are not available'))
        stub.DuckDBPyConnection = object; sys.modules[name] = stub
import forecast_independent as fi
from tools.model_register_20260921.build import load_snapshots, monthly, rmse

FORECASTS = 'output/independent_nowcast_forecasts.csv'
EVIDENCE = 'work/model_briefing_20260914/nowcast_release_evidence.csv'
MODELS = ['HARD_BASE', 'HARD_HALF', 'HARD_FULL']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(series, source, label, log, transform=None):
    """Replace the values of `series` (PeriodIndex) where the Bloomberg `source` has a value; report coverage and the gap."""
    s = series.copy(); src = source if transform is None else transform(source)
    common = s.dropna().index.intersection(src.dropna().index); gap = (s.loc[common] - src.loc[common]).abs()
    log.append(dict(input=label, fixture_n=int(s.notna().sum()), replaced_n=int(len(common)), not_replaced_n=int(s.notna().sum() - len(common)),
                    exact_share=float((gap <= 1e-9).mean()) if len(common) else np.nan, max_abs_gap=float(gap.max()) if len(common) else np.nan,
                    first=str(common.min()) if len(common) else None, last=str(common.max()) if len(common) else None))
    s.loc[common] = src.loc[common]; return s


def bloomberg_frames(frames, bbg, log):
    out = {k: v.copy() for k, v in frames.items()}
    czcpmom = monthly(bbg['CZCPMOM Index']); czcpfmom = monthly(bbg['CZCPFMOM Index']); czcpamom = monthly(bbg['CZCPAMOM Index'])
    czcixm = monthly(bbg['CZCIXM Index']); czcirm = monthly(bbg['CZCIRM Index']); czeii = monthly(bbg['CZEIIMOM Index']); czppa10 = monthly(bbg['CZPPA10M Index'])
    fx = bbg['EURCZK CNB Curncy']; fx_month = fx.groupby(fx.index.to_period('M')).mean().round(3); fx_mm = 100 * (fx_month / fx_month.shift(1) - 1)   # CNB publishes the monthly average to three decimals
    yy = pd.concat([monthly(bbg['CZCIPY Index']), monthly(bbg['CZCPYOY Index'])]); yy = yy[~yy.index.duplicated(keep='last')].sort_index()
    out['headline'].iloc[:, 0] = replace(out['headline'].iloc[:, 0], czcpmom, 'headline m/m -> CZCPMOM', log)
    out['components']['food'] = replace(out['components']['food'], czcpfmom, 'food m/m -> CZCPFMOM', log)
    log.append(dict(input='fuel item m/m (weights, wedge, support): kept CZSO (no exact or rounding-only Bloomberg series)', fixture_n=int(out['components'].fuel.notna().sum()), replaced_n=0))
    out['core'].iloc[:, 0] = replace(out['core'].iloc[:, 0], czcixm, 'CNB core m/m -> CZCIXM', log)
    out['regulated'].iloc[:, 0] = replace(out['regulated'].iloc[:, 0], czcirm, 'CNB regulated m/m -> CZCIRM', log)
    out['alcohol'].iloc[:, 0] = replace(out['alcohol'].iloc[:, 0], czcpamom, 'alcohol & tobacco m/m -> CZCPAMOM', log)
    x = out['features']
    x['eurczk_mm'] = replace(x['eurczk_mm'], fx_mm, 'eurczk_mm -> m/m of the monthly mean of EURCZK CNB', log)
    for col, lag in (('core_l1', 1), ('core_l2', 2), ('core_l12', 12)):
        x[col] = replace(x[col], czcixm.shift(lag, freq='M'), f'{col} -> CZCIXM lag {lag}', log)
    x['import_l2'] = replace(x['import_l2'], czeii.shift(2, freq='M'), 'import_l2 -> CZEIIMOM lag 2', log)
    state = (yy.shift(1, freq='M') > 4).astype(float); state = state.reindex(x.index)
    x['state'] = replace(x['state'], state.where(yy.shift(1, freq='M').reindex(x.index).notna()), 'state -> published y/y at t-1 > 4 (CZCIPY, CZCPYOY)', log)
    x['eurczk_mm_x_state'] = x['eurczk_mm'] * x['state']; x['exp12_x_state'] = x['exp12'] * x['state']; x['import_l2_x_state'] = x['import_l2'] * x['state']
    log.append(dict(input='services_l1: kept CZSO (no Bloomberg series)', fixture_n=int(x.services_l1.notna().sum()), replaced_n=0))
    f = out['food_features']
    f['food_l1'] = replace(f['food_l1'], czcpfmom.shift(1, freq='M'), 'food_l1 -> CZCPFMOM lag 1', log)
    f['food_l12'] = replace(f['food_l12'], czcpfmom.shift(12, freq='M'), 'food_l12 -> CZCPFMOM lag 12', log)
    f['food_ppi_l1'] = replace(f['food_ppi_l1'], czppa10.shift(1, freq='M'), 'food_ppi_l1 -> CZPPA10M lag 1', log)
    log.append(dict(input='agri_l0, agri_l1: kept CZSO (farm prices are not on Bloomberg)', fixture_n=int(f.agri_l0.notna().sum()), replaced_n=0))
    def to_monday(s):
        s = s.copy(); s.index = s.index - pd.to_timedelta(s.index.dayofweek, unit='D'); return s[~s.index.duplicated(keep='last')].sort_index()
    w = out['weekly_fuel']; eb = to_monday(bbg['ECOBETCZ Index']) / 1000.; ob = to_monday(bbg['ECOBOTCZ Index']) / 1000.
    for col, src in (('petrol95', eb), ('diesel', ob)):
        aligned = src.reindex(w.index); common = w[col].dropna().index.intersection(aligned.dropna().index); gap = (w.loc[common, col] - aligned.loc[common]).abs()
        log.append(dict(input=f'weekly {col} -> EC bulletin on Bloomberg (different survey)', fixture_n=int(w[col].notna().sum()), replaced_n=int(len(common)), not_replaced_n=int(w[col].notna().sum() - len(common)),
                        exact_share=float((gap <= 1e-9).mean()), max_abs_gap=float(gap.max()), first=str(common.min().date()), last=str(common.max().date())))
        w.loc[common, col] = aligned.loc[common]
    return out


def run(frames, targets, clocks, label):
    rows = []; started = time.perf_counter()
    for i, target in enumerate(targets):
        r = fi.calculate(frames, pd.Period(target, 'M'), clocks[target])
        rows.append(dict(period=target, **{m: r['points_mm_pct'][m] for m in MODELS}, **{'contrib_' + k: v for k, v in r['main_contributions_pp'].items()}, ready=r['ready_for_first_release']))
        if i % 15 == 0 or i == len(targets) - 1:
            print(f'{label} {i + 1}/{len(targets)} {target}: BASE {r["points_mm_pct"]["HARD_BASE"]:.4f}, {time.perf_counter() - started:.0f}s', flush=True)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--output', type=Path, required=True); ap.add_argument('--limit', type=int); args = ap.parse_args()
    out = args.output if args.output.is_absolute() else ROOT / args.output; out.mkdir(parents=True, exist_ok=False)
    recorded = pd.read_csv(ROOT / FORECASTS, index_col='period'); ev = pd.read_csv(ROOT / EVIDENCE)
    targets = [p for p in recorded.index if p >= '2019-02']; targets = targets[:args.limit] if args.limit else targets
    clocks = {p: pd.Timestamp(recorded.loc[p, 'as_of_eve']).tz_localize('Europe/Prague') for p in targets}
    frames = fi.fixture_frames(); bbg = load_snapshots(); log = []; frames_bbg = bloomberg_frames(frames, bbg, log)
    pd.DataFrame(log).to_csv(out / 'substitutions.csv', index=False)
    frozen = run(frames, targets, clocks, 'frozen'); bloomberg = run(frames_bbg, targets, clocks, 'bloomberg')
    frozen.to_csv(out / 'frozen_run.csv', index=False); bloomberg.to_csv(out / 'bloomberg_run.csv', index=False)
    actual = ev[ev.model.eq('HARD_BASE')].set_index('period').actual; consensus = ev[ev.model.eq('HARD_BASE')].set_index('period').consensus
    table = frozen.set_index('period')[MODELS].join(bloomberg.set_index('period')[MODELS], lsuffix='_frozen', rsuffix='_bbg')
    table['actual'] = actual.reindex(table.index); table['consensus'] = consensus.reindex(table.index)
    for m in MODELS:
        table[m + '_recorded'] = recorded[m].reindex(table.index)
    table.to_csv(out / 'comparison.csv')
    samples = {'all': table.index >= '2000', 'prints_2024plus': table.index >= '2024-01', 'flash_era_2025plus': table.index >= '2025-01'}
    scores = []
    for m in MODELS:
        for sample, mask in samples.items():
            z = table[mask]; big = (z.actual - z.consensus).abs() >= .4 - 1e-12
            for source in ('recorded', 'frozen', 'bbg'):
                e = z[f'{m}_{source}'] - z.actual; gain = (z.consensus - z.actual).abs() - e.abs(); dev = z[f'{m}_{source}'] - z.consensus; alert = dev.abs() >= .2 - 1e-12
                scores.append(dict(model=m, source=source, sample=sample, n=int(mask.sum()), rmse=rmse(e), mae=float(e.abs().mean()), consensus_rmse=rmse(z.consensus - z.actual),
                                   material_wins_big=int(((gain >= .15 - 1e-12) & big).sum()), material_losses_big=int(((gain <= -.15 + 1e-12) & big).sum()),
                                   alerts=int(alert.sum()), alerts_direction_right=int((alert & (np.sign(dev) == np.sign(z.actual - z.consensus))).sum()),
                                   alert_material_wins=int((alert & (gain >= .15 - 1e-12)).sum()), alert_material_losses=int((alert & (gain <= -.15 + 1e-12)).sum())))
    scores = pd.DataFrame(scores); scores.to_csv(out / 'scores.csv', index=False)
    summary = {}
    for m in MODELS:
        d_rep = (table[f'{m}_frozen'] - table[f'{m}_recorded']).abs(); d_bbg = (table[f'{m}_bbg'] - table[f'{m}_frozen']).abs()
        summary[m] = dict(reproduction_max_abs_gap=float(d_rep.max()), reproduction_mean_abs_gap=float(d_rep.mean()), bloomberg_max_abs_change=float(d_bbg.max()), bloomberg_mean_abs_change=float(d_bbg.mean()),
                          bloomberg_change_over_0p05=int((d_bbg > .05).sum()), bloomberg_change_over_0p10=int((d_bbg > .10).sum()),
                          rmse={s: dict(frozen=float(scores[(scores.model == m) & (scores.source == 'frozen') & (scores['sample'] == s)].rmse.iloc[0]),
                                        bbg=float(scores[(scores.model == m) & (scores.source == 'bbg') & (scores['sample'] == s)].rmse.iloc[0])) for s in samples})
    blocks = {}
    for k in [c for c in frozen.columns if c.startswith('contrib_')]:
        d = (bloomberg.set_index('period')[k] - frozen.set_index('period')[k]).abs(); blocks[k] = dict(max_abs_change_pp=float(d.max()), mean_abs_change_pp=float(d.mean()))
    summary['block_contributions_pp'] = blocks
    (out / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')
    inputs = {'forecasts': sha(ROOT / FORECASTS), 'evidence': sha(ROOT / EVIDENCE), 'fixtures': json.loads((ROOT / 'tests/fixtures/cleanup/MANIFEST.json').read_text()), 'runtime': fi.runtime_identity()}
    (out / 'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.now(timezone.utc).isoformat(), inputs=inputs, code=sha(__file__),
                                                       outputs={p.name: sha(p) for p in sorted(out.iterdir()) if p.name != 'manifest.json'}), indent=1), encoding='utf-8')
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
