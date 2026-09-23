"""Monthly Table A6 predictor panels for the TVW-QRF experiments.

Two panels are written from the rebuilt A6 inputs (exact official series, the
Bloomberg series the user selected for rows 60-63 and 65-66, the best candidates
for rows 13, 17, 25 and 54, and CNB LUCI when its tidy file is present).

``paper`` convention: rows are reference months, as in the paper.  Quarterly
series are interpolated with Chow-Lin (monthly unemployment as indicator), every
series not already published seasonally adjusted is X-13 adjusted over the
sample, Table A6 transforms are applied, rows 65-66 are shifted forward 12
months, the fuel principal component uses the whole sample, and missing
initial observations are imputed from common factors.  These full-sample steps
use data after each forecast origin, as the paper's description implies.  The
panel is for comparison with the published RMSEs only.

``realtime`` convention: row ``e`` holds, for every predictor, the transform of
the latest reference month available on the eve of the first release of CPI
for month ``e+1`` (CPI for ``e`` is then known). Publication masks exclude
later releases; revised source histories remain a limitation. There is no
X-13, quarterly series enter as the latest published quarter, the fuel
component is re-estimated on data available at each row, and gaps stay
missing for per-origin training-mean imputation.

Rows 22, 25 and the fuel component 64 use a fixed first-difference policy
because their concepts can be signed. Other Table A6 log differences require
positive adjacent levels; invalid pairs stay missing and are recorded. The
transform policy never depends on values elsewhere in the supplied history.

``--overrides`` replaces rows with inputs in the exact-input long format. The
file has a ``frequency`` column and an optional per-row ``seasonal_adjustment``
policy; one use is the CNB ARAD and CZSO series matched to Table A6 on
12 September 2026.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tools.paper_replication.a6_catalog import BY_NUMBER, PAPER_SAMPLE, ROWS  # noqa: E402
from tools.paper_replication.import_bloomberg_candidates import sha256_file  # noqa: E402

DATA = ROOT / "data" / "paper_replication"
INPUTS = DATA / "a6_inputs_20260912"
AUDIT = ROOT / "output" / "cnb_paper_a6_audit_20260912" / "a6_audit.csv"
TARGET = DATA / "headline_extended_and_states.csv"
CALENDAR = ROOT / "data" / "release_calendar_cz_cpi.csv"
LUCI = DATA / "official_cnb_luci_20260912" / "luci_quarterly.csv"
X13_PATH = Path(os.environ.get("CZ_X13_PATH", str(Path.home() / "x13as" / "x13as" / "x13as.exe")))
DEFAULT_OUTPUT = DATA / "paper_model_panel_20260912"
PANEL_START = pd.Period(PAPER_SAMPLE[0], freq="M")
PAPER_END = pd.Period(PAPER_SAMPLE[1], freq="M")
FACTORS = 8

# Model input for rows without an exact official series (user decision 12 Sep 2026
# for the commodity rows; best available candidate otherwise).
MODEL_CHOICE = {
    13: ("bbg__building_permits_raw_candidate__as_reported", 41),
    25: ("local__trade_balance__as_stored", 40),
    54: ("bbg__pribor_3m__month_last", None),
    60: ("bbg__brent_front_reference__month_mean", None),
    61: ("bbg__gas_day_ahead_spot__month_mean", None),
    62: ("bbg__industrial_metals_spot_index__month_mean", None),
    63: ("bbg__agriculture_spot_index__month_mean", None),
    65: ("bbg__gas_year1_user_selected__month_mean", None),
    66: ("bbg__brent_year1_user_selected__month_mean", None),
}
QUARTERLY_CHOICE = {17: "bbg__nominal_ulc_quarterly__as_reported"}
LUCI_COLUMNS = {15: "luci_total", 16: "luci_wages_labour_costs"}
FORWARD_SHIFT = {65: 12, 66: 12}
# Signed survey/trade balances and a centered fuel principal component.
SIGNED_DIFFERENCE_ROWS = frozenset({22, 25, 64})
CHANGE_KINDS = {"mm_change_pct": lambda v: 1.0 + v / 100.0, "mm_index_previous_month_100": lambda v: v / 100.0}


@dataclass
class Raw:
    number: int
    source: str
    values: pd.Series            # indexed by monthly or quarterly Period
    available: pd.Series         # Timestamp per period
    kind: str = "level"
    components: dict = field(default_factory=dict)   # row 64: fuel name -> (values, available)
    notes: list = field(default_factory=list)


def _periods(values, freq="M") -> pd.PeriodIndex:
    return pd.PeriodIndex([str(v) for v in values], freq=freq)


def _series(frame: pd.DataFrame, value="value", period="period", freq="M") -> pd.Series:
    s = pd.Series(pd.to_numeric(frame[value], errors="coerce").to_numpy(), index=_periods(frame[period], freq))
    return s[~s.index.duplicated(keep="last")].sort_index()


def _available(frame: pd.DataFrame, freq="M", fallback_days: int | None = None) -> pd.Series:
    index = _periods(frame["period"], freq)
    dates = pd.to_datetime(frame["available_from_assumed"], errors="coerce").to_numpy()
    s = pd.Series(dates, index=index)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if fallback_days is not None:
        missing = s.isna()
        s[missing] = [p.end_time.normalize() + pd.Timedelta(days=fallback_days) for p in s.index[missing]]
    return s


def load_raw(inputs: Path = INPUTS, luci: Path = LUCI, overrides: Path | None = None) -> dict[int, Raw]:
    exact = pd.read_csv(inputs / "exact_inputs_long.csv", dtype={"period": str, "component": str})
    cands = pd.read_csv(inputs / "candidate_inputs_long.csv", dtype={"period": str})
    raws: dict[int, Raw] = {}
    for number, rows in exact.groupby("a6_number"):
        kinds = rows.value_kind.unique()
        if number == 64:
            comps = {name: (_series(g), _available(g)) for name, g in rows.groupby("component")}
            first = next(iter(comps.values()))
            raws[number] = Raw(number, "; ".join(sorted(rows.source_id.unique())), first[0], first[1], "components", comps)
            continue
        raws[number] = Raw(number, "; ".join(sorted(rows.source_id.unique())), _series(rows), _available(rows), kinds[0])
    for number, (column, fallback) in MODEL_CHOICE.items():
        rows = cands[cands.column.eq(column)]
        if rows.empty:
            raise ValueError(f"row {number}: candidate column {column} missing")
        raws[number] = Raw(number, column, _series(rows), _available(rows, fallback_days=fallback))
    for number, column in QUARTERLY_CHOICE.items():
        rows = cands[cands.column.eq(column)]
        raws[number] = Raw(number, column, _series(rows, freq="Q"), _available(rows, freq="Q"), "quarterly")
    if luci.exists():
        frame = pd.read_csv(luci, dtype={"period": str})
        for number, column in LUCI_COLUMNS.items():
            if column in frame.columns:
                sub = frame[["period", column, "available_from_assumed"]].rename(columns={column: "value"}).dropna(subset=["value"])
                raws[number] = Raw(number, f"cnb_luci:{column}", _series(sub, freq="Q"), _available(sub, freq="Q"), "quarterly")
    if overrides is not None:
        raws.update(load_overrides(overrides)[0])
    return raws


def load_overrides(path: Path) -> tuple[dict[int, Raw], dict[int, str]]:
    """Replacement inputs in the exact-input long format, and any per-row seasonal-adjustment policies.

    A ``frequency`` column marks quarterly rows (``Q``). ``value_kind`` follows the
    exact inputs: a level (used as is), ``mm_index_previous_month_100`` or ``mm_change_pct``.
    """
    frame = pd.read_csv(path, dtype={"period": str, "component": str, "frequency": str})
    raws, policies = {}, {}
    for number, rows in frame.groupby("a6_number"):
        freq = str(rows["frequency"].iloc[0]) if "frequency" in rows else "M"
        kind = "quarterly" if freq == "Q" else str(rows.value_kind.iloc[0])
        raws[int(number)] = Raw(int(number), "; ".join(sorted(rows.source_id.unique())), _series(rows, freq=freq),
                                _available(rows, freq=freq), kind, notes=["override"])
        if "seasonal_adjustment" in rows and rows.seasonal_adjustment.notna().any():
            policies[int(number)] = str(rows.seasonal_adjustment.dropna().iloc[0])
    return raws, policies


def monthly_levels(raw: Raw) -> pd.Series:
    """Level series used for X-13 and log differences (chains published changes)."""
    s = raw.values.dropna()
    if raw.kind in CHANGE_KINDS:
        return CHANGE_KINDS[raw.kind](s).cumprod()
    return s


def chow_lin(quarterly: pd.Series, indicator: pd.Series) -> pd.Series:
    """Quarterly averages to months with Chow-Lin, one indicator plus a constant."""
    from tsdisagg import disaggregate_series

    q = quarterly.dropna()
    expected = pd.period_range(q.index.min(), q.index.max(), freq="Q")
    if len(expected) != len(q):
        raise ValueError(f"Chow-Lin needs an unbroken quarterly series; missing {[str(p) for p in expected.difference(q.index)]}")
    start = q.index.min().asfreq("M", "start")
    end = indicator.dropna().index.max()
    months = pd.period_range(start, end, freq="M")
    high = indicator.reindex(months).interpolate(limit_direction="both").to_frame("indicator")
    high.index = months.to_timestamp(how="end").normalize()
    low = q.to_frame("target")
    low.index = q.index.to_timestamp(how="end").normalize()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = disaggregate_series(low, high, target_column="target", agg_func="mean", method="chow-lin", verbose=False)
    out = pd.Series(np.asarray(out).reshape(-1), index=months)
    return out


def x13(series: pd.Series, end: pd.Period) -> tuple[pd.Series, str]:
    from statsmodels.tsa.x13 import x13_arima_analysis

    s = series.loc[:end].dropna()
    full = pd.period_range(s.index.min(), s.index.max(), freq="M")
    if len(s) < 48 or not s.index.equals(full):
        return series, "skipped: shorter than 4 years or internal gaps"
    ts = pd.Series(s.to_numpy(), index=full.to_timestamp())
    ts.index.freq = "MS"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = x13_arima_analysis(ts, x12path=str(X13_PATH), prefer_x13=True)
        adjusted = pd.Series(np.asarray(result.seasadj, dtype=float), index=full)
        return adjusted, "x13"
    except Exception as exc:
        return series, f"failed: {type(exc).__name__}"


def transform(series: pd.Series, code: int, *, number: int | None = None) -> tuple[pd.Series, str]:
    """Apply the declared row policy without selecting it from sample values."""
    if code == 0:
        return series, "T0"
    if code == 3:
        return series.diff(), "T3"
    if code == 2:
        if number in SIGNED_DIFFERENCE_ROWS:
            return series.diff(), f"T3 (fixed signed-series policy for row {number}; Table A6 T2)"
        nonpositive = series.le(0)
        values = np.log(series.where(series.gt(0))).diff()
        if nonpositive.any():
            invalid = (nonpositive | nonpositive.shift(1, fill_value=False)) & series.notna() & series.shift(1).notna()
            return values, f"T2: {int(invalid.sum())} invalid adjacent pairs (non-positive levels); left missing"
        return values, "T2"
    raise ValueError(code)


def fuel_pc1(components: dict[str, pd.Series]) -> tuple[pd.Series, float]:
    frame = pd.concat(components, axis=1).dropna()
    z = (frame - frame.mean()) / frame.std(ddof=0)
    u, s, vt = np.linalg.svd(z.to_numpy(), full_matrices=False)
    pc = pd.Series(u[:, 0] * s[0], index=frame.index)
    if pc.corr(z.mean(axis=1)) < 0:
        pc = -pc
    share = float(s[0] ** 2 / np.sum(s ** 2))
    return pc, share


def factor_impute(panel: pd.DataFrame, factors: int = FACTORS) -> tuple[pd.DataFrame, dict]:
    """Tall-wide factor imputation: factors from complete columns, fitted values fill gaps."""
    mean, std = panel.mean(), panel.std(ddof=0).replace(0.0, 1.0)
    z = (panel - mean) / std
    balanced = z.columns[z.notna().all()]
    k = int(min(factors, len(balanced) - 1))
    u, s, _ = np.linalg.svd(z[balanced].to_numpy(), full_matrices=False)
    F = u[:, :k] * s[:k]
    design = np.column_stack([np.ones(len(z)), F])
    filled = z.copy()
    report = {}
    for column in z.columns[z.isna().any()]:
        observed = z[column].notna().to_numpy()
        if observed.sum() < k + 12:
            report[column] = "too few observations; left missing"
            continue
        beta = np.linalg.lstsq(design[observed], z[column].to_numpy()[observed], rcond=None)[0]
        filled.loc[~observed, column] = design[~observed] @ beta
        report[column] = f"imputed {int((~observed).sum())} months"
    return filled * std + mean, {"factors": k, "balanced_columns": len(balanced), "columns": report}


def needs_x13(policy: str, kind: str) -> bool:
    """X-13 decision from a row's seasonal-adjustment policy text (the paper adjusts every series)."""
    if kind == "components" or "do not re-adjust" in policy:
        return False
    return "X-13" in policy or (kind == "quarterly" and "unknown" not in policy)


def paper_panel(raws: dict[int, Raw], audit: pd.DataFrame, end: pd.Period = PAPER_END,
                policies: dict[int, str] | None = None) -> tuple[pd.DataFrame, dict]:
    months = pd.period_range(PANEL_START, end, freq="M")
    adjust = audit.set_index("number").seasonal_adjustment.astype(object).copy()
    for number, policy in (policies or {}).items():
        adjust[number] = policy
    indicator = monthly_levels(raws[11])
    columns, log = {}, {}
    for row in ROWS:
        n = row.number
        entry = {"source": raws[n].source if n in raws else None}
        if n not in raws:
            entry["status"] = "missing"
            log[n] = entry
            continue
        raw = raws[n]
        if raw.kind == "components":
            fuels = {}
            for name, (values, _) in raw.components.items():
                adjusted, status = x13(values.dropna(), end)
                fuels[name] = adjusted
                entry[f"x13_{name}"] = status
            level, share = fuel_pc1({k: v.loc[:end] for k, v in fuels.items()})
            entry["pc1_variance_share"] = share
        elif raw.kind == "quarterly":
            level = chow_lin(raw.values.loc[:end.asfreq("Q")], indicator)
            entry["chow_lin"] = "monthly unemployment rate as indicator"
        else:
            level = monthly_levels(raw)
        policy = str(adjust.get(n, ""))
        if needs_x13(policy, raw.kind):
            level, entry["x13"] = x13(level, end)
        values, entry["transform"] = transform(level, row.transform, number=n)
        if n in FORWARD_SHIFT:
            values = values.shift(FORWARD_SHIFT[n], freq="M")
            entry["forward_shift_months"] = FORWARD_SHIFT[n]
        values = values.reindex(months)
        entry["missing_before_imputation"] = int(values.isna().sum())
        columns[f"a6_{n:02d}"] = values
        log[n] = entry
    panel = pd.DataFrame(columns, index=months)
    empty = [c for c in panel.columns if panel[c].notna().sum() == 0]
    panel = panel.drop(columns=empty)
    filled, report = factor_impute(panel)
    return filled, {"rows": log, "imputation": report, "dropped_empty_columns": empty}


def release_eves(calendar: Path, months: pd.PeriodIndex) -> pd.Series:
    """Eve of the first CPI release for month e+1, for every row e (rule before the calendar starts)."""
    cal = pd.read_csv(calendar, dtype={"target_month": str})
    first = pd.Series(pd.to_datetime(cal.first_release_dt).to_numpy(), index=_periods(cal.target_month))
    eves = []
    for e in months:
        nxt = e + 1
        release = first.get(nxt)
        if release is None or pd.isna(release):
            release = (nxt + 1).start_time.normalize() + pd.Timedelta(days=9)
        eves.append(pd.Timestamp(release).normalize() - pd.Timedelta(days=1))
    return pd.Series(eves, index=months)


def _latest_available(values: pd.Series, available: pd.Series, eves: pd.Series) -> pd.Series:
    """For each row, the value of the latest period whose availability date is on or before the eve."""
    frame = pd.DataFrame({"value": values, "available": available.reindex(values.index)}).dropna(subset=["available"])
    frame = frame.sort_values("available", kind="mergesort")
    order = frame["available"].to_numpy(dtype="datetime64[ns]")
    out = []
    for eve in eves.to_numpy(dtype="datetime64[ns]"):
        k = int(np.searchsorted(order, eve, side="right"))
        if k == 0:
            out.append(np.nan)
            continue
        visible = frame.iloc[:k]
        latest = visible.index.max()
        out.append(frame.loc[latest, "value"])
    return pd.Series(out, index=eves.index, dtype=float)


def realtime_panel(raws: dict[int, Raw], calendar: Path = CALENDAR, end: pd.Period | None = None) -> tuple[pd.DataFrame, dict]:
    last = end or max(r.values.dropna().index.max() for r in raws.values() if r.kind not in ("quarterly",))
    months = pd.period_range(PANEL_START, last, freq="M")
    eves = release_eves(calendar, months)
    columns, log = {}, {}
    for row in ROWS:
        n = row.number
        if n not in raws:
            log[n] = {"status": "missing"}
            continue
        raw = raws[n]
        entry = {"source": raw.source}
        if raw.kind == "components":
            prices = {k: v for k, (v, _) in raw.components.items()}
            avail = next(iter(raw.components.values()))[1]
            frame = pd.concat(prices, axis=1).dropna()
            values = []
            for e, eve in eves.items():
                visible = frame[avail.reindex(frame.index) <= eve]
                if len(visible) < 36:
                    values.append(np.nan)
                    continue
                pc, _ = fuel_pc1({k: visible[k] for k in visible.columns})
                values.append(float(pc.iloc[-1] - pc.iloc[-2]))
            columns[f"a6_{n:02d}"] = pd.Series(values, index=months)
            entry["transform"] = f"T3 (fixed signed-series policy for row {n}; Table A6 T2); component re-estimated at each row"
            log[n] = entry
            continue
        if raw.kind == "quarterly":
            level = raw.values.dropna()
            values, entry["transform"] = transform(level, row.transform, number=n)
            aligned = _latest_available(values, raw.available, eves)
            entry["quarterly"] = "latest published quarter"
        else:
            level = monthly_levels(raw)
            values, entry["transform"] = transform(level, row.transform, number=n)
            aligned = _latest_available(values, raw.available, eves)
        if n in FORWARD_SHIFT:
            aligned = aligned.shift(FORWARD_SHIFT[n])
            entry["forward_shift_months"] = FORWARD_SHIFT[n]
        columns[f"a6_{n:02d}"] = aligned
        entry["missing_rows"] = int(aligned.isna().sum())
        log[n] = entry
    panel = pd.DataFrame(columns, index=months)
    return panel, {"rows": log, "eves": {str(k): str(v.date()) for k, v in eves.items()}}


def target_series(path: Path = TARGET) -> pd.Series:
    frame = pd.read_csv(path, dtype={"period": str})
    return _series(frame, value="headline_mm_extended").rename("cpi_mm")


def build(output: Path = DEFAULT_OUTPUT, inputs: Path = INPUTS, audit_path: Path = AUDIT, overrides: Path | None = None) -> dict:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    audit = pd.read_csv(audit_path)
    raws = load_raw(inputs, overrides=overrides)
    replaced, policies = load_overrides(overrides) if overrides else ({}, {})
    paper, paper_log = paper_panel(raws, audit, policies=policies)
    realtime, realtime_log = realtime_panel(raws)
    target = target_series()
    paths = {"paper": output / "paper_convention_panel.csv", "realtime": output / "realtime_panel.csv",
             "target": output / "target_cpi_mm.csv"}
    paper.to_csv(paths["paper"], index_label="period")
    realtime.to_csv(paths["realtime"], index_label="period")
    target.to_csv(paths["target"], index_label="period")
    kinds = {f"a6_{r.number:02d}": r.kind for r in ROWS}
    manifest = {
        "tool": "build_paper_panel", "created_at": datetime.now(timezone.utc).isoformat(),
        "paper_sample": list(PAPER_SAMPLE), "x13_binary": str(X13_PATH),
        "rows_present": sorted(int(k[3:]) for k in paper.columns),
        "rows_missing": [r.number for r in ROWS if f"a6_{r.number:02d}" not in paper.columns],
        "model_choice": {str(k): v[0] for k, v in MODEL_CHOICE.items() if k not in replaced}
                        | {str(k): v for k, v in QUARTERLY_CHOICE.items() if k not in replaced},
        "overrides": {"file": str(overrides), "sha256": sha256_file(Path(overrides)), "rows": sorted(replaced),
                      "sources": {str(k): r.source for k, r in replaced.items()},
                      "seasonal_policies": {str(k): v for k, v in policies.items()}} if overrides else None,
        "luci_file": str(LUCI) if LUCI.exists() else None,
        "column_kinds": kinds, "paper_convention": paper_log, "realtime_convention": realtime_log,
        "inputs": {str(p): sha256_file(p) for p in [inputs / "exact_inputs_long.csv", inputs / "candidate_inputs_long.csv",
                                                      audit_path, TARGET, CALENDAR] + ([LUCI] if LUCI.exists() else [])},
        "outputs": {k: {"file": p.name, "sha256": sha256_file(p)} for k, p in paths.items()},
        "tool_sha256": sha256_file(Path(__file__)),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overrides", type=Path, help="replacement inputs in the exact-input long format")
    args = parser.parse_args(argv)
    manifest = build(args.output, overrides=args.overrides)
    print(json.dumps({"rows_present": len(manifest["rows_present"]), "rows_missing": manifest["rows_missing"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
