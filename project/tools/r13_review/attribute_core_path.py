"""Post-fit explanatory accounting, never an additional fitted experiment."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from evaluation.core_path_attribution_r13 import replacement_path,error_attribution
from models.path_inputs import compound_path

OUT=ROOT/'output/research_r13/core_attribution'
SOURCES=['tools/r13_review/attribute_core_path.py','evaluation/core_path_attribution_r13.py',
    'models/path_inputs.py','output/research_r13/core_path/native_forecasts.csv',
    'output/research_r13/core_path/forecasts.csv','output/independent_bridge_forecasts.csv',
    'output/independent_path_frozen_inputs.csv','tests/fixtures/cleanup/cnb_core_mm.csv']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(folder):
    hashes={name:sha(ROOT/name) for name in SOURCES}
    read=lambda name:pd.read_csv(ROOT/name,float_precision='round_trip')
    core=read(SOURCES[-1]).set_index('period').iloc[:,0]
    core.index=pd.PeriodIndex(core.index,freq='M')
    frozen=read('output/independent_path_frozen_inputs.csv')
    headline=frozen.set_index(frozen.columns[0]).headline_mm
    headline.index=pd.PeriodIndex(headline.index,freq='M')
    base=read('output/independent_bridge_forecasts.csv')
    base=base[base.model.eq('INDEPENDENT_BRIDGE')]
    pred=read('output/research_r13/core_path/forecasts.csv')
    new=pred[pred.model.str.startswith('CORE_')]
    records=[]
    for origin,group in base.groupby('origin',sort=True):
        t=pd.Period(origin,'M'); replaced=replacement_path(group,core)
        original=group.set_index('h')
        rows=new.loc[new.origin.eq(origin)]
        for h in range(1,13):
            oracle=compound_path(headline.loc[headline.index<t],replaced,t,h,replaced[0])
            for row in rows.loc[rows.h.eq(h)].itertuples():
                reference=float(original.loc[h,'yy_exante'])
                actual=float(row.yy_actual)
                records.append(dict(origin=origin,target=str(t+h),h=h,model=row.model,
                    reference_forecast=reference,candidate_forecast=row.yy_exante,actual=actual,
                    ex_post_core_replaced=oracle,
                    **error_attribution(reference,float(row.yy_exante),actual,oracle)))
    detail=pd.DataFrame(records); summary=[]
    for sample,mask in [('full',np.ones(len(detail),bool)),
                        ('recent_origins',detail.origin>='2024-01'),
                        ('recent_targets',detail.target>='2024-01')]:
        for (model,h),group in detail.loc[mask].groupby(['model','h'],sort=True):
            valid=group.dropna(subset=['headline_squared_gain','core_squared_gain','cross_term_gain'])
            summary.append(dict(sample=sample,model=model,h=h,n=len(valid),
                headline_mse_gain=valid.headline_squared_gain.mean(),
                annual_core_mse_gain=valid.core_squared_gain.mean(),
                cross_term_gain=valid.cross_term_gain.mean(),
                reference_annual_core_rmse=np.sqrt((valid.reference_core_error**2).mean()),
                candidate_annual_core_rmse=np.sqrt((valid.candidate_core_error**2).mean()),
                other_rmse=np.sqrt((valid.other_error**2).mean())))
    folder.mkdir(parents=True,exist_ok=True)
    detail.to_csv(folder/'rows.csv',index=False)
    pd.DataFrame(summary).to_csv(folder/'summary.csv',index=False)
    if hashes != {name:sha(ROOT/name) for name in SOURCES}:
        raise AssertionError('attribution inputs changed during read')
    return hashes


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify:
        manifest=json.loads((OUT/'manifest.json').read_text())
        with tempfile.TemporaryDirectory(prefix='r13_attribution_') as temp:
            other=Path(temp); inputs=run(other)
            if inputs!=manifest['inputs']:
                raise AssertionError('attribution input mismatch')
            for name,value in manifest['outputs'].items():
                if sha(other/name)!=value or sha(OUT/name)!=value:
                    raise AssertionError('attribution output mismatch')
        print('Attribution replay: 2 deterministic files identical.')
    else:
        inputs=run(OUT)
        (OUT/'manifest.json').write_text(json.dumps(dict(inputs=inputs,
            outputs={name:sha(OUT/name) for name in ['rows.csv','summary.csv']},
            status='post-fit descriptive diagnostic; perfect future core is evaluation-only'),indent=2))
        scores=pd.read_csv(OUT/'summary.csv')
        print(scores.loc[scores.h.eq(12)&scores['model'].str.contains('SPLIT_MONTHLY')].to_string(index=False))


if __name__=='__main__':main()
