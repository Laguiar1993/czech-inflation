"""Explicit, create-only current inputs around the unchanged R31C transforms."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,io,json,urllib.request
import numpy as np
import pandas as pd
from tools.live_bundle_r32 import adapter
from tools.forecast_updates_r33 import current_bundle as current,workflow as w
ROOT=Path(__file__).resolve().parents[1]
FARM_URL='https://data.csu.gov.cz/opendata/sady/CEN0203B/distribuce/csv'

def now():return datetime.now(timezone.utc).isoformat()
def sha(data):return hashlib.sha256(data).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def capture_farm(output):
    output=Path(output).resolve()
    if output.exists():raise FileExistsError(str(output))
    start=now();request=urllib.request.Request(FARM_URL,headers={'User-Agent':'Czech-inflation-portable/1.0'})
    with urllib.request.urlopen(request,timeout=120) as response:
        raw=response.read();headers=dict(response.headers.items());url=response.url
    end=now();farm_series(raw) # reject wrong schema before creating the archive
    output.mkdir(parents=True);(output/'.gitattributes').write_bytes(b'* -text\n')
    path=output/'CEN0203B.csv';path.write_bytes(raw)
    meta={'source':FARM_URL,'final_url':url,'sha256':sha(raw),'retrieved_at':start,'completed_at':end,'response_headers':headers}
    write(Path(str(path)+'.metadata.json'),meta)
    write(output/'MANIFEST.json',{'files':{p.name:sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    return {'raw':str(path),'completed_at':end,'bytes':len(raw)}

def farm_series(raw):
    from data.struct_inputs import AGRI_BASKET
    data=pd.read_csv(io.BytesIO(raw))
    needed={'CASMKMQR','UZ02HU.KRAJ','Reprezentant','Hodnota'}
    if not needed<=set(data):raise ValueError('farm source schema changed')
    rows=data[data.CASMKMQR.astype(str).str.fullmatch(r'\d{4}-\d{2}') & data['UZ02HU.KRAJ'].isna() & data.Reprezentant.isin(AGRI_BASKET)].copy()
    if rows.duplicated(['CASMKMQR','Reprezentant']).any():raise ValueError('duplicate national farm observation')
    if rows.empty or not np.isfinite(rows.Hodnota).all() or (rows.Hodnota<=0).any():raise ValueError('positive finite national farm prices required')
    rows['p']=pd.PeriodIndex(rows.CASMKMQR,freq='M')
    pivot=rows.pivot_table(index='p',columns='Reprezentant',values='Hodnota').sort_index()
    if set(pivot)!=set(AGRI_BASKET):raise ValueError('seven farm product histories required')
    if not pivot.index.equals(pd.period_range(pivot.index[0],pivot.index[-1],freq='M')):raise ValueError('farm monthly calendar has gaps')
    return (100*np.log(pivot).diff()).mean(axis=1,skipna=True).shift(1,freq='M').rename('agri_price_mm')

def load_farm(path,as_of):
    path=Path(path).resolve();raw=path.read_bytes();meta_path=Path(str(path)+'.metadata.json');meta=json.loads(meta_path.read_bytes())
    if sha(raw)!=meta['sha256']:raise ValueError('farm source hash mismatch')
    start,end,decision=w.clock(meta['retrieved_at']),w.clock(meta['completed_at']),w.clock(as_of)
    if not meta.get('source') or not start<=end<=decision<=datetime.now(timezone.utc):raise ValueError('farm source not available at decision clock')
    return farm_series(raw),raw,meta,meta_path.read_bytes()

def prepare_nowcast(base,snapshot,farm_raw,target,output,manual=None,as_of=None):
    stamp=as_of or now();decision=w.clock(stamp);target=adapter.target_month(target)
    if decision>w.utcnow() or adapter.decision_clock(stamp).to_period('M')!=target:raise ValueError('prepare requires current Prague target month and an actual available clock')
    output=w.owned(output,output_only=True)
    if output.exists():raise FileExistsError(str(output))
    loaded=adapter.load_bundle(base,ROOT);fresh,capture=current.load_snapshot(snapshot,stamp)
    rows,manual_raw=current.load_manual(manual,stamp) if manual else ([],None)
    agri,raw,metadata,metadata_raw=load_farm(farm_raw,stamp)
    if agri.index.max()-1>=target:raise ValueError('farm source contains current/future monthly observations')
    frames,market=current.extend_frames(loaded,fresh,target,agri,rows)
    # Archive current capture availability in the existing R33 availability list,
    # without treating the farm record as a core/regulated manual observation.
    availability=rows+[{'series':'farm_source_availability','source':metadata['source'],'available_from':metadata['completed_at'],'role':'source availability only; values use unchanged seven-product transform'}]
    prov={'prepared_at':now(),'as_of':stamp,'target':str(target),'base_bundle':str(Path(base).resolve()),'base_provenance':loaded.provenance,'snapshot':capture,
        'farm_source':{'path':str(Path(farm_raw).resolve()),'sha256':sha(raw),'last_observation_month':str(agri.index.max()-1),'completed_at':metadata['completed_at'],'transform':'unchanged national seven-product log-change basket; no frozen file overwritten'},
        'manual_rows':availability,'feature_function':'unchanged cz_struct.assemble_feature_frames','policy':'Frozen training rows preserved; new observations only, missing values remain unavailable. Farm capture clock rechecked at recording.',
        'portable_preparer_sha256':sha(Path(__file__).read_bytes()),'forecast_available':False,'path_available':False}
    output.mkdir(parents=True);(output/'.gitattributes').write_bytes(b'* -text\n')
    for name in ['nowcast','market','sources']:(output/name).mkdir()
    for key,name in adapter.NAMES.items():frames[key].to_csv(output/'nowcast'/name,index_label='period')
    frames['weekly_fuel'].to_csv(output/'nowcast/fuel_weekly_variant_b.csv',index_label='date')
    pd.concat([pd.DataFrame({'ticker':ticker,'observation_date':s.index.strftime('%Y-%m-%d'),'value':s.to_numpy()}) for ticker,s in sorted(market.items()) if ticker in current.MARKET],ignore_index=True).to_csv(output/'market/history_long.csv',index=False)
    (output/'sources/CEN0203B.csv').write_bytes(raw);(output/'sources/CEN0203B.csv.metadata.json').write_bytes(metadata_raw)
    if manual_raw is not None:(output/'manual_inputs.csv').write_bytes(manual_raw)
    write(output/'provenance.json',prov)
    write(output/'MANIFEST.json',{'files':{p.relative_to(output).as_posix():sha(p.read_bytes()) for p in output.rglob('*') if p.is_file()}})
    adapter.load_bundle(output,ROOT)
    w.check_bundle_availability({'mode':'prospective','as_of':stamp},prov)
    return {'status':'prepared','bundle':str(output),'as_of':stamp,'forecast_available':False}
