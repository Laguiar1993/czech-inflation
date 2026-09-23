"""Verify the completed R20 evidence and previous frozen deliveries."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.research_r18.forecast_archive import verify_bundle


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


old={}
for round_ in ('r18','r19'):
    manifest=json.loads((ROOT/f'output/research_{round_}/DELIVERY_MANIFEST.json').read_text())
    for name,digest in manifest['files'].items():
        assert sha(ROOT/name)==digest, name
    old[round_]=len(manifest['files'])
parity=json.loads((ROOT/'output/research_r20/parity_final/parity_summary.json').read_text())
assert parity['rows']==3510 and parity['failed_checks']==0 and parity['finite_mask_mismatches']==0
run=ROOT/'output/research_r20/runs_final/20260915T082214Z_e1d40da2'
receipt=json.loads((run/'receipt.json').read_text())
for name,digest in receipt.items():assert sha(run/name)==digest,name
bundles=list((ROOT/'output/research_r20/archive_final').glob('*/COMMITTED.json'))
assert len(bundles)==3
for seal in bundles:
    item=verify_bundle(seal.parent,verify_artifacts=True)
    assert item['mode']=='replay' and len(item['path_forecasts'])==13
html=(run/'current_paths.html').read_text(encoding='utf-8')
assert html.count('<tr data-model=')==39 and html.count('<option value=')==3
assert 'historical_replay' in html and 'This chart is a historical fixture' in html
assert all((run/p).is_file() for p in ('path_chart.svg','path_chart.png','path.csv','snapshot.json','readiness.json'))
files=[ROOT/'R20_RESULTS_2026-09-15.md',ROOT/'models/current_path.py',ROOT/'docs/implementation/R20_CURRENT_PATH_PLAN_2026-09-15.md',Path(__file__)]
files+=list((ROOT/'tools/current_path').glob('*.py'))
files+=list((ROOT/'tests').glob('test_*current_path*.py'))+list((ROOT/'tests').glob('test_r20_*.py'))
files+=list((ROOT/'work/research_r20_review').glob('*.md'))
for folder in (run,ROOT/'output/research_r20/archive_final',ROOT/'output/research_r20/parity_final'):
    files += [p for p in folder.rglob('*') if p.is_file()]
manifest=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),status='current_paths_connected_historical_replay_verified',
    test_count=191,previous_delivery_files_unchanged=old,parity=parity,
    final_run=str(run.relative_to(ROOT)),verified_bundles=[str(s.parent.relative_to(ROOT)) for s in bundles],
    files={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(files))})
target=ROOT/'output/research_r20/DELIVERY_MANIFEST.json';target.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
for name,digest in manifest['files'].items():assert sha(ROOT/name)==digest,name
print(json.dumps(dict(r20_files_verified=len(manifest['files']),previous_files_unchanged=old,path_rows=parity['rows'],
    max_difference_pp=parity['max_abs'],verified_replay_bundles=len(bundles))))
