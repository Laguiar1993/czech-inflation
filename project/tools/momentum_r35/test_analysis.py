import unittest
import importlib.util
import numpy as np
import pandas as pd

class MomentumTests(unittest.TestCase):
    def fn(self,name):
        spec=importlib.util.find_spec('tools.momentum_r35.analysis')
        self.assertIsNotNone(spec,'R35 momentum implementation is required')
        from tools.momentum_r35 import analysis
        fn=getattr(analysis,name,None);self.assertTrue(callable(fn),name)
        return fn
    def series(self,rate=.01,n=30):
        return pd.Series(100*(1+rate)**np.arange(n),index=pd.period_range('2023-01',periods=n,freq='M'))
    def test_constant_growth_compounds_at_both_horizons(self):
        f=self.fn('annualised');s=self.series()
        self.assertAlmostEqual(f(s,3).iloc[-1],100*(1.01**12-1),11)
        self.assertAlmostEqual(f(s,6).iloc[-1],100*(1.01**12-1),11)
        self.assertNotAlmostEqual(f(s,3).iloc[-1],12.,5)
    def test_single_price_jump_leaves_three_month_window(self):
        s=self.series(0);s.iloc[20:]*=1.03;m=self.fn('annualised')(s,3)
        self.assertGreater(m.iloc[22],12);self.assertAlmostEqual(m.iloc[23],0)
    def test_acceleration_uses_preceding_nonoverlapping_window(self):
        s=self.series(0);s.iloc[-3:]=[101,102,103]
        r=self.fn('metrics')(s,s)
        self.assertAlmostEqual(r.acceleration.iloc[-1],100*(1.03**4-1),10)
        self.assertAlmostEqual(r.previous_m3.iloc[-1],0)
    def test_rebasing_does_not_change_geometric_block(self):
        a=self.series();b=self.series(.002);d=pd.DataFrame({'a':a,'b':b});w=pd.Series({'a':700.,'b':300.})
        f=self.fn('geometric_index');x=f(d,w);y=f(d*pd.Series({'a':5.,'b':.03}),w)
        np.testing.assert_allclose(x,y,atol=1e-10)
        self.assertAlmostEqual(x.iloc[1],100*(1.01**.7)*(1.002**.3),10)
    def test_missing_component_cannot_disappear_from_weights(self):
        f=self.fn('geometric_index');d=pd.DataFrame({'a':self.series()})
        with self.assertRaises(ValueError):f(d,pd.Series({'a':700.,'b':300.}))
        d.iloc[-1,0]=np.nan
        with self.assertRaises(ValueError):f(d,pd.Series({'a':1000.}))
    def test_log_driver_sum_matches_basket_acceleration(self):
        a=self.series();b=self.series(.002);a.iloc[-3:]*=[1.01,1.02,1.03]
        d=pd.DataFrame({'a':a,'b':b});w=pd.Series({'a':700.,'b':300.})
        parts=self.fn('log_drivers')(d,w);basket=self.fn('geometric_index')(d,w)
        expected=400*np.log(basket/basket.shift(3));expected=expected-expected.shift(3)
        np.testing.assert_allclose(parts.sum(axis=1,min_count=2).dropna(),expected.dropna(),atol=1e-10)
    def test_breadth_missing_coverage_keeps_total_denominator(self):
        b=self.fn('breadth')(pd.Series({'a':.3,'b':-.6,'c':np.nan}),pd.Series({'a':600.,'b':100.,'c':300.}))
        self.assertEqual(b['picking_up'],60.);self.assertEqual(b['cooling'],10.);self.assertEqual(b['missing'],30.);self.assertEqual(b['coverage'],70.)
    def test_direction_has_explicit_deadband(self):
        f=self.fn('direction');self.assertEqual(f(.25),'little_change');self.assertEqual(f(-.25),'little_change')
        self.assertEqual(f(.251),'picking_up');self.assertEqual(f(-.251),'cooling');self.assertEqual(f(np.nan),'unavailable')
    def test_bad_calendar_or_nonpositive_levels_reject(self):
        f=self.fn('annualised');s=self.series()
        with self.assertRaises(ValueError):f(s.drop(s.index[12]),3)
        s.iloc[5]=0
        with self.assertRaises(ValueError):f(s,3)
    def test_partial_driver_coverage_matches_emitted_categories(self):
        from tools.momentum_r35 import analysis
        definitions=analysis.blocks();names=[g for b in definitions.values() for g in b['groups']]
        levels=pd.DataFrame({g:self.series(.001) for g in names});sa=levels.copy()
        w=pd.Series(1000/len(names),index=names)
        meta=pd.DataFrame({'column':names,'label_cs':names,'scope_note':['test']*len(names)})
        diag={g:{'status':'ok','quality_flags':[]} for g in names}
        missing=definitions['food']['groups'][0];sa[missing]=np.nan
        diag[missing]={'status':'unavailable','quality_flags':['Adjustment unavailable']}
        result=analysis.assemble(levels,sa,w,meta,diag,{})
        represented={r['id'] for r in result['drivers']}
        expected=sum(r['weight']/10 for r in result['rows'] if r['id'] in represented)
        self.assertAlmostEqual(result['driver_coverage'],expected)
        self.assertLess(result['driver_coverage'],result['breadth']['coverage'])
        self.assertIsNone(result['driver_total_log_pp'])
        self.assertAlmostEqual(result['driver_partial_log_pp'],sum(r['value'] for r in result['drivers']))
        self.assertFalse(result['driver_complete'])

    def test_partition_covers_all_37_once(self):
        definitions=self.fn('blocks')();ids=[g for b in definitions.values() for g in b['groups']]
        self.assertEqual(len(ids),37);self.assertEqual(len(set(ids)),37);self.assertEqual(len(definitions),9)
        self.assertEqual(definitions['actual_rent']['groups'],['actual_rent'])

if __name__=='__main__':unittest.main()
