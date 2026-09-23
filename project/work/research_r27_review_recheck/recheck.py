"""Re-run the R27 test suites (original plus the reviewer-requested tests) against every mutant copy the reviewer kept.

    python work/research_r27_review_recheck/recheck.py
"""
import importlib.util
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MUTANTS = sorted((ROOT / 'work/research_r27_review/probe_07_mutants/mutants').glob('M*.py'))
RUNNER = '''
import importlib.util, sys
spec = importlib.util.spec_from_file_location('models.food_ecm_r27', sys.argv[1]); mod = importlib.util.module_from_spec(spec)
import models; sys.modules['models.food_ecm_r27'] = mod; models.food_ecm_r27 = mod; spec.loader.exec_module(mod)
import pytest
sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', 'tests/test_food_ecm_r27.py', 'tests/test_food_ecm_r27_review.py']))
'''
rows = []
for mutant in MUTANTS:
    result = subprocess.run([sys.executable, '-c', RUNNER, str(mutant)], cwd=ROOT, capture_output=True, text=True)
    last = [l for l in result.stdout.splitlines() if 'passed' in l or 'failed' in l or 'error' in l]
    rows.append((mutant.name, 'SURVIVED' if result.returncode == 0 else 'killed', last[-1] if last else result.stderr[-200:]))
    print(f'{mutant.name:45s} {rows[-1][1]:9s} {rows[-1][2]}', flush=True)
(ROOT / 'work/research_r27_review_recheck/recheck_results.txt').write_text('\n'.join(f'{n}\t{s}\t{l}' for n, s, l in rows) + '\n', encoding='utf-8')
print('survivors:', [n for n, s, _ in rows if s == 'SURVIVED' and n != 'M00_control_unmodified.py'])
