"""Post-score summaries only. Never consumed by model estimation or selection."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]


def main():
    base=ROOT/'output/research_r23';out=base/'diagnostics';out.mkdir(exist_ok=True)
    ev=base/'final/evaluation'
    fits=[json.loads(s) for s in (base/'final/fits.jsonl').read_text().splitlines()]
    selected=pd.DataFrame([dict(origin=f['origin'],model=m,alpha=s['alpha'])
        for f in fits for m,s in f['selection'].items()])
    selected.groupby(['model','alpha']).size().rename('origins').reset_index().to_csv(out/'selected_alphas.csv',index=False)
    e=pd.read_csv(ev/'cnb_first_call_episodes.csv')
    e=e[e.clock.eq('report')&e.threshold.eq(.3)&e.revision_eligible]
    e[e.model.eq('GAP_JOINT_R23')].to_csv(out/'joint_first_calls_report_030.csv',index=False)
    e[e.model.isin(['STATE_FAST_R15','GAP_JOINT_R23','GAP_HALF_R23'])&e.joint_success].to_csv(out/'success_case_comparisons.csv',index=False)
    cases=pd.read_csv(ev/'cnb_lead_pairs.csv')
    cases=cases[cases.clock.eq('report')&cases.threshold.eq(.3)&cases.report_date.eq('2024-08-08')&cases.quarter.eq('2025Q2')]
    cases.to_csv(out/'summer_2024_same_target_all_models.csv',index=False)
    summary=pd.read_csv(ev/'cnb_lead_summary.csv')
    summary[summary.scope.eq('first_call_episodes')].to_csv(out/'lead_sensitivity.csv',index=False)
    counts=[]
    for model,g in e.groupby('model'):
        mature=g[g.realised.notna()];success=mature[mature.joint_success]
        counts.append(dict(model=model,calls=len(g),mature_calls=len(mature),
            material_gains=int(mature.material_gain.sum()),material_losses=int(mature.material_loss.sum()),
            joint_successes=len(success),success_report_dates=success.report_date.nunique(),
            success_target_quarters=success.quarter.nunique()))
    pd.DataFrame(counts).to_csv(out/'success_clustering.csv',index=False)
    # Independent paired differences are descriptive; no winner is chosen here.
    p=pd.read_csv(ev/'primary_scoreboard.csv');p=p[p.metric.eq('headline_yy')&p.h.isin([3,6,12])]
    p.to_csv(out/'headline_summary.csv',index=False)
    meta=dict(status='post_score_descriptive_only_no_model_refit',train_rows=[min(f['n_train'] for f in fits),max(f['n_train'] for f in fits)],
        interpretation='CNB lead successes count target-quarter episodes, not independent economic turns. Adjacent target quarters can share one shock.',
        source='output/research_r23/final',selection='No post-score candidate selection or threshold changes')
    (out/'README.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(pd.DataFrame(counts).to_string(index=False))


if __name__=='__main__':main()
