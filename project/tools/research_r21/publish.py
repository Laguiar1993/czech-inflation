"""Presentation tables and plots, with a fixed-support uncertainty check."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import r17_common as c
from tools.review.evaluate_r15 import block_bootstrap

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r21/presentation'
LABELS={'STATE_FAST_R15':'FAST','STABLE_LOCAL_CORE_R14B':'Current core','DAMPED_P95_Q001_R16':'Gentle slope',
        'CORE_FEEDBACK_R21':'Core error feedback','POOL_PARTIAL_R21':'Partial-outcome blend','ANCHOR_HL12_R21':'Anchor, 12m half-life'}


def main():
    OUT.mkdir(exist_ok=False)
    path=ROOT/'output/research_r21/path_anchor/evaluation';now=ROOT/'output/research_r21/nowcast/evaluation'
    board=pd.read_csv(path/'primary_scoreboard.csv');core=board[board.metric.eq('headline_yy')]
    table=core[core.h.isin([3,6,12])&core['sample'].isin(['full','origins_2024plus'])].pivot(index='model',columns=['sample','h'],values='rmse')
    table.to_csv(OUT/'path_rmse.csv')
    # Reconstruct independent FULL component attribution from the verified shared non-core blocks.
    contrib=c.read('output/contribution_report.csv').set_index('period')
    base=c.read('output/independent_nowcast_forecasts.csv').set_index('period')
    diag=pd.DataFrame(json.loads((ROOT/'output/independent_nowcast_diagnostics.json').read_text()))
    diag=diag[diag.policy.eq('hard')].set_index('period').reindex(base.index);contrib=contrib.reindex(base.index)
    reconstructed=contrib.model-contrib.contrib_core+contrib.w_core*(diag.core_forecast+diag.core_correction)
    np.testing.assert_allclose(reconstructed,base.HARD_FULL,atol=1e-12,rtol=0)
    attrib=pd.DataFrame(index=base.index)
    attrib['core']=contrib.w_core*(diag.core_forecast+diag.core_correction-contrib.act_core)
    for block in ['food','administered','alc','fuel']:attrib[block]=contrib['err_'+block]
    attrib['reconciliation']=contrib.wedge_err;attrib['headline_error']=base.HARD_FULL-contrib.actual
    np.testing.assert_allclose(attrib.drop(columns='headline_error').sum(axis=1),attrib.headline_error,atol=1e-12,rtol=0)
    attrib['squared_error_share']=attrib.headline_error**2/(attrib.headline_error**2).sum()
    attrib.to_csv(OUT/'full_nowcast_error_attribution.csv')
    rows=pd.read_csv(path/'primary_rows.csv');boot=[];omissions=[]
    for h,g in rows.groupby('h'):
        actual=g.drop_duplicates('origin').set_index('origin').yy_actual
        predictions=g.pivot(index='origin',columns='model',values='yy_exante');errors=predictions.sub(actual,axis=0)
        for model in [x for x in errors if x.endswith('_R21')]:
            for sample,mask in [('full',np.ones(len(errors),bool)),('origins_2024plus',errors.index>='2024-01')]:
                e=errors.loc[mask];pairs=pd.DataFrame(dict(origin=e.index,loss_difference=e[model].to_numpy()**2-e.STATE_FAST_R15.to_numpy()**2))
                boot.append(dict(model=model,h=h,sample=sample,**block_bootstrap(pairs)))
            for year in sorted(set(errors.index.str[:4])):
                e=errors[~errors.index.str.startswith(year)]
                omissions.append(dict(model=model,h=h,omitted_year=year,n=len(e),
                    rmse_delta=np.sqrt((e[model]**2).mean())-np.sqrt((e.STATE_FAST_R15**2).mean()),
                    mae_delta=e[model].abs().mean()-e.STATE_FAST_R15.abs().mean()))
    pd.DataFrame(boot).to_csv(OUT/'primary_support_bootstrap.csv',index=False)
    pd.DataFrame(omissions).to_csv(OUT/'leave_one_origin_year_out.csv',index=False)
    nb=pd.read_csv(now/'scoreboard.csv');nb.to_csv(OUT/'nowcast_scoreboard.csv',index=False)
    fig,axes=plt.subplots(2,2,figsize=(14,9),layout='constrained')
    colors=['#195b9b','#718a2c','#9b6aaa','#dd6b20','#159a9c','#b34453']
    for ax,sample,title in [(axes[0,0],'full','Path accuracy: all historical origins'),(axes[0,1],'origins_2024plus','Path accuracy: origins from 2024')]:
        for (model,label),color in zip(LABELS.items(),colors):
            z=core[core.model.eq(model)&core['sample'].eq(sample)].sort_values('h')
            ax.plot(z.h,z.rmse,label=label,color=color,lw=1.8)
        ax.set(title=title,xlabel='Months ahead',ylabel='Annual CPI RMSE, percentage points',xticks=[1,3,6,9,12]);ax.grid(alpha=.18)
    axes[0,0].legend(fontsize=8,loc='upper left')
    names=['HARD_BASE','HARD_HALF','HARD_FULL','CORE_RF_MEAN_R21','CORE_RF_MEDIAN_R21','HEADLINE_ENET_R21']
    labels=['BASE','HALF','FULL','Forest mean','Forest median','Headline ENET']
    big=nb[nb['sample'].eq('big')].set_index('model').loc[names]
    ax=axes[1,0];y=np.arange(len(names));ax.barh(y-.18,big.material_wins,.34,label='Material wins',color='#2d8e70')
    ax.barh(y+.18,big.material_losses,.34,label='Material losses',color='#ba5260')
    ax.set(yticks=y,yticklabels=labels,xlabel='Release count',title='Nowcast: 23 realised big surprises');ax.invert_yaxis();ax.legend(fontsize=8)
    ax.text(0,-.28,'Big = |actual-consensus| ≥0.4pp. Material = ≥0.15pp absolute-error change.\nConditional score; it does not measure advance alert precision.',transform=ax.transAxes,fontsize=8)
    ax=axes[1,1];events=attrib.loc[['2022-10','2023-01']];cols=['core','food','administered','alc','fuel','reconciliation']
    x=np.arange(2);positive=np.zeros(2);negative=np.zeros(2)
    for col,color in zip(cols,['#195b9b','#85a745','#c94752','#8c6aad','#4da5b1','#8d8d8d']):
        v=events[col].to_numpy();bottom=np.where(v>=0,positive,negative)
        ax.bar(x,v,.55,bottom=bottom,label=col.replace('_',' '),color=color)
        positive+=np.maximum(v,0);negative+=np.minimum(v,0)
    ax.scatter(x,events.headline_error,marker='D',color='black',label='Total error',zorder=5)
    ax.axhline(0,color='#666',lw=.8);ax.set(xticks=x,xticklabels=['October 2022','January 2023'],ylabel='Forecast minus actual, pp',title='Two releases explain 48.5% of FULL squared error')
    ax.legend(fontsize=7,ncols=2,loc='upper right')
    fig.suptitle('Czech CPI · R21 model research\nSame frozen origins; no new live model promoted',fontsize=15)
    fig.savefig(OUT/'model_comparison.png',dpi=150);fig.savefig(OUT/'model_comparison.svg');plt.close(fig)
    c.dump(OUT/'checks.json',dict(independent_full_reconstruction_max=float(abs(reconstructed-base.HARD_FULL).max()),
            contribution_error_max=float(abs(attrib[cols].sum(axis=1)-attrib.headline_error).max()),
            two_largest_squared_error_share=float(attrib.squared_error_share.nlargest(2).sum()),
            bootstrap_contract='primary_support_bootstrap uses the fixed969primary keys; inherited evaluator paired bootstrap uses its labelled own paired support and is not interchangeable.'))
    print('Created',OUT,flush=True)


if __name__=='__main__':main()
