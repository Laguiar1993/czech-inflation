"""Offline setup contract tests; run with --basetemp under work/ (see ENVIRONMENT.md)."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest

SOURCE = Path(__file__).resolve().parent
SHELL = shutil.which('powershell.exe') or shutil.which('pwsh.exe')
pytestmark = pytest.mark.skipif(sys.platform != 'win32' or not SHELL, reason='Windows PowerShell setup')


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / 'checkout with spaces'
    portable = root / 'portable'
    portable.mkdir(parents=True)
    assert (SOURCE / 'setup.ps1').is_file(), 'portable/setup.ps1 must exist'
    for name in ('setup.ps1', 'requirements-runtime.txt'):
        shutil.copy2(SOURCE / name, portable / name)
    return root


def run_setup(root, *args, env=None):
    return subprocess.run(
        [SHELL, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
         '-File', str(root / 'portable' / 'setup.ps1'), *map(str, args)],
        cwd=root.parent, env=env, capture_output=True, text=True, timeout=60,
    )


def test_requires_explicit_python(checkout):
    result = run_setup(checkout)
    assert result.returncode != 0
    assert 'PythonExe' in result.stdout + result.stderr
    assert not (checkout / '.venv').exists()


def test_missing_python_fails_before_writing(checkout):
    result = run_setup(checkout, '-PythonExe', checkout / 'missing.exe')
    assert result.returncode != 0
    assert 'not found' in (result.stdout + result.stderr).lower()
    assert not (checkout / '.venv').exists()


def test_check_only_ignores_inherited_pythonpath(checkout):
    polluted = checkout / 'pollution'
    polluted.mkdir()
    marker = checkout / 'inherited-site-was-loaded'
    (polluted / 'sitecustomize.py').write_text(
        f'from pathlib import Path\nPath({str(marker)!r}).touch()\n', encoding='utf-8')
    env = dict(os.environ, PYTHONPATH=str(polluted), PYTHONHOME=str(polluted))
    result = run_setup(checkout, '-PythonExe', sys.executable, '-CheckOnly', env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    assert not (checkout / '.venv').exists()


def test_existing_nonvenv_directory_is_preserved(checkout):
    venv = checkout / '.venv'
    venv.mkdir()
    marker = venv / 'keep.txt'
    marker.write_text('preserve', encoding='utf-8')
    result = run_setup(checkout, '-PythonExe', sys.executable)
    assert result.returncode != 0
    assert 'pyvenv.cfg' in result.stdout + result.stderr
    assert marker.read_text(encoding='utf-8') == 'preserve'


@pytest.mark.parametrize('config, expected', [
    ('version = 3.14.3\ninclude-system-site-packages = false\n', '3.12'),
    ('version = 3.12.14\ninclude-system-site-packages = true\n', 'system-site-packages'),
])
def test_incompatible_existing_venv_is_preserved(checkout, config, expected):
    venv = checkout / '.venv'
    venv.mkdir()
    cfg = venv / 'pyvenv.cfg'
    cfg.write_text(config, encoding='utf-8')
    result = run_setup(checkout, '-PythonExe', sys.executable)
    assert result.returncode != 0
    assert expected in result.stdout + result.stderr
    assert cfg.read_text(encoding='utf-8') == config


def test_explicit_missing_x13_fails_before_install(checkout):
    result = run_setup(checkout, '-PythonExe', sys.executable,
                       '-X13Path', checkout / 'missing-x13.exe', '-CheckOnly')
    assert result.returncode != 0
    assert 'X13' in result.stdout + result.stderr
    assert not (checkout / '.venv').exists()

@pytest.mark.parametrize('major, minor, bits', [(3, 14, 64), (3, 11, 64), (3, 12, 32)])
def test_rejects_incompatible_selected_interpreter(checkout, major, minor, bits):
    # A tiny executable protocol fixture: avoids requiring several installed Pythons.
    probe = checkout / 'incompatible-python.cmd'
    probe.write_text(
        '@echo off\n' +
        f'echo {{"version":[{major},{minor},0],"bits":{bits},"implementation":"CPython",'
        '"platform":"win32","machine":"AMD64","prefix":"unused","base_prefix":"unused"}\n',
        encoding='ascii')
    result = run_setup(checkout, '-PythonExe', probe)
    assert result.returncode != 0
    assert 'requires Windows x64 CPython 3.12' in ' '.join((result.stdout + result.stderr).split())
    assert not (checkout / '.venv').exists()


def test_check_only_discovers_vendored_x13(checkout):
    binary = checkout / 'portable' / 'vendor' / 'x13as' / 'x13as.exe'
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b'path-only-check')  # CheckOnly never executes the binary.
    env = dict(os.environ)
    env.pop('CZ_X13_PATH', None)
    result = run_setup(checkout, '-PythonExe', sys.executable, '-CheckOnly', env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert str(binary) in result.stdout
    assert not (checkout / '.venv').exists()


def test_new_venv_is_local_even_when_package_install_fails(checkout):
    (checkout / 'portable' / 'requirements-runtime.txt').write_text(
        'deliberately invalid requirement syntax\n', encoding='utf-8')
    env = dict(os.environ)
    env.pop('CZ_X13_PATH', None)
    result = run_setup(checkout, '-PythonExe', sys.executable, env=env)
    assert result.returncode != 0
    assert 'Runtime installation failed' in result.stdout + result.stderr
    venv = checkout / '.venv'
    assert (venv / 'portable-cache').is_dir()
    assert (venv / 'Scripts' / 'python.exe').is_file()
    assert 'include-system-site-packages = false' in (venv / 'pyvenv.cfg').read_text()
    assert not (checkout.parent / '.venv').exists()
