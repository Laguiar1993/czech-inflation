"""Probe 7: mutation probes of models/food_ecm_r27.py against tests/test_food_ecm_r27.py.

The original file is never touched. Each mutant is a copy under work/research_r27_review/mutants/ with one
exact string replacement (asserted to occur exactly once). For each mutant a fresh interpreter loads the copy
under the module name `models.food_ecm_r27` (sys.modules plus the package attribute) before pytest collects
the test file, so `from models import food_ecm_r27 as m` in the tests resolves to the mutant.
A control run with an unmodified copy must pass, and a sabotaged copy must fail, for the harness to count.
"""
import json
import subprocess
import sys
from pathlib import Path

import probe_common as pc

OUT = pc.HERE / 'probe_07_mutants'; MUT = OUT / 'mutants'
OUT.mkdir(exist_ok=True); MUT.mkdir(exist_ok=True)
ORIGINAL = (pc.ROOT / 'models/food_ecm_r27.py').read_text(encoding='utf-8')
PY = sys.executable

MUTANTS = {
    'M00_control_unmodified': [],
    'M99_sabotage_correction_raises': [("    t = pd.Period(origin, 'M'); out = {h: 0. for h in range(1, 13)}", "    raise RuntimeError('sabotage')\n    t = pd.Period(origin, 'M'); out = {h: 0. for h in range(1, 13)}")],
    'M01_drop_trend': [("x = np.column_stack([np.ones(len(frame)), trend, frame[regressors].to_numpy(float)])", "x = np.column_stack([np.ones(len(frame)), frame[regressors].to_numpy(float)])"),
                       ("trend_per_month=float(beta[1]), **{f'coef_{r}': float(b) for r, b in zip(regressors, beta[2:])}", "trend_per_month=0., **{f'coef_{r}': float(b) for r, b in zip(regressors, beta[1:])}")],
    'M02_flip_sign_of_correction': [("out[h] = float(alpha * gap_last * (1 + alpha) ** steps)", "out[h] = float(-alpha * gap_last * (1 + alpha) ** steps)")],
    'M03_decay_steps_minus_1': [("out[h] = float(alpha * gap_last * (1 + alpha) ** steps)", "out[h] = float(alpha * gap_last * (1 + alpha) ** (steps - 1))")],
    'M04_apply_h1_to_h12': [("ACTIVE_HORIZONS = range(1, 7)", "ACTIVE_HORIZONS = range(1, 13)")],
    'M05_ignore_publication_mask': [("        y.loc[~(dates.notna() & dates.le(clock)), col] = np.nan\n    return y", "        pass\n    return y")],
    'M06_uncentred_gap': [("    return centred, dict(status='estimated', n=len(frame)", "    return residual, dict(status='estimated', n=len(frame)")],
    'M07_clip_at_minus_050': [("ALPHA_CLIP = (-.25, 0.)", "ALPHA_CLIP = (-.5, 0.)")],
    'M08_gap_at_origin_minus_2': [("gap_last = float(gap.loc[last]); variants = {model: alpha}", "gap_last = float(gap.loc[pd.Period(last, 'M') - 1]); variants = {model: alpha}")],
    'M09_no_clip_at_all': [("alpha = float(np.clip(raw, *ALPHA_CLIP))", "alpha = float(raw)")],
    'M10_speed_on_contemporaneous_gap': [("gap.shift(1).rename('gap')", "gap.shift(0).rename('gap')")],
    'M11_no_minimum_window': [("    if len(frame) < min_window:\n        return None, dict(status='insufficient_window', n=len(frame))", "    if len(frame) < 0:\n        return None, dict(status='insufficient_window', n=len(frame))")],
    'M12_positive_alpha_allowed': [("ALPHA_CLIP = (-.25, 0.)", "ALPHA_CLIP = (-.25, .25)")],
    'M13_no_decay_constant_correction': [("out[h] = float(alpha * gap_last * (1 + alpha) ** steps)", "out[h] = float(alpha * gap_last)")],
    'M14_centre_by_window_mean_not_month': [("    means = series.groupby(series.index.month).transform('mean')", "    means = pd.Series(series.mean(), index=series.index)")],
    'M15_window_97_months': [("frame = published.loc[:last, ['food', *regressors]].dropna().iloc[-window:]", "frame = published.loc[:last, ['food', *regressors]].dropna().iloc[-(window + 1):]")],
    'M16_last_common_month_is_last_food_month': [("    complete = published.dropna()\n    if complete.empty:", "    complete = published[['food']].dropna()\n    if complete.empty:")],
}

LOADER = r'''
import sys, importlib.util
sys.path.insert(0, r"{root}")
import models
spec = importlib.util.spec_from_file_location("models.food_ecm_r27", r"{path}")
mod = importlib.util.module_from_spec(spec); sys.modules["models.food_ecm_r27"] = mod; spec.loader.exec_module(mod); models.food_ecm_r27 = mod
import pytest
sys.exit(pytest.main(["tests/test_food_ecm_r27.py", "-q", "-p", "no:cacheprovider", "--tb=line"]))
'''

results = {}
for name, edits in MUTANTS.items():
    text = ORIGINAL
    for old, new in edits:
        assert text.count(old) == 1, (name, old)
        text = text.replace(old, new)
    path = MUT / f'{name}.py'; path.write_text(text, encoding='utf-8')
    proc = subprocess.run([PY, '-c', LOADER.format(root=str(pc.ROOT), path=str(path))], cwd=str(pc.ROOT), capture_output=True, text=True, timeout=600)
    tail = '\n'.join(proc.stdout.strip().splitlines()[-25:])
    (OUT / f'{name}.log').write_text(proc.stdout + '\n--- stderr ---\n' + proc.stderr, encoding='utf-8')
    summary = [l for l in proc.stdout.splitlines() if ' passed' in l or ' failed' in l or 'error' in l.lower()]
    results[name] = dict(exit_code=proc.returncode, survived=(proc.returncode == 0), summary=summary[-1] if summary else tail[-200:])
    print(name, results[name])
(OUT / 'results.json').write_text(json.dumps(results, indent=1), encoding='utf-8')
survivors = [n for n, r in results.items() if r['survived'] and n not in ('M00_control_unmodified',)]
print('control passes:', results['M00_control_unmodified']['survived'], '| sabotage fails:', not results['M99_sabotage_correction_raises']['survived'])
print('survivors:', survivors)
