"""Validated offline inputs for the bounded R10 core-split diagnostics.

The ARAD inputs are annual NSA inflation rates with first-round tax effects,
not an exact monthly core partition. Detailed CZSO service levels are current
retrieved histories. Basket publication dates are reconstructed assumptions;
their approved midnight convention is preserved, not presented as vintages.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

import numpy as np
import pandas as pd


CATEGORIES = ["actual_rent", "imputed_rent", "catering", "accommodation", "package_holidays"]
BROAD_SERIES = {"SCPICLEM02YOYPECNA": "goods", "SCPICLEM03YOYPECNA": "services"}
DEFAULT_ROOT = Path(__file__).resolve().with_suffix("")
_REQUIRED_FILES = {
    "monthly_levels.csv", "broad_yoy.csv", "selected_basket_weights.csv",
    "canonical_metadata.json", "provenance.json", "raw/arad_retrievals.json",
    "raw/SCPICLEM02YOYPECNA.json", "raw/SCPICLEM03YOYPECNA.json",
    "raw/cpi_cle_en.pdf", "raw/cpi_mz_en.pdf", "audit/FINDINGS.md",
    "audit/numeric_summary.json", "audit/arithmetic_proof.csv",
}


def _verify_manifest(root: Path) -> None:
    """Verify the complete frozen package before parsing any model input."""
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        entries = manifest["files"]
        if manifest.get("schema_version") != 1 or manifest.get("hash_algorithm") != "SHA256":
            raise ValueError("unsupported frozen integrity manifest")
        if not isinstance(entries, dict) or not _REQUIRED_FILES.issubset(entries):
            raise ValueError("frozen integrity manifest omits required files")
        actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
        actual.discard("manifest.json")
        if actual != set(entries):
            raise ValueError("frozen integrity manifest does not match the package files")
        for name, record in entries.items():
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
                raise ValueError("unsafe path in frozen integrity manifest")
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise ValueError("frozen integrity path escapes root")
            payload = path.read_bytes()
            if len(payload) != record["bytes"] or hashlib.sha256(payload).hexdigest() != record["sha256"]:
                raise ValueError(f"SHA256 integrity mismatch: {name}")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid or missing frozen integrity manifest/files") from exc


def _validate_monthly(frame: pd.DataFrame, label: str, *, positive: bool) -> None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"{label}: empty monthly data")
    index = frame.index
    if not isinstance(index, pd.PeriodIndex) or index.freqstr != "M":
        raise ValueError(f"{label}: monthly PeriodIndex required")
    if index.hasnans:
        raise ValueError(f"{label}: missing month")
    if index.has_duplicates:
        raise ValueError(f"{label}: duplicate months")
    if not index.is_monotonic_increasing:
        raise ValueError(f"{label}: months must be in increasing order")
    if not index.equals(pd.period_range(index[0], index[-1], freq="M")):
        raise ValueError(f"{label}: contiguous monthly calendar required")
    if frame.columns.has_duplicates:
        raise ValueError(f"{label}: duplicate categories")
    try:
        values = frame.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}: finite numeric observations required") from exc
    if not np.isfinite(values).all():
        raise ValueError(f"{label}: all observations must be finite; missing values are not filled")
    if positive and (values <= 0).any():
        raise ValueError(f"{label}: index levels must be strictly positive")
    if not positive and (values <= -100).any():
        raise ValueError(f"{label}: annual inflation must exceed -100 for positive gross factors")


def _read_monthly(path: Path, columns: list[str], *, positive: bool) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"target_month": str})
    if list(frame.columns) != ["target_month", *columns]:
        raise ValueError(f"{path.name}: incorrect monthly columns")
    if not frame.target_month.str.fullmatch(r"\d{4}-\d{2}", na=False).all():
        raise ValueError(f"{path.name}: invalid monthly calendar labels")
    try:
        index = pd.PeriodIndex(frame.pop("target_month"), freq="M", name="target_month")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path.name}: invalid monthly calendar") from exc
    frame.index = index
    _validate_monthly(frame, path.name, positive=positive)
    return frame.astype(float)


def _validated_weights(weights: pd.DataFrame) -> pd.DataFrame:
    required = {"effective_year", "series_name", "weight_permille", "availability_assumption_date"}
    if not isinstance(weights, pd.DataFrame) or weights.empty or not required.issubset(weights.columns):
        raise ValueError("weights: nonempty long-form regimes with availability dates required")
    frame = weights.copy()
    try:
        year = pd.to_numeric(frame.effective_year, errors="raise")
        value = pd.to_numeric(frame.weight_permille, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("weights: numeric regime years and weights required") from exc
    if not np.isfinite(year).all() or not year.between(1, 9998).all() or (year % 2 != 0).any():
        raise ValueError("weights: effective regime years must be positive even integers")
    if not np.isfinite(value).all() or (value <= 0).any():
        raise ValueError("weights: each group weight must be finite and positive")
    frame["effective_year"] = year.astype(int)
    frame["weight_permille"] = value.astype(float)
    if frame.duplicated(["effective_year", "series_name"]).any():
        raise ValueError("weights: duplicate category within a regime")
    dates = frame.availability_assumption_date
    if not dates.map(lambda x: isinstance(x, str)).all() or not dates.str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False).all():
        raise ValueError("weights: availability assumption must be a date in YYYY-MM-DD form")
    try:
        # Validate real dates; preserve the declared date strings in the API.
        pd.to_datetime(dates, format="%Y-%m-%d", errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("weights: invalid availability assumption date") from exc
    for _, group in frame.groupby("effective_year", sort=False):
        if len(group) != len(CATEGORIES) or set(group.series_name) != set(CATEGORIES):
            raise ValueError("weights: every regime must contain exactly the same five categories")
        if group.availability_assumption_date.nunique() != 1:
            raise ValueError("weights: each regime must have one shared availability date")
        if group.weight_permille.sum() >= 1000:
            raise ValueError("weights: selected group fractions must sum to less than one")
    return frame


def load_frozen(root: str | Path | None = None) -> dict:
    """Load and validate only the frozen package, without a database or network.

    ``root`` is the package directory (default: ``data/core_split``). Returns
    ``levels`` (five monthly index columns), ``broad_yoy`` (goods/services in
    annual percent), long-form ``weights`` in per mille, and scope ``metadata``.
    Both histories have strict contiguous monthly PeriodIndex calendars.
    Every packaged input and evidence file is checked against its SHA256.
    """
    root = (DEFAULT_ROOT if root is None else Path(root)).resolve()
    _verify_manifest(root)
    levels = _read_monthly(root / "monthly_levels.csv", CATEGORIES, positive=True)
    broad = _read_monthly(root / "broad_yoy.csv", list(BROAD_SERIES.values()), positive=False)
    weights = _validated_weights(pd.read_csv(root / "selected_basket_weights.csv", dtype={
        "subgroup_code": str, "basket_code": str, "availability_assumption_date": str,
    }))
    metadata = json.loads((root / "canonical_metadata.json").read_text(encoding="utf-8"))
    for label, frame in (("levels", levels), ("broad_yoy", broad)):
        try:
            expected = metadata[label]
            matches = (str(frame.index[0]) == expected["first_month"]
                       and str(frame.index[-1]) == expected["last_month"]
                       and len(frame) == expected["months"])
        except (KeyError, TypeError) as exc:
            raise ValueError(f"{label}: missing frozen coverage metadata") from exc
        if not matches:
            raise ValueError(f"{label}: monthly calendar disagrees with declared source coverage")
    return {"levels": levels, "broad_yoy": broad, "weights": weights, "metadata": metadata}


def monthly_rates(levels: pd.DataFrame) -> pd.DataFrame:
    """Compute 100 * monthly percentage change without filling or rebasing.

    Preserve the full calendar, with NaN only in the first row where no previous
    level exists. Missing or nonpositive source levels are rejected first.
    """
    _validate_monthly(levels, "levels", positive=True)
    return 100.0 * levels.astype(float).pct_change(fill_method=None)


def weights_at(weights: pd.DataFrame, origin, as_of) -> pd.Series:
    """Return five origin-available base weights as fractions of headline CPI.

    Choose the most recent even effective year <= origin.year whose assumed
    publication date is known by ``as_of``. Date-only assumptions take effect at
    midnight Europe/Prague, retaining the existing approved convention. Naive
    clocks mean Czech local time; aware clocks are converted to that timezone.
    Unknown regimes fail rather than selecting future weights.

    These are base expenditure fractions, not price-updated current contribution
    shares. Using them as fixed coefficients is a projected diagnostic; official
    contributions additionally require price updating and scope reconciliation.
    """
    frame = _validated_weights(weights)
    try:
        month = origin if isinstance(origin, pd.Period) else pd.Period(origin, freq="M")
        if month.freqstr != "M" or pd.isna(month):
            raise ValueError("origin must be a valid monthly period")
        clock = pd.Timestamp(as_of)
        if pd.isna(clock):
            raise ValueError("origin clock must be valid")
        clock = clock.tz_localize("Europe/Prague") if clock.tz is None else clock.tz_convert("Europe/Prague")
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid monthly origin or as_of clock") from exc
    available = pd.to_datetime(frame.availability_assumption_date).dt.tz_localize("Europe/Prague")
    eligible = frame.loc[frame.effective_year.le(month.year) & available.le(clock)]
    if eligible.empty:
        raise ValueError(f"no known available weight regime for {month} at {clock}")
    regime = int(eligible.effective_year.max())
    selected = eligible.loc[eligible.effective_year.eq(regime)]
    result = selected.set_index("series_name").weight_permille.reindex(CATEGORIES) / 1000.0
    result.name = "headline_basket_fraction"
    result.attrs = {"effective_year": regime, "availability_assumption_date": selected.availability_assumption_date.iloc[0],
                    "weight_kind": "base expenditure fraction; not a price-updated current contribution share"}
    return result
