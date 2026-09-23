import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.inflation_dashboard_r33 import build

class BuildTests(unittest.TestCase):
    def test_relative_run_directories_become_manifest_paths(self):
        with tempfile.TemporaryDirectory(dir=build.HERE) as tmp:
            root=Path(tmp);old=root/'old';new=root/'new'
            for p in (old,new):
                p.mkdir();(p/'evidence.json').write_text('{}')
            with patch('tools.forecast_updates_r33.workflow.compare_runs',return_value={'status':'ok','kind':'replay_revision'}):
                with contextlib.redirect_stdout(io.StringIO()):
                    build.build(root/'page',old.relative_to(build.ROOT),new.relative_to(build.ROOT))
            manifest=json.loads((root/'page/manifest.json').read_text())
            for p in (old,new):
                self.assertIn((p/'evidence.json').relative_to(build.ROOT).as_posix(),manifest['inputs'])

    def test_live_card_requires_prospective_matching_target(self):
        from tools.inflation_dashboard_r33 import analysis
        record=dict(mode='replay',target='2026-09',as_of='2026-09-22T17:00:00Z',
                    recorded_at='2026-09-22T17:00:00Z',forecast=dict(point=.2,components={'core':.2}),model='HARD_BASE')
        with patch('tools.forecast_updates_r33.workflow.load_run',return_value=record):
            with self.assertRaisesRegex(ValueError,'prospective'):
                build.current_forecast(Path('unused'),analysis.assemble())
        record['mode']='prospective';record['target']='2026-07'
        with patch('tools.forecast_updates_r33.workflow.load_run',return_value=record):
            with self.assertRaisesRegex(ValueError,'target'):
                build.current_forecast(Path('unused'),analysis.assemble())
        record['target']='2026-09'
        with patch('tools.forecast_updates_r33.workflow.load_run',return_value=record):
            live=build.current_forecast(Path('unused'),analysis.assemble())
            self.assertEqual(live['status'],'recorded')
            self.assertEqual(live['point'],.2)

    def test_invalid_pair_does_not_create_output(self):
        with tempfile.TemporaryDirectory(dir=build.HERE) as tmp:
            out=Path(tmp)/'page'
            with patch('tools.forecast_updates_r33.workflow.compare_runs',return_value={'status':'blocked','reason':'different target'}):
                with self.assertRaisesRegex(ValueError,'different target'):
                    build.build(out,Path(tmp),Path(tmp))
            self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
