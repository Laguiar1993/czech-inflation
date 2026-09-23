"""Download a new, immutable Bloomberg market snapshot through xbbg BDH/BDP.

Run with a Bloomberg-enabled Python while the Terminal is logged in.
No shared cache or existing model input is changed. All files remain local.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TICKERS = {
    'FSBTY1 Index': 'brent_year1_user_selected',
    'TTFGCY1 Index': 'gas_year1_user_selected',
    'CO1 Comdty': 'brent_front_reference',
    'USDCZK Curncy': 'usdczk',
    'EURCZK Curncy': 'eurczk',
    'CO7 Comdty': 'legacy_brent_generic7',
    'CO13 Comdty': 'legacy_brent_generic13',
    'PRIB03M Index': 'pribor_3m',
    'CKFR0CF Curncy': 'fra_3x6',
    'CKFR0FI Curncy': 'fra_6x9',
    'CKFR0I1 Curncy': 'fra_9x12',
    'CKFR011C Curncy': 'fra_12x15',
    'CKFR1C1F Curncy': 'fra_15x18',
    'CKFR1F1I Curncy': 'fra_18x21',
    'CKFR1I2 Curncy': 'fra_21x24',
}
FIELDS = ['NAME', 'SECURITY_DES', 'CRNCY', 'QUOTE_UNITS', 'INDX_SOURCE',
          'DES_NOTES', 'PX_LAST', 'LAST_UPDATE_DT', 'LAST_UPDATE']


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str),
                    encoding='utf-8')


def validate_history(raw, ticker, start, end):
    if raw is None or raw.empty:
        raise ValueError(f'No historical data returned for {ticker}')
    if isinstance(raw.columns, pd.MultiIndex):
        expected = (ticker, 'PX_LAST')
        if expected not in raw.columns:
            raise ValueError(f'Missing expected column {expected}: {list(raw.columns)}')
        values = raw[expected].copy()
    else:
        raise ValueError(f'Unexpected BDH schema: {raw.columns}')
    values.index = pd.to_datetime(values.index)
    if values.index.has_duplicates or not values.index.is_monotonic_increasing:
        raise ValueError(f'Duplicate or unordered BDH dates for {ticker}')
    if (values.index < pd.Timestamp(start)).any() or (values.index > pd.Timestamp(end)).any():
        raise ValueError(f'BDH dates outside requested interval for {ticker}')
    values = pd.to_numeric(values, errors='raise')
    if values.notna().sum() == 0:
        raise ValueError(f'No finite observations for {ticker}')
    if values.dropna().isin([float('inf'), float('-inf')]).any():
        raise ValueError(f'Infinite observations for {ticker}')
    return values.rename(ticker)


def pull(folder, end):
    from xbbg import blp
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'raw').mkdir()
    request = {
        'retrieved_at': now(), 'end_date': end, 'field': 'PX_LAST',
        'tickers': TICKERS, 'historical_source': 'Bloomberg Desktop API / xbbg.blp.bdh',
        'history_options': {'periodicitySelection': 'DAILY',
                            'nonTradingDayFillOption': 'ACTIVE_DAYS_ONLY'},
        'history_start': '2000-01-01; FX 1998-01-01',
        'reference_fields': FIELDS,
        'vintage_status': 'Current-vintage historical download; not an original-vintage archive.',
        'availability_rule': 'Retrospective daily quotes assumed usable on next calendar day in Prague; no historical publication-time evidence.',
        'live_quote_policy': 'BDP PX_LAST may be intraday. Keep separate from BDH ending before pull day.',
        'python_executable': sys.executable,
        'versions': {p: importlib.metadata.version(p) for p in ['xbbg', 'blpapi', 'pandas']},
    }
    write_json(folder / 'request.json', request)
    series, coverage, metadata, errors = [], [], {}, []
    for ticker, alias in TICKERS.items():
        start = '1998-01-01' if ticker in ['USDCZK Curncy', 'EURCZK Curncy'] else '2000-01-01'
        item = {'ticker': ticker, 'alias': alias, 'requested_start': start,
                'requested_end': end, 'retrieved_at': now()}
        try:
            raw = blp.bdh(ticker, 'PX_LAST', start_date=start, end_date=end,
                          timeout=30000, **request['history_options'])
            raw.to_csv(folder / 'raw' / f'{alias}_bdh.csv', index_label='observation_date')
            values = validate_history(raw, ticker, start, end)
            series.append(values)
            valid = values.dropna()
            item.update(status='ok', observations=len(valid),
                        first_date=valid.index.min().date().isoformat(),
                        last_date=valid.index.max().date().isoformat(),
                        last_value=float(valid.iloc[-1]),
                        lag_calendar_days=(pd.Timestamp(end) - valid.index.max()).days,
                        maximum_quote_gap_days=int(valid.index.to_series().diff().dt.days.max()),
                        null_rows=int(values.isna().sum()))
            print(f'{ticker}: {len(valid)} daily observations, {item["first_date"]} to {item["last_date"]}', flush=True)
        except Exception as exc:
            item.update(status='error', error=f'{type(exc).__name__}: {exc}')
            errors.append({'ticker': ticker, 'stage': 'bdh', 'error': item['error']})
            print(f'{ticker}: ERROR {exc}', flush=True)
        coverage.append(item)
        try:
            ref = blp.bdp(ticker, FIELDS, timeout=30000)
            ref.to_csv(folder / 'raw' / f'{alias}_bdp.csv', index_label='ticker')
            metadata[ticker] = {'retrieved_at': now(),
                                'fields': json.loads(ref.to_json(orient='index', date_format='iso'))}
        except Exception as exc:
            errors.append({'ticker': ticker, 'stage': 'bdp',
                           'error': f'{type(exc).__name__}: {exc}'})
        # Checkpoint after every ticker so connection failures do not lose a pull.
        pd.DataFrame(coverage).to_csv(folder / 'coverage.csv', index=False)
        write_json(folder / 'metadata.json', metadata)
        write_json(folder / 'errors.json', errors)
    if series:
        pd.concat(series, axis=1).sort_index().to_csv(folder / 'daily.csv', index_label='observation_date')
    request['completed_at'] = now()
    request['status'] = 'complete' if not errors else 'partial'
    write_json(folder / 'request.json', request)
    hashes = {str(p.relative_to(folder)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(folder.rglob('*')) if p.is_file()}
    write_json(folder / 'MANIFEST.json', {'sha256': hashes,
               'pull_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--end-date')
    args = parser.parse_args()
    today = datetime.now(ZoneInfo('Europe/Prague')).date()
    end_date = args.end_date or (today - timedelta(days=1)).isoformat()
    if pd.Timestamp(end_date).date() >= today:
        parser.error('BDH end-date must precede the pull day; BDP captures live quotes separately.')
    output = args.output or ROOT / 'data' / 'market_snapshots' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    failures = pull(output, end_date)
    print(f'Saved {output}; errors={len(failures)}', flush=True)
    sys.exit(1 if failures else 0)
