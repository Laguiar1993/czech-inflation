import importlib
import numpy as np
import pandas as pd
import pytest


def module(): return importlib.import_module('path_attribution_r14')


def example(core=1.,food=0.,h0=0.):
    blocks=['core','food','fuel','administered','alcohol_tobacco']
    values=dict(zip(blocks,[core,food,0.,0.,0.])); weights=dict(zip(blocks,[.5,.5,0.,0.,0.]))
    rows=[]
    for h in range(13):
        row=dict(model='SYNTHETIC',origin='2020-01',h=h,target=str(pd.Period('2020-01')+h),
                 as_of_utc='2020-02-10T22:59:00+00:00',mm_forecast=h0 if h==0 else .5*(core+food))
        for b in blocks:
            row['value_'+b]=values[b] if h else np.nan
            row['weight_'+('alc' if b=='alcohol_tobacco' else b)]=weights[b] if h else np.nan
            row['contribution_'+b]=weights[b]*values[b] if h else np.nan
        row['contribution_wedge']=0. if h else np.nan
        rows.append(row)
    actual=pd.DataFrame(0.,index=pd.period_range('2018-01','2021-01',freq='M'),columns=['headline',*blocks])
    return pd.DataFrame(rows),actual


def one(table,h=12,block='core'):
    return table.loc[table.h.eq(h)&table.block.eq(block)].iloc[0]


def test_oracle_exact_annual_identity_and_distinct_linear_log_units():
    native,actual=example(); row=one(module().calculate(native,actual))
    expected=100*((1.005)**12-1)
    assert row.annual_error==pytest.approx(expected)
    assert row.annual_other_error==pytest.approx(0.)
    assert row.annual_block_error==pytest.approx(expected)
    assert row.cumulative_weighted_error==pytest.approx(6.)
    assert row.cumulative_log_error==pytest.approx(1200*np.log1p(.01))


def test_error_offset_can_make_single_block_oracle_worse():
    native,actual=example(core=1.,food=-1.)
    row=one(module().calculate(native,actual))
    assert row.annual_error==pytest.approx(0.)
    assert row.oracle_mse_gain<0
    assert row.block_squared_error+row.other_squared_error+row.cross_term==pytest.approx(0.,abs=1e-10)


def test_single_block_annual_effects_are_not_additive_shares():
    native,actual=example(core=10.,food=10.)
    result=module().calculate(native,actual)
    a=one(result,block='core'); b=one(result,block='food')
    assert abs(a.annual_block_error+b.annual_block_error-a.annual_error)>1.


def test_h0_preserved_and_irrelevant_at_h12():
    native,actual=example(h0=1.); result=module().calculate(native,actual)
    other_native,unused=example(h0=20.); changed=module().calculate(other_native,actual)
    assert one(result,6).annual_error!=one(changed,6).annual_error
    assert one(result,12).annual_error==one(changed,12).annual_error
    assert one(result,6).cumulative_log_error==one(changed,6).cumulative_log_error


def test_missing_intermediate_actual_retained_without_partial_sum():
    native,actual=example(); actual.loc[pd.Period('2020-03'),'core']=np.nan
    result=module().calculate(native,actual)
    assert len(result)==60
    row=one(result,6)
    assert np.isnan(row.cumulative_log_error) and np.isnan(row.annual_block_error)
    assert row.n_actual_months==5 and np.isfinite(row.annual_error)
    assert np.isfinite(one(result,6,'food').annual_block_error)


def test_missing_forecast_stays_missing_but_other_block_error_is_available():
    native,actual=example(); native.loc[native.h.eq(2),'mm_forecast']=np.nan
    native.loc[native.h.eq(2),['value_core','contribution_core']]=np.nan
    result=module().calculate(native,actual)
    assert np.isnan(one(result,6).annual_error)
    assert np.isnan(one(result,6).cumulative_log_error)
    assert np.isfinite(one(result,6,'food').cumulative_log_error)


def test_alcohol_uses_saved_alc_weight_and_no_input_mutation():
    native,actual=example(); native.loc[native.h.gt(0),'weight_alc']=.1
    native.loc[native.h.gt(0),'value_alcohol_tobacco']=2.
    native.loc[native.h.gt(0),'contribution_alcohol_tobacco']=.2
    native.loc[native.h.gt(0),'mm_forecast']+=.2
    old_native=native.copy(deep=True); old_actual=actual.copy(deep=True)
    row=one(module().calculate(native,actual),block='alcohol_tobacco')
    assert row.monthly_weighted_error==pytest.approx(.2)
    assert row.cumulative_weighted_error==pytest.approx(2.4)
    pd.testing.assert_frame_equal(native,old_native); pd.testing.assert_frame_equal(actual,old_actual)


def test_duplicate_or_missing_native_horizon_is_rejected():
    native,actual=example()
    with pytest.raises(ValueError,match='unique|horizon'):
        module().calculate(pd.concat([native,native.iloc[:1]]),actual)
    with pytest.raises(ValueError,match='horizon'):
        module().calculate(native.loc[native.h.ne(2)],actual)
