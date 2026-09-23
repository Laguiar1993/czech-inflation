"""Prepare observed R34 path inputs without fitting a model or changing frozen data.

CSV food columns follow the export contract. Returned model frames use
agri4, food_ppi, food, as required by models.food_stable_r14b.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tools.live_bundle_r32.adapter import checked_files, required, target_month
from tools.bloomberg_lane.food_ppi_variant import cumulated_level
from tools.r14_food.prepare_inputs import PRODUCTS

ROOT = Path(__file__).resolve().parents[2]
BASE = pd.Period("2015-01", "M")
MODEL_COLUMNS = ["agri4", "food_ppi", "food"]
EXPORT_COLUMNS = ["food", "food_ppi", "agri4"]
TICKERS = ("CZCPI Index", "CZCPF Index", "CZPPA10M Index")
OUTPUT_FILES = ("food_levels.csv", "food_available.csv", "pump_weekly.csv",
                "headline_history.csv", "headline_levels.csv", "provenance.json")


def _now():
    return pd.Timestamp(datetime.now(timezone.utc))


def _clock(value, label="clock"):
    try:
        result = pd.Timestamp(value)
        if pd.isna(result) or result.tzinfo is None:
            raise ValueError()
        return result.tz_convert("UTC")
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label} requires an explicit timezone-aware timestamp") from exc


def _decision(value):
    clock = _clock(value, "as_of")
    if clock > _now():
        raise ValueError("future as_of is not allowed for observed input preparation")
    return clock


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _manifest(folder):
    folder = Path(folder).resolve()
    raw = (folder / "MANIFEST.json").read_bytes()
    m = json.loads(raw)
    hashes = m.get("files", m.get("sha256"))
    files = checked_files(folder, hashes)
    return files, {"path": str(folder), "manifest_sha256": _sha(raw),
                   "files": hashes}


def _csv(data):
    return pd.read_csv(io.BytesIO(data), encoding="utf-8", float_precision="round_trip")


def _monthly(data, name, columns=None, numeric=True):
    frame = _csv(data).set_index("period")
    frame.index = pd.PeriodIndex(frame.index, freq="M", name="period")
    if (frame.empty or frame.index.hasnans or frame.index.has_duplicates
            or not frame.index.is_monotonic_increasing):
        raise ValueError(f"{name}: empty, duplicate or unordered monthly index")
    if columns is not None:
        if not set(columns).issubset(frame):
            raise ValueError(f"{name}: missing columns {columns}")
        frame = frame[list(columns)]
    if numeric:
        frame = frame.apply(pd.to_numeric, errors="raise")
        if np.isinf(frame.to_numpy(dtype=float)).any():
            raise ValueError(f"{name}: infinite values")
    return frame


def _complete(series, months, label):
    x = series.reindex(months)
    if not np.isfinite(x.to_numpy(dtype=float)).all():
        missing = list(map(str, months[~np.isfinite(x.to_numpy(dtype=float))]))
        raise ValueError(f"{label}: missing required coverage {missing}")
    return x


def _positive(series, label, ratio=False):
    x = series.to_numpy(dtype=float)
    if not np.isfinite(x).all() or (x <= (-100 if ratio else 0)).any():
        raise ValueError(f"{label}: finite positive {'gross ratios' if ratio else 'levels'} required")


def _overlap(new, old, label):
    aligned = _complete(new, old.index, label)
    error = float((aligned-old).abs().max())
    if not np.isfinite(error) or error > 1e-9:
        raise ValueError(f"{label}: baseline overlap conflict ({error}); frozen training rows cannot change")
    return error


def _availability(frame, levels, clock):
    if not frame.index.equals(levels.index) or list(frame) != list(levels):
        raise ValueError("availability calendar/schema differs from food levels")
    result = frame.copy()
    for col in frame:
        values = []
        for month, value in frame[col].items():
            if pd.isna(value):
                if pd.notna(levels.loc[month, col]):
                    raise ValueError(f"{col} {month}: observed value missing availability")
                values.append(pd.NaT)
                continue
            if pd.isna(levels.loc[month, col]):
                raise ValueError(f"{col} {month}: availability exists without observation")
            stamp = _clock(value, f"{col} availability")
            if stamp > clock:
                raise ValueError(f"{col} {month}: availability exceeds requested clock")
            if stamp.tz_convert("Europe/Prague").tz_localize(None).to_period("M") <= month:
                raise ValueError(f"{col} {month}: monthly observation available before month completed")
            values.append(stamp)
        result[col] = pd.to_datetime(values, utc=True)
    return result


def _capture(files, origin, clock):
    request = json.loads(required(files, "request.json"))
    started = _clock(request["retrieved_at"], "capture start")
    completed = _clock(request["completed_at"], "capture completion")
    if started > completed or completed > clock:
        raise ValueError("capture completion not available by requested clock")
    data = _csv(required(files, "history_long.csv"))
    if not {"ticker", "observation_date", "value"}.issubset(data):
        raise ValueError("capture missing long-form schema")
    data["date"] = pd.to_datetime(data.observation_date)
    if (data.date.isna().any() or data.date.dt.tz is not None
            or (data.date != data.date.dt.normalize()).any()):
        raise ValueError("capture requires naive dated observations")
    data["period"] = data.date.dt.to_period("M")
    if data.duplicated(["ticker", "period"]).any():
        raise ValueError("duplicate capture ticker/month")
    if (data.period >= origin).any() or (data.date > clock.tz_convert("Europe/Prague").tz_localize(None)).any():
        raise ValueError("future/origin realised observation in path capture")
    if (data.date > pd.Timestamp(request["end_date"])).any():
        raise ValueError("capture observation exceeds requested end date")
    data.value = pd.to_numeric(data.value, errors="raise")
    if not np.isfinite(data.value).all():
        raise ValueError("capture nonfinite values")
    series = {}
    for ticker, rows in data.groupby("ticker"):
        if not rows.date.is_monotonic_increasing:
            raise ValueError(f"{ticker}: unordered capture")
        raw = _csv(required(files, "raw/" + ticker.replace(" ", "_") + ".csv"))
        if list(raw.columns) != ["observation_date", "PX_LAST"]:
            raise ValueError(f"{ticker}: raw capture schema")
        if (list(pd.to_datetime(raw.observation_date)) != list(rows.date)
                or not np.array_equal(raw.PX_LAST.to_numpy(dtype=float), rows.value.to_numpy(dtype=float))):
            raise ValueError(f"{ticker}: raw capture/history mismatch")
        series[ticker] = pd.Series(rows.value.to_numpy(dtype=float),
                                   index=pd.PeriodIndex(rows.period, freq="M"))
    months = pd.period_range(BASE, origin-1, freq="M")
    for ticker in TICKERS:
        if ticker not in series:
            raise ValueError(f"missing required ticker {ticker}")
        series[ticker] = _complete(series[ticker], months, ticker)
        _positive(series[ticker], ticker, ratio=ticker == "CZPPA10M Index")
    return series, completed, request


def _current(files, origin, clock):
    prov = json.loads(required(files, "provenance.json"))
    if prov.get("target") != str(origin):
        raise ValueError("current bundle target differs from path origin")
    stamps = [_clock(prov[key], f"current {key}") for key in ("as_of", "prepared_at")]
    stamps.append(_clock(prov["snapshot"]["completed_at"], "current capture completion"))
    stamps += [_clock(row["available_from"], "manual availability") for row in prov.get("manual_rows", [])]
    if max(stamps) > clock:
        raise ValueError("current bundle capture/manual inputs not available by requested clock")
    names = {
        "target_headline_cpi_mm.csv": ["cpi_mm"], "cnb_core_mm.csv": ["core"],
        "cnb_regulated_mm.csv": ["regulated"], "alcohol_tobacco.csv": ["alcohol_tobacco"],
        "component_food_fuel_mm.csv": ["food", "fuel"],
    }
    required_months = pd.period_range(origin-12, origin-1, freq="M")
    coverage = {}
    for name, columns in names.items():
        d = _monthly(required(files, "nowcast/"+name), name)
        if list(d) == ["reg"]:
            d = d.rename(columns={"reg": "regulated"})
        for col in columns:
            if col not in d:
                raise ValueError(f"{name}: missing {col}")
            values = _complete(d[col], required_months, col)
            _positive(values, col, ratio=True)
            if d.loc[d.index >= origin, col].notna().any():
                raise ValueError(f"{col}: future/origin realised observations")
            coverage[col] = str(d[col].last_valid_index())
    return prov, max(stamps), coverage


def _farm(farm_raw, current_prov, origin, clock):
    if farm_raw is None:
        path = Path(current_prov["farm_source"]["path"])
        raw = path.read_bytes()
        if _sha(raw) != current_prov["farm_source"]["sha256"]:
            raise ValueError("farm source hash mismatch")
        completed = _clock(current_prov["prepared_at"], "frozen farm availability")
        source = {"path": str(path.resolve()), "sha256": _sha(raw),
                  "source": "CZSO CEN0203B; preserved R33 archive",
                  "completed_at": completed.isoformat(), "new_capture": False}
    else:
        path = Path(farm_raw).resolve()
        meta_path = path.with_name(path.name + ".metadata.json")
        meta_raw = meta_path.read_bytes()
        meta = json.loads(meta_raw)
        raw = path.read_bytes()
        if _sha(raw) != meta["sha256"]:
            raise ValueError("farm capture hash mismatch")
        completed = _clock(meta["completed_at"], "farm capture completion")
        if _clock(meta["retrieved_at"]) > completed:
            raise ValueError("farm capture clocks reversed")
        source = {"path": str(path), "sha256": _sha(raw), "source": meta["source"],
                  "metadata_path": str(meta_path), "metadata_sha256": _sha(meta_raw),
                  "completed_at": completed.isoformat(), "new_capture": True}
    if completed > clock:
        raise ValueError("farm capture not available by requested clock")
    d = _csv(raw)
    d = d[d.CASMKMQR.astype(str).str.fullmatch(r"\d{4}-\d{2}") &
          d["UZ02HU.KRAJ"].isna() & d.Reprezentant.isin(PRODUCTS)]
    if d.duplicated(["CASMKMQR", "Reprezentant"]).any():
        raise ValueError("duplicate national farm-product month")
    p = d.pivot(index="CASMKMQR", columns="Reprezentant", values="Hodnota").reindex(columns=PRODUCTS)
    p.index = pd.PeriodIndex(p.index, freq="M")
    if (p.index >= origin).any():
        raise ValueError("future/origin realised farm month")
    p = p.loc[p.index >= BASE].sort_index()
    if p.empty or BASE not in p.index:
        raise ValueError("farm Jan2015 baseline missing")
    calendar = pd.period_range(BASE, p.index.max(), freq="M")
    p = p.reindex(calendar)
    if not np.isfinite(p.to_numpy(dtype=float)).all() or (p <= 0).any().any():
        raise ValueError("farm requires complete positive four-product observations; no partial mean")
    # Exact accepted R14 construction: equal average of four log-relative prices.
    levels = (100*np.log(p / p.loc[BASE])).mean(axis=1)
    source.update(products=list(PRODUCTS), first=str(p.index.min()), last=str(p.index.max()),
                  transformation="mean(100*log(each physical price / same product Jan2015 price)); four products")
    return levels, completed, source


def _pump(files, clock):
    d = _csv(required(files, "market/history_long.csv"))
    d = d[d.ticker.isin(["ECOBETCZ Index", "ECOBOTCZ Index"])].copy()
    d["date"] = pd.to_datetime(d.observation_date)
    if (d.empty or d.date.isna().any() or d.date.dt.tz is not None
            or d.duplicated(["ticker", "date"]).any()):
        raise ValueError("pump missing or duplicate/invalid observations")
    if (d.date > clock.tz_convert("Europe/Prague").tz_localize(None)).any():
        raise ValueError("future pump observations")
    _positive(d.value, "gross pump prices")
    result = {}
    for ticker, col in [("ECOBETCZ Index", "gross_petrol95"), ("ECOBOTCZ Index", "gross_diesel")]:
        s = d[d.ticker == ticker].sort_values("date").set_index("date").value
        if s.empty:
            raise ValueError(f"missing pump ticker {ticker}")
        s.index = s.index - pd.to_timedelta(s.index.dayofweek, unit="D")
        result[col] = s[~s.index.duplicated(keep="last")]/1000
    panel = pd.DataFrame(result).sort_index()
    panel = panel.loc[panel.index+pd.Timedelta(days=7) <= clock.tz_convert("Europe/Prague").tz_localize(None)]
    if panel.empty or not np.isfinite(panel.to_numpy()).all():
        raise ValueError("pump pairs missing; cannot silently drop current gross prices")
    # Confirm the portable R33 weekly frame agrees; never include its net/tax columns.
    weekly = _csv(required(files, "nowcast/fuel_weekly_variant_b.csv")).set_index("date")
    weekly.index = pd.to_datetime(weekly.index)
    if weekly.index.has_duplicates or not weekly.index.is_monotonic_increasing or (weekly.index.dayofweek != 0).any():
        raise ValueError("R33 weekly pump index invalid")
    for src, dest in [("petrol95", "gross_petrol95"), ("diesel", "gross_diesel")]:
        known = weekly[src].dropna()
        if not np.allclose(panel[dest].reindex(known.index), known, rtol=0, atol=1e-10):
            raise ValueError("R33 weekly pump frame differs from captured gross source")
    return panel


def _frames_valid(frames, origin, clock):
    levels = frames["food_levels"]
    calendar = pd.period_range(BASE, origin-1, freq="M")
    if not levels.index.equals(calendar) or list(levels) != MODEL_COLUMNS:
        raise ValueError("food calendar/schema must be contiguous Jan2015 through origin-1")
    for col in MODEL_COLUMNS:
        s = levels[col].dropna()
        if s.empty or not s.index.equals(pd.period_range(BASE, s.index.max(), freq="M")):
            raise ValueError(f"{col}: internal missing months")
        if abs(s.iloc[0]) > 1e-9:
            raise ValueError(f"{col}: Jan2015 baseline must be zero")
        if col != "agri4":
            _complete(levels[col], calendar, col)
    frames["food_available"] = _availability(frames["food_available"], levels, clock)
    headline = frames["headline_history"].headline_mm
    if (headline.index >= origin).any():
        raise ValueError("future/origin headline history")
    _positive(_complete(headline, pd.period_range(origin-12, origin-1, freq="M"), "headline"), "headline", ratio=True)
    hl = frames["headline_levels"].headline_level
    _positive(_complete(hl, pd.period_range(origin-13, origin-1, freq="M"), "headline levels"), "headline levels")
    if (hl.index >= origin).any():
        raise ValueError("future headline levels")
    exact = 100*(hl/hl.shift(1)-1)
    idx = exact.dropna().index
    if not np.allclose(headline.reindex(idx), exact.loc[idx], atol=1e-12, rtol=0):
        raise ValueError("headline history does not reconcile to level ratios")
    p = frames["pump_weekly"]
    if (list(p) != ["gross_petrol95", "gross_diesel"] or p.empty or p.index.has_duplicates
            or not p.index.is_monotonic_increasing or (p.index.dayofweek != 0).any()
            or p.index.tz is not None or (p.index != p.index.normalize()).any()):
        raise ValueError("pump schema/index must be unique Monday gross pairs")
    if not np.isfinite(p.to_numpy()).all() or (p <= 0).any().any():
        raise ValueError("pump prices must be positive and finite")
    if (p.index+pd.Timedelta(days=7) > clock.tz_convert("Europe/Prague").tz_localize(None)).any():
        raise ValueError("pump week not available by clock")


def prepare(base_bundle, current_bundle, capture, output, *, origin, as_of, farm_raw=None):
    """Write a new immutable prepared-input directory and return validated frames.

    farm_raw, when supplied, requires adjacent <filename>.metadata.json with
    source, sha256, retrieved_at, completed_at. Omitted means hash-verified R33 raw.
    All paths may be absolute or relative to the caller's working directory.
    """
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite prepared inputs: {output}")
    clock, origin = _decision(as_of), target_month(origin)
    if origin != clock.tz_convert("Europe/Prague").tz_localize(None).to_period("M"):
        raise ValueError("observed current-input origin must match requested clock month")
    baseline, bsource = _manifest(base_bundle)
    current, csource = _manifest(current_bundle)
    captured, source = _manifest(capture)
    raw, capture_time, request = _capture(captured, origin, clock)
    current_prov, current_time, consumer_coverage = _current(current, origin, clock)
    farm, farm_time, farm_source = _farm(farm_raw, current_prov, origin, clock)
    old = _monthly(required(baseline, "path/food_log_levels.csv"), "baseline food", MODEL_COLUMNS)
    if (old.index.max() >= origin or not old.index.equals(pd.period_range(BASE, old.index.max(), freq="M"))
            or not np.isfinite(old.to_numpy()).all()):
        raise ValueError("baseline food history invalid or future")
    old_available = _monthly(required(baseline, "path/food_available_from.csv"),
                             "baseline availability", MODEL_COLUMNS, numeric=False)
    old_available = _availability(old_available, old, clock)
    calendar = pd.period_range(BASE, origin-1, freq="M")
    food = 100*np.log(raw["CZCPF Index"]/raw["CZCPF Index"].loc[BASE])
    ppi = cumulated_level(raw["CZPPA10M Index"])
    errors = {col: _overlap(s, old[col], col)
              for col, s in [("food", food), ("food_ppi", ppi), ("agri4", farm)]}
    levels = old.reindex(calendar).copy()
    available = old_available.reindex(calendar).copy()
    new = calendar[calendar > old.index.max()]
    for col, s, stamp in [("food", food, capture_time), ("food_ppi", ppi, capture_time),
                          ("agri4", farm, farm_time)]:
        idx = new.intersection(s.index)
        levels.loc[idx, col] = s.loc[idx]
        available.loc[idx, col] = stamp
    farm_last = farm.index.max()
    if farm_last < origin-1:
        next_due = ((farm_last+2).to_timestamp()+pd.Timedelta(days=25)).tz_localize("Europe/Prague")
        if clock >= next_due:
            raise ValueError("farm coverage is overdue under accepted availability rule; retrieve official data")
        farm_status = "ragged_not_due_under_accepted_model_rule"
        next_expected = next_due.isoformat()
    else:
        farm_status, next_expected = "observed_through_required_month", None
    headline_level = raw["CZCPI Index"].rename("headline_level")
    exact = (100*(headline_level/headline_level.shift(1)-1)).dropna()
    history = _monthly(required(baseline, "path/headline_history.csv"), "headline baseline", ["headline_mm"])
    if history.loc[history.index >= origin].notna().any().any():
        raise ValueError("future/origin baseline headline observations")
    history = history.reindex(history.index.union(exact.index)).sort_index()
    history.loc[exact.index, "headline_mm"] = exact
    pumps = _pump(current, clock)
    frames = {"food_levels": levels, "food_available": available, "pump_weekly": pumps,
              "headline_history": history, "headline_levels": headline_level.to_frame()}
    _frames_valid(frames, origin, clock)
    last = origin-1
    exact_yy = float(100*(headline_level.loc[last]/headline_level.loc[last-12]-1))
    published = raw.get("CZCPYOY Index")
    published_yy = float(published.loc[last]) if published is not None and last in published.index else None
    annual_difference = exact_yy-published_yy if published_yy is not None else None
    # One-decimal levels induce a ratio interval; do not pretend full-precision CPI is observed.
    one_decimal = bool(np.allclose(headline_level*10, np.round(headline_level*10), atol=1e-9, rtol=0))
    half_unit = .05 if one_decimal else 0.
    a, b = float(headline_level.loc[last]), float(headline_level.loc[last-12])
    interval = [100*((a-half_unit)/(b+half_unit)-1), 100*((a+half_unit)/(b-half_unit)-1)]
    if published_yy is not None and not (interval[0]-.05 <= published_yy <= interval[1]+.05):
        raise ValueError("headline level ratio cannot reconcile to published annual rate within source precision")
    available_from = max(capture_time, current_time, farm_time,
                         *[frames["food_available"][c].max() for c in MODEL_COLUMNS])
    prov = {
        "schema_version": 1, "kind": "observed_current_path_inputs",
        "origin": str(origin), "target": str(origin), "as_of": clock.isoformat(),
        "prepared_at": _now().isoformat(), "available_from": available_from.isoformat(),
        "capture_completed_at": capture_time.isoformat(),
        "sources": {"base_bundle": bsource, "current_bundle": csource,
                    "bloomberg_capture": source, "farm": farm_source},
        "definitions": {
            "food": "100*log(CZCPF level / Jan2015 level); preserve accepted historical rows",
            "food_ppi": "cumulated 100*log1p(CZPPA10M/100), subtract Jan2015 cumulative level",
            "agri4": farm_source["transformation"],
            "headline": "exact ratios of available CZCPI levels; replaces rounded m/m only for compounding, not h0",
            "pump": "R33 EC gross observations from Bloomberg, CZK/1000 litres divided by 1000; Monday of source week",
            "availability": "new observations at retrieval completion; old reconstructed training clocks preserved",
        },
        "baseline_preserved_through": str(old.index.max()), "baseline_overlap_max_abs": errors,
        "consumer_coverage": consumer_coverage,
        "coverage": {c: {"first": str(levels[c].first_valid_index()),
                          "last": str(levels[c].last_valid_index()),
                          "last_available_from": available.loc[levels[c].last_valid_index(), c].isoformat()}
                     for c in MODEL_COLUMNS},
        "farm_status": farm_status, "farm_next_model_rule_clock": next_expected,
        "farm_publication_note": "The inherited 26th-next-month clock is a model convention, not a sourced actual release date. A fresh official observed row is usable at retrieval completion.",
        "pump_coverage": {"first": pumps.index.min().date().isoformat(),
                          "last": pumps.index.max().date().isoformat(), "rows": len(pumps)},
        "headline_reconciliation": {
            "month": str(last), "level": a, "year_ago_level": b,
            "exact_level_ratio_mm": float(exact.loc[last]),
            "exact_level_ratio_yy": exact_yy, "published_rounded_yy": published_yy,
            "difference_pp": annual_difference, "level_precision": "one decimal" if one_decimal else "captured precision",
            "level_rounding_yy_interval": interval,
            "ratio_history_replaced_from": str(exact.index.min()),
            "ratio_history_replaced_through": str(exact.index.max()),
            "definition": "Exact arithmetic on captured rounded index levels; not an assertion of unrounded official inflation.",
        },
        "readiness": {"ready": True, "required_consumer_through": str(origin-1)},
    }
    # Validation precedes exclusive creation. A failure never overwrites or promotes prior inputs.
    output.mkdir(parents=True, exist_ok=False)
    (output/".gitattributes").write_text("* -text\n", encoding="utf-8")
    levels[EXPORT_COLUMNS].to_csv(output/"food_levels.csv", index_label="period", encoding="utf-8")
    export_available = frames["food_available"][EXPORT_COLUMNS].copy()
    for col in export_available:
        export_available[col] = export_available[col].map(lambda x: x.isoformat(timespec="microseconds") if pd.notna(x) else None)
    export_available.to_csv(output/"food_available.csv", index_label="period", encoding="utf-8")
    pumps.to_csv(output/"pump_weekly.csv", index_label="date", encoding="utf-8")
    history.to_csv(output/"headline_history.csv", index_label="period", encoding="utf-8")
    headline_level.to_frame().to_csv(output/"headline_levels.csv", index_label="period", encoding="utf-8")
    (output/"provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    hashes = {name: _sha((output/name).read_bytes()) for name in (*OUTPUT_FILES, ".gitattributes")}
    manifest = {"schema_version": 1, "files": hashes}
    (output/"MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    frames.update(provenance=prov, output=output)
    return frames


def load_prepared(output, *, as_of):
    """Validate hashes, all recorded source clocks, and frame contracts on every load."""
    clock = _decision(as_of)
    files, manifest = _manifest(output)
    prov = json.loads(required(files, "provenance.json"))
    origin = target_month(prov["origin"])
    if prov["target"] != str(origin) or prov.get("schema_version") != 1:
        raise ValueError("prepared input provenance schema/target invalid")
    if _clock(prov["available_from"]) > clock or _clock(prov["capture_completed_at"]) > clock:
        raise ValueError("prepared inputs not available by requested clock")
    # Pin the source snapshots as well as the generated CSVs, using verified bytes.
    for name in ("base_bundle", "current_bundle", "bloomberg_capture"):
        recorded = prov["sources"][name]
        source_files, now = _manifest(recorded["path"])
        if now != recorded:
            raise ValueError(f"{name}: source manifest hash changed")
        if name == "current_bundle":
            _current(source_files, origin, clock)
        elif name == "bloomberg_capture":
            _capture(source_files, origin, clock)
    farm = prov["sources"]["farm"]
    if _sha(Path(farm["path"]).read_bytes()) != farm["sha256"]:
        raise ValueError("farm source hash changed")
    if "metadata_path" in farm and _sha(Path(farm["metadata_path"]).read_bytes()) != farm["metadata_sha256"]:
        raise ValueError("farm capture metadata hash changed")
    if _clock(farm["completed_at"]) > clock:
        raise ValueError("farm capture not available by requested clock")
    frames = {
        "food_levels": _monthly(required(files, "food_levels.csv"), "food levels", MODEL_COLUMNS),
        "food_available": _monthly(required(files, "food_available.csv"), "food availability", MODEL_COLUMNS, numeric=False),
        "headline_history": _monthly(required(files, "headline_history.csv"), "headline history", ["headline_mm"]),
        "headline_levels": _monthly(required(files, "headline_levels.csv"), "headline levels", ["headline_level"]),
    }
    pump = _csv(required(files, "pump_weekly.csv")).set_index("date")
    pump.index = pd.DatetimeIndex(pd.to_datetime(pump.index), name="date")
    frames["pump_weekly"] = pump
    _frames_valid(frames, origin, clock)
    frames.update(provenance=prov, output=Path(output).resolve())
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-bundle", type=Path, required=True)
    parser.add_argument("--current-bundle", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--farm-raw", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--as-of", required=True, help="Explicit timezone-aware decision clock")
    args = parser.parse_args()
    result = prepare(args.base_bundle, args.current_bundle, args.capture, args.output,
                     origin=args.origin, as_of=args.as_of, farm_raw=args.farm_raw)
    print(json.dumps({"output": str(result["output"]), **result["provenance"]["readiness"],
                      "available_from": result["provenance"]["available_from"],
                      "coverage": result["provenance"]["coverage"]}, indent=2))


if __name__ == "__main__":
    main()
