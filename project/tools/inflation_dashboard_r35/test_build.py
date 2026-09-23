import unittest,importlib.util,copy
class RetentionTests(unittest.TestCase):
 def fn(self):
  self.assertIsNotNone(importlib.util.find_spec('tools.inflation_dashboard_r35.build'),'Dashboard assembly required')
  from tools.inflation_dashboard_r35.build import verify_retained
  return verify_retained
 def fixture(self):return {k:{'point':1.2,'clock':'2026-09-22'} for k in ['current_path','live','replay','forecast_context','archive_path']}
 def test_new_analysis_can_be_added_without_changing_forecasts(self):
  before=self.fixture();after=copy.deepcopy(before);after['category_momentum']={'month':'2026-08'}
  self.assertTrue(self.fn()(before,after))
 def test_changed_forecast_or_clock_rejects(self):
  f=self.fn()
  for key in self.fixture():
   before=self.fixture();after=copy.deepcopy(before);after[key]['clock']='2026-08-01'
   with self.assertRaises(ValueError):f(before,after)
 def test_removed_historical_replay_rejects(self):
  before=self.fixture();after=copy.deepcopy(before);after.pop('replay')
  with self.assertRaises(ValueError):self.fn()(before,after)
if __name__=='__main__':unittest.main()
