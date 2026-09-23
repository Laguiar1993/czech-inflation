import numpy as np
import pytest
from test_path_attribution_r14 import example


def test_joint_oracle_exposes_offsets_and_keeps_h0():
    from tools.review.r17_component_attribution import joint_oracles
    native,actual=example(core=1.,food=-1.,h0=.5)
    rows=joint_oracles(native,actual)
    full=rows[rows.block.eq('all_components')].set_index('h')
    noncore=rows[rows.block.eq('noncore')].set_index('h')
    assert full.loc[12,'annual_oracle']==pytest.approx(0.)
    assert full.loc[6,'annual_oracle']==pytest.approx(.5)
    assert noncore.loc[12,'oracle_mse_gain']<0
    assert np.allclose(rows.headline_squared_error,rows.block_squared_error+rows.other_squared_error+rows.cross_term)


def test_missing_joint_actual_never_becomes_partial_replacement():
    from tools.review.r17_component_attribution import joint_oracles
    native,actual=example(core=1.)
    actual.loc['2020-03','food']=np.nan
    rows=joint_oracles(native,actual)
    assert rows.loc[rows.h.ge(2),'annual_oracle'].isna().all()
    assert rows.loc[rows.h.eq(1),'annual_oracle'].notna().all()


def test_primary_support_is_exact_original_all_model_intersection():
    from tools.review.r17_component_attribution import common_support
    import pandas as pd
    raw=pd.DataFrame([dict(origin='2020-01',h=h,model=m,yy_exante=1.,yy_actual=1.) for h in (1,2) for m in ('a','b')])
    raw.loc[raw.h.eq(2)&raw.model.eq('b'),'yy_exante']=np.nan
    assert common_support(raw,['a','b']).h.tolist()==[1]
    with pytest.raises(ValueError):common_support(pd.concat([raw,raw.iloc[:1]]),['a','b'])
