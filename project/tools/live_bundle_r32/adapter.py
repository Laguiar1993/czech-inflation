"""Hash-checked R31C inputs and fail-closed readiness; no model imports here."""
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
NAMES = {'headline': 'target_headline_cpi_mm.csv', 'components': 'component_food_fuel_mm.csv',
         'core': 'cnb_core_mm.csv', 'regulated': 'cnb_regulated_mm.csv', 'alcohol': 'alcohol_tobacco.csv',
         'features': 'core_features.csv', 'food_features': 'food_block_features.csv'}
HARD = ['eurczk_mm', 'import_l2', 'core_l1', 'core_l2', 'core_l12', 'state',
        'eurczk_mm_x_state', 'import_l2_x_state'] + [f'mon_{i}' for i in range(2, 13)]
FOOD = ['food_l1', 'food_l12', 'agri_l0', 'agri_l1', 'food_ppi_l1']
SCHEMA = {'headline': ['cpi_mm'], 'components': ['food', 'fuel'], 'core': ['core'],
          'regulated': ['regulated'], 'alcohol': ['alcohol_tobacco'], 'features': HARD, 'food_features': FOOD}
# Mirrors cz_struct's declared publication rules, not actual historical vintages.
CPI_LAG1 = {'core_l1', 'food_l1', 'state'}
DAYS = {'core_l2': 1, 'core_l12': 1, 'food_l12': 1, 'import_l2': 16,
        'agri_l0': 26, 'agri_l1': 1, 'food_ppi_l1': 16}
PPI_EXCEPTIONS = {1: 9, 3: 4, 4: 4, 6: 1, 12: 1}


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    rel = PurePosixPath(str(relative).replace('\\', '/'))
    if rel.is_absolute() or any(x in ('..', '') or ':' in x for x in rel.parts):
        raise ValueError(f'unsafe path: {relative}')
    path = (Path(root) / str(rel)).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError(f'unsafe path: {relative}')
    return path


def checked_files(root, hashes):
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('empty or invalid file hash manifest')
    result = {}
    for rel, digest in hashes.items():
        path = safe_path(root, rel)
        key = str(rel).replace('\\', '/')
        if key in result or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError(f'invalid hash entry: {rel}')
        if not path.is_file():
            raise ValueError(f'missing hash-listed file: {rel}')
        data = path.read_bytes()
        if sha_bytes(data) != digest:
            raise ValueError(f'hash mismatch: {rel}')
        result[key] = data  # parse the verified bytes; no second file read
    return result


def required(files, name):
    if name not in files:
        raise ValueError(f'required input not hash-listed: {name}')
    return files[name]


def csv_frame(data, label, monthly=True):
    d = pd.read_csv(io.BytesIO(data), index_col=0, float_precision='round_trip')
    d.index = pd.PeriodIndex(d.index, freq='M') if monthly else pd.DatetimeIndex(pd.to_datetime(d.index))
    if d.empty or d.index.hasnans or d.index.has_duplicates or not d.index.is_monotonic_increasing:
        raise ValueError(f'{label}: empty, invalid, duplicate or unordered index')
    if not monthly and (d.index.tz is not None or (d.index != d.index.normalize()).any()):
        raise ValueError(f'{label}: dates must be naive observation dates at midnight')
    d = d.apply(pd.to_numeric, errors='raise')
    if np.isinf(d.to_numpy(dtype=float)).any():
        raise ValueError(f'{label}: infinite values')
    return d


@dataclass
class Bundle:
    frames: dict
    market: dict
    provenance: dict


def load_bundle(bundle, repo_root=ROOT):
    bundle = Path(bundle)
    manifest_bytes = (bundle / 'MANIFEST.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    files = checked_files(bundle, manifest['files'])
    frames = {key: csv_frame(required(files, 'nowcast/' + name), key) for key, name in NAMES.items()}
    if list(frames['regulated'].columns) == ['reg']:
        frames['regulated'] = frames['regulated'].rename(columns={'reg': 'regulated'})
    for key, cols in SCHEMA.items():
        missing = set(cols) - set(frames[key].columns)
        if missing:
            raise ValueError(f'{key}: missing required columns {sorted(missing)}')
        if key not in ('features', 'food_features') and list(frames[key].columns) != cols:
            raise ValueError(f'{key}: unexpected column order/schema')
    x = frames['features']
    if any(c.startswith('services_l1_') for c in x):
        raise ValueError('R31C expects services_l1 as a plain column only')
    frames['features'] = x.drop(columns=['services_l1'], errors='ignore')
    allowed = set(HARD + ['exp12', 'exp36', 'exp12_x_state', 'household_exp', 'esi'])
    if set(frames['features']) - allowed or set(frames['food_features']) != set(FOOD):
        raise ValueError('unexpected feature schema: R31C inputs only')
    weekly = csv_frame(required(files, 'nowcast/fuel_weekly_variant_b.csv'), 'weekly_fuel', monthly=False)
    if not {'petrol95', 'diesel'} <= set(weekly) or (weekly.index.dayofweek != 0).any():
        raise ValueError('weekly_fuel requires Monday petrol95/diesel observations')

    # Portable bundles embed a long Bloomberg export. Frozen R31B bundles instead
    # pin external snapshots in their hash-listed provenance, never via a glob.
    if 'market/history_long.csv' in files:
        snapshots = {'market/history_long.csv': files['market/history_long.csv']}
    else:
        provenance = json.loads(required(files, 'provenance.json'))
        snapshots = checked_files(repo_root, provenance.get('snapshots'))
    parts = []
    wanted = {'CP7FCZ Index', 'EURCZK CNB Curncy', 'ECOBETCZ Index', 'ECOBOTCZ Index'}
    for name, data in sorted(snapshots.items()):
        d = pd.read_csv(io.BytesIO(data), usecols=['ticker', 'observation_date', 'value'])
        d = d[d.ticker.isin(wanted)].copy()
        d['date'] = pd.to_datetime(d.observation_date)
        if d.date.dt.tz is not None or (d.date != d.date.dt.normalize()).any():
            raise ValueError(f'{name}: expected naive midnight observation dates')
        if d.duplicated(['ticker', 'date']).any() or d.date.isna().any():
            raise ValueError(f'{name}: duplicate/invalid Bloomberg observations')
        d['value'] = pd.to_numeric(d.value, errors='raise')
        if not np.isfinite(d.value).all() or (d.value <= 0).any():
            raise ValueError(f'{name}: Bloomberg index/price must be finite and positive')
        if not d.empty:
            parts.append(d)
    if not parts:
        raise ValueError('missing Bloomberg source: CP7FCZ Index and EC pumps')
    d = pd.concat(parts).sort_values(['ticker', 'date'], kind='stable').drop_duplicates(['ticker', 'date'], keep='last')
    market = {ticker: g.set_index('date').value.sort_index() for ticker, g in d.groupby('ticker')}
    for ticker in ('CP7FCZ Index', 'ECOBETCZ Index', 'ECOBOTCZ Index'):
        if ticker not in market:
            raise ValueError(f'missing Bloomberg source: {ticker}')
    fuel = market['CP7FCZ Index'].copy()
    fuel.index = fuel.index.to_period('M')
    fuel = fuel[~fuel.index.duplicated(keep='last')]
    fuel = fuel.reindex(pd.period_range(fuel.index.min(), fuel.index.max(), freq='M'))
    mm = 100 * (fuel / fuel.shift(1) - 1)
    idx = frames['components'].fuel.dropna().index
    missing = idx[mm.reindex(idx).isna()]
    if len(missing):
        raise ValueError(f'CP7FCZ monthly coverage missing: {list(map(str, missing))}')
    frames['components'].loc[idx, 'fuel'] = mm.reindex(idx)
    # Confirm every used pump value is EC; no silent CZSO fallback from the old builder.
    for col, ticker in [('petrol95', 'ECOBETCZ Index'), ('diesel', 'ECOBOTCZ Index')]:
        series = market[ticker].copy()
        series.index -= pd.to_timedelta(series.index.dayofweek, unit='D')
        series = series[~series.index.duplicated(keep='last')] / 1000.
        aligned = series.reindex(weekly.index)
        if aligned[weekly[col].notna()].isna().any():
            raise ValueError(f'{ticker}: EC weekly coverage missing; no CZSO fallback permitted')
        if not np.allclose(weekly[col].dropna(), aligned[weekly[col].notna()], atol=1e-10, rtol=0):
            raise ValueError(f'{ticker}: variant B differs from hash-validated EC source')
    frames['weekly_fuel'] = weekly[['petrol95', 'diesel']].copy()
    return Bundle(frames, market, {'variant': 'R31C_C123', 'bundle_manifest_sha256': sha_bytes(manifest_bytes),
                                  'bundle_files': manifest['files'], 'snapshot_hashes': {p: sha_bytes(v) for p, v in snapshots.items()},
                                  'fuel_ticker': 'CP7FCZ Index', 'weekly_source': 'EC bulletin from Bloomberg, CZK/l',
                                  'dropped_feature': 'services_l1', 'vintage': 'latest-vintage with publication rules; not prospective evidence'})


def decision_clock(as_of):
    try:
        ts = pd.Timestamp(as_of)
        if pd.isna(ts) or ts.tzinfo is None:
            raise ValueError()
        return ts.tz_convert('Europe/Prague').tz_localize(None)
    except (ValueError, TypeError) as exc:
        raise ValueError('as_of must be a valid timestamp with an explicit timezone') from exc


def target_month(value):
    if not re.fullmatch(r'\d{4}-\d{2}', str(value)):
        raise ValueError('target must be YYYY-MM')
    return pd.Period(value, freq='M')


def load_calendar(frozen, live, clock):
    raw = Path(frozen).read_bytes()
    d = pd.read_csv(io.BytesIO(raw))
    d.index = pd.PeriodIndex(d.target_month, freq='M')
    if d.empty or d.index.has_duplicates or not d.index.is_monotonic_increasing:
        raise ValueError('invalid frozen calendar index')
    for col in ('first_release_dt', 'detail_release_dt'):
        d[col] = pd.to_datetime(d[col], errors='raise').dt.normalize() + pd.Timedelta(hours=9)
    info = {'frozen_sha256': sha_bytes(raw), 'frozen_last_target': str(d.index.max()), 'live_sha256': None, 'not_yet_available': []}
    frozen_end = d.index.max()
    if live:
        raw = Path(live).read_bytes(); info['live_sha256'] = sha_bytes(raw)
        extra = pd.read_csv(io.BytesIO(raw), dtype=str).fillna('')
        if not {'target_month', 'first_release_dt', 'detail_release_dt', 'available_from', 'source'} <= set(extra):
            raise ValueError('live calendar requires target_month, aware release clocks, available_from and source')
        seen = set()
        for row in extra.to_dict('records'):
            t = target_month(row['target_month'])
            if t in seen or t <= frozen_end:
                raise ValueError('live calendar may only append after the frozen calendar, without duplicates')
            seen.add(t)
            if not row['source'].strip():
                raise ValueError('live calendar requires source provenance')
            first, detail, available = (decision_clock(row[c]) for c in ('first_release_dt', 'detail_release_dt', 'available_from'))
            if detail < first or first <= t.end_time or available > first:
                raise ValueError('invalid live calendar release ordering')
            if available > clock:
                info['not_yet_available'].append(str(t)); continue
            d.loc[t, ['first_release_dt', 'detail_release_dt']] = [first, detail]
    if d[['first_release_dt', 'detail_release_dt']].isna().any().any() or (d.detail_release_dt < d.first_release_dt).any():
        raise ValueError('missing or inconsistent calendar release clocks')
    return d.sort_index(), info


def released(period, clock, calendar):
    if period in calendar.index:
        return clock >= calendar.loc[period, 'detail_release_dt']
    if period < calendar.index.min():
        return clock >= (period + 1).to_timestamp() + pd.Timedelta(days=19, hours=9)
    return False


def due(col, target, clock, calendar):
    if col.endswith('_x_state'):
        return due(col[:-8], target, clock, calendar) and due('state', target, clock, calendar)
    if col in CPI_LAG1:
        return released(target - 1, clock, calendar)
    if col == 'eurczk_mm':
        return clock >= (target + 1).to_timestamp()
    day = DAYS.get(col, 1)
    if col == 'food_ppi_l1':
        day += PPI_EXCEPTIONS.get((target - 1).month, 0)
    return clock >= target.to_timestamp() + pd.Timedelta(days=day - 1)


def prepare_frames(loaded, target, clock, calendar):
    frames = {k: v.copy(deep=True) for k, v in loaded.frames.items()}
    info = {'status': 'not_needed'}
    for name, cols in [('features', HARD), ('food_features', FOOD)]:
        if target in frames[name].index:
            for col in cols:
                if not due(col, target, clock, calendar):
                    frames[name].loc[target, col] = np.nan
    # Only fill the current month's incomplete mean. Never extend a feature frame.
    if clock.to_period('M') != target or target not in frames['features'].index:
        return frames, info
    daily = loaded.market.get('EURCZK CNB Curncy', pd.Series(dtype=float, index=pd.DatetimeIndex([])))
    cur = daily[(daily.index.to_period('M') == target) & (daily.index < clock.normalize())]
    prev = daily[daily.index.to_period('M') == target - 1]
    info = {'status': 'unavailable', 'ticker': 'EURCZK CNB Curncy', 'n_fixings': len(cur),
            'last_fixing': cur.index.max().strftime('%Y-%m-%d') if len(cur) else None,
            'rule': 'exclude Prague call day; prior monthly mean rounded to 3 dp'}
    if cur.empty or prev.empty:
        info['reason'] = 'missing current or previous month daily fixings'; return frames, info
    # Apply the same seven-day coverage guard to both monthly samples.
    # This is an explicit conservative guard, not a holiday calendar.
    if ((clock.normalize() - cur.index.max()).days > 7
            or (cur.index.min() - target.start_time).days > 7
            or cur.index.to_series().diff().dt.days.max() > 7
            or ((target - 1).end_time.normalize() - prev.index.max()).days > 7
            or (prev.index.min() - (target - 1).start_time).days > 7
            or prev.index.to_series().diff().dt.days.max() > 7):
        info['reason'] = 'daily FX coverage fails the seven-calendar-day freshness guard'; return frames, info
    value = 100 * (float(cur.mean()) / round(float(prev.mean()), 3) - 1)
    state = frames['features'].loc[target, 'state']
    frames['gated_mtd_fx'] = pd.DataFrame({'eurczk_mm': [value], 'eurczk_mm_x_state': [value * state]}, index=pd.PeriodIndex([target]))
    frames['features'].loc[target, ['eurczk_mm', 'eurczk_mm_x_state']] = [value, value * state]
    info.update(status='applied', value_mm_pct=value)
    return frames, info


def readiness(frames, target, clock, calendar, fx=None):
    reasons = []
    def reason(code, **details):
        reasons.append({'code': code, **details})
    if clock.to_period('M') == target and clock > target.start_time + pd.Timedelta(days=7):
        gated = frames.get('gated_mtd_fx')
        if gated is None or target not in gated.index or not np.isfinite(gated.loc[target, 'eurczk_mm']):
            reason('stale_mtd_fx', **(fx or {'status': 'unavailable', 'reason': 'no gated Bloomberg MTD FX row'}))
    if clock < target.start_time:
        reason('target_not_started', target=str(target))
    for p in (target - 1, target):
        if p not in calendar.index:
            reason('missing_release_calendar', target=str(p), required='sourced first/detail release timestamps')
    first = calendar.loc[target, 'first_release_dt'] if target in calendar.index else pd.NaT
    if pd.notna(first) and clock >= first:
        reason('first_release_already_reached', first_release=str(first))
    edges = {}
    series = {name: frames[name].iloc[:, 0] for name in ('headline', 'core', 'regulated', 'alcohol')}
    series.update(food=frames['components'].food, official_fuel=frames['components'].fuel)
    for name, values in series.items():
        eligible = [p for p in values.dropna().index if p < target and released(p, clock, calendar)]
        edge = max(eligible) if eligible else None
        gap = (target - 1 - edge).n if edge is not None else None
        edges[name] = {'latest_released_value': str(edge) if edge is not None else None, 'gap_months': gap}
        if gap != 0:
            reason('component_history_gap', component=name, required_through=str(target - 1), **edges[name])
        if len(eligible) < 48:
            reason('insufficient_history', component=name, n=len(eligible), minimum=48)
        feature_name = 'food_features' if name == 'food' else 'features' if name == 'core' else None
        if feature_name and any(p not in frames[feature_name].index for p in eligible):
            reason('training_feature_rows_missing', frame=feature_name)
    missing = []
    for name, cols in [('features', HARD), ('food_features', FOOD)]:
        if target not in frames[name].index:
            reason('missing_feature_row', frame=name, target=str(target)); continue
        for col in cols:
            if pd.isna(frames[name].loc[target, col]):
                status = 'STALE' if due(col, target, clock, calendar) else 'NOT_DUE'
                missing.append({'frame': name, 'column': col, 'status': status})
                if status == 'STALE':
                    reason('stale_feature', frame=name, column=col, target=str(target))
    last_due = min(clock - pd.Timedelta(days=7), target.end_time)
    expected = pd.date_range((target - 1).start_time, last_due, freq='W-MON')
    wk = frames['weekly_fuel'].loc[:last_due, ['petrol95', 'diesel']].dropna()
    absent = expected.difference(wk.index)
    if len(absent):
        reason('weekly_fuel_gap', missing_observation_dates=[p.strftime('%Y-%m-%d') for p in absent], rule='Monday observation + 7 days')
    if not (wk.index.to_period('M') == target - 1).any():
        reason('missing_prior_month_fuel', target=str(target - 1))
    return {'data_ready': not reasons, 'reasons': reasons, 'missing_inputs': missing,
            'component_history_edges': edges, 'before_first_release': bool(pd.notna(first) and clock < first),
            'first_release': first.isoformat() if pd.notna(first) else None,
            'weekly_fuel': {'last_due': expected[-1].isoformat() if len(expected) else None,
                            'last_available': wk.index.max().isoformat() if len(wk) else None}}
