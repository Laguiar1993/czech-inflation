"""Offline chart and component table for one connected path capture."""
from pathlib import Path
import argparse,html,json,sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from models.current_path import MODELS,LABELS,BLOCKS


def build(run):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    run=Path(run);meta=json.loads((run/'snapshot.json').read_text());ready=json.loads((run/'readiness.json').read_text())
    path=pd.read_csv(run/'path.csv');colors=['#0c716f','#c77b2b','#7866ab']
    fig,axes=plt.subplots(1,2,figsize=(13.6,4.5),gridspec_kw={'width_ratios':[1.6,1]})
    fig.patch.set_facecolor('#f6f8fb')
    for axis,column,title in zip(axes,['yy_exante','mm_forecast'],['Annual CPI inflation','Monthly CPI changes']):
        axis.set_facecolor('#ffffff')
        for model,color in zip(MODELS,colors):
            g=path[path.model.eq(model)].sort_values('h')
            axis.plot(g.h,g[column],color=color,lw=2.3,marker='o',ms=3.5,label=LABELS[model])
        axis.set_title(title,loc='left',fontsize=13,pad=14,color='#172c43')
        axis.set_xticks(range(0,13,2));axis.set_xticklabels([str(pd.Period(meta['target'],'M')+h) for h in range(0,13,2)],rotation=35,ha='right',fontsize=8)
        axis.set_ylabel('%');axis.grid(axis='y',color='#e5eaf0');axis.spines[['top','right']].set_visible(False)
        axis.spines[['left','bottom']].set_color('#b9c8d4')
    axes[0].legend(frameon=False,fontsize=9,loc='best');fig.tight_layout(pad=2.2)
    fig.savefig(run/'path_chart.svg',facecolor=fig.get_facecolor());fig.savefig(run/'path_chart.png',dpi=160,facecolor=fig.get_facecolor());plt.close(fig)
    svg=(run/'path_chart.svg').read_text(encoding='utf-8');svg=svg[svg.index('<svg'):]
    rows=[]
    for model in MODELS:
        for r in path[path.model.eq(model)].sort_values('h').itertuples():
            vals=[getattr(r,'contribution_'+b) for b in BLOCKS]
            rows.append('<tr data-model="'+model+'"><td>'+r.target+'</td><td>'+str(r.h)+'</td><td>'+f'{r.mm_forecast:.3f}'+'</td><td>'+f'{r.yy_exante:.3f}'+'</td>'+''.join('<td>'+f'{v:.3f}'+'</td>' for v in vals)+'</tr>')
    options=''.join('<option value="'+m+'">'+LABELS[m]+'</option>' for m in MODELS)
    document='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CZK Cpi Forecasting - Latest models</title><style>
body{font-family:Segoe UI,Arial,sans-serif;background:#edf2f6;color:#172c43;margin:0}main{max-width:1320px;margin:35px auto;padding:0 24px}h1{font-size:31px;margin-bottom:8px}p{line-height:1.55}.tag{color:#14726b;text-transform:uppercase;letter-spacing:2px;font-size:12px;font-weight:700}.panel{background:white;border:1px solid #d9e2eb;border-radius:12px;padding:20px;margin:22px 0}.meta{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.muted{color:#546b81;font-size:13px}svg{width:100%;height:auto}select{padding:9px;border:1px solid #bacbd8;border-radius:6px;font-size:15px}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:right;padding:10px 8px;border-bottom:1px solid #e7edf3}th:first-child,td:first-child{text-align:left}th{color:#536b80;font-weight:600}.scroll{overflow:auto}.foot{font-size:13px;color:#51697e}@media(max-width:700px){.meta{grid-template-columns:1fr}main{padding:0 12px}h1{font-size:25px}}</style>
<main><div class="tag">Connected monthly path · R20</div><h1>CZK Cpi Forecasting - Latest models</h1>
<p>One independent nowcast, three core-inflation paths, and the same food, fuel and policy assumptions. Every point below is recalculated from the saved input snapshot.</p>
<div class="panel meta"><div><b>RECORD_TYPE</b><p class="muted">This chart is a historical fixture, not a new September forecast.</p></div><div><b>Target: TARGET</b><p class="muted">Decision: DECISION</p></div><div><b>Captured: CAPTURED</b><p class="muted">All paths cover h0–h12.</p></div></div>
<div class="panel">CHART</div><div class="panel"><h2>Monthly contribution detail</h2><p class="muted">Select a model. Contributions are percentage points of monthly headline CPI and sum to the monthly forecast.</p><select id="model" aria-label="Select inflation model">OPTIONS</select><div class="scroll"><table><thead><tr><th>Month</th><th>h</th><th>CPI m/m %</th><th>CPI y/y %</th><th>Core</th><th>Food</th><th>Admin</th><th>Alcohol</th><th>Fuel</th><th>Wedge</th></tr></thead><tbody>ROWS</tbody></table></div></div>
<p class="foot">FAST estimates a changing core trend plus a mean-reverting residual. Current core holds the trailing twelve-month log trend with calendar seasonality. Gentle slope uses the declared p95_q001 damped-slope filter. The food VAR and constant-pump assumption are shared. Future policy changes enter only when available under the announcement rules. These are research forecasts; the migration does not establish extra predictive skill, calibrated probability bands or a trading rule.</p>
<p class="foot">Saved data: <a href="path.csv">path.csv</a> · <a href="forecast.json">nowcast</a> · <a href="readiness.json">readiness</a> · <a href="snapshot.json">input snapshot</a></p></main>
<script>const select=document.getElementById('model');function update(){document.querySelectorAll('tbody tr').forEach(r=>r.hidden=r.dataset.model!==select.value)}select.addEventListener('change',update);update();</script></html>'''
    replacements={'RECORD_TYPE':ready['record_type'],'TARGET':meta['target'],'DECISION':meta['as_of'],'CAPTURED':meta['captured_at'],'CHART':svg,'OPTIONS':options,'ROWS':'\n'.join(rows)}
    for key,value in replacements.items():document=document.replace(key,value if key in ('CHART','OPTIONS','ROWS') else html.escape(value))
    if meta['capture_kind']!='historical_fixture':document=document.replace('This chart is a historical fixture, not a new September forecast.','See readiness before treating this capture as an issued forecast.')
    (run/'current_paths.html').write_text(document,encoding='utf-8')
    return run/'current_paths.html'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',type=Path,required=True);args=parser.parse_args();print(build(args.run))
