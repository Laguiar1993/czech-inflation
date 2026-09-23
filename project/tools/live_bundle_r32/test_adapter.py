"""Focused adapter contracts; all test writes stay in the new adapter directory."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def api():
    assert importlib.util.find_spec('tools.live_bundle_r32.adapter'), 'adapter implementation is missing'
    from tools.live_bundle_r32 import adapter
    return adapter


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def bundle():
    with tempfile.TemporaryDirectory(dir=HERE) as folder:
        root = Path(folder)
        (root / 'nowcast').mkdir()
        (root / 'market').mkdir()
        idx = pd.period_range('2020-01', '2026-09', freq='M')
        features = {'eurczk_mm': 0., 'services_l1': .2, 'import_l2': .1,
                    'core_l1': .1, 'core_l2': .1, 'core_l12': .1, 'state': 0.,
                    'eurczk_mm_x_state': 0., 'import_l2_x_state': 0.}
        features.update({f'mon_{i}': (idx.month == i).astype(float) for i in range(2, 13)})
        names = {'target_headline_cpi_mm': {'cpi_mm': .1}, 'component_food_fuel_mm': {'food': .2, 'fuel': .3},
                 'cnb_core_mm': {'core': .1}, 'cnb_regulated_mm': {'regulated': .1},
                 'alcohol_tobacco': {'alcohol_tobacco': .1}, 'core_features': features,
                 'food_block_features': {c: .1 for c in ['food_l1', 'food_l12', 'food_ppi_l1', 'agri_l0', 'agri_l1']}}
        for name, values in names.items():
            pd.DataFrame(values, index=idx).to_csv(root / 'nowcast' / (name + '.csv'), index_label='period')
        dates = pd.date_range('2019-12-30', '2026-09-21', freq='W-MON')
        pd.DataFrame({'petrol95': 30., 'diesel': 31.}, index=dates).to_csv(root / 'nowcast/fuel_weekly_variant_b.csv', index_label='date')
        fuel = pd.DataFrame({'ticker': 'CP7FCZ Index', 'observation_date': pd.period_range('2019-12', '2026-09', freq='M').to_timestamp('M'), 'value': np.arange(82) + 100.})
        ec = pd.concat([pd.DataFrame({'ticker': ticker, 'observation_date': dates + pd.Timedelta(days=4), 'value': value})
                        for ticker, value in [('ECOBETCZ Index', 30000.), ('ECOBOTCZ Index', 31000.)]])
        fxdates = pd.date_range('2026-08-01', '2026-09-30', freq='B')
        fx = pd.DataFrame({'ticker': 'EURCZK CNB Curncy', 'observation_date': fxdates, 'value': np.where(fxdates.month == 8, 25., 26.)})
        pd.concat([fuel, ec, fx]).to_csv(root / 'market/history_long.csv', index=False)
        seal(root)
        yield root


def seal(root):
    (root / 'MANIFEST.json').write_text(json.dumps({'files': {p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*.csv')}}))


def calendar():
    idx = pd.period_range('2020-01', '2026-09', freq='M')
    return pd.DataFrame({'first_release_dt': (idx + 1).to_timestamp() + pd.Timedelta(days=4, hours=9),
                         'detail_release_dt': (idx + 1).to_timestamp() + pd.Timedelta(days=9, hours=9)}, index=idx)


def test_corrupt_hash_is_rejected_before_frames_are_read(bundle):
    p = bundle / 'nowcast/cnb_core_mm.csv'
    p.write_text(p.read_text() + '\n')
    with pytest.raises(ValueError, match='hash mismatch'):
        api().load_bundle(bundle, ROOT)


def test_required_unhashed_file_is_rejected(bundle):
    p = bundle / 'MANIFEST.json'
    m = json.loads(p.read_text()); del m['files']['nowcast/cnb_core_mm.csv']; p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='not hash-listed'):
        api().load_bundle(bundle, ROOT)


def test_manifest_path_escape_is_rejected(bundle):
    p = bundle / 'MANIFEST.json'
    m = json.loads(p.read_text()); m['files']['../secret.csv'] = '0' * 64; p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='unsafe path'):
        api().load_bundle(bundle, ROOT)


def test_r31c_defaults_and_ec_sources(bundle):
    loaded = api().load_bundle(bundle, ROOT)
    assert 'services_l1' not in loaded.frames['features']
    expected = 100 * (101 / 100 - 1)
    assert loaded.frames['components'].loc['2020-01', 'fuel'] == pytest.approx(expected)
    assert loaded.frames['weekly_fuel'].loc['2026-09-14', 'petrol95'] == 30
    assert loaded.provenance['variant'] == 'R31C_C123'


def test_cp7fcz_gap_cannot_bridge_two_months(bundle):
    p = bundle / 'market/history_long.csv'
    d = pd.read_csv(p); d = d[~(d.ticker.eq('CP7FCZ Index') & d.observation_date.eq('2025-01-31'))]; d.to_csv(p, index=False); seal(bundle)
    with pytest.raises(ValueError, match='CP7FCZ.*coverage'):
        api().load_bundle(bundle, ROOT)


def test_ec_cannot_fall_back_to_czso(bundle):
    p = bundle / 'market/history_long.csv'
    d = pd.read_csv(p); d = d[~d.ticker.eq('ECOBOTCZ Index')]; d.to_csv(p, index=False); seal(bundle)
    with pytest.raises(ValueError, match='ECOBOTCZ'):
        api().load_bundle(bundle, ROOT)


@pytest.mark.parametrize('stamp', ['2026-09-22', 'NaT', '2026-09-22T12:00:00'])
def test_naive_or_invalid_clocks_are_rejected(stamp):
    with pytest.raises(ValueError, match='timezone'):
        api().decision_clock(stamp)


def test_prague_clock_uses_dst():
    a = api()
    assert a.decision_clock('2026-07-01T22:30:00Z') == pd.Timestamp('2026-07-02T00:30')
    assert a.decision_clock('2026-01-01T22:30:00Z') == pd.Timestamp('2026-01-01T23:30')


def test_mtd_excludes_prague_call_day(bundle):
    a = api(); loaded = a.load_bundle(bundle, ROOT)
    loaded.market['EURCZK CNB Curncy'].loc[pd.Timestamp('2026-09-22')] = 500
    frames, info = a.prepare_frames(loaded, pd.Period('2026-09'), a.decision_clock('2026-09-21T22:30Z'), calendar())
    assert frames['gated_mtd_fx'].loc['2026-09', 'eurczk_mm'] == pytest.approx(4.)
    assert info['last_fixing'] == '2026-09-21'
    assert loaded.frames['features'].loc['2026-09', 'eurczk_mm'] == 0.


def test_stale_data_and_unknown_calendar_fail_closed(bundle):
    a = api(); loaded = a.load_bundle(bundle, ROOT); target = pd.Period('2026-09'); clock = a.decision_clock('2026-09-22T12:00+02:00')
    loaded.frames['core'].loc['2026-08'] = np.nan
    loaded.frames['food_features'].loc[target, 'food_ppi_l1'] = np.nan
    loaded.frames['weekly_fuel'] = loaded.frames['weekly_fuel'].loc[:'2026-08-24']
    frames, _ = a.prepare_frames(loaded, target, clock, calendar())
    report = a.readiness(frames, target, clock, calendar().iloc[:-1])
    assert not report['data_ready']
    codes = {r['code'] for r in report['reasons']}
    assert {'missing_release_calendar', 'component_history_gap', 'stale_feature', 'weekly_fuel_gap'} <= codes


def test_not_due_is_distinguished_from_stale(bundle):
    a = api(); loaded = a.load_bundle(bundle, ROOT); t = pd.Period('2026-09'); c = a.decision_clock('2026-09-22T12:00+02:00')
    loaded.frames['food_features'].loc[t, 'agri_l0'] = np.nan
    frames, _ = a.prepare_frames(loaded, t, c, calendar())
    report = a.readiness(frames, t, c, calendar())
    assert report['data_ready']
    assert {'frame': 'food_features', 'column': 'agri_l0', 'status': 'NOT_DUE'} in report['missing_inputs']


def test_release_boundary_is_exclusive(bundle):
    a = api(); loaded = a.load_bundle(bundle, ROOT); t = pd.Period('2026-08')
    r = a.readiness(loaded.frames, t, a.decision_clock('2026-09-05T09:00+02:00'), calendar())
    assert not r['data_ready']
    assert 'first_release_already_reached' in {x['code'] for x in r['reasons']}


def test_live_calendar_is_sourced_gated_and_append_only(bundle):
    a = api(); frozen = bundle / 'frozen.csv'; live = bundle / 'live.csv'
    frozen.write_text('target_month,first_release_dt,detail_release_dt\n2026-08,2026-09-04,2026-09-10\n')
    original = digest(frozen)
    live.write_text('target_month,first_release_dt,detail_release_dt,available_from,source\n2026-09,2026-10-05T09:00+02:00,2026-10-12T09:00+02:00,2026-09-23T09:00+02:00,test fixture\n')
    cal, _ = a.load_calendar(frozen, live, a.decision_clock('2026-09-22T12:00+02:00'))
    assert pd.Period('2026-09') not in cal.index
    cal, _ = a.load_calendar(frozen, live, a.decision_clock('2026-09-24T12:00+02:00'))
    assert cal.loc['2026-09', 'first_release_dt'] == pd.Timestamp('2026-10-05T09:00')
    live.write_text(live.read_text().replace('2026-09,2026-10-05', '2026-08,2026-10-05'))
    with pytest.raises(ValueError, match='frozen calendar'):
        a.load_calendar(frozen, live, a.decision_clock('2026-09-24T12:00+02:00'))
    assert digest(frozen) == original


def test_loader_import_does_not_import_models():
    result = subprocess.run([sys.executable, '-c', "from tools.live_bundle_r32 import adapter; import sys; assert not any(m in sys.modules for m in ('cz_struct','forecast_independent','duckdb','requests','sklearn'))"], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_frozen_bundle_can_be_inspected_without_model_dependencies():
    a = api(); loaded = a.load_bundle(ROOT / 'data/bloomberg_inputs_20260922_foodppi', ROOT)
    t = pd.Period('2026-09'); c = a.decision_clock('2026-09-22T12:00+02:00')
    cal, _ = a.load_calendar(ROOT / 'data/release_calendar_cz_cpi.csv', None, c)
    frames, _ = a.prepare_frames(loaded, t, c, cal)
    report = a.readiness(frames, t, c, cal)
    assert not report['data_ready']
    assert report['component_history_edges']['core']['latest_released_value'] <= '2026-07'


def test_duplicate_months_and_infinite_values_fail_schema(bundle):
    p = bundle / 'nowcast/core_features.csv'
    d = pd.read_csv(p); pd.concat([d, d.iloc[-1:]]).to_csv(p, index=False); seal(bundle)
    with pytest.raises(ValueError, match='duplicate'):
        api().load_bundle(bundle, ROOT)


def test_live_calendar_rows_need_not_arrive_sorted(bundle):
    a = api(); frozen = bundle / 'frozen.csv'; live = bundle / 'live.csv'
    frozen.write_text('target_month,first_release_dt,detail_release_dt\n2026-08,2026-09-04,2026-09-10\n')
    live.write_text('target_month,first_release_dt,detail_release_dt,available_from,source\n2026-10,2026-11-05T09:00+01:00,2026-11-12T09:00+01:00,2026-09-20T12:00+02:00,test fixture\n2026-09,2026-10-05T09:00+02:00,2026-10-12T09:00+02:00,2026-09-20T12:00+02:00,test fixture\n')
    cal, _ = a.load_calendar(frozen, live, a.decision_clock('2026-09-22T12:00+02:00'))
    assert str(cal.index[-1]) == '2026-10'


def test_current_month_without_recent_mtd_fx_is_not_ready(bundle):
    a = api(); loaded = a.load_bundle(bundle, ROOT); t = pd.Period('2026-09'); clock = a.decision_clock('2026-09-22T12:00+02:00')
    loaded.market['EURCZK CNB Curncy'] = loaded.market['EURCZK CNB Curncy'].loc[:'2026-09-01']
    frames, fx = a.prepare_frames(loaded, t, clock, calendar())
    report = a.readiness(frames, t, clock, calendar(), fx=fx)
    assert not report['data_ready']
    assert 'stale_mtd_fx' in {x['code'] for x in report['reasons']}


def test_interior_weekly_gap_is_reported_even_with_fresh_edge(bundle):
    a = api(); loaded = a.load_bundle(bundle, ROOT); t = pd.Period('2026-09'); c = a.decision_clock('2026-09-22T12:00+02:00')
    loaded.frames['weekly_fuel'] = loaded.frames['weekly_fuel'].drop(pd.Timestamp('2026-08-17'))
    r = a.readiness(loaded.frames, t, c, calendar())
    assert not r['data_ready']
    assert any(x['code'] == 'weekly_fuel_gap' and '2026-08-17' in x['missing_observation_dates'] for x in r['reasons'])


def test_published_but_empty_state_is_stale(bundle):
    a = api(); loaded = a.load_bundle(bundle, ROOT); t = pd.Period('2026-09'); c = a.decision_clock('2026-09-22T12:00+02:00')
    loaded.frames['features'].loc[t, 'state'] = np.nan
    r = a.readiness(loaded.frames, t, c, calendar())
    assert any(x.get('column') == 'state' and x['code'] == 'stale_feature' for x in r['reasons'])


@pytest.mark.parametrize('command', ['inspect', 'readiness', 'run'])
def test_cli_inspection_returns_json_without_model_imports(command):
    code = f"from tools.live_bundle_r32.cli import main; import sys; rc=main(['{command}','--bundle','data/bloomberg_inputs_20260922_foodppi','--target','2026-09','--as-of','2026-09-22T12:00+02:00']); assert rc == 2; assert 'cz_struct' not in sys.modules"
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report['status'] == 'blocked'
    assert report['forecast_available'] is False
    assert 'points_mm_pct' not in report
    assert report['readiness']['component_history_edges']['core']['latest_released_value'] == '2026-07'


def test_cli_missing_clock_is_json_error():
    r = subprocess.run([sys.executable, '-m', 'tools.live_bundle_r32', 'inspect', '--bundle', 'data/bloomberg_inputs_20260922_foodppi', '--target', '2026-09'], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 2
    assert json.loads(r.stdout)['reasons'][0]['code'] == 'invalid_arguments'


def test_run_blocks_missing_dependencies_before_import(bundle, monkeypatch):
    from tools.live_bundle_r32 import runner
    monkeypatch.setattr(runner, 'runtime_readiness', lambda: {'ready': False, 'reasons': [{'code': 'missing_dependency', 'package': 'duckdb'}]})
    with pytest.raises(RuntimeError, match='duckdb'):
        runner.calculate({}, pd.Period('2026-09'), '2026-09-22T12:00+02:00', calendar())
    assert 'cz_struct' not in sys.modules


def test_calendar_scope_restores_state_after_error():
    from tools.live_bundle_r32 import runner
    from types import SimpleNamespace
    old = pd.DataFrame({'sentinel': [1]}); model = SimpleNamespace(_CAL=old)
    with pytest.raises(RuntimeError, match='test failure'):
        with runner.calendar_scope(model, calendar()):
            assert model._CAL is not old
            raise RuntimeError('test failure')
    assert model._CAL is old


def test_runtime_check_does_not_import_optional_packages():
    code = "from tools.live_bundle_r32.runner import runtime_readiness; import sys,json; print(json.dumps(runtime_readiness())); assert not any(m in sys.modules for m in ('duckdb','requests','cz_struct','sklearn'))"
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert isinstance(report['ready'], bool)


def test_mtd_readiness_cannot_be_bypassed_by_omitting_fx_metadata(bundle):
    a = api(); loaded = a.load_bundle(bundle, ROOT); t = pd.Period('2026-09'); c = a.decision_clock('2026-09-22T12:00+02:00')
    loaded.market.pop('EURCZK CNB Curncy')
    frames, _ = a.prepare_frames(loaded, t, c, calendar())
    r = a.readiness(frames, t, c, calendar())
    assert not r['data_ready']
    assert 'stale_mtd_fx' in {x['code'] for x in r['reasons']}


def test_timezone_stamped_market_dates_are_rejected(bundle):
    p = bundle / 'market/history_long.csv'
    d = pd.read_csv(p); d['observation_date'] += 'T00:00:00Z'; d.to_csv(p, index=False); seal(bundle)
    with pytest.raises(ValueError, match='observation dates'):
        api().load_bundle(bundle, ROOT)


def test_recorded_input_identity_matches_r31c_manifest():
    a = api(); loaded = a.load_bundle(ROOT / 'data/bloomberg_inputs_20260922_foodppi', ROOT)
    archived = json.loads((ROOT / 'output/bloomberg_lane_20260922_r31c/manifest.json').read_text())
    assert loaded.provenance['bundle_manifest_sha256'] == archived['bundle_manifest']
    snapshots = {Path(k).parent.name: v for k, v in loaded.provenance['snapshot_hashes'].items()}
    assert snapshots == archived['snapshots']
    for name, digest_ in archived['outputs'].items():
        assert digest(ROOT / 'output/bloomberg_lane_20260922_r31c' / name) == digest_
    c = a.decision_clock('2026-08-04T23:59:00+02:00'); t = pd.Period('2026-07')
    cal, _ = a.load_calendar(ROOT / 'data/release_calendar_cz_cpi.csv', None, c)
    frames, fx = a.prepare_frames(loaded, t, c, cal)
    assert a.readiness(frames, t, c, cal, fx=fx)['data_ready']
    assert fx['status'] == 'not_needed'
    pd.testing.assert_frame_equal(frames['features'], loaded.frames['features'])


def test_recorded_r31c_numerical_parity_when_real_runtime_available():
    from tools.live_bundle_r32 import runner
    runtime = runner.runtime_readiness()
    if not runtime['ready']:
        pytest.skip('Numerical parity blocked by real runtime dependencies: ' + ', '.join(r.get('package', r['code']) for r in runtime['reasons']))
    a = api(); loaded = a.load_bundle(ROOT / 'data/bloomberg_inputs_20260922_foodppi', ROOT)
    stamp = '2026-08-04T23:59:00+02:00'; t = pd.Period('2026-07'); c = a.decision_clock(stamp)
    cal, _ = a.load_calendar(ROOT / 'data/release_calendar_cz_cpi.csv', None, c)
    frames, _ = a.prepare_frames(loaded, t, c, cal)
    result = runner.calculate(frames, t, stamp, cal)
    expected = pd.read_csv(ROOT / 'output/bloomberg_lane_20260922_r31c/run_C123.csv', index_col='period').loc['2026-07']
    for name in ('HARD_BASE', 'HARD_HALF', 'HARD_FULL'):
        assert result['points_mm_pct'][name] == pytest.approx(expected[name], abs=1e-10, rel=0)
    for name, value in result['main_contributions_pp'].items():
        assert value == pytest.approx(expected['contrib_' + name], abs=1e-10, rel=0)


@pytest.mark.parametrize('gap', ['missing_prefix', 'interior_gap'])
def test_mtd_rejects_incomplete_current_month_despite_recent_fixing(bundle, gap):
    a = api()
    loaded = a.load_bundle(bundle, ROOT)
    target = pd.Period('2026-09')
    clock = a.decision_clock('2026-09-22T12:00+02:00')
    cal = calendar()
    complete, info = a.prepare_frames(loaded, target, clock, cal)
    assert info['status'] == 'applied'
    assert a.readiness(complete, target, clock, cal, fx=info)['data_ready']

    daily = loaded.market['EURCZK CNB Curncy']
    in_current_month = daily.index.to_period('M') == target
    if gap == 'missing_prefix':
        keep_current = daily.index >= pd.Timestamp('2026-09-21')
    else:
        keep_current = ((daily.index <= pd.Timestamp('2026-09-03'))
                        | (daily.index >= pd.Timestamp('2026-09-14')))
    loaded.market['EURCZK CNB Curncy'] = daily[~in_current_month | keep_current]
    frames, info = a.prepare_frames(loaded, target, clock, cal)
    assert info['last_fixing'] == '2026-09-21'  # recency alone still passes
    assert info['status'] == 'unavailable'
    assert 'seven-calendar-day' in info['reason']
    assert 'gated_mtd_fx' not in frames
    assert pd.isna(frames['features'].loc[target, 'eurczk_mm'])
    report = a.readiness(frames, target, clock, cal, fx=info)
    assert not report['data_ready']
    assert 'stale_mtd_fx' in {r['code'] for r in report['reasons']}
