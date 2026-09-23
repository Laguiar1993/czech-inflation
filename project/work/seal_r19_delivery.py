from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from tools.research_r18.forecast_archive import verify_bundle
bundle=root/'output/research_r19/recorded_final/bec49dd5-e318-4373-9d3a-be7d97991b91'
payload=verify_bundle(bundle,verify_artifacts=True)
assert payload['record_type']=='historical_replay' and payload['path_forecasts']==[]
assert payload['metadata']['freshness_policy']['completion_age_limit_at_handoff_seconds']==120
manifest=json.loads((root/'output/research_r18/DELIVERY_MANIFEST.json').read_text())
for name,digest in manifest['files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,name
files=[root/p for p in ['R19_RESULTS_2026-09-15.md','docs/implementation/R19_RECORDING_PLAN_2026-09-15.md',
    'tools/recording/verified_nowcast.py','tests/test_verified_nowcast_recording.py','tests/test_r19_recording_audit.py',
    'work/audit_r19_delivery.py','work/pull_r19_eru.py','work/pull_r19_eru_methodology.py','work/seal_r19_delivery.py',
    'work/research_r19_review/REVIEW_2026-09-15.md']]
for directory in ['output/research_r19/evidence','output/research_r19/engine_runs','output/research_r19/recorded_final',
                  'data/research_r19/eru_offers_20260915_complete']:
    files += [p for p in (root/directory).rglob('*') if p.is_file()]
receipt=dict(created_at_utc=datetime.now(timezone.utc).isoformat(),status='recording_adapter_verified_no_model_promotion',
    test_count=56,original_r18_files_unchanged=len(manifest['files']),
    verified_replay_bundle=str(bundle.relative_to(root)),
    files={str(p.relative_to(root)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))})
target=root/'output/research_r19/DELIVERY_MANIFEST.json'
target.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in receipt['files'].items())
print(json.dumps({'r19_files_verified':len(receipt['files']),'r18_files_unchanged':len(manifest['files']),
    'bundle_mode':payload['mode'],'manifest':str(target)}))
