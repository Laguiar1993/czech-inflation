"""Additional read-only uncertainty on the original R16 control calendar."""
from pathlib import Path
import sys
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from tools.review import evaluate_r15 as prior


def main():
    folder=ROOT/'output/research_r17/path/evaluation';out=ROOT/'output/research_r17/primary_uncertainty';out.mkdir(parents=True,exist_ok=False)
    files=[folder/'paired_loss_differences.csv',ROOT/'output/research_r17/attribution/primary_support.csv',Path(__file__),Path(prior.__file__)]
    hashes={str(p.resolve()):c.sha(p) for p in files}
    pairs=pd.read_csv(files[0],float_precision='round_trip');support=pd.read_csv(files[1])
    selected=pairs[pairs.metric.eq('headline_yy')&pairs.scope.str.startswith('paired_fast')].merge(support,on=['origin','h'],validate='many_to_one')
    rows=[]
    for (model,h),group in selected.groupby(['model','h']):
        for sample,mask in prior.samples(group).items():
            rows.append(dict(model=model,h=h,sample=sample,scope='original_R16_calendar',benchmark=c.FAST,
                             **prior.block_bootstrap(group[mask])))
    selected.to_csv(out/'paired_rows.csv',index=False);pd.DataFrame(rows).to_csv(out/'bootstrap.csv',index=False)
    for name,digest in hashes.items():
        if c.sha(name)!=digest:raise ValueError('Read-only uncertainty changed source')
    c.dump(out/'manifest.json',dict(inputs=hashes,outputs={p.name:c.sha(p) for p in out.glob('*.csv')}))
    print('Primary uncertainty completed',flush=True)


if __name__=='__main__':main()
