"""Diagnostics preserve forecast evaluation, especially non-event alerts."""
import importlib

import numpy as np
import pandas as pd


def test_up_down_frames_keep_all_release_alert_penalties():
    module = importlib.import_module('core_remainder_experiment')
    ix = pd.period_range('2020-01', periods=4, freq='M')
    pred = pd.DataFrame({'R9_BASE':[.1,-.1,.3,0.], 'TARGET_BASE_REMAINDER':[.4,-.4,.5,0.]}, index=ix)
    survey = pd.DataFrame({'actual':[.5,-.5,0.,.1], 'survey_median':0.}, index=ix)
    result = module.assess(pred, survey)
    scores = result['scores'].query("coverage=='common'").set_index(['model','frame'])
    assert scores.loc[('TARGET_BASE_REMAINDER','big_up'),'n']==1
    assert scores.loc[('TARGET_BASE_REMAINDER','big_down'),'n']==1
    assert scores.loc[('TARGET_BASE_REMAINDER','alerts'),'false_alarm']==1
    assert scores.loc[('TARGET_BASE_REMAINDER','alerts'),'alerts']==3
    assert scores.loc[('TARGET_BASE_REMAINDER','big'),'material_win']==2
    assert scores.loc[('TARGET_BASE_REMAINDER','all'),'material_loss']==1


def test_component_attribution_closes_for_all_models_and_records_own_core():
    module = importlib.import_module('core_remainder_experiment')
    ix = pd.period_range('2020-01', periods=3, freq='M')
    pred = pd.DataFrame({'R9_BASE':[.4,.7,.2], 'TARGET_BASE_REMAINDER':[.5,.6,.3]}, index=ix)
    actual = pd.Series([.3,.5,.1], index=ix)
    survey = pd.DataFrame({'actual':actual,'survey_median':[0.,0.,0.]},index=ix)
    weights = pd.Series(.5,index=ix)
    fixed = pd.Series(.1,index=ix)
    core = pd.Series([.3,.4,.2],index=ix)
    result = module.diagnostics(pred, survey, core, weights, fixed)
    attr = result['component_errors']
    for row in attr.itertuples():
        assert abs(row.error-row.weighted_core_error-row.noncore_reconciliation_error)<1e-12
        assert abs(row.headline_squared_gain-row.weighted_core_squared_gain-row.cross_term_gain)<1e-12
    own = result['core_predictions'].query("model=='TARGET_BASE_REMAINDER'")
    np.testing.assert_allclose(own.core_forecast, [.8,1.,.4],atol=1e-12)
