"""Lazy production model call; genuine dependencies only, scoped calendar overlay."""
from contextlib import contextmanager
import importlib
import importlib.metadata
import importlib.util
import os
from pathlib import Path
import platform
import threading

from .adapter import readiness, decision_clock, sha_bytes

PACKAGES = {'numpy': 'numpy', 'pandas': 'pandas', 'scipy': 'scipy', 'sklearn': 'scikit-learn',
            'statsmodels': 'statsmodels', 'quantile_forest': 'quantile-forest', 'duckdb': 'duckdb', 'requests': 'requests'}
_LOCK = threading.RLock()


def runtime_readiness():
    reasons, packages = [], {}
    for module, package in PACKAGES.items():
        try:
            spec = importlib.util.find_spec(module)
            found = bool(spec and spec.origin and Path(spec.origin).is_file())
        except (ValueError, ImportError):
            found = False
        try:
            version = importlib.metadata.version(package) if found else None
        except importlib.metadata.PackageNotFoundError:
            version = None
        packages[package] = {'found': found, 'version': version}
        if not found:
            reasons.append({'code': 'missing_dependency', 'package': package, 'action': f'Install real {package} in the interpreter used for run'})
    x13 = Path(os.environ.get('CZ_X13_PATH', Path.home() / 'x13as/x13as/x13as.exe'))
    if not x13.is_file():
        reasons.append({'code': 'missing_x13', 'path': str(x13), 'action': 'Set CZ_X13_PATH to the installed X13 executable'})
    return {'ready': not reasons, 'reasons': reasons, 'python': platform.python_version(), 'packages': packages,
            'x13_path': str(x13), 'x13_sha256': sha_bytes(x13.read_bytes()) if x13.is_file() else None,
            'check': 'module discovery only; binary import/execution is verified by run'}


@contextmanager
def calendar_scope(model, calendar):
    # CLI is the supported isolation boundary. Do not share cz_struct with other
    # forecast calls in a concurrent process; its caches are module globals.
    with _LOCK:
        old = model._CAL
        try:
            model._CAL = calendar.copy(deep=True)
            yield
        finally:
            model._CAL = old


def calculate(frames, target, as_of, calendar):
    runtime = runtime_readiness()
    if not runtime['ready']:
        raise RuntimeError('model dependencies unavailable: ' + ', '.join(r.get('package', r['code']) for r in runtime['reasons']))
    preflight = readiness(frames, target, decision_clock(as_of), calendar)
    if not preflight['data_ready']:
        raise ValueError('model inputs not ready: ' + ', '.join(r['code'] for r in preflight['reasons']))
    # Import all real dependencies to surface DLL/transitive failures explicitly.
    for module in PACKAGES:
        importlib.import_module(module)
    import cz_struct
    import forecast_independent
    with calendar_scope(cz_struct, calendar):
        result = forecast_independent.calculate(frames, target, as_of)
    return result
