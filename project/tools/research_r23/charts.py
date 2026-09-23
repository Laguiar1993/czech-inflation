"""Figures from frozen R23 score and CNB lead tables."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'output/research_r23/charts'
LABELS={'STATE_FAST_R15':'FAST','STABLE_LOCAL_CORE_R14B':'Current core','DAMPED_P95_Q001_R16':'Gentle slope',
 'CORE_FEEDBACK_R21':'Core feedback','GAP_CALIBRATION_R23':'Quarterly calibration','GAP_DOMESTIC_R23':'Domestic gaps',
 'GAP_IMPORTED_R23':'Imported gaps','GAP_JOINT_R23':'Joint positive ridge','GAP_FREE_R23':'Joint free ridge',
 'GAP_ENET_R23':'Joint elastic net','GAP_HALF_R23':'Half joint + FAST'}
COLORS={'STATE_FAST_R15':'#1e6091','STABLE_LOCAL_CORE_R14B':'#627684','DAMPED_P95_Q001_R16':'#219c88',
 'GAP_JOINT_R23':'#df8b20','GAP_FREE_R23':'#945bbb','GAP_HALF_R23':'#c24d65'}


def setup(ax):
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color='#e5e8ee',lw=.7);ax.set_axisbelow(True)


def save(fig,name):
    for suffix in ['png','svg']:fig.savefig(OUT/(name+'.'+suffix),dpi=180,facecolor='white')
    plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True);p=ROOT/'output/research_r23/final/evaluation'
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12})
    d=pd.read_csv(p/'primary_scoreboard.csv');d=d[d.metric.eq('headline_yy')]
    fig,axs=plt.subplots(1,2,figsize=(12.6,5.2))
    for ax,sample,title in zip(axs,['full','origins_2024plus'],['Full historical sample','Forecast origins since January 2024']):
        for model,color in COLORS.items():
            g=d[d.model.eq(model)&d['sample'].eq(sample)].sort_values('h');ax.plot(g.h,g.rmse,lw=2,color=color,label=LABELS[model])
        ax.set_title(title,loc='left',fontweight='bold');ax.set_xlabel('Horizon after h0 (months)');ax.set_ylabel('Annual CPI RMSE (percentage points)');ax.set_xticks([1,3,6,9,12]);setup(ax)
    fig.suptitle('R23: adaptive core paths with quarterly cost-gap corrections',x=.065,y=.985,ha='left',fontweight='bold',fontsize=15)
    fig.legend(*axs[0].get_legend_handles_labels(),loc='lower center',ncol=3,bbox_to_anchor=(.5,.055),frameon=False)
    fig.text(.065,.018,'Identical 969 origin/horizon keys per model. At h12: 75 full-sample and 19 recent observations. Current-vintage historical research.',fontsize=8.8,color='#536172')
    fig.subplots_adjust(top=.85,bottom=.29,left=.065,right=.98,wspace=.23);save(fig,'r23_path_accuracy')
    e=pd.read_csv(p/'cnb_first_call_episodes.csv');e=e[e.clock.eq('report')&e.threshold.eq(.3)&e.revision_eligible&e.realised.notna()]
    models=list(LABELS);metrics=[]
    for model in models:
        g=e[e.model.eq(model)]
        metrics.append([int(g.joint_success.sum()),int((g.material_gain&~g.joint_success).sum()),int((~g.material_gain&~g.material_loss).sum()),int(g.material_loss.sum())])
    v=np.array(metrics);fig,ax=plt.subplots(figsize=(12.6,6.2));left=np.zeros(len(models));y=np.arange(len(models))
    for j,(label,color) in enumerate([('CNB confirmation + CPI gain','#238b67'),('CPI gain without CNB confirmation','#5289b1'),('Immaterial CPI difference','#c3c9d0'),('Material CPI loss','#c65d65')]):
        bars=ax.barh(y,v[:,j],left=left,label=label,color=color)
        for bar,n in zip(bars,v[:,j]):
            if n:ax.text(bar.get_x()+bar.get_width()/2,bar.get_y()+bar.get_height()/2,str(n),ha='center',va='center',fontsize=9,color='white' if j!=2 else '#25364a')
        left+=v[:,j]
    ax.set_yticks(y,[LABELS[m] for m in models]);ax.invert_yaxis();ax.set_xlabel('First-call episodes with next-report comparison and realised CPI');ax.set_xlim(0,max(left)+2)
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('Did we disagree before CNB revised, and were we eventually closer?',x=.03,y=.98,ha='left',fontweight='bold',fontsize=14)
    fig.legend(*ax.get_legend_handles_labels(),loc='lower center',ncol=2,bbox_to_anchor=(.5,.075),frameon=False)
    fig.text(.03,.042,'Report clock; call >=0.30pp. Confirmation: next CNB path >=0.15pp closer. CPI gain/loss: >=0.15pp absolute-error difference.',fontsize=8.8,color='#536172')
    fig.text(.03,.015,'Same target quarter must remain beyond the next report quarter. Consecutive same-direction calls deduplicated; adjacent quarters still dependent.',fontsize=8.6,color='#536172')
    fig.subplots_adjust(top=.88,bottom=.25,left=.2,right=.97);save(fig,'r23_cnb_lead_calls')
    payload=json.loads((p/'replay_data.json').read_text());reports=payload['reportsByClock']['report']
    fig,axs=plt.subplots(2,2,figsize=(12.6,8))
    for ax,date in zip(axs.flat,['2022-02-10','2023-02-09','2024-02-15','2025-02-13']):
        r=next(x for x in reports if x['report_date']==date);start=pd.Period(r['origin'],'M')-3;end=pd.Period(r['origin'],'M')+12
        truth=[(k,v) for k,v in payload['realised'].items() if str(start)<=k<=str(end)]
        ax.plot(pd.to_datetime([k for k,v in truth]),[v for k,v in truth],color='#15202c',lw=2.3,label='Realised (current vintage)')
        qpoints=[(pd.Period(x['quarter'],'Q').start_time+pd.DateOffset(months=1),x['value']) for x in r['cnb']]
        ax.plot([k for k,v in qpoints],[v for k,v in qpoints],color='#be2342',lw=2,marker='s',ms=3,label='CNB (quarter averages)')
        for model in ['STATE_FAST_R15','DAMPED_P95_Q001_R16','GAP_JOINT_R23','GAP_HALF_R23']:
            path=r['paths'][model];ax.plot(pd.to_datetime([k for k,v in path]),[v for k,v in path],color=COLORS[model],lw=1.65,label=LABELS[model])
        ax.set_title(f"{r['season']} {r['year']} | snapshot {r['origin']}",loc='left',fontweight='bold');ax.set_xlim(start.start_time,end.end_time);ax.set_ylabel('Annual CPI (%)')
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4));ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'));setup(ax)
    fig.suptitle('Czech inflation paths alongside published CNB rounds',x=.07,y=.985,ha='left',fontweight='bold',fontsize=15)
    fig.legend(*axs[0,0].get_legend_handles_labels(),loc='lower center',ncol=3,bbox_to_anchor=(.5,.045),frameon=False)
    fig.text(.07,.018,'Four consecutive winter rounds, selected by calendar. Monthly paths vs quarterly CNB points; scores use quarter averages. Historical replay.',fontsize=8.8,color='#536172')
    fig.subplots_adjust(top=.91,bottom=.18,left=.07,right=.98,hspace=.39,wspace=.2);save(fig,'r23_cnb_winter_rounds')


if __name__=='__main__':main()
