import numpy as np
import pandas as pd
import pytest


def example():
    d=pd.DataFrame({'origin':['2023-01','2024-01','2024-02'],'target':['2023-07','2024-07','2024-08'],
                    'h':[6]*3,'model':['CORE_GAP_RIDGE_R14']*3,'yy_actual':[1.,1.,1.],
                    'yy_short':[2.,np.nan,3.],'yy_extended':[1.5,1.2,2.],
                    'core_mm_actual':[0.,0.,0.],'core_mm_short':[1.,np.nan,2.],
                    'core_mm_extended':[.5,.2,1.],'core_log_actual':[0.,0.,0.],
                    'core_log_short':[1.,np.nan,2.],'core_log_extended':[.5,.2,1.]})
    return d


def test_history_comparison_separates_paired_and_own_coverage():
    from core_history_comparison_r14b import metric_tables
    d=example();paired,own=metric_tables(d)
    row=paired[(paired['sample']=='full')&(paired.metric=='yy')].iloc[0]
    assert row.n_intended==3 and row.n_common==2
    assert row.n_short==2 and row.n_extended==3
    assert row.short_rmse==pytest.approx(np.sqrt(2.5))
    assert row.extended_rmse==pytest.approx(np.sqrt(.625))
    assert row.mse_gain==pytest.approx(1.875)
    full=own[(own['sample']=='full')&(own.metric=='yy')]
    assert dict(zip(full.policy,full.n))=={'short':2,'extended':3}
    recent=paired[(paired['sample']=='recent_origins')&(paired.metric=='yy')].iloc[0]
    assert recent.n_common==1 and recent.n_intended==2


def test_history_join_rejects_changed_actual_or_missing_origin():
    from core_history_comparison_r14b import pair_frames
    f=pd.DataFrame({'origin':['2024-01'],'h':[1],'target':['2024-02'],'model':['CORE_GAP_RIDGE_R14'],
                    'yy_exante':[2.],'yy_actual':[1.]})
    c=f[['origin','h','target','model']].assign(mm_forecast=.2,mm_actual=.1,cumulative_log_forecast=.2,cumulative_log_actual=.1)
    bad=f.copy();bad['yy_actual']=9.
    with pytest.raises(ValueError,match='actual'):pair_frames(f,bad,c,c)
    with pytest.raises(ValueError,match='grid'):pair_frames(f,f.iloc[:0],c,c)


def test_local_core_identity_is_required_even_without_realised_outcome():
    from core_history_comparison_r14b import verify_local_identity
    d=example();d['model']='CORE_LOCAL_R14';d['yy_actual']=np.nan
    d['core_mm_extended']=d.core_mm_short;d['core_log_extended']=d.core_log_short;d['yy_extended']=d.yy_short
    assert verify_local_identity(d)['status']=='exact'
    d.loc[0,'core_mm_extended']+=1e-8
    with pytest.raises(ValueError,match='local'):verify_local_identity(d)
