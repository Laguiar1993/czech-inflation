import json

import numpy as np
import pandas as pd
import pytest

from tools.recording.cnb_ledger import record, resolve, verify, current_report, quarter_value


def make_run(folder, capture_kind='live', food=.2):
    folder.mkdir(parents=True); origin = pd.Period('2026-09', 'M'); months = pd.period_range('2023-01', '2026-08', freq='M')
    weights = dict(weight_core=.55, weight_food=.18, weight_alc=.08, weight_fuel=.04, weight_administered=.15)
    contributions = lambda core, fd: dict(contribution_core=.55 * core, contribution_food=.18 * fd, contribution_alcohol_tobacco=.08 * .2,
                                          contribution_fuel=.04 * .2, contribution_administered=.15 * .2, contribution_wedge=0.)
    rows = []; history = pd.Series(.2, index=months); rate = {}
    for h in range(13):
        c_ = contributions(.2, .2 if h == 0 else food); rate[h] = sum(c_.values())
        rows.append(dict(origin=str(origin), h=h, target=str(origin + h), as_of_utc='2026-10-04T21:59:00+00:00', model='M', mm_forecast=rate[h], **c_,
                         **({} if h == 0 else dict(value_core=.2, value_food=food, value_alcohol_tobacco=.2, value_fuel=.2, value_administered=.2, value_wedge=0., **weights))))
    for row in rows:
        window = [history.get(m, np.nan) if m < origin else rate[m.ordinal - origin.ordinal] for m in pd.period_range(origin + row['h'] - 11, origin + row['h'], freq='M')]
        row['yy_exante'] = 100 * np.expm1(np.log1p(np.array(window) / 100).sum())
    pd.DataFrame(rows).to_csv(folder / 'path.csv', index=False)
    for name, column in [('headline', 'cpi_mm'), ('core', 'core'), ('alcohol', 'alcohol_tobacco'), ('regulated', 'reg')]:
        history.rename(column).to_csv(folder / f'{name}.csv', index_label='period')
    pd.DataFrame({'food': history, 'fuel': history}).to_csv(folder / 'components.csv', index_label='period')
    (folder / 'snapshot.json').write_text(json.dumps(dict(target=str(origin), as_of='2026-10-04T23:59:00+02:00', capture_kind=capture_kind)))
    (folder / 'forecast.json').write_text(json.dumps(dict(weights=dict(core=.55, food=.18, alc=.08, fuel=.04, administered=.15),
        main_contributions_pp=dict(core=.11, food=.036, alcohol_tobacco=.016, fuel=.008, administered=.03, wedge=0.))))
    return folder


def make_tables(folder, reports):
    folder.mkdir(parents=True); steady = 100 * (1.002 ** 12 - 1); rows = []
    labels = {'cpi': 'Consumer Price Index (%, y-o-y, average)', 'core': 'Core inflation (%, y-o-y, average, 55.00%*)', 'fuel': 'Fuel prices (%, y-o-y, average, 4.00%*)',
              'food_alc_tobacco': 'Food prices (incl. alcoholic beverages and tobacco, %, y-o-y, average, 26.00%*)', 'administered': 'Administered prices (%, y-o-y, average, 15.00%*)'}
    for report, cpi_shift in reports.items():
        for quarter in ['2026Q3', '2026Q4', '2027Q1', '2027Q2', '2027Q3']:
            for key, label in labels.items():
                rows.append(dict(report_date=report, indicator=key, row_label=label, frequency='Q', period=quarter, value=steady + (cpi_shift if key == 'cpi' else 0.), is_forecast=True))
    pd.DataFrame(rows).to_csv(folder / 'cnb_mpr_indicators_long.csv', index=False)
    return folder


def test_quarter_value_mixes_known_history_and_the_path_but_never_a_later_actual():
    known = pd.Series({pd.Period('2026-07', 'M'): 2., pd.Period('2026-08', 'M'): 2.2, pd.Period('2026-09', 'M'): 99.})
    assert quarter_value('2026Q3', pd.Period('2026-09', 'M'), {'2026-09': 2.4}, known) == pytest.approx((2. + 2.2 + 2.4) / 3)
    assert np.isnan(quarter_value('2027Q4', pd.Period('2026-09', 'M'), {'2027-10': 2.}, known))


def test_current_report_is_the_latest_one_before_the_clock_day():
    long = pd.DataFrame({'report_date': ['2026-05-14', '2026-08-13', '2026-11-12']})
    assert current_report(long, '2026-10-04T23:59:00+02:00') == '2026-08-13'
    assert current_report(long, '2026-08-13T10:00:00+02:00') == '2026-05-14'          # the report day itself is not yet "before"


def test_record_appends_once_names_the_driver_and_the_chain_detects_tampering(tmp_path):
    run = make_run(tmp_path / 'run', food=.6); tables = make_tables(tmp_path / 'tables', {'2026-08-13': 0.}); ledger = tmp_path / 'ledger'
    rows = record(run, tables, ledger)
    assert set(rows['mode']) == {'prospective'} and set(rows.quarter) == {'2026Q3', '2026Q4', '2027Q1', '2027Q2', '2027Q3'}
    far = rows.set_index('quarter').loc['2027Q2']
    assert far.gap > .3 and far.call_030 and far.revision_test_eligible and far.dominant_block == 'food_alc_tobacco'
    assert far.gap_food_alc_tobacco == pytest.approx(far.gap, abs=.02) and abs(far.gap_core) < 1e-9
    near = rows.set_index('quarter').loc['2026Q3']
    assert not near.call_030 and not near.revision_test_eligible                  # abstentions are recorded too
    assert verify(ledger) == dict(entries=1, rows=5, ok=True)
    with pytest.raises(ValueError, match='already recorded'):
        record(run, tables, ledger)
    text = (ledger / 'ledger.csv').read_text().replace('above', 'below', 1); (ledger / 'ledger.csv').write_text(text)
    assert not verify(ledger)['ok']
    with pytest.raises(ValueError, match='chain is broken'):
        record(make_run(tmp_path / 'run2', food=.5), tables, ledger)


def test_a_fixture_run_can_never_be_labelled_prospective(tmp_path):
    rows = record(make_run(tmp_path / 'run', capture_kind='historical_fixture'), make_tables(tmp_path / 'tables', {'2026-08-13': 0.}), tmp_path / 'ledger')
    assert set(rows['mode']) == {'replay_not_prospective'}


def test_resolve_never_edits_the_ledger_and_scores_revision_and_outcome_separately(tmp_path):
    run = make_run(tmp_path / 'run', food=.6); ledger = tmp_path / 'ledger'
    record(run, make_tables(tmp_path / 'tables', {'2026-08-13': 0.}), ledger); before = (ledger / 'ledger.csv').read_bytes()
    newer = make_tables(tmp_path / 'tables2', {'2026-08-13': 0., '2026-11-12': .5})
    months = pd.period_range('2023-01', '2027-06', freq='M'); realised = pd.Series(.2, index=months); realised.loc['2026-10':] = .26
    realised.rename('cpi_mm').to_csv(tmp_path / 'headline.csv', index_label='period')
    out = resolve(ledger, newer, tmp_path / 'headline.csv').set_index('quarter')
    assert (ledger / 'ledger.csv').read_bytes() == before and verify(ledger)['ok']
    assert out.loc['2027Q2', 'revision'] == pytest.approx(.5) and out.loc['2027Q2', 'revision_direction_agrees'] and out.loc['2027Q2', 'revision_confirmed']
    assert not out.loc['2026Q4', 'target_still_future'] and np.isnan(out.loc['2026Q4', 'revision'])   # the next report's own quarter is no longer a forecast test
    assert out.loc['2027Q2', 'material_gain'] and not out.loc['2027Q2', 'material_loss']
    assert np.isnan(out.loc['2027Q3', 'realised']) and not out.loc['2027Q3', 'material_gain']        # unmatured stays unmatured
