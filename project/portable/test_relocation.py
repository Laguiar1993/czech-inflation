"""Relocation regressions; all fixture writes stay in disposable temp directories."""
from contextlib import ExitStack
import gzip
import hashlib
import importlib
import json
from pathlib import Path, PureWindowsPath
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.forecast_updates_r33 import workflow as r33
from tools.current_path_r34 import inputs as r34
from tools.momentum_r35 import inputs as r35

try:
    from portable.relocation import relocations
except ImportError:
    relocations = None

CLOCK = "2020-02-05T12:00:00+00:00"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    path.write_bytes(raw)
    return raw


def seal(folder, filename="MANIFEST.json", nested=False, **extra):
    files = {p.relative_to(folder).as_posix(): sha(p.read_bytes())
             for p in folder.rglob("*") if p.is_file() and p.name != filename}
    raw = put(folder / filename, dict(extra, files={k: {"sha256": v} for k, v in files.items()}
                                    if nested else files))
    return {"path": str(folder), "manifest_sha256": sha(raw), "files": files}


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(relocations), "relocations context manager must exist")
        self.tmp = tempfile.TemporaryDirectory(prefix="portable-relocation-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "checkout"
        self.root.mkdir()
        self.old = self.base / "never-created-original"
        self.assertFalse(self.old.exists())
        put(self.root / "data/item.txt", b"sealed bytes")

    def context(self):
        return relocations(self.root, old_root=self.old)

    def test_relative_current_and_old_paths_ignore_cwd(self):
        with self.context() as relocation:
            for value in ("data/item.txt", "data\\item.txt", self.root / "data/item.txt",
                          self.old / "data/item.txt"):
                with self.subTest(value=value):
                    self.assertEqual(relocation.resolve(value), self.root / "data/item.txt")
                    for module in (r33, r34, r35):
                        self.assertEqual(module.Path(value).read_bytes(), b"sealed bytes")
        self.assertFalse(self.old.exists())

    def test_windows_original_path_on_any_host(self):
        old = PureWindowsPath("C:/archive/original")
        with relocations(self.root, old_root=old):
            self.assertEqual(r34.Path(str(old / "data/item.txt")).read_bytes(), b"sealed bytes")
            self.assertEqual(r34.Path("c:/ARCHIVE/original/data/item.txt").read_bytes(), b"sealed bytes")

    def test_rejects_traversal_external_and_windows_ambiguous_paths(self):
        bad = ["../outside", "data/../../outside", "data\\..\\item.txt",
               str(self.old / ".." / "outside"), str(self.old) + "-sibling/data/item.txt",
               self.base / "outside", "C:relative", "\\root-relative", "D:/outside",
               "data/item.txt:stream", "data/name. ", "data/NUL", "\\\\?\\C:\\archive\\x"]
        with self.context():
            for value in bad:
                with self.subTest(value=value), self.assertRaises(ValueError):
                    r34.Path(value).read_bytes()
            with self.assertRaises(ValueError):
                (r33.Path(self.root) / "../outside").read_bytes()

    def test_symlink_escape_is_rejected_before_read(self):
        outside = self.base / "secret"
        put(outside, b"outside")
        link = self.root / "link"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        with self.context(), self.assertRaises(ValueError):
            r34.Path(self.old / "link").read_bytes()

    def test_no_fallback_to_existing_old_file(self):
        put(self.old / "missing.txt", b"must not read original")
        with self.context(), self.assertRaises(FileNotFoundError):
            r34.Path(self.old / "missing.txt").read_bytes()

    def test_read_only_and_context_restoration_on_exception(self):
        before = [(m, m.Path) for m in (r33, r34, r35)]
        helpers = (r34._manifest, r35._manifest, r35._frozen)
        source_identity = r35.frozen.__file__
        with self.assertRaisesRegex(RuntimeError, "sentinel"):
            with self.context():
                self.assertIs(importlib.import_module("pathlib").Path, Path)
                for mode in ("w", "a", "x", "r+", "wb"):
                    with self.assertRaises((PermissionError, AttributeError)):
                        r34.Path("data/item.txt").open(mode)
                raise RuntimeError("sentinel")
        for module, original in before:
            self.assertIs(module.Path, original)
        self.assertEqual(helpers, (r34._manifest, r35._manifest, r35._frozen))
        self.assertEqual(r35.frozen.__file__, source_identity)
        self.assertEqual((self.root / "data/item.txt").read_bytes(), b"sealed bytes")

    def test_nested_context_rejected_and_outer_context_survives(self):
        with self.context():
            with self.assertRaises(RuntimeError):
                with self.context():
                    self.fail("nested relocation entered")
            self.assertEqual(r33.Path("data/item.txt").read_bytes(), b"sealed bytes")
        self.assertIs(r33.Path, Path)

    def test_manifest_metadata_identity_and_hash_tamper(self):
        folder = self.root / "bundle"
        put(folder / "value.csv", b"value\n1\n")
        info = seal(folder)
        archived = str(self.old / "bundle")
        with self.context():
            self.assertEqual(r34._manifest(archived)[1], dict(info, path=archived))
            self.assertEqual(r35._manifest(archived)[2], dict(info, path=archived))
            self.assertEqual(r34._manifest("bundle")[1], info)
            self.assertEqual(r35._manifest(folder)[2], info)
            put(folder / "value.csv", b"value\n2\n")
            for module in (r34, r35):
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    module._manifest(archived)

    def test_manifest_member_traversal_is_rejected(self):
        put(self.root / "bundle/MANIFEST.json", {"files": {"../data/item.txt": sha(b"sealed bytes")}})
        with self.context():
            for module in (r34, r35):
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    module._manifest(self.old / "bundle")

    def test_r33_early_prospective_record_fresh_copy_and_tamper(self):
        seed = self.base / "fixture-seed"
        bundle = seed / "bundle"
        put(bundle / "provenance.json", {"snapshot": {"completed_at": CLOCK}})
        bundle_info = seal(bundle)
        request = dict(command="run", bundle=str(self.old / "bundle"), target="2020-02",
                       as_of=CLOCK, mode="prospective", live_calendar=None, path_file=None,
                       recorded_at=CLOCK)
        inputs = dict(bundle_manifest_sha256=bundle_info["manifest_sha256"],
                      source_hashes={"source.py": "a" * 64}, live_calendar_sha256=None)
        report = dict(schema_version="live_bundle_r32/v1", status="calculated", command="run",
                      target="2020-02", as_of=CLOCK, main_model="HARD_BASE", variant="R31C_C123",
                      ready_for_calculation=True, forecast_available=True, ready_for_first_release=True,
                      reasons=[], runtime={"ready": True}, calendar={"live_sha256": None},
                      readiness=dict(data_ready=True, before_first_release=True, reasons=[],
                                     first_release="2020-03-01T00:00:00+00:00"),
                      provenance={"bundle_manifest_sha256": inputs["bundle_manifest_sha256"]},
                      forecast=dict(version="fixture", target="2020-02", as_of=CLOCK,
                                    main_model="HARD_BASE", points_mm_pct={"HARD_BASE": .5},
                                    main_contributions_pp={"food": .2, "core": .3},
                                    ready_for_first_release=True, before_first_release=True,
                                    food_diagnostics={"method": "x13"},
                                    diagnostics={"hard": {"residual_forest": {"fallback_used": False}}}))
        forecast, path = r33.validate_adapter(request, report, CLOCK, CLOCK, inputs)
        result = dict(request, schema_version=r33.SCHEMA, status="successful", completed_at=CLOCK,
                      forecast=forecast, path=path, model=r33.MODEL, units=r33.UNITS,
                      model_identity=forecast["model_identity"])
        for name, obj in (("request", request), ("result", result), ("inputs", inputs), ("adapter", report)):
            put(seed / "run" / (name + ".json"), obj)
        seal(seed / "run", schema_version=r33.SCHEMA)
        shutil.copytree(seed, self.root, dirs_exist_ok=True)
        before = {p.relative_to(self.root): sha(p.read_bytes()) for p in self.root.rglob("*") if p.is_file()}
        with self.context():
            self.assertEqual(r33.load_run(self.old / "run"), result)
        after = {p.relative_to(self.root): sha(p.read_bytes()) for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        put(self.root / "bundle/provenance.json", b"{}")
        with self.context(), self.assertRaisesRegex(ValueError, "provenance hash mismatch"):
            r33.load_run("run")

    def test_r34_loader_reads_farm_metadata_and_keeps_source_identity(self):
        sources = {}
        for name in ("base_bundle", "current_bundle", "bloomberg_capture"):
            put(self.root / name / "value.csv", b"v\n1\n")
            sources[name] = dict(seal(self.root / name), path=str(self.old / name))
        farm = put(self.root / "farm.csv", b"farm bytes")
        metadata = put(self.root / "farm.metadata.json", {"completed_at": CLOCK})
        sources["farm"] = dict(path=str(self.old / "farm.csv"), sha256=sha(farm),
                               metadata_path=str(self.old / "farm.metadata.json"),
                               metadata_sha256=sha(metadata), completed_at=CLOCK)
        prov = dict(schema_version=1, origin="2020-02", target="2020-02", available_from=CLOCK,
                    capture_completed_at=CLOCK, sources=sources)
        put(self.root / "prepared/provenance.json", prov)
        for name, raw in {"food_levels.csv": b"period,agri4,food_ppi,food\n2020-01,1,2,3\n",
                          "food_available.csv": b"period,agri4,food_ppi,food\n2020-01,a,b,c\n",
                          "headline_history.csv": b"period,headline_mm\n2020-01,1\n",
                          "headline_levels.csv": b"period,headline_level\n2020-01,100\n",
                          "pump_weekly.csv": b"date,petrol95,diesel\n2020-01-01,1,2\n"}.items():
            put(self.root / "prepared" / name, raw)
        seal(self.root / "prepared")
        # Small fixtures isolate relocation; production hash and metadata checks remain real.
        with ExitStack() as stack:
            for name in ("_current", "_capture", "_frames_valid"):
                stack.enter_context(patch.object(r34, name))
            stack.enter_context(self.context())
            self.assertEqual(r34.load_prepared("prepared", as_of=CLOCK)["provenance"], prov)
            put(self.root / "farm.metadata.json", b"tampered")
            with self.assertRaisesRegex(ValueError, "farm capture metadata hash changed"):
                r34.load_prepared("prepared", as_of=CLOCK)

    def test_failed_entry_restores_bindings_and_releases_lock(self):
        with patch("portable.relocation.importlib.import_module", side_effect=ImportError("fixture")):
            with self.assertRaises(ImportError):
                with self.context():
                    self.fail("import failure must prevent entry")
        self.assertIs(r33.Path, Path)
        with self.context():
            self.assertEqual(r35.Path("data/item.txt").read_bytes(), b"sealed bytes")
        self.assertIs(r35.Path, Path)

    def test_r35_loader_extractor_identity_and_source_tamper(self):
        source_relative = "tools/research_r18/category_inputs.py"
        source = put(self.root / source_relative, b"# fixture extractor\n")
        raw = b"a,b\n1,2\n"
        pd = r35.pd
        metadata = pd.DataFrame(dict(coicop2018_code=["011"], source_raw_sha256=[sha(raw)],
                                     first_month=["2015-01"], last_month=["2026-07"], observations=[139]))
        old = pd.DataFrame({"group": [1.]}, index=pd.period_range("2015-01", periods=1, freq="M", name="period"))
        cells = pd.DataFrame(columns=["mapped_series", "basket_code", "weight_permille",
                                      "source_file", "source_sheet", "source_cell"])
        weights = pd.Series([1000.], index=pd.Index(["group"], name="group"), name="weight_permille")
        folder = self.root / "frozen"
        put(folder / "raw/CEN0101E.csv.gz", gzip.compress(raw, mtime=0))
        for name, frame in (("series_metadata.csv", metadata), ("monthly_levels.csv", old),
                            ("basket_weights_long.csv", cells.assign(basket_code=[]))):
            put(folder / name, frame.to_csv(index=name == "monthly_levels.csv").encode())
        frozen_info = seal(folder, "manifest.json", nested=True, builder_sha256=sha(source),
                           source_raw_uncompressed_sha256=sha(raw), created_at_utc=CLOCK)
        frozen_info.update(path=str(self.old / "frozen"), extractor_path=str(self.old / source_relative),
                           extractor_sha256=sha(source), raw_sha256=sha(raw), created_at=CLOCK,
                           weight_effective_year=2026, weight_basis_year=2024, weight_cells=[])
        capture = self.root / "capture"
        put(capture / "CEN0101E.csv.gz", gzip.compress(raw, mtime=0))
        request = dict(source_url=r35.SOURCE_URL, retrieved_at=CLOCK, completed_at=CLOCK,
                       headers={}, raw_sha256=sha(raw), raw_bytes=len(raw))
        put(capture / "request.json", request)
        capture_info = seal(capture)
        capture_info.update(path=str(self.old / "capture"), raw_sha256=sha(raw), raw_bytes=len(raw),
                            source_url=r35.SOURCE_URL, completed_at=CLOCK)
        prov = dict(schema_version=1, kind="observed_category_momentum_inputs", available_from=CLOCK,
                    capture_completed_at=CLOCK, prepared_at=CLOCK, through="2015-01",
                    sources=dict(capture=capture_info, frozen_package=frozen_info),
                    overlap_revision_audit={"fixture": True})
        prepared = self.root / "prepared"
        put(prepared / "provenance.json", prov)
        put(prepared / "monthly_levels.csv", old.to_csv().encode())
        expected_meta = r35._metadata(metadata, pd.Period("2015-01", "M"), request)
        put(prepared / "series_metadata.csv", expected_meta.to_csv(index=False).encode())
        put(prepared / "weights.csv", weights.to_frame().to_csv().encode())
        seal(prepared)
        with ExitStack() as stack:
            # Emulate a NEW-checkout import. Small tables replace domain coverage,
            # while the complete load_prepared I/O/hash/identity/clock path is real.
            stack.enter_context(patch.object(r35.frozen, "__file__", str(self.root / source_relative)))
            stack.enter_context(patch.object(r35.frozen, "RAW_SHA256", sha(raw)))
            for name in ("_valid_metadata", "_valid_levels", "_valid_weights", "_verify_source_labels"):
                stack.enter_context(patch.object(r35, name))
            stack.enter_context(patch.object(r35, "_weights", return_value=(weights, cells)))
            stack.enter_context(patch.object(r35, "extract_current", return_value=old))
            stack.enter_context(patch.object(r35, "_audit", return_value={"fixture": True}))
            stack.enter_context(self.context())
            self.assertEqual(r35._frozen(str(self.old / "frozen"))[-1], frozen_info)
            current_info = r35._frozen(folder)[-1]
            self.assertEqual(current_info["path"], str(folder))
            self.assertEqual(current_info["extractor_path"], str(self.root / source_relative))
            result = r35.load_prepared("prepared", as_of=CLOCK)
            self.assertEqual(result["provenance"], prov)
            pd.testing.assert_frame_equal(result["levels"], old)
            with self.assertRaisesRegex(ValueError, "not available"):
                r35.load_prepared("prepared", as_of="2020-02-04T12:00:00+00:00")
            put(self.root / source_relative, b"changed extractor")
            with self.assertRaisesRegex(ValueError, "extractor source hash"):
                r35.load_prepared("prepared", as_of=CLOCK)


if __name__ == "__main__":
    unittest.main()
