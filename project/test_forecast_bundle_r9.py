import pandas as pd
import pytest


def test_snapshot_roundtrip_and_tamper_detection(tmp_path):
    from forecast_independent import save_snapshot, load_snapshot
    frames={'core':pd.DataFrame({'core':[1.,2.]},index=pd.period_range('2026-01',periods=2,freq='M'))}
    meta={'as_of':'2026-03-09T09:00:00+01:00','target':'2026-03'}
    save_snapshot(tmp_path/'run',frames,meta)
    got,metadata=load_snapshot(tmp_path/'run')
    pd.testing.assert_frame_equal(got['core'],frames['core'],check_names=False)
    assert metadata['as_of']==meta['as_of']
    with (tmp_path/'run/core.csv').open('a') as f:f.write('\nmodified')
    with pytest.raises(ValueError,match='hash'):load_snapshot(tmp_path/'run')


def test_clock_requires_timezone_and_converts_to_prague_wall():
    from forecast_independent import decision_clock
    with pytest.raises(ValueError,match='timezone'):decision_clock('2026-07-01 10:00')
    assert decision_clock('2026-07-01T08:00:00Z')==pd.Timestamp('2026-07-01 10:00')


def test_archive_is_append_only(tmp_path):
    from forecast_independent import save_snapshot
    save_snapshot(tmp_path/'run',{}, {'as_of':'2026-09-09T12:00:00Z'})
    with pytest.raises(FileExistsError):save_snapshot(tmp_path/'run',{}, {})


@pytest.mark.parametrize('actual,expected', [({'a':float('nan')},{'a':1.}),
    ({'a':float('inf')},{'a':1.}), ({'a':1.},{'a':1.,'b':2.}),
    ({'a':1.1},{'a':1.})])
def test_replay_rejects_nonfinite_missing_or_changed_points(actual,expected):
    from forecast_independent import verify_points
    with pytest.raises(ValueError):verify_points(actual,expected)


def test_missing_released_component_is_not_ready():
    from forecast_independent import component_edges
    import cz_struct as s
    idx=pd.period_range('2026-05',periods=2,freq='M')
    values={'regulated':pd.Series([.1,float('nan')],index=idx)}
    result=component_edges(values,pd.Period('2026-07'),pd.Timestamp('2026-08-04 23:59'))
    assert result['regulated']['gap_months']==1


def test_source_change_during_calculation_cannot_publish_receipt(tmp_path, monkeypatch):
    import sys
    import forecast_independent as runner
    source=tmp_path/'watched.py'
    source.write_text('original')
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    monkeypatch.setattr(runner,'fixture_frames',lambda:{})
    monkeypatch.setattr(runner,'code_inputs',lambda:{'watched.py':runner._hash(source)})
    monkeypatch.setattr(runner,'runtime_identity',lambda:{'test_runtime':True})
    def changing_calculation(*args):
        source.write_text('changed while calculating')
        return {'points_mm_pct':{'HARD_BASE':.1},'ready_for_first_release':False}
    monkeypatch.setattr(runner,'calculate',changing_calculation)
    monkeypatch.setattr(sys,'argv',['forecast_independent.py','--fixture',
        '--target','2026-07','--as-of','2026-08-04T23:59:00+02:00',
        '--archive-root',str(tmp_path/'runs')])
    with pytest.raises(ValueError,match='code/static input hash mismatch'):
        runner.main()
    assert not list((tmp_path/'runs').glob('*/receipt.json'))
    assert not list((tmp_path/'runs').glob('*/forecast.json'))
