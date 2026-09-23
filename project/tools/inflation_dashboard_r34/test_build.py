import unittest
import math
from . import build

class CurrentGapTests(unittest.TestCase):
    def call(self,name,*args):
        fn=getattr(build,name,None)
        self.assertTrue(callable(fn),name+' must be implemented')
        return fn(*args)
    def test_recorded_h0_rates_recover_each_contribution(self):
        weights=dict(core=.55,food=.18,fuel=.04,administered=.15,alc=.08)
        contributions=dict(core=-.27,food=-.17,fuel=.19,administered=.02,alcohol_tobacco=.04,wedge=-.01)
        rates=self.call('h0_rates',contributions,weights)
        for name,key in [('core','core'),('food','food'),('fuel','fuel'),('administered','administered'),('alcohol_tobacco','alc')]:
            self.assertAlmostEqual(rates[name]*weights[key],contributions[name])
    def test_missing_h0_cannot_fall_back_to_realised(self):
        with self.assertRaisesRegex(ValueError,'h0|component'):
            self.call('h0_rates',{'food':.1},dict(core=.55,food=.18,fuel=.04,administered=.15,alc=.08))
    def test_zero_weight_rejected(self):
        with self.assertRaisesRegex(ValueError,'weight'):
            self.call('h0_rates',dict(core=0,food=0,fuel=0,administered=0,alcohol_tobacco=0,wedge=0),dict(core=.55,food=.18,fuel=0,administered=.15,alc=.12))
    def test_complete_quarters_only_and_no_nan(self):
        rows=[['2026-09',1.],['2026-10',2.],['2026-11',3.],['2026-12',4.],['2027-01',5.]]
        got=self.call('full_quarters',rows)
        self.assertEqual(got,[{'quarter':'2026Q4','value':3.}])

if __name__=='__main__':unittest.main()
