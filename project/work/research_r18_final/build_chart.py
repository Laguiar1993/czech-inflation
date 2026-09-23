"""Static R18 comparison from the fixed primary scoreboard; no refitting."""
from pathlib import Path
import hashlib,json,os
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'work/research_r18_final/matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

source=ROOT/'output/research_r18/path_v2/evaluation/primary_scoreboard.csv'
f=pd.read_csv(source);f=f[f.metric.eq('headline_yy')]
models={'STATE_FAST_R15':('FAST','#237bb4'),'STABLE_LOCAL_CORE_R14B':('Current core','#239777'),
        'DAMPED_P95_Q001_R16':('Gentle slope','#8273bb'),'MCT_FAST_R18':('New category trend','#e29134'),
        'MCT_SIGNALS_R18':('New category + signals','#c45d62')}
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(13.6,5.7))
rows=[]
for ax,(sample,title) in zip(axes,[('full','Full historical evaluation'),('origins_2024plus','Forecast origins from 2024')]):
    for model,(label,color) in models.items():
        z=f[f.model.eq(model)&f['sample'].eq(sample)].sort_values('h')
        assert len(z)==12 and z.n_missing_forecasts.eq(0).all()
        rows.append(z)
        ax.plot(z.h,z.rmse,marker='o',markersize=3.8,color=color,label=label,linewidth=2)
    ax.set(title=title,xlabel='Months after the nowcast month',ylabel='Annual CPI forecast RMSE (percentage points)')
    ax.set_xticks([1,3,6,9,12]);ax.set_ylim(bottom=0);ax.grid(alpha=.18)
fig.suptitle('R18: broader category information does not yet improve the whole path',x=.055,ha='left',fontsize=16,fontweight='bold')
handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='lower center',ncol=3,frameon=False,bbox_to_anchor=(.5,.045))
fig.text(.055,.02,'Identical original scoring dates per horizon. Full n=88 to 75; recent n=30 to 19. Different panel scales. Historical replay through July 2026.',fontsize=9,color='#555555')
fig.subplots_adjust(left=.07,right=.975,top=.85,bottom=.25,wspace=.26)
out=ROOT/'output/research_r18/presentation';out.mkdir(exist_ok=True)
for suffix in ['png','svg']:fig.savefig(out/('path_accuracy_r18.'+suffix),dpi=170)
pd.concat(rows).to_csv(out/'chart_rows.csv',index=False)
files=[source,Path(__file__),out/'chart_rows.csv',out/'path_accuracy_r18.png',out/'path_accuracy_r18.svg']
(out/'manifest.json').write_text(json.dumps({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},indent=2),encoding='utf-8')
print('Saved chart: 120 source points verified.')
