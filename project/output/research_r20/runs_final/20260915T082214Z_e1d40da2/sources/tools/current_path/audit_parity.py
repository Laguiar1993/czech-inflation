"""Recompute the declared roster; expected forecasts are used only for checking."""
from pathlib import Path
import sys,json,argparse
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from models.current_path import forecast_current_path,MODELS


def main():
    from forecast_independent import fixture_frames
    from models.food_path_r14 import load_inputs
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int)
    args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    frames=fixture_frames();food,available,_=load_inputs()
    pump=pd.read_csv(ROOT/'data/research_r14/fuel/pump_weekly.csv',index_col=0,parse_dates=True,float_precision='round_trip')
    h0=pd.read_csv(ROOT/'output/independent_nowcast_forecasts.csv',index_col='period',float_precision='round_trip')
    sources={MODELS[0]:'output/research_r15/native_forecasts.csv',MODELS[1]:'output/research_r14b/integration/native_forecasts.csv',MODELS[2]:'output/research_r16/native_forecasts.csv'}
    expected=pd.concat([pd.read_csv(ROOT/v,float_precision='round_trip').query('model == @k') for k,v in sources.items()],ignore_index=True)
    annual=pd.read_csv(ROOT/'output/research_r18/path_v2/forecasts.csv',float_precision='round_trip')
    computed=[];differences=[]
    for i,(origin,row) in enumerate(h0.iloc[:args.limit].iterrows()):
        clock=pd.Timestamp(row.as_of_eve).tz_localize('Europe/Prague')
        result=forecast_current_path(frames,food,available,pump,origin,clock,float(row.HARD_BASE))
        actual=result['monthly'];computed.append(actual)
        comp=actual.merge(expected[expected.origin.eq(origin)],on=['origin','h','model'],suffixes=('','_saved'),validate='one_to_one')
        if len(comp)!=39:raise ValueError('All 39 model/horizon rows required')
        cols=['mm_forecast']+[c for c in actual if c.startswith(('value_','weight_','contribution_'))]
        for col in cols:
            delta=comp[col]-comp[col+'_saved']
            mismatch=np.isfinite(comp[col])!=np.isfinite(comp[col+'_saved'])
            for model,g in comp.assign(delta=delta,mismatch=mismatch).groupby('model'):
                differences.append(dict(origin=origin,model=model,field=col,max_abs=float(g.delta.abs().max()),finite_mask_mismatches=int(g.mismatch.sum())))
        scored=actual.merge(annual[['origin','h','model','yy_exante']],on=['origin','h','model'],suffixes=('','_saved'),validate='one_to_one')
        if len(scored)!=39:raise ValueError('All 39 annual reference model/horizon keys required')
        for model,g in scored.groupby('model'):
            differences.append(dict(origin=origin,model=model,field='yy_exante',max_abs=float((g.yy_exante-g.yy_exante_saved).abs().max()),finite_mask_mismatches=int((np.isfinite(g.yy_exante)!=np.isfinite(g.yy_exante_saved)).sum())))
        if i%10==0:print(f'{i+1}/{len(h0.iloc[:args.limit])} origins checked: {origin}',flush=True)
    panel=pd.concat(computed,ignore_index=True);diff=pd.DataFrame(differences)
    panel.to_csv(out/'forecasts.csv',index=False);diff.to_csv(out/'parity_by_origin.csv',index=False)
    failures=diff[(diff.max_abs>1e-8)|diff.finite_mask_mismatches.gt(0)]
    report=dict(origins=panel.origin.nunique(),models=MODELS,rows=len(panel),max_abs=float(diff.max_abs.max()),
        finite_mask_mismatches=int(diff.finite_mask_mismatches.sum()),failed_checks=len(failures),tolerance=1e-8)
    (out/'parity_summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    if len(failures):raise AssertionError('Historical parity failed; see per-origin evidence')


if __name__=='__main__':main()
