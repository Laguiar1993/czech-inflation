"""Offline annual-index fuel conditioning and fail-closed household bill scenarios."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import r17_common as c
from models import energy_path_r17 as e
from models.energy_ledger import Bill, paid_bill
from tools.r14_fuel.prepare import load

ROOT=c.ROOT
SNAP='data/market_snapshots/20260911_bloomberg_full_refresh'


def sources():
    hashes=c.preserved_hashes()
    # Check the saved parameter/price evidence and original numerical engine.
    m=json.loads((ROOT/'output/research_r14/fuel/manifest.json').read_text())
    for name,digest in m['inputs'].items():
        if name.startswith('data/research_r14/fuel/') or name in ('models/fuel_path_r14.py','tools/r14_fuel/prepare.py'):
            if c.sha(ROOT/name)!=digest:raise ValueError('Fuel source drift '+name)
            hashes[name]=digest
    for name,digest in m['outputs'].items():
        p='output/research_r14/fuel/'+name
        if c.sha(ROOT/p)!=digest:raise ValueError('Fuel output drift '+name)
        hashes[p]=digest
    m=json.loads((ROOT/SNAP/'MANIFEST.json').read_text())
    for name,digest in m['sha256'].items():
        p=SNAP+'/'+name
        if c.sha(ROOT/p)!=digest:raise ValueError('Market snapshot drift '+name)
        hashes[p]=digest
    names=['models/energy_path_r17.py','energy_path_experiment_r17.py','r17_common.py','models/energy_ledger.py',
           'docs/implementation/R17_ENERGY_SPEC_2026-09-14.md','work/research_r17_policy/candidate_policy_events.csv',
           'work/research_r17_policy/source_register.csv','work/research_r17_policy/scenario_assumptions.csv']
    hashes.update({p:c.sha(ROOT/p) for p in names})
    return hashes


def policy_scenarios(origins,clocks):
    facts=c.read('work/research_r17_policy/candidate_policy_events.csv');ledger=[];vat=[]
    for origin in origins:
        clock=pd.Timestamp(clocks[origin]);clock=clock.tz_convert('UTC')
        for row in facts.to_dict('records'):
            legal=pd.Timestamp(row['policy_available_from']);treat=pd.to_datetime(row['cpi_application_available_from'],utc=True)
            known=bool(pd.notna(treat) and treat<=clock and legal<=clock)
            eligible,reason=e.national_eligibility(known,False,False)
            ledger.append(dict(origin=origin,event_id=row['event_id'],as_of=clock.isoformat(),
                legal_known=legal<=clock,treatment_known=known,national_candidate_eligible=eligible,reason=reason,
                event_effective_from=row['effective_from'],h_effective=pd.Period(row['effective_from'],'M').ordinal-pd.Period(origin,'M').ordinal))
        bill=Bill('vat_factor_only','electricity',1.,100.,20.,5.,10.,.21,
                  ('commodity','distribution','fixed','levy'),'Scale-free VAT factor; no CPI bill exposure implied')
        t=pd.Period(origin,'M');previous=paid_bill(bill,str(t-1),clock.to_pydatetime(),e.vat_events())
        for h in range(13):
            current=paid_bill(bill,str(t+h),clock.to_pydatetime(),e.vat_events())
            vat.append(dict(origin=origin,h=h,target=str(t+h),as_of=clock.isoformat(),bill_index=current,
                relative=current/previous,monthly_pct=100*(current/previous-1),national_candidate_eligible=False))
            previous=current
    # Fixed January2026 monetary sensitivities; NOT historical national forecasts.
    scenarios=[]
    for quantity in (1.,3.5,10.):
        levy=e.poze_charge(84.7,25,3,12,quantity,495)/quantity
        for fee in (0.,100.,200.):
            q=quantity/12
            old=Bill('illustration','electricity',q,3430.,1500.,fee,levy,.21,
                ('commodity','distribution','fixed','levy'),'Illustrative constant quantity, distribution1500, fixed fee and25Athree-phase')
            for reset in (0.,.5,1.):
                before=paid_bill(old,'2025-12',pd.Timestamp('2026-01-01T00:00Z').to_pydatetime(),())
                # The zero POZE rate affects all scenarios; supplier cut only reset share.
                after=(q*(3430.-reset*240.+1500.)+fee)*1.21
                scenarios.append(dict(event='JAN2026_ILLUSTRATION',source_quantity_known_from='2025-12-30T23:59:59Z',
                    prior_poze_assumption='2024 capacity schedule carried forward;495volume cap binds every illustrated quantity;2025tariff not certified',
                    annual_mwh=quantity,supplier_fixed_czk=fee,commodity_reset_share=reset,
                    distribution_assumption_czk_mwh=1500.,previous_bill_czk=before,current_bill_czk=after,
                    bill_change_pct=100*(after/before-1),national_candidate_eligible=False,
                    reason='Assumed exposure, quantity, distribution and fee; no national CPI weight or baseline subpath'))
    return facts,pd.DataFrame(ledger),pd.DataFrame(vat),pd.DataFrame(scenarios)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'output/research_r17_energy')
    p.add_argument('--limit-origins',type=int);args=p.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=False)
    hashes=sources();c.dump(out/'declaration.json',dict(inputs=hashes,rule='annual index interpolation scenarios, no national policy point candidate'))
    data=load();market=c.read(SNAP+'/daily.csv').set_index('observation_date');market.index=pd.to_datetime(market.index)
    audit=c.read('output/research_r14/fuel/origin_audit.csv').set_index('origin');params=c.read('output/research_r14/fuel/parameters.csv')
    baseline=c.read('output/research_r15/native_forecasts.csv').query('model == @c.FAST')
    reference=c.read('output/research_r14/fuel/native_forecasts.csv').query("model == 'FUEL_ECM_R14' and h > 0")
    origins=sorted(baseline.origin.unique());origins=origins[:args.limit_origins] if args.limit_origins else origins
    quotes=[];native=[];weekly=[];curves=[];audits=[];gas=[];parity=0.;clocks={}
    for origin in origins:
        base=baseline[baseline.origin.eq(origin)];clock=pd.Timestamp(base.as_of_utc.iloc[0]);clocks[origin]=clock
        if e.old.clock_local(clock)!=pd.Timestamp(audit.loc[origin,'as_of']):raise ValueError('Saved fuel clock mismatch')
        values={}
        for ticker in ('FSBTY1 Index','TTFGCY1 Index','TTFGDAHD BCFV Index'):
            value,meta=e.quote(market[ticker],clock);values[ticker]=value
            date=meta['observation_date'];fx_ticker='USDCZK Curncy' if ticker=='FSBTY1 Index' else 'EURCZK Curncy'
            fx=float(market.at[pd.Timestamp(date),fx_ticker]) if date else np.nan
            quotes.append(dict(origin=origin,as_of=str(clock),ticker=ticker,value=value,
                same_date_fx=fx,same_date_fx_available=bool(np.isfinite(fx) and fx>0),**meta))
        results,diag,w,curve=e.fuel_paths(data,origin,clock,float(audit.loc[origin,'petrol_share']),
            params[params.origin.eq(origin)],values['FSBTY1 Index'])
        expected=reference[reference.origin.eq(origin)].sort_values('h').value_fuel.to_numpy()
        parity=max(parity,float(np.max(abs(results['FUEL_SPOT_ECM_R17']-expected))))
        if parity>1e-10:raise ValueError('Original ECM replay drift '+str(parity))
        for model,path in results.items():
            changed=c.replace_block(base,'fuel',dict(zip(range(1,13),path)));changed['model']=model
            changed['energy_scenario_status']=diag.set_index('model').loc[model,'status'];native.append(changed)
        audits.append(diag);weekly.append(w);curves.append(curve)
        spot,annual=values['TTFGDAHD BCFV Index'],values['TTFGCY1 Index']
        for name,mult in [('GAS_SPOT',None),('GAS_ANNUAL',1.),('GAS_ANNUAL_LOW',.8),('GAS_ANNUAL_HIGH',1.2)]:
            for h in range(13):
                value=spot if mult is None else (spot*np.exp(h/12*np.log(mult*annual/spot)) if np.isfinite([spot,annual]).all() else np.nan)
                gas.append(dict(origin=origin,h=h,target=str(pd.Period(origin,'M')+h),model=name,ttf_eur_mwh=value,
                    status='commodity_scenario_only' if np.isfinite(value) else 'missing_quote',
                    mapping='assumed12monthindex_endpoint; not household tariff'))
    native=pd.concat(native,ignore_index=True);forecasts=c.compound(native);keys=['origin','h','model']
    derived=['yy_exante','cumulative_log_forecast','cumulative_log_actual']
    native=native.drop(columns=derived).merge(forecasts[keys+derived],on=keys,validate='one_to_one')
    facts,eligibility,vat,bills=policy_scenarios(origins,clocks)
    tables=dict(native_forecasts=native,forecasts=forecasts,quote_audit=pd.DataFrame(quotes),origin_audit=pd.concat(audits),
        weekly_paths=pd.concat(weekly),crude_curves=pd.concat(curves),gas_scenarios=pd.DataFrame(gas),
        policy_facts=facts,policy_eligibility=eligibility,vat_policy_factors=vat,bill_scenarios=bills)
    for name,frame in tables.items():frame.to_csv(out/(name+'.csv'),index=False)
    c.finish(out,hashes,origin_count=len(origins),models=sorted(forecasts.model.unique()),ecm_replay_max_error=parity,
        national_admin_candidate='unavailable; exposure and identifiable baseline subpath not closed',
        curve='Analyst log interpolation to annual index; exact delivery/roll mapping unverified',
        sensitivity='low/high endpoints are assumptions; never calibrated probability bands')
    print('Completed',out,'ECM parity',parity,flush=True)


if __name__=='__main__':main()
