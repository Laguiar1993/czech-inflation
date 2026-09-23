"""Shared R20 entry into the unchanged FAST/local-core/gentle-slope recipes.

Changing observations are explicit arguments. Existing package functions still
read the release, basket and announcement policies, which the runner snapshots.
No stored forecast, survey, CNB path or realised future target is read here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MODELS=('STATE_FAST_R15','STABLE_LOCAL_CORE_R14B','DAMPED_P95_Q001_R16')
LABELS=dict(zip(MODELS,('FAST core trend','Current core trend','Gentle core slope')))
BLOCKS=('core','food','administered','alcohol_tobacco','fuel','wedge')


def aware_clock(value):
    clock=pd.Timestamp(value)
    if pd.isna(clock) or clock.tzinfo is None:
        raise ValueError('A valid timezone-aware decision clock is required')
    return clock.tz_convert('Europe/Prague')


def constant_pump_path(pump,origin,as_of,petrol_share):
    """Frozen R14 constant-gross-price control, without fitting its unused ECM.

    Average weekly levels by month, then blend each product's relative change.
    Availability remains the declared observation Monday plus seven days.
    """
    from models.fuel_path_r14 import monthly_rates
    t=pd.Period(origin,'M');clock=aware_clock(as_of).tz_localize(None)
    if not isinstance(pump.index,pd.DatetimeIndex) or not pump.index.is_unique or not pump.index.is_monotonic_increasing:
        raise ValueError('Pump requires unique ordered datetime keys')
    if not 0<=petrol_share<=1 or pump.empty or (pump.index.dayofweek!=0).any():
        raise ValueError('Pump requires Monday observations and a valid petrol share')
    gross=['gross_petrol95','gross_diesel']
    required=gross+[c for c in ('net_petrol95','net_diesel') if c in pump]
    known=pump.loc[pump.index+pd.Timedelta(days=7)<=clock].dropna(subset=required)
    if known.empty or not np.isfinite(known[gross]).all().all() or (known[gross]<=0).any().any():
        raise ValueError('No valid released pump prices')
    grid=pd.date_range(pump.index.min(),(t+12).end_time.normalize(),freq='W-MON')
    values=known[gross].rename(columns=dict(zip(gross,('petrol95','diesel')))).reindex(grid).ffill()
    rates=monthly_rates(values,t,petrol_share)
    if not np.isfinite(rates).all():raise ValueError('Incomplete constant pump horizon')
    last=known.index[-1];due=pd.date_range(pump.index.min(),clock-pd.Timedelta(days=7),freq='W-MON')[-1]
    return dict(zip(range(1,13),map(float,rates))),dict(observation_end=str(last),
        available_from=str(last+pd.Timedelta(days=7)),latest_due=str(due),stale=last<due,
        aggregation='monthly mean per product, then weighted relative changes',petrol_share=float(petrol_share))


def core_paths(core,features,available,origin,as_of):
    from models.core_trend_residual_r15 import state_at
    from models.core_learning_r14 import origin_state
    from models.core_slope_transmission_r16 import slope_state
    t=pd.Period(origin,'M');clock=aware_clock(as_of).tz_localize(None)
    reference=state_at(core,available,t,clock)
    if reference is None:raise ValueError('Insufficient, missing or unreleased core history through origin-1')
    local=origin_state(core,features,available,t,clock)
    history=core.loc[(core.index<t)&(core.index>=t-reference['n_history'])]
    q=100*np.log1p(history/100)
    adjusted=q-np.array([reference['seasonal'][m.month] for m in q.index])
    slope=slope_state(adjusted,t,reference['seasonal'])
    if slope is None:raise ValueError('Core slope history unavailable')
    paths={MODELS[0]:{h:float(100*np.expm1(v/100)) for h,v in reference['forecasts_log']['fast'].items()},
           MODELS[1]:{h:float(100*np.expm1((local['trend']+local['seasonal'][(t+h).month])/100)) if local else np.nan for h in range(1,13)},
           MODELS[2]:{h:float(100*np.expm1(v/100)) for h,v in slope['forecasts_log']['p95_q001'].items()}}
    return paths,dict(fast_state=reference,local_state=local,slope_state=slope,
        local_status='estimated' if local else 'unavailable_required_core_or_import_fx_history')


def forecast_current_path(frames,food_levels,food_available,pump,origin,as_of,h0,h0_contributions=None):
    """Calculate three h0–h12 monthly/YoY paths from one information set."""
    import cz_struct as s
    from core_split_experiment import publication_dates
    from independent_bridge_experiment import _monthly_frame, future_weights
    from models.food_stable_r14b import forecast_origin as food_forecast
    from models.path_inputs import compound_path
    t=pd.Period(origin,'M');aware=aware_clock(as_of);clock=aware.tz_localize(None)
    if isinstance(h0,bool) or not np.isfinite(h0) or h0<=-100:
        raise ValueError('A finite independent h0 with positive gross rate is required')
    if h0_contributions is not None:
        if set(h0_contributions)!=set(BLOCKS) or not np.isfinite(list(h0_contributions.values())).all():
            raise ValueError('Invalid h0 contribution schema')
        if not np.isclose(sum(h0_contributions.values()),h0,atol=1e-10,rtol=0):
            raise ValueError('h0 contribution sum differs from independent point')

    def released(name):
        values=_monthly_frame(frames[name],name,t-1)
        return values.loc[s._released_index(values.index,clock)]

    y=released('headline').iloc[:,0];components=released('components')
    core=released('core').iloc[:,0].rename('core');reg=released('regulated').iloc[:,0].rename('reg')
    alcohol=released('alcohol').iloc[:,0]
    features=_monthly_frame(frames['features'],'features',t)
    cp,core_diag=core_paths(core,features,publication_dates(core.index),t,aware)
    food=food_forecast(food_levels,food_available,t,aware)
    fp=food['paths']['FOOD_STABLE_PIPELINE_R14B']
    fuel,fuel_diag=constant_pump_path(pump,t,aware,s._petrol_share(t,clock))
    weights=s.solve_weights(y,components,core,reg,t-1,as_of=clock,alc=alcohol)
    current=weights[s._regime(t)]
    support=pd.concat([y,components[['food','fuel']],alcohol,core,reg],axis=1).dropna().iloc[:,0]
    wedge=s._weighted_wedge(y,components,alcohol,core,reg,support,weights,as_of=clock)
    # Annual base effects use the released headline history only. h0 is always
    # the supplied independent forecast, including when actual t is in frames.
    annual_frame=frames.get('path_headline',frames['headline'])
    history=annual_frame.iloc[:,0].loc[annual_frame.index<t]
    history=history.loc[s._released_index(history.index,clock)]
    common={}
    for h in range(1,13):
        month=t+h;w=future_weights(weights,current,month,clock)
        values=dict(food=fp[h],fuel=fuel[h],
            administered=s.admin_forecast(reg,month,known_through=t-1,as_of=clock,announce_mode='documented',w_adm=w['administered']),
            alcohol_tobacco=s.alc_forecast(alcohol,month,t-1,as_of=clock),
            wedge=s._wedge_at(wedge,month,t-1))
        common[h]=(w,values)
    rows=[]
    for model in MODELS:
        path={0:float(h0)};native=[]
        for h in range(13):
            row=dict(origin=str(t),h=h,target=str(t+h),as_of_utc=aware.tz_convert('UTC').isoformat(),model=model)
            if h==0:
                row.update(mm_forecast=float(h0),**{'contribution_'+k:float(v) for k,v in (h0_contributions or {}).items()})
            else:
                w,other=common[h];values={'core':cp[model][h],**other}
                contributions={b:float(values[b] if b=='wedge' else w['alc' if b=='alcohol_tobacco' else b]*values[b]) for b in BLOCKS}
                path[h]=sum(contributions.values())
                row.update(mm_forecast=path[h],**{'contribution_'+b:v for b,v in contributions.items()},
                    **{'value_'+b:float(v) for b,v in values.items()},**{'weight_'+b:float(v) for b,v in w.items()})
            native.append(row)
        for row in native:
            row['yy_exante']=compound_path(history,path,t,row['h'],h0)
            row['status']='estimated' if np.isfinite(row['mm_forecast']) and np.isfinite(row['yy_exante']) else 'unavailable_component'
        rows.extend(native)
    table=pd.DataFrame(rows)
    return dict(monthly=table,diagnostics=dict(core=core_diag,food=food,fuel=fuel_diag,
        model_ids=MODELS,model_labels=LABELS,h0_model='HARD_BASE',
        all_paths_finite=bool(np.isfinite(table[['mm_forecast','yy_exante']]).all().all()),
        core_history_end=str(core.index[-1]),headline_history_end=str(history.index[-1]),
        availability='Recorded inputs with inherited publication rules; not original statistical vintages',
        future_weights='Current unless next basket regime was published by decision',
        source_refresh_certified=False))
