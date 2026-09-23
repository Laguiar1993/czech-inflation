"""Publication figures from saved R22 scores; no fitting or model selection."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r22/charts'
LABELS={'STATE_FAST_R15':'FAST','STABLE_LOCAL_CORE_R14B':'Current core','DAMPED_P95_Q001_R16':'Gentle slope',
        'JOINT_LINEAR_R22':'Joint linear','JOINT_RF_R22':'Joint + forest','JOINT_ENET_R22':'Joint elastic net',
        'JOINT_HALF_R22':'Half joint + FAST','JOINT_OWN_R22':'Matched core only'}
COLORS={'STATE_FAST_R15':'#1e6091','STABLE_LOCAL_CORE_R14B':'#627684','DAMPED_P95_Q001_R16':'#219c88',
        'JOINT_LINEAR_R22':'#df8b20','JOINT_RF_R22':'#945bbb','JOINT_ENET_R22':'#c24d65'}


def setup(ax):
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',color='#e5e8ee',lw=.7);ax.set_axisbelow(True)


def save(fig,name):
    fig.savefig(OUT/(name+'.png'),dpi=180,facecolor='white');fig.savefig(OUT/(name+'.svg'),facecolor='white');plt.close(fig)


def main():
    OUT.mkdir(exist_ok=True);p=ROOT/'output/research_r22/full/evaluation'
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':12,'axes.labelsize':10})
    d=pd.read_csv(p/'primary_scoreboard.csv');d=d[d.metric.eq('headline_yy')]
    fig,axs=plt.subplots(1,2,figsize=(12.6,5.2))
    for ax,sample,title in zip(axs,['full','origins_2024plus'],['Full historical sample','Forecasts made since January 2024']):
        for model,color in COLORS.items():
            g=d[d.model.eq(model)&d['sample'].eq(sample)].sort_values('h')
            ax.plot(g.h,g.rmse,color=color,lw=2,label=LABELS[model])
        ax.set_title(title,loc='left',fontweight='bold');ax.set_xlabel('Forecast horizon (months after h0)')
        ax.set_ylabel('Annual CPI RMSE (percentage points)');ax.set_xticks([1,3,6,9,12]);setup(ax)
    fig.suptitle('R22: the new transmission systems do not improve path accuracy',x=.065,y=.99,ha='left',fontweight='bold',fontsize=15)
    handles,labels=axs[0].get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',ncol=3,bbox_to_anchor=(.5,.055),frameon=False)
    fig.text(.065,.015,'Same 969 origin/horizon keys per model. At h12: 75 full-sample outcomes; 19 since 2024. Revised-history research.',fontsize=9,color='#536172')
    fig.subplots_adjust(top=.85,bottom=.29,left=.065,right=.98,wspace=.23);save(fig,'r22_path_accuracy')
    raw=pd.read_csv(p/'underlying_core_turn_summary.csv');raw=raw[raw.scope.eq('all_models_common')&raw['sample'].eq('full')]
    equal=pd.read_csv(ROOT/'output/research_r22/diagnostics/seasonality_equalized_turn_summary.csv');equal=equal[equal['sample'].eq('full')]
    models=['JOINT_OWN_R22','JOINT_LINEAR_R22','JOINT_RF_R22','JOINT_ENET_R22'];x=np.arange(4)
    fig,axs=plt.subplots(1,2,figsize=(12.6,5.4))
    for ax,metric,title in zip(axs,['exact_band_hits','false_turns'],['Correct peak/trough calls','False peak/trough calls']):
        a=raw.set_index('model').loc[models,metric];b=equal.set_index('model').loc[models,metric]
        p1=ax.bar(x-.19,a,.36,color='#8497ac',label='Original score');p2=ax.bar(x+.19,b,.36,color='#df8b20',label='Seasonal difference removed')
        ax.bar_label(p1,padding=3);ax.bar_label(p2,padding=3);ax.set_xticks(x,[LABELS[m].replace(' ','\n',1) for m in models]);ax.set_title(title,loc='left',fontweight='bold')
        ax.set_ylim(0,max(a.max(),b.max())*1.2+1);setup(ax)
    fig.suptitle('Apparent turn detection mostly reflects seasonal disagreement',x=.065,y=.98,ha='left',fontweight='bold',fontsize=15)
    fig.legend(*axs[0].get_legend_handles_labels(),loc='lower center',ncol=2,bbox_to_anchor=(.5,.09),frameon=False)
    fig.text(.065,.055,'Diagnostic only: remove R22 seasonality from predictions and restore R15 seasonality; realised event labels stay fixed.',fontsize=9,color='#536172')
    fig.text(.065,.018,'159 overlapping origin/band opportunities, 77 realised turns. These are not independent episodes or evidence of leading CNB.',fontsize=9,color='#536172')
    fig.subplots_adjust(top=.84,bottom=.29,left=.065,right=.98,wspace=.18);save(fig,'r22_turn_audit')
    payload=json.loads((p/'replay_data.json').read_text());reports=payload['reportsByClock']['report']
    dates=['2022-02-10','2023-02-09','2024-02-15','2025-02-13']
    fig,axs=plt.subplots(2,2,figsize=(12.6,8.0))
    for ax,date in zip(axs.flat,dates):
        r=next(x for x in reports if x['report_date']==date)
        start=pd.Period(r['origin'],'M')-3;end=pd.Period(r['origin'],'M')+12
        truth=[(k,v) for k,v in payload['realised'].items() if str(start)<=k<=str(end)]
        ax.plot(pd.to_datetime([k for k,v in truth]),[v for k,v in truth],color='#15202c',lw=2.3,label='Realised (current vintage)')
        qpoints=[(pd.Period(x['quarter'],'Q').start_time+pd.DateOffset(months=1),x['value']) for x in r['cnb']]
        ax.plot([k for k,v in qpoints],[v for k,v in qpoints],color='#be2342',lw=2,marker='s',ms=3,label='CNB (quarter averages)')
        for model in ['STATE_FAST_R15','DAMPED_P95_Q001_R16','JOINT_LINEAR_R22','JOINT_RF_R22']:
            path=r['paths'][model];ax.plot(pd.to_datetime([k for k,v in path]),[v for k,v in path],color=COLORS[model],lw=1.65,label=LABELS[model])
        ax.set_title(f"{r['season']} {r['year']} | snapshot {r['origin']}",loc='left',fontweight='bold')
        ax.set_xlim(start.start_time,end.end_time);ax.set_ylabel('CPI inflation (year-on-year, %)')
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4));ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %y'));setup(ax)
    fig.suptitle('Czech inflation paths alongside published CNB rounds',x=.07,y=.985,ha='left',fontweight='bold',fontsize=15)
    fig.legend(*axs[0,0].get_legend_handles_labels(),loc='lower center',ncol=3,bbox_to_anchor=(.5,.045),frameon=False)
    fig.text(.07,.018,'Four consecutive winter rounds, chosen by calendar. Report clock. Monthly model paths vs quarterly CNB points; scores use quarter averages.',fontsize=8.5,color='#536172')
    fig.subplots_adjust(top=.91,bottom=.18,left=.07,right=.98,hspace=.39,wspace=.2);save(fig,'r22_cnb_winter_rounds')


if __name__=='__main__':main()
