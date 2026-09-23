"""Integrate verified R18 children, reuse fixed score contracts, publish R18 replay."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from tools.review import evaluate_r17 as previous

CONTROLS=['INDEPENDENT_BRIDGE','STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','DAMPED_P95_Q001_R16','FUEL_ANNUAL_R17']


def r18_branding(text):
    return text.replace('Czech CPI · R17 ·','Czech CPI · R18 ·').replace(
        '<title>CNB Rounds Replayed · R17 · historical</title>',
        '<title>CNB Rounds Replayed · R18 · historical</title>').replace(
        'cnb-rounds-r17-visible-v1','cnb-rounds-r18-visible-v1')


def inputs():
    hashes=c.preserved_hashes();parts=[];names=[]
    for directory in ['output/research_r18_category_verified','output/research_r18_food','output/research_r17/path']:
        root=ROOT/directory;m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        for group,base in [('inputs',ROOT),('outputs',root)]:
            for name,digest in m[group].items():
                path=base/name
                if c.sha(path)!=digest:raise ValueError('Input drift '+str(path))
                hashes[path.relative_to(ROOT).as_posix()]=digest
        hashes[(root/'manifest.json').relative_to(ROOT).as_posix()]=c.sha(root/'manifest.json')
        native=pd.read_csv(root/'native_forecasts.csv',float_precision='round_trip',low_memory=False)
        if directory.endswith('research_r17/path'):native=native[native.model.isin(CONTROLS)]
        else:names.extend(sorted(native.model.unique()))
        parts.append(native)
    hashes[Path(__file__).relative_to(ROOT).as_posix()]=c.sha(Path(__file__))
    return pd.concat(parts,ignore_index=True),names,hashes


def monthly_revisions(native):
    cols=['contribution_'+b for b in ['core','food','administered','alcohol_tobacco','fuel','wedge']]
    records=[]
    for (model,target),g in native[native.h.gt(0)].groupby(['model','target']):
        g=g.sort_values('origin')
        for i in range(1,len(g)):
            old,new=g.iloc[i-1],g.iloc[i]
            if pd.Period(new.origin,'M')-pd.Period(old.origin,'M')!=pd.offsets.MonthEnd(1):continue
            delta={x:new[x]-old[x] for x in cols};total=new.mm_forecast-old.mm_forecast
            finite=np.isfinite([total,*delta.values()]).all()
            if finite and not np.isclose(sum(delta.values()),total,atol=1e-12,rtol=0):raise ValueError('Component revision sum failure')
            records.append(dict(model=model,target=target,old_origin=old.origin,new_origin=new.origin,
                 old_h=int(old.h),new_h=int(new.h),monthly_revision=total,annual_revision=new.yy_exante-old.yy_exante,
                 revision_status='reconciled' if finite else 'unavailable_component_or_total',**delta))
    return pd.DataFrame(records)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'output/research_r18/path_v2');args=p.parse_args()
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    native,names,hashes=inputs()
    if native.duplicated(['origin','h','model']).any():raise ValueError('Duplicate native keys')
    if native.groupby('model').size().ne(90*13).any():raise ValueError('Missing original origin rows')
    forecasts=c.compound(native)
    native.to_csv(out/'native_forecasts.csv',index=False);forecasts.to_csv(out/'forecasts.csv',index=False)
    monthly_revisions(native).to_csv(out/'monthly_component_revisions.csv',index=False)
    c.finish(out,hashes,controls=CONTROLS,models=names,
             notes='Component revisions sum to monthly forecast revision, not annual-rate revision; weights changes included.')
    previous.evaluate(out)
    evaluation=out/'evaluation';payload=json.loads((evaluation/'replay_data.json').read_text(encoding='utf-8'))
    payload['title']='CNB Rounds Replayed | R18 | historical'
    payload['method']=[
        'R18 research replay; frozen monthly origins February2019-July2026. No live September call or untouched holdout.',
        'Monthly rates compound into annual CPI. CNB forecasts are quarterly averages. Both original report/cutoff clocks are retained.',
        'Eighteen national category proxies plus separately measured CNB core feed a small common/temporary/sector trend model; they are not an exact core partition.',
        'Two fixed category filters and a chronological smooth-horizon macro correction are compared with existing controls; early label shortage gives the declared unchanged-parent correction.',
        'Food h0 uses saved independent nowcast news; its fixed fast/slow decay profiles and saved-error selector are research candidates. Headline h0 remains HARD_BASE.',
        'All visible models use the same scored dates regardless of checkboxes. Full/recent results, component scores, both CNB clocks, false turns and report omissions remain available in CSVs.',
        'Annual-index fuel is an existing assumption-conditioned comparator. New household-exposure scenarios have no national point score without identified coverage and baseline.',
        'No consensus, inflation expectations or confidence survey enters these new independent path forecasts. Current-vintage histories and historical classification recoding remain limitations.',
        'Defaults display FAST/current core and the new fast category filter for comparison, not model promotion. Scenario ranges are not probability intervals.'
    ]
    labels={'MCT_SLOW_R18':'Category trend - slow','MCT_FAST_R18':'Category trend - fast',
            'MCT_SIGNALS_R18':'Category trend + hard signals','FOOD_H0_FAST_R18':'Food nowcast news - fast decay',
            'FOOD_H0_SLOW_R18':'Food nowcast news - slow decay','FOOD_H0_SELECT_R18':'Food nowcast news - sequential',
            'FUEL_ANNUAL_R17':'Annual-index fuel scenario'}
    for series in payload['series']:
        if series['kind']=='model':
            series['default']=series['id'] in ['STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','MCT_FAST_R18']
            if series['id'] in labels:series['label']=labels[series['id']];series['short']=series['label']
    c.dump(evaluation/'replay_data.json',payload)
    old=evaluation/'cnb_rounds_replayed_r17.html'
    previous.write_replay(old,payload)
    text=r18_branding(old.read_text(encoding='utf-8'))
    target=evaluation/'cnb_rounds_replayed_r18.html'
    target.write_text(text,encoding='utf-8');old.unlink()
    definitions=json.loads((evaluation/'definitions.json').read_text(encoding='utf-8'))
    definitions['limitations']=payload['method'];c.dump(evaluation/'definitions.json',definitions)
    manifest=json.loads((evaluation/'input_manifest.json').read_text(encoding='utf-8'))
    manifest['inputs'][str(Path(__file__).resolve())]=c.sha(Path(__file__))
    manifest['outputs']={x.name:c.sha(x) for x in evaluation.iterdir() if x.is_file() and x.name!='input_manifest.json'}
    c.dump(evaluation/'input_manifest.json',manifest)
    print('Completed R18 fixed-calendar evaluation:',target,flush=True)


if __name__=='__main__':main()
