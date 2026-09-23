"""Review regressions: real validation over in-memory bytes; no model or network runs."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from . import run
from tools.forecast_updates_r33 import workflow as w
from tools.live_bundle_r32 import adapter
from models.path_inputs import compound_path

CLOCK = datetime(2026, 9, 22, 18, 5, tzinfo=timezone.utc)
ORIGIN = "2026-09"
LONG_HISTORY = "data/research_r14/food/coverage_extension/czso_cpi_1995_2025.csv"
H0_RUN = run.ROOT / "output/forecast_updates_r33/runs/20260922T175001527361Z_7c5389d7016a"
BUNDLE = run.ROOT / "output/forecast_updates_r33/current_bundle_20260922_v2"


def encoded(value):
    return w.encoded(value)


@contextmanager
def memory_files(files):
    """Mock byte transport only; hash, schema, date and economic checks stay real."""
    files = {Path(path).resolve(): raw for path, raw in files.items()}
    read_bytes, is_file, exists = Path.read_bytes, Path.is_file, Path.exists
    def read(path):
        path = path.resolve()
        return files[path] if path in files else read_bytes(path)
    def file_exists(path):
        return path.resolve() in files or is_file(path)
    def any_exists(path):
        path = path.resolve()
        return path in files or any(p.is_relative_to(path) for p in files) or exists(path)
    with patch.object(Path, "read_bytes", read), patch.object(Path, "is_file", file_exists), patch.object(Path, "exists", any_exists):
        yield


class ReviewBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h0 = w.load_run(H0_RUN)
        cls.calendar, cls.calendar_info = adapter.load_calendar(
            run.ROOT / "data/release_calendar_cz_cpi.csv", H0_RUN / "live_calendar.csv",
            adapter.decision_clock(CLOCK))
        cls.actual_source_hashes = {
            p.relative_to(run.ROOT).as_posix(): run.sha(p)
            for folder in (BUNDLE, H0_RUN) for p in folder.rglob("*") if p.is_file()
        }

    def setUp(self):
        self.root = (run.ROOT / "tools/current_path_r34/__review_memory__").resolve()
        self.input_dir, self.record_dir = self.root / "inputs", self.root / "record"
        index = pd.period_range("2015-01", "2026-08", freq="M")
        self.levels = pd.DataFrame(
            {"agri4": np.arange(len(index)) / 10,
             "food_ppi": np.arange(len(index)) / 10,
             "food": np.arange(len(index)) / 10}, index=index)
        # August farm prices are legitimately not due on September 22.
        self.levels.loc["2026-08", "agri4"] = np.nan
        self.available = pd.DataFrame("2026-09-20T12:00:00+00:00",
                                      index=index, columns=self.levels.columns)
        self.available.loc["2026-08", "agri4"] = None
        headline_index = pd.period_range("2014-12", "2026-08", freq="M")
        self.headline_levels = pd.Series(
            100. * 1.001 ** np.arange(len(headline_index)), index=headline_index,
            name="headline_level")
        self.history = (100. * (self.headline_levels / self.headline_levels.shift(1) - 1)).dropna().rename("headline_mm")
        self.pump = pd.DataFrame(
            {"gross_petrol95": [35., 35.], "gross_diesel": [34., 34.]},
            index=pd.to_datetime(["2026-09-07", "2026-09-14"]))
        def source_manifest(folder):
            raw = (folder / "MANIFEST.json").read_bytes()
            manifest = json.loads(raw)
            return dict(path=str(folder.resolve()), manifest_sha256=w.sha(raw),
                        files=manifest.get("files", manifest.get("sha256")))
        capture_dir = self.root / "capture"
        source_series = {
            "CZCPF Index": 100. * np.exp(self.levels.food / 100.),
            "CZPPA10M Index": pd.Series(100. * np.expm1(.001), index=index),
            "CZCPI Index": self.headline_levels.reindex(index),
        }
        capture_history = pd.concat([pd.DataFrame({
            "ticker": ticker, "observation_date": index.to_timestamp("M").strftime("%Y-%m-%d"),
            "value": series.to_numpy()}) for ticker, series in source_series.items()], ignore_index=True)
        capture = {
            "request.json": encoded(dict(retrieved_at="2026-09-22T17:59:00+00:00",
                completed_at="2026-09-22T18:00:00+00:00",
                history_start="2015-01-01", end_date="2026-09-21")),
            "history_long.csv": capture_history.to_csv(index=False).encode(),
        }
        for ticker, rows in capture_history.groupby("ticker"):
            capture["raw/" + ticker.replace(" ", "_") + ".csv"] = rows[
                ["observation_date", "value"]].rename(columns={"value": "PX_LAST"}).to_csv(index=False).encode()
        capture_hashes = {name: w.sha(raw) for name, raw in capture.items()}
        capture["MANIFEST.json"] = encoded({"sha256": capture_hashes})
        self.support_files = {capture_dir / name: raw for name, raw in capture.items()}
        current_prov = json.loads((BUNDLE / "provenance.json").read_bytes())
        self.provenance = {
            "schema_version": 1, "kind": "observed_current_path_inputs",
            "target": ORIGIN, "origin": ORIGIN,
            "as_of": "2026-09-22T18:00:00+00:00",
            "prepared_at": "2026-09-22T18:01:00+00:00",
            "available_from": "2026-09-22T18:00:00+00:00",
            "capture_completed_at": "2026-09-22T18:00:00+00:00",
            "sources": {
                "base_bundle": source_manifest(run.ROOT / "data/bloomberg_inputs_20260922_foodppi"),
                "current_bundle": source_manifest(BUNDLE),
                "bloomberg_capture": dict(path=str(capture_dir),
                    manifest_sha256=w.sha(capture["MANIFEST.json"]), files=capture_hashes),
                "farm": dict(path=current_prov["farm_source"]["path"],
                    sha256=current_prov["farm_source"]["sha256"],
                    completed_at=current_prov["prepared_at"], new_capture=False,
                    source="Hash-pinned R33 farm observations"),
            },
            "readiness": {"ready": True, "required_consumer_through": "2026-08"},
            "note": "Synthetic byte fixture; never a calculated model output.",
        }

    def helper(self, name):
        function = getattr(run, name, None)
        self.assertTrue(callable(function), name + " must be implemented")
        return function

    def input_files(self):
        frames = {"food_levels.csv": self.levels, "food_available.csv": self.available,
                  "pump_weekly.csv": self.pump, "headline_history.csv": self.history.to_frame(),
                  "headline_levels.csv": self.headline_levels.to_frame()}
        payloads = {name: frame.to_csv(index_label="date" if name == "pump_weekly.csv" else "period").encode()
                    for name, frame in frames.items()}
        payloads["provenance.json"] = encoded(self.provenance)
        payloads["MANIFEST.json"] = encoded({
            "schema_version": 1,
            "files": {name: w.sha(raw) for name, raw in payloads.items()}})
        return {**self.support_files, **{self.input_dir / name: raw for name, raw in payloads.items()}}

    def fixture_record(self):
        point = self.h0["forecast"]["point"]
        weights = {"core": .5, "food": .2, "administered": .15, "alc": .1, "fuel": .05}
        rows = []
        for h in range(13):
            row = dict(origin=ORIGIN, h=h, target=str(pd.Period(ORIGIN, "M") + h),
                       as_of_utc=CLOCK.isoformat(), model=run.PRIMARY,
                       mm_forecast=point if h == 0 else .2, status="estimated")
            for block in run.BLOCKS:
                weight = weights.get("alc" if block == "alcohol_tobacco" else block, 1.)
                row["contribution_" + block] = (self.h0["forecast"]["components"][block]
                    if h == 0 else (0. if block == "wedge" else .2 * weight))
                row["value_" + block] = np.nan if h == 0 else (0. if block == "wedge" else .2)
            row.update({"weight_" + name: np.nan if h == 0 else value for name, value in weights.items()})
            rows.append(row)
        table = pd.DataFrame(rows)
        self.recompound(table, point)
        metadata = dict(
            schema="current-path-r34/v1", mode="prospective", origin=ORIGIN,
            as_of=CLOCK.isoformat(), recorded_at=CLOCK.isoformat(),
            completed_at=(CLOCK + timedelta(seconds=1)).isoformat(),
            primary_model=run.PRIMARY, h0=point, h0_as_of=self.h0["as_of"],
            h0_run=H0_RUN.relative_to(run.ROOT).as_posix(),
            path_input_directory=self.input_dir.relative_to(run.ROOT).as_posix(),
            nowcast_bundle=BUNDLE.relative_to(run.ROOT).as_posix(),
            first_release=self.h0["forecast"]["first_release"],
            available_models=[run.PRIMARY], headline_history_end="2026-08",
            calendar=self.calendar_info, source_provenance=self.provenance,
            note="Complete synthetic validator fixture; no model was run.")
        return metadata, table

    def recompound(self, table, point):
        mapping = dict(zip(table.h, table.mm_forecast))
        table["yy_exante"] = [compound_path(self.history, mapping, ORIGIN, h, point) for h in range(13)]

    def archive_files(self, metadata, table):
        files = self.input_files()
        sources = dict(self.actual_source_hashes)
        sources.update({p.relative_to(run.ROOT).as_posix(): w.sha(raw) for p, raw in files.items()})
        code = {name: run.sha(run.ROOT / name) for name in ("tools/current_path_r34/run.py", LONG_HISTORY)}
        base = table.copy()
        base["model"] = "STATE_FAST_R15"
        payloads = {
            ".gitattributes": b"* -text\n",
            "snapshot.json": encoded(metadata), "path.csv": table.to_csv(index=False).encode(),
            "base_paths.csv": base.to_csv(index=False).encode(),
            "headline_history.csv": self.history.to_csv(index_label="period").encode(),
            "diagnostics.json": encoded({"base": {"fuel": {"stale": False}},
                                         "primary_model": run.PRIMARY}),
        }
        payloads["manifest.json"] = encoded({
            "schema": "current-path-r34/manifest-v1", "inputs": sources, "code": code,
            "outputs": {name: w.sha(raw) for name, raw in payloads.items()}})
        files.update({self.record_dir / name: raw for name, raw in payloads.items()})
        return files

    def load_fixture(self, metadata, table):
        with memory_files(self.archive_files(metadata, table)):
            return run.load_record(self.record_dir)

    def assert_valid_record(self):
        metadata, table = self.fixture_record()
        loaded, result, _ = self.load_fixture(metadata, table)
        self.assertEqual(loaded["h0"], self.h0["forecast"]["point"])
        self.assertEqual(len(result), 13)
        return metadata, table

    def test_load_inputs_accepts_actual_aware_datetime(self):
        with memory_files(self.input_files()):
            string_result = run.load_inputs(self.input_dir, ORIGIN, CLOCK.isoformat())
            try:
                datetime_result = run.load_inputs(self.input_dir, ORIGIN, CLOCK)
            except (TypeError, ValueError) as exc:
                self.fail("The actual record() datetime must load like its ISO string: " + str(exc))
        pd.testing.assert_frame_equal(datetime_result[0], string_result[0])
        pd.testing.assert_series_equal(datetime_result[3], string_result[3])

    def test_freshness_allows_legitimate_farm_publication_lag(self):
        self.helper("freshness_gate")(self.levels, self.available, ORIGIN, CLOCK.isoformat(), self.calendar)

    def test_freshness_rejects_stale_farm_with_current_food(self):
        gate = self.helper("freshness_gate")
        gate(self.levels, self.available, ORIGIN, CLOCK.isoformat(), self.calendar)
        self.levels.loc["2026-01":, "agri4"] = np.nan
        with self.assertRaisesRegex(ValueError, "(?i)stale|fresh|agri"):
            gate(self.levels, self.available, ORIGIN, CLOCK.isoformat(), self.calendar)

    def test_freshness_rejects_stale_ppi_with_current_food(self):
        gate = self.helper("freshness_gate")
        gate(self.levels, self.available, ORIGIN, CLOCK.isoformat(), self.calendar)
        self.levels.loc["2026-01":, "food_ppi"] = np.nan
        with self.assertRaisesRegex(ValueError, "(?i)stale|fresh|ppi"):
            gate(self.levels, self.available, ORIGIN, CLOCK.isoformat(), self.calendar)

    def test_record_sources_pins_exact_long_food_history(self):
        sources = self.helper("record_sources")()
        self.assertIn(LONG_HISTORY, sources)
        self.assertEqual(sources[LONG_HISTORY], run.sha(run.ROOT / LONG_HISTORY))

    def test_load_record_accepts_complete_positive_control(self):
        self.assert_valid_record()

    def test_load_record_rejects_wrong_h0_even_when_arithmetic_reconciles(self):
        metadata, table = self.assert_valid_record()
        metadata["h0"] += .1
        table.loc[0, "mm_forecast"] = metadata["h0"]
        table.loc[0, "contribution_core"] += .1
        self.recompound(table, metadata["h0"])
        run.validate_table(table, metadata["h0"])
        with self.assertRaisesRegex(ValueError, "(?i)h0|nowcast|anchor"):
            self.load_fixture(metadata, table)

    def test_load_record_rejects_changed_h0_split_with_same_total(self):
        metadata, table = self.assert_valid_record()
        table.loc[0, "contribution_core"] += .1
        table.loc[0, "contribution_food"] -= .1
        run.validate_table(table, metadata["h0"])
        with self.assertRaisesRegex(ValueError, "(?i)h0|nowcast|contribution"):
            self.load_fixture(metadata, table)

    def test_load_record_rejects_future_decision_clock(self):
        metadata, table = self.assert_valid_record()
        future = "2099-01-01T00:00:00+00:00"
        metadata["as_of"] = future
        table["as_of_utc"] = future
        with self.assertRaisesRegex(ValueError, "(?i)future|clock|record|as.of"):
            self.load_fixture(metadata, table)

    def test_load_record_rejects_completion_before_recording(self):
        metadata, table = self.assert_valid_record()
        metadata["completed_at"] = (CLOCK - timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "(?i)clock|complet|record|order"):
            self.load_fixture(metadata, table)


if __name__ == "__main__":
    unittest.main()

