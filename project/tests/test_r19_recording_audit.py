"""Independent recording audit: archive preservation and wall-clock boundaries."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) if isinstance(value, dict) else value, encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def recording(tmp_path, monkeypatch):
    from tools.recording import verified_nowcast as v
    from tools.research_r18 import forecast_archive as a
    root = tmp_path / "repo"
    run = root / "run"
    clock = [datetime(2026, 8, 4, 12, tzinfo=timezone.utc)]
    dump(root / "forecast_independent.py", "# audit engine fixture\n")
    dump(root / "data/release_calendar_cz_cpi.csv", "target_month,first_release_dt,first_release_kind,first_release_source\n2026-07,2026-08-05,flash,czso_release_page\n")
    for name in v.REQUIRED_FRAMES:
        dump(run / (name + ".csv"), "period,value\n2026-06,0.1\n")
    snapshot = dict(target="2026-07", as_of=(clock[0] - timedelta(seconds=119)).isoformat(),
                    captured_at=(clock[0] - timedelta(seconds=119)).isoformat(),
                    capture_kind="live_snapshot", runtime={"audit_fixture": True},
                    hashes={name + ".csv": sha(run / (name + ".csv")) for name in v.REQUIRED_FRAMES},
                    code_and_static_inputs={name: sha(root / name) for name in
                                            ("forecast_independent.py", "data/release_calendar_cz_cpi.csv")})
    forecast = dict(version="independent-r9-2026-09-09", target="2026-07", as_of=snapshot["as_of"],
                    completed_at=(clock[0] - timedelta(seconds=118)).isoformat(),
                    main_model="HARD_BASE", points_mm_pct={"HARD_BASE": .3, "HARD_HALF": .32, "HARD_FULL": .34},
                    main_contributions_pp={"core": .2, "food": .1, "alcohol_tobacco": 0., "administered": 0., "fuel": 0., "wedge": 0.},
                    ready_for_first_release=True, before_first_release=True,
                    completed_before_first_release=True, prospective_eligible=True,
                    component_history_edges={name: {"gap_months": 0} for name in v.COMPONENTS},
                    detailed_CPI_edge_gap=0, fuel_diagnostics={"stale": False}, missing_inputs=[])

    def seal(extras=()):
        dump(run / "snapshot.json", snapshot)
        dump(run / "forecast.json", forecast)
        dump(run / "receipt.json", {name: sha(run / name) for name in
                                   ("snapshot.json", "forecast.json", *extras)})

    seal()
    monkeypatch.setattr(v, "_utc_now", lambda: clock[0])
    monkeypatch.setattr(a, "_utc_now", lambda: clock[0])
    monkeypatch.setattr(v, "_runtime", lambda: {"audit_fixture": True})
    return v, a, root, run, snapshot, forecast, seal, clock, tmp_path / "archive"


def test_bound_copies_survive_original_source_changes(recording):
    v, a, root, run, snapshot, forecast, seal, clock, archive_root = recording
    bundle_dir = v.record_run(run, archive_root, mode="replay", root=root)
    dump(run / "core.csv", "changed after recording\n")
    dump(root / "forecast_independent.py", "changed after recording\n")
    bundle = a.verify_bundle(bundle_dir, verify_artifacts=True)
    assert bundle["point_forecast"] == .3
    assert bundle["path_forecasts"] == []
    assert all(Path(row["path"]).is_relative_to(archive_root / ".sources")
               for rows in bundle["artifacts"].values() for row in rows)


def test_source_change_between_validation_and_copy_is_rejected(recording, monkeypatch):
    v, a, root, run, snapshot, forecast, seal, clock, archive_root = recording
    inspect = v.inspect_run

    def mutate_after_inspect(*args, **kwargs):
        info = inspect(*args, **kwargs)
        dump(run / "core.csv", "changed before recording\n")
        return info

    monkeypatch.setattr(v, "inspect_run", mutate_after_inspect)
    with pytest.raises(ValueError, match="Source hash changed"):
        v.record_run(run, archive_root, mode="prospective", root=root)
    assert not list(archive_root.glob("*/COMMITTED.json"))


def test_staging_delay_over_completion_limit_is_rejected(recording, monkeypatch):
    v, a, root, run, snapshot, forecast, seal, clock, archive_root = recording
    inspect = v.inspect_run

    def advance_after_inspect(*args, **kwargs):
        info = inspect(*args, **kwargs)
        clock[0] += timedelta(seconds=3)
        return info

    monkeypatch.setattr(v, "inspect_run", advance_after_inspect)
    with pytest.raises(ValueError, match="Stale completion"):
        v.record_run(run, archive_root, mode="prospective", root=root)
    assert not list(archive_root.glob("*/COMMITTED.json"))


def test_completion_freshness_is_explicitly_at_handoff(recording, monkeypatch):
    v, a, root, run, snapshot, forecast, seal, clock, archive_root = recording
    collect = a._snapshot_artifacts

    def slow_archive_hash(*args, **kwargs):
        result = collect(*args, **kwargs)
        clock[0] += timedelta(seconds=3)
        return result

    monkeypatch.setattr(a, "_snapshot_artifacts", slow_archive_hash)
    directory = v.record_run(run, archive_root, mode="prospective", root=root)
    bundle = a.verify_bundle(directory, verify_artifacts=True)
    policy = bundle['metadata']['freshness_policy']
    assert policy['completion_age_limit_at_handoff_seconds'] == 120
    assert policy['archive_issue_to_commit_limit_seconds'] == 120
    assert policy['handoff_at_utc'] == (clock[0] - timedelta(seconds=3)).isoformat()


def test_archive_delay_over_its_own_limit_is_rejected(recording, monkeypatch):
    v, a, root, run, snapshot, forecast, seal, clock, archive_root = recording
    collect = a._snapshot_artifacts

    def slow_archive_hash(*args, **kwargs):
        result = collect(*args, **kwargs)
        clock[0] += timedelta(seconds=121)
        return result

    monkeypatch.setattr(a, '_snapshot_artifacts', slow_archive_hash)
    with pytest.raises(ValueError, match='window'):
        v.record_run(run, archive_root, mode='prospective', root=root)
    assert not list(archive_root.glob('*/COMMITTED.json'))


def test_all_verified_receipt_artifacts_are_bound(recording):
    v, a, root, run, snapshot, forecast, seal, clock, archive_root = recording
    dump(run / "path.json", {"paths": {"BRIDGE_HARD": [.3, .4]}})
    dump(run / "path.csv", "model,h,mm_pct\nBRIDGE_HARD,0,0.3\n")
    snapshot["include_path"] = True
    seal(("path.json", "path.csv"))
    bundle_dir = v.record_run(run, archive_root, mode="replay", root=root)
    bundle = a.verify_bundle(bundle_dir, verify_artifacts=True)
    originals = set(bundle["metadata"]["source_path_map"].values())
    assert str((run / "path.json").resolve()) in originals
    assert str((run / "path.csv").resolve()) in originals
    assert bundle["path_forecasts"] == []
    assert bundle["metadata"]["path_status"] == "latest_audited_path_runtime_not_connected"
