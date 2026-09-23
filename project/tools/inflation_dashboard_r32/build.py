"""Build the portable, offline R32 dashboard from frozen, dated research exports.

python -m tools.inflation_dashboard_r32.build --output output/inflation_dashboard_r32
New outputs only. Does not pull data, fit models, or alter any frozen research input.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUTS = {
    'monitor': 'output/inflation_monitor_20260922/monitor_data.json',
    'contributions': 'output/inflation_monitor_20260922/contributions.csv',
    'replay': 'output/cnb_rounds_v3/replay_data.json',
    'nowcast_scores': 'output/bloomberg_lane_20260922_r31c/scores.csv',
    'nowcast_runs': 'output/bloomberg_lane_20260922_r31c/run_C123.csv',
    'path_summary': 'output/bloomberg_lane_20260922_foodppi/path/summary.json',
    'path_rows': 'output/bloomberg_lane_20260922_foodppi/path/path_rows.csv',
    'monitor_manifest': 'output/inflation_monitor_20260922/manifest.json',
    'replay_manifest': 'output/cnb_rounds_v3/manifest.json',
    'nowcast_manifest': 'output/bloomberg_lane_20260922_r31c/manifest.json',
    'path_manifest': 'output/bloomberg_lane_20260922_foodppi/path/manifest.json',
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_export(path):
    manifest = json.loads((path.parent / 'manifest.json').read_text(encoding='utf-8'))
    expected = manifest.get('outputs', {}).get(path.name)
    if not expected or digest(path) != expected:
        raise ValueError('Frozen export missing from manifest or changed: ' + str(path))


def read_json(key):
    path = ROOT / INPUTS[key]
    verify_export(path)
    return json.loads(path.read_text(encoding='utf-8'))


def read_csv(key):
    path = ROOT / INPUTS[key]
    verify_export(path)
    with path.open(encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def contribution_rows(monitor, lag):
    h = monitor['history']
    if lag < 0 or lag >= len(h['months']):
        raise ValueError('Contribution comparison is outside the available history')
    rows = []
    for key, values in {**h['contributions'], 'residual': h['residual']}.items():
        label = 'Reconciliation residual' if key == 'residual' else monitor['blocks'][key]['label']
        value = values[-1] - (values[-1-lag] if lag else 0.)
        if not math.isfinite(value):
            raise ValueError('Non-finite contribution: ' + key)
        rows.append(dict(id=key, label=label, value=value))
    expected = h['headline'][-1] - (h['headline'][-1-lag] if lag else 0.)
    if abs(sum(r['value'] for r in rows) - expected) > 1e-8:
        raise ValueError('Contributions plus residual do not reconcile to headline')
    return sorted(rows, key=lambda r: r['value'], reverse=True)


def quarter_average(points, quarter):
    y, q = int(quarter[:4]), int(quarter[-1])
    if q not in range(1, 5):
        raise ValueError('Invalid quarter')
    p = dict(points)
    values = [p.get(f'{y}-{m:02d}') for m in range(3*q-2, 3*q+1)]
    if any(v is None or not math.isfinite(v) for v in values):
        return None
    return sum(values) / 3


def weighted_breadth(groups):
    if not groups or any(g['d3_yy'] is None or not math.isfinite(g['d3_yy']) for g in groups):
        raise ValueError('Breadth requires all group observations')
    total = sum(g['weight_permille'] for g in groups)
    if abs(total - 1000) > 1e-5:
        raise ValueError('Breadth weights must cover the full basket')
    return 100 * sum(g['weight_permille'] for g in groups if g['d3_yy'] > 0) / total


def month_offset(month, offset):
    y, m = map(int, month.split('-'))
    value = y*12 + m - 1 + offset
    return f'{value//12:04d}-{value%12+1:02d}'


def assemble():
    m, replay, path_summary = read_json('monitor'), read_json('replay'), read_json('path_summary')
    weights = {g: w for b in m['blocks'].values() for g, w in b['group_weights'].items()}
    for group in m['groups_latest']:
        group['weight_permille'] = weights[group['group']]
    score_rows = []
    for row in read_csv('nowcast_scores'):
        if row['source'] != 'C123':
            continue
        score_rows.append({k: (v if k in ('model', 'source', 'sample') else float(v)) for k, v in row.items()})
    for row in score_rows:
        row['n'] = int(row['n'])
    paths = read_csv('path_rows')
    origin = max(r['origin'] for r in paths)
    archive = sorted([[month_offset(origin, int(r['h'])), float(r['yy_lane'])]
                      for r in paths if r['origin'] == origin], key=lambda x: x[0])
    runs = read_csv('nowcast_runs')
    last_run = runs[-1]
    last_run = {k: (v if k in ('period', 'ready') else float(v)) for k, v in last_run.items()}
    momentum = read_csv('contributions')
    for row in momentum:
        for key in ('yy', 'mm', 'contribution', 'd3_yy', 'momentum_3m_ann'):
            row[key] = float(row[key]) if row[key] else None
    # M1's norm changes beyond the July-origin path are a scenario, never model output.
    ledger = [dict(r, forecast_kind='rebased' if r['model_source'] == 'roster path' else 'seasonal_scenario')
              for r in m['ledger']]
    result = dict(schema_version=1, snapshot_date=m['built'],
        vintages=dict(headline=m['headline_month'], groups=m['groups_month'],
                      model_origin=origin, replay_roster=replay['roster_date']),
        live=dict(status='unavailable', point=None, target=month_offset(m['headline_month'], 1),
                  reason='No current forecast is recorded. Refresh the input bundle and release calendar, then run the production adapter.'),
        monitor=m, drivers={str(lag): contribution_rows(m, lag) for lag in (0, 1, 3)},
        breadth=dict(percent=weighted_breadth(m['groups_latest']), month=m['groups_month'],
                     definition='Basket-weighted share of groups with higher y/y inflation than three months earlier.'),
        momentum=[r for r in momentum if r['month'] >= '2024-01'],
        archive_path=archive, updated_path=ledger, replay=replay, last_r31c_run=last_run,
        scores=dict(nowcast=score_rows, path=path_summary['scores'], cnb=path_summary['cnb_pairs_2024plus']),
        sources=[dict(name='Headline CPI', through=m['headline_month'], source='Bloomberg · CZCPYOY / CZCPMOM', status='Flash in this snapshot'),
                 dict(name='Core & regulated CPI', through=m['groups_month'], source='Bloomberg · CZCIXM / CZCIRM', status='Monthly history'),
                 dict(name='37 CPI groups & rents', through=m['groups_month'], source='CZSO · CEN0101E', status='Monthly supplementary pull'),
                 dict(name='Farm prices', through=m['pipeline']['readings']['farm_prices']['month'], source='CZSO · CEN0203B', status='Monthly supplementary pull'),
                 dict(name='Food PPI', through=m['pipeline']['readings']['food_ppi']['month'], source='Bloomberg · CZPPA10M', status='Cumulated published m/m'),
                 dict(name='Domestic manufacturing proxy', through=m['pipeline']['readings']['domestic_ppi']['month'], source='Bloomberg · EPP0BCCZ', status='Analysis; not the exact manufacturing series'),
                 dict(name='Independent path', through=origin, source='R31B bundle · R27 model', status='Archived origin; no new estimation'),
                 dict(name='Historical CNB replay', through=replay['roster_date'], source='Frozen R27 roster & CNB report tables', status='Reconstructed backtest; older input lane')])
    json.dumps(result, allow_nan=False)
    return result


def build(out):
    if out.exists():
        raise FileExistsError('Choose a new output directory; existing snapshots are immutable')
    data = assemble()
    out.mkdir(parents=True)
    (out / '.gitattributes').write_text('* -text\n', encoding='utf-8')
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
    # JSON embedded as script data must not terminate its own script element.
    safe_json = encoded.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    html = (HERE / 'template.html').read_text(encoding='utf-8')
    html = html.replace('/*__DATA__*/null', safe_json)
    html = html.replace('/*__APP__*/', (HERE / 'app.js').read_text(encoding='utf-8'))
    html = html.replace('/*__STYLE__*/', (HERE / 'style.css').read_text(encoding='utf-8'))
    (out / 'index.html').write_text(html, encoding='utf-8')
    (out / 'dashboard_data.json').write_text(encoded, encoding='utf-8')
    manifest = dict(built_at_utc=datetime.now(timezone.utc).isoformat(),
        snapshot_date=data['snapshot_date'], live_forecast=False,
        inputs={path: digest(ROOT / path) for path in INPUTS.values()},
        code={str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in HERE.iterdir() if p.is_file()},
        outputs={p.name: digest(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(dict(page=str(out / 'index.html'), live=False,
                         groups=data['vintages']['groups'], model_origin=data['vintages']['model_origin'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.output if args.output.is_absolute() else ROOT / args.output)
