import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools.forecast_context_r34 import sources,build

CLOCK='2026-09-22T18:30:00Z'
REHEARSAL=sources.ROOT/'work/forecast_context_r34_tests'

class SourceTests(unittest.TestCase):
    def fixtures(self):
        now=[dict(period='2024-01',HARD_BASE='1.0',HARD_HALF='1.2',HARD_FULL='1.4',ready='True')]
        truth=[dict(period='2024-01',actual='1.6',HARD_BASE_C123='1.0')]
        path=[dict(origin='2024-01',h='1',target='2024-02',scored='True',actual_previous='3.0',yy_lane='2.0'),
              dict(origin='2024-01',h='2',target='2024-03',scored='False',actual_previous='999',yy_lane='2.0')]
        return now,truth,path

    def test_source_selection_actual_orientation_and_primary_support(self):
        rows=sources.normalize_history(*self.fixtures())
        self.assertIsInstance(rows,list)
        self.assertEqual(len(rows),2)
        self.assertAlmostEqual(rows[0]['actual']-rows[0]['forecast'],.6)
        self.assertEqual(rows[1]['actual']-rows[1]['forecast'],1.)
        self.assertEqual(rows[1]['h'],1)

    def test_no_duplicate_or_silent_inner_join_support_loss(self):
        now,truth,path=self.fixtures()
        for args in [(now+now,truth,path),(now,truth+truth,path),(now,truth,path+path),
                     (now,[],path),(now,[dict(truth[0],HARD_BASE_C123='2.0')],path),
                     ([dict(now[0],ready='nonsense')],truth,path)]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                sources.normalize_history(*args)

    def test_ready_false_is_preserved_in_fixed_roster(self):
        now,truth,path=self.fixtures()
        now[0]['ready']='False'
        rows=sources.normalize_history(now,truth,path)
        self.assertEqual(sum(r['h']==0 for r in rows),1)

    def test_real_frozen_inputs_keep_ninety_nowcasts(self):
        result=sources.load_historical_errors()
        self.assertIsInstance(result,dict)
        rows=result['errors']
        self.assertEqual(sum(r['h']==0 for r in rows),90)
        self.assertEqual(len({(r['origin'],r['h']) for r in rows}),len(rows))
        self.assertGreater(len(result['inputs']),3)

    def test_recorded_seasonal_archive_and_correct_bundle(self):
        context=sources.load_seasonal(sources.DEFAULT_BUNDLE,sources.DEFAULT_RECORD)
        self.assertIsInstance(context,dict)
        self.assertEqual(context['target'],'2026-09')
        record=json.loads((sources.DEFAULT_RECORD/'result.json').read_text(encoding='utf-8'))
        self.assertEqual(context['point_mm'],record['forecast']['point'])
        for row in context['components']:
            self.assertEqual(row['recorded_contribution_pp'],record['forecast']['components'][row['component']])
        self.assertEqual(context['sample']['n'],11)
        self.assertEqual(context['sample']['end'],'2025-09')
        with self.assertRaises(ValueError):
            sources.load_seasonal(sources.ROOT/'data/bloomberg_inputs_20260922_foodppi',sources.DEFAULT_RECORD)

    def test_model_disagreement_is_separate_from_error_range(self):
        now,_,_=self.fixtures()
        context=sources.historical_disagreement(now,{'2024-01'})
        self.assertIsInstance(context,dict)
        self.assertAlmostEqual(context['samples']['full']['mean_spread_pp'],.4)
        self.assertEqual(context['samples']['2024plus']['n'],1)
        self.assertIn('not',context['definition'])


class ArtifactTests(unittest.TestCase):
    def test_concrete_json_conservation_dates_and_error_units(self):
        context=build.assemble(as_of=CLOCK)
        self.assertIsInstance(context,dict)
        self.assertEqual(context['empirical_ranges']['samples']['full']['0']['n'],90)
        self.assertEqual(context['empirical_ranges']['samples']['2024plus']['0']['n'],31)
        self.assertEqual(context['seasonal']['target'],'2026-09')
        self.assertIsNone(context['base_effect_ledger'])
        recent_h12=context['empirical_ranges']['samples']['2024plus']['12']
        self.assertEqual((recent_h12['n'],recent_h12['status']),(19,'unavailable'))
        self.assertIsNone(recent_h12['lower_offset_pp'])
        json.dumps(context,allow_nan=False)
        s=context['seasonal']
        self.assertAlmostEqual(s['baseline_total_pp']+s['deviation_total_pp'],s['point_mm'])
        self.assertEqual(context['model_disagreement']['samples']['full']['n'],90)
        current=context['model_disagreement']['current']
        self.assertAlmostEqual(current['spread_pp'],.1432948236295375)
        self.assertEqual(current['points_mm']['HARD_BASE'],s['point_mm'])
        self.assertIn('not uncertainty',current['definition'])

    def test_optional_ledger_preserves_h0_and_has_complete_h12(self):
        from .analysis import month_offset
        record=json.loads((sources.DEFAULT_RECORD/'result.json').read_text(encoding='utf-8'))
        point=record['forecast']['point']
        ledger=dict(history_mm={month_offset('2026-09',i):.1 for i in range(-12,0)},
                    forecast_mm={month_offset('2026-09',i):point if i==0 else .2 for i in range(13)})
        result=build.assemble(as_of=CLOCK,ledger_input=ledger)
        self.assertEqual(len(result['base_effect_ledger']),13)
        self.assertEqual(result['base_effect_ledger'][0]['mm'],point)
        ledger['forecast_mm']['2026-09']=100.
        with self.assertRaises(ValueError):build.assemble(as_of=CLOCK,ledger_input=ledger)

    def test_immutable_build_and_hashes_roundtrip(self):
        REHEARSAL.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='artifact_',dir=REHEARSAL) as tmp:
            out=Path(tmp)/'context'
            result=build.build(out,as_of=CLOCK)
            self.assertIsInstance(result,dict)
            self.assertTrue((out/'forecast_context.json').is_file())
            manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'))
            for name,digest in manifest['outputs'].items():
                self.assertEqual(hashlib.sha256((out/name).read_bytes()).hexdigest(),digest)
            before=(out/'forecast_context.json').read_bytes()
            with self.assertRaises(FileExistsError):build.build(out,as_of=CLOCK)
            self.assertEqual((out/'forecast_context.json').read_bytes(),before)

    def test_asof_before_record_rejected_before_output_creation(self):
        REHEARSAL.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='invalid_',dir=REHEARSAL) as tmp:
            out=Path(tmp)/'context'
            with self.assertRaises(ValueError):build.build(out,as_of='2026-09-22T17:00:00Z')
            self.assertFalse(out.exists())


if __name__=='__main__':unittest.main()
