"""Post-forecast attribution only; never fits, selects or changes a model."""
from pathlib import Path
import json

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/research_r12/integration'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    evidence=pd.read_csv(ROOT/'output/research_r12/pooling/component_errors.csv',float_precision='round_trip')
    rows=[]
    for name in ('POOL_SEPARATE','POOL_12','POOL_48'):
        a=evidence[evidence.model==name].set_index('period')
        b=evidence[evidence.model=='TARGET_OWN'].set_index('period').reindex(a.index)
        for sample,mask in [('all',np.ones(len(a),bool)),('recent',a.index>='2024-01'),
                            ('without_oct2022',a.index!='2022-10')]:
            aa,bb=a.loc[mask],b.loc[mask]
            gain=np.mean(bb.error**2-aa.error**2)
            coregain=np.mean(bb.weighted_core_error**2-aa.weighted_core_error**2)
            crossgain=2*np.mean(aa.noncore_reconciliation_error*(bb.weighted_core_error-aa.weighted_core_error))
            if abs(gain-coregain-crossgain)>1e-12:
                raise AssertionError('error attribution failed')
            rows.append(dict(model=name,reference='TARGET_OWN',sample=sample,n=len(aa),
                headline_mse_gain=gain,weighted_core_mse_gain=coregain,error_cross_term_gain=crossgain,
                candidate_rmse=np.sqrt(np.mean(aa.error**2)),reference_rmse=np.sqrt(np.mean(bb.error**2))))
    pd.DataFrame(rows).to_csv(OUT/'pooling_attribution.csv',index=False)
    path=pd.read_csv(ROOT/'output/research_r12/path/forecasts.csv',float_precision='round_trip')
    baseline=path[path.model=='INDEPENDENT_BRIDGE'].set_index(['origin','h'])
    byyear=[]
    for name,g in path.groupby('model',sort=False):
        g=g.set_index(['origin','h']).join(baseline[['yy_exante']].rename(columns={'yy_exante':'reference'}))
        for h in (3,6,12):
            hg=g[g.index.get_level_values('h')==h].copy()
            hg=hg[np.isfinite(hg.yy_actual)&np.isfinite(hg.yy_exante)&np.isfinite(hg.reference)]
            for year,pg in hg.groupby(hg.index.get_level_values('origin').str[:4]):
                e=pg.yy_exante-pg.yy_actual
                b=pg.reference-pg.yy_actual
                byyear.append(dict(model=name,origin_year=int(year),h=h,n=len(pg),
                    rmse=np.sqrt(np.mean(e**2)),mae=e.abs().mean(),bias=e.mean(),
                    mean_squared_gain_vs_bridge=np.mean(b**2-e**2)))
    pd.DataFrame(byyear).to_csv(OUT/'path_origin_year_scores.csv',index=False)
    declarations={'status':'Post-result diagnostics only; no further fitted variants or automatic promotion.',
        'nowcast_references':['R9_BASE','R9_HALF','R9_FULL','TARGET_OWN'],
        'pooling_variants':['POOL_SEPARATE','POOL_12','POOL_48'],
        'path_variants':['FOOD_TREND_R12','FOOD_COST_R12','DIRECT_MONTHLY_R12','DIRECT_CUMULATIVE_R12'],
        'online_retail_collection':False,'expectations_in_new_estimators':False,
        'energy_status':'See energy/summary.json; unavailable effects are not measured zeros.'}
    (OUT/'interpretation.json').write_text(json.dumps(declarations,indent=2),encoding='utf-8')
    print('Wrote interpretation tables without fitting or changing forecasts.')


if __name__=='__main__':
    main()
