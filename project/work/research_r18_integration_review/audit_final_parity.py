"""Check final calibration calendar amendment changes no scored distributions."""
from pathlib import Path
import hashlib
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent


def run():
    old=ROOT/'output/research_r18/uncertainty_verified'
    new=ROOT/'output/research_r18/uncertainty_final'
    exact={}
    for name in ['intervals.csv','pools.json','coverage.csv']:
        assert (old/name).read_bytes()==(new/name).read_bytes(),name
        exact[name]=True
    a,b=[pd.read_csv(p/'scores.csv',float_precision='round_trip') for p in [old,new]]
    changed=['n_intended','n_missing_distributions']
    pd.testing.assert_frame_equal(a.drop(columns=changed),b.drop(columns=changed),check_exact=True)
    assert (b.n_intended<=a.n_intended).all()
    assert (a.n_intended-b.n_intended).equals(a.n_missing_distributions-b.n_missing_distributions)
    ledger=pd.read_csv(new/'scored_calendar.csv')
    support=pd.read_csv(ROOT/'output/research_r17/attribution/primary_support.csv')
    assert len(support)==969 and len(ledger)==969*11
    expected=set(support[['origin','h']].itertuples(index=False,name=None))
    for _,g in ledger.groupby('model'):
        assert set(g[['origin','h']].itertuples(index=False,name=None))==expected
    hashes={}
    for relative in ['output/research_r18/path_v2','output/research_r18/path_v2/evaluation','output/research_r18/uncertainty_final']:
        p=ROOT/relative;mp=p/('input_manifest.json' if p.name=='evaluation' else 'manifest.json')
        manifest=json.loads(mp.read_text());counts={}
        for group,base in [('inputs',ROOT),('outputs',p)]:
            for name,digest in manifest[group].items():
                assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest,(relative,group,name)
            counts[group]=len(manifest[group])
        hashes[relative]=counts
    result=dict(status='passed',byte_exact_outputs=exact,
                scores_all_other_columns_bit_exact=True,changed_score_columns=changed,
                final_calendar_rows=len(ledger),original_keys_per_model=969,manifest_verification=hashes)
    (OUT/'final_parity_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':run()
