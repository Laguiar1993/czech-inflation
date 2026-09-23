import numpy as np
import pandas as pd
from tools.review import evaluate_r17 as e


def test_sustained_score_preserves_false_calls_and_common_support():
    rows=pd.DataFrame([dict(origin=o,target='2025-01',model=m,predicted=p,actual=a,eligible=ok)
        for o,m,p,a,ok in [('2024-01','base',0,1,True),('2024-01','new',1,1,True),
                          ('2024-02','base',1,0,True),('2024-02','new',-1,0,True),
                          ('2024-03','base',1,1,True),('2024-03','new',np.nan,1,False)]])
    scores=e.sustained_summary(rows,['base','new']).query("sample == 'full'").set_index('model')
    assert scores.loc['new','n']==2 and scores.loc['new','hits']==1 and scores.loc['new','false_calls']==1
    assert scores.loc['new','precision']==.5 and scores.loc['base','misses']==1


def test_replay_uses_explicit_roster_and_current_titles(tmp_path):
    roster=['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','PATH_POOL_R17','EXTRA_R17']
    data=e.replay_data(pd.DataFrame(),pd.DataFrame(columns=['is_forecast','report_date']),pd.Series(dtype=float),pd.DataFrame(),pd.DataFrame(),roster)
    assert {x['id'] for x in data['series'] if x['kind']=='model'}==set(roster)
    assert sum(s['default'] for s in data['series'])==5
    target=tmp_path/'r17.html';e.write_replay(target,data)
    text=target.read_text(encoding='utf-8')
    assert 'complete 4-model roster' in text and '14-model' not in text and 'Czech CPI · R17' in text
    assert 'clock-select' in text and 'round-select' in text and 'type="checkbox"' in text


def test_native_only_core_join_retains_numeric_dtype():
    f=pd.DataFrame(dict(origin='2024-01',model='x',h=range(13),target=pd.period_range('2024-01',periods=13,freq='M').astype(str)))
    n=f.assign(value_core=.3);actual=pd.Series(.2,index=pd.period_range('2024-01',periods=13,freq='M'))
    result=e.attach_native_core(f,n,actual)
    assert np.isfinite(result.core_mm_forecast).all()
    assert result.core_mm_forecast.dtype==np.dtype('float64')
