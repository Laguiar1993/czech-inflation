"""Create-only analysis archive; does not estimate or change any forecast model."""
import argparse,hashlib,io,json,re
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from . import analysis

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def clean(v):
    if isinstance(v,dict):return {str(k):clean(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [clean(x) for x in v]
    if isinstance(v,(np.integer,)):return int(v)
    if isinstance(v,(float,np.floating)):return float(v) if np.isfinite(v) else None
    if isinstance(v,(pd.Period,pd.Timestamp,Path)):return str(v)
    return v

def dump(path,value):Path(path).write_text(json.dumps(clean(value),indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8',newline='\n')

def build(prepared,output,rehearsal=False):
    from .inputs import load_prepared
    from .seasonal import adjust_series
    start=datetime.now(timezone.utc);prepared=Path(prepared).resolve();out=Path(output).resolve()
    if not out.is_relative_to(ROOT) or out.exists():raise ValueError('Choose a new analysis directory inside repository')
    inp=load_prepared(prepared,as_of=start.isoformat());levels=inp['levels'];weights=inp['weights'];meta=inp['metadata']
    code={p.relative_to(ROOT).as_posix():sha(p) for p in HERE.iterdir() if p.is_file()}
    code['tools/inflation_monitor/build.py']=sha(ROOT/'tools/inflation_monitor/build.py')
    inputs={p.relative_to(ROOT).as_posix():sha(p) for p in prepared.rglob('*') if p.is_file()}
    out.mkdir(parents=True);(out/'.gitattributes').write_bytes(b'* -text\n')
    sa=pd.DataFrame(index=levels.index,columns=levels.columns,dtype=float);endpoint={};diagnostics={}
    for group in levels:
        try:
            adjusted,diag=adjust_series(levels[group],group,out/'x13'/'full'/group)
            diagnostics[group]=diag
            if diag.get('status')!='ok':continue
            if not adjusted.index.equals(levels.index):raise ValueError('X13 output calendar changed')
            analysis.valid(adjusted);sa[group]=adjusted
        except Exception as exc:
            diagnostics[group]=dict(status='unavailable',method='X-13 failed',quality_flags=['Adjustment unavailable'],error=str(exc));continue
        try:
            adjusted,diag=adjust_series(levels[group].iloc[:-1],group,out/'x13'/'previous_endpoint'/group)
            diagnostics[group]['endpoint_check']=diag
            if diag.get('status')=='ok':
                analysis.valid(adjusted);endpoint[group]=adjusted
        except Exception as exc:
            diagnostics[group]['endpoint_error']=str(exc)
    result=analysis.assemble(levels,sa,weights,meta,diagnostics,endpoint)
    if not any(r['m3'] is not None for r in result['rows']):raise ValueError('No category has usable adjusted momentum; no dashboard may be published')
    result.update(schema='category-momentum-r35/v1',mode='rehearsal' if rehearsal else 'current_analysis',as_of=start.isoformat(),completed_at=datetime.now(timezone.utc).isoformat(),
        prepared=prepared.relative_to(ROOT).as_posix(),provenance=inp['provenance'],diagnostics=diagnostics)
    for name,digest in {**inputs,**code}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Source or code changed during analysis: '+name)
    sa.to_csv(out/'adjusted_levels.csv',index_label='month')
    levels.to_csv(out/'observed_levels.csv',index_label='month')
    dump(out/'momentum.json',result)
    dump(out/'manifest.json',dict(schema='category-momentum-r35/manifest-v1',inputs=inputs,code=code,outputs={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    return dict(output=str(out),month=result['month'],coverage=result['breadth']['coverage'],categories=len(result['rows']),mode=result['mode'])

def _same(actual, expected, label):
    """Compare saved accounting with its replay, allowing only float roundoff."""
    if isinstance(expected,dict):
        if not isinstance(actual,dict) or set(actual)!=set(expected):
            raise ValueError(label+': fields/roster mismatch')
        for key,value in expected.items():_same(actual[key],value,label+'.'+key)
    elif isinstance(expected,list):
        if not isinstance(actual,list) or len(actual)!=len(expected):
            raise ValueError(label+': length/roster mismatch')
        for i,value in enumerate(expected):_same(actual[i],value,f'{label}[{i}]')
    elif isinstance(expected,(float,int)) and not isinstance(expected,bool):
        if isinstance(actual,bool) or not isinstance(actual,(float,int)) or not np.isfinite(actual) or not np.isclose(actual,expected,atol=1e-9,rtol=1e-12):
            raise ValueError(label+': numeric result mismatch')
    elif type(actual) is not type(expected) or actual!=expected:
        raise ValueError(label+': value mismatch')


def _panel(data, expected, label):
    frame=pd.read_csv(io.BytesIO(data),index_col=0,float_precision='round_trip')
    # Compare original tokens before PeriodIndex can silently coerce day labels.
    if list(frame.index)!=list(expected.index.astype(str)):
        raise ValueError(label+': monthly calendar mismatch')
    if list(frame.columns)!=list(expected.columns):
        raise ValueError(label+': column roster mismatch')
    frame.index=expected.index.copy()
    try:return frame.astype(float)
    except (ValueError,TypeError) as exc:raise ValueError(label+': nonnumeric levels') from exc


def _saved_adjustment(files, prefix, diagnostic, observed, start, end):
    """Read hash-checked wrapper evidence only; never invoke the X-13 process."""
    from tools.live_bundle_r32.adapter import required
    if not isinstance(diagnostic,dict) or diagnostic.get('status') not in ('ok','unavailable'):
        raise ValueError(prefix+': invalid adjustment status')
    archived_name=prefix+'/diagnostics.json'
    if diagnostic['status']=='ok' or archived_name in files:
        archived=json.loads(required(files,archived_name))
        base={k:v for k,v in diagnostic.items() if k not in ('endpoint_check','endpoint_error')}
        if base!=archived:raise ValueError(prefix+': archived diagnostic mismatch')
        if archived.get('schema')!='momentum_r35_x13/v1' or archived.get('name')!=observed.name:
            raise ValueError(prefix+': diagnostic identity mismatch')
        clock=pd.Timestamp(archived.get('created_at_utc'))
        if pd.isna(clock) or clock.tzinfo is None or not start<=clock<=end:
            raise ValueError(prefix+': invalid adjustment clock')
    if diagnostic['status']!='ok':return None
    expected_input=dict(n=len(observed),start=str(observed.index[0]),end=str(observed.index[-1]))
    if diagnostic.get('input')!=expected_input:raise ValueError(prefix+': input calendar mismatch')
    source=_panel(required(files,prefix+'/input.csv'),observed.to_frame(),prefix+'/input.csv')
    if not np.array_equal(source.iloc[:,0].to_numpy(),observed.to_numpy()):
        raise ValueError(prefix+': adjustment input differs from observed source')
    lines=required(files,prefix+'/series.d11').decode('ascii').splitlines()
    if len(lines)<3 or lines[0].split()!=['date','series.d11'] or not re.fullmatch(r'[-\s]+',lines[1]):
        raise ValueError(prefix+': invalid D11 header')
    tokens=[line.split() for line in lines[2:] if line.strip()]
    if any(len(t)!=2 for t in tokens) or [t[0] for t in tokens]!=[p.strftime('%Y%m') for p in observed.index]:
        raise ValueError(prefix+': D11 calendar mismatch')
    adjusted=pd.Series([float(t[1].replace('D','E').replace('d','e')) for t in tokens],index=observed.index,name=observed.name)
    return analysis.valid(adjusted)


def _validate_result(d, inp, files, start, end):
    from tools.live_bundle_r32.adapter import required
    levels=inp['levels']
    if d.get('mode') not in ('rehearsal','current_analysis'):raise ValueError('Unsupported analysis mode')
    if d.get('month')!=str(levels.index[-1]):raise ValueError('Analysis month differs from prepared inputs')
    if d.get('provenance')!=inp['provenance']:raise ValueError('Analysis provenance differs from prepared inputs')
    observed=_panel(required(files,'observed_levels.csv'),levels,'observed_levels.csv')
    if not np.array_equal(observed.to_numpy(),levels.to_numpy()):
        raise ValueError('Archived observed levels differ from prepared inputs')
    sa=_panel(required(files,'adjusted_levels.csv'),levels,'adjusted_levels.csv')
    diagnostics=d.get('diagnostics')
    if not isinstance(diagnostics,dict) or set(diagnostics)!=set(levels):
        raise ValueError('Adjustment diagnostic roster mismatch')
    endpoint={}
    for group in levels:
        diag=diagnostics[group]
        if not isinstance(diag,dict) or diag.get('status') not in ('ok','unavailable'):
            raise ValueError(group+': invalid adjustment status')
        if diag['status']=='ok':
            analysis.valid(sa[group])
        elif not sa[group].isna().all():
            raise ValueError(group+': unavailable adjustment has usable values')
        saved=_saved_adjustment(files,'x13/full/'+group,diag,levels[group],start,end)
        if saved is not None and not np.array_equal(saved.to_numpy(),sa[group].to_numpy()):
            raise ValueError(group+': adjusted levels differ from archived D11')
        if 'endpoint_check' in diag:
            if saved is None:raise ValueError(group+': endpoint status without usable full adjustment')
            cut=_saved_adjustment(files,'x13/previous_endpoint/'+group,diag['endpoint_check'],levels[group].iloc[:-1],start,end)
            if cut is not None:endpoint[group]=cut
    # This repeats only deterministic accounting on saved levels, not adjustment.
    expected=clean(analysis.assemble(levels,sa,inp['weights'],inp['metadata'],diagnostics,endpoint))
    if not any(r['m3'] is not None for r in expected['rows']):
        raise ValueError('No category has usable adjusted momentum')
    for key,value in expected.items():
        if key not in d:raise ValueError('Missing analysis result: '+key)
        _same(d[key],value,key)


def load(output):
    from tools.live_bundle_r32.adapter import checked_files,required,safe_path
    from .inputs import load_prepared
    out=Path(output).resolve();m=json.loads((out/'manifest.json').read_bytes())
    if m['schema']!='category-momentum-r35/manifest-v1':raise ValueError('Unsupported manifest schema')
    checked_files(ROOT,m['inputs']);checked_files(ROOT,m['code']);files=checked_files(out,m['outputs']);d=json.loads(required(files,'momentum.json'))
    if d['schema']!='category-momentum-r35/v1':raise ValueError('Unsupported analysis schema')
    start=pd.Timestamp(d['as_of']);end=pd.Timestamp(d['completed_at'])
    if start.tzinfo is None or end.tzinfo is None or not start<=end<=pd.Timestamp.now(tz='UTC'):raise ValueError('Invalid analysis clocks')
    prepared=safe_path(ROOT,d['prepared']);inp=load_prepared(prepared,as_of=d['as_of'])
    if (prepared/'MANIFEST.json').relative_to(ROOT).as_posix() not in m['inputs']:raise ValueError('Prepared source manifest not pinned')
    _validate_result(d,inp,files,start,end)
    return d

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--rehearsal',action='store_true')
    a=p.parse_args();print(json.dumps(build(a.prepared,a.output,a.rehearsal)))
if __name__=='__main__':main()
