"""R23 fixed-support forecast scoring and same-target CNB revision lead test."""
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
from tools.research_r23.lead import lead_pairs,first_episodes,summaries

LABELS={'GAP_CALIBRATION_R23':'Quarterly error calibration','GAP_DOMESTIC_R23':'Domestic cost gaps',
 'GAP_IMPORTED_R23':'Imported cost gaps','GAP_JOINT_R23':'Joint cost gaps - positive ridge',
 'GAP_FREE_R23':'Joint cost gaps - free ridge','GAP_ENET_R23':'Joint cost gaps - elastic net',
 'GAP_HALF_R23':'Half joint cost gaps + FAST','CORE_FEEDBACK_R21':'Core error feedback - R21'}


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);args=ap.parse_args();root=args.root
    previous.evaluate(root);out=root/'evaluation'
    # Projections retain unscored/unmatured paths. Scored pairs would select on
    # availability of later actual CPI and omit live revision-only evidence.
    projections=pd.read_csv(out/'cnb_quarter_projections.csv');projections=projections[projections.model.ne('cnb')]
    cnb=pd.read_csv(ROOT/'data/cnb_mpr_cpi_quarterly.csv')
    lead=pd.concat([first_episodes(lead_pairs(projections,cnb,t),cnb) for t in (.3,.5)],ignore_index=True)
    lead.to_csv(out/'cnb_lead_pairs.csv',index=False);summaries(lead).to_csv(out/'cnb_lead_summary.csv',index=False)
    lead[lead.episode_start].to_csv(out/'cnb_first_call_episodes.csv',index=False)
    flags=['forecast_available','next_report_available','next_forecast_available','target_still_future','revision_eligible']
    coverage=lead.groupby(['model','clock','threshold']+flags,dropna=False).agg(rows=('quarter','size'),calls=('call','sum')).reset_index()
    coverage.to_csv(out/'cnb_lead_coverage.csv',index=False)
    rows=pd.read_csv(out/'primary_rows.csv');boot=[];omissions=[]
    for h,g in rows.groupby('h'):
        actual=g.drop_duplicates('origin').set_index('origin').yy_actual
        error=g.pivot(index='origin',columns='model',values='yy_exante').sub(actual,axis=0)
        for model in [m for m in error if m.endswith('_R23')]:
            for sample,mask in [('full',np.ones(len(error),bool)),('origins_2024plus',error.index>='2024-01')]:
                z=error.loc[mask];p=pd.DataFrame(dict(origin=z.index,loss_difference=z[model].to_numpy()**2-z.STATE_FAST_R15.to_numpy()**2))
                boot.append(dict(model=model,h=h,sample=sample,**block_bootstrap(p)))
            for year in sorted(set(error.index.str[:4])):
                z=error[~error.index.str.startswith(year)]
                omissions.append(dict(model=model,h=h,omitted_year=year,n=len(z),
                    rmse_delta=np.sqrt((z[model]**2).mean())-np.sqrt((z.STATE_FAST_R15**2).mean()),mae_delta=z[model].abs().mean()-z.STATE_FAST_R15.abs().mean()))
    pd.DataFrame(boot).to_csv(out/'primary_support_bootstrap.csv',index=False)
    pd.DataFrame(omissions).to_csv(out/'leave_one_origin_year_out.csv',index=False)
    payload=json.loads((out/'replay_data.json').read_text());payload['title']='CNB Rounds Replayed | R23 | historical research'
    payload['method']=[
      'R23: seven declared quarterly cost-gap candidates, original90 origins and969 primary keys; h0 and noncore unchanged. Historical research, not a live or untouched holdout record.',
      'Common FAST adaptive core baseline and identical saved R15 seasonality. Existing core state predates each decision. Four direct quarterly-average corrections are interpolated to months while exactly preserving their band means.',
      'Domestic inputs: quarterly real ULC gap and unemployment tightening. Imported inputs: relative import/PPI gaps and FX news since the import-price reference. These are statistical cost proxies, not causal contributions or exact core subdivisions.',
      'ULC remains quarterly. Training uses one origin per calendar quarter, only after its whole12-month target is published. Nested regularization uses each validation origin\'s own information clock; no outer outcome selects its model.',
      'Positive coefficient restrictions were declared before scoring and compared with free ridge, elastic net and intercept-only calibration. Missing required history falls back to FAST on the original support.',
      'No survey, CNB forecast or future realised driver enters the independent predictions. Current-vintage histories, assumed publication rules, repeated research and short effective quarterly history remain limitations.',
      'Both CNB clocks use same-origin quarter averages. Model-CNB difference is not evidence of skill: material accuracy gains require at least0.15pp lower absolute error.',
      'Separate lead tables flag abs(model-CNB)>=0.30pp, plus0.50 sensitivity; compare the immediately next CNB report for the same still-future target quarter. Confirmed revisions reduce distance to our original forecast by>=0.15pp; eventual material accuracy is a second test.',
      'All qualifying calls, failures, missing comparisons, unmatured outcomes and first-call episodes are exported. Repeated target quarters are dependent. Leading a later CNB revision is not a causal identification of news or a proven trading signal.',
      'Defaults illustrate the declared joint and half candidates with FAST; no model promotion is implied. Original controls and every candidate remain selectable.'
    ]
    for s in payload['series']:
        if s['kind']=='model':
            s['default']=s['id'] in ['STATE_FAST_R15','GAP_JOINT_R23','GAP_HALF_R23']
            if s['id'] in LABELS:s['label']=s['short']=LABELS[s['id']]
    c.dump(out/'replay_data.json',payload)
    old=out/'cnb_rounds_replayed_r17.html';previous.write_replay(old,payload)
    html=old.read_text(encoding='utf-8').replace('Czech CPI · R17 ·','Czech CPI · R23 ·').replace('CNB Rounds Replayed · R17 · historical','CNB Rounds Replayed · R23 · historical').replace('cnb-rounds-r17-visible-v1','cnb-rounds-r23-visible-v1')
    (out/'cnb_rounds_replayed_r23.html').write_text(html,encoding='utf-8');old.unlink()
    d=json.loads((out/'definitions.json').read_text());d['limitations']=payload['method']
    d['cnb_lead']='.30 and .50 ex-ante deviation thresholds; immediate next report, same target beyond next report quarter; .15pp closer CNB revision and separate eventual .15pp absolute-error improvement; first calls deduplicated by model/clock/target/direction streak.'
    c.dump(out/'definitions.json',d)
    m=json.loads((out/'input_manifest.json').read_text())
    for file in [Path(__file__),Path(__file__).with_name('lead.py')]:m['inputs'][str(file.resolve())]=c.sha(file)
    m['outputs']={p.name:c.sha(p) for p in out.iterdir() if p.is_file() and p.name!='input_manifest.json'};c.dump(out/'input_manifest.json',m)
    print('Completed R23 evaluation',out,flush=True)


if __name__=='__main__':main()
