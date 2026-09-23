"""Fixed weekly R14 fuel ECM under origin-frozen oil, FX and observed tax state."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import lsq_linear

PRODUCTS=('petrol95','diesel')
MODELS=('FUEL_ZERO_R14','FUEL_CONSTANT_PUMP_R14','FUEL_ECM_R14')
LITRES_PER_BARREL=158.987294928


def clock_local(as_of):
    clock=pd.Timestamp(as_of)
    if pd.isna(clock): raise ValueError('valid origin clock required')
    return clock.tz_convert('Europe/Prague').tz_localize(None) if clock.tzinfo else clock


def effective_wedge(gross,net,vat):
    if not np.isfinite([gross,net,vat]).all() or gross<=0 or net<=0 or vat<0:
        raise ValueError('finite positive observed prices and nonnegative VAT required')
    return gross/(1+vat)-net


def monthly_rates(gross,origin,share,horizons=12):
    if not 0<=share<=1: raise ValueError('petrol share must be in[0,1]')
    monthly=gross.groupby(gross.index.to_period('M')).mean()
    months=pd.period_range(origin,periods=horizons+1,freq='M')
    ratios=monthly.reindex(months).pct_change(fill_method=None)*100
    return (share*ratios.petrol95+(1-share)*ratios.diesel).iloc[1:].to_numpy()


def cost_table(data,weeks,clock=None):
    """Weekly lagged-average CZK crude cost and maximum daily publication clock.

    Without clock, full input values serve historical estimation only; the caller
    gates the returned availability. With clock, all unreleased future values
    are replaced by each source's latest available observation.
    """
    oil=data['oil'].brent_usd.copy(); fx=data['fx'].usdczk.copy()
    if clock is not None:
        oil=oil[oil.index+pd.Timedelta(days=14)<=clock]
        fx=fx[fx.index+pd.Timedelta(hours=14,minutes=30)<=clock]
    if oil.empty or fx.empty: raise ValueError('no origin-observable oil/FX')
    start=min(oil.index.min(),fx.index.min(),weeks.min()-pd.Timedelta(days=14))
    days=pd.date_range(start,weeks.max(),freq='D')
    ov=oil.reindex(days).ffill(); fv=fx.reindex(days).ffill()
    od=pd.Series(oil.index,index=oil.index).reindex(days).ffill()+pd.Timedelta(days=14)
    fd=pd.Series(fx.index,index=fx.index).reindex(days).ffill()+pd.Timedelta(hours=14,minutes=30)
    available=pd.concat([od.rename('oil'),fd.rename('fx')],axis=1).max(axis=1)
    price=(ov*fv/LITRES_PER_BARREL).rolling(7,min_periods=7).mean()
    # Availability is nondecreasing after forward fill, so final day is the max.
    ends=weeks-pd.Timedelta(days=1)
    return pd.DataFrame({'cost':price.reindex(ends).to_numpy(),
                         'cost_available':available.reindex(ends).to_numpy()},index=weeks)


def project_net(weeks,cost,net0,delta_net0,cost0,delta_cost0,parameters):
    p=parameters; previous=float(net0); dprevious=float(delta_net0)
    cprevious=float(cost0); dcprevious=float(delta_cost0); values=[]
    for week in weeks:
        current=float(cost.loc[week]); change=current-cprevious
        step=(p['lam']*(p['a']+p['b']*cprevious-previous)
              +p['beta0']*change+p['beta1']*dcprevious+p['phi']*dprevious)
        previous+=step; values.append(previous)
        dprevious=step; cprevious=current; dcprevious=change
    return np.asarray(values)


def fit_product(pump,cost,product,clock):
    target=pump['net_'+product]
    joined=pd.DataFrame({'net':target,'cost':cost.cost,
        'available':pd.concat([pd.Series(pump.index+pd.Timedelta(days=7),index=pump.index),
                              cost.cost_available],axis=1).max(axis=1)})
    long=joined[(joined.available<=clock)&joined.net.notna()&joined.cost.notna()].tail(260)
    if len(long)<104: return None,[], 'insufficient_history'
    solution=lsq_linear(np.column_stack([np.ones(len(long)),long.cost]),long.net.to_numpy(),
                        bounds=([0.,0.],[np.inf,3.]),tol=1e-10,max_iter=1000)
    if not solution.success: return None,[], 'longrun_fit_failed'
    a,b=map(float,solution.x)
    design=pd.DataFrame({'gap':a+b*joined.cost.shift(1)-joined.net.shift(1),
                         'dc0':joined.cost.diff(),'dc1':joined.cost.diff().shift(1),
                         'dn1':joined.net.diff().shift(1),'target':joined.net.diff()},index=joined.index)
    # Every lag source also has to be available; preserve missing calendar weeks.
    design['available']=pd.concat([joined.available,joined.available.shift(1),joined.available.shift(2)],axis=1).max(axis=1)
    dynamic=design.loc[design.index.isin(long.index)&design.available.le(clock)].dropna()
    if len(dynamic)<104: return None,[], 'insufficient_history'
    fit=lsq_linear(dynamic[['gap','dc0','dc1','dn1']].to_numpy(),dynamic.target.to_numpy(),
                   bounds=([0.,0.,0.,0.],[1.,2.,2.,.8]),tol=1e-10,max_iter=1000)
    if not fit.success: return None,[], 'dynamic_fit_failed'
    lam,beta0,beta1,phi=map(float,fit.x)
    p=dict(product=product,a=a,b=b,lam=lam,beta0=beta0,beta1=beta1,phi=phi,
        n_longrun=len(long),n_dynamic=len(dynamic),train_start=str(dynamic.index.min().date()),
        train_end=str(dynamic.index.max().date()),last_training_available=str(dynamic.available.max()),
        longrun_boundary=bool(np.any(abs(solution.active_mask)>0)),
        dynamic_boundary=bool(np.any(abs(fit.active_mask)>0)))
    rows=[dict(product=product,week=str(idx.date()),net=float(joined.loc[idx,'net']),
        cost=float(joined.loc[idx,'cost']),available=str(row.available)) for idx,row in dynamic.iterrows()]
    return p,rows,'estimated'


def forecast(data,origin,as_of,petrol_share):
    origin=pd.Period(origin,'M'); clock=clock_local(as_of)
    for label,frame in data.items():
        if not isinstance(frame.index,pd.DatetimeIndex) or not frame.index.is_unique or not frame.index.is_monotonic_increasing:
            raise ValueError(f'{label}: unique ordered daily/weekly dates required')
    full=data['pump']; weekly=pd.date_range(full.index.min(),full.index.max(),freq='W-MON')
    full=full.reindex(weekly)
    visible=full.loc[full.index+pd.Timedelta(days=7)<=clock].dropna(subset=[f'{kind}_{p}' for p in PRODUCTS for kind in ('net','gross')])
    if visible.empty: raise ValueError('no released pump observations')
    last=visible.index[-1]
    end=(origin+12).end_time.normalize()
    grid=pd.date_range(full.index.min(),end,freq='W-MON')
    future=grid[grid>last]
    old=visible[[f'gross_{p}' for p in PRODUCTS]].copy(); old.columns=PRODUCTS
    constant=old.reindex(grid).ffill()
    zero=np.zeros(12); control=monthly_rates(constant,origin,petrol_share)
    oil_visible=data['oil'][data['oil'].index+pd.Timedelta(days=14)<=clock]
    fx_visible=data['fx'][data['fx'].index+pd.Timedelta(hours=14,minutes=30)<=clock]
    audit=dict(status='estimated',fallback_used=False,petrol_share=float(petrol_share),
        pump_observation_end=str(last),pump_available_end=str(last+pd.Timedelta(days=7)),
        oil_observation_end=str(oil_visible.index.max()),oil_available_end=str(oil_visible.index.max()+pd.Timedelta(days=14)),
        fx_observation_end=str(fx_visible.index.max()),fx_available_end=str(fx_visible.index.max()+pd.Timedelta(hours=14,minutes=30)),
        oil_scenario=float(oil_visible.brent_usd.iloc[-1]),fx_scenario=float(fx_visible.usdczk.iloc[-1]))
    historical_cost=cost_table(data,weekly)
    scenario_cost=cost_table(data,grid,clock)
    predicted=constant.copy(); parameters=[]; fitrows=[]
    for product in PRODUCTS:
        p,rows,status=fit_product(full,historical_cost,product,clock)
        if p is None:
            audit.update(status=status,fallback_used=True); break
        parameters.append(p); fitrows.extend(rows)
        previous=last-pd.Timedelta(days=7)
        net0=float(visible.loc[last,'net_'+product])
        dn0=float(net0-full.loc[previous,'net_'+product]) if previous in full.index and pd.notna(full.loc[previous,'net_'+product]) else 0.
        c0=float(scenario_cost.loc[last,'cost'])
        dc0=c0-float(scenario_cost.loc[previous,'cost'])
        projection=project_net(future,scenario_cost.cost,net0,dn0,c0,dc0,p)
        vat=float(visible.loc[last,'vat_'+product])
        tax=effective_wedge(float(visible.loc[last,'gross_'+product]),net0,vat)
        gross=(projection+tax)*(1+vat)
        if not np.isfinite(gross).all() or not (projection>0).all() or not (gross>0).all():
            audit.update(status='nonpositive_projection',fallback_used=True); break
        predicted.loc[future,product]=gross
        audit['effective_tax_reconciliation_'+product]=tax; audit['vat_'+product]=vat
        audit['statutory_excise_'+product]=float(visible.loc[last,'excise_'+product])
    candidate=control.copy() if audit['fallback_used'] else monthly_rates(predicted,origin,petrol_share)
    if not np.isfinite(candidate).all(): raise ValueError('nonfinite forward monthly fuel path')
    paths=pd.concat([constant.assign(method='FUEL_CONSTANT_PUMP_R14'),
                     (constant if audit['fallback_used'] else predicted).assign(method='FUEL_ECM_R14')])
    paths=paths.loc[paths.index.to_period('M')>=origin].reset_index(names='week')
    return dict(forecasts=dict(zip(MODELS,[zero,control,candidate])),audit=audit,
                parameters=parameters,fit_rows=pd.DataFrame(fitrows),weekly_paths=paths)
