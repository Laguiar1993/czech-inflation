"""Seal Claude's delivery of 17 September 2026 and verify that every earlier delivery is unchanged.

    python -m tools.claude_20260917.seal
"""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/claude_delivery_20260917'
RUNS = ['output/research_r23b/final', 'output/research_r24/final', 'output/research_r25/final']
DIRECTORIES = [*RUNS, 'output/cnb_tracker_20260917', 'output/current_path_r24', 'output/cnb_ledger_replay_demo', 'data/cnb_mpr_tables_20260917', 'data/research_r25',
               'tools/path_diagnostics', 'tools/research_r23b', 'tools/research_r24', 'tools/research_r25', 'tools/cnb_tracker', 'tools/current_path_r24', 'tools/claude_20260917',
               'work/research_r23_claude_review', 'work/research_r23b_review', 'work/research_r24_review', 'work/research_r25_review', 'work/claude_mutation_recheck_20260917']
FILES = ['REVIEW_TO_CODEX_R23_2026-09-17.md', 'R23B_RESULTS_2026-09-17.md', 'R24_RESULTS_2026-09-17.md', 'R25_RESULTS_2026-09-17.md', 'CNB_TRACKER_RESULTS_2026-09-17.md',
         'HANDOFF_TO_CODEX_R25_2026-09-17.md', 'docs/implementation/R23B_MEASUREMENT_REPAIR_SPEC_2026-09-17.md', 'docs/implementation/R24_FOOD_DRIFT_SPEC_2026-09-17.md',
         'docs/implementation/R25_PANEL_PERSISTENCE_SPEC_2026-09-17.md', 'docs/implementation/CNB_TRACKER_SPEC_2026-09-17.md',
         'data/cost_pressure_r23b.py', 'data/hicp_panel_r25.py', 'models/cost_pressure_r23b.py', 'models/food_drift_r24.py', 'models/panel_persistence_r25.py',
         'tools/recording/cnb_ledger.py', 'tests/test_path_diagnostics.py', 'tests/test_cost_pressure_r23b.py', 'tests/test_r23b_review_mutants.py', 'tests/test_food_drift_r24.py',
         'tests/test_panel_persistence_r25.py', 'tests/test_cnb_tracker.py', 'tests/test_cnb_ledger.py', '.gitattributes']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(entries, parent):
    for name, expected in entries.items():
        path = Path(name) if Path(name).is_absolute() else parent / name
        if digest(path) != expected:
            raise ValueError('Hash mismatch: ' + str(path))
    return len(entries)


def main():
    previous = {}
    for r in (18, 19, 20, 21, 22, 23):
        manifest = json.loads((ROOT / f'output/research_r{r}/DELIVERY_MANIFEST.json').read_text()); previous[f'r{r}'] = verify(manifest['files'], ROOT)
    runs = {}
    for run in RUNS:
        m = json.loads((ROOT / run / 'manifest.json').read_text()); e = json.loads((ROOT / run / 'evaluation/input_manifest.json').read_text())
        runs[run] = dict(fit_inputs=verify(m['inputs'], ROOT), fit_outputs=verify(m['outputs'], ROOT / run),
                         evaluation_inputs=verify(e['inputs'], ROOT), evaluation_outputs=verify(e['outputs'], ROOT / run / 'evaluation'))
    files = set(ROOT / f for f in FILES)
    for directory in DIRECTORIES:
        files.update(p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        raise FileNotFoundError(missing)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    OUT.mkdir(parents=True, exist_ok=True)
    result = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), author='Claude (Fable 5.1), session of 17 September 2026', git_head_when_sealed=head,
                  status=dict(R23_review='delivery reproduces byte for byte; diagnosis revised', R23B='six candidates, none promoted, lane closed',
                              R24='FOOD_NORM_SHIFT_R24 meets all four declared conditions; research roster food path; historical evidence only',
                              R25='four candidates, none promoted; regime trade-off as anticipated', CNB_tracker='tables archived, block attribution kept, regression tracker not established',
                              ledger='tool and replay demonstration only; prospective ledger not started'),
                  unchanged_previous_deliveries=previous, run_manifests_verified=runs,
                  tests='93 tests pass: 68 new in seven files plus the 25 R23/R22/R21 targeted tests; both reviewers mutant lists (45) are killed',
                  runtime={'python': platform.python_version(), **{n: importlib.metadata.version(n) for n in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'openpyxl']}},
                  files={p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)})
    (OUT / 'DELIVERY_MANIFEST.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    verify(result['files'], ROOT)
    print(json.dumps(dict(files=len(files), previous=previous, runs=runs, all_verified=True), indent=1))


if __name__ == '__main__':
    main()
