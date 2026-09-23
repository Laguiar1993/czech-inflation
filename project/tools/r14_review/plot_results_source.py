from pathlib import Path
import shutil
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r14/review'
HERE=ROOT
OUT.mkdir(exist_ok=True)
models=['INDEPENDENT_BRIDGE','STABLE_PIPELINE_R14B','STABLE_LOCAL_CORE_R14B','STABLE_LONG_CORE_R14B']
labels=['Existing reference','Food + fuel update','+ Recent core trend','+ Longer-history core']
colors=['#7d8996','#319b92','#1b4c78','#cf8c35']
s=pd.read_csv(ROOT/'output/research_r14b/integration/summary.csv')
s=s[s.scope.eq('combined_common')]
fig,axs=plt.subplots(2,2,figsize=(14,10))
fig.suptitle('CZK Cpi Forecasting - Latest models\nR14 research results | 9 September 2026',fontsize=18,fontweight='bold',color='#15364d')
for ax,sample,title in [(axs[0,0],'recent_origins','Forecasts made since January 2024'),(axs[0,1],'recent_targets','Forecasts for outcomes since January 2024')]:
    for i,(m,l,c) in enumerate(zip(models,labels,colors)):
        q=s[(s['sample']==sample)&s.model.eq(m)&s.h.isin([6,12])].set_index('h')
        x=[j+(i-1.5)*.19 for j in (0,1)]
        values=q.loc[[6,12],'yy_rmse'].tolist()
        bars=ax.bar(x,values,.18,color=c,label=l)
        ax.bar_label(bars,fmt='%.2f',fontsize=8,padding=2)
    counts=s[(s['sample']==sample)&s.model.eq(models[0])].set_index('h').n_common
    ax.set_xticks([0,1],[f'6 months (N={int(counts[6])})',f'12 months (N={int(counts[12])})'])
    ax.set_title(title,fontsize=12);ax.set_ylabel('Annual inflation RMSE, percentage points')
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    ax.set_ylim(0,3.1)
survey=pd.read_csv(ROOT/'output/research_r14/survey/summary.csv')
rows=[]
for m in models:
    rows.append(survey[(survey.scope.eq('paired_'+m))&survey.model.eq(m)].iloc[0])
rows.append(survey[(survey.scope.eq('primary_common'))&survey.model.eq('FMIE')].iloc[0])
ax=axs[1,0]
bars=ax.barh([*labels,'FMIE survey'],[r.rmse for r in rows],color=[*colors,'#44315d'])
ax.bar_label(bars,fmt='%.2f',padding=3);ax.invert_yaxis();ax.set_xlim(0,1.6)
ax.set_title('Dated one-year survey comparison (24 reports)',fontsize=12)
ax.set_xlabel('RMSE, percentage points');ax.spines[['top','right']].set_visible(False)
cnb=pd.read_csv(ROOT/'output/research_r14b/integration/cnb_summary.csv')
q=cnb[cnb.scope.eq('combined_common')&cnb['sample'].eq('recent_reports')&cnb.quarters_ahead.eq('all')].set_index('model')
ax=axs[1,1]
bars=ax.barh([*labels,'CNB reports'],q.loc[[*models,'CNB'],'rmse'],color=[*colors,'#44315d'])
ax.bar_label(bars,fmt='%.2f',padding=3);ax.invert_yaxis();ax.set_xlim(0,.75)
ax.set_title('CNB comparison: reports since 2024',fontsize=12)
ax.set_xlabel('Quarterly average annual inflation RMSE, pp');ax.spines[['top','right']].set_visible(False)
handles,legend=axs[0,0].get_legend_handles_labels()
fig.legend(handles,legend,loc='lower center',bbox_to_anchor=(.5,.015),ncol=4,frameon=False,fontsize=10)
fig.text(.5,.075,'Historical research, not an untouched holdout. Overlapping horizons. Survey issue clocks are reconstructed.\nCNB: 34 report-quarter pairs, 10 distinct quarters; our saved paths precede publication and can be older.',ha='center',fontsize=9,color='#586573')
fig.subplots_adjust(left=.16,right=.96,bottom=.18,top=.84,wspace=.63,hspace=.42)
file=OUT/'CZK_CPI_R14_PATH_COMPARISON_2026-09-09.png'
fig.savefig(file,dpi=160,facecolor='white')
dest=ROOT/'output/research_r14/review/path_comparison.png'
if file.resolve()!=dest.resolve():shutil.copyfile(file,dest)
print(file)
