import io

import numpy as np
import openpyxl
from openpyxl.styles import Font
import pandas as pd
import pytest

import r17_common as c
from tools.cnb_tracker.fetch_tables import parse, indicator_key
from tools.cnb_tracker.component_gaps import cnb_weight, model_block_rates, annual_rates, component_gaps, dominant_block

TABLES = c.ROOT / 'data/cnb_mpr_tables_20260917/cnb_mpr_indicators_long.csv'


def workbook(quarter_labels):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'English version'
    ws.append([None, 'KEY MACROECONOMIC INDICATORS'])
    ws.append([None, None, None, None, None, None, None, 2025, None, None, None, 2026])
    ws.append([None, None, 2021, 2022, 2023, 2024, 2025, *quarter_labels, *quarter_labels])
    ws.append([None, 'PRICES'])
    ws.append([None, 'Consumer Price Index  (%, y-o-y, average)', 3.8, 15.1, 10.7, 2.4, 2.5, 2.7, 2.4, 2.5, 2.2, 1.6, 2.0, 1.9, 2.4])
    ws.append([None, 'Core inflation (%, y-o-y, average, 56.03%*)', 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13])
    for column in (14, 15):
        ws.cell(row=5, column=column).font = Font(bold=True)
    buffer = io.BytesIO(); wb.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize('labels', [['Q1', 'Q2', 'Q3', 'Q4'], ['QI', 'QII', 'QIII', 'QIV']])
def test_parser_reads_years_quarters_and_the_bold_forecast_flag(labels):
    table = parse(workbook(labels))
    cpi = table[table.indicator.eq('cpi') & table.frequency.eq('Q')].set_index('period')
    assert list(cpi.index) == ['2025Q1', '2025Q2', '2025Q3', '2025Q4', '2026Q1', '2026Q2', '2026Q3', '2026Q4']
    assert cpi.value.loc['2026Q2'] == 2.0 and cpi.is_forecast.to_dict() == {**{q: False for q in cpi.index[:6]}, '2026Q3': True, '2026Q4': True}
    assert set(table[table.frequency.eq('A')].period) == {'2021', '2022', '2023', '2024', '2025'}
    assert table[table.indicator.eq('core')].section.iloc[0] == 'PRICES'


def test_indicator_keys_and_weights_from_both_label_generations():
    assert indicator_key('Administered prices (14.58%)* (%, y-o-y, average)') == 'administered'
    assert indicator_key('Food prices (incl. alcoholic beverages and tobacco, %, y-o-y, average, 25.15%*)') == 'food_alc_tobacco'
    assert indicator_key('Average monthly wage in non-market sectors  (%, y-o-y, nominal terms)') is None
    assert indicator_key('Average monthly wage in market sectors  (%, y-o-y, nominal terms)') == 'wage_market'
    assert indicator_key('GDP  (%, q-o-q, real terms, seas. adjusted)') is None and indicator_key('GDP  (%, y-o-y, real terms, seas. adjusted)') == 'gdp_yy'
    assert cnb_weight('Administered prices (14.58%)* (%, y-o-y, average)') == pytest.approx(.1458)
    assert cnb_weight('Core inflation (%, y-o-y, average, 56.03%*)') == pytest.approx(.5603)
    assert np.isnan(cnb_weight('Consumer Price Index  (%, y-o-y, average)'))


def test_archived_tables_match_the_frozen_headline_and_carry_every_block():
    long = pd.read_csv(TABLES); frozen = pd.read_csv(c.ROOT / 'data/cnb_mpr_cpi_quarterly.csv')
    mine = long[long.indicator.eq('cpi') & long.frequency.eq('Q')].set_index(['report_date', 'period'])
    theirs = frozen.set_index(['report_date', 'quarter'])
    np.testing.assert_allclose(mine.value.reindex(theirs.index), theirs.value, atol=1e-12, rtol=0)
    assert (mine.is_forecast.reindex(theirs.index) == theirs.is_forecast.astype(bool)).all()      # bold cells agree with the old date rule
    blocks = long[long.indicator.isin(['core', 'food_alc_tobacco', 'fuel', 'administered'])].drop_duplicates(['report_date', 'indicator'])
    weights = blocks.assign(w=blocks.row_label.map(cnb_weight)).groupby('report_date').w.agg(['size', 'sum'])
    assert len(weights) == 19 and (weights['size'] == 4).all() and weights['sum'].between(.99, 1.01).all()


def gap_fixture(food_forecast):
    months = pd.period_range('2022-01', '2026-12', freq='M')
    actual = pd.DataFrame({b: .2 for b in ['core', 'food', 'alcohol_tobacco', 'fuel', 'administered']}, index=months)
    weights = dict(weight_core=.55, weight_food=.18, weight_alc=.08, weight_fuel=.04, weight_administered=.15)
    rows = [dict(origin='2025-03', model='M', h=h, target=str(pd.Period('2025-03', 'M') + h), value_core=.2, value_food=food_forecast,
                 value_alcohol_tobacco=.2, value_fuel=.2, value_administered=.2, **weights) for h in range(1, 13)]
    rows.append(dict(origin='2025-03', model='M', h=0, target='2025-03'))
    return pd.DataFrame(rows), actual


def test_a_gap_created_in_food_is_attributed_to_food_and_nothing_is_left_over():
    native, actual = gap_fixture(food_forecast=.6); steady = 100 * (1.002 ** 12 - 1)
    monthly, weights = model_block_rates(native, actual, '2025-03')
    assert weights == pytest.approx({'core': .55, 'food_alc_tobacco': .26, 'fuel': .04, 'administered': .15})
    yearly = annual_rates(monthly); assert yearly.core.loc['2026-01'] == pytest.approx(steady)
    combined = (.18 * .6 + .08 * .2) / .26                                          # food and alcohol, weighted, for the ten forecast months
    expected_food = 100 * ((1.002 ** 2) * (1 + combined / 100) ** 10 - 1)            # window 2025-02..2026-01: two realised months, ten forecast
    assert yearly.food_alc_tobacco.loc['2026-01'] == pytest.approx(expected_food)
    labels = {'core': 'Core inflation (%, y-o-y, average, 55.00%*)', 'food_alc_tobacco': 'Food prices (incl. alcoholic beverages and tobacco, %, y-o-y, average, 26.00%*)',
              'fuel': 'Fuel prices (%, y-o-y, average, 4.00%*)', 'administered': 'Administered prices (%, y-o-y, average, 15.00%*)'}
    cnb = pd.DataFrame([dict(report_date='2025-05-15', indicator=k, row_label=v, frequency='Q', period='2026Q1', value=steady) for k, v in labels.items()]
                       + [dict(report_date='2025-05-15', indicator='cpi', row_label='CPI', frequency='Q', period='2026Q1', value=steady)])
    ours = float(sum(w * annual_rates(monthly)[b].loc['2026-01':'2026-03'].mean() for b, w in weights.items()))
    projections = pd.DataFrame([dict(model='M', clock='report', report_date='2025-05-15', quarter='2026Q1', quarters_ahead=4, forecast=ours)])
    clocks = pd.DataFrame([dict(clock='report', report_date='2025-05-15', origin='2025-03')])
    gaps = component_gaps(native, actual, cnb, projections, clocks, ['M']).set_index('block')
    assert gaps.loc['core', 'contribution_gap'] == pytest.approx(0., abs=1e-12) and gaps.loc['fuel', 'contribution_gap'] == pytest.approx(0., abs=1e-12)
    assert gaps.loc['food_alc_tobacco', 'contribution_gap'] == pytest.approx(gaps.headline_gap.iloc[0]) and gaps.loc['food_alc_tobacco', 'contribution_gap'] > .2
    assert gaps.loc['unexplained', 'contribution_gap'] == pytest.approx(0., abs=1e-12)
    top = dominant_block(gaps.reset_index()); assert top.dominant_block.iloc[0] == 'food_alc_tobacco'


def test_tracker_news_uses_only_what_was_released_by_the_next_cutoff():
    from tools.cnb_tracker.revisions import news_at
    months = pd.period_range('2023-01', '2024-12', freq='M')
    public = dict(cpi=pd.Series(3., index=months), core=pd.Series(2.5, index=months),
                  released=pd.Series((months + 1).to_timestamp() + pd.Timedelta(days=9, hours=9), index=months),
                  fx=pd.Series(25., index=pd.bdate_range('2024-01-01', '2024-12-31')), brent=pd.Series(80., index=months))
    index = pd.MultiIndex.from_tuples([('2024-02-15', 'cpi', '2024Q1'), ('2024-02-15', 'core', '2024Q1'), ('2024-02-15', 'czk_eur', '2024Q2'), ('2024-02-15', 'brent', '2024Q2')])
    values = pd.Series([2.6, 2.0, 24.5, 70.], index=index); weights = pd.Series({'2024-02-15': .56})
    news = news_at(values, weights, public, '2024-02-15', '2024-04-26')
    assert news['months_of_quarter_released'] == 3 and news['cpi_news'] == pytest.approx(.4)
    assert news['core_news'] == pytest.approx(.56 * .5) and news['noncore_news'] == pytest.approx(.4 - .28)
    assert news['fx_news'] == pytest.approx(100 * np.log(25 / 24.5)) and news['brent_news'] == pytest.approx(100 * np.log(80 / 70)) and news['brent_month'] == '2024-03'
    early = news_at(values, weights, public, '2024-02-15', '2024-04-05')            # March is released on 10 April: not yet known
    assert early['months_of_quarter_released'] == 2 and np.isnan(early['cpi_news'])
    assert news_at(values, weights, public, '2024-02-15', '2024-04-05', partial=True)['cpi_news'] == pytest.approx(.4)
    public['cpi'].loc['2024-04':] = 1e9                                              # nothing after the quarter can enter
    assert news_at(values, weights, public, '2024-02-15', '2024-04-26')['cpi_news'] == pytest.approx(.4)


def test_tracker_predictions_are_out_of_sample_under_both_schemes():
    from tools.cnb_tracker.revisions import predictions, scores, HORIZONS
    rng = np.random.default_rng(5); rows = []
    for pair in range(18):
        cpi, fx, oil = rng.normal(size=3)
        for j in HORIZONS:
            rows.append(dict(pair=pair, report=f'r{pair:02d}', target=f't{pair}_{j}', j=j, revision=.5 * cpi, cpi_news=cpi, core_news=.3 * cpi, noncore_news=.7 * cpi, fx_news=fx, brent_news=oil))
    pred = predictions(pd.DataFrame(rows)); table = scores(pred).set_index(['scheme', 'model', 'j'])
    assert table.loc[('leave_one_out', 'T1_CPI', 2), 'n'] == 18 and table.loc[('expanding', 'T1_CPI', 2), 'n'] == 10
    assert table.loc[('leave_one_out', 'T1_CPI', 2), 'rmse'] < 1e-9 and table.loc[('expanding', 'T2_CPI_FX_OIL', 3), 'sign_hit_rate'] == 1.
    assert (pred[pred.model.eq('T0_ZERO')].predicted == 0).all() and np.isnan(table.loc[('leave_one_out', 'T0_ZERO', 0), 'sign_hit_rate'])
    spoiled = pd.DataFrame(rows); spoiled.loc[spoiled.pair.eq(17), 'revision'] = 1e6  # the held-out pair cannot influence its own prediction
    again = predictions(spoiled)
    a = pred[(pred.scheme == 'leave_one_out') & (pred.pair == 17)].predicted.to_numpy(); b = again[(again.scheme == 'leave_one_out') & (again.pair == 17)].predicted.to_numpy()
    np.testing.assert_allclose(a, b, atol=1e-12)
