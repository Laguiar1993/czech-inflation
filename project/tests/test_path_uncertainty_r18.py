import numpy as np
import pandas as pd
from models.path_uncertainty_r18 import joint_pool, annual_scenarios


def test_zero_errors_reproduce_index_chain_and_h0_error_matters():
    origin=pd.Period('2022-01','M');known=pd.Series(.2,index=pd.period_range('2020-01','2021-12',freq='M'))
    points=np.array([.5]+[.1]*12)
    a=annual_scenarios(points,np.zeros((2,13)),known,origin)
    assert np.isclose(a[0,0],100*((1.002**11)*1.005-1))
    assert np.isclose(a[0,12],100*(1.001**12-1))
    errors=np.zeros((1,13));errors[0,0]=1.
    b=annual_scenarios(points,errors,known,origin)
    assert b[0,0]>a[0,0] and np.isclose(b[0,12],a[0,12])


def test_joint_pool_rejects_partly_matured_path():
    rows=[]
    for origin in ['2019-01','2019-02','2020-01']:
        for h in range(13):
            target=pd.Period(origin,'M')+h
            rows.append(dict(origin=origin,h=h,target=str(target),forecast=.1,actual=.2,
                             released=str((target+1).to_timestamp()+pd.Timedelta(days=9))))
    f=pd.DataFrame(rows);a=joint_pool(f,'2020-03','2020-04-08')
    assert a['origins']==['2019-01','2019-02']
    f.loc[f.origin=='2020-01','actual']=1000
    b=joint_pool(f,'2020-03','2020-04-08')
    np.testing.assert_array_equal(a['errors'],b['errors'])


def test_missing_known_month_prevents_annual_output():
    known=pd.Series(.1,index=pd.period_range('2020-01','2021-12',freq='M')).drop(pd.Period('2021-11','M'))
    out=annual_scenarios(np.zeros(13),np.zeros((1,13)),known,'2022-01')
    assert np.isnan(out[0,0])
    assert np.isfinite(out[0,12])


def test_interval_scores_expose_missing_distributions_and_zero_common_rows():
    from tools.research_r18.path_uncertainty_final import score_intervals
    intended=pd.DataFrame([dict(origin='2024-01',h=h,model=m,actual=2.)
                           for m in ['A','B'] for h in [1,2]])
    intervals=pd.DataFrame([dict(origin='2024-01',h=h,model='A',actual=2.,point=2.1,
        median=2.,lo80=1.,hi80=3.,lo90=.5,hi90=3.5,crps=.2,coverage80=1.,coverage90=1.)
                           for h in [1,2]])
    scores,ledger=score_intervals(intended,intervals)
    full=scores[scores['sample'].eq('full')]
    assert len(full)==4 and full.n.eq(0).all() and full.n_intended.eq(1).all()
    assert full.loc[full.model.eq('A'),'n_estimated'].eq(1).all()
    assert full.loc[full.model.eq('B'),'n_missing_distributions'].eq(1).all()
    assert full.crps.isna().all() and not ledger.common_scored.any()
    assert ledger.loc[ledger.model.eq('B'),'distribution_status'].eq('missing_distribution').all()


def test_interval_scores_use_same_realised_dates_and_keep_future_ledger_rows():
    from tools.research_r18.path_uncertainty_final import score_intervals
    intended=pd.DataFrame([dict(origin=o,h=1,model=m,actual=a)
                           for m in ['A','B'] for o,a in [('2023-12',2.),('2024-01',np.nan)]])
    intervals=intended.assign(point=2.1,median=2.,lo80=1.,hi80=3.,lo90=.5,hi90=3.5,
                              crps=.2,coverage80=1.,coverage90=1.)
    scores,ledger=score_intervals(intended,intervals)
    full=scores[scores['sample'].eq('full')]
    assert full.n_intended.eq(1).all() and full.n.eq(1).all()
    recent=scores[scores['sample'].eq('origins_2024plus')]
    assert recent.n_intended.eq(0).all() and recent.n.eq(0).all()
    assert len(ledger)==4 and ledger.common_scored.sum()==2
