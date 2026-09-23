"""Probe F: are the tests meaningful? In-memory mutants of the delivered modules, run against the delivered tests.

No file is modified: each mutant is the module source with one string replaced, executed into a fresh
module object that temporarily replaces the real one in sys.modules while the test file is imported
and its test functions are called. A mutant that every test still passes is a behaviour no test pins.
"""
import importlib
import importlib.util
import sys
import types
import warnings
from pathlib import Path

from _common import ROOT, Report

warnings.filterwarnings('ignore')
R = Report('F mutation check of the test suite')
TESTS = {'r23b': ROOT / 'tests/test_cost_pressure_r23b.py', 'diag': ROOT / 'tests/test_path_diagnostics.py'}

MUTANTS = [
    # module, label, old, new, test file
    ('data.cost_pressure_r23b', 'ULC compares with the previous three quarters, not the same quarter of three years', 'used = [ref - 12, ref - 8, ref - 4, ref]', 'used = [ref - 3, ref - 2, ref - 1, ref]', 'r23b'),
    ('data.cost_pressure_r23b', 'ULC uses the mean of the three earlier quarters, not the median', 'rel.iloc[-1] - rel.iloc[:-1].median()', 'rel.iloc[-1] - rel.iloc[:-1].mean()', 'r23b'),
    ('data.cost_pressure_r23b', 'ULC reference quarter may be the unfinished current quarter', "if p.asfreq('M', 'end') <= edge]", "if p.asfreq('M', 'start') <= edge]", 'r23b'),
    ('data.cost_pressure_r23b', 'momentum window of seven months', 'window = pd.period_range(ref - 5, ref, freq=\'M\')', 'window = pd.period_range(ref - 6, ref, freq=\'M\')', 'r23b'),
    ('data.cost_pressure_r23b', 'import momentum ignores the publication mask', 'changes = 100 * np.log1p(v.where(v > -100).reindex(window) / 100)', 'changes = 100 * np.log1p(r.values.reindex(window) / 100)', 'r23b'),
    ('data.cost_pressure_r23b', 'core change not subtracted from momentum', 'out[name] = float(upstream - core_change.sum())', 'out[name] = float(upstream)', 'r23b'),
    ('data.cost_pressure_r23b', 'ULC read without its publication mask', "qv = visible(q.values, q.available, edge.asfreq('Q'), clock).where(lambda v: v > 0)", "qv = q.values.loc[q.values.index <= edge.asfreq('Q')].where(lambda v: v > 0)", 'r23b'),
    ('data.cost_pressure_r23b', 'PPI read without its publication mask', 'r = raw[n]; v = visible(r.values, r.available, edge, clock); ref = v.last_valid_index(); dates = []', 'r = raw[n]; v = (visible(r.values, r.available, edge, clock) if n == 26 else r.values.loc[r.values.index <= edge + 2]); ref = v.last_valid_index(); dates = []', 'r23b'),
    ('models.cost_pressure_r23b', 'label maturity off by one month (s+3b <= t)', '((x.index + 3 * band) < t)', '((x.index + 3 * band) <= t)', 'r23b'),
    ('models.cost_pressure_r23b', 'label release date not checked', '& (released <= local(clock)).to_numpy()', '', 'r23b'),
    ('models.cost_pressure_r23b', 'BOTH label-maturity rules removed (month and release)', "okay = ((x.index.month % 3 == 0) & ((x.index + 3 * band) < t) & released.notna().to_numpy() & (released <= local(clock)).to_numpy()", "okay = ((x.index.month % 3 == 0) & (x.index < t) & released.notna().to_numpy()", 'r23b'),
    ('models.cost_pressure_r23b', 'inner folds built with the OUTER origin and clock (full label look-ahead inside validation)', 'inner = eligible(x, y, available, v, clocks.loc[v], band, 16)', 'inner = eligible(x, y, available, origin, clock, band, 16)', 'r23b'),
    ('tools.research_r23b.run', 'band-2 label needs only its own three releases, not all six', "through = pd.period_range(t + 1, t + 3 * b, freq='M')", "through = months", 'r23b'),
    ('tools.research_r23b.run', 'label is the band SUM, not the band mean', "- base).mean()) if complete else np.nan", "- base).sum()) if complete else np.nan", 'r23b'),
    ('models.cost_pressure_r23b', 'band-2 maturity applied to band 1 too (R23-style single rule)', '((x.index + 3 * band) < t)', '((x.index + 6) < t)', 'r23b'),
    ('models.cost_pressure_r23b', 'cap of 40 training rows removed', 'keys = x.index[okay][-40:]', 'keys = x.index[okay]', 'r23b'),
    ('models.cost_pressure_r23b', 'earliest eight folds instead of the latest eight', 'folds = folds[-8:]', 'folds = folds[:8]', 'r23b'),
    ('models.cost_pressure_r23b', 'ties go to applying a correction (<=)', "if scores[str(best)] < zero:", "if scores[str(best)] <= zero:", 'r23b'),
    ('models.cost_pressure_r23b', 'ties among penalties favour the weaker one', 'key=lambda a: (scores[str(a)], -a)', 'key=lambda a: (scores[str(a)], a)', 'r23b'),
    ('models.cost_pressure_r23b', 'do-no-harm ignored when the path is built', "bands.append(result['prediction'] if applied else 0.)", "bands.append(result['prediction'])", 'r23b'),
    ('models.cost_pressure_r23b', 'predictors centred before scaling (an implicit intercept-free demeaning)', 'design = (x / scale).to_numpy(float); test = (current / scale).to_numpy(float)', 'design = ((x - x.mean()) / scale).to_numpy(float); test = ((current - x.mean()) / scale).to_numpy(float)', 'r23b'),
    ('models.cost_pressure_r23b', 'standard-deviation scaling instead of RMS', 'scale = np.sqrt((x.astype(float) ** 2).mean())', 'scale = x.astype(float).std(ddof=0)', 'r23b'),
    ('models.cost_pressure_r23b', 'ridge penalty not scaled by n (sum of squares objective)', 'design.T @ design / n + alpha * np.eye(p), design.T @ target / n)', 'design.T @ design + alpha * np.eye(p), design.T @ target)', 'r23b'),
    ('models.cost_pressure_r23b', 'inner folds need only 4 rows', 'inner = eligible(x, y, available, v, clocks.loc[v], band, 16)', 'inner = eligible(x, y, available, v, clocks.loc[v], band, 4)', 'r23b'),
    ('models.cost_pressure_r23b', 'inner folds scored at the OUTER clock (label look-ahead inside validation)', 'inner = eligible(x, y, available, v, clocks.loc[v], band, 16)', 'inner = eligible(x, y, available, v, clock, band, 16)', 'r23b'),
    ('models.cost_pressure_r23b', 'fewer than four folds still selects', 'if len(folds) < 4:', 'if len(folds) < 1:', 'r23b'),
    ('models.cost_pressure_r23b', 'far bands receive the band-2 correction', 'monthly_correction([*bands, 0., 0.])', 'monthly_correction([*bands, bands[1], bands[1]])', 'r23b'),
    ('tools.path_diagnostics.bootstrap', 'non-circular blocks (clipped at the end)', 'index = ((starts[:, :, None] + np.arange(block)) % n)', 'index = np.minimum(starts[:, :, None] + np.arange(block), n - 1)', 'diag'),
    ('tools.path_diagnostics.bootstrap', 'block rule 12 from 24 observations', 'return 12 if n >= 48 else 6 if n >= 24 else None', 'return 12 if n >= 24 else 6 if n >= 12 else None', 'diag'),
    ('tools.path_diagnostics.attribution', 'h0 contribution NOT dropped at h12', 'if h == 12:\n            row[0] = 0.', 'if h == 99:\n            row[0] = 0.', 'diag'),
    ('tools.path_diagnostics.attribution', 'months before the origin skipped instead of counted as zero', 'values.append(np.zeros(len(columns))); continue', 'continue', 'diag'),
    ('tools.path_diagnostics.attribution', 'dominant block ignores the direction of the error', "signed = {p: float(parts['c_' + p]) * np.sign(row['model_error']) for p in PARTS}", "signed = {p: abs(float(parts['c_' + p])) for p in PARTS}", 'diag'),
    ('tools.path_diagnostics.benchmarks', 'seasonal naive may use the origin month itself', 'known = rates[(rates.index < origin)', 'known = rates[(rates.index <= origin)', 'diag'),
    ('tools.path_diagnostics.benchmarks', 'seasonal naive ignores publication dates', '& released.notna().to_numpy() & (released <= clock).to_numpy()].dropna()', '].dropna()', 'diag'),
    ('tools.path_diagnostics.lead_baselines', 'base rates treat the origin month as known history', 'values = [actual.get(m, np.nan) if m < origin else constant', 'values = [actual.get(m, np.nan) if m <= origin else constant', 'diag'),
    ('tools.path_diagnostics.lead_baselines', 'random walk carries the origin-month rate (unknown at the clock)', 'last_known = float(actual_yy.get(origin - 1, np.nan))', 'last_known = float(actual_yy.get(origin, np.nan))', 'diag'),
    ('tools.path_diagnostics.gates', 'needed-vs-applied correlation on active rows only', "correlation=float(frame.needed.corr(frame.applied)) if varies else np.nan", "correlation=float(active.needed.corr(active.applied)) if varies else np.nan", 'diag'),
]


def run_tests(path, tag):
    spec = importlib.util.spec_from_file_location(f'_mutation_{tag}', path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    failed = []
    for name in sorted(n for n in dir(module) if n.startswith('test_')):
        try:
            getattr(module, name)()
        except BaseException as error:                                   # pytest.fail raises BaseException subclasses
            failed.append(f'{name} ({type(error).__name__})')
    return failed


baseline = {k: run_tests(p, 'base_' + k) for k, p in TESTS.items()}
R.check('unmutated modules: every test function passes when called directly', not any(baseline.values()), str(baseline))
survivors = []
for i, (modname, label, old, new, which) in enumerate(MUTANTS):
    path = ROOT / (modname.replace('.', '/') + '.py'); source = path.read_text(encoding='utf-8')
    if source.count(old) != 1:
        R.check(f'mutant {i:02d} applies cleanly: {label}', False, f'pattern found {source.count(old)} times'); continue
    original = sys.modules.get(modname) or importlib.import_module(modname)
    mutant = types.ModuleType(modname); mutant.__file__ = str(path); mutant.__package__ = modname.rpartition('.')[0]
    sys.modules[modname] = mutant; parent = sys.modules[modname.rpartition('.')[0]]; leaf = modname.rpartition('.')[2]; had = getattr(parent, leaf, None)
    try:
        exec(compile(source.replace(old, new), str(path), 'exec'), mutant.__dict__); setattr(parent, leaf, mutant)
        failed = run_tests(TESTS[which], f'{i}')
    except BaseException as error:
        failed = [f'import error {type(error).__name__}: {error}']
    finally:
        sys.modules[modname] = original
        if had is not None:
            setattr(parent, leaf, had)
    print(f'[{"KILLED  " if failed else "SURVIVED"}] {modname.split(".")[-1]:22s} {label}' + (f'  <- {failed[0]}' + (f' (+{len(failed) - 1})' if len(failed) > 1 else '') if failed else ''))
    if not failed:
        survivors.append(label)
after = {k: run_tests(p, 'after_' + k) for k, p in TESTS.items()}
R.check('modules restored: the unmutated tests pass again', not any(after.values()), str(after))
R.check(f'every one of the {len(MUTANTS)} behaviour-changing mutants is caught by some test', not survivors, f'{len(survivors)} survive')
for s in survivors:
    print('   untested behaviour:', s)
R.done()
