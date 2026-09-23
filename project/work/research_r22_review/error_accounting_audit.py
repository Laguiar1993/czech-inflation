"""Independent audit of ex-post core oracle, MSE terms and zero-change benchmark."""
from pathlib import Path
import sys,json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c


def main():
    full=ROOT/'output/research_r22/full';out=ROOT/'output/research_r22/diagnostics'
    actual=c.monthly('output/research_r14b/attribution/actual_component_targets.csv','core')
    headline=c.monthly('output/independent_path_frozen_inputs.csv','headline_mm')
    native=pd.read_csv(full/'native_forecasts.csv',float_precision='round_trip',low_memory=False)
    base=native[native.model.eq('STATE_FAST_R15')]
    expected={}
    for origin,g in base.groupby('origin'):
        t=pd.Period(origin,'M');g=g.set_index('h')
        monthly={0:g.loc[0,'mm_forecast']}
        for h in range(1,13):
            monthly[h]=g.loc[h,'mm_forecast']+g.loc[h,'weight_core']*(actual.get(t+h,np.nan)-g.loc[h,'value_core'])
        for h in range(1,13):
            window=pd.period_range(t+h-11,t+h,freq='M')
            rates=np.array([headline.get(m,np.nan) if m<t else monthly[m.ordinal-t.ordinal] for m in window])
            expected[(origin,h)]=100*np.expm1(np.log1p(rates/100).sum())
    p=pd.read_csv(out/'ex_post_error_accounting_pairs.csv')
    difference=p.ex_post_core_truth_yy-np.array([expected[(r.origin,r.h)] for r in p.itertuples()])
    assert abs(difference).max()<1e-10
    assert p.groupby(['origin','h']).ex_post_core_truth_yy.nunique().max()==1
    summaries=pd.read_csv(out/'ex_post_error_accounting_summary.csv')
    for row in summaries.itertuples():
        g=p[p.model.eq(row.model)&p.h.eq(row.h)]
        if row.sample=='origins_2024plus':g=g[g.origin.ge('2024-01')]
        else: assert row.sample=='full'
        other=g.ex_post_core_truth_yy-g.yy_actual;core=g.yy_exante-g.ex_post_core_truth_yy
        expected_terms=[np.mean((g.yy_exante-g.yy_actual)**2),np.mean(other**2),np.mean(core**2),2*np.mean(other*core)]
        np.testing.assert_allclose([row.headline_mse,row.other_mse,row.core_difference_mse,row.cross_term],expected_terms,atol=1e-11)
        assert row.n==len(g)
        np.testing.assert_allclose(row.headline_mse,row.other_mse+row.core_difference_mse+row.cross_term,atol=1e-11)
    drivers=pd.read_csv(full/'driver_forecasts.csv');zero=pd.read_csv(out/'driver_zero_change_benchmark.csv')
    for row in zero.itertuples():
        g=drivers[drivers.model.eq(row.model)&drivers.variable.eq(row.variable)&drivers.h.eq(row.h)]
        if row.sample=='origins_2024plus':g=g[g.origin.ge('2024-01')]
        else: assert row.sample=='full'
        g=g.dropna(subset=['forecast','actual'])
        assert row.n==len(g)
        np.testing.assert_allclose(row.rmse,np.sqrt(np.mean((g.forecast-g.actual)**2)),atol=1e-12)
        np.testing.assert_allclose(row.zero_change_rmse,np.sqrt(np.mean(g.actual**2)),atol=1e-12)
    h12=summaries[summaries.h.eq(12)&summaries['sample'].eq('full')&summaries.model.isin(['STATE_FAST_R15','JOINT_RF_R22'])]
    assert h12.n.eq(75).all()
    report=dict(checks=['Independently compounded oracle from frozen headline history, unchanged h0 and actual future core substitution',
                       'Common oracle identical across every model on all scored keys',
                       'All exported MSE terms and identities reproduced',
                       'All zero-change benchmark comparisons reproduced on identical model/benchmark keys'],
                maximum_oracle_difference=float(abs(difference).max()),h12=h12.to_dict('records'))
    Path(__file__).with_name('error_accounting_audit_results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
