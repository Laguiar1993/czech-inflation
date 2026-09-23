"""Current preparation failure cases; no source fetching or frozen writes."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from tools.live_bundle_r32 import adapter
from tools.forecast_updates_r33 import workflow as w
if importlib.util.find_spec("tools.forecast_updates_r33.current_bundle"):
    from tools.forecast_updates_r33 import current_bundle as cb
else:
    cb = None


class CurrentBundleTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(cb, "current bundle preparation missing")
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.loaded = adapter.load_bundle(w.ROOT/"data/bloomberg_inputs_20260922_foodppi",w.ROOT)
        self.fresh = {}
        monthly = {"CZCPMOM Index":.3,"CZCPYOY Index":1.9,"CZCPFMOM Index":.2,
                   "CZCPAMOM Index":.1,"CZPPA10M Index":-.1,"CZCIXM Index":.4,"CZCIRM Index":.5}
        for ticker,value in monthly.items():
            self.fresh[ticker] = pd.Series([value],index=pd.DatetimeIndex(["2026-08-31"]))
        self.fresh["CZEIIMOM Index"] = pd.Series([.7,.8],index=pd.DatetimeIndex(["2026-06-30","2026-07-31"]))
        self.agri = pd.Series([1.,2.],index=pd.PeriodIndex(["2026-07","2026-08"],freq="M"))

    def build(self):
        return cb.extend_frames(self.loaded,self.fresh,pd.Period("2026-09"),self.agri)

    def test_missing_august_core_and_regulated_are_not_imputed(self):
        del self.fresh["CZCIXM Index"]
        del self.fresh["CZCIRM Index"]
        frames,market = self.build()
        self.assertTrue(pd.isna(frames["core"].loc["2026-08","core"]))
        self.assertTrue(pd.isna(frames["regulated"].loc["2026-08","regulated"]))
        self.assertTrue(pd.isna(frames["features"].loc["2026-09","core_l1"]))

    def test_actual_new_months_and_calendar_lags_are_extended(self):
        frames,market = self.build()
        self.assertAlmostEqual(.3,frames["headline"].loc["2026-08","cpi_mm"])
        self.assertAlmostEqual(.4,frames["features"].loc["2026-09","core_l1"])
        self.assertAlmostEqual(.8,frames["features"].loc["2026-09","import_l2"])
        self.assertAlmostEqual(0.,frames["features"].loc["2026-09","state"])
        self.assertAlmostEqual(2.,frames["food_features"].loc["2026-09","agri_l1"])
        self.assertTrue(pd.isna(frames["food_features"].loc["2026-09","agri_l0"]))
        self.assertAlmostEqual(-.1,frames["food_features"].loc["2026-09","food_ppi_l1"])

    def test_frozen_history_and_r31c_services_exclusion_preserved(self):
        before = copy.deepcopy(self.loaded.frames)
        frames,market = self.build()
        for key in ("headline","core","regulated","alcohol","components","features","food_features"):
            a = before[key].loc[:"2026-07"]
            pd.testing.assert_frame_equal(frames[key].loc[a.index],a)
            pd.testing.assert_frame_equal(self.loaded.frames[key],before[key])
        self.assertNotIn("services_l1",frames["features"])

    def test_missing_input_month_does_not_shift_calendar_lag(self):
        self.fresh["CZEIIMOM Index"] = self.fresh["CZEIIMOM Index"].iloc[:1]
        frames,_ = self.build()
        self.assertTrue(pd.isna(frames["features"].loc["2026-09","import_l2"]))

    def test_fx_current_month_left_for_asof_gating(self):
        self.fresh["EURCZK CNB Curncy"] = pd.Series([24.,25.,26.],index=pd.DatetimeIndex(["2026-08-20","2026-09-15","2026-09-16"]))
        frames,_ = self.build()
        self.assertTrue(pd.isna(frames["features"].loc["2026-09","eurczk_mm"]))

    def test_new_pumps_follow_iso_monday_and_czk_per_litre(self):
        for ticker,value in (("ECOBETCZ Index",40000.),("ECOBOTCZ Index",39000.)):
            self.fresh[ticker]=pd.Series([value],index=pd.DatetimeIndex(["2026-09-18"]))
        frames,_=self.build()
        self.assertAlmostEqual(40.,frames["weekly_fuel"].loc["2026-09-14","petrol95"])
        self.assertAlmostEqual(39.,frames["weekly_fuel"].loc["2026-09-14","diesel"])

    def test_manual_rows_require_source_units_and_available_clock(self):
        path=self.folder/"manual.csv"
        for source,units,available in (("", "mm_pct","2026-09-01T09:00:00+02:00"),
                                       ("official","yy_pct","2026-09-01T09:00:00+02:00"),
                                       ("official","mm_pct","2026-10-01T09:00:00+02:00")):
            pd.DataFrame([{"series":"core","observation_month":"2026-08","value":.4,"units":units,
                           "source":source,"available_from":available}]).to_csv(path,index=False)
            with self.assertRaises(ValueError):
                cb.load_manual(path,"2026-09-22T17:00:00+00:00")

    def test_snapshot_corruption_rejected_before_parse(self):
        (self.folder/"history_long.csv").write_text("bad data")
        (self.folder/"MANIFEST.json").write_text(json.dumps({"sha256":{"history_long.csv":"0"*64}}))
        with self.assertRaisesRegex(ValueError,"hash"):
            cb.load_snapshot(self.folder,"2026-09-22T17:00:00+00:00")


if __name__=="__main__":
    unittest.main()
