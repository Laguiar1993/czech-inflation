"""Append two declared long-run-anchor paths, without changing first-batch R21."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from models.policy_anchor_r21 import core_anchor,anchored_path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    files=['output/research_r21/path/native_forecasts.csv','output/research_r15/states.json',
           'tests/fixtures/cleanup/cnb_core_mm.csv','output/independent_path_frozen_inputs.csv','data/release_calendar_cz_cpi.csv',
           'models/policy_anchor_r21.py','docs/implementation/R21B_ANCHOR_SPEC_2026-09-15.md',Path(__file__).relative_to(ROOT).as_posix()]
    prior=json.loads((ROOT/'output/research_r21/path/manifest.json').read_text());hashes=dict(prior['inputs'])
    for name,digest in prior['outputs'].items():
        path=ROOT/'output/research_r21/path'/name
        if c.sha(path)!=digest:raise ValueError('First-batch drift')
        hashes[path.relative_to(ROOT).as_posix()]=digest
    hashes.update({p:c.sha(ROOT/p) for p in files})
    native=c.read(files[0]);states=json.loads((ROOT/files[1]).read_text());core=c.monthly(files[2],'core')
    headline=c.monthly(files[3],'headline_mm');available=c.publication_dates(headline.index)
    results=[native];diagnostics=[]
    for origin,g in native[native.model.eq('STATE_FAST_R15')].groupby('origin'):
        t=pd.Period(origin,'M');clock=pd.Timestamp(g.as_of_utc.iloc[0]).tz_convert('Europe/Prague').tz_localize(None)
        anchor=core_anchor(core,headline,available,t,clock);state=states[origin]
        # Independent algebraic check of transition alignment against the saved parent.
        parent=anchored_path(state,origin,anchor['anchor_log_monthly'],np.inf)
        np.testing.assert_allclose(g[g.h.gt(0)].set_index('h').value_core.reindex(range(1,13)),list(parent.values()),atol=1e-12,rtol=0)
        for hl in [12,24]:
            name=f'ANCHOR_HL{hl}_R21';frame=c.replace_block(g,'core',anchored_path(state,origin,anchor['anchor_log_monthly'],hl))
            frame['model']=name;results.append(frame);diagnostics.append(dict(origin=origin,as_of=clock.isoformat(),model=name,**anchor))
    result=pd.concat(results,ignore_index=True);result.to_csv(out/'native_forecasts.csv',index=False)
    c.compound(result).to_csv(out/'forecasts.csv',index=False);pd.DataFrame(diagnostics).to_csv(out/'anchors.csv',index=False)
    c.finish(out,hashes,controls=prior['controls'],models=prior['models']+['ANCHOR_HL12_R21','ANCHOR_HL24_R21'],
             notes='Second-stage declared after initial R21 scores; no survey or CNB forecast input. Explicit 2% long-run policy reference adjusted for past core-headline spread.')
    print('Finished anchor candidates',out,flush=True)


if __name__=='__main__':main()
