"""Fixed, reproducible 90-origin independent nowcast comparison (R9).

Run from any directory: python independent_nowcast_experiment.py
No data refresh or legacy output overwrite; all inputs are hashed.
"""
from pathlib import Path
import hashlib
import json
import os

import numpy as np
import pandas as pd
import cz_struct as s
from models.independent_nowcast import policy_frame, sequential_errors, residual_correction

ROOT = Path(__file__).resolve().parent
FIX = ROOT / 'tests/fixtures/cleanup'
OUT = ROOT / 'output'


def read(name):
    d = pd.read_csv(FIX/name, index_col=0, float_precision='round_trip')
    d.index = pd.PeriodIndex(d.index, freq='M')
    return d


def score_forecasts(predictions):
    survey = pd.read_csv(ROOT/'data/czcpmom_survey_history_extended.csv')
    survey = survey[survey.era.ne('flash_survey_suspect')].copy()
    survey.index = pd.PeriodIndex(survey.target_month, freq='M')
    sv = survey.reindex(predictions.index)
    events, scores = [], []
    forecasts = predictions.filter(regex='^(HARD|SENTIMENT|LEGACY)_')
    forecasts['CONSENSUS'] = sv.survey_median
    for model, p in forecasts.items():
        e = p - sv.actual
        surprise = sv.actual - sv.survey_median
        d = p - sv.survey_median
        gain = surprise.abs() - e.abs()
        ev = pd.DataFrame(dict(model=model, actual=sv.actual, consensus=sv.survey_median,
             forecast=p, error=e, surprise=surprise, deviation=d, gain=gain,
             big=surprise.abs() >= .4-1e-9, alert=d.abs() >= .2-1e-9))
        # Ratio is diagnostic only; overshooting incurs ordinary forecast loss.
        ev['capture_ratio'] = (d / surprise).where(ev.big)
        events.append(ev)
        for frame, mask in [('all', p.notna()), ('ex_jan', p.index.month != 1),
                            ('2024+', p.index >= pd.Period('2024-01')),
                            ('flash2025+', p.index >= pd.Period('2025-01')),
                            ('big', ev.big), ('big_ex_jan', ev.big & (p.index.month != 1)),
                            ('alerts', ev.alert)]:
            z = ev[mask].dropna(subset=['actual', 'forecast', 'consensus'])
            scores.append(dict(model=model, frame=frame, n=len(z),
                rmse=np.sqrt(np.mean(z.error**2)), mae=z.error.abs().mean(), bias=z.error.mean(),
                mean_gain=z.gain.mean(), total_gain=z.gain.sum(),
                closer=int((z.gain > 1e-9).sum()),
                material_win=int((z.gain >= .15-1e-9).sum()),
                material_loss=int((z.gain <= -.15+1e-9).sum()),
                direction=int((z.deviation*z.surprise > 0).sum()),
                alerts=int(z.alert.sum()), alerted_big=int((z.alert & z.big).sum()),
                false_alarm=int((z.alert & ~z.big).sum()), missed_big=int((~z.alert & z.big).sum()),
                big_precision=float((z.alert & z.big).sum()/z.alert.sum()) if z.alert.sum() else np.nan,
                big_recall=float((z.alert & z.big).sum()/z.big.sum()) if z.big.sum() else np.nan))
    pd.concat(events).to_csv(OUT/'independent_nowcast_releases.csv', index_label='period')
    board = pd.DataFrame(scores)
    board.to_csv(OUT/'independent_nowcast_scores.csv', index=False)
    # Predeclared ESI practical gate, applied to the baseline only.
    b = board.set_index(['model', 'frame'])
    hard, sentiment = b.loc[('HARD_BASE', 'all')], b.loc[('SENTIMENT_BASE', 'all')]
    keep = bool(sentiment.rmse <= .98*hard.rmse and sentiment.mae <= 1.02*hard.mae
                and b.loc[('SENTIMENT_BASE','2024+'),'rmse'] <= 1.05*b.loc[('HARD_BASE','2024+'),'rmse'])
    decision = {'main_policy': 'sentiment' if keep else 'hard', 'ESI_promoted': keep,
                'selection_status': 'exploratory; no untouched historical holdout',
                'rule': 'BASE RMSE improves >=2%; MAE deterioration <=2%; recent RMSE deterioration <=5%'}
    (OUT/'independent_nowcast_selection.json').write_text(json.dumps(decision, indent=2))
    # Paired circular block bootstrap, descriptive rather than selection-adjusted.
    rng = np.random.default_rng(42)
    boot = []
    for a,bname in [('SENTIMENT_BASE','HARD_BASE'),('HARD_HALF','HARD_BASE'),('HARD_FULL','HARD_BASE')]:
        for frame, mask in [('all', np.ones(len(predictions), bool)),
                            ('2024+', predictions.index >= pd.Period('2024-01'))]:
            ae = (predictions[a]-sv.actual)[mask].to_numpy()
            be = (predictions[bname]-sv.actual)[mask].to_numpy()
            valid = np.isfinite(ae) & np.isfinite(be); ae,be=ae[valid],be[valid]
            n=len(ae)
            for block in (3,6,12):
                starts=rng.integers(0,n,(5000,int(np.ceil(n/block))))
                ix=((starts[:,:,None]+np.arange(block))%n).reshape(5000,-1)[:,:n]
                delta=np.sqrt((ae[ix]**2).mean(1))-np.sqrt((be[ix]**2).mean(1))
                boot.append(dict(candidate=a,reference=bname,frame=frame,block=block,
                    delta=np.sqrt((ae**2).mean())-np.sqrt((be**2).mean()),
                    lower=np.quantile(delta,.025),upper=np.quantile(delta,.975)))
    pd.DataFrame(boot).to_csv(OUT/'independent_nowcast_bootstrap.csv',index=False)
    return board,decision


def main():
    # Exact fixture verification before any fitting.
    hashes=json.loads((FIX/'MANIFEST.json').read_text())
    for name, sha in hashes.items():
        if hashlib.sha256((FIX/name).read_bytes()).hexdigest()!=sha:
            raise ValueError(f'fixture changed: {name}')
    bt=pd.read_csv(OUT/'cz_struct_backtest.csv',index_col='period',float_precision='round_trip')
    bt.index=pd.PeriodIndex(bt.index,freq='M')
    y=read('target_headline_cpi_mm.csv').iloc[:,0]
    comp=read('component_food_fuel_mm.csv')
    core=read('cnb_core_mm.csv').iloc[:,0]
    reg=read('cnb_regulated_mm.csv').iloc[:,0]
    alc=read('alcohol_tobacco.csv').iloc[:,0]
    feats=read('core_features.csv')
    histories={}
    for policy in ('hard','sentiment'):
        histories[policy]=sequential_errors(feats,core,policy,through=bt.index.max()-1)
        histories[policy].to_csv(OUT/f'independent_nowcast_{policy}_errors.csv',index_label='period')
        print(policy, len(histories[policy]), 'sequential errors',flush=True)
    rows, diagnostics=[],[]
    for i,t in enumerate(bt.index):
        clock=pd.Timestamp(bt.loc[t,'as_of_eve'])
        w=s.solve_weights(y,comp,core,reg,t-1,as_of=clock,alc=alc)[s._regime(t)]
        # Non-core legs are shared with the independently reproduced reference.
        # This attribution identity avoids refitting unchanged X13/energy legs.
        old_core=s._ridge_predict(feats,core,t,as_of=clock)[0]
        if abs(old_core-bt.loc[t,'core_pred_eve'])>1e-10:
            raise ValueError(f'legacy core parity failed: {t}')
        rest=bt.loc[t,'STRUCT_EVE']-w['core']*old_core
        row=dict(period=str(t),as_of_eve=clock.isoformat(),coreweight=w['core'],
                 LEGACY_BASE=bt.loc[t,'STRUCT_EVE'],LEGACY_HALF=bt.loc[t,'STRUCT_PEH_WARM_EVE'],
                 LEGACY_FULL=bt.loc[t,'STRUCT_PE_WARM_EVE'])
        for policy in ('hard','sentiment'):
            x=s._mask_row_by_availability(policy_frame(feats,policy),t,clock)
            cp=s._ridge_predict(x,core,t,as_of=clock)[0]
            corr,diag=residual_correction(x,histories[policy],t,clock,policy)
            base=rest+w['core']*cp
            row.update({f'{policy.upper()}_BASE':base,
                        f'{policy.upper()}_HALF':base+.5*w['core']*corr,
                        f'{policy.upper()}_FULL':base+w['core']*corr})
            diagnostics.append(dict(period=str(t),**diag,core_forecast=cp,core_correction=corr))
        rows.append(row)
        pd.DataFrame(rows).to_csv(OUT/'independent_nowcast_forecasts.csv',index=False)
        if i%10==0:print(f'Completed {i+1}/{len(bt)} {t}',flush=True)
    (OUT/'independent_nowcast_diagnostics.json').write_text(json.dumps(diagnostics,indent=2))
    pred=pd.DataFrame(rows).set_index('period');pred.index=pd.PeriodIndex(pred.index,freq='M')
    board,decision=score_forecasts(pred)
    hashes['output/cz_struct_backtest.csv']=hashlib.sha256((OUT/'cz_struct_backtest.csv').read_bytes()).hexdigest()
    hashes['data/czcpmom_survey_history_extended.csv']=hashlib.sha256((ROOT/'data/czcpmom_survey_history_extended.csv').read_bytes()).hexdigest()
    (OUT/'independent_nowcast_manifest.json').write_text(json.dumps({'inputs':hashes,
        'noncore':'unchanged reference; full baseline independently replayed before this experiment',
        'warm_history':'policy-specific sequential ridge; no legacy error file',
        'vintage_status':'pseudo-OOS using frozen latest-vintage feature frames plus publication rules'},indent=2))
    print(board[board.frame.isin(['all','big','2024+','alerts'])].to_string(index=False))
    print(decision)


if __name__=='__main__':
    main()
