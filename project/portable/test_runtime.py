import tempfile,unittest,subprocess
from unittest.mock import patch
from pathlib import Path
import pandas as pd
from portable.runtime import announcement_rows,announcements

class AnnouncementTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'ann.csv'
        self.row=dict(effective_month='2027-01',available_from='2026-11-30T09:00:00+01:00',elec_pct=10,gas_pct=5,heat_pct=3,provenance='prospective',source_url='https://eru.gov.cz/test')
    def save(self,**changes):
        row=dict(self.row,**changes);pd.DataFrame([row]).to_csv(self.path,index=False)
    def test_aware_clock_converts_to_model_prague_wall_time(self):
        self.save(available_from='2026-11-30T08:00:00Z');data=announcement_rows(self.path)
        self.assertEqual(data.available_from.iloc[0],pd.Timestamp('2026-11-30T09:00:00'))
    def test_naive_or_unsourced_or_invalid_rate_rejects(self):
        for changes in [dict(available_from='2026-11-30'),dict(source_url=''),dict(elec_pct=-100),dict(provenance='reconstructed')]:
            self.save(**changes)
            with self.assertRaises(ValueError):announcement_rows(self.path)
    def test_scope_restores_model_cache_and_preserves_historical_rows(self):
        import cz_struct
        old=cz_struct._ANN
        self.save()
        with announcements(self.path):
            self.assertIn(pd.Period('2027-01','M'),cz_struct._ANN.index)
            self.assertIsNone(cz_struct._gate_event(pd.Period('2027-01','M'),pd.Timestamp('2026-10-01'),'documented'))
        self.assertIs(cz_struct._ANN,old)
    def test_equivalent_timezone_instants_are_duplicate(self):
        rows=[dict(self.row,available_from='2026-11-30T08:00:00Z'),dict(self.row,available_from='2026-11-30T09:00:00+01:00',elec_pct=100)]
        pd.DataFrame(rows).to_csv(self.path,index=False)
        with self.assertRaisesRegex(ValueError,'Duplicate'):announcement_rows(self.path)
    def test_historical_overlay_rejected(self):
        self.save(effective_month='2026-01')
        with self.assertRaises(ValueError):
            with announcements(self.path):pass
class DoctorTests(unittest.TestCase):
    def test_bloomberg_timeout_is_bounded_and_actionable(self):
        from portable.runtime import doctor
        with patch('portable.runtime.subprocess.run',side_effect=subprocess.TimeoutExpired('probe',20)) as run:
            result=doctor(True)
        self.assertFalse(result['bloomberg']['ready'])
        self.assertIn('20 seconds',result['bloomberg']['reason'])
        self.assertEqual(run.call_args.kwargs['timeout'],20)
if __name__=='__main__':unittest.main()
