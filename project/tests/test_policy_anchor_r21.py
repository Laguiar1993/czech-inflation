import numpy as np
import pandas as pd
from models.policy_anchor_r21 import core_anchor, anchored_path


def test_unpublished_and_future_history_do_not_change_anchor():
    ix=pd.period_range('2000-01',periods=180,freq='M')
    core=pd.Series(.2,index=ix);headline=pd.Series(.1,index=ix)
    dates=pd.Series((ix+1).to_timestamp()+pd.Timedelta(days=10),index=ix)
    origin=ix[160];clock=(origin+1).to_timestamp()
    a=core_anchor(core,headline,dates,origin,clock)
    core.iloc[160:]=1e9;headline.iloc[160:]=-99.
    assert core_anchor(core,headline,dates,origin,clock)==a
    assert a['last_target']==str(origin-1)


def test_infinite_half_life_matches_fast_and_transition_count():
    state=dict(filter_states={'fast':{'mu':.3,'cycle':.1}},seasonal={str(m):.01*m for m in range(1,13)})
    p=anchored_path(state,'2020-01',.15,np.inf)
    for h in range(1,13):
        assert np.isclose(100*np.log1p(p[h]/100),.3+.8**(h+1)*.1+.01*(pd.Period('2020-01')+h).month)
    p=anchored_path(state,'2020-01',.15,12)
    assert np.isclose(100*np.log1p(p[1]/100),.15+(.3-.15)*2**(-2/12)+.8**2*.1+.02)
