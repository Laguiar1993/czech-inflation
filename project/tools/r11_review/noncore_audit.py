"""Audit frozen R9 non-core forecasts; write only output/review_r11/noncore."""
from pathlib import Path
import hashlib, json, sys, platform, importlib.metadata
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'output/review_r11/noncore'
OUT.mkdir(parents=True, exist_ok=True)
FIX = ROOT / 'tests/fixtures/cleanup'
sys.path.insert(0, str(ROOT))
import requests
def offline(*args, **kwargs):
    raise AssertionError('Live network forbidden in the non-core audit')
requests.sessions.Session.request = offline
import cz_struct as s
from models.components import fuel_mm_from_weekly

def read(path):
    d = pd.read_csv(path, index_col=0, float_precision='round_trip')
    d.index = pd.PeriodIndex(d.index, freq='M')
    return d
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def rmse(v):
    return float(np.sqrt(np.mean(np.square(v))))

inputs = json.loads((FIX/'MANIFEST.json').read_text())
assert all(sha(FIX/k)==v for k,v in inputs.items())
y = read(FIX/'target_headline_cpi_mm.csv').iloc[:,0]
comp = read(FIX/'component_food_fuel_mm.csv')
core = read(FIX/'cnb_core_mm.csv').iloc[:,0].rename('core')
reg = read(FIX/'cnb_regulated_mm.csv').iloc[:,0].rename('reg')
alc = read(FIX/'alcohol_tobacco.csv').iloc[:,0]
weekly = pd.read_csv(FIX/'fuel_weekly.csv', index_col=0, float_precision='round_trip')
weekly.index = pd.to_datetime(weekly.index)
bt = read(ROOT/'output/cz_struct_backtest.csv')
pred = read(ROOT/'output/independent_nowcast_forecasts.csv')
report = read(ROOT/'output/contribution_report.csv')
diagnosis = read(OUT.parent/'large_surprise_diagnosis/release_attribution.csv')
hard_diag = {pd.Period(v['period'],freq='M'):v for v in json.loads((ROOT/'output/independent_nowcast_diagnostics.json').read_text()) if v['policy']=='hard'}
survey = pd.read_csv(ROOT/'data/czcpmom_survey_history_extended.csv',float_precision='round_trip')
suspect = survey[survey.era.eq('flash_survey_suspect')]
survey = survey[survey.era.ne('flash_survey_suspect')].copy()
survey.index = pd.PeriodIndex(survey.target_month,freq='M')
assert survey.index.is_unique
survey = survey.reindex(bt.index)
assert not survey.actual.isna().any()
assert len(bt)==len(pred)==90 and bt.index.equals(pred.index)
actuals={'food':comp.food,'fuel':comp.fuel,'admin':reg,'alc':alc,'core':core}
fc_cols={'food':'food_pred_eve','fuel':'fuel_eve','admin':'adm_pred_eve','alc':'alc_pred_eve','core':'core_pred_eve'}
wk={'food':'food','fuel':'fuel','admin':'administered','alc':'alc','core':'core'}
w0=s.W
wedge0=(y-w0['food']*comp.food-w0['fuel']*comp.fuel-w0['core']*core-w0['administered']*reg).rename('wedge')
rows=[]
replay=[]
for t in bt.index:
    clock=pd.Timestamp(bt.loc[t,'as_of_eve'])
    wm=s.solve_weights(y,comp,core,reg,t-1,as_of=clock,alc=alc)
    w=wm[s._regime(t)]
    weom=s.solve_weights(y,comp,core,reg,t-1,as_of=t.end_time,alc=alc)[s._regime(t)]
    hcore=hard_diag[t]['core_forecast']
    fixed=bt.loc[t,'STRUCT_EVE']-w['core']*bt.loc[t,'core_pred_eve']
    r=dict(period=str(t),as_of_eve=clock.isoformat(),actual=survey.loc[t,'actual'],consensus=survey.loc[t,'survey_median'],actual_fixture=y.loc[t],actual_ref=bt.loc[t,'actual'],HARD_BASE=pred.loc[t,'HARD_BASE'],LEGACY_BASE=bt.loc[t,'STRUCT_EVE'],fixed_noncore=fixed,hard_core_pred=hcore,coreweight_delta=w['core']-pred.loc[t,'coreweight'],weight_sum_delta=sum(w.values())-1)
    r['headline_revision_or_rounding']=r['actual']-r['actual_fixture']
    for b,series in actuals.items():
        r['weight_'+b]=w[wk[b]]
        r['weight_eom_'+b]=weom[wk[b]]
        r['forecast_'+b]=bt.loc[t,fc_cols[b]]
        r['actual_'+b]=series.loc[t]
        r['error_'+b]=w[wk[b]]*(r['forecast_'+b]-r['actual_'+b])
        r['report_weight_delta_'+b]=report.loc[t,'w_'+wk[b]]-w[wk[b]]
        r['report_actual_delta_'+b]=report.loc[t,'act_'+wk[b]]-series.loc[t]
        r['report_block_error_delta_'+b]=report.loc[t,'err_'+wk[b]]-r['error_'+b]
    r['legacy_weighted_core_error']=r['error_core']
    r['error_core']=w['core']*(hcore-core.loc[t])
    r['wedge_forecast']=bt.loc[t,'wedge_eve']
    r['realised_reconciliation_first_release']=r['actual']-sum(w[wk[b]]*r['actual_'+b] for b in actuals)
    r['realised_reconciliation_fixture']=r['actual_fixture']-sum(w[wk[b]]*r['actual_'+b] for b in actuals)
    r['error_wedge']=r['wedge_forecast']-r['realised_reconciliation_first_release']
    r['error_wedge_fixture']=r['wedge_forecast']-r['realised_reconciliation_fixture']
    r['headline_error']=r['HARD_BASE']-r['actual']
    r['noncore_blocks_error']=sum(r['error_'+b] for b in ('food','fuel','admin','alc'))
    r['noncore_error']=r['noncore_blocks_error']+r['error_wedge']
    r['all_blocks_error']=r['noncore_blocks_error']+r['error_core']
    r['fixed_noncore_identity_residual']=fixed-sum(w[wk[b]]*r['forecast_'+b] for b in ('food','fuel','admin','alc'))-r['wedge_forecast']
    r['headline_prediction_identity_residual']=r['HARD_BASE']-(fixed+w['core']*hcore)
    r['headline_error_identity_residual']=r['headline_error']-sum(r['error_'+b] for b in ('food','fuel','admin','alc','core','wedge'))
    r['prior_diagnosis_noncore_delta']=r['noncore_error']-diagnosis.loc[t,'fixed_noncore_reconciliation_error']
    r['big']=abs(r['actual']-r['consensus'])>=.4-1e-9
    r['wedge_offsets_blocks']=r['error_wedge']*r['all_blocks_error']<0
    r['wedge_abs_error_reduction']=abs(r['all_blocks_error'])-abs(r['headline_error'])
    r['wedge_offsets_noncore']=r['error_wedge']*r['noncore_blocks_error']<0
    r['wedge_noncore_abs_error_reduction']=abs(r['noncore_blocks_error'])-abs(r['noncore_error'])
    r['category_core_error']=diagnosis.loc[t,'category_weighted_core_error']
    r['category_headline_error']=diagnosis.loc[t,'category']-r['actual']
    r['category_core_better_headline_worse']=abs(r['category_core_error'])<abs(r['error_core']) and abs(r['category_headline_error'])>abs(r['headline_error'])
    r['core_noncore_cancel']=r['error_core']*r['noncore_error']<0
    r['category_core_gain_pp']=abs(r['error_core'])-abs(r['category_core_error'])
    r['category_headline_loss_pp']=abs(r['category_headline_error'])-abs(r['headline_error'])
    rv={'period':str(t)}
    af=s.alc_forecast(alc,t,t-1,as_of=clock)
    adm=s.admin_forecast(reg,t,as_of=clock,announce_mode='documented',w_adm=w['administered'])
    wtv=s._weighted_wedge(y,comp,alc,core,reg,wedge0,wm,as_of=clock)
    wg=s._wedge_at(wtv,t,t-1)
    wf,_=s._fuel_inputs_as_of(weekly,None,clock)
    fu,fd=fuel_mm_from_weekly(wf,t,petrol_share=s._petrol_share(t,clock))
    for name,val,col in [('alc',af,'alc_pred_eve'),('admin',adm,'adm_pred_eve'),('fuel',fu,'fuel_eve'),('wedge',wg,'wedge_eve')]:
        rv[name+'_replay_delta']=val-bt.loc[t,col]
    rv.update(fd)
    rv['latest_eligible_fuel_observation']=str(wf.index.max())
    rv['target_last_monday']=str(pd.date_range(t.start_time,t.end_time,freq='W-MON').max())
    rv['wedge_history_end']=str(wtv.index.max())
    rv['wedge_same_month_n']=int(((wtv.index.month==t.month)&(wtv.index<=t-1)).sum())
    replay.append(rv)
    rows.append(r)

d=pd.DataFrame(rows).set_index('period')
rp=pd.DataFrame(replay).set_index('period')
d.to_csv(OUT/'exact_attribution_all90.csv',float_format='%.17g')
rp.to_csv(OUT/'cheap_block_replay_all90.csv',float_format='%.17g')
focus=['2020-06','2022-02','2022-04','2022-05','2022-09','2022-10','2022-11','2024-04']
focuscols=['actual','consensus','HARD_BASE','headline_error','error_core','error_food','error_fuel','error_admin','error_alc','wedge_forecast','realised_reconciliation_first_release','error_wedge','noncore_error','category_core_error','category_headline_error','category_core_gain_pp','category_headline_loss_pp']
d.loc[focus,focuscols].to_csv(OUT/'focus_cases.csv',float_format='%.17g')
stats=[]
for name,mask in [('all',np.ones(len(d),bool)),('ex_jan',[pd.Period(t).month!=1 for t in d.index]),('big',d.big),('2022',d.index.str.startswith('2022')),('2024plus',d.index>='2024-01')]:
    z=d.loc[mask]
    for b in ['core','food','fuel','admin','alc','wedge','noncore','all_blocks','headline']:
        col='error_'+b if b in actuals or b=='wedge' else b+'_error'
        stats.append(dict(window=name,block=b,n=len(z),bias=z[col].mean(),mae=z[col].abs().mean(),rmse=rmse(z[col]),squared_term=float(np.square(z[col]).sum()),cross_with_headline=float((z[col]*z.headline_error).sum())))
pd.DataFrame(stats).to_csv(OUT/'error_scores.csv',index=False,float_format='%.17g')
cols=['error_'+b for b in ['core','food','fuel','admin','alc','wedge']]
d[cols].corr().to_csv(OUT/'block_error_correlations.csv',float_format='%.17g')
checks={c:float(d[c].abs().max()) for c in d if c.endswith('_residual') or c in ['coreweight_delta','weight_sum_delta','prior_diagnosis_noncore_delta']}
checks.update({c:float(rp[c].abs().max()) for c in rp if c.endswith('_delta')})
checks['report_weight_max_delta']=float(d.filter(regex='^report_weight_delta_').abs().max().max())
checks['report_actual_max_delta']=float(d.filter(regex='^report_actual_delta_').abs().max().max())
assert max(checks[c] for c in checks if not c.startswith('report_'))<1e-10,checks
changed=d[d.filter(regex='^report_weight_delta_').abs().max(axis=1)>1e-12]
changed.to_csv(OUT/'report_weight_discrepancies.csv',float_format='%.17g')
summary=dict(n=len(d),checks=checks,suspect_rows_filtered=int(len(suspect)),report_weight_different_periods=changed.index.tolist(),headline_fixture_first_release_differences=dict(n_nonzero=int((d.headline_revision_or_rounding.abs()>1e-12).sum()),max_abs=float(d.headline_revision_or_rounding.abs().max()),rmse=rmse(d.headline_revision_or_rounding)),wedge=dict(offsets_all_blocks=int(d.wedge_offsets_blocks.sum()),reduces_all_block_abs_error=int((d.wedge_abs_error_reduction>1e-12).sum()),mean_abs_error_reduction=float(d.wedge_abs_error_reduction.mean()),offsets_noncore=int(d.wedge_offsets_noncore.sum()),reduces_noncore_abs_error=int((d.wedge_noncore_abs_error_reduction>1e-12).sum()),mean_noncore_abs_error_reduction=float(d.wedge_noncore_abs_error_reduction.mean()),rms_no_wedge_error=rmse(d.all_blocks_error),rms_headline=rmse(d.headline_error),corr_admin=float(d.error_wedge.corr(d.error_admin)),corr_core=float(d.error_wedge.corr(d.error_core)),corr_noncore=float(d.error_wedge.corr(d.noncore_blocks_error))),big_core_better_headline_worse=d.index[d.big&d.category_core_better_headline_worse].tolist(),all_core_better_headline_worse=d.index[d.category_core_better_headline_worse].tolist(),fuel_not_all_weeks=rp.index[rp.fraction_observed<1].tolist())
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
sources=[ROOT/'cz_struct.py',ROOT/'contribution_report.py',ROOT/'independent_nowcast_experiment.py',ROOT/'models/components.py',ROOT/'data/local_adapter.py',ROOT/'config.py',ROOT/'data/release_calendar_cz_cpi.csv',ROOT/'data/admin_announcements_history.csv',ROOT/'data/czcpmom_survey_history_extended.csv',ROOT/'output/cz_struct_backtest.csv',ROOT/'output/independent_nowcast_forecasts.csv',ROOT/'output/independent_nowcast_diagnostics.json',ROOT/'output/independent_nowcast_manifest.json',ROOT/'output/contribution_report.csv',OUT.parent/'large_surprise_diagnosis/release_attribution.csv',FIX/'MANIFEST.json',*[FIX/k for k in inputs],Path(__file__)]
manifest=dict(repo_head='8ee32fbb8764e7855449f59c131a7e19931c6a68',python=platform.python_version(),libraries={p:importlib.metadata.version(p) for p in ['numpy','pandas','statsmodels','scikit-learn']},inputs={str(p):sha(p) for p in sources},limitations=['Frozen latest-vintage pseudo-OOS fixtures, not archived component release vintages.','First-release headline from survey history excluding flash_survey_suspect; component actuals from hashed cleanup fixtures.','No new forecasts fitted; cheap original blocks replayed under exact historical release-eve clocks.','Headline minus weighted component actuals is a statistical reconciliation residual, not an official CPI component.','Full food/X13 reproduction is separate targeted check.'])
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(summary,indent=2))
print(d.loc[focus,focuscols].round(6).to_string())
print(pd.DataFrame(stats).query("window=='all'").round(6).to_string(index=False))
