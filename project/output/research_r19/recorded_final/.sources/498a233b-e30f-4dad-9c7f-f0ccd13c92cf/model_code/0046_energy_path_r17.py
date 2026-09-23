"""Source-gated energy scenarios; household assumptions are not national CPI."""
import math
import numpy as np
import pandas as pd
from models.energy_ledger import PolicyEvent
from models import fuel_path_r14 as old


def quote(series,clock,max_age=31):
    cutoff=old.clock_local(clock)
    if not isinstance(series.index,pd.DatetimeIndex) or not series.index.is_unique:raise ValueError('Unique daily quotes required')
    known=series.loc[(series.index+pd.Timedelta(days=1)<=cutoff)&np.isfinite(series)&series.gt(0)].sort_index()
    if known.empty:return np.nan,dict(status='missing_quote',observation_date=None,age_days=None)
    date=known.index[-1];age=(cutoff.normalize()-date).days
    return (float(known.iloc[-1]) if age<=max_age else np.nan),dict(status='available' if age<=max_age else 'stale_quote',
        observation_date=str(date.date()),available_from=str(date+pd.Timedelta(days=1)),age_days=age)


def log_curve(spot,endpoint,dates,start,end):
    if not np.isfinite([spot,endpoint]).all() or min(spot,endpoint)<=0:raise ValueError('Positive finite prices required')
    start,end=pd.Timestamp(start),pd.Timestamp(end)
    if end<=start:raise ValueError('Curve endpoint must follow origin')
    fraction=np.clip((pd.DatetimeIndex(dates)-start)/(end-start),0,1).to_numpy(float)
    return spot*np.exp(fraction*np.log(endpoint/spot))


def poze_charge(rate,breaker_a,phases,billing_months,quantity_mwh,volume_ceiling,includes_poze=False):
    values=[rate,breaker_a,phases,billing_months,quantity_mwh,volume_ceiling]
    if not np.isfinite(values).all() or min(values)<0 or phases not in (1,3) or billing_months<=0 or breaker_a<=0:
        raise ValueError('Explicit consistent positive billing-period inputs required')
    if includes_poze:raise ValueError('POZE already included in total-regulated adjustment')
    return min(rate*math.ceil(breaker_a)*phases*billing_months,quantity_mwh*volume_ceiling)


def aggregate_credit_relative(expenditure,credit):
    if expenditure is None or not np.isfinite([expenditure,credit]).all() or expenditure<=0 or not 0<=credit<expenditure:
        raise ValueError('Comparable national expenditure denominator and credit required')
    return (expenditure-credit)/expenditure


def national_eligibility(treatment_known,complete_exposure,baseline_identified):
    missing=[label for value,label in ((treatment_known,'CPI_treatment'),(complete_exposure,'national_exposure'),
              (baseline_identified,'baseline_energy_subpath')) if not value]
    return not missing, 'eligible' if not missing else 'missing:'+','.join(missing)


def vat_events():
    pub=pd.Timestamp('2021-10-20T23:59:59Z').to_pydatetime();treatment=pd.Timestamp('2021-12-10T23:59:59Z').to_pydatetime()
    result=[]
    for item in ('electricity','gas'):
        for action,month,value,unit in [('start','2021-11',0.,'fraction'),('expiry','2022-01',None,None)]:
            result.append(PolicyEvent('VAT21_'+item+'_'+action,'VAT21_'+item,action,month,item,(),
                'vat_rate',value,unit,pub,treatment,treatment,
                'https://csu.gov.cz/rychle-informace/consumer-price-indices-inflation-november-2021',
                'Sourced VAT factor only; national bill exposure not inferred'))
    return tuple(result)


def visible_rate(rows,target,clock):
    if rows.policy.nunique()!=1:raise ValueError('One tariff field required')
    dates=pd.to_datetime(rows.available_from,utc=True);treatment=pd.to_datetime(rows.treatment,utc=True)
    cutoff=pd.Timestamp(clock);cutoff=cutoff.tz_localize('UTC') if cutoff.tzinfo is None else cutoff.tz_convert('UTC')
    visible=rows.loc[rows.effective_from.le(str(target))&dates.le(cutoff)&treatment.notna()&treatment.le(cutoff)].copy()
    if visible.empty:return np.nan
    visible['gate']=pd.concat([dates,treatment],axis=1).max(axis=1).reindex(visible.index)
    if visible.duplicated(['effective_from','gate']).any():raise ValueError('Conflicting tariff revisions')
    return float(visible.sort_values(['effective_from','gate']).iloc[-1].value)


def fuel_paths(data,origin,clock,share,parameters,endpoint):
    """Saved origin ECM, with changed future oil conditioning only."""
    t=pd.Period(origin,'M');cutoff=old.clock_local(clock);full=data['pump']
    weeks=pd.date_range(full.index.min(),full.index.max(),freq='W-MON');full=full.reindex(weeks)
    cols=[f'{kind}_{p}' for p in old.PRODUCTS for kind in ('net','gross')]
    visible=full.loc[full.index+pd.Timedelta(days=7)<=cutoff].dropna(subset=cols)
    if visible.empty:raise ValueError('No eligible pump price')
    last=visible.index[-1];end=(t+12).end_time.normalize();grid=pd.date_range(full.index.min(),end,freq='W-MON')
    future=grid[grid>last];previous=last-pd.Timedelta(days=7)
    observed=visible[[f'gross_{p}' for p in old.PRODUCTS]].copy();observed.columns=old.PRODUCTS
    constant=observed.reindex(grid).ffill();basecost=old.cost_table(data,grid,cutoff)
    oil=data['oil'].brent_usd.loc[data['oil'].index+pd.Timedelta(days=14)<=cutoff]
    fx=data['fx'].usdczk.loc[data['fx'].index+pd.Timedelta(hours=14,minutes=30)<=cutoff]
    if oil.empty or fx.empty:raise ValueError('No eligible oil/FX')
    names={'FUEL_SPOT_ECM_R17':float(oil.iloc[-1]),'FUEL_ANNUAL_R17':endpoint,
           'FUEL_ANNUAL_LOW_R17':endpoint*.8,'FUEL_ANNUAL_HIGH_R17':endpoint*1.2}
    paths={};audits=[];weekly=[];curve_rows=[]
    for model,annual in names.items():
        missing=not np.isfinite(annual) or annual<=0
        if missing:annual=float(oil.iloc[-1])
        costs=basecost.copy()
        if model!='FUEL_SPOT_ECM_R17' and not missing:
            days=pd.date_range(min(oil.index.min(),fx.index.min(),grid.min()-pd.Timedelta(days=14)),end,freq='D')
            ov=oil.reindex(days).ffill();fv=fx.reindex(days).ffill()
            future_days=days>cutoff.normalize()
            ov.loc[future_days]=log_curve(float(oil.iloc[-1]),annual,days[future_days],cutoff.normalize(),end)
            dailycost=(ov*fv/old.LITRES_PER_BARREL).rolling(7,min_periods=7).mean()
            costs['cost']=dailycost.reindex(grid-pd.Timedelta(days=1)).to_numpy()
            for h in range(13):
                date=(t+h).end_time.normalize()
                curve_rows.append(dict(origin=str(t),model=model,h=h,date=str(date.date()),
                    crude_usd=float(log_curve(float(oil.iloc[-1]),annual,[date],cutoff.normalize(),end)[0]),
                    fx_scenario=float(fx.iloc[-1]),annual_index_endpoint=float(annual)))
        projected=constant.copy();status='missing_annual_quote_constant_spot' if missing else 'estimated'
        valid=len(parameters)==2 and set(parameters['product'])==set(old.PRODUCTS)
        if valid and pd.to_datetime(parameters.last_training_available).gt(cutoff).any():raise ValueError('Future fitted fuel label')
        for product in old.PRODUCTS:
            if not valid:status='original_fit_unavailable_constant_pump';break
            p=parameters[parameters['product'].eq(product)].iloc[0].to_dict()
            net0=float(visible.loc[last,'net_'+product]);oldnet=full.loc[previous,'net_'+product] if previous in full.index else np.nan
            dn0=net0-float(oldnet) if pd.notna(oldnet) else 0.
            c0=float(costs.loc[last,'cost']);dc0=c0-float(costs.loc[previous,'cost'])
            net=old.project_net(future,costs.cost,net0,dn0,c0,dc0,p)
            vat=float(visible.loc[last,'vat_'+product]);wedge=old.effective_wedge(float(visible.loc[last,'gross_'+product]),net0,vat)
            gross=(net+wedge)*(1+vat)
            if not np.isfinite(gross).all() or (net<=0).any() or (gross<=0).any():status='nonpositive_projection_constant_pump';valid=False;break
            projected.loc[future,product]=gross
        if not valid:projected=constant.copy()
        paths[model]=old.monthly_rates(projected,t,share)
        audits.append(dict(origin=str(t),model=model,status=status,pump_end=str(last),
            oil_end=str(oil.index[-1]),fx_end=str(fx.index[-1]),spot_usd=float(oil.iloc[-1]),
            endpoint_usd=float(annual),fx=float(fx.iloc[-1]),petrol_share=share,
            fallback=missing or not valid))
        weekly.append(projected.loc[projected.index.to_period('M')>=t].reset_index(names='week').assign(origin=str(t),model=model))
    return paths,pd.DataFrame(audits),pd.concat(weekly,ignore_index=True),pd.DataFrame(curve_rows)
