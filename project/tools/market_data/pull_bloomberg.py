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
    'TTFGDAHD BCFV Index': 'gas_day_ahead_spot',
    'BCOMAGSP Index': 'agriculture_spot_index',
    'BCOMINSP Index': 'industrial_metals_spot_index',
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
    # Macro candidates supplied for the paper-comparison and path lanes.  The
    # pull stores them as raw candidates; definition checks happen before a
    # series is admitted to a scored model.
    'CZIPITS Index': 'industrial_production_level_sa',
    # Retain the NSA level as a separate challenger so replacing the
    # operating input does not destroy the raw/X-13 comparison lane.
    'CZIPITN Index': 'industrial_production_level_nsa_challenger',
    # Detailed EC business and consumer survey candidates.  These are pulled
    # together with the market candidates below so the next immutable capture
    # can be checked against the official ECFIN/Eurostat question codes.  A
    # Bloomberg mnemonic is never admitted to the paper panel on its own.
    'EUI6CZ Index': 'production_observed_past3m',
    'EUI1CZ Index': 'production_expected_next3m',
    'EUS1CZ Index': 'services_business_situation_past3m',
    'EUS2CZ Index': 'services_demand_past3m_candidate',
    'EUR1CZ Index': 'retail_present_business_situation_candidate',
    'EUB1CZ Index': 'building_activity_past3m_candidate',
    'EUB5F4CZ Index': 'building_constraint_labour',
    'EUB5F5CZ Index': 'building_constraint_material_equipment',
    'EUB5F6CZ Index': 'building_constraint_other_diagnostic',
    'EUB5F7CZ Index': 'building_constraint_financial',
    'EUCCCZ Index': 'consumer_confidence_broad_reference',
    'UMRTCZ Index': 'czech_unemployment',
    'CZRUSHIN Index': 'rushin_weekly',
    'CZGRIDX Index': 'building_permits_raw_candidate',
    'LCTQCZI Index': 'nominal_ulc_quarterly',
    'LCTOCZI Index': 'nominal_ulc_annual_benchmark',
    'EUS3CZ Index': 'services_demand_expectations_next3m',
    'EUS5CZ Index': 'services_employment_expectations_next3m',
    'EUB3CZ Index': 'construction_employment_expectations',
    'EUA2CZ Index': 'consumer_financial_situation_expected_candidate_a',
    'EUA4CZ Index': 'consumer_financial_situation_expected_candidate_b',
    'EUA8EMU Index': 'euro_area_consumer_price_trends_next12m',
    'EUA7EMU Index': 'euro_area_consumer_price_trends_last12m',
    'EUICCZ Index': 'czech_industrial_confidence',
    'EUSCCZ Index': 'czech_services_confidence',
    'EUICDE Index': 'germany_industrial_confidence',
    'EUSCDE Index': 'germany_services_confidence',
    'EURTDE Index': 'germany_retail_confidence',
    'EURTPL Index': 'poland_retail_confidence',
    # Retail/consumer/construction candidates supplied in the latest audit.
    # Bloomberg's established retail prefix is EUR; the confirmed retail-orders
    # mnemonic is kept below without the invalid extra-E diagnostic candidate.
    'EUR3CZ Index': 'czech_retail_orders_expectations_next3m',
    'EUR4CZ Index': 'czech_retail_activity_expectations_next3m',
    'EUR5CZ Index': 'czech_retail_employment_expectations_next3m',
    'EURTCZ Index': 'czech_retail_confidence',
    'EUA1CZ Index': 'czech_consumer_financial_situation_last12m',
    'EUA0CZ Index': 'czech_consumer_savings_next12m',
    'EUAUCZ Index': 'czech_consumer_unemployment_expectations_next12m',
    'EUA6CZ Index': 'czech_consumer_major_purchases_next12m',
    'EUCOCZ Index': 'czech_construction_confidence',
    'EUCODE Index': 'germany_construction_confidence',
    'EUB4CZ Index': 'czech_construction_price_expectations_next3m',
    'EUI5CZ Index': 'czech_industry_selling_price_expectations_next3m',
    'GRCPHCPI Index': 'germany_hicp_level_candidate',
    'UMRTDE Index': 'germany_unemployment_candidate',
    'CZEII Index': 'czech_import_price_level_candidate',
    'LONSCZNF Index': 'nfc_loans_bloomberg_candidate',
}
FIELDS = ['NAME', 'SECURITY_DES', 'CRNCY', 'QUOTE_UNITS', 'INDX_SOURCE',
          'DES_NOTES', 'PX_LAST', 'LAST_UPDATE_DT', 'LAST_UPDATE']
# These two fields are available for many economic securities and preserve the
# terminal's country and next scheduled release date when Bloomberg supplies
# them.  They are metadata only; the historical observation date remains the
# BDH date and is not silently treated as a publication timestamp.
# Keep the adjustment label in the immutable capture.  It is the field that
# distinguishes an official SA level from an NSA/WDA level; leaving it to a
# later ad-hoc probe makes it too easy to admit the wrong transformation.
REFERENCE_FIELDS = FIELDS + ['SEASONALITY_AND_TRANSFORMATION',
                             'ECO_RELEASE_DT', 'COUNTRY']
# Bloomberg leaves CRNCY blank for statistical balance/index series.  These
# are valid official statistics, so a missing currency is recorded as an
# optional absence.  Financial quotes and the loan stock still require CRNCY.
DIMENSIONLESS_TICKERS = {
    'CZIPITS Index', 'CZIPITN Index', 'CZGRIDX Index', 'LCTQCZI Index', 'LCTOCZI Index',
    'EUS3CZ Index', 'EUS5CZ Index', 'EUB3CZ Index', 'EUA2CZ Index', 'EUA4CZ Index',
    'EUA8EMU Index', 'EUA7EMU Index',
    'EUICCZ Index', 'EUSCCZ Index', 'EUICDE Index', 'EUSCDE Index',
    'EURTDE Index', 'EURTPL Index', 'EUR3CZ Index',
    'EUR4CZ Index', 'EUR5CZ Index', 'EURTCZ Index', 'EUA1CZ Index',
    'EUA0CZ Index', 'EUAUCZ Index', 'EUA6CZ Index', 'EUCOCZ Index',
    'EUCODE Index', 'EUB4CZ Index', 'EUI5CZ Index', 'GRCPHCPI Index',
    'UMRTDE Index', 'CZEII Index',
    'EUI6CZ Index', 'EUI1CZ Index', 'EUS1CZ Index', 'EUS2CZ Index',
    'EUR1CZ Index', 'EUB1CZ Index', 'EUB5F4CZ Index', 'EUB5F5CZ Index',
    'EUB5F6CZ Index', 'EUB5F7CZ Index', 'EUCCCZ Index', 'UMRTCZ Index',
    'CZRUSHIN Index',
}
ENERGY_UNITS = {
    'FSBTY1 Index': ('USD', 'USD/barrel'),
    'TTFGCY1 Index': ('EUR', 'EUR/MWh'),
    'TTFGDAHD BCFV Index': ('EUR', 'EUR/MWh'),
    'CO1 Comdty': ('USD', 'USD/bbl.'),
    'CO7 Comdty': ('USD', 'USD/bbl.'),
    'CO13 Comdty': ('USD', 'USD/bbl.'),
}


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


def validate_reference(raw, ticker):
    """Reject ambiguous BDP identity/units; return explicitly absent optional fields.

    xbbg can return empty or incomplete reference data without raising an API
    error. Currency is required for every security. Energy units must match the
    verified conversion contract; optional omissions such as FRA QUOTE_UNITS
    are recorded without claiming why Bloomberg omitted them.
    """
    if raw is None or raw.empty:
        raise ValueError(f'No reference data returned for {ticker}')
    if list(raw.index) != [ticker]:
        raise ValueError(f'Expected exactly one BDP row for {ticker}: {list(raw.index)}')
    row = raw.iloc[0]
    currency = row.get('crncy')
    required = set()
    if ticker not in DIMENSIONLESS_TICKERS:
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError(f'Missing required CRNCY for {ticker}')
        required.add('CRNCY')
    if ticker in ENERGY_UNITS:
        expected_currency, expected_units = ENERGY_UNITS[ticker]
        if currency != expected_currency:
            raise ValueError(f'Unexpected CRNCY for {ticker}: {currency!r}; expected {expected_currency!r}')
        units = row.get('quote_units')
        if not isinstance(units, str) or units != expected_units:
            raise ValueError(f'Unexpected QUOTE_UNITS for {ticker}: {units!r}; expected {expected_units!r}')
        required.add('QUOTE_UNITS')
    missing = []
    for field in FIELDS:
        if field in required:
            continue
        value = row.get(field.lower())
        if pd.isna(value) or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


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
        'reference_fields': REFERENCE_FIELDS,
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
            ref = blp.bdp(ticker, REFERENCE_FIELDS, timeout=30000)
            ref.to_csv(folder / 'raw' / f'{alias}_bdp.csv', index_label='ticker')
            missing_optional = validate_reference(ref, ticker)
            metadata[ticker] = {'retrieved_at': now(),
                                'fields': json.loads(ref.to_json(orient='index', date_format='iso')),
                                'missing_optional_fields': missing_optional}
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
