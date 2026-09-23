"""R14B declared stable-rate pipeline contracts; written before implementation."""
import importlib,importlib.util
import numpy as np
import pandas as pd
import pytest
from test_food_path_r14 import sample

def model():
    assert importlib.util.find_spec('models.food_stable_r14b') is not None, 'R14B food not implemented'
    return importlib.import_module('models.food_stable_r14b')

def forecast(y=None,a=None):
    levels,dates=sample()
    return model().forecast_origin(levels if y is None else y,dates if a is None else a,
        pd.Period('2014-01','M'),pd.Timestamp('2014-02-09'))

def test_future_values_and_dates_are_irrelevant():
    y,a=sample(); before=forecast(); y.loc['2014-01':]=1e12; a.loc['2014-01':]=pd.Timestamp('1999-01-01')
    assert forecast(y,a)['paths']==before['paths']

def test_rate_requires_both_endpoint_levels_released():
    y,a=sample(); a.loc['2013-11','agri4']=pd.NaT
    before=forecast(y,a); y.loc['2013-11','agri4']=1e12
    after=forecast(y,a); assert before['paths']==after['paths']
    assert after['diagnostics']['last_released_rate']['agri4']=='2013-10'

def test_rolling_response_dates_and_food_means_are_matched():
    f=forecast()['fits']; assert f[0]['training_dates']==f[1]['training_dates']
    assert f[0]['n_train']==96
    np.testing.assert_array_equal(np.array(f[0]['seasonal_means'])[:,-1],np.array(f[1]['seasonal_means'])[:,0])
    assert f[0]['sigma'][-1]==f[1]['sigma'][0]

def test_minimum36_missing_not_fallback():
    y,a=sample(); r=model().forecast_origin(y,a,'2002-01','2002-02-09')
    assert r['diagnostics']['status']=='insufficient_history'
    assert all(np.isnan(v) for p in r['paths'].values() for v in p.values())

def test_first_rate_not_invented():
    y,a,meta=model().load_inputs(); rates=model().released_rates(y,a,'2019-02','2019-03-10')[0]
    assert rates.loc['2015-01'].isna().all()
    assert rates.loc['2015-02'].notna().all()

def test_zero_lag_priors_decay_and_no_intercept():
    m=model(); v=m.prior_variance(np.array([2.,1.]),0)
    assert len(v)==12
    assert np.sqrt(v[0])==pytest.approx(.2)
    assert np.sqrt(v[1])==pytest.approx(.2)
    assert np.sqrt(v[2])==pytest.approx(.1)
    f=forecast()['fits'][0]; assert np.asarray(f['coefficients']).shape==(18,3)

def test_training_only_center_scales_covariance():
    m=model(); y,_=sample(); rates=y.diff(); dates=rates.index[-96:]
    fit=m.fit_rate_var(rates,dates)
    selected=rates.loc[dates]; means=selected.groupby(selected.index.month).mean()
    np.testing.assert_allclose(fit['seasonal_means'],means)
    centered=selected.to_numpy()-means.loc[dates.month].to_numpy()
    np.testing.assert_allclose(fit['sigma'],centered.std(axis=0))
    e=fit['residuals']; raw=e.T@e/len(e)
    want=.9*raw+.1*np.diag(np.diag(raw))+np.eye(3)*1e-10*np.diag(raw).mean()
    np.testing.assert_allclose(fit['Q'],want)
    poisoned=rates.copy(); poisoned.loc[:dates[0]-7]=1e10
    other=m.fit_rate_var(poisoned,dates)
    np.testing.assert_array_equal(other['beta'],fit['beta'])

def test_root_contraction_exact_scaled_roots():
    m=model(); rng=np.random.default_rng(41); beta=rng.normal(size=(18,3))*.2
    beta[:3]+=np.eye(3)*1.3
    before=m.companion(beta); rho=max(abs(np.linalg.eigvals(before)))
    result,c,original,final=m.contract(beta)
    assert original==pytest.approx(rho)
    assert final<=.98+1e-10 and c<1
    np.testing.assert_allclose(np.sort_complex(np.linalg.eigvals(m.companion(result))),np.sort_complex(np.linalg.eigvals(before)*c),atol=1e-8)

def test_stable_coefficients_unchanged():
    m=model(); beta=np.zeros((6,1)); beta[0,0]=.5
    result,c,rho,final=m.contract(beta)
    np.testing.assert_array_equal(result,beta); assert c==1 and rho==final

def test_zero_state_returns_explicit_seasonal_mean():
    m=model(); means=np.arange(36).reshape(12,3)/100
    predicted=m.simulate_rates(np.zeros((18,18)),np.zeros(18),'2020-11',4,means)
    np.testing.assert_array_equal(predicted,means[[10,11,0,1]])

def test_delayed_cost_effect_is_recursive():
    m=model(); beta=np.zeros((18,3)); beta[0,0]=.5; beta[0,1]=.5; beta[1,2]=.5
    A=m.companion(beta); state=np.zeros(18); state[0]=1
    pred=m.simulate_rates(A,state,'2020-01',4,np.zeros((12,3)))
    assert pred[0,2]==0 and pred[1,2]>0

def test_all_fitted_roots_stable_and_no_fixed_ratio():
    r=forecast()
    assert all(f['spectral_radius']<=.98+1e-10 for f in r['fits'])
    assert all('cointegration' not in f for f in r['fits'])

def test_rate_reconstruction_compounds_exactly():
    r=forecast()
    for name,path in r['paths'].items():
        rates=r['forecast_food_rates'][name]
        assert 100*np.log1p(np.array(list(path.values()))/100).sum()==pytest.approx(sum(rates[1:]),abs=1e-12)

def test_ragged_conditioning_keeps_observed_coordinate_exact():
    y,a=sample(); a.loc['2013-12','agri4']=pd.NaT
    r=forecast(y,a); update=r['fits'][0]['conditioning_updates'][-1]
    assert update['observed_columns']==['food_ppi','food']
    assert update['state_variance'][0]>0
    np.testing.assert_array_equal(np.array(update['state_variance'])[1:],0.)

def test_existing_nonfood_and_h0_contract_reused():
    m=model(); assert m.replace_food.__module__=='models.food_path_r14'
