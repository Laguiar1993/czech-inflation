"""Seal Claude's delivery of 18-20 September 2026 (R26-R29B, the CNB rounds pages) and verify every earlier delivery is unchanged.

    python -m tools.claude_20260920.seal
"""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/claude_delivery_20260920'
PREVIOUS = 'output/claude_delivery_20260917/DELIVERY_MANIFEST.json'
RUNS_WITH_EVALUATION = ['output/research_r27/final', 'output/research_r28/final', 'output/research_r29/final', 'output/research_r29b/final']
RUNS_SINGLE_MANIFEST = ['output/research_r26/final', 'output/cnb_rounds_v2', 'output/cnb_rounds_v3']
DIRECTORIES = [*RUNS_WITH_EVALUATION, *RUNS_SINGLE_MANIFEST, 'data/research_r29', 'tools/research_r26', 'tools/research_r27', 'tools/research_r28', 'tools/research_r29',
               'tools/research_r29b', 'tools/cnb_rounds_v2', 'tools/cnb_rounds_v3', 'tools/claude_20260920', 'work/research_r27_review', 'work/research_r27_review_recheck']
FILES = ['R26_RESULTS_2026-09-18.md', 'R27_RESULTS_2026-09-20.md', 'R28_RESULTS_2026-09-20.md', 'R29_RESULTS_2026-09-20.md', 'HANDOFF_TO_CODEX_R30_2026-09-20.md',
         'docs/implementation/R26_BENCHMARK_FAMILY_AND_PROMOTION_RULE_SPEC_2026-09-18.md', 'docs/implementation/R27_FOOD_ERROR_CORRECTION_SPEC_2026-09-18.md',
         'docs/implementation/R28_ADMINISTERED_LEVEL_SPEC_2026-09-18.md', 'docs/implementation/R29_CORE_PHASE_SPEC_2026-09-18.md', 'docs/implementation/R29B_CORE_PHASE_LEVEL_SPEC_2026-09-18.md',
         'models/benchmarks_r26.py', 'models/food_ecm_r27.py', 'models/administered_level_r28.py', 'models/core_phase_r29.py', 'models/core_phase_r29b.py', 'data/ppi_panel_r29.py',
         'tests/test_benchmarks_r26.py', 'tests/test_food_ecm_r27.py', 'tests/test_food_ecm_r27_review.py', 'tests/test_administered_level_r28.py', 'tests/test_core_phase_r29.py',
         'tests/test_core_phase_r29b.py', 'output/research_r26_run.log', 'output/research_r27_run.log', 'output/research_r27_evaluate.log', 'output/research_r28_run.log',
         'output/research_r28_evaluate.log', 'output/research_r29_run.log', 'output/research_r29_evaluate.log', 'output/research_r29b_run.log', 'output/research_r29b_evaluate.log',
         'output/cnb_rounds_v3_build.log']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(entries, parent):
    for name, expected in entries.items():
        path = Path(name) if Path(name).is_absolute() else parent / name
        if digest(path) != expected:
            raise ValueError('Hash mismatch: ' + str(path))
    return len(entries)


def main():
    previous = json.loads((ROOT / PREVIOUS).read_text(encoding='utf-8'))
    unchanged = dict(delivery_20260917=verify(previous['files'], ROOT), **{k: verify(json.loads((ROOT / f'output/research_r{r}/DELIVERY_MANIFEST.json').read_text())['files'], ROOT) for k, r in [(f'r{r}', r) for r in (18, 19, 20, 21, 22, 23)]})
    runs = {}
    for run in RUNS_WITH_EVALUATION:
        m = json.loads((ROOT / run / 'manifest.json').read_text()); e = json.loads((ROOT / run / 'evaluation/input_manifest.json').read_text())
        runs[run] = dict(fit_inputs=verify(m['inputs'], ROOT), fit_outputs=verify(m['outputs'], ROOT / run),
                         evaluation_inputs=verify(e['inputs'], ROOT), evaluation_outputs=verify(e['outputs'], ROOT / run / 'evaluation'))
    for run in RUNS_SINGLE_MANIFEST:
        m = json.loads((ROOT / run / 'manifest.json').read_text())
        runs[run] = dict(inputs=verify(m['inputs'], ROOT), outputs=verify(m['outputs'], ROOT / run))
    files = set(ROOT / f for f in FILES)
    for directory in DIRECTORIES:
        files.update(p for p in (ROOT / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        raise FileNotFoundError(missing)
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    OUT.mkdir(parents=True, exist_ok=True)
    result = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), author='Claude (Fable 5.1), sessions of 18 and 20 September 2026', git_head_when_sealed=head,
                  status=dict(R26='benchmark family and promotion rule; the sell-side benchmark loses on levels; R24 food re-labelled as a fixed drift',
                              R27='FOOD_ECM_R27 promoted to the research roster as a fixed level correction (speed -0.25), after an independent review; not an estimator',
                              R28='administered level: four candidates, none promoted; the block error is the unforecast January 2023',
                              R29='phase-conditioned core persistence: the panel gate fails; nothing promoted',
                              R29B='level-based phase, fixed pairs: (1.0, 0.8) passes 1, 2, 5 and fails 4 and 6 by a hair; not promoted; shown as research on the rounds page',
                              rounds_page='CNB Rounds Replayed v3, artifact 4Wo4R9YeuJoRXDry2UVgcL (version 2)'),
                  unchanged_previous_deliveries=unchanged, run_manifests_verified=runs,
                  tests='101 tests pass: 33 new in six files (R26 9, R27 8 + 3 review tests, R28 5, R29 5, R29B 3) plus the 68 of 17 September; all 16 R27 review mutants killed',
                  runtime={'python': platform.python_version(), **{n: importlib.metadata.version(n) for n in ['numpy', 'pandas', 'scipy', 'scikit-learn', 'openpyxl']}},
                  files={p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)})
    (OUT / 'DELIVERY_MANIFEST.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    verify(result['files'], ROOT)
    print(json.dumps(dict(files=len(files), previous=unchanged, runs=runs, all_verified=True), indent=1))


if __name__ == '__main__':
    main()
