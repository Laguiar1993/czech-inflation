"""Offline preparation of frozen primary R14 fuel sources; no model fitting."""
from pathlib import Path
import hashlib
import json
from datetime import datetime,timezone

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/research_r14/fuel'


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def local_price(eur_per_1000,eur_per_czk):
    if np.any(np.asarray(eur_per_czk)<=0): raise ValueError('exchange rate must be positive')
    return eur_per_1000/eur_per_czk/1000


def tax_schedule(book,sheet):
    frame=pd.read_excel(book,sheet_name=sheet,header=None)
    frame[0]=frame[0].ffill()
    frame=frame[frame[0]=='CZ_'].copy()
    frame.index=pd.to_datetime(frame[1])
    out=frame[[2,3]].apply(pd.to_numeric,errors='coerce').sort_index().ffill()
    out.columns=['petrol95','diesel']
    return out/(100 if sheet=='VAT' else 1000)


def prepare():
    raw=DATA/'raw'; book=raw/'ec_weekly_oil_history.xlsx'; pump=pd.DataFrame()
    for kind,sheet,prefix in [('gross','Prices with taxes','with_tax'),('net','Prices wo taxes','wo_tax')]:
        frame=pd.read_excel(book,sheet_name=sheet,header=0)
        valid=frame.iloc[:,0].map(lambda v:hasattr(v,'year'))
        frame=frame.loc[valid].copy(); frame.index=pd.to_datetime(frame.iloc[:,0])
        rate=pd.to_numeric(frame.CZ_exchange_rate,errors='coerce')
        for product,key in [('petrol95','euro95'),('diesel','diesel')]:
            pump[f'{kind}_{product}']=local_price(pd.to_numeric(frame[f'CZ_price_{prefix}_{key}'],errors='coerce'),rate)
    pump=pump.sort_index(); pump.index.name='date'
    for kind,sheet in [('vat','VAT'),('excise','Excise duties')]:
        schedule=tax_schedule(book,sheet)
        schedule.to_csv(DATA/f'{kind}_schedule.csv',index_label='effective_date')
        for product in ('petrol95','diesel'):
            pump[f'{kind}_{product}']=schedule[product].reindex(schedule.index.union(pump.index)).sort_index().ffill().reindex(pump.index)
    pump.to_csv(DATA/'pump_weekly.csv')
    taxes=[]
    for p in ('petrol95','diesel'):
        reconstructed=(pump['net_'+p]+pump['excise_'+p])*(1+pump['vat_'+p])
        taxes.append(pd.DataFrame(dict(date=pump.index,product=p,actual_gross=pump['gross_'+p].to_numpy(),
            reconstructed_gross=reconstructed.to_numpy(),difference=(reconstructed-pump['gross_'+p]).to_numpy())))
    pd.concat(taxes).to_csv(DATA/'tax_identity_audit.csv',index=False)
    oil=pd.read_excel(raw/'eia_brent_daily.xls',sheet_name='Data 1',header=2)
    oil=oil.iloc[:,:2]; oil.columns=['date','brent_usd']; oil.date=pd.to_datetime(oil.date)
    oil=oil.set_index('date').sort_index(); oil.to_csv(DATA/'brent_daily.csv')
    fxrows=[]
    for file in sorted(raw.glob('cnb_fx_*.txt')):
        columns=None
        for line in file.read_text(encoding='utf-8-sig').splitlines():
            values=line.split('|')
            if values[0]=='Date': columns=values; continue
            if len(values)<3: continue
            row=dict(zip(columns,values)); fxrows.append(dict(date=pd.to_datetime(row['Date'],format='%d.%m.%Y'),
                usdczk=float(row['1 USD']),eurczk=float(row['1 EUR'])))
    fx=pd.DataFrame(fxrows).set_index('date').sort_index()
    if not fx.index.is_unique: raise ValueError('duplicate CNB daily FX')
    fx.to_csv(DATA/'fx_daily.csv')
    old=pd.read_csv(ROOT/'tests/fixtures/cleanup/fuel_weekly.csv',index_col=0,parse_dates=True)
    overlap=pump[['gross_petrol95','gross_diesel']].join(old[['petrol95','diesel']]).dropna()
    overlap['petrol95_difference']=overlap.gross_petrol95-overlap.petrol95
    overlap['diesel_difference']=overlap.gross_diesel-overlap.diesel
    overlap.to_csv(DATA/'fixture_overlap_audit.csv')
    urls={
        'ec_weekly_oil_history.xlsx':'https://energy.ec.europa.eu/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx',
        'eia_brent_daily.xls':'https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls',
        'ec_czech_methodology.pdf':'https://energy.ec.europa.eu/document/download/2b6efb04-9c48-4ef5-a5b1-c2e8183d3c08_en?filename=CZECHIA+2022.pdf'}
    records={}
    for p in sorted(raw.iterdir()):
        url=urls.get(p.name)
        if p.name.startswith('cnb_fx_'):
            url='https://www.cnb.cz/en/financial-markets/foreign-exchange-market/central-bank-exchange-rate-fixing/central-bank-exchange-rate-fixing/year.txt?year='+p.stem[-4:]
        records[p.relative_to(DATA).as_posix()]=dict(sha256=sha(p),bytes=p.stat().st_size,url=url,
            retrieval_completed_utc=datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat())
    manifest=dict(raw_sources=records,prepared={p.name:sha(p) for p in sorted(DATA.glob('*.csv'))},
        parser_sha256=sha(__file__),vintage='Latest retrieved histories; reconstructed availability, no archived vintages.',
        pump_lag_days=7,oil_lag_days=14,fx_prague_time='14:30',
        pump_units='CZK/litre; source EUR/1000litres divided by source EUR/CZK and1000',
        oil_units='USD/barrel',fx_units='CZK per one USD or EUR',
        pump_start=str(pump.index.min().date()),pump_end=str(pump.index.max().date()),
        missing_pump_dates=[str(v.date()) for v in pump.index[pump[['gross_petrol95','gross_diesel']].isna().any(axis=1)]],
        overlap_n=len(overlap),max_overlap_difference=overlap.filter(like='_difference').abs().max().to_dict(),
        max_tax_identity_difference=float(pd.concat(taxes).difference.abs().max()))
    (DATA/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('raw_sources','prepared')},indent=2))


def load():
    manifest=json.loads((DATA/'manifest.json').read_text())
    for name,record in manifest['raw_sources'].items():
        if sha(DATA/name)!=record['sha256']: raise ValueError(f'raw fuel source changed: {name}')
    for name,expected in manifest['prepared'].items():
        if sha(DATA/name)!=expected: raise ValueError(f'prepared fuel source changed: {name}')
    return {key:pd.read_csv(DATA/file,index_col=0,parse_dates=True,float_precision='round_trip')
            for key,file in [('pump','pump_weekly.csv'),('oil','brent_daily.csv'),('fx','fx_daily.csv')]}


if __name__=='__main__': prepare()
