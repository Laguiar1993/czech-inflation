"""Fixed-specification X13 adjustment with create-only evidence and no fallback.

Only D11 is returned. Outlier effects remain in it: X11's `final` argument is
deliberately omitted. An executable exit code of zero is NOT a success test.
See SEASONAL_README.md for the contract, diagnostics, and synthetic limitations.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

DEFAULT_BINARY = Path("C:/Users/luis_/x13as/x13as/x13as.exe")
TIMEOUT_SECONDS = 120
METHOD = "X13 log-autoARIMA AO/LS/TC X11 D11"
SETTINGS = {
    "version": "momentum_r35_fixed_v1",
    "period": 12,
    "minimum_observations": 96,
    "transform": "log",
    "automdl": "installed binary defaults; no manual model selection or retries",
    "outlier_types": ["ao", "ls", "tc"],
    "outlier_effects_retained": True,
    "x11_mode": "mult",
    "x11_final": "omitted: retain AO/LS/TC effects in D11",
    "return_table": "d11",
    "save_tables": ["d10", "d11", "d12", "d13"],
    "append_forecasts": False,
    "append_backcasts": False,
    "calendar_regressors": [],
    "easter_policy": "none for all groups; no pre-established robust holiday specification",
    "spectrum_logqs": True,
    "spectrum_robustsa": False,
    "qs_flag_p_value_below": 0.01,
    "timeout_seconds": TIMEOUT_SECONDS,
    "other_options": "installed X13 defaults, executable SHA256 and effective .udg archived",
}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def _bytes(path, value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    with Path(path).open("xb") as stream:
        stream.write(value or b"")


def _validate(series, name):
    if not isinstance(series, pd.Series):
        raise ValueError("input must be a pandas Series")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a nonempty string")
    if not isinstance(series.index, pd.PeriodIndex) or series.index.freqstr != "M":
        raise ValueError("input must have a monthly PeriodIndex")
    if len(series) < SETTINGS["minimum_observations"]:
        raise ValueError("at least 96 monthly observations are required")
    if series.index.hasnans or not series.index.is_unique:
        raise ValueError("monthly index must be unique and nonmissing")
    if not series.index.is_monotonic_increasing:
        raise ValueError("monthly index must be increasing; no implicit sorting")
    expected = pd.period_range(series.index[0], series.index[-1], freq="M")
    if not series.index.equals(expected):
        raise ValueError("monthly observations must be contiguous; no gap filling")
    if not is_numeric_dtype(series.dtype) or is_complex_dtype(series.dtype) or is_bool_dtype(series.dtype):
        raise ValueError("values must have a real numeric dtype")
    values = series.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("all monthly CPI levels must be finite and strictly positive")
    return pd.Series(values, index=series.index.copy(), name=name)


def _spec(series):
    values = series.to_numpy()
    data = "\n".join(" ".join(format(v, ".17g") for v in values[i:i+6])
                     for i in range(0, len(values), 6))
    start = series.index[0]
    # Do not interpolate caller-supplied names into X13 syntax or filenames.
    return (
        'series { title="R35 monthly CPI index" '
        f"start={start.year}.{start.month} period=12 data=(\n{data}\n) }}\n"
        "transform { function=log }\n"
        "automdl { }\n"
        "outlier { types=(ao ls tc) }\n"
        "x11 { mode=mult save=(d10 d11 d12 d13) "
        "appendfcst=no appendbcst=no savelog=all }\n"
        "spectrum { logqs=yes robustsa=no print=all savelog=all }\n"
        "check { }\n"
    )


def _read_d11(path, index, name):
    """Accept only the installed ASCII table format and an exact date match."""
    lines = Path(path).read_text(encoding="ascii").splitlines()
    if len(lines) < 3 or lines[0].split() != ["date", "series.d11"]:
        raise ValueError("missing or malformed D11 header")
    if not re.fullmatch(r"[-\s]+", lines[1]):
        raise ValueError("malformed D11 header separator")
    dates, values = [], []
    for line in lines[2:]:
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 2 or not re.fullmatch(r"\d{6}", fields[0]):
            raise ValueError(f"malformed D11 row: {line[:100]}")
        token = fields[0]
        dates.append(pd.Period(f"{token[:4]}-{token[4:]}", freq="M"))
        values.append(float(fields[1].replace("D", "E").replace("d", "e")))
    actual = pd.PeriodIndex(dates, freq="M")
    if not actual.is_unique or not actual.equals(index):
        raise ValueError("D11 dates do not exactly match input: duplicate, missing, or misaligned dates")
    values = np.asarray(values, dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("D11 contains nonfinite or nonpositive values")
    return pd.Series(values, index=index.copy(), name=name)


def _udg(text):
    values = {}
    for line in text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip().lower()] = value.strip()
    return values


def _residual_diagnostics(udg, index):
    tests, flags = {}, []
    labels = {
        "qsori": "original, full sample",
        "qssori": "original, last up to 96 months",
        "qsrsd": "regARIMA residuals, full sample",
        "qssrsd": "regARIMA residuals, last up to 96 months",
        "qssadj": "log D11, full sample",
        "qsssadj": "log D11, last up to 96 months",
        "qssadjevadj": "log extreme-value-adjusted SA, full sample",
        "qsssadjevadj": "log extreme-value-adjusted SA, last up to 96 months",
    }
    for key, label in labels.items():
        raw = udg.get(key, "").split()
        try:
            if len(raw) != 2:
                continue
            statistic, p_value = [float(v.replace("D", "E")) for v in raw]
            if not np.isfinite([statistic, p_value]).all() or statistic < 0 or not 0 <= p_value <= 1:
                continue
            tests[key] = {"statistic": statistic, "p_value": p_value, "series": label}
        except ValueError:
            continue
    sa_qs = [tests[k] for k in ("qssadj", "qsssadj") if k in tests]
    if len(sa_qs) < 2:
        flags.append("residual_seasonality_diagnostics_unavailable")
    if any(test["p_value"] < .01 for test in sa_qs):
        flags.append("residual_seasonality_qs")
    spectral = {k: v for k, v in udg.items() if k.startswith("peaks.") or k.startswith("spcsa.")}
    if "sa" in udg.get("peaks.seas", "").split() or "sa" in udg.get("peaks.tukey.seas", "").split():
        flags.append("residual_seasonality_spectrum")
    nonparametric = {k: udg[k] for k in ("npsadj", "npssadj") if k in udg}
    if any(v.lower() == "yes" for v in nonparametric.values()):
        flags.append("residual_seasonality_nonparametric")
    detected = any(f != "residual_seasonality_diagnostics_unavailable" for f in flags)
    return {
        "status": "flagged" if detected else ("unavailable" if not sa_qs else "not_detected_by_available_tests"),
        "qs_tests": tests,
        "nonparametric_sa": nonparametric,
        "spectral": spectral,
        "qs_threshold": .01,
        "full_start": str(index[0]),
        "recent_start": str(index[max(0, len(index)-96)]),
        "end": str(index[-1]),
        "spectrum_start_as_reported": udg.get("startspec"),
        "interpretation": "Diagnostics are warnings, not proof of valid adjustment or calibrated uncertainty. D11 retains shocks.",
    }, flags


def _finish(out, diagnostic):
    diagnostic["quality_flags"] = list(dict.fromkeys(diagnostic["quality_flags"]))
    diagnostic["quality_status"] = (
        "unavailable" if diagnostic["status"] != "ok" else
        ("flagged" if diagnostic["quality_flags"] else "not_flagged_by_available_diagnostics")
    )
    diagnostic["archive_files"] = {
        p.name: _sha256(p) for p in sorted(out.iterdir()) if p.is_file()
    }
    _json(out / "diagnostics.json", diagnostic)
    _json(out / "manifest.json", {
        "schema": "momentum_r35_x13_archive/v1",
        "delivery_seal": False,
        "files": {p.name: _sha256(p) for p in sorted(out.iterdir()) if p.is_file()},
    })


def adjust_series(series, name, output_dir):
    """Return (aligned SA Series, JSON-safe diagnostic); failures return all NaN.

    output_dir must not already exist. Directory/evidence-write errors propagate:
    callers must not treat an unarchived result as usable. No retries or fallback.
    """
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=False)
    index = series.index.copy() if isinstance(series, pd.Series) else pd.PeriodIndex([], freq="M")
    sa = pd.Series(np.nan, index=index, name=name if isinstance(name, str) else None, dtype=float)
    diagnostic = {
        "schema": "momentum_r35_x13/v1",
        "name": str(name),
        "status": "unavailable",
        "method": METHOD,
        "reason": None,
        "failure_stage": None,
        "quality_flags": [],
        "warnings": [],
        "settings": json.loads(json.dumps(SETTINGS)),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(out),
        "binary_path": None,
        "binary_sha256": None,
        "binary_sha256_after": None,
        "process_returncode": None,
        "residual_seasonality": {"status": "unavailable", "qs_tests": {}},
        "limitations": [
            "Current-vintage descriptive adjustment; historical values revise.",
            "Parent builder owns endpoint comparison; wrapper processes one supplied sample.",
            "No Easter or trading-day regressors, including travel-sensitive groups.",
            "Exactly deterministic series may fail automatic outlier detection with zero residual variance.",
        ],
    }
    _json(out / "settings.json", diagnostic["settings"])
    stage = "input_validation"
    try:
        clean = _validate(series, name)
        diagnostic["input"] = {"n": len(clean), "start": str(clean.index[0]), "end": str(clean.index[-1])}
        clean.to_csv(out / "input.csv", index_label="month", encoding="utf-8", mode="x", float_format="%.17g")
        _bytes(out / "series.spc", _spec(clean))
        stage = "binary_validation"
        binary = Path(os.environ.get("CZ_X13_PATH", str(DEFAULT_BINARY))).expanduser().resolve()
        diagnostic["binary_path"] = str(binary)
        diagnostic["binary_sha256"] = _sha256(binary)
        command = [str(binary), "series", "-s"]
        diagnostic["command"] = command
        stage = "process"
        try:
            result = subprocess.run(
                command, cwd=out, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=TIMEOUT_SECONDS, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            _bytes(out / "stdout.txt", exc.stdout)
            _bytes(out / "stderr.txt", exc.stderr)
            raise
        _bytes(out / "stdout.txt", result.stdout)
        _bytes(out / "stderr.txt", result.stderr)
        diagnostic["process_returncode"] = int(result.returncode)
        diagnostic["binary_sha256_after"] = _sha256(binary)
        if diagnostic["binary_sha256_after"] != diagnostic["binary_sha256"]:
            raise ValueError("X13 executable hash changed during the run")
        reports = {}
        for filename in ("series.err", "series.out", "series.log", "stdout.txt", "stderr.txt"):
            path = out / filename
            if path.exists():
                reports[filename] = path.read_text(encoding="utf-8", errors="replace")
        # Keep full multi-line warnings as well as all unmodified source reports.
        for filename, report in reports.items():
            for match in re.finditer(r"(?im)^\s*(?:WARNING|NOTE):[^\n]*(?:\n[ \t]+[^\n]+)*", report):
                diagnostic["warnings"].append({"file": filename, "message": match.group(0).strip()})
        diagnostic["warnings"] = list({(w["file"], w["message"]): w for w in diagnostic["warnings"]}.values())
        report_text = "\n".join(reports.values())
        if result.returncode != 0:
            raise ValueError(f"X13 process exited with code {result.returncode}")
        fatal = re.search(r"(?im)^\s*(?:ERROR|FATAL(?: ERROR)?):[^\n]*(?:\n[ \t]+[^\n]+)*", report_text)
        if fatal or re.search(r"program error\(s\) halt execution", report_text, re.I):
            raise ValueError(fatal.group(0).strip() if fatal else "X13 reports fatal program errors")
        stage = "output_validation"
        udg_path = out / "series.udg"
        udg = _udg(udg_path.read_text(encoding="ascii")) if udg_path.exists() else {}
        if udg.get("converged", "").lower() == "no":
            raise ValueError("X13 estimation did not converge")
        sa = _read_d11(out / "series.d11", clean.index, name)
        diagnostic["effective_model"] = {k: udg.get(k) for k in (
            "version", "build", "arimamdl", "converged", "seasonalma", "finaltrendma",
            "outlier.ao", "outlier.ls", "outlier.tc", "finalreg01",
        )}
        residual, flags = _residual_diagnostics(udg, clean.index)
        diagnostic["residual_seasonality"] = residual
        diagnostic["quality_flags"].extend(flags)
        diagnostic["x11_quality_statistics"] = {
            k: v for k, v in udg.items() if k.startswith("f3.") or k in ("d11.f", "d11.3y.f", "f2.idseasonal")
        }
        if udg.get("f2.idseasonal", "").lower() == "no":
            diagnostic["quality_flags"].append("identifiable_seasonality_not_detected")
        if any(w["message"].startswith("WARNING:") for w in diagnostic["warnings"]):
            diagnostic["quality_flags"].append("x13_warning")
        diagnostic["status"] = "ok"
    except (ValueError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
        sa = pd.Series(np.nan, index=index, name=name if isinstance(name, str) else None, dtype=float)
        diagnostic["reason"] = f"{type(exc).__name__}: {exc}"
        diagnostic["failure_stage"] = stage
        diagnostic["quality_flags"].append(f"{stage}_failed")
    _finish(out, diagnostic)
    return sa, diagnostic
