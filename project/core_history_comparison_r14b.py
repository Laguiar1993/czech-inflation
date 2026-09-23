"""Evaluation-only identical-recipe comparison of short and extended core history."""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import hashlib,json,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'output/research_r14b/core_history_comparison'
FOLDERS={'short':'output/research_r14/core','extended':'output/research_r14b/core'}
MODELS=('CORE_LOCAL_R14','CORE_LEVEL_RIDGE_R14','CORE_GAP_RIDGE_R14','CORE_GAP_ADAPT_R14','CORE_LEVEL_RF_R14','CORE_GAP_RF_R14')
KEYS=['origin','model','h','target']
METRICS=('yy','core_mm','core_log')

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def read(path):return pd.read_csv(path,float_precision='round_trip')

def eligible(frame):
    result=frame.loc[frame.model.isin(MODELS)&frame.h.between(1,12)].copy()
    if result.duplicated(KEYS).any():raise ValueError('Duplicate model-origin-horizon grid')
    expected=[str(pd.Period(r.origin,'M')+r.h) for r in result.itertuples()]
    if list(result.target)!=expected:raise ValueError('Target differs from origin+h')
    return result

def pair_frames(short,extended,short_core,extended_core):
    panels={}
    for policy,f,c in [('short',short,short_core),('extended',extended,extended_core)]:
        f=eligible(f)[KEYS+['yy_exante','yy_actual']]
        c=eligible(c)[KEYS+['mm_forecast','mm_actual','cumulative_log_forecast','cumulative_log_actual']]
        g=f.merge(c,on=KEYS,how='outer',validate='one_to_one',indicator=True)
        if not g._merge.eq('both').all():raise ValueError('Headline and core grids differ')
        panels[policy]=g.drop(columns='_merge').rename(columns={
            'yy_exante':'yy_'+policy,'yy_actual':'yy_actual_'+policy,
            'mm_forecast':'core_mm_'+policy,'mm_actual':'core_mm_actual_'+policy,
            'cumulative_log_forecast':'core_log_'+policy,'cumulative_log_actual':'core_log_actual_'+policy})
    paired=panels['short'].merge(panels['extended'],on=KEYS,how='outer',validate='one_to_one',indicator=True)
    if not paired._merge.eq('both').all():raise ValueError('Short and extended grids differ')
    paired=paired.drop(columns='_merge')
    for metric in METRICS:
        left=paired[metric+'_actual_short'].to_numpy();right=paired[metric+'_actual_extended'].to_numpy()
        if not np.array_equal(left,right,equal_nan=True):raise ValueError('Changed immutable actual targets')
        paired[metric+'_actual']=left
        paired=paired.drop(columns=[metric+'_actual_short',metric+'_actual_extended'])
    return paired.sort_values(KEYS).reset_index(drop=True)

def errors(pred,truth):
    e=pred-truth
    return dict(rmse=float(np.sqrt(np.mean(e**2))) if len(e) else np.nan,
                mae=float(np.mean(abs(e))) if len(e) else np.nan,
                bias=float(np.mean(e)) if len(e) else np.nan)

def metric_tables(detail):
    paired=[];own=[]
    for sample,mask in [('full',np.ones(len(detail),bool)),('recent_targets',detail.target>='2024-01'),('recent_origins',detail.origin>='2024-01')]:
        for (model,h),d in detail.loc[mask].groupby(['model','h'],sort=True):
            for metric in METRICS:
                truth=d[metric+'_actual'];short=d[metric+'_short'];long=d[metric+'_extended']
                oks=np.isfinite(short)&np.isfinite(truth);okl=np.isfinite(long)&np.isfinite(truth);common=oks&okl
                row=dict(sample=sample,model=model,h=int(h),metric=metric,n_intended=len(d),n_targets=int(np.isfinite(truth).sum()),
                         n_short=int(oks.sum()),n_extended=int(okl.sum()),n_common=int(common.sum()))
                for policy,pred,ok in [('short',short,oks),('extended',long,okl)]:
                    row.update({policy+'_'+key:value for key,value in errors(pred.loc[common],truth.loc[common]).items()})
                    own.append(dict(sample=sample,model=model,h=int(h),metric=metric,policy=policy,n_intended=len(d),n=int(ok.sum()),
                                    **errors(pred.loc[ok],truth.loc[ok])))
                gains=(short.loc[common]-truth.loc[common])**2-(long.loc[common]-truth.loc[common])**2
                row['mse_gain']=float(gains.mean()) if len(gains) else np.nan
                paired.append(row)
    return pd.DataFrame(paired),pd.DataFrame(own)

def verify_local_identity(detail):
    local=detail.loc[detail.model.eq('CORE_LOCAL_R14')]
    if not len(local):raise ValueError('Missing local-core identity control')
    for metric in METRICS:
        if not np.array_equal(local[metric+'_short'].to_numpy(),local[metric+'_extended'].to_numpy(),equal_nan=True):
            raise ValueError('The local core control changed under historical feature extension')
    return dict(status='exact',origins=int(local.origin.nunique()),horizon_rows=len(local),checked_metrics=list(METRICS))

def history_tables():
    rows=[];configs=[]
    for policy,relative in FOLDERS.items():
        folder=ROOT/relative;states=json.loads((folder/'historical_states.json').read_text())
        candidate=read(folder/'sequential_candidates.csv');selected=read(folder/'selection_summary.csv')
        for band,g in selected.groupby('band',sort=True):
            estimated=candidate.loc[candidate.band.eq(band)&candidate.prediction.notna()]
            mature=g.loc[g.n_validation.ge(24)]
            rows.append(dict(policy=policy,band=int(band),first_state=min(states),last_state=max(states),n_states=len(states),
                first_estimated_candidate=estimated.origin.min() if len(estimated) else None,
                n_outer_origins=len(g),n_insufficient_validation=int(g.reason.eq('insufficient_validation').sum()),
                n_selected_default=int(g.config.eq('a30_wexpanding').sum()),n_active_selection=len(mature),
                validation_n_min=int(g.n_validation.min()),validation_n_max=int(g.n_validation.max()),
                last_validation_release=g.validation_last_release.dropna().max() if 'validation_last_release' in g else None,
                core_fallback_policy='none; insufficient validation selects declared default, not a fit fallback'))
            for (config,reason),z in g.groupby(['config','reason'],sort=True):
                configs.append(dict(policy=policy,band=int(band),config=config,reason=reason,n=len(z)))
    return pd.DataFrame(rows),pd.DataFrame(configs)

def dependencies():
    files=[ROOT/p for p in ('core_history_comparison_r14b.py','test_core_history_comparison_r14b.py',
                           'docs/implementation/R14B_CORE_HISTORY_DESIGN.md')]
    for folder in FOLDERS.values():
        p=ROOT/folder;m=json.loads((p/'manifest.json').read_text())
        for name,digest in m['inputs'].items():
            if sha(ROOT/name)!=digest:raise ValueError('Consumed model input hash changed: '+name)
        for name,digest in m['outputs'].items():
            if sha(p/name)!=digest:raise ValueError('Saved model output hash changed: '+name)
        files += [p/'manifest.json']+[p/name for name in ('forecasts.csv','core_outcomes.csv','historical_states.json','sequential_candidates.csv','selection_summary.csv')]
    return {p.relative_to(ROOT).as_posix():sha(p) for p in files}

def run(folder=OUT):
    hashes=dependencies();folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    short=ROOT/FOLDERS['short'];long=ROOT/FOLDERS['extended']
    detail=pair_frames(read(short/'forecasts.csv'),read(long/'forecasts.csv'),read(short/'core_outcomes.csv'),read(long/'core_outcomes.csv'))
    paired,own=metric_tables(detail);history,configs=history_tables();validation=verify_local_identity(detail)
    detail.to_csv(folder/'paired_rows.csv',index=False)
    paired.to_csv(folder/'paired_summary.csv',index=False);own.to_csv(folder/'own_coverage_summary.csv',index=False)
    history.to_csv(folder/'history_coverage.csv',index=False);configs.to_csv(folder/'configuration_counts.csv',index=False)
    dump(folder/'validation.json',validation)
    if hashes!=dependencies():raise ValueError('Comparison sources changed during evaluation')
    output_names=['paired_rows.csv','paired_summary.csv','own_coverage_summary.csv','history_coverage.csv','configuration_counts.csv','validation.json']
    manifest=dict(inputs=hashes,outputs={name:sha(folder/name) for name in output_names},
                  interpretation='Paired identical recipes on common support; own-coverage scores are distinct. Positive mse_gain favors extended history. Evaluation only.')
    dump(folder/'manifest.json',manifest)
    return manifest

def verify(folder=OUT):
    folder=Path(folder);frozen=json.loads((folder/'manifest.json').read_text())
    if frozen['inputs']!=dependencies():raise ValueError('Comparison inputs changed')
    for name,digest in frozen['outputs'].items():
        if sha(folder/name)!=digest:raise ValueError('Comparison payload changed: '+name)
    with tempfile.TemporaryDirectory(prefix='r14b_history_') as tmp,ExitStack() as stack:
        for target in ('socket.socket','socket.create_connection','requests.sessions.Session.request','duckdb.connect'):
            stack.enter_context(patch(target,side_effect=AssertionError('Evaluation replay attempted external access')))
        replay=run(Path(tmp))
        if replay['outputs']!=frozen['outputs']:raise ValueError('Comparison replay mismatch')
    receipt=dict(status='passed',payloads=len(frozen['outputs']),input_artifacts=len(frozen['inputs']))
    dump(folder/'verification_receipt.json',receipt);print(receipt)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--verify',action='store_true');parser.add_argument('--output-dir',type=Path,default=OUT)
    args=parser.parse_args();verify(args.output_dir) if args.verify else run(args.output_dir)
