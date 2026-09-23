import numpy as np
import pandas as pd
import pytest
from models.nowcast_reliability_r18 import error_law, weighted_quantile, crps, event_probabilities, past_scale


def history():
    idx=pd.period_range('2018-01',periods=40,freq='M')
    return pd.DataFrame({'origin':idx.astype(str),'released':[(x+1).to_timestamp()+pd.Timedelta(days=9) for x in idx],
       'error':np.sin(np.arange(40))*.2,'own_scale':.2,'full_gap':.1,'category_gap':.2})


def test_future_outcomes_do_not_change_law():
    h=history();t='2020-07';clock='2020-08-09'
    a=error_law(h,t,clock,.3,[.1,.2],'STATE')
    h.loc[h.origin>=t,['error','full_gap','category_gap']]=99999
    b=error_law(h,t,clock,.3,[.1,.2],'STATE')
    np.testing.assert_array_equal(a['support'],b['support'])
    np.testing.assert_array_equal(a['weights'],b['weights'])
    assert all(x<t for x in a['training_origins'])


def test_release_gate_and_minimum_history():
    h=history().iloc[:24].copy();h.loc[0,'released']=pd.Timestamp('2025-01-01')
    a=error_law(h,'2020-01','2020-02-09',.3,[.1,.2],'SCALE')
    assert a['status']=='insufficient_history' and a['n']==23


def test_quantile_crps_and_material_overshoot():
    x=np.array([-1.,1.]);w=np.array([.5,.5])
    assert weighted_quantile(x,w,.5)==-1
    assert crps(x,w,0.)==pytest.approx(.5)
    # Actual below consensus, but point far below actual: same direction loses.
    p=event_probabilities(np.array([-.5]),np.array([1.]),-1.2,0.)
    assert p['p_material_gain']==0 and p['p_big']==1


def test_scaled_law_is_finite_and_normalized():
    h=history();a=error_law(h,'2021-06','2021-07-09',.1,[1e6,1e6],'STATE')
    assert a['status']=='estimated'
    assert a['kernel_fallback']
    assert np.isfinite(a['support']).all()
    assert sum(a['weights'])==pytest.approx(1)
    assert a['ess']>=1


def test_pooled_law_keeps_signed_bias_and_scaling_default():
    h=history();h.error=.2
    a=error_law(h,'2021-06','2021-07-09',.4,[.1,.2],'POOLED')
    np.testing.assert_allclose(a['support'],.6)
    assert past_scale(np.array([]))==.25
    assert past_scale(np.zeros(30))==.05
