"""Verify unchanged dependencies and seal the canonical R22 research delivery."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import platform
ROOT=Path(__file__).resolve().parents[2]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(entries,parent):
    for name,expected in entries.items():
        p=parent/name
        if digest(p)!=expected:raise ValueError('Hash mismatch: '+str(p))
    return len(entries)


def main():
    top=ROOT/'output/research_r22';full=top/'full';ev=full/'evaluation';files=set()
    previous={}
    for r in (18,19,20,21):
        m=ROOT/f'output/research_r{r}/DELIVERY_MANIFEST.json';d=json.loads(m.read_text())
        previous[f'r{r}']=verify(d['files'],ROOT);files.add(m)
    m=json.loads((full/'manifest.json').read_text())
    fitted={'inputs':verify(m['inputs'],ROOT),'outputs':verify(m['outputs'],full)}
    files.update(ROOT/p for p in m['inputs'])
    e=json.loads((ev/'input_manifest.json').read_text())
    evaluated={'inputs':verify(e['inputs'],ROOT),'outputs':verify(e['outputs'],ev)}
    files.update(Path(p) for p in e['inputs'])
    for directory in [full,top/'diagnostics',top/'charts',ROOT/'tools/research_r22',ROOT/'work/research_r22_review']:
        files.update(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    files.update(ROOT/p for p in ['R22_RESULTS_2026-09-15.md','tests/test_transmission_r22.py',
        'tests/test_released_error_research_r21.py','tests/test_policy_anchor_r21.py'])
    result=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),status='seven_fixed_path_candidates_tested_no_promotion',
        canonical_experiment='output/research_r22/full',excluded_obsolete_pilot='output/research_r22/run',
        unchanged_previous_deliveries=previous,fit_manifest_verified=fitted,evaluation_manifest_verified=evaluated,
        tests='16 R22 and related R21 tests passed; independent reviewer also ran seven R22 tests and numerical audit scripts',
        diagnostics='Seasonality equalization, source metadata addendum, ex-post error decomposition and zero-change driver benchmark are post-score explanations; no forecast refit.',
        runtime={'python':platform.python_version(),**{name:importlib.metadata.version(name) for name in ['numpy','pandas','scipy','scikit-learn']}},
        files={p.relative_to(ROOT).as_posix():digest(p) for p in sorted(files)})
    out=top/'DELIVERY_MANIFEST.json';out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    verify(result['files'],ROOT)
    print(json.dumps(dict(files=len(files),previous=previous,fit=fitted,evaluation=evaluated,all_verified=True),indent=2))


if __name__=='__main__':main()
