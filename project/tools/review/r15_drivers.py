"""Exact additive explanation of selected R15 elastic-net residuals; not causal effects."""
from pathlib import Path
import argparse
import json
import hashlib
import numpy as np
import pandas as pd


def linear_contributions(row,info):
    values={'intercept':float(info['intercept'])}
    for column in info['columns']:
        value=row.get(column,np.nan)
        z=(value-info['means'][column])/info['scales'][column] if np.isfinite(value) else 0.
        values[column]=float(z*info['coefficients'][column])
    return values


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,required=True)
    args=parser.parse_args(argv);p=args.experiment;out=p/'interpretation';out.mkdir(exist_ok=True)
    inputs=[p/name for name in ('fits.json','states.json','features_by_origin.csv','core_predictions.csv')]
    fits=json.loads(inputs[0].read_text());states=json.loads(inputs[1].read_text())
    x=pd.read_csv(inputs[2],index_col='origin',float_precision='round_trip')
    pred=pd.read_csv(inputs[3],float_precision='round_trip').set_index(['origin','model','h']).core_log
    rows=[];maxdiff=0.
    for info in fits:
        if info['family']=='forest' or info['status']!='estimated':continue
        t=info['origin'];band=int(info['band']);horizons=range(1+3*band,4+3*band)
        row=x.loc[t].copy();state=states[t]
        row['destination_season']=np.mean([state['seasonal'][str((pd.Period(t,'M')+h).month)] for h in horizons])
        parts=linear_contributions(row,info);total=sum(parts.values())
        for h in horizons:
            actual=pred.loc[(t,'ENET_'+info['family'].upper()+'_R15',h)]-state['forecasts_log']['mid'][str(h)]
            maxdiff=max(maxdiff,abs(total-actual))
        rows.extend(dict(origin=t,band=band,family=info['family'],feature=key,log_core_pp=value) for key,value in parts.items())
    if maxdiff>1e-10:raise ValueError('Linear driver reconstruction mismatch: '+str(maxdiff))
    detail=pd.DataFrame(rows);detail.to_csv(out/'linear_drivers.csv',index=False)
    latest=detail[detail.origin.eq(detail.origin.max())].copy()
    latest['absolute_contribution']=latest.log_core_pp.abs()
    latest.sort_values(['family','band','absolute_contribution'],ascending=[True,True,False]).to_csv(out/'latest_drivers.csv',index=False)
    receipt=dict(max_reconstruction_error=maxdiff,linear_models_explained=len(detail.groupby(['origin','band','family'])),
        meaning='Additive fitted residual contributions in monthly log core pp. Intercept and transformed predictors sum to residual; not causal estimates.',
        inputs={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs},
        tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(receipt['linear_models_explained'], 'linear fits explained; maximum difference',maxdiff)


if __name__=='__main__':main()
