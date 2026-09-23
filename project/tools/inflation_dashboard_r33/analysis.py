"""Dated briefing, diagnostic attribution and transparent path sensitivities."""
import json
from pathlib import Path
import math
from tools.inflation_dashboard_r32 import build as previous

month_offset = previous.month_offset
GAP_LABELS = dict(core='Core', food_alc_tobacco='Food, alcohol & tobacco',
                  fuel='Fuel', administered='Administered prices', unexplained='Unexplained residual')

def explain_gap(row):
    if not row.get('complete'):
        return dict(quarter=row['quarter'],complete=False,parts=[],summary='Component coverage is incomplete.',residual_dominant=False)
    parts=[dict(id=k,label=GAP_LABELS.get(k,k),value=float(v)) for k,v in row['parts'].items()]
    if any(not math.isfinite(p['value']) for p in parts) or abs(sum(p['value'] for p in parts)-row['gap'])>1e-8:
        raise ValueError('CNB components do not reconcile: '+row['quarter'])
    residual=next((p['value'] for p in parts if p['id']=='unexplained'),0.)
    known=[p for p in parts if p['id']!='unexplained']
    dominant=abs(residual)>=max((abs(p['value']) for p in known),default=0.)
    if dominant:
        summary='The unexplained residual is the largest individual term. The component comparison cannot fully explain the headline gap.'
    else:
        lower=sorted([p for p in known if p['value']<0],key=lambda p:p['value'])
        higher=sorted([p for p in known if p['value']>0],key=lambda p:-p['value'])
        clauses=[]
        if lower: clauses.append(lower[0]['label']+' pulls the model below the CNB')
        if higher: clauses.append(higher[0]['label'].lower()+' pushes it above')
        summary='; '.join(clauses)+'. The residual is retained separately.'
    return dict(quarter=row['quarter'],complete=True,gap=row['gap'],model=row.get('model'),cnb=row.get('cnb'),
                parts=parts,residual_dominant=dominant,summary=summary)

def scenario_path(rows,food=0.,core=0.,energy=0.):
    amounts=(food,core,energy)
    if any(not math.isfinite(v) or abs(v)>5 for v in amounts):
        raise ValueError('Scenario increments must be finite headline m/m percentage points within ±5')
    source=[r for r in rows if r.get('forecast_kind')=='rebased']
    adjustments={}
    result=[]
    for i,r in enumerate(source):
        increment=(food if i<3 else 0.)+(core if i<6 else 0.)+(energy if r['month'].endswith('-01') else 0.)
        mm=r['model_mm']
        if 1+(mm+increment)/100<=0 or 1+mm/100<=0:
            raise ValueError('Scenario price level must remain positive')
        adjustments[r['month']]=(1+(mm+increment)/100)/(1+mm/100)
        first=month_offset(r['month'],-11)
        multiplier=math.prod(f for m,f in adjustments.items() if first<=m<=r['month'])
        yy=(100+r['implied_yy_model'])*multiplier-100 if increment or multiplier!=1 else r['implied_yy_model']
        result.append(dict(month=r['month'],baseline_yy=r['implied_yy_model'],scenario_yy=yy,
                           headline_mm_increment=increment,baseline_mm=mm,scenario_mm=mm+increment))
    return result

def briefing(data,lag):
    m=data['monitor'];h=m['history']
    drivers=data['drivers'][str(lag)]
    return dict(from_month=h['months'][-1-lag],to_month=h['months'][-1],
                headline_change=h['headline'][-1]-h['headline'][-1-lag],
                core_change=h['core'][-1]-h['core'][-1-lag],
                services_change=h['services'][-1]-h['services'][-1-lag],
                goods_change=h['goods'][-1]-h['goods'][-1-lag],drivers=drivers,
                top_moves=sorted([r for r in drivers if r['id']!='residual'],key=lambda r:abs(r['value']),reverse=True)[:3])

def pressure_rows(data):
    m=data['monitor'];rows=[]
    for row in m['latest']:
        if row['block']=='rents':continue
        rows.append(dict(id=row['block'],label=row['label'],yy=row['yy'],momentum=row['momentum'],
                         change_3m=row['d3_yy'],weight=row['weight'],contribution=row['contribution']))
    for r in m['groups_latest']:
        if r['group'] not in ('actual_rent','imputed_rent'):continue
        rows.append(dict(id=r['group'],label='Actual rent' if r['group']=='actual_rent' else 'Imputed rent · owner-occupied housing',
                         yy=r['yy'],momentum=r['momentum_3m_ann'],change_3m=r['d3_yy'],
                         weight=r['weight_permille'],contribution=r['contribution']))
    if abs(sum(r['weight'] for r in rows)-1000)>1e-5:raise ValueError('Pressure rows must partition the basket')
    order=['actual_rent','imputed_rent','catering','other_services','core_goods','food','energy','vehicle_operation','alcohol_tobacco']
    return sorted(rows,key=lambda r:order.index(r['id']))

def assemble():
    data=previous.assemble()
    data['schema_version']=2
    data['briefings']={str(lag):briefing(data,lag) for lag in (1,3)}
    data['pressure_rows']=pressure_rows(data)
    data['gap_explanations']={
        clock:{r['id']:{model:[explain_gap(row) for row in rows] for model,rows in r['gaps'].items()} for r in reports}
        for clock,reports in data['replay']['reportsByClock'].items()
    }
    data['revision']=dict(status='unavailable',kind='no_comparable_runs',target=data['live']['target'],
                          delta=None,components=[],path_changes=[],
                          reason='Two validated runs for the same target month and model have not been recorded. July release changes are not forecast revisions.')
    data['scenario_baseline']=scenario_path(data['updated_path'])
    data['watch']=[
        dict(id='cpi',event='Next CPI flash & detail',frequency='Monthly',next_release=None,
             block='Headline / core / housing',watch='Whether services and rent momentum ease; whether food disinflation persists.',
             impact='Resets the starting point of every path; detail updates component histories.',evidence='Observed CPI; full detail needed'),
        dict(id='food',event='Farm prices & food PPI',frequency='Monthly',next_release=None,
             block='Food',watch='A less negative food pipeline would challenge continued disinflation.',
             impact='Updates the food nowcast features and the producer-price gap in the path.',evidence='Historical food link is relatively stable'),
        dict(id='pumps',event='Pump prices & CNB FX fixing',frequency='Weekly / daily',next_release=None,
             block='Fuel / core',watch='Pump changes feed near-term fuel; FX moves affect the core input.',
             impact='A validated same-target re-run measures the actual forecast revision.',evidence='Direct model inputs; no assumed elasticity'),
        dict(id='wages',event='Wages, retail sales & household credit',frequency='Quarterly / monthly',next_release=None,
             block='Services / domestic demand',watch='Wage and demand strength alongside recent services momentum.',
             impact='Analysis watch only; no quantified wage/demand forecast coefficient is introduced.',evidence='Evidence module pending'),
        dict(id='energy',event='January energy announcements',frequency='Annual / event-driven',next_release=None,
             block='Administered energy',watch='Regulator, supplier and government decisions, with effective and available dates.',
             impact='Update the documented announcement ledger; scenario effects are separate assumptions.',evidence='Verified announcement required')
    ]
    data['official_release']=json.loads((Path(__file__).parent/'official_release.json').read_text(encoding='utf-8'))
    data['watch'][0].update(next_release='2026-10-06',detail_release='2026-10-13',source=data['official_release']['august']['url'])
    metadata=Path(previous.ROOT)/'data/core_split/canonical_metadata.json'
    manifest=json.loads((metadata.parent/'manifest.json').read_text(encoding='utf-8'))
    if previous.digest(metadata)!=manifest['files']['canonical_metadata.json']['sha256']:
        raise ValueError('Core split definition metadata changed')
    data['broad_definitions']=json.loads(metadata.read_text(encoding='utf-8'))['broad_yoy']
    data['source_issues']=[]
    for row in data['sources']:
        if row['name']=='Headline CPI':row['status']='Saved monitor observation; latest official detail verified separately'
    data['sources'].insert(0,dict(name='Latest official release',through='2026-08',source='CZSO release published 10 Sep 2026',status='Headline, goods, services and selected detail verified separately'))
    return data
