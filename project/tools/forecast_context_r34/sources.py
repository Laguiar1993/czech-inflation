"""Verified local source adapters. Reads and validates; never calls model calculation."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from .analysis import clock, empirical_ranges, month_number, month_offset, number, quantile, seasonal_from_frames

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD = ROOT/'output/forecast_updates_r33/runs/20260922T175001527361Z_7c5389d7016a'
DEFAULT_BUNDLE = ROOT/'output/forecast_updates_r33/current_bundle_20260922_v2'
NOWCAST = ROOT/'output/bloomberg_lane_20260922_r31c/run_C123.csv'
TRUTH = NOWCAST.with_name('comparison.csv')
PATH_ROWS = ROOT/'output/bloomberg_lane_20260922_foodppi/path/path_rows.csv'
CALENDAR = ROOT/'data/release_calendar_cz_cpi.csv'
MODELS = ('HARD_BASE','HARD_HALF','HARD_FULL')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def input_key(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def csv_rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))


def verified_export(path, inputs):
    path = Path(path).resolve()
    manifest_path = path.with_name('manifest.json')
    manifest_raw = manifest_path.read_bytes()
    expected = json.loads(manifest_raw)['outputs'].get(path.name)
    raw = path.read_bytes()
    if not expected or digest(raw) != expected:
        raise ValueError('Frozen export hash mismatch: '+str(path))
    inputs[input_key(path)] = digest(raw)
    inputs[input_key(manifest_path)] = digest(manifest_raw)
    return csv_rows(raw)


def unique(rows, keys, label):
    result = {}
    for row in rows:
        key = tuple(row[k] for k in keys)
        if key in result:
            raise ValueError('Duplicate '+label+': '+str(key))
        result[key] = row
    return result


def numeric_or_nan(raw):
    return float(raw) if raw not in ('',None) else float('nan')


def normalize_history(nowcast_rows, truth_rows, path_rows):
    """No inner-join attrition: validate complete source support before selecting h1..12."""
    now = unique(nowcast_rows,('period',),'nowcast month')
    truth = unique(truth_rows,('period',),'truth month')
    unique(path_rows,('origin','h'),'path origin/h')
    if now.keys() != truth.keys():
        raise ValueError('Nowcast and truth support differ')
    errors = []
    for (origin,), row in sorted(now.items()):
        month_number(origin)
        if str(row['ready']).lower() not in ('true','false'):
            raise ValueError('Invalid archived readiness flag')
        point = numeric_or_nan(row['HARD_BASE'])
        reference = numeric_or_nan(truth[(origin,)]['HARD_BASE_C123'])
        if math.isfinite(point) != math.isfinite(reference) or (math.isfinite(point) and abs(point-reference)>1e-12):
            raise ValueError('Comparison forecast does not match run_C123')
        errors.append(dict(origin=origin,target=origin,h=0,forecast=point,
                           actual=numeric_or_nan(truth[(origin,)]['actual'])))
    keys = set()
    for row in path_rows:
        h = int(row['h']); origin = str(row['origin']); target = str(row['target'])
        month_number(origin); month_number(target)
        if not 0<=h<=12 or target != month_offset(origin,h):
            raise ValueError('Invalid path target/horizon')
        key = (origin,h)
        if key in keys: raise ValueError('Duplicate canonical path origin/horizon')
        keys.add(key)
        scored = str(row['scored']).lower()
        if scored not in ('true','false'): raise ValueError('Invalid scored flag')
        if h == 0 or scored != 'true': continue
        errors.append(dict(origin=origin,target=target,h=h,forecast=numeric_or_nan(row['yy_lane']),
                           actual=numeric_or_nan(row['actual_previous'])))
    return errors


def load_historical_errors():
    inputs = {}
    now = verified_export(NOWCAST,inputs)
    truth = verified_export(TRUTH,inputs)
    path = verified_export(PATH_ROWS,inputs)
    if len(now) != 90:
        raise ValueError('Expected the complete frozen 90-origin R31C roster')
    errors = normalize_history(now,truth,path)
    raw = CALENDAR.read_bytes()
    calendar_rows = csv_rows(raw)
    calendar = {}
    for row in calendar_rows:
        m = row['target_month']; month_number(m)
        if m in calendar: raise ValueError('Duplicate receipt calendar month')
        calendar[m] = row.get('detail_release_dt') or None
    inputs[input_key(CALENDAR)] = digest(raw)
    return dict(errors=errors,nowcast_rows=now,release_calendar=calendar,inputs=inputs,
                support_definition='All 90 R31C HARD_BASE origins; path h1..h12 only scored=True from the accepted R31B file',
                truth_definition='h0: comparison.csv actual, matched to run_C123 HARD_BASE; path: actual_previous minus yy_lane, never actual_bbg',
                ready_false_origins=[r['period'] for r in now if str(r['ready']).lower()=='false'])


def load_seasonal(bundle, record):
    """Public path API validates the successful run and its exact prepared bundle."""
    from tools.forecast_updates_r33.workflow import load_run
    from tools.live_bundle_r32.adapter import load_bundle
    bundle = Path(bundle).resolve(); record = Path(record).resolve()
    if record.name == 'result.json': record = record.parent
    result = load_run(record)
    expected = json.loads((record/'inputs.json').read_text(encoding='utf-8'))['bundle_manifest_sha256']
    manifest_raw = (bundle/'MANIFEST.json').read_bytes()
    if digest(manifest_raw) != expected:
        raise ValueError('Seasonal bundle does not match the recorded forecast')
    loaded = load_bundle(bundle)
    forecast = json.loads((record/'adapter.json').read_text(encoding='utf-8'))['forecast']
    if forecast['main_contributions_pp'] != result['forecast']['components'] or forecast['points_mm_pct']['HARD_BASE'] != result['forecast']['point']:
        raise ValueError('Adapter contribution/point mismatch')
    context = seasonal_from_frames(loaded.frames,forecast,target=result['target'],as_of=result['as_of'])
    context.update(recorded_at=result['recorded_at'],completed_at=result['completed_at'],
                   record_directory=input_key(record),model=result['model'],mode=result['mode'],
                   recorded_alternative_points_mm={k:number(forecast['points_mm_pct'][k]) for k in MODELS})
    inputs = {input_key(bundle/'MANIFEST.json'):digest(manifest_raw)}
    for rel, expected_hash in json.loads(manifest_raw)['files'].items():
        inputs[input_key(bundle/rel)] = expected_hash
    archive_raw = (record/'MANIFEST.json').read_bytes()
    inputs[input_key(record/'MANIFEST.json')] = digest(archive_raw)
    for rel, expected_hash in json.loads(archive_raw)['files'].items():
        inputs[input_key(record/rel)] = expected_hash
    context['inputs'] = inputs
    return context


def historical_disagreement(nowcast_rows, eligible_origins):
    """Use the same matured h0 origins, reporting missing alternatives explicitly."""
    unique(nowcast_rows,('period',),'model spread month')
    history, skipped = [], []
    for row in nowcast_rows:
        if row['period'] not in eligible_origins: continue
        try: points = {m:number(row[m]) for m in MODELS}
        except (KeyError,TypeError,ValueError):
            skipped.append(row['period']); continue
        lo, hi = min(points.values()),max(points.values())
        history.append(dict(origin=row['period'],points_mm=points,min_mm=lo,max_mm=hi,spread_pp=hi-lo,
                            half_minus_base_pp=points['HARD_HALF']-points['HARD_BASE'],
                            full_minus_base_pp=points['HARD_FULL']-points['HARD_BASE']))
    history.sort(key=lambda r:r['origin'])
    samples = {}
    for label in ('full','2024plus'):
        rows = [r for r in history if label=='full' or r['origin']>='2024-01']
        values = [r['spread_pp'] for r in rows]
        samples[label] = dict(n=len(rows),origin_start=rows[0]['origin'] if rows else None,
                             origin_end=rows[-1]['origin'] if rows else None,
                             mean_spread_pp=math.fsum(values)/len(values) if values else None,
                             median_spread_pp=quantile(values,.5) if values else None,
                             max_spread_pp=max(values) if values else None,rows=rows)
    return dict(definition='Historical HARD_BASE/HARD_HALF/HARD_FULL max-minus-min m/m spread, not an error range, confidence interval or model promotion',
                samples=samples,excluded_missing_alternatives=skipped,
                scope='Matured h0 origins also included in the empirical-error context; fresh core-path sensitivities are supplied separately by the parent')
