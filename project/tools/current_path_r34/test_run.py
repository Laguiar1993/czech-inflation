import unittest
import numpy as np
import pandas as pd
from . import run

class PathAccountingTests(unittest.TestCase):
    def call(self,name,*args):
        function=getattr(run,name,None)
        self.assertTrue(callable(function),name+' must be implemented')
        return function(*args)
    def fixture(self):
        rows=[]
        for h in range(13):
            row=dict(origin='2026-09',h=h,target=str(pd.Period('2026-09','M')+h),model='STATE_FAST_R15',mm_forecast=.2,yy_exante=2.4)
            row.update({'contribution_'+k:.2/6 for k in ('core','food','administered','alcohol_tobacco','fuel','wedge')})
            row.update(weight_food=.2,value_food=1/6)
            rows.append(row)
        return pd.DataFrame(rows)
    def test_food_replacement_preserves_h0_and_other_components(self):
        base=self.fixture(); history=pd.Series(.1,index=pd.period_range('2024-09','2026-08',freq='M'))
        got=self.call('apply_food',base,{h:.8 for h in range(1,13)},history)
        self.assertEqual(got.iloc[0].mm_forecast,.2)
        np.testing.assert_array_equal(got.contribution_core,base.contribution_core)
        self.assertAlmostEqual(got.iloc[1].mm_forecast,.2-.2/6+.16)
        self.assertAlmostEqual(got.iloc[12].yy_exante,100*((1+got.iloc[1].mm_forecast/100)**12-1))
    def test_rejects_incomplete_or_duplicate_horizon(self):
        base=self.fixture();base.loc[12,'h']=11
        with self.assertRaisesRegex(ValueError,'horizon|duplicate'):
            self.call('validate_table',base,.2)
    def test_rejects_wrong_month_label(self):
        base=self.fixture();base.loc[2,'target']='2030-01'
        with self.assertRaisesRegex(ValueError,'target'):
            self.call('validate_table',base,.2)
    def test_rejects_nonconserving_component_sum(self):
        base=self.fixture();base.loc[3,'contribution_food']+=.01
        with self.assertRaisesRegex(ValueError,'contribution'):
            self.call('validate_table',base,.2)
    def test_rejects_replaced_nowcast(self):
        with self.assertRaisesRegex(ValueError,'h0|nowcast'):
            self.call('validate_table',self.fixture(),.3)
    def test_known_history_excludes_future_realised_prices(self):
        x=pd.Series(.1,index=pd.period_range('2024-09','2027-01',freq='M'))
        a=self.call('known_history',x,'2026-09')
        x.loc['2026-09':]=50
        b=self.call('known_history',x,'2026-09')
        pd.testing.assert_series_equal(a,b)
        self.assertEqual(str(a.index.max()),'2026-08')
    def test_rejects_missing_compounding_month(self):
        x=pd.Series(.1,index=pd.period_range('2025-09','2026-08',freq='M')).drop(pd.Period('2026-02','M'))
        with self.assertRaisesRegex(ValueError,'history|month'):
            self.call('known_history',x,'2026-09')

if __name__=='__main__':unittest.main()
