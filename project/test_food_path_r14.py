"""R14 economic-pipeline and information-clock contracts, before fitting."""
import importlib
import importlib.util

import numpy as np
import pandas as pd
import pytest


def model():
    assert importlib.util.find_spec('models.food_path_r14') is not None, 'R14 food model not implemented'
    return importlib.import_module('models.food_path_r14')


def sample():
    index=pd.period_range('2000-01','2016-12',freq='M'); z=np.arange(len(index))
    values=pd.DataFrame({'agri4':.12*z+2*np.sin(z/8), 'food_ppi':.17*z+.8*np.sin(z/9),
                        'food':.2*z+.5*np.sin(z/10)+.2*np.sin(2*np.pi*z/12)},index=index)
    dates=pd.DataFrame({col:[(p+1).to_timestamp()+pd.Timedelta(days=20) for p in index] for col in values},index=index)
    return values,dates


def forecast(values=None,dates=None):
    m=model(); y,a=sample()
    return m.forecast_origin(y if values is None else values,a if dates is None else dates,
                            pd.Period('2014-01','M'),pd.Timestamp('2014-02-09'))


def test_future_values_and_release_dates_cannot_change_forecast():
    y,a=sample(); reference=forecast(); y.loc[y.index>=pd.Period('2014-01','M')]=1e12
    a.loc[a.index>=pd.Period('2014-01','M')]=pd.Timestamp('2000-01-01')
    assert forecast(y,a)['paths']==reference['paths']


def test_unknown_last_release_is_not_conditioned_as_observed():
    y,a=sample(); a.loc['2013-12','agri4']=pd.NaT
    reference=forecast(y,a); y.loc['2013-12','agri4']=1e8
    changed=forecast(y,a)
    assert changed['paths']==reference['paths']
    assert changed['diagnostics']['last_released_month']['agri4']=='2013-11'


def test_matched_own_model_uses_primary_training_dates():
    result=forecast(); fits=result['fits']
    assert fits[0]['train_start']==fits[1]['train_start']
    assert fits[0]['train_end']==fits[1]['train_end']
    assert fits[0]['n_train']==fits[1]['n_train']


def test_prior_own_random_walk_means_and_lag_decay():
    m=model(); sigma=np.array([2.,1.]); mean,variance=m.minnesota_prior(sigma,0)
    assert mean[0]==1 and mean[1]==0 and mean[2]==0
    assert np.sqrt(variance[0])==pytest.approx(.2)
    assert np.sqrt(variance[1])==pytest.approx(.2)
    assert np.sqrt(variance[2])==pytest.approx(.1)
    assert mean[-1]==0


def test_training_only_sigma_and_covariance():
    m=model(); y,a=sample(); cut=y.loc[:'2012-12']; fit=m.fit_level_var(cut)
    np.testing.assert_allclose(fit['sigma'],cut.diff().iloc[1:].std(ddof=0))
    e=fit['residuals']; raw=e.T@e/len(e); want=.9*raw+.1*np.diag(np.diag(raw))
    want+=np.eye(3)*(1e-10*np.diag(raw).mean())
    np.testing.assert_allclose(fit['Q'],want,atol=1e-15)


def test_minimum_history_has_no_fallback():
    m=model(); y,a=sample(); t=pd.Period('2002-01','M')
    result=m.forecast_origin(y,a,t,pd.Timestamp('2002-02-09'))
    assert all(np.isnan(v) for p in result['paths'].values() for v in p.values())
    assert result['diagnostics']['status']=='insufficient_history'


def test_conditional_state_matches_observation_and_keeps_unknown_uncertainty():
    m=model(); mean=np.array([1.,2.,3.]); cov=np.array([[2.,1.,0.],[1.,3.,.5],[0.,.5,4.]])
    updated,variance=m.condition_state(mean,cov,{0:5.})
    assert updated[0]==5.
    assert updated[1]==4.
    assert abs(variance[0,0])<1e-12 and variance[1,1]>0


def test_conditioning_never_treats_unknown_coordinate_as_zero():
    m=model(); mean=np.array([2.,3.]); cov=np.eye(2)
    new,v=m.condition_state(mean,cov,{})
    np.testing.assert_array_equal(new,mean); np.testing.assert_array_equal(v,cov)


def test_recursive_known_cost_shock_has_delayed_food_effect():
    m=model(); A=np.zeros((3,3)); A[0,0]=.5; A[1,0]=.5; A[2,1]=.5
    baseline=m.simulate_state(A,np.zeros((3,12)),np.zeros(3),pd.Period('2020-01','M'),4)
    shocked=m.simulate_state(A,np.zeros((3,12)),np.array([1.,0.,0.]),pd.Period('2020-01','M'),4)
    assert shocked[0,2]==baseline[0,2]
    assert shocked[1,2]>baseline[1,2]


def test_destination_month_deterministic_terms():
    m=model(); terms=m.calendar_terms(pd.Period('2020-02','M'))
    assert terms[0]==1 and terms[1]==1 and terms.sum()==2
    assert m.calendar_terms(pd.Period('2020-01','M')).sum()==1


def test_forecast_log_path_and_monthly_product_identity():
    result=forecast()
    for name,path in result['paths'].items():
        loglevel=result['forecast_food_levels'][name]
        assert len(path)==12
        assert sum(np.log1p(np.array(list(path.values()))/100))*100==pytest.approx(loglevel[12]-loglevel[0],abs=1e-12)


def test_no_future_upstream_values_or_marginal_level_ratio_constraint():
    result=forecast()
    assert all(np.isfinite(list(path.values())).all() for path in result['paths'].values())
    assert all('cointegration' not in fit for fit in result['fits'])


def test_replacing_food_preserves_h0_nonfood_and_weights():
    m=model(); base=pd.DataFrame({'h':range(13),'mm_forecast':[.2]*13,'value_food':[.2]*13,
        'weight_food':[.2]*13,'contribution_food':[.04]*13,
        'contribution_core':[.1]*13,'contribution_fuel':[.02]*13,
        'contribution_administered':[.02]*13,'contribution_alcohol_tobacco':[.01]*13,
        'contribution_wedge':[.01]*13})
    new=m.replace_food(base,{h:.4 for h in range(1,13)})
    pd.testing.assert_series_equal(base.loc[0],new.loc[0])
    cols=[x for x in base if x.startswith('contribution_') and x!='contribution_food']+['weight_food']
    pd.testing.assert_frame_equal(base[cols],new[cols])
    assert new.loc[1,'mm_forecast']==pytest.approx(.24)


def test_nonfinite_original_nonfood_stays_nonfinite():
    m=model(); frame=pd.DataFrame({'h':[1],'weight_food':[.2],'value_food':[.2],
        'mm_forecast':[np.nan], 'contribution_core':[np.nan], 'contribution_fuel':[0.],
        'contribution_administered':[0.], 'contribution_alcohol_tobacco':[0.], 'contribution_wedge':[0.]})
    assert np.isnan(m.replace_food(frame,{1:.2}).mm_forecast.iloc[0])


def test_food_input_anchor_and_original_monthly_identity():
    m=model(); panel,available,manifest=m.load_inputs()
    assert panel.index[0]==pd.Period('2015-01','M')
    assert len(panel)==139
    np.testing.assert_array_equal(panel.iloc[0].to_numpy(),0.)
    assert manifest['food_reconstruction_max_abs_difference']<1e-12
