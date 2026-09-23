"""Contract, adversarial output, and real installed-X13 tests (no source fetches)."""
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

try:
    from tools.momentum_r35 import seasonal
except ImportError:
    seasonal = None


def test_wrapper_is_available():
    assert seasonal is not None, "R35 seasonal wrapper has not been implemented"


@pytest.fixture
def api():
    assert seasonal is not None, "R35 seasonal wrapper has not been implemented"
    return seasonal


def sample(season=True, noise=True):
    t = np.arange(180)
    irregular = np.random.default_rng(173).normal(0, .0005, len(t)) if noise else 0
    y = 100 * np.exp(.002*t + irregular + (.08*np.sin(2*np.pi*t/12) if season else 0))
    return pd.Series(y, pd.period_range(end="2026-08", periods=len(t), freq="M"), name="input")


def assert_unavailable(sa, diagnostic, original):
    assert diagnostic["status"] == "unavailable"
    assert diagnostic["reason"]
    assert diagnostic["quality_flags"]
    assert sa.isna().all()
    if isinstance(original, pd.Series):
        assert sa.index.equals(original.index)


@pytest.mark.parametrize("defect", ["short", "gap", "duplicate", "reverse", "zero", "negative", "nan", "infinite", "datetime", "quarterly", "complex", "strings"])
def test_rejects_invalid_inputs_without_running_x13(api, tmp_path, monkeypatch, defect):
    s = sample()
    if defect == "short": s = s.iloc[:95]
    elif defect == "gap": s = s.drop(s.index[20])
    elif defect == "duplicate": s.index = s.index[:20].append(s.index[19:-1])
    elif defect == "reverse": s = s.iloc[::-1]
    elif defect in {"zero", "negative", "nan", "infinite"}: s.iloc[20] = {"zero": 0, "negative": -1, "nan": np.nan, "infinite": np.inf}[defect]
    elif defect == "datetime": s.index = s.index.to_timestamp()
    elif defect == "quarterly": s.index = pd.period_range("1980Q1", periods=len(s), freq="Q")
    elif defect == "complex": s = s.astype(complex) + 1j
    elif defect == "strings": s = s.astype(str)
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid input reached X13")
    monkeypatch.setattr(api.subprocess, "run", unexpected)
    sa, diag = api.adjust_series(s, "group", tmp_path / defect)
    assert_unavailable(sa, diag, s)
    assert diag["failure_stage"] == "input_validation"
    assert json.loads((tmp_path / defect / "diagnostics.json").read_text())["status"] == "unavailable"


def fake_run(s, *, defect=None, udg=None, error="", returncode=0):
    """Mimic only the process boundary; parser, validation, and archives stay real."""
    def run(command, *, cwd, **kwargs):
        p = Path(cwd)
        dates = [str(d.year) + f"{d.month:02d}" for d in s.index]
        values = [f"{v:.16E}" for v in s]
        if defect == "missing": return subprocess.CompletedProcess(command, 0, b"", b"")
        if defect == "misaligned": dates[-1] = "202609"
        if defect == "duplicate": dates[-1] = dates[-2]
        if defect == "nonfinite": values[-1] = "NaN"
        if defect == "infinite": values[-1] = "1E999"
        if defect == "negative": values[-1] = "-1"
        if defect == "truncated": dates, values = dates[:-1], values[:-1]
        rows = [f"{d}\t{v}" for d, v in zip(dates, values)]
        if defect == "malformed": rows[50] = "unexpected text"
        (p / "series.d11").write_text("date\tseries.d11\n------\t-----------------------\n" + "\n".join(rows) + "\n")
        (p / "series.err").write_text(error)
        (p / "series.out").write_text("X13 report\n" + error)
        (p / "series.udg").write_text(udg if udg is not None else "converged: yes\nqssadj: 0.0 1.0\nqsssadj: 0.0 1.0\nnpsadj: no\nnpssadj: no\npeaks.seas: none\n")
        return subprocess.CompletedProcess(command, returncode, b"completed\n", b"")
    return run


@pytest.mark.parametrize("defect", ["missing", "misaligned", "duplicate", "nonfinite", "infinite", "negative", "truncated", "malformed"])
def test_rejects_bad_d11_even_after_exit_zero(api, tmp_path, monkeypatch, defect):
    s = sample()
    monkeypatch.setattr(api.subprocess, "run", fake_run(s, defect=defect))
    sa, diag = api.adjust_series(s, "group", tmp_path / defect)
    assert_unavailable(sa, diag, s)
    assert diag["failure_stage"] == "output_validation"


@pytest.mark.parametrize("failure", ["nonzero", "fatal_exit_zero", "timeout", "launch", "not_converged"])
def test_process_failures_are_explicit_and_archived(api, tmp_path, monkeypatch, failure):
    s = sample()
    run = fake_run(s, returncode=5) if failure == "nonzero" else fake_run(s, error="ERROR: estimation failed\n")
    if failure == "not_converged": run = fake_run(s, udg="converged: no\n")
    if failure in {"timeout", "launch"}:
        def run(*args, **kwargs):
            if failure == "timeout": raise subprocess.TimeoutExpired("x13", 120, output=b"partial report")
            raise OSError("cannot launch")
    monkeypatch.setattr(api.subprocess, "run", run)
    sa, diag = api.adjust_series(s, "group", tmp_path / failure)
    assert_unavailable(sa, diag, s)
    assert (tmp_path / failure / "series.spc").is_file()
    assert (tmp_path / failure / "manifest.json").is_file()


def test_missing_binary_is_unavailable(api, tmp_path, monkeypatch):
    monkeypatch.setenv("CZ_X13_PATH", str(tmp_path / "missing.exe"))
    sa, diag = api.adjust_series(sample(), "group", tmp_path / "run")
    assert_unavailable(sa, diag, sample())


def test_create_only_directory(api, tmp_path):
    p = tmp_path / "existing"
    p.mkdir()
    (p / "sentinel").write_bytes(b"unchanged")
    with pytest.raises(FileExistsError): api.adjust_series(sample(), "group", p)
    assert list(p.iterdir()) == [p / "sentinel"]


def test_qs_spectral_and_missing_diagnostics_are_flags_not_validation_claims(api, tmp_path, monkeypatch):
    for name, udg, expected in [
        ("qs", "qssadj: 15.2 0.0005\nqsssadj: 0 1\npeaks.seas: none\n", "residual_seasonality_qs"),
        ("spectral", "qssadj: 0 1\nqsssadj: 0 1\npeaks.seas: sa irr\n", "residual_seasonality_spectrum"),
        ("np", "qssadj: 0 1\nqsssadj: 0 1\nnpsadj: yes\npeaks.seas: none\n", "residual_seasonality_nonparametric"),
        ("missing", "converged: yes\n", "residual_seasonality_diagnostics_unavailable"),
    ]:
        monkeypatch.setattr(api.subprocess, "run", fake_run(sample(), udg=udg))
        sa, diag = api.adjust_series(sample(), name, tmp_path / name)
        assert diag["status"] == "ok"
        assert expected in diag["quality_flags"]
        assert diag["quality_status"] == "flagged"
        assert "validated" not in diag["quality_status"]


def test_spec_keeps_shocks_and_archive_hashes_are_complete(api, tmp_path, monkeypatch):
    monkeypatch.setattr(api.subprocess, "run", fake_run(sample()))
    out = tmp_path / "package_holidays"
    sa, diag = api.adjust_series(sample(), 'package_holidays', out)
    spec = (out / "series.spc").read_text()
    assert "function=log" in spec and "automdl" in spec and "types=(ao ls tc)" in spec
    assert "final=" not in spec and "d11" in spec and "easter" not in spec.lower()
    assert diag["settings"]["outlier_effects_retained"] is True
    assert len(diag["binary_sha256"]) == 64
    manifest = json.loads((out / "manifest.json").read_text())
    actual = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.name != "manifest.json"}
    assert manifest["files"] == actual
    assert json.loads((out / "diagnostics.json").read_text()) == diag
    assert sa.name == "package_holidays"


def test_real_x13_removes_seasonality_and_preserves_trend_and_shock(api, tmp_path):
    s = sample()
    sa, diag = api.adjust_series(s, "synthetic_seasonal", tmp_path / "seasonal")
    assert diag["status"] == "ok", diag
    assert sa.index.equals(s.index) and np.isfinite(sa).all() and (sa > 0).all()
    trend = .002*np.arange(len(s))
    raw_amplitude = np.ptp((np.log(s/100)-trend).groupby(s.index.month).mean())
    adjusted_amplitude = np.ptp((np.log(sa/100)-trend).groupby(sa.index.month).mean())
    assert adjusted_amplitude < .02 * raw_amplitude
    assert abs(np.polyfit(np.arange(len(sa)), np.log(sa), 1)[0] - .002) < .00001
    assert diag["residual_seasonality"]["qs_tests"]["qssadj"]["p_value"] >= .01
    shock = s.copy(); shock.iloc[130] *= 1.25
    sa_shock, shock_diag = api.adjust_series(shock, "synthetic_shock", tmp_path / "shock")
    assert shock_diag["status"] == "ok", shock_diag
    assert abs(sa_shock.iloc[130]/sa.iloc[130] - 1.25) < .002


def test_real_constant_growth_with_irregular_component_preserves_rates(api, tmp_path):
    sa, diag = api.adjust_series(sample(season=False), "constant_growth", tmp_path / "growth")
    assert diag["status"] == "ok", diag
    expected = 100*np.expm1(.002*12)
    for window in (3, 6):
        rates = 100*((sa/sa.shift(window))**(12/window)-1)
        assert abs(rates.mean() - expected) < .05
        assert abs(rates.iloc[-1] - expected) < .25


@pytest.mark.parametrize("has_season", [True, False])
def test_real_degenerate_exact_trend_fails_without_specification_switch(api, tmp_path, has_season):
    s = sample(season=has_season, noise=False)
    sa, diag = api.adjust_series(s, "exact_deterministic", tmp_path / "exact")
    assert_unavailable(sa, diag, s)
    assert "zero" in diag["reason"].lower() or "converg" in diag["reason"].lower()
    assert len(list((tmp_path / "exact").glob("*.spc"))) == 1


def test_real_through_july_has_exact_truncated_index(api, tmp_path):
    s = sample().iloc[:-1]
    sa, diag = api.adjust_series(s, "through_july", tmp_path / "july")
    assert diag["status"] == "ok", diag
    assert sa.index.equals(s.index) and str(sa.index[-1]) == "2026-07"
