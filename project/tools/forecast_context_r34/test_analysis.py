import math
import unittest
import pandas as pd
from tools.forecast_context_r34 import analysis as a


def mm_series(start, values):
    return dict(zip(map(str, pd.period_range(start, periods=len(values), freq="M")), values))


def error_rows(n=30, start="2022-01", h=0):
    return [dict(origin=str(t), target=str(t+h), h=h, forecast=1., actual=1.+i)
            for i,t in enumerate(pd.period_range(start, periods=n, freq="M"))]


def seasonal_fixture():
    idx=pd.period_range("2023-01", "2026-09", freq="M")
    frames={name:pd.DataFrame({col:[v]*len(idx)}, index=idx) for name,col,v in
            [("headline","cpi_mm",.4),("core","core",-.4),
             ("regulated","regulated",.2),("alcohol","alcohol_tobacco",.1)]}
    frames["components"]=pd.DataFrame({"food":-.2,"fuel":1.},index=idx)
    for f in frames.values(): f.loc[pd.Period("2026-09")]=999.
    weights=dict(core=.6,food=.2,administered=.1,alc=.05,fuel=.05)
    contrib=dict(core=-.3,food=-.05,administered=.02,alcohol_tobacco=.01,fuel=.06,wedge=.03)
    forecast=dict(weights=weights,main_contributions_pp=contrib,points_mm_pct={"HARD_BASE":sum(contrib.values())})
    return frames,forecast


class LedgerTests(unittest.TestCase):
    def test_exact_recurrence_removal_then_add_and_full_h12(self):
        hist=mm_series("2025-09",[-.6,.5,-.3,-.3,.9,-.1,.6,.5,.1,-.3,.6,.3])
        forecasts=mm_series("2026-09",[.2]*13)
        rows=a.base_effect_ledger(hist,forecasts)
        self.assertIsInstance(rows,list)
        self.assertEqual(len(rows),13)
        last_yy=100*(math.prod(1+x/100 for x in hist.values())-1)
        all_mm=dict(hist)
        for row,(month,new) in zip(rows,forecasts.items()):
            old=all_mm[str(pd.Period(month)-12)]
            removed=(100+last_yy)/(1+old/100)-100
            yy=(100+removed)*(1+new/100)-100
            self.assertAlmostEqual(row['previous_yy'],last_yy,11)
            self.assertAlmostEqual(row['base_effect_pp'],removed-last_yy,11)
            self.assertAlmostEqual(row['new_price_pp'],yy-removed,11)
            self.assertAlmostEqual(row['base_effect_pp']+row['new_price_pp'],row['change_pp'],11)
            self.assertAlmostEqual(row['yy'],yy,11)
            all_mm[month]=new;last_yy=yy
            rolling=100*(math.prod(1+all_mm[str(pd.Period(month)-i)]/100 for i in range(12))-1)
            self.assertAlmostEqual(row['yy'],rolling,10)
        self.assertGreater(rows[0]['base_effect_pp'],0)
        self.assertEqual(rows[-1]['dropout_mm'],.2)

    def test_equal_new_and_old_preserves_annual_rate(self):
        hist=mm_series("2025-09",[-.6]*12)
        rows=a.base_effect_ledger(hist,{"2026-09":-.6})
        self.assertIsInstance(rows,list)
        self.assertAlmostEqual(rows[0]['change_pp'],0,11)

    def test_no_gap_no_duplicate_no_future_realised(self):
        hist=mm_series("2025-09",[.1]*12)
        for history,forecast in [(hist,{"2026-09":.1,"2026-11":.2}),
             ({k:v for k,v in hist.items() if k!="2026-02"},{"2026-09":.2}),
             (dict(hist,**{"2026-09":123.}),{"2026-09":.2}),
             (list(hist.items())+[('2025-09',.1)],{"2026-09":.2}),
             (hist,[("2026-09",.1),("2026-09",.1)])]:
            with self.subTest(history=history,forecast=forecast),self.assertRaises(ValueError):
                a.base_effect_ledger(history,forecast)

    def test_reject_nonpositive_factor_and_horizon_over_h12(self):
        for forecast in [{"2026-09":-100.},{"2026-09":float('nan')},mm_series("2026-09",[.1]*14)]:
            with self.subTest(forecast=forecast),self.assertRaises(ValueError):
                a.base_effect_ledger(mm_series("2025-09",[.1]*12),forecast)


class EmpiricalTests(unittest.TestCase):
    def test_signed_linear_quantiles_and_separate_samples(self):
        rows=error_rows(30,start="2023-01")
        r=a.empirical_ranges(rows,as_of="2027-01-01T00:00:00Z")
        self.assertIsInstance(r,dict)
        full=r['samples']['full']['0'];recent=r['samples']['2024plus']['0']
        self.assertEqual(full['n'],30)
        self.assertAlmostEqual(full['lower_offset_pp'],2.9)
        self.assertAlmostEqual(full['upper_offset_pp'],26.1)
        self.assertEqual(full['origin_start'],'2023-01')
        self.assertEqual(full['origin_end'],'2025-06')
        self.assertEqual(recent['n'],18)
        self.assertEqual(recent['status'],'unavailable')
        self.assertIsNone(recent['lower_offset_pp'])
        self.assertEqual(full['units'],'mm_percentage_points')

    def test_twenty_finite_errors_required_each_horizon(self):
        rows=error_rows(20,h=1)+error_rows(19,h=2)
        rows.append(dict(origin='2026-01',target='2026-02',h=1,forecast=float('nan'),actual=4))
        r=a.empirical_ranges(rows,as_of="2027-01-01T00:00:00Z")
        self.assertIsInstance(r,dict)
        self.assertEqual(r['samples']['full']['1']['status'],'available')
        self.assertEqual(r['samples']['full']['1']['n'],20)
        self.assertEqual(r['samples']['full']['2']['status'],'unavailable')
        self.assertEqual(r['samples']['full']['1']['units'],'yy_percentage_points')
        self.assertEqual(r['excluded']['nonfinite'],1)

    def test_future_outcomes_excluded_using_date_only_receipt(self):
        rows=error_rows(21,start='2024-01')
        calendar={'2025-09':'2025-10-10'}
        before=a.empirical_ranges(rows,as_of='2025-10-10T12:00:00Z',release_calendar=calendar)
        after=a.empirical_ranges(rows,as_of='2025-10-11T00:00:00Z',release_calendar=calendar)
        self.assertIsInstance(before,dict);self.assertIsInstance(after,dict)
        self.assertEqual(before['samples']['full']['0']['n'],20)
        self.assertEqual(after['samples']['full']['0']['n'],21)
        self.assertEqual(before['excluded']['not_yet_released'],1)

    def test_fallback_waits_until_following_month_complete(self):
        rows=error_rows(21,start='2024-01')
        before=a.empirical_ranges(rows,as_of='2025-10-31T23:59:59Z')
        after=a.empirical_ranges(rows,as_of='2025-11-01T00:00:00Z')
        self.assertIsInstance(before,dict);self.assertIsInstance(after,dict)
        self.assertEqual(before['samples']['full']['0']['n'],20)
        self.assertEqual(after['samples']['full']['0']['n'],21)

    def test_impossible_receipt_cannot_admit_future_target(self):
        row=dict(origin='2026-01',target='2027-01',h=12,forecast=2.,actual=5.)
        with self.assertRaises(ValueError):
            a.empirical_ranges([row],as_of='2026-09-22T18:00:00Z',
                               release_calendar={'2027-01':'2026-01-01'})

    def test_reject_duplicates_wrong_target_naive_clock(self):
        row=error_rows(1)[0]
        for rows,clock in [([row,row],'2027-01-01T00:00:00Z'),
              ([dict(row,target='2022-02')],'2027-01-01T00:00:00Z'),([row],'2027-01-01')]:
            with self.subTest(rows=rows,clock=clock),self.assertRaises(ValueError):
                a.empirical_ranges(rows,as_of=clock)


class SeasonalTests(unittest.TestCase):
    def test_recorded_contributions_fixed_and_mean_at_recorded_weights(self):
        frames,f=seasonal_fixture()
        r=a.seasonal_from_frames(frames,f,target='2026-09',as_of='2026-09-22T18:00:00Z')
        self.assertIsInstance(r,dict)
        rows={x['component']:x for x in r['components']}
        self.assertEqual(len(rows),6)
        self.assertEqual(rows['core']['recorded_contribution_pp'],-.3)
        self.assertAlmostEqual(rows['core']['seasonal_mean_mm'],-.4)
        self.assertAlmostEqual(rows['core']['baseline_contribution_pp'],-.24)
        self.assertAlmostEqual(rows['core']['deviation_pp'],-.06)
        self.assertEqual(r['sample']['months'],['2023-09','2024-09','2025-09'])
        self.assertEqual(r['sample']['n'],3)
        self.assertAlmostEqual(sum(x['baseline_contribution_pp'] for x in rows.values()),.4)
        self.assertAlmostEqual(sum(x['baseline_contribution_pp']+x['deviation_pp'] for x in rows.values()),f['points_mm_pct']['HARD_BASE'])
        self.assertEqual(r['exact_model_seasonal_terms']['status'],'unavailable')
        self.assertIn('disinflation',r['limitations'].lower())

    def test_joint_support_missing_month_is_reported_not_imputed(self):
        frames,f=seasonal_fixture(); frames['core'].loc[pd.Period('2024-09'),'core']=float('nan')
        r=a.seasonal_from_frames(frames,f,target='2026-09',as_of='2026-09-22T18:00:00Z')
        self.assertIsInstance(r,dict)
        self.assertEqual(r['sample']['n'],2)
        self.assertEqual(r['sample']['excluded_incomplete'],['2024-09'])

    def test_invalid_component_totals_or_weights_rejected(self):
        for field in ['sum','weight','duplicate']:
            frames,f=seasonal_fixture()
            if field=='sum':f['points_mm_pct']['HARD_BASE']=100.
            if field=='weight':f['weights']['core']=.8
            if field=='duplicate':frames['core']=pd.concat([frames['core'],frames['core'].iloc[:1]])
            with self.subTest(field=field),self.assertRaises(ValueError):
                a.seasonal_from_frames(frames,f,target='2026-09',as_of='2026-09-22T18:00:00Z')


if __name__=='__main__': unittest.main()
