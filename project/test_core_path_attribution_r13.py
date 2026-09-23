import importlib.util
import numpy as np
import pandas as pd
import pytest


def api():
    assert importlib.util.find_spec('evaluation.core_path_attribution_r13'), 'attribution implementation missing'
    from evaluation.core_path_attribution_r13 import replacement_path, error_attribution
    return replacement_path,error_attribution


def fixture():
    frame=pd.DataFrame({'h':range(13),'target':pd.period_range('2024-01',periods=13,freq='M').astype(str),
                        'mm_forecast':np.repeat(.3,13),'weight_core':np.repeat(.5,13)})
    for name in ('food','administered','alcohol_tobacco','fuel','wedge'):
        frame['contribution_'+name]=.02
    core=pd.Series(.2,index=pd.PeriodIndex(frame.target,freq='M'))
    return frame,core


def test_replacement_is_evaluation_only_preserves_h0_and_inputs():
    replace,_=api(); frame,core=fixture(); original=frame.copy(deep=True)
    result=replace(frame,core)
    assert result[0]==.3
    assert result[1]==pytest.approx(.2)
    pd.testing.assert_frame_equal(frame,original)
    core.iloc[1]=1.
    assert replace(frame,core)[1]==pytest.approx(.6)
    pd.testing.assert_frame_equal(frame,original)


def test_missing_core_or_other_leg_stays_unavailable():
    replace,_=api(); frame,core=fixture()
    core.iloc[1]=np.nan
    frame.loc[2,'contribution_food']=np.nan
    result=replace(frame,core)
    assert np.isnan(result[1]) and np.isnan(result[2])


def test_exact_nonlinear_annual_error_identity():
    _,attribute=api()
    result=attribute(6.,5.,2.,3.)
    assert result['reference_core_error']==3
    assert result['candidate_core_error']==2
    assert result['other_error']==1
    assert result['headline_squared_gain']==7
    assert result['core_squared_gain']==5
    assert result['cross_term_gain']==2


def test_invalid_month_grid_rejected():
    replace,_=api(); frame,core=fixture()
    with pytest.raises(ValueError,match='horizon'):
        replace(frame.iloc[:-1],core)
