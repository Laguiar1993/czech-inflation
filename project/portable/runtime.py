"""Local environment and explicit announcement input; no frozen-source writes."""
from contextlib import contextmanager
from pathlib import Path
import hashlib,json,os,sys,subprocess
ROOT=Path(__file__).resolve().parents[1]

def configure():
    os.environ.setdefault('CZ_X13_PATH',str(ROOT/'portable/vendor/x13as/x13as.exe'))
    os.environ.setdefault('CZ_CPI_DB',str(ROOT/'portable/local/czechia.duckdb'))
    os.environ['PYTHONDONTWRITEBYTECODE']='1';os.environ['PYTHONIOENCODING']='utf-8'
    sys.dont_write_bytecode=True

def doctor(bloomberg=False):
    configure()
    from tools.live_bundle_r32.runner import runtime_readiness
    result=runtime_readiness();result['repository']=str(ROOT)
    result['legacy_database_available']=Path(os.environ['CZ_CPI_DB']).is_file()
    result['bloomberg']={'checked':False,'note':'Needed for fresh pulls only; model calculations use archived bundles'}
    if bloomberg:
        # Desktop API service open/stop can block even after a TCP connect timeout.
        # Isolate it so a disconnected or idle Terminal cannot hang the operator.
        cmd=[sys.executable,'-E','-s','-B','-c','from portable.runtime import _bloomberg_probe; _bloomberg_probe()']
        try:
            proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=20)
            if proc.returncode:raise ValueError(proc.stderr.strip() or 'Bloomberg probe failed')
            result['bloomberg']=json.loads(proc.stdout)
        except subprocess.TimeoutExpired:
            result['bloomberg']={'checked':True,'ready':False,'reason':'Bloomberg Desktop API did not respond within 20 seconds; sign into Terminal and retry'}
        except Exception as exc:result['bloomberg']={'checked':True,'ready':False,'reason':str(exc)}
    return result

def _bloomberg_probe():
    import blpapi
    session=None
    try:
        opts=blpapi.SessionOptions();opts.setServerHost('localhost');opts.setServerPort(8194);opts.setConnectTimeout(5000)
        session=blpapi.Session(opts)
        result={'checked':True,'ready':bool(session.start() and session.openService('//blp/refdata'))}
    finally:
        if session is not None:session.stop()
    print(json.dumps(result))

def announcement_rows(path):
    import pandas as pd,numpy as np
    raw=Path(path).read_bytes();data=pd.read_csv(path)
    required={'effective_month','available_from','elec_pct','gas_pct','heat_pct','provenance','source_url'}
    if not required<=set(data) or data.empty:raise ValueError('Announcement CSV lacks required sourced rows')
    data['p']=pd.PeriodIndex(data.effective_month,freq='M')
    if not data.provenance.eq('prospective').all() or data.source_url.isna().any() or data.source_url.str.strip().eq('').any():raise ValueError('New announcements must be prospective and cite source_url')
    stamps=[]
    for value in data.available_from:
        stamp=pd.Timestamp(value)
        if stamp.tzinfo is None:raise ValueError('New announcement availability needs timezone')
        stamps.append(stamp.tz_convert('Europe/Prague').tz_localize(None))
    data['available_from']=stamps
    if data.duplicated(['p','available_from']).any():raise ValueError('Duplicate announcement clock/month after timezone normalization')
    for col in ('elec_pct','gas_pct','heat_pct'):
        data[col]=pd.to_numeric(data[col],errors='raise')
        if not np.isfinite(data[col]).all() or (data[col]<=-100).any():raise ValueError('Energy changes must be finite percentages above -100')
    data['announced_regulated_mm_est_pct']=np.nan
    return data.set_index('p')[['announced_regulated_mm_est_pct','available_from','provenance','elec_pct','gas_pct','heat_pct']]

@contextmanager
def announcements(path=None):
    if path is None:yield;return
    import cz_struct,pandas as pd
    extra=announcement_rows(path);old=cz_struct._ANN
    try:
        base=cz_struct._announcements().copy()
        # New rows append to historical evidence; recorded rows are never edited.
        if extra.index.min()<pd.Period('2027-01','M'):raise ValueError('Portable prospective energy additions begin January 2027; historical amendments require separate research')
        cz_struct._ANN=pd.concat([base,extra]);yield
    finally:cz_struct._ANN=old
