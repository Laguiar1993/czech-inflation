"""R21 frozen support evaluation and research charts."""
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import r17_common as c
from tools.review import evaluate_r17 as previous


def nowcast(root):
    out=root/'evaluation';out.mkdir(exist_ok=False)
    manifest=json.loads((root/'manifest.json').read_text())
    for name,digest in manifest['outputs'].items():
        if c.sha(root/name)!=digest:raise ValueError('Nowcast input drift')
    rows=pd.read_csv(root/'predictions.csv');controls=rows[rows.model.eq('HARD_BASE')].copy()
    controls['model']='CONSENSUS';controls['forecast']=controls.consensus
    rows=pd.concat([rows,controls],ignore_index=True)
    rows['error']=rows.forecast-rows.actual;rows['surprise']=rows.actual-rows.consensus
    rows['deviation']=rows.forecast-rows.consensus;rows['gain']=rows.surprise.abs()-rows.error.abs()
    rows['big']=rows.surprise.abs().ge(.4-1e-9);rows['alert']=rows.deviation.abs().ge(.2-1e-9)
    rows['material_win']=rows.gain.ge(.15-1e-9);rows['material_loss']=rows.gain.le(-.15+1e-9)
    rows['direction']=rows.deviation*rows.surprise>0
    train=pd.read_csv(root/'training.csv');fitted=train[train.model.eq('HEADLINE_ENET_R21')&train.status.eq('estimated')].origin
    scores=[]
    for model,g in rows.groupby('model'):
        samples={'full90':np.ones(len(g),bool),'common_fitted':g.origin.isin(fitted),'2024+':g.origin.ge('2024-01'),
                 'ex_january':~g.origin.str.endswith('-01'),'big':g.big,'big_ex_january':g.big&~g.origin.str.endswith('-01'),
                 'all_alerts':g.alert,'common_fitted_alerts':g.alert&g.origin.isin(fitted)}
        for name,mask in samples.items():
            z=g[mask];e=z.error.to_numpy()
            scores.append(dict(model=model,sample=name,n=len(z),rmse=np.sqrt(np.mean(e**2)) if len(e) else np.nan,
                mae=np.mean(abs(e)) if len(e) else np.nan,bias=np.mean(e) if len(e) else np.nan,
                material_wins=int(z.material_win.sum()),material_losses=int(z.material_loss.sum()),direction_hits=int(z.direction.sum()),
                big=int(z.big.sum()),alerts=int(z.alert.sum()),alerted_big=int((z.alert&z.big).sum()),
                material_big_alerts=int((z.material_win&z.alert&z.big).sum()),gain=z.gain.mean()))
    pd.DataFrame(scores).to_csv(out/'scoreboard.csv',index=False);rows.to_csv(out/'releases.csv',index=False)
    boot=[];omissions=[];rng=np.random.default_rng(210915)
    wide=rows.pivot(index='origin',columns='model',values='error')
    for model in [x for x in wide.columns if x.endswith('_R21')]:
        for reference in ['HARD_BASE','HARD_FULL']:
            for sample,mask in [('full90',np.ones(len(wide),bool)),('common_fitted',wide.index.isin(fitted)),('2024+',wide.index>='2024-01')]:
                own=wide.loc[mask];a=own[model].to_numpy();b=own[reference].to_numpy();n=len(a)
                for block in [3,6,12]:
                    starts=rng.integers(0,n,(2000,int(np.ceil(n/block))));ix=((starts[:,:,None]+np.arange(block))%n).reshape(2000,-1)[:,:n]
                    delta=np.sqrt((a[ix]**2).mean(axis=1))-np.sqrt((b[ix]**2).mean(axis=1))
                    boot.append(dict(model=model,reference=reference,sample=sample,block=block,n=n,
                        rmse_delta=np.sqrt(np.mean(a*a))-np.sqrt(np.mean(b*b)),lower=np.quantile(delta,.025),upper=np.quantile(delta,.975)))
            for omitted in wide.index:
                z=wide.drop(index=omitted)
                omissions.append(dict(model=model,reference=reference,omitted=omitted,
                    rmse_delta=np.sqrt((z[model]**2).mean())-np.sqrt((z[reference]**2).mean()),mae_delta=z[model].abs().mean()-z[reference].abs().mean()))
    pd.DataFrame(boot).to_csv(out/'paired_bootstrap.csv',index=False);pd.DataFrame(omissions).to_csv(out/'leave_one_release_out.csv',index=False)
    c.dump(out/'definitions.json',dict(big='.4pp absolute actual-consensus; alert .2pp absolute model-consensus; material gain .15pp ordinary absolute loss',
         common_fitted=list(fitted),limitation='These are reused historical labels and revised features; descriptive bootstrap is not adjusted for research selection.',
         training_last_release_checks=int((pd.to_datetime(train.last_release)>pd.to_datetime(train.as_of)).sum())))
    print(pd.DataFrame(scores).query("sample in ['full90','common_fitted','2024+','big','all_alerts']").to_string(index=False),flush=True)


def path(root):
    previous.evaluate(root)
    out=root/'evaluation';payload=json.loads((out/'replay_data.json').read_text())
    payload['title']='CNB Rounds Replayed | R21 | historical research'
    payload['method']=[
        'R21: fixed 90 monthly origins February2019-July2026. Revised input history and reconstructed availability; no untouched holdout or live record.',
        'New candidates learn from earlier released errors only. Pool prior is half FAST, quarter current core, quarter gentle slope. Learned weights are shared across all future months.',
        'Complete and partial pools share one objective: exact cumulative headline log error, equal horizon importance, recency weighting and shrinkage to the prior. Partial pool uses each released prefix without waiting for h12.',
        'Component feedback uses past h1 core/food log errors, a shrunk mean and a fixed decaying correction. No administrative magnitude or January rule was tuned.',
        'Independent HARD_BASE h0 and basket accounting are preserved. Monthly forecasts compound into annual rates; quarter forecasts average those annual rates.',
        'CNB report and cutoff clocks both retained. Identical scored support regardless of checkboxes. Repeated target quarters are dependent; .15pp absolute-error improvement defines materiality.',
        'Core turns, sustained movement, headline base effects and CNB-relative accuracy are separate diagnostics. No count of independent turns anticipated before CNB is implied.',
        'No consensus, expectations or CNB forecast enters estimation. Default visibility is for comparison, not promotion.']
    labels={'POOL_PRIOR_R21':'Fixed path blend','POOL_COMPLETE_R21':'Blend - complete outcomes','POOL_PARTIAL_R21':'Blend - released prefixes',
            'CORE_FEEDBACK_R21':'Core error feedback','FOOD_FEEDBACK_R21':'Food error feedback','DUAL_FEEDBACK_R21':'Core + food error feedback'}
    for series in payload['series']:
        if series['kind']=='model':
            series['default']=series['id'] in ['STATE_FAST_R15','POOL_PARTIAL_R21','DUAL_FEEDBACK_R21']
            if series['id'] in labels:series['label']=series['short']=labels[series['id']]
    c.dump(out/'replay_data.json',payload)
    old=out/'cnb_rounds_replayed_r17.html';previous.write_replay(old,payload)
    html=old.read_text(encoding='utf-8').replace('Czech CPI · R17 ·','Czech CPI · R21 ·').replace('CNB Rounds Replayed · R17 · historical','CNB Rounds Replayed · R21 · historical').replace('cnb-rounds-r17-visible-v1','cnb-rounds-r21-visible-v1')
    (out/'cnb_rounds_replayed_r21.html').write_text(html,encoding='utf-8');old.unlink()
    definitions=json.loads((out/'definitions.json').read_text());definitions['limitations']=payload['method'];c.dump(out/'definitions.json',definitions)
    manifest=json.loads((out/'input_manifest.json').read_text());manifest['inputs'][str(Path(__file__).resolve())]=c.sha(Path(__file__))
    manifest['outputs']={p.name:c.sha(p) for p in out.iterdir() if p.is_file() and p.name!='input_manifest.json'};c.dump(out/'input_manifest.json',manifest)
    board=pd.read_csv(out/'primary_scoreboard.csv');print(board.query("metric=='headline_yy' and h in [3,6,12]")[['model','sample','h','n','rmse','mae']].to_string(index=False),flush=True)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('family',choices=['path','nowcast']);ap.add_argument('--root',type=Path,required=True);args=ap.parse_args()
    (path if args.family=='path' else nowcast)(args.root)


if __name__=='__main__':main()
