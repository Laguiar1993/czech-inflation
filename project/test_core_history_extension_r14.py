"""Historical import extension changes only authorised missing core features."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

import core_learning_experiment_r14 as runner
from models.core_learning_r14 import origin_state
from test_core_learning_r14 import inputs


def write_extension(tmp_path, monkeypatch, rows=None):
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    folder=tmp_path/'extension';folder.mkdir()
    source=tmp_path/'source.csv';source.write_text('verified,source\n1,2\n')
    payload=pd.DataFrame(rows or [dict(period='2010-01',import_l2=.3,available_from='2010-02-01T00:00:00+01:00')])
    target=folder/'core_feature_extension.csv';payload.to_csv(target,index=False)
    manifest=dict(inputs={'source.csv':hashlib.sha256(source.read_bytes()).hexdigest()},
                  outputs={target.name:hashlib.sha256(target.read_bytes()).hexdigest()},
                  policy='fill_pre_first_valid_import_l2_only')
    (folder/'manifest.json').write_text(json.dumps(manifest))
    return folder


def features():
    return pd.DataFrame({'import_l2':[np.nan,np.nan,.8,.9],'eurczk_mm':[1.,2.,3.,4.]},
                        index=pd.period_range('2009-12',periods=4,freq='M'))


def test_extension_none_is_an_independent_unchanged_copy():
    before=features();actual,available,audit=runner.apply_feature_extension(before,None)
    pd.testing.assert_frame_equal(actual,before,check_exact=True)
    actual.iloc[0,1]=99
    assert before.iloc[0,1]==1 and available is None and audit['policy']=='frozen'


def test_extension_only_fills_missing_historical_import_cell(tmp_path,monkeypatch):
    folder=write_extension(tmp_path,monkeypatch);before=features()
    actual,available,audit=runner.apply_feature_extension(before,folder)
    expected=before.copy();expected.loc['2010-01','import_l2']=.3
    pd.testing.assert_frame_equal(actual,expected,check_exact=True)
    assert pd.isna(before.loc['2010-01','import_l2'])
    assert list(available.index)==[pd.Period('2010-01','M')]
    assert available.iloc[0]==pd.Timestamp('2010-02-01T00:00:00+01:00')
    assert audit['filled_cells']==1


@pytest.mark.parametrize('row,match',[
    (dict(period='2010-02',import_l2=.3,available_from='2010-03-01T00:00:00+01:00'),'finite'),
    (dict(period='2009-11',import_l2=.3,available_from='2009-12-01T00:00:00+01:00'),'existing'),
    (dict(period='2010-01',import_l2=-100.,available_from='2010-02-01T00:00:00+01:00'),'finite'),
    (dict(period='2010-01',import_l2=.3,available_from='2010-01-16T00:00:00+01:00'),'publication'),
    (dict(period='2010-01',import_l2=.3,available_from='2010-02-01T00:00:00'),'aware'),
    (dict(period='2010-01',import_l2=.3,available_from='2010-02-01T00:00:00+01:00',eurczk_mm=7),'columns'),
])
def test_extension_rejects_invalid_overwrites_sources_and_dates(tmp_path,monkeypatch,row,match):
    folder=write_extension(tmp_path,monkeypatch,[row])
    with pytest.raises(ValueError,match=match):runner.apply_feature_extension(features(),folder)


def test_extension_rejects_interior_or_tail_missing_cell(tmp_path,monkeypatch):
    folder=write_extension(tmp_path,monkeypatch,[dict(period='2010-03',import_l2=.3,available_from='2010-04-01T00:00:00+02:00')])
    before=features();before.loc['2010-03','import_l2']=np.nan
    with pytest.raises(ValueError,match='historical'):runner.apply_feature_extension(before,folder)


def test_extension_rejects_duplicate_periods(tmp_path,monkeypatch):
    row=dict(period='2010-01',import_l2=.3,available_from='2010-02-01T00:00:00+01:00')
    folder=write_extension(tmp_path,monkeypatch,[row,row])
    with pytest.raises(ValueError,match='unique'):runner.apply_feature_extension(features(),folder)


def test_extension_verifies_declared_source_and_payload_hashes(tmp_path,monkeypatch):
    folder=write_extension(tmp_path,monkeypatch)
    (tmp_path/'source.csv').write_text('changed')
    with pytest.raises(ValueError,match='hash'):runner.apply_feature_extension(features(),folder)


def test_default_fingerprints_include_executed_fixture_reader():
    assert 'independent_nowcast_experiment.py' in runner.dependencies()


def test_extension_fingerprints_include_its_separate_design_declaration():
    assert 'docs/implementation/R14B_CORE_HISTORY_DESIGN.md' in runner.dependencies('data/research_r14b/imports')


def test_import_override_is_keyed_by_fixture_month_and_gates_last_source():
    core,f,dates=inputs();t=pd.Period('2015-06','M');clock=pd.Timestamp('2015-07-09 23:59',tz='Europe/Prague')
    override=pd.Series([clock+pd.Timedelta(minutes=1)],index=pd.PeriodIndex([t-1],freq='M'))
    assert origin_state(core,f,dates,t,clock,import_available_from=override) is None
    override.iloc[0]=clock
    got=origin_state(core,f,dates,t,clock,import_available_from=override)
    assert got is not None
    assert got['sources']['import']['last_available_from']=='2015-07-09 23:59:00'
    assert got['sources']['import']['n_availability_overrides']==1


def test_import_override_rejects_timezone_naive_or_duplicate_dates():
    core,f,dates=inputs();t=pd.Period('2015-06','M');clock=pd.Timestamp('2015-07-09 23:59')
    naive=pd.Series([clock],index=pd.PeriodIndex([t-1],freq='M'))
    with pytest.raises(ValueError,match='aware'):origin_state(core,f,dates,t,clock,import_available_from=naive)
    aware=pd.Series([clock.tz_localize('Europe/Prague')]*2,index=pd.PeriodIndex([t-1,t-1],freq='M'))
    with pytest.raises(ValueError,match='unique'):origin_state(core,f,dates,t,clock,import_available_from=aware)


def test_native_metadata_reports_candidate_availability_and_preserves_legacy_evidence():
    frame=pd.DataFrame({'h':[0,1,2],'mm_forecast':[.2,.3,.4],
                        'origin_status':['failed_nonfinite']*3,'converged':[False]*3,
                        'fallback_used':[False,True,False],
                        'unemployment_end':['2020-01']*3,'adjustments':[7]*3})
    got=runner.native_metadata(frame,'estimated')
    assert got.origin_status.eq('estimated').all() and got.converged.all()
    assert not got.core_fallback_used.any()
    assert got.legacy_source_fallback_used.tolist()==[False,True,False]
    assert 'unemployment_end' not in got and 'adjustments' not in got
    assert got.legacy_source_unemployment_end.eq('2020-01').all()
    pd.testing.assert_series_equal(got.mm_forecast,frame.mm_forecast,check_exact=True)
    assert frame.origin_status.eq('failed_nonfinite').all()


def test_native_metadata_keeps_partial_path_unavailable():
    frame=pd.DataFrame({'h':[0,1,2],'mm_forecast':[.2,.3,np.nan]})
    got=runner.native_metadata(frame,'unavailable_core_or_noncore')
    assert got.origin_status.eq('failed_nonfinite').all()
    assert got.converged.tolist()==[True,True,False]
    assert got.status.tolist()==['estimated','estimated','unavailable_core_or_noncore']
