"""Probe 10: assembled headline annual-rate RMSE at every horizon 1..12, candidate against the R24 path, by era, on the
primary support (recompounded from mm_forecast; nothing from the evaluator)."""
import json
import numpy as np
import pandas as pd
import probe_common as pc

OUT = pc.HERE / 'probe_10_headline_all_h'; OUT.mkdir(exist_ok=True)
native = pc.load_native(); headline = pc.load_headline(); support = pc.load_support()
rows = []
for (o, m), g in native[native.model.isin([pc.BASELINE, pc.CANDIDATE, pc.PPI_CANDIDATE])].groupby(['origin', 'model']):
    path = g.set_index('h').mm_forecast.to_dict()
    for h in range(1, 13):
        if (o, h) not in support:
            continue
        t = pd.Period(o, 'M') + h; w = headline.reindex(pd.period_range(t - 11, t, freq='M'))
        rows.append(dict(origin=o, model=m, h=h, yy=pc.compound_yy(headline, path[0], path, o, h), yy_actual=float(100 * np.expm1(np.log1p(w / 100).sum())) if w.notna().all() else np.nan))
r = pd.DataFrame(rows).dropna()
out = []
for h in range(1, 13):
    g = r[r.h == h].pivot(index='origin', columns='model', values='yy'); truth = r[r.h == h].drop_duplicates('origin').set_index('origin').yy_actual
    for era in pc.ERAS:
        z = g[pc.era_mask(g.index, era)].dropna(); t = truth.reindex(z.index)
        out.append(dict(h=h, sample=era, n=len(z), baseline=pc.rmse(z[pc.BASELINE] - t), candidate=pc.rmse(z[pc.CANDIDATE] - t), ppi=pc.rmse(z[pc.PPI_CANDIDATE] - t)))
out = pd.DataFrame(out); out['ratio'] = out.candidate / out.baseline; out['ratio_ppi'] = out.ppi / out.baseline
out.to_csv(OUT / 'headline_by_h_era.csv', index=False)
piv = out.pivot(index='h', columns='sample', values='ratio').round(4); piv.to_csv(OUT / 'headline_ratio_by_h_era.csv')
print(piv.to_string())
print('cells worse than baseline:', int((out.ratio > 1).sum()), 'of', len(out))
print(out[out.ratio > 1][['h', 'sample', 'n', 'baseline', 'candidate', 'ratio']].to_string())
