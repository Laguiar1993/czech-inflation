"""Independent R23 final hashes, fixed support, CNB lead and denominator audit."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
path=ROOT/(sys.argv[1] if len(sys.argv)>1 else 'output/research_r23/final')
evaluation=path/'evaluation'
count=0
for manifest,parents in [(path/'manifest.json',{'inputs':ROOT,'outputs':path}),
                          (evaluation/'input_manifest.json',{'inputs':ROOT,'outputs':evaluation})]:
    data=json.loads(manifest.read_text())
    for category,parent in parents.items():
        for name,digest in data[category].items():
            assert hashlib.sha256((parent/name).read_bytes()).hexdigest()==digest,(category,name)
            count+=1

primary=pd.read_csv(evaluation/'primary_rows.csv')
support=pd.read_csv(ROOT/'output/research_r17/attribution/primary_support.csv')[['origin','h']]
assert len(support)==969
for model,g in primary.groupby('model'):
    pd.testing.assert_frame_equal(g[['origin','h']].sort_values(['origin','h']).reset_index(drop=True),
                                  support.sort_values(['origin','h']).reset_index(drop=True))

cnb=pd.read_csv(ROOT/'data/cnb_mpr_cpi_quarterly.csv')
report_dates=sorted(cnb.report_date.unique())
next_report=dict(zip(report_dates,report_dates[1:]))
position={d:i for i,d in enumerate(report_dates)}
forecast=cnb[cnb.is_forecast.astype(str).str.lower().eq('true')].set_index(['report_date','quarter']).value
rows=pd.read_csv(evaluation/'cnb_lead_pairs.csv',float_precision='round_trip')
projections=pd.read_csv(evaluation/'cnb_quarter_projections.csv',float_precision='round_trip')
projections=projections[projections.model.ne('cnb')]
assert len(rows)==2*len(projections)
assert not rows.duplicated(['model','clock','threshold','report_date','quarter']).any()
assert set(rows.threshold)=={.3,.5} and set(rows.clock)=={'report','cutoff'}
for r in rows.itertuples():
    nxt=next_report.get(r.report_date)
    old=forecast.get((r.report_date,r.quarter),np.nan)
    new=forecast.get((nxt,r.quarter),np.nan)
    future=nxt is not None and pd.Period(r.quarter,'Q')>pd.Period(nxt,'Q')
    finite=np.isfinite([old,new,r.forecast]).all()
    eligible=bool(future and finite)
    call=bool(np.isfinite(r.forecast-old) and abs(r.forecast-old)>=r.threshold-1e-12)
    assert r.revision_eligible==eligible and r.call==call
    assert (pd.isna(r.next_report) and nxt is None) or r.next_report==nxt
    assert r.forecast_available==np.isfinite(r.forecast)
    assert r.next_report_available==(nxt is not None)
    assert r.next_forecast_available==np.isfinite(new)
    assert r.target_still_future==future
    agrees=bool(eligible and (new-old)*(r.forecast-old)>0)
    confirmed=bool(call and agrees and abs(old-r.forecast)-abs(new-r.forecast)>=.15-1e-12)
    assert r.revision_direction_agrees==agrees and r.revision_confirmed==confirmed
    if np.isfinite(r.realised) and np.isfinite(r.forecast):
        gain=abs(old-r.realised)-abs(r.forecast-r.realised)
        np.testing.assert_allclose(r.abs_error_gain,gain,atol=1e-12)
        assert r.material_gain==(gain>=.15-1e-12)
        assert r.material_loss==(gain<=-.15+1e-12)
        assert r.joint_success==(confirmed and gain>=.15-1e-12)

for _,g in rows.groupby(['model','clock','threshold','quarter']):
    g=g.sort_values('report_date')
    previous=None
    for r in g.itertuples():
        call=(position[r.report_date],np.sign(r.deviation)) if r.call else None
        start=call is not None and (previous is None or call[0]!=previous[0]+1 or call[1]!=previous[1])
        assert r.episode_start==start
        previous=call

summary=pd.read_csv(evaluation/'cnb_lead_summary.csv',float_precision='round_trip')
for r in summary.itertuples():
    z=rows[rows.model.eq(r.model)&rows.clock.eq(r.clock)&rows.threshold.eq(r.threshold)]
    if r.sample=='reports_2024plus':z=z[z.report_date.ge('2024-01-01')]
    if r.scope=='first_call_episodes':z=z[z.episode_start]
    eligible=z[z.revision_eligible];calls=eligible[eligible.call];mature=calls[calls.realised.notna()]
    assert r.considered_pairs==len(z) and r.all_calls==int(z.call.sum())
    assert r.calls_without_eligible_revision==int((z.call&~z.revision_eligible).sum())
    assert r.n_pairs==len(eligible) and r.calls==len(calls) and r.mature_calls==len(mature)
    assert r.unconfirmed_calls+r.revision_confirmations==r.calls
    assert r.revision_confirmations==int(calls.revision_confirmed.sum())
    assert r.revision_direction_matches==int(calls.revision_direction_agrees.sum())
    assert r.material_gains==int(mature.material_gain.sum())
    assert r.material_losses==int(mature.material_loss.sum())
    assert r.joint_successes==int(mature.joint_success.sum())
coverage=pd.read_csv(evaluation/'cnb_lead_coverage.csv')
assert coverage.rows.sum()==len(rows) and coverage.calls.sum()==rows.call.sum()
episodes=pd.read_csv(evaluation/'cnb_first_call_episodes.csv')
assert len(episodes)==rows.episode_start.sum() and episodes.episode_start.all()
print(json.dumps({'status':'pass','manifest_hashes_verified':count,'primary_keys_per_model':969,
                  'lead_rows':len(rows),'summary_rows':len(summary),'episode_rows':len(episodes),
                  'checks':['immediate next report','same still-future target','all projection support',
                            'direction vs distance','all-call and mature denominators','episode resets',
                            'missing comparison coverage']},indent=2))
