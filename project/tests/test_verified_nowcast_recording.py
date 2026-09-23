import hashlib,json
from datetime import datetime,timezone,timedelta
from pathlib import Path
import pytest


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value,dict) else value,encoding='utf-8')


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def saved(tmp_path,monkeypatch):
    from tools.recording import verified_nowcast as v
    root=tmp_path/'repo';run=root/'run';now=datetime(2026,8,4,12,tzinfo=timezone.utc)
    write(root/'forecast_independent.py','# frozen fixture engine')
    calendar=root/'data/release_calendar_cz_cpi.csv'
    write(calendar,'target_month,first_release_dt,first_release_kind,first_release_source\n2026-07,2026-08-05,flash,czso_release_page\n')
    for name in v.REQUIRED_FRAMES:write(run/(name+'.csv'),'period,value\n2026-06,0.1\n')
    meta=dict(target='2026-07',as_of=(now-timedelta(seconds=60)).isoformat(),
        captured_at=(now-timedelta(seconds=60)).isoformat(),capture_kind='live_snapshot',runtime={'fixture':True},
        hashes={n+'.csv':digest(run/(n+'.csv')) for n in v.REQUIRED_FRAMES},
        frame_schema={n:'monthly' for n in v.REQUIRED_FRAMES},
        code_and_static_inputs={n:digest(root/n) for n in ['forecast_independent.py','data/release_calendar_cz_cpi.csv']})
    result=dict(version='independent-r9-2026-09-09',target=meta['target'],as_of=meta['as_of'],main_model='HARD_BASE',
        completed_at=(now-timedelta(seconds=1)).isoformat(),points_mm_pct={'HARD_BASE':.3,'HARD_HALF':.32,'HARD_FULL':.34},
        main_contributions_pp={'core':.2,'food':.1,'alcohol_tobacco':0.,'administered':0.,'fuel':0.,'wedge':0.},
        ready_for_first_release=True,before_first_release=True,completed_before_first_release=True,prospective_eligible=True,
        detailed_CPI_edge_gap=0,component_history_edges={k:{'gap_months':0} for k in v.COMPONENTS},
        fuel_diagnostics={'stale':False},missing_inputs=[])
    write(run/'snapshot.json',meta);write(run/'forecast.json',result)
    def seal():write(run/'receipt.json',{n:digest(run/n) for n in ['snapshot.json','forecast.json']})
    seal();monkeypatch.setattr(v,'_utc_now',lambda:now);monkeypatch.setattr(v,'_runtime',lambda:{'fixture':True})
    return v,root,run,meta,result,seal,now


def test_replay_records_units_primary_and_comparisons(saved,tmp_path,monkeypatch):
    v,root,run,meta,result,seal,now=saved
    from tools.research_r18 import forecast_archive as a
    monkeypatch.setattr(a,'_utc_now',lambda:now)
    folder=v.record_run(run,tmp_path/'archive',mode='replay',root=root)
    bundle=a.verify_bundle(folder,verify_artifacts=True)
    assert bundle['record_type']=='historical_replay' and bundle['model']=='HARD_BASE'
    assert bundle['point_forecast']==.3 and bundle['path_forecasts']==[]
    assert bundle['metadata']['units']['point']=='monthly_CPI_percent'
    assert bundle['metadata']['independent_comparisons']['HARD_FULL']==.34
    assert bundle['metadata']['path_status']=='latest_audited_path_runtime_not_connected'


def test_fresh_prospective_uses_actual_archive_clock(saved,tmp_path,monkeypatch):
    v,root,run,meta,result,seal,now=saved
    from tools.research_r18 import forecast_archive as a
    monkeypatch.setattr(a,'_utc_now',lambda:now)
    folder=v.record_run(run,tmp_path/'archive',mode='prospective',root=root)
    b=a.verify_bundle(folder,verify_artifacts=True)
    assert b['issued_at_utc']==now.isoformat().replace('+00:00','Z')
    assert b['metadata']['engine_decision_at_utc']!=b['issued_at_utc']
    assert all(x['availability_kind']=='observed_at_verification' for x in b['data_availability'].values())


@pytest.mark.parametrize('file',['core.csv','forecast.json','snapshot.json'])
def test_tampering_fails_before_archive(saved,tmp_path,file):
    v,root,run,meta,result,seal,now=saved
    with (run/file).open('a') as f:f.write(' ')
    with pytest.raises(ValueError,match='hash'):v.record_run(run,tmp_path/'archive',mode='replay',root=root)
    assert not (tmp_path/'archive').exists()


@pytest.mark.parametrize('change,message',[
    ({'main_model':'SENTIMENT_BASE'},'independent'),({'target':'2026-06'},'target'),
    ({'points_mm_pct':{'HARD_BASE':float('nan'),'HARD_HALF':.2,'HARD_FULL':.2}},'finite'),
    ({'main_contributions_pp':{'core':.9,'food':0.,'alcohol_tobacco':0.,'administered':0.,'fuel':0.,'wedge':0.}},'contribution'),
    ({'completed_at':'2026-08-04T11:55:00+00:00'},'completion'),
    ({'ready_for_first_release':False},'ready'),
    ({'component_history_edges':{'core':{'gap_months':1}}},'component'),
    ({'fuel_diagnostics':{'stale':True}},'fuel'),
])
def test_inconsistent_or_stale_result_is_not_prospective(saved,change,message):
    v,root,run,meta,result,seal,now=saved
    result.update(change);write(run/'forecast.json',result);seal()
    with pytest.raises(ValueError,match=message):v.inspect_run(run,mode='prospective',root=root)


def test_fixture_cannot_claim_prospective(saved):
    v,root,run,meta,result,seal,now=saved
    meta['capture_kind']='historical_fixture';write(run/'snapshot.json',meta);seal()
    with pytest.raises(ValueError,match='live'):v.inspect_run(run,mode='prospective',root=root)


def test_replay_allows_completed_after_historical_release(saved,monkeypatch):
    v,root,run,meta,result,seal,now=saved
    actual_now=datetime(2026,9,15,tzinfo=timezone.utc)
    monkeypatch.setattr(v,'_utc_now',lambda:actual_now)
    meta['capture_kind']='historical_fixture';meta['captured_at']=actual_now.isoformat()
    result['completed_at']=actual_now.isoformat();result['prospective_eligible']=False
    result['completed_before_first_release']=False
    write(run/'snapshot.json',meta);write(run/'forecast.json',result);seal()
    assert v.inspect_run(run,mode='replay',root=root)['mode']=='replay'


def test_unsafe_snapshot_name_and_code_drift_fail(saved):
    v,root,run,meta,result,seal,now=saved
    meta['hashes']['../escape.csv']='0'*64;write(run/'snapshot.json',meta);seal()
    with pytest.raises(ValueError,match='path'):v.inspect_run(run,mode='replay',root=root)
    del meta['hashes']['../escape.csv'];write(run/'snapshot.json',meta);seal()
    write(root/'forecast_independent.py','# changed')
    with pytest.raises(ValueError,match='hash'):v.inspect_run(run,mode='replay',root=root)


def test_missing_calendar_and_runtime_drift_fail(saved,monkeypatch):
    v,root,run,meta,result,seal,now=saved
    monkeypatch.setattr(v,'_runtime',lambda:{'fixture':False})
    with pytest.raises(ValueError,match='runtime'):v.inspect_run(run,mode='replay',root=root)
    monkeypatch.setattr(v,'_runtime',lambda:{'fixture':True})
    meta['target']=result['target']='2026-09';write(run/'snapshot.json',meta);write(run/'forecast.json',result);seal()
    with pytest.raises(ValueError,match='calendar'):v.inspect_run(run,mode='replay',root=root)
