"""Validate/rebase already-frozen food pipeline source levels; no fits or scores."""
from pathlib import Path
import hashlib
import json
import sys

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from core_split_experiment import publication_dates
from data.struct_inputs import AGRI_BASKET

OUT=ROOT/'data/research_r14/food'
FILES=('tests/fixtures/cleanup/component_food_fuel_mm.csv','data/cz_agri_prices_raw.csv',
       'data/cz_ppi_product_raw.csv','data/release_calendar_cz_cpi.csv')
PRODUCTS=[AGRI_BASKET[i] for i in (0,1,3,4)]


def prepare():
    food=pd.read_csv(ROOT/FILES[0],index_col=0,float_precision='round_trip').food
    food.index=pd.PeriodIndex(food.index,freq='M')
    food=food.reindex(pd.period_range('2015-01',food.last_valid_index(),freq='M'))
    # January is an arbitrary level anchor; only February onward needs m/m.
    if food.index[0]!=pd.Period('2015-01','M') or not np.isfinite(food.iloc[1:]).all():
        raise ValueError('Food needs January anchor and complete February-onward rates')
    if not food.index.equals(pd.period_range(food.index[0],food.index[-1],freq='M')):
        raise ValueError('Food monthly history must be contiguous')
    raw=pd.read_csv(ROOT/FILES[1])
    raw=raw[raw.CASMKMQR.astype(str).str.fullmatch(r'\d{4}-\d{2}') & raw['UZ02HU.KRAJ'].isna()
            & raw.Reprezentant.isin(PRODUCTS)]
    if raw.duplicated(['CASMKMQR','Reprezentant']).any():
        raise ValueError('Ambiguous national farm-price row')
    agri=raw.pivot(index='CASMKMQR',columns='Reprezentant',values='Hodnota')
    agri.index=pd.PeriodIndex(agri.index,freq='M')
    agri=agri.reindex(food.index)[PRODUCTS]
    raw=pd.read_csv(ROOT/FILES[2],low_memory=False)
    selected=raw[(raw['CZCPA3.CZCPA_U2'].astype(str).str.replace('.0','',regex=False)=='10')
        & raw['CZCPA3.CZCPA_U3'].isna() & raw.TYPUDAJE5A.eq('IZ2015')
        & raw.CASMKMQRM12.astype(str).str.fullmatch(r'\d{4}-\d{2}')]
    if selected.CASMKMQRM12.duplicated().any():
        raise ValueError('Ambiguous national food PPI row')
    ppi=pd.Series(selected.Hodnota.to_numpy(dtype=float),index=pd.PeriodIndex(selected.CASMKMQRM12,freq='M')).reindex(food.index)
    if not np.isfinite(agri.to_numpy()).all() or not np.isfinite(ppi).all() or (agri<=0).any().any() or (ppi<=0).any():
        raise ValueError('Complete positive source levels required')
    if (food<=-100).any():
        raise ValueError('Food gross rates must be positive')
    q=100*np.log1p(food/100); q.iloc[0]=0.
    panel=pd.DataFrame({'agri4':(100*np.log(agri/agri.iloc[0])).mean(axis=1),
                        'food_ppi':100*np.log(ppi/ppi.iloc[0]),'food':q.cumsum()},index=food.index)
    reconstructed=100*np.expm1(panel.food.diff()/100)
    delta=float((reconstructed.iloc[1:]-food.iloc[1:]).abs().max())
    if delta>1e-12:
        raise AssertionError('Food level reconstruction changed original m/m rates')
    exceptions={1:9,3:4,4:4,6:1,12:1}
    available=pd.DataFrame(index=panel.index)
    available['agri4']=[((m+1).to_timestamp()+pd.Timedelta(days=25)).tz_localize('Europe/Prague').isoformat() for m in panel.index]
    available['food_ppi']=[((m+1).to_timestamp()+pd.Timedelta(days=15+exceptions.get(m.month,0))).tz_localize('Europe/Prague').isoformat() for m in panel.index]
    dates=publication_dates(panel.index)
    available['food']=[d.tz_localize('Europe/Prague').isoformat() if pd.notna(d) else None for d in dates]
    OUT.mkdir(parents=True,exist_ok=True)
    panel.to_csv(OUT/'pipeline_log_levels.csv',index_label='period')
    available.to_csv(OUT/'pipeline_available_from.csv',index_label='period')
    agri.to_csv(OUT/'agri4_physical_prices.csv',index_label='period')
    manifest=dict(inputs={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES},
        outputs={f:hashlib.sha256((OUT/f).read_bytes()).hexdigest() for f in
                 ('pipeline_log_levels.csv','pipeline_available_from.csv','agri4_physical_prices.csv')},
        first=str(panel.index[0]),last=str(panel.index[-1]),months=len(panel),agri_products=PRODUCTS,
        food_reconstruction_max_abs_difference=delta,
        units='100 log-level points, each series normalized to zero in January 2015',
        vintage='Latest stored raw histories with reconstructed availability, no model fits')
    (OUT/'input_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if k not in ('inputs','outputs','agri_products')},indent=2))


if __name__=='__main__':
    prepare()
