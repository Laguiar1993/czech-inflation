import importlib
import numpy as np
import pandas as pd
import pytest


def e():return importlib.import_module('models.energy_path_r17')


def test_quote_is_next_day_and_stale_quotes_do_not_become_current():
    s=pd.Series([10.,20.,999.],index=pd.to_datetime(['2020-01-01','2020-01-03','2020-01-04']))
    value,meta=e().quote(s,pd.Timestamp('2020-01-04 10:00'))
    assert value==20 and meta['observation_date']=='2020-01-03'
    assert np.isnan(e().quote(s,pd.Timestamp('2020-03-01'))[0])


def test_log_curve_endpoint_no_predecision_change_and_positive_only():
    dates=pd.to_datetime(['2020-01-01','2020-02-01','2021-01-01'])
    curve=e().log_curve(50.,100.,dates,pd.Timestamp('2020-02-01'),pd.Timestamp('2021-01-01'))
    np.testing.assert_allclose(curve,[50,50,100])
    with pytest.raises(ValueError):e().log_curve(-1,100,dates,dates[0],dates[-1])


def test_poze_capacity_volume_and_double_counting():
    assert e().poze_charge(84.7,25,3,12,3.5,495)==pytest.approx(3.5*495)
    assert e().poze_charge(1,1.2,1,12,100,495)==24
    with pytest.raises(ValueError):e().poze_charge(84.7,25,3,12,3.5,495,True)


def test_national_credit_requires_denominator_and_exposure_is_fail_closed():
    with pytest.raises(ValueError):e().aggregate_credit_relative(None,1.)
    assert e().aggregate_credit_relative(100.,10.)==.9
    assert not e().national_eligibility(True,False,True)[0]
    assert not e().national_eligibility(True,True,False)[0]


def test_vat_expiry_is_inverse_and_gated_by_treatment():
    from models.energy_ledger import Bill, paid_bill
    bill=Bill('illustration','electricity',1.,100.,20.,5.,10.,.21,('commodity','distribution','fixed','levy'),'test')
    events=e().vat_events()
    early=pd.Timestamp('2021-12-09T23:59:59Z').to_pydatetime();late=pd.Timestamp('2021-12-11T00:00Z').to_pydatetime()
    normal=paid_bill(bill,'2021-12',early,events)
    waived=paid_bill(bill,'2021-12',late,events)
    restored=paid_bill(bill,'2022-01',late,events)
    assert waived/normal==pytest.approx(1/1.21)
    assert restored/waived==pytest.approx(1.21)


def test_versions_replace_and_unknown_treatment_is_unavailable():
    rows=pd.DataFrame([dict(policy='p',effective_from='2026-01',available_from='2025-11-28',treatment='2025-11-28',value=8.32),
        dict(policy='p',effective_from='2026-01',available_from='2025-12-29',treatment='2025-12-29',value=0.)])
    assert e().visible_rate(rows,'2026-01','2025-12-01')==8.32
    assert e().visible_rate(rows,'2026-01','2025-12-30')==0
    rows.loc[1,'treatment']=None
    assert e().visible_rate(rows,'2026-01','2025-12-30')==8.32
