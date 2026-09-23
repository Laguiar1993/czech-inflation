"""Failure-first tests for official R35 current-vintage input preparation."""
from __future__ import annotations
import gzip
import hashlib
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from tools.research_r18 import category_inputs as frozen

try:
    sut = importlib.import_module("tools.momentum_r35.inputs")
except ModuleNotFoundError:
    sut = None

GROUPS = [item[0] for item in frozen.CATEGORIES.values()]
COLUMNS = [
    "Ukazatel", "IndicatorType", "Typ indexu", "TYPUDAJE4A",
    "Klasifikace COICOP 2018-Oddíl", "CZCOICOP2.CZCOP1",
    "Klasifikace COICOP 2018-Skupina a třída", "CZCOICOP2.CZCOP23",
    "Skupiny domácností", "EKAKTIOCDS", "Území", "UZ02P",
    "Měsíce, měsíční kumulace, měsíce klouzavých průměrů, čtvrtletí, roky",
    "CASMKMQRM12", "Hodnota", "MJ_TEXT", "MJ_SYMBOL",
]
CLOCK = "2026-09-22T20:00:00+00:00"
CAPTURED = "2026-09-22T19:00:00.123456+00:00"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def json_write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def reseal(path):
    json_write(path/"MANIFEST.json", {"files": {
        p.name: sha(p.read_bytes()) for p in path.iterdir()
        if p.is_file() and p.name != "MANIFEST.json"
    }})


class InputsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen_levels = pd.read_csv(frozen.PACKAGE/"monthly_levels.csv",
                                      index_col=0, float_precision="round_trip")
        labels = pd.read_csv(frozen.PACKAGE/"series_metadata.csv", dtype={"coicop2018_code": str}).set_index("column").label_cs.to_dict()
        rows = []
        for code, definition in frozen.CATEGORIES.items():
            name = definition[0]
            for month in pd.period_range("2015-01", "2026-08", freq="M"):
                value = cls.frozen_levels.loc[str(month), name] if str(month) in cls.frozen_levels.index else 150.
                rows.append({
                    "IndicatorType": "6134", "TYPUDAJE4A": "IZ2015",
                    "CZCOICOP2.CZCOP1": code[:2],
                    "CZCOICOP2.CZCOP23": code if len(code) == 3 else None,
                    "EKAKTIOCDS": "0", "UZ02P": "CZ", "CASMKMQRM12": str(month),
                    "Hodnota": str(value),
                    ("Klasifikace COICOP 2018-Skupina a třída" if len(code) == 3 else "Klasifikace COICOP 2018-Oddíl"): labels[name],
                })
        cls.template = pd.DataFrame(rows).reindex(columns=COLUMNS)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="momentum_r35_inputs_", dir=frozen.ROOT/"work")
        self.root = Path(self.temp.name)
        self.capture = self.root/"capture"
        self.capture.mkdir()
        self.output = self.root/"prepared"
        self.raw = self.template.copy()

    def tearDown(self):
        self.temp.cleanup()

    def call(self, name, *args, **kwargs):
        function = getattr(sut, name, None)
        self.assertTrue(callable(function), f"R35 {name} must be implemented")
        return function(*args, **kwargs)

    def extraction(self, raw=None):
        return self.call("extract_current", self.raw if raw is None else raw,
                         expected_columns=COLUMNS, through="2026-08", as_of=CLOCK)

    def write_capture(self, completed=CAPTURED):
        b = self.raw.to_csv(index=False).encode("utf-8")
        (self.capture/"CEN0101E.csv.gz").write_bytes(gzip.compress(b, mtime=0))
        json_write(self.capture/"request.json", {
            "source_url": frozen.SOURCE_URL, "final_url": frozen.SOURCE_URL,
            "retrieved_at": "2026-09-22T18:59:59+00:00", "completed_at": completed,
            "headers": {"Content-Type": "text/csv"}, "raw_sha256": sha(b),
            "raw_bytes": len(b), "compression": "gzip, mtime=0",
        })
        reseal(self.capture)

    def prepare(self, clock=CLOCK):
        return self.call("prepare", self.capture, self.output, as_of=clock)

    def test_missing_august_category_is_rejected(self):
        self.raw = self.raw.iloc[:-1]
        with self.assertRaisesRegex(ValueError, "Missing|missing|coverage"):
            self.extraction()

    def test_duplicate_month_is_rejected(self):
        self.raw = pd.concat([self.raw, self.raw.iloc[[-1]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.extraction()

    def test_nonpositive_level_is_rejected(self):
        self.raw.loc[5, "Hodnota"] = "0"
        with self.assertRaisesRegex(ValueError, "positive"):
            self.extraction()

    def test_wrong_household_geography_indicator_or_index_type_is_not_substituted(self):
        for column, wrong in [("EKAKTIOCDS", "1"), ("UZ02P", "CZ010"),
                              ("IndicatorType", "9999"), ("TYPUDAJE4A", "IM")]:
            with self.subTest(column=column):
                changed = self.raw.copy()
                changed.loc[139, column] = wrong
                with self.assertRaisesRegex(ValueError, "Missing|missing|coverage"):
                    self.extraction(changed)

    def test_different_population_extra_rows_do_not_contaminate_levels(self):
        others = self.raw.copy()
        others["EKAKTIOCDS"] = "1"; others["Hodnota"] = "99999"
        result = self.extraction(pd.concat([self.raw, others], ignore_index=True))
        self.assertEqual(result.loc[pd.Period("2026-08", "M"), "food"], 150.)

    def test_changed_schema_is_rejected_even_if_required_columns_remain(self):
        changed = self.raw.copy(); changed["unexpected_new_schema"] = "x"
        with self.assertRaisesRegex(ValueError, "schema"):
            self.extraction(changed)

    def test_future_month_is_rejected(self):
        addition = self.raw.loc[self.raw.CASMKMQRM12 == "2026-08"].copy()
        addition["CASMKMQRM12"] = "2026-09"
        changed = pd.concat([self.raw, addition], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "future|coverage|through"):
            self.extraction(changed)

    def test_naive_clock_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone|aware"):
            self.call("extract_current", self.raw, expected_columns=COLUMNS,
                      through="2026-08", as_of="2026-09-22")

    def test_source_hash_mismatch_is_rejected(self):
        self.write_capture()
        (self.capture/"CEN0101E.csv.gz").write_bytes(gzip.compress(b"changed", mtime=0))
        with self.assertRaisesRegex(ValueError, "hash"):
            self.prepare()

    def test_uncompressed_raw_hash_mismatch_is_rejected(self):
        self.write_capture()
        r = json.loads((self.capture/"request.json").read_text(encoding="utf-8"))
        r["raw_sha256"] = "0"*64
        json_write(self.capture/"request.json", r); reseal(self.capture)
        with self.assertRaisesRegex(ValueError, "raw.*hash|hash.*raw"):
            self.prepare()

    def test_future_capture_clock_is_rejected(self):
        self.write_capture(completed="2099-09-22T19:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "future|available|clock"):
            self.prepare()

    def test_capture_after_requested_asof_is_rejected(self):
        self.write_capture(completed="2026-09-22T20:00:01+00:00")
        with self.assertRaisesRegex(ValueError, "available|clock"):
            self.prepare()

    def test_wrong_official_source_is_rejected(self):
        self.write_capture()
        r = json.loads((self.capture/"request.json").read_text(encoding="utf-8"))
        r["source_url"] = "https://example.org/cpi.csv"
        json_write(self.capture/"request.json", r); reseal(self.capture)
        with self.assertRaisesRegex(ValueError, "source"):
            self.prepare()

    def test_existing_output_is_never_overwritten(self):
        self.write_capture(); self.output.mkdir()
        (self.output/"existing").write_text("keep", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual((self.output/"existing").read_text(encoding="utf-8"), "keep")

    def test_complete_contract_and_recorded_revision(self):
        # A current official revision is recorded, not silently suppressed.
        self.raw.loc[5, "Hodnota"] = str(float(self.raw.loc[5, "Hodnota"])+.2)
        self.write_capture()
        result = self.prepare()
        loaded = self.call("load_prepared", self.output, as_of=CLOCK)
        self.assertEqual(set(loaded), {"levels", "metadata", "weights", "provenance"})
        self.assertEqual(loaded["levels"].shape, (140, 37))
        self.assertIsInstance(loaded["levels"].index, pd.PeriodIndex)
        self.assertEqual(list(loaded["levels"]), GROUPS)
        self.assertEqual(list(loaded["weights"].index), GROUPS)
        self.assertAlmostEqual(loaded["weights"].sum(), 1000., places=9)
        self.assertEqual(loaded["metadata"]["column"].tolist(), GROUPS)
        audit = loaded["provenance"]["overlap_revision_audit"]
        self.assertEqual(audit["changed_cells"], 1)
        self.assertAlmostEqual(audit["changes"][0]["delta"], .2)
        self.assertEqual(audit["changes"][0]["group"], "food")
        self.assertEqual(loaded["provenance"]["available_from"], CAPTURED)
        self.assertIn("current", loaded["provenance"]["use_scope"])
        pd.testing.assert_frame_equal(result["levels"], loaded["levels"])
        self.call("load_prepared", self.output)  # optional clock means actual now
        with self.assertRaisesRegex(ValueError, "available|clock"):
            self.call("load_prepared", self.output, as_of="2026-09-22T19:00:00+00:00")

    def test_prepared_corruption_is_rejected(self):
        self.write_capture(); self.prepare()
        with (self.output/"monthly_levels.csv").open("a", encoding="utf-8") as f:
            f.write("\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.call("load_prepared", self.output, as_of=CLOCK)

    def test_invalid_weights_do_not_get_normalised_away(self):
        self.write_capture(); self.prepare()
        p = self.output/"weights.csv"
        w = pd.read_csv(p); w.loc[0, "weight_permille"] += 1.; w.to_csv(p, index=False)
        reseal(self.output)
        with self.assertRaisesRegex(ValueError, "weight"):
            self.call("load_prepared", self.output, as_of=CLOCK)


    def test_changed_fresh_category_label_requires_review(self):
        self.raw.loc[139, "Klasifikace COICOP 2018-Skupina a třída"] = "Different category scope"
        self.write_capture()
        with self.assertRaisesRegex(ValueError, "label|mapping"):
            self.prepare()

    def test_rehashed_prepared_values_must_still_match_official_raw(self):
        self.write_capture(); self.prepare()
        p = self.output/"monthly_levels.csv"
        d = pd.read_csv(p); d.loc[0, "food"] += 1; d.to_csv(p, index=False)
        reseal(self.output)
        with self.assertRaisesRegex(ValueError, "levels.*raw|levels.*extraction"):
            self.call("load_prepared", self.output, as_of=CLOCK)

    def test_maintaining_weight_total_does_not_allow_changed_allocations(self):
        self.write_capture(); self.prepare()
        p = self.output/"weights.csv"
        w = pd.read_csv(p); w.loc[0, "weight_permille"] += 1.; w.loc[1, "weight_permille"] -= 1.
        w.to_csv(p, index=False); reseal(self.output)
        with self.assertRaisesRegex(ValueError, "weights.*frozen"):
            self.call("load_prepared", self.output, as_of=CLOCK)

if __name__ == "__main__":
    unittest.main()
