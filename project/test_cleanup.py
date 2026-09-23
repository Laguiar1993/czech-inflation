"""Operational cleanup contracts; no live data or network required."""
import importlib
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent


def test_scoreboard_import_does_not_read_data_or_write_outputs(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('import must not load or score data')
    monkeypatch.setattr(pd, 'read_csv', forbidden)
    sys.modules.pop('scoreboards_codex_p0', None)
    importlib.import_module('scoreboards_codex_p0')


def test_active_model_does_not_import_research_drivers():
    code = ('import sys; import cz_struct; '
            'assert not any(n.startswith("backtest_h0") for n in sys.modules)')
    subprocess.run([sys.executable, '-c', code], cwd=ROOT, check=True)


@pytest.mark.parametrize('changes,expected', [
    ({'archive_ok': False}, 'INELIGIBLE_ARCHIVE'),
    ({'archive_ok': 'False'}, 'INELIGIBLE_ARCHIVE'),
    ({'n_imputed': 2}, 'INCOMPLETE_INPUTS'),
    ({'release_stage': 'pre_final'}, 'FINAL_RELEASE_ONLY'),
    ({'release_stage': 'unknown'}, 'UNVERIFIED_STAGE'),
    ({'run_ts': '2026-09-07 07:59'}, 'UNVERIFIED_CLOCK'),
    ({'run_ts': '2026-09-07T08:00:00+00:00'}, 'RETROSPECTIVE'),
    ({}, 'TIMELY_UNVERIFIED'),
])
def test_first_release_evidence_is_not_inferred_from_timestamp_alone(changes, expected):
    from evaluation.prospective import classify_shadow_row
    row = {'archive_ok': True, 'n_imputed': 0, 'release_stage': 'pre_flash',
           'run_ts': '2026-09-07T06:59:00+00:00',
           'release_ts': '2026-09-07T09:00:00+02:00',
           'spec': 'v2.4-live-parity-2026-09-07'}
    row.update(changes)
    assert classify_shadow_row(row)==expected


def test_database_and_x13_paths_can_be_configured(monkeypatch, tmp_path):
    from data import local_adapter as la
    monkeypatch.setenv('CZ_CPI_DB', str(tmp_path/'czechia.duckdb'))
    monkeypatch.setenv('CZ_X13_PATH', str(tmp_path/'x13as.exe'))
    try:
        importlib.reload(la)
        assert la.DB_PATH==tmp_path/'czechia.duckdb'
        assert Path(la._X13_PATH)==tmp_path/'x13as.exe'
    finally:
        monkeypatch.undo()
        importlib.reload(la)
