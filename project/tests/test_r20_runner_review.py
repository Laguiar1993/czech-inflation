"""Independent review regressions for the R20 capture boundary."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest


@pytest.mark.parametrize('missing', ['value', 'availability'])
def test_freshness_requires_both_endpoints_of_latest_food_rate(missing):
    from tools.current_path.run import input_freshness

    index = pd.period_range('2026-04', '2026-06', freq='M')
    levels = pd.DataFrame({col: [1., 2., 3.] for col in ('agri4', 'food_ppi', 'food')}, index=index)
    available = pd.DataFrame({
        'agri4': ['2026-05-26', '2026-06-26', '2026-07-26'],
        'food_ppi': ['2026-05-20', '2026-06-16', '2026-07-17'],
        'food': ['2026-05-12', '2026-06-10', '2026-07-10'],
    }, index=index)
    if missing == 'value':
        levels.loc['2026-05', 'food'] = np.nan
    else:
        available.loc['2026-05', 'food'] = None

    report = input_freshness(levels, available, '2026-07', '2026-08-04T12:00:00Z')
    assert not report['ready'], 'June food level cannot supply a released June rate without its May endpoint'


def test_path_manifest_hash_binds_the_bytes_that_are_parsed(tmp_path, monkeypatch):
    from tools.current_path import run

    levels_path = tmp_path / 'pipeline_log_levels.csv'
    original_levels = 'period,agri4,food_ppi,food\n2026-06,10,20,30\n'
    levels_path.write_text(original_levels)
    (tmp_path / 'pipeline_available_from.csv').write_text(
        'period,agri4,food_ppi,food\n2026-06,2026-07-26,2026-07-17,2026-07-10\n')
    (tmp_path / 'pump_weekly.csv').write_text(
        'period,gross_petrol95,gross_diesel,net_petrol95,net_diesel\n2026-07-27,40,38,20,19\n')
    manifest = dict(schema=1, units=run.PATH_UNITS, source_notes='review fixture',
                    files={name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
                           for name in run.PATH_FILES})
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    original_read_csv = pd.read_csv
    replaced = False

    def replace_source_before_first_parse(*args, **kwargs):
        nonlocal replaced
        if not replaced:
            levels_path.write_text(original_levels.replace(',10,', ',999,'))
            replaced = True
        return original_read_csv(*args, **kwargs)

    monkeypatch.setattr(pd, 'read_csv', replace_source_before_first_parse)
    try:
        levels, _, _, _ = run.load_path_inputs(tmp_path)
    except ValueError as exc:
        assert any(word in str(exc).lower() for word in ('hash', 'chang', 'mutat'))
    else:
        assert levels.loc['2026-06', 'agri4'] == 10., 'Accepted data differ from the declared input hash'


def test_snapshot_folder_is_never_overwritten(tmp_path):
    import forecast_independent as old

    destination = tmp_path / 'immutable'
    frame = pd.DataFrame({'value': [1.]}, index=pd.period_range('2026-01', periods=1, freq='M'))
    old.save_snapshot(destination, {'example': frame}, {})
    original = (destination / 'example.csv').read_bytes()
    with pytest.raises(FileExistsError):
        old.save_snapshot(destination, {'example': frame * 2}, {})
    assert (destination / 'example.csv').read_bytes() == original


def test_snapshot_rejects_runtime_mismatch(tmp_path, monkeypatch):
    import forecast_independent as old

    destination = tmp_path / 'runtime'
    old.save_snapshot(destination, {}, {'runtime': {'python': 'archived'}})
    monkeypatch.setattr(old, 'runtime_identity', lambda: {'python': 'different'})
    with pytest.raises(ValueError, match='runtime'):
        old.load_snapshot(destination)


def test_snapshot_rejects_mutated_frame_bytes(tmp_path):
    import forecast_independent as old

    destination = tmp_path / 'frame'
    frame = pd.DataFrame({'value': [1.]}, index=pd.period_range('2026-01', periods=1, freq='M'))
    old.save_snapshot(destination, {'example': frame}, {})
    (destination / 'example.csv').write_text('period,value\n2026-01,999\n')
    with pytest.raises(ValueError, match='hash'):
        old.load_snapshot(destination)


@pytest.mark.parametrize('field,value', [
    ('completed_at', 'NaT'),
    ('completed_at', '2026-09-03T11:59:00+00:00'),
    ('completed_at', '2026-09-03T11:59:45'),
    ('completed_at', '2026-09-03T12:01:00+00:00'),
    ('captured_at', 'NaT'),
    ('captured_at', '2026-09-03T11:59:30'),
    ('as_of', '2026-09-03T11:59:00+00:00'),
    ('valid_prospective', None),
    ('valid_replay', None),
])
def test_record_requires_valid_completion_timeline(tmp_path, monkeypatch, field, value):
    from tools.current_path import record
    import forecast_independent as old

    run = tmp_path / 'capture'
    run.mkdir()
    clock = pd.Timestamp('2026-09-03T12:00:00+00:00')
    as_of = '2026-09-03T11:59:30+00:00'
    runtime = {'review_fixture': True}
    meta = dict(path_engine='current-path-r20', target='2026-08', as_of=as_of,
                captured_at=as_of, capture_kind='live_snapshot', runtime=runtime,
                hashes={}, frame_schema={}, code_and_static_inputs={})
    point = dict(target='2026-08', main_model='HARD_BASE', as_of=as_of,
                 points_mm_pct={'HARD_BASE': .2}, completed_at='2026-09-03T11:59:45+00:00')
    if field == 'completed_at':
        point[field] = value
    elif field in ('captured_at', 'as_of'):
        meta[field] = value
    if field == 'as_of':
        as_of = point['as_of'] = value
    if field == 'valid_replay':
        meta['capture_kind'] = 'historical_fixture'
        as_of = meta['as_of'] = point['as_of'] = '2026-09-03T11:59:00+00:00'
    ready = dict(prospective_eligible=True, at_decision={'ready_at_decision': True})
    for name, value in [('snapshot.json', meta), ('forecast.json', point),
                        ('readiness.json', ready), ('path.json', {})]:
        (run / name).write_text(json.dumps(value))
    rows = [dict(model=model, h=h, origin=meta['target'],
                 target=str(pd.Period(meta['target'], 'M') + h),
                 as_of_utc=as_of, mm_forecast=.2, yy_exante=2.,
                 **{'contribution_' + block: .2 / len(record.BLOCKS) for block in record.BLOCKS})
            for model in record.MODELS for h in range(13)]
    pd.DataFrame(rows).to_csv(run / 'path.csv', index=False)
    required = ('snapshot.json', 'forecast.json', 'readiness.json', 'path.json', 'path.csv')
    (run / 'receipt.json').write_text(json.dumps({name: record.sha(run / name) for name in required}))
    monkeypatch.setattr(old, 'runtime_identity', lambda: runtime)
    monkeypatch.setattr(record, 'now', lambda: clock.to_pydatetime())
    # The test isolates the pre-archive handoff validation; no archive is written.
    monkeypatch.setattr(record.archive, 'archive_forecast', lambda *args, **kwargs: tmp_path / 'bundle')
    monkeypatch.setattr(record.archive, 'verify_bundle', lambda *args, **kwargs: None)

    if field.startswith('valid_'):
        mode = field.removeprefix('valid_')
        assert len(record.record_capture(run, tmp_path / 'archive', mode)) == 3
    else:
        with pytest.raises(ValueError, match='(?i)completion|timestamp|clock|time'):
            record.record_capture(run, tmp_path / 'archive', 'prospective')
