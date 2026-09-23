"""Failure-first contracts; fake adapter transport only, real archive/comparison I/O."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if importlib.util.find_spec("tools.forecast_updates_r33.workflow"):
    from tools.forecast_updates_r33 import workflow as w
else:
    w = None

NOW = datetime.now(timezone.utc)
CLOCK = (NOW - timedelta(seconds=30)).isoformat()
OLD = (NOW - timedelta(seconds=90)).isoformat()
FIRST = (NOW + timedelta(days=10)).isoformat()
TARGET = NOW.strftime("%Y-%m")


def adapter(as_of=CLOCK, point=.5, components=None):
    return {
        "schema_version": "live_bundle_r32/v1", "status": "calculated", "command": "run",
        "target": TARGET, "as_of": as_of, "main_model": "HARD_BASE", "variant": "R31C_C123",
        "ready_for_calculation": True, "forecast_available": True, "ready_for_first_release": True,
        "reasons": [], "readiness": {"data_ready": True, "before_first_release": True,
                                     "first_release": FIRST, "reasons": []},
        "runtime": {"ready": True}, "calendar": {"frozen_sha256": "a"*64},
        "provenance": {"bundle_manifest_sha256": "b"*64},
        "forecast": {"version": "test-model-v1", "target": TARGET, "as_of": as_of,
                     "main_model": "HARD_BASE", "points_mm_pct": {"HARD_BASE": point},
                     "main_contributions_pp": components or {"core": .3, "food": .2},
                     "ready_for_first_release": True, "before_first_release": True,
                     "food_diagnostics": {"method": "x13"},
                     "diagnostics": {"hard": {"residual_forest": {"fallback_used": False}}}},
    }


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(w, "R33 bounded recording/comparison implementation is missing")
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.store = Path(self.tmp.name)
        self.bundle = self.store / "bundle"
        self.bundle.mkdir()
        (self.bundle / "MANIFEST.json").write_text('{"files": {}}')

    def run_record(self, report=None, as_of=CLOCK, mode="replay", command="run", **kw):
        report = report if report is not None else adapter(as_of)
        report["provenance"]["bundle_manifest_sha256"] = w.sha((self.bundle / "MANIFEST.json").read_bytes())
        return w.record(self.bundle, TARGET, as_of, mode, store=self.store / "archive",
                        command=command, invoke=lambda *a, **k: copy.deepcopy(report), **kw)

    def compare(self, a, b):
        return w.compare_runs(a["run_directory"], b["run_directory"])

    def test_failed_attempt_preserves_prior_success_byte_exact(self):
        good = self.run_record(as_of=OLD)
        pointer = self.store / "archive/latest_successful.json"
        prior = pointer.read_bytes()
        bad = adapter()
        bad["status"] = "blocked"
        bad["reasons"] = [{"code": "stale_feature"}]
        failure = self.run_record(bad)
        self.assertEqual("blocked", failure["status"])
        self.assertEqual(prior, pointer.read_bytes())
        self.assertTrue((Path(failure["run_directory"]) / "request.json").is_file())
        self.assertEqual("successful", w.load_run(good["run_directory"])["status"])

    def test_naive_clock_recorded_as_failure(self):
        r = self.run_record(as_of="2026-09-22T12:00:00")
        self.assertEqual("blocked", r["status"])
        self.assertIn("timezone", r["reason"])

    def test_future_clock_rejected_even_for_replay(self):
        r = self.run_record(as_of=(NOW + timedelta(days=1)).isoformat())
        self.assertEqual("blocked", r["status"])
        self.assertIn("future", r["reason"])

    def test_archival_ready_flag_cannot_be_prospective(self):
        r = self.run_record(as_of="2026-08-04T23:59:00+02:00", mode="prospective")
        self.assertEqual("blocked", r["status"])
        self.assertIn("stale", r["reason"])

    def test_recorded_after_first_release_blocks_prospective(self):
        report = adapter()
        report["readiness"]["first_release"] = (NOW - timedelta(seconds=10)).isoformat()
        r = self.run_record(report, mode="prospective")
        self.assertEqual("blocked", r["status"])
        self.assertIn("first release", r["reason"])

    def test_readiness_never_publishes_forecast(self):
        report = adapter()
        report.update(status="ready_for_calculation", command="readiness", forecast_available=False)
        report.pop("forecast")
        r = self.run_record(report, command="readiness")
        self.assertEqual("ready", r["status"])
        self.assertIn("no forecast calculated", r["reason"])
        self.assertIsNone(r["forecast"])
        self.assertFalse((self.store / "archive/latest_successful.json").exists())

    def test_nonfinite_or_nonconserving_components_rejected(self):
        for values in ({"core": float("nan")}, {"core": .7}):
            r = self.run_record(adapter(components=values))
            self.assertEqual("blocked", r["status"])

    def test_adapter_target_and_clock_mismatch_rejected(self):
        for key, value in (("target", "2020-01"), ("as_of", OLD), ("variant", "other")):
            report = adapter()
            report[key] = value
            self.assertEqual("blocked", self.run_record(report)["status"])

    def test_fallback_even_with_ready_true_rejected(self):
        report = adapter()
        report["forecast"]["food_diagnostics"]["method"] = "fallback"
        self.assertEqual("blocked", self.run_record(report)["status"])

    def test_immutable_runs_and_manifest_tamper_rejection(self):
        a, b = self.run_record(), self.run_record()
        self.assertNotEqual(a["run_directory"], b["run_directory"])
        p = Path(a["run_directory"]) / "result.json"
        p.write_text(p.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "hash"):
            w.load_run(a["run_directory"])

    def test_two_validated_runs_reconcile(self):
        a = self.run_record(as_of=OLD)
        b = self.run_record(adapter(point=.6, components={"core": .35, "food": .25}))
        out = self.compare(a, b)
        self.assertEqual("ok", out["status"])
        self.assertEqual("replay_revision", out["kind"])
        self.assertAlmostEqual(.1, out["delta"])
        self.assertAlmostEqual(out["delta"], sum(c["delta"] for c in out["components"]) + out["residual"])
        self.assertIn("not causal", out["reason"])
        self.assertEqual({"status","kind","target","model","old_as_of","new_as_of",
                          "old_point","new_point","delta","components","residual","path_changes","reason"},
                         set(out))

    def test_identical_or_reversed_clock_not_revision(self):
        a = self.run_record()
        b = self.run_record(as_of=OLD)
        for x, y in ((a, a), (a, b)):
            result = self.compare(x, y)
            self.assertEqual("unavailable", result["kind"])
            self.assertIn("newer", result["reason"])

    def test_changed_target_model_units_modes_not_revision(self):
        original = self.run_record(as_of=OLD)
        for field, value in (("target", "2026-08"), ("model", "HARD_FULL"),
                             ("units", "yoy_pct"), ("model_identity", "different")):
            a = w.load_run(original["run_directory"])
            b = copy.deepcopy(a)
            b["as_of"] = CLOCK
            b[field] = value
            result = w.compare_records(a, b)
            self.assertEqual("unavailable", result["kind"])
        a = self.run_record(as_of=OLD)
        b = self.run_record(mode="prospective")
        self.assertEqual("unavailable", self.compare(a, b)["kind"])

    def test_missing_blocked_or_corrupt_run_never_revision(self):
        bad = adapter()
        bad["status"] = "blocked"
        a, b = self.run_record(as_of=OLD), self.run_record(bad)
        for path in (b["run_directory"], str(self.store / "absent")):
            self.assertEqual("unavailable", w.compare_runs(a["run_directory"], path)["kind"])

    def test_path_alignment_uses_month_union_and_null_for_unmatched(self):
        def path_file(name, clock, rows):
            p = self.store / name
            p.write_text(json.dumps({"target": TARGET, "model": "HARD_BASE", "units": "mm_pct",
                                    "as_of": clock, "source": "external test fixture", "points": rows}))
            return p
        a = self.run_record(as_of=OLD, path_file=path_file("a.json", OLD, [
            {"target_month": "2027-01", "point": .1, "h": 3},
            {"target_month": "2027-02", "point": .2, "h": 4}]))
        b = self.run_record(path_file=path_file("b.json", CLOCK, [
            {"target_month": "2027-02", "point": .3, "h": 1},
            {"target_month": "2027-03", "point": .4, "h": 2}]))
        out = self.compare(a, b)["path_changes"]
        self.assertEqual(["2027-01", "2027-02", "2027-03"], [p["target_month"] for p in out])
        self.assertIsNone(out[0]["delta"])
        self.assertAlmostEqual(.1, out[1]["delta"])
        self.assertIsNone(out[2]["delta"])

    def test_duplicate_path_month_rejected(self):
        p = self.store / "path.json"
        p.write_text(json.dumps({"target": TARGET,"model":"HARD_BASE","units":"mm_pct","as_of":CLOCK,
                                "source":"test","points":[{"target_month":TARGET,"point":.5}]*2}))
        self.assertEqual("blocked", self.run_record(path_file=p)["status"])

    def test_timeout_retains_pointer_and_attempt(self):
        self.run_record(as_of=OLD)
        pointer = self.store / "archive/latest_successful.json"
        old = pointer.read_bytes()
        def timeout(*a, **kw):
            raise subprocess.TimeoutExpired("adapter", 1)
        r = w.record(self.bundle, TARGET, CLOCK, "replay", store=self.store / "archive", invoke=timeout)
        self.assertEqual("blocked", r["status"])
        self.assertIn("TimeoutExpired", r["reason"])
        self.assertEqual(old, pointer.read_bytes())

    def test_publication_replace_failure_keeps_prior_pointer(self):
        from unittest.mock import patch
        self.run_record(as_of=OLD)
        p = self.store / "archive/latest_successful.json"
        before = p.read_bytes()
        with patch.object(w.os, "replace", side_effect=OSError("simulated disk failure")):
            r = self.run_record()
        self.assertEqual(before, p.read_bytes())
        self.assertEqual("failed", r["publication"]["status"])
        self.assertTrue((Path(r["run_directory"]) / "publication.json").exists())

    def test_prospective_and_replay_do_not_replace_each_other(self):
        self.run_record(mode="prospective")
        self.run_record(as_of=OLD, mode="replay")
        pointer = json.loads((self.store / "archive/latest_successful.json").read_text())
        self.assertEqual(2, len(pointer["entries"]))

    def test_cli_requires_explicit_mode_and_inputs(self):
        result = subprocess.run([w.sys.executable, "-B", "-m", "tools.forecast_updates_r33", "run"],
                                cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(2, result.returncode)
        self.assertEqual("blocked", json.loads(result.stdout)["status"])


    def test_malformed_manifest_returns_unavailable_not_exception(self):
        folder = self.store / "malformed"
        folder.mkdir()
        (folder / "MANIFEST.json").write_text("[]")
        self.assertEqual("unavailable", w.compare_runs(folder, folder)["kind"])

    def test_successful_record_includes_command_for_revalidation(self):
        a = self.run_record(as_of=OLD)
        b = self.run_record()
        self.assertEqual("ok", w.compare_records(w.load_run(a["run_directory"]),
                                                  w.load_run(b["run_directory"]))["status"])

    def test_adapter_command_mismatch_fails_closed(self):
        report = adapter()
        report["command"] = "readiness"
        self.assertEqual("blocked", self.run_record(report)["status"])

    def test_component_name_change_is_not_a_revision(self):
        a = self.run_record(as_of=OLD)
        b = self.run_record(adapter(components={"core":.3,"fuel":.2}))
        self.assertEqual("unavailable", self.compare(a,b)["kind"])

    def test_busy_writer_records_failed_attempt_without_removing_lock(self):
        self.run_record(as_of=OLD)
        lock = self.store / "archive/.refresh.lock"
        lock.write_text("other process")
        pointer = (lock.parent / "latest_successful.json").read_bytes()
        result = self.run_record()
        self.assertEqual("blocked", result["status"])
        self.assertEqual("other process", lock.read_text())
        self.assertEqual(pointer, (lock.parent / "latest_successful.json").read_bytes())

    def test_resealed_inconsistent_forecast_rejected(self):
        result = self.run_record()
        folder = Path(result["run_directory"])
        p = folder / "result.json"
        content = w.read_json(p)
        content["forecast"]["point"] += .01
        p.write_bytes(w.encoded(content))
        manifest = w.read_json(folder / "MANIFEST.json")
        manifest["files"]["result.json"] = w.sha(p.read_bytes())
        (folder / "MANIFEST.json").write_bytes(w.encoded(manifest))
        self.assertEqual("unavailable", w.compare_runs(folder,folder)["kind"])

    def test_slow_run_crossing_release_blocks_prospective(self):
        report = adapter()
        report["readiness"]["first_release"] = (NOW + timedelta(seconds=1)).isoformat()
        request = {"command":"run","as_of":CLOCK,"target":TARGET,"mode":"prospective"}
        inputs = {"bundle_manifest_sha256":"b"*64, "live_calendar_sha256":None, "source_hashes":{}}
        with self.assertRaisesRegex(ValueError, "first release"):
            w.validate_adapter(request, report, NOW.isoformat(),
                               (NOW + timedelta(seconds=2)).isoformat(), inputs)

    def test_prospective_success_has_actual_recording_timestamp(self):
        r = self.run_record(mode="prospective")
        self.assertEqual("successful", r["status"])
        self.assertGreater(w.clock(r["recorded_at"]), w.clock(CLOCK))
        self.assertLessEqual(w.clock(r["completed_at"]), datetime.now(timezone.utc))


    def test_real_process_timeout_is_bounded(self):
        import time
        self.assertTrue(hasattr(w, "bounded_run"), "bounded child-tree runner is missing")
        start = time.monotonic()
        with (self.store/"out").open("wb") as out, (self.store/"err").open("wb") as err:
            with self.assertRaises(subprocess.TimeoutExpired):
                w.bounded_run([w.sys.executable, "-B", "-c", "import time; time.sleep(60)"],
                              timeout=.1, cwd=ROOT, env=dict(w.os.environ), stdout=out, stderr=err)
        self.assertLess(time.monotonic()-start, 10)

    def test_publication_after_first_release_is_rejected(self):
        from unittest.mock import patch
        r = self.run_record(mode="prospective")
        pointer = self.store/"archive/latest_successful.json"
        before = pointer.read_bytes()
        with patch.object(w, "utcnow", return_value=NOW+timedelta(days=20)):
            with self.assertRaisesRegex(ValueError, "first release"):
                w.publish(pointer.parent, Path(r["run_directory"]), w.load_run(r["run_directory"]))
        self.assertEqual(before,pointer.read_bytes())

    def test_supported_model_code_identity_covers_configuration(self):
        self.assertIn("config.py",w.source_hashes())
        self.assertIn("models/horizon_models.py",w.source_hashes())


if __name__ == "__main__":
    unittest.main()
