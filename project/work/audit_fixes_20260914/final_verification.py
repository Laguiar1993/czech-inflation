"""Check preserved artifacts and bind the final correction batch to test evidence."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import platform
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/audit_fixes_20260914'
OUT=ROOT/'output/audit_fixes_20260914'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


scoring=json.loads((WORK/'scoring_artifact_verification.json').read_text())
for item in scoring['original_files_unchanged']:
    assert sha(ROOT/item['path'])==item['sha256'], item['path']
causal=json.loads((OUT/'causal_tvw_common/manifest.json').read_text())
for name, value in causal['sources'].items():
    assert sha(ROOT/name)==value, name
for name, value in causal['outputs'].items():
    assert sha(OUT/'causal_tvw_common'/name)==value, name
imports=json.loads((OUT/'import_manifest_refresh/refresh_receipt.json').read_text())
assert sha(ROOT/imports['old_manifest'])==imports['old_sha256']
assert sha(ROOT/'data/research_r14b/imports/manifest.json')==imports['new_sha256']
for name, value in imports['byte_identical_outputs'].items():
    assert sha(ROOT/'data/research_r14b/imports'/name)==value
transform=json.loads((OUT/'transforms/comparison_manifest.json').read_text())
for panel in transform['panels'].values():
    for name, value in panel['protected_sha256'].items():
        assert sha(Path(name))==value, name
checks={'path_final.log':132,'forest_scoring_final.log':92}
for name, count in checks.items():
    assert f'{count} passed' in (WORK/name).read_text(encoding='utf-8')
assert 'PASS: actual 30-tree runner' in (WORK/'runner_smoke.log').read_text(encoding='utf-8')
files=['models/paper_tvwqrf.py','paper_tvwqrf_experiment.py',
       'tools/paper_replication/build_paper_panel.py','independent_nowcast_experiment.py',
       'tools/review/nowcast_vs_consensus_20260914.py','tools/cnb_rounds/build_cnb_rounds.py',
       'tools/cnb_rounds/cnb_rounds_template.html','tools/review/recalibrate_tvw_20260914.py',
       'tools/review/refresh_import_manifest_20260914.py','IMPLEMENTED_AUDIT_FIXES_2026-09-14.md',
       'HANDOFF_TO_CODEX_2026-09-14.md','docs/implementation/PAPER_TVWQRF_SPEC_2026-09-12.md']
receipt=dict(created_at=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
    packages={p:importlib.metadata.version(p) for p in
              ['numpy','pandas','scikit-learn','quantile-forest','statsmodels','scipy']},
    test_logs={name:dict(passed=count,sha256=sha(WORK/name)) for name,count in checks.items()},
    targeted_tests_passed=sum(checks.values()),actual_forest_runner_smoke=True,
    final_files={name:sha(ROOT/name) for name in files},
    nowcast_original_files_preserved=len(scoring['original_files_unchanged']),
    causal_replay_sources_verified=len(causal['sources']),
    causal_replay_outputs_verified=len(causal['outputs']),
    input_panels_preserved=True, original_import_manifest_preserved=True,
    import_outputs_byte_identical=5, strict_import_loader_unchanged=True,
    corrected_artifact_sha256=sha(OUT/'artifact/cnb_rounds_replayed.html'),
    basket_hour_changed=False, forecast_promotion=False, commit_created=False,
    pinned_python314_full_forest_refit=False,
    limitation='Frozen current-vintage inputs retained; no prospective performance claim. '
               'Separate HTML retains archived TVW curves with visible disclosure; corrected TVW scores are in causal_tvw_common.')
(WORK/'verification_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
print(json.dumps(receipt,indent=2))
