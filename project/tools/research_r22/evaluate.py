"""Fixed-support R22 headline/core, driver, response and CNB evaluation."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from tools.review import evaluate_r17 as previous
from tools.review.evaluate_r15 import block_bootstrap

LABELS={'JOINT_OWN_R22':'Matched core-only system','JOINT_DOMESTIC_R22':'Domestic transmission',
        'JOINT_IMPORTED_R22':'Imported-cost transmission','JOINT_LINEAR_R22':'Joint Bayesian ridge',
        'JOINT_ENET_R22':'Joint elastic net','JOINT_RF_R22':'Joint + nonlinear core residual','JOINT_HALF_R22':'Half joint + FAST',
        'CORE_FEEDBACK_R21':'Core error feedback - R21'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();root=args.root
    previous.evaluate(root);out=root/'evaluation'
    drivers=pd.read_csv(root/'driver_forecasts.csv');responses=pd.read_csv(root/'response_diagnostics.csv')
    ds=[];rs=[]
    for (model,variable,h),g in drivers.groupby(['model','variable','h']):
        for sample,z in [('full',g),('origins_2024plus',g[g.origin.ge('2024-01')])]:
            z=z.dropna(subset=['forecast','actual','persistence']);e=z.forecast-z.actual;b=z.persistence-z.actual
            ds.append(dict(model=model,variable=variable,h=h,sample=sample,n=len(z),
                rmse=np.sqrt(np.mean(e**2)),mae=e.abs().mean(),persistence_rmse=np.sqrt(np.mean(b**2)),persistence_mae=b.abs().mean()))
    for (model,variable,h),g in responses.groupby(['model','variable','h']):
        sign=-1 if variable=='unemployment' else 1
        for sample,z in [('full',g),('origins_2024plus',g[g.origin.ge('2024-01')])]:
            v=z.core_cumulative_log_response
            rs.append(dict(model=model,variable=variable,h=h,sample=sample,n=len(z),mean=v.mean(),median=v.median(),
                 minimum=v.min(),maximum=v.max(),opposite_expected_sign=int((sign*v<-.001).sum()),near_zero=int((v.abs()<=.001).sum())))
    pd.DataFrame(ds).to_csv(out/'driver_scoreboard.csv',index=False);pd.DataFrame(rs).to_csv(out/'response_summary.csv',index=False)
    rows=pd.read_csv(out/'primary_rows.csv');boot=[];omissions=[]
    for h,g in rows.groupby('h'):
        actual=g.drop_duplicates('origin').set_index('origin').yy_actual
        errors=g.pivot(index='origin',columns='model',values='yy_exante').sub(actual,axis=0)
        for model in [x for x in errors if x.endswith('_R22')]:
            for sample,mask in [('full',np.ones(len(errors),bool)),('origins_2024plus',errors.index>='2024-01')]:
                e=errors.loc[mask];p=pd.DataFrame(dict(origin=e.index,loss_difference=e[model].to_numpy()**2-e.STATE_FAST_R15.to_numpy()**2))
                boot.append(dict(model=model,h=h,sample=sample,**block_bootstrap(p)))
            for year in sorted(set(errors.index.str[:4])):
                e=errors[~errors.index.str.startswith(year)]
                omissions.append(dict(model=model,h=h,omitted_year=year,n=len(e),rmse_delta=np.sqrt((e[model]**2).mean())-np.sqrt((e.STATE_FAST_R15**2).mean()),
                                       mae_delta=e[model].abs().mean()-e.STATE_FAST_R15.abs().mean()))
    pd.DataFrame(boot).to_csv(out/'primary_support_bootstrap.csv',index=False);pd.DataFrame(omissions).to_csv(out/'leave_one_origin_year_out.csv',index=False)
    payload=json.loads((out/'replay_data.json').read_text());payload['title']='CNB Rounds Replayed | R22 | historical research'
    payload['method']=[
      'R22 fixed research experiment.90 original origins February2019-July2026; same969primary scored keys. Revised histories and reconstructed availability; no untouched holdout or live promotion.',
      'Seven candidates forecast a joint monthly system: core, statistical services/housing/goods proxies, unemployment, quarterly ULC pressure, industrial production, import and producer costs, FX, Brent and metals.',
      'Domestic, imported, full and core-only families share exact training dates and preprocessing. Six lags with fixed shrinkage, stable companion dynamics and released-data conditioning. No parameter selection on these results.',
      'ULC is a quarterly annual-growth proxy carried over three reference months with one publication date. It is not measured monthly wages; early40monthly training rows contain only14 distinct ULC source quarters.',
      'Goods/services/housing averages are incomplete statistical measurements, not official core partitions. CNB core is separately forecast; current basket weights are never imposed on historical category averages.',
      'The nonlinear candidate adds a shrunk forest residual to the linear core recursion. Ragged-edge conditioning remains linear. Perturbed-state responses diagnose associations; they are not identified causal shocks.',
      'Independent HARD_BASE headline h0 and all non-core components/weights remain fixed. Month-t FX/commodity information can condition the internal economic system when already available. h1 is next reference month.',
      'Every model retains original support regardless of checkboxes. Both CNB report/cutoff clocks, false turns, sustained movements, driver errors and report omissions are exported. No CNB forecast, survey or confidence input.',
      'Defaults are visual comparisons, not model promotion. Cumulative/annual inflation is compounded from same-origin monthly rates. Forecast failures and data approximations remain visible.'
    ]
    for s in payload['series']:
        if s['kind']=='model':
            s['default']=s['id'] in ['STATE_FAST_R15','JOINT_LINEAR_R22','JOINT_RF_R22']
            if s['id'] in LABELS:s['label']=s['short']=LABELS[s['id']]
    c.dump(out/'replay_data.json',payload)
    old=out/'cnb_rounds_replayed_r17.html';previous.write_replay(old,payload)
    text=old.read_text(encoding='utf-8').replace('Czech CPI · R17 ·','Czech CPI · R22 ·').replace('CNB Rounds Replayed · R17 · historical','CNB Rounds Replayed · R22 · historical').replace('cnb-rounds-r17-visible-v1','cnb-rounds-r22-visible-v1')
    (out/'cnb_rounds_replayed_r22.html').write_text(text,encoding='utf-8');old.unlink()
    definitions=json.loads((out/'definitions.json').read_text());definitions['limitations']=payload['method']
    definitions['driver_scores']='Same-origin statistical measurements, including quarterly ULClog proxy; seasonal persistence uses latest released observation.'
    definitions['responses']='After internal h0 conditioning, perturb state by published spec units; no refit. Wrong sign is a diagnostic, not proof of causality.'
    c.dump(out/'definitions.json',definitions)
    manifest=json.loads((out/'input_manifest.json').read_text());manifest['inputs'][str(Path(__file__).resolve())]=c.sha(Path(__file__))
    for name in ['driver_forecasts.csv','response_diagnostics.csv']:manifest['inputs'][str((root/name).resolve())]=c.sha(root/name)
    manifest['outputs']={p.name:c.sha(p) for p in out.iterdir() if p.is_file() and p.name!='input_manifest.json'};c.dump(out/'input_manifest.json',manifest)
    print('Completed R22 evaluation',out,flush=True)


if __name__=='__main__':main()
