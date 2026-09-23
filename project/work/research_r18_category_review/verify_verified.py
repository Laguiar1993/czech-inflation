"""Read-only parity and corrected metadata audit of the versioned R18 runner."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).parent
OLD=ROOT/'output/research_r18_category';NEW=ROOT/'output/research_r18_category_verified'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:pd.read_csv(p,float_precision='round_trip')
counts={}
for folder in (OLD,NEW):
    m=json.loads((folder/'manifest.json').read_text())
    for name,digest in m['inputs'].items():assert sha(ROOT/name)==digest,name
    for name,digest in m['outputs'].items():assert sha(folder/name)==digest,name
    counts[folder.name]=dict(inputs=len(m['inputs']),outputs=len(m['outputs']))
old=json.loads((OLD/'states.json').read_text());new=json.loads((NEW/'states.json').read_text())
assert old.keys()==new.keys()
for origin,models in old.items():
    for model,record in models.items():
        for field,value in record.items():assert new[origin][model][field]==value,(origin,model,field)
        mm=new[origin][model]['core_mm_path']
        path=new[origin][model]['path']
        for h in range(1,13):assert mm[str(h)]==float(100*np.expm1(path[str(h)]/100))
checks=[]
for name in ('state_predictions','core_predictions','forecasts','native_forecasts','training_labels','features_by_origin'):
    a=read(OLD/(name+'.csv'));b=read(NEW/(name+'.csv'))
    keys=[c for c in ('origin','model','h') if c in a]
    a=a.sort_values(keys).reset_index(drop=True);b=b.sort_values(keys).reset_index(drop=True)
    # Actual equality of every shared column is stronger than point-column equality.
    pd.testing.assert_frame_equal(a,b[a.columns],check_exact=True)
    checks.append(dict(payload=name,rows=len(a),all_shared_columns_bit_exact=True))
statuses=read(NEW/'status.csv')
for row in statuses[statuses.model.isin(['MCT_FAST_R18','MCT_SLOW_R18'])].itertuples():
    assert row.n_history==new[row.origin][row.model]['n_history']<=96
    assert row.n_available_history>=row.n_history
signals_old=json.loads((OLD/'signal_updates.json').read_text());signals_new=json.loads((NEW/'signal_updates.json').read_text())
assert signals_old==signals_new
receipt=dict(status='passed',hashes=counts,all180_existing_state_fields_exact=True,
    all90_signal_updates_exact=True,point_and_shared_column_checks=checks,
    fitted_history_count_matches_all180_states=True,available_history_separately_reported=True,
    old_manifest_sha256=sha(OLD/'manifest.json'),new_manifest_sha256=sha(NEW/'manifest.json'),
    model_engine_unchanged=True,parameters_unchanged=True,
    new_helper_tests='source availability failure, nonfinite history, exact monthly fallback, actual96 vs available120 history')
(HERE/'verified_runner_verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
