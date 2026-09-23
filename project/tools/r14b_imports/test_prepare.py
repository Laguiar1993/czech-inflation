import importlib
import numpy as np
import pandas as pd
import pytest


def module(): return importlib.import_module('tools.r14b_imports.prepare')


def test_only_missing_pre2015_import_cells_change():
    original=pd.DataFrame({'period':['2008-03','2015-03','2026-08'],
        'import_l2':['','0.30000000000000004',''], 'other':['-0.0','','5'],
        'import_l2_x_state':['','0.3','']})
    prices=pd.Series([-.6,-99.,9.],index=pd.PeriodIndex(['2008-01','2015-01','2026-06'],freq='M'))
    got=module().extend_features(original,prices)
    expected=original.copy(); expected.loc[0,'import_l2']='-0.6'
    pd.testing.assert_frame_equal(got,expected)


def test_source_clock_is_after_known_late_march2014_release():
    clock=module().source_clock(pd.Period('2014-01'))
    assert clock>=pd.Timestamp('2014-03-17 23:59:59',tz='Europe/Prague')
    assert clock==pd.Timestamp('2014-04-01',tz='Europe/Prague')


def test_explicit_import_total_selector_excludes_export_and_cumulative():
    frame=pd.DataFrame({'IndicatorType':['614703','614603','614703','614703'],
        'TYPUDAJE5B':['IM']*4, 'SITCVAD':['00890001','00890001','0','00890001'],
        'Uz0':['CZ']*4,'CASMKMQRM12':['2008-01','2008-01','2008-01','2008-01K'],
        'Hodnota':['99.4','777','888','999']})
    got=module().extract(frame,'SITC')
    assert len(got)==1 and got.iloc[0]==pytest.approx(-.6)


def test_duplicate_months_fail_instead_of_selecting_arbitrary_value():
    frame=pd.DataFrame({'IndicatorType':['614703']*2,'TYPUDAJE5B':['IM']*2,
        'SITCVAD':['00890001']*2,'Uz0':['CZ']*2,'CASMKMQRM12':['2008-01']*2,
        'Hodnota':['99.4','99.5']})
    with pytest.raises(AssertionError,match='duplicate'): module().extract(frame,'SITC')
