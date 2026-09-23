from pathlib import Path
import hashlib,json
import pandas as pd
import pytest


def test_live_bundle_requires_explicit_unit_and_source_contract(tmp_path):
    from tools.current_path.run import load_path_inputs
    with pytest.raises(ValueError,match='manifest'):load_path_inputs(tmp_path)


def test_bundle_hash_and_units_fail_closed(tmp_path):
    from tools.current_path.run import load_path_inputs,PATH_FILES,PATH_UNITS
    for name in PATH_FILES:(tmp_path/name).write_text('period,x\n2026-01,1\n')
    manifest={'schema':1,'units':PATH_UNITS,'source_notes':'test supplier inputs',
        'files':{name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in PATH_FILES}}
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    (tmp_path/PATH_FILES[0]).write_text('tampered')
    with pytest.raises(ValueError,match='hash'):load_path_inputs(tmp_path)
    manifest['units']={};(tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='units'):load_path_inputs(tmp_path)


def test_expired_and_future_calendar_targets_are_not_ready():
    from tools.current_path.run import first_release
    with pytest.raises(ValueError,match='calendar'):first_release('2099-01')


def test_json_nonfinite_is_null():
    from tools.current_path.run import clean_json
    assert clean_json({'a':float('nan'),'b':[float('inf'),.1]})=={'a':None,'b':[None,.1]}


def test_source_package_requires_declared_files(tmp_path):
    from tools.current_path.run import load_path_inputs,PATH_UNITS
    (tmp_path/'manifest.json').write_text(json.dumps({'schema':1,'units':PATH_UNITS,'source_notes':'fixture','files':{'../outside.csv':'abc'}}))
    with pytest.raises(ValueError,match='files'):load_path_inputs(tmp_path)


def test_future_forecast_changes_replay_check():
    from tools.current_path.run import verify_path
    from models.current_path import MODELS
    rows=[dict(origin='2026-07',h=h,target=str(pd.Period('2026-07','M')+h),model=m,
        mm_forecast=.2,yy_exante=2.4,contribution_core=.1,status='estimated') for m in MODELS for h in range(13)]
    expected=pd.DataFrame(rows);actual=expected.copy();actual.loc[5,'contribution_core']+=.01
    with pytest.raises(ValueError,match='contribution_core'):verify_path(actual,expected)


def test_freshness_rejects_stale_pipeline_but_allows_normal_lags():
    from tools.current_path.run import input_freshness
    # At the July release eve, June food is known; June PPI/agri are still
    # subject to their own later July publication rules.
    idx=pd.period_range('2026-04','2026-06',freq='M')
    levels=pd.DataFrame({'agri4':[1.,2.,3.],'food_ppi':[1.,2.,3.],'food':[1.,2.,3.]},index=idx)
    available=pd.DataFrame({'agri4':['2026-05-26','2026-06-26','2026-07-26'],
        'food_ppi':['2026-05-20','2026-06-16','2026-07-17'],
        'food':['2026-05-12','2026-06-10','2026-07-10']},index=idx)
    report=input_freshness(levels,available,'2026-07','2026-08-04T12:00:00Z')
    assert report['ready']
    available.loc['2026-06','agri4']=None
    assert not input_freshness(levels,available,'2026-07','2026-08-04T12:00:00Z')['ready']
