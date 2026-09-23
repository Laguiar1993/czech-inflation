"""Plot frozen forecast evidence for the briefing. No fitting or live data calls."""
from pathlib import Path
import hashlib
import json
import os
# Keep Matplotlib's disposable font cache inside the writable report workspace.
os.environ.setdefault('MPLCONFIGDIR',str(Path(__file__).resolve().parent/'matplotlib_cache'))
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
OUT=HERE/'charts'
OUT.mkdir(exist_ok=True)
REPLAY=ROOT/'output/research_r17/path/evaluation/replay_data.json'
SCORES=ROOT/'output/research_r17/path/evaluation/primary_scoreboard.csv'
NOW=HERE/'nowcast_release_evidence.csv'
SUMMARY=HERE/'nowcast_summary.csv'
SOURCE_FILES=[REPLAY,SCORES,NOW,SUMMARY,HERE/'ANALYSIS_SCOPE.md']
data=json.loads(REPLAY.read_text(encoding='utf-8'))
scores=pd.read_csv(SCORES)
events=pd.read_csv(NOW)
summary=pd.read_csv(SUMMARY)
NAVY='#193c52'; GREY='#617580'; BLACK='#25313b'; RED='#bc4254'
BLUE='#2769b1'; TEAL='#16838a'; PURPLE='#8563ae'; GOLD='#be8b2d'
LABELS={'STATE_FAST_R15':('FAST',BLUE),
        'STABLE_LOCAL_CORE_R14B':('Current core',TEAL),
        'DAMPED_P95_Q001_R16':('Gentle slope',PURPLE),
        'INDEPENDENT_BRIDGE':('Original bridge',GREY)}
REFERENCES=list(LABELS)[:3]
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.2,
    'axes.labelsize':8,'xtick.labelsize':7.5,'ytick.labelsize':7.5,
    'axes.titlesize':10.3,'axes.titleweight':'bold','axes.titlecolor':NAVY,
    'text.color':NAVY,'axes.labelcolor':GREY,'xtick.color':GREY,
    'ytick.color':GREY,'axes.edgecolor':'#d0dbe0','axes.spines.top':False,
    'axes.spines.right':False,'savefig.facecolor':'white'})
plotted=[]
chart_files=[]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def month(s):return pd.Period(s,freq='M').ordinal
def month_label(x):return pd.Period(ordinal=int(x),freq='M').strftime('%b\n%Y')
def tidy(ax):
    ax.grid(axis='y',color='#e8eef0',lw=.65,zorder=0)
    ax.set_axisbelow(True)

def record(chart,series,period,value,**extra):
    plotted.append(dict(chart=chart,series=series,period=str(period),value=float(value),**extra))

def save(fig,name):
    fig.savefig(OUT/f'{name}.png',dpi=220)
    plt.close(fig)
    chart_files.append(OUT/f'{name}.png')

def path_chart(report_date,name,title):
    report=next(r for r in data['reportsByClock']['report'] if r['report_date']==report_date)
    o=month(report['origin']);lo=o-6;hi=o+12
    fig,ax=plt.subplots(figsize=(7.1,2.77))
    fig.subplots_adjust(left=.085,right=.985,bottom=.255,top=.75)
    fig.text(.085,.952,title,fontsize=10.3,fontweight='bold',color=NAVY)
    asof=report['origin_clock'].split()[0]
    fig.text(.085,.878,f"CNB report {report_date} | model origin {report['origin']} | forecast as of {asof}",
             fontsize=7.5,color=GREY)
    ax.axvspan(o-.5,hi+.5,color='#eef5f7',zorder=0)
    ax.axvline(o-.5,color='#a1b6c1',lw=.8,ls='--')
    actual=[(m,v) for m,v in data['realised'].items() if lo<=month(m)<=hi and v is not None]
    ax.plot([month(m) for m,v in actual],[v for m,v in actual],color=BLACK,lw=1.8,zorder=5)
    for m,v in actual:record(name,'realised_monthly',m,v)
    for model in REFERENCES:
        vals=[(m,v) for m,v in report['paths'][model] if o-1<=month(m)<=hi and v is not None]
        assert len(vals)==14,(report_date,model,len(vals))
        assert [month(m) for m,v in vals]==list(range(o-1,o+13))
        ax.plot([month(m) for m,v in vals],[v for m,v in vals],color=LABELS[model][1],lw=1.45,zorder=3)
        for m,v in vals:record(name,model,m,v,origin=report['origin'],report_date=report_date)
    for q in report['cnb']:
        p=pd.Period(q['quarter'],freq='Q');start=month(str(p.asfreq('M','start')))-.5
        end=month(str(p.asfreq('M','end')))+.5
        if end<lo-.5 or start>hi+.5:continue
        ax.hlines(q['value'],max(start,lo-.5),min(end,hi+.5),color=RED,lw=2.3,zorder=4)
        record(name,'cnb_quarterly_average',q['quarter'],q['value'],report_date=report_date)
    ax.set_xlim(lo-.5,hi+.5)
    ticks=list(range(lo,hi+1,3))
    ax.set_xticks(ticks,[month_label(t) for t in ticks])
    ax.set_ylabel('Headline CPI, % year on year')
    ax.text(.985,1.035,'Shaded: forecast targets h0-h12',transform=ax.transAxes,ha='right',va='bottom',
            fontsize=7.2,color=GREY)
    tidy(ax)
    handles=[Line2D([],[],color=BLACK,lw=1.8,label='Realised (current vintage)'),
             Line2D([],[],color=RED,lw=2.3,label='CNB quarterly average')]
    handles += [Line2D([],[],color=LABELS[m][1],lw=1.5,label=LABELS[m][0]) for m in REFERENCES]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.51,.005),ncol=3,
               frameon=False,fontsize=7.15,handlelength=2,columnspacing=1.5,labelspacing=.55)
    save(fig,name)

def path_performance():
    name='path_accuracy'
    fig,axes=plt.subplots(1,2,figsize=(7.1,3.05),sharex=True)
    fig.subplots_adjust(left=.085,right=.985,bottom=.25,top=.83,wspace=.27)
    for ax,sample,title in zip(axes,['full','origins_2024plus'],['All scored origins','Origins from 2024']):
        sub=scores[(scores.scope=='original_R16_calendar')&(scores.metric=='headline_yy')&
                   (scores['sample']==sample)&scores.h.between(1,12)]
        for model,(label,color) in LABELS.items():
            rows=sub[sub.model==model].sort_values('h')
            assert len(rows)==12
            ax.plot(rows.h,rows.rmse,label=label,color=color,lw=1.6,
                    ls='--' if model=='INDEPENDENT_BRIDGE' else '-',marker='o',ms=2.8)
            for row in rows.itertuples():record(name,model,row.h,row.rmse,sample=sample,n=int(row.n))
        counts=sub[sub.model=='STATE_FAST_R15'].sort_values('h')
        ax.set_title(title,pad=13)
        ax.text(.03,.96,f'n = {int(counts.iloc[0].n)} at h1; {int(counts.iloc[-1].n)} at h12',
                transform=ax.transAxes,va='top',fontsize=7.1,color=GREY)
        ax.set_xticks([1,3,6,9,12]);ax.set_xlabel('Months ahead (h)');ax.set_ylim(bottom=0);tidy(ax)
    axes[0].set_ylabel('Headline YoY RMSE, percentage points')
    fig.legend(*axes[0].get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,.015),
               frameon=False,ncol=4,fontsize=7.5)
    save(fig,name)

def nowcast_performance():
    name='nowcast_accuracy'
    models=['CONSENSUS','HARD_BASE','HARD_HALF','HARD_FULL','CATEGORY_RAW']
    labels=['Survey','Base','Half','Full','Category\nRaw']
    palette=[RED,GREY,BLUE,TEAL,PURPLE]
    fig,axes=plt.subplots(1,3,figsize=(7.1,2.73),sharey=True)
    fig.subplots_adjust(left=.085,right=.985,bottom=.23,top=.79,wspace=.12)
    for ax,frame,title in zip(axes,['all','2024+','flash2025+'],
             ['All releases (n=90)','2024 onward (n=31)','Flash only (n=19)']):
        rows=summary[(summary.frame==frame)&summary.model.isin(models)].set_index('model').loc[models]
        ax.bar(range(5),rows.rmse,color=palette,width=.73,zorder=3)
        for i,(model,row) in enumerate(rows.iterrows()):
            ax.text(i,row.rmse+.009,f'{row.rmse:.3f}',ha='center',fontsize=6.6,color=NAVY)
            record(name,model,frame,row.rmse,n=int(row.n))
        ax.set_xticks(range(5),labels,rotation=45,ha='right',fontsize=7)
        ax.set_title(title,fontsize=9.3,pad=10);ax.set_ylim(0,.48);tidy(ax)
    axes[0].set_ylabel('Monthly CPI RMSE, percentage points')
    save(fig,name)

def surprise_scatter():
    name='nowcast_surprise_scatter'
    rows=events[events.model=='HARD_FULL'].copy()
    assert len(rows)==90 and int(rows.big.sum())==23
    fig,ax=plt.subplots(figsize=(7.1,3.2))
    fig.subplots_adjust(left=.085,right=.985,bottom=.22,top=.86)
    ax.set_title('FULL: actual surprise versus our departure from survey',loc='left',pad=12)
    ax.axvspan(-.4,.4,color='#f2f5f6',zorder=0)
    ax.axhspan(-.2,.2,color='#dceaf0',alpha=.45,zorder=0)
    ax.axhline(0,color='#9aadb6',lw=.7);ax.axvline(0,color='#9aadb6',lw=.7)
    ax.plot([-2.5,1.1],[-2.5,1.1],ls='--',lw=1,color='#91a2ab')
    for big,label,color in [(False,'Other releases (67)','#adbfc8'),(True,'Large surprises (23)',TEAL)]:
        r=rows[rows.big==big]
        ax.scatter(r.surprise,r.deviation,s=25 if big else 15,color=color,edgecolors='white',
                   linewidths=.4,label=label,zorder=4,alpha=.9)
    ax.set_xlim(-2.5,1.1);ax.set_ylim(-2.5,1.1)
    ax.set_xlabel('Actual - survey (percentage points)')
    ax.set_ylabel('FULL - survey (percentage points)')
    tidy(ax)
    for period,label,offset in [
        ('2022-10','Oct 2022: wrong side',(17,15)),
        ('2024-01','Jan 2024: overshoot',(-108,-18)),
        ('2024-04','Apr 2024: material gain',(-110,35))]:
        r=rows[rows.period==period].iloc[0]
        ax.annotate(label,(r.surprise,r.deviation),xytext=offset,textcoords='offset points',fontsize=7.2,
                    arrowprops=dict(arrowstyle='-',lw=.7,color=GREY),color=NAVY,
                    bbox=dict(facecolor='white',edgecolor='none',alpha=.85,pad=1.5))
    ax.text(.03,.07,'Dashed diagonal: perfect forecast\nBlue band: departure below the 0.20 pp alert threshold',
             transform=ax.transAxes,fontsize=7.1,color=GREY)
    fig.legend(*ax.get_legend_handles_labels(),loc='lower center',bbox_to_anchor=(.5,.0),
               ncol=2,frameon=False,fontsize=7.3)
    for r in rows.itertuples():
        record(name,'FULL_deviation',r.period,r.deviation,surprise=r.surprise,big=bool(r.big))
    save(fig,name)

def surprise_gains():
    name='nowcast_big_event_gains'
    r=events[(events.model=='HARD_FULL')&events.big].sort_values('period')
    assert len(r)==23
    calc=(r.actual-r.consensus).abs()-(r.forecast-r.actual).abs()
    assert np.allclose(calc,r.gain,atol=1e-12)
    win=r.gain>=.15-1e-9;loss=r.gain<=-.15+1e-9
    assert (int(win.sum()),int(loss.sum()))==(9,2)
    colors=[TEAL if w else RED if l else '#a9bac2' for w,l in zip(win,loss)]
    fig,ax=plt.subplots(figsize=(7.1,2.78))
    fig.subplots_adjust(left=.085,right=.985,bottom=.295,top=.80)
    ax.bar(range(len(r)),r.gain,color=colors,width=.75,zorder=3)
    ax.axhline(0,color='#8c9ea8',lw=.8)
    for y in [-.15,.15]:ax.axhline(y,color=GREY,lw=.75,ls='--')
    ax.set_xticks(range(len(r)),[pd.Period(x).strftime('%b %y') for x in r.period],rotation=65,ha='right',fontsize=6.8)
    ax.set_ylabel('Absolute-error reduction, pp')
    ax.set_title('Every large surprise: 9 material gains, 2 material losses',loc='left',pad=12)
    ax.set_ylim(-.24,.64);tidy(ax)
    fig.legend(handles=[Patch(color=TEAL,label='Gain at least 0.15 pp'),Patch(color=RED,label='Loss at least 0.15 pp'),
                        Patch(color='#a9bac2',label='Smaller change')],loc='lower center',
               bbox_to_anchor=(.5,.002),ncol=3,frameon=False,fontsize=7.2)
    for row in r.itertuples():record(name,'FULL_absolute_error_reduction',row.period,row.gain)
    save(fig,name)

def main():
    selections=[
        ('2022-02-10','path_2022_winter','Winter 2022 | the inflation shock'),
        ('2023-02-09','path_2023_winter','Winter 2023 | disinflation from a high starting point'),
        ('2023-08-10','path_2023_summer','Summer 2023 | the 2024 Q1 trough'),
        ('2024-02-15','path_2024_winter','Winter 2024 | the smaller 2024 Q2 peak'),
        ('2025-08-14','path_2025_summer','Summer 2025 | a recent completed forecast year'),
        ('2026-08-13','path_2026_summer','Summer 2026 | the latest archived comparison')]
    for args in selections:path_chart(*args)
    path_performance();nowcast_performance();surprise_scatter();surprise_gains()
    points=OUT/'plotted_points.csv'
    pd.DataFrame(plotted).to_csv(points,index=False,float_format='%.17g')
    manifest={'description':'Frozen-data figures only; no model estimation or data updates.',
              'clock':'report','monthly_realised_last_period':max(data['realised']),
              'selection':'Six illustrative CNB rounds, plus complete-sample score and surprise charts.',
              'sources':{str(p.relative_to(ROOT)):sha(p) for p in SOURCE_FILES},
              'outputs':{str(p.relative_to(ROOT)):sha(p) for p in chart_files+[points]},
              'builder_sha256':sha(Path(__file__)),'n_charts':len(chart_files),'n_plotted_values':len(plotted)}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({k:manifest[k] for k in ['n_charts','n_plotted_values','monthly_realised_last_period']},indent=2))

if __name__=='__main__':main()
