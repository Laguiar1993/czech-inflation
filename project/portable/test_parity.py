import unittest
import numpy as np,pandas as pd
from portable import parity

class ComparisonTests(unittest.TestCase):
    def report(self):return {'ready_for_first_release':True,'food_diagnostics':{'method':'x13'},'points_mm_pct':{'HARD_BASE':0.1,'HARD_HALF':0.2,'HARD_FULL':0.3}}
    def test_invalid_forecasts_never_pass_comparison(self):
        reference=self.report()['points_mm_pct']
        for value in (float('nan'),float('inf'),float('-inf')):
            actual=self.report();actual['points_mm_pct']['HARD_FULL']=value
            with self.subTest(value=value),self.assertRaises(ValueError):parity.compare_points(actual,reference)
        actual=self.report();actual['ready_for_first_release']=False
        with self.assertRaises(ValueError):parity.compare_points(actual,reference)
        actual=self.report();actual['food_diagnostics']['method']='fallback'
        with self.assertRaises(ValueError):parity.compare_points(actual,reference)
    def test_point_roster_and_real_difference_rejected(self):
        actual=self.report();reference=dict(actual['points_mm_pct'])
        actual['points_mm_pct'].pop('HARD_FULL')
        with self.assertRaises(ValueError):parity.compare_points(actual,reference)
        actual=self.report();actual['points_mm_pct']['HARD_BASE']=0.101
        with self.assertRaises(ValueError):parity.compare_points(actual,reference)
        self.assertEqual(max(parity.compare_points(self.report(),reference).values()),0)
        legacy=self.report();legacy['points_mm_pct']['SENTIMENT_BASE']=0.4
        self.assertEqual(max(parity.compare_points(legacy,reference).values()),0)
    def test_path_nan_infinity_duplicate_or_missing_row_rejected(self):
        ref=pd.DataFrame({'model':['A','A'],'h':[0,1],'mm_forecast':[.1,.2],'yy_exante':[2.,2.1],'contribution_food':[.05,.1]})
        for val in (float('nan'),float('inf')):
            bad=ref.copy();bad.loc[1,'mm_forecast']=val
            with self.subTest(value=val),self.assertRaises(ValueError):parity.compare_path(bad,ref)
        for bad in (ref.iloc[:1],pd.concat([ref,ref.iloc[:1]],ignore_index=True)):
            with self.assertRaises(ValueError):parity.compare_path(bad,ref)
        self.assertEqual(parity.compare_path(ref.copy(),ref),0)
if __name__=='__main__':unittest.main()
