"""Run the research-only, Bloomberg-independent paper-style CPI panel.

The operating nowcast in :mod:`forecast_independent` is intentionally small and
frozen.  This entry point is a separate challenger inspired by the CNB WP
9/2026 TVW-QRF and the Bank of England BBIM paper.  It uses only local official
data already present in the project database or versioned CSV snapshots.  It
does not use Bloomberg.  The canonical ``backtest_h0_hybrid`` builder may
refresh public official inputs when available; a fully local fallback is kept
for offline smoke tests and records the fallback reason in the manifest.

The command writes a release-stamped forecast table, policy-specific feature
lists and a summary under ``output/big_model``.  It is research output until a
common-window comparison, a publication-clock review and a prospective shadow
run have been completed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from models.paper_big import (
    POLICIES,
    direct_bbim_forecast,
    direct_tvwqrf_forecast,
    panel_variants,
)


HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "output" / "big_model"


def _period_index(index: pd.Index) -> pd.PeriodIndex:
    if isinstance(index, pd.PeriodIndex):
        return index.asfreq("M")
    return pd.PeriodIndex(pd.to_datetime(index), freq="M")


def _monthly(obj: pd.Series | pd.DataFrame, *, lag_months: int = 0):
    """Normalize a loader result to one row per month and apply an availability lag."""

    out = obj.copy()
    out.index = _period_index(out.index)
    if out.index.has_duplicates:
        out = out.groupby(level=0).last()
    if lag_months:
        out.index = out.index + int(lag_months)
    return out.sort_index()


def _read_import_prices() -> pd.Series:
    path = HERE / "data" / "czso_import_prices_sitc_monthly.csv"
    frame = pd.read_csv(path)
    values = pd.Series(
        pd.to_numeric(frame["value"], errors="coerce").to_numpy(dtype=float),
        index=pd.PeriodIndex(frame["month"].astype(str), freq="M"),
        name="import_prices_mm",
    ).sort_index()
    # The source value is the reference-month m/m change; CZSO's release is in
    # the following month, so the feature is placed on its conservative clock.
    values.index = values.index + 1
    return values


def _rename_ppi_yoy_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Expose the PPI adapter's year-on-year transform in the column names.

    ``data.local_adapter.load_ppi_yoy`` returns CZSO same-period-year-ago
    growth (the source's ``yoy_index - 100``), not a monthly percentage
    change.  The old adapter names end in ``_mm`` for historical reasons;
    this research panel keeps the values but removes that ambiguity at its
    boundary.
    """

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("PPI predictors must be a DataFrame")
    rename = {column: f"{column[:-3]}_yoy" for column in frame.columns if str(column).endswith("_mm")}
    return frame.rename(columns=rename)


def _read_ppi_predictors() -> pd.DataFrame:
    from data import local_adapter as la

    return _rename_ppi_yoy_columns(la.load_ppi_yoy())


def _read_de_hicp() -> pd.DataFrame:
    """Build a small foreign-price block from the local ECB/Eurostat mirror.

    The mirror contains processed and unprocessed food rather than a single
    CP01 total.  Their unweighted mean is explicitly labelled a proxy; no
    invented food weights are presented as official data.
    """

    path = HERE / "data" / "hicp_components_ecb_mirror.csv"
    frame = pd.read_csv(path, usecols=["REF_AREA", "ICP_ITEM", "TIME_PERIOD", "OBS_VALUE"])
    frame = frame[frame["REF_AREA"].eq("DE")]
    wanted = {
        "FOODPR": "de_food_processed_mm",
        "FOODUN": "de_food_unprocessed_mm",
        "NRGY00": "de_energy_mm",
        "SERV00": "de_services_mm",
        "IGXE00": "de_industrial_goods_ex_energy_mm",
    }
    levels = {}
    for item, name in wanted.items():
        sub = frame[frame["ICP_ITEM"].eq(item)].copy()
        if sub.empty:
            continue
        idx = pd.PeriodIndex(sub["TIME_PERIOD"].astype(str), freq="M")
        s = pd.Series(pd.to_numeric(sub["OBS_VALUE"], errors="coerce").to_numpy(), index=idx)
        s = s.groupby(level=0).last().sort_index()
        levels[name] = 100.0 * s.pct_change()
    if not levels:
        return pd.DataFrame()
    out = pd.concat(levels, axis=1)
    food_cols = [c for c in ("de_food_processed_mm", "de_food_unprocessed_mm") if c in out]
    if food_cols:
        out["de_food_hicp_mm_proxy"] = out[food_cols].mean(axis=1)
    # Eurostat HICP is normally released in the following month.  A one-month
    # placement is conservative for a monthly end-of-month forecast origin.
    out.index = out.index + 1
    return out.sort_index()


def quarterly_lci_to_monthly(frame: pd.DataFrame) -> pd.Series:
    """Convert the frozen Czech labour-cost index to a release-clock series.

    The input is a quarterly level index.  We calculate quarterly year-on-year
    growth and place each observation three months after quarter-end, matching
    the conservative lag used in the path experiments.  Values are held until
    the next eligible quarter; no interpolation of an unreleased quarter is
    performed.
    """

    if not isinstance(frame, pd.DataFrame) or not {"quarter", "value"}.issubset(frame.columns):
        raise ValueError("LCI frame must contain quarter and value columns")
    q = pd.PeriodIndex(frame["quarter"].astype(str), freq="Q")
    level = pd.Series(pd.to_numeric(frame["value"], errors="coerce").to_numpy(dtype=float), index=q)
    level = level.groupby(level=0).last().sort_index()
    # Reindex to calendar quarters before taking the four-quarter lag.  A
    # missing quarter must remain missing; positional shifting would otherwise
    # compare adjacent observations and mislabel the growth rate.
    level = level.reindex(pd.period_range(level.index.min(), level.index.max(), freq="Q"))
    yoy = 100.0 * (level / level.shift(4) - 1.0)
    eligible = yoy.dropna()
    if eligible.empty:
        return pd.Series(dtype=float, name="wage_lci_yoy")
    available = eligible.copy()
    available.index = pd.PeriodIndex(
        [quarter.asfreq("M", how="end") + 3 for quarter in eligible.index], freq="M"
    )
    available = available.groupby(level=0).last().sort_index()
    months = pd.period_range(available.index.min(), available.index.max(), freq="M")
    return available.reindex(months).ffill().rename("wage_lci_yoy")


def _read_lci() -> pd.Series:
    return quarterly_lci_to_monthly(pd.read_csv(HERE / "data" / "eurostat_lci_cz_quarterly.csv"))


def _build_local_official_panel() -> tuple[pd.Series, pd.DataFrame, dict[str, object]]:
    """Build the offline fallback panel from the local adapters.

    This is retained for smoke tests and for a checkout where the canonical
    ``backtest_h0_hybrid`` dependencies (notably ``quantile-forest`` and its
    live fetchers) are unavailable.  Production research runs should normally
    use :func:`backtest_h0_hybrid.build_panel`, via the public wrapper below.
    """

    from data import local_adapter as la
    from data import struct_inputs as si

    y = _monthly(la.load_headline_cpi_mm()).rename("cpi_mm")
    pieces: list[pd.Series | pd.DataFrame] = []
    source_meta: dict[str, object] = {
        "network": False,
        "bloomberg": False,
        "availability_lags": {
            "ppi": "loader: +1 month; source is YoY index growth (panel names end _yoy)",
            "activity": "loader: +2 months",
            "import_prices_mm": "+1 month",
            "foreign_hicp": "+1 month",
            "cpi_derived_breadth_median_services": "+1 month",
            "credit_trade": "+1 month",
            "confidence": "+1 month",
            "wage_lci_yoy": "quarter end +3 months (quarterly Eurostat LCI)",
            "inflation_expectations": "+1 month (survey month labels are not release timestamps)",
        },
        "omitted": {},
    }

    def add(name: str, loader, *, lag: int = 0):
        try:
            value = loader()
            value = _monthly(value, lag_months=lag)
            if isinstance(value, pd.Series):
                value = value.rename(name) if value.name is None else value
            pieces.append(value)
        except Exception as exc:  # optional local source: keep the reason in metadata
            source_meta["omitted"][name] = f"{type(exc).__name__}: {exc}"

    add("ppi", _read_ppi_predictors)
    add("esi", la.load_esi, lag=1)
    add("price_expect_survey", lambda: la.load_inflation_expectations(12), lag=1)
    add("price_expect_survey_36m", lambda: la.load_inflation_expectations(36), lag=1)
    add("fx", la.load_fx_monthly_mm)
    add("activity", la.load_real_activity)
    add("confidence", la.load_confidence_ri, lag=1)
    add("financial", la.load_financial)
    add("credit", la.load_credit_aggregates, lag=1)
    add("trade_balance", la.load_trade_balance, lag=1)
    add("breadth", la.load_cpi_breadth, lag=1)
    add("median_cpi_mm", la.load_median_cpi_mm, lag=1)
    add("services_cpi_mm", si.load_services_cpi_mm, lag=1)
    add("agri_price_mm", si.load_agri_price_mm)
    add("housing", si.load_housing_channel)
    add("m3_yoy", si.load_m3_yoy)
    add("wage_lci_yoy", _read_lci)
    add("import_prices_mm", _read_import_prices)
    try:
        de = _read_de_hicp()
        if not de.empty:
            pieces.append(de)
        else:
            source_meta["omitted"]["de_hicp"] = "local mirror returned no German rows"
    except Exception as exc:
        source_meta["omitted"]["de_hicp"] = f"{type(exc).__name__}: {exc}"

    # Drop short one-off analytical splits: they have too little history to be
    # a defensible large-panel predictor and would otherwise be mostly means.
    X = pd.concat(pieces, axis=1).sort_index()
    X = X.loc[:, ~X.columns.duplicated()]
    full_index = pd.period_range(
        min(y.index.min(), X.index.min()), max(y.index.max(), X.index.max()), freq="M"
    )
    X = X.reindex(full_index)
    # Numeric coercion and a strict infinite-value check happen before any
    # estimator sees the frame.  Missing cells are expected ragged-edge data.
    X = X.apply(pd.to_numeric, errors="coerce")
    if np.isinf(X.to_numpy(dtype=float)).any():
        raise ValueError("official panel contains an infinite value")
    # Do not let a source with fewer than 24 total observations masquerade as a
    # learned predictor.  Preserve the omission reason in the manifest.
    short = [c for c in X.columns if int(X[c].notna().sum()) < 24]
    if short:
        X = X.drop(columns=short)
        source_meta["omitted"]["short_series"] = {c: "fewer than 24 observations" for c in short}
    source_meta["all_columns"] = list(X.columns)
    source_meta["n_rows"] = int(len(X))
    source_meta["target_start"] = str(y.index.min())
    source_meta["target_end"] = str(y.index.max())
    source_meta["builder"] = "big_model_experiment._build_local_official_panel"
    return y, X, source_meta


def _extend_target(y: pd.Series) -> tuple[pd.Series, dict[str, object]]:
    """Add the exact pre-CZSO national CPI history when it is available.

    The feature panel is deliberately not extended by this helper.  It is
    valid for the target to start earlier than a predictor, in which case the
    origin preparation layer leaves that predictor missing until its own first
    publication.  This keeps the target extension from creating a fake early
    vintage.
    """

    base = _monthly(y).rename("cpi_mm")
    try:
        from data.local_adapter import load_headline_cpi_mm_extended

        extended = _monthly(load_headline_cpi_mm_extended()).rename("cpi_mm")
        if extended.index.min() < base.index.min():
            return extended.combine_first(base).sort_index(), {
                "target_builder": "data.local_adapter.load_headline_cpi_mm_extended",
                "target_extension": "exact national series fills pre-CZSO history",
            }
        return base, {
            "target_builder": "backtest_h0_hybrid.build_panel.y",
            "target_extension": "no earlier observations returned",
        }
    except Exception as exc:
        return base, {
            "target_builder": "backtest_h0_hybrid.build_panel.y",
            "target_extension_error": _safe_error(exc),
        }


def _shared_hybrid_panel() -> tuple[pd.Series, pd.DataFrame, dict[str, object]] | dict[str, object] | None:
    """Load the canonical non-Bloomberg panel used by the operating h0 model.

    The shared builder is deliberately imported lazily.  It imports the exact
    TVW-QRF dependency at module load time and performs a handful of official
    live-source reads; neither is needed for unit tests or for the local
    fallback.  A caller can therefore run a bounded wiring smoke test on a
    minimal checkout while a full research run still records that it used the
    canonical panel when it is available.
    """

    try:
        from backtest_h0_hybrid import build_panel

        y, _y_ex_fuel, panel, _fuel_weight = build_panel()
        if not isinstance(y, pd.Series) or not isinstance(panel, pd.DataFrame):
            raise TypeError("backtest_h0_hybrid.build_panel returned an invalid panel")
        return (
            _monthly(y).rename("cpi_mm"),
            _monthly(panel),
            {"builder": "backtest_h0_hybrid.build_panel", "fallback": False},
        )
    except Exception as exc:
        # The public wrapper records this exception in its metadata and uses
        # the explicit offline fallback.  This is not hidden model behaviour:
        # each output manifest states which builder was used and why the
        # canonical one was unavailable.
        return None if isinstance(exc, KeyboardInterrupt) else {
            "error": _safe_error(exc),
            "builder": "backtest_h0_hybrid.build_panel",
            "fallback": True,
        }


def build_official_panel() -> tuple[pd.Series, pd.DataFrame, dict[str, object]]:
    """Load the paper panel, preferring the canonical hybrid builder.

    ``backtest_h0_hybrid.build_panel`` is the source of truth for the official
    non-Bloomberg panel.  If its optional dependency or one of its live public
    fetchers is unavailable, the runner uses the fully local panel builder so
    that a bounded smoke run remains possible.  The distinction is explicit in
    ``source_meta`` and is written into ``manifest.json``; callers must not
    compare the two panel variants as if they were the same experiment.
    """

    shared = _shared_hybrid_panel()
    if isinstance(shared, tuple):
        y, X, meta = shared
        # The operating builder has the best-established release treatment.
        # Extend only the target with the exact national history when it is
        # available; no pre-2015 feature value is invented here.
        y, target_meta = _extend_target(y)
        meta = {**meta, **target_meta}
        meta["network"] = "canonical builder may fetch official public sources"
        meta["bloomberg"] = False
        meta["all_columns"] = list(X.columns)
        meta["n_rows"] = int(len(X))
        meta["target_start"] = str(y.index.min())
        meta["target_end"] = str(y.index.max())
        return y, X, meta

    fallback_reason = shared.get("error") if isinstance(shared, dict) else "unknown"
    y, X, meta = _build_local_official_panel()
    meta["canonical_builder_error"] = fallback_reason
    meta["builder_fallback"] = True
    y, target_meta = _extend_target(y)
    meta.update(target_meta)
    return y, X, meta


def align_extended_headline(y: pd.Series, X: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Return sorted monthly y and X reindexed to exactly y's months."""

    yy = _monthly(y).sort_index()
    xx = _monthly(X).sort_index()
    yy = yy.groupby(level=0).last()
    xx = xx.groupby(level=0).last()
    return yy, xx.reindex(yy.index)


def _rw_forecast(y: pd.Series, h: int) -> float:
    observed = y.dropna()
    return float(observed.iloc[-1])


def _ar_forecast(y: pd.Series, h: int, p: int = 3) -> float:
    observed = y.dropna().astype(float)
    if len(observed) <= p + max(h, 1):
        return _rw_forecast(observed, h)
    lags = pd.concat([observed.shift(i) for i in range(p)], axis=1)
    lags.columns = [f"l{i}" for i in range(p)]
    df = pd.concat([observed.shift(-h).rename("target"), lags], axis=1).dropna()
    if len(df) < p + 5:
        return _rw_forecast(observed, h)
    design = np.column_stack([np.ones(len(df)), df[[f"l{i}" for i in range(p)]].to_numpy()])
    beta = np.linalg.lstsq(design, df["target"].to_numpy(), rcond=None)[0]
    now = observed.iloc[-1:-(p + 1):-1].to_numpy()
    return float(np.r_[1.0, now] @ beta)


def _hash(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_error(exc: BaseException) -> str:
    """Serialize an exception without leaking API keys in a manifest."""

    text = f"{type(exc).__name__}: {exc}"
    return re.sub(r"(api[_-]?key=)[^&\s]+", r"\1<redacted>", text, flags=re.IGNORECASE)


def _score_table(forecasts: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in forecasts.groupby(["horizon", "policy", "model"], dropna=False):
        valid = group.dropna(subset=["actual", "forecast"])
        if valid.empty:
            continue
        err = valid["forecast"].to_numpy() - valid["actual"].to_numpy()
        rows.append(
            {
                "horizon": int(keys[0]),
                "policy": keys[1],
                "model": keys[2],
                "n": int(len(valid)),
                "rmse": float(np.sqrt(np.mean(err**2))),
                "mae": float(np.mean(np.abs(err))),
                "bias": float(np.mean(err)),
                "directional_hit": float(
                    np.mean(np.sign(valid["forecast"].to_numpy()) == np.sign(valid["actual"].to_numpy()))
                ),
                "fallback_rate": float(valid["fallback_used"].mean()) if "fallback_used" in valid else np.nan,
            }
        )
    if not rows:
        return pd.DataFrame(columns=["horizon", "policy", "model", "n", "rmse", "mae", "bias", "directional_hit", "fallback_rate"])
    return pd.DataFrame(rows).sort_values(["horizon", "rmse", "policy", "model"]).reset_index(drop=True)


def _run_policy_model(
    y: pd.Series,
    X: pd.DataFrame,
    *,
    horizon: int,
    policy: str,
    model_name: str,
    oos_start: str,
    min_train: int,
    max_origins: int | None,
    trees: int,
    rounds: int,
) -> pd.DataFrame:
    """Run one policy/model while retaining the wrapper's eligibility metadata.

    ``backtest.engine.run_backtest`` deliberately accepts scalar forecasts.  The
    paper wrappers return a diagnostics mapping, so this small clock loop keeps
    the same origin rule while preserving fallback and selected-column fields.
    """

    targets = y.loc[pd.Period(oos_start, freq="M"):].index
    if max_origins is not None:
        targets = targets[-int(max_origins):]
    rows = []
    for target_period in targets:
        origin = target_period - int(horizon)
        y_hist = y.loc[:origin]
        X_hist = X.loc[:origin]
        # ``min_train`` is the number of usable direct labels.  The history
        # handed to this function includes the h-month label delay, so require
        # min_train+h observed targets before fitting.  This keeps the model
        # score on the same origin window as the scalar benchmarks and avoids
        # quietly mixing early random-walk fallbacks into an ML score.
        if len(y_hist.dropna()) < int(min_train) + int(horizon) or y_hist.empty or X_hist.empty:
            continue
        try:
            if model_name == "TVW_QRF":
                detail = direct_tvwqrf_forecast(
                    y_hist,
                    X_hist,
                    horizon,
                    policy=policy,
                    min_history=min_train,
                    qrf_options={
                        "n_estimators": int(trees),
                        "min_samples_leaf": 3,
                        "band_max_features": None,
                    },
                )
            elif model_name == "BBIM":
                detail = direct_bbim_forecast(
                    y_hist,
                    X_hist,
                    horizon,
                    policy=policy,
                    min_history=min_train,
                    bbim_options={
                        "rounds": int(rounds),
                        "lr": 0.02,
                        "subsample": 0.5,
                        "val_len": 24,
                        "patience": 20,
                    },
                )
            else:
                raise ValueError(f"unknown policy model: {model_name}")
        except Exception as exc:
            detail = {
                "forecast": np.nan,
                "status": "failed",
                "fallback_used": False,
                "error": f"{type(exc).__name__}: {exc}",
                "n_train": np.nan,
                "selected_columns": [],
            }
        rows.append(
            {
                "period": target_period,
                "horizon": int(horizon),
                "policy": policy,
                "model": model_name,
                "actual": float(y.loc[target_period]),
                "forecast": detail.get("forecast", np.nan),
                "status": detail.get("status", "unknown"),
                "fallback_used": bool(detail.get("fallback_used", False)),
                "fallback_reason": detail.get("fallback_reason"),
                "n_train": detail.get("n_train", np.nan),
                "n_features": len(detail.get("selected_columns", [])),
                "selected_columns": ";".join(detail.get("selected_columns", [])),
                "engine": detail.get("engine"),
                "error": detail.get("error"),
            }
        )
    return pd.DataFrame(rows)


def write_manifest(
    output_dir: Path,
    *,
    script_path: Path,
    model_path: Path,
    horizons: Iterable[int],
    oos_start: str,
    min_train: int,
    panel_columns: Mapping[str, Iterable[str]],
    forecast_rows: int,
    summary_rows: int,
    failure_count: int,
    metadata: Mapping[str, object] | None = None,
) -> Path:
    """Write a compact reproducibility manifest and return its path."""

    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": _hash(Path(script_path)),
        "model_sha256": _hash(Path(model_path)),
        "horizons": [int(h) for h in horizons],
        "oos_start": str(oos_start),
        "min_train": int(min_train),
        "panel_columns": {str(k): [str(c) for c in v] for k, v in panel_columns.items()},
        "forecast_rows": int(forecast_rows),
        "summary_rows": int(summary_rows),
        "failure_count": int(failure_count),
        "metadata": dict(metadata or {}),
    }
    path = output_dir / "manifest.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def run_experiment(
    *,
    output_dir: Path = DEFAULT_OUTPUT,
    horizons: Iterable[int] = (1, 3, 6, 9, 12),
    oos_start: str = "2019-01",
    min_train: int = 60,
    max_origins: int | None = None,
    trees: int = 200,
    rounds: int = 100,
    policies: Iterable[str] = POLICIES,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Run the three policies and return forecasts, scores and metadata."""

    if min_train <= 0:
        raise ValueError("min_train must be positive")
    hs = tuple(int(h) for h in horizons)
    if not hs or any(h <= 0 for h in hs):
        raise ValueError("horizons must contain positive integers")
    requested = tuple(policies)
    if any(p not in POLICIES for p in requested):
        raise ValueError(f"policies must be drawn from {POLICIES}")

    y, X, source_meta = build_official_panel()
    # Import scipy-backed backtesting only for an actual experiment.  The
    # alignment and manifest helpers should remain lightweight and usable in a
    # minimal offline test environment.
    from backtest.engine import run_backtest

    y, X = align_extended_headline(y, X)
    variants = panel_variants(X)
    panel_columns = {p: list(variants[p].columns) for p in requested}
    output_dir.mkdir(parents=True, exist_ok=True)
    # Archive the exact panel used by this run.  This is a provenance snapshot,
    # not an additional input path: a later run still rebuilds from the local
    # official sources.  The period index is the model's conservative
    # availability month for each column; missing values are left missing.
    snapshot = pd.concat([y.rename("cpi_mm"), X], axis=1)
    snapshot.index.name = "period"
    snapshot_path = output_dir / "input_snapshot.csv"
    snapshot.to_csv(snapshot_path, float_format="%.12g")
    availability_rows = []
    for column in X.columns:
        finite = X[column].dropna()
        availability_rows.append(
            {
                "feature": column,
                "first_available": str(finite.index.min()) if not finite.empty else None,
                "last_available": str(finite.index.max()) if not finite.empty else None,
                "n_finite": int(finite.size),
            }
        )
    availability_path = output_dir / "feature_availability.csv"
    pd.DataFrame(availability_rows).to_csv(availability_path, index=False)
    rows: list[pd.DataFrame] = []
    failure_count = 0

    for h in hs:
        # The engine's origins are target periods.  A bounded tail is useful for
        # a quick local smoke run; the default evaluates the full requested OOS.
        target_oos = pd.Period(oos_start, freq="M")
        if max_origins is not None:
            target_oos = max(target_oos, y.index.max() - int(max_origins) + 1)
        common_models = {
            "RW": lambda yh, xh, hh: _rw_forecast(yh, hh),
            "AR3": lambda yh, xh, hh: _ar_forecast(yh, hh),
        }
        bt = run_backtest(y, X, h, str(target_oos), common_models, min_train=min_train + h)
        if not bt.empty:
            for model in ("RW", "AR3"):
                rows.append(
                    pd.DataFrame(
                        {
                            "period": bt.index,
                            "horizon": h,
                            "policy": "common",
                            "model": model,
                            "actual": bt["actual"].to_numpy(),
                            "forecast": bt[model].to_numpy(),
                            "status": "benchmark",
                            "fallback_used": False,
                            "n_train": np.nan,
                            "n_features": np.nan,
                        }
                    )
                )
        for policy in requested:
            # Run separately so the wrapper's status, fallback reason and
            # selected columns survive into the release-by-release table.
            for model_name in ("TVW_QRF", "BBIM"):
                bt = _run_policy_model(
                    y,
                    X,
                    horizon=h,
                    policy=policy,
                    model_name=model_name,
                    oos_start=str(target_oos),
                    min_train=min_train,
                    max_origins=max_origins,
                    trees=trees,
                    rounds=rounds,
                )
                if not bt.empty:
                    failure_count += int((bt["status"] == "failed").sum())
                    rows.append(bt)

    forecasts = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    if not forecasts.empty:
        forecasts["period"] = forecasts["period"].astype(str)
        forecasts = forecasts.sort_values(["horizon", "period", "policy", "model"]).reset_index(drop=True)
    summary = _score_table(forecasts) if not forecasts.empty else pd.DataFrame()
    forecasts.to_csv(output_dir / "forecasts.csv", index=False)
    summary.to_csv(output_dir / "summary.csv", index=False)
    feature_rows = [
        {"policy": p, "feature": c, "independent": p == "independent", "sentiment": p in ("sentiment", "full")}
        for p in requested
        for c in variants[p].columns
    ]
    pd.DataFrame(feature_rows).to_csv(output_dir / "features.csv", index=False)
    metadata = {
        "source": source_meta,
        "requested_policies": list(requested),
        "trees": trees,
        "rounds": rounds,
        "input_snapshot": snapshot_path.name,
        "input_snapshot_sha256": _hash(snapshot_path),
        "feature_availability": availability_path.name,
        "feature_availability_sha256": _hash(availability_path),
    }
    write_manifest(
        output_dir,
        script_path=Path(__file__),
        model_path=HERE / "models" / "paper_big.py",
        horizons=hs,
        oos_start=oos_start,
        min_train=min_train,
        panel_columns=panel_columns,
        forecast_rows=len(forecasts),
        summary_rows=len(summary),
        failure_count=failure_count,
        metadata=metadata,
    )
    return forecasts, summary, metadata


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--oos-start", default="2019-01")
    p.add_argument("--min-train", type=int, default=60)
    p.add_argument("--trees", type=int, default=200, help="QRF trees; lower for a smoke run")
    p.add_argument("--rounds", type=int, default=100, help="BBIM rounds")
    p.add_argument("--max-origins", type=int, default=None, help="evaluate only the most recent target months")
    p.add_argument("--horizons", type=int, nargs="+", default=[1, 3, 6, 9, 12])
    p.add_argument("--policies", nargs="+", choices=POLICIES, default=list(POLICIES))
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _, summary, _ = run_experiment(
        output_dir=args.output_dir,
        horizons=args.horizons,
        oos_start=args.oos_start,
        min_train=args.min_train,
        max_origins=args.max_origins,
        trees=args.trees,
        rounds=args.rounds,
        policies=args.policies,
    )
    if not summary.empty:
        print(summary.to_string(index=False))
    print(f"wrote {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
