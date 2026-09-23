"""Independent arithmetic and comparison-clock audit; reads frozen outputs only."""
from pathlib import Path
import json, re, hashlib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
html = (ROOT / 'output/cnb_rounds_replayed_20260912/cnb_rounds_replayed.html').read_text(encoding='utf-8')
data = json.JSONDecoder().raw_decode(html.split('const DATA = ', 1)[1])[0]
head = pd.read_csv(ROOT/'output/independent_path_frozen_inputs.csv')
mm = pd.Series(head.headline_mm.to_numpy(), index=pd.PeriodIndex(head.period, freq='M')).dropna()
yy = 100*np.expm1(np.log1p(mm/100).rolling(12).sum())
board = pd.read_csv(ROOT/'output/research_r14b/integration/forecasts.csv')
forest = pd.read_csv(ROOT/'output/paper_tvwqrf_20260912/path_scores_luci_month/board_a_forecasts.csv')
combined = pd.concat([board, forest], ignore_index=True)
assert not combined.duplicated(['origin','h','model']).any()
errors = []
for (model, origin), g in combined.groupby(['model','origin']):
    p = pd.Period(origin, freq='M')
    monthly = dict(zip(g.h, g.mm_forecast))
    for row in g.itertuples():
        months = pd.period_range(p+row.h-11,p+row.h,freq='M')
        vals = [mm.get(t,np.nan) if t<p else monthly.get(t.ordinal-p.ordinal,np.nan) for t in months]
        calc = 100*np.expm1(np.log1p(np.array(vals)/100).sum())
        errors.append(abs(calc-row.yy_exante))

artifact_rows=[]
mae_diffs=[]
for r in data['reports']:
    realised = dict((q, float(yy.reindex(pd.period_range(pd.Period(q).asfreq('M','start'),pd.Period(q).asfreq('M','end'),freq='M')).mean())) for q in r['score']['quarters'])
    for model, points in [('cnb',[(a['quarter'],a['value']) for a in r['cnb']]), *r['quarter_points'].items()]:
        points=dict(points)
        used=[]
        for q in r['score']['quarters']:
            if q not in points: continue
            e=points[q]-realised[q]
            used.append(e)
            artifact_rows.append(dict(report_date=r['report_date'],cutoff_date=r['cutoff_date'],origin=r['origin'],origin_clock=r['origin_clock'],model=model,quarter=q,quarters_ahead=pd.Period(q).ordinal-pd.Period(r['report_date'],freq='Q').ordinal+1,forecast=points[q],realised=realised[q],error=e))
        published=r['score']['mae'].get(model)
        if published is not None:
            mae_diffs.append(abs(np.mean(np.abs(used))-published))
adf=pd.DataFrame(artifact_rows)
adf.to_csv(OUT/'artifact_pairs.csv',index=False)

def summaries(frame, path):
    rows=[]
    for sample, f in [('all',frame),('reports_2024plus',frame[frame.report_date>='2024-01-01'])]:
        for (h,model),g in f.groupby(['quarters_ahead','model']):
            rows.append(dict(sample=sample,h=h,model=model,n=len(g),rmse=np.sqrt(np.mean(g.error**2)),mae=np.mean(abs(g.error)),bias=g.error.mean()))
        for model,g in f.groupby('model'):
            rows.append(dict(sample=sample,h='all',model=model,n=len(g),rmse=np.sqrt(np.mean(g.error**2)),mae=np.mean(abs(g.error)),bias=g.error.mean()))
    z=pd.DataFrame(rows)
    z.to_csv(OUT/path,index=False)
    return z

az=summaries(adf,'artifact_summary.csv')

# Both clocks on identical report/target-quarter/model support. Cutoff date is
# conservatively start of Prague day; moving to end of day does not change the chosen runs.
cnb=pd.read_csv(ROOT/'data/cnb_mpr_cpi_quarterly.csv')
cnb=cnb[cnb.is_forecast.astype(str).str.lower().eq('true') & cnb.report_date.ge('2022-01-01')]
clocks=pd.to_datetime(board.drop_duplicates('origin').set_index('origin').as_of_utc,utc=True).sort_values()
chosen=['INDEPENDENT_BRIDGE','STABLE_PIPELINE_R14B','STABLE_LOCAL_CORE_R14B','STABLE_LONG_CORE_R14B','STABLE_LONG_GAP_R14B','TVWQRF_TVW3_FULLM','TVWQRF_QRF_MEAN_FULLM']
rows=[]; coverage=[]
for (date,cutoff),g in cnb.groupby(['report_date','cutoff_date']):
    selected={}
    for mode,time in [('report',date),('cutoff',cutoff)]:
        eligible=clocks[clocks<pd.Timestamp(time).tz_localize('Europe/Prague').tz_convert('UTC')]
        if len(eligible): selected[mode]=(eligible.index[-1],eligible.iloc[-1])
    if len(selected)!=2: continue
    coverage.append(dict(report_date=date,cutoff=cutoff,report_origin=selected['report'][0],cutoff_origin=selected['cutoff'][0],report_clock=str(selected['report'][1]),cutoff_clock=str(selected['cutoff'][1])))
    for qrow in g.itertuples():
        q=pd.Period(qrow.quarter,freq='Q'); months=pd.period_range(q.asfreq('M','start'),q.asfreq('M','end'),freq='M')
        actuals=yy.reindex(months)
        if not actuals.notna().all(): continue
        bymode={}
        for mode,(origin,clock) in selected.items():
            o=pd.Period(origin,'M'); vals={}
            for model in chosen:
                rows_model=combined[combined.origin.eq(origin)&combined.model.eq(model)]
                path=dict(zip(rows_model.target,rows_model.yy_exante))
                fs=[float(yy.get(m,np.nan)) if m<o else path.get(str(m),np.nan) for m in months]
                if np.isfinite(fs).all():vals[model]=np.mean(fs)
            bymode[mode]=vals
        # require all roster models in both clocks to use one panel for sensitivity
        if any(set(v)!=set(chosen) for v in bymode.values()):continue
        for mode,vals in bymode.items():
            for model,pred in {**vals,'cnb':qrow.value}.items():
                rows.append(dict(mode=mode,report_date=date,quarter=str(q),quarters_ahead=q.ordinal-pd.Period(date,freq='Q').ordinal+1,origin=selected[mode][0],model=model,forecast=pred,realised=actuals.mean(),error=pred-actuals.mean()))
df=pd.DataFrame(rows);df.to_csv(OUT/'cutoff_matched_pairs.csv',index=False)
pd.DataFrame(coverage).to_csv(OUT/'report_cutoff_clocks.csv',index=False)
zs=[]
for mode,g in df.groupby('mode'):
    z=summaries(g,f'{mode}_clock_summary.csv');z['mode']=mode;zs.append(z)
zs=pd.concat(zs)

manifest=json.loads((ROOT/'output/research_r14b/integration/manifest.json').read_text())
mismatches=[]
for role,paths in manifest.items():
    if role not in ('inputs','outputs'):continue
    for path,sha in paths.items():
        f=ROOT/path if role=='inputs' else ROOT/'output/research_r14b/integration'/path
        actual=hashlib.sha256(f.read_bytes()).hexdigest() if f.exists() else None
        if actual!=sha:mismatches.append(dict(role=role,path=path,expected=sha,actual=actual))
summary=dict(artifact_object=data['f_object'],artifact_reports=len(data['reports']),max_compounding_difference=float(np.nanmax(errors)),n_compounding_checks=len(errors),max_artifact_mae_rounding_difference=float(max(mae_diffs)),manifest_mismatches=mismatches)
(OUT/'checks.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
print('\nARTIFACT POOLED (descriptive, overlapping)')
print(az[az.h.eq('all')].to_string(index=False))
print('\nSAME-QUARTER CUTOFF SENSITIVITY')
print(zs[zs.h.eq('all')].to_string(index=False))
