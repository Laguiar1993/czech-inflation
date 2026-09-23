"""Forecast archive contract; all successful bundles contain synthetic fixtures."""
import importlib.util
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

MODULE = Path(__file__).resolve().parents[1] / "tools/research_r18/forecast_archive.py"
NOW = datetime(2030, 2, 8, 12, 0, tzinfo=timezone.utc)


def load_module():
    assert MODULE.exists(), "Archive implementation has not been created"
    spec = importlib.util.spec_from_file_location("forecast_archive_test", MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_archive_api_exists():
    module = load_module()
    assert callable(module.archive_forecast) and callable(module.verify_bundle)


@pytest.fixture
def setup_case(tmp_path, monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "_utc_now", lambda: NOW)
    files = {}
    for name, content in {"model.py": "# synthetic fixture\n", "input.csv": "x\n1\n", "sources.json": '{"fixture":true}'}.items():
        path = tmp_path / name
        path.write_text(content)
        files[name] = path
    artifacts = {"model_code": [files["model.py"]], "inputs": [files["input.csv"]], "source_manifests": [files["sources.json"]]}
    availability = {str(path): {"available_from": "2030-02-07T09:00:00Z", "reference_period": "2029-12", "note": "synthetic fixture"}
                    for path in [files["input.csv"], files["sources.json"]]}
    kwargs = dict(mode="prospective", issued_at="2030-02-08T11:59:30Z", target_origin="2030-01",
                  target_first_release_at="2030-02-09T08:00:00Z", model="synthetic_fixture_model",
                  point_forecast=.4, path_forecasts=[{"target_month": "2030-01", "point": .4}, {"target_month": "2030-02", "point": .2}],
                  artifact_paths=artifacts, data_availability=availability)
    return module, tmp_path / "archive", kwargs, files


def test_prospective_fixture_commits_hashes_and_remains_readable_later(setup_case, monkeypatch):
    module, archive, args, files = setup_case
    path = module.archive_forecast(archive, **args)
    result = module.verify_bundle(path, verify_artifacts=True)
    assert result["mode"] == "prospective" and result["archived_at_utc"] == "2030-02-08T12:00:00Z"
    assert result["point_forecast"] == .4 and len(result["artifacts"]["inputs"][0]["sha256"]) == 64
    monkeypatch.setattr(module, "_utc_now", lambda: datetime(2031,1,1,tzinfo=timezone.utc))
    assert module.verify_bundle(path)["mode"] == "prospective"
    assert {p.name for p in path.iterdir()} == {"bundle.json", "COMMITTED.json"}


def test_replay_is_explicit_and_cannot_pass_as_prospective(setup_case):
    module, archive, args, _ = setup_case
    args["issued_at"] = "2030-02-07T12:00:00Z"
    with pytest.raises(ValueError, match="now window"):
        module.archive_forecast(archive, **args)
    assert not archive.exists()
    args["mode"] = "replay"
    bundle = module.archive_forecast(archive, **args)
    assert module.verify_bundle(bundle)["mode"] == "replay"
    assert module.verify_bundle(bundle)["issued_at_utc"] == "2030-02-07T12:00:00Z"


def test_collision_never_changes_existing_bundle(setup_case):
    module, archive, args, _ = setup_case
    identifier = str(uuid4())
    bundle = module.archive_forecast(archive, bundle_id=identifier, **args)
    before = {p.name: p.read_bytes() for p in bundle.iterdir()}
    args["point_forecast"] = .9
    with pytest.raises(FileExistsError):
        module.archive_forecast(archive, bundle_id=identifier, **args)
    assert before == {p.name: p.read_bytes() for p in bundle.iterdir()}


def test_payload_and_source_artifact_tamper_detected(setup_case):
    module, archive, args, files = setup_case
    bundle = module.archive_forecast(archive, **args)
    files["input.csv"].write_text("x\n999\n")
    assert module.verify_bundle(bundle)["point_forecast"] == .4
    with pytest.raises(ValueError, match="artifact"):
        module.verify_bundle(bundle, verify_artifacts=True)
    document = json.loads((bundle / "bundle.json").read_text())
    document["point_forecast"] = 999
    (bundle / "bundle.json").write_text(json.dumps(document))
    with pytest.raises(ValueError, match="integrity"):
        module.verify_bundle(bundle)


@pytest.mark.parametrize("field,value,match", [
    ("issued_at", "2030-02-08T11:57:59Z", "now window"),
    ("issued_at", "2030-02-08T12:00:01Z", "future"),
    ("issued_at", "2030-02-08 12:00:00", "timezone"),
    ("target_first_release_at", "2030-02-08T11:59:30Z", "first release"),
    ("target_first_release_at", "2030-02-08T11:59:29Z", "first release"),
    ("target_first_release_at", "2030-02-08T11:59:45Z", "first release"),
    ("mode", "historical_prospective", "mode"),
    ("point_forecast", float("nan"), "finite"),
])
def test_ineligible_archive_refused_before_directory_creation(setup_case, field, value, match):
    module, archive, args, _ = setup_case
    args[field] = value
    with pytest.raises(ValueError, match=match):
        module.archive_forecast(archive, **args)
    assert not archive.exists()


def test_future_or_missing_source_availability_refused(setup_case):
    module, archive, args, files = setup_case
    args["data_availability"][str(files["input.csv"])]["available_from"] = "2030-02-08T12:00:00Z"
    with pytest.raises(ValueError, match="source availability"):
        module.archive_forecast(archive, **args)
    args["data_availability"] = {}
    with pytest.raises(ValueError, match="availability"):
        module.archive_forecast(archive, **args)
    assert not archive.exists()


def test_path_duplicate_or_earlier_month_refused(setup_case):
    module, archive, args, _ = setup_case
    args["path_forecasts"] = [{"target_month":"2030-01","point":.4}, {"target_month":"2030-01","point":.3}]
    with pytest.raises(ValueError, match="chronological"):
        module.archive_forecast(archive, **args)
    args["path_forecasts"] = [{"target_month":"2029-12","point":.4}]
    with pytest.raises(ValueError, match="origin"):
        module.archive_forecast(archive, **args)


def test_uncommitted_directory_is_rejected_and_cannot_be_reused(setup_case):
    module, archive, args, _ = setup_case
    identifier = str(uuid4())
    reserved = archive / identifier
    reserved.mkdir(parents=True)
    (reserved / "bundle.json").write_text("{}")
    with pytest.raises(ValueError, match="Uncommitted"):
        module.verify_bundle(reserved)
    with pytest.raises(FileExistsError):
        module.archive_forecast(archive, bundle_id=identifier, **args)


def test_clock_rechecked_after_input_hashing(setup_case, monkeypatch):
    module, archive, args, _ = setup_case
    clocks = iter([NOW, datetime(2030, 2, 8, 12, 3, tzinfo=timezone.utc)])
    monkeypatch.setattr(module, "_utc_now", lambda: next(clocks))
    with pytest.raises(ValueError, match="now window"):
        module.archive_forecast(archive, **args)
    assert not archive.exists()


def test_clock_rechecked_before_atomic_commit(setup_case, monkeypatch):
    module, archive, args, _ = setup_case
    clocks = iter([NOW, NOW, NOW, datetime(2030, 2, 8, 12, 3, tzinfo=timezone.utc)])
    monkeypatch.setattr(module, "_utc_now", lambda: next(clocks))
    with pytest.raises(ValueError, match="now window"):
        module.archive_forecast(archive, **args)
    folders = list(archive.iterdir())
    assert len(folders) == 1
    with pytest.raises(ValueError, match="Uncommitted"):
        module.verify_bundle(folders[0])


def test_structurally_invalid_sealed_record_refused(setup_case):
    module, archive, args, _ = setup_case
    bundle = module.archive_forecast(archive, **args)
    document = json.loads((bundle / "bundle.json").read_text())
    document["path_forecasts"] = [{"target_month":"2030-01","point":.4}, {"target_month":"2030-01","point":.3}]
    content = json.dumps(document).encode()
    (bundle / "bundle.json").write_bytes(content)
    seal = json.loads((bundle / "COMMITTED.json").read_text())
    seal.update(bundle_bytes=len(content), bundle_sha256=hashlib.sha256(content).hexdigest())
    (bundle / "COMMITTED.json").write_text(json.dumps(seal))
    with pytest.raises(ValueError, match="chronological"):
        module.verify_bundle(bundle)
