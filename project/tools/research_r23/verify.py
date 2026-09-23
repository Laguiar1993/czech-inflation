"""Capture final R23 test/probe evidence without modifying fitted artifacts."""
from pathlib import Path
from datetime import datetime, timezone
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]


def main():
    jobs=[['-m','pytest','tests/test_cost_gaps_r23.py','tests/test_transmission_r22.py',
        'tests/test_released_error_research_r21.py','tests/test_policy_anchor_r21.py',
        '-q','-p','no:cacheprovider','--basetemp','work/pytest_r23_seal'],
        ['work/research_r23_review/probes.py'],
        ['work/research_r23_review/output_checks.py','output/research_r23/final'],
        ['work/research_r23_review/evaluation_checks.py','output/research_r23/final']]
    runs=[]
    for args in jobs:
        p=subprocess.run([sys.executable,*args],cwd=ROOT,capture_output=True,text=True,timeout=180)
        runs.append(dict(command=[sys.executable,*args],returncode=p.returncode,stdout=p.stdout,stderr=p.stderr))
        print(' '.join(args),p.returncode,flush=True)
        if p.returncode:print(p.stdout,p.stderr);break
    dest=ROOT/'output/research_r23/diagnostics/verification.json'
    dest.write_text(json.dumps(dict(verified_at_utc=datetime.now(timezone.utc).isoformat(),runs=runs,
        all_passed=len(runs)==len(jobs) and all(r['returncode']==0 for r in runs)),indent=2),encoding='utf-8')
    if len(runs)!=len(jobs) or any(r['returncode'] for r in runs):raise SystemExit(1)
    print('All tests and review probes passed; evidence:',dest,flush=True)


if __name__=='__main__':main()
