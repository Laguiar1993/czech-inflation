"""Meaningful invariants for descriptive CNB comparisons, not causal attribution."""
import numpy as np
import pandas as pd
import pytest


def api():
    import importlib.util
    assert importlib.util.find_spec('evaluation.path_diagnostics_r13'), 'R13 diagnostic implementation missing'
    from evaluation.path_diagnostics_r13 import prepare_rows, summarise, revision_rows
    return prepare_rows, summarise, revision_rows


def source():
    return pd.DataFrame([
        dict(model='INDEPENDENT_BRIDGE', report_date='2022-02-10',
             report_clock_utc='2022-02-09T23:00:00Z', origin='2021-12',
             as_of_utc='2022-01-11T22:59:00Z', quarter='2022Q3', quarters_ahead=3,
             forecast=3., cnb=2., realised=5., complete=True),
        dict(model='INDEPENDENT_BRIDGE', report_date='2022-05-12',
             report_clock_utc='2022-05-11T22:00:00Z', origin='2022-03',
             as_of_utc='2022-04-11T22:59:00Z', quarter='2022Q3', quarters_ahead=2,
             forecast=4., cnb=4.5, realised=5., complete=True),
    ])


def test_shared_error_identity_and_distinct_agreement():
    prepare, _, _ = api()
    rows = prepare(source())
    first = rows.iloc[0]
    assert first.model_error == -2
    assert first.cnb_error == -3
    assert first.disagreement == 1
    assert first.model_squared_error == pytest.approx(9+1-6)
    assert first.cross_term == -6
    assert first.shared_large_miss
    assert not first.close_agreement
    assert first.abs_error_gain == 1


def test_revisions_compare_same_destination():
    prepare, _, revisions = api()
    other = source().iloc[[0]].copy()
    other['quarter'] = '2022Q4'
    other['quarters_ahead'] = 4
    rows = prepare(pd.concat([source(), other], ignore_index=True))
    rev = revisions(rows)
    assert len(rev) == 1
    assert rev.iloc[0].quarter == '2022Q3'
    assert rev.iloc[0].model_revision == 1
    assert rev.iloc[0].cnb_revision == 2.5
    assert rev.iloc[0].model_abs_error_improvement == 1
    assert rev.iloc[0].cnb_abs_error_improvement == 2.5


@pytest.mark.parametrize('column', ['as_of_utc', 'report_clock_utc'])
def test_naive_or_missing_clock_rejected(column):
    prepare, _, _ = api()
    for value in ['2022-01-01', None]:
        data = source()
        data.loc[0,column] = value
        with pytest.raises(ValueError, match='clock'):
            prepare(data)


def test_post_report_or_duplicate_forecast_rejected():
    prepare, _, _ = api()
    bad = source()
    bad.loc[0, 'as_of_utc'] = bad.loc[0, 'report_clock_utc']
    with pytest.raises(ValueError, match='before'):
        prepare(bad)
    with pytest.raises(ValueError, match='duplicate'):
        prepare(pd.concat([source(), source().iloc[[0]]]))


def test_unknown_outcome_keeps_agreement_without_accuracy():
    prepare, summary, revisions = api()
    data = source()
    data['realised'] = np.nan
    rows = prepare(data)
    assert rows.forecast_available.all()
    assert not rows.scored.any()
    assert rows.disagreement.tolist() == [1., -.5]
    assert rows.model_error.isna().all()
    allrow = summary(rows).query("panel == 'all_reports' and horizon == 'all'").iloc[0]
    assert allrow.n_agreement == 2 and allrow.n_scored == 0
    assert np.isnan(allrow.model_rmse)
    assert revisions(rows).model_abs_error_improvement.isna().all()


def test_incomplete_predictions_remain_in_coverage():
    prepare, summary, _ = api()
    data = source()
    data.loc[0, 'complete'] = False
    data.loc[0, 'forecast'] = np.nan
    allrow = summary(prepare(data)).query("panel == 'all_reports' and horizon == 'all'").iloc[0]
    assert allrow.n_source == 2
    assert allrow.n_agreement == allrow.n_scored == 1


def test_infinity_and_inconsistent_realised_quarter_rejected():
    prepare, _, _ = api()
    data = source()
    data.loc[0, 'forecast'] = np.inf
    with pytest.raises(ValueError, match='infinite'):
        prepare(data)
    data = source()
    data.loc[0, 'realised'] = 4
    with pytest.raises(ValueError, match='outcomes'):
        prepare(data)


def test_summaries_count_unique_quarters_and_age():
    prepare, summary, _ = api()
    allrow = summary(prepare(source())).query("panel == 'all_reports' and horizon == 'all'").iloc[0]
    assert allrow.n_scored == 2 and allrow.n_unique_quarters == 1
    assert allrow.model_rmse == pytest.approx(np.sqrt(2.5))
    assert allrow.cnb_rmse == pytest.approx(np.sqrt(4.625))
    assert allrow.age_days_min > 28
    assert allrow.model_mse == pytest.approx(allrow.cnb_mse+allrow.disagreement_mse+allrow.mean_cross_term)


def test_unchanged_origin_not_described_as_new_model_forecast():
    prepare, _, revisions = api()
    data = source()
    data.loc[1, 'origin'] = data.loc[0, 'origin']
    data.loc[1, 'as_of_utc'] = data.loc[0, 'as_of_utc']
    data.loc[1, 'forecast'] = data.loc[0, 'forecast']
    rev = revisions(prepare(data)).iloc[0]
    assert not rev.model_origin_changed
    assert rev.model_revision == 0


def test_missing_middle_report_is_not_silently_bridged():
    prepare, _, revisions = api()
    data = source()
    third = data.iloc[[1]].copy()
    third['report_date'] = '2022-08-11'
    third['report_clock_utc'] = '2022-08-10T22:00:00Z'
    third['as_of_utc'] = '2022-08-09T21:59:00Z'
    third['origin'] = '2022-07'
    data.loc[1,'complete'] = False
    data.loc[1,'forecast'] = np.nan
    rev = revisions(prepare(pd.concat([data,third],ignore_index=True)))
    assert len(rev) == 2
    assert rev.model_revision.isna().all()
    assert not rev.revision_available.any()


def test_same_archived_origin_cannot_claim_conflicting_clocks():
    prepare, _, _ = api()
    data = source()
    data.loc[1,'origin'] = data.loc[0,'origin']
    with pytest.raises(ValueError,match='origin.*clock'):
        prepare(data)
