"""Failure-first regression tests for the R34 input boundary."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd

from . import inputs

ROOT = Path(__file__).resolve().parents[2]
CLOCK = "2026-09-22T18:00:00+00:00"
CAPTURED = "2026-09-22T17:00:00+00:00"
PRODUCTS = [
    "Pšenice potravinářská [t]", "Mléko kravské Q. tř. j. [tis. l.]",
    "Prasata jatečná  j.tř. SEU v JUT [t]", "Kuřata jatečná v živém I.tř.j [t]",
]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def seal(folder, key="files"):
    write_json(folder / "MANIFEST.json", {key: {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in folder.rglob("*") if p.is_file() and p.name != "MANIFEST.json"
    }})


class InputBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="r34_inputs_")
        self.root = Path(self.tmp.name)
        self.base = self.root / "base"
        self.current = self.root / "current"
        self.capture = self.root / "capture"
        self.output = self.root / "prepared"
        for folder in (self.base / "path", self.current / "nowcast",
                       self.current / "market", self.capture / "raw"):
            folder.mkdir(parents=True)
        idx = pd.period_range("2015-01", "2026-08", freq="M")
        self.idx = idx
        self.food = pd.Series(100 + np.arange(len(idx)) * .25, index=idx)
        self.ppi = pd.Series(.1, index=idx)
        self.headline = pd.Series(80 + np.arange(len(idx)) * .15, index=idx)
        farm = pd.Series(100 + np.arange(len(idx)) * .2, index=idx)
        self.baseline = pd.DataFrame({
            "agri4": 100*np.log(farm/farm.iloc[0]),
            "food_ppi": np.arange(len(idx))*100*np.log1p(.001),
            "food": 100*np.log(self.food/self.food.iloc[0]),
        }).iloc[:-1]
        self.baseline.to_csv(self.base/"path/food_log_levels.csv", index_label="period")
        pd.DataFrame("2026-09-01T00:00:00+00:00", index=self.baseline.index,
                     columns=self.baseline.columns).to_csv(
                         self.base/"path/food_available_from.csv", index_label="period")
        pd.DataFrame({"headline_mm": .1}, index=idx[:-1]).to_csv(
            self.base/"path/headline_history.csv", index_label="period")
        write_json(self.base/"provenance.json", {})
        seal(self.base)
        for name, columns in [
            ("target_headline_cpi_mm.csv", ["cpi_mm"]),
            ("cnb_core_mm.csv", ["core"]),
            ("cnb_regulated_mm.csv", ["regulated"]),
            ("alcohol_tobacco.csv", ["alcohol_tobacco"]),
            ("component_food_fuel_mm.csv", ["food", "fuel"]),
        ]:
            pd.DataFrame(.1, index=idx, columns=columns).to_csv(
                self.current/"nowcast"/name, index_label="period")
        weekly = pd.date_range("2025-09-01", "2026-09-14", freq="W-MON")
        market = pd.concat([pd.DataFrame({
            "ticker": ticker, "observation_date": weekly + pd.Timedelta(days=4),
            "value": price,
        }) for ticker, price in [("ECOBETCZ Index", 35000.), ("ECOBOTCZ Index", 34000.)]])
        market.to_csv(self.current/"market/history_long.csv", index=False)
        pd.DataFrame({"petrol95": 35., "diesel": 34.}, index=weekly).to_csv(
            self.current/"nowcast/fuel_weekly_variant_b.csv", index_label="date")
        self.farm = self.root/"farm.csv"
        rows = [{"CASMKMQR": str(p), "UZ02HU.KRAJ": None, "Reprezentant": product,
                 "Hodnota": farm.loc[p]*(j+1)}
                for p in idx[:-1] for j, product in enumerate(PRODUCTS)]
        pd.DataFrame(rows).to_csv(self.farm, index=False)
        write_json(self.farm.with_name(self.farm.name+".metadata.json"), {
            "source": "https://data.csu.gov.cz/opendata/sady/CEN0203B/distribuce/csv",
            "retrieved_at": CAPTURED, "completed_at": CAPTURED,
            "sha256": hashlib.sha256(self.farm.read_bytes()).hexdigest(),
        })
        write_json(self.current/"provenance.json", {
            "target": "2026-09", "as_of": CAPTURED, "prepared_at": CAPTURED,
            "snapshot": {"completed_at": CAPTURED},
            "manual_rows": [{"available_from": CAPTURED}],
            "farm_source": {"path": str(self.farm),
                            "sha256": hashlib.sha256(self.farm.read_bytes()).hexdigest()},
        })
        seal(self.current)
        self.hist = pd.concat([pd.DataFrame({
            "ticker": ticker, "observation_date": idx.to_timestamp("M"), "value": values,
        }) for ticker, values in [
            ("CZCPF Index", self.food.to_numpy()), ("CZCPI Index", self.headline.to_numpy()),
            ("CZPPA10M Index", self.ppi.to_numpy()),
            ("CZCPYOY Index", np.round(100*(self.headline/self.headline.shift(12)-1), 1).fillna(0).to_numpy()),
            ("CZCPMOM Index", np.round(100*(self.headline/self.headline.shift(1)-1), 1).fillna(0).to_numpy()),
        ]], ignore_index=True)
        write_json(self.capture/"request.json", {
            "retrieved_at": CAPTURED, "completed_at": CAPTURED,
            "history_start": "2015-01-01", "end_date": "2026-09-21",
        })
        self.save_capture()

    def tearDown(self):
        self.tmp.cleanup()

    def save_capture(self):
        self.hist.to_csv(self.capture/"history_long.csv", index=False)
        for ticker, d in self.hist.groupby("ticker"):
            d[["observation_date", "value"]].rename(columns={"value": "PX_LAST"}).to_csv(
                self.capture/"raw"/(ticker.replace(" ", "_")+".csv"), index=False)
        seal(self.capture, "sha256")

    def prepare(self, **kwargs):
        return inputs.prepare(self.base, self.current, self.capture, self.output,
                              origin="2026-09", as_of=kwargs.pop("as_of", CLOCK),
                              farm_raw=self.farm, **kwargs)

    def test_missing_august_consumer_rejected(self):
        self.hist = self.hist[~((self.hist.ticker == "CZCPF Index") &
                               (self.hist.observation_date.dt.month == 8) &
                               (self.hist.observation_date.dt.year == 2026))]
        self.save_capture()
        with self.assertRaisesRegex(ValueError, "coverage|missing"):
            self.prepare()

    def test_duplicate_month_rejected(self):
        self.hist = pd.concat([self.hist, self.hist.iloc[[-1]]], ignore_index=True)
        self.save_capture()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.prepare()

    def test_nonpositive_index_rejected(self):
        self.hist.loc[0, "value"] = 0
        self.save_capture()
        with self.assertRaisesRegex(ValueError, "positive"):
            self.prepare()

    def test_nonpositive_ppi_ratio_rejected(self):
        self.hist.loc[self.hist.ticker == "CZPPA10M Index", "value"] = -100
        self.save_capture()
        with self.assertRaisesRegex(ValueError, "positive|ratio"):
            self.prepare()

    def test_revision_conflicting_with_frozen_food_rejected(self):
        self.hist.loc[12, "value"] += .1
        self.save_capture()
        with self.assertRaisesRegex(ValueError, "overlap|baseline"):
            self.prepare()

    def test_hash_tamper_rejected(self):
        with (self.capture/"history_long.csv").open("a", encoding="utf-8") as f:
            f.write("\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.prepare()

    def test_earlier_capture_clock_rejected(self):
        with self.assertRaisesRegex(ValueError, "available|capture|clock"):
            self.prepare(as_of="2026-09-22T16:59:59+00:00")

    def test_naive_clock_rejected(self):
        with self.assertRaisesRegex(ValueError, "timezone|aware"):
            self.prepare(as_of="2026-09-22T18:00:00")

    def test_future_requested_clock_rejected(self):
        with self.assertRaisesRegex(ValueError, "future"):
            self.prepare(as_of="2099-09-22T18:00:00+00:00")

    def test_future_realised_month_rejected(self):
        self.hist.loc[139, "observation_date"] = pd.Timestamp("2026-09-30")
        self.save_capture()
        with self.assertRaisesRegex(ValueError, "future|origin"):
            self.prepare()

    def test_current_manual_availability_rechecked(self):
        path = self.current/"provenance.json"
        prov = json.loads(path.read_text(encoding="utf-8"))
        prov["manual_rows"][0]["available_from"] = "2026-09-22T18:01:00+00:00"
        write_json(path, prov); seal(self.current)
        with self.assertRaisesRegex(ValueError, "available|clock"):
            self.prepare()

    def test_missing_current_core_month_rejected(self):
        p = self.current/"nowcast/cnb_core_mm.csv"
        d = pd.read_csv(p);d = d.iloc[:-1];d.to_csv(p, index=False);seal(self.current)
        with self.assertRaisesRegex(ValueError, "core|coverage"):
            self.prepare()

    def test_no_output_overwrite(self):
        self.output.mkdir()
        marker = self.output/"keep"
        marker.write_text("existing", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(marker.read_text(encoding="utf-8"), "existing")

    def test_round_trip_preserves_baseline_and_ragged_edge(self):
        result = self.prepare()
        got = inputs.load_prepared(self.output, as_of=CLOCK)
        pd.testing.assert_frame_equal(got["food_levels"].loc[self.baseline.index],
                                      self.baseline, check_names=False)
        self.assertTrue(pd.isna(got["food_levels"].loc["2026-08", "agri4"]))
        self.assertTrue(pd.isna(got["food_available"].loc["2026-08", "agri4"]))
        self.assertEqual(list(got["pump_weekly"]), ["gross_petrol95", "gross_diesel"])
        self.assertEqual(str(got["food_levels"].index[-1]), "2026-08")
        self.assertEqual(result["provenance"]["available_from"], CAPTURED)
        self.assertEqual(got["provenance"]["origin"], "2026-09")
        mm = got["headline_history"].headline_mm
        self.assertAlmostEqual(mm.iloc[-1], 100*(self.headline.iloc[-1]/self.headline.iloc[-2]-1))
        self.assertAlmostEqual(100*((1+mm.iloc[-12:]/100).prod()-1),
                               100*(self.headline.iloc[-1]/self.headline.iloc[-13]-1))
        with self.assertRaisesRegex(ValueError, "available|clock"):
            inputs.load_prepared(self.output, as_of="2026-09-22T16:59:59+00:00")

    def test_seven_product_or_partial_four_product_not_averaged(self):
        d = pd.read_csv(self.farm)
        d = d.iloc[:-1];d.to_csv(self.farm, index=False)
        meta = json.loads(self.farm.with_name(self.farm.name+".metadata.json").read_text(encoding="utf-8"))
        meta["sha256"] = hashlib.sha256(self.farm.read_bytes()).hexdigest()
        write_json(self.farm.with_name(self.farm.name+".metadata.json"), meta)
        with self.assertRaisesRegex(ValueError, "farm|agri|complete"):
            self.prepare()


    def test_fresh_august_four_product_observation_uses_retrieval_clock(self):
        d = pd.read_csv(self.farm)
        addition = pd.DataFrame([{
            "CASMKMQR": "2026-08", "UZ02HU.KRAJ": None,
            "Reprezentant": product, "Hodnota": (100+139*.2)*(j+1),
        } for j, product in enumerate(PRODUCTS)])
        pd.concat([d, addition], ignore_index=True).to_csv(self.farm, index=False)
        metadata = self.farm.with_name(self.farm.name+".metadata.json")
        meta = json.loads(metadata.read_text(encoding="utf-8"))
        meta.update(sha256=hashlib.sha256(self.farm.read_bytes()).hexdigest(),
                    completed_at="2026-09-22T17:30:00+00:00")
        write_json(metadata, meta)
        result = self.prepare()
        self.assertAlmostEqual(result["food_levels"].loc["2026-08", "agri4"],
                               100*np.log(127.8/100))
        self.assertEqual(result["food_available"].loc["2026-08", "agri4"],
                         pd.Timestamp("2026-09-22T17:30:00+00:00"))
        self.assertEqual(result["provenance"]["available_from"], "2026-09-22T17:30:00+00:00")
        with self.assertRaisesRegex(ValueError, "available|clock"):
            inputs.load_prepared(self.output, as_of="2026-09-22T17:29:59+00:00")

    def test_farm_capture_earlier_clock_rejected(self):
        metadata = self.farm.with_name(self.farm.name+".metadata.json")
        meta = json.loads(metadata.read_text(encoding="utf-8"))
        meta["completed_at"] = "2026-09-22T18:01:00+00:00"
        write_json(metadata, meta)
        with self.assertRaisesRegex(ValueError, "farm.*available|clock"):
            self.prepare()

    def test_ppi_revised_training_not_spliced(self):
        position = self.hist[self.hist.ticker == "CZPPA10M Index"].index[-3]
        self.hist.loc[position, "value"] += .1
        self.save_capture()
        with self.assertRaisesRegex(ValueError, "baseline overlap"):
            self.prepare()

    def test_baseline_anchor_required(self):
        self.hist = self.hist[~((self.hist.ticker == "CZCPF Index") &
                               (self.hist.observation_date == pd.Timestamp("2015-01-31")))]
        self.save_capture()
        with self.assertRaisesRegex(ValueError, "missing|coverage|base"):
            self.prepare()

    def test_raw_long_disagreement_rejected_even_with_valid_hashes(self):
        path = self.capture/"raw/CZCPF_Index.csv"
        d = pd.read_csv(path); d.loc[0, "PX_LAST"] += 1; d.to_csv(path, index=False)
        seal(self.capture, "sha256")
        with self.assertRaisesRegex(ValueError, "raw capture/history"):
            self.prepare()

    def test_baseline_future_availability_rejected(self):
        p = self.base/"path/food_available_from.csv"
        d = pd.read_csv(p); d.loc[len(d)-1, "food"] = "2026-09-22T18:01:00+00:00"
        d.to_csv(p, index=False); seal(self.base)
        with self.assertRaisesRegex(ValueError, "availability"):
            self.prepare()

    def test_prepared_hash_tamper_rejected(self):
        self.prepare()
        with (self.output/"food_levels.csv").open("a", encoding="utf-8") as f:
            f.write("\n")
        with self.assertRaisesRegex(ValueError, "hash"):
            inputs.load_prepared(self.output, as_of=CLOCK)

    def test_pump_current_gross_survives_stale_net_fields(self):
        p = self.current/"nowcast/fuel_weekly_variant_b.csv"
        d = pd.read_csv(p); d["net_petrol95"] = np.nan; d["net_diesel"] = np.nan
        d.to_csv(p, index=False); seal(self.current)
        result = self.prepare()
        self.assertEqual(result["pump_weekly"].index[-1], pd.Timestamp("2026-09-14"))
        self.assertEqual(result["pump_weekly"].iloc[-1].to_dict(),
                         {"gross_petrol95": 35., "gross_diesel": 34.})

    def test_invalid_pump_not_dropped(self):
        p = self.current/"market/history_long.csv"
        d = pd.read_csv(p); d.loc[len(d)-1, "value"] = 0; d.to_csv(p, index=False)
        seal(self.current)
        with self.assertRaisesRegex(ValueError, "positive"):
            self.prepare()

    def test_duplicate_farm_product_rejected(self):
        d = pd.read_csv(self.farm)
        pd.concat([d, d.iloc[[-1]]], ignore_index=True).to_csv(self.farm, index=False)
        metadata = self.farm.with_name(self.farm.name+".metadata.json")
        meta = json.loads(metadata.read_text(encoding="utf-8"))
        meta["sha256"] = hashlib.sha256(self.farm.read_bytes()).hexdigest()
        write_json(metadata, meta)
        with self.assertRaisesRegex(ValueError, "duplicate national farm"):
            self.prepare()



    def test_export_availability_uniform_precision_for_parent_parser(self):
        request = self.capture/"request.json"
        data = json.loads(request.read_text(encoding="utf-8"))
        data["completed_at"] = "2026-09-22T17:00:00.123456+00:00"
        write_json(request, data); seal(self.capture, "sha256")
        self.prepare()
        dates = pd.read_csv(self.output/"food_available.csv").food
        self.assertTrue(pd.to_datetime(dates, utc=True, errors="coerce").notna().all(),
                        "Mixed fractional precision must not hide current consumer availability")

if __name__ == "__main__":
    unittest.main()
