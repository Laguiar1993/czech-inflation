"""Strict, timezone-aware release selection for archived monthly observations.

The selector operates on publication timestamps, never reference-month lag rules.
SA and trend-cycle are separate concepts; ``published_adjusted`` explicitly follows
the statistics CZSO published at each origin, carrying adjustment metadata.
"""
from pathlib import Path
import numpy as np
import pandas as pd


DEFAULT_UNEMPLOYMENT_PATH = Path(__file__).parent / "vintages" / "unemployment.csv.gz"
REQUIRED = ("series", "reference_period", "available_from", "value", "source", "sha256")


def _aware_utc(value, label):
    try:
        stamp = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label} must be an explicit timezone-aware timestamp") from exc
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError(f"{label} must be an explicit timezone-aware timestamp")
    return stamp.tz_convert("UTC")


def _validated(frame):
    missing = [c for c in REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(f"Missing vintage metadata: {', '.join(missing)}")
    result = frame.copy()
    for column in ("series", "reference_period", "source", "sha256"):
        if result[column].isna().any() or result[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Missing vintage metadata: {column}")
    if not result["reference_period"].astype(str).str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise ValueError("reference_period must be a canonical YYYY-MM month")
    if not result["sha256"].astype(str).str.fullmatch(r"[0-9a-fA-F]{64}").all():
        raise ValueError("sha256 must contain a full SHA-256 digest")
    result["available_from"] = pd.to_datetime(
        [_aware_utc(x, "available_from") for x in result["available_from"]], utc=True)
    result["value"] = pd.to_numeric(result["value"], errors="coerce")
    if not np.isfinite(result["value"].to_numpy(dtype=float)).all():
        raise ValueError("value must be finite")
    keys = ["series", "reference_period", "available_from"]
    if result.duplicated(keys, keep=False).any():
        raise ValueError("Ambiguous duplicate series/reference_period/available_from vintage")
    return result


def select_vintages(frame, as_of, series=None):
    """Return the last actually released row per series and reference month.

    All metadata is validated, including future rows; duplicate vintage keys fail
    rather than selecting a row based on input order. Equality is eligible.
    """
    clock = _aware_utc(as_of, "as_of")
    eligible = _validated(frame)
    eligible = eligible.loc[eligible["available_from"] <= clock]
    if series is not None:
        names = [series] if isinstance(series, str) else list(series)
        eligible = eligible.loc[eligible["series"].isin(names)]
    return (eligible.sort_values(["series", "reference_period", "available_from"])
            .drop_duplicates(["series", "reference_period"], keep="last")
            .reset_index(drop=True))


def released_unemployment(as_of, vintage_path=DEFAULT_UNEMPLOYMENT_PATH,
                          adjustment="published_adjusted"):
    """Return CZSO total 15–64 unemployment (%) with monthly PeriodIndex.

    ``published_adjusted`` uses SA or trend-cycle as published at the origin.
    ``sa``, ``trend_cycle`` and ``nsa`` require that specific concept. Missing
    archive coverage returns an empty series, without any latest-data fallback.
    Selected row provenance and adjustment labels are available in ``attrs``.
    Fit one-sided transformations only after selecting the origin's series.
    """
    policies = {"published_adjusted": ["sa", "trend_cycle"], "sa": ["sa"],
                "trend_cycle": ["trend_cycle"], "nsa": ["nsa"]}
    if adjustment not in policies:
        raise ValueError(f"Unknown adjustment policy: {adjustment}")
    frame = pd.read_csv(vintage_path)
    for column in ("adjustment", "vintage_kind"):
        if column not in frame or frame[column].isna().any():
            raise ValueError(f"Missing vintage metadata: {column}")
    if not frame["vintage_kind"].eq("historical_release").all():
        raise ValueError("released_unemployment requires historical_release rows only")
    selected = select_vintages(frame, as_of,
                               [f"unemployment_{a}" for a in policies[adjustment]])
    expected = "unemployment_" + selected["adjustment"].astype(str)
    if not selected["series"].eq(expected).all():
        raise ValueError("series and adjustment metadata disagree")
    # The transition release republishes the whole history as trend-cycle.
    # Select its rows by publication timestamp, never append a 2026 history to
    # a 2019 origin. A same-time conflicting adjustment is an ambiguity.
    if selected.duplicated(["reference_period", "available_from"]).any():
        raise ValueError("Ambiguous adjusted vintage at the same publication timestamp")
    selected = (selected.sort_values(["reference_period", "available_from"])
                .drop_duplicates("reference_period", keep="last"))
    result = pd.Series(selected["value"].to_numpy(dtype=float),
                       index=pd.PeriodIndex(selected["reference_period"], freq="M"),
                       name="unemployment_rate").sort_index()
    result.attrs.update(vintage_mode="historical_release", adjustment_policy=adjustment,
                        adjustments=sorted(selected["adjustment"].unique().tolist()),
                        as_of=_aware_utc(as_of, "as_of").isoformat(),
                        provenance=selected.assign(available_from=selected["available_from"].astype(str))
                        .to_dict("records"))
    return result
