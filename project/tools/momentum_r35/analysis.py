"""Exact current-vintage category momentum and transparent fixed-weight accounting."""
import copy
import numpy as np
import pandas as pd

DEADBAND=.25

def blocks():
    from tools.inflation_monitor.build import BLOCKS
    b=copy.deepcopy(BLOCKS);b.pop('rents')
    b['actual_rent']=dict(label='Actual rents',short='Actual rents',groups=['actual_rent'])
    b['imputed_rent']=dict(label='Imputed rents',short='Imputed rents',groups=['imputed_rent'])
    b['core_goods'].update(label='Goods excluding food & energy',short='Goods')
    b['vehicle_operation'].update(label='Fuel & vehicle costs',short='Fuel & vehicle costs')
    b['other_services'].update(label='Other services & mixed',short='Other services & mixed')
    order=['food','core_goods','catering','other_services','actual_rent','imputed_rent','energy','vehicle_operation','alcohol_tobacco']
    return {k:b[k] for k in order}

def valid(series):
    if not isinstance(series.index,pd.PeriodIndex) or not series.index.is_unique or not series.index.is_monotonic_increasing:
        raise ValueError('Unique ordered monthly index required')
    if not series.index.equals(pd.period_range(series.index.min(),series.index.max(),freq='M')):
        raise ValueError('Monthly calendar gap')
    if not np.isfinite(series.to_numpy()).all() or (series<=0).any():raise ValueError('Positive finite index levels required')
    return series.astype(float)

def annualised(series,horizon):
    s=valid(series)
    if horizon not in (3,6,12):raise ValueError('Supported horizons: 3,6,12')
    return 100*np.expm1((12/horizon)*(np.log(s)-np.log(s.shift(horizon))))

def metrics(nsa,sa=None):
    nsa=valid(nsa)
    out=pd.DataFrame(index=nsa.index);out['yy']=annualised(nsa,12)
    if sa is not None:
        sa=valid(sa)
        if not nsa.index.equals(sa.index):raise ValueError('NSA/SA calendar mismatch')
        out['m3']=annualised(sa,3);out['m6']=annualised(sa,6)
        out['previous_m3']=out.m3.shift(3);out['acceleration']=out.m3-out.previous_m3
        out['mm_sa']=100*(sa/sa.shift(1)-1)
    else:
        for k in ['m3','m6','previous_m3','acceleration','mm_sa']:out[k]=np.nan
    return out

def checked_weights(weights,columns,total=None):
    w=pd.Series(weights,dtype=float)
    if not w.index.is_unique or set(w.index)!=set(columns) or not np.isfinite(w).all() or (w<=0).any():raise ValueError('Complete unique positive weights required')
    if total is not None and not np.isclose(w.sum(),total,atol=1e-6,rtol=0):raise ValueError('Weights do not cover the complete basket')
    return w

def geometric_index(levels,weights):
    w=checked_weights(weights,levels.columns)
    for c in levels:valid(levels[c])
    logs=np.log(levels/levels.iloc[0]);return 100*np.exp(logs.mul(w/w.sum()).sum(axis=1))

def log_drivers(sa,weights):
    w=checked_weights(weights,sa.columns,total=1000)
    for c in sa:
        if sa[c].notna().any():valid(sa[c])
    speed=400*(np.log(sa)-np.log(sa.shift(3)))
    return (speed-speed.shift(3)).mul(w/1000)

def direction(value):
    if not np.isfinite(value):return 'unavailable'
    return 'picking_up' if value>DEADBAND else 'cooling' if value<-DEADBAND else 'little_change'

def breadth(acceleration,weights):
    w=checked_weights(weights,acceleration.index,total=1000)
    result={k:float(w[[direction(acceleration[g])==k for g in w.index]].sum()/10) for k in ['picking_up','cooling','little_change','unavailable']}
    result['missing']=result.pop('unavailable');result['coverage']=100-result['missing']
    return result

def records(frame):
    f=frame.copy();f.index=f.index.astype(str);f.index.name='month'
    return f.reset_index().replace({np.nan:None}).to_dict('records')

def assemble(levels,sa,weights,metadata,diagnostics,endpoint_sa):
    w=checked_weights(weights,levels.columns,total=1000);definitions=blocks()
    assigned=[g for b in definitions.values() for g in b['groups']]
    if len(assigned)!=len(set(assigned)) or set(assigned)!=set(levels):raise ValueError('Categories must partition observed groups')
    if not levels.index.equals(sa.index) or set(sa)!=set(levels):raise ValueError('Adjusted panel alignment required')
    md=metadata.set_index('column');last=levels.index[-1];histories={};latest=[];groups={};group_acc={}
    contributions=log_drivers(sa,w)
    for g in levels:
        present=sa[g].notna().all();m=metrics(levels[g],sa[g] if present else None);group_acc[g]=m.acceleration.iloc[-1]
        flags=list(diagnostics[g].get('quality_flags',[]))
        endpoint=None
        if present and g in endpoint_sa and endpoint_sa[g].notna().all():
            cut=endpoint_sa[g];endpoint=float(annualised(sa[g],3).loc[cut.index[-1]]-annualised(cut,3).iloc[-1])
            if abs(endpoint)>.5:flags.append('Endpoint-sensitive')
        elif present:flags.append('Endpoint check unavailable')
        hist=records(m.tail(36));histories[g]=hist
        groups[g]=dict(id=g,label=g.replace('_',' ').capitalize(),label_cs=str(md.loc[g,'label_cs']),weight=float(w[g]),history=hist,quality_flags=sorted(set(flags)),endpoint_revision_pp=endpoint,method=diagnostics[g].get('method','X-13'),scope_note=str(md.loc[g,'scope_note']))
    for bid,b in definitions.items():
        names=b['groups'];ww=w[names];nsa=geometric_index(levels[names],ww)
        present=sa[names].notna().all().all();adjusted=geometric_index(sa[names],ww) if present else None
        m=metrics(nsa,adjusted);m['contribution_log_pp']=contributions[names].sum(axis=1,min_count=len(names))
        hist=records(m.tail(36));histories[bid]=hist
        raw_flags={f for g in names for f in groups[g]['quality_flags']}
        aliases={'Endpoint-sensitive':'component_endpoint_sensitive','identifiable_seasonality_not_detected':'component_weak_seasonality','x13_warning':'component_model_warning'}
        flags=sorted({aliases.get(f,'component_residual_seasonality' if f.startswith('residual_seasonality_') else f) for f in raw_flags}) if len(names)>1 else sorted(raw_flags)
        end_revision=None
        if present and all(g in endpoint_sa for g in names):
            cut=pd.concat({g:endpoint_sa[g] for g in names},axis=1)
            if cut.notna().all().all():
                old=geometric_index(cut,ww);end_revision=float(annualised(adjusted,3).loc[old.index[-1]]-annualised(old,3).iloc[-1])
                if abs(end_revision)>.5:flags=sorted(set(flags+['Endpoint-sensitive']))
        row=dict(id=bid,label=b['label'],short=b['short'],weight=float(ww.sum()),children=names,quality_flags=flags,endpoint_revision_pp=end_revision,**hist[-1])
        row['direction']=direction(m.acceleration.iloc[-1]);latest.append(row)
    coverage=breadth(pd.Series(group_acc),w)
    basket=None
    if sa.notna().all().all():
        index=geometric_index(sa,w);m=metrics(geometric_index(levels,w),index);basket=records(m.tail(36))
        expected=400*(np.log(index)-np.log(index.shift(3)));expected=expected-expected.shift(3)
        if not np.allclose(contributions.sum(axis=1,min_count=len(w)).dropna(),expected.dropna(),atol=1e-8,rtol=0):raise ValueError('Weighted driver accounting does not reconcile')
    drivers=[dict(id=r['id'],label=r['label'],value=r['contribution_log_pp']) for r in latest if r['contribution_log_pp'] is not None]
    driver_ids={r['id'] for r in drivers};driver_coverage=sum(r['weight']/10 for r in latest if r['id'] in driver_ids)
    driver_complete=len(drivers)==len(latest);partial=sum(r['value'] for r in drivers)
    return dict(month=str(last),rows=latest,groups=groups,histories=histories,basket=basket,breadth=coverage,
        drivers=drivers,driver_total_log_pp=partial if driver_complete else None,driver_partial_log_pp=partial,driver_complete=driver_complete,driver_coverage=driver_coverage,
        heatmap_months=[str(m) for m in levels.index[-12:]],deadband_pp=DEADBAND,
        definitions=dict(m3='100*((SA(t)/SA(t-3))**4-1)',m6='100*((SA(t)/SA(t-6))**2-1)',
            acceleration='M3(t)-M3(t-3); adjacent non-overlapping three-month windows',
            aggregation='Fixed 2026 basket weights; weighted geometric index levels, normalized to 100 in Jan 2015',
            drivers='Additive annualised log percentage-point contributions to the change in the analytical basket pace',
            history='Current-vintage X-13 estimates; revised history, not archived real-time signals',
            direction='Descriptive change outside +/-0.25 pp, not a significance test'))
