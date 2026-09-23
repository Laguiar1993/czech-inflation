"""Regression examples from the 14 September scoring and artifact review."""
import json
import hashlib
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from tools.cnb_rounds import build_cnb_rounds as rounds


@pytest.fixture
def scored_nowcasts(tmp_path, monkeypatch):
    import independent_nowcast_experiment as nowcast
    (tmp_path / "data").mkdir()
    periods = ["2022-10", "2024-01", "2024-02", "2024-03"]
    pd.DataFrame(dict(target_month=periods, actual=[-1.4, .6, .6, .1],
                      survey_median=[.9, .2, .2, 0.0], era="regular")).to_csv(
        tmp_path / "data/czcpmom_survey_history_extended.csv", index=False)
    monkeypatch.setattr(nowcast, "ROOT", tmp_path)
    monkeypatch.setattr(nowcast, "OUT", tmp_path)
    predictions = pd.DataFrame({m: [1.173, .4, .35, .3] for m in
        ("HARD_BASE", "HARD_HALF", "HARD_FULL", "SENTIMENT_BASE")},
        index=pd.PeriodIndex(periods, freq="M"))
    board, _ = nowcast.score_forecasts(predictions)
    return board, pd.read_csv(tmp_path / "independent_nowcast_releases.csv")


def test_wrong_way_october_alert_retains_magnitude_only_hit(scored_nowcasts):
    board, events = scored_nowcasts
    event = events[(events.model == "HARD_BASE") & (events.period == "2022-10")].iloc[0]
    assert event.big and event.alert
    assert not event.directional_big_hit
    assert event.wrong_way_big_alert
    assert not event.material_big_hit
    assert event.gain == pytest.approx(-.273)
    all_rows = board[(board.model == "HARD_BASE") & (board.frame == "all")].iloc[0]
    assert all_rows.alerted_big == 2
    assert all_rows.false_alarm == 1
    assert all_rows.directional_big_hit == 1
    assert all_rows.wrong_way_big_alert == 1
    assert all_rows.material_big_hit == 1
    assert all_rows.directional_big_precision == pytest.approx(1 / 3)
    assert all_rows.material_big_precision == pytest.approx(1 / 3)


def test_float_boundary_is_a_large_surprise(scored_nowcasts):
    _, events = scored_nowcasts
    event = events[(events.model == "HARD_BASE") & (events.period == "2024-01")].iloc[0]
    assert .6 - .2 < .4
    assert event.big and event.alert and event.material_big_hit


def test_review_uses_shared_large_surprise_threshold():
    source = (Path(__file__).resolve().parents[1] / "tools/review/nowcast_vs_consensus_20260914.py").read_text()
    assert "is_big_surprise(" in source
    assert "abs() >= 0.4" not in source


def test_offline_scoring_import_does_not_load_live_data_dependencies():
    result = subprocess.run([sys.executable, "-c", "import sys; sys.modules['requests'] = None; import independent_nowcast_experiment"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_saved_nowcast_rescoring_preserves_original_metrics_and_files(tmp_path):
    import independent_nowcast_experiment as nowcast
    files = [nowcast.OUT / f"independent_nowcast_{suffix}" for suffix in (
        "forecasts.csv", "scores.csv", "releases.csv", "bootstrap.csv", "selection.json")]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    predictions = pd.read_csv(files[0], index_col="period", float_precision="round_trip")
    predictions.index = pd.PeriodIndex(predictions.index, freq="M")
    nowcast.score_forecasts(predictions, output_dir=tmp_path / "scores")
    for old_path in files[1:4]:
        old = pd.read_csv(old_path, float_precision="round_trip")
        new = pd.read_csv(tmp_path / "scores" / old_path.name, float_precision="round_trip")
        pd.testing.assert_frame_equal(old, new[old.columns], check_exact=False, atol=1e-12, rtol=0)
    assert json.loads(files[-1].read_text()) == json.loads((tmp_path / "scores" / files[-1].name).read_text())
    assert before == {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


@pytest.mark.parametrize("options", [[], ["--output-dir", "output"]])
def test_score_only_cli_rejects_original_output_directory(options):
    result = subprocess.run([sys.executable, "independent_nowcast_experiment.py", "--score-only",
        "output/independent_nowcast_forecasts.csv", *options], capture_output=True, text=True)
    assert result.returncode == 2
    assert "separate --output-dir" in result.stderr


def test_template_labels_simulated_historical_clock():
    source = rounds.TEMPLATE.read_text(encoding="utf-8")
    assert "simulated cutoff" in source.lower()
    assert "last run before the report came out" not in source
    assert "run, made" not in source
    assert "current-vintage" in source


@pytest.fixture
def artifact_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(rounds, "REPO", tmp_path)
    monkeypatch.setattr(rounds, "OUTPUT", tmp_path / "original.html")
    monkeypatch.setattr(rounds, "LATEST_RELEASES", {})
    monkeypatch.setattr(rounds, "SERIES", [
        dict(id="realised", kind="realised"), dict(id="cnb", kind="cnb"),
        dict(id="BRIDGE", kind="model", source="board"),
        dict(id="F1b", kind="model", source="step2", column="F1b"),
        dict(id="FOREST", kind="model", source="forest", run_model="QRF_MEAN"),
    ])
    for dirname in ("output/research_r14b/integration", "data"):
        (tmp_path / dirname).mkdir(parents=True)
    periods = pd.period_range("2022-01", "2024-12", freq="M").astype(str)
    pd.DataFrame(dict(period=periods, headline_mm=0.0)).to_csv(
        tmp_path / "output/independent_path_frozen_inputs.csv", index=False)
    pd.DataFrame(dict(period=["2024-01"], HARD_BASE=[0.0])).to_csv(
        tmp_path / "output/independent_nowcast_forecasts.csv", index=False)
    board = pd.DataFrame(dict(model="BRIDGE", origin="2024-01", h=range(13),
        target=pd.period_range("2024-01", periods=13, freq="M").astype(str),
        as_of_utc="2024-02-01T22:59:00+00:00", yy_exante=[1.00049, 1.00049, 1.00149] + [1.0] * 10))
    board.to_csv(tmp_path / "output/research_r14b/integration/forecasts.csv", index=False)
    pd.DataFrame(dict(origin="2024-01", h=range(1, 13),
        target=pd.period_range("2024-02", periods=12, freq="M").astype(str),
        yy_a_F1b=np.nan, yy_a_F2_D1_fixed=np.nan, yy_b_F1b=99.0,
        yy_b_F2_D1_fixed=99.0)).to_csv(tmp_path / "output/path_step2.csv", index=False)
    pd.DataFrame(dict(report_date=["2024-02-08"], cutoff_date=["2024-01-26"], season=["winter"],
        vintage_year=[2024], is_forecast=[True], quarter=["2024Q1"], value=[2.0])).to_csv(
        tmp_path / "data/cnb_mpr_cpi_quarterly.csv", index=False)
    forest_run = tmp_path / "forest.csv"
    pd.DataFrame(dict(model="QRF_MEAN", edge="2023-12", horizon=range(1, 14), forecast=0.0,
        target_period=pd.period_range("2024-01", periods=13, freq="M").astype(str))).to_csv(forest_run, index=False)
    forest_board = board.assign(model="FOREST", yy_exante=0.0)
    forest_board_path = tmp_path / "forest_board.csv"
    forest_board.to_csv(forest_board_path, index=False)
    monkeypatch.setattr(rounds, "FOREST_RUNS", [forest_run])
    monkeypatch.setattr(rounds, "FOREST_BOARD", forest_board_path)
    return tmp_path, board


def artifact_payload(path):
    html = path.read_text(encoding="utf-8")
    return json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])


def test_artifact_does_not_substitute_realised_month_zero(artifact_inputs):
    root, _ = artifact_inputs
    rounds.main()
    payload = artifact_payload(root / "original.html")
    assert payload["f_object"] == "a"
    assert "F1b" not in payload["reports"][0]["paths"]
    assert payload["reports"][0]["score"]["mae"].get("F1b") is None


def test_artifact_scores_unrounded_forecasts(artifact_inputs):
    root, _ = artifact_inputs
    rounds.main()
    score = artifact_payload(root / "original.html")["reports"][0]["score"]
    assert score["mae"]["BRIDGE"] == pytest.approx(1.001)


def test_artifact_output_override_preserves_original(artifact_inputs):
    root, _ = artifact_inputs
    original = root / "original.html"
    original.write_text("original archived artifact")
    destination = root / "corrected/page.html"
    rounds.main(output=destination)
    assert original.read_text() == "original archived artifact"
    assert artifact_payload(destination)["f_object"] == "a"


@pytest.mark.parametrize("defect", ["duplicate", "clock"])
def test_artifact_rejects_ambiguous_board(artifact_inputs, defect):
    root, board = artifact_inputs
    if defect == "duplicate":
        board = pd.concat([board, board.iloc[[0]]], ignore_index=True)
    else:
        board.loc[1, "as_of_utc"] = "2024-02-02T22:59:00+00:00"
    board.to_csv(root / "output/research_r14b/integration/forecasts.csv", index=False)
    with pytest.raises(ValueError, match="duplicate|clock"):
        rounds.main()


@pytest.mark.parametrize("defect", ["missing", "mismatch", "empty", "duplicate"])
def test_forest_reconciliation_fails_closed(artifact_inputs, defect):
    _, _ = artifact_inputs
    board = pd.read_csv(rounds.FOREST_BOARD)
    if defect == "missing":
        board.loc[0, "target"] = "2099-01"
    elif defect == "mismatch":
        board.loc[0, "yy_exante"] = 2e-10
    elif defect == "empty":
        board = board.iloc[:0]
    else:
        board = pd.concat([board, board.iloc[[0]]], ignore_index=True)
    board.to_csv(rounds.FOREST_BOARD, index=False)
    with pytest.raises(ValueError, match="forest|duplicate"):
        rounds.main()


def test_forest_run_rejects_duplicate_model_edge_horizon(artifact_inputs):
    run = pd.read_csv(rounds.FOREST_RUNS[0])
    pd.concat([run, run.iloc[[0]]], ignore_index=True).to_csv(rounds.FOREST_RUNS[0], index=False)
    with pytest.raises(ValueError, match="duplicate"):
        rounds.main()
