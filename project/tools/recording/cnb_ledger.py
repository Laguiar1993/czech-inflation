"""Prospective ledger of disagreements with the CNB forecast, written before the next report.

`record` freezes, for one recorded forecast run, every comparison with the CNB forecast that
was current at the run's clock: the model's quarter-average annual rate, CNB's number, the gap,
whether it is a call at 0.30 and 0.50, which CNB price block drives it, and whether the target
is far enough ahead for the revision test. Abstentions are rows too. Rows are append-only and
the file is hash-chained, so a later edit is detectable. `resolve` never edits the ledger: it
writes a separate table with the next CNB forecast and realised inflation once they exist.

CNB forecasts are used here to evaluate and to name a disagreement. They never enter a model.

    python -m tools.recording.cnb_ledger record --run <recorded run> [--path <path table>] --tables data/cnb_mpr_tables_YYYYMMDD --ledger output/cnb_ledger
    python -m tools.recording.cnb_ledger resolve --ledger output/cnb_ledger --tables <newer tables> --headline <monthly csv with cpi_mm>
    python -m tools.recording.cnb_ledger verify --ledger output/cnb_ledger
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
from tools.cnb_tracker.component_gaps import component_gaps, dominant_block

THRESHOLDS = (.3, .5)
CONFIRM = .15
WEIGHT_KEY = {'core': 'core', 'food': 'food', 'alcohol_tobacco': 'alc', 'fuel': 'fuel', 'administered': 'administered'}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def monthly(path):
    frame = pd.read_csv(path, index_col=0, float_precision='round_trip'); frame.index = pd.PeriodIndex(frame.index, freq='M')
    return frame


def annual(headline_mm):
    return 100 * np.expm1(np.log1p(headline_mm / 100).rolling(12, min_periods=12).sum())


def quarter_value(quarter, origin, path_yy, known_yy):
    q = pd.Period(quarter, 'Q'); values = []
    for m in pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M'):
        values.append(known_yy.get(m, np.nan) if m < origin else path_yy.get(str(m), np.nan))
    return float(np.mean(values)) if np.isfinite(values).all() else np.nan


def current_report(cnb_long, as_of):
    """The latest CNB report published strictly before the run's clock day."""
    day = pd.Timestamp(as_of).tz_convert('Europe/Prague').normalize().tz_localize(None) if pd.Timestamp(as_of).tzinfo else pd.Timestamp(as_of).normalize()
    dates = sorted(d for d in cnb_long.report_date.unique() if pd.Timestamp(d) < day)
    if not dates:
        raise ValueError('No CNB report precedes the run clock')
    return dates[-1]


def ledger_rows(path, headline, blocks, h0_blocks, cnb_long, origin, as_of):
    """All comparisons of one recorded path table with the CNB forecast current at `as_of`."""
    t = pd.Period(origin, 'M'); report = current_report(cnb_long, as_of); report_quarter = pd.Period(report, 'Q')
    known = annual(headline.iloc[:, 0].loc[headline.index < t])
    cnb = cnb_long[cnb_long.report_date.eq(report) & cnb_long.indicator.eq('cpi') & cnb_long.frequency.eq('Q') & cnb_long.is_forecast.astype(bool)]
    projections = []
    for model, g in path.groupby('model', sort=False):
        path_yy = dict(zip(g.target.astype(str), g.yy_exante))
        for r in cnb.itertuples():
            value = quarter_value(r.period, t, path_yy, known)
            if np.isfinite(value):
                projections.append(dict(model=model, clock='ledger', report_date=report, quarter=r.period, forecast=value,
                                        quarters_ahead=pd.Period(r.period, 'Q').ordinal - report_quarter.ordinal + 1))
    projections = pd.DataFrame(projections)
    if projections.empty:
        raise ValueError('No comparable quarter between the path and the CNB forecast')
    clocks = pd.DataFrame([dict(clock='ledger', report_date=report, origin=str(t))])
    gaps = component_gaps(path, blocks, cnb_long, projections, clocks, list(path.model.unique()), h0_blocks=h0_blocks)
    drivers = dominant_block(gaps).set_index(['model', 'quarter']); rows = []
    cnb_value = cnb.set_index('period').value
    for p in projections.itertuples():
        gap = p.forecast - float(cnb_value[p.quarter]); d = drivers.loc[(p.model, p.quarter)] if (p.model, p.quarter) in drivers.index else None
        rows.append(dict(model=p.model, origin=str(t), as_of=str(as_of), cnb_report_date=report, quarter=p.quarter, quarters_ahead=p.quarters_ahead,
                         model_rate=p.forecast, cnb_rate=float(cnb_value[p.quarter]), gap=gap, direction='above' if gap > 0 else 'below' if gap < 0 else 'equal',
                         **{f'call_{int(100 * k):03d}': bool(abs(gap) >= k - 1e-12) for k in THRESHOLDS},
                         revision_test_eligible=bool(p.quarters_ahead >= 3),
                         dominant_block=None if d is None else d.dominant_block,
                         **{c_: (np.nan if d is None else float(d[c_])) for c_ in ['gap_core', 'gap_food_alc_tobacco', 'gap_fuel', 'gap_administered', 'gap_unexplained']}))
    return pd.DataFrame(rows), report


def read_run(run, path_file=None):
    run = Path(run); snapshot = json.loads((run / 'snapshot.json').read_text(encoding='utf-8')); point = json.loads((run / 'forecast.json').read_text(encoding='utf-8'))
    path = pd.read_csv(path_file or run / 'path.csv', float_precision='round_trip')
    blocks = pd.concat([monthly(run / 'core.csv').iloc[:, 0].rename('core'), monthly(run / 'components.csv')[['food', 'fuel']],
                        monthly(run / 'alcohol.csv').iloc[:, 0].rename('alcohol_tobacco'), monthly(run / 'regulated.csv').iloc[:, 0].rename('administered')], axis=1)
    h0 = {b: point['main_contributions_pp'][b] / point['weights'][w] for b, w in WEIGHT_KEY.items()}
    return snapshot, path, monthly(run / 'headline.csv'), blocks, h0


def chain_state(folder):
    chain = folder / 'ledger_chain.json'
    return json.loads(chain.read_text(encoding='utf-8')) if chain.exists() else []


def verify(folder):
    folder = Path(folder); chain = chain_state(folder); ledger = folder / 'ledger.csv'
    if not chain:
        return dict(entries=0, ok=not ledger.exists())
    ok = sha_bytes(ledger.read_bytes()) == chain[-1]['ledger_sha256_after'] and all(chain[i]['ledger_sha256_before'] == chain[i - 1]['ledger_sha256_after'] for i in range(1, len(chain)))
    return dict(entries=len(chain), rows=int(chain[-1]['rows_total']), ok=bool(ok))


def record(run, tables, folder, path_file=None):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    if not verify(folder)['ok']:
        raise ValueError('Ledger chain is broken; refusing to append')
    snapshot, path, headline, blocks, h0 = read_run(run, path_file); cnb_long = pd.read_csv(Path(tables) / 'cnb_mpr_indicators_long.csv')
    rows, report = ledger_rows(path, headline, blocks, h0, cnb_long, snapshot['target'], snapshot['as_of'])
    source = Path(path_file or Path(run) / 'path.csv'); entry_id = sha_bytes(source.read_bytes())[:16] + '_' + report
    chain = chain_state(folder)
    if any(e['entry_id'] == entry_id for e in chain):
        raise ValueError('This path table is already recorded against CNB report ' + report)
    mode = 'prospective' if snapshot.get('capture_kind') == 'live' else 'replay_not_prospective'
    rows.insert(0, 'entry_id', entry_id); rows.insert(1, 'mode', mode); rows.insert(2, 'recorded_at_utc', datetime.now(timezone.utc).isoformat())
    ledger = folder / 'ledger.csv'; before = sha_bytes(ledger.read_bytes()) if ledger.exists() else None
    existing = pd.read_csv(ledger) if ledger.exists() else pd.DataFrame(columns=rows.columns)
    if ledger.exists() and list(existing.columns) != list(rows.columns):
        raise ValueError('Ledger schema changed')
    rows.to_csv(ledger, mode='a', header=not ledger.exists(), index=False, lineterminator='\n')
    chain.append(dict(entry_id=entry_id, mode=mode, run=Path(run).as_posix(), path_table=source.as_posix(), path_sha256=sha_bytes(source.read_bytes()),
                      tables=Path(tables).as_posix(), cnb_report_date=report, origin=snapshot['target'], as_of=snapshot['as_of'], rows_added=len(rows),
                      rows_total=len(existing) + len(rows), ledger_sha256_before=before, ledger_sha256_after=sha_bytes(ledger.read_bytes())))
    (folder / 'ledger_chain.json').write_text(json.dumps(chain, indent=2), encoding='utf-8')
    return rows


def resolve(folder, tables, headline_file):
    """Derived outcomes for every ledger row: next CNB forecast, confirmation, realised rate, gains and losses."""
    folder = Path(folder); ledger = pd.read_csv(folder / 'ledger.csv'); cnb_long = pd.read_csv(Path(tables) / 'cnb_mpr_indicators_long.csv')
    cpi = cnb_long[cnb_long.indicator.eq('cpi') & cnb_long.frequency.eq('Q')]; dates = sorted(cpi.report_date.unique())
    forecast = cpi[cpi.is_forecast.astype(bool)].set_index(['report_date', 'period']).value
    realised_yy = annual(monthly(headline_file).iloc[:, 0]); out = []
    for r in ledger.itertuples():
        later = [d for d in dates if d > r.cnb_report_date]; nxt = later[0] if later else None
        new = float(forecast.get((nxt, r.quarter), np.nan)) if nxt else np.nan
        q = pd.Period(r.quarter, 'Q'); months = realised_yy.reindex(pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M'))
        realised = float(months.mean()) if months.notna().all() else np.nan
        still_future = bool(nxt is not None and q > pd.Period(nxt, 'Q')); revision = new - r.cnb_rate if np.isfinite(new) and still_future else np.nan
        closer = abs(r.cnb_rate - r.model_rate) - abs(new - r.model_rate) if np.isfinite(revision) else np.nan
        gain = abs(r.cnb_rate - realised) - abs(r.model_rate - realised) if np.isfinite(realised) else np.nan
        out.append(dict(entry_id=r.entry_id, model=r.model, quarter=r.quarter, next_report_date=nxt, cnb_next=new, target_still_future=still_future, revision=revision,
                        revision_direction_agrees=bool(np.isfinite(revision) and revision * r.gap > 0), revision_confirmed=bool(np.isfinite(closer) and revision * r.gap > 0 and closer >= CONFIRM - 1e-12),
                        realised=realised, abs_error_gain=gain, material_gain=bool(np.isfinite(gain) and gain >= CONFIRM - 1e-12), material_loss=bool(np.isfinite(gain) and gain <= -CONFIRM + 1e-12)))
    table = pd.DataFrame(out); table.to_csv(folder / 'resolutions.csv', index=False)
    return table


def main():
    ap = argparse.ArgumentParser(description=__doc__); sub = ap.add_subparsers(dest='command', required=True)
    a = sub.add_parser('record'); a.add_argument('--run', type=Path, required=True); a.add_argument('--path', type=Path); a.add_argument('--tables', type=Path, required=True); a.add_argument('--ledger', type=Path, required=True)
    b = sub.add_parser('resolve'); b.add_argument('--ledger', type=Path, required=True); b.add_argument('--tables', type=Path, required=True); b.add_argument('--headline', type=Path, required=True)
    v = sub.add_parser('verify'); v.add_argument('--ledger', type=Path, required=True); args = ap.parse_args()
    if args.command == 'record':
        rows = record(args.run, args.tables, args.ledger, args.path)
        print(rows[['model', 'quarter', 'model_rate', 'cnb_rate', 'gap', 'call_030', 'revision_test_eligible', 'dominant_block']].round(3).to_string(index=False))
    elif args.command == 'resolve':
        print(resolve(args.ledger, args.tables, args.headline).round(3).to_string(index=False))
    print(json.dumps(verify(args.ledger)))


if __name__ == '__main__':
    main()
