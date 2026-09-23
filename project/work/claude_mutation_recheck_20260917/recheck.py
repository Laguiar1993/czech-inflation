"""Re-run the two independent reviewers' mutants against the test suite as extended after their reviews.

The mutant lists are read verbatim from the reviewers' probe files (parsed, not imported, so nothing of theirs is
re-executed or overwritten). No file is modified: each mutant is source text with one replacement, executed
into a module object that temporarily replaces the real one. Prints which mutants survive.
"""
import ast, importlib, inspect, sys, types, warnings
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); warnings.filterwarnings('ignore')


def literal(path, name):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', None) == name)
    return ast.literal_eval(node.value)


def call_tests(module, fixtures=None):
    failed = []
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        if not name.startswith('test_') or fn.__module__ != module.__name__:
            continue
        params = list(inspect.signature(fn).parameters)
        cases = [dict(origin='2019-02', clock='2019-03-10T23:59:00+01:00'), dict(origin='2024-06', clock='2024-07-09T23:59:00+02:00')] if 'origin' in params else \
                [dict(labels=['Q1', 'Q2', 'Q3', 'Q4'])] if 'labels' in params else [{}]
        for case in cases:
            kwargs = dict(case); patch = pytest.MonkeyPatch()
            if 'monkeypatch' in params: kwargs['monkeypatch'] = patch
            if 'real' in params: kwargs['real'] = fixtures['real']()
            try:
                fn(**kwargs)
            except BaseException as error:
                failed.append(f'{name} ({type(error).__name__})')
            finally:
                patch.undo()
    return failed


def fresh(path, tag):
    spec = importlib.util.spec_from_file_location(tag, path); module = importlib.util.module_from_spec(spec); sys.modules[tag] = module; spec.loader.exec_module(module)
    return module


# ---- R23B reviewer's 37 mutants, against the two original test files plus the file added after the review
mutants = literal(ROOT / 'work/research_r23b_review/probe_F_mutation.py', 'MUTANTS')
files = [ROOT / 'tests/test_cost_pressure_r23b.py', ROOT / 'tests/test_path_diagnostics.py', ROOT / 'tests/test_r23b_review_mutants.py']
base = [f for i, p in enumerate(files) for f in call_tests(fresh(p, f'base{i}'))]
print('unmutated: failing tests =', base); survivors = []
for i, (modname, label, old, new, _) in enumerate(mutants):
    path = ROOT / (modname.replace('.', '/') + '.py'); source = path.read_text(encoding='utf-8'); assert source.count(old) == 1, label
    original = sys.modules.get(modname) or importlib.import_module(modname); parent = sys.modules[modname.rpartition('.')[0]]; leaf = modname.rpartition('.')[2]
    mutant = types.ModuleType(modname); mutant.__file__ = str(path); mutant.__package__ = modname.rpartition('.')[0]
    sys.modules[modname] = mutant; had = getattr(parent, leaf, None)
    try:
        exec(compile(source.replace(old, new), str(path), 'exec'), mutant.__dict__); setattr(parent, leaf, mutant)
        failed = [f for k, p in enumerate(files) for f in call_tests(fresh(p, f'm{i}_{k}'))]
    except BaseException as error:
        failed = [f'import error {type(error).__name__}']
    finally:
        sys.modules[modname] = original
        if had is not None: setattr(parent, leaf, had)
    print(f'[{"KILLED  " if failed else "SURVIVED"}] {label}' + (f'  <- {failed[0]}' if failed else ''))
    if not failed: survivors.append(label)
print(f'R23B: {len(mutants) - len(survivors)} of {len(mutants)} mutants killed; survivors: {survivors}')

# ---- R24 reviewer's mutants, against tests/test_food_drift_r24.py as extended
r24 = literal(ROOT / 'work/research_r24_review/probe_G_test_strength.py', 'MUTANTS'); names = literal(ROOT / 'work/research_r24_review/probe_G_test_strength.py', 'NAMES')
source = (ROOT / 'models/food_drift_r24.py').read_text(encoding='utf-8'); left = []
import models.food_drift_r24 as real_module
from models.food_path_r14 import load_inputs
levels, available, _ = load_inputs()
for label, replacements in r24.items():
    text = source
    for a, b in replacements:
        assert text.count(a) == 1, a; text = text.replace(a, b)
    mutant = types.ModuleType('models.food_drift_r24'); mutant.__file__ = str(ROOT / 'models/food_drift_r24.py'); exec(compile(text, 'mutant', 'exec'), mutant.__dict__)
    sys.modules['models.food_drift_r24'] = mutant
    try:
        tests = fresh(ROOT / 'tests/test_food_drift_r24.py', 'r24_' + label[:2])
        def fixture():
            rates, published = mutant.long_food_rates(levels, available, ROOT / mutant.LONG_HISTORY); return levels, available, rates, published
        failed = call_tests(tests, dict(real=fixture))
    finally:
        sys.modules['models.food_drift_r24'] = real_module
    print(f'[{"KILLED  " if failed else "SURVIVED"}] {label}' + (f'  <- {failed[0]}' if failed else ''))
    if not failed and replacements: left.append(label)
print(f'R24: survivors among {len(r24) - 1} behaviour-changing mutants: {left}')
