"""Independent adversarial checks for R18 error-vector/compounding contracts."""
import numpy as np
import pandas as pd
import pytest
from models.path_uncertainty_r18 import annual_scenarios, joint_pool
from models.nowcast_reliability_r18_final import weighted_quantile


def history_rows(origins):
    rows=[]
    for i,origin in enumerate(origins):
        for h in range(13):
            target=pd.Period(origin,'M')+h
            rows.append(dict(origin=origin,h=h,target=str(target),forecast=.1*i+.01*h,
                actual=.2*i+.02*h,released=str((target+1).start_time+pd.Timedelta(days=15))))
    return pd.DataFrame(rows)


def test_future_label_mutation_cannot_change_whole_matured_pool():
    rows=history_rows(['2019-01','2019-02','2019-03','2020-01'])
    first=joint_pool(rows,'2020-03','2020-04-09')
    assert first['origins']==['2019-01','2019-02']
    rows.loc[rows.origin.ge('2019-03'),'actual']=900
    rows.loc[rows.origin.ge('2019-03'),'released']='2099-01-01'
    second=joint_pool(rows,'2020-03','2020-04-09')
    np.testing.assert_array_equal(first['errors'],second['errors'])
    assert first['origins']==second['origins']


def test_single_unreleased_missing_or_wrong_h0_invalidates_entire_cohort():
    rows=history_rows(['2019-01','2019-02','2019-03'])
    rows.loc[(rows.origin=='2019-01')&(rows.h==0),'released']='2025-01-01 00:00:00'
    rows.loc[(rows.origin=='2019-02')&(rows.h==0),'actual']=np.nan
    rows=rows[~((rows.origin=='2019-03')&(rows.h==0))]
    assert joint_pool(rows,'2021-01','2021-02-09')['n_pool']==0


def test_pool_latest_sixty_preserves_whole_joint_vectors():
    rows=history_rows([str(x) for x in pd.period_range('2010-01',periods=70,freq='M')])
    rows=rows.sample(frac=1,random_state=18)
    result=joint_pool(rows,'2020-01','2020-02-01')
    assert result['n_pool']==60
    assert result['origins'][0]=='2010-11' and result['origins'][-1]=='2015-10'
    for i,origin in enumerate(result['origins']):
        own=rows[rows.origin.eq(origin)].sort_values('h')
        expected=100*np.log((1+own.actual.to_numpy()/100)/(1+own.forecast.to_numpy()/100))
        np.testing.assert_allclose(result['errors'][i],expected,atol=1e-12,rtol=0)


def test_annual_scenarios_include_own_h0_then_roll_it_out_at_h12():
    known=pd.Series(0.,index=pd.period_range('2019-01','2019-12',freq='M'))
    points=np.zeros(13);errors=np.zeros((2,13))
    errors[0,0]=100*np.log(1.1);errors[1,12]=100*np.log(1.2)
    actual=annual_scenarios(points,errors,known,'2020-01')
    np.testing.assert_allclose(actual[0,:12],10,atol=1e-12)
    assert actual[0,12]==0
    np.testing.assert_allclose(actual[1,:12],0,atol=1e-12)
    np.testing.assert_allclose(actual[1,12],20,atol=1e-12)
    np.testing.assert_array_equal(points,np.zeros(13))


def test_annual_product_uses_current_origin_only_and_keeps_vectors_together():
    known=pd.Series(np.arange(12)/10,index=pd.period_range('2019-01','2019-12',freq='M'))
    points=np.arange(13)/7
    errors=np.array([np.arange(13)/9,-np.arange(13)/11])
    result=annual_scenarios(points,errors,known,'2020-01')
    for i in range(2):
        path=(1+points/100)*np.exp(errors[i]/100)
        all_relatives=np.r_[1+known.to_numpy()/100,path]
        expected=np.array([100*(np.prod(all_relatives[1+h:13+h])-1) for h in range(13)])
        np.testing.assert_allclose(result[i],expected,atol=2e-12,rtol=0)


def test_future_history_duplicate_keys_and_target_mismatch_fail_closed():
    known=pd.Series([0.],index=pd.PeriodIndex(['2020-01'],freq='M'))
    with pytest.raises(ValueError,match='current/future'):
        annual_scenarios(np.zeros(13),np.zeros((1,13)),known,'2020-01')
    rows=history_rows(['2019-01'])
    with pytest.raises(ValueError,match='Duplicate'):
        joint_pool(pd.concat([rows,rows.iloc[:1]]),'2021-01','2021-02-01')
    rows.loc[rows.h.eq(2),'target']='2019-09'
    with pytest.raises(ValueError,match='horizon'):
        joint_pool(rows,'2021-01','2021-02-01')


@pytest.mark.parametrize('n,p', [(30,.5),(30,.9),(60,.1),(60,.5)])
def test_equal_weight_quantile_exact_boundaries_use_inverse_empirical_cdf(n,p):
    assert weighted_quantile(np.arange(n),np.ones(n)/n,p)==int(np.ceil(n*p))-1


def test_quantile_one_retains_tiny_positive_tail_and_skips_zero_mass_atoms():
    assert weighted_quantile([0,1,2,3],[0,1,1e-18,0],1)==2
    assert weighted_quantile([0,1,2,3],[0,1,1e-18,0],0)==1
