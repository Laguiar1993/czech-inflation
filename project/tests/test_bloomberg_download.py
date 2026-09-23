"""Offline checks that ambiguous Bloomberg metadata cannot pass a download."""
import json
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from tools.market_data import pull_bloomberg as downloader


ENERGY_UNITS = {
    'FSBTY1 Index': ('USD', 'USD/barrel'),
    'TTFGCY1 Index': ('EUR', 'EUR/MWh'),
    'CO1 Comdty': ('USD', 'USD/bbl.'),
    'CO7 Comdty': ('USD', 'USD/bbl.'),
    'CO13 Comdty': ('USD', 'USD/bbl.'),
    'TTFGDAHD BCFV Index': ('EUR', 'EUR/MWh'),
}


def test_requested_g6_commodity_securities_are_configured():
    assert downloader.TICKERS['BCOMAGSP Index'] == 'agriculture_spot_index'
    assert downloader.TICKERS['BCOMINSP Index'] == 'industrial_metals_spot_index'
    assert downloader.TICKERS['TTFGDAHD BCFV Index'] == 'gas_day_ahead_spot'


def test_requested_macro_candidates_are_configured_for_definition_checks():
    expected = {
        'CZIPITS Index': 'industrial_production_level_sa',
        'CZIPITN Index': 'industrial_production_level_nsa_challenger',
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
    for ticker, alias in expected.items():
        assert downloader.TICKERS[ticker] == alias


def test_invalid_retail_orders_typo_is_not_requested():
    """The confirmed retail-orders mnemonic is EUR3CZ, without the extra E."""
    assert 'EEUR3CZ Index' not in downloader.TICKERS


def test_adjustment_label_is_captured_with_reference_metadata():
    assert 'SEASONALITY_AND_TRANSFORMATION' in downloader.REFERENCE_FIELDS


def run_pull(tmp_path, monkeypatch, ticker, reference):
    """Replace only the external API and installed-package version lookup."""
    history = pd.DataFrame(
        [70., 71.], index=pd.to_datetime(['2026-09-07', '2026-09-08']),
        columns=pd.MultiIndex.from_tuples([(ticker, 'PX_LAST')]),
    )
    api = SimpleNamespace(bdh=lambda *a, **kw: history.copy(),
                          bdp=lambda *a, **kw: reference.copy())
    monkeypatch.setitem(sys.modules, 'xbbg', SimpleNamespace(blp=api))
    monkeypatch.setattr(downloader, 'TICKERS', {ticker: 'test_security'})
    monkeypatch.setattr(downloader.importlib.metadata, 'version', lambda name: 'offline-test')
    destination = tmp_path / 'capture'
    errors = downloader.pull(destination, '2026-09-08')
    request = json.loads((destination / 'request.json').read_text())
    metadata = json.loads((destination / 'metadata.json').read_text())
    return destination, errors, request, metadata


@pytest.mark.parametrize('ticker', ['CZIPITS Index', 'CZIPITN Index'])
def test_dimensionless_official_statistics_may_omit_currency(tmp_path, monkeypatch, ticker):
    ref = pd.DataFrame({'name': ['Czech Republic Industrial Prod']}, index=[ticker])
    _, errors, request, metadata = run_pull(tmp_path, monkeypatch, ticker, ref)
    assert errors == [] and request['status'] == 'complete'
    assert metadata[ticker]['missing_optional_fields'] == [
        name for name in downloader.FIELDS if name != 'NAME'
    ]


@pytest.mark.parametrize('reference', [
    pd.DataFrame(),
    pd.DataFrame({'crncy': ['CZK']}, index=['EURCZK Curncy']),
    pd.DataFrame({'crncy': ['CZK', 'CZK']},
                 index=['USDCZK Curncy', 'EURCZK Curncy']),
    pd.DataFrame({'crncy': ['CZK', 'CZK']},
                 index=['USDCZK Curncy', 'USDCZK Curncy']),
])
def test_empty_or_ambiguous_security_identity_marks_capture_partial(tmp_path, monkeypatch, reference):
    destination, errors, request, _ = run_pull(tmp_path, monkeypatch, 'USDCZK Curncy', reference)
    assert request['status'] == 'partial'
    assert len(errors) == 1 and errors[0]['stage'] == 'bdp'
    # The response remains available for diagnosis, even when invalid.
    assert (destination / 'raw/test_security_bdp.csv').exists()


@pytest.mark.parametrize('currency', [None, np.nan, '', '   '])
@pytest.mark.parametrize('ticker', ['USDCZK Curncy', 'PRIB03M Index', 'CKFR0CF Curncy'])
def test_missing_currency_rejects_fx_fixing_and_fra(tmp_path, monkeypatch, ticker, currency):
    ref = pd.DataFrame({'crncy': [currency]}, index=[ticker])
    _, errors, request, _ = run_pull(tmp_path, monkeypatch, ticker, ref)
    assert request['status'] == 'partial'
    assert len(errors) == 1 and 'CRNCY' in errors[0]['error']


def test_absent_currency_field_is_not_treated_as_an_optional_field(tmp_path, monkeypatch):
    ref = pd.DataFrame({'name': ['USD-CZK X-RATE']}, index=['USDCZK Curncy'])
    _, errors, request, _ = run_pull(tmp_path, monkeypatch, 'USDCZK Curncy', ref)
    assert request['status'] == 'partial'
    assert len(errors) == 1 and 'CRNCY' in errors[0]['error']


@pytest.mark.parametrize('ticker', list(ENERGY_UNITS))
@pytest.mark.parametrize('field,bad_value', [('crncy', 'GBP'),
                                           ('quote_units', 'GBP/therm'),
                                           ('quote_units', None)])
def test_wrong_energy_currency_or_units_cannot_be_silently_converted(
        tmp_path, monkeypatch, ticker, field, bad_value):
    currency, units = ENERGY_UNITS[ticker]
    ref = pd.DataFrame({'crncy': [currency], 'quote_units': [units]}, index=[ticker])
    ref.loc[ticker, field] = bad_value
    _, errors, request, _ = run_pull(tmp_path, monkeypatch, ticker, ref)
    assert request['status'] == 'partial'
    assert len(errors) == 1 and field.upper() in errors[0]['error']


@pytest.mark.parametrize('ticker', list(ENERGY_UNITS))
def test_verified_energy_units_succeed_and_optional_absences_are_explicit(tmp_path, monkeypatch, ticker):
    currency, units = ENERGY_UNITS[ticker]
    ref = pd.DataFrame({'crncy': [currency], 'quote_units': [units]}, index=[ticker])
    _, errors, request, metadata = run_pull(tmp_path, monkeypatch, ticker, ref)
    assert errors == [] and request['status'] == 'complete'
    assert metadata[ticker].get('missing_optional_fields') == [
        name for name in downloader.FIELDS if name not in ('CRNCY', 'QUOTE_UNITS')]
    assert metadata[ticker]['fields'][ticker]['quote_units'] == units


def test_inapplicable_fra_units_are_reported_without_failing_capture(tmp_path, monkeypatch):
    ticker = 'CKFR0CF Curncy'
    ref = pd.DataFrame({'crncy': ['CZK'], 'name': ['CZK FRA 3X6'],
                        'quote_units': [np.nan], 'indx_source': ['   ']}, index=[ticker])
    _, errors, request, metadata = run_pull(tmp_path, monkeypatch, ticker, ref)
    assert errors == [] and request['status'] == 'complete'
    assert metadata[ticker].get('missing_optional_fields') == [
        name for name in downloader.FIELDS if name not in ('CRNCY', 'NAME')]
