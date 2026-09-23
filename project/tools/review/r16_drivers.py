"""Exact two-stage fitted contributions; predictive arithmetic, not causal effects."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools.review.r15_drivers import linear_contributions


def transmission_parts(core_row,core_fit,signal_rows,signal_fits):
    parts={'core_intercept':float(core_fit['intercept'])}
    for column in core_fit['columns']:
        if not column.endswith('_projection'):
            parts[column]=linear_contributions(core_row,core_fit)[column]
            continue
        signal=column.removesuffix('_projection')
        beta=core_fit['coefficients'][column];scale=core_fit['scales'][column]
        parts[signal+'_centering']=-beta*core_fit['means'][column]/scale
        for feature,value in linear_contributions(signal_rows[signal],signal_fits[signal]).items():
            parts[signal+'.'+feature]=beta*value/(12*scale)
    return parts


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--experiment',type=Path,required=True)
    args=parser.parse_args(argv);p=args.experiment;out=p/'interpretation';out.mkdir(exist_ok=True)
    read=lambda name:pd.read_csv(p/name,float_precision='round_trip')
    fits=json.loads((p/'fits.json').read_text());states=json.loads((p/'states.json').read_text())
    stage1={(r['origin'],r['band'],r['family']):r for r in fits if r['stage']=='signal'}
    source={s:read(f'signal_features_{s}.csv').set_index('origin') for s in ('services','goods')}
    x=read('stage2_features.csv').set_index(['origin','band','family'])
    predictions=read('core_predictions.csv').set_index(['origin','h','model']).core_log
    outer=set(predictions.index.get_level_values('origin'));rows=[];max_difference=0.;count=0
    for fit in fits:
        t=fit['origin'];band=fit['band'];family=fit['family']
        if fit['stage']!='core' or t not in outer or fit['status']!='estimated':continue
        parts=transmission_parts(x.loc[(t,band,family)],fit,{s:source[s].loc[t] for s in source},
                                 {s:stage1[t,band,s] for s in source})
        total=sum(parts.values());count+=1
        for h in range(1+3*band,4+3*band):
            actual=predictions.loc[(t,h,'TRANSMISSION_'+family.upper()+'_R16')]-states[t]['forecasts_log']['fast'][str(h)]
            max_difference=max(max_difference,abs(actual-total))
        rows.extend(dict(origin=t,band=band,family=family,source=key,log_core_pp=value) for key,value in parts.items())
    if max_difference>1e-10:raise ValueError('End-to-end driver reconstruction mismatch')
    frame=pd.DataFrame(rows);frame.to_csv(out/'source_contributions.csv',index=False)
    frame[frame.origin.eq(max(outer))].to_csv(out/'latest_source_contributions.csv',index=False)
    sha=lambda f:hashlib.sha256(Path(f).read_bytes()).hexdigest()
    names=['fits.json','states.json','stage2_features.csv','core_predictions.csv','signal_features_services.csv','signal_features_goods.csv']
    receipt=dict(explained_fits=count,maximum_reconstruction_error=max_difference,
        units='Monthly log core pp; includes ridge constants and generated-predictor centering; not causal effects.',
        inputs={name:sha(p/name) for name in names},source_sha256=sha(__file__),
        helper_sha256=sha(Path(__file__).with_name('r15_drivers.py')),
        outputs={name:sha(out/name) for name in ('source_contributions.csv','latest_source_contributions.csv')})
    (out/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ('explained_fits','maximum_reconstruction_error')}))


if __name__=='__main__':main()
