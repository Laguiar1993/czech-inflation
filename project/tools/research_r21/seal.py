"""Verify upstream deliveries and seal research-only R21 evidence."""
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
ROOT=Path(__file__).resolve().parents[2]


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    prior={}
    for round_ in ['r18','r19','r20']:
        m=json.loads((ROOT/f'output/research_{round_}/DELIVERY_MANIFEST.json').read_text())
        for name,digest in m['files'].items():
            if sha(ROOT/name)!=digest:raise ValueError('Earlier delivery changed: '+name)
        prior[round_]=len(m['files'])
    files={};checks=[]
    for folder in ['nowcast','path','path_anchor']:
        d=ROOT/'output/research_r21'/folder;m=json.loads((d/'manifest.json').read_text())
        for group,parent in [('inputs',ROOT),('outputs',d)]:
            for name,digest in m[group].items():
                p=parent/name
                if sha(p)!=digest:raise ValueError('Experiment drift: '+str(p))
                files[p.relative_to(ROOT).as_posix()]=digest
        checks.append(folder)
        if folder!='nowcast':
            m=json.loads((d/'evaluation/input_manifest.json').read_text())
            for group,parent in [('inputs',ROOT),('outputs',d/'evaluation')]:
                for name,digest in m[group].items():
                    p=parent/name
                    if sha(p)!=digest:raise ValueError('Evaluation drift: '+str(p))
                    files[p.relative_to(ROOT).as_posix()]=digest
    extras=['R21_RESULTS_2026-09-15.md','models/released_error_research_r21.py','models/policy_anchor_r21.py',
        'tests/test_released_error_research_r21.py','tests/test_policy_anchor_r21.py','docs/implementation/R21_RESEARCH_SPEC_2026-09-15.md',
        'docs/implementation/R21B_ANCHOR_SPEC_2026-09-15.md','output/contribution_report.csv','output/independent_nowcast_diagnostics.json']
    paths=[ROOT/p for p in extras]
    for directory in ['tools/research_r21','output/research_r21','work/research_r21_review']:
        paths.extend(p for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='DELIVERY_MANIFEST.json')
    for p in paths:files[p.relative_to(ROOT).as_posix()]=sha(p)
    result=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),status='twelve_research_candidates_tested_no_live_promotion',
                nowcast_candidates=4,path_candidates=8,first_batch_spec='docs/implementation/R21_RESEARCH_SPEC_2026-09-15.md',
                second_stage='Anchor hypothesis declared after initial results; not untouched pre-registration.',test_count=24,
                previous_delivery_files_unchanged=prior,verified_experiments=checks,
                runtime={'python':platform.python_version(),**{n:importlib.metadata.version(n) for n in ['numpy','pandas','scipy','scikit-learn','quantile-forest']}},
                files=dict(sorted(files.items())))
    out=ROOT/'output/research_r21/DELIVERY_MANIFEST.json';out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(file_count=len(files),test_count=24,earlier_files_unchanged=prior,manifest=str(out)),indent=2))


if __name__=='__main__':main()
