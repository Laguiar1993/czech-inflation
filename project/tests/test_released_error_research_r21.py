import numpy as np
import pandas as pd
from models.released_error_research_r21 import eligible_rows, bias_offset, pool_weights, blend_paths, offset_prediction
from tools.research_r21.path import prepare_training, feedback, EXPERTS


def test_future_and_unpublished_labels_do_not_enter_bias():
    rows=pd.DataFrame({'target':['2020-01','2020-02','2020-03'], 'available_from':['2020-02-10','2020-07-10','2020-04-10'], 'error':[.2,1e8,1e8]})
    z=eligible_rows(rows,'2020-03','2020-03-10')
    assert z.target.tolist()==['2020-01']
    assert bias_offset(z,minimum=1)==.2/25
    rows.loc[1:,'error']=-1e9
    assert bias_offset(eligible_rows(rows,'2020-03','2020-03-10'),minimum=1)==.2/25


def test_missing_availability_fails_closed():
    rows=pd.DataFrame({'target':['2020-01'], 'available_from':[None], 'error':[1.]})
    assert eligible_rows(rows,'2020-03','2020-03-10').empty


def test_pool_does_not_read_unmatured_outcomes():
    pred=np.ones((15,3,12))*.2
    pred[:,1,:]=.1;pred[:,2,:]=.3
    truth=np.ones((15,12))*.1
    mask=np.ones((15,12),bool);mask[-3:,3:]=False
    ages=np.tile(np.arange(12)[::-1],(15,1))
    a=pool_weights(pred,truth,mask,ages)
    truth[~mask]=1e20
    b=pool_weights(pred,truth,mask,ages)
    np.testing.assert_allclose(a,b,atol=1e-12)
    assert np.isclose(a.sum(),1) and a[0]>=.25-1e-10 and min(a)>=0


def test_equal_experts_keep_prior_and_exact_blend():
    pred=np.ones((15,3,12))*.2
    w=pool_weights(pred,np.ones((15,12))*.1,np.ones((15,12),bool),np.zeros((15,12)))
    np.testing.assert_allclose(w,[.5,.25,.25],atol=1e-10)
    np.testing.assert_allclose(blend_paths(pred[0],w),.2)


def test_nowcast_fit_never_uses_future_labels_or_preprocessing_rows():
    dates=pd.period_range('2010-01',periods=40,freq='M')
    x=pd.DataFrame({'a':np.arange(40,dtype=float)},index=dates)
    y=pd.Series(.2,index=dates)
    releases=pd.Series((dates+1).to_timestamp()+pd.Timedelta(days=10),index=dates)
    o=dates[30];asof=releases.iloc[29]+pd.Timedelta(days=1)
    a=offset_prediction(x,y,releases,o,asof,'enet')
    y.loc[o:]=1e8;x.loc[dates>o]=1e12
    b=offset_prediction(x,y,releases,o,asof,'enet')
    assert a==b
    assert a['n']==30 and a['last_release']<=asof.isoformat()


def test_partial_pool_uses_only_published_prefix_and_is_future_poison_invariant():
    target=pd.period_range('2020-02',periods=12,freq='M')
    frame=pd.DataFrame([dict(origin='2020-01',h=h,model=m,mm_forecast=.2) for m in EXPERTS for h in range(1,13)])
    actual=pd.Series(.1,index=target);available=pd.Series((target+1).to_timestamp()+pd.Timedelta(days=10),index=target)
    args=(frame,actual,available,pd.Period('2020-05','M'),pd.Timestamp('2020-05-15'))
    a,ledger=prepare_training(*args)
    assert [r['h'] for r in ledger]==[1,2,3]
    actual.iloc[3:]=1e12
    b,_=prepare_training(*args)
    for x,y in zip(a,b):np.testing.assert_allclose(x,y,equal_nan=True)
    assert prepare_training(*args,complete=True)[1]==[]


def test_feedback_preserves_h0_and_contribution_sum_and_decays():
    f=pd.DataFrame(dict(h=range(13),mm_forecast=.3,value_core=.2,weight_core=.5,contribution_core=.1,contribution_food=.2))
    months=pd.period_range('2018-01',periods=12,freq='M')
    errors=pd.DataFrame(dict(block='core',target=months.astype(str),available_from=(months+1).to_timestamp(),error=.3))
    out,diag=feedback(f,errors,pd.Period('2020-01','M'),pd.Timestamp('2020-02-01'),['core'])
    assert out.iloc[0].equals(f.iloc[0])
    np.testing.assert_allclose(out.mm_forecast,out.contribution_core+out.contribution_food)
    delta=100*(np.log1p(out.value_core.iloc[1:]/100)-np.log1p(.2/100))
    np.testing.assert_allclose(delta,diag[0]['offset_log']*.9**np.arange(12))
