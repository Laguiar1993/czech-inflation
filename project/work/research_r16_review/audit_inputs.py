"""Read-only R16 prefit input audit; writes reviewer evidence only."""
from pathlib import Path
import sys
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.paper_replication import build_paper_panel as b

OUT = Path(__file__).resolve().parent

def read_monthly(path):
    d = pd.read_csv(ROOT/path, index_col=0, float_precision='round_trip')
    d.index = pd.PeriodIndex(d.index, freq='M')
    return d

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

manifest = json.loads((ROOT/'output/research_r15/manifest.json').read_text())
checks = []
for kind, prefix in [('inputs', ROOT), ('outputs', ROOT/'output/research_r15')]:
    for name, expected in manifest[kind].items():
        actual = digest(prefix/name)
        checks.append(dict(kind=kind, name=name, expected=expected, actual=actual, matches=actual==expected))
pd.DataFrame(checks).to_csv(OUT/'r15_integrity.csv', index=False)
assert all(x['matches'] for x in checks)

broad = read_monthly('data/core_split/broad_yoy.csv')
panel = read_monthly('data/paper_replication/paper_model_panel_20260912_luci/realtime_panel.csv')
fx = read_monthly('tests/fixtures/cleanup/core_features.csv').eurczk_mm
raws = b.load_raw()
edges = pd.period_range('2005-12', '2009-11', freq='M')
eves = b.release_eves(b.CALENDAR, edges)
# All inspected broad target months precede the release calendar's 2010 start.
# Rebuild its documented next-month day20 09:00 proxy without importing runners.
available = pd.Series({p: (p+1).start_time + pd.Timedelta(days=19,hours=9) for p in broad.index})
rows = []
clock_rows = []
max_diff = 0.
for e, cutoff in eves.items():
    t = e+1
    older = t.end_time.normalize() + pd.Timedelta(days=7,hours=23,minutes=59)
    clock_rows.append(dict(origin=str(t), a6_edge=str(e), panel_clock=str(cutoff),
        legacy_clock=str(older), legacy_is_earlier=older<cutoff,
        broad_last_release=str(available[e]), broad_tminus1_eligible=available[e]<=cutoff))
    for n in (11,12,17,26,45,47,62):
        raw = raws[n]
        levels = raw.values.dropna() if raw.kind=='quarterly' else b.monthly_levels(raw)
        values, policy = b.transform(levels,b.BY_NUMBER[n].transform,number=n)
        eligible = raw.available.loc[raw.available.le(cutoff)].index
        source = eligible.max() if len(eligible) else None
        reconstructed = values.get(source,np.nan)
        saved = panel.loc[e, f'a6_{n:02}']
        equal = (pd.isna(reconstructed) and pd.isna(saved)) or np.isclose(reconstructed,saved,rtol=1e-12,atol=1e-14)
        assert equal, (e,n,saved,reconstructed)
        if np.isfinite(saved): max_diff=max(max_diff,abs(saved-reconstructed))
        rows.append(dict(origin=str(t), row=n, source=raw.source, source_period=str(source),
            available_from=str(raw.available.get(source,pd.NaT)), cutoff=str(cutoff),
            source_was_later_than_legacy_clock=bool(source is not None and raw.available[source]>older),
            transform=policy, raw_reconstructed=reconstructed, saved=saved, matches=equal))
pd.DataFrame(rows).to_csv(OUT/'warmup_raw_lineage.csv',index=False)
pd.DataFrame(clock_rows).to_csv(OUT/'warmup_clocks.csv',index=False)

summary=dict(r15_hashes=len(checks),r15_hashes_match=True,
    broad_start=str(broad.index.min()),broad_end=str(broad.index.max()),
    broad_finite=broad.notna().sum().to_dict(),fx_first_finite=str(fx.first_valid_index()),
    warmup_origins=len(edges),warmup_raw_checks=len(rows),maximum_panel_difference=max_diff,
    legacy_clock_earlier_count=sum(x['legacy_is_earlier'] for x in clock_rows),
    broad_last_observation_eligible_count=sum(x['broad_tminus1_eligible'] for x in clock_rows),
    selected_raw_rows_later_than_legacy_clock=sum(x['source_was_later_than_legacy_clock'] for x in rows))
(OUT/'input_summary.json').write_text(json.dumps(summary,indent=2,default=str)+'\n')
print(json.dumps(summary,indent=2,default=str))

# Independently reconstruct every declared first-stage predictor before reading
# the R16 implementation. This is a reference table, not a fit or selection.
states = json.loads((ROOT/'output/research_r15/states.json').read_text())
origins = pd.period_range('2006-01', max(states), freq='M')
all_eves = b.release_eves(b.CALENDAR, pd.PeriodIndex([t-1 for t in origins],freq='M'))
calendar = pd.read_csv(ROOT/'data/release_calendar_cz_cpi.csv')
calendar.index = pd.PeriodIndex(calendar.target_month,freq='M')
pub = pd.Series({p: pd.Timestamp(calendar.loc[p,'detail_release_dt']) + pd.Timedelta(hours=9)
    if p in calendar.index else (p+1).start_time + pd.Timedelta(days=19,hours=9)
    for p in broad.index})
feature_rows = []
for t in origins:
    edge = t-1
    cutoff = pd.Timestamp(states[str(t)]['as_of']) if str(t) in states else all_eves[edge]
    assert all_eves[edge] <= cutoff
    def snap(n,lag=0):
        return float(panel[f'a6_{n:02}'].get(edge-lag,np.nan))
    def growth(n,lag):
        a,bv=snap(n),snap(n,lag)
        return float(100*np.log(a/bv)) if np.isfinite(a) and np.isfinite(bv) and min(a,bv)>0 else np.nan
    def mean3(n):
        values=[snap(n,k) for k in range(3)]
        return float(np.mean(values)) if np.isfinite(values).all() else np.nan
    fxvalues=fx.reindex(pd.period_range(edge-2,edge,freq='M'))
    fx3=float(np.sum(100*np.log1p(fxvalues/100))) if np.isfinite(fxvalues).all() and (fxvalues>-100).all() else np.nan
    for group in ['services','goods']:
        z=[]
        for p in [edge,edge-3,edge-12]:
            value=broad[group].get(p,np.nan)
            z.append(100*np.log1p(value/100) if pd.notna(pub.get(p,pd.NaT)) and pub[p]<=cutoff and np.isfinite(value) and value>-100 else np.nan)
        row=dict(origin=str(t),group=group,clock=str(cutoff),panel_clock=str(all_eves[edge]),
            z=z[0],z_change3=z[0]-z[1],z_change12=z[0]-z[2])
        if group=='services':
            row.update(unemployment_change3=snap(11)-snap(11,3),ulc_growth12=growth(17,12),ip_growth3=growth(12,3))
        else:
            row.update(cost_26_mean3=mean3(26),cost_45_mean3=mean3(45),cost_47_mean3=mean3(47),fx3=fx3,cost_62_mean3=mean3(62))
        feature_rows.append(row)
pd.DataFrame(feature_rows).to_csv(OUT/'first_stage_predictor_reference.csv',index=False)
print('Independent first-stage predictor rows:',len(feature_rows))
